import sqlite3
from contextlib import contextmanager

SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version(version INTEGER PRIMARY KEY);
INSERT OR IGNORE INTO schema_version VALUES(1);
CREATE TABLE IF NOT EXISTS documents(
 id TEXT PRIMARY KEY, org_id TEXT NOT NULL, source_id TEXT NOT NULL,
 current_version INTEGER, deleted INTEGER NOT NULL DEFAULT 0,
 UNIQUE(org_id,source_id));
CREATE TABLE IF NOT EXISTS versions(
 doc_id TEXT, version INTEGER, revision INTEGER NOT NULL, hash TEXT NOT NULL,
 title TEXT NOT NULL, source_kind TEXT NOT NULL, roles TEXT NOT NULL, regions TEXT NOT NULL,
 effect_start TEXT, effect_end TEXT, status TEXT NOT NULL, object_key TEXT NOT NULL,
 PRIMARY KEY(doc_id,version), UNIQUE(doc_id,revision));
CREATE TABLE IF NOT EXISTS jobs(
 id TEXT PRIMARY KEY, doc_id TEXT, version INTEGER, state TEXT NOT NULL,
 attempts INTEGER NOT NULL DEFAULT 0, lease REAL, lease_token TEXT, error TEXT,
 UNIQUE(doc_id,version));
CREATE TABLE IF NOT EXISTS chunks(
 id TEXT PRIMARY KEY, doc_id TEXT, version INTEGER, parent_id TEXT,
 kind TEXT, ordinal INTEGER, text TEXT, position TEXT);
CREATE TABLE IF NOT EXISTS lexical_index(chunk_id TEXT PRIMARY KEY, text TEXT);
CREATE TABLE IF NOT EXISTS vector_index(chunk_id TEXT PRIMARY KEY, vector TEXT);
CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, org_id TEXT, user_id TEXT);
CREATE TABLE IF NOT EXISTS messages(
 id TEXT PRIMARY KEY, session_id TEXT, query TEXT, response TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS feedback(
 id TEXT PRIMARY KEY, request_id TEXT, user_id TEXT, comment TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS audit_events(
 id INTEGER PRIMARY KEY AUTOINCREMENT, actor TEXT, action TEXT, target TEXT, created_at TEXT);
CREATE INDEX IF NOT EXISTS chunk_version ON chunks(doc_id,version);
"""

class Database:
    def __init__(self, path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript(SCHEMA)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()
