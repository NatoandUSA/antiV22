"""The launch loop: a keyword must be able to reach PUBLISHED and leave the queue.

WHY THIS EXISTS
The tool found 792 buildable keywords and 0 were ever built. The bottleneck was
never discovery — it was that a keyword had no way to finish. `mark_done` existed
but only as a binary flag, so "we designed this" and "this is live on Etsy" were
the same state and no follow-up was ever scheduled.

PUBLISHED_MANUALLY is the ONLY way the system learns a listing went live. The
tool never publishes; the owner does it by hand and records the fact here.
"""
import csv
from datetime import date, timedelta

import pytest

from src import build_shortlist as bq

SPRINT = ["mens carry on bag", "mini bride tote bags", "embroidered sweatshirt"]


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(bq, "ACTIONED", tmp_path / "build_actioned.csv")
    return bq.ACTIONED


# --- the two end states -------------------------------------------------------
def test_a_keyword_can_be_marked_published_manually(ledger):
    assert bq.mark_done("mens carry on bag", "owner", status=bq.PUBLISHED)
    rec = bq.load_actioned()["mens carry on bag"]
    assert rec["status"] == bq.PUBLISHED


def test_done_and_published_are_different_states(ledger):
    bq.mark_done("a keyword", "owner", status=bq.DONE)
    bq.mark_done("b keyword", "owner", status=bq.PUBLISHED)
    got = bq.load_actioned()
    assert got["a keyword"]["status"] == bq.DONE
    assert got["b keyword"]["status"] == bq.PUBLISHED


def test_publishing_schedules_the_day3_and_day7_reviews(ledger):
    """Scheduled by the act of publishing, not by remembering."""
    bq.mark_done("mens carry on bag", "owner", status=bq.PUBLISHED)
    rec = bq.load_actioned()["mens carry on bag"]
    assert rec["check_day3"] == str(date.today() + timedelta(days=3))
    assert rec["check_day7"] == str(date.today() + timedelta(days=7))


def test_plain_done_schedules_no_review(ledger):
    """Nothing went live, so there is nothing to review."""
    bq.mark_done("shelved idea", "owner", status=bq.DONE)
    rec = bq.load_actioned()["shelved idea"]
    assert not rec["check_day3"] and not rec["check_day7"]


def test_an_unknown_status_falls_back_to_done_never_published(ledger):
    """A typo must never claim a listing is live on Etsy."""
    bq.mark_done("x keyword", "owner", status="LIVE")
    assert bq.load_actioned()["x keyword"]["status"] == bq.DONE


# --- backwards compatibility --------------------------------------------------
def test_rows_written_before_status_existed_still_load(ledger):
    """The ledger is append-only and predates these columns."""
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["keyword", "user", "ts"])
        w.writerow(["old keyword", "someone", "2026-07-01 10:00"])
    rec = bq.load_actioned()["old keyword"]
    assert rec["status"] == bq.DONE
    assert rec["check_day3"] == ""


def test_a_later_publish_supersedes_an_earlier_done(ledger):
    """Append-only ledger: the last write wins."""
    bq.mark_done("mens carry on bag", "owner", status=bq.DONE)
    bq.mark_done("mens carry on bag", "owner", status=bq.PUBLISHED)
    assert bq.load_actioned()["mens carry on bag"]["status"] == bq.PUBLISHED


# --- follow-ups ---------------------------------------------------------------
def test_follow_ups_lists_only_reviews_that_are_due(ledger):
    bq.mark_done("mens carry on bag", "owner", status=bq.PUBLISHED)
    assert bq.follow_ups() == []                       # nothing due today
    later = date.today() + timedelta(days=4)
    due = bq.follow_ups(today=later)
    assert [d for _k, d, _t in due] == [3]             # day 3 only
    later = date.today() + timedelta(days=8)
    assert [d for _k, d, _t in bq.follow_ups(today=later)] == [3, 7]


def test_follow_ups_ignores_keywords_that_were_never_published(ledger):
    bq.mark_done("shelved idea", "owner", status=bq.DONE)
    assert bq.follow_ups(today=date.today() + timedelta(days=30)) == []


# --- the queue ----------------------------------------------------------------
def test_a_published_keyword_leaves_the_active_build_queue(ledger, monkeypatch):
    """Acceptance: published/done keywords must not stay in Build Now."""
    data = bq.analyze()
    if not data["buildable"]:
        pytest.skip("no local master rows to build from")
    first = data["open"][0]["keyword"]
    bq.mark_done(first, "owner", status=bq.PUBLISHED)
    after = bq.analyze()
    assert first not in [p["keyword"] for p in after["open"]], "still in the queue"
    assert first in [p["keyword"] for p in after["done"]]


def test_the_done_row_shows_its_status_and_review_dates(ledger):
    data = bq.analyze()
    if not data["buildable"]:
        pytest.skip("no local master rows to build from")
    first = data["open"][0]["keyword"]
    bq.mark_done(first, "owner", status=bq.PUBLISHED)
    html = bq.render_html(bq.analyze(), csrf="t", limit=5)
    assert "published manually" in html
    assert "Post-launch review due" in html or "review:" in html


def test_the_queue_offers_both_actions_on_an_open_row(ledger):
    data = bq.analyze()
    if not data["buildable"]:
        pytest.skip("no local master rows to build from")
    html = bq.render_html(data, csrf="t", limit=3)
    assert "Published" in html and bq.PUBLISHED in html
    assert "/launch-kit?q=" in html, "no route into Launch Kit"


# --- the guardrail ------------------------------------------------------------
def test_nothing_here_publishes_to_etsy():
    """The owner publishes by hand. This module records that fact and no more."""
    from src.team_ops import PUBLISH_AUTOMATION
    assert PUBLISH_AUTOMATION is False
    src = open("src/build_shortlist.py", encoding="utf-8").read()
    for bad in ("requests.post", "etsy.com/v3", "oauth", "api_key"):
        assert bad not in src.lower(), f"build_shortlist references {bad}"
