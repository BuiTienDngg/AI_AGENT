from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from game_seo.core import ROOT, load_json
from game_seo.qa import validate
from game_seo.runner import codex_call, build_repair_context
from game_seo.translation import validate_translation
from game_seo.writing import unclear_phrases, STYLE_FILE
from test_pipeline import fixtures, translated_fixture


class PlainWritingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.work = Path(self.tmp.name)
        self.article, self.sources, self.images, self.frames = fixtures(self.work)
        self.cfg = load_json(ROOT / 'config.json')

    def tearDown(self):
        self.tmp.cleanup()

    def test_reported_english_phrases_are_blocked_at_paragraph_path(self):
        for phrase in ['compact rectangles', 'different spatial demands', 'direct its placement']:
            with self.subTest(phrase=phrase):
                self.article['sections'][2]['paragraphs'][0]['text'] += ' ' + phrase
                report = validate(self.article, self.sources, self.images, self.frames, self.cfg)
                self.assertFalse(report['pass'])
                self.assertTrue(any(x['code'] == 'OPAQUE_GAMEPLAY_LANGUAGE' and
                                    x['path'] == 'sections[2].paragraphs[0]' for x in report['issues']))

    def test_clear_owner_confirmed_rule_and_controls_are_accepted(self):
        text = ('Pick up a block, drag it onto the board, and release it in an empty space. '
                'Fill a whole row or column and it clears, leaving room for the next blocks.')
        self.assertEqual(unclear_phrases(text), [])
        self.article['sections'][2]['paragraphs'][0]['text'] += ' ' + text
        report = validate(self.article, self.sources, self.images, self.frames, self.cfg)
        self.assertTrue(report['pass'], report['issues'])

    def test_literal_vietnamese_calque_is_rejected(self):
        vi = translated_fixture(self.article)
        vi['sections'][2]['paragraphs'][0]['text'] += ' Các hình chữ nhật gọn đặt ra những yêu cầu khác nhau.'
        report = validate_translation(self.article, vi)
        self.assertFalse(report['pass'])
        self.assertTrue(any(x['code'] == 'UNNATURAL_VI_WORDING' and
                            x['path'] == 'sections[2].paragraphs[0]' for x in report['issues']))

    def test_natural_vietnamese_action_rule_result_is_accepted(self):
        vi = translated_fixture(self.article)
        vi['sections'][2]['paragraphs'][0]['text'] += (
            ' Kéo khối hình vào ô trống rồi thả tay. Lấp kín một hàng ngang hoặc cột dọc là bùm! '
            'Hàng hoặc cột đó biến mất, nhường chỗ cho các khối tiếp theo.'
        )
        self.assertTrue(validate_translation(self.article, vi)['pass'])

    def test_model_receives_the_shared_style_guide(self):
        def execute(command, **kwargs):
            self.assertEqual((self.work / 'writing_style.md').read_text(encoding='utf-8'),
                             STYLE_FILE.read_text(encoding='utf-8'))
            self.assertIn('writing_style.md', command[-1])
            Path(command[command.index('--output-last-message') + 1]).write_text('{}', encoding='utf-8')
            return SimpleNamespace(returncode=0, stdout='', stderr='')
        with patch('game_seo.runner.shutil.which', return_value='codex'), \
             patch('game_seo.runner.subprocess.run', side_effect=execute):
            codex_call('draft', self.work, self.cfg)

    def test_semantic_clarity_error_enters_targeted_repair(self):
        report = validate(self.article, self.sources, self.images, self.frames, self.cfg)
        critique = {'pass_editorial': False, 'issues': [{'path': 'sections[5].paragraphs[0]',
            'severity': 'error', 'problem': 'Controls do not explain the confirmed input.',
            'suggestion': 'Describe the confirmed drag and drop action.'}]}
        context = build_repair_context(self.article, report, critique, self.sources, self.images, self.frames['frames'])
        self.assertIn('sections[5].paragraphs[0]', [row['path'] for row in context['allowed_edits']])
