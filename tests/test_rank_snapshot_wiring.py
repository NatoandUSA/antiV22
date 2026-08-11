"""rank_snapshot.snapshot() must fire from real rank runs (harvest, enrichment)
and NEVER from a dry harvest run (nothing was written, so there is no new
rank to snapshot) or from page rendering (not tested here - structurally
true because build_inbox() itself never imports or calls rank_snapshot)."""


def _fake_harvest_result(**over):
    base = {"scanned": 0, "new_total": 0, "new_emb": 0, "new_pod": 0,
           "emb_sample": [], "pod_sample": [], "wrote_data": 0}
    base.update(over)
    return base


def test_a_real_harvest_run_triggers_a_snapshot(monkeypatch):
    from src import harvest as hv
    calls = []
    monkeypatch.setattr(hv, "harvest", lambda **k: _fake_harvest_result())
    monkeypatch.setattr("src.rank_snapshot.snapshot",
                        lambda **k: calls.append(k))
    hv.run_harvest([])
    assert len(calls) == 1
    assert calls[0]["source"] == "harvest"


def test_a_dry_harvest_run_never_snapshots(monkeypatch):
    from src import harvest as hv
    calls = []
    monkeypatch.setattr(hv, "harvest", lambda **k: _fake_harvest_result())
    monkeypatch.setattr("src.rank_snapshot.snapshot",
                        lambda **k: calls.append(k))
    hv.run_harvest(["--dry"])
    assert calls == []


def test_a_harvest_run_survives_a_snapshot_that_raises(monkeypatch):
    """A snapshot bug must never take the harvest run down with it."""
    from src import harvest as hv
    monkeypatch.setattr(hv, "harvest", lambda **k: _fake_harvest_result())

    def _boom(**k):
        raise RuntimeError("snapshot exploded")
    monkeypatch.setattr("src.rank_snapshot.snapshot", _boom)
    hv.run_harvest([])                    # must not raise


def test_an_enrichment_drain_triggers_a_snapshot(monkeypatch):
    from src import enrichment_runner as er
    monkeypatch.setattr(er.oi, "build_inbox",
                        lambda *a, **k: {"counts": {"needs_enrichment": 0}})
    monkeypatch.setattr(er.enrich, "run", lambda **k: {
        "targeted": 1, "attempted": 1, "enriched": 1, "filled": 1,
        "written": 1, "timed_out": 0, "stopped_early": None})
    calls = []
    monkeypatch.setattr("src.rank_snapshot.snapshot",
                        lambda **k: calls.append(k))
    er.drain_enrichment()
    assert len(calls) == 1
    assert calls[0]["source"] == "enrich-drain"


def test_a_drain_survives_a_snapshot_that_raises(monkeypatch):
    from src import enrichment_runner as er
    monkeypatch.setattr(er.oi, "build_inbox",
                        lambda *a, **k: {"counts": {"needs_enrichment": 0}})
    monkeypatch.setattr(er.enrich, "run", lambda **k: {
        "targeted": 0, "attempted": 0, "enriched": 0, "filled": 0,
        "written": 0, "timed_out": 0, "stopped_early": None})

    def _boom(**k):
        raise RuntimeError("snapshot exploded")
    monkeypatch.setattr("src.rank_snapshot.snapshot", _boom)
    evt = er.drain_enrichment()           # must not raise
    assert evt["enriched"] == 0
