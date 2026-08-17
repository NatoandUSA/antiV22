# 22etsy-agent — Handoff (V37.6 → V37.8)

_Session of 2026-08-02/03. Owner: Alex (Hue, Vietnam). Supersedes `22etsy_agent_handoff_V37.5.md`._
_Read this file first. Where it disagrees with V37.5, **this file wins** — V37.5 contains a claim that
turned out to be wrong (see §7)._

Repo: `D:\Claude\22etsy-agent` · GitHub `github.com/NatoandUSA/etsy-agent` · VPS `~/etsy-agent`,
service `etsy-web`. Live: https://etsy.theglobalserviceteam.site

---

## 0 · Status at a glance

| Commit | What | Deployed? |
|---|---|---|
| `f018530` | V37.6 scoring — made the GO band reachable (0 of 1523 could reach it) | ✅ live |
| `77c8e6e` | V37.7 steps 1–2 — closed the winner→Inbox loop, fixed HeyEtsy import bugs | ✅ live |
| `55697db` | V37.7 step 3 — one 12-step workflow spine (home + WORKFLOW.md) | ✅ live |
| `258b2d2` | V37.8 **wip** — `feasibility_gate.py`, dry-run + unwired | ❌ **do NOT deploy** |

`local main == origin main == 258b2d2`. **The VPS is on `55697db` and should stay there** — `258b2d2`
adds an unwired module; deploying it only puts dead code on the server.

**Verify the deploy in one command** (do this instead of ever saying "deploy unconfirmed"):
```bash
curl -s -o /dev/null -w '%{http_code}\n' https://etsy.theglobalserviceteam.site/send-to-rerank
# 405 = V37.7 live (route registered, POST-only).  404 = stale.
```

Tests: **527 passed, 1 failed**. The failure is `test_full_selftest_pipeline` →
`Trending/Opportunities/Gems paginate past the ~10-row server cap`. It needs live MCP, predates all of
this work, and was confirmed failing on a stashed baseline. **Do not "fix" it offline.**

---

## 1 · How this session was run (and why)

The owner's words: *"the work still feels too fragmented… one small fix here, one patch there… I do not
even clearly know what step I am in."* That criticism was fair. The session switched to **review first,
fix second, in an approved order**, and that is the working mode to keep.

Order the owner approved and signed off on step by step:
1. Close the 10→11 loop · 2. Fix the import bugs · 3. One workflow spine · 4. Review Pinterest/supplier.

**Do not start work outside an agreed order.** Present findings, propose a ranked plan, get sign-off.

---

## 2 · V37.6 — the GO band was unreachable (`f018530`)

**Before: 0 of 1523 keywords could reach GO.** A deadlock: rows *with* market data topped out at 76.2
against a ≥80 threshold; rows *without* data scored up to 87.2 but were force-capped at WATCH by the
demand-grounded gate. Measuring a keyword cost it ~20 points.

Three causes, all **fabricated or mis-scaled values, not bad maths**. No weight, band or curve was
retuned to make numbers look better:

| # | Cause | Fix |
|---|---|---|
| 1 | **Demand leg fed the wrong unit.** V37.5 correctly made `avg_revenue` per-listing, but nothing converted it back and `_demand_from`'s curve is calibrated for niche totals. Median per-listing $627 → demand 22.8 vs niche total $64,142 → demand 80.2. The whole base sat ~57 demand points low. **This was a regression introduced by V37.5's own fix.** | `_to_scorer` passes `niche_revenue`; `_demand_from` reads it first |
| 2 | **Fabricated seasonality constant.** `_feasibility` inserted `60.0` for a signal with no source (`seasonal.py` is a holiday *calendar*), costing every row 14 pts and capping F at 79.25. | Renormalise onto the measured signal. Widens spread both ways: launchable 79.2→88.0, unmakeable 56.8→48.0 |
| 3 | **Missing legs RAISED scores.** 561 rows with no market data scored 76–87 on competition-from-listing-count + a deterministic classifier, and sorted **above** every measured row. | `overall_score = None` when core (M or C) missing; new `evidence_weight` field |

**Backtest before adopting:** 156 flips (10.2%) — SKIP→WATCH 101, WATCH→CONDITIONAL 52, CONDITIONAL→GO 3.
Nothing downgraded except genuinely weak rows (SKIP 225→124).

Also plumbed the **O leg** from `scout_opportunities`' own `opportunity_score` (a vendor estimate,
distinct from `momentum_score`/`competition_score`), which harvest received and discarded into the dedup
field. New `opportunity_score` column in `keyword_data.csv`.

> ⚠️ **DO NOT plumb `discovered_keywords.opportunity` from `agent.db`.** It looks ideal (11,680 rows, 449
> distinct, p10 0.1 → p90 97.5) and is **the wrong column**: it is `discover.score()` =
> `log10(revenue+1) × conv × momentum ÷ listings` — every input is already a leg in the composite, so it
> would double-count all four and, being a product, amplify them. Pinned by
> `test_o_leg_is_never_fed_a_derived_score`. I recommended this in error mid-session; the spread fooled
> me. Good spread ≠ independent information.

**Freeze exception:** this commit modifies `opportunity_score.py`, which V37.5 froze. Owner-authorised,
in its own commit. **`ranking_engine.py` remains untouched** and must stay that way.

---

## 3 · V37.7 steps 1–2 — the open loop and the import bugs (`77c8e6e`)

Found by running the owner's **real** `HeyEtsy_4412078408_Detail.csv` + `Etsy_4412078408_Reviews.csv`
through the actual code path instead of reading it.

**Step 1 — the 10→11 loop was open.** The listing keyword map had been built on every import since
V37.4, and `candidates_for_rerank()` had **zero production callers**. Pattern Miner's existing
"Send candidates to Re-rank" button only filed a *team task*; keywords still had to be retyped by hand.
That open loop is what made the tool feel like it ran back and forth.

- `candidates_for_keyword()` — joins a mined keyword to its winners' candidates via the same
  CF007-guarded bridge (verified: `stainless steel dog tag` correctly returns nothing).
- `send_to_rerank()` — reuses `keyword_lab.save_candidates()`, the **same** path Keyword Lab uses, so
  keywords enter the master through one path. Tags `source=winner:<listing_id>`, which harvest treats as
  provenance and never overwrites.
- Audit ledger `data/imports/rerank_pushes/`: source listing_id, source keyword, reason, evidence
  summary, action cap, actor, per-keyword match type + confidence.
- UI: pickable candidates on `/imports` and `/pattern-miner`; `POST /send-to-rerank`; confirmation
  banner on `/rerank`. Dedupe verified (`already_present`, no duplicate rows).

Everything is capped at `CONFIRM_FIRST`; the frozen engine still decides the final action.

**Step 2 — import bugs:**
- **Listing URL pointed at the HeyEtsy shop page.** `_ci()` returns the first header containing a needle
  in *file order*, and the v3.4 export puts `shop_url` (col 20) before `etsy_url` (col 24) — the real
  listing URL was dropped, breaking workflow step 7.
- **Winner photos never captured** — `image_urls` (JSON array) + `main_image` now parsed (20 images on
  the test listing), `image_count` derived when absent.
- **`shop_rating` never mapped** — now stored and displayed.
- **`"flower"` was in `RECIPIENT_NOUNS`** as a stand-in for "flower girl", but matching is per-token, so
  any floral *pattern* mention generated `personalized tote for flower`. Now phrase-matched.

---

## 4 · V37.7 step 3 — the workflow spine (`55697db`)

104 routes, 39 CLI commands, no ordering; `WORKFLOW.md` described a **different 9-step V30 flow**.

**`src/workflow_spine.py` is now the single source of truth** for the owner's real 12-step process. The
home page and `WORKFLOW.md` both render from it, and `test_workflow_spine.py` asserts the doc matches
the module, so they cannot drift again.

Per step: name · ONE canonical route · required input · live status · action button · output · next step ·
owner role. `status()` reads real data (honest-nulls — a step is only ✅ when its output exists on disk;
an unreadable probe degrades to "unknown", never a fake tick). Home highlights the first unfinished step
as **YOU ARE HERE**.

Route policy: 12 canonical routes on the main path; everything else grouped under a collapsed
**Advanced / support routes** block. A test asserts no route is both canonical and support.
**No route was moved or renamed.** The old 9-step flow is marked DEPRECATED in `WORKFLOW.md` with the
reason it was wrong.

**If you add a route, that does NOT mean adding a step.** Add it to `SUPPORT_ROUTES`.

---

## 5 · Evidence it worked — five keywords, live master

| Keyword | Before | After | Supplier | Proves |
|---|---|---|---|---|
| `patriotic soft tee` | 74.6 CONDITIONAL | **81.0 GO** | Makeable | First GO ever; only the units changed |
| `custom crew t-shirt` | 64.8 WATCH | 71.4 CONDITIONAL | Makeable | $2,188/listing · 5.1% conv · 30 listings |
| `40th birthday cozies` | 63.9 WATCH | 70.0 CONDITIONAL | **Not makeable** | 9.7% conv, but no koozie supplier |
| `wood look sign` | **87.2 (top of inbox)** | — (no score) | Not checked | 5 listings, no revenue/conv, ev 0.38 |
| `personalized name tote handbag` | not in master | 1 of 9 auto-derived | **Not makeable** | The closed loop working |

`wood look sign` is the clearest proof the old ranking was inverted: the emptiest row in the database was
the single highest-ranked keyword in the tool.

Report artifact: https://claude.ai/code/artifact/9f535e13-dfa7-4cbe-bbf2-ca43aa36a8c0

---

## 6 · V37.8 wip — supplier feasibility gate (`258b2d2`, NOT wired)

`src/feasibility_gate.py`. **Nothing imports it.** Dry-run only, at the owner's explicit instruction.

Why it exists: supplier feasibility was only checked at the **publish** gate
(`product_manager.gates["supplier_confirmed"]`) — after title, 13 tags, description, design brief and
photo plan were written for a product the shop cannot make. In the owner's workflow it is **step 3**.

Verdicts `MAKEABLE / UNKNOWN / NOT_MAKEABLE`. Empty or unreadable library ⇒ **UNKNOWN, never a block**.
Pinterest support is **advisory only** (`RISING/FLAT/NONE/UNKNOWN`) and can never veto.

> **It deliberately does not use `supplier_ops.match()`.** That scores token overlap between a keyword
> and a supplier product NAME. The real library holds four blank types — `TSHIRT`, `SWEATSHIRT`,
> `HOODIE`, `WASH CAP`, all EMBROIDERY. Measured: **every threshold blocked ~100% of keywords**;
> `"custom crew t-shirt"` does not even token-match `"TSHIRT"`. The gate normalises both sides to a small
> product-TYPE vocabulary instead. Result on the live master: **74% UNKNOWN (dormant) · 16% MAKEABLE ·
> 10% NOT_MAKEABLE**, spot-checks correct (tote/koozie blocked; tee/hoodie/cap allowed).
> **`supplier_ops.match()` remains a real, unfixed bug used elsewhere** (`supplier_trend` lane leads,
> supplier library UI).

**Zero frozen references** — an early draft imported `ranking_engine._PRI` read-only; the owner had it
removed (an import is a dependency). The six action priorities are duplicated locally.

### What the owner requires BEFORE enforcement (order: A→F, currently at B done)

- **A.** Keep dry-run. ✅
- **B.** Remove frozen import. ✅ done in `258b2d2`.
- **C.** Tests for `supplier_fit` / `build_allowed` / `pinterest_label` / `apply_to_row`, plus a
  `test_no_frozen_imports` grepping code lines for `ranking_engine|opportunity_score`.
- **D.** Supplier catalog coverage: `product_family`, `supplier_source`,
  `coverage_status (complete/partial/unknown)`, `last_updated`, `confidence`. Rule:
  complete + no match ⇒ NOT_MAKEABLE; **partial/unknown + no match ⇒ `NEEDS_SUPPLIER_CHECK`, not a hard
  block**; empty library ⇒ UNKNOWN.
- **E.** Wire to Inbox + spine as a **visible badge only**: Makeable / Not checked / Needs supplier
  check / Supplier blocked.
- **F.** Enforcement (block Build Queue / Launch Kit / Team Ops build tasks) **only after** the library
  is verified complete enough.

Required tests: UNKNOWN does not block · partial library ⇒ NEEDS_SUPPLIER_CHECK · complete library +
no match ⇒ blocks build · Pinterest NONE does not block.

**Open question for the owner:** is the supplier library genuinely embroidery-only, or is it incomplete?
That decides whether the 10% NOT_MAKEABLE figure is a real business constraint or an import gap.

---

## 7 · Corrections to V37.5 (do not repeat these)

1. **"No long-tail can ever be promoted; the best 4-word keyword reaches 73.6."** Wrong reading. The
   ceiling was real but it held the *entire base* down, head terms included, and the cause was the
   V37.5 unit regression (§2). Re-measured: among demand-grounded rows long-tails score marginally
   **higher** than head terms (max 76.2 vs 74.3, median 53.7 vs 48.8). **There is no word-count bias in
   the engine.** `longtail.py`'s docstring carries the correction.
2. **"Deploy unconfirmed."** V37.5 §6 said this; it caused the claim to be repeated across three
   sessions while the owner had in fact deployed each time. **Probe the live site, never quote a doc's
   deploy status.** See §0.
3. `DESIGN_PREP_READY` / `PUBLISH_READY` being false is a **listing-QA** gate
   (`product_manager.py:588` — `not fails and exactly_13_tags`), unrelated to GO. Keep the two apart.

---

## 8 · Known-broken / next candidates

1. **Zero BUILD_NOW rows.** All 3 GO keywords are 3 words, and L4 deliberately routes anything <4 words
   to Pattern Miner (`ranking_engine.py:176-186`) — the owner's own rule. Only 82 of 1523 rows are 4+
   words, so **long-tail supply is now the binding constraint**, not scoring.
2. **`supplier_ops.match()`** — see §6. Needs one canonical matcher shared with the gate, with tests.
3. **Workflow steps 2 and 3 are empty** — no Pinterest capture, no supplier check has ever run.
   `data/imports/pinterest/` and `data/imports/supplier/` (the paths `pipeline_status.py:75-76` uses).
4. **Keyword Lab enrich gap** — `shortlister_integration._enrich_row` never fetches revenue or views, so
   Lab candidates are capped at WATCH by construction.
5. Parked from V37.4: v38 ranking math (backtest says don't adopt), `design_analyzer.py` removal.

---

## 9 · Data + guardrails

- `keyword_data.csv` — **1,523 rows**, sources `mcp:search` 698 / `mcp:ranking` 482 / `mcp:trending` 259
  / `mcp:opportunity` 84. **No test data.** Every test-pushed `winner:` row was removed.
- Schema gained `total_revenue` (V37.5) and `opportunity_score` (V37.6). Readers use `DictReader`, so
  older files still load. `opportunity_score` only populates on the next `main.py harvest`.
- Evidence lanes retained for listing **4412078408** (detail / reviews / keyword_map) with the corrected
  V37.7 parse — useful as a real fixture. Tests use `tmp_path`, so they never touch the real master.
- Untracked and left to the owner: `22Etsy_Evidence_Exporter_v3.3/`, `22Etsy_Evidence_Exporter_v3.4.0 (1)/`,
  and the two source CSVs.
- `PUBLISH_AUTOMATION = False` (`team_ops.py:2227`, `ops.py:335`) · no Seller-Central connection ·
  honest-nulls · owner approval gates · **`ranking_engine.py` frozen and untouched**.
