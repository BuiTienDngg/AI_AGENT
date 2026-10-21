from __future__ import annotations
import json
import math
import shutil
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from .core import save_json, utc_now


def require_ffmpeg():
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        raise RuntimeError('FFmpeg and FFprobe not found. Install FFmpeg and add its bin directory to PATH.')


def video_duration(path: Path):
    cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'json', str(path)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=35, check=True)
    return float(json.loads(proc.stdout)['format']['duration'])


def extract_frames(video: Path, workdir: Path, cfg: dict):
    require_ffmpeg()
    video = Path(video).expanduser().resolve()
    if not video.is_file():
        raise FileNotFoundError(video)
    workdir = Path(workdir)
    folder = workdir / 'frames'
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob('FRAME*.jpg'):
        old.unlink()
    seconds = video_duration(video)
    if seconds <= 0 or seconds > cfg['max_video_minutes'] * 60:
        raise ValueError(f'Video duration {seconds:.1f}s outside allowed range. Adjust max_video_minutes in config.json.')
    n = max(4, min(48, int(cfg['frames_per_video'])))
    # Sample throughout the entire video, not just its beginning.
    fps = n / max(1.0, seconds)
    vf = f'fps={fps:.8f},scale=960:540:force_original_aspect_ratio=decrease'
    cmd = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-i', str(video), '-vf', vf, '-frames:v', str(n), '-q:v', '3', str(folder / 'FRAME%03d.jpg')]
    subprocess.run(cmd, check=True, timeout=max(90, min(300, int(seconds * 2))))
    paths = sorted(folder.glob('FRAME*.jpg'))
    if len(paths) < 2:
        raise RuntimeError('Not enough frames extracted; verify MP4 is playable.')
    frames = []
    for i, path in enumerate(paths):
        t = round(min(seconds, (i + 0.5) / fps), 1)
        frames.append({'frame_id': f'FRAME{i + 1:03}', 'timestamp_seconds_approx': t, 'path': str(path.resolve())})
    sheet_folder = workdir / 'contact_sheets'
    sheet_folder.mkdir(exist_ok=True)
    sheets = []
    per_sheet = 8
    tile_w, tile_h = 470, 305
    font = ImageFont.load_default()
    for start in range(0, len(frames), per_sheet):
        subset = frames[start:start + per_sheet]
        out = Image.new('RGB', (tile_w * 2, tile_h * math.ceil(len(subset) / 2)), '#f4f5f6')
        draw = ImageDraw.Draw(out)
        for j, frame in enumerate(subset):
            x = (j % 2) * tile_w
            y = (j // 2) * tile_h
            with Image.open(frame['path']) as im:
                im.thumbnail((tile_w - 16, tile_h - 38))
                out.paste(im.convert('RGB'), (x + (tile_w - im.width)//2, y + 6))
            draw.text((x + 12, y + tile_h - 25), f"{frame['frame_id']} / ~{frame['timestamp_seconds_approx']}s", fill='#17191c', font=font)
        sheet = sheet_folder / f'contact_{len(sheets)+1:02}.jpg'
        out.save(sheet, quality=88)
        sheets.append(str(sheet.resolve()))
    manifest = {'source_video': str(video), 'duration_seconds': round(seconds, 2), 'frames': frames, 'contact_sheets': sheets, 'created_at': utc_now()}
    save_json(workdir / 'frames.json', manifest)
    return manifest
