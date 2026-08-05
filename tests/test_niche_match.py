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


def test_the_query_splits_into_four_buckets():
    c = nm.classify(QUERY)
    assert c["modifier"] == ["personalized"]
    # embroidery is HOW it is made, not WHAT is sold. product_fit lumps it into
    # its noun set, which made "embroidered" look like the product.
    assert c["technique"] == ["embroidery"]
    assert c["product"] == ["shirt"]
    # halloween is the ONLY token that says which niche this is
    assert c["theme"] == ["halloween"]


@pytest.mark.parametrize("token,want", [
    ("personalized", "modifier"), ("custom", "modifier"), ("name", "modifier"),
    ("monogram", "modifier"),
    ("crew", "style"), ("oversized", "style"), ("comfort", "style"),
    ("embroidery", "technique"), ("embroidered", "technique"),
    ("printed", "technique"), ("engraved", "technique"),
    ("shirt", "product"), ("hoodie", "product"), ("sweatshirt", "product"),
    ("tote", "product"), ("cap", "product"), ("mug", "product"),
    ("blanket", "product"),
    # not in product_fit's noun set; supplier_ops knows it is a tote
    ("handbag", "product"),
    ("halloween", "theme"), ("teacher", "theme"), ("nurse", "theme"),
    ("bride", "theme"), ("graduation", "theme"), ("birthday", "theme"),
])
def test_every_token_lands_in_the_right_bucket(token, want):
    assert nm.bucket(token) == want


def test_a_technique_is_never_mistaken_for_the_product():
    """'embroidered hoodie' sells a HOODIE. If embroidery counted as the product,
    an embroidered mug would satisfy the product requirement."""
    c = nm.classify("embroidered hoodie")
    assert c["product"] == ["hoodie"] and c["technique"] == ["embroidery"]
    assert nm.match("Embroidered Ceramic Mug", "embroidered hoodie") is False


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


def test_why_names_the_real_reason_not_just_the_shape():
    """The rejection reason must say WHAT IS MISSING. A teacher shirt is not
    rejected because it 'only shares a product' — it is rejected because it has
    no halloween."""
    ok, reason, shared = nm.why(CONTAMINANTS[0], QUERY)
    assert (ok, reason) == (False, "rejected_missing_theme")
    assert set(shared) == {"personalized", "shirt"}
    assert nm.why(REAL[0], QUERY)[1] == "theme"
    assert nm.why("Custom Embroidered Halloween Shirt", QUERY)[1] == "theme"
    assert nm.why("Ceramic Mug", QUERY)[1] == "none"


@pytest.mark.parametrize("title", CONTAMINANTS)
def test_every_halloween_contaminant_is_rejected_with_an_honest_reason(title):
    """All rejected — and the reason names what is actually missing.

    A listing that shares SOME query tokens but no halloween is
    rejected_missing_theme. One that shares nothing at all is `none`: claiming a
    missing theme there would overstate how close it came.
    """
    matched, reason, shared = nm.why(title, QUERY)
    assert matched is False, title
    assert reason == ("rejected_missing_theme" if shared else "none"), \
        f"{title} -> {reason} (shared={shared})"


def test_the_headline_contaminants_are_rejected_for_the_missing_theme():
    """The ones that produced teacher 52% and the bride tags DID share tokens
    with the query — {personalized, shirt} — so the reason must name the theme."""
    for title in ("Personalized Teacher Shirt, Comfort Colors Back to School Tee",
                  "Teacher Appreciation Shirt Personalized Name Gift",
                  "Personalized Dog Mom Shirt Custom Name",
                  "Personalized Bride Shirt, Fiancee Gift, Engagement Tee"):
        matched, reason, shared = nm.why(title, QUERY)
        assert (matched, reason) == (False, "rejected_missing_theme"), title
        assert shared, title


def test_the_reason_vocabulary_is_the_agreed_one():
    seen = {nm.why(t, q)[1] for t, q in [
        ("Personalized Dog Tag Custom", "personalized dog tag"),       # exact
        (REAL[0], QUERY),                                              # theme
        ("Custom Tee Personalized", "custom crew t-shirt"),            # synonym
        ("Personalized Name Tote Bag", "custom name tote handbag"),    # product_only
        (CONTAMINANTS[0], QUERY),                       # rejected_missing_theme
        ("Personalized Name Mug", "custom name tote handbag"),
        ("Ceramic Mug", QUERY)]}                                       # none
    assert seen <= {"exact", "theme", "synonym", "product_only",
                    "modifier_only", "rejected_missing_theme",
                    "rejected_product_mismatch", "none"}
    assert {"exact", "theme", "synonym", "product_only",
            "rejected_missing_theme", "rejected_product_mismatch",
            "none"} <= seen


# --- the owner's edge cases ---------------------------------------------------
@pytest.mark.parametrize("query,title,want", [
    # theme present -> the theme is required
    ("personalized embroidery halloween shirt",
     "Personalized Halloween Embroidered Sweatshirt", True),
    ("personalized embroidery halloween shirt",
     "Personalized Teacher Shirt Comfort Colors", False),
    # no theme -> the PRODUCT is required, and a seasonal word is not invented
    ("custom name tote handbag", "Personalized Name Tote Bag", True),
    ("custom name tote handbag", "Personalized Name Mug", False),
    ("embroidered hoodie", "Embroidered Hoodie Custom Name", True),
    ("embroidered hoodie", "Embroidered Ceramic Mug", False),
    ("personalized dog tag", "Personalized Dog Tag Custom", True),
    # 'crew' is a cut, not a niche: a plain tee must still match
    ("custom crew t-shirt", "Custom Tee Personalized", True),
    ("custom crew t-shirt", "Custom T-Shirt Personalized", True),
    # the recipient IS the niche
    ("teacher shirt", "Teacher Appreciation Shirt", True),
    ("teacher shirt", "Halloween Ghost Shirt", False),
    ("bride shirt", "Custom Future Mrs Bride Shirt", True),
    ("bride shirt", "Personalized Teacher Shirt", False),
])
def test_the_owners_edge_cases(query, title, want):
    assert nm.match(title, query) is want, f"{query!r} vs {title!r}"


def test_a_query_with_no_theme_requires_the_product_not_just_overlap():
    """'tote bag' has no theme to require, so the product carries it. A mug that
    shares 'personalized' is not a tote."""
    assert nm.classify("tote bag")["theme"] == []
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
