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


def test_the_staff_training_guide_teaches_the_same_five_phases():
    """V37.12: /training served a hand-written guide for the RETIRED 9-step flow
    (Feed/Rank/Pattern/Lab/Re-rank/Build/Photo/Ads/Learn) while home and
    WORKFLOW.md showed 5 phases — a third competing map, on the page used to
    TRAIN new staff. Pinned the same way WORKFLOW.md is."""
    import html as _html
    # unescape first: the guide writes 'Tìm &amp; lọc' (trap: _h_esc/&amp;)
    doc = _html.unescape(Path("staff_guide_vn.html").read_text(encoding="utf-8"))
    for ph in ws.PHASES:                       # every phase, by name and route
        assert ph["vi"].upper() in doc.upper(), f"guide is missing phase {ph['p']}"
        assert ph["route"] in doc
    assert "9 bước cũ" in doc and "đã BỎ" in doc          # retired, not silently dropped
    # the old rail keys must be gone: they are what made the guide teach a
    # different process from every other surface
    for dead in ("key:'FEED'", "key:'LAB'", "key:'RERANK'", "key:'BUILD'",
                 "key:'PHOTO'", "key:'ADS'", "key:'LEARN'"):
        assert dead not in doc, f"the retired 9-step card {dead} is still in the guide"
    # the two lies V37.11 found on the home page must not live on in the guide
    assert "py main.py harvest" in doc                    # /trending cannot harvest
    assert "/rerank" in doc and "Send to Re-rank" in doc  # the send lives on /imports


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


def test_advisory_steps_never_capture_you_are_here():
    """MEASURED on the real repo: steps 4-9 and 11 were ready and 9 winner-derived
    candidates sat unsent at step 10, yet home said "Open Pinterest trends" —
    because step 2 is the first not-ready step and, being optional by design,
    always will be. The pointer must name work that actually moves the shop."""
    st = {s["key"]: {"state": "ready", "detail": "x"} for s in ws.STEPS}
    st["pinterest"] = {"state": "todo", "detail": "no Pinterest capture yet"}
    st["supplier"] = {"state": "todo", "detail": "coverage PARTIAL"}
    st["rerank"] = {"state": "todo", "detail": "9 candidate(s) waiting to be sent"}
    assert ws.current_step(st) == 10                  # the real blocker, not 2
    assert 10 in ws.current_phase(st)["steps"]
    # ...but nothing is hidden: phase 1 still reports the advisory gap
    assert ws.phase_status(st)["find"]["state"] == "todo"
    assert ws.phase_status(st)["find"]["next_step"]["n"] == 2


def test_advisory_steps_are_still_asked_for_once_the_required_work_is_done():
    st = {s["key"]: {"state": "ready", "detail": "x"} for s in ws.STEPS}
    st["pinterest"] = {"state": "todo", "detail": "x"}
    assert ws.current_step(st) == 2      # nothing else open -> now it is the ask


def test_only_pinterest_and_supplier_are_advisory():
    """A step is advisory only when the code itself refuses to let it block:
    feasibility_gate calls Pinterest 'advisory, displayed only' and cannot return
    NOT_MAKEABLE until supplier coverage is complete. Anything else is required."""
    assert {s["n"] for s in ws.STEPS if s.get("advisory")} == {2, 3}
