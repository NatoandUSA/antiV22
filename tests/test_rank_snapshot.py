"""rank_snapshot: the one place a rank fact gets stored between runs. The
critical guarantee this file tests: a snapshot must never invent history -
no prior state means no event, not a promotion from nowhere.
"""
import json

import pytest

from src import rank_snapshot as rs


@pytest.fixture(autouse=True)
def _isolated_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(rs, "STATE", tmp_path / "rank_state.json")
    monkeypatch.setattr(rs, "EVENTS", tmp_path / "rank_events.jsonl")


def _rows(*items):
    """items: (keyword, action, priority, verdict, score) tuples."""
    return [{"keyword": kw, "action": a, "priority": p, "verdict": v,
            "score": s} for kw, a, p, v, s in items]


def _fake_build_inbox(pod_rows, emb_rows=None):
    """Defaults embroidery to EMPTY, not a copy of pod_rows - a test that only
    passes one row set is testing one mode, not asserting the two modes
    coincidentally share data."""
    emb_rows = [] if emb_rows is None else emb_rows

    def _build_inbox(mode=None, limit=100000):
        return {"rows": pod_rows if mode == "pod" else emb_rows}
    return _build_inbox


def test_the_first_snapshot_ever_creates_state_but_zero_events(monkeypatch):
    monkeypatch.setattr(rs.oi, "build_inbox", _fake_build_inbox(
        _rows(("nurse shirt", "WATCH", 2, "REVIEW", 40.0))))
    summary = rs.snapshot()
    assert summary["pod"]["changed"] == 0
    assert summary["pod"]["promoted"] == 0
    assert not rs.EVENTS.is_file() or rs.EVENTS.read_text().strip() == ""
    state = json.loads(rs.STATE.read_text(encoding="utf-8"))
    assert state["modes"]["pod"]["nurse shirt"]["action"] == "WATCH"


def test_an_unchanged_second_snapshot_emits_no_event(monkeypatch):
    fake = _fake_build_inbox(_rows(("nurse shirt", "WATCH", 2, "REVIEW", 40.0)))
    monkeypatch.setattr(rs.oi, "build_inbox", fake)
    rs.snapshot()
    summary = rs.snapshot()               # identical data again
    assert summary["pod"]["changed"] == 0
    assert not rs.EVENTS.is_file() or rs.EVENTS.read_text().strip() == ""


def test_watch_to_confirm_emits_exactly_one_promoted_event(monkeypatch):
    monkeypatch.setattr(rs.oi, "build_inbox", _fake_build_inbox(
        _rows(("nurse shirt", "WATCH", 2, "REVIEW", 40.0))))
    rs.snapshot()
    monkeypatch.setattr(rs.oi, "build_inbox", _fake_build_inbox(
        _rows(("nurse shirt", "CONFIRM_FIRST", 4, "CONDITIONAL", 62.0))))
    summary = rs.snapshot()
    assert summary["pod"]["changed"] == 1
    assert summary["pod"]["promoted"] == 1
    assert summary["pod"]["demoted"] == 0
    lines = rs.EVENTS.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    evt = json.loads(lines[0])
    assert evt["direction"] == "promoted"
    assert evt["old_action"] == "WATCH"
    assert evt["new_action"] == "CONFIRM_FIRST"
    assert evt["keyword"] == "nurse shirt"


def test_build_now_to_skip_emits_a_demoted_event(monkeypatch):
    monkeypatch.setattr(rs.oi, "build_inbox", _fake_build_inbox(
        _rows(("funny shirt", "BUILD_NOW", 5, "GO", 80.0))))
    rs.snapshot()
    monkeypatch.setattr(rs.oi, "build_inbox", _fake_build_inbox(
        _rows(("funny shirt", "SKIP", 1, "SKIP", 10.0))))
    summary = rs.snapshot()
    assert summary["pod"]["demoted"] == 1
    assert summary["pod"]["promoted"] == 0
    evt = json.loads(rs.EVENTS.read_text(encoding="utf-8").splitlines()[0])
    assert evt["direction"] == "demoted"


def test_a_brand_new_keyword_in_a_later_snapshot_is_a_baseline_not_an_event(
        monkeypatch):
    """A keyword that did not exist in the previous snapshot must not read as
    promoted-from-nothing - it has no 'old' to be promoted from."""
    monkeypatch.setattr(rs.oi, "build_inbox", _fake_build_inbox(
        _rows(("old kw", "WATCH", 2, "REVIEW", 40.0))))
    rs.snapshot()
    monkeypatch.setattr(rs.oi, "build_inbox", _fake_build_inbox(_rows(
        ("old kw", "WATCH", 2, "REVIEW", 40.0),
        ("brand new kw", "BUILD_NOW", 5, "GO", 90.0))))
    summary = rs.snapshot()
    assert summary["pod"]["changed"] == 0
    assert summary["pod"]["promoted"] == 0
    assert not rs.EVENTS.is_file() or rs.EVENTS.read_text().strip() == ""


def test_modes_are_tracked_independently(monkeypatch):
    monkeypatch.setattr(rs.oi, "build_inbox", _fake_build_inbox(
        pod_rows=_rows(("shared kw", "WATCH", 2, "REVIEW", 40.0)),
        emb_rows=_rows(("shared kw", "CONFIRM_FIRST", 4, "CONDITIONAL", 55.0))))
    rs.snapshot()
    state = json.loads(rs.STATE.read_text(encoding="utf-8"))
    assert state["modes"]["pod"]["shared kw"]["action"] == "WATCH"
    assert state["modes"]["embroidery"]["shared kw"]["action"] == "CONFIRM_FIRST"


def test_promoted_since_filters_by_time_and_mode(monkeypatch):
    monkeypatch.setattr(rs.oi, "build_inbox", _fake_build_inbox(
        _rows(("nurse shirt", "WATCH", 2, "REVIEW", 40.0))))
    rs.snapshot()
    monkeypatch.setattr(rs.oi, "build_inbox", _fake_build_inbox(
        _rows(("nurse shirt", "CONFIRM_FIRST", 4, "CONDITIONAL", 62.0))))
    import time
    t0 = time.time()
    rs.snapshot()
    assert len(rs.promoted_since(t0 - 1)) == 1
    assert len(rs.promoted_since(t0 + 3600)) == 0        # after the event
    assert len(rs.promoted_since(t0 - 1, mode="embroidery")) == 0


def test_promoted_since_dedupes_to_the_latest_event_per_keyword(monkeypatch):
    monkeypatch.setattr(rs.oi, "build_inbox", _fake_build_inbox(
        _rows(("kw", "WATCH", 2, "REVIEW", 40.0))))
    rs.snapshot()
    monkeypatch.setattr(rs.oi, "build_inbox", _fake_build_inbox(
        _rows(("kw", "CONFIRM_FIRST", 4, "CONDITIONAL", 55.0))))
    rs.snapshot()
    monkeypatch.setattr(rs.oi, "build_inbox", _fake_build_inbox(
        _rows(("kw", "BUILD_NOW", 5, "GO", 80.0))))
    rs.snapshot()
    import time
    events = rs.promoted_since(time.time() - 3600)
    assert len(events) == 1
    assert events[0]["new_action"] == "BUILD_NOW"


def test_a_snapshot_failure_on_one_mode_never_raises(monkeypatch):
    def _boom(mode=None, limit=100000):
        raise RuntimeError("scoring blew up")
    monkeypatch.setattr(rs.oi, "build_inbox", _boom)
    summary = rs.snapshot()               # must not raise
    assert summary == {}


def test_atomic_write_survives_an_interrupted_write(monkeypatch):
    """If the process dies mid-write, the temp file may be left behind or
    corrupt, but the real state file must still hold the last GOOD state."""
    monkeypatch.setattr(rs.oi, "build_inbox", _fake_build_inbox(
        _rows(("kw", "WATCH", 2, "REVIEW", 40.0))))
    rs.snapshot()
    good = rs.STATE.read_text(encoding="utf-8")

    real_dump = json.dump

    def _dump_then_die(data, fh, **kw):
        fh.write("{not even valid json")
        raise OSError("disk full (simulated)")
    monkeypatch.setattr(json, "dump", _dump_then_die)
    monkeypatch.setattr(rs.oi, "build_inbox", _fake_build_inbox(
        _rows(("kw", "BUILD_NOW", 5, "GO", 90.0))))
    with pytest.raises(OSError):
        rs.snapshot()
    monkeypatch.setattr(json, "dump", real_dump)
    assert rs.STATE.read_text(encoding="utf-8") == good


def test_last_snapshot_at_is_none_before_any_run():
    assert rs.last_snapshot_at() is None


def test_last_snapshot_at_reflects_the_most_recent_run(monkeypatch):
    monkeypatch.setattr(rs.oi, "build_inbox", _fake_build_inbox(
        _rows(("kw", "WATCH", 2, "REVIEW", 40.0))))
    import time
    t0 = time.time()
    rs.snapshot()
    assert rs.last_snapshot_at() >= t0
