"""Authentication + role-based access control for the team dashboard.

Passwords are hashed with Werkzeug's pbkdf2 (already a Flask dependency — no new
install), never stored or logged in plain text. SQLite via src/appdb.py. Roles
gate what each teammate can do; only OWNER/ADMIN/MANAGER may approve a listing.
"""
import os
from datetime import datetime, timedelta, timezone

from werkzeug.security import generate_password_hash, check_password_hash

from src import appdb

ROLES = ["OWNER", "ADMIN", "MANAGER", "SELLER", "DESIGNER", "RESEARCHER", "VIEWER"]
STATUSES = ["ACTIVE", "DISABLED", "INVITED"]

MAX_FAILED = 5
LOCK_MINUTES = 15

# Role -> permission set. OWNER implicitly has everything.
PERMISSIONS = {
    "OWNER": {"*"},
    "ADMIN": {"users.manage", "logs.view_all", "tasks.assign", "tasks.review",
              "reports.export", "listing.approve", "workspace.build",
              "listing.edit", "spy.run", "supplier.edit", "feedback.edit",
              "design.edit", "workspace.view_all"},
    "MANAGER": {"logs.view_all", "tasks.assign", "tasks.review", "reports.export",
                "listing.approve", "workspace.build", "listing.edit", "spy.run",
                "supplier.edit", "feedback.edit", "design.edit", "workspace.view_all"},
    "SELLER": {"workspace.build", "listing.edit", "supplier.edit", "feedback.edit",
               "spy.run", "reports.export"},
    "DESIGNER": {"workspace.build", "design.edit", "spy.run", "reports.export"},
    "RESEARCHER": {"workspace.build", "spy.run", "supplier.edit", "feedback.edit",
                   "reports.export"},
    "VIEWER": {"workspace.view"},
}


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def has_perm(role, perm):
    role = (role or "").upper()
    if role == "OWNER":
        return True
    perms = PERMISSIONS.get(role, set())
    return "*" in perms or perm in perms


def can_approve(role):
    return (role or "").upper() in ("OWNER", "ADMIN", "MANAGER")


# ------------------------------------------------------------- users ----
def get_user_by_email(email):
    return appdb.q("SELECT * FROM users WHERE email = ?", (email.strip().lower(),), one=True)


def get_user(user_id):
    return appdb.q("SELECT * FROM users WHERE user_id = ?", (user_id,), one=True)


def list_users():
    return appdb.q("SELECT * FROM users ORDER BY user_id")


def user_count():
    return appdb.q("SELECT COUNT(*) n FROM users", one=True)["n"]


def create_user(email, password, display_name, role="VIEWER", created_by="system",
                must_change=False):
    email = email.strip().lower()
    role = role.upper()
    if role not in ROLES:
        raise ValueError(f"invalid role {role}; choose {ROLES}")
    if get_user_by_email(email):
        raise ValueError(f"user {email} already exists")
    now = _now()
    uid = appdb.execute(
        "INSERT INTO users (email, display_name, password_hash, role, status, "
        "must_change_password, created_by, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (email, display_name, generate_password_hash(password), role, "ACTIVE",
         1 if must_change else 0, created_by, now, now))
    return get_user(uid)


def set_role(email, role):
    role = role.upper()
    if role not in ROLES:
        raise ValueError(f"invalid role {role}")
    appdb.execute("UPDATE users SET role=?, updated_at=? WHERE email=?",
                  (role, _now(), email.strip().lower()))


def set_status(email, status):
    status = status.upper()
    if status not in STATUSES:
        raise ValueError(f"invalid status {status}")
    appdb.execute("UPDATE users SET status=?, updated_at=? WHERE email=?",
                  (status, _now(), email.strip().lower()))


def disable_user(email):
    set_status(email, "DISABLED")


def reset_password(email, new_password):
    appdb.execute("UPDATE users SET password_hash=?, failed_login_count=0, "
                  "locked_until=NULL, updated_at=? WHERE email=?",
                  (generate_password_hash(new_password), _now(), email.strip().lower()))


# --------------------------------------------------------- authenticate ----
def _record_attempt(email, ip, success):
    appdb.execute("INSERT INTO login_attempts (email, ip_address, success, timestamp) "
                  "VALUES (?,?,?,?)", (email, ip, 1 if success else 0, _now()))


def authenticate(email, password, ip=""):
    """Return (user_dict, reason). reason in ok/invalid/disabled/locked."""
    email = (email or "").strip().lower()
    u = get_user_by_email(email)
    if not u or u["status"] == "DISABLED":
        _record_attempt(email, ip, False)
        return None, ("disabled" if u else "invalid")
    if u.get("locked_until"):
        try:
            if datetime.fromisoformat(u["locked_until"]) > datetime.now(timezone.utc):
                _record_attempt(email, ip, False)
                return None, "locked"
        except ValueError:
            pass
    if check_password_hash(u["password_hash"], password):
        appdb.execute("UPDATE users SET failed_login_count=0, locked_until=NULL, "
                      "last_login_at=?, last_login_ip=?, updated_at=? WHERE user_id=?",
                      (_now(), ip, _now(), u["user_id"]))
        _record_attempt(email, ip, True)
        return get_user(u["user_id"]), "ok"
    # bad password
    fails = (u["failed_login_count"] or 0) + 1
    locked = _now() if fails < MAX_FAILED else \
        (datetime.now(timezone.utc) + timedelta(minutes=LOCK_MINUTES)).isoformat(timespec="seconds")
    appdb.execute("UPDATE users SET failed_login_count=?, locked_until=?, updated_at=? "
                  "WHERE user_id=?",
                  (fails, None if fails < MAX_FAILED else locked, _now(), u["user_id"]))
    _record_attempt(email, ip, False)
    return None, "invalid"


def failed_login_summary(limit=20):
    return appdb.q("SELECT * FROM login_attempts WHERE success=0 "
                   "ORDER BY id DESC LIMIT ?", (limit,))


# --------------------------------------------------------- bootstrap ----
def seed_admin_from_env():
    """On first run (no users), create the OWNER from .env. Falls back to
    WEB_PASSWORD so the owner is never locked out after upgrading."""
    appdb.init_db()
    if user_count() > 0:
        return None
    email = (os.getenv("ADMIN_EMAIL") or "owner@local").strip().lower()
    pw = (os.getenv("ADMIN_PASSWORD_INITIAL") or os.getenv("WEB_PASSWORD") or "").strip()
    if not pw:
        return None
    return create_user(email, pw, "Owner", role="OWNER", created_by="seed",
                       must_change=bool(os.getenv("ADMIN_PASSWORD_INITIAL")))
