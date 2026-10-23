"""Local administrator sessions layered on existing host/origin/CSRF checks."""
import secrets
import threading
import time
from functools import wraps
from flask import abort, session
from werkzeug.security import generate_password_hash, check_password_hash
from .capacity_db import audit
from .secret_store import Secrets


class AdminAuth:
    def __init__(self, app, store):
        self.store = store
        self.lock = threading.Lock()
        self.failures = []
        vault = Secrets(store)
        key = vault.get('admin-session')
        if not key:
            key = secrets.token_hex(32)
            vault.put('admin-session', key)
        app.secret_key = key
        app.config.update(SESSION_COOKIE_NAME='office_admin', SESSION_COOKIE_HTTPONLY=True,
                          SESSION_COOKIE_SAMESITE='Strict', PERMANENT_SESSION_LIFETIME=3600)

    def configured(self):
        with self.store.connection() as db:
            return bool(db.execute('SELECT 1 FROM admin_auth WHERE id=1').fetchone())

    @staticmethod
    def allowed():
        return session.get('role') == 'administrator'

    def setup(self, password):
        if not isinstance(password, str) or not 12 <= len(password) <= 200:
            raise ValueError('Mật khẩu admin cần từ 12 đến 200 ký tự.')
        hashed = generate_password_hash(password)
        with self.lock, self.store.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM admin_auth WHERE id=1').fetchone():
                abort(409, description='Admin đã được thiết lập.')
            db.execute('INSERT INTO admin_auth VALUES(1,?)', (hashed,))
            audit(self.store, 'admin.setup', 'local-admin', db)
        session.clear()
        session['role'] = 'administrator'
        session.permanent = True

    def login(self, password):
        with self.lock:
            now = time.monotonic()
            self.failures = [t for t in self.failures if t > now-300]
            if len(self.failures) >= 5:
                abort(429, description='Thử đăng nhập quá nhiều. Chờ 5 phút.')
            with self.store.connection() as db:
                row = db.execute('SELECT password_hash FROM admin_auth WHERE id=1').fetchone()
            if not isinstance(password, str) or len(password) > 200 or not row or not check_password_hash(row[0], password):
                self.failures.append(now)
                abort(401, description='Mật khẩu không đúng.')
            self.failures.clear()
        session.clear()
        session['role'] = 'administrator'
        session.permanent = True
        audit(self.store, 'admin.login', 'local-admin')

    def require(self, fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            if not self.allowed():
                abort(403, description='Cần đăng nhập administrator.')
            return fn(*args, **kwargs)
        return wrapped
