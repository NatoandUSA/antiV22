"""Freshness column: the date a keyword entered our data.

The trap this guards: printing the render clock per row would look like a
per-row measurement while actually being the same number 40 times. Only "added"
is stored, so only "added" is a column.
"""
import csv
import sqlite3
from datetime import date

import pytest

from src import freshness as fr


@pytest.fixture
def data(tmp_path):
    """A master and a feed log that disagree, which is the normal case: the feed
    sees a keyword days before it is written to the master."""
    m = tmp_path / "keyword_data.csv"
    with m.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["keyword", "collected_at"])
        w.writeheader()
        w.writerow({"keyword": "bridesmaid bag", "collected_at": "2026-07-09"})
        w.writerow({"keyword": "canvas wine tote", "collected_at": "2026-08-02"})
        w.writerow({"keyword": "master only", "collected_at": "2026-08-05"})
    d = tmp_path / "agent.db"
    conn = sqlite3.connect(d)
    conn.execute("CREATE TABLE discovered_keywords (tag TEXT, captured_at TEXT)")
    conn.executemany(
        "INSERT INTO discovered_keywords VALUES (?, ?)",
        [("bridesmaid bag", "2026-07-05 18:02:33"),      # earlier than master
         ("bridesmaid bag", "2026-07-20 09:00:00"),      # a later re-sighting
         ("canvas wine tote", "2026-08-01 10:00:00"),
         ("Feed Only", "2026-06-01 08:00:00")])
    conn.commit()
    conn.close()
    return str(m), str(d)


def test_the_earlier_of_the_two_sources_wins(data):
    """The feed log usually sees a keyword first; taking the master's date would
    silently age the keyword down and hide how long we have sat on it."""
    m, d = data
    assert fr.first_seen("bridesmaid bag", m, d) == "2026-07-05"


def test_a_later_re_sighting_never_overwrites_the_first(data):
    """discovered_keywords appends on every pull, so the same keyword has many
    rows. MIN is the whole point."""
    m, d = data
    assert fr.first_seen("bridesmaid bag", m, d) == "2026-07-05"


def test_either_source_alone_is_enough(data):
    m, d = data
    assert fr.first_seen("master only", m, d) == "2026-08-05"
    assert fr.first_seen("feed only", m, d) == "2026-06-01"


def test_lookup_is_case_insensitive(data):
    """Feed tags and master keywords do not agree on case."""
    m, d = data
    assert fr.first_seen("FEED ONLY", m, d) == "2026-06-01"
    assert fr.first_seen("  Canvas Wine Tote  ", m, d) == "2026-08-01"


def test_a_keyword_we_have_never_seen_is_new_not_blank(data):
    """NEW is the most useful cell in the column — the fresh discovery."""
    m, d = data
    assert fr.first_seen("never heard of it", m, d) is None
    assert fr.age_label(None) == fr.NEW


def test_age_label_reads_as_freshness(data):
    assert fr.age_label("2026-08-06", today=date(2026, 8, 6)) == "today"
    assert fr.age_label("2026-08-03", today=date(2026, 8, 6)) == "3d"
    assert fr.age_label("2026-07-05", today=date(2026, 8, 6)) == "32d"
    # a clock skew must not render as a negative age
    assert fr.age_label("2026-08-09", today=date(2026, 8, 6)) == "today"


def test_a_missing_or_junk_stamp_is_new_never_a_crash(data):
    m, d = data
    for junk in ("", None, "not-a-date", "2026", "0000-00-00"):
        assert fr.age_label(junk) == fr.NEW


def test_missing_sources_read_new_and_never_raise(tmp_path):
    """No master and no db must not break a page — every row just reads NEW."""
    m = str(tmp_path / "nope.csv")
    d = str(tmp_path / "nope.db")
    assert fr.first_seen("anything", m, d) is None
    assert fr.labels_for(["a", "b"], m, d) == {"a": fr.NEW, "b": fr.NEW}


def test_labels_for_is_what_a_table_renders(data):
    m, d = data
    got = fr.labels_for(["bridesmaid bag", "brand new thing"], m, d,
                        today=date(2026, 8, 6))
    assert got == {"bridesmaid bag": "32d", "brand new thing": "NEW"}


def test_a_whole_table_costs_one_read_not_one_per_row(data, monkeypatch):
    """The naive shape is a query per row. On six tables of 40 rows that is 240
    open/query/close cycles per page load."""
    m, d = data
    fr._SNAP.clear()
    real = sqlite3.connect
    calls = []

    def _counted(*a, **k):
        calls.append(a[0] if a else None)
        return real(*a, **k)

    monkeypatch.setattr(sqlite3, "connect", _counted)
    fr.labels_for(["bridesmaid bag", "canvas wine tote", "feed only",
                   "master only", "unknown a", "unknown b"], m, d)
    assert len(calls) == 1, f"expected one DB read for the table, got {len(calls)}"


def test_the_cache_refreshes_when_the_data_changes(data):
    """A stale cache would keep showing NEW after a keyword is harvested."""
    m, d = data
    assert fr.first_seen("late arrival", m, d) is None
    conn = sqlite3.connect(d)
    conn.execute("INSERT INTO discovered_keywords VALUES (?, ?)",
                 ("late arrival", "2026-08-06 07:00:00"))
    conn.commit()
    conn.close()
    assert fr.first_seen("late arrival", m, d) == "2026-08-06"


def test_ranked_note_states_the_live_fact_once():
    """'ranked' is not stored — it happens on page load. Said once per table."""
    note = fr.ranked_note("2026-08-06 09:30")
    assert "Ranked live" in note and "NEW" in note and "Added" in note


# --- the wiring ---------------------------------------------------------------
FEEDS = [
    ("trending", "trending_keywords"),
    ("opportunities", "scout_opportunities"),
    ("gems", "hidden_gems"),
]


@pytest.fixture
def feed(monkeypatch):
    """Two keywords: one long known, one never seen. Serves every feed."""
    from src import interactive as it
    rows = [{"tag": "bridesmaid bag", "momentum_score": 51.6, "gem_score": 90,
             "opportunity_score": 91.1, "competition_level": "medium",
             "avg_conversion_rate": 0.031, "avg_price": 19.47,
             "avg_price_usd": 19.47, "sellers": 9, "listing_count": 40,
             "seller_count": 10},
            {"tag": "brand new tote bag", "momentum_score": 40.0, "gem_score": 80,
             "opportunity_score": 70.0, "competition_level": "low",
             "avg_conversion_rate": 0.02, "avg_price": 10.0,
             "avg_price_usd": 10.0, "sellers": 3, "listing_count": 12,
             "seller_count": 4}]
    monkeypatch.setattr(it, "_pull", lambda *a, **k: rows)
    monkeypatch.setattr(
        it, "_ages",
        lambda picks, key="tag": (lambda r: {"bridesmaid bag": "32d"}.get(
            r.get("tag"), fr.NEW)))
    return it


@pytest.mark.parametrize("fn_name,_pull_name", FEEDS)
def test_every_keyword_feed_carries_the_added_column(feed, fn_name, _pull_name):
    out = getattr(feed, fn_name)(mode="pod")
    header = next((l for l in out.splitlines() if "| Added |" in l), None)
    assert header, f"{fn_name} has no Added column"
    # the separator row must gain a column too or the table renders broken
    lines = out.splitlines()
    i = lines.index(header)
    assert lines[i + 1].count("|") == header.count("|"), \
        f"{fn_name} header/separator column count disagree"


@pytest.mark.parametrize("fn_name,_pull_name", FEEDS)
def test_a_never_seen_keyword_reads_new_in_the_feed(feed, fn_name, _pull_name):
    out = getattr(feed, fn_name)(mode="pod")
    row = next(l for l in out.splitlines()
               if l.startswith("| brand new tote bag "))
    assert "| NEW |" in row, row
    known = next(l for l in out.splitlines()
                 if l.startswith("| bridesmaid bag "))
    assert "| 32d |" in known, known


@pytest.mark.parametrize("fn_name,_pull_name", FEEDS)
def test_the_live_ranking_fact_is_stated_once_not_per_row(feed, fn_name,
                                                          _pull_name):
    """'ranked' is not stored. Printing the render clock down a column would
    look like 40 measurements when it is one."""
    out = getattr(feed, fn_name)(mode="pod")
    assert out.count("Ranked live") == 1, f"{fn_name}: {out.count('Ranked live')}"


def test_newest_has_no_added_column_because_its_rows_are_not_our_keywords(
        monkeypatch):
    """Listings, not keywords. There is nothing in our base to have been added,
    so the honest stamp is when WE PULLED it — and Age already covers the row."""
    from src import interactive as it
    monkeypatch.setattr(it.mcp, "browse_new_listings",
                        lambda **k: [{"title": "Siren Mermaid Ornament",
                                      "primary_tag": "ornament", "tags": ["felt"],
                                      "price_usd": 34.0, "performance_score": 99.2,
                                      "sold_24h": 2, "conversion_rate": 0.151,
                                      "age_days": 30}])
    out = it.newest(mode="pod")
    assert "| Added |" not in out
    assert "Pulled live" in out and "how old the listing is on Etsy" in out


def test_the_build_queue_carries_the_column_too():
    from src import build_shortlist as bs
    html = bs.render_html(bs.analyze(), csrf="t", limit=3)
    assert "<th>Added</th>" in html


def test_the_build_queue_costs_one_lookup_for_the_whole_page(monkeypatch):
    """open rows AND the done drawer share a single lookup.

    Counts calls INTO freshness rather than raw sqlite3.connect calls —
    build_shortlist.analyze() opens its own connections, and counting those made
    this assertion pass or fail depending on what ran before it.
    """
    from src import build_shortlist as bs
    data = bs.analyze()                      # outside the count: not our cost
    calls = []
    real = fr.labels_for
    monkeypatch.setattr(fr, "labels_for",
                        lambda *a, **k: (calls.append(1), real(*a, **k))[1])
    bs.render_html(data, csrf="t", limit=40)
    assert len(calls) == 1, f"expected 1 freshness lookup, got {len(calls)}"


def test_no_frozen_imports():
    """Same freeze rule as feasibility_gate: new code adds no dependency on a
    frozen file."""
    import ast
    from pathlib import Path
    tree = ast.parse(Path("src/freshness.py").read_text(encoding="utf-8"))
    frozen = {"ranking_engine", "opportunity_score", "product_fit", "etsy_proof",
              "opportunity_inbox"}
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[-1] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported |= {a.name.split(".")[-1] for a in node.names}
            imported |= {(node.module or "").split(".")[-1]}
    assert not (imported & frozen), sorted(imported & frozen)
