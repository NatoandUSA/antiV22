"""SQLite storage: research history, discovered keywords, and API cache."""
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path("data/agent.db")


def get_conn():
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    # NOTE: a `keyword_snapshots` table used to be created here for main.py's
    # research(), which imported the src/scoring.py that c65c1b5 deleted. That
    # command has raised on every run since, so the table never held a row (0 in
    # the live agent.db). The keyword time-series the Inbox actually reads is
    # data/history/keyword_snapshots.csv, written by ytx_import - a different
    # store with a different shape. Both the dead command and its writer are now
    # gone; the empty table is left on disk untouched rather than dropped.
    conn.execute(
        """CREATE TABLE IF NOT EXISTS discovered_keywords (
            id INTEGER PRIMARY KEY,
            captured_at TEXT DEFAULT (datetime('now', 'localtime')),
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


def save_discovered(rows):
    """rows are (source, tag, listing_count, avg_price, avg_revenue, conversion,
    momentum, competition_level, action, opportunity) tuples.

    captured_at is stamped explicitly with local time rather than relying on
    the table's default. SQLite's CURRENT_TIMESTAMP is UTC, but the harvest
    cron fires at 06:00 local (Asia/Ho_Chi_Minh, UTC+7) - inside the window
    that maps to the PREVIOUS UTC calendar day. That silently aged every
    day's freshly harvested keyword by one full day in freshness.py, which
    reads this column's date part directly against date.today() (local).
    Existing rows already on disk keep their old UTC stamps - only new
    writes are corrected; there is nothing to safely rewrite retroactively.
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_conn()
    conn.executemany(
        "INSERT INTO discovered_keywords "
        "(captured_at, source, tag, listing_count, avg_price, avg_revenue, "
        " conversion, momentum, competition_level, action, opportunity) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [(now,) + tuple(r) for r in rows],
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
    # DELETE only moves pages to the freelist; the file itself never shrinks.
    # vacuum() existed for exactly this and had no caller, so agent.db sat at
    # 10.9 MB with 1,761 of 2,666 pages free — 66% of the file was reclaimable
    # dead space. Prune is the only thing that frees pages, so reclaim here.
    if n:
        vacuum()
    return n


def vacuum():
    """Reclaim freed pages on disk after deletes so the .db file actually shrinks.
    Never raises: a locked DB must not break the caller's page."""
    try:
        conn = get_conn()
        try:
            conn.isolation_level = None      # VACUUM cannot run in a transaction
            conn.execute("VACUUM")
        finally:
            conn.close()
    except Exception:  # noqa: BLE001 — housekeeping is best-effort
        pass
