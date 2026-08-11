"""Enrichment drain — a bounded, ledger-recording wrapper around enrich.run(),
so the web button, the CLI, and the post-harvest scheduler hook all trigger
the exact same enrichment path instead of three different ones.

enrich.run() already does the real per-keyword work (per-keyword timeout,
2-strike circuit breaker, honest-nulls, atomic write + backup, resumable).
This module only adds: a default bound suitable for an unattended/web-
triggered call, and a persisted run record - same shape as import_ledger.py
(one JSONL line per event, best-effort, never raises).
"""
import json
import time
import uuid
from pathlib import Path

from src import enrich
from src import opportunity_inbox as oi

LEDGER = Path("data/enrichment_runs.jsonl")
_MAX_EVENTS = 2000

# A web click must return in a reasonable time (proxy/tunnel timeouts, and the
# operator is waiting). ~11-17s/keyword measured live means 12 keywords could
# take 3+ minutes worst case, so the button gets a small bound; a scheduler
# call (no one waiting) should pass a larger limit/max_runtime_s explicitly.
DEFAULT_LIMIT = 12
DEFAULT_MAX_RUNTIME_S = 90


def _queued(mode):
    return oi.build_inbox(mode, limit=1)["counts"].get("needs_enrichment", 0)


def _append(evt):
    try:
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        with LEDGER.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(evt, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001 - the ledger must never break a run
        pass


def drain_enrichment(mode=None, *, limit=DEFAULT_LIMIT,
                     max_runtime_s=DEFAULT_MAX_RUNTIME_S, source="enrich-drain",
                     log=lambda *_a: None):
    """Run one bounded enrich.run() call and persist a run record.

    Never raises - a failed run still returns/persists a record with
    error_summary set, matching enrich.run()'s own best-effort contract.
    """
    run_id = uuid.uuid4().hex[:12]
    started = time.time()
    queued_before = _queued(mode)
    error_summary = None
    res = {"targeted": 0, "enriched": 0, "filled": 0, "written": 0,
          "timed_out": 0, "stopped_early": None}
    try:
        res = enrich.run(mode=mode, limit=limit, max_runtime_s=max_runtime_s,
                         log=log)
    except Exception as exc:  # noqa: BLE001 - a run must never raise on its caller
        error_summary = f"{type(exc).__name__}: {exc}"
    finished = time.time()
    evt = {
        "run_id": run_id, "mode": mode or "all", "source": source,
        "started_at": started, "finished_at": finished,
        "duration_s": round(finished - started, 1),
        "queued_before": queued_before, "attempted": res["targeted"],
        "enriched": res["enriched"], "failed": max(
            0, res["targeted"] - res["enriched"]),
        "timed_out": res.get("timed_out", 0),
        "remaining_after": _queued(mode),
        "error_summary": error_summary or res.get("stopped_early"),
    }
    _append(evt)
    return evt


def last_run(mode=None):
    """Most recent run record (any mode, or filtered), or None."""
    if not LEDGER.is_file():
        return None
    try:
        with LEDGER.open(encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError:
        return None
    for line in reversed(lines[-_MAX_EVENTS:]):
        line = line.strip()
        if not line:
            continue
        try:
            evt = json.loads(line)
        except ValueError:
            continue
        if mode and evt.get("mode") not in (mode, "all"):
            continue
        return evt
    return None
