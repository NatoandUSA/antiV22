"""V35.5 L0 gate regression tests.

Locks the four gate bugs found by the external engine review (GPT / Gemini /
Grok) so they cannot silently come back:
  BUG-1  discover.matches_mode substring miscategorisation (patch->patchwork)
  BUG-2  bare "stitch" hard-blocked as the Lilo & Stitch trademark
  BUG-3  ambiguous everyday words (converse/frozen/mario/...) blocked w/o context
  BUG-4  concatenated brands (superbowl/starwars/babyyoda) slipping through

All pure/offline - no network, no data/ tree.
"""
from src.trademark import check
from src.discover import matches_mode
from src.product_fit import classify, EMBROIDERY_FIT, POD_FIT, TRADEMARK_RISK, DIGITAL_FIT


# --------------------------------------------------------------------------
# BUG-2 : embroidery technique "stitch" must NOT be a trademark block
# --------------------------------------------------------------------------

def test_stitch_technique_not_trademark_blocked():
    for kw in ("cross stitch monogram sweatshirt",
               "satin stitch nurse gift",
               "chain stitch embroidered hoodie",
               "stitch count",
               "back stitch tote bag"):
        assert check(kw)[0] != "HIGH", kw


def test_lilo_and_stitch_still_blocked():
    for kw in ("lilo and stitch shirt", "lilo & stitch hoodie",
               "lilo stitch birthday shirt", "stitch disney ohana tee"):
        assert check(kw)[0] == "HIGH", kw


# --------------------------------------------------------------------------
# BUG-3 : ambiguous everyday words - block only WITH brand context
# --------------------------------------------------------------------------

def test_ambiguous_words_not_hard_blocked_without_context():
    for kw in ("converse with god shirt",
               "frozen hot chocolate mug",
               "mario birthday shirt",          # a person named Mario
               "ford tough work gloves"):
        assert check(kw)[0] in ("OK", "CAUTION"), kw


def test_ambiguous_words_blocked_with_brand_context():
    for kw in ("frozen elsa birthday shirt",
               "disney frozen olaf shirt",
               "super mario bros party shirt",
               "air jordan sneaker tee"):
        assert check(kw)[0] == "HIGH", kw


def test_real_brands_still_blocked():
    for kw in ("bluey birthday shirt", "taylor swift eras hoodie",
               "pokemon pikachu tee", "disney nurse shirt"):
        assert check(kw)[0] == "HIGH", kw


# --------------------------------------------------------------------------
# BUG-4 : concatenated multi-word brands must be caught
# --------------------------------------------------------------------------

def test_concatenated_brands_caught():
    for kw in ("superbowl party shirt", "starwars birthday shirt",
               "babyyoda mug"):
        assert check(kw)[0] == "HIGH", kw


def test_spaced_multiword_brands_still_caught():
    for kw in ("super bowl party shirt", "star wars birthday shirt",
               "baby yoda mug"):
        assert check(kw)[0] == "HIGH", kw


# --------------------------------------------------------------------------
# BUG-1 : embroidery-mode routing on token boundaries, not substrings
# --------------------------------------------------------------------------

def test_pod_words_not_forced_to_embroidery():
    # "patch" must not match "patchwork"; "knit" must not match "knitting".
    for kw in ("patchwork usa tee", "dispatch rider shirt",
               "knitting nana shirt"):
        assert matches_mode(kw, "embroidery") is False, kw
        assert matches_mode(kw, "pod") is True, kw


def test_real_embroidery_terms_still_route_to_embroidery():
    for kw in ("cross stitch monogram sweatshirt",
               "custom embroidered sweatshirt",
               "embroidered patch sweatshirt",
               "chenille name bag",
               "monogrammed tote bag"):
        assert matches_mode(kw, "embroidery") is True, kw


# --------------------------------------------------------------------------
# End-to-end product_fit.classify (the real L0 gate the Inbox reads)
# --------------------------------------------------------------------------

def test_golden_keyword_patchwork_usa_tee_launchable_in_pod():
    c = classify("patchwork usa tee", mode="pod")
    assert c["status"] == POD_FIT and c["launchable"], c


def test_pod_keywords_not_misrouted():
    assert classify("dispatch rider shirt", mode="pod")["launchable"]
    knit = classify("knitting nana shirt", mode="pod")
    assert knit["status"] == POD_FIT and knit["launchable"], knit


def test_cross_stitch_is_launchable_embroidery():
    c = classify("cross stitch monogram sweatshirt")
    assert c["status"] == EMBROIDERY_FIT and c["launchable"], c


def test_trademark_keywords_still_blocked_end_to_end():
    assert classify("lilo and stitch shirt")["status"] == TRADEMARK_RISK
    assert classify("bluey birthday shirt")["status"] == TRADEMARK_RISK


def test_digital_still_skipped():
    assert classify("nurse svg bundle")["status"] == DIGITAL_FIT
