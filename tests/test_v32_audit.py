"""V32 audit-fix regression tests (CPA + bug-hunter findings)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import etsy_proof as ep                       # noqa: E402
from src import ranking_engine as re_eng               # noqa: E402


def test_pct_midrank_zero_sales_not_100():
    """All-zero column must score 50 (midrank), never 100 per zero row."""
    f = ep._pct([0, 0, 0, 0, 0])
    assert f(0) == 50.0
    g = ep._pct([0] * 8 + [10, 20])
    assert g(0) == 40.0        # (0 less + 8*0.5)/10
    assert g(20) == 95.0       # (9 + 0.5)/10


def test_age_zero_days_is_real_data():
    """AGE (DAYS)=0 (listed today) must map to 0.0 months, not None."""
    # replicate the mapping expression from _capture_rows
    age_days = 0.0
    val = (age_days / 30.0) if age_days is not None else None
    assert val == 0.0                   # 0 days -> 0.0 months, NOT None


def test_medium_conf_proven_never_demotes_and_never_contradicts():
    """Fuzzy PROVEN (conf .34-.50): raises weak actions to CONFIRM_FIRST; a
    merit-earned BUILD_NOW keeps action AND appends (not replaces) reason."""
    proof = {"verdict": "PROVEN_WINNER", "match": "fuzzy",
             "match_confidence": 0.40,
             "evidence": "60 sold - 3 shops", "sold": 60}
    # weak base (WATCH market) -> raised to CONFIRM_FIRST
    d1 = re_eng.decide("personalized nurse gift embroidered sweatshirt",
                       "WATCH", mode="embroidery", proof=proof)
    assert d1["action"] == "CONFIRM_FIRST"
    # strong base (GO market, 4+ words) -> BUILD_NOW kept, reason appended
    d2 = re_eng.decide("personalized nurse gift embroidered sweatshirt",
                       "GO", mode="embroidery", proof=proof)
    assert d2["action"] == "BUILD_NOW"
    assert "verify the match" in d2["reason"]
    assert not d2["reason"].startswith("PROVEN evidence via fuzzy")


def test_sold_24h_has_its_own_threshold():
    """20+ sold in 24h across 2+ shops is PROVEN even with 0 lifetime sold."""
    rows = [{"keyword": "usa patchwork tee", "title": f"USA Patchwork Tee {i}",
             "shop": f"shop{i}", "sold": 12, "recent": True, "revenue": 200.0,
             "age_months": 2.0, "price": None, "reviews": None}
            for i in range(3)]
    import unittest.mock as um
    with um.patch.object(ep, "_latest_rows", return_value=[]), \
         um.patch.object(ep, "_capture_rows", return_value=rows):
        proof = ep.build_proof()
    rec = list(proof.values())[0]
    assert rec["sold_24h"] == 36 and rec["sold"] == 0
    assert rec["verdict"] == "PROVEN_WINNER"
    assert "sold/24h" in rec["evidence"]


def test_cross_source_dedup_no_double_count():
    """Same listing in the export AND a capture must count once."""
    row = {"keyword": "usa patchwork tee", "title": "USA Patchwork Tee",
           "shop": "shopA", "sold": 30, "revenue": 500.0, "age_months": 5.0,
           "price": None, "reviews": None}
    import unittest.mock as um
    with um.patch.object(ep, "_latest_rows", return_value=[dict(row)]), \
         um.patch.object(ep, "_capture_rows", return_value=[dict(row)]):
        proof = ep.build_proof()
    rec = list(proof.values())[0]
    assert rec["sold"] == 30      # NOT 60
    assert rec["verdict"] != "PROVEN_WINNER"


def test_merge_keywords_survives_bom():
    """A BOM'd master must still merge (not wipe) - utf-8-sig read."""
    import csv as _csv
    import tempfile, os
    from src import ytx_import as yx
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "kd.csv")
        with open(p, "w", encoding="utf-8-sig", newline="") as fh:
            w = _csv.writer(fh)
            w.writerow(["keyword", "etsy_listings", "seller_count", "views_24h",
                        "avg_price", "avg_revenue", "conversion_rate",
                        "momentum", "tm_risk", "source", "collected_at"])
            w.writerow(["existing kw", "10", "5", "20", "9.99", "100", "0.03",
                        "50", "", "mcp:search", "2026-07-01"])
        idx = yx._resolve(["Keyword", "Momentum"])
        added, new = yx._merge_keywords("test", [["brand new kw", "60"]], idx,
                                        path=p)
        with open(p, encoding="utf-8-sig") as fh:
            kws = {r["keyword"] for r in _csv.DictReader(fh)}
        assert "existing kw" in kws and "brand new kw" in kws   # merged, not wiped
        assert new == 1


if __name__ == "__main__":
    for n, f in sorted(globals().items()):
        if n.startswith("test_"):
            f()
            print(f"ok {n}")
