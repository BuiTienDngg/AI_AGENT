import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from game_seo.brand import brand_context, developer_authorship_allowed
from game_seo.core import ROOT, load_json
from game_seo.qa import validate
from game_seo.runner import codex_call
from test_pipeline import fixtures


class BrandVoiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)
        self.article, self.sources, self.images, self.frames = fixtures(self.folder)
        self.cfg = {**load_json(ROOT / 'config.json'),'editorial_profile':'legacy'}
        self.article['sections'][0]['paragraphs'][0]['text'] += (
            ' We developed our game around the rhythm of moving through an urban railway.'
        )

    def tearDown(self):
        self.tmp.cleanup()

    def check(self, cfg):
        return validate(self.article, self.sources, self.images, self.frames, cfg)

    def test_confirmed_developer_voice_passes(self):
        cfg = {**self.cfg, 'brand_role': 'developer', 'developer_authorship_confirmed': True}
        result = self.check(cfg)
        self.assertTrue(result['pass'], result['issues'])

    def test_unconfirmed_or_string_confirmation_does_not_allow_authorship(self):
        for confirmation in (False, None, 'true'):
            with self.subTest(confirmation=confirmation):
                cfg = {**self.cfg, 'brand_role': 'developer', 'developer_authorship_confirmed': confirmation}
                result = self.check(cfg)
                self.assertIn('UNVERIFIED_DEVELOPMENT_HISTORY', [x['code'] for x in result['issues']])

    def test_publisher_declaration_does_not_claim_developer_role(self):
        cfg = {**self.cfg, 'brand_role': 'publisher', 'developer_authorship_confirmed': True}
        self.assertFalse(developer_authorship_allowed(cfg))
        self.assertFalse(self.check(cfg)['pass'])

    def test_legacy_config_keeps_authorship_guard(self):
        cfg = {key: value for key, value in self.cfg.items()
               if key not in ('brand_role', 'developer_authorship_confirmed')}
        self.assertFalse(developer_authorship_allowed(cfg))
        self.assertFalse(self.check(cfg)['pass'])

    def test_each_codex_stage_receives_owner_context(self):
        cfg = {**self.cfg, 'brand_role': 'developer', 'developer_authorship_confirmed': True,
               'concept_narrative_authorized': True}

        def execute(command, **kwargs):
            context = load_json(self.folder / 'brand_context.json')
            self.assertTrue(context['developer_authorship_confirmed'])
            self.assertTrue(context['concept_narrative_authorized'])
            self.assertEqual(context['declaration_source'], 'project owner configuration')
            self.assertIn('brand_context.json', command[-1])
            destination = Path(command[command.index('--output-last-message') + 1])
            destination.write_text('{}', encoding='utf-8')
            return SimpleNamespace(returncode=0, stdout='', stderr='')

        with patch('game_seo.runner.shutil.which', return_value='codex'), \
             patch('game_seo.runner.subprocess.run', side_effect=execute):
            for stage in ('analyze', 'notes', 'draft', 'critique', 'repair', 'translate'):
                self.assertEqual(codex_call(stage, self.folder, cfg), {})

    def test_creative_concept_requires_explicit_authorization(self):
        context = brand_context({**self.cfg, 'concept_narrative_authorized': False})
        self.assertTrue(context['developer_authorship_confirmed'])
        self.assertFalse(context['concept_narrative_authorized'])
