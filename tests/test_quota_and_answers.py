import tempfile
import unittest
import io
import json
from unittest.mock import patch, MagicMock
from pathlib import Path

from game_seo.admin_store import Store
from game_seo.core import load_json, save_json
from game_seo.quota import capture_quota, read_rate_limits
from game_seo.web_review import save_answers
from test_admin import seed_review


class QuotaAndAnswerTests(unittest.TestCase):
    def test_unfinished_last_call_does_not_claim_an_after_measurement(self):
        with tempfile.TemporaryDirectory() as folder:
            def windows(percent):
                return {'5h': {'used_percent':percent, 'resets_at':100, 'window_minutes':300}}
            capture_quota(folder, 'analyze', 'before', reader=lambda _:windows(20))
            capture_quota(folder, 'analyze', 'after', reader=lambda _:windows(22))
            capture_quota(folder, 'draft', 'before', reader=lambda _:windows(23))
            summary=load_json(Path(folder)/'quota_usage.json')['summary']['5h']
            self.assertIsNone(summary['after_percent'])
            self.assertIsNone(summary['delta_percent_points'])
            self.assertEqual(summary['latest_percent'],23)
            self.assertFalse(summary['measurement_complete'])

    def test_rpc_reads_two_windows_without_model_generation(self):
        process=MagicMock()
        process.stdin=io.StringIO()
        process.stdout=io.StringIO('\n'.join(json.dumps(message) for message in [
            {'id':1,'result':{}},
            {'id':2,'result':{'rateLimitsByLimitId':{'codex':{
                'primary':{'usedPercent':24,'windowDurationMins':300,'resetsAt':100},
                'secondary':{'usedPercent':62,'windowDurationMins':10080,'resetsAt':500}}}}}]))
        with patch('game_seo.quota.shutil.which',return_value='codex.exe'), \
             patch('game_seo.quota.subprocess.Popen',return_value=process) as spawn:
            result=read_rate_limits()
        self.assertEqual(result['5h']['used_percent'],24)
        self.assertEqual(result['week']['used_percent'],62)
        self.assertEqual(spawn.call_args.args[0],['codex.exe','app-server'])
        process.terminate.assert_called_once()

    def test_missing_quota_is_saved_as_unavailable_without_breaking_pipeline(self):
        with tempfile.TemporaryDirectory() as folder:
            def unavailable(_):
                raise RuntimeError('Account not available')
            capture_quota(folder,'draft','before',reader=unavailable)
            doc=load_json(Path(folder)/'quota_usage.json')
            self.assertEqual(doc['summary'],{})
            self.assertEqual(doc['samples'][0]['error'],'Account not available')

    def test_library_snapshot_is_frozen_per_run_and_pending_answers_stay_private(self):
        from game_seo.admin_jobs import Jobs
        from game_seo.stage_context import prepare_stage_context
        from test_admin import inputs
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            store=Store(root/'data')
            video=root/'video.mp4';video.write_bytes(b'test')
            game=store.save_game({**inputs(),'video_path':str(video)})
            rows=[{'kind':'question','question':'Can blocks rotate?','answer':'No','decision':'confirmed'},
                  {'kind':'question','question':'How are points calculated?','answer':'Guess','decision':'pending'}]
            store.remember_answers(game['id'],rows)
            jobs=Jobs(store,root/'runs')
            with patch.object(jobs,'_launch',side_effect=lambda job:job):
                job=jobs.start(game,{})
            path=jobs.workdir(job)/'answer_library.json'
            original=path.read_bytes()
            entry=next(e for e in store.answers_for_game(game['id']) if e['question']['decision']=='confirmed')
            store.update_saved_answer(game['id'],entry['key'],'Yes','confirmed',entry['updated'])
            self.assertEqual(path.read_bytes(),original)
            context=load_json(prepare_stage_context(jobs.workdir(job),'analyze'))
            self.assertEqual(len(context['answer_library.json']['entries']),1)
            self.assertEqual(context['answer_library.json']['entries'][0]['question']['answer'],'No')
            self.assertNotIn('answer_library.json',load_json(prepare_stage_context(jobs.workdir(job),'translate')))

    def test_backfill_does_not_overwrite_edited_library_or_lose_older_confirmations(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);store=Store(root/'data')
            game=store.save_game({'name':'Test'})
            store.add_job(game,'old','old');store.add_job(game,'new','new')
            question={'kind':'question','question':'Can it jump?','answer':'Yes','decision':'confirmed'}
            save_json(root/'runs/old/owner_questions.json',{'questions':[question]})
            save_json(root/'runs/new/owner_questions.json',{'questions':[{**question,'answer':'','decision':'pending'}]})
            store.backfill_answers(root/'runs')
            entry=store.answers_for_game(game['id'])[0]
            self.assertEqual(entry['question']['answer'],'Yes')
            store.update_saved_answer(game['id'],entry['key'],'No','confirmed',entry['updated'])
            store.backfill_answers(root/'runs')
            self.assertEqual(store.answers_for_game(game['id'])[0]['question']['answer'],'No')

    def test_quota_snapshots_are_persisted_and_reset_has_no_delta(self):
        with tempfile.TemporaryDirectory() as folder:
            before = {'5h': {'used_percent': 20, 'resets_at': 100, 'window_minutes': 300},
                      'week': {'used_percent': 40, 'resets_at': 500, 'window_minutes': 10080}}
            after = {'5h': {'used_percent': 25, 'resets_at': 100, 'window_minutes': 300},
                     'week': {'used_percent': 2, 'resets_at': 900, 'window_minutes': 10080}}
            capture_quota(folder, 'draft', 'before', reader=lambda _: before)
            capture_quota(folder, 'draft', 'after', reader=lambda _: after)
            doc = load_json(Path(folder) / 'quota_usage.json')
            self.assertEqual(doc['summary']['5h']['delta_percent_points'], 5)
            self.assertIsNone(doc['summary']['week']['delta_percent_points'])
            self.assertEqual(len(doc['samples']), 2)

    def test_saved_answers_reuse_on_next_run_and_can_be_edited(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            store = Store(root / 'data')
            first = root / 'first'
            first.mkdir()
            _, _, doc = seed_review(first)
            pending = [q for q in doc['questions'] if q['decision'] == 'pending']
            changes = [{'id': q['id'], 'decision': 'excluded'} for q in pending]
            changes[0] = {'id': pending[0]['id'], 'decision': 'confirmed',
                          'answer': 'This is a crate with no bonus effect.'}
            approved = save_answers(first, changes, approve=True)
            store.remember_answers('game-1', approved['questions'])
            self.assertEqual(len(store.answers_for_game('game-1')), len(doc['questions']))

            second = root / 'second'
            second.mkdir()
            save_json(second / 'answer_library.json', {'entries': store.answers_for_game('game-1')})
            analysis, frames, questions = seed_review(second)
            self.assertEqual(questions['state'], 'approved')
            self.assertEqual(questions['questions'][1]['answer'], 'This is a crate with no bonus effect.')

            entry = next(e for e in store.answers_for_game('game-1') if e['question']['kind'] == 'object')
            store.update_saved_answer('game-1', entry['key'], 'This crate blocks the path.',
                                      'confirmed', entry['updated'])
            third = root / 'third'
            third.mkdir()
            save_json(third / 'answer_library.json', {'entries': store.answers_for_game('game-1')})
            _, _, edited = seed_review(third)
            self.assertEqual(edited['questions'][1]['answer'], 'This crate blocks the path.')

    def test_unmatched_question_still_requires_owner_review(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            work = root / 'run'
            work.mkdir()
            save_json(work / 'answer_library.json', {'entries': []})
            _, _, questions = seed_review(work)
            self.assertEqual(questions['state'], 'pending')
            self.assertTrue(any(q['decision'] == 'pending' for q in questions['questions']))


if __name__ == '__main__':
    unittest.main()
