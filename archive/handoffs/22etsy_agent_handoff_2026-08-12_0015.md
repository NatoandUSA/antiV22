# 22etsy-agent — Handoff · 2026-08-12 00:15 (+07)

_Session owner: Alex (Hue, Vietnam). **Supersedes `22etsy_agent_handoff_2026-08-11_1617.md`**,
which supersedes 2026-08-11 01:00 → 2026-08-10 11:00 → 2026-08-08 00:15 → 2026-08-07 15:48 →
2026-08-06 02:49 → 01:45 → 2026-08-05 22:47 → 14:26 → 2026-08-04 00:16 → V37.11. Read this file
first; where they disagree, the newest wins._

Repo `D:\Claude\22etsy-agent` · GitHub `NatoandUSA/etsy-agent` · VPS `~/etsy-agent`, service `etsy-web`.
Live: https://etsy.theglobalserviceteam.site

---

## 0 · Status — 5 commits shipped this session, deployed and verified live

| | |
|---|---|
| **Commits** | `24a7eb6` → `c969756` → `6d284a0` → `512632b` → `63d45b0` — local == origin/main == VPS, verified by direct comparison, not assumed |
| **Service** | active, restart timestamp (00:10:41) confirmed AFTER the deployed commit landed |
| **Tests** | local full suite green (exit 0) + VPS full suite green (exit 0), every commit, no shortcuts |
| **Live acceptance** | homepage rename/freshness strip verified via a real Flask test-client hit on `/`, not just unit tests; enrichment fix verified with a real (unmocked) 3-keyword drain against production MCP; first real rank snapshot run on production (`changed: 0` both modes, as designed) |
| `PUBLISH_AUTOMATION` | untouched |
| **Frozen files** (`ranking_engine`, `opportunity_score`, `product_fit`, `etsy_proof`, `opportunity_inbox`) | zero edits to scoring/weight logic — `opportunity_inbox.build_inbox()` is read from (same as every other consumer module), never modified |
| **Working tree** | clean |

**Standing rules carried forward, unchanged:** Claude has the owner's full authorization to
commit, push, and deploy without asking first (2026-08-10). Verification (tests, live probe) is
still mandatory every time. See `[[deploy-runs-from-user-side]]`.

---

## 1 · How this session ran — the golden rule found real bugs, not just documented claims

Three pasted JSON docs this session (freshness diagnosis → freshness recovery sprint plan →
post-Patch-1 best route). Each verified against real code/data before acting — see
`[[json-handoff-review-golden-rule]]`. Unlike most prior sessions, this one wasn't just about
catching a wrong claim in a doc — tracing the docs' own claims led to finding and fixing **three
real, previously-unknown production bugs**, none of which either JSON doc had diagnosed:

1. **The "Enrich leads" button had never worked, ever.** Traced the 631-keyword enrichment
   backlog instead of accepting the sprint doc's "needs a bounded drain loop" framing at face
   value. Found: `/enrich-leads` called `keyword_lab.save_candidates()`, whose dedup guard skips
   any keyword already in `keyword_data.csv` — but every needs-enrichment keyword is *already
   there* (that's why it needs enrichment). Reproduced directly: enrich mocked to always
   succeed, `save_candidates` still left the file byte-for-byte unchanged. `src/enrich.py`
   already had the correct fix (update-in-place logic) but was CLI-only and undiscoverable from
   the web flow.
2. **A stale "VPS is IP-blocked from YTrends" assumption, repeated in three files.** Tested live
   instead of trusting the docstrings: a direct MCP call from the VPS itself succeeded in 17.3s
   with real data. The claim was almost certainly about the old REST/cookie transport, not the
   MCP token transport this code actually uses. Corrected the docstrings in `enrich.py`,
   `harvest.py`, `workflow_spine.py`, and one test file — did **not** move harvest itself from
   PC to VPS (separate decision, explicitly deferred per the owner's freeze rule).
3. **The 6-second per-keyword enrichment timeout was shorter than a real call takes** (~11–17s
   measured live) — so even a *correctly wired* enrich would have timed out almost every
   attempt. `enrich.py` had no timeout at all (the same 2-minute-hang risk already patched
   elsewhere). Added a real 25s timeout + circuit breaker.
4. **A measurement bug found live, during the capacity burn-in itself.** A 15-minute bounded
   drain reported "attempted: 200, failed: 124" — a ~62% failure rate that didn't match the
   ledger's own `enriched: 76, timed_out: 1`. Traced it: `enrich.run()`'s `targeted` field is the
   *requested slice size*, not how many keywords the loop actually reached before the time bound
   cut it short; the wrapper was computing `failed = targeted - enriched`, silently counting
   everything never even attempted as a failure. Fixed with a real `attempted` counter; a second
   burn-in run confirmed the fix (14/14 succeeded, 0 failed).
5. **Resolved, not just noted, two "discrepancies" that turned out to be my own wrong lookups.**
   The first freshness review initially found `data/imports/etsy_proof/latest.json` had only 2
   rows against a doc's claimed "819 listings" — kept digging instead of reporting a false
   mismatch, and found the real source: `/status`'s "819 listings" is `sources.proof_listings`
   (the cumulative Alura+captures proof map), a different field than the single latest-import
   file. Confirmed exact match once read correctly.

---

## 2 · What shipped

**Homepage truthfulness** (`24a7eb6`, `63d45b0`): "Today's Opportunities" (implied
newly-discovered) → "Top current proven markets" (what it actually is — the live top ranking).
Added a real "N new today" count from `freshness.py`'s existing `first_seen` tracking, an honest
freshness strip (last harvest / enrichment / proof / rank-snapshot / report-generated ages), and
a PROMOTED lane that renders nothing until a genuine rank-snapshot delta exists.

**Timezone fix** (`c969756`): `discovered_keywords.captured_at` was stamped via SQLite's
`CURRENT_TIMESTAMP` (UTC). The daily harvest cron fires at 06:00 ICT — inside the window that
maps to the *previous* UTC calendar day — so every day's freshly-harvested keyword was silently
aged one full day in `freshness.py`, which compares this column's date part directly against
`date.today()` (local). It could never show as NEW/today on the day it was actually discovered.
`save_discovered()` now stamps local time explicitly. Old rows keep their historical (wrong)
stamps — nothing safe to rewrite retroactively.

**Enrichment actually works now** (`6d284a0`, `512632b`): `src/enrich.py` gained a real
per-keyword timeout + circuit breaker + optional `max_runtime_s` bound. New
`src/enrichment_runner.py` wraps it with a persisted run ledger
(`data/enrichment_runs.jsonl`) so the web button, the CLI (`main.py enrich --minutes N`), and the
daily cron (`vps-build.sh` now runs a bounded 15-minute drain after harvest) all go through one
code path. Pipeline Health (`/status`) shows the last run's queued→attempted→enriched→failed→
remaining. **Capacity burn-in confirmed healthy**: two production runs, 76+14 enriched, 0-1
timeouts, 0 rate-limit trips, throughput matching the sprint doc's own modeled 52-81/15min
estimate.

**Rank snapshots** (`63d45b0`): new `src/rank_snapshot.py`. `snapshot()` diffs the current rank
against `data/rank_state.json` (atomic write: temp file + replace) and appends real action-change
events to `data/rank_events.jsonl` — never on first sight of a keyword (no false "promoted from
nothing"), never on an unchanged action. Called from exactly two places — `harvest.run_harvest()`
(non-dry only) and `enrichment_runner.drain_enrichment()` — deliberately **not** from
`build_inbox()`/page rendering, which runs on every view and would misfire on unrelated writes
(browsing `/trending` alone touches `agent.db`'s mtime via `discover.save_discovered()` without
anything being re-ranked). First real production snapshot already run: `changed: 0` both modes,
as designed for a first-ever baseline.

---

## 3 · Sprint state — freshness recovery (ChatGPT's 5-patch plan)

Owner confirmed staged priority via `AskUserQuestion`: safe/well-specified patches first, the two
patches with real judgment-call/cost implications deferred pending a quick decision.

| Patch | Status |
|---|---|
| Homepage rename + honest "new today" | **Shipped** (`24a7eb6`) |
| 1 — Enrichment drain + observability | **Shipped** (`6d284a0`, `512632b`) — turned out to require fixing a real no-op bug, not just adding batching |
| 3 — Rank snapshots + homepage truthfulness | **Shipped** (`63d45b0`) |
| 2 — Seed frontier / discovery expansion | **Not started.** Flagged: harvest already has unseeded rankings/opportunities/trending pulls providing daily variety — "recycles the same territory" framing in the doc is only true for the *seeded* half of `harvest._pull()`. Also touches daily MCP call volume (global CLAUDE.md rule: flag API-cost-affecting changes before building). |
| 4 — Execution-actionability overlay (MINE_NICHE reclassification) | **Not started.** Hardcodes word lists ("funny/vintage/cute/trendy/embroidered" = broad → downgrade Build Now) that directly change the operator's CTA on ~1900 keywords — a business judgment call, not mechanical porting. The post-Patch-1 doc's own recommendation is read-only calibration first (audit top 100-200 Build/Confirm rows, propose reason codes, review with owner) before any behavior change — not yet started. |

**Separate finding, explicitly not acted on:** if the VPS genuinely isn't IP-blocked from YTrends
anymore (§1.2), the same may be true for `harvest.py`'s daily pull, which currently still assumes
it must run from the PC. That's a bigger, separate architectural question (would change where/how
daily harvest runs, with real cost/schedule implications) — flagged for the owner's decision, not
touched. The sprint's own freeze rules explicitly say not to move harvest PC→VPS in the same
patch as freshness recovery.

---

## 4 · Traps hit this session (new)

1. **A sprint doc's root-cause framing can be plausible and still wrong at the mechanism level.**
   "Needs a bounded drain loop with observability" (Patch 1's stated design) implicitly assumed
   the underlying single-batch enrich already worked and just needed scaling. It didn't work at
   all — looping a no-op 631 times would have produced a very convincing-looking dashboard over
   a button that still did nothing. Only caught by reproducing the actual write behavior with a
   mocked-always-succeeding enrich call, not by reading the code more carefully.
2. **A bug can hide inside your own verification run.** The capacity burn-in itself (step
   explicitly requested by the doc, run in good faith to check "is Patch 1 healthy") produced a
   misleading "62% failure rate" that was actually a counting artifact in code shipped minutes
   earlier. Cross-checking the suspicious number against the OTHER numbers in the same ledger
   entry (`enriched: 76` didn't square with `failed: 124` on a bounded/interrupted run) is what
   caught it — a single metric taken in isolation would have read as a real problem.
3. **"Verified live" needs the exact right call, not an adjacent one.** The VPS-blocked
   docstring turned out to describe the legacy REST/cookie transport, not the MCP token
   transport `_enrich_row` actually uses (confirmed by `test_enrich.py`'s own
   `test_the_live_guard_probes_the_transport_the_command_actually_uses`, which had already
   documented this exact split). Testing "the VPS can reach YTrends" in the abstract would have
   been the wrong question; testing the specific function the fix depends on was the right one.
4. **Reusing existing, working code beats reimplementing it — even when your first draft looks
   fine.** Built a duplicate `keyword_lab.enrich_existing()` before discovering `src/enrich.py`
   already did the same job more robustly (atomic write + backup, resumable, honest-nulls).
   Deleted the duplicate and extended the existing module instead once found — a broader search
   before designing would have caught this without the throwaway work.
5. **A background SSH command's own completion notification isn't the remote job's completion.**
   `nohup ... &` over SSH returns almost immediately once detached; the harness notification for
   *that* SSH call says nothing about whether the real 15-minute remote job is done. Had to poll
   the remote process explicitly (a blocking loop-and-check SSH call) rather than trust the first
   notification.

---

## 5 · How the owner wants this work run (unchanged, carried forward)

**Do not blind fix — check the code, check the process, verify claims against the actual
codebase and live data before building anything on top of them, including claims from a pasted
"handoff" doc, even one framed as evidence, even when it's ChatGPT reviewing Claude's own prior
output.** Show measurements, not assertions. Prefer the smallest safe change over a broad one.

**For large/speculative/business-judgment work specifically:** state assumptions and tradeoffs,
then ask — don't silently build all of it just because broad deploy authorization exists.
Confirmed working this session: `AskUserQuestion` to sequence Patch 1/3 (safe) ahead of Patch 2/4
(cost + judgment implications) was the right call, not a stall.

**Commit/push/deploy no longer needs pre-approval — verification still does. Every commit this
session:** local full suite green, VPS full suite green, service restarted, restart timestamp
checked against the deploy, live probe (302/404 pattern at minimum; real functional checks where
practical — a real Flask test-client hit, a real unmocked enrichment call — beat a plain HTTP
probe alone).

**English-only output · never auto-publish a listing · `PUBLISH_AUTOMATION` stays False · no
Etsy/Printify API automation that takes account actions (read-only catalog lookups are fine) ·
frozen L0–L4 files are frozen (scoring/weights, not read access — every rank-adjacent module
already reads `opportunity_inbox.build_inbox()`) · ranking logic untouched unless explicitly
asked.**

---

## 6 · Open items for next session

1. **Decide Patch 2 (seed frontier) scope and API-cost tolerance**, or confirm it stays deferred.
   Needs: real overlap measurement (how much of harvest's unseeded rankings/trending pulls
   already provides variety) before designing new seed-rotation machinery.
2. **Decide how to approach Patch 4's calibration.** Owner input needed on the word lists before
   any code changes — a read-only audit command (inspect top 100-200 Build/Confirm rows, propose
   execution_action + reason codes, no behavior change) is the doc's own recommended first step
   and has not been built yet.
3. **Decide whether to investigate moving harvest from PC to VPS**, now that the IP-block
   assumption is disproven for the MCP transport specifically (§1.2, §3). Not urgent — current
   PC/VPS split still works — but worth a deliberate decision rather than leaving stale
   architecture in place indefinitely.
4. **Watch the enrichment ledger** (`data/enrichment_runs.jsonl`) over the next few days now that
   the daily cron actually drains backlog — confirm `remaining_after` trends down day over day
   and the 15-minute bound is enough to keep pace with `mens carry on bag`-scale daily net-new
   volume (~52-77/day observed this session).
5. **`mens carry on bag` Duffel #372** — still waiting on the owner's Printify dashboard session
   (dimensions/cost/processing-time) and real sample photos, per the prior handoff. Untouched
   this session; not a sprint blocker, deliberately parked.
6. **Prior open items, still open, not touched this session:** the Printify matcher's `≤3`-char
   word-exclusion bug; `PRODUCT_FAMILIES` vocabulary for HPW/HogoToPod; `product_manager.PACKAGES`
   (confirmed disconnected from the live sprint flow, no action needed unless the owner wants
   that separate feature worked on).
