"""Validate the structural equivalence of an en-US article and its Vietnamese translation."""
from __future__ import annotations
from collections import Counter
from .qa import TOKEN_PATTERN
from .writing import unclear_phrases


HEADINGS_VI = {
    'Concept and Inspiration': 'Ý tưởng và cảm hứng',
    'Story': 'Cốt truyện',
    'Gameplay': 'Lối chơi',
    'Visual Style': 'Phong cách hình ảnh',
    'Standout Features': 'Điểm nổi bật',
    'Controls': 'Điều khiển',
}


def validate_translation(en, vi, *, localize_title=False):
    """Hard gate: aligned sections/paragraphs, citation tokens and media IDs.

    Does not claim to verify translation quality or meaning; Codex performs that review.
    """
    issues = []
    def error(path, code, detail):
        issues.append({'path': path, 'code': code, 'detail': detail})
    if not isinstance(vi, dict):
        return {'pass': False, 'issues': [{'path': '$', 'code': 'TRANSLATION_NOT_OBJECT', 'detail': 'Translation is not JSON object'}]}
    for field in ('title', 'meta_title', 'meta_description'):
        if not isinstance(vi.get(field), str) or not vi[field].strip():
            error(field, 'TRANSLATION_EMPTY_METADATA', field)
    if not localize_title and vi.get('title') != en.get('title'):
        # Game name/title is an identity; prevent invention or renaming.
        error('title', 'GAME_TITLE_CHANGED', 'Keep the source article game title unchanged')
    en_sec = en.get('sections', [])
    vi_sec = vi.get('sections', [])
    if len(en_sec) != len(vi_sec):
        error('sections', 'SECTION_COUNT', f'Expected {len(en_sec)}, got {len(vi_sec)}')
    def check_paragraphs(a, b, base):
        if len(a) != len(b):
            error(base, 'PARAGRAPH_COUNT', f'Expected {len(a)}, got {len(b)}')
        for i, (ea, va) in enumerate(zip(a, b)):
            path = f'{base}[{i}]'
            if not str(va.get('text','')).strip():
                error(path, 'EMPTY_TRANSLATION', 'Paragraph text missing')
            unclear = unclear_phrases(str(va.get('text', '')), 'vi')
            if unclear:
                error(path, 'UNNATURAL_VI_WORDING', 'Rewrite naturally: ' + ', '.join(unclear))
            a_tokens = TOKEN_PATTERN.findall(ea.get('text', ''))
            b_tokens = TOKEN_PATTERN.findall(va.get('text', ''))
            if a_tokens != b_tokens:
                error(path, 'CITATION_SEQUENCE', f'Expected {a_tokens}; got {b_tokens}')
            if ea.get('image_ids', []) != va.get('image_ids', []):
                error(path, 'IMAGE_SEQUENCE', 'Image IDs/order differ from English source')
            en_captions = ea.get('image_captions', [])
            vi_captions = va.get('image_captions', [])
            if not isinstance(vi_captions, list) or [x.get('image_id') for x in en_captions] != [x.get('image_id') for x in vi_captions if isinstance(x, dict)]:
                error(path, 'CAPTION_SEQUENCE', 'Caption image IDs/order differ from English source')
            elif any(not isinstance(x, dict) or not isinstance(x.get('caption'), str) or not x['caption'].strip() for x in vi_captions):
                error(path, 'EMPTY_IMAGE_CAPTION', 'Translated image caption missing')
    for i, (es, vs) in enumerate(zip(en_sec, vi_sec)):
        loc = f'sections[{i}]'
        expected_heading = HEADINGS_VI.get(es['heading'])
        if expected_heading and vs.get('heading') != expected_heading:
            error(loc + '.heading', 'VI_HEADING', f'Expected {expected_heading!r}')
        check_paragraphs(es.get('paragraphs', []), vs.get('paragraphs', []), loc + '.paragraphs')
        e_sub, v_sub = es.get('subsections', []), vs.get('subsections', [])
        if len(e_sub) != len(v_sub):
            error(loc + '.subsections', 'SUBSECTION_COUNT', f'Expected {len(e_sub)}, got {len(v_sub)}')
        for j, (eu, vu) in enumerate(zip(e_sub, v_sub)):
            u_loc = f'{loc}.subsections[{j}]'
            if not isinstance(vu.get('heading'), str) or not vu['heading'].strip():
                error(u_loc + '.heading', 'EMPTY_SUBHEADING', 'Subheading missing')
            check_paragraphs(eu.get('paragraphs', []), vu.get('paragraphs', []), u_loc + '.paragraphs')
    return {'pass': not issues, 'issues': issues, 'paragraphs_checked': sum(len(s.get('paragraphs', [])) + sum(len(u.get('paragraphs', [])) for u in s.get('subsections', [])) for s in en_sec)}
