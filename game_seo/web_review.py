"""File-backed owner review used by the local admin; CLI/Tk behavior stays intact."""
from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path

from .core import load_json, save_json, utc_now
from .objects import ObjectReviewPending, archive_inventory, normalize_objects


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    save_json(temporary, data)
    temporary.replace(path)


def question_id(text):
    return 'Q' + hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]


def answer_key(question):
    """Match the same owner question across runs without relying on model IDs."""
    def normalized(value):
        return ' '.join(str(value or '').casefold().split())
    identity = [question.get('kind', ''),
                normalized(question.get('original_name') or question.get('name', '')),
                normalized(question.get('original_question') or question.get('question', ''))]
    return hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode('utf-8')).hexdigest()


def reuse_answer(question, library):
    saved = library.get(answer_key(question))
    if not saved or saved.get('decision') not in ('confirmed', 'excluded'):
        return question
    if saved['decision'] == 'confirmed' and not saved.get('answer'):
        return question
    question.setdefault('original_question', question.get('question', ''))
    for key in ('decision', 'answer', 'question', 'question_vi', 'name', 'appearance'):
        if key in saved:
            question[key] = saved[key]
    if question.get('kind') == 'object' and not question.get('name'):
        return question
    from .question_translation import set_translation
    set_translation(question, saved.get('question_vi'))
    from .question_translation import set_display_translations
    from .question_translation import text_hash
    set_display_translations(question,{k:saved[k] for k in ('name_vi','appearance_vi','answer_vi')
                                      if saved.get(k) and saved.get(k+'_source_sha256')==text_hash(question.get(k[:-3],''))})
    question['reused_answer'] = True
    return question


def sync_questions(workdir, inventory=None, extra=(), extra_vi=()):
    from .question_translation import set_translation
    path = Path(workdir) / 'owner_questions.json'
    doc = load_json(path, default={'state': 'pending', 'questions': []})
    library_doc = load_json(Path(workdir) / 'answer_library.json', default={'entries': []})
    library = {entry['key']: entry['question'] for entry in library_doc.get('entries', [])}
    doc.setdefault('version', uuid.uuid4().hex)
    known = {q['id'] for q in doc['questions']}
    if inventory is not None:
        for row in inventory['objects']:
            key = 'object:' + row['id']
            if key in known:
                continue
            doc['questions'].append(reuse_answer(set_translation({
                'id': key, 'object_id': row['id'], 'kind': 'object',
                'question': row.get('question') or 'Kiểm tra tên, hình dáng và vai trò của đối tượng này.',
                'name': row['name'], 'original_name': row['name'], 'appearance': row.get('appearance', ''),
                'answer': row.get('observed_behavior', ''), 'frame_ids': row.get('frame_ids', []),
                'decision': 'pending' if row.get('needs_confirmation') else 'observed',
            }, row.get('question_vi')), library))
            from .question_translation import set_display_translations
            set_display_translations(doc['questions'][-1],{
                key:value for key,value in [('name_vi',row.get('name_vi')),
                ('appearance_vi',row.get('appearance_vi')),('answer_vi',row.get('observed_behavior_vi'))]
                if value and not doc['questions'][-1].get('reused_answer')})
            known.add(key)
            doc['state'] = 'pending'
    for index, text in enumerate(extra):
        if not isinstance(text, str) or not text.strip():
            continue
        key = question_id(text.strip())
        if key in known:
            continue
        vi = extra_vi[index] if isinstance(extra_vi, (list, tuple)) and len(extra_vi) == len(extra) else None
        doc['questions'].append(reuse_answer(set_translation({'id': key, 'kind': 'question', 'question': text.strip(),
                                 'answer': '', 'decision': 'pending'}, vi), library))
        known.add(key)
        doc['state'] = 'pending'
    atomic_json(path, doc)
    return doc


def require_web_review(workdir, inventory, analysis):
    doc = sync_questions(workdir, inventory, analysis.get('unverified_mechanics', []),
                         analysis.get('unverified_mechanics_vi', []))
    if (doc['state'] != 'approved' and any(q.get('reused_answer') for q in doc['questions'])
            and all(q['decision'] != 'pending' for q in doc['questions'])):
        save_answers(workdir, [], approve=True)
        doc = load_json(Path(workdir) / 'owner_questions.json')
    if doc['state'] != 'approved':
        raise ObjectReviewPending('Chờ bạn duyệt đối tượng và trả lời trên trang quản trị.')
    return load_json(Path(workdir) / 'game_objects.json')


def require_notes_review(workdir, notes):
    doc = sync_questions(workdir, extra=notes.get('unsupported_questions', []),
                         extra_vi=notes.get('unsupported_questions_vi', []))
    if (doc['state'] != 'approved' and any(q.get('reused_answer') for q in doc['questions'])
            and all(q['decision'] != 'pending' for q in doc['questions'])):
        save_answers(workdir, [], approve=True)
        doc = load_json(Path(workdir) / 'owner_questions.json')
    if doc['state'] != 'approved':
        raise ObjectReviewPending('Có câu hỏi bổ sung sau nghiên cứu. Hãy trả lời trên trang quản trị.')


def save_answers(workdir, changes, approve=False):
    """Only explicit confirmations become owner facts. Unknown items stay excluded."""
    workdir = Path(workdir)
    from .question_translation import set_translation
    doc = load_json(workdir / 'owner_questions.json')
    if not isinstance(changes, list):
        raise ValueError('Câu trả lời phải là một danh sách.')
    questions = {q['id']: dict(q) for q in doc['questions']}
    for change in changes:
        if not isinstance(change, dict) or change.get('id') not in questions:
            raise ValueError('Câu hỏi không tồn tại.')
        q = questions[change['id']]
        decision = change.get('decision', q['decision'])
        allowed = ('pending', 'confirmed', 'excluded', 'observed') if q['kind'] == 'object' else ('pending', 'confirmed', 'excluded')
        if decision not in allowed or (decision == 'observed' and q['decision'] != 'observed'):
            raise ValueError('Chọn xác nhận, chưa trả lời hoặc bỏ chi tiết khỏi bài.')
        for key in ('name', 'appearance', 'answer', 'question', 'question_vi', 'name_vi','appearance_vi','answer_vi'):
            if key in change:
                if not isinstance(change[key], str) or len(change[key]) > 12000:
                    raise ValueError('Nội dung trả lời không hợp lệ hoặc quá dài.')
                if key == 'question':
                    q.setdefault('original_question', q['question'])
                q[key] = change[key].strip()
        # Editing observed content is an explicit owner confirmation, never new video evidence.
        old = next(x for x in doc['questions'] if x['id'] == q['id'])
        from .question_translation import set_display_translations
        supplied = {key:change[key] for key in ('name_vi','appearance_vi','answer_vi')
                    if key in change and (change[key]!=old.get(key) or
                    q.get(key[:-3])==old.get(key[:-3]))}
        set_display_translations(q,supplied)
        if q.get('question') != old.get('question'):
            supplied = change.get('question_vi') if change.get('question_vi') != old.get('question_vi') else None
            q['question_vi_source_sha256'] = ''
            set_translation(q, supplied)
        elif 'question_vi' in change:
            set_translation(q, change['question_vi'])
        if decision == 'observed' and any(q.get(k) != old.get(k) for k in ('name', 'appearance', 'answer')):
            decision = 'confirmed'
        if decision == 'confirmed' and not q.get('answer'):
            raise ValueError('Nhập câu trả lời đã chốt trước khi xác nhận.')
        if q['kind'] == 'object' and not q.get('name'):
            raise ValueError('Đối tượng cần có tên.')
        q['decision'] = decision
    updated = {**doc, 'questions': list(questions.values()), 'state': 'pending',
               'version': uuid.uuid4().hex, 'updated_at': utc_now()}
    if approve:
        if any(q['decision'] == 'pending' for q in updated['questions']):
            raise ValueError('Vẫn còn câu hỏi chưa trả lời. Hãy xác nhận hoặc chọn bỏ chi tiết khỏi bài.')
        updated['state'] = 'approved'
    inventory = load_json(workdir / 'game_objects.json')
    frames = load_json(workdir / 'frames.json')
    rows = []
    for raw in inventory['objects']:
        q = questions.get('object:' + raw['id'])
        if not q:
            rows.append(raw)
            continue
        changed = {**raw, 'name': q['name'], 'appearance': q.get('appearance', ''),
                   'observed_behavior': q.get('answer', '')}
        if q['decision'] == 'confirmed':
            changed['include_in_article'] = True
            changed = normalize_objects([changed], frames, confirmed=True)[0]
        elif q['decision'] == 'excluded':
            changed.update(include_in_article=False, publishable=False, needs_confirmation=False, question='')
        else:
            changed.update(include_in_article=q['decision'] == 'observed',
                           publishable=q['decision'] == 'observed')
        rows.append(changed)
    # Preserve every prior answer and inventory version, including edits after completion.
    atomic_json(workdir / 'answer_history' / (uuid.uuid4().hex + '.json'),
                {'saved_at': utc_now(), 'before': doc, 'after': updated})
    archive_inventory(workdir, inventory)
    atomic_json(workdir / 'game_objects.json', {
        **inventory, 'objects': rows,
        'review': {'state': 'confirmed' if approve else 'pending', 'owner_paused': not approve, 'updated_at': utc_now()},
    })
    atomic_json(workdir / 'owner_answers.json', {
        'declaration_source': 'Owner review in local admin',
        'answers': [{k: v for k, v in q.items() if k not in ('question_vi', 'question_vi_source_sha256')}
                    for q in updated['questions'] if q['decision'] in ('confirmed', 'excluded')],
    })
    atomic_json(workdir / 'owner_questions.json', updated)
    return updated


def add_object(workdir, name, behavior, appearance='', category='other'):
    if not isinstance(name, str) or not name.strip() or not isinstance(behavior, str) or not behavior.strip():
        raise ValueError('Nhập tên và vai trò/cơ chế của đối tượng mới.')
    workdir = Path(workdir)
    inventory = load_json(workdir / 'game_objects.json')
    frames = load_json(workdir / 'frames.json')
    row = normalize_objects([{'id': 'MANUAL_' + uuid.uuid4().hex[:10], 'name': name,
                             'observed_behavior': behavior, 'appearance': appearance,
                             'category': category, 'frame_ids': []}], frames, confirmed=True)[0]
    archive_inventory(workdir, inventory)
    inventory['objects'].append(row)
    inventory['review'].update(state='pending', owner_paused=True)
    atomic_json(workdir / 'game_objects.json', inventory)
    doc = sync_questions(workdir, inventory)
    return save_answers(workdir, [{'id': 'object:' + row['id'], 'decision': 'confirmed'}])
