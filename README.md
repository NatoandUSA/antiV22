# Etsy Product Manager V27.3

**New in V27.3 — Spy fixed + Analyze bug + smarter Command Center.**
- **🕵️ Spy is self-contained again:** it now has its own keyword + product-mode +
  **Decode competitors** form (the previous version wrongly pointed to a removed
  button). Spy decodes the **competitors ranking for a keyword** — their titles,
  tags, price, image angle, who just launched, and the gaps to beat them.
- **Fixed the /Analyze bug:** the active button (Analyze vs Expand) now reflects
  the view you're on, and the page uses the theme (no more off-brand inline styles).
- **Command Center:** removed the 6 empty option boxes — those attributes are
  **AI-filled from live data inside the workspace** ("📝 Run inputs" panel), editable
  with source + confidence. No guessing up front.

**V27.2 — friendlier, faster UI (fewer steps, less clutter).**
- **Command Center** now shows just what you need — product mode + keyword +
  **Build full workspace**. The 6 optional fields and single-tool shortcuts moved
  into a **"＋ More options"** disclosure. Removed the duplicate Spy button (the
  richer Spy card stays).
- **Sales feedback** dropped from **24 fields to 6** up front (URL, keyword, price,
  Day-7 views, orders, revenue); the rest live under **"＋ More metrics"**.
- **Pulse strips** (like Team Tasks) added to **Launchpad** and **Profit Center**
  — see the board's health / your net at a glance — with confident lead copy.

**V27.1 — security hardening (from the full audit).**
- **XSS closed:** free-text inputs that flowed into markdown/HTML (the `/run`
  workspace options, the `/grade` listing fields, competitor titles) are now
  stripped of tag-injection characters at the boundary. A `javascript:` shop/listing
  URL can no longer become a live link.
- **Security headers** on every response (CSP, `X-Frame-Options: DENY`, nosniff,
  Referrer-Policy) as defense-in-depth.
- **Cookie:** set `WEB_SECURE_COOKIES=1` in the VPS `.env` to mark the session
  cookie HTTPS-only. Login no longer reveals whether an email exists.
- Audit confirmed the fundamentals are solid: **no SQL injection**, no dangerous
  eval/shell, debug off, pbkdf2 passwords + lockout, admin routes gated, no secret
  leakage, path traversal defended.

**V27.0 — full audit + the Embroidery-mode fix.**
- **Embroidery mode is no longer starved.** Switching to Embroidery used to show
  ~2 keywords vs POD's ~50, because a crude pre-filter dropped every design theme.
  Now product-fit (already mode-aware) decides: **POD and Embroidery each show ~50**,
  they *share* design themes (a theme can be printed OR embroidered) and *differ* on
  product-specific keywords (shirts/bags → POD; chenille/monogram/engraved → Embroidery).
  Wrong-mode real products are dropped silently instead of cluttering the "risky" list.
- **Audit:** selftest + pytest green, trademark keywords still **BLOCKED**, no
  auto-publish path, publish-gate invariant intact.

# Etsy Product Manager V26.9

**New in V26.9 — a real task scheduler + editable tasks + a polished board.**
- **Date + time picker:** the Due date field is now a native calendar + clock
  (`datetime-local`) — pick the day and the hour, no typing `YYYY-MM-DD`.
- **Edit / reassign tasks:** every card on Team Tasks has an **✏️ Edit** link —
  change the assignee, priority, status, due date/time, keyword, or title after it's
  created (owner/managers).
- **Professional redesign:** a **team-pulse** stat strip (Active / In progress / In
  review / Overdue / Completed), a **staff name + initial avatar** on every card (see
  who owns each job at a glance), clock-stamped due dates (overdue in red), and an
  encouraging header — built to make managing the team feel motivating, not clerical.

**V26.8 — team Tool Feedback.**
- Every team member gets a **💬 Tool Feedback** box (Team → Tool Feedback): pick a
  category (idea / bug / question) and write what to improve, add, or fix. They see
  their own submissions + status.
- The **Owner / managers** see the full list with an open-count badge on the hub
  card and a **✓ Mark resolved** (and Reopen) tick on each item. Stored in the team
  DB (`data/app.db`), separate from the listing *Sales feedback*.

**V26.7 — cleanup + disk hygiene + VPS self-fetch confirmed.**
- **`py main.py clean`** (laptop or VPS) reclaims disk: trims old `reports/runs`
  archives (kept newest 5), prunes stale keyword cache + `VACUUM`s `agent.db`,
  drops `__pycache__`/`.pytest_cache`. Freed ~107 MB on first run.
- The keyword cache now **self-prunes** (keeps ~3 days) on every warm, so
  `agent.db` can't grow without bound.
- **Confirmed: the VPS reaches the public MCP directly** — it runs its own
  every-6h `warm --fresh` cron; the laptop→VPS cache sync is now just a fallback.
- Cheat sheet rewritten: where-to-run each command, the `.venv/bin/python` rule,
  and a **"reopen the VPS"** guide.

**V26.6 — automatic keyword refresh (no manual runs).**
- **`py main.py warm --fresh`** — force a live re-pull (bypasses the per-day cache)
  so a scheduled run gets *current* data, not this morning's copy.
- **On the VPS (if it can reach the public MCP):** schedule it directly —
  `.venv/bin/python main.py cron install --every-hours 6 --command warm`. No laptop
  needed. (The YTrends MCP at `mcp.trends.ytuong.ai` is free/public/60-rpm-per-IP;
  the old datacenter-IP block was on the *cookie* website API, not the MCP.)
- **On the laptop (fallback if the VPS is blocked):** `deploy/schedule-warm.ps1`
  registers a Windows task that runs `deploy/warm-sync.ps1` every N hours
  (refresh cache + ship `agent.db` to the VPS). Needs passwordless SSH.

**V26.5 — the deep lists now reach the TEAM (VPS), not just the laptop.**
The live Trending/Opportunities pages read their keywords from a cache in
`data/agent.db`. The VPS can't fetch YTrends (blocked IP), and the deploy script
wasn't syncing that cache — so the team saw empty/stale keyword pages while the
laptop saw the deep lists. Now `deploy/push-to-vps.ps1` runs `py main.py warm`
(deep-pull the cache) and ships `agent.db` up with an **atomic rename**, so the
server shows the same 50-deep lists + clusters. Team logins/tasks/activity live in
a separate `data/app.db` and are never touched by the sync. New `py main.py warm`
command warms the cache on demand.

**V26.4 — deeper lists + instant first load.**
- **Deeper pull:** Trending/Opportunities now pull **100** and show up to **50**
  launch-ready keywords (was 60/30), so clusters get even richer.
- **Pre-warmed cache:** the daily run now pre-fetches these surfaces into the
  per-day cache (`warm_keyword_cache` step), so the team's **first** dashboard load
  of the day is instant instead of a multi-second live pull. Run `py main.py
  daily-run` on the fetching machine (or let cron do it at 06:00).

**V26.3 — 4–5× more keywords per page (root-cause fix).**
The YTrends API hands data out ~10 rows at a time and **ignores a big `limit`** —
so asking for 90 still returned 10, and after filtering junk you saw ~5. The tool
now **paginates** these surfaces (walking `offset`, deduping, skipping the odd
server-side "poison" row), so Trending/Opportunities pull ~60 and, after filtering,
show **40+ launch-ready keywords** with **substantial clusters** (e.g. Bag ×12,
Shirt ×7) instead of one tiny pair. First load of the day costs a few seconds;
every load after is served from the daily cache. Market Pulse + harvest get the
same depth. This was a *tool* limit, not a data-source limit.

**V26.2 — clusters that actually group, on both keyword pages.**
- **🧩 Product clusters on Trending AND Opportunities:** related keywords now
  collapse into one product idea keyed on the **product noun** — three "…bag"
  keywords become a single **Bag** idea; `summer/travel/bridesmaid pouch` → **Pouch**.
  Modifiers like "name" or "custom" no longer create fake clusters, and plurals are
  normalised (`decals` → `decal`). Each cluster suggests a base title so you build
  **one strong listing** that targets every keyword in it.

**V26.1 — more keywords, product clusters + a Team Calendar.**
- **More ideas to dig into:** the product-fit filter no longer over-hides — a
  keyword with no literal product noun (e.g. `coastal grandmother`, `retro sunset`,
  `50th celebrations`) is now a **design theme** you can put on any product, so it
  stays. Only real junk (shop handles, spells, brands, digital, broad seeds) is
  hidden. Source limits raised too.
- **🧩 Opportunity clusters:** Opportunities groups related keywords into
  **product clusters** so you build **one strong listing per cluster** instead of
  chasing each keyword.
- **📅 Team Calendar** (Team → Team Calendar): tasks by due date with
  Today / This week / Overdue / Upcoming views (managers see everyone; members see
  their own).

**V26.0 — product-fit quality filter + smarter seasonal timing.** Trending
and Opportunities now **hide junk** — shop handles (`haticemediumstudio`),
spell/psychic niches, trademark/brand terms, digital-only terms, and broad seeds —
each with a reason, behind a **"Show risky / review"** toggle. The seasonal
calendar now labels each event's **launch status** (PREP_NOW / PREP_EARLY /
LATE_TEST_ONLY / NEXT_YEAR_PREP) with a **range dropdown**, so a passed window
isn't shown as a fresh chance. Workflow is now a clean role→action→output **table**
(+ Vietnamese). See `docs/UPGRADE_DECISION_LOG.md` for what was built vs. deferred
(most of the requested modules already existed) and `docs/GITHUB_REFERENCE_RESEARCH.md`.

**V25.3 — "due soon" heads-up.** Before a task is actually overdue, tasks
due **today or tomorrow** now show a soft **🟠 Due soon** reminder — in the home
"My tasks" strip (orange), as its own group on My Tasks, and as an info alert.
It clears automatically once the task is done or rescheduled (and upgrades to the
red overdue warning if the deadline passes).

**V25.2 — a professional, tidy task experience.** Every member now sees a
**"My tasks"** reminder strip pinned to the **top of the home dashboard** (open
count + overdue in red). **My Tasks** is grouped (🔴 Overdue → To do → In progress
→ Awaiting review) with priority colours, a **"what 'done' means"** line per task
type, and one-click **Start → Submit for review** buttons. **Team Tasks** is a tidy
**status board** (To do / In progress / Awaiting review / Done) with the create
form tucked into a collapsible **➕ New task**. Assign and report both key off the
task type = workflow stage.

**V25.1 — overdue-task alerts + one-click Assign-task.** Tasks past their
due date now show up automatically in the 🔔 Alerts panel (and clear when done).
Managers can assign a task in one click from a **🚀 Launchpad** card or from the
**"Assign a task for this product"** bar on any workspace run (keyword pre-filled).

**V25.0 — team login, roles, activity tracking, tasks & manager approval.**
The dashboard is now multi-user. No auto-publishing — publishing stays manual and
manager-approved.

- **Per-user login** (SQLite `data/app.db`, passwords hashed with Werkzeug — no new
  dependency). Real `/login` (email + password + remember-me), `/logout`, `/me`,
  failed-login **lockout** (5 tries → 15 min), 12-hour session timeout, HTTP-only
  SameSite cookies.
- **7 roles / RBAC:** OWNER · ADMIN · MANAGER · SELLER · DESIGNER · RESEARCHER ·
  VIEWER. Only OWNER/ADMIN/MANAGER can approve a listing.
- **Activity log** (dashboard actions only — never keystrokes/screens/secrets):
  who logged in, searched, used Spy, built a workspace, checked suppliers, exported
  a PDF, updated feedback, approved/rejected. `Team → Activity Log` + CSV export.
- **Team tasks + Review Queue:** assign work, track status, approve/needs-fix/reject.
- **Manager approval:** approve a run *for manual publishing* — re-verified
  server-side against PUBLISH_READY; `MANAGER_APPROVED_FOR_MANUAL_PUBLISH` is
  logged; a known-brand can never be approved; `PUBLISH_AUTOMATION: false` always.
- **CLI:** `auth create-admin|create-user|list-users|disable-user|reset-password`,
  `activity list|export`, `task create|list|update`. Guide: `docs/USER_LOGIN_GUIDE.md`.

First run: set `ADMIN_EMAIL` + `ADMIN_PASSWORD_INITIAL` + `APP_SECRET_KEY` in
`.env` (owner auto-seeded), or `py main.py auth create-admin ...`.

**V24.2 — publish gate rebuilt with manager sign-off + release packaging +
schema validation + audit hardening.**

- **Manager sign-off closes the publish gate (safely).** Before, `PUBLISH_READY`
  could never become true (manual checks were hardcoded), so the team always saw
  "DRAFT ONLY". Now a **manager ticks each item** (supplier · competitor audit ·
  material/size/processing · image/mockup · trademark) on the workspace, and only
  then can `PUBLISH_READY` become true. The tool still **never publishes**, and a
  **known-brand trademark can never be cleared** by any confirmation.
- **`py main.py package release`** → a clean delivery zip (`.releaseignore` + a
  hardcoded safety net). **`.env`, `.git`, caches, logs, `*.pem` are never
  included**; only `.env.example` ships.
- **`py main.py validate data|run|suppliers|feedback`** + `src/schemas/*.json` —
  catches invalid JSON, missing headers, <13 tags, a CONFIRMED supplier missing
  cost/URL, and the PUBLISH_READY-with-failed-checks safety violation.
- **Bugs fixed:** alerts now auto-resolve (no stale Day-3/7 pile-up), market
  `opportunity` is now computed, `alerts` CLI is crash-safe.
- **66 tests** (new publish-gate + route suites) + internal Claude maintenance
  skills (`.claude/skills/`). See `AUDIT_REPORT.md`.

**V24.1 — Spy becomes a Competitor Reverse Engine + a sticky Home button.**

- **🕵️ Spy + Reverse Engine** — Spy now *decodes each top competitor's playbook*:
  their keyword/tag strategy, price positioning (premium/mid/budget vs the niche
  average), offer angle, estimated strength (sold · conversion · favorites), the
  specific weakness to beat, and **"our better angle" built from their gaps** —
  mode-aware, structural learning only, never copy. (Folded into Spy, not a
  separate page, to keep the dashboard lean.)
- **🏠 Easy Home button** — every secondary page now has a **sticky** accent Home
  button pinned to the top, so it's always one tap away even when you've scrolled
  down page 2 or 3.

**V24.0 — the sales-execution OS layer (Helium-10-inspired, Etsy-specific).**
Five new modules turn the tool from research into an operating system. All
self-populating, English only, no auto-publishing.

- **🔔 Alerts Center** (`/alerts`) — one "what needs attention today" list, auto-built
  from state (stale data, Day-3/7 reviews due, kill/scale flags, daily-run failures,
  problem suppliers). Home card shows the open count.
- **🚀 Launchpad** (`/launchpad`) — a Kanban launch board (Not started → Ready for
  manager → Published manually → Day-7 → Scaled/Killed) that **derives itself** from
  saved runs + feedback. No auto-publishing.
- **📊 Keyword + Market Trackers** (`/trackers`) — metrics over time, rising / falling /
  stable. **The 6 AM run snapshots them automatically.**
- **💰 Profit Center** (`/profit`) — real P&L per sale with the Etsy fee model
  (listing $0.20 · 6.5% txn · ~3%+$0.25 pay · 15% offsite); feeds supplier scores.
- **📋 Listing Analyzer** (`/grade`) — Listing / SEO / Buyer-Trust / Image sub-scores
  + a hard publish gate with the exact failed checks. Plus a manual **Ads Readiness**
  check (never runs ads).

Also fixed a real usability bug: the trademark check no longer flags normal 4-word
long-tail tags (e.g. "gift for dog mom") as slogans — brands + real slogans are
still caught. New `tests/test_os_modules.py` (12 tests) + `.pre-commit-config.yaml`
+ `docs/MARKET_GAP_RESEARCH.md`. Publishing stays manual, gated on `PUBLISH_READY`.

**V23.1 — Spy is mode-aware + full-system audit hardening.**

- **🕵️ Spy now respects Product Mode.** The bug where Embroidery mode was
  silently dropped is fixed: the mode flows form → route → `spy()`. Spy now shows
  a mode-correct **"Can we make this?"** supplier feasibility check (embroidery
  suppliers for embroidery, POD for POD), the right design rules (stitch-safe vs
  print-ready), an embroidery-compatibility read of the winners, and a
  POD-vs-Embroidery comparison in Both mode. Supplier matching is now mode-correct
  (embroidery is never satisfied by a POD/jewelry supplier, and vice-versa).
- **Sales Feedback Loop** extended to the full schema (run_id, Day-1/3/7
  impressions + views, timestamps) with an 11-value decision set including
  `NEW` / `NEEDS_MORE_DATA`; a logged `0` is data, missing is `NEEDS_MORE_DATA`.
- **Audit hardening (fail clearly & safely):** the self-serve tools and the
  6 AM `daily-run` now catch the MCP `SystemExit` (rate-limit/network) and show a
  graceful "data source unavailable" notice instead of a 500 / aborting the
  nightly job. The home page always shows the Command Center (even on a fresh
  deploy before any report sync). See `AUDIT_REPORT.md`.

Publishing is still always manual, gated on `PUBLISH_READY = true`. (English only.)

**V23.0 — a sales-execution & private-learning system.** The tool now
tracks results and learns which listings actually sell, so we beat competitors
who only have the same public keyword data. No auto-publishing — a listing is
only ever published manually when `PUBLISH_READY = true`.

- **Offer Strength Score (0–100)** joins Can-We-Win, Launch-Readiness, and
  First-Image as a hard gate: **SELL NOW now requires** overall ≥ 75, can-we-win
  ≥ 70, launch-readiness ≥ 85, **first-image ≥ 75, offer-strength ≥ 70**, clean
  supplier + trademark + 13 tags, and `PUBLISH_READY = true`. Anything short is
  **DRAFT ONLY — DO NOT PUBLISH**, with the exact failed checks listed.
- **Sales Feedback Loop** (`py` dashboard → 📉 Sales feedback): after a *manual*
  publish, log the listing's real numbers (Day-1 impressions, Day-3/7 views,
  favorites, carts, orders, revenue, cost, image/mockup/offer) and get one
  **Day-3/7 action** — KEEP / CHANGE_MAIN_PHOTO / CHANGE_TITLE / CHANGE_TAGS /
  RAISE_PRICE / LOWER_PRICE / MAKE_VARIANTS / KILL_LISTING / SCALE_PRODUCT_LINE.
  Saved to `data/performance/` + mirrored into the run's `feedback_tracking.json`.
- **Private learning system** (`data/learning/*.json`): every logged outcome
  updates winner / failed / image / tag / supplier patterns, and future runs use
  them — a keyword or tag that has sold for us **raises** its Can-We-Win score;
  a supplier that caused refunds **lowers** it. This is our edge.
- **Researcher** role report/PDF added (data + trademark + supplier checks).
- **Hands-off automation:** `py main.py daily-run` (pull + refresh + summary, never
  publishes), `py main.py healthcheck`, and `py main.py cron install --time "06:00"`
  / `cron status`. Clean logs in `logs/`. Home page no longer shows the Archive
  card. (English only.)

**V22.0 — auto-pulling learning feeds + a real seasonal planner.** Three
self-serve upgrades, all from the official YTrends MCP (never scraped):

- **🏪 Saved shops → Auto-pull new shops already selling.** One click pulls the
  fresh-winner feed, groups it by shop, and auto-saves the shops whose listings
  are all **recent (< 1 year)** with real sales and the **highest conversion**,
  ranked. (Etsy exposes no shop-registration date, so this is an honest
  *young-listing* proxy for a new shop.)
- **📌 Saved listings → Auto-pull young winners.** Pulls listings **under ~3
  months old** that already **outperform their niche**, ranked by performance,
  **conversion, views, favorites, and sales** — with a thumbnail and an "open on
  Etsy" link. (Add-to-cart is never public; favorites + conversion stand in.)
- **📅 Seasonal calendar → what to launch next, timed.** Upcoming holidays /
  e-com events with a **🚀 launch-by date** (≈6 weeks before the peak), a
  suggested product per mode, and keyword angles — merged with the **live rising
  keywords** from the index (peak date, opportunity grade, competition).

Both feeds auto-refresh nightly on the VPS (`py main.py autopull`, wired into
`deploy/vps-build.sh`). Learning only — study structure, **never copy**; nothing
auto-publishes. (English only.)

**V21.9 — Listing Grader + demand sparkline (learned from the best
open-source Etsy tools).** A **📝 Grade my listing** tool: paste a title, your 13
tags, and the description and get a **0–100 score with exact fixes** — keyword
front-loading, tag **character-packing** (how much of the 260-char tag budget you
use), typo and trademark cautions, and description gaps. Every workspace now shows
a **demand-over-time sparkline** (▁▂▃▅▇ from the keyword's 6-month timeline) with
a rising / flat / falling read, and the **🕵️ Spy** view lists the **tags the top
listings share** (reference only — write your own). Grade only — never
auto-publishes. (English only.)

**V21.8 — supplier ops + Sales Feedback Loop.** New CLI: `supplier sync`
(register a catalog supplier), `supplier import-csv --source shineon|embroidery
--file <csv>` (normalize into `data/suppliers/supplier_products.csv`), `supplier
match --product "..." --mode ...` (0-100 supplier match), and `workspace build
--keyword "..." --mode ...` (build + save a run from the CLI). On the dashboard:
a **🏭 Suppliers** library (all 8 suppliers, Open-catalog links, **CSV upload**
for ShineOn/Embroidery, Sync) and a **📉 Sales Feedback** loop — log a published
listing's real numbers and get a Day-3/7 **KEEP / CHANGE / KILL / SCALE**
recommendation. Never auto-publishes. (English only.)

**V21.7 — sales-execution brain.** The workspace now scores and gates on
what actually wins: a **Can We Win score** (12 advantages — gates SELL NOW; if
< 70 it won't recommend SELL NOW), a **Launch Readiness score** (10 checks —
gates publishing; must be ≥ 85), a **First Image Battle** (competitor pattern vs
our plan + score), an **Offer Builder** (better offer, bundles, upsell, trust),
and a **Better Angle Generator** (nearby angles to rescue a weak keyword). The
verdict, hero chips, publish gate, and Manager/Designer PDFs all use these. Also
added the supplier source registry (`data/suppliers/supplier_sources.json` +
6 POD catalogs + ShineOn/Embroidery). (English only.)

**V21.6 — supplier command flags + data audit trail.** `py main.py
supplier pod|embroidery "product" [--country US] [--suppliers Printify,Printway,…]
[--output file.csv]` now takes flags, **pre-fills real costs** from
`supplier_costs.csv` (so rows come back SUPPLIER_PARTIAL instead of empty),
marks digital products `PRODUCT_NOT_SUPPORTED`, and never invents a field.
And every `harvest` now writes an **audit trail**: raw pull →
`data/raw/ytuong/keywords_YYYY-MM-DD.json`, normalized →
`data/processed/keyword_data.csv` (with `source`, `raw_source_url`,
`data_check_status`). Nothing faked; suspicious rows are flagged.

**V21.5 — 🕵️ Spy tool.** A dedicated competitor-intelligence view: type a
keyword → **who dominates the niche** (top shops with listings/revenue/avg price/
country + saturation + new-entrant rate), **what's winning right now** (do NOT
copy), **who just launched**, and the **gaps to exploit**. Same official YTrends
MCP data (no scraping of the login-gated /spy page) — learning only. On the home
grid (🕵️ Spy) and as a Command Center button.

**V21.4 — clearer workspace + Manager audit fix.** The `/run` page is
reorganized so it's easy to follow: a **hero** (verdict + at-a-glance chips:
overall score, mode, publish-ready, trademark, next action), a **sticky jump
nav**, and five labelled groups (① Decision · ② Listing & supplier · ③ Design ·
④ Do next · ⑤ Export); the editable inputs are collapsed by default. **Manager
fix:** slogan/phrase keywords (no product noun) now fall back to an apparel cost,
so the supplier, margin, and sales-forecast profit are correct (previously the
forecast used zero cost and overstated profit).

**V21.3 — Saved Shops + Saved Listings.** A competitor-**learning**
library on the dashboard: save Etsy shops/listings you want to learn from, record
a structured analysis + your 0-100 scores, and (for listings with a main keyword)
pull **live market context** + an **original-angle** suggestion. Market learning
only — the tool never scrapes Etsy and repeats "study structure, never copy
artwork/titles/photos/branding." Saved to `data/saved_*.json` (persist on the
server). Home cards: 🏪 Saved shops · 📌 Saved listings.

**V21.2 — PDF exports + AI-suggested editable fields.** Each run now opens
with an **AI-filled, editable input panel** — every field (product type, niche,
customer, occasion, style, personalization, mode) shows the **AI suggestion,
source, and confidence**, and you can edit + re-run. And there are **Manager /
Seller / Designer report exports**: each opens a clean, print-ready page — use
the browser's **Print → Save as PDF** (English; no dependencies, works on the
VPS). Save writes the JSON files as before.

**V21.1 — Action-center workspace.** The Command Center now has a
**Product Mode toggle (POD / Embroidery / Both)** at the top that controls the
whole run (Both shows a side-by-side POD-vs-Embroidery recommendation). Each run
adds: a **strict verdict** (SELL NOW / VALIDATE / WATCH / SKIP / BLOCKED) that
gates the UI (WATCH/SKIP/BLOCKED never say "publish"), a **strict Publish-Ready
QA gate** with `FAILED_PUBLISH_CHECKS`, a **fixed 13-tag builder** (always 13,
typo auto-fix, trademark-caution blocked, per-tag type + status), **How We Beat
Competitors**, **Competitor Audit**, **7-day Sales Forecast**, **Product-Line
Expansion**, **Source Confidence + data-check**, and **mode-specific Design Risk
warnings**. Daily reports moved under **Archive**. Save writes JSON files under
`reports/latest/runs/`. Bilingual Manager/Seller/Designer PDF export is next.

**V21.0 — Instant Product Command Center.** The dashboard home page is now
a command center: type one keyword (plus optional niche / occasion / customer /
style / personalization / supplier type) and **Build full workspace** →
`/run` renders one interactive page with a **product verdict**, **9 opportunity
scores (0–100)**, market & keyword opportunity, niche angles, an **automatic
listing builder** (title + 13 tags + description + real cost/margin), an
**internal product preview** (marketplace-style, no Etsy branding), **design
prompts** (POD + stitch-safe embroidery), a **seller checklist**, a **designer
brief**, and copy/save/export — never auto-published. The Instant Tools
(Analyze / Expand / Should I sell? / Build listing) and reports are unchanged.

**V20.8 — hands-off builds + richer listing drafts.** The data layer is
now **MCP-first**, so the whole report pipeline can build **on the VPS itself**
(the MCP is reachable there; no cookie, no laptop). Point cron at
`deploy/vps-build.sh` and the dashboard refreshes 24/7 with your PC off. The
**Draft listing** tool now shows the **real supplier cost, margin, and a
recommended price** (e.g. "at $34 you'd make $10.25/sale; price ≥ $32 for ~$8
profit").

**V20.7 — Self-serve Team Tools dashboard.** The portal home page now
leads with live, self-serve tools any teammate can use anytime (no terminal, no
waiting on the operator), all powered by the YTrends MCP and running on the VPS
24/7:
- **Analyze** a keyword (demand, price, competition, what's winning, related keywords)
- **Should I sell?** — GO / CONDITIONAL / NO-GO verdict with reasons
- **Expand** — related keywords · **Draft listing** — title + 13 tags + price + description
- **Trending now** / **Opportunities** (per line) · **Seasonal calendar**

Every tool has the trademark check built in. The read-only daily reports (built
by the operator) sit below the tools. (Needs the server to reach the YTrends MCP.)

**V20.5 — Keyword harvester.** `py main.py harvest` pulls a deep,
data-driven keyword universe from the live YTrends index (top rankings +
opportunities + trending + targeted POD/embroidery search), filters out digital
/ off-domain noise, and writes `keyword_data.csv` so the ideas + manager reports
research it. This took Embroidery from ~13 keywords to 200+, and the demand
floor is now niche-aware (Embroidery is premium/low-volume). The sync runs it
automatically before each build.

**V20.4 — Live Market Pulse.** Every `daily` run builds a **Market Pulse**
report (per mode: Print on Demand + Embroidery) straight from the official
**YTrends MCP** live index — trending keywords, hidden gems, winning listings
(market intel, never copy), and the seasonal calendar — each cross-checked
against **Google Trends** (Pinterest and X switch on when you add their tokens
to `.env`). It's the first card on the team dashboard. PDF export was removed;
reports are Markdown-only. See [SUPPLIERS.md](SUPPLIERS.md) for data sources.

> 📋 **New here? Read [CHEATSHEET.md](CHEATSHEET.md)** — every command in plain
> language, grouped by what you want to do.

## Run it on a new computer (Mac M1 / Windows / Linux)

The tool is pure Python and cross-platform. To set it up on another machine
(e.g. a MacBook Pro M1):

    # 1. Get the code
    git clone https://github.com/NatoandUSA/etsy-agent.git
    cd etsy-agent

    # 2. Create an isolated environment (recommended)
    python3 -m venv .venv
    source .venv/bin/activate         # Windows: .venv\Scripts\activate

    # 3. Install dependencies
    pip install -r requirements.txt

    # 4. Add your secrets (NEVER commit this file)
    cp .env.example .env              # Windows: copy .env.example .env
    #   then edit .env and fill in your real API tokens

    # 5. Verify + run
    python3 main.py selftest          # health check, no network needed
    python3 main.py daily             # the daily command

On macOS/Linux use `python3`; on Windows use `py` or `python`. Everything
in this README that shows `py main.py` works the same as `python3 main.py`.

Your `.env` (API tokens/cookies) is git-ignored and stays on each machine —
copy it over manually or re-fill it from `.env.example`. To pull the latest
changes on any machine later: `git pull`.

## Simple daily workflow (this is all most people need)

    python main.py selftest      <- after install/update only: health check
    python main.py daily         <- the daily command: makes the 5 reports
    python main.py listreports   <- shows where the reports are
    python main.py openreports   <- opens the report folder

## What to read (in this order)

    reports/latest/
      00_START_HERE.md                        <- navigation + today's status
      01_MANAGER_ACTION_REPORT.md             <- Manager: decisions, blockers,
                                                 publish permission
      02_MARKET_KEYWORD_OPPORTUNITY_REPORT.md <- Researcher: keyword ranking,
                                                 ideas, discover, performance
      03_SELLER_EXECUTION_REPORT.md           <- Seller: drafts, title/tags,
                                                 QA (drafts only!)
      04_DESIGNER_BRIEF_REPORT.md             <- Designer: briefs + prompts

Every run is also archived with exact time in reports/runs/, including
raw_data/ and archive_debug_reports/ (the detailed reports live there).

## Which command first, and why

- selftest: only after install or update - proves the tool is healthy.
- daily: the normal team command, run at end of day (or morning).
- listreports: find the newest reports any time.
- openreports: open the folder; start from 00_START_HERE.
- rawreports / manager / market / seller / designer / tasks / blockers /
  statusboard / finalqa / performance / grow / discover / supplier /
  printify / expand / listing: advanced or debug - normal team members
  do not need these.

## Publishing safety rule

Seller may publish manually only when 01_MANAGER_ACTION_REPORT says
Publish Allowed = YES and Final QA status is PUBLISH_READY.

## If reports say DATA_UNAVAILABLE

The run still produces all 5 reports; they name the fix: refresh
YTRENDS_COOKIE in .env or provide fresh keyword_data.csv. No product
moves forward, no publishing, until data is restored.

## SAFETY - read first
- This tool NEVER publishes to Etsy. All publishing is manual.
- It never scrapes Etsy or automates the Etsy website.
- PUBLISH_READY appears only when every evidence gate passes
  (see src/publish_gate.py - the single source of truth).
- Flagged/suspicious data can never drive product decisions.
- Supplier truth lives in supplier_products.csv (supplier_costs.csv
  is cluster-level estimates only).

## Manual Etsy review checklist (before ANY publish)
[ ] Supplier verified: URL + material + size + cost + processing,
    last_verified date filled in supplier_products.csv
[ ] Production partner disclosed in Etsy listing settings
[ ] Original design confirmed (seller_original_design_confirmed=yes)
[ ] Trademark: USPTO checked + link saved, or manager approval logged
[ ] Etsy policy reviewed (prohibited/mature/reselling)
[ ] Title approved (validator passing, buyer-readable)
[ ] 13 tags approved (validator passing)
[ ] Photos/mockups honest - show the real product
[ ] Price/margin approved (real costs, >= $6 net)
[ ] Shipping/processing accurate in the listing
[ ] manual_review=yes recorded in supplier_products.csv

## What this tool does NOT do
No auto-publishing, no Etsy scraping, no legal advice, no sales
guarantees. It prepares and gates; your team decides.

# Etsy Agent - Niche Research (Phase 1)

Finds rising, low-competition niches for your POD/embroidery shop using
Google Trends (free), with a ready slot for the YTrends API.

## Setup (one time)

1. Install Python 3.10+ from https://python.org (check "Add to PATH" on Windows).
2. Open this folder in VS Code (File -> Open Folder).
3. Open the terminal in VS Code (Ctrl+`) and run:

   pip install -r requirements.txt

## Run it

   python main.py

It reads `keywords.csv`, checks 12-month Google Trends momentum for each
keyword, scores every niche, and writes a ranked report into `reports/`.

## Weekly workflow

1. Add new keyword ideas to `keywords.csv` (one per line).
2. Fill the `competition` column: search the keyword on Etsy and copy the
   listing count (or read it from YTrends). This makes scores far more accurate.
3. Run `python main.py`.
4. Designer works only on DESIGN_PREP_READY items. Seller may prepare drafts only; publish manually only after PUBLISH_READY.
5. Never automate the Etsy website itself. All publishing is manual copy-paste.

## Discover mode (live YTrends data)

   py main.py discover

Pulls YTuong's top-revenue keywords + trending + hidden gems, then:
- marks FOCUS picks: sellable POD/embroidery product, <=300 Etsy
  listings (or LOW level), 500+ views/day, conversion >=2%, rising,
  and no known trademark hit
- shows Etsy listing count + seller count + 24h views per keyword
- flags trademark risk: HIGH (known brand - skip) and CAUTION
  (slogan-like - verify at tmsearch.uspto.gov before designing)
- filters out shop-name junk and service keywords automatically
Results cached per day; safe within your 800/day API quota.

## Expand a niche

   py main.py expand "chenille name bag"

Shows 20 related keywords (with listings count, revenue, conversion,
and trademark flag) so you can build out a niche you like.

## Top performers

The discover report now includes the top 3 Etsy listings per FOCUS
keyword: title, price, sold, revenue, listing age, link, and the tags
the winners share. MARKET INTEL ONLY - never copy a design or title.

## Category intelligence

   py main.py categories

Ranks Etsy's categories by revenue-per-seller so you know where the
money concentrates (e.g. Jewelry pays ~$4,800/seller).

## Authentication

Prefer YTRENDS_API_TOKEN in `.env`. A session cookie is supported only as a fallback and must never be shared or committed. If a cookie expires, refresh it manually; do not automate browser access.

## Best Etsy Idea Report (cluster mode)

   py main.py ideas

Groups keywords into product clusters, scores each on demand,
competition, conversion, AOV, momentum, profit margin, IP/policy
safety, and differentiation (weighted), then gives verdicts:
DESIGN NOW / VALIDATE FIRST / SKIP. Auto-rejects services, passed
seasons, thin margins, low demand, and unverified trademark risks.
Includes first-5-designs, title formula, 13 tags, pricing target,
and a 7-day validation plan per winning cluster.

Team inputs the agent depends on:
- costs.csv        -> one row per supplier per cluster; agent auto-picks
                      the cheapest. REPLACE placeholders with real prices
                      from each supplier dashboard (see SUPPLIERS.md)
- tm_verified.csv  -> log every USPTO check (keyword, CLEAR/BLOCKED,
                      link, who, date); CAUTION keywords stay rejected
                      until logged here

## Listing Factory (goi listing hoan chinh)

   py main.py listing "chenille name bag"

Tao goi listing DRAFT: TITLE + 13 TAGS + DESCRIPTION (tieng Anh,
dan thang vao Etsy), gia ban kem loi nhuan uoc tinh, link 3 doi thu manh
nhat, checklist 10 anh/mockup, va 14 buoc dang tren Shop Manager - tat ca
huong dan bang tieng Viet. Tu khoa dinh thuong hieu HIGH se
bi chan; CAUTION se co canh bao kiem tra USPTO truoc.

## Printify integration (real costs)

   py main.py printify "pouch"       -> find matching Printify products
   py main.py printify cost 1090     -> print providers + REAL US shipping

Needs PRINTIFY_API_TOKEN in .env (Printify -> My Profile -> Connections,
catalog.read scope). Shipping comes from the API; blank-product base cost
you read once from the Printify catalog page. Put both in costs.csv, then
rerun `py main.py ideas` for true profit numbers.

## Etsy Product Manager AI (lenh chinh moi)

   py main.py manager

Bao cao quan ly san pham 12 muc: quyet dinh (DESIGN NOW / VALIDATE FIRST /
WATCHLIST / SKIP / BLOCKED / WAIT FOR TM CHECK), cluster tot nhat + diem
/100, 5 brief cho designer, mo hinh loi nhuan day du, audit doi thu (loc
relevance >= 0.75), 2 goi listing da kiem tra (dung 13 tag), bang tu khoa
bi loai + cach cuu, hang doi trademark, ke hoach 7 ngay, va QA validator
15 muc (READY / NEEDS_FIX). Xuat: .md (song ngu), .json (may doc),
tasks_*.md (viec cho designer/seller/researcher/trademark).

Legacy notes - BAN HANG TOT HON DOI THU (sales execution):
- Muc 1b "Tom tat hanh dong ban hang": tra loi 11 cau hoi (ban gi, vi sao,
  thiet ke gi, supplier nao, lai bao nhieu, listing the nao, kiem tra gi,
  test gi 7 ngay, nhan rong the nao) trong 1 trang.
- Muc 6b "Kiem tra tin hieu da nguon": Google Trends chay TU DONG cho tu
  khoa cua cum tot nhat; Pinterest/X khong co API gia re nen researcher
  kiem tra tay 5 phut roi dien social_signals.csv (he thong tu tao mau,
  KHONG BAO GIO bia tin hieu). Verdict: CONFIRMED / MIXED / ETSY_ONLY /
  DECLINING.
- Muc 9c "Ke hoach loi the canh tranh": 11 chien thuat co bang chung +
  nguoi phu trach (anh dau tien, mockup, ca nhan hoa, goc ngach, bundle,
  gia, SEO, uy tin, ship ro rang, video, mo rong dong san pham). 3 loi the
  hang dau duoc bom thang vao prompt cua designer.
- Du lieu tu khoa TU LAM MOI: keyword_data.csv cu hon hom nay -> tu keo
  lai + grow.

V16 - TU DONG MO RONG TU KHOA & NGACH (grow):
   py main.py grow                          (tu dong: viral + hidden gem +
                                             goi y tu ngach cua ban)
   py main.py grow "embroidered sweatshirt" (dao sau 1 ngach cu the)
   py main.py grow pod / grow embroidery    (theo dong san pham)
Tu dong cap nhat: keywords.csv (kem so listing canh tranh), niches.txt
(danh dau auto-added de ban duyet), keyword_data.csv (manager cham diem
ngay lan chay sau). Loc trung lap, junk, dich vu, trademark HIGH.
Demand duoc suy ra trung thuc: views/ngay = tong ban/ngay : ty le mua.
'py main.py manager' cung tu grow khi keo du lieu moi. Quota: ~15 call.

V15 - MOI:
   py main.py manager pod          (chi tu khoa print-on-demand)
   py main.py manager embroidery   (chi tu khoa theu)
Moi lan chay manager tao them 2 file cho team:
- design_prompts_*.md: prompt san sang COPY-DAN vao Claude/Claude Design
  cho tung thiet ke (kem du lieu best seller Etsy + spec san xuat POD/theu)
- seller_pack_*.md: chi tiet listing theo DUNG thu tu dan vao Etsy
Bao cao manager gio co du 2 ban: tieng Anh (goc) + _VI.md tieng Viet.

V14 - LENH SUPPLIER (2 lenh moi):
   py main.py supplier pod "clear concert bag"
   py main.py supplier embroidery "chenille name bag"
Tao ho so supplier vao supplier_products.csv (Printify keo truc tiep qua
API; ShineOn/BurgerPrints/Printway khong co API du lieu -> team dien tu
dashboard). San pham chi PUBLISH_READY khi 1 dong supplier dat
SUPPLIER_CONFIRMED. Bao cao luon in 3 trang thai: QA_REPORT_READY /
DESIGN_PREP_READY / PUBLISH_READY.

QUY TAC XUAT BAN (publish gates): moi listing package co 2 trang thai:
DESIGN_PREP_READY (designer duoc chuan bi mockup) va PUBLISH_READY (seller
duoc dang). PUBLISH_READY chi khi du 7 dieu kien: audit doi thu dat, supplier
xac nhan material/size/processing (dien vao supplier_costs.csv), tu khoa
chinh khong bi DATA_CHECK_REQUIRED, trademark da xac minh/chap nhan duoc,
du 13 tag, khong con placeholder, va lai >= $6. Muc 0 cua bao cao liet ke
moi thu dang chan - KHONG duoc dang khi muc 0 con o trong.

Kiem tra cai dat:  py main.py selftest  (khong can API, khong can mang)

Input files (tu tao mau neu thieu): keyword_data.csv (tu dong keo tu
YTrends neu chua co), supplier_costs.csv, tm_verified.csv,
competitor_audit.csv. Xem SYSTEM_PROMPT.md de hieu toan bo quy tac.

## Modes: POD vs Embroidery

   py main.py discover pod          py main.py ideas pod
   py main.py discover embroidery   py main.py ideas embroidery

Loc ket qua theo dong san pham. Khong ghi mode = tat ca.
Embroidery = tu khoa chua: embroider/chenille/monogram/applique/
stitch/patch/crochet/knit. POD = phan con lai.

## Song ngu (bilingual)

Moi bao cao xuat 2 file: report.md (tieng Viet) va report_EN.md
(tieng Anh) - cung noi dung, cung so lieu.

Noi dung huong dan trong bao cao viet bang tieng Viet; tu khoa va so
lieu giu tieng Anh vi Etsy la thi truong tieng Anh.

## Next upgrades (do these in Claude Code)

- Wire in the YTrends API: see instructions inside `src/ytrends_client.py`.
- Phase 2 "Listing Factory": drafts title + 13 tags + description per niche.
- Phase 3: import Etsy Stats CSV exports to learn what converts.

## Safety rules baked in

- Secrets live only in `.env` (git-ignored). Never in code, never in chat.
- No scraping or automation of etsy.com. Data comes from YTrends' API,
  Google Trends, and your own manual CSV exports from Shop Manager.
