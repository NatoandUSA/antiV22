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
