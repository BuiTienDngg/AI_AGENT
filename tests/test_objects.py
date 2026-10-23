import copy
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from game_seo.core import ROOT, load_json, save_json
from game_seo.objects import (prepare_inventory, normalize_objects, ensure_inventory, save_review,
                              review_reasons, draft_needs_refresh, record_article_objects,
                              ObjectReviewPending)
from test_pipeline import fixtures, translated_fixture


class ObjectInventoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.work = Path(self.tmp.name)
        self.article, self.sources, self.images, self.frames = fixtures(self.work)
        self.analysis = {'game_title': 'Fixture Game', 'game_objects': [
            {'id': 'OBJ001', 'name': 'Runner', 'category': 'player', 'appearance': 'Small figure',
             'observed_behavior': 'Moves along the tracks', 'frame_ids': ['FRAME001'],
             'confidence': 'high', 'needs_confirmation': False, 'question': ''}]}
        save_json(self.work / 'analysis.json', self.analysis)
        save_json(self.work / 'frames.json', self.frames)
        self.cfg = {**load_json(ROOT / 'config.json'), 'min_detected_objects': 8,'editorial_profile':'legacy'}

    def tearDown(self):
        self.tmp.cleanup()

    def test_unknown_frames_and_uncertain_functions_are_not_publishable(self):
        row = {**self.analysis['game_objects'][0], 'frame_ids': ['FRAME999'], 'confidence': 'low'}
        result = normalize_objects([row], self.frames)[0]
        self.assertFalse(result['publishable'])
        self.assertTrue(result['needs_confirmation'])
        self.assertEqual(result['frame_ids'], [])
        with self.assertRaises(ValueError):
            normalize_objects([row], self.frames, confirmed=True)

    def test_manual_object_without_a_frame_is_valid_owner_evidence(self):
        inventory = prepare_inventory(self.work, self.analysis, self.frames)
        updated = save_review(self.work, inventory, [{'name': 'Nam châm', 'category': 'power_up',
            'observed_behavior': 'Hút tiền xu ở các làn bên cạnh', 'frame_ids': []}], 'confirmed')
        row = updated['objects'][0]
        self.assertEqual(row['name'], 'Nam châm')
        self.assertEqual(row['evidence'], 'developer_confirmed')
        self.assertTrue(row['publishable'])
        self.assertFalse(row['needs_confirmation'])

    def test_auto_opens_for_missing_objects_and_reuses_confirmation(self):
        def confirm(work, inventory, reasons):
            self.assertTrue(reasons)
            save_review(work, inventory, inventory['objects'], 'confirmed')
        with patch('game_seo.object_form.open_object_form', side_effect=confirm) as form:
            self.assertEqual(ensure_inventory(self.work, self.analysis, self.frames, self.cfg)['review']['state'], 'confirmed')
            ensure_inventory(self.work, self.analysis, self.frames, self.cfg)
            self.assertEqual(form.call_count, 1)

    def test_pause_does_not_continue_and_reopens_even_with_enough_objects(self):
        def pause(work, inventory, reasons):
            save_review(work, inventory, inventory['objects'], 'pending')
        cfg = {**self.cfg, 'min_detected_objects': 1}
        with patch('game_seo.object_form.open_object_form', side_effect=pause) as form:
            with self.assertRaises(ObjectReviewPending):
                ensure_inventory(self.work, self.analysis, self.frames, cfg, mode='always')
            with self.assertRaises(ObjectReviewPending):
                ensure_inventory(self.work, self.analysis, self.frames, cfg)
            self.assertEqual(form.call_count, 2)
        self.assertFalse(load_json(self.work / 'game_objects.json')['objects'][0]['publishable'])

    def test_never_mode_does_not_open_gui_or_confirm_ai_guesses(self):
        self.analysis['game_objects'][0]['needs_confirmation'] = True
        with patch('game_seo.object_form.open_object_form') as form:
            inventory = ensure_inventory(self.work, self.analysis, self.frames, self.cfg, mode='never')
        form.assert_not_called()
        self.assertFalse(inventory['objects'][0]['publishable'])

    def test_a_remaining_question_prevents_publishing_even_if_ai_flag_is_wrong(self):
        row = {**self.analysis['game_objects'][0], 'needs_confirmation': False,
               'question': 'Does this object grant invincibility?'}
        result = normalize_objects([row], self.frames)[0]
        self.assertTrue(result['needs_confirmation'])
        self.assertFalse(result['publishable'])

    def test_changed_analysis_archives_owner_input_instead_of_losing_it(self):
        inventory = prepare_inventory(self.work, self.analysis, self.frames)
        save_review(self.work, inventory, [{'name': 'Manual object', 'frame_ids': []}], 'confirmed')
        changed = {**self.analysis, 'game_title': 'Different input'}
        inventory = prepare_inventory(self.work, changed, self.frames)
        self.assertEqual(inventory['review']['state'], 'pending')
        history = [load_json(path) for path in (self.work / 'object_reviews').glob('*.json')]
        self.assertTrue(any(any(row['name'] == 'Manual object' for row in item['objects']) for item in history))

    def test_object_edit_invalidates_draft_and_unchanged_review_does_not(self):
        inventory = prepare_inventory(self.work, self.analysis, self.frames)
        save_json(self.work / 'article.json', self.article)
        self.assertTrue(draft_needs_refresh(self.work, inventory))
        record_article_objects(self.work, inventory)
        self.assertFalse(draft_needs_refresh(self.work, inventory))
        changed = copy.deepcopy(inventory)
        changed['objects'][0]['observed_behavior'] = 'A new developer-confirmed behavior'
        self.assertTrue(draft_needs_refresh(self.work, changed))

    def test_bad_ai_inventory_opens_empty_review_instead_of_crashing(self):
        analysis = {'game_objects': [None, {'name': ''}]}
        inventory = prepare_inventory(self.work, analysis, self.frames)
        self.assertEqual(inventory['objects'], [])
        self.assertTrue(review_reasons(inventory, self.cfg))

    def test_unavailable_gui_leaves_actionable_json_import_path(self):
        with patch('game_seo.object_form.open_object_form', side_effect=RuntimeError('No GUI')):
            with self.assertRaisesRegex(ObjectReviewPending, '--from-json'):
                ensure_inventory(self.work, self.analysis, self.frames, self.cfg)

    def test_json_import_cli_confirms_owner_input_without_gui(self):
        supplied = self.work / 'manual.json'
        save_json(supplied, {'objects': [{'name': 'Shield', 'category': 'power_up',
                                         'observed_behavior': 'Protects the player', 'frame_ids': []}]})
        result = subprocess.run([sys.executable, str(ROOT / 'run.py'), 'objects', '--run-dir', str(self.work),
                                 '--from-json', str(supplied)], capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
        self.assertEqual(load_json(self.work / 'game_objects.json')['objects'][0]['evidence'], 'developer_confirmed')

    def test_resume_rewrites_stale_draft_before_translation(self):
        import run
        save_json(self.work / 'article.json', self.article)
        save_json(self.work / 'sources.json', {'sources': self.sources})
        save_json(self.work / 'images.json', {'images': self.images})
        save_json(self.work / 'research_notes.json', {})
        calls = []
        def model(stage, work, cfg, **kwargs):
            calls.append(stage)
            if stage == 'draft':
                self.assertTrue(load_json(work / 'game_objects.json')['objects'])
                save_json(work / 'article.json', self.article)
                return self.article
            self.assertTrue((work / 'qa_report.json').is_file())
            self.assertTrue(load_json(work / 'qa_report.json')['pass'])
            return {'pass_editorial': True, 'issues': []}
        with patch('run.codex_call', side_effect=model), \
             patch('run.ensure_vietnamese_translation', return_value=translated_fixture(self.article)), \
             patch('run.export_all', return_value={}):
            result = run.run_all('unused.mp4', self.work, self.cfg, resume=True, object_review='never')
        self.assertEqual(result, 0)
        self.assertEqual(calls, ['draft', 'critique'])
        self.assertTrue(list((self.work / 'article_history').glob('*.json')))
        self.assertFalse(draft_needs_refresh(self.work, load_json(self.work / 'game_objects.json')))


class NativeObjectFormTests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        from game_seo.object_form import ObjectReviewForm
        self.tmp = tempfile.TemporaryDirectory()
        self.work = Path(self.tmp.name)
        frames = {'frames': [{'frame_id': 'FRAME001'}]}
        save_json(self.work / 'frames.json', frames)
        self.analysis = {'game_objects': [{'name': 'Runner', 'frame_ids': ['FRAME001'], 'confidence': 'high'},
                                          {'name': 'Train', 'frame_ids': ['FRAME001'], 'confidence': 'high'}]}
        self.inventory = prepare_inventory(self.work, self.analysis, frames)
        try:
            self.root = tk.Tk()
        except tk.TclError:
            self.tmp.cleanup()
            self.skipTest('Tk display not available')
        self.root.withdraw()
        self.form = ObjectReviewForm(self.root, self.work, self.inventory)

    def tearDown(self):
        try:
            self.root.destroy()
        except Exception:
            pass
        self.tmp.cleanup()

    def test_switching_rows_keeps_edits_and_confirmation_is_persisted(self):
        self.form.name.set('Player character')
        self.form.tree.selection_set('1')
        self.form.select()
        self.assertEqual(self.form.rows[0]['name'], 'Player character')
        self.form.new()
        self.form.name.set('Gold coin')
        self.form.behavior.insert('1.0', 'Collectible currency')
        self.form.commit()
        self.form.confirm()
        saved = load_json(self.work / 'game_objects.json')
        self.assertEqual(saved['review']['state'], 'confirmed')
        self.assertEqual(len(saved['objects']), 3)
        self.assertTrue(all(row['publishable'] for row in saved['objects']))

    def test_closing_form_saves_draft_and_keeps_unconfirmed_text_private(self):
        self.form.behavior.delete('1.0', 'end')
        self.form.behavior.insert('1.0', 'Needs another look')
        self.form.pause()
        saved = load_json(self.work / 'game_objects.json')
        self.assertEqual(saved['review']['state'], 'pending')
        self.assertTrue(saved['review']['owner_paused'])
        self.assertFalse(any(row['publishable'] for row in saved['objects']))
