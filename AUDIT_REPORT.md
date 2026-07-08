# AUDIT REPORT — Etsy Product Manager V23.1

_Full-system audit + Spy embroidery fix + hardening._
_English only. Nothing in this tool publishes to Etsy._

---

## 1. What was checked

- **Spy pipeline** end to end: UI form → `/spy` route → `interactive.spy()` →
  supplier matching → design rules → output, in POD / Embroidery / Both modes.
- **Every module** listed for review: `main.py`, `src/web.py`,
  `src/interactive.py`, `src/feedback.py`, `src/learning.py`,
  `src/supplier_ops.py`, `src/supplier_pull.py`, `src/daily.py`,
  `src/listing_factory.py`, `src/crosscheck.py`, `src/gtrends.py`, `src/ops.py`
  (read in full by a dedicated audit pass).
- **All dashboard routes** (14) via a Flask test client.
- **All buttons / links** map to real routes; all command handlers match their
  targets.
- **Data save/load**: saved runs, feedback CSV/JSON, learning JSON, supplier CSV.
- **PDF exports** for all four roles. **healthcheck / daily-run / cron.**

## 2. Bugs found

| # | Sev | Bug |
|---|---|---|
| 1 | HIGH | **Spy ignored Product Mode.** `spy(kw, mode)` accepted a mode but never used it, and the `/spy` route called `spy(q)` with no mode — so choosing Embroidery did nothing. |
| 2 | HIGH | **Supplier match wasn't mode-correct.** In embroidery mode a POD/jewelry row could earn the production-fit points (and vice-versa). |
| 3 | MED | **MCP `SystemExit` escaped the tool routes.** The MCP layer raises `SystemExit` (not `Exception`) on network error / HTTP 429 / 401. The self-serve routes only caught `Exception`, so a rate-limit → raw **500** for the team (Spy, Should-I-sell, Trending, Opportunities, Calendar, Draft, auto-pull). |
| 4 | MED | **`daily-run` aborted on MCP `SystemExit`** before writing its summary, defeating the "always writes a summary + logs" design of the 6 AM job. |
| 5 | MED | **Fresh-deploy home page was blank.** Before the first report sync, `index()` early-returned "No reports yet" and hid the entire Command Center + all live tools. |
| 6 | LOW | `printify cost abc` and `web --port xyz` raised raw `ValueError` tracebacks instead of a clear usage message. |
| 7 | LOW | Bare `python main.py` raises `FileNotFoundError` if `keywords.csv` is deleted (legacy path; the file ships with the repo). |

## 3. Bugs fixed

- **#1 Spy is now mode-aware.** Mode flows `form (supplier_type) → /spy route →
  spy(q, mode)`. `spy()` shows the mode in the header, a mode-correct **supplier
  feasibility** section (`supplier_ops.match(kw, mode)`), the right **design
  rules** (embroidery = stitch-safe ≤6 colors / POD = print-ready), an
  **embroidery-compatibility count** of the top listings, mode-scoped **new
  entrants**, mode-specific **gaps**, and a **POD-vs-Embroidery** comparison in
  Both mode. The home Spy card + Command Center button both carry the mode.
- **#2** New `supplier_ops._mode_ok()` — embroidery is satisfied only by
  EMBROIDERY/CHENILLE rows; POD excludes embroidery rows. Verified in self-test.
- **#3** All self-serve tool routes now `except (SystemExit, Exception)` → the
  graceful "data source unavailable" notice instead of a 500.
- **#4** `daily_run()`'s `step()` catches `SystemExit` too, so one failing step
  is logged and the run still writes `daily_summary_*.json`.
- **#5** `index()` no longer early-returns; the Command Center + tools always
  render (default mode POD), with the daily-report archive shown only when synced.
- **#6** `printify cost` and `web --port` validate numeric input and print a
  clear usage message.
- **#7** Left as-is (legacy; file present) and documented under Remaining risks.

## 4. Tests run

- `py main.py selftest` → **ALL CHECKS PASSED** (added mode-correct-supplier,
  graceful-failure, fresh-deploy-home, and mode-aware-Spy checks).
- `pytest -q` → **all passed**.

## 5. Commands tested

| Command | Result |
|---|---|
| `workspace build "usa raccoon shirt" --mode pod` | WATCH · publish_ready=false · NEED_SUPPLIER_DETAILS |
| `workspace build "chenille name bag" --mode embroidery` | WATCH · fib gate · embroidery supplier path |
| `workspace build "custom travel pouch" --mode both` | SKIP · POD-vs-Embroidery compare |
| `workspace build "gift for her" --mode both` | WATCH · better-angle generator · no publish |
| `workspace build "taylor swift hoodie" --mode pod` | **BLOCKED** (trademark) · no publish path |
| `supplier match "chenille name bag" --mode embroidery` | 50/100 embroidery supplier (SUPPLIER_PARTIAL) |
| `supplier match "usa raccoon shirt" --mode pod` | 25/100 (no POD supplier on file → VALIDATE_SUPPLIER_FIRST) |
| `daily-run` | harvest + autopull + summary written · **no publish** |
| `healthcheck` | all PASS except cron (WARN on Windows) |

## 6. Dashboard pages tested (Flask test client — all HTTP 200)

`/`, `/cheatsheet`, `/shops`, `/listings`, `/calendar`, `/suppliers`,
`/feedback`, `/grade`, `/spy` (embroidery / pod / both / no-keyword),
`/trending`, `/opportunities`, `/run` (all 5 modes),
`/run/export/{manager,seller,designer,researcher}`.

- Home: **no** "Archive — reports" card, **has** Cheat Sheet card, Spy card
  carries the mode.
- All 5 `/run` builds: `publish_ready=false`, **no live publish button**, draft
  wording present. `taylor swift hoodie` → BLOCKED.
- All 4 PDF role exports: 200, non-empty.

## 7. Spy — the three modes (verified live)

| Mode | Header | Supplier feasibility | Design rules |
|---|---|---|---|
| Embroidery (`chenille name bag`) | "· Embroidery" | Embroidery supplier 50/100 | stitch-safe, ≤6 colors |
| POD (`usa raccoon shirt`) | "· Print on Demand" | no POD supplier → VALIDATE_SUPPLIER_FIRST | print-ready |
| Both (`custom travel pouch`) | "· POD vs Embroidery" | POD 25 vs Embroidery 50 side-by-side | compare both |

## 8. "What if it fails" — verified safe behavior

- **Embroidery with no supplier match** → `VALIDATE_SUPPLIER_FIRST`,
  `PUBLISH_READY=false`, failed checks listed.
- **Spy / MCP returns nothing or is rate-limited** → graceful "data source
  unavailable" notice (no 500); empty sections say so.
- **Keyword too broad** (`gift`, `gift for her`) → better-angle generator, no
  publish.
- **Fewer than 13 clean tags / trademark caution / supplier partial** → publish
  gate fails with the exact reason; verdict never becomes SELL NOW.
- **`PUBLISH_READY=false`** → button reads Save Draft; **no** publish instruction.
- **PDF export error** → the page renders a "could not build it" message, not a
  crash.
- **`daily-run` step fails** → logged to `logs/errors.log`, other steps continue,
  summary still written.
- **Feedback with no numbers** → `NEEDS_MORE_DATA` (a logged `0` is treated as
  real data).

## 9. Remaining risks

- **No real POD supplier on file yet.** The library currently holds Embroidery +
  ShineOn CSVs, so POD supplier matches score low (correctly → VALIDATE_SUPPLIER_
  FIRST). Import a POD catalog CSV to raise POD matches.
- **Two supplier stores exist:** `supplier_ops` (dashboard/Spy) reads
  `data/suppliers/supplier_products.csv`; the legacy `listing_factory` CLI reads
  a root `supplier_products.csv`. They can disagree. The dashboard path is the
  authoritative one; aligning `listing_factory` is a follow-up (low urgency — the
  workspace supplier status is manual-confirm regardless).
- **Live data depends on the YTrends MCP.** If it's down, tools now fail *gracefully*.
- **`keywords.csv`** deletion breaks the legacy bare `python main.py` path only.
- **cron** installs on the Linux VPS; on Windows it prints the exact line.

## 10. Final readiness status

```
SYSTEM_READY_FOR_TEAM_USE : true
DASHBOARD_READY           : true
SPY_READY                 : true   (mode-aware POD / Embroidery / Both, verified)
SUPPLIER_MODULE_READY     : true   (mode-correct; conservative — confirms only with full fields)
FEEDBACK_LOOP_READY       : true   (full schema, Day-3/7 decisions, learning-fed)
PDF_EXPORT_READY          : true   (print-to-PDF, 4 roles, English only)
DAILY_AUTORUN_READY       : true   (robust to MCP outages; installs on the VPS)
PUBLISH_AUTOMATION        : false  (always — publishing is manual, human-gated)
```

**Recommendation:** ready for daily team use. On the VPS: `git pull` +
`sudo systemctl restart etsy-web`. Keep publishing manual — only list when the
workspace shows `PUBLISH_READY = true` and a human has confirmed supplier,
trademark, and the first image.
