from __future__ import annotations
import re
from collections import Counter
from pathlib import Path
from .core import load_json, public_url, save_json, utc_now
from .brand import developer_authorship_allowed
from .writing import unclear_phrases

TOKEN_PATTERN = re.compile(r'\[\[(SRC\d{3})\]\]')
BAD_MARKERS = re.compile(r'URL not verified|URL chưa được xác minh|citation needed|TODO|TBD|\[Helsinki Metro bridge\]|DEMO_USER_SUPPLIED_UNVERIFIED', re.I)
PUBLIC_EVIDENCE_NOTE = re.compile(r'\b(?:not part of the confirmed rules|(?:footage|video|analysis) (?:does not|cannot) (?:confirm|establish))\b', re.I)
UNREFERENCED_CLAIMS = re.compile(r'\b(?:research(?:ers)? (?:shows?|suggests?|indicates?)|studies (?:show|suggest|indicate)|according to (?:a|the) (?:study|research)|a (?:20\d\d|19\d\d) study)\b', re.I)
UNSUPPORTED_AUTHORS = re.compile(r'\b(?:we (?:created|developed|built|coded|designed|were inspired)|our (?:original|first|exclusive) (?:idea|inspiration|feature))\b', re.I)


def walk_paragraphs(article):
    for si, sec in enumerate(article.get('sections', [])):
        for pi, para in enumerate(sec.get('paragraphs', [])):
            yield f'sections[{si}].paragraphs[{pi}]', sec['heading'], para
        for ui, sub in enumerate(sec.get('subsections', [])):
            for pi, para in enumerate(sub.get('paragraphs', [])):
                yield f'sections[{si}].subsections[{ui}].paragraphs[{pi}]', sec['heading'], para


def get_para_by_path(article, path):
    if not re.fullmatch(r'sections\[\d+\](?:\.subsections\[\d+\])?\.paragraphs\[\d+\]', path):
        raise ValueError(f'Unsupported paragraph path: {path}')
    cur = article
    for key, idx in re.findall(r'(sections|subsections|paragraphs)\[(\d+)\]', path):
        cur = cur[key][int(idx)]
    if not isinstance(cur, dict) or 'text' not in cur:
        raise ValueError(f'Not a paragraph: {path}')
    return cur


def validate(article, sources, images, frame_manifest, cfg):
    issues = []
    def report(code, message, path='', severity='error'):
        issues.append({'code': code, 'message': message, 'path': path, 'severity': severity})
    expected = cfg['required_sections']
    headings = [s.get('heading', '') for s in article.get('sections', [])]
    if headings != expected:
        report('HEADING_STRUCTURE', f'Expected headings in this order: {expected}; got {headings}', 'sections')
    if not str(article.get('title', '')).strip() or not str(article.get('meta_description', '')).strip():
        report('MISSING_METADATA', 'Need game title and meta_description', 'metadata')
    source_index = {s['id']: s for s in sources if s.get('id') and s.get('verified_metadata') and public_url(s.get('url', ''))}
    allowed_sources = {k: v for k, v in source_index.items() if v.get('evidence_quality') != 'metadata_only' and len(v.get('excerpt', '')) >= 130}
    images_by_id = {img['id']: img for img in images}
    frames_by_id = {f['frame_id']: f for f in frame_manifest.get('frames', [])}
    source_mentions = []
    used_images = []
    body_len = 0
    referenced_src_section = Counter()
    for path, section, paragraph in walk_paragraphs(article):
        content = str(paragraph.get('text', ''))
        unclear = unclear_phrases(content)
        if unclear:
            report('OPAQUE_GAMEPLAY_LANGUAGE', 'Replace vague wording with a concrete object/action/result: ' + ', '.join(unclear), path)
        body_len += len(content)
        tokens = TOKEN_PATTERN.findall(content)
        source_mentions.extend(tokens)
        referenced_src_section[section] += len(tokens)
        for token in tokens:
            if token not in allowed_sources:
                report('INVALID_SOURCE_ID', f'{token} not in verified evidence registry', path)
        if re.search(r'\[[0-9]+\](?!\])', content):
            report('PRENUMBERED_CITATION', 'Use only [[SRC001]] tokens; Python will number citations.', path)
        if BAD_MARKERS.search(content):
            report('PLACEHOLDER_OR_INTERNAL_NOTE', 'Contains a placeholder or internal metadata string.', path)
        if PUBLIC_EVIDENCE_NOTE.search(content):
            report('PUBLIC_EVIDENCE_NOTE', 'Keep evidence limitations in private analysis; describe only the confirmed public-facing facts.', path)
        if UNREFERENCED_CLAIMS.search(content) and not tokens:
            report('ACADEMIC_CLAIM_UNSOURCED', 'A research-based assertion needs a supporting source in this paragraph.', path)
        if UNSUPPORTED_AUTHORS.search(content) and not developer_authorship_allowed(cfg):
            report('UNVERIFIED_DEVELOPMENT_HISTORY', 'Developer authorship requires an explicit project-owner declaration.', path)
        for image_id in paragraph.get('image_ids', []):
            used_images.append(image_id)
            if image_id not in images_by_id and image_id not in frames_by_id:
                report('INVALID_IMAGE_ID', f'Unknown image ID {image_id}', path)
        if 'image_captions' in paragraph:
            captions = paragraph['image_captions']
            if not isinstance(captions, list) or any(not isinstance(x, dict) for x in captions):
                report('INVALID_IMAGE_CAPTIONS', 'Image captions must be structured image_id/caption records.', path)
            elif [x.get('image_id') for x in captions] != paragraph.get('image_ids', []):
                report('IMAGE_CAPTION_SEQUENCE', 'Provide one caption per image in image_ids order.', path)
            else:
                for item in captions:
                    caption = item.get('caption', '')
                    if not isinstance(caption, str) or not caption.strip() or re.search(r'https?://|\[\[SRC|\bFRAME\d{3}\b|\b\d{1,3}(?:\.\d+)?s\b', caption, re.I):
                        report('INVALID_IMAGE_CAPTION', 'Use a content/heading caption without URLs, frame IDs or timestamps.', path)
        if re.search(r'https?://\S+', content):
            report('INLINE_URL', 'Use source IDs, not raw URLs in article paragraphs.', path)
    if body_len < cfg.get('min_article_characters',2200):
        report('THIN_ARTICLE', f'Article too short ({body_len} characters). Expand substantive sections.', 'sections')
    unique_used = len(set(x for x in source_mentions if x in allowed_sources))
    if unique_used < cfg['min_text_sources']:
        report('SOURCE_COVERAGE', f'{unique_used} unique valid text sources; required {cfg["min_text_sources"]}.', 'sections')
    if len(source_mentions) < cfg['min_citation_mentions']:
        report('CITATION_MENTIONS', f'{len(source_mentions)} total citation tokens; required {cfg["min_citation_mentions"]}.', 'sections')
    if referenced_src_section['Concept and Inspiration'] < cfg.get('min_intro_citations',2):
        report('INTRO_MISSING_CITATIONS', 'Concept and Inspiration needs at least two citations.', 'sections[0]')
    intro_ids = []
    for _, section, para in walk_paragraphs(article):
        if section == 'Concept and Inspiration':
            intro_ids.extend(x for x in para.get('image_ids', []) if x in images_by_id)
    if len(set(intro_ids)) < cfg['commons_images']:
        report('INTRO_MISSING_COMMONS_IMAGES', f'Intro needs {cfg["commons_images"]} distinct, licensed image IDs.', 'sections[0]')
    gameplay_image_ids = set(x for x in used_images if x in frames_by_id)
    if len(gameplay_image_ids) < cfg['frames_in_article']:
        report('MISSING_GAMEPLAY_IMAGES', f'Need {cfg["frames_in_article"]} distinct video frames in article.', 'sections')
    academic_claims = []
    for path, section, para in walk_paragraphs(article):
        txt = para.get('text', '')
        if UNREFERENCED_CLAIMS.search(txt):
            refs = TOKEN_PATTERN.findall(txt)
            if not any(allowed_sources.get(x, {}).get('kind') == 'academic' for x in refs):
                academic_claims.append(path)
    for path in academic_claims:
        report('ACADEMIC_SOURCE_REQUIRED', 'Research claim must cite an academic source with available abstract/evidence.', path)
    verdict = not any(x['severity'] == 'error' for x in issues)
    return {'pass': verdict, 'summary': {'source_mentions': len(source_mentions), 'unique_sources': unique_used,
                      'commons_in_intro': len(set(intro_ids)), 'gameplay_images': len(gameplay_image_ids),
                      'body_characters': body_len, 'issues': len(issues)}, 'issues': issues, 'checked_at': utc_now()}


def apply_patches(article, patches):
    """Only modify the paragraph paths explicitly returned by Codex; no full-article overwrite."""
    import copy
    updated = copy.deepcopy(article)
    changed = []
    for edit in patches.get('edits', []):
        path = edit.get('path', '')
        if not path:
            continue
        para = get_para_by_path(updated, path)
        text = edit.get('text', '')
        ids = edit.get('image_ids', para.get('image_ids', []))
        if not isinstance(text, str) or not text.strip() or not isinstance(ids, list) or not all(isinstance(x, str) for x in ids):
            raise ValueError('Repair patch must contain valid text and image_ids.')
        para['text'] = text.strip()
        para['image_ids'] = ids
        if 'image_captions' in edit:
            if not isinstance(edit['image_captions'], list):
                raise ValueError('Repair image_captions must be a list.')
            para['image_captions'] = copy.deepcopy(edit['image_captions'])
        elif ids != get_para_by_path(article, path).get('image_ids', []):
            para.pop('image_captions', None)
        changed.append(path)
    return updated, changed


def verify_references(source_registry, article):
    """References sorted in first-use order, and every final URL comes from registry."""
    valid = {s['id']: s for s in source_registry}
    ordered = []
    for _, _, paragraph in walk_paragraphs(article):
        for ref in TOKEN_PATTERN.findall(paragraph.get('text', '')):
            if ref not in valid:
                raise ValueError(f'Invalid reference {ref}')
            if ref not in ordered:
                ordered.append(ref)
    return {sid: n for n, sid in enumerate(ordered, start=1)}
