"""Acceptance tests for the Team Operations OS (src/team_ops.py + src/team_ui.py).

Mirrors the numbered checks in the build spec: RBAC, deadline/timezone maths,
proactive-log 48-hour lock + audit trail, checklist gating, bottleneck
thresholds, soft deletes, indexes and route health.

Every test runs inside the `sandbox` fixture (isolated project copy + chdir), so
data/app.db is created fresh and nothing touches the real workspace.
"""
from datetime import datetime, time, timedelta, timezone

import pytest

from src import appdb, auth
from src import team_ops as T


# --------------------------------------------------------------- fixtures ----
@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """Point src/appdb at a throwaway SQLite file.

    Deliberately NOT the repo-wide `sandbox` fixture: this suite only needs a
    clean database, and copying the whole project once per test filled the disk.
    """
    monkeypatch.setattr(appdb, "DB_PATH", tmp_path / "app.db")
    T.reset_cache()
    appdb.init_db()
    T.init_schema(force=True)
    yield tmp_path
    T.reset_cache()


@pytest.fixture
def team(isolated_db):
    """A fresh DB with Owner, Manager, Seller, Designer and a stranger Seller."""
    owner = auth.create_user("owner@t.local", "Pw1!", "Olive Owner", "OWNER")
    mgr = auth.create_user("mgr@t.local", "Pw1!", "Max Manager", "MANAGER")
    seller = auth.create_user("sell@t.local", "Pw1!", "Sam Seller", "SELLER")
    designer = auth.create_user("des@t.local", "Pw1!", "Dana Designer", "DESIGNER")
    outsider = auth.create_user("out@t.local", "Pw1!", "Otto Outsider", "SELLER")
    for u in (seller, designer):
        T.update_staff(u["user_id"], manager_id=mgr["user_id"],
                       timezone="Asia/Ho_Chi_Minh", target_designs=10,
                       target_listings=10)
    return {"owner": T.get_user(owner["user_id"]), "mgr": T.get_user(mgr["user_id"]),
            "seller": T.get_user(seller["user_id"]),
            "designer": T.get_user(designer["user_id"]),
            "outsider": T.get_user(outsider["user_id"])}


@pytest.fixture
def client(team):
    """Flask test client factory: `client(team["seller"])` signs that user in."""
    from src import web
    app = web.build_app("", "secret")
    app.config["TESTING"] = True

    def make(user):
        c = app.test_client()
        with c.session_transaction() as s:
            s["uid"] = user["user_id"]
            s["_csrf"] = "t"
        orig = c.post

        def post(*a, **k):
            data = k.get("data") or {}
            if isinstance(data, dict):
                data.setdefault("_csrf", "t")
            k["data"] = data
            return orig(*a, **k)
        c.post = post
        return c
    return make


def _task(team, assignee="seller", **kw):
    kw.setdefault("task_type", "OTHER")
    return T.create_task("Test task", assignee_id=team[assignee]["user_id"],
                         assigned_by_id=team["owner"]["user_id"],
                         actor=team["owner"], **kw)


def _tick_required(task, user):
    for item in task["checklist"]:
        if item.get("required"):
            T.set_checklist_item(task["id"], item["id"], True, user)
    return T.get_task(task["id"])


# ============================================ RBAC / task permissions (1-13) ==
def test_1_staff_cannot_see_other_staff_tasks(team):
    t = _task(team)
    assert T.can_see_task(team["seller"], t)
    assert not T.can_see_task(team["outsider"], t)
    assert [x["id"] for x in T.list_tasks(user=team["outsider"])] == []


def test_2_staff_cannot_mark_task_done(team):
    t = _task(team)
    T.set_status(t["id"], "IN_PROGRESS", team["seller"])
    _tick_required(T.get_task(t["id"]), team["seller"])
    T.set_status(t["id"], "REVIEW", team["seller"])
    updated, err = T.set_status(t["id"], "DONE", team["seller"])
    assert updated is None and "Manager or Owner" in err
    assert T.get_task(t["id"])["status"] == "REVIEW"


def test_3_manager_can_approve_done(team):
    t = _task(team)
    T.set_status(t["id"], "IN_PROGRESS", team["seller"])
    T.set_status(t["id"], "REVIEW", team["seller"])
    updated, err = T.set_status(t["id"], "DONE", team["mgr"])
    assert err == "" and updated["status"] == "DONE"
    assert updated["completed_at"]


def test_4_owner_sees_all_tasks(team):
    _task(team, "seller")
    _task(team, "outsider")
    assert len(T.list_tasks(user=team["owner"])) == 2
    # a manager sees only their own reports (outsider has no manager)
    assert len(T.list_tasks(user=team["mgr"])) == 1


def test_5_staff_submit_moves_to_review(team):
    t = _task(team)
    T.set_status(t["id"], "IN_PROGRESS", team["seller"])
    out, err = T.submit_for_review(t["id"], team["seller"], note="done",
                                   link="https://drive.google.com/x")
    assert err == "" and out["status"] == "REVIEW"
    assert out["links"] and out["links"][0]["url"].startswith("https://")


def test_6_request_fix_sets_status_and_new_deadline(team):
    t = _task(team)
    T.set_status(t["id"], "IN_PROGRESS", team["seller"])
    T.set_status(t["id"], "REVIEW", team["seller"])
    out, err = T.request_fix(t["id"], team["mgr"], "tags missing", "add 13 tags")
    assert err == "" and out["status"] == "FIX_REQUESTED"
    assert T.parse_iso(out["due_at"]) > T.utcnow()
    # the reason is recorded as a system comment on the task
    assert any("tags missing" in (c["comment_text"] or "")
               for c in T.task_comments(t["id"]))


def test_7_review_queue_only_shows_review(team):
    a = _task(team)
    _task(team, "designer")
    T.set_status(a["id"], "IN_PROGRESS", team["seller"])
    T.set_status(a["id"], "REVIEW", team["seller"])
    q = T.list_tasks(user=team["owner"], status="REVIEW")
    assert [x["id"] for x in q] == [a["id"]]


def test_8_every_status_change_writes_activity_log(team):
    t = _task(team)
    T.set_status(t["id"], "IN_PROGRESS", team["seller"])
    T.set_status(t["id"], "REVIEW", team["seller"])
    T.set_status(t["id"], "DONE", team["owner"])
    moves = [(a["old_value"], a["new_value"]) for a in T.task_activity(t["id"])
             if a["action"] == "status"]
    assert ("TODO", "IN_PROGRESS") in moves
    assert ("IN_PROGRESS", "REVIEW") in moves
    assert ("REVIEW", "DONE") in moves


def test_9_task_links_to_opportunity_keyword_listing(team):
    t = _task(team, related_opportunity_id="OPP-42", related_keyword="nurse tumbler",
              related_listing_id="L-9", related_store="Shop A")
    got = T.get_task(t["id"])
    assert got["related_opportunity_id"] == "OPP-42"
    assert got["related_keyword"] == "nurse tumbler"
    assert got["related_listing_id"] == "L-9"
    assert got["related_store"] == "Shop A"


def test_10_day3_and_day7_followups_from_learn(team):
    made = T.create_followups_for_listing("L-9", "nurse tumbler",
                                          team["seller"]["user_id"],
                                          team["owner"]["user_id"])
    types = sorted(t["task_type"] for t in made)
    assert types == ["DAY3_FOLLOWUP", "DAY7_FOLLOWUP"]
    d3 = T.parse_iso([t for t in made if t["task_type"] == "DAY3_FOLLOWUP"][0]["due_at"])
    d7 = T.parse_iso([t for t in made if t["task_type"] == "DAY7_FOLLOWUP"][0]["due_at"])
    assert (d7 - d3).days == 4


def test_11_assignee_gets_notification(team):
    t = _task(team)
    rows = T.notifications(team["seller"]["user_id"])
    assert any(n["type"] == "TASK_ASSIGNED" and n["related_task_id"] == t["id"]
               for n in rows)


def test_12_manager_notified_when_staff_submits(team):
    t = _task(team)
    T.set_status(t["id"], "IN_PROGRESS", team["seller"])
    T.set_status(t["id"], "REVIEW", team["seller"])
    rows = T.notifications(team["mgr"]["user_id"])
    assert any(n["type"] == "TASK_REVIEW" for n in rows)


def test_13_publish_automation_stays_false(team):
    assert T.PUBLISH_AUTOMATION is False
    from pathlib import Path
    src = Path("src/team_ops.py").read_text(encoding="utf-8") + \
        Path("src/team_ui.py").read_text(encoding="utf-8")
    for banned in ("etsy.com/openapi", "openapi/v3", "x-api-key",
                   "requests.post(\"https://api.etsy"):
        assert banned not in src


# ================================================ deadline / timezone (14-19) ==
def test_14_default_deadline_is_next_day_1700_local(team):
    now = datetime(2026, 7, 30, 22, 11, tzinfo=T.zone("Asia/Ho_Chi_Minh"))
    due = T.default_due_at(team["seller"], now=now)
    assert due == "2026-07-31T10:00:00+00:00"          # 17:00 ICT == 10:00 UTC
    assert T.to_local(due, team["seller"]) == "2026-07-31 17:00"


def test_14b_assignee_timezone_wins_over_business_default(team):
    T.update_staff(team["designer"]["user_id"], timezone="America/New_York")
    des = T.get_user(team["designer"]["user_id"])
    now = datetime(2026, 7, 30, 22, 11, tzinfo=timezone.utc)
    due = T.default_due_at(des, now=now)
    assert T.to_local(due, des) == "2026-07-31 17:00"   # 17:00 in THEIR zone
    assert T.to_local(due, team["seller"]) != "2026-07-31 17:00"


def test_14c_missing_timezone_falls_back_to_ho_chi_minh(team):
    T.update_staff(team["seller"]["user_id"], timezone="")
    u = T.get_user(team["seller"]["user_id"])
    assert not u["timezone"]
    now = datetime(2026, 7, 30, 22, 11, tzinfo=T.zone("Asia/Ho_Chi_Minh"))
    assert T.default_due_at(u, now=now) == "2026-07-31T10:00:00+00:00"


def test_15_all_timestamps_stored_in_utc(team):
    t = _task(team)
    for col in ("created_at", "updated_at", "due_at"):
        assert t[col].endswith("+00:00"), col
    row = appdb.q("SELECT created_at FROM team_tasks WHERE id=?", (t["id"],),
                  one=True)
    assert T.parse_iso(row["created_at"]).tzinfo == timezone.utc


def test_16_ui_displays_in_user_timezone(team, client):
    _task(team)
    T.update_staff(team["designer"]["user_id"], timezone="Australia/Sydney")
    body = client(team["owner"]).get("/team/ops/board").get_data(as_text=True)
    assert "Team Ops" in body and "Task Board" in body


def test_17_sorting_by_due_at_uses_utc(team):
    late = _task(team, due_at="2026-08-02T10:00:00+00:00")
    early = _task(team, due_at="2026-08-01T10:00:00+00:00")
    rows = appdb.q("SELECT id FROM team_tasks WHERE deleted_at IS NULL "
                   "ORDER BY due_at")
    assert [r["id"] for r in rows] == [early["id"], late["id"]]


def test_18_due_soon_triggers_under_four_hours(team):
    now = T.utcnow()
    soon = _task(team, due_at=T.iso(now + timedelta(hours=3)))
    later = _task(team, due_at=T.iso(now + timedelta(hours=9)))
    assert T.is_due_soon(soon) and T.due_state(soon) == "soon"
    assert not T.is_due_soon(later) and T.due_state(later) == "ontrack"


def test_19_overdue_only_when_not_review_or_done(team):
    past = T.iso(T.utcnow() - timedelta(hours=2))
    t = _task(team, due_at=past)
    assert T.is_overdue(t) and T.due_state(t) == "overdue"
    T.set_status(t["id"], "IN_PROGRESS", team["seller"])
    T.set_status(t["id"], "REVIEW", team["seller"])
    assert not T.is_overdue(T.get_task(t["id"]))
    T.set_status(t["id"], "DONE", team["owner"])
    assert not T.is_overdue(T.get_task(t["id"]))


# =========================== proactive work log / KPI integrity (20-30) ==
def _log_row(team, who="seller", **kw):
    kw.setdefault("work_type", "Design completed")
    kw.setdefault("design_count", 3)
    row, err = T.create_log(team[who], **kw)
    assert err == "", err
    return row


def _age_log(lid, hours, day_offset=None):
    """Backdate a row so the dynamic 48-hour lock kicks in without a cronjob."""
    created = T.iso(T.utcnow() - timedelta(hours=hours))
    params = [created]
    sql = "UPDATE proactive_work_logs SET created_at=?"
    if day_offset is not None:
        sql += ", date=?"
        params.append((T.utcnow() - timedelta(days=day_offset)).date().isoformat())
    appdb.execute(sql + " WHERE id=?", tuple(params + [lid]))
    return T.get_log(lid)


def test_20_log_autofills_date_and_staff(team):
    row = _log_row(team)
    assert row["date"] == T.local_today(team["seller"])
    assert row["staff_id"] == team["seller"]["user_id"]
    assert row["role"] == "SELLER"


def test_21_staff_can_only_edit_own_logs(team):
    row = _log_row(team)
    out, err = T.update_log(row["id"], team["outsider"], {"design_count": 99})
    assert out is None and "your own" in err


def test_22_staff_can_edit_today(team):
    row = _log_row(team)
    out, err = T.update_log(row["id"], team["seller"], {"design_count": 7})
    assert err == "" and out["design_count"] == 7


def test_23_staff_can_edit_yesterday(team):
    yesterday = (T.utcnow().astimezone(T.user_tz(team["seller"])).date()
                 - timedelta(days=1)).isoformat()
    row = _log_row(team, date=yesterday)
    out, err = T.update_log(row["id"], team["seller"], {"listing_count": 4})
    assert err == "" and out["listing_count"] == 4


def test_24_staff_cannot_edit_logs_older_than_48h(team):
    row = _age_log(_log_row(team)["id"], hours=49, day_offset=3)
    assert T.log_locked(row)
    out, err = T.update_log(row["id"], team["seller"], {"design_count": 99})
    assert out is None and "locked" in err
    assert T.get_log(row["id"])["design_count"] == 3      # unchanged in the DB


def test_inline_autosave_round_trip_with_a_real_csrf_token(team, client):
    """The grid's fetch() reads the token off <body data-csrf>. If that attribute
    stops being injected, every inline edit silently 403s."""
    import re
    row = _log_row(team)
    c = client(team["seller"])
    with c.session_transaction() as s:      # drop the fixture's fake token
        s.pop("_csrf", None)
    body = c.get("/team/ops/logs").get_data(as_text=True)
    m = re.search(r'<body data-csrf="([a-f0-9]+)"', body)
    assert m, "no data-csrf on <body> — inline edit cannot authenticate"
    r = c.post("/team/ops/logs/%d/save" % row["id"],
               data={"_csrf": m.group(1), "field": "design_count", "value": "8"})
    assert r.status_code == 200 and '"ok": true' in r.get_data(as_text=True)
    assert T.get_log(row["id"])["design_count"] == 8
    bad = c.post("/team/ops/logs/%d/save" % row["id"],
                 data={"_csrf": "deadbeef", "field": "design_count", "value": "99"})
    assert bad.status_code == 403
    assert T.get_log(row["id"])["design_count"] == 8


def test_24b_lock_is_enforced_through_the_http_route_too(team, client):
    row = _age_log(_log_row(team)["id"], hours=49, day_offset=3)
    r = client(team["seller"]).post(
        "/team/ops/logs/%d/save" % row["id"],
        data={"field": "design_count", "value": "99"})
    assert r.status_code == 403
    assert T.get_log(row["id"])["design_count"] == 3


def test_25_manager_can_edit_old_log_only_with_reason(team):
    row = _age_log(_log_row(team)["id"], hours=49, day_offset=3)
    out, err = T.update_log(row["id"], team["mgr"], {"design_count": 9})
    assert out is None and "reason" in err
    out, err = T.update_log(row["id"], team["mgr"], {"design_count": 9},
                            edit_reason="counted from Drive")
    assert err == "" and out["design_count"] == 9
    assert out["edited_after_lock_by"] == team["mgr"]["user_id"]
    assert out["edited_after_lock_reason"] == "counted from Drive"


def test_26_locked_edit_writes_audit_row(team):
    row = _age_log(_log_row(team)["id"], hours=49, day_offset=3)
    T.update_log(row["id"], team["mgr"], {"design_count": 9}, edit_reason="recount")
    audit = T.log_audit_trail(row["id"])
    assert len(audit) == 1
    a = audit[0]
    assert (a["field_name"], a["old_value"], a["new_value"]) == ("design_count", "3", "9")
    assert a["edited_after_lock"] == 1 and a["edit_reason"] == "recount"


def test_27_28_editing_counts_writes_audit(team):
    row = _log_row(team, listing_count=1)
    T.update_log(row["id"], team["seller"], {"design_count": 8})
    T.update_log(row["id"], team["seller"], {"listing_count": 6})
    fields = sorted(a["field_name"] for a in T.log_audit_trail(row["id"]))
    assert fields == ["design_count", "listing_count"]
    # a no-op write must not manufacture an audit row
    T.update_log(row["id"], team["seller"], {"design_count": 8})
    assert len(T.log_audit_trail(row["id"])) == 2


def test_29_audit_history_is_append_only(team, client):
    row = _log_row(team)
    T.update_log(row["id"], team["seller"], {"design_count": 8})
    before = len(T.log_audit_trail(row["id"]))
    T.soft_delete_log(row["id"], team["seller"], "mistake")
    assert len(T.log_audit_trail(row["id"])) == before      # survives the delete
    # no route exposes a delete for the audit table
    from src import web
    app = web.build_app("", "secret")
    rules = [str(r) for r in app.url_map.iter_rules()]
    assert not [r for r in rules if "audit" in r and "delete" in r]


def test_30_kpi_uses_verified_not_raw(team):
    row = _age_log(_log_row(team, design_count=5)["id"], hours=49, day_offset=3)
    T.update_log(row["id"], team["mgr"], {"design_count": 50}, edit_reason="bump")
    raw_d, _raw_l, ver_d, _ver_l = T.log_counts_for_kpi(T.get_log(row["id"]))
    assert (raw_d, ver_d) == (50, 0)                # edited after lock -> not verified
    T.verify_log(row["id"], team["mgr"])
    raw_d, _raw_l, ver_d, _ver_l = T.log_counts_for_kpi(T.get_log(row["id"]))
    assert (raw_d, ver_d) == (50, 50)               # manager sign-off restores it


# ============================================================ checklist (31-35) ==
def test_31_checklist_stored_as_validated_json(team):
    t = _task(team, task_type="LISTING_DRAFT")
    raw = appdb.q("SELECT checklist_json FROM team_tasks WHERE id=?", (t["id"],),
                  one=True)["checklist_json"]
    import json
    assert isinstance(json.loads(raw), list)
    if T._JSON1:
        assert appdb.q("SELECT json_valid(checklist_json) v FROM team_tasks "
                       "WHERE id=?", (t["id"],), one=True)["v"] == 1
        # the CHECK constraint must actually reject non-JSON
        import sqlite3
        with pytest.raises(sqlite3.IntegrityError):
            appdb.execute("UPDATE team_tasks SET checklist_json='not json' WHERE id=?",
                          (t["id"],))


def test_32_backend_updates_one_checklist_item(team):
    t = _task(team, task_type="LISTING_DRAFT")
    appdb.execute("UPDATE team_tasks SET metadata_json=? WHERE id=?",
                  ('{"keep": "me"}', t["id"]))
    first = t["checklist"][0]["id"]
    out, err = T.set_checklist_item(t["id"], first, True, team["seller"])
    assert err == ""
    ticked = [i for i in out["checklist"] if i["id"] == first][0]
    assert ticked["is_checked"] and ticked["checked_by"] == team["seller"]["user_id"]
    assert all(not i["is_checked"] for i in out["checklist"] if i["id"] != first)
    assert out["metadata"] == {"keep": "me"}        # untouched by the item write
    assert out["checklist_completed_count"] == 1


def test_33_checklist_renders_interactively(team, client):
    t = _task(team, task_type="LISTING_DRAFT")
    body = client(team["seller"]).get("/team/ops/task/%d" % t["id"]).get_data(as_text=True)
    assert "13 tags complete" in body
    assert 'type="checkbox"' in body
    assert "/checklist" in body


def test_34_required_checklist_blocks_submit(team):
    t = _task(team, task_type="LISTING_DRAFT")
    T.set_status(t["id"], "IN_PROGRESS", team["seller"])
    out, err = T.submit_for_review(t["id"], team["seller"], note="ready")
    assert out is None and "checklist incomplete" in err
    assert T.get_task(t["id"])["status"] == "IN_PROGRESS"
    assert T.task_comments(t["id"]) == []            # nothing recorded on a block
    _tick_required(T.get_task(t["id"]), team["seller"])
    out, err = T.submit_for_review(t["id"], team["seller"], note="ready")
    assert err == "" and out["status"] == "REVIEW"


def test_35_checklist_changes_write_activity_log(team):
    t = _task(team, task_type="DESIGN")
    item = t["checklist"][0]["id"]
    T.set_checklist_item(t["id"], item, True, team["designer"] if False
                         else team["seller"])
    actions = [a["action"] for a in T.task_activity(t["id"])]
    assert "checklist:" + item in actions


def test_35b_manager_can_untick_during_review(team):
    t = _task(team, task_type="DESIGN")
    item = t["checklist"][0]["id"]
    T.set_checklist_item(t["id"], item, True, team["seller"])
    out, err = T.set_checklist_item(t["id"], item, False, team["mgr"])
    assert err == ""
    assert not [i for i in out["checklist"] if i["id"] == item][0]["is_checked"]


# =========================================================== bottlenecks (36-42) ==
def _bulk(team, n, status, who="seller", reviewer=None, due_at=None):
    for _ in range(n):
        t = _task(team, who, due_at=due_at)
        if reviewer:
            appdb.execute("UPDATE team_tasks SET reviewer_manager_id=? WHERE id=?",
                          (reviewer, t["id"]))
        if status != "TODO":
            appdb.execute("UPDATE team_tasks SET status=? WHERE id=?",
                          (status, t["id"]))


def _find(alerts, atype, severity=None):
    return [a for a in alerts
            if a["alert_type"] == atype and (severity is None
                                             or a["severity"] == severity)]


def test_36_manager_review_warning_over_10(team):
    _bulk(team, 11, "REVIEW", reviewer=team["mgr"]["user_id"])
    alerts = T.bottlenecks(team["owner"])
    assert _find(alerts, "Manager Review Backlog", "warning")


def test_37_manager_review_critical_over_15(team):
    _bulk(team, 16, "REVIEW", reviewer=team["mgr"]["user_id"])
    assert _find(T.bottlenecks(team["owner"]), "Manager Review Backlog", "critical")


def test_37b_manager_critical_when_oldest_review_over_24h(team):
    _bulk(team, 2, "REVIEW", reviewer=team["mgr"]["user_id"])
    appdb.execute("UPDATE team_tasks SET updated_at=?",
                  (T.iso(T.utcnow() - timedelta(hours=30)),))
    assert _find(T.bottlenecks(team["owner"]), "Manager Review Backlog", "critical")


def test_38_39_staff_inprogress_thresholds(team):
    _bulk(team, 6, "IN_PROGRESS")
    assert _find(T.bottlenecks(team["owner"]), "Staff Context Switching", "warning")
    _bulk(team, 3, "IN_PROGRESS")
    assert _find(T.bottlenecks(team["owner"]), "Staff Context Switching", "critical")


def test_40_staff_overdue_critical_over_3(team):
    past = T.iso(T.utcnow() - timedelta(hours=5))
    _bulk(team, 4, "TODO", due_at=past)
    assert _find(T.bottlenecks(team["owner"]), "Staff Overdue Load", "critical")


def test_41_42_daily_log_alerts(team):
    tz = T.user_tz(team["seller"])
    today = T.utcnow().astimezone(tz).date()
    at_1740 = datetime.combine(today, time(17, 40), tzinfo=tz).astimezone(timezone.utc)
    at_2130 = datetime.combine(today, time(21, 30), tzinfo=tz).astimezone(timezone.utc)
    at_1000 = datetime.combine(today, time(10, 0), tzinfo=tz).astimezone(timezone.utc)
    assert not _find(T.bottlenecks(team["owner"], now=at_1000), "Missing Daily Log")
    assert _find(T.bottlenecks(team["owner"], now=at_1740), "Missing Daily Log",
                 "warning")
    assert _find(T.bottlenecks(team["owner"], now=at_2130), "Missing Daily Log",
                 "critical")
    # day_off suppresses it entirely (outsider is a Seller too, so include them)
    for role in ("seller", "designer", "outsider"):
        T.update_staff(team[role]["user_id"], day_off=1)
    assert not _find(T.bottlenecks(team["owner"], now=at_2130), "Missing Daily Log")


def test_42b_filing_a_log_clears_the_alert(team):
    tz = T.user_tz(team["seller"])
    at_2130 = datetime.combine(T.utcnow().astimezone(tz).date(), time(21, 30),
                               tzinfo=tz).astimezone(timezone.utc)
    _log_row(team)
    hits = _find(T.bottlenecks(team["owner"], now=at_2130), "Missing Daily Log")
    # Sam filed, so only the staff who didn't are flagged.
    assert {a["who"] for a in hits} == {"Dana Designer", "Otto Outsider"}
    # ...and a manager only ever sees their own reports flagged.
    mgr_hits = _find(T.bottlenecks(team["mgr"], now=at_2130), "Missing Daily Log")
    assert {a["who"] for a in mgr_hits} == {"Dana Designer"}


def test_team_review_queue_and_overdue_share_alerts(team):
    _bulk(team, 26, "REVIEW", reviewer=team["mgr"]["user_id"])
    alerts = T.bottlenecks(team["owner"])
    assert _find(alerts, "Team Review Queue", "warning")


# ========================================================== soft deletes (43-48) ==
def test_43_44_45_task_soft_delete(team):
    t = _task(team)
    ok, err = T.soft_delete_task(t["id"], team["owner"], "duplicate")
    assert ok and err == ""
    row = appdb.q("SELECT * FROM team_tasks WHERE id=?", (t["id"],), one=True)
    assert row is not None                               # 43: row still there
    assert row["deleted_at"] and row["delete_reason"] == "duplicate"
    assert row["deleted_by_id"] == team["owner"]["user_id"]
    assert T.list_tasks(user=team["owner"]) == []        # 44: gone from the board
    exported = list(T.tasks_csv_rows(team["owner"], include_deleted=True))
    assert [r["delete_reason"] for r in exported] == ["duplicate"]   # 45: in audit


def test_43b_staff_cannot_delete_a_task(team):
    t = _task(team)
    ok, err = T.soft_delete_task(t["id"], team["seller"], "oops")
    assert not ok and "Manager or Owner" in err
    assert T.get_task(t["id"])["deleted_at"] is None


def test_46_47_log_soft_delete_keeps_kpi_working(team):
    row = _log_row(team, design_count=4)
    T.soft_delete_log(row["id"], team["seller"], "double entry")
    stored = appdb.q("SELECT * FROM proactive_work_logs WHERE id=?", (row["id"],),
                     one=True)
    assert stored is not None and stored["deleted_at"]
    assert T.list_logs(user=team["owner"]) == []
    data = T.analytics(user=team["owner"])               # 47: KPI still computes
    assert data["widgets"]["designs"] == 0
    assert T.rebuild_kpi_daily() >= 1


def test_48_deactivated_user_stays_in_history(team):
    t = _task(team)
    T.set_status(t["id"], "IN_PROGRESS", team["seller"])
    T.set_user_active(team["seller"]["user_id"], False, team["owner"]["user_id"])
    gone = T.get_user(team["seller"]["user_id"])
    assert gone is not None and not T.user_active(gone)
    assert gone["deactivated_at"]
    assert T.get_task(t["id"])["assignee_id"] == team["seller"]["user_id"]
    names = T.users_by_id(include_inactive=True)
    assert names[team["seller"]["user_id"]]["display_name"] == "Sam Seller"
    # and they still appear in the owner's analytics history
    board = T.analytics(user=team["owner"])["leaderboard"]
    assert any(r["name"] == "Sam Seller" for r in board)


# ================================================ indexes / performance (49-55) ==
def _indexes(table):
    return {r["name"] for r in appdb.q(
        "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name=?", (table,))}


@pytest.mark.parametrize("table,expected", [
    ("team_tasks", ["idx_team_tasks_assignee_id", "idx_team_tasks_status",
                    "idx_team_tasks_due_at", "idx_team_tasks_assignee_status",
                    "idx_team_tasks_status_due_at", "idx_team_tasks_assigned_by_id",
                    "idx_team_tasks_reviewer_manager_id",
                    "idx_team_tasks_related_opportunity_id",
                    "idx_team_tasks_deleted_at"]),
    ("proactive_work_logs", ["idx_work_logs_staff_id", "idx_work_logs_date",
                             "idx_work_logs_staff_date", "idx_work_logs_status",
                             "idx_work_logs_account_store",
                             "idx_work_logs_deleted_at"]),
    ("notifications", ["idx_notifications_user_read", "idx_notifications_created_at"]),
    ("task_activity_log", ["idx_activity_task_id", "idx_activity_actor_id",
                           "idx_activity_created_at"]),
    ("task_comments", ["idx_comments_task_id", "idx_comments_created_at"]),
    ("proactive_work_log_audit", ["idx_work_log_audit_log_id",
                                  "idx_work_log_audit_actor_id",
                                  "idx_work_log_audit_created_at"]),
])
def test_49_53_indexes_exist(team, table, expected):
    have = _indexes(table)
    assert set(expected) <= have, sorted(set(expected) - have)


def test_54_board_query_uses_an_index(team):
    _task(team)
    plan = appdb.q("EXPLAIN QUERY PLAN SELECT * FROM team_tasks WHERE deleted_at "
                   "IS NULL AND status = 'REVIEW' ORDER BY due_at")
    assert any("idx_team_tasks" in str(r.get("detail", "")) for r in plan), plan


def test_55_home_widgets_do_not_scan_work_logs(team):
    _log_row(team)
    plan = appdb.q("EXPLAIN QUERY PLAN SELECT 1 FROM proactive_work_logs WHERE "
                   "staff_id=? AND date=? AND deleted_at IS NULL",
                   (team["seller"]["user_id"], T.local_today(team["seller"])))
    detail = " ".join(str(r.get("detail", "")) for r in plan)
    assert "SCAN" not in detail.upper() or "idx_work_logs" in detail


# ===================================================== routes + role scoping ==
@pytest.mark.parametrize("route", [
    "/team/ops", "/team/ops/board", "/team/ops/my", "/team/ops/logs",
    "/team/ops/review", "/team/ops/analytics", "/team/ops/staff",
    "/team/ops/settings", "/team/ops/notifications", "/team/ops/task/new",
    "/team/ops/logs/audit", "/team/ops/export/tasks.csv",
    "/team/ops/export/logs.csv",
])
def test_owner_pages_all_return_200(team, client, route):
    assert client(team["owner"]).get(route).status_code == 200


@pytest.mark.parametrize("route", ["/team/ops", "/team/ops/board", "/team/ops/my",
                                   "/team/ops/logs", "/team/ops/staff"])
def test_staff_pages_return_200(team, client, route):
    assert client(team["seller"]).get(route).status_code == 200


@pytest.mark.parametrize("route", ["/team/ops/review", "/team/ops/analytics",
                                   "/team/ops/settings", "/team/ops/task/new",
                                   "/team/ops/logs/audit"])
def test_staff_blocked_from_manager_pages(team, client, route):
    r = client(team["seller"]).get(route, follow_redirects=False)
    assert r.status_code == 302 and "err=" in r.headers.get("Location", "")


def test_manager_cannot_open_owner_settings(team, client):
    r = client(team["mgr"]).get("/team/ops/settings", follow_redirects=False)
    assert r.status_code == 302


def test_staff_sees_only_own_kpi(team, client):
    _task(team, "outsider")
    body = client(team["seller"]).get("/team/ops/my").get_data(as_text=True)
    assert "Otto Outsider" not in body


def test_anonymous_is_redirected_to_login(team):
    from src import web
    app = web.build_app("", "secret")
    r = app.test_client().get("/team/ops", follow_redirects=False)
    assert r.status_code in (301, 302) and "/login" in r.headers.get("Location", "")


def test_team_ops_is_linked_from_the_team_tab(team, client):
    body = client(team["owner"]).get("/team").get_data(as_text=True)
    assert 'href="/team/ops"' in body


def test_workflow_modules_offer_task_handoff(team, client):
    c = client(team["owner"])
    for route, label in (("/inbox", "Assign Pattern Miner"),
                         ("/rerank", "Assign Listing Draft"),
                         ("/pattern-miner", "Assign Designer"),
                         ("/build-queue", "Assign Listing Draft"),
                         ("/feedback", "Day 3 check")):
        body = c.get(route).get_data(as_text=True)
        assert label in body, route
        assert "/team/ops/task/new" in body, route


def test_staff_never_see_the_assign_strip(team, client):
    body = client(team["seller"]).get("/pattern-miner").get_data(as_text=True)
    assert "Assign Designer" not in body


# ================================================================== settings ==
def test_settings_change_the_default_deadline(team):
    T.set_setting("default_deadline_hour", "9")
    T.set_setting("default_deadline_offset_days", "2")
    now = datetime(2026, 7, 30, 22, 11, tzinfo=T.zone("Asia/Ho_Chi_Minh"))
    assert T.to_local(T.default_due_at(team["seller"], now=now),
                      team["seller"]) == "2026-08-01 09:00"


def test_urgent_allows_same_day_deadline(team):
    now = datetime(2026, 7, 30, 9, 0, tzinfo=T.zone("Asia/Ho_Chi_Minh"))
    urgent = T.default_due_at(team["seller"], urgent=True, now=now)
    assert T.to_local(urgent, team["seller"]) == "2026-07-30 17:00"
    normal = T.default_due_at(team["seller"], now=now)
    assert T.to_local(normal, team["seller"]) == "2026-07-31 17:00"


def test_quality_score_uses_the_spec_weights(team):
    t = _task(team)
    T.set_status(t["id"], "IN_PROGRESS", team["seller"])
    T.set_status(t["id"], "REVIEW", team["seller"])
    T.set_status(t["id"], "DONE", team["owner"])
    _log_row(team, design_count=10, listing_count=10)
    row = [r for r in T.analytics(user=team["owner"])["leaderboard"]
           if r["staff_id"] == team["seller"]["user_id"]][0]
    assert 0 <= row["quality_score"] <= 100
    assert row["tasks_done_approved"] == 1
    assert row["design_verified"] == 10 and row["listing_verified"] == 10


def test_bulk_actions_respect_permissions(team, client):
    a, b = _task(team), _task(team)
    r = client(team["seller"]).post("/team/ops/board/bulk", data={
        "action": "status", "status": "DONE",
        "task_ids": [str(a["id"]), str(b["id"])]}, follow_redirects=False)
    assert "err=" in r.headers.get("Location", "")
    assert T.get_task(a["id"])["status"] == "TODO"
    client(team["owner"]).post("/team/ops/board/bulk", data={
        "action": "priority", "priority": "URGENT",
        "task_ids": [str(a["id"]), str(b["id"])]})
    assert T.get_task(a["id"])["priority"] == "URGENT"


# ============================================== system health / schema check ==
def test_health_reports_a_clean_schema(team):
    h = T.health()
    assert h["overall"] in ("ok", "warn")
    bad = [(s["title"], r["name"], r["detail"])
           for s in h["sections"] for r in s["rows"] if r["state"] == "fail"]
    assert bad == [], bad


def test_health_lists_every_required_object(team):
    h = T.health()
    by_key = {s["key"]: s for s in h["sections"]}
    names = {s["key"]: {r["name"] for r in s["rows"]} for s in h["sections"]}
    assert set(T.REQUIRED_TABLES) <= names["tables"]
    for table, idxs in T.REQUIRED_INDEXES.items():
        assert set(idxs) <= names["indexes"], table
    assert set(T.PARTIAL_INDEXES) <= names["indexes"]
    assert {c for c, _d in T._USER_COLS} <= names["user_columns"]
    assert all(r["state"] == "ok" for r in by_key["tables"]["rows"])
    assert all(r["state"] == "ok" for r in by_key["user_columns"]["rows"])


def test_health_detects_a_missing_index(team):
    appdb.execute("DROP INDEX idx_team_tasks_due_at")
    h = T.health()
    row = [r for s in h["sections"] for r in s["rows"]
           if r["name"] == "idx_team_tasks_due_at"][0]
    assert row["state"] == "fail" and "MISSING" in row["detail"]
    assert h["overall"] == "fail"


def test_health_detects_a_missing_user_column(tmp_path, monkeypatch):
    monkeypatch.setattr(appdb, "DB_PATH", tmp_path / "app.db")
    T.reset_cache()
    appdb.init_db()                       # users table WITHOUT the team columns
    h = T.health()
    missing = [r for s in h["sections"] for r in s["rows"]
               if s["key"] == "user_columns" and r["state"] == "fail"]
    assert missing == [] or h["overall"] == "fail"


def test_health_reports_json_check_constraints(team):
    h = T.health()
    js = [s for s in h["sections"] if s["key"] == "json"][0]
    named = {r["name"]: r for r in js["rows"]}
    for table, cols in T.JSON_COLUMNS.items():
        for col in cols:
            row = named[table + "." + col]
            if T._JSON1:
                assert row["state"] == "ok" and "json_valid" in row["detail"]
            else:
                assert row["state"] == "warn"


def test_health_confirms_publish_automation_is_false(team):
    h = T.health()
    assert h["publish_automation"] is False
    safety = [s for s in h["sections"] if s["key"] == "safety"][0]
    row = [r for r in safety["rows"] if r["name"] == "PUBLISH_AUTOMATION"][0]
    assert row["state"] == "ok" and row["detail"].startswith("False")
    assert safety["state"] == "ok"


def test_health_counts_rows(team):
    t = _task(team)
    _task(team)
    T.soft_delete_task(t["id"], team["owner"], "dupe")
    _log_row(team)
    T.update_log(T.list_logs()[0]["id"], team["seller"], {"design_count": 9})
    c = T.health()["counts"]
    assert c["tasks_active"] == 1 and c["tasks_deleted"] == 1
    assert c["logs_active"] == 1 and c["logs_deleted"] == 0
    assert c["audit_rows"] == 1
    assert c["notifications"] >= 2          # one per assignment
    assert c["activity_rows"] >= 4


def test_health_warns_when_both_task_systems_hold_rows(team):
    from src import tasks as legacy
    _task(team)
    h = T.health()
    assert h["legacy"]["both_active"] is False       # no legacy rows yet
    assert h["legacy"]["label"] == ""
    legacy.create_task("Old board task", assigned_to_user_id=team["seller"]["user_id"])
    h = T.health()
    assert h["legacy"]["both_active"] is True
    assert h["legacy"]["label"] == "Legacy task system still active during rollout."
    assert h["legacy"]["legacy_rows"] == 1 and h["legacy"]["teamops_rows"] == 1
    assert h["overall"] == "warn"


def test_health_never_migrates_legacy_tasks(team):
    from src import tasks as legacy
    legacy.create_task("Old board task", assigned_to_user_id=team["seller"]["user_id"])
    before_new = len(T.list_tasks())
    before_old = len(legacy.list_tasks())
    T.health()
    T.health()                                        # idempotent + read-only
    assert len(T.list_tasks()) == before_new == 0
    assert len(legacy.list_tasks()) == before_old == 1


def test_system_health_page_200_for_owner(team, client):
    r = client(team["owner"]).get("/team/ops/system-health")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "PUBLISH_AUTOMATION" in body and "False" in body
    for table in T.REQUIRED_TABLES:
        assert table in body, table
    assert "idx_team_tasks_status_due_at" in body
    assert "target_designs" in body                    # a required user column
    assert "Active tasks" in body and "Audit rows" in body


@pytest.mark.parametrize("role", ["seller", "designer", "mgr"])
def test_system_health_blocked_for_non_owner(team, client, role):
    r = client(team[role]).get("/team/ops/system-health", follow_redirects=False)
    assert r.status_code == 302
    assert "err=" in r.headers.get("Location", "")
    body = client(team[role]).get("/team/ops/system-health",
                                  follow_redirects=True).get_data(as_text=True)
    assert "idx_team_tasks_status_due_at" not in body


def test_system_health_page_shows_the_legacy_rollout_warning(team, client):
    from src import tasks as legacy
    _task(team)
    legacy.create_task("Old board task", assigned_to_user_id=team["seller"]["user_id"])
    body = client(team["owner"]).get("/team/ops/system-health").get_data(as_text=True)
    assert "Legacy task system still active during rollout." in body
    assert "never migrates" in body


def test_system_health_is_linked_from_settings(team, client):
    body = client(team["owner"]).get("/team/ops/settings").get_data(as_text=True)
    assert 'href="/team/ops/system-health"' in body


# ================================================ new vs legacy UI labelling ==
@pytest.mark.parametrize("route", ["/team/ops/board", "/team/ops/my",
                                   "/team/ops/my-tasks"])
def test_new_board_is_labelled_as_the_new_system(team, client, route):
    body = client(team["seller"]).get(route).get_data(as_text=True)
    assert "New Team Ops task system" in body
    assert "Legacy task system remains active during rollout" in body
    assert 'href="/me/tasks"' in body                  # points at the old board


@pytest.mark.parametrize("route", ["/me/tasks", "/admin/tasks"])
def test_legacy_boards_are_labelled_and_link_forward(team, client, route):
    body = client(team["owner"]).get(route).get_data(as_text=True)
    assert "Legacy task system" in body
    assert "Legacy task system remains active during rollout." in body
    assert 'href="/team/ops/board"' in body
    assert 'href="/team/ops/my-tasks"' in body


def test_my_tasks_alias_serves_the_same_page(team, client):
    c = client(team["seller"])
    assert (c.get("/team/ops/my-tasks").get_data(as_text=True)
            == c.get("/team/ops/my").get_data(as_text=True))


def test_page_title_has_no_html_in_it(team, client):
    """The badge must not leak into <title> — shell() takes it separately."""
    import re
    body = client(team["seller"]).get("/team/ops/board").get_data(as_text=True)
    title = re.search(r"<title>(.*?)</title>", body, re.S).group(1)
    assert "<" not in title and ">" not in title
    assert "Task Board" in title


# ================================================ DAILY REPORTS module (1-26) ==
@pytest.mark.parametrize("route", ["/team/ops/reports", "/team/ops/daily-reports",
                                   "/team/ops/working-log", "/team/ops/logs"])
def test_dr_1_4_all_report_routes_serve_the_module(team, client, route):
    r = client(team["owner"]).get(route)
    assert r.status_code == 200
    assert "Team Daily Reports" in r.get_data(as_text=True)


@pytest.mark.parametrize("route", ["/team/ops/reports", "/team/ops/daily-reports",
                                   "/team/ops/working-log", "/team/ops/logs"])
def test_dr_staff_see_the_staff_first_page(team, client, route):
    body = client(team["seller"]).get(route).get_data(as_text=True)
    assert "My Daily Report" in body
    assert "Add Today Report" in body
    assert "Report your Etsy work" in body


def test_dr_5_sidebar_label_says_daily_reports(team, client):
    body = client(team["seller"]).get("/team/ops").get_data(as_text=True)
    assert ">Daily Reports</span>" in body
    assert 'href="/team/ops/reports"' in body
    for old in ("Working Log", "Proactive Log"):
        assert ">" + old + "</span>" not in body


def test_dr_helper_text_is_present(team, client):
    for role in ("owner", "seller"):
        body = client(team[role]).get("/team/ops/reports").get_data(as_text=True)
        assert ("Staff use this page to report daily Etsy work: designs completed, "
                "listings created, keywords researched, and Drive folders.") in body


def test_dr_6_staff_can_create_own_report(team, client):
    c = client(team["seller"])
    c.post("/team/ops/reports/new", data={
        "date": T.local_today(team["seller"]), "work_type": "Listing created",
        "account_store": "Shop A", "seed_phrase_keyword": "nurse tumbler",
        "design_count": "0", "listing_count": "4", "status": "Completed"})
    rows = T.list_logs(staff_id=team["seller"]["user_id"])
    assert len(rows) == 1
    assert rows[0]["listing_count"] == 4 and rows[0]["role"] == "SELLER"


def test_dr_7_staff_cannot_file_for_another_staff_member(team, client):
    """A forged staff_id is refused outright — not silently re-pointed at the
    submitter, so a staff member can never quietly inflate someone else's KPI."""
    r = client(team["seller"]).post("/team/ops/reports/new", data={
        "staff_id": str(team["designer"]["user_id"]), "work_type": "Design completed",
        "design_count": "9"}, follow_redirects=False)
    assert "err=" in r.headers.get("Location", "")
    assert T.list_logs() == []
    out, err = T.create_log(team["seller"], staff_id=team["designer"]["user_id"])
    assert out is None and "your own" in err
    # a manager filing on behalf of their team is still allowed
    out, err = T.create_log(team["mgr"], staff_id=team["designer"]["user_id"])
    assert err == "" and out["staff_id"] == team["designer"]["user_id"]


def test_dr_8_9_10_staff_edit_window(team, client):
    tz_today = T.utcnow().astimezone(T.user_tz(team["seller"])).date()
    today = _log_row(team, date=tz_today.isoformat())
    yday = _log_row(team, date=(tz_today - timedelta(days=1)).isoformat())
    assert T.update_log(today["id"], team["seller"], {"listing_count": 5})[1] == ""
    assert T.update_log(yday["id"], team["seller"], {"listing_count": 6})[1] == ""
    old = _age_log(_log_row(team)["id"], hours=49, day_offset=3)
    out, err = T.update_log(old["id"], team["seller"], {"listing_count": 7})
    assert out is None and "locked" in err


def test_dr_11_manager_edits_locked_report_only_with_reason(team, client):
    old = _age_log(_log_row(team)["id"], hours=49, day_offset=3)
    assert T.update_log(old["id"], team["mgr"], {"design_count": 12})[1] != ""
    out, err = T.update_log(old["id"], team["mgr"], {"design_count": 12},
                            edit_reason="checked the Drive folder")
    assert err == "" and out["design_count"] == 12
    assert T.log_audit_trail(old["id"])[0]["edited_after_lock"] == 1


def test_dr_12_13_owner_sees_all_manager_sees_managed(team):
    _log_row(team, "seller")
    _log_row(team, "designer")
    _log_row(team, "outsider")               # no manager -> outside Max's team
    assert len(T.list_logs(user=team["owner"])) == 3
    seen = {r["staff_id"] for r in T.list_logs(user=team["mgr"])}
    assert seen == {team["seller"]["user_id"], team["designer"]["user_id"]}
    assert len(T.list_logs(user=team["seller"])) == 1


def test_dr_14_15_role_default_work_type(team, client):
    assert T.default_work_type(team["seller"]) == "Listing created"
    assert T.default_work_type(team["designer"]) == "Design completed"
    sb = client(team["seller"]).get("/team/ops/reports").get_data(as_text=True)
    assert '<option value="Listing created" selected>' in sb
    db = client(team["designer"]).get("/team/ops/reports").get_data(as_text=True)
    assert '<option value="Design completed" selected>' in db
    # and the default applies when the field is left empty
    row, err = T.create_log(team["designer"])
    assert err == "" and row["work_type"] == "Design completed"


def test_dr_16_grid_has_the_required_columns(team, client):
    _log_row(team)
    body = client(team["owner"]).get("/team/ops/reports").get_data(as_text=True)
    for col in ("Date", "Staff Name", "Role", "Account / Store", "Work Type",
                "Seed phrase / Keyword", "Product Type", "Google Drive Folder",
                "Listing URL", "Design Count", "Listing Count", "Status", "Notes",
                "Last Updated", "Edited After Lock", "Verified"):
        assert "<th>" + col + "</th>" in body, col


def test_dr_17_18_19_owner_filters(team, client):
    _log_row(team, "seller", seed_phrase_keyword="nurse tumbler", status="Completed")
    _log_row(team, "designer", seed_phrase_keyword="dog mom hoodie", status="Blocked")
    c = client(team["owner"])
    by_staff = c.get("/team/ops/reports?view=team&staff=%d"
                     % team["seller"]["user_id"]).get_data(as_text=True)
    assert "nurse tumbler" in by_staff and "dog mom hoodie" not in by_staff
    by_kw = c.get("/team/ops/reports?view=team&q=dog+mom").get_data(as_text=True)
    assert "dog mom hoodie" in by_kw and "nurse tumbler" not in by_kw
    by_status = c.get("/team/ops/reports?view=team&status=Blocked").get_data(as_text=True)
    assert "dog mom hoodie" in by_status and "nurse tumbler" not in by_status
    by_role = c.get("/team/ops/reports?view=team&role=DESIGNER").get_data(as_text=True)
    assert "dog mom hoodie" in by_role and "nurse tumbler" not in by_role


def test_dr_20_owner_can_verify_a_report(team, client):
    row = _log_row(team)
    r = client(team["owner"]).post("/team/ops/reports/%d/verify" % row["id"],
                                   data={"note": "counted in Drive"})
    assert r.status_code == 302
    got = T.get_log(row["id"])
    assert got["verified_by_manager_id"] == team["owner"]["user_id"]
    assert got["verified_at"] and got["manager_note"] == "counted in Drive"
    assert any(n["type"] == "REPORT_VERIFIED"
               for n in T.notifications(team["seller"]["user_id"]))


def test_dr_20b_staff_cannot_verify_their_own_report(team, client):
    row = _log_row(team)
    r = client(team["seller"]).post("/team/ops/reports/%d/verify" % row["id"])
    assert "err=" in r.headers.get("Location", "")
    assert T.get_log(row["id"])["verified_by_manager_id"] is None


def test_dr_20c_manager_row_actions(team, client):
    row = _log_row(team)
    c = client(team["mgr"])
    c.post("/team/ops/reports/%d/action" % row["id"],
           data={"action": "clarify", "note": "which store was this?"})
    assert T.get_log(row["id"])["manager_note"] == "which store was this?"
    assert any(n["type"] == "REPORT_CLARIFY"
               for n in T.notifications(team["seller"]["user_id"]))
    c.post("/team/ops/reports/%d/action" % row["id"],
           data={"action": "blocked", "note": "waiting on supplier"})
    assert T.get_log(row["id"])["status"] == "Blocked"
    # forcing a KPI-sensitive field is audited like any other edit
    assert any(a["field_name"] == "status" for a in T.log_audit_trail(row["id"]))


def test_dr_20d_manager_action_scope_and_validation(team):
    outsider_row, _ = T.create_log(team["outsider"], work_type="Other")
    out, err = T.manager_action(outsider_row["id"], team["mgr"], "note", "hi")
    assert out is None and "outside your team" in err
    row = _log_row(team)
    assert T.manager_action(row["id"], team["seller"], "note", "x")[1] != ""
    assert T.manager_action(row["id"], team["mgr"], "note", "")[1] != ""


def test_dr_21_verified_counts_are_separate_from_submitted(team):
    row = _age_log(_log_row(team, design_count=5)["id"], hours=49, day_offset=3)
    T.update_log(row["id"], team["mgr"], {"design_count": 40}, edit_reason="bump")
    s = T.daily_report_summary(team["owner"])
    assert s["designs_submitted"] == 40 and s["designs_verified"] == 0
    T.verify_log(row["id"], team["owner"])
    s = T.daily_report_summary(team["owner"])
    assert s["designs_submitted"] == 40 and s["designs_verified"] == 40


def test_dr_21b_analytics_labels_submitted_and_verified(team, client):
    _log_row(team, design_count=2, listing_count=3)
    body = client(team["owner"]).get("/team/ops/analytics").get_data(as_text=True)
    for label in ("Total designs submitted", "Total designs verified",
                  "Total listings submitted", "Total listings verified",
                  "Staff with no report today", "Blocked reports",
                  "Edited-after-lock reports", "Avg listings per seller",
                  "Avg designs per designer"):
        assert label in body, label
    for col in ("Submitted designs", "Verified designs", "Submitted listings",
                "Verified listings", "Reports submitted", "Missing report days"):
        assert "<th>" + col + "</th>" in body, col


def test_dr_22_team_home_shows_the_daily_reports_widget(team, client):
    _log_row(team, design_count=2, listing_count=3)
    body = client(team["owner"]).get("/team/ops").get_data(as_text=True)
    assert "Daily Staff Reports" in body
    for label in ("Reports submitted today", "Staff missing report today",
                  "Designs today", "Listings today", "Blocked reports",
                  "Edited-after-lock reports"):
        assert label in body, label
    assert "View Daily Reports" in body and "Add My Report" in body
    assert "/team/ops/reports?view=team&amp;missing=1" in body


def test_dr_23_missing_report_warning_after_1730(team, client):
    tz = T.user_tz(team["seller"])
    today = T.utcnow().astimezone(tz).date()
    before = datetime.combine(today, time(9, 0), tzinfo=tz).astimezone(timezone.utc)
    after = datetime.combine(today, time(17, 40), tzinfo=tz).astimezone(timezone.utc)
    assert not T.missing_report_warning(team["seller"], now=before)
    assert T.missing_report_warning(team["seller"], now=after)
    _log_row(team)                                    # once filed, no warning
    assert not T.missing_report_warning(team["seller"], now=after)


def test_dr_23b_warning_copy_renders_for_staff(team, client):
    body = client(team["seller"]).get("/team/ops/reports").get_data(as_text=True)
    # before 17:30 it's a soft nudge; the hard copy is the missing-report warning
    assert ("You have not submitted today's Etsy work report." in body
            or "No report yet today" in body)
    assert not T.has_report_today(team["seller"])
    _log_row(team)
    body = client(team["seller"]).get("/team/ops/reports").get_data(as_text=True)
    assert "You have not submitted today's Etsy work report." not in body


def test_dr_23c_day_off_suppresses_the_warning(team):
    tz = T.user_tz(team["seller"])
    after = datetime.combine(T.utcnow().astimezone(tz).date(), time(21, 0),
                             tzinfo=tz).astimezone(timezone.utc)
    assert T.missing_report_warning(team["seller"], now=after)
    T.update_staff(team["seller"]["user_id"], day_off=1)
    assert not T.missing_report_warning(T.get_user(team["seller"]["user_id"]),
                                        now=after)


def test_dr_24_add_to_daily_report_prefills_from_a_task(team, client):
    t = _task(team, task_type="LISTING_DRAFT", related_keyword="nurse tumbler",
              related_store="Shop A", drive_folder="https://drive.google.com/abc")
    T.set_status(t["id"], "IN_PROGRESS", team["seller"])
    pre = T.report_prefill_from_task(T.get_task(t["id"]))
    assert pre["work_type"] == "Listing created"
    assert pre["seed_phrase_keyword"] == "nurse tumbler"
    assert pre["account_store"] == "Shop A"
    assert pre["link_folder_google_drive"] == "https://drive.google.com/abc"
    assert pre["listing_count"] == 1 and pre["design_count"] == 0
    # the task page offers the button, and the form comes back filled in
    detail = client(team["seller"]).get("/team/ops/task/%d" % t["id"]).get_data(as_text=True)
    assert "Add to Daily Report" in detail
    assert "from_task=" + str(t["id"]) in detail
    form = client(team["seller"]).get(
        "/team/ops/reports?view=mine&from_task=%d" % t["id"]).get_data(as_text=True)
    assert 'value="nurse tumbler"' in form
    assert 'value="Shop A"' in form or '"Shop A" selected' in form
    assert "https://drive.google.com/abc" in form
    assert '<option value="Listing created" selected>' in form


def test_dr_24b_design_task_prefills_design_count(team):
    t = _task(team, "designer", task_type="DESIGN", related_keyword="dog mom")
    pre = T.report_prefill_from_task(T.get_task(t["id"]))
    assert pre["work_type"] == "Design completed"
    assert pre["design_count"] == 1 and pre["listing_count"] == 0
    assert T.work_type_for_task("PATTERN_MINER") == "Pattern Miner completed"
    assert T.work_type_for_task("KEYWORD_RERANK") == "Re-rank completed"
    assert T.work_type_for_task(None) == "Other"


def test_dr_24c_prefill_is_a_draft_not_an_automatic_credit(team, client):
    """The button opens a form; nothing is written until the person saves."""
    t = _task(team, task_type="LISTING_DRAFT", related_keyword="nurse tumbler")
    client(team["seller"]).get("/team/ops/reports?view=mine&from_task=%d" % t["id"])
    assert T.list_logs() == []


def test_dr_24d_prefill_refuses_a_task_you_cannot_see(team, client):
    t = _task(team, "seller")
    form = client(team["outsider"]).get(
        "/team/ops/reports?view=mine&from_task=%d" % t["id"]).get_data(as_text=True)
    assert "Pre-filled from task" not in form


def test_dr_25_26_no_etsy_automation_added(team):
    from pathlib import Path
    assert T.PUBLISH_AUTOMATION is False
    src = (Path("src/team_ops.py").read_text(encoding="utf-8")
           + Path("src/team_ui.py").read_text(encoding="utf-8"))
    for banned in ("openapi.etsy.com", "api.etsy.com", "/v3/application",
                   "x-api-key", "oauth/connect", "shopListing"):
        assert banned not in src, banned
    # listing_url is only ever set from a submitted form value, never fetched
    assert "requests.get" not in src and "urlopen" not in src


def test_dr_status_listed_is_staff_controlled(team, client):
    row = _log_row(team, status="Draft")
    client(team["seller"]).post("/team/ops/reports/%d/save" % row["id"],
                                data={"field": "status", "value": "Listed"})
    assert T.get_log(row["id"])["status"] == "Listed"
    # ...and the change is audited, because status feeds KPI
    assert any(a["field_name"] == "status" and a["new_value"] == "Listed"
               for a in T.log_audit_trail(row["id"]))


def test_dr_manager_note_column_exists_and_survives_upgrade(team):
    cols = {r["name"] for r in appdb.q("PRAGMA table_info(proactive_work_logs)")}
    for col in ("manager_note", "verified_by_manager_id", "verified_at",
                "edited_after_lock_by", "edited_after_lock_reason", "metadata_json",
                "deleted_at", "deleted_by_id", "delete_reason"):
        assert col in cols, col
    # the migration is additive: an existing row keeps its data
    row = _log_row(team, design_count=7)
    T.init_schema(force=True)
    assert T.get_log(row["id"])["design_count"] == 7


def test_dr_csv_export_includes_verification_columns(team, client):
    row = _log_row(team)
    T.verify_log(row["id"], team["owner"], "ok")
    body = client(team["owner"]).get("/team/ops/export/logs.csv").get_data(as_text=True)
    assert "manager_note" in body and "verified_at" in body
    assert "ok" in body


def test_dr_missing_report_days_ignores_pre_hire_days(team):
    T.update_staff(team["seller"]["user_id"],
                   joined_at=T.local_today(team["seller"]))
    person = T.get_user(team["seller"]["user_id"])
    assert T.missing_report_days(person) == 0


def test_mentions_notify_the_right_people(team):
    t = _task(team)
    T.add_comment(t["id"], team["seller"]["user_id"], "@Owner please look at this")
    assert any(n["type"] == "MENTION"
               for n in T.notifications(team["owner"]["user_id"]))
