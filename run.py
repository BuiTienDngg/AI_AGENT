#!/usr/bin/env python3
"""Game SEO Office: approved en-US article -> EN + VI Word, with Codex token reporting."""
from __future__ import annotations
import argparse
import json
import hashlib
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

from game_seo.core import ROOT, load_json, save_json, slugify
from game_seo.video import extract_frames, require_ffmpeg
from game_seo.research import collect_text_sources, collect_commons_images
from game_seo.qa import validate, apply_patches
from game_seo.export import export_all
from game_seo.translation import validate_translation
from game_seo.usage import print_usage
from game_seo.runner import codex_call, filter_notes, build_repair_context, attach_diagnostics, editorial_accepted
from game_seo.objects import (ensure_inventory, prepare_inventory, review_reasons, save_review,
                              draft_needs_refresh, record_article_objects, ObjectReviewPending)


def config():
    return load_json(ROOT / 'config.json')


def collect(run, cfg):
    analysis = load_json(run / 'analysis.json')
    # A local research plan can correct discovery queries without invalidating
    # reviewed gameplay objects or spending another vision call.
    plan = load_json(run / 'research_plan.json', default={})
    analysis = dict(analysis)
    cfg = dict(cfg)
    for key, field in [('text_queries', 'research_topics'), ('image_queries', 'image_search_topics')]:
        if key in plan:
            queries = plan[key]
            if not isinstance(queries, list) or not queries or any(not isinstance(q, str) or not q.strip() for q in queries):
                raise ValueError(f'research_plan.json {key} must be a nonempty list of query strings.')
            analysis[field] = queries
    if 'academic_queries' in plan:
        queries = plan['academic_queries']
        if not isinstance(queries, list) or any(not isinstance(q, str) or not q.strip() for q in queries):
            raise ValueError('research_plan.json academic_queries must be a list of query strings (or [] when no academic claims are planned).')
        cfg['research_academic_queries'] = queries
    print('[2/7] Finding real text sources (Wikipedia + OpenAlex) ...', flush=True)
    sources = collect_text_sources(analysis, cfg, run)
    print(f'      {len(sources)} source candidates collected.', flush=True)
    print('[3/7] Finding licensed Wikimedia Commons images ...', flush=True)
    images = collect_commons_images(analysis, cfg, run)
    print(f'      {len(images)} licensed images downloaded.', flush=True)
    return sources, images



def article_hash(article):
    payload = json.dumps(article, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def ensure_vietnamese_translation(run, article, cfg, resume=False):
    """Translate the final approved EN, never run another Research/Writer pass for VI."""
    file = run / 'translation_vi.json'
    meta_file = run / 'translation_provenance.json'
    expected_sha = article_hash(article)
    if resume and file.exists() and meta_file.exists():
        meta = load_json(meta_file)
        if meta.get('en_article_sha256') == expected_sha:
            candidate = load_json(file)
            check = validate_translation(article, candidate,localize_title=cfg.get('editorial_profile')=='gameplay_first_v2')
            if check['pass']:
                save_json(run / 'translation_qa.json', check)
                print('      Reusing verified VI translation for unchanged approved EN draft.', flush=True)
                return candidate
    max_tries = int(cfg.get('max_translation_attempts', 2))
    for attempt in range(1, max_tries + 1):
        print(f'      Translating approved EN to Vietnamese ({attempt}/{max_tries}) ...', flush=True)
        translated = codex_call('translate', run, cfg)
        check = validate_translation(article, translated,localize_title=cfg.get('editorial_profile')=='gameplay_first_v2')
        save_json(run / 'translation_qa.json', check)
        if check['pass']:
            save_json(meta_file, {'en_article_sha256': expected_sha, 'translation_file': file.name,
                                  'language': 'vi-VN', 'method': 'Codex translated from approved EN'})
            return translated
        print(f'      Vietnamese translation validation failed: {check["issues"][:3]}', flush=True)
    raise RuntimeError('VI translation did not preserve headings, paragraph order, image IDs or citation tokens. See translation_qa.json. No Word export was performed.')


def run_all(video, output_dir, cfg, resume=False, game_title_override=None, object_review=None):
    run = Path(output_dir).expanduser().resolve()
    run.mkdir(exist_ok=True, parents=True)
    from game_seo.editorial import enabled,policy,ledger,retain_brief,chief,review_gate,assert_preserved
    cfg=policy(run,cfg)
    modern=enabled(cfg)
    print(f'Working folder: {run}', flush=True)
    if not resume or not (run / 'frames.json').is_file():
        print('[1/7] Extracting and labeling video frames ...', flush=True)
        frames = extract_frames(Path(video), run, cfg)
    else:
        frames = load_json(run / 'frames.json')
    if not resume or not (run / 'analysis.json').is_file():
        analysis = codex_call('analyze', run, cfg, image_paths=frames['contact_sheets'])
    else:
        analysis = load_json(run / 'analysis.json')
    if game_title_override and game_title_override.strip():
        analysis['game_title'] = game_title_override.strip()
        save_json(run / 'analysis.json', analysis)
    inventory = ensure_inventory(run, analysis, frames, cfg, mode=object_review)
    print(f'      Objects: {len(inventory["objects"])} listed; review: {inventory["review"]["state"]}.', flush=True)
    if not resume or not ((run / 'sources.json').is_file() and (run / 'images.json').is_file()):
        sources, images = collect(run, cfg)
    else:
        sources = load_json(run / 'sources.json')['sources']
        images = load_json(run / 'images.json')['images']
    if modern:
        evidence=ledger(run,analysis,inventory,frames,sources)
    print('[4/7] Codex building evidence notes ...', flush=True)
    if not resume or not (run / 'research_notes.json').is_file():
        raw = codex_call('notes', run, cfg)
        clean, rejected = filter_notes(raw, sources)
        if modern:
            brief=retain_brief(raw,evidence,sources)
            accepted={r['source_id'] for r in brief['research_filter'] if r['include']}
            for category in ('context','player_psychology','genre_and_competitors'):
                clean[category]=[row for row in clean[category] if row['source_id'] in accepted]
            clean['editorial_brief']=brief
            save_json(run/'editorial_brief.json',brief)
        save_json(run / 'research_notes.json', clean)
        save_json(run / 'rejected_notes.json', rejected)
    if object_review == 'web':
        from game_seo.web_review import require_notes_review
        require_notes_review(run, load_json(run / 'research_notes.json'))
    print('[5/7] Codex writing full en-US article ...', flush=True)
    if not resume or draft_needs_refresh(run, inventory):
        if (run / 'article.json').is_file():
            stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
            save_json(run / 'article_history' / f'article_before_objects_{stamp}.json', load_json(run / 'article.json'))
        codex_call('draft', run, cfg)
        record_article_objects(run, inventory)
    article = load_json(run / 'article.json')
    print('[6/7] Deterministic QA + independent editorial review ...', flush=True)
    report = validate(article, sources, images, frames, cfg)
    save_json(run / 'qa_report.json', report)
    def critical_review(round_number):
        if not modern:
            return codex_call('critique',run,cfg)
        literary=codex_call('literary',run,cfg)
        factual=codex_call('factual',run,cfg)
        return chief(run,article,literary,factual,round_number)
    review = critical_review(0)
    attached = attach_diagnostics(run, report, review)
    print(f"      Initial QA: {'PASS' if attached['overall_pass'] else 'FAIL'} {report['summary']}", flush=True)
    rounds = 0
    while not attached['overall_pass'] and rounds < cfg['max_repair_rounds']:
        rounds += 1
        context = build_repair_context(article, report, review, sources, images, frames['frames'], cfg=cfg)
        save_json(run / 'repair_context.json', context)
        if context['unrepairable'] or not context['allowed_edits']:
            print('      Structural failures require human/editorial intervention; stopping.', flush=True)
            break
        print(f'      Repair round {rounds}: {len(context["allowed_edits"])} targeted paragraphs ...', flush=True)
        edits = codex_call('repair', run, cfg)
        allowed = {x['path'] for x in context['allowed_edits']}
        for edit in edits.get('edits', []):
            if edit.get('path') not in allowed:
                raise RuntimeError(f"Codex patch targeted an unapproved paragraph {edit.get('path')}.")
        revised, changed = apply_patches(article, edits)
        if modern:
            assert_preserved(article,revised,changed)
        article=revised
        save_json(run / 'article.json', article)
        save_json(run / f'repair_round_{rounds}.json', {'changed': changed, 'edits': edits})
        report = validate(article, sources, images, frames, cfg)
        save_json(run / 'qa_report.json', report)
        # A final fresh critical review prevents subjective issues from bypassing editorial review.
        review = critical_review(rounds)
        attached = attach_diagnostics(run, report, review)
        print(f"      QA after repair {rounds}: {'PASS' if attached['overall_pass'] else 'FAIL'} {report['summary']}", flush=True)
    if not attached['overall_pass']:
        print(f"STOPPED: QA errors remain. Inspect {run / 'qa_report.json'} and run again with --resume after making corrections.", flush=True)
        return 2
    print('[7/8] Translating approved EN article into Vietnamese ...', flush=True)
    translation = ensure_vietnamese_translation(run, article, cfg, resume=resume)
    if modern:
        local=review_gate(codex_call('localization',run,cfg),translation,'localization')
        while not local['pass_editorial'] and rounds<cfg['max_repair_rounds']:
            context=build_repair_context(translation,{'pass':True,'issues':[]},local,sources,images,frames['frames'],cfg=cfg)
            if not context.get('allowed_edits'):
                break
            rounds+=1
            save_json(run/'repair_context.json',context)
            edits=codex_call('localize_repair',run,cfg)
            allowed={row['path'] for row in context['allowed_edits']}
            if any(e['path'] not in allowed for e in edits.get('edits',[])):
                raise ValueError('Unauthorized Vietnamese rewrite path.')
            revised,changed=apply_patches(translation,edits)
            assert_preserved(translation,revised,changed)
            if not validate_translation(article,revised,localize_title=True)['pass']:
                raise ValueError('Vietnamese rewrite broke evidence alignment.')
            save_json(run/f'localization_before_{rounds}.json',translation)
            translation=revised
            save_json(run/'translation_vi.json',translation)
            local=review_gate(codex_call('localization',run,cfg),translation,'localization')
        local.update(en_article_sha256=article_hash(article),vi_article_sha256=article_hash(translation))
        save_json(run/'localization_qa.json',local)
        if not local['pass_editorial']:
            print('STOPPED: bilingual semantic/editorial review did not approve. See localization_qa.json.',flush=True)
            return 2
    print('[8/8] Exporting two aligned Word documents (EN + VI) ...', flush=True)
    results = export_all(article, sources, images, frames, run, translation_vi=translation,**({'editorial_v2':True} if modern else {}))
    save_json(run / 'export_manifest.json', {'files': results, 'qa_summary': report['summary'],
                                             'translation_qa': 'translation_qa.json', 'token_report': 'token_usage.json'})
    for kind, filename in results.items():
        print(f'  {kind}: {filename}', flush=True)
    print('SUCCESS. Two Word documents (EN + VI) created. No model API key used; Codex CLI account login is required.', flush=True)
    return 0


def doctor():
    print('Game SEO Office v1 — dependency check')
    for binary in ['ffmpeg', 'ffprobe', 'codex']:
        val = shutil.which(binary)
        print(f'  {binary}: {val or "NOT FOUND"}')
    try:
        from docx import Document
        from PIL import Image
        import requests
        print('  python-docx, Pillow, requests: available')
    except Exception as exc:
        print(f'  Python dependencies missing: {exc}')
    print('  API keys: not required. Internet: needed for Wikimedia + OpenAlex.')


def cli():
    p = argparse.ArgumentParser(description='Local Codex CLI Game SEO pipeline (en-US / no per-model API keys).')
    subs = p.add_subparsers(dest='cmd', required=True)
    subs.add_parser('doctor')
    run = subs.add_parser('run')
    run.add_argument('--video', required=True, help='Local MP4 or other FFmpeg supported video')
    run.add_argument('--out', help='Output run folder; default runs/<video stem>_<date>')
    run.add_argument('--resume', action='store_true', help='Use existing stage artifacts; regenerate QA/review')
    run.add_argument('--game-title', default=None, help='Optional correction if the video does not show the game title')
    run.add_argument('--object-review', choices=['auto', 'always', 'never'], default=None,
                     help='Open object form when needed, always, or continue with AI evidence only')
    objects = subs.add_parser('objects', help='Review or complete the game-object inventory')
    objects.add_argument('--run-dir', required=True)
    objects.add_argument('--from-json', help='Import a developer-confirmed object list without opening a GUI')
    stats = subs.add_parser('usage')
    stats.add_argument('--run-dir', required=True, help='Show token usage for an existing article run')
    qa = subs.add_parser('qa')
    qa.add_argument('--run-dir', required=True)
    exp = subs.add_parser('export')
    exp.add_argument('--run-dir', required=True)
    args = p.parse_args()
    cfg = {**config(), 'quota_tracking': True}
    if args.cmd == 'doctor':
        doctor(); return 0
    if args.cmd == 'usage':
        print_usage(Path(args.run_dir).expanduser().resolve()); return 0
    if args.cmd == 'objects':
        work = Path(args.run_dir).expanduser().resolve()
        analysis = load_json(work / 'analysis.json')
        frames = load_json(work / 'frames.json')
        inventory = prepare_inventory(work, analysis, frames)
        if args.from_json:
            supplied = load_json(Path(args.from_json).expanduser().resolve())
            rows = supplied.get('objects', []) if isinstance(supplied, dict) else supplied
            save_review(work, inventory, rows, 'confirmed')
        else:
            ensure_inventory(work, analysis, frames, cfg, mode='always')
        print(f'Object inventory saved: {work / "game_objects.json"}. Resume the run to incorporate changed objects into the article.')
        return 0
    if args.cmd == 'run':
        if args.resume and not args.out:
            p.error('--resume requires --out pointing to an existing run directory')
        dst = args.out or ROOT / 'runs' / (slugify(Path(args.video).stem) + '_' + datetime.now().strftime('%Y%m%d_%H%M%S'))
        try:
            return run_all(args.video, dst, cfg, resume=args.resume, game_title_override=args.game_title, object_review=args.object_review)
        finally:
            print_usage(dst)
    work = Path(args.run_dir).resolve()
    from game_seo.editorial import policy,enabled
    frozen=load_json(work/'admin_config.json',default={})
    marker=load_json(work/'editorial_policy.json',default={})
    cfg=policy(work,{**cfg,'editorial_profile':frozen.get('editorial_profile',marker.get('profile','legacy'))})
    src = load_json(work / 'sources.json')['sources']
    imgs = load_json(work / 'images.json')['images']
    frames = load_json(work / 'frames.json')
    article = load_json(work / 'article.json')
    if args.cmd == 'export' and (work / 'game_objects.json').exists():
        inventory = load_json(work / 'game_objects.json')
        if draft_needs_refresh(work, inventory):
            raise RuntimeError('Object inventory changed after the draft. Run the pipeline with --resume before exporting.')
    report = validate(article, src, imgs, frames, cfg)
    save_json(work / 'qa_report.json', report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if args.cmd == 'qa':
        return 0 if report['pass'] else 2
    # Export should not override an earlier editorial rejection.
    critique = load_json(work / 'critique.json', default={'pass_editorial': False, 'issues': []})
    if not report['pass'] or not editorial_accepted(critique):
        raise RuntimeError('Refusing export: deterministic QA or editorial critique failed.')
    try:
        translation = ensure_vietnamese_translation(work, article, cfg, resume=True)
        if enabled(cfg):
            local=load_json(work/'localization_qa.json',default={})
            if not local.get('pass_editorial') or local.get('en_article_sha256')!=article_hash(article) or local.get('vi_article_sha256')!=article_hash(translation):
                raise RuntimeError('Refusing export: bilingual editorial approval is missing or stale.')
        results = export_all(article, src, imgs, frames, work, translation_vi=translation,**({'editorial_v2':True} if enabled(cfg) else {}))
        save_json(work / 'export_manifest.json', {'files': results, 'qa_summary': report['summary'],
                                                'translation_qa': 'translation_qa.json', 'token_report': 'token_usage.json'})
        print(results)
    finally:
        print_usage(work)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(cli())
    except (Exception, KeyboardInterrupt) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        sys.exit(1)
