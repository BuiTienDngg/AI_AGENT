import json
import re
import tempfile
import time
import unittest
from datetime import datetime,timezone
from pathlib import Path
from unittest.mock import MagicMock,patch

from game_seo.admin_web import create_app
from game_seo.quota_policy import evaluate,quota_state
from game_seo.quota_jsonl import parse_jsonl,read_session_logs
from game_seo.secret_store import Secrets
from game_seo.core import utc_now,load_json,save_json


def windows(remaining=50,reset=None):
    return {key:{'used_percent':100-remaining,'resets_at':reset or time.time()+3600,
                 'window_minutes':minutes} for key,minutes in [('5h',300),('week',10080)]}


class PolicyTests(unittest.TestCase):
    def test_api_cli_uses_env_key_and_redacts_output_without_calling_real_provider(self):
        import os
        import subprocess
        from game_seo.runner import codex_call
        from game_seo.core import ROOT
        with tempfile.TemporaryDirectory() as folder:
            work=Path(folder)
            cfg={**load_json(ROOT/'config.json'),'api_provider':True,'quota_tracking':False}
            def execute(command,**kwargs):
                self.assertIn('model_provider="seo_api"',command)
                self.assertIn('model_providers.seo_api.env_key="GAME_SEO_API_KEY"',command)
                self.assertNotIn('simulation-private-key',' '.join(command))
                save_json(work/'question_translation_output.json',{'translations':[]})
                return subprocess.CompletedProcess(command,0,stdout='simulation-private-key',stderr='simulation-private-key')
            with patch.dict(os.environ,{'GAME_SEO_API_KEY':'simulation-private-key'}), \
                 patch('game_seo.runner.shutil.which',return_value='codex.exe'), \
                 patch('game_seo.runner.subprocess.run',side_effect=execute):
                codex_call('questions_vi',work,cfg)
            for file in (work/'logs').iterdir():
                self.assertNotIn('simulation-private-key',file.read_text())
            cfg['max_job_tokens']=1000
            save_json(work/'token_usage.json',{'measured_totals':{'total_tokens':1000}})
            with patch('game_seo.runner.subprocess.run') as spawn:
                with self.assertRaisesRegex(RuntimeError,'ngân sách'):
                    codex_call('questions_vi',work,cfg)
                spawn.assert_not_called()

    def test_boundaries_both_windows_and_cold_start(self):
        history=[{'result':'completed','delta_5h':1,'delta_week':1}]*3
        for remaining,allowed,state in [(100,True,'AVAILABLE'),(20,True,'LOW_QUOTA'),(13,True,'LOW_QUOTA'),(12,False,'LOW_QUOTA'),(0,False,'EXHAUSTED')]:
            with self.subTest(remaining=remaining):
                p={'windows':windows(remaining),'last_success':utc_now()}
                self.assertEqual(evaluate(p,history=history)['allowed'],allowed)
                self.assertEqual(evaluate(p,history=history)['status'],state)
        self.assertFalse(evaluate({'windows':windows(20),'last_success':utc_now()})['allowed'])
        p={'windows':windows(80),'last_success':utc_now()}
        p['windows']['week']['used_percent']=99
        self.assertFalse(evaluate(p,history=history)['allowed'])

    def test_stale_reset_future_missing_and_malformed(self):
        old=datetime.fromtimestamp(time.time()-500,timezone.utc).isoformat()
        self.assertEqual(quota_state(windows(),old),'STALE')
        self.assertEqual(quota_state(windows(reset=time.time()-1),utc_now()),'STALE')
        self.assertEqual(quota_state({},utc_now()),'UNKNOWN')
        bad=windows();bad['5h']['used_percent']=float('nan')
        self.assertEqual(quota_state(bad,utc_now()),'UNKNOWN')
        self.assertFalse(evaluate({'windows':windows(reset=time.time()-1),'last_success':utc_now()})['allowed'])

    def test_jsonl_corruption_metadata_and_no_reset_fabrication(self):
        event={'timestamp':utc_now(),'payload':{'rate_limits':{
            'primary':{'used_percent':88,'window_minutes':10080,'resets_at':10},
            'secondary':{'used_percent':20,'window_minutes':300,'resets_at':20}}}}
        row=parse_jsonl('broken\n'+json.dumps(event)+'\n{}\n[]')
        self.assertEqual(row['windows']['week']['used_percent'],88)
        self.assertEqual(row['windows']['5h']['used_percent'],20)
        self.assertEqual(quota_state(row['windows'],row['captured']),'STALE')
        self.assertIsNone(parse_jsonl('invalid\n{}'))
        self.assertIsNone(read_session_logs('/not/a/real/path'))


class CapacityIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.app=create_app(self.root/'data',self.root/'runs',probe=lambda p:30)
        self.client=self.app.test_client()
        self.token=re.search(r'name="office-token" content="([^"]+)"',self.client.get('/admin').text)[1]
        self.headers={'X-Office-Token':self.token}
        self.monitor=self.app.extensions['office_accounts'];self.jobs=self.app.extensions['office_jobs']
        self.capacity=self.app.extensions['office_capacity'];self.store=self.app.extensions['office_store']
        self.home=self.root/'codex';self.home.mkdir()
        self.profile=self.monitor.save({'name':'Primary','home':str(self.home)})
        video=self.root/'video.mp4';video.write_bytes(b'fixture')
        self.game=self.store.save_game({'name':'Fixture','video_path':str(video),'site_url':'https://slope3.com/'})
        self.monitor.reader=lambda **kwargs:windows()
        self.monitor.scan()

    def tearDown(self):
        self.monitor.close();self.jobs.close();self.temp.cleanup()

    def enable(self,**changes):
        return self.capacity.configure({'enabled':True,'primary_account':self.profile,**changes})

    def test_admin_auth_viewer_authorization_and_audit(self):
        self.assertEqual(self.client.get('/accounts').status_code,200)
        self.assertNotIn('home',self.client.get('/api/codex/accounts').json['accounts'][0])
        self.assertEqual(self.client.put('/admin/api/policy',json={'enabled':True},headers=self.headers).status_code,403)
        self.assertEqual(self.client.post('/admin/auth/setup',json={'password':'test-admin-password'},headers=self.headers).status_code,200)
        self.assertEqual(self.client.post('/admin/auth/setup',json={'password':'new-admin-password'},headers=self.headers).status_code,409)
        self.assertEqual(self.client.get('/admin/api/audit').status_code,200)
        self.client.post('/admin/auth/logout',headers=self.headers)
        self.assertEqual(self.client.delete('/admin/api/accounts/'+self.profile,headers=self.headers).status_code,403)
        self.assertEqual(self.client.post('/admin/auth/login',json={'password':'wrong'},headers=self.headers).status_code,401)
        self.assertEqual(self.client.post('/admin/auth/login',json={'password':'test-admin-password'},headers=self.headers).status_code,200)
        other=self.app.test_client()
        self.assertEqual(other.patch('/admin/api/accounts/'+self.profile,json={'name':'hacked'},headers=self.headers).status_code,403)

    def test_wait_queue_restart_cancel_and_no_automatic_plus_rotation(self):
        self.monitor.reader=lambda **kwargs:windows(0);self.monitor.scan()
        alternate=self.root/'other';alternate.mkdir()
        self.monitor.save({'name':'Other Plus','home':str(alternate)})
        self.enable()
        self.jobs.process_factory=MagicMock(side_effect=AssertionError('Must not launch'))
        job=self.jobs.start(self.game,{})
        self.assertEqual(job['status'],'waiting_for_capacity')
        restarted=create_app(self.root/'data',self.root/'runs')
        self.assertEqual(restarted.extensions['office_store'].job(job['id'])['status'],'waiting_for_capacity')
        restarted.extensions['office_jobs'].close()
        self.capacity.pump()
        self.jobs.process_factory.assert_not_called()
        self.jobs.stop(job['id'])
        self.assertEqual(self.store.job(job['id'])['status'],'cancelled')

    def test_queued_job_rechecks_then_launches_once(self):
        self.enable()
        self.monitor.reader=lambda **kwargs:windows(0);self.monitor.scan()
        job=self.jobs.start(self.game,{})
        self.monitor.reader=lambda **kwargs:windows(80);self.monitor.scan()
        with self.store.connection() as db:
            db.execute('UPDATE job_assignments SET next_retry=0 WHERE job_id=?',(job['id'],))
        def launch(row):
            self.jobs.active[row['id']]={'fixture':True}
        with patch.object(self.jobs,'_launch',side_effect=launch) as call:
            self.capacity.pump();self.capacity.pump()
            self.assertEqual(call.call_count,1)
        self.jobs.active.clear()
        self.jobs.stop(job['id'])

    def test_idempotency_returns_same_snapshot(self):
        self.enable()
        self.monitor.reader=lambda **kwargs:windows(0);self.monitor.scan()
        first=self.jobs.start(self.game,{},request_key='same-request')
        second=self.jobs.start(self.game,{},request_key='same-request')
        self.assertEqual(first['id'],second['id'])
        self.assertEqual(len(self.store.jobs()),1)

    def test_spawn_failure_releases_assignment_for_manual_retry(self):
        self.enable()
        self.jobs.process_factory=MagicMock(side_effect=RuntimeError('fixture spawn failure'))
        with self.assertRaisesRegex(RuntimeError,'spawn failure'):
            self.jobs.start(self.game,{})
        self.assertEqual(self.store.jobs()[0]['status'],'failed')
        self.assertEqual(self.capacity.jobs_list()[0]['state'],'FAILED')
        self.assertFalse(self.jobs.active)

    def test_api_probe_failure_queues_and_secrets_never_appear(self):
        self.enable(allow_api=True)
        self.monitor.reader=lambda **kwargs:windows(0);self.monitor.scan()
        secret='sk-simulation-not-a-real-key'
        key=self.capacity.save_provider({'name':'Fallback','model':'test-model','api_key':secret,'enabled':True})
        with self.store.connection() as db:
            raw=' '.join(row[0] for row in db.execute('SELECT ciphertext FROM secure_values'))
        self.assertNotIn(secret,raw)
        self.assertNotIn(secret,json.dumps(self.capacity.providers()))
        with patch('game_seo.capacity_service.requests.get',side_effect=RuntimeError(secret)):
            job=self.jobs.start(self.game,{})
        self.assertEqual(job['status'],'waiting_for_capacity')
        self.assertNotIn(secret,json.dumps(self.capacity.providers()))
        self.assertEqual(self.capacity.vault.get('api-'+key),secret)

    def test_api_fallback_env_only_checkpoint_and_account_unchanged(self):
        self.enable(allow_api=True)
        self.monitor.reader=lambda **kwargs:windows(0);self.monitor.scan()
        provider=self.capacity.save_provider({'name':'Fallback','model':'test-model','api_key':'fixture-secret','enabled':True})
        job=self.store.add_job(self.game,'fixture','fixture')
        work=self.jobs.workdir(job);work.mkdir()
        save_json(work/'admin_config.json',{'codex_model':'original'})
        with patch.object(self.capacity,'check_provider',return_value='AVAILABLE'):
            env=self.capacity.admit(job)
        self.assertEqual(env['GAME_SEO_API_KEY'],'fixture-secret')
        self.assertNotIn('fixture-secret',(work/'admin_config.json').read_text())
        self.assertTrue(load_json(work/'admin_config.json')['api_provider'])
        self.assertEqual(self.capacity.settings()['primary_account'],self.profile)
        self.store.update_job(job['id'],'failed','API failure')
        self.capacity.finished(self.store.job(job['id']))
        self.assertEqual(self.capacity.jobs_list()[0]['state'],'FAILED')
        self.assertEqual(self.capacity.providers()[0]['status'],'ERROR')

    def test_migration_repeat_and_running_job_restart_requires_manual_resume(self):
        from game_seo.account_monitor import AccountMonitor
        AccountMonitor(self.store);AccountMonitor(self.store)
        with self.store.connection() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM schema_migrations').fetchone()[0],1)
            db.execute("INSERT INTO job_assignments(job_id,state,updated) VALUES('inflight','RUNNING',?)",(utc_now(),))
        self.capacity.recover()
        self.assertEqual(self.capacity.jobs_list()[0]['state'],'INTERRUPTED')
