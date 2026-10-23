"""Local SQLite records. Input revisions and job snapshots are never overwritten."""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from contextlib import contextmanager
from pathlib import Path

from .core import utc_now


class Store:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.path = self.folder / 'office.sqlite3'
        with self.connection() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS games (
                    id TEXT PRIMARY KEY, data TEXT NOT NULL, revision INTEGER NOT NULL,
                    created TEXT NOT NULL, updated TEXT NOT NULL, deleted INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS revisions (
                    game_id TEXT NOT NULL, revision INTEGER NOT NULL, data TEXT NOT NULL, saved TEXT NOT NULL,
                    PRIMARY KEY(game_id, revision));
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, game_id TEXT NOT NULL, run_name TEXT NOT NULL UNIQUE,
                    revision INTEGER NOT NULL, status TEXT NOT NULL, data TEXT NOT NULL,
                    created TEXT NOT NULL, updated TEXT NOT NULL, error TEXT NOT NULL DEFAULT '');
                CREATE TABLE IF NOT EXISTS answer_library (
                    game_id TEXT NOT NULL, key TEXT NOT NULL, question TEXT NOT NULL,
                    updated TEXT NOT NULL, PRIMARY KEY(game_id, key));
                CREATE TABLE IF NOT EXISTS answer_library_history (
                    id TEXT PRIMARY KEY, game_id TEXT NOT NULL, key TEXT NOT NULL,
                    question TEXT NOT NULL, saved TEXT NOT NULL);
            """)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def unpack(row):
        if row is None:
            return None
        result = dict(row)
        result['data'] = json.loads(result['data'])
        return result

    def games(self):
        with self.connection() as db:
            return [self.unpack(r) for r in db.execute('SELECT * FROM games WHERE deleted=0 ORDER BY updated DESC')]

    def game(self, key, include_deleted=False):
        with self.connection() as db:
            row = db.execute('SELECT * FROM games WHERE id=?', (key,)).fetchone()
            return self.unpack(row) if row and (include_deleted or not row['deleted']) else None

    def save_game(self, data, key=None):
        stamp = utc_now()
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            if key:
                row = db.execute('SELECT * FROM games WHERE id=? AND deleted=0', (key,)).fetchone()
                if not row:
                    raise KeyError(key)
                expected = data.pop('_expected_revision', None)
                if expected is not None and int(expected) != row['revision']:
                    raise ValueError('Game đã được sửa ở tab khác. Hãy tải lại trước khi lưu.')
                revision = row['revision'] + 1
                db.execute('UPDATE games SET data=?,revision=?,updated=? WHERE id=?',
                           (json.dumps(data, ensure_ascii=False), revision, stamp, key))
            else:
                key = uuid.uuid4().hex
                revision = 1
                db.execute('INSERT INTO games(id,data,revision,created,updated) VALUES(?,?,?,?,?)',
                           (key, json.dumps(data, ensure_ascii=False), revision, stamp, stamp))
            db.execute('INSERT INTO revisions VALUES(?,?,?,?)',
                       (key, revision, json.dumps(data, ensure_ascii=False), stamp))
        return self.game(key)

    def delete_game(self, key):
        with self.connection() as db:
            db.execute('UPDATE games SET deleted=1,updated=? WHERE id=?', (utc_now(), key))

    def jobs(self):
        with self.connection() as db:
            return [self.unpack(r) for r in db.execute('SELECT * FROM jobs ORDER BY created DESC, rowid DESC')]

    def job(self, key):
        with self.connection() as db:
            return self.unpack(db.execute('SELECT * FROM jobs WHERE id=?', (key,)).fetchone())

    def add_job(self, game, run_name, key, execution=None):
        now = utc_now()
        with self.connection() as db:
            db.execute('INSERT INTO jobs(id,game_id,run_name,revision,status,data,created,updated) VALUES(?,?,?,?,?,?,?,?)',
                       (key, game['id'], run_name, game['revision'], 'running',
                        json.dumps({**game['data'], **({'execution': execution} if execution else {})},
                                   ensure_ascii=False), now, now))
        return self.job(key)

    def update_job(self, key, status, error=''):
        with self.connection() as db:
            db.execute('UPDATE jobs SET status=?,error=?,updated=? WHERE id=?', (status, error, utc_now(), key))

    def recover(self):
        with self.connection() as db:
            db.execute("UPDATE jobs SET status='interrupted',error=?,updated=? WHERE status IN ('running','stopping')",
                       ('Ứng dụng đã đóng giữa chừng. Có thể chạy tiếp từ dữ liệu đã lưu.', utc_now()))

    def answers_for_game(self, game_id):
        with self.connection() as db:
            rows = db.execute('SELECT key,question,updated FROM answer_library WHERE game_id=? ORDER BY updated DESC',
                              (game_id,)).fetchall()
        return [{'key': row['key'], 'question': json.loads(row['question']), 'updated': row['updated']}
                for row in rows]

    def remember_answers(self, game_id, questions, *, only_new=False, allow_downgrade=False):
        from .web_review import answer_key
        saved = 0
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            for question in questions:
                if question.get('decision') not in ('pending', 'observed', 'confirmed', 'excluded'):
                    continue
                if question['decision'] == 'confirmed' and not question.get('answer'):
                    continue
                key = answer_key(question)
                old = db.execute('SELECT question FROM answer_library WHERE game_id=? AND key=?',
                                 (game_id, key)).fetchone()
                if old and only_new:
                    continue
                if old and not allow_downgrade:
                    previous = json.loads(old['question'])
                    if previous.get('decision') in ('confirmed', 'excluded') and question['decision'] in ('pending', 'observed'):
                        continue
                payload = json.dumps({k: question.get(k, '') for k in (
                    'kind', 'original_name', 'original_question', 'name', 'appearance',
                    'question', 'question_vi', 'answer', 'decision')}, ensure_ascii=False)
                if old and old['question'] == payload:
                    continue
                stamp = datetime.now(timezone.utc).isoformat(timespec='microseconds')
                db.execute('INSERT INTO answer_library_history VALUES(?,?,?,?,?)',
                           (uuid.uuid4().hex, game_id, key, payload, stamp))
                db.execute('INSERT INTO answer_library VALUES(?,?,?,?) '
                           'ON CONFLICT(game_id,key) DO UPDATE SET question=excluded.question,updated=excluded.updated',
                           (game_id, key, payload, stamp))
                saved += 1
        return saved

    def update_saved_answer(self, game_id, key, answer, decision, expected_updated):
        if decision not in ('pending', 'observed', 'confirmed', 'excluded') or not isinstance(answer, str) or len(answer) > 12000:
            raise ValueError('Câu trả lời hoặc quyết định không hợp lệ.')
        if decision == 'confirmed' and not answer.strip():
            raise ValueError('Nhập câu trả lời trước khi xác nhận.')
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT question,updated FROM answer_library WHERE game_id=? AND key=?',
                             (game_id, key)).fetchone()
            if not row:
                raise KeyError(key)
            if row['updated'] != expected_updated:
                raise ValueError('Câu trả lời đã đổi ở tab khác. Hãy tải lại.')
            question = json.loads(row['question'])
            question.update(answer=answer.strip(), decision=decision)
            payload = json.dumps(question, ensure_ascii=False)
            stamp = datetime.now(timezone.utc).isoformat(timespec='microseconds')
            db.execute('INSERT INTO answer_library_history VALUES(?,?,?,?,?)',
                       (uuid.uuid4().hex, game_id, key, payload, stamp))
            db.execute('UPDATE answer_library SET question=?,updated=? WHERE game_id=? AND key=?',
                       (payload, stamp, game_id, key))
        return {'key': key, 'question': question, 'updated': stamp}

    def backfill_answers(self, runs):
        """Import existing per-run owner answers once, newest run first."""
        from .core import load_json
        runs = Path(runs)
        documents = []
        for job in self.jobs():
            path = runs / job['run_name'] / 'owner_questions.json'
            try:
                if path.is_file():
                    documents.append((job['game_id'], load_json(path).get('questions', [])))
            except (OSError, ValueError):
                continue
        for settled in (True, False):
            for game_id, rows in documents:
                self.remember_answers(game_id, [q for q in rows
                    if (q.get('decision') in ('confirmed', 'excluded')) == settled], only_new=True)
