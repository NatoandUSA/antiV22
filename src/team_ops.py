"""Team Operations OS — data + logic layer (SQLite via src/appdb.py).

The Team tab's execution system: role-based tasks, review flow, proactive work
logs with a 48-hour KPI lock, bottleneck alerts and KPI analytics. Everything is
INTERNAL: no Etsy account is touched, nothing is published, no Seller API is
called. Tasks only move work between people on this dashboard.

Design notes
------------
* Storage is SQLite (what the app already uses), so the spec's "SQLite fallback"
  applies: JSON columns are TEXT guarded by ``CHECK(json_valid(col))`` and
  updated with the JSON1 ``json_set()`` operator, which rewrites one path
  without touching unrelated columns. If a SQLite build has no JSON1 the CHECK
  is dropped and the helpers fall back to read-modify-write of that one column.
* All timestamps are stored UTC ISO-8601 with a ``+00:00`` suffix so plain
  string comparison sorts correctly. Display converts to the user's timezone
  (``users.timezone``), defaulting to Asia/Ho_Chi_Minh.
* Tasks and work logs are never hard-deleted — ``deleted_at`` / ``deleted_by_id``
  / ``delete_reason`` only. Every default query filters ``deleted_at IS NULL``.

The legacy ``tasks`` table (src/tasks.py) is left alone; this module owns the
new ``team_*`` tables so the old Team Tasks board keeps working during rollout.
"""
import json
from datetime import datetime, time, timedelta, timezone

from src import appdb

# ------------------------------------------------------------ constants ----
DEFAULT_TZ = "Asia/Ho_Chi_Minh"
DEFAULT_DUE_HOUR = 17          # 17:00 local
DEFAULT_DUE_OFFSET_DAYS = 1    # T+1
DUE_SOON_HOURS = 4
LOG_LOCK_HOURS = 48

STATUSES = ["TODO", "IN_PROGRESS", "REVIEW", "FIX_REQUESTED", "DONE", "CANCELLED"]
STATUS_LABELS = {"TODO": "To-do", "IN_PROGRESS": "In Progress", "REVIEW": "Review",
                 "FIX_REQUESTED": "Fix Requested", "DONE": "Done",
                 "CANCELLED": "Cancelled"}
# "Active" = still consuming team attention (used by overdue % + bottlenecks).
ACTIVE_STATUSES = ("TODO", "IN_PROGRESS", "REVIEW", "FIX_REQUESTED")
# Statuses where a passed deadline counts as overdue (spec §7).
OVERDUE_STATUSES = ("TODO", "IN_PROGRESS", "FIX_REQUESTED")

PRIORITIES = ["LOW", "MEDIUM", "HIGH", "URGENT"]
PRIORITY_RANK = {"URGENT": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}

TASK_TYPES = [
    ("RESEARCH", "Research"),
    ("PATTERN_MINER", "Pattern Miner"),
    ("KEYWORD_RERANK", "Keyword Re-rank"),
    ("LISTING_DRAFT", "Listing Draft"),
    ("LISTING_UPLOAD", "Listing Upload"),
    ("DESIGN", "Design"),
    ("MOCKUP", "Mockup"),
    ("PHOTO_STUDIO", "Photo Studio"),
    ("TRADEMARK_CHECK", "Trademark Check"),
    ("SUPPLIER_CHECK", "Supplier Check"),
    ("REVIEW_QA", "Review / QA"),
    ("DAY3_FOLLOWUP", "Day 3 Follow-up"),
    ("DAY7_FOLLOWUP", "Day 7 Follow-up"),
    ("FIX_REQUEST", "Fix Request"),
    ("OTHER", "Other"),
]
TASK_TYPE_LABELS = dict(TASK_TYPES)
# What a Designer sees first in the task-type picker (spec §1).
DESIGNER_TYPES = ["DESIGN", "MOCKUP", "PHOTO_STUDIO", "OTHER"]

WORK_TYPES = ["Design completed", "Listing created", "Keyword researched",
              "Competitor analyzed", "Pattern Miner completed", "Re-rank completed",
              "Image set completed", "Fix completed", "Other"]
LOG_STATUSES = ["Draft", "Completed", "Listed", "Waiting Review", "Blocked"]

# Changing one of these rewrites KPI history, so every edit is audited (spec §10).
KPI_SENSITIVE_FIELDS = ("design_count", "listing_count", "status", "work_type",
                        "seed_phrase_keyword", "account_store", "listing_url",
                        "link_folder_google_drive")

# Default QA checklists per task type (spec §6). (id, label, required)
CHECKLIST_TEMPLATES = {
    "LISTING_DRAFT": [
        ("title_complete", "Title complete", True),
        ("tags_complete", "13 tags complete", True),
        ("description_complete", "Description complete", True),
        ("personalization_clear", "Personalization instruction clear", True),
        ("price_profit_checked", "Price/profit checked", True),
        ("trademark_checked", "Trademark checked", True),
        ("supplier_confirmed", "Supplier confirmed", True),
        ("photos_ready", "Photos ready", False),
    ],
    "DESIGN": [
        ("correct_product_type", "Correct product type", True),
        ("correct_image_size", "Correct image size", True),
        ("correct_file_format", "Correct file format", True),
        ("no_trademark_issue", "No trademark issue", True),
        ("mockup_ready", "Mockup ready", False),
        ("drive_folder_clean", "Drive folder clean", False),
    ],
    "PATTERN_MINER": [
        ("listings_analyzed", "5-10 listings analyzed", True),
        ("top_sellers_shown", "Top sellers shown", True),
        ("title_pattern", "Title pattern complete", True),
        ("tag_overlap", "Tag overlap complete", True),
        ("price_band", "Price band complete", True),
        ("photo_pattern", "Photo pattern complete", False),
        ("gap_to_beat", "Gap to beat clear", True),
        ("keyword_candidates", "Keyword candidates generated", True),
        ("sent_to_rerank", "Sent to Re-rank", False),
    ],
    "KEYWORD_RERANK": [
        ("generated_reviewed", "Generated keyword reviewed", True),
        ("exact_proof", "Exact proof checked", True),
        ("cluster_proof", "Cluster proof checked", True),
        ("supplier_fit", "Supplier fit checked", True),
        ("can_we_win", "Can-We-Win checked", True),
        ("final_action", "Final action selected", True),
        ("next_task_created", "Next task created", False),
    ],
}
# Mockup / Photo Studio reuse the Design QA gate; Listing Upload reuses Listing.
CHECKLIST_TEMPLATES["MOCKUP"] = CHECKLIST_TEMPLATES["DESIGN"]
CHECKLIST_TEMPLATES["PHOTO_STUDIO"] = CHECKLIST_TEMPLATES["DESIGN"]
CHECKLIST_TEMPLATES["LISTING_UPLOAD"] = CHECKLIST_TEMPLATES["LISTING_DRAFT"]

# Bottleneck thresholds (spec §12) — one dict so the numbers live in one place.
THRESHOLDS = {
    "manager_review_warn": 10, "manager_review_crit": 15,
    "manager_oldest_review_hours": 24,
    "staff_inprogress_warn": 5, "staff_inprogress_crit": 8,
    "staff_overdue_warn": 2, "staff_overdue_crit": 3,
    "team_review_warn": 25, "team_review_crit": 40,
    "team_overdue_pct_warn": 20, "team_overdue_pct_crit": 35,
    "daily_log_warn_hour": 17.5, "daily_log_crit_hour": 21.0,
}


# ------------------------------------------------------------ time utils ----
def utcnow():
    return datetime.now(timezone.utc)


def iso(dt):
    """UTC ISO-8601 to the second. Sorts correctly as a plain string."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def now_iso():
    return iso(utcnow())


def parse_iso(s):
    """Parse a stored timestamp back to an aware UTC datetime (None if unusable)."""
    s = (s or "").strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def zone(name=None):
    """A tzinfo for `name`, falling back to the business timezone then UTC+7."""
    name = (name or "").strip() or DEFAULT_TZ
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(name)
    except Exception:  # noqa: BLE001 - Windows without tzdata, or a bad name
        if name != DEFAULT_TZ:
            return zone(DEFAULT_TZ)
        return timezone(timedelta(hours=7), "ICT")


def user_tz(user):
    return zone((user or {}).get("timezone") or business_tz_name())


def business_tz_name():
    return get_setting("business_timezone", DEFAULT_TZ)


def to_local(ts, user=None, fmt="%Y-%m-%d %H:%M"):
    """Render a stored UTC timestamp in the user's timezone."""
    dt = parse_iso(ts)
    if not dt:
        return ""
    return dt.astimezone(user_tz(user)).strftime(fmt)


def local_today(user=None):
    return utcnow().astimezone(user_tz(user)).date().isoformat()


def default_due_at(assignee=None, urgent=False, now=None):
    """Deadline for a newly assigned task: T+1 at 17:00 in the assignee's
    timezone, converted to UTC for storage (spec §3).

    Urgent tasks are allowed to land the same day: if 17:00 local today is still
    in the future we use today instead of tomorrow.
    """
    tzinfo = user_tz(assignee)
    local_now = (now or utcnow()).astimezone(tzinfo)
    hour = _setting_int("default_deadline_hour", DEFAULT_DUE_HOUR)
    offset = _setting_int("default_deadline_offset_days", DEFAULT_DUE_OFFSET_DAYS)
    target = local_now.date() + timedelta(days=offset)
    if urgent:
        same_day = datetime.combine(local_now.date(), time(hour, 0), tzinfo=tzinfo)
        if same_day > local_now:
            target = local_now.date()
    return iso(datetime.combine(target, time(hour, 0), tzinfo=tzinfo))


def local_dt_to_utc(value, user=None):
    """Convert a browser ``datetime-local`` value (YYYY-MM-DDTHH:MM) typed in the
    user's timezone into a stored UTC timestamp."""
    value = (value or "").strip()
    if not value:
        return None
    try:
        naive = datetime.fromisoformat(value[:16])
    except ValueError:
        return None
    return iso(naive.replace(tzinfo=user_tz(user)))


def utc_to_local_input(ts, user=None):
    """Inverse of local_dt_to_utc — fills a ``datetime-local`` input."""
    return to_local(ts, user, "%Y-%m-%dT%H:%M")


# ---------------------------------------------------------------- schema ----
_INITED = set()


def _has_json1():
    try:
        appdb.q("SELECT json_valid('[]') ok", one=True)
        return True
    except Exception:  # noqa: BLE001 - SQLite built without JSON1
        return False


def _json_col(name, default):
    chk = " CHECK(json_valid({0}))".format(name) if _JSON1 else ""
    return "{0} TEXT NOT NULL DEFAULT '{1}'{2}".format(name, default, chk)


_JSON1 = True   # re-probed in init_schema()


def _schema():
    return """
CREATE TABLE IF NOT EXISTS team_tasks (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    title                  TEXT NOT NULL,
    description            TEXT,
    task_type              TEXT,
    status                 TEXT NOT NULL DEFAULT 'TODO',
    priority               TEXT NOT NULL DEFAULT 'MEDIUM',
    assignee_id            INTEGER,
    assigned_by_id         INTEGER,
    reviewer_manager_id    INTEGER,
    related_opportunity_id TEXT,
    related_keyword        TEXT,
    related_listing_id     TEXT,
    related_store          TEXT,
    expected_output        TEXT,
    drive_folder           TEXT,
    internal_notes         TEXT,
    {links},
    {checklist},
    checklist_completed_count INTEGER NOT NULL DEFAULT 0,
    checklist_total_count     INTEGER NOT NULL DEFAULT 0,
    {task_meta},
    due_at                 TEXT,
    completed_at           TEXT,
    created_at             TEXT NOT NULL,
    updated_at             TEXT NOT NULL,
    deleted_at             TEXT,
    deleted_by_id          INTEGER,
    delete_reason          TEXT
);
CREATE INDEX IF NOT EXISTS idx_team_tasks_assignee_id ON team_tasks(assignee_id);
CREATE INDEX IF NOT EXISTS idx_team_tasks_status ON team_tasks(status);
CREATE INDEX IF NOT EXISTS idx_team_tasks_due_at ON team_tasks(due_at);
CREATE INDEX IF NOT EXISTS idx_team_tasks_assignee_status ON team_tasks(assignee_id, status);
CREATE INDEX IF NOT EXISTS idx_team_tasks_status_due_at ON team_tasks(status, due_at);
CREATE INDEX IF NOT EXISTS idx_team_tasks_assigned_by_id ON team_tasks(assigned_by_id);
CREATE INDEX IF NOT EXISTS idx_team_tasks_reviewer_manager_id ON team_tasks(reviewer_manager_id);
CREATE INDEX IF NOT EXISTS idx_team_tasks_related_opportunity_id ON team_tasks(related_opportunity_id);
CREATE INDEX IF NOT EXISTS idx_team_tasks_deleted_at ON team_tasks(deleted_at);
-- Partial indexes: every dashboard view filters deleted_at IS NULL, so the
-- board/home queries stay index-only instead of scanning soft-deleted rows.
CREATE INDEX IF NOT EXISTS idx_team_tasks_active_status_due
    ON team_tasks(status, due_at) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_team_tasks_active_assignee_status
    ON team_tasks(assignee_id, status) WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS task_comments (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id       INTEGER NOT NULL,
    user_id       INTEGER,
    comment_text  TEXT,
    {attachments},
    {mentions},
    is_system_event INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_comments_task_id ON task_comments(task_id);
CREATE INDEX IF NOT EXISTS idx_comments_created_at ON task_comments(created_at);

CREATE TABLE IF NOT EXISTS task_activity_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id    INTEGER NOT NULL,
    actor_id   INTEGER,
    action     TEXT NOT NULL,
    old_value  TEXT,
    new_value  TEXT,
    {act_meta},
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_activity_task_id ON task_activity_log(task_id);
CREATE INDEX IF NOT EXISTS idx_activity_actor_id ON task_activity_log(actor_id);
CREATE INDEX IF NOT EXISTS idx_activity_created_at ON task_activity_log(created_at);

CREATE TABLE IF NOT EXISTS proactive_work_logs (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    date                    TEXT NOT NULL,
    staff_id                INTEGER NOT NULL,
    role                    TEXT,
    account_store           TEXT,
    work_type               TEXT,
    seed_phrase_keyword     TEXT,
    product_type            TEXT,
    link_folder_google_drive TEXT,
    listing_url             TEXT,
    design_count            INTEGER NOT NULL DEFAULT 0,
    listing_count           INTEGER NOT NULL DEFAULT 0,
    status                  TEXT NOT NULL DEFAULT 'Draft',
    notes                   TEXT,
    {log_meta},
    edited_after_lock_by    INTEGER,
    edited_after_lock_reason TEXT,
    verified_by_manager_id  INTEGER,
    verified_at             TEXT,
    manager_note            TEXT,
    review_state            TEXT,
    created_at              TEXT NOT NULL,
    updated_at              TEXT NOT NULL,
    deleted_at              TEXT,
    deleted_by_id           INTEGER,
    delete_reason           TEXT
);
CREATE INDEX IF NOT EXISTS idx_work_logs_staff_id ON proactive_work_logs(staff_id);
CREATE INDEX IF NOT EXISTS idx_work_logs_date ON proactive_work_logs(date);
CREATE INDEX IF NOT EXISTS idx_work_logs_staff_date ON proactive_work_logs(staff_id, date);
CREATE INDEX IF NOT EXISTS idx_work_logs_status ON proactive_work_logs(status);
CREATE INDEX IF NOT EXISTS idx_work_logs_account_store ON proactive_work_logs(account_store);
CREATE INDEX IF NOT EXISTS idx_work_logs_deleted_at ON proactive_work_logs(deleted_at);
CREATE INDEX IF NOT EXISTS idx_work_logs_active_staff_date
    ON proactive_work_logs(staff_id, date) WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS proactive_work_log_audit (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    log_id            INTEGER NOT NULL,
    actor_id          INTEGER,
    field_name        TEXT NOT NULL,
    old_value         TEXT,
    new_value         TEXT,
    edit_reason       TEXT,
    edited_after_lock INTEGER NOT NULL DEFAULT 0,
    created_at        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_work_log_audit_log_id ON proactive_work_log_audit(log_id);
CREATE INDEX IF NOT EXISTS idx_work_log_audit_actor_id ON proactive_work_log_audit(actor_id);
CREATE INDEX IF NOT EXISTS idx_work_log_audit_created_at ON proactive_work_log_audit(created_at);

CREATE TABLE IF NOT EXISTS notifications (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL,
    type            TEXT,
    title           TEXT,
    message         TEXT,
    related_task_id INTEGER,
    {notif_meta},
    read_at         TEXT,
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_notifications_user_read ON notifications(user_id, read_at);
CREATE INDEX IF NOT EXISTS idx_notifications_created_at ON notifications(created_at);

CREATE TABLE IF NOT EXISTS staff_kpi_daily (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    date                   TEXT NOT NULL,
    staff_id               INTEGER NOT NULL,
    tasks_done             INTEGER NOT NULL DEFAULT 0,
    tasks_overdue          INTEGER NOT NULL DEFAULT 0,
    on_time_rate           REAL NOT NULL DEFAULT 0,
    design_count_raw       INTEGER NOT NULL DEFAULT 0,
    design_count_verified  INTEGER NOT NULL DEFAULT 0,
    listing_count_raw      INTEGER NOT NULL DEFAULT 0,
    listing_count_verified INTEGER NOT NULL DEFAULT 0,
    proactive_log_count    INTEGER NOT NULL DEFAULT 0,
    fix_request_count      INTEGER NOT NULL DEFAULT 0,
    logs_edited_after_lock INTEGER NOT NULL DEFAULT 0,
    quality_score          REAL NOT NULL DEFAULT 0,
    created_at             TEXT NOT NULL,
    updated_at             TEXT NOT NULL,
    UNIQUE(date, staff_id)
);
CREATE INDEX IF NOT EXISTS idx_kpi_daily_staff_date ON staff_kpi_daily(staff_id, date);

CREATE TABLE IF NOT EXISTS team_settings (
    key        TEXT PRIMARY KEY,
    value      TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS team_dropdowns (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    kind       TEXT NOT NULL,
    value      TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    active     INTEGER NOT NULL DEFAULT 1,
    UNIQUE(kind, value)
);
""".format(
        links=_json_col("links_json", "[]"),
        checklist=_json_col("checklist_json", "[]"),
        task_meta=_json_col("metadata_json", "{}"),
        attachments=_json_col("attachments_json", "[]"),
        mentions=_json_col("mentions_json", "[]"),
        act_meta=_json_col("metadata_json", "{}"),
        log_meta=_json_col("metadata_json", "{}"),
        notif_meta=_json_col("metadata_json", "{}"),
    )


# Extra user columns the Staff Directory needs (spec §14).
_USER_COLS = [
    ("manager_id", "INTEGER"),
    ("timezone", "TEXT"),
    ("active", "INTEGER NOT NULL DEFAULT 1"),
    ("deactivated_at", "TEXT"),
    ("default_store", "TEXT"),
    ("joined_at", "TEXT"),
    ("target_designs", "INTEGER NOT NULL DEFAULT 0"),
    ("target_listings", "INTEGER NOT NULL DEFAULT 0"),
    ("target_research", "INTEGER NOT NULL DEFAULT 0"),
    ("day_off", "INTEGER NOT NULL DEFAULT 0"),
]

# Columns added to proactive_work_logs after the table first shipped. CREATE
# TABLE IF NOT EXISTS never alters an existing table, so upgrades come through
# here — the daily-report rows staff already filed are kept, never rebuilt.
_LOG_COLS = [("manager_note", "TEXT"), ("review_state", "TEXT")]


def init_schema(force=False):
    """Create/upgrade the team tables. Idempotent and cheap after the first call."""
    global _JSON1
    key = str(appdb.DB_PATH.resolve())
    if key in _INITED and not force:
        return
    appdb.init_db()
    _JSON1 = _has_json1()
    with appdb.connect() as c:
        c.executescript(_schema())
        for col, decl in _USER_COLS:
            appdb._add_column(c, "users", col, decl)
        for col, decl in _LOG_COLS:
            appdb._add_column(c, "proactive_work_logs", col, decl)
    _INITED.add(key)


def _ensure():
    if str(appdb.DB_PATH.resolve()) not in _INITED:
        init_schema()


def reset_cache():
    """Forget which DBs were initialised — used by tests that chdir into a sandbox."""
    _INITED.clear()


def _same(a, b):
    """Compare a stored value with a submitted one without the ``0 or ''`` trap
    (a count of 0 must not look like a change)."""
    return ("" if a is None else str(a)) == ("" if b is None else str(b))


def _jloads(s, fallback):
    try:
        v = json.loads(s or "")
    except (ValueError, TypeError):
        return fallback
    return v if isinstance(v, type(fallback)) else fallback


# -------------------------------------------------------------- settings ----
_SETTING_DEFAULTS = {
    "default_deadline_hour": str(DEFAULT_DUE_HOUR),
    "default_deadline_offset_days": str(DEFAULT_DUE_OFFSET_DAYS),
    "business_timezone": DEFAULT_TZ,
    "due_soon_hours": str(DUE_SOON_HOURS),
    "overdue_notifications": "1",
    "inapp_notifications": "1",
    "email_notifications": "0",
    "push_notifications": "0",
}


def get_setting(key, default=None):
    _ensure()
    row = appdb.q("SELECT value FROM team_settings WHERE key = ?", (key,), one=True)
    if row and row["value"] is not None:
        return row["value"]
    return _SETTING_DEFAULTS.get(key, default)


def set_setting(key, value):
    _ensure()
    appdb.execute(
        "INSERT INTO team_settings (key, value, updated_at) VALUES (?,?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value, "
        "updated_at=excluded.updated_at", (key, str(value), now_iso()))


def all_settings():
    _ensure()
    out = dict(_SETTING_DEFAULTS)
    for r in appdb.q("SELECT key, value FROM team_settings"):
        if r["value"] is not None:
            out[r["key"]] = r["value"]
    return out


def _setting_int(key, default):
    try:
        return int(float(get_setting(key, default)))
    except (TypeError, ValueError):
        return default


def due_soon_hours():
    return _setting_int("due_soon_hours", DUE_SOON_HOURS)


# ------------------------------------------------------------- dropdowns ----
DROPDOWN_KINDS = ("store", "task_type", "work_type", "priority", "status",
                  "product_type")


def dropdown_values(kind, fallback=None):
    _ensure()
    rows = appdb.q("SELECT value FROM team_dropdowns WHERE kind=? AND active=1 "
                   "ORDER BY sort_order, value", (kind,))
    vals = [r["value"] for r in rows]
    return vals or list(fallback or [])


def add_dropdown(kind, value):
    _ensure()
    value = (value or "").strip()
    if not value or kind not in DROPDOWN_KINDS:
        return False
    appdb.execute("INSERT OR IGNORE INTO team_dropdowns (kind, value) VALUES (?,?)",
                  (kind, value))
    return True


def remove_dropdown(kind, value):
    _ensure()
    appdb.execute("DELETE FROM team_dropdowns WHERE kind=? AND value=?", (kind, value))


def store_options():
    return dropdown_values("store")


def product_type_options():
    return dropdown_values("product_type")


def work_type_options():
    return dropdown_values("work_type", WORK_TYPES)


# ------------------------------------------------------------------ RBAC ----
# The dashboard has 7 legacy roles; the Team OS collapses them onto the 4 roles
# in the spec so no existing account has to be re-created.
_ROLE_MAP = {"OWNER": "OWNER", "ADMIN": "OWNER", "MANAGER": "MANAGER",
             "SELLER": "SELLER", "RESEARCHER": "SELLER", "DESIGNER": "DESIGNER",
             "VIEWER": "VIEWER"}
STAFF_ROLES = ("SELLER", "DESIGNER")


def team_role(user):
    return _ROLE_MAP.get(((user or {}).get("role") or "").upper(), "VIEWER")


def is_owner(user):
    return team_role(user) == "OWNER"


def is_manager(user):
    """Owner or Manager — the two roles that can approve, assign and review."""
    return team_role(user) in ("OWNER", "MANAGER")


def is_staff(user):
    return team_role(user) in STAFF_ROLES


def user_active(user):
    u = user or {}
    if (u.get("status") or "ACTIVE").upper() == "DISABLED":
        return False
    return bool(u.get("active", 1))


def managed_ids(user):
    """User ids a Manager may act on: their direct reports plus themselves."""
    _ensure()
    if not user:
        return set()
    if is_owner(user):
        return {u["user_id"] for u in appdb.q("SELECT user_id FROM users")}
    uid = user["user_id"]
    rows = appdb.q("SELECT user_id FROM users WHERE manager_id = ?", (uid,))
    return {r["user_id"] for r in rows} | {uid}


def can_see_task(user, task):
    if not user or not task:
        return False
    if is_owner(user):
        return True
    if is_manager(user):
        return (task.get("assignee_id") in managed_ids(user)
                or task.get("assigned_by_id") == user["user_id"]
                or task.get("reviewer_manager_id") == user["user_id"])
    return task.get("assignee_id") == user["user_id"]


def can_edit_task(user, task):
    """Full edit (title/assignee/deadline/priority). Staff only submit work."""
    return is_manager(user) and can_see_task(user, task)


def can_transition(user, task, new_status):
    """Status rules from spec §4. Returns (allowed, reason)."""
    cur = (task or {}).get("status")
    new_status = (new_status or "").upper()
    if new_status not in STATUSES:
        return False, "unknown status"
    if not can_see_task(user, task):
        return False, "not your task"
    if cur == new_status:
        return False, "already " + STATUS_LABELS[new_status]
    if is_manager(user):
        return True, ""
    if not is_staff(user):
        return False, "your role cannot change task status"
    if task.get("assignee_id") != user["user_id"]:
        return False, "not your task"
    allowed = {"TODO": {"IN_PROGRESS"},
               "IN_PROGRESS": {"REVIEW"},
               "FIX_REQUESTED": {"IN_PROGRESS"},
               "REVIEW": set()}.get(cur, set())
    if new_status == "DONE":
        return False, "only a Manager or Owner can mark a task Done"
    if new_status not in allowed:
        return False, "staff cannot move {0} to {1}".format(
            STATUS_LABELS.get(cur, cur), STATUS_LABELS[new_status])
    return True, ""


# ------------------------------------------------------------------ users ----
def list_team(include_inactive=False):
    _ensure()
    sql = "SELECT * FROM users"
    if not include_inactive:
        sql += " WHERE status != 'DISABLED' AND COALESCE(active,1) = 1"
    return appdb.q(sql + " ORDER BY display_name")


def users_by_id(include_inactive=True):
    return {u["user_id"]: u for u in list_team(include_inactive=include_inactive)}


def get_user(uid):
    _ensure()
    return appdb.q("SELECT * FROM users WHERE user_id = ?", (uid,), one=True)


def visible_staff(user):
    """Who this user may see in directory / analytics / leaderboards."""
    people = list_team(include_inactive=True)
    if is_owner(user):
        return people
    if is_manager(user):
        ids = managed_ids(user)
        return [p for p in people if p["user_id"] in ids]
    return [p for p in people if p["user_id"] == (user or {}).get("user_id")]


def update_staff(uid, **fields):
    """Owner-editable directory fields. Unknown keys are ignored."""
    _ensure()
    allowed = {"manager_id", "timezone", "default_store", "joined_at",
               "target_designs", "target_listings", "target_research", "day_off"}
    sets, params = [], []
    for k, v in fields.items():
        if k in allowed:
            sets.append(k + "=?")
            params.append(v)
    if not sets:
        return
    params += [now_iso(), uid]
    appdb.execute("UPDATE users SET {0}, updated_at=? WHERE user_id=?"
                  .format(", ".join(sets)), tuple(params))


def set_user_active(uid, active, actor_id=None):
    """Deactivate instead of deleting — history must keep resolving (spec §14)."""
    _ensure()
    now = now_iso()
    appdb.execute(
        "UPDATE users SET active=?, status=?, deactivated_at=?, updated_at=? "
        "WHERE user_id=?",
        (1 if active else 0, "ACTIVE" if active else "DISABLED",
         None if active else now, now, uid))


# ------------------------------------------------------------------ tasks ----
def _checklist_from_template(task_type):
    tpl = CHECKLIST_TEMPLATES.get((task_type or "").upper(), [])
    return [{"id": i, "label": lbl, "required": bool(req), "is_checked": False,
             "checked_by": None, "checked_at": None} for i, lbl, req in tpl]


def _checklist_counts(items):
    return sum(1 for i in items if i.get("is_checked")), len(items)


def create_task(title, assignee_id=None, assigned_by_id=None, task_type="OTHER",
                priority="MEDIUM", description="", due_at=None,
                related_opportunity_id="", related_keyword="",
                related_listing_id="", related_store="", expected_output="",
                drive_folder="", links=None, checklist=None, metadata=None,
                internal_notes="", reviewer_manager_id=None, actor=None):
    """Create + assign a task. Deadline defaults to T+1 17:00 in the assignee's
    timezone (spec §3); Urgent may land the same day."""
    _ensure()
    priority = (priority or "MEDIUM").upper()
    if priority not in PRIORITIES:
        priority = "MEDIUM"
    task_type = (task_type or "OTHER").upper()
    assignee = get_user(assignee_id) if assignee_id else None
    if not due_at and assignee_id:
        due_at = default_due_at(assignee, urgent=(priority == "URGENT"))
    if reviewer_manager_id is None and assignee:
        reviewer_manager_id = assignee.get("manager_id")
    if reviewer_manager_id is None and assigned_by_id:
        reviewer_manager_id = assigned_by_id
    items = checklist if checklist is not None else _checklist_from_template(task_type)
    done_n, total_n = _checklist_counts(items)
    now = now_iso()
    tid = appdb.execute(
        "INSERT INTO team_tasks (title, description, task_type, status, priority, "
        "assignee_id, assigned_by_id, reviewer_manager_id, related_opportunity_id, "
        "related_keyword, related_listing_id, related_store, expected_output, "
        "drive_folder, internal_notes, links_json, checklist_json, "
        "checklist_completed_count, checklist_total_count, metadata_json, due_at, "
        "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (title.strip()[:200], description, task_type, "TODO", priority,
         assignee_id, assigned_by_id, reviewer_manager_id,
         related_opportunity_id or None, related_keyword or None,
         related_listing_id or None, related_store or None, expected_output,
         drive_folder, internal_notes, json.dumps(links or []),
         json.dumps(items), done_n, total_n, json.dumps(metadata or {}),
         due_at, now, now))
    actor_id = (actor or {}).get("user_id") or assigned_by_id
    log_activity(tid, actor_id, "created", new_value=title.strip()[:200])
    if assignee_id:
        log_activity(tid, actor_id, "assigned",
                     new_value=(assignee or {}).get("display_name") or str(assignee_id))
        notify(assignee_id, "TASK_ASSIGNED", "New task assigned",
               title.strip()[:120], task_id=tid)
    return get_task(tid)


def get_task(tid, include_deleted=True):
    _ensure()
    sql = "SELECT * FROM team_tasks WHERE id = ?"
    if not include_deleted:
        sql += " AND deleted_at IS NULL"
    t = appdb.q(sql, (tid,), one=True)
    return _hydrate(t) if t else None


def _hydrate(t):
    t["checklist"] = _jloads(t.get("checklist_json"), [])
    t["links"] = _jloads(t.get("links_json"), [])
    t["metadata"] = _jloads(t.get("metadata_json"), {})
    return t


def list_tasks(user=None, status=None, assignee_id=None, task_type=None,
               priority=None, store=None, search=None, include_deleted=False,
               limit=1000, since=None, until=None):
    """Scoped, soft-delete-aware task query. `user` applies the RBAC scope."""
    _ensure()
    where, params = [], []
    if not include_deleted:
        where.append("deleted_at IS NULL")
    if user is not None and not is_owner(user):
        if is_manager(user):
            ids = sorted(managed_ids(user))
            marks = ",".join("?" * len(ids)) or "NULL"
            where.append("(assignee_id IN ({0}) OR assigned_by_id = ? "
                         "OR reviewer_manager_id = ?)".format(marks))
            params += ids + [user["user_id"], user["user_id"]]
        else:
            where.append("assignee_id = ?")
            params.append(user["user_id"])
    if status:
        vals = [status] if isinstance(status, str) else list(status)
        where.append("status IN ({0})".format(",".join("?" * len(vals))))
        params += vals
    if assignee_id:
        where.append("assignee_id = ?"); params.append(assignee_id)
    if task_type:
        where.append("task_type = ?"); params.append(task_type)
    if priority:
        where.append("priority = ?"); params.append(priority)
    if store:
        where.append("related_store = ?"); params.append(store)
    if since:
        where.append("created_at >= ?"); params.append(since)
    if until:
        where.append("created_at <= ?"); params.append(until)
    if search:
        where.append("(title LIKE ? OR related_keyword LIKE ? OR description LIKE ?)")
        params += ["%{0}%".format(search)] * 3
    sql = "SELECT * FROM team_tasks"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += (" ORDER BY CASE priority WHEN 'URGENT' THEN 0 WHEN 'HIGH' THEN 1 "
            "WHEN 'MEDIUM' THEN 2 ELSE 3 END, due_at IS NULL, due_at, id DESC LIMIT ?")
    params.append(limit)
    return [_hydrate(r) for r in appdb.q(sql, tuple(params))]


def update_task(tid, actor=None, **fields):
    """Edit task fields (Manager/Owner). Each changed field writes activity."""
    _ensure()
    t = get_task(tid)
    if not t:
        return None
    editable = {"title", "description", "task_type", "priority", "assignee_id",
                "reviewer_manager_id", "related_opportunity_id", "related_keyword",
                "related_listing_id", "related_store", "expected_output",
                "drive_folder", "internal_notes", "due_at"}
    sets, params, changes = [], [], []
    for k, v in fields.items():
        if k not in editable or v is None:
            continue
        if _same(t.get(k), v):
            continue
        sets.append(k + "=?")
        params.append(v)
        changes.append((k, t.get(k), v))
    if not sets:
        return t
    params += [now_iso(), tid]
    appdb.execute("UPDATE team_tasks SET {0}, updated_at=? WHERE id=?"
                  .format(", ".join(sets)), tuple(params))
    actor_id = (actor or {}).get("user_id")
    for k, old, new in changes:
        log_activity(tid, actor_id, "updated:" + k, old_value=old, new_value=new)
        if k == "assignee_id" and new:
            notify(int(new), "TASK_ASSIGNED", "Task assigned to you",
                   t["title"][:120], task_id=tid)
    return get_task(tid)


def set_status(tid, new_status, actor, note="", new_due_at=None):
    """The one place a task changes status. Enforces §4 and always audits."""
    _ensure()
    t = get_task(tid, include_deleted=False)
    if not t:
        return None, "task not found"
    ok, why = can_transition(actor, t, new_status)
    if not ok:
        return None, why
    new_status = new_status.upper()
    if new_status == "REVIEW":
        missing = missing_required(t)
        if missing:
            return None, "checklist incomplete: " + ", ".join(missing)
    now = now_iso()
    completed = now if new_status == "DONE" else t.get("completed_at")
    sets = ["status=?", "completed_at=?", "updated_at=?"]
    params = [new_status, completed, now]
    if new_due_at:
        sets.append("due_at=?")
        params.append(new_due_at)
    params.append(tid)
    appdb.execute("UPDATE team_tasks SET {0} WHERE id=?".format(", ".join(sets)),
                  tuple(params))
    log_activity(tid, (actor or {}).get("user_id"), "status",
                 old_value=t["status"], new_value=new_status)
    if note:
        add_comment(tid, (actor or {}).get("user_id"), note, system=True)
    _notify_status(t, new_status, actor)
    return get_task(tid), ""


def _notify_status(t, new_status, actor):
    tid, title = t["id"], (t.get("title") or "")[:120]
    if new_status == "REVIEW":
        for uid in _reviewers_for(t):
            notify(uid, "TASK_REVIEW", "Waiting for review", title, task_id=tid)
    elif new_status == "FIX_REQUESTED" and t.get("assignee_id"):
        notify(t["assignee_id"], "TASK_FIX", "Fix requested", title, task_id=tid)
    elif new_status == "DONE" and t.get("assignee_id"):
        notify(t["assignee_id"], "TASK_DONE", "Task approved", title, task_id=tid)
    elif new_status == "CANCELLED" and t.get("assignee_id"):
        notify(t["assignee_id"], "TASK_CANCELLED", "Task cancelled", title, task_id=tid)


def _reviewers_for(t):
    """Who gets told when work lands in Review: the named reviewer, the
    assignee's manager, then every owner as a backstop."""
    out = []
    if t.get("reviewer_manager_id"):
        out.append(t["reviewer_manager_id"])
    a = get_user(t.get("assignee_id")) if t.get("assignee_id") else None
    if a and a.get("manager_id"):
        out.append(a["manager_id"])
    if not out:
        out = [u["user_id"] for u in list_team() if is_manager(u)]
    return sorted(set(x for x in out if x))


def request_fix(tid, actor, reason, required_changes="", new_due_at=None):
    """Review -> Fix Requested with a reason and a fresh deadline (spec §11)."""
    t = get_task(tid, include_deleted=False)
    if not t:
        return None, "task not found"
    if not is_manager(actor):
        return None, "only a Manager or Owner can request a fix"
    if not new_due_at:
        new_due_at = default_due_at(get_user(t.get("assignee_id")))
    body = reason or "Fix requested"
    if required_changes:
        body += "\nRequired: " + required_changes
    return set_status(tid, "FIX_REQUESTED", actor, note=body, new_due_at=new_due_at)


def soft_delete_task(tid, actor, reason=""):
    """Never removes the row — KPI history and foreign keys stay valid (§17)."""
    _ensure()
    if not is_manager(actor):
        return False, "only a Manager or Owner can delete a task"
    t = get_task(tid)
    if not t:
        return False, "task not found"
    if not can_see_task(actor, t):
        return False, "not your task"
    appdb.execute("UPDATE team_tasks SET deleted_at=?, deleted_by_id=?, "
                  "delete_reason=?, updated_at=? WHERE id=?",
                  (now_iso(), actor["user_id"], reason or "", now_iso(), tid))
    log_activity(tid, actor["user_id"], "deleted", new_value=reason or "")
    return True, ""


def restore_task(tid, actor):
    _ensure()
    if not is_owner(actor):
        return False, "only an Owner can restore"
    appdb.execute("UPDATE team_tasks SET deleted_at=NULL, deleted_by_id=NULL, "
                  "delete_reason=NULL, updated_at=? WHERE id=?", (now_iso(), tid))
    log_activity(tid, actor["user_id"], "restored")
    return True, ""


# ---- deadline state ----
def is_overdue(t, now=None):
    if t.get("status") not in OVERDUE_STATUSES:
        return False
    due = parse_iso(t.get("due_at"))
    return bool(due) and due < (now or utcnow())


def is_due_soon(t, now=None, hours=None):
    if t.get("status") not in OVERDUE_STATUSES:
        return False
    due = parse_iso(t.get("due_at"))
    if not due:
        return False
    now = now or utcnow()
    window = timedelta(hours=hours if hours is not None else due_soon_hours())
    return now <= due <= now + window


def due_state(t, now=None):
    """Card colour: overdue / fix / soon / ontrack / none (spec §7)."""
    if t.get("status") == "FIX_REQUESTED":
        return "fix"
    if is_overdue(t, now):
        return "overdue"
    if is_due_soon(t, now):
        return "soon"
    return "ontrack" if t.get("due_at") else "none"


# ------------------------------------------------------------- checklist ----
def missing_required(task):
    """Required checklist labels still unticked — blocks Submit for Review."""
    return [i.get("label") or i.get("id") for i in (task.get("checklist") or [])
            if i.get("required") and not i.get("is_checked")]


def set_checklist_item(tid, item_id, checked, actor):
    """Tick/untick ONE checklist item.

    With JSON1 this is a targeted ``json_set`` on three paths inside
    checklist_json — metadata_json and every other column are untouched.
    """
    _ensure()
    t = get_task(tid, include_deleted=False)
    if not t:
        return None, "task not found"
    if not can_see_task(actor, t):
        return None, "not your task"
    if not (is_manager(actor) or t.get("assignee_id") == actor.get("user_id")):
        return None, "not your task"
    items = t["checklist"]
    idx = next((n for n, i in enumerate(items) if i.get("id") == item_id), None)
    if idx is None:
        return None, "unknown checklist item"
    checked = bool(checked)
    actor_id = (actor or {}).get("user_id")
    stamp = now_iso() if checked else None
    if _JSON1:
        appdb.execute(
            "UPDATE team_tasks SET checklist_json = json_set(checklist_json, "
            "'$[' || ? || '].is_checked', json(?), "
            "'$[' || ? || '].checked_by', ?, "
            "'$[' || ? || '].checked_at', ?), updated_at = ? WHERE id = ?",
            (idx, "true" if checked else "false", idx,
             actor_id if checked else None, idx, stamp, now_iso(), tid))
    else:
        items[idx].update({"is_checked": checked,
                           "checked_by": actor_id if checked else None,
                           "checked_at": stamp})
        appdb.execute("UPDATE team_tasks SET checklist_json=?, updated_at=? WHERE id=?",
                      (json.dumps(items), now_iso(), tid))
    fresh = get_task(tid)
    done_n, total_n = _checklist_counts(fresh["checklist"])
    appdb.execute("UPDATE team_tasks SET checklist_completed_count=?, "
                  "checklist_total_count=? WHERE id=?", (done_n, total_n, tid))
    log_activity(tid, actor_id, "checklist:" + item_id,
                 old_value="checked" if not checked else "unchecked",
                 new_value="checked" if checked else "unchecked")
    return get_task(tid), ""


def apply_checklist_template(tid, task_type, actor):
    """Replace the checklist with the template for a task type."""
    _ensure()
    items = _checklist_from_template(task_type)
    done_n, total_n = _checklist_counts(items)
    appdb.execute("UPDATE team_tasks SET checklist_json=?, checklist_completed_count=?, "
                  "checklist_total_count=?, updated_at=? WHERE id=?",
                  (json.dumps(items), done_n, total_n, now_iso(), tid))
    log_activity(tid, (actor or {}).get("user_id"), "checklist:template",
                 new_value=task_type)
    return get_task(tid)


# ------------------------------------------------- comments + activity ----
def log_activity(task_id, actor_id, action, old_value=None, new_value=None,
                 metadata=None):
    _ensure()
    appdb.execute(
        "INSERT INTO task_activity_log (task_id, actor_id, action, old_value, "
        "new_value, metadata_json, created_at) VALUES (?,?,?,?,?,?,?)",
        (task_id, actor_id, action,
         None if old_value is None else str(old_value)[:400],
         None if new_value is None else str(new_value)[:400],
         json.dumps(metadata or {}), now_iso()))


def task_activity(task_id, limit=200):
    _ensure()
    return appdb.q("SELECT * FROM task_activity_log WHERE task_id = ? "
                   "ORDER BY id DESC LIMIT ?", (task_id, limit))


def parse_mentions(text, task=None):
    """Resolve @Owner / @Manager / @Assignee / @Name to user ids."""
    _ensure()
    low = (text or "").lower()
    hits = set()
    if "@owner" in low:
        hits |= {u["user_id"] for u in list_team() if is_owner(u)}
    if "@manager" in low:
        hits |= {u["user_id"] for u in list_team() if team_role(u) == "MANAGER"}
        if task and task.get("reviewer_manager_id"):
            hits.add(task["reviewer_manager_id"])
    if "@assignee" in low and task and task.get("assignee_id"):
        hits.add(task["assignee_id"])
    for u in list_team():
        handle = "@" + (u["display_name"] or "").split()[0].lower() if u["display_name"] else ""
        if handle and len(handle) > 2 and handle in low:
            hits.add(u["user_id"])
    return sorted(hits)


def add_comment(task_id, user_id, text, attachments=None, system=False):
    _ensure()
    t = get_task(task_id)
    mentions = [] if system else parse_mentions(text, t)
    cid = appdb.execute(
        "INSERT INTO task_comments (task_id, user_id, comment_text, "
        "attachments_json, mentions_json, is_system_event, created_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (task_id, user_id, (text or "")[:4000], json.dumps(attachments or []),
         json.dumps(mentions), 1 if system else 0, now_iso()))
    if not system:
        log_activity(task_id, user_id, "commented", new_value=(text or "")[:120])
        for uid in mentions:
            if uid != user_id:
                notify(uid, "MENTION", "You were mentioned",
                       (text or "")[:120], task_id=task_id)
    return cid


def task_comments(task_id, limit=200):
    _ensure()
    rows = appdb.q("SELECT * FROM task_comments WHERE task_id = ? "
                   "ORDER BY id DESC LIMIT ?", (task_id, limit))
    for r in rows:
        r["attachments"] = _jloads(r.get("attachments_json"), [])
        r["mentions"] = _jloads(r.get("mentions_json"), [])
    return rows


def latest_comment(task_id):
    rows = task_comments(task_id, limit=1)
    return rows[0] if rows else None


def latest_comments_map(task_ids):
    """One query for the board: newest non-system comment per task."""
    _ensure()
    ids = [t for t in task_ids if t]
    if not ids:
        return {}
    marks = ",".join("?" * len(ids))
    rows = appdb.q(
        "SELECT task_id, comment_text, MAX(id) AS mid FROM task_comments "
        "WHERE task_id IN ({0}) AND is_system_event = 0 "
        "GROUP BY task_id".format(marks), tuple(ids))
    return {r["task_id"]: r["comment_text"] for r in rows}


def submit_for_review(tid, actor, note="", link="", drive_folder=""):
    """Staff submission flow (spec §5): attach work, note, then move to Review."""
    _ensure()
    t = get_task(tid, include_deleted=False)
    if not t:
        return None, "task not found"
    # Check the gates BEFORE attaching anything, so a blocked submit doesn't
    # leave a duplicate link + note behind on every retry.
    ok, why = can_transition(actor, t, "REVIEW")
    if not ok:
        return None, why
    missing = missing_required(t)
    if missing:
        return None, "checklist incomplete: " + ", ".join(missing)
    if link or drive_folder:
        links = t["links"]
        if link:
            links.append({"url": link, "added_at": now_iso(),
                          "by": (actor or {}).get("user_id")})
        sets, params = ["links_json=?"], [json.dumps(links)]
        if drive_folder:
            sets.append("drive_folder=?")
            params.append(drive_folder)
        params += [now_iso(), tid]
        appdb.execute("UPDATE team_tasks SET {0}, updated_at=? WHERE id=?"
                      .format(", ".join(sets)), tuple(params))
        log_activity(tid, (actor or {}).get("user_id"), "submitted:link",
                     new_value=(link or drive_folder)[:200])
        t = get_task(tid)
    if note:
        add_comment(tid, (actor or {}).get("user_id"), note)
    return set_status(tid, "REVIEW", actor)


# ---------------------------------------------------------- notifications ----
def notify(user_id, ntype, title, message="", task_id=None, metadata=None):
    _ensure()
    if not user_id or get_setting("inapp_notifications", "1") != "1":
        return None
    return appdb.execute(
        "INSERT INTO notifications (user_id, type, title, message, "
        "related_task_id, metadata_json, created_at) VALUES (?,?,?,?,?,?,?)",
        (user_id, ntype, title, message, task_id, json.dumps(metadata or {}),
         now_iso()))


def notifications(user_id, unread_only=False, limit=50):
    _ensure()
    sql = "SELECT * FROM notifications WHERE user_id = ?"
    if unread_only:
        sql += " AND read_at IS NULL"
    return appdb.q(sql + " ORDER BY id DESC LIMIT ?", (user_id, limit))


def unread_count(user_id):
    _ensure()
    r = appdb.q("SELECT COUNT(*) n FROM notifications WHERE user_id=? AND "
                "read_at IS NULL", (user_id,), one=True)
    return r["n"] if r else 0


def mark_notifications_read(user_id, nid=None):
    _ensure()
    if nid:
        appdb.execute("UPDATE notifications SET read_at=? WHERE id=? AND user_id=?",
                      (now_iso(), nid, user_id))
    else:
        appdb.execute("UPDATE notifications SET read_at=? WHERE user_id=? AND "
                      "read_at IS NULL", (now_iso(), user_id))


def sweep_deadline_notifications(now=None):
    """Fire one overdue / due-soon notice per task per state, to the assignee and
    their manager. Idempotent: the metadata marker stops repeats."""
    _ensure()
    if get_setting("overdue_notifications", "1") != "1":
        return 0
    now = now or utcnow()
    sent = 0
    for t in list_tasks(status=list(OVERDUE_STATUSES)):
        state = "overdue" if is_overdue(t, now) else (
            "soon" if is_due_soon(t, now) else None)
        if not state or not t.get("assignee_id"):
            continue
        marker = "DEADLINE_" + state.upper()
        seen = appdb.q("SELECT 1 FROM notifications WHERE related_task_id=? AND "
                       "type=? LIMIT 1", (t["id"], marker), one=True)
        if seen:
            continue
        title = "Overdue" if state == "overdue" else "Due soon"
        notify(t["assignee_id"], marker, title, (t.get("title") or "")[:120],
               task_id=t["id"])
        if state == "overdue":
            for uid in _reviewers_for(t):
                notify(uid, marker, "Team task overdue",
                       (t.get("title") or "")[:120], task_id=t["id"])
        sent += 1
    return sent


# --------------------------------------------------- proactive work logs ----
def log_locked(log, user=None, now=None):
    """True once the row passes the dynamic 48-hour edit lock (spec §10).

    Computed from created_at on every read, so no cronjob has to stamp it.
    """
    created = parse_iso(log.get("created_at"))
    if not created:
        return False
    return (now or utcnow()) > created + timedelta(hours=LOG_LOCK_HOURS)


def can_edit_log(user, log, now=None):
    """(allowed, needs_reason, why). Enforced in the backend, not just the UI."""
    if not user or not log:
        return False, False, "not found"
    if log.get("deleted_at"):
        return False, False, "log deleted"
    owner_of_row = log.get("staff_id") == user.get("user_id")
    if is_manager(user):
        if not is_owner(user) and log.get("staff_id") not in managed_ids(user):
            return False, False, "outside your team"
        return True, log_locked(log, user, now), ""
    if not owner_of_row:
        return False, False, "you can only edit your own log"
    if log_locked(log, user, now):
        return False, False, "locked — older than 48 hours"
    today = utcnow().astimezone(user_tz(user)).date()
    row_day = (log.get("date") or "")[:10]
    if row_day not in (today.isoformat(), (today - timedelta(days=1)).isoformat()):
        return False, False, "staff may only edit Today and Yesterday"
    return True, False, ""


def can_create_log_for(user, day):
    """Staff may only file Today/Yesterday; Manager/Owner any day."""
    if is_manager(user):
        return True
    today = utcnow().astimezone(user_tz(user)).date()
    return (day or "")[:10] in (today.isoformat(),
                                (today - timedelta(days=1)).isoformat())


def create_log(user, **fields):
    _ensure()
    day = (fields.get("date") or "").strip() or local_today(user)
    if not can_create_log_for(user, day):
        return None, "staff may only log Today and Yesterday"
    staff_id = fields.get("staff_id") or user["user_id"]
    if staff_id != user["user_id"] and not is_manager(user):
        return None, "you can only log your own work"
    staff = get_user(staff_id) or user
    now = now_iso()
    lid = appdb.execute(
        "INSERT INTO proactive_work_logs (date, staff_id, role, account_store, "
        "work_type, seed_phrase_keyword, product_type, link_folder_google_drive, "
        "listing_url, design_count, listing_count, status, notes, metadata_json, "
        "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (day, staff_id, team_role(staff), fields.get("account_store") or "",
         fields.get("work_type") or default_work_type(staff),
         fields.get("seed_phrase_keyword") or "",
         fields.get("product_type") or "",
         fields.get("link_folder_google_drive") or "",
         fields.get("listing_url") or "", _int(fields.get("design_count")),
         _int(fields.get("listing_count")), fields.get("status") or "Draft",
         fields.get("notes") or "", json.dumps(fields.get("metadata") or {}),
         now, now))
    return get_log(lid), ""


def _int(v, default=0):
    try:
        return int(float(str(v).strip() or default))
    except (TypeError, ValueError):
        return default


def get_log(lid):
    _ensure()
    return appdb.q("SELECT * FROM proactive_work_logs WHERE id = ?", (lid,), one=True)


LOG_FIELDS = ("account_store", "work_type", "seed_phrase_keyword", "product_type",
              "link_folder_google_drive", "listing_url", "design_count",
              "listing_count", "status", "notes", "date")


def update_log(lid, user, fields, edit_reason=""):
    """Inline-grid save. Enforces the lock, then audits every KPI-sensitive
    field change into proactive_work_log_audit (spec §10)."""
    _ensure()
    log = get_log(lid)
    if not log:
        return None, "log not found"
    allowed, needs_reason, why = can_edit_log(user, log)
    if not allowed:
        return None, why
    if needs_reason and not (edit_reason or "").strip():
        return None, "an edit reason is required for a locked log"
    after_lock = log_locked(log)
    sets, params, audits = [], [], []
    for k in LOG_FIELDS:
        if k not in fields:
            continue
        new = fields[k]
        if k in ("design_count", "listing_count"):
            new = _int(new)
        old = log.get(k)
        if _same(old, new):
            continue
        sets.append(k + "=?")
        params.append(new)
        if k in KPI_SENSITIVE_FIELDS:
            audits.append((k, old, new))
    if not sets:
        return log, ""
    if after_lock:
        sets += ["edited_after_lock_by=?", "edited_after_lock_reason=?"]
        params += [user["user_id"], edit_reason or ""]
    params += [now_iso(), lid]
    appdb.execute("UPDATE proactive_work_logs SET {0}, updated_at=? WHERE id=?"
                  .format(", ".join(sets)), tuple(params))
    for field, old, new in audits:
        _audit_log(lid, user["user_id"], field, old, new, edit_reason, after_lock)
    return get_log(lid), ""


def _audit_log(lid, actor_id, field, old, new, reason, after_lock):
    appdb.execute(
        "INSERT INTO proactive_work_log_audit (log_id, actor_id, field_name, "
        "old_value, new_value, edit_reason, edited_after_lock, created_at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (lid, actor_id, field, None if old is None else str(old)[:400],
         None if new is None else str(new)[:400], (reason or "")[:400],
         1 if after_lock else 0, now_iso()))


def log_audit_trail(lid=None, limit=500):
    _ensure()
    if lid:
        return appdb.q("SELECT * FROM proactive_work_log_audit WHERE log_id=? "
                       "ORDER BY id DESC LIMIT ?", (lid, limit))
    return appdb.q("SELECT * FROM proactive_work_log_audit ORDER BY id DESC "
                   "LIMIT ?", (limit,))


def verify_log(lid, manager, note=""):
    """Manager sign-off — the gate that lets a locked/edited row count for KPI."""
    _ensure()
    if not is_manager(manager):
        return None, "only a Manager or Owner can verify"
    log = get_log(lid)
    if not log:
        return None, "report not found"
    if not is_owner(manager) and log.get("staff_id") not in managed_ids(manager):
        return None, "outside your team"
    now = now_iso()
    appdb.execute("UPDATE proactive_work_logs SET verified_by_manager_id=?, "
                  "verified_at=?, review_state='approved', "
                  "manager_note=COALESCE(?, manager_note), "
                  "updated_at=? WHERE id=?",
                  (manager["user_id"], now, (note or "").strip()[:1000] or None,
                   now, lid))
    if log.get("staff_id"):
        notify(log["staff_id"], "REPORT_VERIFIED", "Daily report verified",
               _report_label(log), metadata={"log_id": lid})
    return get_log(lid), ""


# Manager row actions on a daily report (spec §4). Verify is separate above
# because it also unlocks the row for KPI.
MANAGER_ACTIONS = {
    "clarify": ("REPORT_CLARIFY", "Improvement requested",
                "A manager asked you to improve this daily report"),
    "blocked": ("REPORT_BLOCKED", "Report rejected",
                "A manager rejected this daily report"),
    "note": ("REPORT_NOTE", "Manager note added",
             "A manager left a note on your daily report"),
}

# The verdict shown in the Review column. `note` is neutral and leaves it alone.
REVIEW_STATE_BY_ACTION = {"clarify": "improve", "blocked": "rejected"}


def manager_action(lid, manager, action, note=""):
    """Request clarification / mark blocked / add a manager note.

    None of these rewrite the staff member's numbers — they only attach a note
    (and, for `blocked`, set the status). Changing a count stays an edit, and an
    edit stays audited.
    """
    _ensure()
    if not is_manager(manager):
        return None, "only a Manager or Owner can do that"
    if action not in MANAGER_ACTIONS:
        return None, "unknown action"
    log = get_log(lid)
    if not log:
        return None, "report not found"
    if not is_owner(manager) and log.get("staff_id") not in managed_ids(manager):
        return None, "outside your team"
    note = (note or "").strip()[:1000]
    if action in ("clarify", "note") and not note:
        return None, "a note is required"
    now = now_iso()
    state = REVIEW_STATE_BY_ACTION.get(action)
    if action == "blocked":
        old = log.get("status")
        appdb.execute("UPDATE proactive_work_logs SET status='Blocked', "
                      "review_state=?, manager_note=?, updated_at=? WHERE id=?",
                      (state, note, now, lid))
        # status is KPI-sensitive, so a manager forcing it is audited like any edit
        _audit_log(lid, manager["user_id"], "status", old, "Blocked", note,
                   log_locked(log))
    else:
        appdb.execute("UPDATE proactive_work_logs SET manager_note=?, "
                      "review_state=COALESCE(?, review_state), updated_at=? "
                      "WHERE id=?", (note, state, now, lid))
    ntype, title, _desc = MANAGER_ACTIONS[action]
    if log.get("staff_id"):
        notify(log["staff_id"], ntype, title,
               _report_label(log) + (" — " + note if note else ""),
               metadata={"log_id": lid})
    return get_log(lid), ""


def _report_label(log):
    bits = [(log.get("date") or "")[:10], log.get("work_type") or "",
            log.get("seed_phrase_keyword") or ""]
    return " · ".join(b for b in bits if b)[:120]


def soft_delete_log(lid, actor, reason=""):
    _ensure()
    log = get_log(lid)
    if not log:
        return False, "log not found"
    allowed, _needs, why = can_edit_log(actor, log)
    if not (allowed or is_manager(actor)):
        return False, why or "not allowed"
    appdb.execute("UPDATE proactive_work_logs SET deleted_at=?, deleted_by_id=?, "
                  "delete_reason=?, updated_at=? WHERE id=?",
                  (now_iso(), actor["user_id"], reason or "", now_iso(), lid))
    return True, ""


def list_logs(user=None, staff_id=None, store=None, status=None, work_type=None,
              date_from=None, date_to=None, search=None, include_deleted=False,
              role=None, limit=1000):
    _ensure()
    where, params = [], []
    if not include_deleted:
        where.append("deleted_at IS NULL")
    if user is not None and not is_owner(user):
        if is_manager(user):
            ids = sorted(managed_ids(user))
            where.append("staff_id IN ({0})".format(",".join("?" * len(ids))))
            params += ids
        else:
            where.append("staff_id = ?")
            params.append(user["user_id"])
    if role:
        where.append("role = ?"); params.append(role.upper())
    if staff_id:
        where.append("staff_id = ?"); params.append(staff_id)
    if store:
        where.append("account_store = ?"); params.append(store)
    if status:
        where.append("status = ?"); params.append(status)
    if work_type:
        where.append("work_type = ?"); params.append(work_type)
    if date_from:
        where.append("date >= ?"); params.append(date_from)
    if date_to:
        where.append("date <= ?"); params.append(date_to)
    if search:
        where.append("(seed_phrase_keyword LIKE ? OR notes LIKE ? OR "
                     "product_type LIKE ? OR account_store LIKE ?)")
        params += ["%{0}%".format(search)] * 4
    sql = "SELECT * FROM proactive_work_logs"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY date DESC, id DESC LIMIT ?"
    params.append(limit)
    return appdb.q(sql, tuple(params))


# ------------------------------------------------------- daily reports ----
# What each role reports most days, so the Add form opens on the right choice.
ROLE_DEFAULT_WORK_TYPE = {"SELLER": "Listing created",
                          "DESIGNER": "Design completed"}
DEFAULT_WORK_TYPE = "Other"

# Turning a finished task into a daily-report row (spec §7).
TASK_TYPE_WORK_TYPE = {
    "DESIGN": "Design completed",
    "MOCKUP": "Image set completed",
    "PHOTO_STUDIO": "Image set completed",
    "LISTING_DRAFT": "Listing created",
    "LISTING_UPLOAD": "Listing created",
    "RESEARCH": "Keyword researched",
    "PATTERN_MINER": "Pattern Miner completed",
    "KEYWORD_RERANK": "Re-rank completed",
    "FIX_REQUEST": "Fix completed",
    "SUPPLIER_CHECK": "Competitor analyzed",
    "TRADEMARK_CHECK": "Competitor analyzed",
    "REVIEW_QA": "Other",
}
_DESIGN_WORK = ("Design completed", "Image set completed")
_LISTING_WORK = ("Listing created",)


def default_work_type(user):
    return ROLE_DEFAULT_WORK_TYPE.get(team_role(user), DEFAULT_WORK_TYPE)


def work_type_for_task(task_type):
    return TASK_TYPE_WORK_TYPE.get((task_type or "").upper(), DEFAULT_WORK_TYPE)


def report_prefill_from_task(task):
    """Pre-fill an Add Today Report form from a task the staff member finished.

    Only carries what the task already knows — the counts are a starting point
    the person confirms before saving, never an automatic KPI credit.
    """
    if not task:
        return {}
    wt = work_type_for_task(task.get("task_type"))
    link = task.get("drive_folder") or ""
    if not link:
        for l in (task.get("links") or []):
            if l.get("url"):
                link = l["url"]
                break
    listing_url = ""
    for l in (task.get("links") or []):
        url = (l.get("url") or "")
        if "etsy.com" in url.lower():
            listing_url = url
            break
    return {
        "work_type": wt,
        "seed_phrase_keyword": task.get("related_keyword") or "",
        "account_store": task.get("related_store") or "",
        "link_folder_google_drive": link,
        "listing_url": listing_url,
        "design_count": 1 if wt in _DESIGN_WORK else 0,
        "listing_count": 1 if wt in _LISTING_WORK else 0,
        "notes": "From task #{0}: {1}".format(task.get("id"),
                                              (task.get("title") or "")[:80]),
        "task_id": task.get("id"),
    }


def report_for_day(staff_id, day):
    _ensure()
    return appdb.q("SELECT * FROM proactive_work_logs WHERE staff_id=? AND date=? "
                   "AND deleted_at IS NULL ORDER BY id", (staff_id, day))


def has_report_today(user, now=None):
    day = (now or utcnow()).astimezone(user_tz(user)).date().isoformat()
    return bool(report_for_day(user["user_id"], day))


def missing_report_warning(user, now=None):
    """True once it's past the warn hour locally and this person hasn't filed.

    Staff-facing nudge; the same threshold drives the manager's bottleneck alert.
    """
    if not is_staff(user) or user.get("day_off") or not user_active(user):
        return False
    now = now or utcnow()
    local = now.astimezone(user_tz(user))
    if local.hour + local.minute / 60.0 < THRESHOLDS["daily_log_warn_hour"]:
        return False
    return not has_report_today(user, now)


def staff_missing_report(user, now=None):
    """Everyone in scope who owes a daily report for their local today."""
    _ensure()
    now = now or utcnow()
    out = []
    for p in visible_staff(user):
        if not is_staff(p) or not user_active(p) or p.get("day_off"):
            continue
        if not has_report_today(p, now):
            out.append(p)
    return out


def daily_report_summary(user, date_from=None, date_to=None, now=None, **filters):
    """Widgets for the Daily Reports page and the Team Home card (spec §5/§6).

    Submitted = what staff typed. Verified = not edited after the 48h lock, or
    signed off by a manager. Both are reported, never merged.
    """
    _ensure()
    now = now or utcnow()
    today = local_today(user)
    rows = list_logs(user=user, date_from=date_from, date_to=date_to, **filters)
    sub_d = sub_l = ver_d = ver_l = 0
    for r in rows:
        a, b, c, d = log_counts_for_kpi(r)
        sub_d += a; sub_l += b; ver_d += c; ver_l += d
    today_rows = [r for r in rows if (r.get("date") or "")[:10] == today]
    if date_from is None and date_to is None:
        today_rows = [r for r in list_logs(user=user, date_from=today, date_to=today)]
    people = [p for p in visible_staff(user) if is_staff(p)]
    sellers = [p for p in people if team_role(p) == "SELLER"]
    designers = [p for p in people if team_role(p) == "DESIGNER"]
    missing = staff_missing_report(user, now)
    return {
        "reports": len(rows),
        "reports_today": len(today_rows),
        "designs_submitted": sub_d, "designs_verified": ver_d,
        "listings_submitted": sub_l, "listings_verified": ver_l,
        "designs_today": sum(_int(r.get("design_count")) for r in today_rows),
        "listings_today": sum(_int(r.get("listing_count")) for r in today_rows),
        "blocked": sum(1 for r in rows if (r.get("status") or "") == "Blocked"),
        "waiting_review": sum(1 for r in rows
                              if (r.get("status") or "") == "Waiting Review"),
        "edited_after_lock": sum(1 for r in rows if r.get("edited_after_lock_by")),
        "verified_rows": sum(1 for r in rows if r.get("verified_by_manager_id")),
        "missing_today": missing,
        "missing_today_n": len(missing),
        "avg_listings_per_seller": (round(sub_l / float(len(sellers)), 1)
                                    if sellers else 0.0),
        "avg_designs_per_designer": (round(sub_d / float(len(designers)), 1)
                                     if designers else 0.0),
    }


def missing_report_days(person, date_from=None, date_to=None, now=None):
    """How many local days in the window the person filed nothing (day off and
    days before their joined_at don't count against them)."""
    now = now or utcnow()
    tzinfo = user_tz(person)
    end = now.astimezone(tzinfo).date()
    start = end - timedelta(days=6)
    if date_from:
        try:
            start = datetime.fromisoformat(date_from[:10]).date()
        except ValueError:
            pass
    if date_to:
        try:
            end = datetime.fromisoformat(date_to[:10]).date()
        except ValueError:
            pass
    if person.get("day_off"):
        return 0
    joined = (person.get("joined_at") or "")[:10]
    filed = {(r.get("date") or "")[:10]
             for r in list_logs(staff_id=person["user_id"],
                                date_from=start.isoformat(),
                                date_to=end.isoformat())}
    misses, day = 0, start
    while day <= end and day < now.astimezone(tzinfo).date():
        iso_day = day.isoformat()
        if not (joined and iso_day < joined) and iso_day not in filed:
            misses += 1
        day += timedelta(days=1)
    return misses


def log_counts_for_kpi(log):
    """Raw vs verified split (spec §10/§13).

    A row counts as *verified* when it was never edited after the 48h lock, or
    when a Manager explicitly verified it.
    """
    raw_d, raw_l = _int(log.get("design_count")), _int(log.get("listing_count"))
    edited = bool(log.get("edited_after_lock_by"))
    verified = bool(log.get("verified_by_manager_id")) or not edited
    return raw_d, raw_l, (raw_d if verified else 0), (raw_l if verified else 0)


# ------------------------------------------------------------ bottlenecks ----
def _alert(atype, severity, who, count, threshold, action, link=""):
    return {"alert_type": atype, "severity": severity, "who": who, "count": count,
            "threshold": threshold, "action": action, "link": link}


def bottlenecks(user=None, now=None):
    """Every alert from spec §12, computed from live task/log state."""
    _ensure()
    now = now or utcnow()
    tasks = list_tasks(user=user)
    people = {u["user_id"]: u for u in visible_staff(user)}
    out = []

    # --- Manager Review Backlog ---
    review = [t for t in tasks if t["status"] == "REVIEW"]
    per_mgr = {}
    for t in review:
        per_mgr.setdefault(t.get("reviewer_manager_id"), []).append(t)
    for mid, items in per_mgr.items():
        if not mid:
            continue
        name = (people.get(mid) or get_user(mid) or {}).get("display_name") or "Manager"
        oldest_h = max((_hours_since(t.get("updated_at"), now) for t in items),
                       default=0)
        n = len(items)
        if n > THRESHOLDS["manager_review_crit"] or \
                oldest_h > THRESHOLDS["manager_oldest_review_hours"]:
            out.append(_alert("Manager Review Backlog", "critical", name, n,
                              THRESHOLDS["manager_review_crit"],
                              "Re-assign reviews or clear the oldest first "
                              "({0}h waiting)".format(int(oldest_h)),
                              "/team/ops/review"))
        elif n > THRESHOLDS["manager_review_warn"]:
            out.append(_alert("Manager Review Backlog", "warning", name, n,
                              THRESHOLDS["manager_review_warn"],
                              "Block 30 minutes to clear the review queue",
                              "/team/ops/review"))

    # --- Staff context switching + overdue load ---
    for uid, person in people.items():
        if not is_staff(person):
            continue
        mine = [t for t in tasks if t.get("assignee_id") == uid]
        prog = sum(1 for t in mine if t["status"] == "IN_PROGRESS")
        od = sum(1 for t in mine if is_overdue(t, now))
        name = person.get("display_name") or "Staff"
        link = "/team/ops/board?assignee={0}".format(uid)
        if prog > THRESHOLDS["staff_inprogress_crit"]:
            out.append(_alert("Staff Context Switching", "critical", name, prog,
                              THRESHOLDS["staff_inprogress_crit"],
                              "Too many open threads — park some back to To-do", link))
        elif prog > THRESHOLDS["staff_inprogress_warn"]:
            out.append(_alert("Staff Context Switching", "warning", name, prog,
                              THRESHOLDS["staff_inprogress_warn"],
                              "Ask them to finish one before starting another", link))
        if od > THRESHOLDS["staff_overdue_crit"]:
            out.append(_alert("Staff Overdue Load", "critical", name, od,
                              THRESHOLDS["staff_overdue_crit"],
                              "Re-plan deadlines or re-assign work today", link))
        elif od > THRESHOLDS["staff_overdue_warn"]:
            out.append(_alert("Staff Overdue Load", "warning", name, od,
                              THRESHOLDS["staff_overdue_warn"],
                              "Check what is blocking them", link))

    # --- Team review queue + overdue share ---
    n_review = len(review)
    if n_review > THRESHOLDS["team_review_crit"]:
        out.append(_alert("Team Review Queue", "critical", "Team", n_review,
                          THRESHOLDS["team_review_crit"],
                          "Add a second reviewer today", "/team/ops/review"))
    elif n_review > THRESHOLDS["team_review_warn"]:
        out.append(_alert("Team Review Queue", "warning", "Team", n_review,
                          THRESHOLDS["team_review_warn"],
                          "Review throughput is falling behind", "/team/ops/review"))
    active = [t for t in tasks if t["status"] in ACTIVE_STATUSES]
    if active:
        pct = round(100.0 * sum(1 for t in active if is_overdue(t, now)) / len(active), 1)
        if pct > THRESHOLDS["team_overdue_pct_crit"]:
            out.append(_alert("Team Overdue Share", "critical", "Team", pct,
                              THRESHOLDS["team_overdue_pct_crit"],
                              "Stop new assignments until the backlog clears",
                              "/team/ops/board?due=overdue"))
        elif pct > THRESHOLDS["team_overdue_pct_warn"]:
            out.append(_alert("Team Overdue Share", "warning", "Team", pct,
                              THRESHOLDS["team_overdue_pct_warn"],
                              "Re-plan this week's deadlines",
                              "/team/ops/board?due=overdue"))

    # --- Missing daily logs ---
    for uid, person in people.items():
        if not is_staff(person) or not user_active(person):
            continue
        if person.get("day_off"):
            continue
        local = now.astimezone(user_tz(person))
        hour = local.hour + local.minute / 60.0
        today = local.date().isoformat()
        has = appdb.q("SELECT 1 FROM proactive_work_logs WHERE staff_id=? AND "
                      "date=? AND deleted_at IS NULL LIMIT 1", (uid, today), one=True)
        if has:
            continue
        name = person.get("display_name") or "Staff"
        if hour >= THRESHOLDS["daily_log_crit_hour"]:
            out.append(_alert("Missing Daily Log", "critical", name, 0,
                              THRESHOLDS["daily_log_crit_hour"],
                              "No work log for today — ask before end of day",
                              "/team/ops/reports?view=team&staff={0}".format(uid)))
        elif hour >= THRESHOLDS["daily_log_warn_hour"]:
            out.append(_alert("Missing Daily Log", "warning", name, 0,
                              THRESHOLDS["daily_log_warn_hour"],
                              "Remind them to file today's log",
                              "/team/ops/reports?view=team&staff={0}".format(uid)))
    rank = {"critical": 0, "warning": 1, "info": 2}
    out.sort(key=lambda a: (rank.get(a["severity"], 3), a["alert_type"]))
    return out


def _hours_since(ts, now=None):
    dt = parse_iso(ts)
    if not dt:
        return 0.0
    return max(0.0, ((now or utcnow()) - dt).total_seconds() / 3600.0)


# -------------------------------------------------------------- analytics ----
def analytics(user=None, date_from=None, date_to=None, staff_id=None, role=None,
              store=None, task_type=None, now=None):
    """Team Analytics widgets + leaderboard (spec §13)."""
    _ensure()
    now = now or utcnow()
    tasks = list_tasks(user=user, task_type=task_type, store=store,
                       assignee_id=staff_id, since=date_from, until=date_to)
    logs = list_logs(user=user, staff_id=staff_id, store=store,
                     date_from=(date_from or "")[:10] or None,
                     date_to=(date_to or "")[:10] or None)
    people = {u["user_id"]: u for u in visible_staff(user)}
    if role:
        people = {k: v for k, v in people.items() if team_role(v) == role.upper()}

    done = [t for t in tasks if t["status"] == "DONE"]
    on_time = [t for t in done if _finished_on_time(t)]
    overdue = [t for t in tasks if is_overdue(t, now)]
    fixes = _fix_counts([t["id"] for t in tasks])
    widgets = {
        "created": len(tasks),
        "completed": len(done),
        "overdue": len(overdue),
        "on_time_rate": _pct(len(on_time), len(done)),
        "designs": sum(_int(l.get("design_count")) for l in logs),
        "listings": sum(_int(l.get("listing_count")) for l in logs),
        "keywords_researched": sum(1 for l in logs
                                   if l.get("work_type") == "Keyword researched"),
        "pattern_runs": sum(1 for t in done if t["task_type"] == "PATTERN_MINER"),
        "rerank_reviewed": sum(1 for t in done if t["task_type"] == "KEYWORD_RERANK"),
        "fix_rate": _pct(sum(fixes.values()), max(len(tasks), 1)),
        "avg_review_hours": _avg([_review_hours(t) for t in done]),
        "avg_completion_hours": _avg([_hours_between(t.get("created_at"),
                                                     t.get("completed_at"))
                                      for t in done]),
    }
    board = [_leaderboard_row(p, tasks, logs, fixes, now) for p in people.values()]
    board.sort(key=lambda r: -r["quality_score"])
    return {"widgets": widgets, "leaderboard": board,
            "task_count": len(tasks), "log_count": len(logs)}


def _pct(part, whole):
    return round(100.0 * part / whole, 1) if whole else 0.0


def _avg(values):
    vals = [v for v in values if v is not None]
    return round(sum(vals) / len(vals), 1) if vals else 0.0


def _hours_between(a, b):
    da, db = parse_iso(a), parse_iso(b)
    if not da or not db:
        return None
    return max(0.0, (db - da).total_seconds() / 3600.0)


def _finished_on_time(t):
    due, done = parse_iso(t.get("due_at")), parse_iso(t.get("completed_at"))
    if not done:
        return False
    return True if not due else done <= due


def _review_hours(t):
    """Hours a finished task spent sitting in Review, from the activity log."""
    rows = appdb.q("SELECT action, new_value, created_at FROM task_activity_log "
                   "WHERE task_id=? AND action='status' ORDER BY id", (t["id"],))
    entered = None
    for r in rows:
        if r["new_value"] == "REVIEW":
            entered = r["created_at"]
        elif r["new_value"] in ("DONE", "FIX_REQUESTED") and entered:
            return _hours_between(entered, r["created_at"])
    return None


def _fix_counts(task_ids):
    _ensure()
    if not task_ids:
        return {}
    marks = ",".join("?" * len(task_ids))
    rows = appdb.q(
        "SELECT task_id, COUNT(*) n FROM task_activity_log WHERE task_id IN ({0}) "
        "AND action='status' AND new_value='FIX_REQUESTED' GROUP BY task_id"
        .format(marks), tuple(task_ids))
    return {r["task_id"]: r["n"] for r in rows}


def _leaderboard_row(person, tasks, logs, fixes, now):
    uid = person["user_id"]
    mine = [t for t in tasks if t.get("assignee_id") == uid]
    my_logs = [l for l in logs if l.get("staff_id") == uid]
    done = [t for t in mine if t["status"] == "DONE"]
    on_time = [t for t in done if _finished_on_time(t)]
    overdue_n = sum(1 for t in mine if is_overdue(t, now))
    fix_n = sum(fixes.get(t["id"], 0) for t in mine)
    reviewed = [t for t in mine if t["status"] in ("DONE", "REVIEW", "FIX_REQUESTED")]
    raw_d = raw_l = ver_d = ver_l = 0
    for l in my_logs:
        a, b, c, d = log_counts_for_kpi(l)
        raw_d += a; raw_l += b; ver_d += c; ver_l += d
    edited = sum(1 for l in my_logs if l.get("edited_after_lock_by"))

    on_time_rate = _pct(len(on_time), len(done)) / 100.0
    approval_rate = _pct(len(done), len(reviewed)) / 100.0 if reviewed else 0.0
    target = max(_int(person.get("target_designs")) +
                 _int(person.get("target_listings")), 1)
    volume_score = min(1.0, (ver_d + ver_l) / float(target))
    low_fix = 1.0 - min(1.0, fix_n / float(max(len(mine), 1)))
    integrity = log_integrity_score(person, my_logs, now) / 100.0
    quality = round(100 * (on_time_rate * 0.25 + approval_rate * 0.25
                           + volume_score * 0.20 + low_fix * 0.20
                           + integrity * 0.10), 1)
    return {
        "staff_id": uid, "name": person.get("display_name") or "—",
        "role": team_role(person), "active": user_active(person),
        "tasks_done_approved": len(done),
        "on_time_pct": round(on_time_rate * 100, 1),
        "overdue": overdue_n,
        "design_raw": raw_d, "design_verified": ver_d,
        "listing_raw": raw_l, "listing_verified": ver_l,
        "log_count": len(my_logs), "logs_edited_after_lock": edited,
        "fix_requests": fix_n, "quality_score": quality,
        "missing_report_days": missing_report_days(person, now=now),
        "verified_rows": sum(1 for l in my_logs if l.get("verified_by_manager_id")),
    }


def log_integrity_score(person, my_logs, now=None):
    """100 when nothing was edited after lock and daily logs were filed."""
    now = now or utcnow()
    score = 100.0
    edited = sum(1 for l in my_logs if l.get("edited_after_lock_by")
                 and not l.get("verified_by_manager_id"))
    score -= min(50.0, edited * 10.0)
    days = {(l.get("date") or "")[:10] for l in my_logs}
    local_now = now.astimezone(user_tz(person))
    joined = (person.get("joined_at") or "")[:10]
    expected = 0
    missing = 0
    for back in range(1, 8):                    # the last 7 completed days
        d = (local_now.date() - timedelta(days=back)).isoformat()
        if joined and d < joined:               # don't penalise days before hire
            continue
        expected += 1
        if d not in days:
            missing += 1
    if expected:
        score -= min(50.0, 50.0 * missing / expected)
    return max(0.0, round(score, 1))


def rebuild_kpi_daily(day=None, user=None):
    """Aggregate one day into staff_kpi_daily (idempotent upsert)."""
    _ensure()
    day = (day or local_today())[:10]
    now = now_iso()
    n = 0
    for person in visible_staff(user) if user else list_team(include_inactive=True):
        uid = person["user_id"]
        tasks = list_tasks(assignee_id=uid)
        done = [t for t in tasks if t["status"] == "DONE"
                and (t.get("completed_at") or "")[:10] == day]
        on_time = [t for t in done if _finished_on_time(t)]
        logs = list_logs(staff_id=uid, date_from=day, date_to=day)
        raw_d = raw_l = ver_d = ver_l = 0
        for l in logs:
            a, b, c, d2 = log_counts_for_kpi(l)
            raw_d += a; raw_l += b; ver_d += c; ver_l += d2
        fixes = _fix_counts([t["id"] for t in tasks])
        row = _leaderboard_row(person, tasks, logs, fixes, utcnow())
        appdb.execute(
            "INSERT INTO staff_kpi_daily (date, staff_id, tasks_done, tasks_overdue, "
            "on_time_rate, design_count_raw, design_count_verified, "
            "listing_count_raw, listing_count_verified, proactive_log_count, "
            "fix_request_count, logs_edited_after_lock, quality_score, created_at, "
            "updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(date, staff_id) DO UPDATE SET tasks_done=excluded.tasks_done, "
            "tasks_overdue=excluded.tasks_overdue, on_time_rate=excluded.on_time_rate, "
            "design_count_raw=excluded.design_count_raw, "
            "design_count_verified=excluded.design_count_verified, "
            "listing_count_raw=excluded.listing_count_raw, "
            "listing_count_verified=excluded.listing_count_verified, "
            "proactive_log_count=excluded.proactive_log_count, "
            "fix_request_count=excluded.fix_request_count, "
            "logs_edited_after_lock=excluded.logs_edited_after_lock, "
            "quality_score=excluded.quality_score, updated_at=excluded.updated_at",
            (day, uid, len(done), row["overdue"], _pct(len(on_time), len(done)),
             raw_d, ver_d, raw_l, ver_l, len(logs), row["fix_requests"],
             row["logs_edited_after_lock"], row["quality_score"], now, now))
        n += 1
    return n


# ------------------------------------------------------------- home queues ----
def home_queues(user, now=None):
    """The action queues on Team Home — small lists, never a giant table."""
    _ensure()
    now = now or utcnow()
    uid = user["user_id"]
    scope = list_tasks(user=user)
    mine = [t for t in scope if t.get("assignee_id") == uid]
    today = local_today(user)

    def due_today(t):
        return (to_local(t.get("due_at"), user, "%Y-%m-%d") == today
                and t["status"] in ACTIVE_STATUSES)

    review = [t for t in scope if t["status"] == "REVIEW"]
    if not is_manager(user):
        review = [t for t in review if t.get("assignee_id") == uid]
    done_today = [t for t in scope if t["status"] == "DONE"
                  and to_local(t.get("completed_at"), user, "%Y-%m-%d") == today]
    no_log = []
    if is_manager(user):
        for p in visible_staff(user):
            if not is_staff(p) or not user_active(p) or p.get("day_off"):
                continue
            d = utcnow().astimezone(user_tz(p)).date().isoformat()
            hit = appdb.q("SELECT 1 FROM proactive_work_logs WHERE staff_id=? AND "
                          "date=? AND deleted_at IS NULL LIMIT 1",
                          (p["user_id"], d), one=True)
            if not hit:
                no_log.append(p)
    unassigned = [t for t in scope if not t.get("assignee_id")
                  and t["status"] in ACTIVE_STATUSES] if is_manager(user) else []
    reports = daily_report_summary(user, now=now)
    return {
        "reports": reports,
        "my_report_missing": missing_report_warning(user, now),
        "my_reports_today": len(report_for_day(uid, today)),
        "my_overdue": [t for t in mine if is_overdue(t, now)],
        "due_today": [t for t in mine if due_today(t)],
        "waiting_review": review,
        "fix_requested": [t for t in mine if t["status"] == "FIX_REQUESTED"],
        "done_today": done_today,
        "no_log": no_log,
        "unassigned": unassigned,
        "top_performers": _top_performers(user, now),
        "alerts": bottlenecks(user, now),
    }


def _top_performers(user, now=None):
    now = now or utcnow()
    since = iso(now - timedelta(days=7))
    data = analytics(user=user, date_from=since)
    return [r for r in data["leaderboard"] if r["tasks_done_approved"] or
            r["design_verified"] or r["listing_verified"]][:5]


# --------------------------------------------------------------- exports ----
TASK_CSV_COLS = ["id", "title", "task_type", "status", "priority", "assignee",
                 "assigned_by", "related_keyword", "related_store",
                 "related_opportunity_id", "related_listing_id", "due_at_utc",
                 "completed_at_utc", "checklist_completed_count",
                 "checklist_total_count", "created_at_utc", "deleted_at_utc",
                 "delete_reason"]

LOG_CSV_COLS = ["id", "date", "staff", "role", "account_store", "work_type",
                "seed_phrase_keyword", "product_type", "link_folder_google_drive",
                "listing_url", "design_count", "listing_count", "status", "notes",
                "edited_after_lock_by", "edited_after_lock_reason",
                "verified_by_manager_id", "verified_at", "manager_note",
                "review_state",
                "created_at_utc", "updated_at_utc", "deleted_at_utc",
                "delete_reason"]


def tasks_csv_rows(user, include_deleted=False):
    names = {u["user_id"]: u.get("display_name") for u in list_team(include_inactive=True)}
    for t in list_tasks(user=user, include_deleted=include_deleted):
        yield {"id": t["id"], "title": t["title"], "task_type": t["task_type"],
               "status": t["status"], "priority": t["priority"],
               "assignee": names.get(t.get("assignee_id"), ""),
               "assigned_by": names.get(t.get("assigned_by_id"), ""),
               "related_keyword": t.get("related_keyword") or "",
               "related_store": t.get("related_store") or "",
               "related_opportunity_id": t.get("related_opportunity_id") or "",
               "related_listing_id": t.get("related_listing_id") or "",
               "due_at_utc": t.get("due_at") or "",
               "completed_at_utc": t.get("completed_at") or "",
               "checklist_completed_count": t.get("checklist_completed_count") or 0,
               "checklist_total_count": t.get("checklist_total_count") or 0,
               "created_at_utc": t.get("created_at") or "",
               "deleted_at_utc": t.get("deleted_at") or "",
               "delete_reason": t.get("delete_reason") or ""}


def logs_csv_rows(user, include_deleted=False, **filters):
    names = {u["user_id"]: u.get("display_name") for u in list_team(include_inactive=True)}
    for l in list_logs(user=user, include_deleted=include_deleted, **filters):
        row = {c: l.get(c, "") for c in LOG_CSV_COLS}
        row.update({"staff": names.get(l.get("staff_id"), ""),
                    "created_at_utc": l.get("created_at") or "",
                    "updated_at_utc": l.get("updated_at") or "",
                    "deleted_at_utc": l.get("deleted_at") or ""})
        yield row


# ------------------------------------------------------------ integration ----
# Deep-link helper so Rank / Pattern Miner / Re-rank / Build / Learn can hand
# work to the team without any of them importing the UI layer.
def new_task_url(task_type="OTHER", title="", keyword="", opportunity_id="",
                 listing_id="", store=""):
    from urllib.parse import urlencode
    q = {k: v for k, v in (("type", task_type), ("title", title),
                           ("keyword", keyword), ("opportunity", opportunity_id),
                           ("listing", listing_id), ("store", store)) if v}
    return "/team/ops/task/new" + ("?" + urlencode(q) if q else "")


def create_followups_for_listing(listing_id, keyword, assignee_id, assigned_by_id,
                                 store="", now=None):
    """Day 3 + Day 7 follow-up tasks from Learn. Internal reminders only — this
    never touches Etsy, it just puts the check on somebody's board."""
    _ensure()
    now = now or utcnow()
    assignee = get_user(assignee_id) if assignee_id else None
    tzinfo = user_tz(assignee)
    hour = _setting_int("default_deadline_hour", DEFAULT_DUE_HOUR)
    made = []
    for days, ttype, label in ((3, "DAY3_FOLLOWUP", "Day 3"),
                               (7, "DAY7_FOLLOWUP", "Day 7")):
        day = now.astimezone(tzinfo).date() + timedelta(days=days)
        due = iso(datetime.combine(day, time(hour, 0), tzinfo=tzinfo))
        made.append(create_task(
            "{0} check — {1}".format(label, keyword or listing_id),
            assignee_id=assignee_id, assigned_by_id=assigned_by_id,
            task_type=ttype, priority="MEDIUM", due_at=due,
            related_listing_id=listing_id, related_keyword=keyword,
            related_store=store,
            expected_output="Log views / favourites / carts and apply the "
                            "recommendation."))
    return made


# The Team OS is an internal execution board. It never publishes, never signs in
# to Etsy and never calls the Seller API — this constant is asserted by tests.
PUBLISH_AUTOMATION = False


# ---------------------------------------------------- system health check ----
# What a healthy install looks like. The health page diffs the live DB against
# these lists, so an upgrade that adds a table/index/column but never runs on a
# given box shows up as a red row instead of a mystery 500 at 2am.
REQUIRED_TABLES = ["team_tasks", "task_comments", "task_activity_log",
                   "proactive_work_logs", "proactive_work_log_audit",
                   "notifications", "staff_kpi_daily", "team_settings",
                   "team_dropdowns"]

REQUIRED_INDEXES = {
    "team_tasks": ["idx_team_tasks_assignee_id", "idx_team_tasks_status",
                   "idx_team_tasks_due_at", "idx_team_tasks_assignee_status",
                   "idx_team_tasks_status_due_at", "idx_team_tasks_assigned_by_id",
                   "idx_team_tasks_reviewer_manager_id",
                   "idx_team_tasks_related_opportunity_id",
                   "idx_team_tasks_deleted_at"],
    "proactive_work_logs": ["idx_work_logs_staff_id", "idx_work_logs_date",
                            "idx_work_logs_staff_date", "idx_work_logs_status",
                            "idx_work_logs_account_store",
                            "idx_work_logs_deleted_at"],
    "notifications": ["idx_notifications_user_read", "idx_notifications_created_at"],
    "task_activity_log": ["idx_activity_task_id", "idx_activity_actor_id",
                          "idx_activity_created_at"],
    "task_comments": ["idx_comments_task_id", "idx_comments_created_at"],
    "proactive_work_log_audit": ["idx_work_log_audit_log_id",
                                 "idx_work_log_audit_actor_id",
                                 "idx_work_log_audit_created_at"],
    "staff_kpi_daily": ["idx_kpi_daily_staff_date"],
}

# Partial indexes on the active rows — every dashboard view filters
# deleted_at IS NULL, so these are what keep Home/Board off a full scan.
PARTIAL_INDEXES = ["idx_team_tasks_active_status_due",
                   "idx_team_tasks_active_assignee_status",
                   "idx_work_logs_active_staff_date"]

# JSON columns that should carry a CHECK(json_valid(...)) guard on SQLite.
JSON_COLUMNS = {
    "team_tasks": ["links_json", "checklist_json", "metadata_json"],
    "task_comments": ["attachments_json", "mentions_json"],
    "task_activity_log": ["metadata_json"],
    "proactive_work_logs": ["metadata_json"],
    "notifications": ["metadata_json"],
}


def _row(name, state, detail=""):
    return {"name": name, "state": state, "detail": detail}


def _objects(kind):
    return {r["name"] for r in appdb.q(
        "SELECT name FROM sqlite_master WHERE type = ?", (kind,))}


def _table_sql(name):
    r = appdb.q("SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
                (name,), one=True)
    return ((r or {}).get("sql") or "")


def _count(sql, params=()):
    try:
        r = appdb.q(sql, params, one=True)
        return int((r or {}).get("n") or 0)
    except Exception:  # noqa: BLE001 - a missing table must not break the page
        return None


def health():
    """Schema + data self-check for the Owner's pre-deploy page.

    Read-only: it inspects sqlite_master and counts rows. It never creates,
    migrates or deletes anything — in particular it does NOT move legacy tasks
    into the Team OS, it only reports that both systems are live.
    """
    _ensure()
    tables, indexes = _objects("table"), _objects("index")
    sections = []

    # --- tables ---
    rows = [_row(t, "ok" if t in tables else "fail",
                 "present" if t in tables else "MISSING")
            for t in REQUIRED_TABLES]
    sections.append({"key": "tables", "title": "Team Ops tables", "rows": rows})

    # --- indexes ---
    rows = []
    for table in sorted(REQUIRED_INDEXES):
        for idx in REQUIRED_INDEXES[table]:
            rows.append(_row(idx, "ok" if idx in indexes else "fail",
                             table + (" · present" if idx in indexes
                                      else " · MISSING")))
    for idx in PARTIAL_INDEXES:
        rows.append(_row(idx, "ok" if idx in indexes else "warn",
                         "partial (deleted_at IS NULL) · "
                         + ("present" if idx in indexes else "missing — "
                            "dashboard queries fall back to a wider scan")))
    sections.append({"key": "indexes", "title": "Indexes", "rows": rows})

    # --- users columns ---
    have = set()
    try:
        have = {r["name"] for r in appdb.q("PRAGMA table_info(users)")}
    except Exception:  # noqa: BLE001
        pass
    rows = [_row(col, "ok" if col in have else "fail",
                 "present" if col in have else "MISSING — run init_schema()")
            for col, _decl in _USER_COLS]
    sections.append({"key": "user_columns", "title": "users table columns",
                     "rows": rows})

    # --- JSON validation ---
    rows = [_row("SQLite JSON1 extension", "ok" if _JSON1 else "warn",
                 "available — json_valid()/json_set() in use" if _JSON1 else
                 "not available — JSON stored as plain TEXT, single-item "
                 "checklist writes fall back to read-modify-write")]
    for table in sorted(JSON_COLUMNS):
        sql = _table_sql(table)
        for col in JSON_COLUMNS[table]:
            guarded = ("json_valid(" + col + ")") in sql
            if guarded:
                rows.append(_row(table + "." + col, "ok", "CHECK(json_valid) enforced"))
            elif not _JSON1:
                rows.append(_row(table + "." + col, "warn",
                                 "no CHECK — this SQLite build has no JSON1"))
            else:
                rows.append(_row(table + "." + col, "fail",
                                 "CHECK(json_valid) MISSING — table predates the "
                                 "constraint; recreate it to enforce"))
    sections.append({"key": "json", "title": "JSON validation (SQLite fallback)",
                     "rows": rows})

    # --- safety ---
    safe = PUBLISH_AUTOMATION is False
    sections.append({"key": "safety", "title": "Safety", "rows": [
        _row("PUBLISH_AUTOMATION", "ok" if safe else "fail", str(PUBLISH_AUTOMATION)
             + (" — no publish path exists" if safe else " — MUST be False")),
        _row("Etsy Seller API", "ok", "not called — Team Ops is internal only"),
        _row("Auto-publish", "ok", "no code path publishes a listing"),
    ]})

    for s in sections:
        states = [r["state"] for r in s["rows"]]
        s["state"] = ("fail" if "fail" in states
                      else "warn" if "warn" in states else "ok")

    counts = {
        "tasks_active": _count("SELECT COUNT(*) n FROM team_tasks WHERE "
                               "deleted_at IS NULL"),
        "tasks_open": _count("SELECT COUNT(*) n FROM team_tasks WHERE deleted_at "
                             "IS NULL AND status IN ('TODO','IN_PROGRESS','REVIEW',"
                             "'FIX_REQUESTED')"),
        "tasks_deleted": _count("SELECT COUNT(*) n FROM team_tasks WHERE "
                                "deleted_at IS NOT NULL"),
        "logs_active": _count("SELECT COUNT(*) n FROM proactive_work_logs WHERE "
                              "deleted_at IS NULL"),
        "logs_deleted": _count("SELECT COUNT(*) n FROM proactive_work_logs WHERE "
                               "deleted_at IS NOT NULL"),
        "audit_rows": _count("SELECT COUNT(*) n FROM proactive_work_log_audit"),
        "notifications": _count("SELECT COUNT(*) n FROM notifications"),
        "notifications_unread": _count("SELECT COUNT(*) n FROM notifications WHERE "
                                       "read_at IS NULL"),
        "comments": _count("SELECT COUNT(*) n FROM task_comments"),
        "activity_rows": _count("SELECT COUNT(*) n FROM task_activity_log"),
        "kpi_rows": _count("SELECT COUNT(*) n FROM staff_kpi_daily"),
    }

    legacy_n = _count("SELECT COUNT(*) n FROM tasks") if "tasks" in tables else 0
    both = bool(legacy_n) and bool(counts["tasks_active"])
    legacy = {
        "table_present": "tasks" in tables,
        "legacy_rows": legacy_n or 0,
        "teamops_rows": counts["tasks_active"] or 0,
        "both_active": both,
        "label": "Legacy task system still active during rollout." if both else "",
        "note": ("The old /admin/tasks + /me/tasks board still holds "
                 + str(legacy_n or 0) + " row(s). Nothing is migrated "
                 "automatically — the two systems run side by side until you "
                 "decide to retire the old one."),
    }

    overall = ("fail" if any(s["state"] == "fail" for s in sections)
               else "warn" if (any(s["state"] == "warn" for s in sections) or both)
               else "ok")
    return {"overall": overall, "sections": sections, "counts": counts,
            "legacy": legacy, "json1": _JSON1,
            "db_path": str(appdb.DB_PATH.resolve()),
            "publish_automation": PUBLISH_AUTOMATION}
