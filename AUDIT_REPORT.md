# AUDIT REPORT — Etsy Product Manager V25.0

_Team login, roles, activity tracking, tasks & manager approval. English only.
Nothing in this tool publishes to Etsy._

---

## 1. Stack audit

Flask app (`src/web.py` `build_app`) + CLI (`main.py`) + JSON/CSV data. Added
**SQLite** (`data/app.db`) via stdlib `sqlite3` (no new dependency) for auth /
activity / tasks, and hashed passwords with **Werkzeug** (already a Flask
dependency — no install). Existing commands and saved runs are unaffected.

## 2. What was added

- **Auth (`src/auth.py`, `src/appdb.py`):** users table, Werkzeug pbkdf2 hashing,
  7 roles + a permission matrix, `authenticate()` with failed-login **lockout**
  (5 → 15 min), `seed_admin_from_env()`.
- **Activity (`src/activity.py`):** dashboard-only event logging (redacts anything
  that looks like a password/token/cookie), list + CSV export + today summary.
- **Tasks (`src/tasks.py`):** task + review CRUD (types / priority / status /
  review status), review queue.
- **Web:** real `/login` (email + password + remember + privacy notice),
  `/logout`, `/me`, per-user sessions (HTTP-only, SameSite=Lax, 12-h timeout),
  `require_perm` RBAC, Team pages (`/team`, `/me/tasks`, `/admin/tasks`,
  `/admin/reviews`, `/admin/users`, `/admin/activity`), user chip + Team link in
  the header, and a **manager approval** flow on a run.
- **Activity instrumentation:** login/logout, WORKSPACE_BUILD/SAVE, SPY_SEARCH,
  FEEDBACK_ADD/UPDATE, PDF_EXPORT_*, SUPPLIER_CSV_UPLOAD, TASK_*, MANAGER_APPROVE/
  REJECT, DAILY_RUN_START/COMPLETE/FAILED.
- **CLI:** `auth create-admin|create-user|list-users|disable-user|reset-password`,
  `activity list|export`, `task create|list|update`.
- **Docs:** `docs/USER_LOGIN_GUIDE.md`, `.env.example` (APP_SECRET_KEY, ADMIN_EMAIL,
  ADMIN_PASSWORD_INITIAL). Healthcheck extended with auth checks.

## 3. Safety / privacy

- Passwords are **hashed, never plaintext** and never logged.
- Activity records **only dashboard actions** — no keystrokes, screens, browser
  history, passwords, cookies, or tokens (redaction guard in `activity._clean`).
- The login page states the tracking scope.
- Manager approval **re-verifies PUBLISH_READY server-side** before recording, a
  known brand can never be approved, and `PUBLISH_AUTOMATION` stays **false** —
  approval only means "allowed for manual publishing".
- `.env` is never in the release package; only `.env.example` ships.

## 4. Tests run / results

- `pytest -q` → **75 passed** (added `tests/test_auth.py` — hashing, login
  success/fail, lockout, RBAC, disable, activity-no-secrets, task create/update/
  review, publish-automation-false; updated `tests/test_routes.py` to log in a
  real user).
- `py main.py selftest` → **ALL CHECKS PASSED** (added team-login / activity /
  approval checks).
- `py main.py healthcheck` → user DB + admin + **hashed passwords** + activity/
  task tables + **no publish automation** all PASS (session-secret WARN only when
  APP_SECRET_KEY unset).
- Live web flow (test client): anon → `/login`; owner reaches all Team pages;
  **seller → `/admin/users` = 403**; task assigned by owner appears in seller's My
  Tasks; bad login re-shows the form; events logged.
- **Backward compat:** `workspace build`, `daily-run`, `supplier match`, and all
  CLI commands still work; saved runs unaffected.

## 5. Database tables

`users`, `activity_logs`, `tasks`, `login_attempts`, `approvals` (in `data/app.db`,
gitignored).

## 6. New commands

`auth create-admin / create-user / list-users / disable-user / reset-password` ·
`activity list / export` · `task create / list / update`.

## 7. Remaining risks / not done (deliberate, phase 2)

- **Per-section "Assign task" buttons** inside each workspace section and the
  **productivity summary cards** — additive UI, safer to layer on the proven core.
- **CSRF tokens** on POST forms (currently mitigated by SameSite=Lax + login gate);
  a full token needs `flask-wtf`. Documented.
- **Password-reset UI** (CLI reset works; self-service reset is phase 2).
- Set `APP_SECRET_KEY` in `.env` on the VPS so sessions survive restarts.
- Legacy single shared-password login is removed; everyone re-logs in with their
  own email (one-time).

## 8. Final readiness status

```
AUTH_READY               : true
ROLE_PERMISSION_READY    : true
ACTIVITY_LOG_READY       : true
TASK_SYSTEM_READY        : true
MANAGER_REVIEW_READY     : true
DASHBOARD_LOGIN_READY    : true
DAILY_RUN_STILL_WORKS    : true
PUBLISH_AUTOMATION       : false   (always — approval = allowed for manual publish)
```

**Deploy:** on the VPS, add `APP_SECRET_KEY` + `ADMIN_EMAIL` +
`ADMIN_PASSWORD_INITIAL` to `.env`, `git pull`, `sudo systemctl restart etsy-web`.
The owner is seeded on first start; add the rest of the team via **Team → User
Management** or `py main.py auth create-user`.
