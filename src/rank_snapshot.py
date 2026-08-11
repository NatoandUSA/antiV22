"""Truthful freshness: a compact snapshot of every keyword's rank state, plus
an append-only log of real action changes between snapshots.

WHY THIS EXISTS
Every score is computed fresh on every page load (freshness.py's own finding
- "ranked" is never stored). That makes the homepage's proof-first block look
identical whether nothing happened today or the whole backlog just got
re-ranked: there was no way to answer "did today's harvest/enrich run
actually change anything?" honestly. This module is the one place that DOES
persist a rank fact: what action/verdict/score a keyword held the last time a
real rank run happened.

WHAT COUNTS AS A "RANK RUN"
snapshot() is called from exactly two places: harvest.run_harvest() and
enrichment_runner.drain_enrichment() - both represent underlying data
actually changing. It is NOT called from build_inbox()/page rendering: that
runs on every home/inbox/status view, and its own mtime-keyed cache already
debounces recomputation for a different reason (skip redundant work) than
what this module needs (only record a fact when something REAL happened).
Browsing /trending, for example, touches agent.db's mtime via
discover.save_discovered() without any keyword actually being re-ranked -
hooking this into build_inbox() would misfire a "rank run" for that.

NO FALSE PROMOTIONS ON THE FIRST RUN
snapshot() diffs each keyword against the PREVIOUS rank_state.json. No prior
entry for a keyword (first time ever seen, or the file did not exist yet)
means establishing a baseline, not a promotion or demotion - zero events are
written for anything with no prior state.

STORAGE
data/rank_state.json   - latest compact state per (mode, keyword). Atomic
                          write (temp file + replace) so an interrupted write
                          can never leave a half-written state.
data/rank_events.jsonl - append-only, one line per keyword whose action
                          actually changed since the last snapshot. Same
                          best-effort/never-raises shape as import_ledger.py.
"""
import json
import time
from pathlib import Path

from src import opportunity_inbox as oi

STATE = Path("data/rank_state.json")
EVENTS = Path("data/rank_events.jsonl")
_MAX_EVENTS = 5000

MODES = ("pod", "embroidery")


def _atomic_write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False)
    tmp.replace(path)


def _load_state():
    if not STATE.is_file():
        return {"generated_at": None, "modes": {}}
    try:
        with STATE.open(encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {"generated_at": None, "modes": {}}
    if not isinstance(data, dict) or "modes" not in data:
        return {"generated_at": None, "modes": {}}
    return data


def _append_event(evt):
    try:
        EVENTS.parent.mkdir(parents=True, exist_ok=True)
        with EVENTS.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(evt, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001 - the event log must never break a rank run
        pass


def snapshot(modes=MODES, source="unspecified"):
    """Compute the current rank for each mode, diff against the stored
    previous state, append one event per keyword whose action actually
    changed (never on first sight of a keyword), then atomically overwrite
    the state file.

    Returns {mode: {"rows": n, "changed": n, "promoted": n, "demoted": n}}.
    Best-effort: never raises on the caller - a snapshot failure must not
    break the harvest/enrich run that triggered it.
    """
    from src import opportunity_inbox as oi
    now = time.time()
    prev = _load_state()
    prev_modes = prev.get("modes", {})
    new_modes = {}
    summary = {}
    for mode in modes:
        try:
            rows = oi.build_inbox(mode, limit=100000)["rows"]
        except Exception:  # noqa: BLE001
            continue
        prev_mode = prev_modes.get(mode, {})
        cur_mode = {}
        changed = promoted = demoted = 0
        for r in rows:
            kw = r["keyword"]
            entry = {"action": r["action"], "priority": r.get("priority"),
                     "verdict": r.get("verdict"), "score": r.get("score")}
            cur_mode[kw] = entry
            old = prev_mode.get(kw)
            if old is None or old.get("action") == entry["action"]:
                continue                       # baseline, or genuinely unchanged
            changed += 1
            op, npv = old.get("priority"), entry["priority"]
            if op is not None and npv is not None and npv > op:
                direction = "promoted"
                promoted += 1
            elif op is not None and npv is not None and npv < op:
                direction = "demoted"
                demoted += 1
            else:
                direction = "changed"
            _append_event({
                "event_at": now, "keyword": kw, "mode": mode,
                "direction": direction,
                "old_action": old.get("action"), "new_action": entry["action"],
                "old_verdict": old.get("verdict"), "new_verdict": entry["verdict"],
                "old_score": old.get("score"), "new_score": entry["score"],
                "source": source,
            })
        new_modes[mode] = cur_mode
        summary[mode] = {"rows": len(cur_mode), "changed": changed,
                         "promoted": promoted, "demoted": demoted}
    _atomic_write_json(STATE, {"generated_at": now, "modes": new_modes})
    return summary


def promoted_since(since, mode=None):
    """Real PROMOTED events at/after the given epoch timestamp, newest first,
    deduped to one (the latest) event per keyword - a keyword can be
    promoted more than once in the window."""
    if not EVENTS.is_file():
        return []
    try:
        with EVENTS.open(encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError:
        return []
    seen = set()
    out = []
    for line in reversed(lines[-_MAX_EVENTS:]):
        line = line.strip()
        if not line:
            continue
        try:
            evt = json.loads(line)
        except ValueError:
            continue
        if evt.get("direction") != "promoted" or evt.get("event_at", 0) < since:
            continue
        if mode and evt.get("mode") != mode:
            continue
        kw = evt.get("keyword")
        if kw in seen:
            continue
        seen.add(kw)
        out.append(evt)
    return out


def last_snapshot_at():
    """Epoch timestamp of the last snapshot, or None if none has run yet."""
    return _load_state().get("generated_at")
