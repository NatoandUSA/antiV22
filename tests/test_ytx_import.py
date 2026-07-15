"""YTrends extension ingest - parsing + merge + category fallback."""
import csv
import os
from pathlib import Path

from src import ytx_import as yi


def test_parse_number_formats():
    assert yi.parse_number("$1,234.56") == 1234.56
    assert yi.parse_number("12,486.75") == 12486.75
    assert yi.parse_number("-") is None
    assert yi.parse_number("") is None
    assert yi.parse_number("(3.00)") == -3.0
    assert yi.parse_number("30") == 30.0


def test_parse_percent():
    assert abs(yi.parse_percent("5.1%") - 0.051) < 1e-9
    assert abs(yi.parse_percent("0.05") - 0.05) < 1e-9
    assert yi.parse_percent("-") is None


def _keyword_payload():
    return {
        "view": "hidden-gems",
        "headers": ["Rank", "Keyword", "Gem Score", "Listings", "Sellers",
                    "Listings/Seller", "Avg Price", "Revenue", "Conversion",
                    "Sold 24h", "Views Vel.", "Trend", "Competition"],
        "rows": [
            ["#512", "patriotic soft tee", "97.1", "30", "8", "3.8", "$19.25",
             "$12,486.75", "5.1%", "2", "4.39", "Rising", "Low"],
            ["#556", "teacher doodle shirt", "58.2", "42", "28", "1.5", "$7.06",
             "$7,031.71", "3.2%", "0", "1.15", "Stable", "Low"],
        ],
    }


def test_ingest_keywords_merges_into_keyword_data(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    out = yi.ingest(_keyword_payload())
    assert out["type"] == "keywords" and out["keyword_rows_merged"] == 2
    rows = list(csv.DictReader((tmp_path / "keyword_data.csv").open(encoding="utf-8")))
    by_kw = {r["keyword"]: r for r in rows}
    assert "patriotic soft tee" in by_kw
    # conversion normalised from "5.1%" to a fraction
    assert abs(float(by_kw["patriotic soft tee"]["conversion_rate"]) - 0.051) < 1e-3
    # a SECOND import must MERGE, not wipe the first
    p2 = _keyword_payload()
    p2["rows"] = [["#900", "nurse gift mug", "70", "20", "10", "2", "$15",
                   "$5,000", "4%", "1", "2", "Rising", "Low"]]
    yi.ingest(p2)
    rows2 = list(csv.DictReader((tmp_path / "keyword_data.csv").open(encoding="utf-8")))
    kws = {r["keyword"] for r in rows2}
    assert "nurse gift mug" in kws and "patriotic soft tee" in kws  # old kept


def test_ingest_categories_writes_fallback_csv(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    payload = {
        "view": "opportunity-categories",
        "headers": ["Category", "Path", "Listings", "Sellers", "Revenue",
                    "Avg Price", "Conversion", "Sold 24h", "Views Vel.",
                    "Competition", "Opportunity", "Verdict", "Demand/Supply"],
        "rows": [["Psychic Readings", "Home & Living", "3,503", "574",
                  "$8,258,915.84", "$23.13", "7.8%", "1", "0.11", "High",
                  "80.3", "Competitive", "3.17"]],
    }
    out = yi.ingest(payload)
    assert out["type"] == "categories"
    assert (tmp_path / "data" / "imports" / "category_intel.csv").is_file()
    got = yi.latest_categories()
    assert got and got[0]["Category"] == "Psychic Readings"


def test_empty_payload_is_safe(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    out = yi.ingest({"view": "x", "headers": ["Keyword"], "rows": []})
    assert out["type"] == "empty" and out["rows_received"] == 0
    assert not (tmp_path / "keyword_data.csv").is_file()  # empty never writes fuel
