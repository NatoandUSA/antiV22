# 22etsy-agent — Handoff (V37.8 → V37.11)

_Session of 2026-08-03. Owner: Alex (Hue, Vietnam). **Supersedes `22etsy_agent_handoff_V37.8.md`**,
which supersedes V37.5. Read this file first; where they disagree, the newest wins._

Repo `D:\Claude\22etsy-agent` · GitHub `NatoandUSA/etsy-agent` · VPS `~/etsy-agent`, service `etsy-web`.
Live: https://etsy.theglobalserviceteam.site

---

## 0 · Status

| Commit | What | Deploy |
|---|---|---|
| `258b2d2` | V37.8 **wip** — `feasibility_gate.py`, dry-run + **unwired** | ❌ never deploy alone |
| `1202ad2` | V37.9 — home rebuilt around ONE workflow (killed the duplicate 9-step pipeline) | ✅ |
| `66a0032` | V37.10 — 12 steps → **5 phases**; guide text Vietnamese | ✅ |
| `5d8b01e` | V37.11 — **one workflow model on every page**; fixed 2 buttons that lied; home back to English | ⬅ **latest** |

`local main == origin main == 5d8b01e`.

**Verify what's actually live — never quote a doc for this:**
```bash
curl -s -o /dev/null -w '%{http_code}\n' https://etsy.theglobalserviceteam.site/send-to-rerank
# 405 = V37.7+ live (route exists, POST-only). 404 = stale.
```

Tests: **531 passed, 1 failed** — `test_full_selftest_pipeline` →
`Trending/Opportunities/Gems paginate past the ~10-row server cap`. Needs live MCP, predates all this
work, confirmed failing on a stashed baseline. **Do not "fix" it offline.**

---

## 1 · The workflow model (read before touching any page)

`src/workflow_spine.py` is the **single source of truth**. It defines:

- **`STEPS`** — the owner's real 12 steps (the checklist).
- **`PHASES`** — 5 phases that GROUP those steps (the navigation).

| Phase | Steps | Route | English (UI) | Vietnamese (guide) |
|---|---|---|---|---|
| 1 | 1–3 | `/trending` | Find & filter | Tìm & lọc |
| 2 | 4 | `/inbox` | Rank | Xếp hạng |
| 3 | 5–8 | `/imports` | Learn from winners | Học người thắng |
| 4 | 9–10 | `/imports` | New keywords | Từ khoá mới |
| 5 | 11–12 | `/launch-kit` | Build & ship | Làm & giao |

**Why 5 and not 12:** the 12 are the right checklist but the wrong navigation. Steps 6/7/8 are one
sitting-down job on one route; 9/10 became a **single button** when the winner→Inbox loop closed in
V37.7. Twelve tiles read as a project plan, not a day's work. Nothing was lost — a test asserts all 12
are covered exactly once.

**Everything renders from this module:** the home page, `_stage_nav()` (the strip on every tool page),
and `WORKFLOW.md`. If you add a route, that does **not** mean adding a step — add it to
`SUPPORT_ROUTES`.

### Language rule (owner-specified, corrected twice)
- **UI / home page → ENGLISH** (`en`, `en_do`, `en_out`).
- **How-to-use guide → VIETNAMESE** (`vi`, `vi_do`, `vi_out`, and all of `WORKFLOW.md`).
- **Listing output — title, 13 tags, description → ENGLISH**, because the buyers are American.
- Vietnamese is **web-UI/doc only**. CLI output stays unaccented: the Windows console is cp1252 and
  accented characters raise `UnicodeEncodeError`. (Use `PYTHONIOENCODING=utf-8` when testing locally.)

---

## 2 · V37.9–V37.11 — what was wrong and what fixed it

**V37.9.** V37.7's spine was only *added*. Live home showed the 12-step rail **and** the older 9-step
button pipeline (a different process: no Pinterest, no supplier, no evidence) above 32 tool cards in
four always-open grids. Two competing maps. Fixed: one "Do this next" card + a compact rail, pipeline
deleted, all tool cards behind one disclosure, 15 orphaned CSS rules removed.

**V37.10.** Owner: *"12 steps is too many."* Correct → the 5 phases above.

**V37.11 — the important one.** The owner clicked the phase cards and landed in the wrong place.
Click-testing all 12 routes *and their destination content* (status codes were 200 and told me nothing)
found three defects:

1. **Every tool page still showed the old NINE-stage strip.** V37.10 fixed home only. `_stage_nav()`
   — on `/imports`, `/inbox`, `/pattern-miner`, `/rerank`, `/launch-kit`, `/keyword-lab` and 4 more —
   still drew `Feed·Rank·Pattern·Keywords·Re-rank·Build·Images·Ads·Learn`. Clicking a phase card landed
   you on a page describing a *different* workflow with *different* numbers. **This was the real cause
   of "leads to wrong page" and was invisible from home.** Now renders from `PHASES`;
   `_STAGE_TO_PHASE` maps the 9 old keys so all call sites keep working.
2. **Step 1 "Harvest keywords" → `/trending` did not harvest.** That view is a plain listing. Harvest is
   `py main.py harvest` **on the PC** (the VPS IP is blocked from YTrends). Relabelled
   *"Browse trending keywords"*.
3. **Step 10 "Send to Re-rank / Inbox" → `/rerank` sent nothing.** `GET /rerank` never calls
   `send_to_rerank`; the send is `POST /send-to-rerank` whose button lives on `/imports`. Re-pointed to
   `/imports`, relabelled *"Pick candidates & send"*.

Verified: **12/12 step buttons reach a page that can actually perform that step** (content-checked).

---

## 3 · V37.8 wip — supplier feasibility gate (committed, **NOT wired**)

`src/feasibility_gate.py`. Nothing imports it. Dry-run at the owner's instruction.

Why: supplier feasibility was only checked at the **publish** gate
(`product_manager.gates["supplier_confirmed"]`) — after the title, 13 tags, description, design brief
and photo plan were written for a product the shop cannot make. It belongs at step 3.

`MAKEABLE / UNKNOWN / NOT_MAKEABLE`. Empty or unreadable library ⇒ **UNKNOWN, never a block**.
Pinterest is **advisory only** (`RISING/FLAT/NONE/UNKNOWN`) and can never veto.

> **It deliberately avoids `supplier_ops.match()`** — that scores token overlap between a keyword and a
> supplier product NAME, and the real library holds four blank types (`TSHIRT`, `SWEATSHIRT`, `HOODIE`,
> `WASH CAP`, all EMBROIDERY). Measured: **every threshold blocked ~100% of keywords**;
> `"custom crew t-shirt"` does not even token-match `"TSHIRT"`. The gate normalises both sides to a
> product-TYPE vocabulary instead → **74% UNKNOWN / 16% MAKEABLE / 10% NOT_MAKEABLE**, spot-checks
> correct. **`supplier_ops.match()` is still a real unfixed bug** used by the supplier UI and
> `supplier_trend` lane leads.

**Zero frozen references** (an early draft imported `ranking_engine._PRI`; removed at owner's request).

### Owner's required order — A and B done, C–F remain
- **A** keep dry-run ✅ · **B** remove frozen import ✅
- **C** tests for `supplier_fit` / `build_allowed` / `pinterest_label` / `apply_to_row` + a
  `test_no_frozen_imports`
- **D** supplier coverage: `product_family`, `supplier_source`,
  `coverage_status(complete/partial/unknown)`, `last_updated`, `confidence`.
  complete + no match ⇒ NOT_MAKEABLE; **partial/unknown + no match ⇒ `NEEDS_SUPPLIER_CHECK`, not a
  hard block**; empty ⇒ UNKNOWN
- **E** Inbox + spine **badge only** (Makeable / Not checked / Needs supplier check / Supplier blocked)
- **F** enforcement only after the library is verified complete

**Open question for the owner:** is the supplier library genuinely embroidery-only, or just incomplete?
That decides whether 10% NOT_MAKEABLE is a business fact or an import gap.

---

## 4 · Known broken / next up

1. **`/training` still teaches the retired 9-step flow** — it now contradicts home *and* `WORKFLOW.md`.
   Cheapest remaining inconsistency to close.
2. **`supplier_ops.match()`** — see §3. Needs one canonical matcher shared with the gate, with tests.
3. **Zero BUILD_NOW rows locally.** All GO keywords are 3 words and L4 routes anything <4 words to
   Pattern Miner (`ranking_engine.py:176-186`) — the owner's own rule. **Long-tail supply is the
   binding constraint**, not scoring.
4. **Live data gap:** the VPS shows *71 winners imported · 0 with reviews*, so the team exports HeyEtsy
   Detail but skips the Reviews export — they do the expensive half and skip the cheap half. Reviews
   are what produce the recipient/occasion language behind the candidates.
   Also **810 candidates from 136 winners waiting to be sent** at phase 4: the loop we built, loaded and
   unused.
5. Keyword Lab enrich gap: `shortlister_integration._enrich_row` never fetches revenue or views, so Lab
   candidates are capped at WATCH by construction.

---

## 5 · Traps — do not repeat

1. **Never plumb `discovered_keywords.opportunity` into the O leg.** It looks ideal (11,680 rows, 449
   distinct) and is `discover.score()` = `log10(revenue) × conv × momentum ÷ listings` — every input is
   already a leg, so it double-counts all four and amplifies them. Pinned by
   `test_o_leg_is_never_fed_a_derived_score`. I recommended it in error; good spread ≠ independent
   information.
2. **Never say "deploy unconfirmed" from a doc.** Probe the live site (§0). That stale line got repeated
   across three sessions while the owner had deployed every time.
3. **A 200 status code proves nothing.** All 12 broken-feeling buttons returned 200. Check destination
   **content**.
4. **`_h_esc` escapes `&` → `&amp;`.** Two "failures" this session were wrong test strings, not broken
   code. Unescape before asserting.
5. V37.5's *"no long-tail can ever be promoted, best is 73.6"* was **wrong** — it was a unit regression
   holding the whole base down. Long-tails score marginally *higher* than head terms.
6. `DESIGN_PREP_READY`/`PUBLISH_READY` is a **listing-QA** gate (`product_manager.py:588`), unrelated
   to GO.

---

## 6 · Data + guardrails

- `keyword_data.csv` — **1,523 rows** locally (VPS ~1,544), sources `mcp:search` 698 / `mcp:ranking` 482
  / `mcp:trending` 259 / `mcp:opportunity` 84. **No test data**; every `winner:` test row was removed.
- Schema gained `total_revenue` (V37.5) and `opportunity_score` (V37.6); `DictReader` keeps old files
  loading. `opportunity_score` only fills on the next `main.py harvest`.
- Evidence lanes for listing **4412078408** retained with the corrected V37.7 parse — a real fixture.
  Tests use `tmp_path` and never touch the real master.
- Untracked, owner's call: `22Etsy_Evidence_Exporter_v3.3/`, `22Etsy_Evidence_Exporter_v3.4.0 (1)/`,
  and the two source CSVs.
- `PUBLISH_AUTOMATION = False` (`team_ops.py:2227`, `ops.py:335`) · no Seller-Central connection ·
  honest-nulls · **`ranking_engine.py` frozen and untouched**. `opportunity_score.py` was modified in
  V37.6 under explicit owner authorisation, in its own commit.

---

## 7 · How the owner wants this work run

Stated directly and worth honouring: **review first, propose a ranked plan, get sign-off, then fix in
that order.** No broad refactors, no unrelated modules, no new features while the current workflow is
unstable. Show measurements, not assertions — every claim in this file was measured against the live
master or a click test.
