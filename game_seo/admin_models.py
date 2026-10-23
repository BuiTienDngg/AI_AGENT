"""Read the installed Codex model catalog without network calls or auth secrets."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
try:
    import tomllib
except ImportError:  # Python 3.10, supported by the original project.
    import tomli as tomllib

LEVELS = ('low', 'medium', 'high', 'xhigh', 'max')


def codex_home():
    return Path(os.environ.get('CODEX_HOME') or Path.home() / '.codex')


def catalog(cfg, home=None):
    home = Path(home) if home else codex_home()
    try:
        local = tomllib.loads((home / 'config.toml').read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        local = {}
    current = cfg.get('codex_model') or local.get('model') or ''
    effort = cfg.get('model_reasoning_effort') or local.get('model_reasoning_effort') or 'medium'
    try:
        cached = json.loads((home / 'models_cache.json').read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        cached = {}
    models, seen = [], set()
    for raw in cached.get('models', []):
        slug = raw.get('slug', '')
        if not isinstance(slug, str) or not re.fullmatch(r'gpt-[A-Za-z0-9._-]{1,90}', slug):
            continue
        if slug in seen or raw.get('visibility') != 'list' or 'image' not in raw.get('input_modalities', []):
            continue
        levels = [r.get('effort') for r in raw.get('supported_reasoning_levels', [])
                  if isinstance(r, dict) and r.get('effort') in LEVELS]
        models.append({'id': slug, 'label': raw.get('display_name') or slug,
                       'efforts': levels or list(LEVELS),
                       'default_effort': raw.get('default_reasoning_level', 'medium')})
        seen.add(slug)
    if current and current not in seen:
        models.insert(0, {'id': current, 'label': current + ' (cấu hình hiện tại)',
                          'efforts': list(LEVELS), 'default_effort': effort})
    return {'models': models, 'model': current, 'reasoning_effort': effort}


def execution_config(cfg, payload, home=None):
    if not isinstance(payload, dict):
        raise ValueError('Cấu hình model không hợp lệ.')
    options = catalog(cfg, home)
    model = payload.get('model', options['model'])
    effort = payload.get('reasoning_effort', options['reasoning_effort'])
    if not isinstance(model, str) or not re.fullmatch(r'gpt-[A-Za-z0-9._-]{1,90}', model):
        raise ValueError('Nhập đúng ID model GPT, ví dụ gpt-6-sol.')
    entry = next((r for r in options['models'] if r['id'] == model), None)
    allowed = entry['efforts'] if entry else LEVELS
    if effort not in allowed:
        raise ValueError('Mức suy luận không được model này hỗ trợ: ' + str(effort))
    return {**cfg, 'codex_model': model, 'model_reasoning_effort': effort}
