# AUDIT REPORT — Etsy Product Manager V24.2

_Full audit + publish-gate rebuild (manager sign-off) + release packaging + schema
validation. English only. Nothing in this tool publishes to Etsy._

---

## 1. What was checked

- A dedicated read-through of every module (`main.py`, `web.py`, `workspace.py`,
  `publish_gate.py`, `feedback.py`, `learning.py`, `alerts.py`, `tracking.py`,
  `profit.py`, `launchpad.py`, `supplier_ops.py`, `ops.py`, `trademark.py`,
  `validators.py`, plus the new `packaging.py` / `data_validate.py`).
- Every module byte-compiles; every `COMMANDS` handler signature matches; every
  `web.py` route + form field + link maps to a real handler.
- The publish-gate safety invariant, across all scenarios.
- All required commands + the full test suite.

## 2. Bugs found

| # | Sev | Bug |
|---|---|---|
| 1 | MED | **Alerts never auto-resolved.** Day-3/Day-7 "log numbers" reminders had no resolve path, so once a listing aged or numbers were logged the stale reminder stayed open forever (and a >7-day listing showed *both* a Day-3 and Day-7 reminder). |
| 2 | LOW | `main.py cmd_alerts` sorted on `x["level"]` → `KeyError` on a malformed alert record (web route already used `.get`). |
| 3 | LOW | `tracking.snapshot_market()` never set `opportunity`, so every market row persisted `opportunity: 0` (dead column). |
| 4 | DESIGN | **PUBLISH_READY was unreachable.** The gate + launch-readiness hardcoded 3 manual checks to `False` with no way to clear them, so PUBLISH_READY could never become true — making "manager approval when PUBLISH_READY=true" impossible in-tool. |

The audit also **confirmed** (not bugs): the publish-when-not-ready safety concern
does not occur anywhere; MCP field access is None-guarded; every tool/run route
catches the MCP `SystemExit`; command↔handler and link↔route wiring all match.

## 3. Bugs fixed

- **#1** New `alerts.resolve_ref(ref)`; `generate()` now clears the Day-3 reminder
  once Day-3 is logged or the listing enters the Day-7 window, and clears Day-7
  once logged. No more pile-up.
- **#2** `cmd_alerts` uses `.get("level")` / `.get("message")`.
- **#3** `snapshot_market()` computes a real 0–100 `opportunity` (demand-per-listing,
  damped by saturation).
- **#4 (the important one) — publish gate rebuilt with manager sign-off.** The
  manual checks now clear only when a **manager explicitly confirms** each item
  (supplier / competitor-audit / material-size-processing / image-mockup /
  trademark) via checkboxes on the workspace. `launch_readiness` honors the same
  confirms. So **PUBLISH_READY becomes true only by deliberate human sign-off** —
  the tool still never publishes, and a **HIGH-trademark (known brand) can never be
  cleared** by any confirmation. Verified: no confirms → blocked (lr 70); full
  confirms + passing scores → PUBLISH_READY true (lr 100); HIGH TM + full confirms
  → still blocked.

## 4. New this release

- **Release packaging:** `.releaseignore` + `py main.py package release` → a clean
  delivery zip. A hardcoded safety net (independent of `.releaseignore`) excludes
  `.env`, `.git`, caches, logs, `*.pem`; only `.env.example` ships. Verified: 138
  files, no secrets, self-checked.
- **Schema validation:** `src/schemas/*.json` (8 stores) + `py main.py validate
  data|run|suppliers|feedback`. Catches invalid JSON, missing CSV headers, <13
  tags, invalid status, a CONFIRMED supplier missing cost/URL, missing timestamps,
  and the **PUBLISH_READY-with-failed-checks** safety violation. (Dependency-light:
  built-in checks always run; uses `jsonschema` only if it's installed.)
- **Tests:** `tests/test_publish_gate.py` (9) + `tests/test_routes.py` (18) — the
  gate safety invariant + the offline dashboard checklist.
- **Internal Claude skills:** `.claude/skills/{system-audit, publish-gate,
  test-runner, supplier-audit, feedback-learning, dashboard-cleanup, market-gap}`.
- **Private learning formalized:** `private_learning_boost / _warning / _reason`
  saved into each run.

## 5. Tests run / results

- `py main.py selftest` → **ALL CHECKS PASSED** (added V24.2 checks).
- `pytest -q` → **66 passed** (was 39; +27 new).
- `py main.py healthcheck` → all PASS except cron (WARN on Windows).
- `py main.py daily-run` → harvest + autopull + tracker snapshots + alerts refresh,
  summary written, **no publish**.
- `py main.py validate data` → runs; flagged only legacy pre-V23 run folders
  missing the newer artifacts (expected; new runs are complete).
- `py main.py package release` → clean zip, **no secrets**.

## 6. Commands tested

| Command | Result |
|---|---|
| workspace build "usa raccoon shirt" pod | WATCH · publish-ready **false** |
| workspace build "chenille name bag" embroidery | WATCH · publish-ready false |
| workspace build "custom travel pouch" both | SKIP |
| workspace build "gift for her" both | WATCH |
| workspace build "taylor swift hoodie" pod | **BLOCKED** |
| supplier match "chenille name bag" embroidery | 50/100 SUPPLIER_PARTIAL |
| supplier match "usa raccoon shirt" pod | 25/100 → VALIDATE_SUPPLIER_FIRST |
| alerts / profit / launchpad / validate / package | all OK |

## 7. Dashboard pages tested (Flask test client, in `tests/test_routes.py`)

`/`, `/cheatsheet`, `/workflow`, `/suppliers`, `/feedback`(+POST), `/profit`(+POST),
`/grade`(+POST), `/alerts`, `/launchpad`, `/trackers`, `/research`, `/shops`,
`/listings`, `/spy`, `/run`. Asserts: auth redirect; **no Archive card**; Cheat
Sheet + all cards present; Listing Analyzer blocks a thin listing (DRAFT ONLY); **no
"Publish now" language leaks**. Live Spy/workspace (3 modes) verified via the audit
run + selftest.

## 8. Remaining risks

- **No POD supplier CSV on file** → POD matches score low (correctly →
  VALIDATE_SUPPLIER_FIRST). Import a POD catalog CSV to raise them.
- **Legacy run folders** (pre-V23) lack the newer JSON artifacts; `validate data`
  flags them. Harmless; new runs are complete.
- **Not done (deliberate):** the big `routes/services/ui/` refactor of
  web.py/workspace.py (high-risk churn on a working, tested tool) and Playwright
  (the Flask-client route tests cover the same checklist, offline + fast). Both
  documented as future options.
- Live data depends on the YTrends MCP; tools fail *gracefully* if it's down.

## 9. Final readiness status

```
SYSTEM_READY_FOR_TEAM_USE : true
DASHBOARD_READY           : true   (route tests green; no Archive; sticky Home)
SPY_READY                 : true   (POD / Embroidery / Both, reverse engine)
SUPPLIER_MODULE_READY     : true   (mode-correct; conservative)
FEEDBACK_LOOP_READY       : true   (feeds scoring; private_learning fields)
MARKET_TRACKER_READY      : true   (opportunity now computed; auto-snapshots)
PROFIT_CENTER_READY       : true
ALERTS_READY              : true   (auto-resolve fixed)
PDF_EXPORT_READY          : true
DAILY_AUTORUN_READY       : true
PUBLISH_AUTOMATION        : false  (always — publishing is manual, human-gated)
```

**Clean release package:** `py main.py package release` → `dist/etsy-product-manager-v24.2.zip`
(no `.env`, `.git`, caches, or logs).

**Recommendation:** ready for daily team use. Publishing stays manual: a listing
reaches `PUBLISH_READY = true` only after a manager ticks every sign-off item, and
even then the team publishes it themselves on Etsy — the tool never does.
