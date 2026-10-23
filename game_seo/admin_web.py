"""Loopback-only administration API and offline frontend for the existing pipeline."""
from __future__ import annotations

import hmac
import json
import math
import secrets
import shutil
import subprocess
import uuid
import io
import zipfile
from pathlib import Path
from urllib.parse import urlsplit

from flask import Flask, abort, jsonify, render_template, request, send_file
from werkzeug.exceptions import HTTPException

from .admin_jobs import Jobs
from .admin_models import catalog, execution_config
from .admin_store import Store
from .core import ROOT, canonical_url, load_json, utc_now
from .web_review import add_object, save_answers

VIDEO_EXTENSIONS = {'.mp4', '.mov', '.mkv', '.webm', '.avi', '.m4v'}
MAX_UPLOAD = 4 * 1024 ** 3


def safe_json(path, default=None):
    try:
        return load_json(path, default={} if default is None else default)
    except (OSError, ValueError):
        return {} if default is None else default


def validate_fields(form):
    fields = {}
    for name in ('name', 'site_url', 'game_url', 'idea_origin', 'story', 'game_style', 'controls_pc', 'controls_mobile'):
        value = form.get(name, '')
        if not isinstance(value, str) or len(value) > 12000:
            raise ValueError('Nội dung mỗi ô không được vượt quá 12.000 ký tự.')
        fields[name] = value.strip()
    required = {'name': 'Tên game', 'site_url': 'Site game', 'game_url': 'URL chơi game',
                'controls_pc': 'Điều khiển PC', 'controls_mobile': 'Điều khiển điện thoại'}
    for name, label in required.items():
        if not fields[name]:
            raise ValueError(label + ' là bắt buộc.')
    if len(fields['name']) > 160:
        raise ValueError('Tên game tối đa 160 ký tự.')
    for key in ('site_url', 'game_url'):
        if not canonical_url(fields[key]):
            raise ValueError('URL cần đầy đủ https:// hoặc http://, không chứa tài khoản/mật khẩu.')
    return fields


def probe_gameplay(path):
    proc = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0',
                           '-show_entries', 'stream=codec_type:format=duration', '-of', 'json', str(path)],
                          capture_output=True, text=True, encoding='utf-8', check=True, timeout=35)
    info = json.loads(proc.stdout)
    if not info.get('streams'):
        raise ValueError('File không có hình ảnh video.')
    return float(info['format']['duration'])


def create_app(data_dir=None, runs_dir=None, *, probe=probe_gameplay, process_factory=None):
    data = Path(data_dir or ROOT / 'local_admin_data').resolve()
    runs = Path(runs_dir or ROOT / 'runs').resolve()
    app = Flask(__name__, template_folder=str(ROOT / 'admin_ui'), static_folder=str(ROOT / 'admin_ui' / 'static'))
    app.config.update(MAX_CONTENT_LENGTH=MAX_UPLOAD, MAX_FORM_MEMORY_SIZE=256 * 1024)
    store = Store(data)
    store.backfill_answers(runs)
    jobs = Jobs(store, runs, **({'process_factory': process_factory} if process_factory else {}))
    app.extensions.update(office_store=store, office_jobs=jobs)
    token = secrets.token_urlsafe(32)
    from .account_web import install_accounts
    install_accounts(app, store, token)

    @app.before_request
    def local_only():
        if request.host.split(':')[0].lower() not in ('localhost', '127.0.0.1'):
            abort(403, description='Chỉ truy cập từ máy local.')
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            provided = request.headers.get('X-Office-Token', '')
            if not hmac.compare_digest(provided, token):
                abort(403, description='Phiên trang đã thay đổi. Hãy tải lại trang.')
            if request.headers.get('Origin') and request.headers['Origin'].rstrip('/') != request.host_url.rstrip('/'):
                abort(403, description='Yêu cầu khác nguồn bị từ chối.')

    @app.after_request
    def headers(response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; "
            "media-src 'self' blob:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'")
        return response

    @app.errorhandler(Exception)
    def error(exc):
        if isinstance(exc, HTTPException):
            return jsonify(error='Video quá lớn. Giới hạn 4 GB.' if exc.code == 413 else exc.description), exc.code
        if isinstance(exc, (ValueError, KeyError)):
            return jsonify(error=str(exc).strip("'")), 400
        app.logger.exception('Local admin error')
        return jsonify(error='Không thực hiện được thao tác: ' + str(exc)), 500

    def get_game(key):
        game = store.game(key)
        if not game:
            abort(404, description='Không tìm thấy game.')
        return game

    def get_job(key):
        job = store.job(key)
        if not job:
            abort(404, description='Không tìm thấy lượt chạy.')
        return job

    def idle_job(key):
        job = get_job(key)
        if key in jobs.active or job['status'] in ('running', 'stopping'):
            abort(409, description='Dừng lượt chạy trước khi sửa câu trả lời.')
        return job

    def present_job(job):
        result = dict(job)
        actual_cfg = safe_json(jobs.workdir(job)/'admin_config.json')
        execution = job['data'].get('execution')
        if not execution:
            cfg = safe_json(jobs.workdir(job) / 'admin_config.json')
            execution = {'model': cfg.get('codex_model'), 'reasoning_effort': cfg.get('model_reasoning_effort')}
        result['execution'] = execution
        if actual_cfg.get('api_provider'):
            result['execution'] = {'model':actual_cfg.get('codex_model'),
                                   'reasoning_effort':actual_cfg.get('model_reasoning_effort'),'provider':'API'}
        activity = jobs.active.get(job['id'])
        if activity and activity.get('task') == 'questions_vi':
            result['status'] = 'stopping' if activity['stopped'] else 'translating'
        return result

    def run_path(name):
        if not name or name in ('.', '..') or '/' in name or '\\' in name:
            abort(404)
        path = (runs / name).resolve()
        if path.parent != runs or not path.is_dir():
            abort(404)
        return path

    def docx_files(work):
        files = safe_json(work / 'export_manifest.json').get('files', {})
        result = {}
        for kind in ('docx_en', 'docx_vi'):
            raw = files.get(kind)
            if not isinstance(raw, str):
                continue
            target = Path(raw)
            if not target.is_absolute():
                target = work / target
            if not target.is_file():
                target = work / 'output' / Path(raw).name
            target = target.resolve()
            if target.parent == (work / 'output').resolve() and target.suffix.lower() == '.docx' and target.is_file():
                result[kind] = target
        return result

    def history():
        linked = {j['run_name']: present_job(j) for j in store.jobs()}
        result = []
        for work in runs.iterdir():
            if not work.is_dir() or work.is_symlink():
                continue
            analysis = safe_json(work / 'analysis.json')
            article = safe_json(work / 'article.json')
            files = docx_files(work)
            job = linked.get(work.name)
            if not job and not (analysis or files):
                continue
            qa = safe_json(work / 'qa_report.json')
            state = job['status'] if job else ('completed' if len(files) == 2 else 'legacy')
            result.append({'run_name': work.name, 'name': job['data']['name'] if job else article.get('title') or analysis.get('game_title', work.name),
                           'status': state, 'job_id': job['id'] if job else None,
                           'game_id': job['game_id'] if job else None,
                           'updated': job['updated'] if job else utc_stamp(work),
                           'files': list(files), 'qa': qa.get('summary', {}),
                           'result_available': len(files)==2 and (work/'result'/'result_manifest.json').is_file(),
                           'usage': safe_json(work / 'token_usage.json').get('measured_totals', {}),
                           'quota': safe_json(work / 'quota_usage.json').get('summary', {})})
            result[-1]['execution'] = job['execution'] if job else {}
        return sorted(result, key=lambda item: item['updated'], reverse=True)

    @app.get('/')
    def index():
        return render_template('index.html', office_token=token)

    @app.get('/api/state')
    def state():
        cfg = safe_json(ROOT / 'config.json')
        return jsonify(games=store.games(), jobs=[present_job(j) for j in store.jobs()], history=history(),
                       settings={**catalog(cfg), 'features': {'question_translation': True},
                                 'capacity_policy_enabled': app.extensions['office_capacity'].settings()['enabled'],
                                 'frames': cfg.get('frames_per_video', 16),
                                 'max_minutes': cfg.get('max_video_minutes', 45),
                                 'dependencies': {key: bool(shutil.which(key)) for key in ('ffmpeg', 'ffprobe', 'codex')}})

    def save_game(key=None):
        old = get_game(key) if key else None
        fields = validate_fields(request.form)
        upload = request.files.get('video')
        new_file = None
        try:
            source = None
            if not old and not (upload and upload.filename) and request.form.get('import_run'):
                source_work = run_path(request.form['import_run'])
                source = Path(safe_json(source_work / 'frames.json').get('source_video', ''))
                if not source.is_file():
                    raise ValueError('Video của lượt cũ không còn ở đường dẫn ban đầu. Hãy kéo thả video vào form.')
            if (upload and upload.filename) or source:
                filename = upload.filename if upload and upload.filename else source.name
                extension = Path(filename).suffix.lower()
                if extension not in VIDEO_EXTENSIONS:
                    raise ValueError('Chọn video MP4, MOV, MKV, WEBM, AVI hoặc M4V.')
                folder = data / 'videos'
                folder.mkdir(exist_ok=True)
                new_file = folder / (uuid.uuid4().hex + extension)
                if source:
                    if source.stat().st_size > MAX_UPLOAD:
                        raise ValueError('Video vượt quá giới hạn 4 GB.')
                    shutil.copyfile(source, new_file)
                    fields['source_run'] = request.form['import_run']
                else:
                    upload.save(new_file)
                try:
                    duration = probe(new_file)
                    limit = safe_json(ROOT / 'config.json').get('max_video_minutes', 45) * 60
                    if not math.isfinite(duration) or not 0 < duration <= limit:
                        raise ValueError(f'Video cần có thời lượng từ 1 giây đến {limit // 60} phút.')
                except (OSError, subprocess.SubprocessError, KeyError, TypeError, json.JSONDecodeError) as exc:
                    raise ValueError('Không đọc được video. Kiểm tra FFprobe và chọn file video phát được.') from exc
                fields.update(video_path=str(new_file), video_name=Path(filename).name,
                              video_bytes=new_file.stat().st_size, video_seconds=round(duration, 2))
            elif old:
                fields.update({k: v for k, v in old['data'].items() if k.startswith('video_')})
                if not Path(fields.get('video_path', '')).is_file():
                    raise ValueError('Video cũ không còn tồn tại. Hãy chọn lại video.')
            else:
                raise ValueError('Video gameplay là bắt buộc.')
            if old:
                if not request.form.get('revision'):
                    raise ValueError('Thiếu phiên bản game. Hãy tải lại trang.')
                fields['_expected_revision'] = request.form['revision']
            game = store.save_game(fields, key)
            return jsonify(game=game), 200 if old else 201
        except Exception:
            if new_file and new_file.exists():
                new_file.unlink()
            raise

    @app.post('/api/games')
    def create_game():
        return save_game()

    @app.post('/api/games/<key>')
    def edit_game(key):
        return save_game(key)

    @app.delete('/api/games/<key>')
    def delete_game(key):
        with jobs.lock:
            get_game(key)
            if any(j['game_id'] == key and (j['status'] in ('running', 'stopping', 'queued', 'waiting_for_capacity') or j['id'] in jobs.active)
                   for j in store.jobs()):
                abort(409, description='Dừng lượt chạy của game trước khi xóa.')
            store.delete_game(key)  # Keep source videos and run history; no destructive filesystem delete.
        return jsonify(ok=True)

    @app.post('/api/games/<key>/run')
    def start(key):
        body = request.get_json(silent=True) or {}
        cfg = execution_config(load_json(ROOT / 'config.json'), body)
        request_key = request.headers.get('Idempotency-Key') or body.get('idempotency_key')
        if request_key and (not isinstance(request_key,str) or len(request_key)>100):
            raise ValueError('Idempotency key không hợp lệ.')
        return jsonify(job=jobs.start(get_game(key), cfg, request_key=request_key)), 202

    @app.post('/api/jobs/<key>/resume')
    def resume(key):
        return jsonify(job=jobs.resume(get_job(key))), 202

    @app.post('/api/jobs/<key>/stop')
    def stop(key):
        get_job(key)
        jobs.stop(key)
        return jsonify(ok=True)

    @app.get('/api/jobs/<key>')
    def detail(key):
        job = get_job(key)
        work = jobs.workdir(job)
        log = ''
        if (work / 'admin.log').is_file():
            with (work / 'admin.log').open('rb') as handle:
                handle.seek(0, 2)
                handle.seek(max(0, handle.tell() - 64000))
                log = handle.read().decode('utf-8', errors='replace')
        questions = safe_json(work / 'owner_questions.json')
        from .question_translation import set_translation, set_display_translations
        for question in questions.get('questions', []):
            set_translation(question)
            set_display_translations(question)
        return jsonify(job=present_job(job), log=log, questions=questions,
                       question_translation=safe_json(work / 'question_translation_result.json'),
                       qa=safe_json(work / 'qa_report.json'), files=list(docx_files(work)),
                       result_available=len(docx_files(work))==2 and (work/'result'/'result_manifest.json').is_file(),
                       usage=safe_json(work / 'token_usage.json'),
                       quota=safe_json(work / 'quota_usage.json'),
                       answer_history=[safe_json(f) for f in sorted((work / 'answer_history').glob('*.json'),
                                      key=lambda f: f.stat().st_mtime, reverse=True)][:30])

    @app.post('/api/jobs/<key>/translate-questions')
    def translate_questions(key):
        return jsonify(job=present_job(jobs.translate_questions(get_job(key)))), 202

    @app.post('/api/jobs/<key>/answers')
    def answers(key):
        with jobs.lock:
            job = idle_job(key)
            body = request.get_json() or {}
            expected = body.get('version')
            current = safe_json(jobs.workdir(job) / 'owner_questions.json').get('version')
            if expected is not None and expected != current:
                abort(409, description='Câu trả lời đã thay đổi ở tab khác. Hãy tải lại trước khi lưu.')
            result = save_answers(jobs.workdir(job), body.get('questions', []), approve=body.get('approve') is True)
            store.remember_answers(job['game_id'], result['questions'], allow_downgrade=True)
            if job['status'] == 'completed':
                from .objects import draft_needs_refresh
                inventory = load_json(jobs.workdir(job) / 'game_objects.json')
                if draft_needs_refresh(jobs.workdir(job), inventory):
                    store.update_job(key, 'waiting', 'Câu trả lời đã thay đổi. Duyệt và chạy tiếp để cập nhật bài; Word cũ vẫn được giữ.')
        return jsonify(questions=result)

    @app.post('/api/jobs/<key>/objects')
    def manual_object(key):
        with jobs.lock:
            job = idle_job(key)
            body = request.get_json() or {}
            result = add_object(jobs.workdir(job), body.get('name'), body.get('behavior'),
                                body.get('appearance', ''), body.get('category', 'other'))
            store.remember_answers(job['game_id'], result['questions'])
            if job['status'] == 'completed':
                store.update_job(key, 'waiting', 'Có đối tượng mới. Duyệt và chạy tiếp để cập nhật bài.')
        return jsonify(questions=result)

    @app.get('/api/games/<key>/answers')
    def saved_answers(key):
        get_game(key)
        return jsonify(entries=store.answers_for_game(key))

    @app.post('/api/games/<key>/answers/<answer_key>')
    def edit_saved_answer(key, answer_key):
        get_game(key)
        body = request.get_json() or {}
        row = store.update_saved_answer(key, answer_key, body.get('answer'),
                                        body.get('decision'), body.get('updated'))
        return jsonify(entry=row)

    @app.get('/api/runs/<name>/download/<kind>')
    def download(name, kind):
        files = docx_files(run_path(name))
        if kind not in files:
            abort(404, description='File Word chưa được tạo.')
        return send_file(files[kind], as_attachment=True, download_name=files[kind].name)

    @app.get('/api/runs/<name>/result.zip')
    def download_result(name):
        work = run_path(name)
        folder = work/'result'
        if folder.is_symlink() or not folder.is_dir() or len(docx_files(work))!=2:
            abort(404,description='Bộ result chưa được tạo.')
        manifest = safe_json(folder/'result_manifest.json')
        if set(manifest.get('documents',{}))!={'docx_en','docx_vi'}:
            abort(404,description='Bộ result chưa đầy đủ.')
        names = [row['file'] for row in manifest['documents'].values()]
        names += [row['file'] for row in manifest.get('images',[])]
        names += ['image_names.csv','IMAGE_CREDITS.txt','result_manifest.json']
        root = folder.resolve()
        if root.parent != work.resolve():
            abort(404)
        paths = []
        for relative in dict.fromkeys(names):
            file = (root/relative).resolve()
            if Path(relative).is_absolute() or not file.is_relative_to(root) or not file.is_file() or (root/relative).is_symlink():
                abort(404,description='Bộ result thiếu file hoặc đường dẫn không hợp lệ.')
            paths.append((file,file.relative_to(root).as_posix()))
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer,'w',compression=zipfile.ZIP_DEFLATED) as archive:
            for file,relative in paths:
                archive.write(file,'result/'+relative)
        buffer.seek(0)
        return send_file(buffer,mimetype='application/zip',as_attachment=True,download_name=work.name+'_result.zip')

    @app.get('/api/runs/<name>/brief')
    def import_brief(name):
        work = run_path(name)
        brief = safe_json(work / 'game_brief.json')
        article = safe_json(work / 'article.json')
        analysis = safe_json(work / 'analysis.json')
        fields = {key: brief.get(key, '') for key in inputs_keys()}
        fields['name'] = brief.get('name') or article.get('title') or analysis.get('game_title', '')
        fields['site_url'] = brief.get('site_url') or safe_json(ROOT / 'config.json').get('brand_website', '')
        source = Path(safe_json(work / 'frames.json').get('source_video', ''))
        available = source.is_file() and source.suffix.lower() in VIDEO_EXTENSIONS
        return jsonify(fields=fields, run_name=name, video_available=available,
                       video_name=source.name if available else '')

    @app.get('/api/jobs/<key>/frame/<frame_id>')
    def frame(key, frame_id):
        work = jobs.workdir(get_job(key))
        manifest = safe_json(work / 'frames.json')
        entry = next((f for f in manifest.get('frames', []) if f.get('frame_id') == frame_id), None)
        if not entry:
            abort(404)
        path = Path(entry['path']).resolve()
        if path.parent != (work / 'frames').resolve() or path.suffix.lower() != '.jpg' or not path.is_file():
            abort(404)
        return send_file(path)

    return app


def utc_stamp(path):
    from datetime import datetime, timezone
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(timespec='seconds')


def inputs_keys():
    return ('name', 'site_url', 'game_url', 'idea_origin', 'story', 'game_style', 'controls_pc', 'controls_mobile')
