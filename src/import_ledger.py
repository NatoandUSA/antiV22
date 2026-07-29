"""Import ledger — WHO added HOW MANY keywords, WHEN, from WHICH channel.

Answers the owner's operational questions directly:
  - "How many keywords today / up to today, from MCP vs extension vs CSV?"
  - "Which staff member imported which keywords?" (or at least how many)

Design: one JSONL file (data/imports/import_history.jsonl), one line per import
event. Growth-by-source ALSO derives from the master CSV itself (collected_at =
first-seen date + source channel), so totals stay correct even for events that
predate the ledger. Honest rule: numbers we can't attribute show as
"extension (no name set)" / "unknown" — never invented.
"""
import csv
import json
import time
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

LEDGER = Path("data/imports/import_history.jsonl")
MASTER = Path("keyword_data.csv")

_MAX_EVENTS = 5000          # ledger read cap (file is append-only)


def record(user=None, channel="", view="", lanes=None, files=0,
           rows=0, kw_new=0, kw_updated=0, leads=0):
    """Append one import event. Never raises (best-effort audit trail).

    kw_new     = brand-new keyword phrases added to the master list.
    kw_updated = existing keywords whose market numbers were refreshed by this
                 import (resends count here, so a re-import never reads as '0').
    leads      = rows captured into the spy / proof / supplier lanes (Etsy /
                 Amazon / Pinterest / Alibaba / ytuong listings) — real work
                 even though they are not keywords.
    """
    try:
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        evt = {
            "ts": time.time(),
            "date": date.today().isoformat(),
            "user": (str(user).strip()[:60] or "unknown") if user else "unknown",
            "channel": str(channel)[:24],       # extension | file-drop | keyword-lab | mcp
            "view": str(view)[:60],
            "lanes": lanes or {},
            "files": int(files or 0),
            "rows": int(rows or 0),
            "kw_new": int(kw_new or 0),
            "kw_updated": int(kw_updated or 0),
            "leads": int(leads or 0),
        }
        with LEDGER.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(evt, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001 — the ledger must never break an import
        pass


def _events():
    if not LEDGER.is_file():
        return []
    out = []
    try:
        with LEDGER.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        return []
    return out[-_MAX_EVENTS:]


def _channel_of(source):
    """Map a master-CSV source value to a human channel."""
    s = (source or "").strip().lower()
    if s.startswith("mcp:"):
        return "MCP (auto)"
    if s.startswith("ext:"):
        return "Extension / file drop"
    if s == "keyword-lab":
        return "Keyword Lab"
    if s.endswith("-lead") or s == "lane-enrich":
        return "Capture lanes"
    return "CSV / other"


def stats(days=14):
    """Growth + attribution summary.

    Returns {total, today, last7, daily:[{date, added, by_channel}],
             by_channel_total, by_user:[{user, today, last7, total}],
             recent_events:[...], note}."""
    today_s = date.today().isoformat()
    d7 = {(date.today() - timedelta(days=i)).isoformat() for i in range(7)}
    d30 = {(date.today() - timedelta(days=i)).isoformat() for i in range(30)}
    window = [(date.today() - timedelta(days=i)).isoformat()
              for i in range(days)]

    # ---- growth by first-seen date + channel, from the master itself ----
    # This is the ONLY reconciling view: every DISTINCT keyword in the base is
    # counted exactly once, so base_by_channel sums to `total`. (The per-user
    # ledger below counts import EVENTS, which over-counts when the same
    # keywords are re-pulled — see the note at the bottom.)
    total = 0
    daily = defaultdict(lambda: defaultdict(int))     # date -> channel -> n
    chan_total = defaultdict(int)                     # channel -> distinct kw
    n_dated = 0                                       # kws with a real date
    try:
        with MASTER.open(encoding="utf-8-sig") as fh:
            for r in csv.DictReader(fh):
                kw = (r.get("keyword") or "").strip()
                if not kw:
                    continue
                total += 1
                d = (r.get("collected_at") or "").strip() or "unknown"
                ch = _channel_of(r.get("source"))
                daily[d][ch] += 1
                chan_total[ch] += 1
                if d != "unknown":
                    n_dated += 1
    except OSError:
        pass
    today_n = sum(daily.get(today_s, {}).values())
    last7_n = sum(sum(v.values()) for k, v in daily.items() if k in d7)
    last30_n = sum(sum(v.values()) for k, v in daily.items() if k in d30)
    day_rows = [{"date": d, "added": sum(daily[d].values()),
                 "by_channel": dict(daily[d])} for d in window if d in daily]

    # ---- WHO, from the ledger (events since the ledger went live) ----
    by_user = defaultdict(lambda: {"today": 0, "last7": 0, "last30": 0,
                                   "total": 0, "rows": 0, "events": 0})
    events = _events()
    for e in events:
        u = e.get("user") or "unknown"
        n = int(e.get("kw_new") or 0)
        by_user[u]["total"] += n
        by_user[u]["rows"] += int(e.get("rows") or 0)
        by_user[u]["events"] += 1
        if e.get("date") == today_s:
            by_user[u]["today"] += n
        if e.get("date") in d7:
            by_user[u]["last7"] += n
        if e.get("date") in d30:
            by_user[u]["last30"] += n
    users = [{"user": u, **v} for u, v in
             sorted(by_user.items(), key=lambda kv: -kv[1]["total"])]

    # how spread-out are the first-seen dates? if nearly everything sits on ONE
    # day, the daily/today/7d/30d numbers are not yet trustworthy (the old
    # re-stamp bug collapsed history) — the render uses this to warn honestly.
    dated_days = len([k for k in daily if k != "unknown"])
    single_day = None
    if dated_days == 1:
        single_day = next(k for k in daily if k != "unknown")

    return {
        "total": total,
        "today": today_n,
        "last7": last7_n,
        "last30": last30_n,
        "daily": day_rows,
        "by_channel_total": dict(chan_total),   # distinct kw per channel -> sums to total
        "base_by_channel": [{"channel": c, "count": n,
                             "pct": round(100 * n / total) if total else 0}
                            for c, n in sorted(chan_total.items(),
                                               key=lambda kv: -kv[1])],
        "dated_days": dated_days,      # how many distinct real first-seen dates exist
        "single_day": single_day,      # set when ALL dated kws share one day
        "by_user": users,
        "recent_events": list(reversed(events[-20:])),
        "note": ("The 'By person' totals count import EVENTS, not distinct "
                 "keywords: when the same keyword list is re-pulled (e.g. MCP "
                 "auto-pull re-sends the same saved searches), every pull "
                 "re-counts those keywords, so the per-person 'new kws' can be "
                 "many times larger than your actual base. Your true base is "
                 "the 'keywords total' number above. collected_at = first-seen "
                 "date; dates before 2026-07-19 were re-stamped on every "
                 "import, so older history is compressed onto one day and "
                 "daily/7d/30d only become reliable going forward."),
    }
