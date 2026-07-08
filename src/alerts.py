"""Alerts Center — what needs the team's attention today. INTERNAL ONLY.

No Etsy account automation, no auto-publishing. Alerts are:
  - auto-generated from system state (generate()), and
  - optionally added by the team (add()).
Stored in data/alerts/alerts.json. Deduped by (kind, ref). Never logs secrets.
"""
import json
from datetime import date, datetime
from pathlib import Path

STORE = Path("data/alerts/alerts.json")
LEVELS = ("info", "warn", "critical")


def _load_raw():
    if STORE.exists():
        try:
            return json.loads(STORE.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return []
    return []


def _save(rows):
    STORE.parent.mkdir(parents=True, exist_ok=True)
    STORE.write_text(json.dumps(rows, indent=2), encoding="utf-8")


def load(include_resolved=False):
    rows = _load_raw()
    if include_resolved:
        return rows
    return [r for r in rows if not r.get("resolved")]


def add(kind, message, level="info", ref="", source="manual"):
    """Upsert an alert keyed by (kind, ref) so re-generation never duplicates."""
    level = level if level in LEVELS else "info"
    rows = _load_raw()
    key = (kind, ref)
    for r in rows:
        if (r.get("kind"), r.get("ref")) == key and not r.get("resolved"):
            r["message"], r["level"] = message, level
            r["updated_at"] = str(date.today())
            _save(rows)
            return r
    rec = {"id": max([r.get("id", 0) for r in rows], default=0) + 1,
           "kind": kind, "message": message, "level": level, "ref": ref,
           "source": source, "resolved": False,
           "created_at": str(date.today()), "updated_at": str(date.today())}
    rows.append(rec)
    _save(rows)
    return rec


def resolve(aid):
    rows = _load_raw()
    for r in rows:
        if r.get("id") == aid:
            r["resolved"] = True
            r["updated_at"] = str(date.today())
    _save(rows)


def _days_since(iso):
    try:
        d = datetime.strptime(str(iso)[:10], "%Y-%m-%d").date()
        return (date.today() - d).days
    except Exception:  # noqa: BLE001
        return None


def generate():
    """Scan system state and (re)raise internal alerts. Returns the open list.

    Sources: stale keyword data, last daily-run result, feedback listings that
    need a Day-3/7 review, kill/scale flags, and problem suppliers. Read-only on
    everything except the alerts store."""
    # keyword data freshness
    kd = Path("data/processed/keyword_data.csv")
    if not kd.exists():
        add("keyword_data_missing", "No keyword data yet — run daily-run.",
            "warn", "keyword_data", "auto")
    else:
        age = _days_since(datetime.fromtimestamp(kd.stat().st_mtime).date())
        if age is not None and age >= 2:
            add("keyword_data_stale",
                f"Keyword data is {age} days old — run daily-run.", "warn",
                "keyword_data", "auto")
        else:
            resolve_kind("keyword_data_stale")

    # last daily-run result
    summaries = sorted(Path("data/processed").glob("daily_summary_*.json"))
    if summaries:
        try:
            s = json.loads(summaries[-1].read_text(encoding="utf-8"))
            bad = [k for k, v in (s.get("steps") or {}).items() if not v.get("ok")]
            if bad:
                add("daily_run_failed",
                    f"Last daily-run had failed steps: {', '.join(bad)}.",
                    "critical", "daily_run", "auto")
            else:
                resolve_kind("daily_run_failed")
        except Exception:  # noqa: BLE001
            pass

    # feedback: listings that need a Day-3 / Day-7 review, plus kill/scale flags
    try:
        from src import feedback as fb
        for r in fb.load():
            ref = str(r.get("id"))
            age = _days_since(r.get("publish_date") or r.get("added_at"))
            has7 = str(r.get("day_7_views") or "").strip() not in ("", "None")
            has3 = str(r.get("day_3_views") or "").strip() not in ("", "None")
            title = (r.get("title") or r.get("keyword") or r.get("listing_url") or "listing")[:40]
            # Day-3 reminder: only while 3-6 days old and not yet logged; clear it
            # once Day-3 is logged OR the listing has aged into the Day-7 window.
            if age is not None and 3 <= age < 7 and not has3:
                add("needs_day3", f"'{title}' is {age}d live — log Day-3 numbers.",
                    "info", f"fb3-{ref}", "auto")
            else:
                resolve_ref(f"fb3-{ref}")
            # Day-7 reminder: while 7+ days old and not yet logged; clear once logged.
            if age is not None and age >= 7 and not has7:
                add("needs_day7", f"'{title}' is {age}d live — log Day-7 numbers.",
                    "info", f"fb7-{ref}", "auto")
            else:
                resolve_ref(f"fb7-{ref}")
            dec = r.get("decision") or r.get("day7_action")
            if dec == "KILL_LISTING":
                add("should_kill", f"'{title}' → KILL_LISTING per feedback.",
                    "warn", f"kill-{ref}", "auto")
            elif dec == "SCALE_PRODUCT_LINE":
                add("should_scale", f"'{title}' → SCALE_PRODUCT_LINE — expand it.",
                    "info", f"scale-{ref}", "auto")
    except Exception:  # noqa: BLE001
        pass

    # suppliers that hurt us
    try:
        from src import learning
        for sup, n in learning.problem_suppliers().items():
            add("supplier_issue", f"Supplier '{sup}' has {n} refund/issue(s).",
                "warn", f"sup-{sup}", "auto")
    except Exception:  # noqa: BLE001
        pass

    return load()


def resolve_kind(kind):
    """Auto-resolve every open alert of a kind (state recovered)."""
    rows = _load_raw()
    changed = False
    for r in rows:
        if r.get("kind") == kind and not r.get("resolved"):
            r["resolved"] = True
            r["updated_at"] = str(date.today())
            changed = True
    if changed:
        _save(rows)


def resolve_ref(ref):
    """Auto-resolve any open alert with this ref (its condition cleared)."""
    rows = _load_raw()
    changed = False
    for r in rows:
        if r.get("ref") == ref and not r.get("resolved"):
            r["resolved"] = True
            r["updated_at"] = str(date.today())
            changed = True
    if changed:
        _save(rows)


def summary():
    rows = load()
    return {"open": len(rows),
            "critical": sum(1 for r in rows if r["level"] == "critical"),
            "warn": sum(1 for r in rows if r["level"] == "warn"),
            "info": sum(1 for r in rows if r["level"] == "info")}
