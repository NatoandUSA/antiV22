"""Long-tail lane + the harvest data-integrity fixes it depends on.

The lane is a VIEW: it must never change a score, verdict or action. These
tests pin that, the honest-nulls rules, and the four harvest bugs that made
long-tails unrankable.
"""
import csv

import pytest

from src import harvest, longtail as lt


# --------------------------------------------------------------- the lane ----
def _row(keyword, conv=0.04, rev=800.0, listings=50, **kw):
    r = {"keyword": keyword, "conv": conv, "rev": rev, "comp": listings,
         "sellers": None, "rev_total": None, "launchable": True,
         "action": "WATCH", "fit_label": "POD product", "proof_tier": 9,
         "source": "mcp:trending"}
    r.update(kw)
    return r


def test_short_tail_is_excluded():
    assert lt.sellability(_row("funny shirt")) is None
    assert lt.sellability(_row("funny dad shirt")) is not None


def test_no_evidence_is_excluded_not_scored_low():
    """honest-nulls: an unmeasured keyword is a blank, not a weak opportunity."""
    assert lt.sellability(_row("cute grad gift ideas", conv=0)) is None
    assert lt.sellability(_row("cute grad gift ideas", rev=0)) is None
    assert lt.sellability(_row("cute grad gift ideas", listings=None)) is None


def test_unbuildable_rows_stay_out():
    assert lt.sellability(_row("disney dad shirt", action="BLOCKED")) is None
    assert lt.sellability(_row("some theme phrase", launchable=False)) is None


def test_saturated_market_is_excluded():
    assert lt.sellability(_row("retro 4th of july tee", listings=50_000)) is None


def test_legacy_total_revenue_is_normalised_per_listing():
    """Pre-fix opportunity rows hold the NICHE TOTAL in `rev`; reading it as
    per-listing revenue is what made head terms look 250x richer."""
    legacy = _row("funny shirt for dad", rev=80_000.0, listings=175,
                  source="mcp:opportunity", rev_total=None)
    fixed = _row("funny shirt for dad", rev=457.0, listings=175,
                 source="mcp:opportunity", rev_total=80_000.0)
    assert lt.sellability(legacy)["rev_per_listing"] == pytest.approx(457.1, abs=1)
    assert lt.sellability(fixed)["rev_per_listing"] == pytest.approx(457.0)


def test_more_money_and_conversion_scores_higher():
    lo = lt.sellability(_row("dad shirt with photo", conv=0.02, rev=200.0))
    hi = lt.sellability(_row("dad shirt with photo", conv=0.06, rev=2000.0))
    assert hi["score"] > lo["score"]
    assert hi["verdict"] == lt.PUSH


def test_room_beats_a_crowded_market():
    open_mkt = lt.sellability(_row("hair bow monogram set", listings=30))
    crowded = lt.sellability(_row("hair bow monogram set", listings=1500))
    assert open_mkt["score"] > crowded["score"]


def test_page_renders_and_reports_what_it_dropped(monkeypatch):
    monkeypatch.setattr(lt, "shortlist", lambda *a, **k: {
        "rows": [lt.sellability(_row("custom couple shirts", conv=0.05,
                                     rev=2300.0, listings=44))],
        "n_scored": 1, "n_long": 10, "n_total": 100, "dropped_no_evidence": 9})
    out = lt.page()
    assert "custom couple shirts" in out
    assert "**9**" in out              # excluded rows are stated, not hidden


# ------------------------------------------------------- supply (offline) ----
def test_pull_keeps_only_evidence_backed_long_tails(monkeypatch):
    related = [
        {"tag": "best dad ever shirt", "avg_revenue": 1396.79,
         "avg_conversion_rate": 0.0303, "tag_listing_count": 444},
        {"tag": "dad gift", "avg_revenue": 2129.98,          # 2 words -> out
         "avg_conversion_rate": 0.02, "tag_listing_count": 3899},
        {"tag": "custom photo dad shirt", "avg_revenue": None,   # no money -> out
         "avg_conversion_rate": 0.02, "tag_listing_count": 100},
    ]
    import src.ytrends_mcp as mcp
    monkeypatch.setattr(mcp, "research_keyword",
                        lambda kw, days=30: {"related_keywords": related})
    got = lt.pull(["funny shirt for dad"], per_seed=10)
    assert [r["keyword"] for r in got] == ["best dad ever shirt"]
    assert got[0]["avg_revenue"] == 1396.79 and got[0]["source"] == "longtail:related"


def test_pull_survives_a_dead_seed(monkeypatch):
    import src.ytrends_mcp as mcp

    def boom(kw, days=30):
        raise RuntimeError("MCP down")
    monkeypatch.setattr(mcp, "research_keyword", boom)
    assert lt.pull(["anything"]) == []


def test_save_rows_appends_without_duplicating(tmp_path):
    p = tmp_path / "keyword_data.csv"
    p.write_text("keyword,etsy_listings,avg_revenue,conversion_rate,source,"
                 "collected_at\nexisting kw,10,5,0.01,mcp:search,2026-01-01\n",
                 encoding="utf-8")
    rows = [{"keyword": "best dad ever shirt", "etsy_listings": 444,
             "avg_revenue": 1396.79, "conversion_rate": 0.0303,
             "source": "longtail:related"},
            {"keyword": "existing kw", "avg_revenue": 1.0}]
    assert lt.save_rows(rows, str(p)) == 1
    out = list(csv.DictReader(p.open(encoding="utf-8")))
    assert len(out) == 2
    assert out[1]["keyword"] == "best dad ever shirt"
    assert out[1]["avg_revenue"] == "1396.79"


# ------------------------------------------------ harvest data integrity ----
def test_revenue_units_never_mix():
    """scout_opportunities returns a niche TOTAL, trending a per-listing avg."""
    store = {}
    harvest._add(store, "opportunity kw", 70, "opportunity", listings=100,
                 revenue_total=80_000.0)
    harvest._add(store, "trending kw", 40, "trending", listings=100, revenue=800.0)
    assert store["opportunity kw"]["revenue"] == pytest.approx(800.0)
    assert store["opportunity kw"]["revenue_total"] == 80_000.0
    assert store["trending kw"]["revenue"] == 800.0
    assert store["trending kw"]["revenue_total"] is None


def test_momentum_is_measured_or_blank(tmp_path):
    """A source score is not momentum. Plain search has none -> stays blank."""
    store = {}
    harvest._add(store, "searched kw", 40, "search")
    harvest._add(store, "trending kw", 55, "trending", momentum=55.0)
    p = tmp_path / "kd.csv"
    harvest.write_keyword_data(store, str(p))
    got = {r["keyword"]: r for r in csv.DictReader(p.open(encoding="utf-8"))}
    assert got["searched kw"]["momentum"] == ""
    assert got["trending kw"]["momentum"] == "55.0"


def test_absent_metrics_are_blank_not_zero(tmp_path):
    """0 meant both 'measured zero' and 'never measured', so the scorer read a
    row with nothing behind it as a real 0% converter."""
    store = {}
    harvest._add(store, "bare kw", 40, "search")
    p = tmp_path / "kd.csv"
    harvest.write_keyword_data(store, str(p))
    row = next(csv.DictReader(p.open(encoding="utf-8")))
    for col in ("etsy_listings", "avg_revenue", "conversion_rate", "views_24h"):
        assert row[col] == "", col


def test_harvest_merge_keeps_keywords_the_pull_did_not_return(tmp_path):
    """The bug that deleted every Keyword Lab long-tail on each harvest."""
    p = tmp_path / "kd.csv"
    p.write_text("keyword,etsy_listings,seller_count,views_24h,avg_price,"
                 "avg_revenue,total_revenue,conversion_rate,momentum,"
                 "niche_age_days,tm_risk,source,collected_at\n"
                 "generated long tail,44,20,,,640,,0.063,,,,keyword-lab,2026-07-01\n",
                 encoding="utf-8")
    store = {}
    harvest._add(store, "fresh from mcp", 60, "trending", listings=10)
    assert harvest.merge_existing(store, str(p)) == 1
    harvest.write_keyword_data(store, str(p))
    got = {r["keyword"]: r for r in csv.DictReader(p.open(encoding="utf-8"))}
    assert "generated long tail" in got, "harvest deleted a non-MCP keyword"
    assert got["generated long tail"]["source"] == "keyword-lab"
    assert got["generated long tail"]["avg_revenue"] == "640.0"
    assert "fresh from mcp" in got


def test_merge_keeps_original_source_for_a_rediscovered_keyword(tmp_path):
    p = tmp_path / "kd.csv"
    p.write_text("keyword,source,collected_at\nshared kw,keyword-lab,2026-07-01\n",
                 encoding="utf-8")
    store = {}
    harvest._add(store, "shared kw", 60, "trending", listings=10)
    harvest.merge_existing(store, str(p))
    assert store["shared kw"]["source"] == "keyword-lab"   # provenance is sticky
    assert store["shared kw"]["listings"] == 10            # metrics stay fresh
