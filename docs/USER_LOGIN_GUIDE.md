# Team Login & Task System — Guide

Per-user login with roles, activity tracking, tasks, and manager approval. No
auto-publishing — publishing is always manual and manager-approved.

---

## 1. Create the first admin (owner)

On the machine that runs the dashboard:

```bash
python main.py auth create-admin --email you@example.com --password "StrongPass123!" --name "You"
```

Or set these in `.env` and (re)start `python main.py web` — the owner is seeded automatically:

```
ADMIN_EMAIL=you@example.com
ADMIN_PASSWORD_INITIAL=StrongPass123!
APP_SECRET_KEY=some-long-random-string
```

Change the initial password after first login.

## 2. Add team members

By CLI:

```bash
python main.py auth create-user --email seller@example.com --password "Temp123!" --name "Seller One" --role SELLER
python main.py auth list-users
python main.py auth disable-user --email seller@example.com
python main.py auth reset-password --email seller@example.com --password "NewTemp123!"
```

Or in the dashboard: **Team → User Management** (OWNER/ADMIN only) — create users,
change roles, disable.

## 3. How roles work

| Role | Can do |
|---|---|
| **OWNER** | Everything: users, logs, tasks, approvals, settings. |
| **ADMIN** | Manage users (not owner), logs, tasks, approvals, exports. |
| **MANAGER** | See all work, assign + review tasks, **approve listings**, logs, exports. |
| **SELLER** | Build drafts, edit title/tags/description, supplier + feedback fields. *No final approval.* |
| **DESIGNER** | Design briefs, first image / mockup tasks. *No approval.* |
| **RESEARCHER** | Keyword research, Spy, competitor audit, source/trademark/supplier research. *No approval.* |
| **VIEWER** | Read-only. |

Only **OWNER / ADMIN / MANAGER** can mark a listing *approved for manual publish*.

## 4. Assign and review tasks

- **Team → Team Tasks** (managers+): create a task, pick an assignee, type, priority,
  keyword, due date. The assignee sees it under **Team → My Tasks** and updates its
  status (TODO → IN_PROGRESS → READY_FOR_REVIEW).
- **Team → Review Queue** (managers+): approve / needs-fix / reject submitted work.
- CLI: `python main.py task create --title "..." --assign-to email --type SUPPLIER_CHECK --keyword "..." --priority HIGH`,
  `python main.py task list`, `python main.py task update --task-id 5 --status READY_FOR_REVIEW`.

## 5. See who did what (activity log)

- **Team → Activity Log** (managers+): every dashboard action — login, Spy, workspace
  build, supplier check, PDF export, feedback update, task changes, approvals — with
  who / when / keyword. Filter + **Export CSV**.
- CLI: `python main.py activity list --limit 50`, `python main.py activity export --output data/exports/activity_log.csv`.

**We track dashboard actions only** — never keystrokes, screens, browser history,
passwords, cookies, or anything outside this tool. The login page states this.

## 6. Approve a listing (manual publish only)

1. Build the workspace for a keyword.
2. Complete the **🔑 Manager sign-off** (supplier, competitor audit, material,
   image, trademark) so `PUBLISH_READY = true`.
3. As OWNER/ADMIN/MANAGER, use **✅ Approve for manual publish** on the run.
4. The decision is recorded (`MANAGER_APPROVED_FOR_MANUAL_PUBLISH: true`) in the
   activity log. **The tool never publishes** — you list it yourself on Etsy.

A known-brand (HIGH trademark) can never be approved.

## 7. Security notes

- Passwords are **hashed** (Werkzeug pbkdf2), never stored or logged in plain text.
- 5 failed logins → the account is locked for 15 minutes.
- Session cookies are HTTP-only + SameSite=Lax, and time out after 12 hours.
- Cron / `daily-run` runs as SYSTEM and needs no browser login; it logs
  `DAILY_RUN_START` / `_COMPLETE` / `_FAILED`.
- Never commit the real `.env`. `python main.py package release` excludes it.
