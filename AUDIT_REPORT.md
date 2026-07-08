# AUDIT REPORT — Etsy Product Manager V24.0

_Full re-audit + sales-execution OS layer (Alerts, Launchpad, Profit Center,
Trackers, Listing Analyzer). English only. Nothing in this tool publishes to Etsy._

---

## 1. What was checked

- Every module in the review list (`main.py`, `web.py`, `interactive.py`,
  `feedback.py`, `learning.py`, `supplier_ops.py`, `supplier_pull.py`, `daily.py`,
  `listing_factory.py`, `crosscheck.py`, `gtrends.py`, `ops.py`) — plus the new
  V24 modules (`alerts.py`, `tracking.py`, `profit.py`, `launchpad.py`).
- All dashboard routes (incl. the 4 new pages) via Flask test client.
- Data save/load: saved runs, feedback, learning, supplier CSV, and the new
  tracker / profit / alerts / launchpad stores (JSON + CSV).
- The full required command list + all pytest + selftest checks.

## 2. Bugs found (this pass)

| # | Sev | Bug |
|---|---|---|
| 1 | MED | **Trademark check over-flagged.** Any 4-word phrase with 3+ non-product words was marked CAUTION ("could be a slogan"), so normal Etsy long-tail tags like "gift for dog mom" tripped the publish gate — too noisy to be usable. |
| 2 | LOW | Listing grader treated HIGH (real brand) and CAUTION (verify) tags the same, tanking the SEO score for verifiable tags. |

(Prior V23.1 audit findings — MCP `SystemExit` on the tool routes, `daily-run`
robustness, blank fresh-deploy home, `int()` guards — remain fixed.)

## 3. Bugs fixed

- **#1** `trademark.check` now requires **5+ words / 4+ non-product words** for the
  pure-length slogan flag; brand detection (HIGH) and pronoun-slogan detection
  ("make them chase you" → CAUTION) are unchanged. Verified: "gift for dog mom" →
  OK, "personalized dog name shirt" → OK, "make them chase you" → CAUTION,
  "taylor swift shirt" → HIGH.
- **#2** The Listing Analyzer separates HIGH (remove) from CAUTION (verify +
  manager-approve); only HIGH costs SEO points. Both still block the publish gate.

## 4. New modules added (V24)

| Module | File | What it does |
|---|---|---|
| **Alerts Center** | `src/alerts.py` | Internal alerts auto-generated from state (stale data, Day-3/7 reviews due, kill/scale flags, daily-run failures, problem suppliers) + manual. Home badge shows the open count. |
| **Keyword + Market Trackers** | `src/tracking.py` | Snapshot metrics over time → rising / falling / stable / recheck / drop. **Auto-snapshots in the 6 AM run.** |
| **Profit Center** | `src/profit.py` | Real P&L per sale with the Etsy fee model (listing $0.20, 6.5% txn, ~3%+$0.25 pay, 15% offsite). Feeds supplier profit into the learning system. |
| **Launchpad** | `src/launchpad.py` | Kanban launch board (Not started → … → Day-7 → Scaled/Killed), **self-derived** from saved runs + feedback, with manual override. |
| **Listing Analyzer** | `interactive.analyze_listing` | Listing / SEO / Buyer-Trust / Image sub-scores + a hard publish gate with FAILED_PUBLISH_CHECKS. |
| **Ads Readiness** | `interactive.ads_readiness` | Manual-only "is this worth testing Etsy Ads" check. Never runs ads. |

All new stores auto-create; the 6 AM `daily-run` now also snapshots trackers and
refreshes alerts (verified: `track_snapshots` + `refresh_alerts` steps OK).

## 5. Tests run

- `pytest -q` → **all passed** (incl. `tests/test_os_modules.py` — 12 new tests:
  profit math, tracker trend, alerts add/resolve/generate, launchpad board,
  analyzer gate pass/fail, ads readiness, trademark tuning).
- `py main.py selftest` → **ALL CHECKS PASSED** (added Alerts / Trackers / Profit /
  Launchpad / Listing-Analyzer / trademark / daily-run-hooks checks).
- `.pre-commit-config.yaml` added (ruff + file hygiene + local pytest/selftest hooks).

## 6. Commands tested

| Command | Result |
|---|---|
| `healthcheck` | all PASS except cron (WARN on Windows dev box) |
| `daily-run` | harvest + autopull + **track_snapshots (10 kw)** + learning + **refresh_alerts** — all OK, summary written, **no publish** |
| `supplier match "chenille name bag" --mode embroidery` | 50/100 embroidery (SUPPLIER_PARTIAL) |
| `supplier match "usa raccoon shirt" --mode pod` | low (no POD supplier on file → VALIDATE_SUPPLIER_FIRST) |
| `workspace build … pod / embroidery / both / gift for her / taylor swift hoodie` | WATCH / WATCH / SKIP / WATCH / **BLOCKED** — all `publish_ready=false` |
| `alerts` / `profit` / `launchpad` / `track` | all work (see live output) |

## 7. Dashboard pages tested (Flask test client — all HTTP 200)

`/`, `/alerts`, `/launchpad`, `/trackers`, `/profit`, `/grade` (Listing Analyzer),
plus the existing `/spy` (3 modes), `/shops`, `/listings`, `/calendar`,
`/suppliers`, `/feedback`, `/cheatsheet`, `/run`, `/run/export/{4 roles}`.

- Home shows the new cards (🔔 Alerts w/ badge, 🚀 Launchpad, 📊 Trackers,
  💰 Profit Center, 📋 Listing Analyzer), **no** Archive card.
- No publish button on any run with `PUBLISH_READY=false`; BLOCKED never shows
  publish instructions.

## 8. Remaining risks

- **No POD supplier CSV on file** → POD matches score low (correctly →
  VALIDATE_SUPPLIER_FIRST). Import a POD catalog CSV to raise POD matches.
- **Trackers/markets start empty** and fill over days as the 6 AM run snapshots;
  markets need one manual add (or a saved niche) to begin tracking.
- **Two supplier stores** (dashboard vs legacy `listing_factory`) — dashboard path
  is authoritative; alignment is a documented follow-up.
- **Playwright e2e** and a standalone **Competitor Reverse Engine** page are the
  next planned phase (Spy already covers the reverse-engineering today).
- Live data depends on the YTrends MCP; tools fail *gracefully* if it's down.

## 9. Final readiness status

```
SYSTEM_READY_FOR_TEAM_USE : true
DASHBOARD_READY           : true
SPY_READY                 : true
SUPPLIER_MODULE_READY     : true
FEEDBACK_LOOP_READY       : true
MARKET_TRACKER_READY      : true   (auto-snapshots daily; add a market to seed it)
PROFIT_CENTER_READY       : true
ALERTS_READY              : true
PDF_EXPORT_READY          : true
DAILY_AUTORUN_READY       : true
PUBLISH_AUTOMATION        : false  (always — publishing is manual, human-gated)
```

**Recommendation:** ready for daily team use. On the VPS: `git pull` +
`sudo systemctl restart etsy-web`. Publishing stays manual — only list when the
Listing Analyzer's **Publish Gate = true** and a manager has approved supplier,
trademark, and the first image.
