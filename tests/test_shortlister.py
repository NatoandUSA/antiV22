"""Shortlister integration + K/M parse fix (from the YTrends bundle feedback)."""
import json
import os

from src import ytx_import as yi
from src import shortlister_integration as si


def test_parse_number_k_m_b_suffix():
    # the real sample abbreviates big counts; these used to parse ~1000x too small
    assert yi.parse_number("1.8K") == 1800.0
    assert yi.parse_number("3.4K") == 3400.0
    assert yi.parse_number("1.2M") == 1_200_000.0
    assert yi.parse_number("2B") == 2_000_000_000.0
    assert yi.parse_number("$5,900.25") == 5900.25   # unaffected
    assert yi.parse_number("760") == 760.0


SAMPLE = {
    "view": "hidden-gems",
    "captured_at": "2026-07-15T08:48:14+00:00",
    "headers": ["Rank", "Keyword", "Views 24h", "Revenue", "Avg Price",
                "Conversion Rate", "Listings", "Sellers", "Category"],
    "rows": [
        ["1", "personalized travel pouch", "1,240", "$3,420.50", "$24.99",
         "5.1%", "128", "82", "Bags & Pouches"],
        ["3", "custom bridesmaid makeup bag", "1.8K", "$5,900.25", "$22.50",
         "6.2%", "175", "97", "Wedding Gifts"],
        ["5", "haticemediumstudio", "999", "$1,000", "$12.00", "2.2%", "5", "1",
         "Shop Name Likely"],
        ["7", "gift for her", "3.4K", "$8,000", "$28.00", "3.0%", "50000",
         "12000", "Broad Gift"],
    ],
}


def test_map_row_does_not_set_raw_demand():
    d = si.map_row_to_scorer(SAMPLE["headers"], SAMPLE["rows"][0], "hidden-gems")
    # views_24h carries the raw count; there must be NO raw "demand" key (that slot
    # is a 0-100 score and a raw count there blows Market past 100)
    assert d["views_24h"] == 1240.0
    assert "demand" not in d
    assert d.get("is_hidden_gem") is True          # view-implied opportunity signal


def test_score_latest_is_sane_and_filters_junk(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    yi.ingest(SAMPLE)                              # writes the raw file score_latest reads
    res = si.score_latest()
    assert res["ok"]
    kws = {r["keyword"] for r in res["results"]}
    # real products kept, junk (shop handle, broad seed) dropped
    assert "personalized travel pouch" in kws
    assert "custom bridesmaid makeup bag" in kws
    assert "haticemediumstudio" not in kws
    assert "gift for her" not in kws
    # every composite score is within 0-100 (the raw-demand bug produced >2000)
    for r in res["results"]:
        assert r["overall_score"] is None or 0 <= r["overall_score"] <= 100
