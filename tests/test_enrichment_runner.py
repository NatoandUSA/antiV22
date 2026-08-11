"""Enrichment drain: a bounded, ledger-recording wrapper around enrich.run().
enrich.run() (the real per-keyword work) is tested in test_enrich.py - these
tests isolate the wrapper's own job: computing queued_before/remaining_after,
passing bounds through, and persisting a run record that survives a failure.
"""
import json

import pytest

from src import enrichment_runner as er


@pytest.fixture(autouse=True)
def _isolated_ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(er, "LEDGER", tmp_path / "enrichment_runs.jsonl")


def _fake_queue(before, after):
    """oi.build_inbox fake: needs_enrichment reads `before` on the first call
    (queued_before) and `after` on every call thereafter (remaining_after)."""
    calls = {"n": 0}

    def _build_inbox(mode=None, limit=1):
        calls["n"] += 1
        n = before if calls["n"] == 1 else after
        return {"counts": {"needs_enrichment": n}}
    return _build_inbox


def test_a_successful_run_reports_before_after_and_no_error(monkeypatch):
    monkeypatch.setattr(er.oi, "build_inbox", _fake_queue(12, 5))
    monkeypatch.setattr(er.enrich, "run", lambda **k: {
        "targeted": 7, "attempted": 7, "enriched": 6, "filled": 20,
        "written": 7, "timed_out": 0, "stopped_early": None})
    evt = er.drain_enrichment()
    assert evt["queued_before"] == 12
    assert evt["remaining_after"] == 5
    assert evt["attempted"] == 7
    assert evt["enriched"] == 6
    assert evt["failed"] == 1
    assert evt["error_summary"] is None


def test_failed_counts_only_what_was_actually_attempted_not_the_full_slice(
        monkeypatch):
    """Regression: a run bounded by max_runtime_s can stop long before
    reaching the end of its requested slice. `failed` must be derived from
    attempted (what the loop actually reached), not targeted (the slice size)
    - otherwise every keyword never even tried gets misreported as failed.
    Reproduces the live burn-in reading ("failed": 124 on a run that only
    got partway through a 200-keyword slice before time ran out)."""
    monkeypatch.setattr(er.oi, "build_inbox", _fake_queue(628, 551))
    monkeypatch.setattr(er.enrich, "run", lambda **k: {
        "targeted": 200, "attempted": 82, "enriched": 76, "filled": 300,
        "written": 200, "timed_out": 1, "stopped_early": "max_runtime_s reached"})
    evt = er.drain_enrichment(limit=200, max_runtime_s=900)
    assert evt["targeted"] == 200
    assert evt["attempted"] == 82
    assert evt["failed"] == 6           # 82 attempted - 76 enriched, NOT 124
    assert evt["enriched"] == 76


def test_bounds_are_passed_through_to_enrich_run(monkeypatch):
    monkeypatch.setattr(er.oi, "build_inbox", _fake_queue(0, 0))
    seen = {}

    def _fake_run(**kwargs):
        seen.update(kwargs)
        return {"targeted": 0, "attempted": 0, "enriched": 0, "filled": 0,
               "written": 0, "timed_out": 0, "stopped_early": None}
    monkeypatch.setattr(er.enrich, "run", _fake_run)
    er.drain_enrichment("pod", limit=40, max_runtime_s=600)
    assert seen["mode"] == "pod"
    assert seen["limit"] == 40
    assert seen["max_runtime_s"] == 600


def test_a_run_that_stopped_early_surfaces_the_reason(monkeypatch):
    monkeypatch.setattr(er.oi, "build_inbox", _fake_queue(50, 44))
    monkeypatch.setattr(er.enrich, "run", lambda **k: {
        "targeted": 6, "attempted": 6, "enriched": 6, "filled": 12,
        "written": 6, "timed_out": 0, "stopped_early": "max_runtime_s reached"})
    evt = er.drain_enrichment()
    assert evt["error_summary"] == "max_runtime_s reached"


def test_never_raises_when_enrich_run_blows_up(monkeypatch):
    monkeypatch.setattr(er.oi, "build_inbox", _fake_queue(9, 9))

    def _boom(**k):
        raise RuntimeError("boom")
    monkeypatch.setattr(er.enrich, "run", _boom)
    evt = er.drain_enrichment()
    assert "boom" in evt["error_summary"]
    assert evt["queued_before"] == 9
    assert evt["remaining_after"] == 9


def test_a_run_persists_a_ledger_line(monkeypatch):
    monkeypatch.setattr(er.oi, "build_inbox", _fake_queue(3, 1))
    monkeypatch.setattr(er.enrich, "run", lambda **k: {
        "targeted": 2, "attempted": 2, "enriched": 2, "filled": 4,
        "written": 2, "timed_out": 0, "stopped_early": None})
    er.drain_enrichment()
    lines = er.LEDGER.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    last = json.loads(lines[-1])
    assert last["enriched"] == 2
    assert last["run_id"]


def test_last_run_returns_the_most_recent_record(monkeypatch):
    monkeypatch.setattr(er.oi, "build_inbox", _fake_queue(3, 1))
    monkeypatch.setattr(er.enrich, "run", lambda **k: {
        "targeted": 1, "attempted": 1, "enriched": 1, "filled": 1,
        "written": 1, "timed_out": 0, "stopped_early": None})
    first = er.drain_enrichment()
    second = er.drain_enrichment()
    assert er.last_run()["run_id"] == second["run_id"]
    assert second["run_id"] != first["run_id"]


def test_last_run_is_none_when_the_ledger_is_empty():
    assert er.last_run() is None


def test_last_run_can_filter_by_mode(monkeypatch):
    monkeypatch.setattr(er.oi, "build_inbox", _fake_queue(1, 0))
    monkeypatch.setattr(er.enrich, "run", lambda **k: {
        "targeted": 1, "attempted": 1, "enriched": 1, "filled": 1,
        "written": 1, "timed_out": 0, "stopped_early": None})
    er.drain_enrichment("embroidery")
    pod_run = er.drain_enrichment("pod")
    assert er.last_run("pod")["run_id"] == pod_run["run_id"]
