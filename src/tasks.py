"""Team task + review system (SQLite via src/appdb.py)."""
from datetime import datetime, timedelta, timezone

from src import appdb

# An auto-assigned task defaults to a 24h deadline (the team can change it later).
DEFAULT_DUE_HOURS = 24

TASK_TYPES = ["KEYWORD_RESEARCH", "SPY_RESEARCH", "SUPPLIER_CHECK",
              "COMPETITOR_AUDIT", "TRADEMARK_CHECK", "LISTING_DRAFT",
              "DESIGN_BRIEF", "FIRST_IMAGE", "MOCKUP", "PDF_EXPORT",
              "FEEDBACK_DAY3", "FEEDBACK_DAY7", "MANAGER_REVIEW", "FIX_REQUIRED"]
PRIORITIES = ["LOW", "MEDIUM", "HIGH", "URGENT"]
STATUSES = ["TODO", "IN_PROGRESS", "BLOCKED", "READY_FOR_REVIEW", "APPROVED",
            "REJECTED", "DONE"]
REVIEW_STATUSES = ["NOT_REVIEWED", "APPROVED", "NEEDS_FIX", "REJECTED"]
OPEN_STATUSES = ("TODO", "IN_PROGRESS", "BLOCKED", "READY_FOR_REVIEW")

# What "done" means for each stage — shown on the member's task so assigning and
# reporting always line up with the workflow section.
TYPE_GUIDE = {
    "KEYWORD_RESEARCH": "Find + shortlist viable keywords (demand vs competition).",
    "SPY_RESEARCH": "Run Spy: who wins, their price/angle, and the gap to exploit.",
    "SUPPLIER_CHECK": "Confirm product URL, base + shipping cost, material, processing time.",
    "COMPETITOR_AUDIT": "Fill the competitor audit: top rivals, what they do well, what to beat.",
    "TRADEMARK_CHECK": "Verify the keyword + tags on USPTO; flag anything risky.",
    "LISTING_DRAFT": "Write title + 13 clean tags + description (draft only).",
    "DESIGN_BRIEF": "Produce the design brief + POD/embroidery prompt.",
    "FIRST_IMAGE": "Deliver a hero image that beats rivals: readable, personalization visible, gift context.",
    "MOCKUP": "Add lifestyle + gift-in-use mockups and a size/detail shot.",
    "PDF_EXPORT": "Export the role PDF and attach/share it.",
    "FEEDBACK_DAY3": "Log the Day-3 numbers (views, favorites, carts).",
    "FEEDBACK_DAY7": "Log the Day-7 numbers and apply the recommendation.",
    "MANAGER_REVIEW": "Review the submitted work and approve or send back.",
    "FIX_REQUIRED": "Apply the requested fix, then resubmit for review.",
}

# The member's next step(s) for a status: (label, target_status, is_primary).
def member_actions(status):
    return {
        "TODO": [("Start", "IN_PROGRESS", True)],
        "IN_PROGRESS": [("Submit for review", "READY_FOR_REVIEW", True),
                        ("Block", "BLOCKED", False)],
        "BLOCKED": [("Resume", "IN_PROGRESS", True)],
        "READY_FOR_REVIEW": [("Reopen", "IN_PROGRESS", False)],
    }.get(status, [])


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def default_due(hours=DEFAULT_DUE_HOURS):
    """Default deadline for an auto-assigned task: local now + `hours`, in the
    datetime-local format (YYYY-MM-DDTHH:MM) the calendar + picker use."""
    return (datetime.now() + timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M")


def create_task(title, assigned_to_user_id=None, assigned_by_user_id=None,
                task_type=None, priority="MEDIUM", description="", role_target="",
                related_keyword="", related_workspace_id="", related_listing_id="",
                related_supplier="", due_date=""):
    priority = (priority or "MEDIUM").upper()
    if priority not in PRIORITIES:
        priority = "MEDIUM"
    # Auto-assigned task with no explicit deadline -> default 24h (changeable later).
    if assigned_to_user_id and not (due_date or "").strip():
        due_date = default_due()
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


def update_task(task_id, status=None, priority=None, assigned_to_user_id=None,
                title=None, task_type=None, related_keyword=None, due_date=None,
                work_report=None):
    """Update a task. status/priority/assignee were the original fields; title,
    task_type, related_keyword and due_date let an owner/manager EDIT the task;
    work_report is the STAFF member's note on what they did. Any field left as
    None keeps its current value."""
    t = get_task(task_id)
    if not t:
        return None
    status = (status or t["status"])
    if status not in STATUSES:
        raise ValueError(f"invalid status {status}")
    completed = _now() if status in ("DONE", "APPROVED") else t.get("completed_at")
    keep = lambda new, cur: cur if new is None else new
    appdb.execute(
        "UPDATE tasks SET status=?, priority=?, assigned_to_user_id=?, title=?, "
        "task_type=?, related_keyword=?, due_date=?, work_report=?, updated_at=?, "
        "completed_at=? WHERE task_id=?",
        (status, (priority or t["priority"]).upper(),
         assigned_to_user_id if assigned_to_user_id is not None
         else t["assigned_to_user_id"],
         keep(title, t["title"]), keep(task_type, t.get("task_type")),
         keep(related_keyword, t.get("related_keyword")),
         keep(due_date, t.get("due_date")), keep(work_report, t.get("work_report")),
         _now(), completed, task_id))
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


def is_overdue(t):
    from datetime import date
    due = (t.get("due_date") or "").strip()
    return bool(due) and t["status"] in OPEN_STATUSES and due[:10] < date.today().isoformat()


def is_due_soon(t):
    """Open task due today or tomorrow (and not already overdue) — a soft heads-up."""
    from datetime import date, timedelta
    due = (t.get("due_date") or "").strip()[:10]
    if not due or t["status"] not in OPEN_STATUSES:
        return False
    today = date.today().isoformat()
    return today <= due <= (date.today() + timedelta(days=1)).isoformat()


def my_open(user_id):
    """A user's still-open tasks, urgent/overdue first."""
    rows = [t for t in list_tasks(assigned_to=user_id) if t["status"] in OPEN_STATUSES]
    rows.sort(key=lambda t: (not is_overdue(t),
                             {"URGENT": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
                             .get(t["priority"], 2)))
    return rows


def review_queue():
    return list_tasks(status="READY_FOR_REVIEW")


def summary_by_user():
    rows = appdb.q(
        "SELECT assigned_to_user_id uid, "
        "SUM(CASE WHEN status IN ('DONE','APPROVED') THEN 1 ELSE 0 END) done, "
        "SUM(CASE WHEN status='REJECTED' THEN 1 ELSE 0 END) rejected, "
        "COUNT(*) total FROM tasks GROUP BY assigned_to_user_id")
    return rows
