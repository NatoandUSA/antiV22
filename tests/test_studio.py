"""Studio (/studio) -- the first real caller of src/contracts.py's compile
pipeline. Tests mock opportunity_inbox/execution_action (same boundary as
Start Here) and check studio()'s own wiring: real field mapping into
create_master_keyword, honest empty/error states, and that real captured
proof becomes a real evidence-backed tag instead of leaving every slot a
TAG_GAP.
"""
from src import interactive


def _row(keyword, action="CONFIRM_FIRST", score=42, verdict="GO",
         fit_status="POD_FIT", proof=None, proof_tier=9):
    return {"keyword": keyword, "action": action, "score": score,
            "verdict": verdict, "fit_status": fit_status,
            "proof": proof, "proof_tier": proof_tier}


def _setup(monkeypatch, rows, exec_result=None, tm=("OK", "")):
    monkeypatch.setattr(interactive, "tm_check", lambda kw: tm)
    monkeypatch.setattr("src.opportunity_inbox.build_inbox",
                        lambda *a, **k: {"rows": rows})
    monkeypatch.setattr(
        "src.execution_action.derive_execution_action",
        lambda row, mode: exec_result or {"execution_action": row["action"],
                                          "specificity_class": "SPECIFIC_ACTIONABLE"})


def test_high_trademark_risk_blocks_before_any_compile(monkeypatch):
    called = []
    monkeypatch.setattr(interactive, "tm_check", lambda kw: ("HIGH", "brand term"))
    monkeypatch.setattr("src.opportunity_inbox.build_inbox",
                        lambda *a, **k: called.append(1) or {"rows": []})
    out = interactive.studio("nike bag", mode=None)
    assert "Trademark risk is HIGH" in out
    assert not called


def test_keyword_not_in_ranked_pool_gets_an_honest_message_not_a_crash(monkeypatch):
    _setup(monkeypatch, [])
    out = interactive.studio("never seen this", mode=None)
    assert "hasn't been through the ranking engine" in out
    assert "/should-sell?q=" in out


def test_compiles_a_real_package_with_no_fabricated_tags(monkeypatch):
    rows = [_row("bridesmaid bag")]
    _setup(monkeypatch, rows)
    out = interactive.studio("bridesmaid bag", mode=None)
    assert "Bridesmaid Bag" in out  # title, bare capitalized (no enrichment yet)
    assert "0 evidence-backed, 13 gap" in out
    assert "no evidence yet, never invented" in out
    assert "DATA UNAVAILABLE" in out
    assert "Publish ready: ❌ NO" in out


def test_real_captured_proof_becomes_one_evidence_backed_tag(monkeypatch):
    proof = {"sold": 1124, "revenue": 794200, "shops": 1, "listings": 3,
             "young": 4, "verdict": "SELLING", "match": "exact",
             "evidence": "1124 sold/24h"}
    rows = [_row("bridesmaid bag", proof=proof, proof_tier=1)]
    _setup(monkeypatch, rows)
    out = interactive.studio("bridesmaid bag", mode=None)
    assert "1 evidence-backed, 12 gap" in out
    tags_section = out.split("## Tags")[1].split("##")[0]
    assert "bridesmaid bag" in tags_section


def test_real_neighbor_proof_becomes_additional_evidence_backed_tags(monkeypatch):
    # The typed keyword itself has no proof, but a real close neighbor does
    # -- that neighbor's real evidence must still surface as a tag, since a
    # real Etsy listing tags on related terms too, not just the literal seed.
    proof = {"sold": 40, "verdict": "SELLING", "match": "fuzzy",
             "evidence": "40 sold/24h"}
    rows = [_row("bridesmaid bag"),
            _row("bridesmaid gift bag", proof=proof, proof_tier=2)]
    _setup(monkeypatch, rows)
    out = interactive.studio("bridesmaid bag", mode=None)
    assert "1 evidence-backed, 12 gap" in out
    tags_section = out.split("## Tags")[1].split("##")[0]
    assert "bridesmaid gift bag" in tags_section


def test_suggested_title_uses_real_evidence_tags_without_overriding_the_compiled_title(monkeypatch):
    proof = {"sold": 40, "verdict": "SELLING", "match": "fuzzy"}
    rows = [_row("bridesmaid bag"),
            _row("bridesmaid gift bag", proof=proof, proof_tier=2)]
    _setup(monkeypatch, rows)
    out = interactive.studio("bridesmaid bag", mode=None)
    assert "## Title\n`Bridesmaid Bag`" in out  # compiled title untouched
    assert "Suggested longer title" in out
    assert "Bridesmaid Gift Bag" in out.split("Suggested longer title")[1]


def test_no_suggested_title_line_when_evidence_adds_nothing_new(monkeypatch):
    # only the exact keyword itself has proof -- no new words to add
    proof = {"sold": 40, "verdict": "SELLING", "match": "exact"}
    rows = [_row("bridesmaid bag", proof=proof, proof_tier=1)]
    _setup(monkeypatch, rows)
    out = interactive.studio("bridesmaid bag", mode=None)
    assert "Suggested longer title" not in out


def test_proof_with_a_verdict_outside_the_contract_vocabulary_is_skipped_not_forced(monkeypatch):
    # etsy_proof.py's verdict vocabulary is expected to already match
    # contracts.VALID_VERDICTS, but this must degrade honestly (skip the
    # evidence ref) rather than crash or silently coerce an unknown value.
    proof = {"sold": 5, "verdict": "SOMETHING_UNEXPECTED", "match": "exact"}
    rows = [_row("edge case kw", proof=proof, proof_tier=1)]
    _setup(monkeypatch, rows)
    out = interactive.studio("edge case kw", mode=None)
    assert "0 evidence-backed, 13 gap" in out


def test_invalid_row_data_fails_honestly_not_with_a_crash(monkeypatch):
    # fit_status not in VALID_FIT_STATUSES -> create_master_keyword raises
    rows = [_row("weird row", fit_status="NOT_A_REAL_STATUS")]
    _setup(monkeypatch, rows)
    out = interactive.studio("weird row", mode=None)
    assert "Couldn't compile" in out


def test_embroidery_keyword_resolves_to_embroidery_mode_even_under_pod_toggle(monkeypatch):
    rows = [_row("custom embroidery patch")]
    _setup(monkeypatch, rows)
    # must not raise even though the UI toggle says pod -- the keyword's own
    # craft word is authoritative (same rule draft_listing already follows)
    out = interactive.studio("custom embroidery patch", mode="pod")
    assert "Couldn't compile" not in out
    assert "Custom Embroidery Patch" in out


def test_publish_ready_is_never_true_with_zero_owner_verification(monkeypatch):
    proof = {"sold": 1124, "verdict": "PROVEN_WINNER", "match": "exact"}
    rows = [_row("hot keyword", proof=proof, proof_tier=0)]
    _setup(monkeypatch, rows)
    out = interactive.studio("hot keyword", mode=None)
    # even strong real evidence never auto-satisfies Owner Checks or price
    assert "Publish ready: ❌ NO" in out


def test_real_sold_and_revenue_derive_a_reference_price(monkeypatch):
    proof = {"sold": 100, "revenue": 5000, "verdict": "SELLING", "match": "exact"}
    rows = [_row("priced keyword", proof=proof, proof_tier=1)]
    _setup(monkeypatch, rows)
    out = interactive.studio("priced keyword", mode=None)
    assert "$50.00" in out
    assert "reference only, not owner-set" in out
    assert "DATA UNAVAILABLE" not in out


def test_no_price_derived_when_proof_lacks_sold_or_revenue(monkeypatch):
    proof = {"verdict": "SELLING", "match": "exact"}  # no sold/revenue
    rows = [_row("unpriced keyword", proof=proof, proof_tier=1)]
    _setup(monkeypatch, rows)
    out = interactive.studio("unpriced keyword", mode=None)
    assert "DATA UNAVAILABLE" in out


def test_derived_reference_price_never_makes_publish_ready_true(monkeypatch):
    proof = {"sold": 100, "revenue": 5000, "verdict": "PROVEN_WINNER", "match": "exact"}
    rows = [_row("priced keyword", proof=proof, proof_tier=0)]
    _setup(monkeypatch, rows)
    out = interactive.studio("priced keyword", mode=None)
    assert "$50.00" in out
    # MODELED, not OWNER_SET -- a real derived price still can't satisfy
    # publish readiness on its own
    assert "Publish ready: ❌ NO" in out
