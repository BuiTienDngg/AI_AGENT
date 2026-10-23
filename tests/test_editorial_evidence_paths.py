"""Regression tests for editorial evidence and paragraph path normalization."""
import tempfile
import unittest
from pathlib import Path

from game_seo.qa import get_para_by_path, apply_patches
from game_seo.editorial import review_gate
from game_seo.runner import build_repair_context


class EditorialEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.article = {'sections': [
            {'heading': 'Gameplay', 'paragraphs': [
                {'text': 'Place one block to clear a complete row.', 'image_ids': []},
                {'text': 'Preserve space for the next three shapes.', 'image_ids': []},
            ], 'subsections': []}
        ]}

    def test_prefixed_path_resolves(self):
        self.assertEqual(
            get_para_by_path(self.article, 'article.json.sections[0].paragraphs[0]')['text'],
            'Place one block to clear a complete row.')

    def test_prefixed_patch_is_applied(self):
        result, paths = apply_patches(self.article, {'edits': [
            {'path': 'article.json.sections[0].paragraphs[1]',
             'text': 'Keep room for another shape.'}]})
        self.assertEqual(paths, ['sections[0].paragraphs[1]'])
        self.assertEqual(result['sections'][0]['paragraphs'][1]['text'],
                         'Keep room for another shape.')

    def test_verbatim_critic_evidence_is_accepted(self):
        metrics = ('accuracy', 'seo_integration')
        review = {'pass_editorial': True, 'issues': [], 'strengths': [],
                  'scores': [{'metric': metric, 'score': 10, 'reason': 'Verified.',
                              'revision': '', 'evidence': [{
                                  'path': 'article.json.sections[0].paragraphs[0]',
                                  'quote': 'clear a complete row'}]} for metric in metrics]}
        result = review_gate(review, self.article, 'factual')
        self.assertTrue(result['pass_editorial'])
        for row in result['scores']:
            self.assertEqual(row['evidence'][0]['path'], 'sections[0].paragraphs[0]')

    def test_paraphrased_evidence_rejected(self):
        review = {'pass_editorial': True, 'issues': [], 'strengths': [],
                  'scores': [{'metric': metric, 'score': 10, 'reason': 'Good.',
                              'revision': '', 'evidence': [{
                                  'path': 'sections[0].paragraphs[0]',
                                  'quote': 'Completing rows produces points.'}]}
                             for metric in ('accuracy', 'seo_integration')]}
        result = review_gate(review, self.article, 'factual')
        self.assertFalse(result['pass_editorial'])
        self.assertEqual(sum('Invalid score/evidence' in issue['problem']
                             for issue in result['issues']), 2)

    def test_issue_path_can_be_repaired(self):
        report = {'issues': []}
        critique = {'issues': [{'path': 'article.json.sections[0].paragraphs[1]',
                                'severity': 'error', 'problem': 'Repeated idea',
                                'suggestion': 'Remove duplication'}]}
        cfg = {'min_citation_mentions': 0, 'min_text_sources': 0}
        context = build_repair_context(self.article, report, critique, [], [], [], cfg)
        self.assertEqual([x['path'] for x in context['allowed_edits']],
                         ['sections[0].paragraphs[1]'])


if __name__ == '__main__':
    unittest.main()
