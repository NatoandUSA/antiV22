"""Team task + review system (SQLite via src/appdb.py)."""
from datetime import datetime, timezone

from src import appdb

TASK_TYPES = ["KEYWORD_RESEARCH", "SPY_RESEARCH", "SUPPLIER_CHECK",
              "COMPETITOR_AUDIT", "TRADEMARK_CHECK", "LISTING_DRAFT",
              "DESIGN_BRIEF", "FIRST_IMAGE", "MOCKUP", "PDF_EXPORT",
              "FEEDBACK_DAY3", "FEEDBACK_DAY7", "MANAGER_REVIEW", "FIX_REQUIRED"]
PRIORITIES = ["LOW", "MEDIUM", "HIGH", "URGENT"]
STATUSES = ["TODO", "IN_PROGRESS", "BLOCKED", "READY_FOR_REVIEW", "APPROVED",
            "REJECTED", "DONE"]
REVIEW_STATUSES = ["NOT_REVIEWED", "APPROVED", "NEEDS_FIX", "REJECTED"]


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def create_task(title, assigned_to_user_id=None, assigned_by_user_id=None,
                task_type=None, priority="MEDIUM", description="", role_target="",
                related_keyword="", related_workspace_id="", related_listing_id="",
                related_supplier="", due_date=""):
    priority = (priority or "MEDIUM").upper()
    if priority not in PRIORITIES:
        priority = "MEDIUM"
    now = _now()
    tid = appdb.execute(
        "INSERT INTO tasks (title, description, assigned_to_user_id, "
        "assigned_by_user_id, role_target, related_keyword, related_workspace_id, "
        "related_listing_id, related_supplier, task_type, priority, status, "
        "due_date, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (title, description, assigned_to_user_id, assigned_by_user_id, role_target,
         related_keyword, related_workspace_id, related_listing_id, related_supplier,
         task_type, priority, "TODO", due_date, now, now))
    return get_task(tid)


def get_task(task_id):
    return appdb.q("SELECT * FROM tasks WHERE task_id = ?", (task_id,), one=True)


def list_tasks(assigned_to=None, status=None, role_target=None, task_type=None,
               keyword=None, limit=500):
    where, params = [], []
    if assigned_to:
        where.append("assigned_to_user_id = ?"); params.append(assigned_to)
    if status:
        where.append("status = ?"); params.append(status)
    if role_target:
        where.append("role_target = ?"); params.append(role_target)
    if task_type:
        where.append("task_type = ?"); params.append(task_type)
    if keyword:
        where.append("related_keyword LIKE ?"); params.append(f"%{keyword}%")
    sql = "SELECT * FROM tasks"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY CASE priority WHEN 'URGENT' THEN 0 WHEN 'HIGH' THEN 1 " \
           "WHEN 'MEDIUM' THEN 2 ELSE 3 END, task_id DESC LIMIT ?"
    params.append(limit)
    return appdb.q(sql, tuple(params))


def update_task(task_id, status=None, priority=None, assigned_to_user_id=None):
    t = get_task(task_id)
    if not t:
        return None
    status = (status or t["status"])
    if status not in STATUSES:
        raise ValueError(f"invalid status {status}")
    completed = _now() if status in ("DONE", "APPROVED") else t.get("completed_at")
    appdb.execute("UPDATE tasks SET status=?, priority=?, assigned_to_user_id=?, "
                  "updated_at=?, completed_at=? WHERE task_id=?",
                  (status, (priority or t["priority"]).upper(),
                   assigned_to_user_id if assigned_to_user_id is not None
                   else t["assigned_to_user_id"], _now(), completed, task_id))
    return get_task(task_id)


def review_task(task_id, reviewer_id, review_status, notes=""):
    review_status = review_status.upper()
    if review_status not in REVIEW_STATUSES:
        raise ValueError(f"invalid review status {review_status}")
    new_status = {"APPROVED": "APPROVED", "REJECTED": "REJECTED",
                  "NEEDS_FIX": "IN_PROGRESS"}.get(review_status)
    appdb.execute("UPDATE tasks SET review_status=?, reviewed_by=?, review_notes=?, "
                  "status=COALESCE(?, status), updated_at=? WHERE task_id=?",
                  (review_status, reviewer_id, notes, new_status, _now(), task_id))
    return get_task(task_id)


def review_queue():
    return list_tasks(status="READY_FOR_REVIEW")


def summary_by_user():
    rows = appdb.q(
        "SELECT assigned_to_user_id uid, "
        "SUM(CASE WHEN status IN ('DONE','APPROVED') THEN 1 ELSE 0 END) done, "
        "SUM(CASE WHEN status='REJECTED' THEN 1 ELSE 0 END) rejected, "
        "COUNT(*) total FROM tasks GROUP BY assigned_to_user_id")
    return rows
