"""Patch 4 Stage 2 -- execution_action overlay tests (offline, no API/DB)."""
from src import execution_action as ea
from src.execution_action import derive_execution_action, _phrase_present, _tokens


def _run(keyword, action, proof=None, mode="pod"):
    return derive_execution_action({"keyword": keyword, "action": action,
                                     "proof": proof}, mode)


def _row(kw, action, proof=None):
    return {"keyword": kw, "action": action, "proof": proof}


def _fake_build_inbox(rows):
    def _build_inbox(mode=None, limit=100000, show_archived=False):
        return {"rows": rows}
    return _build_inbox


# --- tokenization regressions (the substring bug caught in the Phase B audit) ---

def test_short_vocab_words_do_not_substring_match():
    toks = _tokens("newborn dedication")
    assert "rn" not in toks
    assert "cat" not in toks


def test_weak_modifier_does_not_substring_match_inside_longer_word():
    assert "cool" not in _tokens("beach bach cooler")


def test_phrase_matches_only_as_contiguous_token_sequence():
    assert _phrase_present(_tokens("please carry onward now"), "carry on") is False
    assert _phrase_present(_tokens("mens carry on bag"), "carry on") is True


# --- broad parent -> MINE_NICHE -------------------------------------------

def test_weak_modifier_only_is_broad_parent():
    for kw in ("funny shirts", "funny vintage shirt", "embroidered sweatshirt"):
        out = _run(kw, "CONFIRM_FIRST")
        assert out["execution_action"] == "MINE_NICHE", kw
        assert out["specificity_class"] == "BROAD_PARENT", kw


def test_personalization_alone_is_insufficient():
    out = _run("personalized sweatshirt", "CONFIRM_FIRST")
    assert out["execution_action"] == "MINE_NICHE"
    assert "PERSONALIZATION_ONLY" in out["reason_codes"]


def test_product_subtype_alone_is_insufficient():
    out = _run("company tote", "CONFIRM_FIRST")
    assert out["execution_action"] == "MINE_NICHE"


def test_unclassified_theme_with_no_signal_is_broad_parent_not_ambiguous():
    # product_fit calls this THEME_FIT_NEEDS_PRODUCT (not AMBIGUOUS_PHRASE) --
    # a confidently-classified-but-generic theme must still route to
    # MINE_NICHE, not get stuck in REVIEW_ACTIONABILITY forever.
    out = _run("quarter zip", "CONFIRM_FIRST")
    assert out["execution_action"] == "MINE_NICHE"
    assert out["specificity_class"] == "BROAD_PARENT"


# --- specific actionable ----------------------------------------------------

def test_specific_occasion_alone_is_sufficient():
    out = _run("25th birthday shirt", "CONFIRM_FIRST")
    assert out["specificity_class"] == "SPECIFIC_ACTIONABLE"
    assert out["execution_action"] == "CONFIRM_FIRST"


def test_specific_profession_role_alone_is_sufficient():
    out = _run("nicu nurse sweatshirt", "CONFIRM_FIRST", mode="embroidery")
    assert out["specificity_class"] == "SPECIFIC_ACTIONABLE"


def test_bridesmaid_role_plus_personalization():
    out = _run("bridesmaid sweatshirt name role", "CONFIRM_FIRST", mode="embroidery")
    assert out["specificity_class"] == "SPECIFIC_ACTIONABLE"


def test_specific_use_case_alone_is_sufficient():
    out = _run("mens carry on bag", "CONFIRM_FIRST")
    assert out["specificity_class"] == "SPECIFIC_ACTIONABLE"


def test_two_medium_signals_combine_to_strong():
    # "fishing" (motif, medium) + "dad" (generic audience, medium) -> combo
    out = _run("fishing dad hat", "CONFIRM_FIRST")
    assert out["specificity_class"] == "SPECIFIC_ACTIONABLE"
    assert "MEDIUM_SIGNAL_COMBO" in out["reason_codes"]


def test_single_medium_signal_alone_is_not_enough():
    # "dad" alone (generic audience, one medium category) -> insufficient
    out = _run("dad shirt", "CONFIRM_FIRST")
    assert out["specificity_class"] == "BROAD_PARENT"
    assert out["execution_action"] == "MINE_NICHE"


# --- proof capping on BUILD_NOW ---------------------------------------------

def test_specific_build_now_with_no_proof_caps_to_confirm():
    out = _run("mens carry on bag", "BUILD_NOW", proof=None)
    assert out["execution_action"] == "CONFIRM_FIRST"
    assert "NO_EXACT_OR_GROUP_PROOF" in out["reason_codes"]


def test_specific_build_now_with_exact_proof_stays_build_now():
    out = _run("mens carry on bag", "BUILD_NOW", proof={"match": "exact"})
    assert out["execution_action"] == "BUILD_NOW"


def test_specific_build_now_with_group_proof_caps_to_confirm():
    out = _run("mens carry on bag", "BUILD_NOW",
               proof={"match": "fuzzy", "match_confidence": 0.7})
    assert out["execution_action"] == "CONFIRM_FIRST"
    assert "GROUP_PROOF_CAP" in out["reason_codes"]


def test_broad_parent_with_proof_still_mines_niche():
    out = _run("funny mug", "BUILD_NOW", proof={"match": "exact"})
    assert out["execution_action"] == "MINE_NICHE"


# --- hard gates never move ---------------------------------------------------

def test_blocked_never_upgraded():
    out = _run("some trademark term", "BLOCKED", proof={"match": "exact"})
    assert out["execution_action"] == "BLOCKED"
    assert out["reason_codes"] == ["ENGINE_ACTION_PRESERVED"]


def test_skip_never_upgraded():
    out = _run("shop handle studio", "SKIP")
    assert out["execution_action"] == "SKIP"


# --- purity: no engine field is mutated -------------------------------------

def test_row_is_not_mutated():
    row = {"keyword": "funny mug", "action": "CONFIRM_FIRST", "proof": None}
    before = dict(row)
    derive_execution_action(row, "pod")
    assert row == before


# --- find_children: real children only, never fabricated -------------------

def test_finds_a_real_specific_child_sharing_both_parent_tokens(monkeypatch):
    pool = [
        _row("corporate gift bag", "CONFIRM_FIRST"),
        _row("bridal gift bags", "CONFIRM_FIRST"),      # real child: occasion signal
        _row("birthday gift bag", "WATCH"),              # real child even if only WATCH
        _row("random other keyword", "CONFIRM_FIRST"),   # unrelated -- must not appear
    ]
    monkeypatch.setattr(ea.oi, "build_inbox", _fake_build_inbox(pool))
    children, needs_research = ea.find_children("corporate gift bag", "pod")
    assert needs_research is False
    kws = {c["keyword"] for c in children}
    assert kws == {"bridal gift bags", "birthday gift bag"}
    assert all(c["execution"]["specificity_class"] == "SPECIFIC_ACTIONABLE"
               for c in children)


def test_no_real_child_reports_needs_research_not_a_fabricated_one(monkeypatch):
    pool = [_row("preppy pouch", "CONFIRM_FIRST"),
            _row("unrelated keyword entirely", "CONFIRM_FIRST")]
    monkeypatch.setattr(ea.oi, "build_inbox", _fake_build_inbox(pool))
    children, needs_research = ea.find_children("preppy pouch", "pod")
    assert children == []
    assert needs_research is True


def test_parent_keyword_itself_is_excluded_from_its_own_children(monkeypatch):
    pool = [_row("bridal gift bags", "CONFIRM_FIRST")]
    monkeypatch.setattr(ea.oi, "build_inbox", _fake_build_inbox(pool))
    children, _ = ea.find_children("bridal gift bags", "pod")
    assert children == []


def test_blocked_and_skipped_candidates_are_never_suggested_as_children(monkeypatch):
    pool = [
        _row("corporate gift bag", "CONFIRM_FIRST"),
        _row("bridal gift bag trademark", "BLOCKED"),
        _row("bridal gift bag shop handle", "SKIP"),
    ]
    monkeypatch.setattr(ea.oi, "build_inbox", _fake_build_inbox(pool))
    children, _ = ea.find_children("corporate gift bag", "pod")
    assert children == []
