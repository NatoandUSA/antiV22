"""SQLite backend for the team system (auth, activity, tasks).

Stdlib sqlite3 only — no new dependency. One connection per call (safe under
Flask's threaded server). DB lives at data/app.db (gitignored). This module owns
the schema; src/auth.py, src/activity.py and src/tasks.py use it.
"""
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path("data/app.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    email             TEXT UNIQUE NOT NULL,
    display_name      TEXT NOT NULL,
    password_hash     TEXT NOT NULL,
    role              TEXT NOT NULL,
    status            TEXT NOT NULL DEFAULT 'ACTIVE',
    must_change_password INTEGER NOT NULL DEFAULT 0,
    failed_login_count   INTEGER NOT NULL DEFAULT 0,
    locked_until      TEXT,
    last_login_at     TEXT,
    last_login_ip     TEXT,
    created_by        TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS activity_logs (
    event_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp     TEXT NOT NULL,
    user_id       INTEGER,
    user_email    TEXT,
    user_role     TEXT,
    event_type    TEXT NOT NULL,
    module        TEXT,
    action        TEXT,
    entity_type   TEXT,
    entity_id     TEXT,
    keyword       TEXT,
    product_mode  TEXT,
    summary       TEXT,
    ip_address    TEXT,
    user_agent    TEXT,
    success       INTEGER NOT NULL DEFAULT 1,
    error_message TEXT
);
CREATE INDEX IF NOT EXISTS idx_activity_user ON activity_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_activity_type ON activity_logs(event_type);
CREATE INDEX IF NOT EXISTS idx_activity_ts   ON activity_logs(timestamp);

CREATE TABLE IF NOT EXISTS tasks (
    task_id             INTEGER PRIMARY KEY AUTOINCREMENT,
    title               TEXT NOT NULL,
    description         TEXT,
    assigned_to_user_id INTEGER,
    assigned_by_user_id INTEGER,
    role_target         TEXT,
    related_keyword     TEXT,
    related_workspace_id TEXT,
    related_listing_id  TEXT,
    related_supplier    TEXT,
    task_type           TEXT,
    priority            TEXT NOT NULL DEFAULT 'MEDIUM',
    status              TEXT NOT NULL DEFAULT 'TODO',
    due_date            TEXT,
    reviewed_by         INTEGER,
    review_status       TEXT NOT NULL DEFAULT 'NOT_REVIEWED',
    review_notes        TEXT,
    work_report         TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    completed_at        TEXT
);
CREATE INDEX IF NOT EXISTS idx_tasks_assignee ON tasks(assigned_to_user_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status   ON tasks(status);

CREATE TABLE IF NOT EXISTS login_attempts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    email      TEXT,
    ip_address TEXT,
    success    INTEGER,
    timestamp  TEXT
);

CREATE TABLE IF NOT EXISTS approvals (
    approval_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id    TEXT,
    keyword         TEXT,
    decision        TEXT NOT NULL,          -- APPROVED / REJECTED
    by_user_id      INTEGER,
    by_email        TEXT,
    note            TEXT,
    gate_snapshot   TEXT,
    created_at      TEXT NOT NULL
);

-- Team feedback ABOUT THE TOOL (bug/idea/UX) — distinct from sales feedback.
-- Any member submits; owner/managers mark items resolved.
CREATE TABLE IF NOT EXISTS tool_feedback (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  TEXT NOT NULL,
    user_id     INTEGER,
    author      TEXT,
    category    TEXT,
    message     TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'open',   -- open / resolved
    resolved_by TEXT,
    resolved_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_feedback_status ON tool_feedback(status);
"""


@contextmanager
def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _add_column(c, table, col, decl):
    """Idempotent migration: add a column to an existing table if it's missing
    (CREATE TABLE IF NOT EXISTS never alters an already-created table)."""
    have = [r[1] for r in c.execute(f"PRAGMA table_info({table})").fetchall()]
    if col not in have:
        c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")


def init_db():
    with connect() as c:
        c.executescript(SCHEMA)
        _add_column(c, "tasks", "work_report", "TEXT")   # V27.6: staff work report


def q(sql, params=(), one=False):
    with connect() as c:
        cur = c.execute(sql, params)
        rows = cur.fetchall()
    rows = [dict(r) for r in rows]
    if one:
        return rows[0] if rows else None
    return rows


def execute(sql, params=()):
    with connect() as c:
        cur = c.execute(sql, params)
        return cur.lastrowid
