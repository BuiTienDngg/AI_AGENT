import os
import re
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from game_seo.account_monitor import AccountMonitor
from game_seo.admin_store import Store
from game_seo.admin_web import create_app


class AccountTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.home = self.root / 'profile'
        self.home.mkdir()
        (self.home / 'auth.json').write_text('do-not-read-or-delete')
        self.store = Store(self.root / 'data')
        self.reader = MagicMock(return_value={'5h': {'used_percent': 90, 'resets_at': 100, 'window_minutes': 300},
                                              'week': {'used_percent': 20, 'resets_at': 200, 'window_minutes': 10080}})
        self.monitor = AccountMonitor(self.store, reader=self.reader)

    def tearDown(self):
        self.monitor.close()
        self.temp.cleanup()

    def save(self, **changes):
        return self.monitor.save({'name': 'Editor', 'home': str(self.home), **changes})

    def test_crud_persists_and_never_deletes_auth(self):
        key = self.save()
        self.monitor.scan()
        self.assertTrue(self.monitor.profiles()[0]['low'])
        self.monitor.save({'name': 'Renamed', 'home': str(self.home), 'enabled': False, 'warning': 10}, key)
        rows = AccountMonitor(self.store).profiles()
        self.assertEqual(rows[0]['name'], 'Renamed')
        self.assertFalse(rows[0]['enabled'])
        self.reader.reset_mock()
        self.monitor.scan()
        self.reader.assert_not_called()
        self.monitor.delete(key)
        self.assertEqual(self.monitor.profiles(), [])
        self.assertEqual((self.home / 'auth.json').read_text(), 'do-not-read-or-delete')
        with self.store.connection() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM codex_profile_samples').fetchone()[0], 0)

    def test_failed_read_preserves_last_success_and_hides_diagnostics(self):
        self.save()
        self.monitor.scan()
        before = self.monitor.profiles()[0]
        self.reader.side_effect = RuntimeError('sensitive-bearer-token')
        self.monitor.scan()
        after = self.monitor.profiles()[0]
        self.assertEqual(after['windows'], before['windows'])
        self.assertEqual(after['last_success'], before['last_success'])
        self.assertTrue(after['error'])
        self.assertNotIn('sensitive', after['error'])
        self.assertFalse(after['low'])

    def test_profile_validation_and_duplicate_path(self):
        self.save()
        for change in ({'home':'relative'}, {'name':''}, {'warning':float('nan')},
                       {'warning':True}, {'enabled':'yes'}):
            with self.assertRaises(ValueError):
                self.save(**change)
        with self.assertRaises(ValueError):
            self.save(name='Duplicate')

    def test_delete_while_reading_does_not_recreate_profile_or_sample(self):
        key = self.save()
        self.reader.side_effect = lambda **kwargs: (self.monitor.delete(key) or {})
        self.monitor.scan()
        self.assertEqual(self.monitor.profiles(), [])
        with self.store.connection() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM codex_profile_samples').fetchone()[0], 0)

    def test_home_edit_invalidates_old_quota(self):
        key = self.save()
        self.monitor.scan()
        other = self.root / 'other'
        other.mkdir()
        self.monitor.save({'name': 'Other', 'home': str(other)}, key)
        self.assertEqual(self.monitor.profiles()[0]['windows'], {})
        self.assertIsNone(self.monitor.profiles()[0]['last_success'])

    def test_worker_and_manual_refresh_do_not_overlap(self):
        entered, release = threading.Event(), threading.Event()
        def reader(**kwargs):
            entered.set()
            release.wait(3)
            return {}
        self.monitor.reader = reader
        self.save()
        self.monitor.start()
        self.assertTrue(entered.wait(2))
        self.assertFalse(self.monitor.trigger())
        release.set()
        self.monitor.close()
        self.assertFalse(self.monitor.thread.is_alive())

    def test_admin_api_csrf_routes_and_persistence(self):
        app = create_app(self.root/'api-data', self.root/'runs')
        client = app.test_client()
        html = client.get('/admin').text
        token = re.search(r'name="office-token" content="([^"]+)"', html)[1]
        headers = {'X-Office-Token': token}
        self.assertEqual(client.post('/admin/auth/setup',json={'password':'fixture-admin-password'},headers=headers).status_code,200)
        body = {'name':'Profile', 'home':str(self.home)}
        self.assertEqual(client.post('/admin/api/accounts', json=body).status_code, 403)
        self.assertEqual(client.post('/admin/api/accounts', json=body, headers={**headers,'Origin':'https://evil.example'}).status_code, 403)
        response = client.post('/admin/api/accounts', json=body, headers=headers)
        self.assertEqual(response.status_code, 201)
        key = response.json['id']
        self.assertEqual(client.put('/admin/api/accounts/'+key, json={**body,'name':'Edited'}, headers=headers).status_code, 200)
        self.assertEqual(client.get('/admin/api/accounts').json['accounts'][0]['name'], 'Edited')
        self.assertEqual(client.get('/api/accounts').status_code, 404)
        self.assertEqual(client.get('/admin', headers={'Host':'evil.example'}).status_code, 403)
        self.assertEqual(client.delete('/admin/api/accounts/'+key, headers=headers).status_code, 200)
        self.assertEqual(client.get('/admin/api/accounts').json['accounts'], [])

    def test_quota_home_is_scoped_to_subprocess(self):
        from game_seo.quota import read_rate_limits
        import io
        import json
        process = MagicMock()
        process.stdin = io.StringIO()
        process.stdout = io.StringIO('\n'.join(json.dumps(m) for m in [
            {'id':1,'result':{}},
            {'id':2,'result':{'rateLimits':{'primary':{'usedPercent':10,'windowDurationMins':300,'resetsAt':100}}}}]))
        prior = os.environ.get('CODEX_HOME')
        with patch('game_seo.quota.shutil.which', return_value='codex.exe'), \
             patch('game_seo.quota.subprocess.Popen', return_value=process) as spawn:
            read_rate_limits(codex_home=str(self.home))
        self.assertEqual(spawn.call_args.kwargs['env']['CODEX_HOME'], str(self.home))
        self.assertEqual(os.environ.get('CODEX_HOME'), prior)
