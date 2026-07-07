# AUDIT REPORT — Etsy Product Manager V23.0

_Full system audit after the sales-execution + private-learning upgrade._
_English only. Nothing in this tool publishes to Etsy._

---

## 1. Summary

The tool was upgraded from a keyword/listing builder into a **sales-execution and
learning system** and then audited end to end. All automated checks pass
(`py main.py selftest` → **ALL CHECKS PASSED**, `pytest` → all green). The six
required test cases behave correctly, the daily 6:00 AM auto-run works and never
publishes, and the health check is green except cron (which only installs on the
Linux VPS, not this Windows dev box).

One deliberate deviation from the written spec: it asked for **bilingual
English/Vietnamese PDFs**, but the standing instruction (repeated in the same
request) is **English only**. English-only wins — no Vietnamese was built. Flag
this if the intent was actually bilingual.

**Bottom line:** ready for daily team use as a research → draft → track → learn
system. It never auto-publishes; publishing stays a manual human step gated on
`PUBLISH_READY = true`.

## 2. What was checked

- Backend modules, imports, and command routing (`main.py`, `src/*`)
- Publish-ready / verdict / score gate logic (safety-critical)
- Sales Feedback Loop, private learning system, supplier module
- Dashboard routes + buttons (Flask test client, all 200)
- Data pipeline folders + saved-run artifacts (JSON validity)
- Daily auto-run, health check, cron helpers, logging
- Role PDF exports (Manager / Seller / Designer / Researcher)

## 3. Bugs found

| # | Severity | Bug |
|---|---|---|
| 1 | High | **Offer Strength Score existed only as text — it did not gate.** SELL NOW and the publish gate ignored it, so a weak offer could pass. |
| 2 | Medium | SELL NOW did not require **First-Image ≥ 75** even though the score was computed. |
| 3 | Medium | Sales Feedback Loop used a thin schema and a non-standard action set; it wrote to `data/feedback.json`, not `data/performance/`. |
| 4 | Medium | No private-learning feedback into scoring — logged outcomes were not reused. |
| 5 | Low | Home page still showed the big "Archive — reports & exports" card the spec wanted removed; no Cheat Sheet card. |
| 6 | Low | Saved runs did not write `supplier_check.json`, `sales_forecast.json`, `product_line_expansion.json`, `publish_gate.json`, `feedback_tracking.json`. |
| 7 | Low | Two self-test assertions used the wrong string format (cron cron-syntax vs `HH:MM`, and a button located in the wrong module). Test-only, no runtime impact. |

## 4. Bugs fixed

- **#1/#2** — `offer_builder` now returns a 0–100 **Offer Strength Score** (7
  factors). `strict_verdict` SELL NOW now requires **overall ≥ 75, competition ≥
  55, no data flags, Can-We-Win ≥ 70, Launch-Readiness ≥ 85, First-Image ≥ 75,
  Offer-Strength ≥ 70**. `publish_gate` also fails on offer < 70.
- **#3** — `src/feedback.py` rewritten: full schema (URL, dates, mode, supplier,
  costs, price, title, image/mockup/offer, Day-1 impressions, Day-3/7 views,
  favorites, carts, orders, revenue, profit, refund). Day-3 **and** Day-7
  recommendations from the exact action set (KEEP / CHANGE_MAIN_PHOTO /
  CHANGE_TITLE / CHANGE_TAGS / RAISE_PRICE / LOWER_PRICE / MAKE_VARIANTS /
  KILL_LISTING / SCALE_PRODUCT_LINE). Saves to
  `data/performance/listing_feedback.{json,csv}` and mirrors
  `feedback_tracking.json` into the matching saved run.
- **#4** — new `src/learning.py` maintains 5 pattern files
  (`winner/failed/image/tag/supplier`). Every logged outcome updates them; each
  new run reads them and **nudges the Can-We-Win score** (a keyword/tag that has
  sold for us raises it; a refund-prone supplier lowers it) with a visible
  "🔒 Our private sales data" note.
- **#5** — Archive card removed from home; daily reports tucked into a small
  collapsible. Added a **Cheat Sheet** card.
- **#6** — `save_run` now writes all listed artifacts; every file validated as
  JSON in testing.
- **#7** — assertions corrected; self-test green.

## 5. Remaining risks

- **Supplier matching is intentionally conservative.** For "chenille name bag" it
  returns `SUPPLIER_PARTIAL` (50/100) — it will not mark a supplier
  `SUPPLIER_CONFIRMED` without complete fields, so publish stays blocked until a
  human confirms. This is by design, not a bug.
- **Shop "age" and "add-to-cart" are proxies** — Etsy/YTrends do not expose a
  shop-registration date or cart counts. The tool uses listing-age and
  favorites/conversion and says so; do not read them as literal.
- **Live data depends on the YTrends MCP.** If it is unreachable, live tools fail
  fast with a clear message rather than faking numbers.
- **cron** installs only on the Linux VPS; on Windows the command prints the exact
  line + a Task Scheduler hint.

## 6. Commands tested

| Command | Result |
|---|---|
| `py main.py selftest` | **ALL CHECKS PASSED** |
| `pytest -q` | all passed |
| `py main.py workspace build --keyword "usa raccoon shirt" --mode pod` | WATCH · publish_ready=false · supplier NEED_SUPPLIER_DETAILS |
| `... "chenille name bag" --mode embroidery` | WATCH · fib 74 blocks · supplier required |
| `... "custom travel pouch" --mode both` | SKIP · both-mode compare shown |
| `... "taylor swift hoodie" --mode pod` | **BLOCKED** (trademark HIGH) · no publish path |
| `... "gift for her" --mode both` | WATCH · better-angle generator · no publish |
| `py main.py supplier match --product "chenille name bag" --mode embroidery` | 50/100 SUPPLIER_PARTIAL |
| `py main.py daily-run` | harvest OK (1030 kw) · autopull OK · summary written · **no publish** |
| `py main.py healthcheck` | all PASS except cron (WARN on Windows) |
| `py main.py cron status` / `cron install --time "06:00"` | prints status + exact cron line |

## 7. Dashboard pages tested (Flask test client, all HTTP 200)

Home (`/`), `/shops`, `/listings`, `/calendar`, `/suppliers`, `/feedback`,
`/grade`, `/cheatsheet`, `/run` (workspace), `/run/export/{manager,seller,
designer,researcher}`. Home shows the tool cards (Trending, Opportunities, Spy,
Seasonal calendar, Saved research, Saved shops, Saved listings, Suppliers, Sales
feedback, Grade, Cheat Sheet) and **no** Archive card.

## 8. Supplier tests

- `supplier match` (embroidery + POD) runs and classifies mode correctly;
  chenille → `CHENILLE_PATCH`, returns `SUPPLIER_PARTIAL` when fields are thin.
- CSV import (ShineOn / Embroidery) and the supplier library UI (open catalog,
  sync, upload) are wired and covered by self-test.
- The six catalog `supplier sync` sources (Printify, BurgerPrints, Printway,
  CatKissFish, PGPrints, Merchize) are registered in
  `data/suppliers/supplier_sources.json` with open-catalog links; they pull
  manually (no scraping). Live network sync of each catalog was **not** run in
  this audit.

## 9. PDF export tests

Manager / Seller / Designer / **Researcher** reports build without error and open
as print-ready HTML pages (browser **Print → Save as PDF**; no external PDF
dependency). Each shows `PUBLISH_READY` and, when false, **"DRAFT ONLY — DO NOT
PUBLISH"** with the exact failed checks. **English only** (bilingual PDFs
intentionally not built).

## 10. Daily 6:00 AM auto-run status

`py main.py daily-run` verified end to end: pulls fresh YTuong keywords
(`data/processed/keyword_data.csv`), refreshes the shop/listing feeds, updates the
learning summary, writes `data/processed/daily_summary_<date>.json`, logs to
`logs/daily-run.log`, and **publishes nothing**. Timezone = server local time.

## 11. Cron / systemd status

Cron is not installed on this Windows dev box (expected). The install command
prints the exact line for the VPS:

```
0 6 * * * cd /home/etsy/etsy-agent && /usr/bin/python3 main.py daily-run >> logs/daily-run.log 2>&1 # etsy-agent-daily-run
```

Install on the VPS with `py main.py cron install --time "06:00"` (or paste the
line via `crontab -e`). `deploy/vps-build.sh` already runs the same pipeline
nightly and includes `autopull`.

## 12. Final readiness status

```
SYSTEM_READY_FOR_TEAM_USE : true
DASHBOARD_READY           : true
PDF_EXPORT_READY          : true    (print-to-PDF, English only)
SUPPLIER_MODULE_READY     : true    (conservative — confirms only with full fields)
DAILY_AUTORUN_READY       : true    (cron installs on the VPS)
PUBLISH_AUTOMATION        : false   (always — publishing is manual, human-gated)
```

**Recommendation:** cleared for daily team use. Run `py main.py cron install
--time "06:00"` on the VPS to schedule the auto-run. Keep publishing manual: only
list when the workspace shows `PUBLISH_READY = true` and a human has confirmed the
supplier, trademark, and first image.
