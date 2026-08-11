"""`py main.py enrich` — backfill the market data that leaves a row unscored.

Measured on the live master before this existed: 843 of 1,523 keywords carried no
overall score, because harvest's two biggest sources add a name (mcp:search) or a
listing count (mcp:ranking) and no demand fields. The one-click enrich was scoped
to capture-lane leads, of which there are zero, so nothing in the app could reach
them. A 14-keyword random sample enriched 14/14 and moved 2 to CONFIRM_FIRST and
4 to SKIP — the demotions clear the WATCH pile, which is worth as much as the
promotions.
"""
import csv
import time
from pathlib import Path

from src import enrich

HEADER = ["keyword", "etsy_listings", "seller_count", "views_24h", "avg_price",
          "avg_revenue", "total_revenue", "conversion_rate", "momentum",
          "niche_age_days", "tm_risk", "source", "collected_at"]


def _master(tmp_path, rows):
    p = tmp_path / "keyword_data.csv"
    with p.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=HEADER)
        w.writeheader()
        for r in rows:
            w.writerow({h: r.get(h, "") for h in HEADER})
    return p


def _read(p):
    with Path(p).open(encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def _rich(_d, _mode=None):
    """Stand-in for the live MCP top-up."""
    _d.update({"listing_count": 31.0, "seller_count": 24.0, "views_24h": 18.58,
               "avg_price": 19.9, "revenue": 2119.18, "niche_revenue": 65694.58,
               "avg_conversion_rate": 0.0507, "momentum_score": 41.86})
    return True


def test_enrich_fills_blanks_and_never_overwrites_a_real_value(tmp_path,
                                                               monkeypatch):
    p = _master(tmp_path, [
        {"keyword": "bare row", "source": "mcp:search"},
        {"keyword": "measured row", "etsy_listings": "900",
         "avg_revenue": "12.5", "source": "mcp:trending"},
    ])
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(enrich, "unscored", lambda _m=None: ["bare row",
                                                             "measured row"])
    monkeypatch.setattr("src.shortlister_integration._enrich_row", _rich)
    res = enrich.run(pause=0, log=lambda *_a: None)

    rows = {r["keyword"]: r for r in _read(p)}
    assert res["enriched"] == 2
    assert rows["bare row"]["etsy_listings"] == "31.0"
    assert rows["bare row"]["total_revenue"] == "65694.58"   # the niche TOTAL
    assert rows["bare row"]["avg_revenue"] == "2119.18"      # per-listing, apart
    # a value the master already measured is never replaced by the MCP's
    assert rows["measured row"]["etsy_listings"] == "900"
    assert rows["measured row"]["avg_revenue"] == "12.5"


def test_enrich_writes_no_zeros(tmp_path, monkeypatch):
    """The MCP answers an unknown keyword with zero counts. A 0 in a count column
    reads downstream as 'this niche has no competitors' — the most attractive
    market in the scorer. Unknown must stay blank."""
    p = _master(tmp_path, [{"keyword": "unknown kw", "source": "mcp:search"}])
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(enrich, "unscored", lambda _m=None: ["unknown kw"])

    def _zeros(d, _mode=None):
        d.update({"listing_count": 0.0, "seller_count": 0.0})
        return False
    monkeypatch.setattr("src.shortlister_integration._enrich_row", _zeros)
    enrich.run(pause=0, log=lambda *_a: None)
    row = _read(p)[0]
    assert row["etsy_listings"] == ""
    assert row["seller_count"] == ""


def test_enrich_preserves_every_row_and_column(tmp_path, monkeypatch):
    """It rewrites the master, so the one thing it must never do is lose data."""
    rows = [{"keyword": f"kw {i}", "source": "mcp:search",
             "collected_at": "2026-07-01"} for i in range(60)]
    p = _master(tmp_path, rows)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(enrich, "unscored", lambda _m=None: ["kw 0"])
    monkeypatch.setattr("src.shortlister_integration._enrich_row", _rich)
    enrich.run(pause=0, save_every=10, log=lambda *_a: None)

    out = _read(p)
    assert len(out) == 60
    assert [r["keyword"] for r in out] == [r["keyword"] for r in rows]
    assert all(r["collected_at"] == "2026-07-01" for r in out)
    # provenance is untouched — enrich adds measurements, it does not re-source
    assert all(r["source"] == "mcp:search" for r in out)
    assert Path(tmp_path / "keyword_data.bak.csv").is_file()   # backup written


def test_enrich_adds_the_canonical_column_it_needs(tmp_path, monkeypatch):
    """The live master drifted a column behind harvest.KDATA_FIELDS (no
    opportunity_score). Appending it is what lets the O leg ever carry a value."""
    p = _master(tmp_path, [{"keyword": "kw", "source": "mcp:search"}])
    assert "opportunity_score" not in _read(p)[0]
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(enrich, "unscored", lambda _m=None: ["kw"])

    def _opp(d, _mode=None):
        d["opportunity_score"] = 71.0
        return True
    monkeypatch.setattr("src.shortlister_integration._enrich_row", _opp)
    enrich.run(pause=0, log=lambda *_a: None)
    row = _read(p)[0]
    assert row["opportunity_score"] == "71.0"
    assert row["keyword"] == "kw"          # existing columns kept, order intact


def test_enrich_is_resumable_because_the_worklist_is_derived(tmp_path,
                                                             monkeypatch):
    """No cursor file to corrupt: the work list is 'rows the engine could not
    score', so a re-run naturally skips whatever the last run fixed."""
    from src import opportunity_inbox as oi
    scored = {"keyword": "done", "score": 71.0, "comp": 1, "rev": 1,
              "source": "mcp:trending"}
    unscored = {"keyword": "todo", "score": None, "comp": None, "rev": None,
                "source": "mcp:search"}
    monkeypatch.setattr(oi, "build_inbox",
                        lambda *a, **k: {"rows": [scored, unscored]})
    assert enrich.unscored() == ["todo"]


def test_cli_registers_enrich():
    import main
    assert "enrich" in main.COMMANDS
    assert "enrich" in main.LIVE_API_CMDS     # guarded when the MCP is down


def test_the_live_guard_probes_the_transport_the_command_actually_uses(
        monkeypatch, capsys):
    """YTrends is reachable over two independent transports: the legacy REST API
    (YTRENDS_COOKIE, which expires) and the MCP (YTRENDS_API_TOKEN). Measured on
    this machine: ytrends_client.probe() was False while the MCP answered
    "OK (14 tools)" — so guarding an MCP-backed command on the REST probe refuses
    to run a command that works perfectly."""
    import main
    monkeypatch.setattr("src.ytrends_client.probe", lambda: False)
    monkeypatch.setattr("src.ytrends_mcp.available", lambda: (True, "OK"))
    main._live_api_guard("enrich")             # must NOT exit
    # a REST-backed command still fails fast on the REST probe
    import pytest
    with pytest.raises(SystemExit):
        main._live_api_guard("expand")


def test_the_guard_still_stops_enrich_when_the_mcp_is_down(monkeypatch):
    import main
    import pytest
    monkeypatch.setattr("src.ytrends_mcp.available", lambda: (False, "no token"))
    with pytest.raises(SystemExit):
        main._live_api_guard("enrich")


# ---------------------------------------------------------------------------
# Timeout + bounded runtime: run() used to call _enrich_row with no timeout at
# all (a hang there was the same 2min+ failure save_candidates was patched
# against) and no way to bound total wall-clock time - both needed once this
# can be triggered from a web request or an unattended scheduler, not just a
# Ctrl-C-able manual PC session.
# ---------------------------------------------------------------------------
def test_a_hung_call_times_out_without_blocking_the_run(tmp_path, monkeypatch):
    _master(tmp_path, [{"keyword": "hangs forever", "source": "mcp:search"}])
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(enrich, "unscored", lambda _m=None: ["hangs forever"])

    def _hang(d, _mode=None):
        time.sleep(2)
        return True
    monkeypatch.setattr("src.shortlister_integration._enrich_row", _hang)
    t0 = time.time()
    res = enrich.run(pause=0, timeout_s=0.2, log=lambda *_a: None)
    elapsed = time.time() - t0
    assert elapsed < 1.5, f"run() waited on the hung call: {elapsed:.2f}s"
    assert res["timed_out"] == 1
    assert res["enriched"] == 0


def test_stops_after_two_consecutive_failures(tmp_path, monkeypatch):
    _master(tmp_path, [{"keyword": f"kw {i}", "source": "mcp:search"}
                       for i in range(3)])
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(enrich, "unscored",
                        lambda _m=None: [f"kw {i}" for i in range(3)])
    calls = []

    def _dead(d, _mode=None):
        calls.append(d["tag"])
        raise RuntimeError("MCP unreachable")
    monkeypatch.setattr("src.shortlister_integration._enrich_row", _dead)
    res = enrich.run(pause=0, log=lambda *_a: None)
    assert len(calls) == 2, calls          # breaker opens after the 2nd failure
    assert "2 consecutive failures" in res["stopped_early"]


def test_max_runtime_s_stops_before_the_whole_backlog(tmp_path, monkeypatch):
    _master(tmp_path, [{"keyword": f"kw {i}", "source": "mcp:search"}
                       for i in range(5)])
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(enrich, "unscored",
                        lambda _m=None: [f"kw {i}" for i in range(5)])
    calls = []

    def _slow(d, _mode=None):
        calls.append(d["tag"])
        time.sleep(0.3)
        return True
    monkeypatch.setattr("src.shortlister_integration._enrich_row", _slow)
    res = enrich.run(pause=0, max_runtime_s=0.5, log=lambda *_a: None)
    assert len(calls) < 5, "should have stopped before the whole backlog"
    assert res["stopped_early"] == "max_runtime_s reached"
    # "targeted" is the requested slice size (5); "attempted" must reflect
    # only what the loop actually reached before time ran out, matching the
    # real calls made - not the full slice (see enrichment_runner's
    # regression test for why this distinction matters for failed-counting).
    assert res["targeted"] == 5
    assert res["attempted"] == len(calls)
    assert res["attempted"] < 5


def test_cli_minutes_flag_sets_max_runtime_s_and_does_not_leak_into_limit(
        monkeypatch):
    """--minutes 10 must become max_runtime_s=600, and its value ("10") must
    not also be parsed as a positional limit on the next loop iteration."""
    import main
    from src import opportunity_inbox as oi
    monkeypatch.setattr(oi, "build_inbox",
                        lambda *a, **k: {"counts": {"needs_enrichment": 0}})
    seen = {}

    def _fake_run(**k):
        seen.update(k)
        return {"targeted": 0, "enriched": 0, "filled": 0, "written": 0,
               "timed_out": 0, "stopped_early": None}
    monkeypatch.setattr("src.enrich.run", _fake_run)
    main.cmd_enrich("enrich", ["--minutes", "10", "pod"])
    assert seen["max_runtime_s"] == 600
    assert seen["limit"] is None
    assert seen["mode"] == "pod"


def test_no_bound_behaves_exactly_as_before(tmp_path, monkeypatch):
    """max_runtime_s=None (the default) must not change the historical
    unbounded-manual-run behaviour."""
    _master(tmp_path, [{"keyword": "kw", "source": "mcp:search"}])
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(enrich, "unscored", lambda _m=None: ["kw"])
    monkeypatch.setattr("src.shortlister_integration._enrich_row", _rich)
    res = enrich.run(pause=0, log=lambda *_a: None)
    assert res["stopped_early"] is None
    assert res["enriched"] == 1
