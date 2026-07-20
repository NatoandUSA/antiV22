"""Pipeline Health (V32) - make the data flow SELF-EVIDENT.

The owner's #1 pain across three external reviews: "data goes in but nothing
visibly changes". This module answers, in one glance: which build is running,
how fresh every data file is, what each lane contributes, and whether the
proof tier has fuel. No hidden state - everything here is read from disk.
"""
import json
import subprocess
import time
from pathlib import Path

from src.version import VERSION

_STARTED = time.time()
_GIT_SHA = None


def git_sha():
    """Short git SHA of the RUNNING checkout (cached; '?' when unavailable)."""
    global _GIT_SHA
    if _GIT_SHA is None:
        try:
            _GIT_SHA = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True, text=True, timeout=3,
                cwd=str(Path(__file__).resolve().parent.parent),
            ).stdout.strip() or "?"
        except Exception:  # noqa: BLE001
            _GIT_SHA = "?"
    return _GIT_SHA


def _age(ts):
    if not ts:
        return None
    s = max(0, int(time.time() - ts))
    if s < 60:
        return "just now"
    if s < 3600:
        return f"{s // 60}m ago"
    if s < 86400:
        return f"{s // 3600}h ago"
    return f"{s // 86400}d ago"


def _mtime(p):
    try:
        return Path(p).stat().st_mtime
    except OSError:
        return None


def _lane(pattern_dir):
    d = Path(pattern_dir)
    if not d.is_dir():
        return {"files": 0, "newest": None}
    fs = list(d.glob("*.json")) + list(d.glob("*.csv"))
    if not fs:
        return {"files": 0, "newest": None}
    return {"files": len(fs), "newest": max(f.stat().st_mtime for f in fs)}


def snapshot(mode=None):
    """Everything the health card + /status page need. Cheap: reuses the
    Inbox's own cache for counts/sources."""
    s = {
        "version": VERSION,
        "git_sha": git_sha(),
        "started_ago": _age(_STARTED),
        "master_mtime": _mtime("keyword_data.csv"),
        "lanes": {
            "etsy_spy": _lane("data/imports/etsy_spy"),
            "etsy_proof": _lane("data/imports/etsy_proof"),
            "pinterest": _lane("data/imports/pinterest"),
            "supplier": _lane("data/imports/supplier"),
            "ytrends_ext": _lane("data/imports/ytrends_ext"),
        },
        "learning_mtime": _mtime("data/learning/winner.json"),
    }
    try:
        with open("data/imports/last_import.json", encoding="utf-8") as fh:
            s["last_import"] = json.load(fh)
    except Exception:  # noqa: BLE001
        s["last_import"] = None
    try:
        from src import opportunity_inbox as oi
        d = oi.build_inbox(mode, limit=1)
        s["counts"] = d["counts"]
        s["sources"] = d.get("sources", {})
        s["has_proof"] = d.get("has_proof", False)
    except Exception:  # noqa: BLE001
        s["counts"], s["sources"], s["has_proof"] = {}, {}, False
    # Proof-coverage callout (review #2): say WHY proof is dark, loudly.
    warn = []
    c = s["counts"]
    if s["lanes"]["etsy_spy"]["files"] and not (
            c.get("proven", 0) or c.get("selling", 0)):
        warn.append("Etsy captures are loaded but NONE carry sold/revenue "
                    "columns - capture WITH the HeyEtsy overlay visible, or "
                    "drop an Alura/EverBee export, to light the proof tier.")
    if c.get("needs_enrichment"):
        warn.append(f"{c['needs_enrichment']} lane leads have no market data - "
                    "run Enrich leads via MCP.")
    s["warnings"] = warn
    s["age"] = {
        "master": _age(s["master_mtime"]),
        "captures": _age(s["lanes"]["etsy_spy"]["newest"]),
        "proof": _age(s["lanes"]["etsy_proof"]["newest"]),
        "learning": _age(s["learning_mtime"]),
    }
    return s
