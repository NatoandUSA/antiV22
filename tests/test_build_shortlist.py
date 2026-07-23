"""Tests for the Build Queue module (V36)."""
import csv
import os
from pathlib import Path

import pytest

from src import build_shortlist as bq


@pytest.fixture()
def base(tmp_path, monkeypatch):
    p = tmp_path / "keyword_data.csv"
    fields = ["keyword", "etsy_listings", "seller_count", "views_24h",
              "avg_price", "avg_revenue", "conversion_rate", "momentum",
              "niche_age_days", "tm_risk", "source", "collected_at"]
    rows = [
        # proven, buildable, clean
        ["custom shirt kids", 30, 10, 88, 21.76, 500, 0.041, 89.5, "", "", "mcp:x", "2026-07-09"],
        # proven but too crowded (listings > 300)
        ["wall art print", 5000, 900, 9000, 15, 8000, 0.02, 70, "", "", "mcp:x", "2026-07-09"],
        # proven but cheap (price < 8)
        ["sticker pack", 40, 5, 200, 3.5, 100, 0.03, 60, "", "", "mcp:x", "2026-07-09"],
        # partial (listings only)
        ["mystery tag", 12, 3, 0, 0, 0, 0, 40, "", "", "mcp:x", "2026-07-09"],
        # unverified (all zero)
        ["ghost keyword", 0, 0, 0, 0, 0, 0, 40, "", "", "mcp:x", "2026-07-09"],
    ]
    with p.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(fields)
        w.writerows(rows)
    # point the module's data files into the temp dir
    monkeypatch.setattr(bq, "MASTER", p)
    monkeypatch.setattr(bq, "ARCHIVE", tmp_path / "arch.csv")
    monkeypatch.setattr(bq, "ACTIONED", tmp_path / "actioned.csv")
    return p


def test_classification_counts(base):
    d = bq.analyze()
    assert d["total"] == 5
    assert d["counts"] == {"proven": 3, "partial": 1, "unverified": 1}


def test_buildable_filters_crowded_and_cheap(base):
    d = bq.analyze()
    kws = {p["keyword"] for p in d["buildable"]}
    assert "custom shirt kids" in kws
    assert "wall art print" not in kws     # too crowded
    assert "sticker pack" not in kws       # margin too thin
    assert "ghost keyword" not in kws      # unverified


def test_build_score_and_theme(base):
    d = bq.analyze()
    p = next(x for x in d["buildable"] if x["keyword"] == "custom shirt kids")
    assert 0 <= p["build_score"] <= 100
    assert p["theme"] == "Personalized"
    assert p["tm"] in ("OK", "CAUTION", "HIGH")


def test_mark_done_moves_to_done(base):
    assert bq.mark_done("custom shirt kids", "Quyen") is True
    d = bq.analyze()
    assert any(p["keyword"] == "custom shirt kids" for p in d["done"])
    assert all(p["keyword"] != "custom shirt kids" for p in d["open"])


def test_archive_empties_moves_only_unverified(base):
    moved, kept = bq.archive_empties()
    assert moved == 1
    assert kept == 4
    remaining = [r["keyword"] for r in bq._load_master()]
    assert "ghost keyword" not in remaining
    assert bq.ARCHIVE.is_file()
    with bq.ARCHIVE.open(encoding="utf-8-sig") as f:
        arch = [r["keyword"] for r in csv.DictReader(f)]
    assert arch == ["ghost keyword"]


def test_render_html_smoke(base):
    d = bq.analyze()
    html = bq.render_html(d, csrf="TOK")
    assert "Build Queue" in html and "<table>" in html
    assert "/design-analyzer?q=" in html and "/launch-kit?q=" in html
    assert "archive-empties" in html


def test_render_handles_empty_base(tmp_path, monkeypatch):
    p = tmp_path / "keyword_data.csv"
    p.write_text("keyword,etsy_listings,views_24h,avg_revenue,conversion_rate,"
                 "avg_price,momentum,seller_count\n", encoding="utf-8")
    monkeypatch.setattr(bq, "MASTER", p)
    monkeypatch.setattr(bq, "ACTIONED", tmp_path / "a.csv")
    d = bq.analyze()
    html = bq.render_html(d, csrf="TOK")
    assert "No proven buildable" in html
