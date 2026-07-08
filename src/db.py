"""SQLite storage: research history, discovered keywords, and API cache."""
import sqlite3
from pathlib import Path

DB_PATH = Path("data/agent.db")


def get_conn():
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS keyword_snapshots (
            id INTEGER PRIMARY KEY,
            captured_at TEXT DEFAULT CURRENT_TIMESTAMP,
            keyword TEXT NOT NULL,
            avg_interest REAL,
            momentum_pct REAL,
            competition INTEGER,
            opportunity REAL
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS discovered_keywords (
            id INTEGER PRIMARY KEY,
            captured_at TEXT DEFAULT CURRENT_TIMESTAMP,
            source TEXT,
            tag TEXT,
            listing_count INTEGER,
            avg_price REAL,
            avg_revenue REAL,
            conversion REAL,
            momentum REAL,
            competition_level TEXT,
            action TEXT,
            opportunity REAL
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS api_cache (
            key TEXT NOT NULL,
            day TEXT NOT NULL,
            payload TEXT,
            PRIMARY KEY (key, day)
        )"""
    )
    return conn


def save_snapshot(rows):
    conn = get_conn()
    conn.executemany(
        "INSERT INTO keyword_snapshots "
        "(keyword, avg_interest, momentum_pct, competition, opportunity) "
        "VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()


def save_discovered(rows):
    conn = get_conn()
    conn.executemany(
        "INSERT INTO discovered_keywords "
        "(source, tag, listing_count, avg_price, avg_revenue, conversion, "
        " momentum, competition_level, action, opportunity) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()


def cache_get(key, day):
    conn = get_conn()
    row = conn.execute(
        "SELECT payload FROM api_cache WHERE key = ? AND day = ?", (key, day)
    ).fetchone()
    conn.close()
    return row[0] if row else None


def cache_put(key, day, payload):
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO api_cache (key, day, payload) VALUES (?, ?, ?)",
        (key, day, payload),
    )
    conn.commit()
    conn.close()


def prune_cache(keep_days=3):
    """Delete api_cache rows older than keep_days. Only *today's* rows are ever
    read, so older days are dead weight — this keeps data/agent.db from growing
    without bound. Returns the number of rows removed."""
    from datetime import date, timedelta
    cutoff = str(date.today() - timedelta(days=max(0, keep_days)))
    conn = get_conn()
    n = conn.execute("DELETE FROM api_cache WHERE day < ?", (cutoff,)).rowcount
    conn.commit()
    conn.close()
    return n


def vacuum():
    """Reclaim freed pages on disk after deletes so the .db file actually shrinks."""
    conn = get_conn()
    conn.execute("VACUUM")
    conn.close()
