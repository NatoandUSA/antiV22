"""Start Here (/start) -- the single front-door page: seed phrase in, a
ranked evidence-backed shortlist scoped to it out. Wraps the existing
engine (opportunity_inbox, execution_action, ytrends_mcp) rather than
adding new scoring logic, so these tests mock those boundaries and check
start_here()'s own behavior: trademark gating, niche-first sort, honest
empty-state guidance, and MCP-suggestion dedup -- never fabrication.
"""
from src import interactive


def _row(keyword, action="WATCH", priority=2, score=10, proof=None,
         proof_tier=9, verdict=None, fit_label=None):
    return {"keyword": keyword, "action": action, "priority": priority,
            "score": score, "proof": proof, "proof_tier": proof_tier,
            "verdict": verdict, "fit_label": fit_label}


def test_high_trademark_risk_blocks_before_any_data_pull(monkeypatch):
    monkeypatch.setattr(interactive, "tm_check", lambda kw: ("HIGH", "looks like a brand"))
    called = []
    monkeypatch.setattr("src.opportunity_inbox.build_inbox",
                        lambda *a, **k: called.append(1) or {"rows": []})
    out = interactive.start_here("nike bag", mode=None)
    assert "Trademark risk is HIGH" in out
    assert "looks like a brand" in out
    assert not called, "must not touch data at all once TM blocks the seed"


def test_specific_actionable_sorts_before_broad_parent(monkeypatch):
    monkeypatch.setattr(interactive, "tm_check", lambda kw: ("OK", ""))
    rows = [_row("bag"), _row("bridesmaid bag")]
    monkeypatch.setattr("src.opportunity_inbox.build_inbox",
                        lambda *a, **k: {"rows": rows})
    monkeypatch.setattr("src.opportunity_inbox.focus_rows",
                        lambda pool, q: pool)

    def _exec(row, mode):
        spec = "SPECIFIC_ACTIONABLE" if row["keyword"] == "bridesmaid bag" \
            else "BROAD_PARENT"
        return {"execution_action": row["action"], "specificity_class": spec}
    monkeypatch.setattr("src.execution_action.derive_execution_action", _exec)
    monkeypatch.setattr("src.execution_action.find_children",
                        lambda *a, **k: ([], False))
    monkeypatch.setattr("src.ytrends_mcp.research_keyword",
                        lambda kw: {})

    out = interactive.start_here("bag", mode=None)
    lines = [l for l in out.splitlines() if l.startswith("| ")]
    # lines[0] is the header row; the niche keyword must sort first among data rows
    assert "bridesmaid bag" in lines[1]
    assert "bag" in lines[2] and "bridesmaid" not in lines[2]


def test_no_local_data_and_no_children_shows_research_guidance_not_a_blank_page(monkeypatch):
    monkeypatch.setattr(interactive, "tm_check", lambda kw: ("OK", ""))
    monkeypatch.setattr("src.opportunity_inbox.build_inbox",
                        lambda *a, **k: {"rows": []})
    monkeypatch.setattr("src.opportunity_inbox.focus_rows",
                        lambda pool, q: [])
    monkeypatch.setattr("src.execution_action.find_children",
                        lambda *a, **k: ([], True))
    monkeypatch.setattr("src.ytrends_mcp.research_keyword",
                        lambda kw: {})

    out = interactive.start_here("para el amor de mi vida", mode=None)
    assert "Needs niche research first" in out
    assert "/pattern-miner?q=" in out
    assert "/keyword-lab?q=" in out
    # never invents a fake child keyword to fill the gap
    assert "para el amor de mi vida bag" not in out


def test_fresh_mcp_suggestions_dedup_against_already_scored_rows(monkeypatch):
    monkeypatch.setattr(interactive, "tm_check", lambda kw: ("OK", ""))
    rows = [_row("bridesmaid bag")]
    monkeypatch.setattr("src.opportunity_inbox.build_inbox",
                        lambda *a, **k: {"rows": rows})
    monkeypatch.setattr("src.opportunity_inbox.focus_rows",
                        lambda pool, q: pool)
    monkeypatch.setattr(
        "src.execution_action.derive_execution_action",
        lambda row, mode: {"execution_action": row["action"],
                           "specificity_class": "SPECIFIC_ACTIONABLE"})
    monkeypatch.setattr("src.execution_action.find_children",
                        lambda *a, **k: ([], False))
    monkeypatch.setattr(
        "src.ytrends_mcp.research_keyword",
        lambda kw: {"related_keywords": [
            {"tag": "bridesmaid bag"},       # already scored -> must not repeat
            {"tag": "bridesmaid tote bag"},  # new -> must appear
        ]})

    out = interactive.start_here("bridesmaid bag", mode=None)
    assert "Fresh from MCP" in out
    fresh_section = out.split("Fresh from MCP")[1]
    assert "bridesmaid tote bag" in fresh_section
    # already-scored keyword must not be repeated as an unscored "fresh" one
    assert "bridesmaid bag" not in fresh_section


def test_simple_row_never_fabricates_evidence_when_none_exists():
    row = {**_row("some keyword"), "execution": {"execution_action": "WATCH"}}
    line = interactive._simple_row(row)
    cols = [c.strip() for c in line.split("|")]
    assert cols[1] == "some keyword"
    # no proof, no verdict -> honest placeholder, not an invented claim
    assert cols[2] == "—"
    assert "None" not in line


def test_simple_row_labels_mine_niche_in_plain_language():
    row = {**_row("broad term"),
           "execution": {"execution_action": "MINE_NICHE"}}
    line = interactive._simple_row(row)
    assert "Niche down" in line
    assert "MINE_NICHE" not in line  # never leak the internal constant name


def test_simple_row_flags_group_match_proof_as_needing_verification():
    row = {**_row("bridesmaid gift bag",
                  proof={"evidence": "1124 sold/24h", "match": "fuzzy",
                         "keyword": "bridesmaid bag", "source": "capture"},
                  proof_tier=1),
           "execution": {"execution_action": "CONFIRM_FIRST"}}
    line = interactive._simple_row(row)
    assert "verify" in line.lower()


def test_simple_row_does_not_flag_loop_verified_proof_as_needing_verification():
    row = {**_row("bridesmaid bag",
                  proof={"evidence": "3 shops", "match": "fuzzy",
                         "source": "loop"},
                  proof_tier=0),
           "execution": {"execution_action": "BUILD_NOW"}}
    line = interactive._simple_row(row)
    assert "verify" not in line.lower()


def test_blocked_and_skip_rows_get_no_build_link():
    for action in ("BLOCKED", "SKIP"):
        row = {**_row("risky term"), "execution": {"execution_action": action}}
        line = interactive._simple_row(row)
        assert "/draft-listing" not in line
