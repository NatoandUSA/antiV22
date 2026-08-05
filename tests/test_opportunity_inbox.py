"""Opportunity Inbox: field mapping, O de-bias, ledger reconciliation, WATCH rank."""
from src import opportunity_inbox as oi
from src import opportunity_score as osc


def test_to_scorer_maps_real_columns_and_no_gem_copy():
    row = {"keyword": "indoor decals", "etsy_listings": "43", "seller_count": "14",
           "views_24h": "51", "avg_price": "6.69", "avg_revenue": "20906.1",
           "conversion_rate": "0.0632", "momentum": "91.3",
           "source": "mcp:opportunity"}
    d, comp, views, rev, cr, mom = oi._to_scorer(row)
    assert d["tag"] == "indoor decals"
    assert comp == 43 and views == 51 and mom == 91.3
    # V30.1 O de-bias: momentum must NOT be copied into gem_score, and provenance
    # must NOT become is_hidden_gem (constant-85 inflation).
    assert "gem_score" not in d
    assert "is_hidden_gem" not in d
    assert d.get("source") == "mcp:opportunity"


def test_missing_o_does_not_cap_verdict():
    d, *_ = oi._to_scorer({"keyword": "personalized dinosaur birthday shirt",
                           "etsy_listings": "30", "views_24h": "88",
                           "avg_revenue": "99583", "conversion_rate": "0.041",
                           "momentum": "90", "source": "mcp:opportunity"})
    s = osc.score(d, keyword=d["tag"])
    assert s["sub_scores"]["opportunity_signal"] is None
    assert s["core_complete"] is True          # core = Market + Competition only
    assert s["verdict"] != "WATCH" or s["overall_score"] < 65


def test_vendor_opportunity_score_lights_up_the_o_leg():
    """V37.6: scout_opportunities returns its own opportunity_score, independent
    of momentum_score and competition_score. harvest used to discard it into the
    dedup field; now it reaches the O leg that V30.1 left as an honest null."""
    base = {"keyword": "bridal gift bags", "etsy_listings": "38",
            "avg_revenue": "1398", "conversion_rate": "0.043",
            "momentum": "47.4", "source": "mcp:opportunity"}
    d, *_ = oi._to_scorer(base)
    assert osc.score(d, keyword=d["tag"])["sub_scores"]["opportunity_signal"] is None
    d2, *_ = oi._to_scorer({**base, "opportunity_score": "92.6"})
    s2 = osc.score(d2, keyword=d2["tag"])
    assert s2["sub_scores"]["opportunity_signal"] == 92.6
    assert "opportunity_signal" not in s2["missing"]
    assert s2["evidence_weight"] > osc.score(d, keyword=d["tag"])["evidence_weight"]


def test_o_leg_is_never_fed_a_derived_score():
    """discovered_keywords.opportunity is discover.score() = log10(revenue) x
    conversion x momentum / listings - every input is already a leg here, so
    routing it into O would double-count all four and amplify them. Only an
    explicit vendor column may populate O."""
    d, *_ = oi._to_scorer({"keyword": "summer pouch", "etsy_listings": "34",
                           "avg_revenue": "5493", "conversion_rate": "0.0308",
                           "momentum": "60.6", "source": "mcp:trending"})
    assert "opportunity_score" not in d
    assert "gem_score" not in d
    assert osc.score(d, keyword=d["tag"])["sub_scores"]["opportunity_signal"] is None


def test_ledger_counts_reconcile():
    d = oi.build_inbox(limit=100000)
    c = d["counts"]
    assert (c["build"] + c["confirm"] + c["review"] + c["watch"]
            + c["skip"] + c["blocked"]) == c["total"]


def test_watch_rows_subranked_by_momentum_x_conversion():
    # V37.4 ordering: WATCH rows sort by (proof_tier, priority, launchable) FIRST,
    # then by the momentum x conversion sub-rank WITHIN each such group. A
    # launchable real product outranks a higher-watch_rank non-launchable theme by
    # design ("next 12 month" must not top "indoor decals"), so the sub-rank is
    # non-increasing per group, NOT globally across every WATCH row.
    from itertools import groupby
    d = oi.build_inbox(limit=100000)
    watch = [r for r in d["rows"] if r["action"] == "WATCH"]
    keyfn = lambda r: (r.get("proof_tier", 9), -r.get("priority", 0),
                       0 if r.get("launchable") else 1)
    for _key, grp in groupby(watch, key=keyfn):
        ranks = [r.get("watch_rank", 0) for r in grp]
        assert ranks == sorted(ranks, reverse=True), (_key, ranks[:10])


def test_enrichment_queue_covers_every_unscorable_row():
    """MEASURED: the queue was `source endswith '-lead' and no comp and no rev`,
    so it could only ever hold Pinterest/supplier lane leads. The live master has
    ZERO of those, so the queue was permanently empty and the one-click enrich
    button never rendered — while 843 rows scored None and the 838 from
    mcp:search / mcp:ranking had no route to enrichment anywhere in the app."""
    from src import opportunity_inbox as oi
    rows = [
        {"keyword": "scored row", "score": 71.0, "comp": 40, "rev": 900,
         "source": "mcp:trending"},
        {"keyword": "bare master row", "score": None, "comp": None, "rev": None,
         "source": "mcp:search"},
        {"keyword": "partial master row", "score": None, "comp": 300, "rev": None,
         "source": "mcp:ranking"},
        {"keyword": "lane lead", "score": None, "comp": None, "rev": None,
         "source": "pinterest-lead"},
    ]
    assert [r["keyword"] for r in rows if oi._needs_enrichment(r)] == [
        "bare master row", "partial master row", "lane lead"]
    assert not oi._needs_enrichment(rows[0])       # a scored row is left alone


def test_enrichment_queue_puts_lane_leads_first(monkeypatch):
    """Lane leads are the freshest human-sourced candidates; enriching them is
    what turns them into rankable rows. Partial-data rows come next."""
    from src import opportunity_inbox as oi
    rows = [
        {"keyword": "bare", "score": None, "comp": None, "rev": None,
         "source": "mcp:search"},
        {"keyword": "partial", "score": None, "comp": 300, "rev": None,
         "source": "mcp:ranking"},
        {"keyword": "lead", "score": None, "comp": None, "rev": None,
         "source": "supplier-lead"},
        {"keyword": "scored", "score": 80.0, "comp": 1, "rev": 1,
         "source": "mcp:trending"},
    ]
    monkeypatch.setattr(oi, "build_inbox", lambda *a, **k: {"rows": rows})
    assert oi.lead_keywords(limit=12) == ["lead", "partial", "bare"]


# --- sellability overlay: the "which confirm-first first?" answer -------------
def test_sellability_overlay_changes_no_verdict_action_or_score(monkeypatch):
    """Same hard guarantee the supplier badge carries: an overlay may add a
    column's worth of meaning, never move a row the frozen engine produced."""
    from src import opportunity_inbox as oi
    from src import longtail as lt

    def rank():
        oi._CACHE.clear()
        return [(r["keyword"], r["verdict"], r["action"], r["score"],
                 r["priority"]) for r in oi.build_inbox(None, limit=100000)["rows"]]

    with_overlay = rank()
    monkeypatch.setattr(lt, "sellability", lambda *a, **k: None)   # overlay off
    without = rank()
    oi._CACHE.clear()
    assert with_overlay == without


def test_sellability_rides_in_the_action_cell_not_an_11th_column():
    """The supplier badge set the rule: same question, no 11th column."""
    from src import interactive as ia
    hdr = ia._INBOX_HDR[0]
    assert hdr.count("|") == 11                    # 10 columns, unchanged
    row = ia._inbox_row(1, {
        "keyword": "custom shirt logo", "action": "CONFIRM_FIRST",
        "verdict": "CONDITIONAL", "score": 70.0, "fit_label": "POD product",
        "sell": 83.5, "sell_verdict": "PUSH", "proof_tier": 9, "proof": None,
        "comp": 34, "conv": 0.053, "momentum": 40, "route": "analyze",
        "action_reason": "", "evidence": "", "sub_scores": {}, "rationale": [],
    })
    assert row.count("|") == 11                    # still 10 columns
    assert "\U0001F4B0 83.5 PUSH" in row


def test_seller_count_reaches_the_lane_so_the_concentration_penalty_can_fire():
    """seller_count was read for the evidence line and thrown away, so
    longtail._room()'s '3+ listings per seller' penalty read row['sellers'],
    which no row carried — a designed signal with no path to its consumer."""
    from src import longtail as lt
    open_market = {"keyword": "a b c", "launchable": True, "action": "WATCH",
                   "conv": 0.05, "comp": 30.0, "rev": 400.0, "rev_total": None,
                   "source": "mcp:trending", "sellers": 25.0}
    concentrated = dict(open_market, sellers=2.0)   # 15 listings per seller
    a = lt.sellability(open_market)
    b = lt.sellability(concentrated)
    assert a and b
    assert b["score"] < a["score"], "a market a few shops own must score lower"


# --- trend map: read the history that was already on disk ---------------------
def test_trend_map_reads_the_write_only_history_table(tmp_path, monkeypatch):
    """`discovered_keywords` had been append-only since 2026-07-05 with no reader
    anywhere — 11,680 rows, momentum on 9,795 — while _trend_map read only a CSV
    that an MCP-harvesting shop never writes, so the trend column was blank."""
    monkeypatch.chdir(tmp_path)
    from src import db
    conn = db.get_conn()
    conn.executemany(
        "INSERT INTO discovered_keywords (captured_at, source, tag, momentum) "
        "VALUES (?,?,?,?)",
        [("2026-07-05 01:00:00", "harvest", "rising kw", 40.0),
         ("2026-08-02 01:00:00", "harvest", "rising kw", 88.0),
         ("2026-07-05 01:00:00", "harvest", "fading kw", 80.0),
         ("2026-08-02 01:00:00", "harvest", "fading kw", 40.0),
         ("2026-07-05 01:00:00", "harvest", "flat kw", 50.0),
         ("2026-08-02 01:00:00", "harvest", "flat kw", 52.0),
         ("2026-08-02 01:00:00", "harvest", "one reading", 60.0)])
    conn.commit()
    conn.close()
    from src import opportunity_inbox as oi
    tm = oi._trend_map()
    assert tm["rising kw"][0] == "\u2197"
    assert tm["fading kw"][0] == "\u2198"
    assert tm["flat kw"][0] == "\u2192"
    assert "one reading" not in tm        # a single observation is not a trend


def test_trend_compares_oldest_to_newest_not_the_last_two(tmp_path, monkeypatch):
    """MEASURED on the live history: consecutive days give 30 rising, ZERO
    fading, 513 stable, median delta 0.00 — momentum barely moves day to day and
    the same value is re-recorded many times daily, so a last-two read calls
    ~95% of keywords 'stable'. Across the month: 31 rising, 38 fading."""
    monkeypatch.chdir(tmp_path)
    from src import db
    conn = db.get_conn()
    # climbs all month, then flat for the final two days
    conn.executemany(
        "INSERT INTO discovered_keywords (captured_at, source, tag, momentum) "
        "VALUES (?,?,?,?)",
        [("2026-07-05 01:00:00", "harvest", "slow climber", 30.0),
         ("2026-08-01 01:00:00", "harvest", "slow climber", 79.0),
         ("2026-08-02 01:00:00", "harvest", "slow climber", 80.0)])
    conn.commit()
    conn.close()
    from src import opportunity_inbox as oi
    arrow, detail = oi._trend_map()["slow climber"]
    assert arrow == "\u2197", "a month-long climb must not read as 'stable'"
    assert "30" in detail and "80" in detail


def test_trend_map_survives_a_missing_database(tmp_path, monkeypatch):
    """History is a bonus signal; its absence must never break the Inbox."""
    monkeypatch.chdir(tmp_path)
    from src import opportunity_inbox as oi
    assert oi._trend_map() == {}
