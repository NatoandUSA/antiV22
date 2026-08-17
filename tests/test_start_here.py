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
    # Neither row is a literal exact match for the seed, so this isolates
    # the specificity-based sort from the exact-match-first rule.
    monkeypatch.setattr(interactive, "tm_check", lambda kw: ("OK", ""))
    rows = [_row("big tote"), _row("bridesmaid tote")]
    monkeypatch.setattr("src.opportunity_inbox.build_inbox",
                        lambda *a, **k: {"rows": rows})
    monkeypatch.setattr("src.opportunity_inbox.focus_rows",
                        lambda pool, q: pool)

    def _exec(row, mode):
        spec = "SPECIFIC_ACTIONABLE" if row["keyword"] == "bridesmaid tote" \
            else "BROAD_PARENT"
        return {"execution_action": row["action"], "specificity_class": spec}
    monkeypatch.setattr("src.execution_action.derive_execution_action", _exec)
    monkeypatch.setattr("src.execution_action.find_children",
                        lambda *a, **k: ([], False))
    monkeypatch.setattr("src.ytrends_mcp.research_keyword",
                        lambda kw: {})

    out = interactive.start_here("tote", mode=None)
    lines = [l for l in out.splitlines() if l.startswith("| ")]
    # lines[0] is the header row; the niche keyword must sort first among data rows
    assert "bridesmaid tote" in lines[1]
    assert "big tote" in lines[2] and "bridesmaid" not in lines[2]


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


def _setup(monkeypatch, rows, exec_map, needs_research=False, related=None):
    """Shared wiring for the tests below: real tm_check pass-through, a
    controlled pool, and execution results keyed by keyword."""
    monkeypatch.setattr(interactive, "tm_check", lambda kw: ("OK", ""))
    monkeypatch.setattr("src.opportunity_inbox.build_inbox",
                        lambda *a, **k: {"rows": rows})
    monkeypatch.setattr("src.opportunity_inbox.focus_rows",
                        lambda pool, q: pool)
    monkeypatch.setattr(
        "src.execution_action.derive_execution_action",
        lambda row, mode: exec_map[row["keyword"]])
    monkeypatch.setattr("src.execution_action.find_children",
                        lambda *a, **k: ([], needs_research))
    monkeypatch.setattr("src.ytrends_mcp.research_keyword",
                        lambda kw: {"related_keywords": related or []})


def test_exact_seed_match_sorts_first_even_over_a_more_specific_relative(monkeypatch):
    rows = [_row("teacher shirt"), _row("funny teacher shirt")]
    _setup(monkeypatch, rows, {
        "teacher shirt": {"execution_action": "WATCH",
                          "specificity_class": "BROAD_PARENT"},
        "funny teacher shirt": {"execution_action": "CONFIRM_FIRST",
                                "specificity_class": "SPECIFIC_ACTIONABLE"},
    })
    out = interactive.start_here("teacher shirt", mode=None)
    lines = [l for l in out.splitlines() if l.startswith("| ")]
    assert "teacher shirt" in lines[1] and "funny" not in lines[1]
    # exact match present -> no "no data on that exact phrase" disclaimer
    assert "No data yet on that exact phrase" not in out


def test_no_exact_match_gets_an_explicit_disclaimer_not_silence(monkeypatch):
    rows = [_row("funny teacher shirt")]
    _setup(monkeypatch, rows, {
        "funny teacher shirt": {"execution_action": "CONFIRM_FIRST",
                                "specificity_class": "SPECIFIC_ACTIONABLE"},
    })
    out = interactive.start_here("teacher appreciation shirt", mode=None)
    assert "No data yet on that exact phrase" in out


def test_empty_pool_does_not_show_the_no_exact_match_disclaimer(monkeypatch):
    # Nothing to compare against -> the "closest related keywords" framing
    # would be actively misleading (there's no list below it).
    _setup(monkeypatch, [], {}, needs_research=True)
    out = interactive.start_here("brand new phrase", mode=None)
    assert "No data yet on that exact phrase" not in out
    assert "Nothing worth building yet" in out


def test_skip_and_blocked_rows_are_pulled_out_of_the_main_table(monkeypatch):
    rows = [_row("good keyword"), _row("dead keyword"), _row("risky keyword")]
    _setup(monkeypatch, rows, {
        "good keyword": {"execution_action": "BUILD_NOW",
                         "specificity_class": "SPECIFIC_ACTIONABLE"},
        "dead keyword": {"execution_action": "SKIP",
                         "specificity_class": "SPECIFIC_ACTIONABLE"},
        "risky keyword": {"execution_action": "BLOCKED",
                          "specificity_class": "SPECIFIC_ACTIONABLE"},
    })
    out = interactive.start_here("keyword", mode=None)
    table_lines = [l for l in out.splitlines() if l.startswith("| ")]
    # only the one real opportunity gets a full row
    assert len(table_lines) == 2  # header + 1 data row
    assert "good keyword" in table_lines[1]
    # the other two are still disclosed, just not given a full table row
    assert "dead keyword" in out and "risky keyword" in out
    assert "2 more checked and not worth building" in out


def test_mcp_failure_is_distinguished_from_genuinely_nothing_new(monkeypatch):
    _setup(monkeypatch, [], {}, needs_research=True)
    monkeypatch.setattr(
        "src.ytrends_mcp.research_keyword",
        lambda kw: (_ for _ in ()).throw(RuntimeError("MCP down")))
    out = interactive.start_here("some seed", mode=None)
    assert "Fresh from MCP — unavailable" in out
    assert "Fresh from MCP — nothing new" not in out


def test_mcp_success_with_no_related_keywords_says_nothing_new_not_unavailable(monkeypatch):
    _setup(monkeypatch, [], {}, needs_research=True, related=[])
    out = interactive.start_here("some seed", mode=None)
    assert "Fresh from MCP — nothing new" in out
    assert "unavailable" not in out


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


# ---- reconciliation: YTrends model vs staff's real captured proof --------

def test_reconcile_model_and_real_evidence_agree():
    row = _row("x", verdict="GO", proof_tier=1)
    assert interactive._reconcile(row) == "confirmed by real evidence"


def test_reconcile_model_hot_but_unverified_by_staff():
    row = _row("x", verdict="GO", proof_tier=9)
    assert interactive._reconcile(row) == "model says hot, not staff-verified yet"


def test_reconcile_real_evidence_contradicts_the_model():
    # the valuable case: YTrends says watch/skip but staff have real proof
    row = _row("x", verdict="WATCH", proof_tier=0)
    out = interactive._reconcile(row)
    assert out is not None and "contradicts the model" in out


def test_reconcile_returns_none_when_both_sources_agree_on_low_priority():
    row = _row("x", verdict="WATCH", proof_tier=9)
    assert interactive._reconcile(row) is None


def test_simple_row_surfaces_the_reconciliation_verdict():
    row = {**_row("nurse tote", verdict="WATCH", proof_tier=0,
                  proof={"evidence": "2 shops selling"}),
           "execution": {"execution_action": "CONFIRM_FIRST"}}
    line = interactive._simple_row(row)
    assert "contradicts the model" in line


def test_simple_row_stays_clean_when_nothing_to_reconcile():
    row = {**_row("dull term", verdict="WATCH", proof_tier=9),
           "execution": {"execution_action": "WATCH"}}
    line = interactive._simple_row(row)
    assert "·" not in line  # no reconciliation marker appended


# ---- data-freshness caveat -----------------------------------------------

def test_stale_underlying_data_gets_an_explicit_caveat(monkeypatch):
    from datetime import date, timedelta
    stale = (date.today() - timedelta(days=30)).isoformat()
    rows = [_row("teacher shirt")]
    rows[0]["collected_at"] = stale
    _setup(monkeypatch, rows, {
        "teacher shirt": {"execution_action": "CONFIRM_FIRST",
                          "specificity_class": "SPECIFIC_ACTIONABLE"},
    })
    out = interactive.start_here("teacher shirt", mode=None)
    assert "more than" in out and "YTRENDS_FRESH_DAYS old" in out


def test_fresh_underlying_data_gets_no_caveat(monkeypatch):
    from datetime import date
    rows = [_row("teacher shirt")]
    rows[0]["collected_at"] = date.today().isoformat()
    _setup(monkeypatch, rows, {
        "teacher shirt": {"execution_action": "CONFIRM_FIRST",
                          "specificity_class": "SPECIFIC_ACTIONABLE"},
    })
    out = interactive.start_here("teacher shirt", mode=None)
    assert "YTRENDS_FRESH_DAYS old" not in out
