"""The niche matcher — the root cause of Pattern Miner's mixed clusters.

Reproduces the owner's real run: query "personalized embroidery halloween shirt"
returned 385 listings whose winning words came back teacher 52%, school 38%,
back 33%, appreciation 24% — because {personalized, shirt} alone satisfied
`hits >= min(2, len(qtoks))` and the token carrying the niche (halloween) was
never required.
"""
import json

import pytest

from src import niche_match as nm

QUERY = "personalized embroidery halloween shirt"

# Straight from the owner's Pattern Miner HTML: the pattern it actually mined.
CONTAMINANTS = [
    "Personalized Teacher Shirt, Comfort Colors Back to School Tee",
    "Teacher Appreciation Shirt Personalized Name Gift",
    "Custom Teacher Name Sweatshirt, Elementary Teacher Gift",
    "Personalized Dog Mom Shirt Custom Name",
    "Custom Future Mrs Shirt, Engaged Gift, Bride Shirt, Honeymoon Outfit",
    "Personalized Bride Shirt, Fiancee Gift, Engagement Tee",
]
REAL = [
    "Personalized Halloween Embroidered Sweatshirt, Ghost Dog Crewneck",
    "Embroidered Ghost Dog Sweatshirt Halloween",
    "Custom Embroidered Halloween Shirt",
    "Personalized Boo Embroidered Shirt Halloween",
]


def test_the_query_splits_into_modifier_product_and_theme():
    toks, products, themes = nm.split_query(QUERY)
    assert toks == ["personalized", "embroidery", "halloween", "shirt"]
    assert set(products) == {"embroidery", "shirt"}
    # halloween is the ONLY token that says which niche this is
    assert themes == ["halloween"]


@pytest.mark.parametrize("title", CONTAMINANTS)
def test_generic_tokens_can_no_longer_carry_a_match(title):
    """'personalized' + 'shirt' is not a Halloween listing."""
    assert nm.match(title, QUERY) is False, title


@pytest.mark.parametrize("title", REAL)
def test_real_niche_listings_still_match(title):
    assert nm.match(title, QUERY) is True, title


def _old_rule(title, query):
    """The threshold as it shipped: hits >= min(2, len(qtoks)) — a fixed floor
    of 2 whatever the query length."""
    qtoks = nm.split_query(query)[0]
    tt = set(nm.tokens(title))
    return sum(1 for t in qtoks if t in tt) >= min(2, len(qtoks))


def test_the_old_rule_would_have_let_the_contaminants_through():
    """Pins the REGRESSION, not just the fix. Computed, not hardcoded: if the
    old threshold is ever restored, the second assertion goes red."""
    leaked = [t for t in CONTAMINANTS if _old_rule(t, QUERY)]
    # these are the titles that produced teacher 52% / bride tags in the real run
    assert "Personalized Teacher Shirt, Comfort Colors Back to School Tee" in leaked
    assert "Personalized Bride Shirt, Fiancee Gift, Engagement Tee" in leaked
    assert len(leaked) >= 4, f"fixtures stopped reproducing the bug: {leaked}"
    # and not one of them survives the new rule
    assert [t for t in CONTAMINANTS if nm.match(t, QUERY)] == []


def test_the_new_rule_is_strictly_narrower_never_wider():
    """The fix may only REMOVE matches. Anything the old rule rejected must stay
    rejected, or this 'fix' is quietly pulling in new noise."""
    for title in CONTAMINANTS + REAL:
        if not _old_rule(title, QUERY):
            assert not nm.match(title, QUERY), title


def test_why_labels_the_reason_a_listing_was_rejected():
    """Feeds the evidence table's match-type column: staff must see WHY."""
    ok, kind, shared = nm.why(CONTAMINANTS[0], QUERY)
    assert (ok, kind) == (False, "product")
    assert set(shared) == {"personalized", "shirt"}
    ok, kind, _ = nm.why(REAL[0], QUERY)
    assert (ok, kind) == (True, "theme")
    ok, kind, _ = nm.why("Custom Embroidered Halloween Shirt", QUERY)
    assert (ok, kind) == (True, "theme")
    assert nm.why("Ceramic Mug", QUERY)[1] == "none"


def test_a_query_with_no_theme_is_unchanged():
    """'tote bag' is all product nouns — there is no theme to require, so the
    old overlap rule stands alone and nothing regresses."""
    assert nm.split_query("tote bag")[2] == []
    assert nm.match("Canvas Tote Bag Personalized", "tote bag") is True
    assert nm.match("Ceramic Mug Custom", "tote bag") is False


def test_a_single_theme_query_requires_that_theme():
    assert nm.match("Nurse Appreciation Sweatshirt", "nurse sweatshirt") is True
    assert nm.match("Teacher Appreciation Sweatshirt", "nurse sweatshirt") is False


def test_an_empty_query_matches_everything_not_nothing():
    """Overview mode. Matching nothing would read as 'no captures'."""
    assert nm.match("anything at all", "") is True
    assert nm.match("anything at all", None) is True


# --- wired into both subsystems ----------------------------------------------
def test_pattern_miner_title_path_uses_the_shared_rule():
    from src import pattern_miner as pm
    qtoks = pm._query_tokens(QUERY)
    assert pm._title_matches(CONTAMINANTS[0], qtoks, QUERY) is False
    assert pm._title_matches(REAL[0], qtoks, QUERY) is True


def test_pattern_miner_serp_view_path_uses_the_shared_rule():
    """A SERP captured from 'teacher shirt' must not be swept into a Halloween
    query just because both say shirt."""
    from src import pattern_miner as pm
    qtoks = pm._query_tokens(QUERY)
    assert pm._view_matches("etsy personalized teacher shirt", qtoks) is False
    assert pm._view_matches("etsy personalized halloween shirt", qtoks) is True


def test_the_evidence_router_honours_the_same_rule():
    from src import feed_evidence_router as fer
    assert fer._niche_ok(CONTAMINANTS[4], QUERY) is False   # bride/engagement
    assert fer._niche_ok(REAL[0], QUERY) is True


# --- end to end on a synthetic capture ---------------------------------------
@pytest.fixture
def captures(tmp_path, monkeypatch):
    """A SERP capture holding BOTH niches, the way the real pool does."""
    from src import pattern_miner as pm
    d = tmp_path / "etsy_search"
    d.mkdir()
    rows = [[t, "19.99", "ShopA" if i % 2 else "ShopB", "", "", ""]
            for i, t in enumerate(REAL + CONTAMINANTS)]
    (d / "capture.json").write_text(json.dumps({
        "view": "etsy mixed capture",
        "headers": ["title", "price", "shop", "star", "ad", "free shipping"],
        "rows": rows}), encoding="utf-8")
    monkeypatch.setattr(pm, "_SEARCH_DIR", d)
    monkeypatch.setattr(pm, "_IMPORT_DIR", tmp_path / "nope")
    monkeypatch.setattr(pm, "_from_db", lambda kw: [])
    monkeypatch.setattr(pm, "MASTER", tmp_path / "nomaster.csv")
    return pm


def test_mining_the_halloween_query_excludes_teacher_and_bride(captures):
    pm = captures
    kw, batch, matched, scanned = pm.load_batch(QUERY)
    titles = [b["title"] for b in batch]
    assert scanned == len(REAL) + len(CONTAMINANTS)
    assert matched == len(REAL), titles
    for bad in CONTAMINANTS:
        assert bad not in titles
    for good in REAL:
        assert good in titles


def test_the_mined_pattern_no_longer_says_teacher(captures):
    """The end the owner cares about: winning words must describe the niche."""
    pm = captures
    res = pm.mine(QUERY)
    words = {w for w, _pct in res["top_words"]}
    assert "teacher" not in words and "school" not in words
    assert res["n"] == len(REAL)
    assert res["matched"] == len(REAL)
