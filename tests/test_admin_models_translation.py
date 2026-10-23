from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from game_seo.admin_models import catalog, execution_config
from game_seo.core import load_json, save_json
from game_seo.objects import inventory_digest, record_article_objects, draft_needs_refresh
from game_seo.question_translation import pending_translations, text_hash, translate_questions
from game_seo.stage_context import prepare_stage_context
from game_seo.web_review import save_answers, sync_questions
from test_admin import seed_review


class ModelSelectionTests(unittest.TestCase):
    def test_catalog_uses_visible_image_models_and_keeps_configured_choice(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / 'config.toml').write_text('model = "gpt-configured"\nmodel_reasoning_effort = "medium"', encoding='utf-8')
            save_json(folder / 'models_cache.json', {'models': [
                {'slug':'gpt-test','visibility':'list','display_name':'GPT Test','input_modalities':['text','image'],
                 'supported_reasoning_levels':[{'effort':'low'},{'effort':'medium'}]},
                {'slug':'gpt-hidden','visibility':'hide','input_modalities':['text','image']},
                {'slug':'gpt-text','visibility':'list','input_modalities':['text']}]})
            result = catalog({}, folder)
            self.assertEqual([r['id'] for r in result['models']], ['gpt-configured','gpt-test'])
            cfg = execution_config({}, {'model':'gpt-test','reasoning_effort':'low'}, folder)
            self.assertEqual(cfg['codex_model'], 'gpt-test')
            self.assertEqual(cfg['model_reasoning_effort'], 'low')
            with self.assertRaises(ValueError):
                execution_config({}, {'model':'gpt-test','reasoning_effort':'ultra'}, folder)
            with self.assertRaises(ValueError):
                execution_config({}, {'model':'gpt-test --config shell=bad','reasoning_effort':'low'}, folder)

    def test_missing_cache_and_custom_exact_gpt_id_work_without_network(self):
        with tempfile.TemporaryDirectory() as temp:
            cfg = execution_config({'codex_model':'gpt-existing'}, {'model':'gpt-custom-2026','reasoning_effort':'medium'}, temp)
            self.assertEqual(cfg['codex_model'], 'gpt-custom-2026')
            self.assertEqual(catalog({'codex_model':'gpt-existing'}, temp)['models'][0]['id'], 'gpt-existing')

    def test_model_and_effort_are_frozen_in_job_and_worker_config(self):
        from game_seo.admin_jobs import Jobs
        from game_seo.admin_store import Store
        from test_admin import inputs
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            video = folder / 'video.mp4'
            video.write_bytes(b'test')
            store = Store(folder / 'data')
            jobs = Jobs(store, folder / 'runs')
            game = store.save_game({**inputs(), 'video_path':str(video)})
            cfg = {'codex_model':'gpt-selected', 'model_reasoning_effort':'high'}
            with patch.object(jobs, '_launch', side_effect=lambda job:job):
                job = jobs.start(game, cfg)
            cfg['codex_model'] = 'gpt-changed-later'
            self.assertEqual(store.job(job['id'])['data']['execution'],
                             {'model':'gpt-selected', 'reasoning_effort':'high'})
            self.assertEqual(load_json(jobs.workdir(job) / 'admin_config.json')['codex_model'], 'gpt-selected')

    def test_runner_passes_selected_model_and_reasoning_to_codex_cli(self):
        import subprocess
        from game_seo.runner import codex_call
        from game_seo.core import ROOT
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp)
            save_json(work / 'question_translation_request.json', {'questions':[]})
            cfg = {**load_json(ROOT / 'config.json'), 'codex_model':'gpt-exact', 'model_reasoning_effort':'high'}
            def execute(command, **kwargs):
                self.assertEqual(command[command.index('--model')+1], 'gpt-exact')
                self.assertEqual(command[command.index('--config')+1], 'model_reasoning_effort=high')
                save_json(work / 'question_translation_output.json', {'translations':[]})
                return subprocess.CompletedProcess(command, 0, stdout='', stderr='')
            with patch('game_seo.runner.shutil.which', return_value='codex.exe'), \
                 patch('game_seo.runner.subprocess.run', side_effect=execute):
                codex_call('questions_vi', work, cfg)


class BilingualQuestionTests(unittest.TestCase):
    def test_object_display_fields_translate_cache_and_invalidate_without_confirming(self):
        from game_seo.question_translation import set_display_translations
        question={'id':'object:X','kind':'object','name':'Raised block','appearance':'Blue cube',
                  'answer':'May clear a row','decision':'pending'}
        set_display_translations(question,{'name_vi':'Khối nổi','appearance_vi':'Khối lập phương màu xanh',
                                          'answer_vi':'Có thể xóa một hàng'})
        self.assertEqual(question['name_vi_source_sha256'],text_hash('Raised block'))
        self.assertEqual(question['decision'],'pending')
        question['answer']='Only decoration'
        set_display_translations(question)
        self.assertEqual(question['answer_vi'],'')
        self.assertEqual(question['name_vi'],'Khối nổi')
        self.assertEqual(question['decision'],'pending')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.work = Path(self.temp.name)
        self.analysis, self.frames, self.doc = seed_review(self.work)

    def tearDown(self):
        self.temp.cleanup()

    def test_new_analysis_pairs_are_preserved_without_extra_ai_call(self):
        work = self.work / 'new'
        work.mkdir()
        row = {'id':'OBJ001','name':'Box','name_vi':'Hộp','question':'Does it explode?', 'question_vi':'Nó có phát nổ không?',
               'needs_confirmation':True}
        doc = sync_questions(work, {'objects':[row]}, ['Does Space jump?'], ['Phím Space có dùng để nhảy không?'])
        self.assertEqual(doc['questions'][0]['question'], 'Does it explode?')
        self.assertEqual(doc['questions'][0]['question_vi'], 'Nó có phát nổ không?')
        self.assertEqual(doc['questions'][1]['question_vi'], 'Phím Space có dùng để nhảy không?')
        with patch('game_seo.runner.codex_call') as model:
            self.assertEqual(translate_questions(work, {}), 0)
            model.assert_not_called()

    def test_legacy_batch_is_cached_and_cannot_change_answers_or_article(self):
        changes = [{'id':q['id'],'decision':'excluded'} for q in self.doc['questions']]
        save_answers(self.work, changes, approve=True)
        inventory = load_json(self.work / 'game_objects.json')
        save_json(self.work / 'article.json', {'title':'Approved'})
        record_article_objects(self.work, inventory)
        answers = (self.work / 'owner_answers.json').read_bytes()
        expected = pending_translations(self.work)
        def model(stage, work, cfg):
            self.assertEqual(stage, 'questions_vi')
            return {'translations':[{'id':q['id'], 'question_vi':'Bản dịch: ' + q['question']} for q in expected]}
        with patch('game_seo.runner.codex_call', side_effect=model) as call:
            self.assertEqual(translate_questions(self.work, {'codex_model':'gpt-test'}), len(expected))
            self.assertEqual(translate_questions(self.work, {}), 0)
            self.assertEqual(call.call_count, 1)
        self.assertEqual((self.work / 'owner_answers.json').read_bytes(), answers)
        self.assertFalse(draft_needs_refresh(self.work, inventory))
        self.assertEqual(pending_translations(self.work), [])

    def test_wrong_ids_or_partial_translation_save_nothing(self):
        before = load_json(self.work / 'owner_questions.json')['questions'][1]
        with patch('game_seo.runner.codex_call', return_value={'translations':[{'id':'BAD','question_vi':'Sai'}]}):
            with self.assertRaises(ValueError):
                translate_questions(self.work, {})
        after = load_json(self.work / 'owner_questions.json')['questions'][1]
        self.assertEqual(before['answer'], after['answer'])
        self.assertEqual(before['question'], after['question'])
        self.assertFalse(after.get('question_vi'))

    def test_source_edit_invalidates_translation_and_manual_vi_is_saved(self):
        q = self.doc['questions'][1]
        save_answers(self.work, [{'id':q['id'],'question_vi':'Hộp này có cho phần thưởng không?'}])
        saved = load_json(self.work / 'owner_questions.json')['questions'][1]
        self.assertEqual(saved['question_vi_source_sha256'], text_hash(saved['question']))
        save_answers(self.work, [{'id':q['id'],'question':'Can the box be moved?',
                                'question_vi':saved['question_vi']}])
        changed = load_json(self.work / 'owner_questions.json')['questions'][1]
        self.assertEqual(changed['question_vi'], '')
        save_answers(self.work, [{'id':q['id'],'question_vi':'Có thể di chuyển hộp này không?'}])
        self.assertEqual(load_json(self.work / 'owner_questions.json')['questions'][1]['question_vi'],
                         'Có thể di chuyển hộp này không?')

    def test_translation_bundle_contains_no_article_sources_or_owner_facts(self):
        save_json(self.work / 'game_brief.json', {'private':'not needed'})
        save_json(self.work / 'owner_answers.json', {'answers':[]})
        save_json(self.work / 'question_translation_request.json', {'questions':[{'id':'Q1','question':'Can it jump?'}]})
        bundle = load_json(prepare_stage_context(self.work, 'questions_vi'))
        self.assertEqual(set(bundle), {'question_translation_request.json'})

    def test_vietnamese_original_needs_no_codex_call(self):
        save_json(self.work / 'owner_questions.json', {'questions':[
            {'id':'Q1','question':'Nhân vật có nhảy được không?','answer':'','decision':'pending'}]})
        with patch('game_seo.runner.codex_call') as model:
            self.assertEqual(translate_questions(self.work, {}), 0)
            model.assert_not_called()
        self.assertEqual(load_json(self.work / 'owner_questions.json')['questions'][0]['question_vi'],
                         'Nhân vật có nhảy được không?')
