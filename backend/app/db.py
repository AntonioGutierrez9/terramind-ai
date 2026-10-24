"""SQLite schema and connection helper. JSON columns hold flexible assumption trees."""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone

from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  profile TEXT NOT NULL,            -- JSON: location, type, strategy, business model, currency...
  assumptions TEXT NOT NULL,        -- JSON: registry keys + unit_mix + sustainability_measures
  meta TEXT NOT NULL,               -- JSON: provenance per variable
  status TEXT NOT NULL DEFAULT 'draft',   -- draft | hypothetical | approved | portfolio | archived
  in_portfolio INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS changes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL,
  batch_id TEXT NOT NULL,
  actor TEXT NOT NULL,              -- user | chatbot | agent:<name> | system
  key TEXT NOT NULL,
  old_value TEXT, new_value TEXT,   -- JSON
  old_meta TEXT, new_meta TEXT,     -- JSON
  reason TEXT,
  undone INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_changes_project ON changes(project_id, id);
CREATE TABLE IF NOT EXISTS pending_changes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL,
  kind TEXT NOT NULL,               -- assumptions | status
  payload TEXT NOT NULL,            -- JSON
  reason TEXT,
  requested_by TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',  -- pending | confirmed | rejected
  created_at TEXT NOT NULL,
  resolved_at TEXT
);
CREATE TABLE IF NOT EXISTS variants (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL,
  kind TEXT NOT NULL,               -- scenario | configuration
  name TEXT NOT NULL,
  payload TEXT NOT NULL,            -- JSON: changes list or override dict
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS research (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL,
  agent TEXT NOT NULL,              -- regulatory | market | cost | financing | sustainability
  request TEXT,
  payload TEXT NOT NULL,            -- JSON (structured findings with sources)
  from_cache INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS research_cache (
  cache_key TEXT PRIMARY KEY,
  agent TEXT NOT NULL,
  request TEXT NOT NULL,
  payload TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS actuals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL,
  month INTEGER NOT NULL,
  data TEXT NOT NULL,               -- JSON: cost, units_sold, avg_price_per_area, collections, debt_balance, progress_pct
  created_at TEXT NOT NULL,
  UNIQUE(project_id, month)
);
CREATE TABLE IF NOT EXISTS ic_memos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL,
  recommendation TEXT NOT NULL,
  memo TEXT NOT NULL,               -- JSON
  metrics TEXT NOT NULL,            -- JSON snapshot from the engine
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chat_messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER,
  role TEXT NOT NULL,               -- user | assistant
  content TEXT NOT NULL,
  extra TEXT,                       -- JSON: tool summaries, changes, pending ids, usage
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS token_usage (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  project_id INTEGER,
  agent TEXT NOT NULL,
  purpose TEXT,
  model TEXT NOT NULL,
  requests INTEGER NOT NULL DEFAULT 0,
  input_tokens INTEGER NOT NULL DEFAULT 0,
  cached_tokens INTEGER NOT NULL DEFAULT 0,
  output_tokens INTEGER NOT NULL DEFAULT 0,
  web_searches INTEGER NOT NULL DEFAULT 0,
  cost_usd REAL NOT NULL DEFAULT 0,
  seconds REAL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,      -- pbkdf2_sha256$salt$digest (never returned)
  first_name TEXT NOT NULL,
  last_name TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS documents (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER,
  owner TEXT,
  filename TEXT NOT NULL,
  kind TEXT NOT NULL,               -- pdf | excel | word | csv | text | image
  mime TEXT,
  size INTEGER NOT NULL,
  path TEXT NOT NULL,               -- stored file under data/uploads (never served to other owners)
  text TEXT,                        -- extracted text (untrusted)
  meta TEXT,                        -- JSON: pages, sheets, truncated...
  analysis TEXT,                    -- JSON: Document agent output
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_documents_project ON documents(project_id);
CREATE TABLE IF NOT EXISTS message_translations (
  message_id INTEGER NOT NULL,
  lang TEXT NOT NULL,               -- en | es
  content TEXT NOT NULL,
  PRIMARY KEY (message_id, lang)
);
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
"""

_lock = threading.RLock()


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def dumps(x) -> str:
    return json.dumps(x, ensure_ascii=False, default=str)


def loads(s):
    return None if s is None else json.loads(s)


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


_conn: sqlite3.Connection | None = None


MIGRATIONS = [("projects", "owner", "TEXT"), ("chat_messages", "owner", "TEXT"), ("token_usage", "owner", "TEXT")]


def get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = connect()
        _conn.executescript(SCHEMA)
        for table, col, typ in MIGRATIONS:  # add columns to databases created before accounts existed
            cols = {r[1] for r in _conn.execute(f"PRAGMA table_info({table})")}
            if col not in cols:
                _conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")
        _conn.execute("CREATE INDEX IF NOT EXISTS ix_projects_owner ON projects(owner)")
        _conn.commit()
    return _conn


@contextmanager
def tx():
    """Serialized transaction (SQLite + one process is plenty for this app)."""
    with _lock:
        conn = get_conn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def query(sql: str, params=()) -> list[sqlite3.Row]:
    with _lock:
        return get_conn().execute(sql, params).fetchall()


def query_one(sql: str, params=()):
    rows = query(sql, params)
    return rows[0] if rows else None
