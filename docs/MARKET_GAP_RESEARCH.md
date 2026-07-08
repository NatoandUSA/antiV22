# Market-Gap Research — Etsy Sales Execution Manager

_What the big tools do, what we already have, and what we deliberately build vs.
skip. Positioning: we are a **sales-execution + private-learning system**, not
another research tool. English only. No auto-publishing, ever._

---

## 1. Market tools reviewed (as inspiration, not to copy)

| Tool | What it's great at | The gap for a POD/embroidery team |
|---|---|---|
| **Helium 10** (Amazon) | Black Box product research, Cerebro reverse-ASIN, Keyword Tracker, Listing Analyzer, Product Launchpad, Market Tracker, Profits, Alerts | Amazon-only; no Etsy supplier/POD/embroidery reality; no manual-publish discipline |
| **Alura** (Etsy) | Keyword/product research, shop analyzer, listing helper, shop analytics | Research-first; doesn't drive execution, supplier confirmation, or a launch process |
| **EverBee** (Etsy) | Sales/revenue/conversion/views/favorites estimates, trend filters, tag analyzer | Great data, no "can WE make + win this" (supplier, first image, offer, learning) |
| **eRank / Marmalead / Koalanda** (Etsy) | Keyword research, trend tracking, SEO checks, competitor/shop research | SEO-centric; no P&L, no launch board, no private win/loss learning |

**Takeaway:** every public tool helps sellers *research*. None help a supplier-based
team *execute and learn*. That's our lane.

## 2. Useful features found (worth adapting, Etsy-specific)

- Reverse-engineer a competitor's keyword/tag/angle strategy (Cerebro idea).
- Track a keyword/niche's metrics over time → rising / falling / stable.
- A listing analyzer with sub-scores + a hard publish gate (Listing Analyzer).
- A launch pipeline / Kanban from idea → post-launch (Product Launchpad).
- A market/niche watchlist with change alerts (Market Tracker + Alerts).
- Real P&L per product with the platform's fee model (Profits).
- Tag character-packing + tag frequency across winners (eRank/Marmalead).

## 3. What our tool ALREADY has (V21–V23)

- Instant Command Center: keyword → full workspace (verdict + scores + listing +
  design + publish gate).
- **Opportunity Finder** built in: verdicts (SELL NOW / VALIDATE / WATCH / SKIP /
  BLOCKED) gated on Overall ≥75, Can-We-Win ≥70, Launch ≥85, First-Image ≥75,
  Offer ≥70, supplier confirmed, 13 clean tags, PUBLISH_READY.
- **Can We Win**, **First Image Battle**, **Offer Builder** (all scored + gating).
- **Spy** — mode-aware competitor intelligence + supplier feasibility + "tags the
  winners share" (this IS the Cerebro-style reverse engine for Etsy).
- **Supplier module** — POD catalogs + ShineOn/Embroidery CSV, mode-correct match.
- **Sales Feedback Loop** + **private learning** (winner/failed/image/tag/supplier
  patterns feed future scoring).
- Auto-pull Saved Shops/Listings, seasonal planner, role PDFs (Manager/Seller/
  Designer/Researcher), daily-run + healthcheck + cron.

## 4. What was MISSING (built in V24)

- **Alerts Center** — no single "what needs attention today" view. → `src/alerts.py`
- **Keyword + Market Trackers** — metrics weren't tracked over time. → `src/tracking.py`
- **Profit Center** — no real P&L with the Etsy fee model feeding supplier scores.
  → `src/profit.py`
- **Launchpad** — no launch pipeline / board. → `src/launchpad.py`
- **Listing Analyzer** — the grader didn't split SEO/Trust/Image or gate publish.
  → `interactive.analyze_listing`
- **Ads Readiness** (manual) — no "is this worth testing Etsy Ads" check.
  → `interactive.ads_readiness`

Design choice: the trackers **auto-snapshot** in the 6 AM run and alerts
**auto-generate** from state, so a non-technical team reads a board instead of
maintaining forms.

## 5. What we deliberately did NOT build

- **No Etsy account automation / auto-publishing.** No Seller-Central connection,
  no auto-post, no "click publish." Publishing stays a manual, manager-gated act.
- **No paid ad execution.** Ads Readiness only *advises*; it never runs ads.
- **No competitor scraping.** All data comes from the official YTrends MCP; Spy
  studies structure only — never copies art/titles/photos.
- **No clone of eRank/EverBee dashboards.** We don't chase feature parity on pure
  research; our edge is execution + private data.

## 6. GitHub / open-source patterns reviewed

| Pattern | What we learned | How we applied it |
|---|---|---|
| **pytest** | Small, fast, isolated unit tests | `tests/test_os_modules.py` — 12 offline tests for the new modules |
| **Flask test client** | Route/integration tests without a browser | Dashboard route tests (all 200) in the audit run |
| **JSON stores + CSV mirror** | Human-readable + spreadsheet-friendly | Every new module writes `*.json` + `*.csv` |
| **pre-commit** | Cheap lint/format/JSON-validity gate | `.pre-commit-config.yaml` (ruff + file hygiene + local selftest hook) |
| **Etsy fee models (public docs)** | Listing $0.20, 6.5% txn, ~3%+$0.25 pay, 15% offsite | `profit.compute()` |
| **Kanban/board data model** | Derive columns from item state | `launchpad.board()` derives stage from run + feedback |
| **Playwright (e2e)** | Browser-level dashboard tests | Deferred — Flask test-client already covers routes; documented as next step |

**License caution notes:** we studied *patterns and public docs only*. No code was
copied from any repository. We use permissive, widely-installed libraries already
in the project (Flask, Markdown, requests, pytest). Any new dev tool (ruff,
pre-commit) is opt-in and MIT/Apache-licensed. Etsy fee percentages come from
Etsy's public help pages, not from any scraped or proprietary source.

## 7. Recommendation / next steps

- **Next turn:** a standalone **Competitor Keyword Reverse Engine** page (paste a
  competitor URL/shop → structured keyword/angle/price/image read — most of this
  already lives in Spy) and **Playwright e2e** for the critical dashboard flows.
- Keep the dashboard lean: the new modules are cards + collapsible pages, and the
  home page still leads with the Command Center.
- Import a **POD supplier CSV** so POD matches score high (today only Embroidery +
  ShineOn are on file, so POD correctly reads VALIDATE_SUPPLIER_FIRST).
