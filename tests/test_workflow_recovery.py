import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from game_seo.core import ROOT, load_json, save_json
from game_seo.research import search_wikipedia, collect_text_sources, collect_commons_images
from game_seo.runner import editorial_accepted, attach_diagnostics, build_repair_context, codex_failure_message
from game_seo.qa import validate
from test_pipeline import fixtures


class WorkflowRecoveryTests(unittest.TestCase):
    def test_codex_json_error_takes_priority_over_warning_only_stderr(self):
        events = ('{"type":"error","message":"You’ve hit your usage limit."}\n'
                  '{"type":"turn.failed","error":{"message":"You’ve hit your usage limit."}}\n')
        self.assertEqual(codex_failure_message(events, 'WARN plugin icon path'),
                         'You’ve hit your usage limit.')

    def test_public_evidence_disclaimer_is_blocked_at_its_paragraph(self):
        with tempfile.TemporaryDirectory() as folder:
            article, sources, images, frames = fixtures(folder)
            article['sections'][2]['paragraphs'][0]['text'] += ' The precise trigger and scoring effect are not part of the confirmed rules.'
            report = validate(article, sources, images, frames, load_json(ROOT / 'config.json'))
            self.assertTrue(any(i['code'] == 'PUBLIC_EVIDENCE_NOTE' and i['path'] == 'sections[2].paragraphs[0]' for i in report['issues']))

    def test_repair_counts_missing_sources_separately_from_total_mentions(self):
        with tempfile.TemporaryDirectory() as folder:
            article, sources, images, frames = fixtures(folder)
            context = build_repair_context(article, {'issues': []}, {'issues': []}, sources, images, frames['frames'])
            self.assertEqual(context['citation_requirements']['current_mentions'], 6)
            self.assertEqual(context['citation_requirements']['minimum_distinct_sources'], 4)
            self.assertEqual(context['citation_requirements']['unused_source_ids'], [])

    def test_warning_only_model_rejection_is_nonblocking_but_raw_verdict_survives(self):
        review = {'pass_editorial': False, 'issues': [{'severity': 'warning', 'path': 'sections[0].paragraphs[0]'}]}
        with tempfile.TemporaryDirectory() as folder:
            report = attach_diagnostics(folder, {'pass': True, 'issues': []}, review)
            self.assertTrue(report['overall_pass'])
            self.assertFalse(report['editorial_model_pass'])
            self.assertFalse(review['pass_editorial'])
            self.assertEqual(len(review['issues']), 1)

    def test_errors_unexplained_rejections_and_invalid_issues_still_block(self):
        for review in [
            {'pass_editorial': True, 'issues': [{'severity': 'error'}]},
            {'pass_editorial': False, 'issues': []},
            {'pass_editorial': True, 'issues': [{'severity': 'unknown'}]},
            {'issues': [{'severity': 'warning'}]},
        ]:
            with self.subTest(review=review):
                self.assertFalse(editorial_accepted(review))

    def test_section_level_critic_error_maps_only_to_that_sections_existing_paragraphs(self):
        with tempfile.TemporaryDirectory() as folder:
            article, sources, images, frames = fixtures(folder)
            review = {'issues': [{'path': 'sections[0]', 'severity': 'error'},
                                 {'path': 'sections[5]', 'severity': 'warning'}]}
            context = build_repair_context(article, {'issues': []}, review, sources, images, frames['frames'])
            self.assertEqual([e['path'] for e in context['allowed_edits']],
                             ['sections[0].paragraphs[0]', 'sections[0].paragraphs[1]'])

    def test_exact_concept_page_is_preferred_over_unrelated_full_text_matches(self):
        data = {'query': {'pages': {'1': {'title': 'Polyomino', 'fullurl': 'https://en.wikipedia.org/wiki/Polyomino',
                                          'extract': 'A polyomino consists of joined squares. ' * 8}}}}
        with patch('game_seo.research.get_json', return_value=data) as get:
            result = search_wikipedia('Polyomino')
        self.assertEqual(result[0]['title'], 'Polyomino')
        self.assertEqual(get.call_count, 1)
        self.assertEqual(get.call_args.args[1]['titles'], 'Polyomino')

    def test_source_limit_is_respected_even_when_academic_queries_continue(self):
        cfg = load_json(ROOT / 'config.json')
        cfg['max_web_sources'] = 4
        def entries(*args, **kwargs):
            return [{'title': f'Source {i}', 'url': f'https://example.org/{i}', 'excerpt': 'Supported evidence. ' * 12,
                     'kind': 'encyclopedia', 'evidence_quality': 'overview'} for i in range(12)]
        with tempfile.TemporaryDirectory() as folder, \
             patch('game_seo.research.search_wikipedia', side_effect=entries), \
             patch('game_seo.research.search_openalex', side_effect=entries), \
             patch('game_seo.research.check_source_link', return_value={'http_status': 200}):
            sources = collect_text_sources({'research_topics': ['Mosaic']}, cfg, Path(folder))
        self.assertEqual(len(sources), 4)
        self.assertEqual(sources[-1]['id'], 'SRC004')

    def test_puzzle_image_discovery_never_falls_back_to_unrelated_trains(self):
        cfg = load_json(ROOT / 'config.json')
        with tempfile.TemporaryDirectory() as folder, patch('game_seo.research.commons_search', return_value=[]) as search:
            with self.assertRaisesRegex(RuntimeError, 'relevant licensed Commons'):
                collect_commons_images({'image_search_topics': ['Wikimedia Commons geometric mosaic tiles']}, cfg, Path(folder))
            queries = [call.args[0] for call in search.call_args_list]
            self.assertEqual(queries, ['geometric mosaic tiles'])
            self.assertNotIn('train', ' '.join(queries))

    def test_research_plan_does_not_change_owner_reviewed_analysis(self):
        import run
        with tempfile.TemporaryDirectory() as folder:
            work = Path(folder)
            original = {'game_title': 'Owner game', 'research_topics': ['Long old query']}
            save_json(work / 'analysis.json', original)
            save_json(work / 'research_plan.json', {'text_queries': ['Mosaic'], 'image_queries': ['mosaic tile pattern'], 'academic_queries': []})
            with patch('run.collect_text_sources', return_value=[]) as text, \
                 patch('run.collect_commons_images', return_value=[]) as image:
                run.collect(work, load_json(ROOT / 'config.json'))
            self.assertEqual(text.call_args.args[0]['research_topics'], ['Mosaic'])
            self.assertEqual(image.call_args.args[0]['image_search_topics'], ['mosaic tile pattern'])
            self.assertEqual(text.call_args.args[1]['research_academic_queries'], [])
            self.assertEqual(load_json(work / 'analysis.json'), original)
