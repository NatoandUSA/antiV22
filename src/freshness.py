"""How fresh is a keyword? One shared, batched answer for every table.

WHY THIS EXISTS
Staff read six different tables (Trending, Opportunities, Hidden gems, Build
Queue, Newest winners, the Inbox) and none of them said WHEN a keyword entered
our data. "We want fresh new keywords everyday" is unanswerable if a row we
first saw on 2026-07-05 looks identical to one discovered an hour ago.

WHAT IS ACTUALLY STORED — and what is not
Only ONE of the three timestamps in the request genuinely exists:

  added     REAL. `discovered_keywords.captured_at` (every feed pull appends)
            and the master's `collected_at` column. We take the EARLIER of the
            two, because the feed usually sees a keyword days before it is
            written to the master.
  analyzed  NOT separately stored. The master carries one `collected_at` and no
            enriched-at, so there is nothing honest to print per row.
  ranked    NOT stored at all. Every score on these pages is computed live on
            page load, so the only true answer is "just now" — a table-level
            fact, not a per-row column.

So this module answers "added", and the callers print the live-ranking fact once
per table instead of fabricating two more columns that would repeat the render
clock 40 times and look like measurements.

NEW IS NOT A NULL
A keyword we have never seen before returns None, which renders as NEW. That is
the most useful cell in the column, not a missing value — it is the fresh
discovery the team is looking for.

BATCHED ON PURPOSE
One SQLite round trip and one CSV read per page, cached by file mtime. The naive
shape - a query per row - is 40 open/query/close cycles per table.
"""
import csv
import sqlite3
from datetime import date, datetime
from pathlib import Path

MASTER = "keyword_data.csv"
DB = "data/agent.db"

NEW = "NEW"

_SNAP = {}


def _stamp(*paths):
    out = []
    for p in paths:
        try:
            st = Path(p).stat()
            out.append((str(p), st.st_mtime, st.st_size))
        except OSError:
            out.append((str(p), 0, 0))
    return tuple(out)


def _day(value):
    """The date part of a stamp, however it was written. None when unreadable."""
    text = str(value or "").strip()
    if len(text) < 10:
        return None
    head = text[:10]
    try:
        datetime.strptime(head, "%Y-%m-%d")
    except ValueError:
        return None
    return head


def _load(master=None, db=None):
    """{keyword: earliest date seen} across both sources. Never raises."""
    m = str(master or MASTER)
    d = str(db or DB)
    key = _stamp(m, d)
    hit = _SNAP.get(key)
    if hit is not None:
        return hit
    seen = {}

    def _keep(kw, day):
        k = str(kw or "").strip().lower()
        if not k or not day:
            return
        old = seen.get(k)
        if old is None or day < old:
            seen[k] = day

    try:                                    # the feed log: usually the earliest
        conn = sqlite3.connect(d)
        try:
            rows = conn.execute(
                "SELECT tag, MIN(captured_at) FROM discovered_keywords "
                "GROUP BY lower(tag)").fetchall()
        finally:
            conn.close()
        for tag, first in rows:
            _keep(tag, _day(first))
    except Exception:  # noqa: BLE001 - no history == everything reads NEW
        pass
    try:
        p = Path(m)
        if p.exists():
            with p.open(newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    _keep(row.get("keyword"), _day(row.get("collected_at")))
    except Exception:  # noqa: BLE001
        pass
    _SNAP.clear()                           # only ever keep the newest state
    _SNAP[key] = seen
    return seen


def first_seen_many(keywords, master=None, db=None):
    """{keyword: 'YYYY-MM-DD' or None} for a whole table in one read."""
    seen = _load(master, db)
    out = {}
    for kw in keywords or []:
        k = str(kw or "").strip().lower()
        out[kw] = seen.get(k) if k else None
    return out


def first_seen(keyword, master=None, db=None):
    """When this keyword first entered our data, or None if never seen."""
    k = str(keyword or "").strip().lower()
    return _load(master, db).get(k) if k else None


def age_label(day, today=None):
    """NEW / today / '3d' / '45d'. Relative, because the question is freshness.

    None is NEW, not blank: a keyword absent from both sources is one we are
    seeing for the first time.
    """
    if not day:
        return NEW
    d = _day(day)
    if not d:
        return NEW
    now = today or date.today()
    if isinstance(now, str):
        now = datetime.strptime(now[:10], "%Y-%m-%d").date()
    try:
        then = datetime.strptime(d, "%Y-%m-%d").date()
    except ValueError:
        return NEW
    n = (now - then).days
    if n <= 0:
        return "today"
    return "%dd" % n


def labels_for(keywords, master=None, db=None, today=None):
    """{keyword: 'NEW' | 'today' | 'Nd'} — what a table column renders."""
    found = first_seen_many(keywords, master, db)
    return {k: age_label(v, today) for k, v in found.items()}


def ranked_note(now=None):
    """The table-level truth: scores are computed on this page load, not stored.

    Printed ONCE per table. Repeating the render clock down a 40-row column
    would look like 40 separate measurements.
    """
    t = now or datetime.now()
    if isinstance(t, str):
        return "_Ranked live " + t + ". **Added** = when the keyword first " \
               "entered your data; **NEW** = first seen in this pull._"
    return ("_Ranked live " + t.strftime("%Y-%m-%d %H:%M")
            + ". **Added** = when the keyword first entered your data; "
              "**NEW** = first seen in this pull._")
