"""Gameplay-first policy, evidence ledger, review gates and deterministic Chief."""
from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path
from .core import load_json, save_json

PROFILE = 'gameplay_first_v2'
RUBRIC = {'accuracy':10,'naturalness':9,'narrative_flow':8,'language_elegance':8,
          'editorial_depth':8,'originality':8,'game_specificity':9,'seo_integration':8,
          'localization':9,'non_repetition':9}
REVIEW_METRICS = {
    'literary':('naturalness','narrative_flow','language_elegance','editorial_depth','originality','game_specificity','non_repetition'),
    'factual':('accuracy','seo_integration'),
    'localization':('accuracy','naturalness','localization','non_repetition')}


def enabled(cfg):
    return cfg.get('editorial_profile') == PROFILE


def policy(work, cfg):
    cfg = dict(cfg)
    if not enabled(cfg):
        return cfg
    brief = load_json(Path(work)/'game_brief.json',default={})
    story = str(brief.get('story','')).strip()
    absent = brief.get('story_status') == 'PUBLISHER_CONFIRMED_ABSENT' or story.casefold() in (
        'không có cốt truyện','không có cốt truyện.','no story','no storyline','none')
    state = 'PUBLISHER_CONFIRMED_ABSENT' if absent else 'PUBLISHER_CONFIRMED_PRESENT' if story else 'UNKNOWN'
    cfg.update(min_text_sources=0,min_citation_mentions=0,min_intro_citations=0,min_article_characters=0,
               commons_images=max(0,int(cfg.get('editorial_external_images',0))),
               research_academic_queries=[],max_repair_rounds=min(2,cfg.get('max_repair_rounds',2)),
               required_sections=['Concept and Inspiration']+(['Story'] if state=='PUBLISHER_CONFIRMED_PRESENT' else [])+
               ['Gameplay','Visual Style','Controls'])
    save_json(Path(work)/'editorial_policy.json',{'profile':PROFILE,'story_status':state,
              'required_sections':cfg['required_sections'],'rubric':RUBRIC,
              'external_sources':'Only useful, directly relevant evidence; no quantity quota.',
              'images':'Gameplay first; external illustrations optional and justified.'})
    return cfg


def ledger(work, analysis, inventory, frames, sources=()):
    work=Path(work)
    facts=[]
    def add(text,kind,evidence):
        if str(text).strip():
            facts.append({'id':f'FACT{len(facts)+1:03}','text':str(text).strip(),
                          'classification':'FACT','evidence_type':kind,'evidence':evidence})
    brief=load_json(work/'game_brief.json',default={})
    for key in ('name','site_url','game_url','controls_pc','controls_mobile','idea_origin','story','game_style'):
        if brief.get(key):
            add(brief[key],'publisher_input',{'file':'game_brief.json','field':key})
    for obj in inventory.get('objects',[]):
        if obj.get('publishable') and obj.get('include_in_article',True):
            add(obj['name']+': '+obj.get('observed_behavior',''),'owner_confirmation' if obj.get('evidence')=='developer_confirmed' else 'video_observation',
                {'object_id':obj['id'],'frame_ids':obj.get('frame_ids',[])})
    answers=load_json(work/'owner_answers.json',default={})
    for answer in answers.get('answers',[]):
        if answer.get('decision')=='confirmed' and answer.get('answer'):
            add(answer['answer'],'owner_confirmation',{'question_id':answer['id']})
    valid_frames={r['frame_id'] for r in frames.get('frames',[])}
    for observation in analysis.get('observations',[]):
        refs=observation.get('frame_ids',[])
        if refs and set(refs)<=valid_frames:
            add(observation.get('description',''),'video_observation',{'frame_ids':refs,'observation_id':observation['id']})
    for source in sources:
        if source.get('verified_metadata') and source.get('evidence_quality')!='metadata_only' and source.get('excerpt'):
            add(source.get('excerpt',''),'external_source',{'source_id':source['id'],'url':source['url']})
    result={'facts':facts,'rules':{'SUPPORTED_INFERENCE':'Must cite supporting FACT IDs; never a new rule.',
            'EDITORIAL_DESCRIPTION':'Express verified events vividly; never add a feature.',
            'UNVERIFIED':'Private only; never promote to FACT.'}}
    save_json(work/'fact_ledger.json',result)
    return result


def retain_brief(notes, evidence, sources):
    """Validate traceability before passing model-authored angles to the writer."""
    valid={f['id'] for f in evidence['facts']}
    brief=copy.deepcopy(notes.get('editorial_brief',{}))
    errors=[]
    for group in ('insights','information_ownership'):
        for item in brief.get(group,[]):
            refs=item.get('fact_ids',[])
            if not refs or not set(refs)<=valid:
                errors.append('Untraceable '+group+' entry: '+str(item.get('id',item.get('fact_id',''))))
    for section in brief.get('sections',[]):
        if not section.get('purpose') or not section.get('transition'):
            errors.append('Section plan lacks purpose/transition.')
    expected={s['id'] for s in sources}
    if {r.get('source_id') for r in brief.get('research_filter',[])} != expected:
        errors.append('Every research source must receive a relevance decision.')
    for row in brief.get('research_filter',[]):
        if row.get('source_id') not in expected:
            errors.append('Research relevance cites unknown source.')
        elif row.get('source_url') != next(s['url'] for s in sources if s['id']==row['source_id']):
            errors.append('Research relevance changed the source URL.')
    if not brief.get('core_identity') or not brief.get('central_tension'):
        errors.append('Editorial angle is missing.')
    if errors:
        raise ValueError('Editorial brief rejected: '+'; '.join(errors))
    return brief


def review_gate(review, article, role):
    from .qa import get_para_by_path
    issues=list(review.get('issues',[]))
    scores=review.get('scores',[])
    metrics=[s.get('metric') for s in scores]
    for metric in REVIEW_METRICS[role]:
        entries=[s for s in scores if s.get('metric')==metric]
        if len(entries)!=1:
            issues.append({'path':'','severity':'error','problem':'Missing/duplicate rubric metric: '+metric,'suggestion':'Run a valid independent review.'})
            continue
        row=entries[0];value=row.get('score')
        evidence=row.get('evidence',[])
        valid_evidence=bool(evidence)
        for quote in evidence:
            try:
                valid_evidence &= bool(quote.get('quote')) and quote['quote'] in get_para_by_path(article,quote['path'])['text']
            except (KeyError,IndexError,ValueError,TypeError):
                valid_evidence=False
        if not isinstance(value,(int,float)) or isinstance(value,bool) or not 0<=value<=10 or not valid_evidence:
            issues.append({'path':'','severity':'error','problem':'Invalid score/evidence: '+metric,'suggestion':'Supply actual paragraph quotations, not an assigned target score.'})
        elif value<RUBRIC[metric]:
            for quote in evidence:
                issues.append({'path':quote['path'],'severity':'error',
                               'problem':metric+': '+str(value)+' < '+str(RUBRIC[metric])+'. '+row.get('reason',''),
                               'suggestion':row.get('revision','Revise the cited weakness without changing facts.')})
    if review.get('pass_editorial') is not True and not any(i.get('severity')=='error' for i in issues):
        issues.append({'path':'','severity':'error','problem':'Reviewer withheld approval.','suggestion':'Resolve the reviewer verdict before publication.'})
    return {'pass_editorial':not any(i.get('severity')=='error' for i in issues),
            'issues':issues,'strengths':review.get('strengths',[]),'scores':scores}


def chief(work, article, literary, factual, round_number):
    a=review_gate(literary,article,'literary');b=review_gate(factual,article,'factual')
    result={'pass_editorial':a['pass_editorial'] and b['pass_editorial'],
            'issues':b['issues']+a['issues'],'strengths':a['strengths']+b['strengths'],
            'reviews':{'literary':a,'factual':b},'priority':'Factuality blocks independently of prose scores.',
            'article_sha256':hashlib.sha256(json.dumps(article,sort_keys=True).encode()).hexdigest()}
    save_json(Path(work)/f'chief_review_{round_number}.json',result)
    save_json(Path(work)/'critique.json',result)
    return result


def assert_preserved(before, after, changed):
    from .qa import get_para_by_path,TOKEN_PATTERN
    from collections import Counter
    for path in changed:
        old,new=get_para_by_path(before,path),get_para_by_path(after,path)
        if Counter(TOKEN_PATTERN.findall(old['text']))-Counter(TOKEN_PATTERN.findall(new['text'])):
            raise ValueError('Rewrite dropped citations: '+path)
        if old.get('image_ids',[])!=new.get('image_ids',[]):
            raise ValueError('Rewrite changed established media order: '+path)
