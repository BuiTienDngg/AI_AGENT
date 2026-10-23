"""Prepare one read-only evidence bundle per Codex stage.

No LLM or paid API calls. Data is preserved (not shortened) to avoid
accidentally discarding citations or gameplay facts. Missing optional inputs
are omitted; essential inputs remain enforced by the existing workflow/QA.
"""
from __future__ import annotations
import json
from pathlib import Path

STAGE_INPUTS = {
    'analyze': ('brand_context.json', 'writing_style.md', 'frames.json'),
    'notes': ('brand_context.json', 'analysis.json', 'sources.json'),
    'draft': ('brand_context.json', 'writing_style.md', 'publishing_requirements.json', 'analysis.json',
              'game_objects.json', 'frames.json', 'images.json', 'sources.json',
              'research_notes.json', 'revision_context.json'),
    'critique': ('brand_context.json', 'writing_style.md', 'publishing_requirements.json', 'article.json',
                 'analysis.json', 'game_objects.json', 'research_notes.json',
                 'sources.json', 'images.json', 'frames.json', 'qa_report.json'),
    'repair': ('brand_context.json', 'writing_style.md', 'publishing_requirements.json', 'repair_context.json',
               'article.json', 'analysis.json', 'game_objects.json',
               'sources.json', 'research_notes.json', 'images.json', 'frames.json',
               'qa_report.json', 'critique.json'),
    'translate': ('brand_context.json', 'writing_style.md', 'article.json'),
    'questions_vi': ('question_translation_request.json',),
}
STAGE_INPUTS['literary'] = tuple(x for x in STAGE_INPUTS['critique'] if x not in ('qa_report.json',))
STAGE_INPUTS['factual'] = STAGE_INPUTS['critique']
STAGE_INPUTS['localization'] = ('article.json','translation_vi.json','game_objects.json','sources.json','writing_style.md')
STAGE_INPUTS['localize_repair'] = STAGE_INPUTS['localization']+('repair_context.json',)

def prepare_stage_context(workdir, stage):
    """Write stage_context_<stage>.json atomically; return its absolute path."""
    workdir = Path(workdir).resolve()
    if stage not in STAGE_INPUTS:
        raise ValueError(f'Unknown stage: {stage}')
    data = {}
    inputs = STAGE_INPUTS[stage] if stage == 'questions_vi' else (
        *STAGE_INPUTS[stage], 'game_brief.json', 'owner_answers.json',
        *(('answer_library.json',) if stage != 'translate' else ()))
    if stage!='questions_vi':
        inputs=(*inputs,'editorial_policy.json','fact_ledger.json','editorial_brief.json')
    for filename in inputs:
        src = workdir / filename
        if not src.is_file():
            continue
        if filename.endswith('.json'):
            payload = json.loads(src.read_text(encoding='utf-8-sig'))
            if filename == 'answer_library.json':
                payload = {**payload, 'entries': [entry for entry in payload.get('entries', [])
                           if entry.get('question', {}).get('decision') in ('confirmed', 'excluded')]}
            # Warnings are informative, not authorized repair targets.
            # Exclude them only from the Repair agent's assembled context;
            # original reports remain unchanged and available for auditing.
            if stage == 'repair' and filename == 'critique.json' and isinstance(payload, dict):
                payload = {**payload, 'issues': [
                    issue for issue in payload.get('issues', [])
                    if issue.get('severity') == 'error'
                ]}
            if stage == 'repair' and filename == 'qa_report.json' and isinstance(payload, dict):
                payload = {**payload, 'editorial_issues': [
                    issue for issue in payload.get('editorial_issues', [])
                    if issue.get('severity') == 'error'
                ]}
            data[filename] = payload
        else:
            data[filename] = src.read_text(encoding='utf-8-sig')
    target = workdir / f'stage_context_{stage}.json'
    temporary = target.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    temporary.replace(target)
    return target
