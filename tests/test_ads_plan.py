"""Ads plan must vary by keyword (regression for the 'same result every keyword' bug)."""
from pathlib import Path

from src import interactive as iv
from src import ads_plan as ap


def test_price_conversion_fall_back_to_master(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("keyword_data.csv").write_text(
        "keyword,avg_price,conversion_rate\nwidget niche,12.5,0.05\n", encoding="utf-8")
    price, _base, _ship, conv = iv._price_cost_for("widget niche", "pod")
    assert price == 12.5 and conv == 0.05
    # zero / blank stays an honest null (not a fake $0 plan)
    Path("keyword_data.csv").write_text(
        "keyword,avg_price,conversion_rate\nempty niche,0,0\n", encoding="utf-8")
    p2, _b, _s, c2 = iv._price_cost_for("empty niche", "pod")
    assert p2 is None and c2 is None


def test_ads_plan_clicks_track_real_conversion():
    # a real conversion rate changes clicks-per-sale -> the plan is keyword-specific
    hi = ap.build("k-hi", conversion_rate=0.05)   # ~20 clicks/sale
    lo = ap.build("k-lo", conversion_rate=0.02)   # ~50 clicks/sale
    assert hi["clicks_per_sale"] == 20 and lo["clicks_per_sale"] == 50
    assert hi["assumed_cr"] is None               # real CR used, not assumed
