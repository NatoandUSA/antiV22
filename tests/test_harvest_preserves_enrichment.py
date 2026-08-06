"""Harvest must never let a weaker pull blank enrichment the master already has.

THE REAL LOSS, measured on the VPS
    Aug 6 00:42 backup   1,701 rows  revenue 998  conversion 1,458
    Aug 6 06:06 cron     1,798 rows  revenue 256  conversion   721

The 06:00 cron (`deploy/vps-build.sh` -> `main.py harvest`) added 97 genuinely
new keywords and simultaneously blanked revenue on ~740 rows.

MECHANISM
`harvest()` folds the master into the live-pull store with `merge_existing()`,
then `write_keyword_data()` rewrites the file wholesale with "w".
`merge_existing` only carried keywords the pull did NOT return; for a keyword the
pull DID return it kept the fresh row and copied nothing but `source`. The VPS IP
is blocked from YTrends, so its pulls come back thin — and every thin row
overwrote a rich one.

There is a guard for a TOTAL outage (`if append and not store`) but none for a
PARTIAL one, which is the case that actually happens.

INVARIANT
Blank / missing / zero must never beat a known value. New keywords may be added;
existing keywords may only be updated field-by-field, and only upward.
"""
import csv

import pytest

from src import harvest as H

# the master columns that carry enrichment, and the store key each maps to
FIELD_MAP = {
    "etsy_listings": "listings", "seller_count": "sellers",
    "views_24h": "views", "avg_price": "price", "avg_revenue": "revenue",
    "total_revenue": "revenue_total", "conversion_rate": "conv",
    "momentum": "momentum", "niche_age_days": "age",
    "opportunity_score": "opportunity",
}
COLS = ["keyword", "etsy_listings", "seller_count", "views_24h", "avg_price",
        "avg_revenue", "total_revenue", "conversion_rate", "momentum",
        "niche_age_days", "tm_risk", "source", "collected_at",
        "opportunity_score"]


def _master(tmp_path, rows):
    p = tmp_path / "keyword_data.csv"
    with p.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in COLS})
    return str(p)


def _rich(kw="mini bride tote bags"):
    return {"keyword": kw, "etsy_listings": 7, "seller_count": 3,
            "views_24h": 169, "avg_price": 24.5, "avg_revenue": 1397.74,
            "total_revenue": 58415.0, "conversion_rate": 0.0436,
            "momentum": 43.5, "niche_age_days": 120, "source": "keyword-lab",
            "collected_at": "2026-07-09", "opportunity_score": 81.2}


def _thin(tag):
    """What a YTrends-blocked VPS pull actually yields: the keyword, nothing else."""
    return {"tag": tag, "score": 0.0, "source": "mcp:trending", "listings": None,
            "sellers": None, "comp": None, "price": None, "conv": None,
            "revenue": None, "revenue_total": None, "momentum": None,
            "sold": None, "views": None, "age": None, "opportunity": None}


def _read(path):
    with open(path, encoding="utf-8-sig") as f:
        return {r["keyword"].strip().lower(): r for r in csv.DictReader(f)}


def _roundtrip(tmp_path, master_rows, store):
    """merge_existing + write_keyword_data — exactly what harvest() does."""
    p = _master(tmp_path, master_rows)
    carried = H.merge_existing(store, path=p)
    H.write_keyword_data(store, path=p)
    return _read(p), carried


# --- the headline losses ------------------------------------------------------
def test_existing_revenue_survives_a_harvest_row_with_blank_revenue(tmp_path):
    rows, _ = _roundtrip(tmp_path, [_rich()],
                         {"mini bride tote bags": _thin("mini bride tote bags")})
    got = rows["mini bride tote bags"]
    assert got["total_revenue"], "total_revenue was blanked by a thin pull"
    assert float(got["total_revenue"]) == pytest.approx(58415.0)
    assert got["avg_revenue"], "avg_revenue was blanked by a thin pull"


def test_existing_conversion_survives_a_harvest_row_with_blank_conversion(tmp_path):
    rows, _ = _roundtrip(tmp_path, [_rich()],
                         {"mini bride tote bags": _thin("mini bride tote bags")})
    got = rows["mini bride tote bags"]
    assert got["conversion_rate"], "conversion_rate was blanked by a thin pull"
    assert float(got["conversion_rate"]) == pytest.approx(0.0436)


@pytest.mark.parametrize("col", sorted(FIELD_MAP))
def test_every_enriched_field_survives_a_thin_pull(tmp_path, col):
    rows, _ = _roundtrip(tmp_path, [_rich()],
                         {"mini bride tote bags": _thin("mini bride tote bags")})
    assert rows["mini bride tote bags"][col], f"{col} was blanked by a thin pull"


def test_a_zero_from_the_api_never_beats_a_known_value(tmp_path):
    """A zero usually means 'I don't know'. It must not overwrite a measurement."""
    store = _thin("mini bride tote bags")
    store.update(revenue_total=0, conv=0, price=0, listings=0)
    rows, _ = _roundtrip(tmp_path, [_rich()], {"mini bride tote bags": store})
    got = rows["mini bride tote bags"]
    assert float(got["total_revenue"]) == pytest.approx(58415.0)
    assert float(got["conversion_rate"]) == pytest.approx(0.0436)


# --- what must STILL work -----------------------------------------------------
def test_a_genuinely_better_value_still_wins(tmp_path):
    """Preservation must not freeze the master: a real fresh number updates."""
    store = _thin("mini bride tote bags")
    store.update(revenue_total=99000.0, conv=0.07)
    rows, _ = _roundtrip(tmp_path, [_rich()], {"mini bride tote bags": store})
    got = rows["mini bride tote bags"]
    assert float(got["total_revenue"]) == pytest.approx(99000.0)
    assert float(got["conversion_rate"]) == pytest.approx(0.07)


def test_new_keywords_are_still_added(tmp_path):
    store = {"mini bride tote bags": _thin("mini bride tote bags"),
             "brand new phrase": _thin("brand new phrase")}
    rows, _ = _roundtrip(tmp_path, [_rich()], store)
    assert "brand new phrase" in rows
    assert len(rows) == 2


def test_keywords_absent_from_the_pull_are_still_carried(tmp_path):
    rows, carried = _roundtrip(
        tmp_path, [_rich(), _rich("canvas wine tote")],
        {"mini bride tote bags": _thin("mini bride tote bags")})
    assert carried == 1
    assert "canvas wine tote" in rows
    assert rows["canvas wine tote"]["total_revenue"]


def test_provenance_still_sticks(tmp_path):
    """A human/lab source must outlive an mcp: pull."""
    rows, _ = _roundtrip(tmp_path, [_rich()],
                         {"mini bride tote bags": _thin("mini bride tote bags")})
    assert rows["mini bride tote bags"]["source"] == "keyword-lab"


# --- the invariant, stated as a whole-file property ---------------------------
def test_row_count_can_grow_but_enrichment_density_must_not_fall(tmp_path):
    """The exact shape of the production loss: +97 rows, -740 revenue values."""
    master = [_rich(f"kw {i}") for i in range(40)]
    store = {f"kw {i}": _thin(f"kw {i}") for i in range(30)}     # thin re-pull
    store["brand new one"] = _thin("brand new one")              # plus a new one
    rows, _ = _roundtrip(tmp_path, master, store)
    rev = sum(1 for r in rows.values() if (r.get("total_revenue") or "").strip())
    conv = sum(1 for r in rows.values() if (r.get("conversion_rate") or "").strip())
    assert len(rows) == 41, "the new keyword must be added"
    assert rev == 40, f"revenue density fell from 40 to {rev}"
    assert conv == 40, f"conversion density fell from 40 to {conv}"


def test_merge_report_counts_what_was_preserved(tmp_path):
    """Silent preservation is as hard to trust as silent loss — the cron needs a
    number it can assert on."""
    p = _master(tmp_path, [_rich(), _rich("canvas wine tote")])
    store = {"mini bride tote bags": _thin("mini bride tote bags")}
    rep = H.merge_existing(store, path=p, report=True)
    assert rep["carried"] == 1          # absent from the pull
    assert rep["preserved"] >= 1        # thin fields refilled from the master
    assert rep["fields_preserved"] >= 8


# --- the cron guard (step 7) --------------------------------------------------
def test_density_guard_aborts_a_write_that_would_gut_the_master():
    """Belt and braces behind merge_existing: an unattended 06:00 cron must never
    replace measured data with blanks, whatever future writer causes it."""
    before = {"total_revenue": 998, "conversion_rate": 1458,
              "avg_price": 1452, "views_24h": 1421}
    after = {"total_revenue": 256, "conversion_rate": 721,
             "avg_price": 778, "views_24h": 764}          # the real production loss
    reason = H._density_drop(before, after)
    assert reason and "total_revenue 998 -> 256" in reason


def test_density_guard_allows_a_healthy_write():
    d = {"total_revenue": 998, "conversion_rate": 1458,
         "avg_price": 1452, "views_24h": 1421}
    assert H._density_drop(d, d) is None
    grown = {k: v + 10 for k, v in d.items()}
    assert H._density_drop(d, grown) is None


def test_density_guard_tolerates_small_genuine_corrections():
    """A few rows legitimately losing a value is a correction, not a gutting."""
    before = {"total_revenue": 1000, "conversion_rate": 1000,
              "avg_price": 1000, "views_24h": 1000}
    after = {k: 960 for k in before}                       # 4% drift
    assert H._density_drop(before, after) is None
    assert H._density_drop(before, {k: 850 for k in before})   # 15% -> abort


def test_density_of_store_counts_what_is_about_to_be_written(tmp_path):
    store = {"a": _thin("a"), "b": _thin("b")}
    store["a"].update(revenue_total=100.0, conv=0.04, price=20.0, views=50)
    got = H._density_of_store(store)
    assert got == {"total_revenue": 1, "conversion_rate": 1,
                   "avg_price": 1, "views_24h": 1}


def test_an_empty_master_never_blocks_the_first_write():
    """No file yet = nothing to protect. The guard must not deadlock a fresh
    install into never writing."""
    assert H._density_drop({f: 0 for f in H._GUARDED},
                           {f: 0 for f in H._GUARDED}) is None
