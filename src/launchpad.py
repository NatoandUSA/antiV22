"""Launchpad — the launch status board (idea → … → Day-7 → scale/kill).

Self-populating: each saved workspace run becomes a card, and its column is
derived from the run's publish gate + verdict + any logged feedback. A manual
override (data/tracking/launchpad.json) always wins, so the team can drag a card
by setting its stage. No auto-publishing — "Published manually" only ever reflects
a human action the team logged.
"""
import json
from pathlib import Path

RUNS = Path("reports/latest/runs")
OVERRIDE = Path("data/tracking/launchpad.json")

# Kanban columns, in board order.
COLUMNS = ["Not started", "In progress", "Blocked", "Ready for manager",
           "Published manually", "Day 3 check", "Day 7 decision",
           "Scaled", "Killed"]

# The launch stages (idea → scale/kill) shown per card.
STAGES = ["Idea", "Supplier check", "Competitor audit", "Design brief",
          "First image ready", "Listing draft", "Manager approval",
          "Manual publish", "Day 3 review", "Day 7 review", "Scale / fix / kill"]


def _load_override():
    if OVERRIDE.exists():
        try:
            return json.loads(OVERRIDE.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}
    return {}


def set_status(run_id, column):
    if column not in COLUMNS:
        return False
    ov = _load_override()
    ov[run_id] = column
    OVERRIDE.parent.mkdir(parents=True, exist_ok=True)
    OVERRIDE.write_text(json.dumps(ov, indent=2), encoding="utf-8")
    return True


def _feedback_index():
    """keyword-slug -> feedback row (latest), for matching runs to results."""
    idx = {}
    try:
        from src import feedback as fb
        for r in fb.load():
            key = (r.get("run_id") or r.get("keyword") or "").lower()
            if key:
                idx[key] = r
    except Exception:  # noqa: BLE001
        pass
    return idx


def _derive(run_id, wj, fb_row):
    """Derive a column + next action from a run's data + any feedback."""
    verdict = ((wj.get("verdict") or {}).get("cls") if isinstance(wj.get("verdict"), dict)
               else wj.get("verdict"))
    ready = bool(wj.get("publish_ready"))
    if fb_row:
        dec = fb_row.get("decision") or fb_row.get("day7_action")
        if dec == "KILL_LISTING":
            return "Killed", "Retire or fully rewrite."
        if dec == "SCALE_PRODUCT_LINE":
            return "Scaled", "Make variants + expand the line."
        if str(fb_row.get("day_7_views") or "").strip() not in ("", "None"):
            return "Day 7 decision", f"Day-7 says: {dec}."
        if str(fb_row.get("day_3_views") or "").strip() not in ("", "None"):
            return "Day 3 check", "Log Day-7 next."
        return "Published manually", "Log Day-3 numbers at day 3."
    if verdict == "avoid":
        return "Blocked", "Trademark/policy — change the wording."
    if ready:
        return "Ready for manager", "Manager approves, then publish manually."
    return "In progress", "Complete supplier + first image + 13 tags."


def board():
    """Return {column: [cards]} across every saved run."""
    fb_idx = _feedback_index()
    ov = _load_override()
    cols = {c: [] for c in COLUMNS}
    if RUNS.exists():
        for d in sorted(RUNS.iterdir(), reverse=True):
            wjp = d / "workspace.json"
            if not wjp.is_file():
                continue
            try:
                wj = json.loads(wjp.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
            run_id = d.name
            kw = wj.get("keyword", run_id)
            fb_row = fb_idx.get(run_id.lower()) or fb_idx.get(str(kw).lower())
            col, nxt = _derive(run_id, wj, fb_row)
            col = ov.get(run_id, col)   # manual override wins
            cols.setdefault(col, []).append({
                "run_id": run_id, "keyword": kw,
                "mode": wj.get("product_mode", ""),
                "verdict": (wj.get("verdict") or {}).get("verdict")
                if isinstance(wj.get("verdict"), dict) else "",
                "publish_ready": bool(wj.get("publish_ready")),
                "next_action": nxt})
    return cols


def summary():
    b = board()
    return {c: len(b.get(c, [])) for c in COLUMNS}
