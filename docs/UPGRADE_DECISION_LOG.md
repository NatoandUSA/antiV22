# Upgrade Decision Log

Reviewed the full spec against the current tool (V25.3) and my decision authority:
build only what **truly improves** the tool; don't duplicate, don't add clutter.
Legend — **Now** = built this round · **Have** = already exists · **Later** =
useful but deferred · **Skip** = not worth it / would add clutter.

| # | Request / Idea | Decision | Reason | Implement now? |
|---|---|---|---|---|
| 1 | Full audit + AUDIT_REPORT + readiness | **Now** | Ran commands, refreshed the report. | ✅ |
| 2 | Clean release package (`package release`, `.releaseignore`) | **Have** | Built V24.2; verified excludes `.env`/secrets. | — |
| 3 | GitHub/public reference research doc | **Now** | `docs/GITHUB_REFERENCE_RESEARCH.md`. | ✅ |
| 4 | Keyword Discovery 2.0 (combine 11 sources, big schema) | **Later** | High overlap with Trending/Opportunities/Spy/saved shops/learning already present; the real pain (junk results) is fixed by the product-fit filter below. Full multi-source merge is a large build for modest extra value — deferred. | — |
| 5 | **Product-fit / quality filter** | **Now** | The concrete pain: shop names, spells, brands, digital, broad seeds showing as opportunities. `src/product_fit.py` classifies every term; junk is hidden with a reason. **Highest-value functional upgrade.** | ✅ |
| 6 | Opportunity cluster engine | **Later** | Genuinely useful, but clustering is non-trivial and the product-fit filter already removes the noise that made raw keywords hard to use. Deferred as a focused next step. | — |
| 7 | Trending/Opportunities page fix (fit column, default filters, risky toggle) | **Now** | Wired the product-fit filter into both pages + a "Show risky / review" toggle. | ✅ |
| 8 | Seasonal calendar launch-status + range | **Now** | Added launch_status (PREP_NOW / PREP_EARLY / LATE_TEST_ONLY / NEXT_YEAR_PREP) + a range dropdown so passed windows aren't shown as fresh chances. | ✅ |
| 9 | Competitive Moat / private_advantage_score | **Have (mostly)** | Can-We-Win score + private-learning notes already answer "why we can win". A separate score would duplicate it; deferred a rename/merge. | — |
| 10 | Helium-10-style modules (Opportunity Finder, Reverse Engine, Keyword/Market Tracker, Listing Analyzer, Launchpad, Profit, Alerts, Ads Readiness) | **Have** | All built V24.0–V24.1. | — |
| 11 | Team management 2.0 (roles, pages, task types/status) | **Have** | Built V25.0–V25.3. | — |
| 12 | Per-section "Assign task" buttons | **Have (core)** | Launchpad card + run-page "Assign a task for this product" cover the intent. Per-section buttons in every workspace panel = marginal; deferred. | — |
| 13 | Team Calendar (Today/Week/Overdue views) | **Later** | The grouped My Tasks + overdue/due-soon alerts + status board already give deadline visibility. A full calendar view is a nice add but not essential; deferred. | — |
| 14 | Activity log + manager daily summary | **Have** | Built V25.0 (activity log + CSV + summary_today). | — |
| 15 | Manager review queue | **Have** | Built V25.0. | — |
| 16 | Dashboard cleanup (above-the-fold, no Archive) | **Have** | Archive removed V23.1; hero shows verdict/scores/next; Cheat Sheet present. | — |
| 17 | Workflow as a table | **Now** | Rebuilt WORKFLOW.md as a clean role→action→output table (kept bilingual per the user's earlier explicit request). | ✅ |
| 18 | Publish gate strict rules | **Have** | Manager sign-off gate (V24.2) enforces all listed checks. | — |
| 19 | Testing | **Now** | Added product-fit + calendar-status tests; selftest checks. | ✅ |
| 20 | Daily 6 AM auto-run + cron | **Have** | daily-run + cron install/status (V23). | — |

**Skipped (would add clutter / low value now):** a second keyword store duplicating
existing trackers; a standalone moat score duplicating Can-We-Win; Playwright (the
Flask test-client suite already covers the checklist).

**Guiding answers** (the 7 questions): the product-fit filter helps **find better
products** and **avoid junk**; the calendar fix helps **timing**; both keep the
dashboard **cleaner** (less noise), not messier. Everything else requested is
already present, so adding more would duplicate or clutter.
