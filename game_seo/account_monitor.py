"""Read-only quota monitoring of existing Codex profiles; no account selection."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import uuid
from pathlib import Path

from .core import utc_now
from .quota import read_rate_limits


class AccountMonitor:
    interval = 60

    def __init__(self, store, reader=read_rate_limits):
        self.store, self.reader = store, reader
        self.stop_event = threading.Event()
        self.wake = threading.Event()
        self.lock = threading.RLock()
        self.thread = None
        self.scanning = False
        self.last_scan = None
        self.last_trigger = 0.0
        self.after_scan = None
        self.last_error = ''
        with store.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS codex_profiles (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, home TEXT NOT NULL UNIQUE,
                    notes TEXT NOT NULL, enabled INTEGER NOT NULL, warning REAL NOT NULL,
                    updated TEXT NOT NULL, checked TEXT, last_success TEXT,
                    windows TEXT NOT NULL DEFAULT '{}', error TEXT NOT NULL DEFAULT '');
                CREATE TABLE IF NOT EXISTS codex_profile_samples (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, profile_id TEXT NOT NULL,
                    checked TEXT NOT NULL, windows TEXT NOT NULL, error TEXT NOT NULL);
            """)

        from .capacity_db import migrate
        migrate(store)

    def profiles(self):
        with self.store.connection() as db:
            rows = db.execute('SELECT * FROM codex_profiles ORDER BY name,id').fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item['enabled'] = bool(item['enabled'])
            item['windows'] = json.loads(item['windows'])
            from .quota_policy import quota_state
            item['status'] = quota_state(item['windows'],item['last_success'],error=item['error'],warning=item['warning'])
            item['low'] = not item['error'] and any(
                100 - w['used_percent'] <= item['warning'] for w in item['windows'].values())
            result.append(item)
        return result

    @staticmethod
    def validate(data):
        if not isinstance(data, dict):
            raise ValueError('Dữ liệu hồ sơ không hợp lệ.')
        name, home, notes = (data.get(key, '') for key in ('name', 'home', 'notes'))
        if not all(isinstance(value, str) for value in (name, home, notes)):
            raise ValueError('Tên, thư mục và ghi chú phải là văn bản.')
        if not name.strip() or len(name) > 100 or len(notes) > 1000 or len(home) > 500:
            raise ValueError('Tên bắt buộc, tối đa 100 ký tự; ghi chú tối đa 1.000 ký tự.')
        # Empty home explicitly registers the existing default Codex home.
        path = Path(home.strip() or os.environ.get('CODEX_HOME') or Path.home() / '.codex').expanduser()
        if not path.is_absolute() or not path.is_dir():
            raise ValueError('CODEX_HOME phải là thư mục tuyệt đối đã tồn tại và đã đăng nhập bằng Codex.')
        warning = data.get('warning', 20)
        if isinstance(warning, bool) or not isinstance(warning, (int, float)) or not 0 <= warning <= 100:
            raise ValueError('Ngưỡng cảnh báo phải từ 0 đến 100%.')
        enabled = data.get('enabled', True)
        if not isinstance(enabled, bool):
            raise ValueError('Trạng thái theo dõi phải là bật hoặc tắt.')
        return name.strip(), str(path.resolve()), notes.strip(), int(enabled), warning

    def save(self, data, key=None):
        values = self.validate(data)
        model = data.get('model','')
        import re
        if not isinstance(model,str) or (model and not re.fullmatch(r'[a-zA-Z0-9._-]{1,100}',model)):
            raise ValueError('Model ID không hợp lệ.')
        with self.lock, self.store.connection() as db:
            existing = db.execute('SELECT * FROM codex_profiles WHERE id=?', (key,)).fetchone() if key else None
            if key and not existing:
                raise KeyError(key)
            if not key and db.execute('SELECT count(*) FROM codex_profiles').fetchone()[0] >= 20:
                raise ValueError('Tối đa 20 hồ sơ theo dõi.')
            try:
                if existing:
                    db.execute('UPDATE codex_profiles SET name=?,home=?,notes=?,enabled=?,warning=?,updated=? WHERE id=?',
                               (*values, utc_now(), key))
                    if existing['home'] != values[1]:
                        db.execute("UPDATE codex_profiles SET checked=NULL,last_success=NULL,windows='{}',error='' WHERE id=?", (key,))
                        db.execute('DELETE FROM codex_profile_samples WHERE profile_id=?', (key,))
                else:
                    key = uuid.uuid4().hex
                    db.execute('INSERT INTO codex_profiles(id,name,home,notes,enabled,warning,updated) VALUES(?,?,?,?,?,?,?)',
                               (key, *values, utc_now()))
                db.execute('UPDATE codex_profiles SET model=? WHERE id=?',(model,key))
                from .capacity_db import audit
                audit(self.store,'account.update' if existing else 'account.create',key,db)
            except sqlite3.IntegrityError:
                raise ValueError('Thư mục Codex này đã được đăng ký.') from None
        return key

    def delete(self, key):
        with self.lock, self.store.connection() as db:
            if not db.execute('DELETE FROM codex_profiles WHERE id=?', (key,)).rowcount:
                raise KeyError(key)
            db.execute('DELETE FROM codex_profile_samples WHERE profile_id=?', (key,))
            from .capacity_db import audit
            audit(self.store,'account.delete',key,db)
        # Never delete credential files or call logout.

    def scan(self):
        with self.lock:
            if self.scanning:
                return
            self.scanning = True
        try:
            for profile in self.profiles():
                if self.stop_event.is_set():
                    break
                if not profile['enabled']:
                    continue
                windows, error, captured, source = {}, '', utc_now(), 'official'
                try:
                    windows = self.reader(codex_home=profile['home'])
                except Exception:
                    # Do not return raw CLI diagnostics that could contain credentials.
                    error = 'Không đọc được quota. Kiểm tra đăng nhập ChatGPT, kết nối mạng và Codex CLI.'
                    from .quota_jsonl import read_session_logs
                    fallback = read_session_logs(profile['home'])
                    if fallback:
                        windows, captured, source = fallback['windows'],fallback['captured'],fallback['source']
                        error = ''
                checked = utc_now()
                with self.lock, self.store.connection() as db:
                    # A delete or home edit during IO must not restore a stale reading.
                    current = db.execute('SELECT home,enabled FROM codex_profiles WHERE id=?', (profile['id'],)).fetchone()
                    if not current or current['home'] != profile['home'] or not current['enabled']:
                        continue
                    if error:
                        db.execute('UPDATE codex_profiles SET checked=?,error=? WHERE id=?', (checked, error, profile['id']))
                    else:
                        db.execute('UPDATE codex_profiles SET checked=?,last_success=?,windows=?,error=?,source=? WHERE id=?',
                                   (checked, captured, json.dumps(windows), '', source, profile['id']))
                    db.execute('INSERT INTO codex_profile_samples(profile_id,checked,windows,error) VALUES(?,?,?,?)',
                               (profile['id'], checked, json.dumps(windows), error))
                    db.execute('DELETE FROM codex_profile_samples WHERE profile_id=? AND id NOT IN '
                               '(SELECT id FROM codex_profile_samples WHERE profile_id=? ORDER BY id DESC LIMIT 100)',
                               (profile['id'], profile['id']))
        finally:
            with self.lock:
                self.scanning = False
                self.last_scan = utc_now()

    def trigger(self):
        with self.lock:
            if self.scanning or time.monotonic() - self.last_trigger < 30:
                return False
            self.last_trigger = time.monotonic()
            self.wake.set()
            return True

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._loop, name='codex-quota-monitor', daemon=True)
        self.thread.start()

    def _loop(self):
        while not self.stop_event.is_set():
            self.wake.clear()
            try:
                self.scan()
                if self.after_scan and not self.stop_event.is_set():
                    self.after_scan()
                self.last_error = ''
            except Exception:
                self.last_error = 'Chu kỳ giám sát lỗi; sẽ thử lại, backend vẫn hoạt động.'
            self.wake.wait(self.interval)

    def close(self):
        self.stop_event.set()
        self.wake.set()
        if self.thread:
            self.thread.join(timeout=15)
