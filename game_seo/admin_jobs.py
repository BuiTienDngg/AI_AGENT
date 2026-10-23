"""Single active local run; each new run freezes the game's current input revision."""
from __future__ import annotations

import os
import shutil
import sys
import threading
import uuid
from datetime import datetime
from pathlib import Path

from .core import ROOT, load_json, utc_now, slugify
from .local_process import ProcessTree
from .web_review import atomic_json


class Jobs:
    def __init__(self, store, runs, process_factory=ProcessTree):
        self.store, self.runs = store, Path(runs).resolve()
        self.runs.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.active = {}
        self.capacity = None
        self.process_factory = process_factory
        self.store.recover()

    def workdir(self, job):
        return self.runs / job['run_name']

    def ensure_idle(self):
        if self.active:
            raise ValueError('Đang có một lượt chạy. Hãy dừng hoặc chờ xong trước khi chạy lượt khác.')

    def start(self, game, cfg, request_key=None):
        with self.lock:
            if request_key:
                with self.store.connection() as db:
                    previous = db.execute('SELECT game_id,job_id FROM job_request_keys WHERE key=?',(request_key,)).fetchone()
                if previous:
                    if previous['game_id'] != game['id']:
                        raise ValueError('Idempotency key đã dùng cho game khác.')
                    return self.store.job(previous['job_id'])
            if not self.capacity or not self.capacity.settings()['enabled']:
                self.ensure_idle()
            if not Path(game['data']['video_path']).is_file():
                raise ValueError('Không tìm thấy video đã lưu. Hãy tải lại video cho game.')
            key = uuid.uuid4().hex
            base = slugify(game['data']['name']) + '_' + datetime.now().strftime('%d-%m-%Y_%H-%M-%S')
            run_name = base
            suffix = 1
            while True:
                work = self.runs / run_name
                try:
                    work.mkdir()
                    break
                except FileExistsError:
                    suffix += 1
                    run_name = f'{base}_{suffix}'
            brief = {**game['data'], 'game_id': game['id'], 'input_revision': game['revision'],
                     'created_at': utc_now()}
            atomic_json(work / 'game_brief.json', brief)
            atomic_json(work / 'admin_config.json', {**cfg, 'brand_website': brief['site_url']})
            atomic_json(work / 'answer_library.json', {
                'game_id': game['id'], 'entries': self.store.answers_for_game(game['id']),
                'captured_at': utc_now()})
            job = self.store.add_job(game, run_name, key, execution={
                'model': cfg.get('codex_model'), 'reasoning_effort': cfg.get('model_reasoning_effort')})
            if request_key:
                with self.store.connection() as db:
                    db.execute('INSERT INTO job_request_keys VALUES(?,?,?)',(request_key,game['id'],job['id']))
            return self._launch(job)

    def resume(self, job):
        with self.lock:
            self.ensure_idle()
            job = self.store.job(job['id'])
            if job['status'] not in ('waiting', 'failed', 'stopped', 'interrupted', 'completed', 'waiting_for_capacity', 'cancelled'):
                raise ValueError('Lượt này đang chạy.')
            work = self.workdir(job)
            questions = load_json(work / 'owner_questions.json', default={})
            if questions and questions.get('state') != 'approved':
                raise ValueError('Hãy trả lời và duyệt câu hỏi trước khi chạy tiếp.')
            # A completed job with unchanged input should be a download, not another paid review.
            if job['status'] == 'completed':
                from .objects import draft_needs_refresh
                inventory = load_json(work / 'game_objects.json')
                if not draft_needs_refresh(work, inventory):
                    raise ValueError('Bài đã hoàn tất và đầu vào không đổi. Bạn có thể tải hai file Word.')
            from .objects import draft_needs_refresh
            inventory = load_json(work / 'game_objects.json', default={})
            if (work / 'export_manifest.json').is_file() and draft_needs_refresh(work, inventory):
                archive = work / 'output_history' / uuid.uuid4().hex
                archive.mkdir(parents=True)
                if (work / 'output').is_dir():
                    shutil.copytree(work / 'output', archive / 'output')
                for name in ('export_manifest.json', 'article.json', 'translation_vi.json', 'qa_report.json'):
                    if (work / name).is_file():
                        shutil.copy2(work / name, archive / name)
            return self._launch(job)

    def translate_questions(self, job):
        with self.lock:
            self.ensure_idle()
            job = self.store.job(job['id'])
            if job['status'] in ('running', 'stopping'):
                raise ValueError('Chờ lượt chạy dừng để dịch câu hỏi.')
            from .question_translation import pending_translations
            if not pending_translations(self.workdir(job)):
                return job
            return self._launch(job, task='questions_vi')

    def _launch(self, job, task='article'):
        work = self.workdir(job)
        provider_env = {}
        if task=='article' and self.active and self.capacity and self.capacity.settings()['enabled']:
            self.capacity.defer(job)
            return self.store.job(job['id'])
        if self.capacity:
            if task == 'article':
                provider_env = self.capacity.admit(job,task)
                if provider_env is None:
                    return self.store.job(job['id'])
            else:
                cfg = load_json(work/'admin_config.json',default={})
                assignment = next((a for a in self.capacity.jobs_list() if a['job_id']==job['id']),None)
                if cfg.get('api_provider'):
                    secret = self.capacity.vault.get('api-'+assignment['provider_id']) if assignment else None
                    if not secret:
                        raise ValueError('Thiếu credential API cho lượt này.')
                    provider_env = {'GAME_SEO_API_KEY':secret}
                elif assignment and assignment['kind']=='codex':
                    profile = next((p for p in self.capacity.monitor.profiles() if p['id']==assignment['provider_id']),None)
                    if not profile:
                        raise ValueError('Hồ sơ đã dùng cho lượt này không còn tồn tại.')
                    provider_env = {'CODEX_HOME':profile['home']}
        if not (work / 'answer_library.json').is_file():
            from .web_review import answer_key
            questions = load_json(work / 'owner_questions.json', default={}).get('questions', [])
            atomic_json(work / 'answer_library.json', {
                'game_id': job['game_id'],
                'entries': [{'key': answer_key(q), 'question': q} for q in questions],
                'captured_at': utc_now()})
        config_path = work / 'admin_config.json'
        if config_path.is_file():
            cfg = load_json(config_path)
            if not cfg.get('quota_tracking') and not cfg.get('api_provider'):
                atomic_json(config_path, {**cfg, 'quota_tracking': True})
        result = work / ('worker_result.json' if task == 'article' else 'question_translation_result.json')
        if result.exists():
            result.unlink()
        log = open(work / 'admin.log', 'ab', buffering=0)
        log.write(('\n--- Chạy từ dữ liệu đã lưu: ' + utc_now() + ' ---\n').encode('utf-8'))
        env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUNBUFFERED='1')
        env.update(provider_env)
        try:
            command = [sys.executable, '-u', str(ROOT / 'admin_worker.py'), '--run-dir', str(work)]
            if task != 'article':
                command += ['--task', task]
            tree = self.process_factory(command, cwd=str(ROOT),
                                        env=env, stdout=log, stderr=log)
        except Exception as exc:
            log.close()
            self.store.update_job(job['id'], 'failed' if task == 'article' else job['status'], str(exc))
            if self.capacity and task=='article':
                self.capacity.finished(self.store.job(job['id']))
            raise
        self.active[job['id']] = {'tree': tree, 'stopped': False, 'log': log,
                                  'task': task, 'previous_status': job['status'], 'previous_error': job.get('error', '')}
        if task == 'article':
            self.store.update_job(job['id'], 'running')
        watcher = threading.Thread(target=self._watch, args=(job['id'],), daemon=True)
        self.active[job['id']]['thread'] = watcher
        watcher.start()
        return self.store.job(job['id'])

    def _watch(self, key):
        entry = self.active[key]
        code = entry['tree'].proc.wait()
        with self.lock:
            job = self.store.job(key)
            entry['tree'].close()  # Kill any leftover descendants on exit, too.
            entry['log'].close()
            try:
                filename = 'worker_result.json' if entry['task'] == 'article' else 'question_translation_result.json'
                result = load_json(self.workdir(job) / filename, default={})
            except (ValueError, OSError):
                result = {}
            if entry['task'] != 'article':
                message = ('Đã dừng dịch câu hỏi.' if entry['stopped'] else
                           '' if code == 0 and result.get('status') == 'translated' else
                           result.get('error') or 'Dịch câu hỏi chưa thành công. Có thể thử lại.')
                previous_error = entry['previous_error']
                self.store.update_job(key, entry['previous_status'],
                                      '\n'.join(text for text in (previous_error, message) if text))
            elif entry['stopped']:
                self.store.update_job(key, 'stopped', 'Đã dừng. Khung hình và các bước hoàn tất được giữ để chạy tiếp.')
            elif code == 3 and result.get('status') == 'waiting':
                questions = load_json(self.workdir(job) / 'owner_questions.json', default={})
                self.store.remember_answers(job['game_id'], questions.get('questions', []))
                self.store.update_job(key, 'waiting', result.get('error', ''))
            elif code == 0 and result.get('status') == 'completed' and (self.workdir(job) / 'export_manifest.json').is_file():
                self.store.update_job(key, 'completed')
            else:
                self.store.update_job(key, 'failed', result.get('error') or f'Tiến trình kết thúc với mã {code}. Xem nhật ký.')
            self.active.pop(key, None)
            if self.capacity and entry['task']=='article':
                try:
                    self.capacity.finished(self.store.job(key))
                except Exception:
                    self.capacity.last_error = 'Chưa lưu được thống kê lượt chạy.'

    def stop(self, key):
        with self.lock:
            entry = self.active.get(key)
            if not entry:
                job = self.store.job(key)
                if job and job['status'] in ('waiting_for_capacity','queued'):
                    self.store.update_job(key,'cancelled','Đã hủy bài đang chờ quota.')
                    with self.store.connection() as db:
                        db.execute("UPDATE job_assignments SET state='CANCELLED',updated=? WHERE job_id=?",(utc_now(),key))
                    return
                raise ValueError('Lượt này không còn chạy.')
            entry['stopped'] = True
            if entry['task'] == 'article':
                self.store.update_job(key, 'stopping')
            try:
                entry['tree'].stop()
            except Exception:
                entry['stopped'] = False
                self.store.update_job(key, 'running' if entry['task'] == 'article' else entry['previous_status'],
                                      'Chưa dừng được tiến trình. Hãy thử lại.')
                raise

    def close(self):
        with self.lock:
            entries = list(self.active.values())
            for key in list(self.active):
                self.stop(key)
        for entry in entries:
            if entry.get('thread') and entry['thread'] is not threading.current_thread():
                entry['thread'].join(timeout=10)
