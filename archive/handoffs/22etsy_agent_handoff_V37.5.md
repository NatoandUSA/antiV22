# 22etsy-agent — Handoff (V37.5)

_Session of 2026-08-01/02. Owner: Alex (Hue, Vietnam). Follows `22etsy_agent_handoff_V37.4.md`._
_The frozen L0–L4 ranking math (product_fit, trademark, opportunity_score, ranking_engine.decide) was
NOT touched. Two features were added and six data bugs fixed — all upstream of, or beside, the freeze._

Repo: `D:\Claude\22etsy-agent` (Windows) · GitHub `github.com/NatoandUSA/etsy-agent` · VPS `~/etsy-agent`,
service `etsy-web`. Live: https://etsy.theglobalserviceteam.site

---

## 0 · Status at a glance

**All four commits are on GitHub `main`. Nothing is pending commit.**

| Commit | What |
|---|---|
| `8f380cf` | Daily Reports UX — clickable Drive/Listing links, coloured statuses, Approve/Improve/Reject |
| `65d8959` | Long-tail lane + 5 data bugs that made long-tails unrankable |
| `43ab88d` | docs: V37.4 handoff, deploy notes, cleanup audit, v38 backtest (were untracked) |
| `9ef457d` | Stop the PC↔VPS data sync deleting the other machine's keywords |

No new Python deps, no DB migration (one additive nullable column), no Chrome-extension change.

**Runtime state:** local `keyword_data.csv` was re-harvested 2026-08-02 19:49 with the fixes applied
(1523 rows, new `total_revenue` column). **DEPLOYED AND VERIFIED 2026-08-02** — see §6. Do not tell the
owner the deploy is unconfirmed.

---

## 1 · The problem this session solved

Owner's report: *"Build now is full of head terms (funny tee, funny shirt). I need long-tail keywords to
push — low signal but higher chance to sell."* Plus: *"it has been a few days but this is not updating
anything."*

Diagnosis (measured, not assumed):
- The **word-count rule already favours long-tails** — `ranking_engine` forces ≤2-word terms down to
  Pattern Miner. It was never the blocker. Head terms reach Build only via the **Etsy-proof override**
  (`ranking_engine.py:94-98`), which bypasses the word rule; big terms are exactly the ones with sales proof.
- ~~**GO needs overall ≥ 80** (`opportunity_score.py:347`). The highest-scoring long-tail in the whole base
  was **73.6**. No long-tail could ever be promoted on merit.~~
  **⚠️ CORRECTED IN V37.6 — this reading was wrong.** The 73.6 ceiling was real but it was not a long-tail
  problem: it held the *entire base* down, head terms included, and it was caused by a data-unit bug this
  very session introduced (see the V37.6 block at the end of §2). Re-measured on the live master,
  long-tails score marginally **higher** than head terms among demand-grounded rows (max 76.2 vs 74.3,
  median 53.7 vs 48.8). There is no word-count bias in the engine to correct.
- Only **54 of 1123** keywords were ≥4 words (4.8%); 50% were ≤2 words.
- Real long-tails were sitting at WATCH with genuine sales, e.g. `funny shirt for dad` — $80.5K niche
  revenue, 3.0% conversion, 175 listings → WATCH.

The root causes were all **data**, upstream of the frozen engine.

---

## 2 · Six bugs found and fixed (all in the harvest / sync path)

| # | Bug | Evidence | Fix |
|---|---|---|---|
| 1 | **Revenue units mixed.** `scout_opportunities` returns `total_revenue_usd` (niche total), `find_trending_keywords` returns `avg_revenue` (per listing). Both were written into `avg_revenue`, which feeds the log-scaled demand leg. | Median by source: opportunity **$86,822** vs trending **$336** — 258×. Same market, ~60 demand points apart on provenance alone. | `_add()` keeps `revenue` (always per listing) and `revenue_total` separate; new `total_revenue` column. |
| 2 | **`momentum` was not momentum** — it was whatever score the source returned, and fed 35% of the market leg. | opportunity 66–91 · ranking 38–75 · trending 21–52 · **search: hardcoded 40.0 on all 657 rows** (1 distinct value). Live API says real momentum is often `null`. | Only a measured momentum is written; otherwise blank. |
| 3 | **Absent metrics written as `0`** — "never measured" and "measured zero" became identical, so the scorer read conversion `0.0` as a real datapoint and scored rows with nothing behind them. | The `5 listings · $0 rev · 0.0% conv` rows. | `_opt()` writes blank; honest-nulls survive from pull to scorer. |
| 4 | **harvest deleted the keyword base.** `harvest()` passed `write_keyword_data()` only the fresh MCP pull, and it opens the file with `"w"`. Every keyword the pull didn't return was erased. | This wiped every Keyword Lab long-tail, lane lead and extension import on **each run** — why generated long-tails never accumulated (Keyword Lab 30 of 1131). | `merge_existing()` carries them over; a rediscovered keyword keeps its original source, takes fresh metrics. |
| 5 | **`browse_rankings` rows carry `listing_count` only** — 237 rows, half the existing long-tails, with no demand data at all. | — | Documented at the call site; `longtail.pull()` is the supply fix. |
| 6 | **PC↔VPS sync deleted the other side's keywords.** `push-to-vps.ps1` scp'd the PC's master straight over the server's, so anything the team added *on* the VPS (Keyword Lab, long-tail pulls, extension drops) was destroyed on every data sync. | Same class as #4, across the machine boundary. | `merge_master()` unions both; the script pulls the server copy down, merges, pushes the union. |

**Backtest before adopting** (on the real 1123-row master): **38 verdict flips (3.4%), all
CONDITIONAL → WATCH** — rows that were riding on inflated revenue or fabricated momentum. Nothing falsely
promoted; SKIP count unchanged.

**Verified after the real harvest ran:** 1123 keywords before → **all 1123 survived** + 400 new = 1523.
Zero lost. Conversion literal-zeros: 0. Momentum blank on 558/698 search and 251/482 ranking rows.

---

### ⚠️ V37.6 — bug #1's fix had a silent regression, plus two older bugs of the same family

Bug #1 correctly made `avg_revenue` mean *per listing* everywhere. But **nothing converted it back**, and
`opportunity_score._demand_from`'s curve is calibrated for the **niche total** ($100 → demand 0,
$316k → 100). So every row entered the demand leg on the wrong scale.

| # | Bug | Evidence | Fix |
|---|---|---|---|
| 7 | **Demand leg fed per-listing revenue on a niche-total curve.** The V37.5 unit fix made all sources *consistent* — consistently ~57 demand points too low. | Median per-listing **$627 → demand 22.8** vs median niche total **$64,142 → demand 80.2**. Whole base pushed under the GO band. | `_to_scorer` passes `niche_revenue` (harvested `total_revenue`, else per-listing × listings); `_demand_from` reads it first. |
| 8 | **A fabricated seasonality constant capped every score.** `_feasibility` inserted `60.0` for a signal that has no source (`seasonal.py` is a holiday *calendar*, not a per-tag score), costing every row 14 points and hard-capping F at **79.25** — so every composite was dragged toward 79. | Same anti-pattern as the flat-50 private boost (V33) and the constant-85 opportunity signal (V30.1), both already removed. | Renormalise the 80 movable points onto the measured signal. Widens spread both ways: launchable 79.2 → 88.0, unmakeable 56.8 → 48.0. |
| 9 | **Missing legs RAISED the score.** Renormalising over present components is right, but dropping a low leg lifts the average — so **561 rows with no market data at all** scored 76–87 on competition-from-listing-count plus the deterministic feasibility read, and sorted at the **top** of the inbox above every measured row. | Ungrounded median 68.6 vs grounded 48.8 — measuring a keyword *cost* it ~20 points. | `overall_score` is now `None` when core (M or C) is missing, and a new `evidence_weight` reports how much was actually measured. Consumers already guard with `score or 0`, so nulls sort last. |

**Backtest on the live 1523-row master:** **156 flips (10.2%)** — SKIP→WATCH 101, WATCH→CONDITIONAL 52,
CONDITIONAL→**GO 3**. Nothing was downgraded except genuinely weak rows (SKIP 225 → 124).

**Before: 0 of 1523 keywords could reach GO.** Measured rows topped out at 76.2 (below the ≥80 threshold);
unmeasured rows scored up to 87.2 but were force-capped at WATCH by the demand-grounded gate. A perfect
deadlock: *measure a keyword and it can't score 80; don't measure it and it's capped regardless.*
**After: GO is reachable** — 3 GO, 83 CONDITIONAL, and the top of the inbox is measured rows
(`patriotic soft tee` 81.0) instead of dataless ones (`wood look sign` 87.2).

Still **0 BUILD_NOW**, and that part is *correct*: all 3 GO rows are 3-word, and L4's long-tail rule
(`ranking_engine.py:176-186`) deliberately routes anything under 4 words to Pattern Miner first. Reaching
BUILD_NOW needs 4+ word keywords with real data — only 82 of 1523 rows are 4+ words, which is the
long-tail **supply** problem, not a scoring one.

**Not a ranking-math issue:** `DESIGN_PREP_READY` / `PUBLISH_READY` being false is a separate listing-QA
gate (`product_manager.py:588` — `not fails and exactly_13_tags`), unrelated to GO.

### V37.6b — the O leg now has a real source (and one that was nearly a trap)

`opportunity_signal` was null on all 1523 rows. It now fills from
`scout_opportunities`' own **`opportunity_score`** — a vendor estimate that arrives alongside, and is
distinct from, `momentum_score` and `competition_score` (e.g. `icecreamnlove`: opportunity 92.6,
momentum 47.4, competition 39.2). harvest already received it and threw it away into the internal dedup
`score`; it is now captured as a metric and written to a new `opportunity_score` column.

**Rejected source — read this before "improving" it.** `discovered_keywords.opportunity` in `agent.db`
looks ideal (11,680 rows, 449 distinct, p10 0.1 → p90 97.5) and is **the wrong column**. It is
`discover.score()` = `log10(revenue+1) × conv × (1+momentum/100) × 100 / listings` — every input is
already a leg in the composite (revenue→demand, conv→conversion, momentum→velocity, listings→competition).
Feeding it to O would double-count all four and, being a product, amplify them: V30.1's failure in a worse
form. Only an explicit vendor column may populate O. Pinned by
`test_o_leg_is_never_fed_a_derived_score`.

**Guards:** the vendor score is passed only from the two `scout_opportunities` call sites — never from
trending (whose `score` is momentum), rankings (a rank score) or search (a flat 40). Pinned by
`test_vendor_opportunity_score_survives_the_csv_round_trip`.

**Measured impact** (56 master keywords have a cached vendor score): mean **+3.4** points, max +5.1,
**11 rows WATCH → CONDITIONAL**, no GO change, nothing downgraded.

**Known bias, accepted:** `scout_opportunities` only returns tags it already considers opportunities, so
the score is never low where present (observed range 58.1–92.6). O is therefore a one-directional bonus
that fires only on scout-sourced rows. At +3.4 mean that is small, and the values genuinely discriminate
(69 distinct across 91 tags) — but if scout coverage grows a lot, so does the provenance skew. The new
`evidence_weight` field makes it visible.

**Not retroactive:** the column is only written by a harvest run, so O stays null until the next
`py main.py harvest` (step 1/4 of `push-to-vps.ps1`). Older CSVs load fine — readers use `DictReader`.

**Left on the table (measured, not built):** `competition_level` is returned by both trending and scout
and is captured into the harvest store, but `KDATA_FIELDS` has no column for it, so it is discarded on
write and the C leg — 28% of the weight, more than O — falls back to the listing-count heuristic on every
row. `agent.db` holds 7,777 real labels. Same one-column plumbing as this fix.

---

## 3 · New: the Long-tail lane (`/longtail`)

`src/longtail.py` (new, ~340 lines) + route + `main.py longtail` CLI.

**It is a VIEW.** It re-reads the rows the frozen engine already produced and applies its own selection.
A test (`test_longtail_lane_does_not_change_the_ranking`) pins that opening it changes no score, verdict
or action anywhere.

- **Question it asks:** not "how big is this market" (that's Rank, which head terms win) but "which
  specific phrases are already selling, in a market small enough to enter".
- **Ranked on:** money per listing (35%), conversion (30%), room to rank (20%), specificity (15%).
  Conversion and competition curves mirror `opportunity_score` so the words mean the same thing app-wide.
- **Honest-nulls:** a keyword without **both** revenue and conversion is **excluded, not down-ranked**, and
  the page states how many it dropped (450 of 534 long-tails today).
- **Unit-safe:** `_rev_per_listing()` handles both old (mixed) and new (`rev_total` present) rows, so the
  lane was correct even before the harvest re-ran.
- **Verdicts:** PUSH ≥70 · TEST ≥55 · WATCH.

**Result on live data: 106 evidence-backed long-tails, 26 PUSH**, where Rank shows 0 buildable ones.
Top rows: `custom crew t-shirt` $2,188/listing 5.1% conv 30 listings · `40th birthday cozies` $1,704 9.7%
39 · `hair bow monogram` $1,353 10.2% 30.

**V37.6 update — two of the four legs were doing no ranking work:**
- `specific` (word count, 15%) gave **99 of 106 scored rows the identical value**, and the master contains
  no 5+ word keyword at all. Removed; weights renormalised to money .41 / conversion .35 / room .24.
  Dropping it widened the p10–p90 spread 26.9 → 28.6. MIN_WORDS already enforces long-tail-ness.
- `money` saturated at **$2,512/listing** — 7 of the top 26 rows pinned at exactly 100, so the leg stopped
  separating rows exactly where the build decision is made. Scale now runs to ~$6.3k (real max $6,117).

Post-fix the lane scores **140 rows** (up from 106 — the engine fixes made more rows launchable) with
**13 PUSH**, a tighter and better-separated shortlist.

**Supply** — `longtail.pull()` reads YTrends `research_keyword` → `related_keywords`, which arrive **with
per-tag revenue + conversion**, so they are demand-grounded on arrival and can score immediately. Contrast
Keyword Lab: `shortlister_integration._enrich_row` fills conversion/listings/price but **never revenue or
views**, so its candidates are capped at WATCH by construction (`opportunity_score.py:345` — the
demand-grounded gate). Verified live: 1 seed → 8 usable long-tails.

Entry points: `/longtail` (top-bar 💎 link), the "Pull more long-tails" button on that page, and
`py main.py longtail "seed one" "seed two" [--dry]`.

---

## 4 · Also shipped: Team Daily Reports UX (`8f380cf`)

- Drive/Listing URL cells render as open-in-new-tab pills; editing moved to a ✎ button.
- Status as coloured badges (Draft grey · Completed green · Listed blue · Waiting Review amber · Blocked red),
  in both the manager grid and My reports; the inline-save JS re-renders the same badge.
- Row actions are now the review verdict: **✅ Approve** (was Verify) · **✏️ Improve** (was Clarify) ·
  **⛔ Reject** (was Block, now requires a reason). Note + delete are neutral icons.
- "Verified" column → **Review**, showing one badge: Approved / Needs improvement / Rejected / Pending.
- Backing change: additive nullable `review_state` column on `proactive_work_logs` (via the existing
  `_LOG_COLS` migration — filed rows untouched), so a manager Reject is distinct from a staff member
  self-marking their row Blocked. Included in the logs CSV export.
- `tests/test_team_ops.py` DR-16 updated: `<th>Verified</th>` → `<th>Review</th>`.

---

## 5 · Files changed

**New:** `src/longtail.py`, `tests/test_longtail.py` (19 tests), `22etsy_agent_handoff_V37.5.md`.

**Edited:** `src/harvest.py` (bugs 1-4, 6 — `_add`, `_pull`, `merge_existing`, `merge_master`,
`write_keyword_data`, `KDATA_FIELDS`), `src/opportunity_inbox.py` (+`rev_total` display field),
`src/team_ops.py` + `src/team_ui.py` (daily reports), `src/web.py` (`/longtail`, `/longtail/pull`,
top-bar link), `main.py` (`longtail` command), `deploy/push-to-vps.ps1` (merge step, now 1/4..4/4),
`tests/test_routes.py`, `tests/test_team_ops.py`.

**Schema:** `keyword_data.csv` gained `total_revenue` (between `avg_revenue` and `conversion_rate`).
Readers use `DictReader`, so older files still load.

---

## 6 · Deploy state — DONE, verified 2026-08-02

**Nothing outstanding. V37.5 is live.** Evidence, not assumption:

- VPS `git fetch && git reset --hard origin/main` → `HEAD is now at 319ebf9`, service restarted.
- Verified from outside: `https://etsy.theglobalserviceteam.site/longtail` serves the login page while an
  unknown path (`/zzz-not-a-real-route`) returns HTTP 404. The new route exists on the running process,
  so the restart picked up V37.5 code.
- `push-to-vps.ps1` ran twice post-fix (20:36, 20:47). Step 3/4 reported
  `carried in 0 VPS-only keyword(s), enriched 0` both times — the merge path works and destroyed nothing.
  1523 keywords on both machines.

**How to re-verify in one command** (do this instead of repeating "unconfirmed"):
```bash
curl -s -o /dev/null -w '%{http_code}\n' https://etsy.theglobalserviceteam.site/longtail   # 200/302 = V37.5 live, 404 = stale
```

Routine sync from the PC (the VPS IP is blocked from YTrends, so the PC harvests):
```powershell
cd D:\Claude\22etsy-agent
powershell -ExecutionPolicy Bypass -File deploy\push-to-vps.ps1   # step 1/4 already runs harvest
```
Restart `etsy-web` on the VPS only when code changed; data alone needs no restart.

**Closed:** the ~30 VPS `keyword-lab` keywords were lost in a pre-`9ef457d` push and are unrecoverable
(the growth ledger stores counts, not phrases). Confirmed: the current 1523-row master contains **zero**
`keyword-lab` rows — sources are `mcp:search` 698, `mcp:ranking` 482, `mcp:trending` 259,
`mcp:opportunity` 84. `py main.py longtail "<seed>"` regenerates that class with real metrics attached.

---

## 7 · Open / next

1. **Owner decision — top-bar placement.** 💎 Long-tail was added to the global top bar, which the owner
   had just trimmed (`4d70860`). Move it to Home-only if unwanted.
2. **Offered, not built — Re-rank plural matcher.** `/rerank`'s keyword box requires both typed words
   verbatim (`interactive.py:2129-2133`), no stemming, so "bridesmaid pajamas" misses "bridesmaid pajama
   set" / "bridesmaid pjs". ~2 lines.
3. **Keyword Lab enrich gap (bug 5's sibling).** `_enrich_row` never fetches revenue or views, so every
   Lab candidate is capped at WATCH. Either add those fields there or route Lab through `longtail.pull()`.
4. **Supply is still thin** — 106 evidence-backed long-tails from 1523 keywords. Run `main.py longtail`
   per niche regularly, or add a long-tail pass to `harvest._pull` (note: `find_trending_keywords` and
   `scout_opportunities` both default `min_listings=30`, which the API docs say "filters out low-signal
   long tail" — lowering it is the obvious lever).
5. **Pre-existing failure, not ours:** `tests/test_integration.py::test_full_selftest_pipeline` fails
   offline on "Trending/Opportunities/Gems paginate past the ~10-row server cap" (needs live MCP).
   Confirmed failing on a stashed baseline before any of this session's work.
6. Still parked from V37.4: v38 ranking-math (backtest says don't adopt), `design_analyzer.py` removal.

## 8 · Guardrails upheld

PUBLISH_AUTOMATION=false · no Seller-Central connection · honest-nulls (strengthened this session) ·
owner approval gates.

**Freeze status — changed in V37.6.** V37.5 kept `opportunity_score.py` and `ranking_engine.py`
untouched. V37.6 **did modify `opportunity_score.py`** (owner-authorised), because the GO band had become
unreachable for all 1523 keywords and the causes were all inside it. `ranking_engine.py` is still
untouched — the L4 word-count and proof-override rules are unchanged.

Three edits, all of them *removing fabricated values* rather than retuning the math — no weight, band or
curve was moved to make numbers look better:
1. `_demand_from` reads `niche_revenue` first (unit fix; the curve's own calibration was never changed).
2. `_feasibility` no longer inserts a `60.0` for an unmeasured seasonality signal.
3. `score()` returns `overall_score=None` when core data is missing, and adds `evidence_weight`.

Verified: **509 passed, 1 failed** — the failure is `test_full_selftest_pipeline`, the known offline MCP
pagination check, confirmed failing on a stashed baseline without these changes.
