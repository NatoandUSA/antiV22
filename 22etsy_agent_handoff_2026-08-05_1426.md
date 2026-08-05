# 22etsy-agent — Handoff · 2026-08-05 14:26 (+07)

_Session owner: Alex (Hue, Vietnam). **Supersedes `22etsy_agent_handoff_2026-08-04_0016.md`**,
which supersedes 2026-08-03 11:08 → V37.11 → V37.8 → V37.5. Read this file first; where they
disagree, the newest wins._

Repo `D:\Claude\22etsy-agent` · GitHub `NatoandUSA/etsy-agent` · VPS `~/etsy-agent`, service `etsy-web`.
Live: https://etsy.theglobalserviceteam.site

---

## 0 · Status

**Tests: 598 collected, 598 pass, 0 fail.** The suite is fully green for the first time — see
§4 for why the long-standing failure was never what the last two handoffs said it was.

**Nothing is committed.** The tree carries this session's work plus the previous session's
uncommitted phase-4 re-point (`PHASES[4]["route"] = "/imports"` + the matching `WORKFLOW.md`
line), which answers §5 item 1 of the last handoff and is kept.

`src/version.py` is now `37.13` and `README.md` matches — the selftest pins the two together and
caught the mismatch when only one was bumped. Deploy not attempted this session.

---

## 1 · The headline: the engine was starved, not mis-tuned

`0 BUILD_NOW` was blamed on long-tail supply. Measured, it was mostly **a field the enricher
never copied.**

`ytrends_mcp.research_keyword()` has always returned `total_revenue`, `avg_revenue` and
`avg_views_24h`. `shortlister_integration._enrich_row()` read **none of them**.
`opportunity_score._demand_from()` needs revenue or views; without either the row is
`core_missing` → `overall_score = None` → WATCH. So **every Keyword Lab and winner-derived
candidate was capped at WATCH by construction** — not a scoring bias, a missing copy.

Proof — one keyword that had sat in the master since **2026-07-09**:

```
mini bride tote bags
  before: etsy_listings 7 · source mcp:ranking · every other column blank
          -> score None -> WATCH, buried among 1,266 rows, for 27 days
  after : $58,415 niche revenue · 4.36% conv · 169 views/24h · 3 sellers hold 7 listings
          -> 81.2 GO -> BUILD_NOW · sellability 87.0 PUSH
```

The first BUILD_NOW row this system has produced.

### 1.1 · The same call also fabricated a competitive advantage

For a keyword it has never indexed, the MCP answers `total_listings: 0`, `total_sellers: 0`,
nulls elsewhere — and sometimes `competition_level: "low"`. The old `put()` accepted the zero
**and returned True**. Measured, on the same keyword:

| | before | after |
|---|---|---|
| `_enrich_row` on an unknown keyword | returns **True** | returns **False** |
| …what it leaves in the row | `listing_count 0.0 · seller_count 0.0 · competition_level low` | `{}` |
| …the master cell it wrote | `'0.0'` | `''` |
| …that row's score once revenue arrives | **67.6 CONDITIONAL** | **None WATCH** |

`_competition()` reads 0 listings as **90.0 — a better market than a genuinely open 38-listing
niche at 75.2.** Same family as the constant-85 opportunity signal (V30.1), the flat-50 private
boost (V33) and the hardcoded seasonality leg. A `competition_level` label arriving with no
counts behind it is now ignored for the same reason.

---

## 2 · Everything else found and fixed

1. **Home told the team to do the wrong thing every morning.** `current_step()` returned the
   first not-ready step. Steps 4–9 and 11 were ready and 9 winner candidates sat unsent at step
   10, but home said *"Open Pinterest trends"* — step 2 is first-not-ready and always will be.
   Steps 2 and 3 are now `advisory`, which is what the code already says of them
   (`feasibility_gate`: *"advisory, displayed only"*; the gate cannot block until coverage is
   `complete`). Nothing is hidden — phase 1 still renders `todo 1/3 · next=2`.
2. **The enrichment queue could not reach anything that needed enriching.** It filtered on
   `source endswith '-lead'`; the master has **zero** lane leads, so the button never rendered
   while **843** rows scored None. Now keyed on the condition the scorer actually applies.
3. **The test suite wrote into production data.** `ytx_import` hardcoded `Path("data/history")`
   while honouring `path=`, so every `pytest` run appended to the real
   `data/history/keyword_snapshots.csv`. All 74 rows in it were the test's own `"brand new kw"`.
   That file feeds the Inbox trend arrows and its mtime is in `_data_stamp()`, so running the
   tests also invalidated the production inbox cache. The snapshot now lands beside the master it
   snapshots; the file was reset to its header (backup in the session scratchpad).
4. **`python main.py` had been broken since `c65c1b5`** — that commit deleted `src/scoring.py`
   as a dead duplicate but not this last caller, and the `ImportError` handler blamed a missing
   pytrends. Dead `research()`/`load_keywords()` removed, and the orphaned `db.save_snapshot()`
   with them.
5. **`agent.db` 10.9 MB → 3.4 MB.** `vacuum()` existed with no caller, so 1,761 of 2,666 pages
   were reclaimable dead space. `prune_cache()` now reclaims after a delete. Integrity ok, zero
   rows lost.
6. **Empty MCP answers were cached for a whole day.** The cache key is `(request, DAY)`, so one
   hiccup at 09:00 blanked Trending/Gems until midnight and read as "no data". **65 of 535**
   cached rows were empty payloads. Real answers still cache; `_bad()`'s deliberate `{}` cache
   for a *validation* error is untouched.
7. **`seller_count` never reached the lane.** Read for the evidence line and thrown away, so
   `longtail._room()`'s "3+ listings per seller" penalty read `row["sellers"]`, which no row
   carried. It now fires on 21 rows.
8. **The live-API guard probed the wrong transport.** YTrends is reachable two independent ways:
   the legacy REST API (`YTRENDS_COOKIE`) and the MCP (`YTRENDS_API_TOKEN`). Measured on the PC:
   `ytrends_client.probe()` → **False** while `ytrends_mcp.available()` → **"OK (14 tools)"**.
   Gating an MCP-backed command on the REST probe refuses to run a command that works. Every
   pre-existing `LIVE_API_CMDS` member really does import `ytrends_client`, so they keep the REST
   probe; only MCP-backed commands use the new `_MCP_CMDS`.
9. `src/version.py` maintained (`37.0` → `37.13`) and `README.md` brought in line.

### A claim from this session that was WRONG — do not re-add

An earlier note reported a **thread leak** in `save_candidates`. It is not one: CPython frees the
`ThreadPoolExecutor` by refcount when the function returns, and the worker exits. Probed on both
trees with 5 saves under fast and slow enrich — **both settle to 0 extra threads.** What had been
seen was one transient in-flight worker. The change was reverted and its test deleted.

---

## 3 · Three things built (owner signed off after a measured proposal)

### 3.1 · `py main.py enrich [N] [pod|embroidery]` — new `src/enrich.py`

Backfills the market data that leaves a row unscored. Harvest's two biggest sources add a name
(`mcp:search`, 698 rows) or a listing count (`mcp:ranking`, 482 rows) and no demand fields.

* Fills **blanks only** — a value the master already measured is never overwritten.
* Writes **no zeros**; honest-nulls throughout.
* Backup to `keyword_data.bak.csv`, temp-file + atomic replace, flush every 25 keywords.
* **Resumable by construction**: the work list is "rows the engine could not score", so a re-run
  skips whatever the last run fixed. No cursor file to corrupt. *(Verified the hard way — the run
  was killed mid-flight and the master came back 1,523 rows / 14 cols / 0 overwrites.)*
* Repairs the master's schema drift — the file is now the canonical 14 columns
  (`opportunity_score` was missing).
* **Runs on the PC.** The VPS IP is blocked from YTrends (same reason `harvest` is);
  `harvest.merge_master()` carries the result to the server.
* Measured cost: **~9–15 s per keyword.** That is why this is a CLI and not a web button — the
  old 12-per-click button was ~2 minutes of blocking request.

### 3.2 · Sellability overlay on every Inbox action

The Inbox labelled 112 rows `CONFIRM_FIRST` identically and sorted them by market score ("how big
is this market?"). `/longtail` already computed the other half ("is this phrase actually
selling?") on a page reachable only as a tool chip. The score now rides **in the action cell** —
following the supplier badge's rule, *same question, no 11th column*:

```
| 1 | mini bride tote bags | — | POD product · 🏭 check supplier | 🚀 Build Now · 💰 87.0 PUSH | 🟢 GO (81.2) | ...
```

Display only. `test_sellability_overlay_changes_no_verdict_action_or_score` pins that turning it
on moves no verdict, action, score or position — the same guarantee the supplier badge carries.

### 3.3 · Keyword trend history from `discovered_keywords`

`discovered_keywords` in `agent.db` had been append-only since 2026-07-05 with **no reader
anywhere** — 11,680 rows, 1,029 tags, momentum on 9,795. Meanwhile `_trend_map()` read only
`data/history/keyword_snapshots.csv`, which an MCP-harvesting shop never writes, so the trend
column was permanently blank. **464 Inbox rows now carry a trend where 0 did.**

The window is the decisive detail. Measured on the real history:

| comparison | result |
|---|---|
| last two days (what it used to do) | 30 rising · **0 fading** · 513 stable · median Δ **0.00** |
| oldest vs newest | **31 rising · 38 fading** · 474 stable |

YTrends momentum barely moves day to day and the same value is re-recorded many times daily, so a
last-two read calls ~95% of keywords "stable". Full scan is 15 ms — no index needed.
`data/agent.db` was added to `opportunity_inbox._data_stamp()`; without it new history would never
bust the cache (the same miss already fixed twice, for `winner.json` and the proof ledger).

> The four-handoff warning still stands and is **not** what this does: never plumb
> `discovered_keywords.opportunity` into the O leg. This reads the `momentum` column as a time
> series only.

---

## 4 · The "unfixable" test was a stale assertion, not a live-MCP problem

`test_full_selftest_pipeline` → *"Trending/Opportunities/Gems paginate past the ~10-row server
cap"* was carried by two handoffs as **"needs live MCP, predates everything, do not fix
offline."** All three claims were wrong.

It is a **static source-text check**. Four of its five clauses passed. The fifth asserted the
literal `mcp.trending_keywords(limit=PULL)` in `interactive.py` — a string that commit `833e280`
("Winner Finder + Build Queue read keyword store") removed when it routed all three capped
surfaces through the `_pull()` helper so they can serve either the live MCP or the local keyword
store. The deep pull was kept; only the call-site spelling moved. The assertion was never updated,
so the check has been red since `833e280` and never touched the network.

Now pinned to the mechanism instead of one spelling: every capped surface is fetched through the
deep-pull helper at `PULL` depth. **Verified it has teeth** — injecting a regression
(`hidden_gems` dropped back to `limit=10`) makes it fail; restoring makes it pass.

---

## 5 · What the data did (measured, same probe before and after)

`before` = this session's start. Enrichment ran over **435 of the 843** unscored keywords
(300-row batch + 135 of a second run, stopped deliberately — see §6.1).

| metric | before | now | Δ |
|---|---|---|---|
| Rows the engine can score | 680 | **1,107** | +427 |
| Unscored backlog | 843 | **416** | −427 |
| L2 `GO` verdicts | 3 | **9** | +6 |
| Rows with per-listing sales evidence | 140 | **265** | +125 |
| …rated PUSH | 11 | **34** | +23 |
| Rows showing a trend | **0** | **464** | +464 |
| **BUILD_NOW** | **0** | **1** | +1 |
| CONFIRM_FIRST | 112 | **215** | +103 |
| WATCH | 1,266 | **1,074** | −192 |
| SKIP | 113 | **201** | +88 |

The SKIP growth matters as much as the promotions: those are rows correctly demoted out of a WATCH
pile nobody could triage.

**Scoring math is untouched.** A before/after probe over the whole master with only the *code*
changed returned every lane count identical. All movement above comes from data.

Data integrity after the backfill: 1,523 rows, 1,523 unique keywords, **0 values overwritten,
0 anomalies** (no zeros written, no negatives, no conversion above 100%).

---

## 6 · Known broken / next up

1. **Finish the backfill: `py main.py enrich`** on the PC. **416 rows remain**, ~15 s each ≈ 1.7 h.
   Resumable — just run it; it re-derives its own work list. Then sync to the VPS.
2. **Long-tail supply is now provably the binding constraint.** With real data in, **9 rows reach
   GO** (was 3) and **8 of the 9 are held below BUILD_NOW purely by the word-count rule** — they
   are 2–3 words. The market signal is finding good niches; turning them into 4+ word buyer-intent
   phrases is the bottleneck, which is exactly what phase 3 → 4 (Pattern Miner → Keyword Lab →
   Send to Re-rank) exists to do. **That loop is now the highest-leverage step in the workflow.**
3. **`/longtail` MIN_WORDS=3 vs the engine's 4.** Deliberately NOT changed. Raising it collapses
   the lane from 140 scored / 13 PUSH to 8 / 2, and every one of the lane's top rows is
   CONFIRM_FIRST or WATCH in the engine — the lane never contradicts it, it ranks *within* the
   bucket the engine already flagged. They answer different questions.
4. **`discovered_keywords` still grows unbounded** (11,680 rows, 1,029 distinct tags, heavy
   duplication — 72 copies of `bridesmaid bag`). It now has one reader (§3.3) but no pruning.
   Deleting rows deletes history; the owner's call.
5. **`data/db/etsy.db` (the Local Capture Index, `src/data_store.py`, 647 lines) does not exist
   locally.** It fills only from extension SERP captures, of which there have been none, so Pattern
   Miner's DB lookup, Winner Finder "My data" and Build Queue's mined rows all return empty.
   Dormant, not broken — but a whole subsystem is unexercised.
6. **`/team/ops` still has no phase strip** (11 of 12 step routes carry it). Left alone
   deliberately — a full-page sub-app needing a 9th parameter through `team_ui.register()`.
7. **`WORKFLOW.md` still says it is generated from `workflow_spine.py`, and is not.** Hand-written
   and already drifted; the pin-test only checks names and routes.
8. **Nobody has clicked any of this in a browser.** Every claim here is from rendered HTML behind a
   Flask test client or a direct module call.
9. **VPS data gap unchanged:** the team runs the expensive HeyEtsy Detail export and skips the
   cheap Reviews export. Reviews produce the recipient/occasion language behind the candidates.
10. **Supplier library still `partial`** — 25 rows, 1 of 8 registered suppliers, 0 confirmed. Two
    columns (`product_url`, `processing_days`) added to `data/suppliers/Embroidery.csv` and
    re-uploaded at `/suppliers` flip embroidery coverage to `complete` and switch enforcement on.
    `supplier_products.csv` is gitignored, so `git pull` does not carry it — re-upload on the VPS.

---

## 7 · Traps — do not repeat

Carried forward, still true: **a 200 proves nothing** · `class="stgnav"` is not a reliable
phase-strip marker, grep the label text · do not cache `/trending`/`/opportunities`/`/gems` ·
`"learn"` is ambiguous · never plumb `discovered_keywords.opportunity` into the O leg · `_h_esc`
escapes `&` → `&amp;` · never say "deploy unconfirmed" from a doc — probe · a probe can be
non-discriminating · a score floor is worse than a wrong score — check the **distribution** ·
"unknown" and "no match" are different answers · derived data can silently drop source data.

New this session:

1. **A zero from an API usually means "I don't know", not "the answer is zero".** The MCP returns
   `total_listings: 0` for keywords it has never indexed. Any code treating a count of 0 as a
   measurement hands the scorer its most attractive possible input.
2. **Check which transport a probe actually tests.** Two YTrends paths fail independently; the REST
   cookie was dead while the MCP was healthy.
3. **A "one-click" queue can be scoped to a population that does not exist.** The enrich button was
   correct code over an empty set for months, and read as "nothing needs enriching".
4. **A function honouring a `path=` argument can still write to a hardcoded sibling path.** Check
   the whole function, not the argument.
5. **Verify a leak before fixing it.** The thread-leak claim (§2) was wrong and cost a real change;
   refcount semantics already reclaimed the pool.
6. **The selftest pins `README.md` to `src/version.py`.** Bump both or it fails.
7. **"Do not fix offline" in a handoff is a hypothesis, not a fact.** The pagination check needed
   no network at all (§4) and stayed red for weeks because nobody re-read the assertion. When a
   test is documented as unfixable, read what it actually asserts before carrying the note forward.

---

## 8 · Data + guardrails

- `keyword_data.csv` — **1,523 rows, 14 columns** (canonical schema restored). Backup:
  `keyword_data.bak.csv` (pre-backfill state of the last run).
- `data/agent.db` — 3.4 MB after vacuum. The `keyword_snapshots` table is empty and now has no
  writer; left on disk rather than dropped.
- `PUBLISH_AUTOMATION = False` · no Seller-Central connection · honest-nulls ·
  **`ranking_engine.py` and `opportunity_score.py` frozen and untouched.**
- All 121 `src/`, `tests/` and `main.py` files verified to parse under **Python 3.10**
  (`ast.parse(feature_version=(3,10))`) — the VPS runs 3.10.12, no PEP 701 f-strings.
- New public API: `src/enrich.py` (`run`, `unscored`, `FIELD_MAP`) ·
  `opportunity_inbox._needs_enrichment` · `opportunity_inbox.TREND_DELTA` ·
  `opportunity_inbox._history_from_db` / `_history_from_csv` · `main._MCP_CMDS`.
- **23 new tests** this session; `tests/test_enrich.py` is new. 598 total, all green.

Changed: `README.md` · `WORKFLOW.md` · `main.py` · `src/db.py` · `src/interactive.py` ·
`src/keyword_lab.py` · `src/opportunity_inbox.py` · `src/selftest.py` ·
`src/shortlister_integration.py` · `src/version.py` · `src/web.py` · `src/workflow_spine.py` ·
`src/ytrends_mcp.py` · `src/ytx_import.py` · 5 test modules.
New: `src/enrich.py` · `tests/test_enrich.py`.

---

## 9 · How the owner wants this work run

Unchanged and honoured: **review first, propose a ranked plan, get sign-off, then fix in that
order.** No broad refactors, no unrelated modules. *"Do not blind fix — check the code, check the
process."* — and **read the data too.** Every finding here came from measuring the real master,
the real database, or a rendered page.

**Show measurements, not assertions** — and when a claim turns out to be wrong (the thread leak,
§2), say so plainly and revert it.
