"""Additive SQLite migrations, following the existing sqlite3 architecture."""
import sqlite3
from .core import ROOT, utc_now


def migrate(store):
    with store.connection() as db:
        db.execute('CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY, applied TEXT NOT NULL)')
    for file in sorted((ROOT/'migrations').glob('*.sql')):
        with store.connection() as db:
            if db.execute('SELECT 1 FROM schema_migrations WHERE name=?', (file.name,)).fetchone():
                continue
            try:
                db.executescript('BEGIN IMMEDIATE;\n' + file.read_text(encoding='utf-8'))
                db.execute('INSERT INTO schema_migrations VALUES(?,?)', (file.name, utc_now()))
                db.commit()
            except Exception:
                db.rollback()
                # A second server may have committed this migration while we waited.
                if not db.execute('SELECT 1 FROM schema_migrations WHERE name=?', (file.name,)).fetchone():
                    raise


def audit(store, action, target, db=None):
    if db is not None:
        db.execute('INSERT INTO account_audit_logs(actor,action,target,timestamp) VALUES(?,?,?,?)',
                   ('administrator', action, target, utc_now()))
    else:
        with store.connection() as connection:
            audit(store, action, target, connection)
