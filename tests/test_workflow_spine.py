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
    assert "DEPRECATED" in doc                        # old flow marked, not silent
    assert "Bảng 9 bước" not in doc and "9 bước" not in doc
    # the closed loop is stated explicitly (step 10)
    assert "Send to Re-rank" in doc and "retyped keywords by hand" in doc


def test_step_10_is_the_closed_loop():
    s10 = next(s for s in ws.STEPS if s["n"] == 10)
    assert "Re-rank" in s["name"] if (s := s10) else False
    assert "winner:" in s10["output"]
    assert "CONFIRM_FIRST" in s10["why"]
