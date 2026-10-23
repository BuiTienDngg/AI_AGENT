import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from game_seo.admin_jobs import Jobs
from game_seo.admin_store import Store
from game_seo.core import load_json


class AdminRunNameTests(unittest.TestCase):
    def test_named_runs_are_unique_and_old_runs_keep_their_path(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            video = root / 'video.mp4'
            video.write_bytes(b'fixture')
            store = Store(root / 'data')
            game = store.save_game({'name': '../../Block Blast 3D: Test?',
                                    'video_path': str(video), 'site_url': 'https://slope3.com/'})
            jobs = Jobs(store, root / 'runs')
            old = store.add_job(game, 'admin_legacy', 'legacy')
            with patch('game_seo.admin_jobs.datetime') as clock, \
                 patch.object(jobs, '_launch', side_effect=lambda job: job):
                clock.now.return_value = datetime(2026, 10, 23, 14, 30, 5)
                first = jobs.start(game, {})
                second = jobs.start(game, {})
            self.assertEqual(first['run_name'], 'block-blast-3d-test_23-10-2026_14-30-05')
            self.assertEqual(second['run_name'], first['run_name'] + '_2')
            self.assertEqual(jobs.workdir(first).parent, (root / 'runs').resolve())
            self.assertTrue(jobs.workdir(second).is_dir())
            self.assertEqual(load_json(jobs.workdir(first) / 'game_brief.json')['game_id'], game['id'])
            self.assertEqual(jobs.workdir(old).name, 'admin_legacy')
