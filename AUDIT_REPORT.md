# AUDIT REPORT — Etsy Product Manager V28.0 (readiness fixes)

_Execution engine on top of the YTuong/HeyEtsy research engine. This round fixed
release safety, made the audit tell the truth, and hardened the execution pipeline
(product mode, product-fit, clusters). Nothing in this tool publishes to Etsy._

**Verified on:** Windows dev laptop, Python 3.14.6, 2026-07-13. All dependencies
installed, `pytest` green (110 passed), `selftest` ALL CHECKS PASSED,
`healthcheck --with-tests` → SYSTEM_READY_FOR_TEAM_USE: true.

> Truth note: the readiness flags below were produced by `py main.py healthcheck
> --with-tests` on the laptop. **Re-run that same command on the VPS** before
> declaring the VPS ready — the flags flip to false there if Flask/Werkzeug/Markdown
> are missing or `pytest` fails.

## 1. What was fixed this round (the 10 readiness items)

| # | Item | Status | What changed |
|---|---|---|---|
| 1 | Release safety | **fixed + verified** | `package release` now ships only curated reference data. Real DBs (`app.db`, `agent.db`) + all business data (saved shops/listings, imports, learning, tracking, research, `keyword_data.csv`, `social_signals.csv`) are excluded via a `data/` whitelist in `src/packaging.py`. A post-build assertion now **deletes the zip and fails** if anything sensitive leaks. Fixed the Windows `UnicodeEncodeError` (`✓`) that crashed the command. Verified a fresh extract has no DBs and bootstraps via `auth create-admin`. |
| 2 | Audit truth | **fixed** | `healthcheck` now imports Flask/Werkzeug/Markdown/pytest and emits honest named flags: Flask↦DASHBOARD_READY, Werkzeug↦AUTH_READY, Markdown↦PDF_EXPORT_READY, pytest↦SYSTEM_READY_FOR_TEAM_USE. `--with-tests` runs pytest for a definitive verdict; exits non-zero on a known failure. TESTS_PASS/SYSTEM_READY stay "REQUIRES pytest" until actually run. |
| 3 | Product mode preservation | **fixed + tested** | Research-Queue "Build workspace" link now carries `&mode=`; `/run` accepts `mode` as an alias for `supplier_type`. End-to-end test: import forces Embroidery over the auto-guess → link carries it → `/run` flows it into workspace opts. |
| 4 | Product-fit filter | **fixed + tested** | `THEME_FIT` split into `THEME_FIT_READY` (launchable), `THEME_FIT_NEEDS_PRODUCT` (choose a product first — not launch-ready), `AMBIGUOUS_PHRASE`, `LOW_BUYER_INTENT`. Only POD/EMBROIDERY/JEWELRY/ACRYLIC/THEME_FIT_READY show as normal opportunities. All 7 spec cases locked in tests. |
| 5 | Opportunity clusters | **partial (honest)** | `clusters.py` enriched into sellable clusters: readable name ("Personalized Bridesmaid Pouch"), product mode/type, occasion/style/audience/personalization, `next_action`, `verdict`, `reason_shown`; persisted to `data/discovery/opportunity_clusters.json`. **Market/profit scores are left `null` with `scores_status: pending`** — filled by the live pipeline, never fabricated. Dashboard already shows clusters before raw rows. |
| 6 | Team calendar | **improved + tested** | Added the missing **This month** view (Today / This week / This month / Overdue / Upcoming / All). Per-user/manager scoping + status updates exist. Rich multi-field filters (role/priority/product line/type) and manager bulk actions remain a larger enhancement — noted, not built. |
| 7 | Staff/Manager home | **already present** | Role-aware home cards already cover staff (Overdue, Due soon, Day 3/7, My research) and manager (Review Queue, Research Queue, Ready-to-publish, Blocked). Tidy; no change made (avoiding clutter). |
| 8 | YTuong Import Center | **improved + tested** | Added the "Could not extract a keyword from that URL automatically — enter it manually" message; undecodable URLs no longer create junk candidates. Deep links (Open in YTuong/HeyEtsy/Etsy), Build workspace, and Assign task already existed via the Research Queue. |
| 9 | Strict publish gate | **verified, no change** | `workspace.publish_gate()` sets PUBLISH_READY true only when zero checks fail (launch ≥85, exactly 13 clean tags, HIGH-TM hard block, CAUTION needs manager approval, supplier/competitor/material/image sign-offs). UI shows "DRAFT ONLY — DO NOT PUBLISH" + FAILED_PUBLISH_CHECKS when false. |
| 10 | Final tests | **done** | See §2. |

## 2. Commands run (this environment)

- `py -m pytest -q` → **110 passed**
- `py main.py selftest` → **ALL CHECKS PASSED**
- `py main.py healthcheck --with-tests` → **SYSTEM_READY_FOR_TEAM_USE: true**
- `py main.py package release` → clean (143 files, 453 KB, 0 leaks); fresh extract
  bootstraps `auth create-admin`
- Manual/automated spec cases: monogram tote→Embroidery (mode preserved);
  funny raccoon→THEME_FIT_NEEDS_PRODUCT; gift for her→BROAD_SEED_ONLY;
  calendar Today/Week/Month/Overdue/Upcoming render; release excludes
  `.env`/`.git`/logs/real DBs.

## 3. Final readiness status

```
SYSTEM_READY_FOR_TEAM_USE : true      (laptop, healthcheck --with-tests; re-verify on VPS)
DASHBOARD_READY           : true
AUTH_READY                : true
RELEASE_PACKAGE_READY     : true      (clean package + verified fresh-deploy bootstrap)
YTUONG_IMPORT_READY       : true
RESEARCH_QUEUE_READY      : true
PRODUCT_MODE_PRESERVED    : true      (fixed + end-to-end test)
PRODUCT_FIT_FILTER_READY  : true      (THEME_FIT split + tests)
OPPORTUNITY_CLUSTER_READY : partial   (model + JSON + next-action done; market scores pending live-data wiring)
TEAM_CALENDAR_READY       : true      (5 date views; rich filters + bulk manager actions still partial)
PUBLISH_GATE_READY        : true      (verified strict)
DAILY_AUTORUN_READY       : true
PUBLISH_AUTOMATION        : false     (always — no publish path exists)
```

## 4. Action required — rotate exposed secrets

The delivery package never contained `.env`. But `.env` holds **real** secrets and
was present in the shared root ZIP, so treat these as exposed and rotate:
`OPENAI_API_KEY`, `PRINTIFY_API_TOKEN`, `SHINEON_API_KEY`, `YTRENDS_API_TOKEN`,
`YTRENDS_COOKIE`, `APP_SECRET_KEY`, and both `ADMIN_PASSWORD_INITIAL` / `WEB_PASSWORD`.
(`BURGERPRINTS_API_KEY` / `PRINTWAY_API_KEY` looked like unset placeholders.)

## 5. Honest remaining work (not done this round)

- **Opportunity cluster market scores** — demand/competition/trend/profit/can-we-win/
  launch-readiness/private-learning per cluster need the live market + supplier +
  learning pipeline wired in. The structure is ready; the numbers are `pending`.
- **Team calendar** — multi-field filters (role/priority/product line/type) and
  one-click manager bulk actions (approve/reject/reassign/change-due) beyond the
  existing per-task status updates.
- These are enhancements, not blockers. Team daily use is safe now.
