"""Keyword Lab: long-tail-only emission, sane subjects, adjacent-buyer expansion."""
import json
from pathlib import Path

from src import keyword_lab as kl


def _seed_spy(tmpdir=Path("data/imports/etsy_spy")):
    tmpdir.mkdir(parents=True, exist_ok=True)
    p = tmpdir / "zz_test_lab.json"
    p.write_text(json.dumps({
        "view": "etsy",
        "headers": ["title", "price", "shop", "search"],
        "rows": [["Personalized Nurse Embroidered Sweatshirts", "39.99", "A", "nurse"],
                 ["Custom Nurse RN Sweatshirt Gift", "42", "B", "nurse"]]}),
        encoding="utf-8")
    return p


def test_candidates_are_long_tail_only_and_subject_sane():
    p = _seed_spy()
    try:
        g = kl.generate("nurse sweatshirt")
        assert g["candidates"], "should generate candidates"
        for c in g["candidates"]:
            assert len(c["keyword"].split()) >= 3, c
            assert "sweatshirts" not in c["keyword"]          # no plural garbage
            assert c["keyword"].count("sweatshirt") <= 1      # no product doubling
        # adjacent-buyer expansion present
        assert any("er nurse" in c["keyword"] or "icu nurse" in c["keyword"]
                   for c in g["candidates"])
    finally:
        p.unlink(missing_ok=True)


def test_trademarked_seed_not_suggested_as_buildable():
    # V37.4 safety regression: a trademarked seed must not yield build-ready
    # infringing long-tails. All HIGH-trademark candidates are screened out.
    g = kl.generate("disney princess shirt")
    assert g.get("tm_dropped", 0) > 0
    assert all("disney" not in c["keyword"] for c in g["candidates"])


def test_mode_aware_material_and_keyword_product():
    # POD keeps no material word; embroidery adds "embroidered"; the keyword's own
    # product (sweatshirt) drives candidates rather than a pattern-derived noun.
    pod = [c["keyword"] for c in kl.generate("nurse sweatshirt", mode="pod")["candidates"]]
    emb = [c["keyword"] for c in kl.generate("nurse sweatshirt", mode="embroidery")["candidates"]]
    assert pod and all("embroidered" not in k for k in pod)     # POD: no material word
    assert any("sweatshirt" in k for k in pod)                  # product from keyword
    assert any("embroidered" in k for k in emb)                 # embroidery keeps it
