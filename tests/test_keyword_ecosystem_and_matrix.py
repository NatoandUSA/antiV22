import pytest
from src import ytrends_mcp as mcp
from src import pattern_miner as pm
from src import keyword_lab as kl
from src import listing_factory as lf


def test_pull_keyword_ecosystem_structure():
    eco = mcp.pull_keyword_ecosystem("nurse sweatshirt")
    assert isinstance(eco, dict)
    assert "seed" in eco
    assert "stats" in eco
    assert "related_keywords" in eco
    assert "competitor_tags" in eco
    assert "top_listings" in eco


def test_keyword_lab_expansion_para_mi_hija():
    res = kl.generate("para mi hija", limit=14)
    assert isinstance(res, dict)
    cands = res.get("candidates") or []
    assert len(cands) >= 5
    for c in cands:
        kw = c.get("keyword")
        assert kw
        assert len(kw.split()) >= 3  # Longtail only rule


def test_pattern_miner_contextual_dna():
    pat = pm.mine("nurse sweatshirt")
    assert isinstance(pat, dict)
    dna = pat.get("contextual_dna")
    assert dna is not None
    assert "title_syntax_dna" in dna
    assert "tag_distribution_dna" in dna
    assert "data_proofs" in dna
    assert isinstance(dna["data_proofs"], list)


def test_listing_factory_13_tags_matrix():
    pack = lf.build_listing("para mi hija")
    assert pack["keyword"] == "para mi hija"
    assert "tags_matrix" in pack
    matrix = pack["tags_matrix"]
    assert len(matrix) <= 13
    assert len(pack["tags"]) == len(matrix)
    for tm in matrix:
        assert len(tm["tag"]) <= 20
        assert tm["char_count"] <= 20
        assert tm["tm_status"] in ("PASS", "CAUTION", "HIGH")
        assert "role" in tm
        assert "source" in tm
        assert "demand" in tm
        assert "competition" in tm

    # Test report write
    path = lf.write_pack(pack)
    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert "Etsy Master Tag & Keyword Matrix (13 Tags Model)" in content
    assert "Etsy Learning Box (Few-Shot Contextual DNA)" in content
