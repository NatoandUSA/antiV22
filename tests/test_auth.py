"""Auth + RBAC + activity + task tests (isolated SQLite; offline)."""
import tempfile
from pathlib import Path

import pytest

from src import appdb


@pytest.fixture(autouse=True)
def temp_db():
    """Point every test in this module at a throwaway database."""
    old = appdb.DB_PATH
    appdb.DB_PATH = Path(tempfile.mkdtemp()) / "app.db"
    appdb.init_db()
    yield
    appdb.DB_PATH = old


# ------------------------------------------------------------ passwords ----
def test_password_is_hashed_not_plaintext():
    from src import auth
    u = auth.create_user("a@x.com", "SuperSecret1!", "A", "SELLER")
    assert u["password_hash"] != "SuperSecret1!"
    assert "SuperSecret1!" not in u["password_hash"]


def test_login_success_and_fail():
    from src import auth
    auth.create_user("b@x.com", "Right123!", "B", "SELLER")
    ok, why = auth.authenticate("b@x.com", "Right123!")
    assert ok and why == "ok"
    bad, why2 = auth.authenticate("b@x.com", "wrong")
    assert bad is None and why2 == "invalid"
    assert auth.authenticate("nobody@x.com", "x")[0] is None


def test_lockout_after_five_failures():
    from src import auth
    auth.create_user("c@x.com", "Right123!", "C", "SELLER")
    for _ in range(5):
        auth.authenticate("c@x.com", "bad")
    _, why = auth.authenticate("c@x.com", "Right123!")   # correct pw, but locked
    assert why == "locked"


# ---------------------------------------------------------------- roles ----
def test_role_permissions():
    from src import auth
    assert auth.has_perm("OWNER", "users.manage")
    assert auth.has_perm("MANAGER", "listing.approve")
    assert auth.has_perm("SELLER", "listing.edit")
    assert not auth.has_perm("SELLER", "users.manage")
    assert not auth.has_perm("VIEWER", "workspace.build")


def test_manager_can_approve_seller_cannot():
    from src import auth
    for r in ("OWNER", "ADMIN", "MANAGER"):
        assert auth.can_approve(r)
    for r in ("SELLER", "DESIGNER", "RESEARCHER", "VIEWER"):
        assert not auth.can_approve(r)


def test_disable_user_blocks_login():
    from src import auth
    auth.create_user("d@x.com", "Right123!", "D", "SELLER")
    auth.disable_user("d@x.com")
    ok, why = auth.authenticate("d@x.com", "Right123!")
    assert ok is None and why == "disabled"


# ------------------------------------------------------------- activity ----
def test_activity_log_creation_and_no_secrets():
    from src import auth, activity
    u = auth.create_user("e@x.com", "Right123!", "E", "RESEARCHER")
    activity.log("SPY_SEARCH", user=u, module="spy", keyword="dog mom shirt")
    activity.log("AUTH_LOGIN_SUCCESS", user=u, summary="password=hunter2")  # must redact
    evs = activity.list_events()
    assert any(e["event_type"] == "SPY_SEARCH" for e in evs)
    assert all("hunter2" not in (e.get("summary") or "") for e in evs)


# --------------------------------------------------------------- tasks ----
def test_task_create_update_review():
    from src import auth, tasks
    o = auth.create_user("mgr@x.com", "Right123!", "Mgr", "MANAGER")
    s = auth.create_user("sel@x.com", "Right123!", "Sel", "SELLER")
    t = tasks.create_task("Check supplier", assigned_to_user_id=s["user_id"],
                          assigned_by_user_id=o["user_id"], task_type="SUPPLIER_CHECK",
                          priority="HIGH")
    assert t["status"] == "TODO"
    t = tasks.update_task(t["task_id"], status="READY_FOR_REVIEW")
    assert t["status"] == "READY_FOR_REVIEW"
    assert len(tasks.review_queue()) == 1
    t = tasks.review_task(t["task_id"], o["user_id"], "APPROVED", "ok")
    assert t["review_status"] == "APPROVED" and t["status"] == "APPROVED"


def test_publish_automation_is_false():
    # The approval path only records "allowed for manual publish" — it never
    # publishes. Guard the visible promise + require server-side re-verification.
    src = Path("src/web.py").read_text(encoding="utf-8")
    assert "PUBLISH_AUTOMATION: false" in src
    assert "MANAGER_APPROVED_FOR_MANUAL_PUBLISH" in src
    # approval re-checks publish_ready server-side before recording
    assert "not ready" in src or "not PUBLISH_READY" in src
