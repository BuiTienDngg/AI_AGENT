"""Structured game-object evidence and an optional owner review before writing."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone

from .core import load_json, save_json, utc_now


CATEGORIES = ('player', 'enemy', 'obstacle', 'collectible', 'power_up', 'terrain',
              'decoration', 'interactive', 'ui', 'other')


class ObjectReviewPending(RuntimeError):
    pass


def fingerprint(analysis, frames):
    payload = {'analysis': analysis, 'source_video': frames.get('source_video'),
               'frames_created_at': frames.get('created_at'), 'frames': frames.get('frames', [])}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()


def normalize_objects(rows, frames, confirmed=False):
    if not isinstance(rows, list):
        raise ValueError('Danh sách đối tượng phải là một mảng JSON.')
    valid_frames = {f['frame_id'] for f in frames.get('frames', [])}
    result, used_ids = [], set()
    for index, raw in enumerate(rows, 1):
        if not isinstance(raw, dict) or not isinstance(raw.get('name'), str) or not raw['name'].strip():
            raise ValueError(f'Đối tượng {index} cần có tên.')
        frame_ids = raw.get('frame_ids', [])
        if not isinstance(frame_ids, list) or not all(isinstance(x, str) for x in frame_ids):
            raise ValueError(f'Frame IDs của đối tượng {index} phải là danh sách chuỗi.')
        unknown_frames = set(frame_ids) - valid_frames
        if confirmed and unknown_frames:
            raise ValueError(f'Frame không tồn tại: {", ".join(sorted(unknown_frames))}')
        object_id = raw.get('id') or f'OBJ{index:03}'
        if not isinstance(object_id, str) or object_id in used_ids:
            raise ValueError('ID đối tượng phải là chuỗi và không được trùng nhau.')
        used_ids.add(object_id)
        confidence = raw.get('confidence', 'low')
        if confidence not in ('high', 'medium', 'low'):
            confidence = 'low'
        needs_confirmation = bool(raw.get('needs_confirmation', False) or str(raw.get('question', '')).strip()
                                  or unknown_frames or confidence != 'high' or not frame_ids)
        result.append({
            'id': object_id, 'name': raw['name'].strip(),
            'category': raw.get('category') if raw.get('category') in CATEGORIES else 'other',
            'appearance': str(raw.get('appearance', '')).strip(),
            'observed_behavior': str(raw.get('observed_behavior', '')).strip(),
            **{key:str(raw.get(key,'')).strip() for key in ('name_vi','appearance_vi','observed_behavior_vi')},
            'frame_ids': list(dict.fromkeys(x for x in frame_ids if x in valid_frames)),
            'confidence': 'high' if confirmed else confidence,
            'needs_confirmation': False if confirmed else needs_confirmation,
            'question': '' if confirmed else str(raw.get('question', '')).strip(),
            **({'question_vi': '' if confirmed else str(raw.get('question_vi', '')).strip()}
               if 'question_vi' in raw else {}),
            'evidence': 'developer_confirmed' if confirmed else 'video_observed',
            'include_in_article': raw.get('include_in_article', True) is not False,
            'publishable': bool(confirmed or not needs_confirmation),
        })
    return result


def archive_inventory(workdir, previous):
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')
    save_json(Path(workdir) / 'object_reviews' / f'game_objects_{stamp}.json', previous)


def prepare_inventory(workdir, analysis, frames):
    workdir = Path(workdir)
    path = workdir / 'game_objects.json'
    expected = fingerprint(analysis, frames)
    if path.exists():
        previous = load_json(path)
        if previous.get('input_fingerprint') == expected:
            if previous.get('review', {}).get('state') != 'confirmed' and not previous.get('review', {}).get('owner_paused'):
                refreshed = normalize_objects(previous.get('objects', []), frames)
                if refreshed != previous.get('objects'):
                    previous['objects'] = refreshed
                    save_json(path, previous)
            return previous
        archive_inventory(workdir, previous)
    raw_rows = analysis.get('game_objects', [])
    if not isinstance(raw_rows, list):
        raw_rows = []
    rows = normalize_objects([row for row in raw_rows
                              if isinstance(row, dict) and isinstance(row.get('name'), str) and row['name'].strip()], frames)
    inventory = {'version': 1, 'input_fingerprint': expected, 'objects': rows,
                 'review': {'state': 'pending', 'updated_at': utc_now()},
                 'note': 'Owner-confirmed gameplay facts are product input, not academic sources. '
                         'Only included, publishable objects may be stated as facts in the article.'}
    save_json(path, inventory)
    return inventory


def review_reasons(inventory, cfg):
    reasons = []
    rows = inventory['objects']
    minimum = int(cfg.get('min_detected_objects', 8))
    if len(rows) < minimum:
        reasons.append(f'AI mới liệt kê {len(rows)} đối tượng (ngưỡng gợi ý: {minimum}). Không cần thêm đối tượng không có thật.')
    uncertain = [x['name'] for x in rows if x.get('needs_confirmation') or x.get('question')]
    if uncertain:
        reasons.append('Cần xác nhận: ' + ', '.join(uncertain))
    return reasons


def save_review(workdir, inventory, rows, state):
    if state not in ('confirmed', 'skipped', 'pending'):
        raise ValueError('Invalid object review state')
    workdir = Path(workdir)
    frames = load_json(workdir / 'frames.json')
    if state == 'confirmed' and not rows:
        raise ValueError('Hãy nhập ít nhất một đối tượng, hoặc chọn bỏ qua.')
    clean = normalize_objects(rows, frames, confirmed=(state == 'confirmed'))
    if state == 'pending':
        for row in clean:
            row['publishable'] = False
    path = workdir / 'game_objects.json'
    if path.exists():
        archive_inventory(workdir, load_json(path))
    updated = {**inventory, 'objects': clean, 'review': {'state': state, 'updated_at': utc_now(), 'owner_paused': state == 'pending'}}
    save_json(path, updated)
    return updated


def ensure_inventory(workdir, analysis, frames, cfg, mode=None):
    inventory = prepare_inventory(workdir, analysis, frames)
    mode = mode or cfg.get('object_review_mode', 'auto')
    if mode == 'web':
        from .web_review import require_web_review
        return require_web_review(workdir, inventory, analysis)
    if mode not in ('auto', 'always', 'never'):
        raise ValueError('Object review mode must be auto, always or never.')
    if mode == 'never' or (mode != 'always' and inventory['review']['state'] in ('confirmed', 'skipped')):
        return inventory
    reasons = review_reasons(inventory, cfg)
    if mode == 'always' or reasons or inventory['review'].get('owner_paused'):
        print('  Mở form kiểm tra đối tượng trong game...', flush=True)
        from .object_form import open_object_form
        try:
            open_object_form(workdir, inventory, reasons)
        except (ImportError, RuntimeError) as exc:
            raise ObjectReviewPending(f'Không mở được form: {exc}. Dùng `python run.py objects --run-dir "{workdir}" --from-json objects.json`.') from exc
        inventory = load_json(Path(workdir) / 'game_objects.json')
        if inventory['review']['state'] == 'pending':
            raise ObjectReviewPending('Đã lưu danh sách nháp. Chạy lại với --resume hoặc dùng lệnh objects để điền tiếp.')
    return inventory


def inventory_digest(inventory):
    rows = [{k: v for k, v in row.items() if k not in ('question', 'question_vi','name_vi','appearance_vi','observed_behavior_vi')} for row in inventory.get('objects', [])]
    return hashlib.sha256(json.dumps(rows, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()


def draft_needs_refresh(workdir, inventory):
    path = Path(workdir) / 'article_provenance.json'
    if not (Path(workdir) / 'article.json').exists():
        return True
    if not inventory.get('objects') and not path.exists():
        return False  # Keep legacy drafts until there is actual object input to incorporate.
    meta = load_json(path, default={})
    return (meta.get('objects_sha256') != inventory_digest(inventory)
            or (owner_input_digest(workdir) is not None
                and meta.get('owner_input_sha256') != owner_input_digest(workdir)))


def owner_input_digest(workdir):
    files = {name: load_json(Path(workdir) / name) for name in ('game_brief.json', 'owner_answers.json')
             if (Path(workdir) / name).is_file()}
    if not files:
        return None
    return hashlib.sha256(json.dumps(files, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()


def record_article_objects(workdir, inventory):
    save_json(Path(workdir) / 'article_provenance.json',
              {'objects_sha256': inventory_digest(inventory),
               'owner_input_sha256': owner_input_digest(workdir), 'updated_at': utc_now()})
