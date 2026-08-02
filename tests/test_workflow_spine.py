"""The 12-step workflow spine — one definition, rendered everywhere.

Pins the thing that actually broke: the dashboard grew to 104 routes with no
ordering, WORKFLOW.md described a different (9-step) flow, and staff could not
say what step they were in.
"""
import re
from pathlib import Path

from src import workflow_spine as ws


def test_twelve_steps_in_order_with_one_canonical_route_each():
    assert [s["n"] for s in ws.STEPS] == list(range(1, 13))
    for s in ws.STEPS:
        for field in ("name", "route", "owner", "need", "output", "why"):
            assert s.get(field), f"step {s['n']} is missing {field}"
        assert s["route"].startswith("/")
        assert len(s["action"]) == 2


def test_owners_are_real_roles():
    allowed = {ws.OWNER, ws.SELLER, ws.DESIGNER, ws.MANAGER, ws.RESEARCHER}
    assert {s["owner"] for s in ws.STEPS} <= allowed


def test_support_routes_are_not_workflow_steps():
    """Showing all 104 routes equally is what made the dashboard unreadable."""
    canonical = {s["route"] for s in ws.STEPS}
    support = {r for _, rs in ws.SUPPORT_ROUTES for r in rs}
    assert not (canonical & support), "a step route must not also be 'support'"


def test_status_reports_every_step_without_guessing():
    st = ws.status()
    assert set(st) >= {s["key"] for s in ws.STEPS}
    for s in ws.STEPS:
        assert st[s["key"]]["state"] in ("ready", "todo", "unknown")
        assert st[s["key"]]["detail"]


def test_you_are_here_is_the_first_unfinished_step():
    st = {s["key"]: {"state": "ready", "detail": "x"} for s in ws.STEPS}
    assert ws.current_step(st) == 12                 # all done -> last step
    st["evidence"] = {"state": "todo", "detail": "x"}
    assert ws.current_step(st) == 6


def test_workflow_md_matches_the_module_and_drops_the_old_9_step_flow():
    doc = Path("WORKFLOW.md").read_text(encoding="utf-8")
    for s in ws.STEPS:
        assert s["name"] in doc, f"WORKFLOW.md is missing step {s['n']}"
        assert f"`{s['route']}`" in doc
    # V37.10: the guide is Vietnamese (team-facing). The old 9-step flow must be
    # explicitly retired, not silently dropped — so the phrase may appear, but
    # only alongside the retirement notice.
    assert "đã BỎ" in doc                             # old flow marked, not silent
    assert "9 bước cũ" in doc and "Bảng 9 bước" not in doc
    for ph in ws.PHASES:                              # phases documented too
        assert ph["vi"] in doc and f"`{ph['route']}`" in doc
    # the closed loop is stated explicitly
    assert "Send to Re-rank" in doc and "gõ lại từ khoá bằng tay" in doc


def test_step_10_is_the_closed_loop():
    s10 = next(s for s in ws.STEPS if s["n"] == 10)
    assert "Re-rank" in s["name"] if (s := s10) else False
    assert "winner:" in s10["output"]
    assert "CONFIRM_FIRST" in s10["why"]


# --- V37.10: five phases on screen, twelve steps inside them ------------------
def test_five_phases_cover_all_twelve_steps_exactly_once():
    """The 12 steps are the right checklist but the wrong navigation. Phases must
    lose nothing and duplicate nothing."""
    assert len(ws.PHASES) == 5
    nums = [n for ph in ws.PHASES for n in ph["steps"]]
    assert sorted(nums) == list(range(1, 13))
    assert len(nums) == len(set(nums)), "a step must belong to exactly one phase"


def test_every_phase_has_vietnamese_guide_text_and_one_route():
    """Team-facing guide text is Vietnamese; listing OUTPUT stays English."""
    for ph in ws.PHASES:
        for f in ("vi", "vi_do", "vi_out", "route", "owner", "icon"):
            assert ph.get(f), f"phase {ph['p']} missing {f}"
        assert ph["route"].startswith("/")
        assert ws.steps_of(ph), "a phase must contain steps"


def test_phase_is_only_ready_when_every_step_in_it_is_ready():
    allr = {s["key"]: {"state": "ready", "detail": "x"} for s in ws.STEPS}
    ps = ws.phase_status(allr)
    assert all(v["state"] == "ready" for v in ps.values())
    # knock out one step inside phase 3 -> that phase must stop being ready
    ph3 = next(p for p in ws.PHASES if p["p"] == 3)
    victim = ws.steps_of(ph3)[-1]
    partial = dict(allr, **{victim["key"]: {"state": "todo", "detail": "x"}})
    ps2 = ws.phase_status(partial)
    assert ps2[ph3["key"]]["state"] == "todo"
    assert ps2[ph3["key"]]["next_step"]["n"] == victim["n"]
    assert ps2[ph3["key"]]["done"] == ps2[ph3["key"]]["total"] - 1


def test_current_phase_contains_the_current_step():
    st = {s["key"]: {"state": "ready", "detail": "x"} for s in ws.STEPS}
    st["evidence"] = {"state": "todo", "detail": "x"}     # step 6
    assert ws.current_step(st) == 6
    assert 6 in ws.current_phase(st)["steps"]
