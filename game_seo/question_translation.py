"""Bilingual display data; translations never become confirmed gameplay facts."""
from __future__ import annotations

import hashlib
import re
import uuid
from pathlib import Path

from .core import load_json
from .web_review import atomic_json

VI_LETTERS = re.compile('[ăâđêôơưĂÂĐÊÔƠƯ\u1ea0-\u1ef9]')
DISPLAY_FIELDS = ('name','appearance','answer')


def set_display_translations(question, supplied=None):
    supplied = supplied or {}
    for field in DISPLAY_FIELDS:
        text = question.get(field,'')
        key = field+'_vi'
        fingerprint = key+'_source_sha256'
        if key in supplied:
            value = supplied[key].strip()
        elif question.get(fingerprint)==text_hash(text):
            continue
        else:
            value = text if VI_LETTERS.search(text) else ''
        question[key] = value
        question[fingerprint] = text_hash(text) if value else ''
    return question


def text_hash(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def set_translation(question, vietnamese=None):
    text = question.get('question', '')
    if vietnamese is None and question.get('question_vi_source_sha256') == text_hash(text):
        return question
    translated = vietnamese.strip() if isinstance(vietnamese, str) else ''
    if not translated and VI_LETTERS.search(text):
        translated = text
    question['question_vi'] = translated
    question['question_vi_source_sha256'] = text_hash(text) if translated else ''
    return question


def pending_translations(workdir):
    doc = load_json(Path(workdir) / 'owner_questions.json', default={'questions': []})
    result = []
    for q in doc['questions']:
        for field in ('question',*DISPLAY_FIELDS):
            text = q.get(field,'')
            if text and (not q.get(field+'_vi') or q.get(field+'_vi_source_sha256')!=text_hash(text)):
                result.append({'id':q['id'] if field=='question' else q['id']+'::'+field,
                               'question':text,'owner_id':q['id'],'field':field})
    return result


def translate_questions(workdir, cfg):
    workdir = Path(workdir)
    doc = load_json(workdir / 'owner_questions.json')
    changed = False
    for question in doc['questions']:
        before = dict(question)
        set_translation(question)
        set_display_translations(question)
        changed |= before != question
    if changed:
        doc['version'] = uuid.uuid4().hex
        atomic_json(workdir / 'owner_questions.json', doc)
    pending = pending_translations(workdir)
    if not pending:
        return 0
    request = [{'id': q['id'], 'question': q['question']} for q in pending]
    atomic_json(workdir / 'question_translation_request.json', {'questions': request})
    from .runner import codex_call
    result = codex_call('questions_vi', workdir, cfg)
    translations = result.get('translations')
    if not isinstance(translations, list) or len(translations) != len(request):
        raise ValueError('Bản dịch không khớp số câu hỏi. Chưa thay đổi câu trả lời.')
    expected = {q['id']: q for q in pending}
    seen = set()
    for row in translations:
        if not isinstance(row, dict) or row.get('id') not in expected or row['id'] in seen:
            raise ValueError('ID câu hỏi trong bản dịch không hợp lệ.')
        if not isinstance(row.get('question_vi'), str) or not row['question_vi'].strip():
            raise ValueError('Bản dịch tiếng Việt bị trống.')
        seen.add(row['id'])
    current = load_json(workdir / 'owner_questions.json')
    lookup = {q['id']: q for q in current['questions']}
    for row in translations:
        entry = expected[row['id']]
        target = lookup.get(entry['owner_id'])
        if not target or target.get(entry['field'],'') != entry['question']:
            raise ValueError('Câu hỏi đã đổi trong lúc dịch. Hãy dịch lại phiên bản mới.')
    # Save only after every ID/source has passed validation.
    for row in translations:
        entry = expected[row['id']]
        if entry['field']=='question':
            set_translation(lookup[entry['owner_id']], row['question_vi'])
        else:
            set_display_translations(lookup[entry['owner_id']],{entry['field']+'_vi':row['question_vi']})
    current['version'] = uuid.uuid4().hex
    atomic_json(workdir / 'owner_questions.json', current)
    return len(translations)
