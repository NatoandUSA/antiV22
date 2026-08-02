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
(1523 rows, new `total_revenue` column). Whether the VPS has been pulled/synced since is unconfirmed —
see §6.

---

## 1 · The problem this session solved

Owner's report: *"Build now is full of head terms (funny tee, funny shirt). I need long-tail keywords to
push — low signal but higher chance to sell."* Plus: *"it has been a few days but this is not updating
anything."*

Diagnosis (measured, not assumed):
- The **word-count rule already favours long-tails** — `ranking_engine` forces ≤2-word terms down to
  Pattern Miner. It was never the blocker. Head terms reach Build only via the **Etsy-proof override**
  (`ranking_engine.py:94-98`), which bypasses the word rule; big terms are exactly the ones with sales proof.
- **GO needs overall ≥ 80** (`opportunity_score.py:347`). The highest-scoring long-tail in the whole base
  was **73.6**. No long-tail could ever be promoted on merit.
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

## 6 · Deploy state — what still needs doing

```bash
# VPS
cd ~/etsy-agent && git fetch origin && git reset --hard origin/main && sudo systemctl restart etsy-web
```
```powershell
# PC — the fixes only reach the data when harvest rewrites it (already run once, 19:49 on 08-02)
cd D:\Claude\22etsy-agent
py main.py harvest
powershell -ExecutionPolicy Bypass -File deploy\push-to-vps.ps1
```

Watch for `carried in N VPS-only keyword(s)` in step 3/4 — keywords the old script would have deleted.

**Unresolved:** the VPS held ~30 `keyword-lab` keywords. If `push-to-vps.ps1` was run before `9ef457d`
landed, they were overwritten and cannot be recovered (the growth ledger stores counts, not phrases).
`py main.py longtail "<seed>"` regenerates that class of keyword with real metrics attached.

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
owner approval gates · **L0–L4 ranking math frozen** — `opportunity_score.py` and `ranking_engine.py`
were not modified. Every fix was to the data feeding them or to a view beside them.
