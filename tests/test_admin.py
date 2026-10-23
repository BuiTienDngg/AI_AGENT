from __future__ import annotations

import io
import re
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from pathlib import Path

from game_seo.admin_web import create_app
from game_seo.core import ROOT, load_json, save_json
from game_seo.objects import (ObjectReviewPending, draft_needs_refresh, ensure_inventory, record_article_objects)
from game_seo.stage_context import prepare_stage_context
from game_seo.web_review import add_object, require_notes_review, save_answers


def inputs():
    return {'name': 'Block Test', 'site_url': 'https://slope3.com/',
            'game_url': 'https://slope3.com/block-test', 'idea_origin': 'Mosaic idea',
            'story': '', 'game_style': '', 'controls_pc': 'Drag with mouse', 'controls_mobile': 'Drag with finger'}


def seed_review(work):
    frames = {'frames': [{'frame_id': 'FRAME001'}], 'source_video': 'test.mp4'}
    analysis = {'game_title': 'Test', 'game_objects': [
        {'id': 'OBJ001', 'name': 'Player', 'frame_ids': ['FRAME001'], 'confidence': 'high',
         'observed_behavior': 'Moves forward'},
        {'id': 'OBJ002', 'name': 'Box', 'frame_ids': ['FRAME001'], 'confidence': 'low',
         'observed_behavior': 'Possibly a power up', 'question': 'Does the box give a bonus?'}],
        'unverified_mechanics': ['Is there a jump button?']}
    save_json(work / 'frames.json', frames)
    save_json(work / 'analysis.json', analysis)
    try:
        ensure_inventory(work, analysis, frames, {}, mode='web')
    except ObjectReviewPending:
        pass
    return analysis, frames, load_json(work / 'owner_questions.json')


class WebReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.work = Path(self.temp.name)
        self.analysis, self.frames, self.questions = seed_review(self.work)

    def tearDown(self):
        self.temp.cleanup()

    def test_waiting_review_never_confirms_ai_guesses(self):
        inventory = load_json(self.work / 'game_objects.json')
        self.assertFalse(inventory['objects'][1]['publishable'])
        with self.assertRaises(ObjectReviewPending):
            ensure_inventory(self.work, self.analysis, self.frames, {}, mode='web')
        with self.assertRaisesRegex(ValueError, 'chưa trả lời'):
            save_answers(self.work, [], approve=True)
        self.assertFalse((self.work / 'owner_answers.json').exists())

    def test_confirm_exclude_and_resume_preserve_each_evidence_type(self):
        changes = [{'id': q['id'], 'decision': 'excluded'} for q in self.questions['questions'] if q['decision'] == 'pending']
        changes[0] = {'id': 'object:OBJ002', 'decision': 'confirmed', 'answer': 'Breakable crate, no power-up effect'}
        save_answers(self.work, changes, approve=True)
        inventory = ensure_inventory(self.work, self.analysis, self.frames, {}, mode='web')
        self.assertEqual(inventory['review']['state'], 'confirmed')
        self.assertEqual(inventory['objects'][0]['evidence'], 'video_observed')
        self.assertEqual(inventory['objects'][1]['evidence'], 'developer_confirmed')
        self.assertEqual(inventory['objects'][1]['observed_behavior'], changes[0]['answer'])
        self.assertEqual(load_json(self.work / 'owner_answers.json')['answers'][-1]['decision'], 'excluded')
        require_notes_review(self.work, {'unsupported_questions': []})

    def test_additional_research_question_waits(self):
        save_answers(self.work, [{'id': q['id'], 'decision': 'excluded'} for q in self.questions['questions']], approve=True)
        with self.assertRaises(ObjectReviewPending):
            require_notes_review(self.work, {'unsupported_questions': ['Does gold double the score?']})
        self.assertEqual(len(load_json(self.work / 'owner_questions.json')['questions']), 4)

    def test_free_answer_edit_invalidates_draft_and_keeps_answer_history(self):
        rows = [{'id': q['id'], 'decision': 'excluded'} for q in self.questions['questions']]
        save_answers(self.work, rows, approve=True)
        inventory = load_json(self.work / 'game_objects.json')
        save_json(self.work / 'article.json', {'title': 'Old draft'})
        record_article_objects(self.work, inventory)
        self.assertFalse(draft_needs_refresh(self.work, inventory))
        general = self.questions['questions'][-1]
        save_answers(self.work, [{'id': general['id'], 'decision': 'confirmed', 'answer': 'Space jumps on PC'}], approve=True)
        self.assertTrue(draft_needs_refresh(self.work, load_json(self.work / 'game_objects.json')))
        self.assertEqual(len(list((self.work / 'answer_history').glob('*.json'))), 2)

    def test_manual_object_and_pending_draft_do_not_turn_other_guesses_into_facts(self):
        add_object(self.work, 'Gold coin', 'Collect to earn one point')
        inventory = load_json(self.work / 'game_objects.json')
        self.assertEqual(len(inventory['objects']), 3)
        self.assertFalse(inventory['objects'][1]['publishable'])
        self.assertEqual(inventory['objects'][2]['evidence'], 'developer_confirmed')
        self.assertEqual(inventory['objects'][2]['observed_behavior'], 'Collect to earn one point')
        # Pending web review survives another worker invocation without normalizing away confirmations.
        with self.assertRaises(ObjectReviewPending):
            ensure_inventory(self.work, self.analysis, self.frames, {}, mode='web')
        self.assertEqual(load_json(self.work / 'game_objects.json')['objects'][2]['evidence'], 'developer_confirmed')

    def test_previously_excluded_object_can_be_confirmed_and_used_again(self):
        save_answers(self.work, [{'id':'object:OBJ002', 'decision':'excluded'}])
        save_answers(self.work, [{'id':'object:OBJ002', 'decision':'confirmed', 'answer':'Breakable crate'}])
        row = load_json(self.work / 'game_objects.json')['objects'][1]
        self.assertTrue(row['include_in_article'])
        self.assertTrue(row['publishable'])
        self.assertEqual(row['evidence'], 'developer_confirmed')

    def test_brief_and_answers_reach_every_agent_stage(self):
        save_json(self.work / 'game_brief.json', inputs())
        save_json(self.work / 'owner_answers.json', {'answers': [{'answer': 'Space jumps'}]})
        for stage in ('analyze', 'notes', 'draft', 'critique', 'repair', 'translate'):
            bundle = load_json(prepare_stage_context(self.work, stage))
            self.assertEqual(bundle['game_brief.json']['idea_origin'], 'Mosaic idea')
            self.assertEqual(bundle['owner_answers.json']['answers'][0]['answer'], 'Space jumps')


class AdminApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.app = create_app(self.folder / 'data', self.folder / 'runs', probe=lambda p: 301.5)
        self.client = self.app.test_client()
        html = self.client.get('/').text
        self.token = re.search(r'name="office-token" content="([^"]+)"', html)[1]
        self.headers = {'X-Office-Token': self.token}
        self.store = self.app.extensions['office_store']
        self.jobs = self.app.extensions['office_jobs']

    def tearDown(self):
        self.jobs.close()
        self.temp.cleanup()

    def create(self, **changes):
        form = {**inputs(), 'video': (io.BytesIO(b'fake video for mocked probe'), '../../outside.mp4'), **changes}
        return self.client.post('/api/games', data=form, headers=self.headers)

    def test_required_fields_video_urls_and_both_control_platforms(self):
        for field in ('name', 'site_url', 'game_url', 'controls_pc', 'controls_mobile'):
            self.assertEqual(self.create(**{field: ''}).status_code, 400, field)
        self.assertEqual(self.client.post('/api/games', data=inputs(), headers=self.headers).status_code, 400)
        self.assertEqual(self.create(game_url='javascript:alert(1)').status_code, 400)
        self.assertEqual(self.create(video=(io.BytesIO(b'x'), 'test.exe')).status_code, 400)
        self.assertEqual(self.store.games(), [])

    def test_crud_versions_persistence_and_safe_upload_paths(self):
        response = self.create()
        self.assertEqual(response.status_code, 201)
        game = response.json['game']
        path = Path(game['data']['video_path'])
        self.assertEqual(path.parent, self.folder / 'data' / 'videos')
        changed = self.client.post('/api/games/' + game['id'], data={**inputs(), 'name': 'Edited', 'revision': 1}, headers=self.headers)
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(changed.json['game']['revision'], 2)
        conflict = self.client.post('/api/games/' + game['id'], data={**inputs(), 'revision': 1}, headers=self.headers)
        self.assertEqual(conflict.status_code, 400)
        self.assertEqual(self.store.game(game['id'])['data']['name'], 'Edited')
        self.assertTrue(path.exists())
        self.assertEqual(self.client.delete('/api/games/' + game['id'], headers=self.headers).status_code, 200)
        self.assertEqual(self.client.get('/api/state').json['games'], [])
        self.assertTrue(path.exists())
        with self.store.connection() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM revisions').fetchone()[0], 2)

    def test_foreign_origin_and_host_cannot_change_local_records(self):
        self.assertEqual(self.client.post('/api/games', data=inputs()).status_code, 403)
        self.assertEqual(self.client.get('/api/state', headers={'Host': 'evil.example'}).status_code, 403)
        self.assertEqual(self.client.post('/api/games', data=inputs(),
                         headers={**self.headers, 'Origin': 'https://evil.example'}).status_code, 403)

    def test_legacy_download_stays_inside_its_run_output(self):
        work = self.folder / 'runs' / 'legacy'
        output = work / 'output'
        output.mkdir(parents=True)
        valid = output / 'en.docx'
        valid.write_bytes(b'word fixture')
        outside = self.folder / 'secret.docx'
        outside.write_bytes(b'private')
        save_json(work / 'export_manifest.json', {'files': {'docx_en': str(valid), 'docx_vi': str(outside)}})
        response = self.client.get('/api/state')
        self.assertEqual(response.json['history'][0]['files'], ['docx_en'])
        download = self.client.get('/api/runs/legacy/download/docx_en')
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download.data, b'word fixture')
        download.close()
        self.assertEqual(self.client.get('/api/runs/legacy/download/docx_vi').status_code, 404)

    def test_api_answers_persist_history_and_reject_old_tab(self):
        game = self.create().json['game']
        job = self.store.add_job(game, 'review', 'job-review')
        work = self.jobs.workdir(job)
        work.mkdir()
        _, _, doc = seed_review(work)
        self.store.update_job(job['id'], 'waiting')
        payload = {'questions': [{'id': q['id'], 'decision': 'excluded'} for q in doc['questions']],
                   'approve': True, 'version': doc['version']}
        result = self.client.post('/api/jobs/job-review/answers', json=payload, headers=self.headers)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json['questions']['state'], 'approved')
        self.assertEqual(self.client.post('/api/jobs/job-review/answers', json=payload, headers=self.headers).status_code, 409)
        detail = self.client.get('/api/jobs/job-review').json
        self.assertEqual(len(detail['answer_history']), 1)
        self.assertEqual(detail['questions']['questions'][1]['decision'], 'excluded')

    def test_saved_answers_api_can_edit_future_reuse_and_detail_shows_quota(self):
        game = self.create().json['game']
        job = self.store.add_job(game, 'review', 'job-review')
        work = self.jobs.workdir(job)
        work.mkdir()
        _, _, doc = seed_review(work)
        self.store.update_job(job['id'], 'waiting')
        pending = [q for q in doc['questions'] if q['decision'] == 'pending']
        payload = {'questions': [{'id': q['id'], 'decision': 'excluded'} for q in pending],
                   'approve': True, 'version': doc['version']}
        self.assertEqual(self.client.post('/api/jobs/job-review/answers', json=payload,
                                          headers=self.headers).status_code, 200)
        entries = self.client.get('/api/games/' + game['id'] + '/answers').json['entries']
        self.assertEqual(len(entries), len(doc['questions']))
        entry = next(e for e in entries if e['question']['decision'] == 'excluded')
        url = '/api/games/' + game['id'] + '/answers/' + entry['key']
        updated = self.client.post(url, json={'answer': 'No bonus effect', 'decision': 'confirmed',
                                              'updated': entry['updated']}, headers=self.headers)
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json['entry']['question']['answer'], 'No bonus effect')
        self.assertEqual(self.client.post(url, json={'answer': 'stale', 'decision': 'confirmed',
                                                    'updated': entry['updated']}, headers=self.headers).status_code, 400)
        save_json(work / 'quota_usage.json', {'summary': {'5h': {'after_percent': 25}}, 'samples': []})
        self.assertEqual(self.client.get('/api/jobs/job-review').json['quota']['summary']['5h']['after_percent'], 25)

    def test_invalid_video_is_cleaned_up_without_saving_game(self):
        app = create_app(self.folder / 'bad', self.folder / 'bad_runs', probe=lambda p: 999999)
        client = app.test_client()
        token = re.search(r'name="office-token" content="([^"]+)"', client.get('/').text)[1]
        response = client.post('/api/games', data={**inputs(), 'video': (io.BytesIO(b'x'), 'bad.mp4')},
                               headers={'X-Office-Token': token})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(list((self.folder / 'bad' / 'videos').glob('*')), [])

    def test_import_legacy_keeps_required_inputs_and_copies_original_video(self):
        work = self.folder / 'runs' / 'old_run'
        work.mkdir()
        source = self.folder / 'original.mp4'
        source.write_bytes(b'original video')
        save_json(work / 'frames.json', {'source_video': str(source)})
        save_json(work / 'article.json', {'title': 'Approved old title'})
        brief = self.client.get('/api/runs/old_run/brief').json
        self.assertEqual(brief['fields']['name'], 'Approved old title')
        self.assertEqual(brief['fields']['controls_mobile'], '')
        self.assertTrue(brief['video_available'])
        bad = self.client.post('/api/games', data={**inputs(), 'controls_pc':'', 'import_run':'old_run'}, headers=self.headers)
        self.assertEqual(bad.status_code, 400)
        response = self.client.post('/api/games', data={**inputs(), 'import_run':'old_run'}, headers=self.headers)
        self.assertEqual(response.status_code, 201, response.text)
        saved = Path(response.json['game']['data']['video_path'])
        self.assertNotEqual(saved, source)
        self.assertEqual(saved.read_bytes(), source.read_bytes())
        self.assertEqual(source.read_bytes(), b'original video')


class WorkerIntegrationTests(unittest.TestCase):
    def test_real_orchestrator_pauses_twice_then_exports_two_words_without_repeating_vision(self):
        import admin_worker
        from test_pipeline import fixtures, translated_fixture
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp)
            article, sources, images, frames = fixtures(work)
            frames['contact_sheets'] = []
            save_json(work / 'frames.json', frames)
            save_json(work / 'game_brief.json', {**inputs(), 'video_path': 'fixture.mp4'})
            cfg = {**load_json(ROOT / 'config.json'),'editorial_profile':'legacy'}
            save_json(work / 'admin_config.json', cfg)
            analysis = {'game_title': 'Block Test', 'game_objects': [
                {'id':'OBJ001','name':'Player','confidence':'high','frame_ids':['FRAME001'],
                 'observed_behavior':'Runs along the tracks'}], 'unverified_mechanics':[]}
            calls = []
            def model(stage, path, config, **kwargs):
                calls.append(stage)
                if stage == 'analyze':
                    result, name = analysis, 'analysis.json'
                elif stage == 'notes':
                    result, name = {'context':[], 'player_psychology':[], 'genre_and_competitors':[],
                                    'unsupported_questions':['Is a jump supported?']}, 'research_notes.json'
                elif stage == 'draft':
                    result, name = article, 'article.json'
                else:
                    result, name = {'pass_editorial':True, 'issues':[]}, 'critique.json'
                save_json(path / name, result)
                return result
            def collect(path, config):
                save_json(path / 'sources.json', {'sources':sources})
                save_json(path / 'images.json', {'images':images})
                return sources, images
            # fixtures() already writes frames.json, so resume must reuse it.
            with patch.object(sys, 'argv', ['admin_worker.py','--run-dir',str(work)]), \
                 patch('run.codex_call', side_effect=model), \
                 patch('run.collect', side_effect=collect), \
                 patch('run.extract_frames', side_effect=AssertionError('Existing frames must be reused')), \
                 patch('run.ensure_vietnamese_translation', return_value=translated_fixture(article)):
                self.assertEqual(admin_worker.main(), 3)
                self.assertEqual(load_json(work / 'worker_result.json')['status'], 'waiting')
                save_answers(work, [], approve=True)
                self.assertEqual(admin_worker.main(), 3)
                questions = load_json(work / 'owner_questions.json')['questions']
                save_answers(work, [{'id':q['id'], 'decision':'excluded'} for q in questions if q['decision']=='pending'], approve=True)
                self.assertEqual(admin_worker.main(), 0)
            self.assertEqual(calls, ['analyze','notes','draft','critique'])
            manifest = load_json(work / 'export_manifest.json')
            self.assertEqual(set(manifest['files']), {'docx_en','docx_vi'})
            self.assertTrue(all(Path(path).is_file() for path in manifest['files'].values()))
            self.assertEqual(len(list((work / 'output').iterdir())), 2)


class ProcessManagementTests(unittest.TestCase):
    def test_real_child_process_is_stopped_and_snapshot_is_frozen(self):
        from game_seo.admin_jobs import Jobs
        from game_seo.admin_store import Store
        from game_seo.local_process import ProcessTree
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            video = folder / 'game.mp4'
            video.write_bytes(b'fixture')
            worker = folder / 'fake_worker.py'
            worker.write_text(
                "import subprocess,sys,time\n"
                "from pathlib import Path\n"
                "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(120)'])\n"
                "Path(sys.argv[1]).write_text(str(child.pid))\n"
                "time.sleep(120)\n", encoding='utf-8')
            marker = folder / 'child.pid'
            def factory(command, **kwargs):
                return ProcessTree([sys.executable, str(worker), str(marker)], **kwargs)
            store = Store(folder / 'db')
            manager = Jobs(store, folder / 'runs', process_factory=factory)
            game = store.save_game({**inputs(), 'video_path': str(video)})
            try:
                job = manager.start(game, {})
                deadline = time.monotonic() + 10
                while not marker.exists() and time.monotonic() < deadline:
                    time.sleep(.05)
                self.assertTrue(marker.exists())
                child_pid = int(marker.read_text())
                # Hold a child handle before Stop so PID reuse cannot influence the assertion.
                import os
                if os.name == 'nt':
                    import ctypes
                    from ctypes import wintypes
                    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
                    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
                    kernel.OpenProcess.restype = wintypes.HANDLE
                    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
                    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
                    child_handle = kernel.OpenProcess(0x100000, False, child_pid)
                    self.assertTrue(child_handle)
                with self.assertRaisesRegex(ValueError, 'Đang có'):
                    manager.start(game, {})
                store.save_game({**inputs(), 'name': 'Edited during run', 'video_path': str(video)}, game['id'])
                self.assertEqual(store.job(job['id'])['data']['name'], 'Block Test')
                manager.stop(job['id'])
                deadline = time.monotonic() + 10
                while manager.active and time.monotonic() < deadline:
                    time.sleep(.05)
                self.assertEqual(store.job(job['id'])['status'], 'stopped')
                if os.name == 'nt':
                    try:
                        self.assertEqual(kernel.WaitForSingleObject(child_handle, 5000), 0)
                    finally:
                        kernel.CloseHandle(child_handle)
            finally:
                manager.close()
                deadline = time.monotonic() + 10
                while manager.active and time.monotonic() < deadline:
                    time.sleep(.05)


if __name__ == '__main__':
    unittest.main()
