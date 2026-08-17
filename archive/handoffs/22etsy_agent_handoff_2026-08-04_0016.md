# 22etsy-agent — Handoff · 2026-08-04 00:16 (+07)

_Session owner: Alex (Hue, Vietnam). **Supersedes `22etsy_agent_handoff_2026-08-03_1108.md`**, which
supersedes V37.11 → V37.8 → V37.5. Read this file first; where they disagree, the newest wins._

Repo `D:\Claude\22etsy-agent` · GitHub `NatoandUSA/etsy-agent` · VPS `~/etsy-agent`, service `etsy-web`.
Live: https://etsy.theglobalserviceteam.site

Naming convention continues: `22etsy_agent_handoff_<YYYY-MM-DD>_<HHMM>.md`, local time (+07).

---

## 0 · Status

| Commit | What | Pushed |
|---|---|---|
| `adff73c` | (previous session) home rebuilt, 5 phase rows naming their tools | ✅ |
| `c869c65` | (previous session) handoff 2026-08-03 11:08 | ✅ |
| `95ed431` | One canonical supplier matcher · feasibility badge gated on coverage | ✅ |
| `2624119` | `/training` + phase 1 teach the same 5 phases | ✅ |
| `5b74883` | selftest: assert the `WORKFLOW.md` table V37.10 actually wrote | ✅ |
| `ca37a58` | Supplier library made completable · coverage asked per mode | ✅ |
| `3c554bc` | Guide: phase 4 teaches both keyword sources | ⬅ **latest** |

`local main == origin main == 3c554bc`. Safety branch `backup/pre-rebase-v37.12` still exists —
delete once you are satisfied.

### ⚠️ VPS deploy is UNVERIFIED, and the usual probe cannot verify it

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://etsy.theglobalserviceteam.site/send-to-rerank
# 405 — but this only proves V37.7+, which was already true before this session.
```

**Every route this session changed is behind `@login_required`** (`/training`, `/suppliers`,
`/inbox`, `/trending` all return `302` to `/login` unauthenticated; `/healthz` does not exist).
No new route was added, so there is no new 404→405 marker either. **There is no unauthenticated
probe that discriminates this release.** Do not claim it is deployed from this file.

To confirm, deploy then check **logged in**:

```bash
ssh -p 55317 etsy@51.79.200.65 "cd ~/etsy-agent && git pull && .venv/bin/python -m compileall -q src && sudo systemctl restart etsy-web && sleep 2 && systemctl is-active etsy-web"
```
Then open `/suppliers` and look for the **"To finish"** column. If it is there, this release is live.

Tests: **572 collected, 571 pass, 1 fail.** The single failure is
`test_full_selftest_pipeline` → `Trending/Opportunities/Gems paginate past the ~10-row server cap`
(needs live MCP, predates everything). **Do not "fix" it offline.** The *second* sub-check the
previous handoff documented (`Workflow shown as a table`) is fixed — see §1.4.

---

## 1 · What this session changed

The previous handoff's §5 list drove the work. Items 1, 2, 3 and 4 are now done.

### 1.1 · `supplier_ops.match()` — the bug was worse than recorded

Recorded as "token overlap blocks ~100% of keywords". Measured on the live master, the truth was the
opposite and worse: **all 1,523 keywords scored exactly 50/100 "weak"**, because the score was
40 pts of token overlap it could never earn plus 50 pts of metadata (base cost, material,
personalization) that measures how *complete* a supplier record is, not how well it *fits*.

`"chenille name bag"` came back with **TSHIRT as its best supplier, 50/100, no warning.**

`product_family()` is now the ONE matcher, in `supplier_ops`, imported by `feasibility_gate`
(`test_the_gate_shares_this_matcher_and_does_not_fork_its_own` pins that they are the same object):

- different family → **0**, not a weak match
- no family and no shared token → **0**; metadata alone never scores
- explicit `pod`/`embroidery` mismatch → **0** (a production constraint, not a preference).
  Auto mode stays soft — nobody has said which method to use.

| | before | after |
|---|---|---|
| `custom crew t-shirt` (emb) | 50 weak | **90 strong → TSHIRT** |
| `chenille name bag` (emb) | 50 weak → TSHIRT | **0 → no supplier** |
| whole master, embroidery | 1,523 × 50 | **238 strong / 1,285 no-match** |
| whole master, POD | 1,523 × 50 | **0 — there are no POD product rows** |

`/suppliers` drops zero-score rows, so an all-miss search says "nobody" instead of listing eight
do-not-use rows.

### 1.2 · Feasibility gate — items C, D, E, F all done

- **C** — 25 tests (`tests/test_feasibility_gate.py`), plus 13 in `tests/test_supplier_ops.py`.
  `test_no_frozen_imports` parses the AST rather than grepping, so the module may
  still *name* `ranking_engine` in prose while never importing it.
- **D** — `coverage()` plus `product_family` / `supplier_source` / `coverage_status` /
  `last_updated` / `confidence` on **every** verdict. A miss on an incomplete library is
  `NEEDS_SUPPLIER_CHECK`, never a block.
- **E** — wired into the Inbox as a **badge**: `🏭 makeable` / `🏭 check supplier` rides in the
  Product-fit cell (same question, no 11th column), plus one summary line.
  `test_the_inbox_badge_changes_no_verdict_action_or_score` asserts every row is identical with the
  badge on and off.
- **F** — enforcement unlocks itself when coverage reaches `complete`. **Nothing is blocked today.**

### 1.3 · The open question is answered — by measurement

> *Is the supplier library genuinely embroidery-only, or just incomplete?*

**Incomplete.** `supplier_sources.json` registers **eight** suppliers; **one** has products.
The six POD catalogs and ShineOn have **zero rows imported**. So the old 10% `NOT_MAKEABLE` was an
import gap, not a fact about the shop.

### 1.4 · `/training`, phase 1, and the stale selftest assertion

- `/training` was serving 9 cards for the retired flow with "start at Build Queue every morning".
  **Rebuilt as 7 cards** (golden rules → 5 phases → support tools), Vietnamese, teaching content
  preserved and re-anchored. Pinned by a test the same way `WORKFLOW.md` is.
- Corrected inside it against what the code does: `/trending` cannot harvest (`py main.py harvest`
  on the PC); `/rerank` does not send; Build Queue is a shortcut, not the map; phase 3 says export
  HeyEtsy Detail **and** Etsy Reviews.
- `selftest.py:996` asserted a `WORKFLOW.md` header `66a0032` replaced. Fixed to the real 5-phase +
  per-phase tables.

---

## 2 · The supplier library — why it could not be finished, and what unblocks it

Enforcement (item F) was unreachable for **three separate reasons**, all now fixed. No data is
invented anywhere.

**① The importer threw away real supplier data.** `Embroidery.csv` carries
`US ePacket 7-12 business days - INCLUDED in price`; `_import_embroidery` kept the price and dropped
the window. All 25 rows now carry `shipping_time 7–12`, parsed from the sheet the team already
uploaded.

**② There was no way to enter the two facts every row is missing.** All 25 sit at
`SUPPLIER_PARTIAL` for want of `product_url` and `processing_time_min` — and **neither column exists
in the sheet**, while the upload form accepts only that one layout. The record was permanently
uncompletable through the app. The importer now reads **optional `product_url` and
`processing_days`** columns; absent stays absent.

> `CORE` / `SUPPLIER_CONFIRMED` was **not** relaxed. It feeds
> `product_manager.gates["supplier_confirmed"]` and the publish gate, so the two facts must come
> from the supplier, not from a lowered bar.

**③ Coverage is now asked PER MODE.** Judged as one library it could never be complete — six
registered-but-unimported POD catalogs would hold every mode at `partial` forever. A source's
declared modes are read with the same `mode_allows()` rule as a product row's, so there is still one
rule.

| mode | status | what is blocking |
|---|---|---|
| embroidery | `partial` | **zero missing suppliers** — only the 25 unconfirmed rows |
| pod | `unknown` | nothing imported from any of the 7 registered sources |
| overall | `partial` | both of the above |

Current badge counts (all modes): **238 makeable · 157 need a supplier check · 1,128 name no product
· 0 blocked.**

### The owner's move — two columns, one upload

Add to `data/suppliers/Embroidery.csv` and re-upload at `/suppliers`:

```
product_url,processing_days
https://…/tshirt,3-5
```

**Dry-run verified** (scratchpad, placeholder values, real file untouched): 25 rows →
`SUPPLIER_CONFIRMED`, embroidery coverage → `complete`, enforcement live —
`chenille name bag` → `NOT_MAKEABLE`, build blocked — while **POD correctly stays dormant**. Match
confidence on real products rises `medium` → `high`.

`/suppliers` now spells this out: a **To finish** column (`add product_url (25),
processing_time_min (25)`) and per-mode coverage naming exactly what flips the step-3 gate from a
badge to a block.

> **Deploy gotcha:** `data/suppliers/supplier_products.csv` is **gitignored**. The VPS keeps its own
> copy, so `git pull` does **not** carry the shipping-window fix — re-upload the sheet at
> `/suppliers` on the live site.

---

## 3 · Two sessions pushed to `main` on 2026-08-03

The push was rejected: `adff73c`/`c869c65` had landed while this work was in progress. Resolved by
rebasing 5 commits onto `c869c65` — history stays linear. **Four files genuinely overlapped:**

| Conflict | Resolution |
|---|---|
| `/suppliers` phase strip | **Theirs** — they found the same bug and fixed it better (`_stage_nav` + Back/Next + mode switch, new `"supplier"` stage key) |
| `_mode_tool` · `/trending` · `/pinterest-trends` | **Theirs** — same fix via the cleaner `_tool_head()` |
| `staff_guide_vn.html` header | **Mine** — theirs added a banner pointing *away* from a stale guide; the guide is no longer stale |
| Home guide card label | **Mine** — theirs says "guide to each tool, official process is /workflow"; the guide **is** the process now |

Both sessions independently found the missing phase-1 strip. Theirs is the better implementation and
is what shipped.

**The guide test then caught a real break:** phases 3/4 had moved to `/pattern-miner` and
`/keyword-lab`, so the guide named a route the spine no longer used. Fixed in `3c554bc`.

---

## 4 · Traps — do not repeat

Carried forward from the previous handoff, still true: **a 200 proves nothing** (check destination
*content*, and which phase the page thinks you are in) · `class="stgnav"` is **not** a reliable
marker for the phase strip, grep the phase **label text** · **do not** cache
`/trending`/`/opportunities`/`/gems` (they are already cached; 15 s was a cold laptop) · `"learn"`
is ambiguous · never plumb `discovered_keywords.opportunity` into the O leg · `_h_esc` escapes
`&` → `&amp;`, unescape before asserting · never say "deploy unconfirmed" from a doc — probe.

New this session:

1. **The probe itself can be non-discriminating.** `/send-to-rerank` → 405 proves V37.7+ and nothing
   more. Everything this release touched is behind login. Probing and *concluding* are different
   steps — say "unverified" when the probe cannot tell (§0).
2. **A score floor is worse than a wrong score.** `match()` gave every keyword 50/100 because
   metadata points were added to fit points. Any scorer that awards points for *data completeness*
   alongside *fit* will do this. Check the **distribution** over the real master, not two examples —
   1,523 identical scores is invisible from a spot check.
3. **"Unknown" and "no match" are different answers.** A POD query against a library with zero POD
   rows must say "not checked", not "needs a supplier check" — the latter claims we looked.
4. **A `sync()` placeholder row has a `supplier_id` and no product.** Counting it as "this supplier
   is covered" hides the entire gap. Require a non-empty `product_name`.
5. **`_import_embroidery` proves derived data can silently drop source data.** The shipping window
   sat in the sheet for months. When a record is stuck `PARTIAL`, check the *source* file before
   assuming the fact is unknown.

---

## 5 · Known broken / next up

1. **Phase 4's card and its own step buttons disagree.** `PHASES[4]["route"] == "/keyword-lab"`, but
   steps 9 and 10 route to `/imports` and `/rerank`, and step 10's *action* is `/imports` (V37.11
   fixed it there because `/rerank` sends nothing). **This is the exact defect class V37.11 existed
   to fix.** The re-point answered a direct owner complaint, so it was not overridden — but Keyword
   Lab candidates are capped at WATCH by construction (item 5 below) while **810 winner-derived
   candidates sit unsent**, so phase 4's headline route points at the weaker generator.
   **Owner decision needed:** re-point phase 4 to `/imports` and give Keyword Lab a tool slot, or
   re-point steps 9/10 to match the phase.
2. **`/team/ops` has no phase strip.** It is a full-page sub-app in `src/team_ui.py` with its own
   sidebar and a "↩ Command Center" link; adding the strip means a 9th parameter through
   `team_ui.register()`. Left alone deliberately. 11 of 12 step routes carry it.
3. **`WORKFLOW.md` says it is generated from `workflow_spine.py`, and is not.** It is hand-written
   and has already drifted (step 1's `need` text differs from the module). A real generator would
   close this permanently; the pin-test only checks names and routes.
4. **Nobody has clicked any of this in a browser.** Carried forward and still true — every claim
   here is from rendered HTML behind a Flask test client. Confirm phase 3 → Pattern Miner, phase 4 →
   Keyword Lab, and the `/suppliers` To-finish column on the live site.
5. **Keyword Lab enrich gap:** `shortlister_integration._enrich_row` never fetches revenue or views,
   so Lab candidates are capped at WATCH by construction.
6. **Zero BUILD_NOW rows locally.** All GO keywords are 3 words and L4 routes anything <4 words to
   Pattern Miner (`ranking_engine.py:176-186`) — the owner's own rule. **Long-tail supply is the
   binding constraint**, not scoring.
7. **Live data gap:** VPS shows *71 winners imported · 0 with reviews* — the team runs the expensive
   HeyEtsy Detail export and skips the cheap Reviews export. Reviews produce the recipient/occasion
   language behind the candidates. The `/training` guide now says this explicitly in phase 3.
8. **Three guide chapters the previous session flagged are now written** — Pinterest trend signal,
   Supplier feasibility and HeyEtsy evidence all have content inside phases 1 and 3. Review the
   Vietnamese for tone; it was written from the code, not from the owner's words.
9. `src/version.py` still says `VERSION = "37.0"` and has tracked no V37.x work. It is not a deploy
   marker. Either maintain it or delete it.

---

## 6 · Data + guardrails

- `keyword_data.csv` — **1,523 rows** locally (VPS ~1,544). No test data.
- Supplier library: **25 rows, 1 of 8 registered suppliers, 0 confirmed**, families
  `cap / hoodie / sweatshirt / tshirt`, all `EMBROIDERY`. `supplier_products.csv` is **gitignored**.
- New public API: `supplier_ops.product_family()` · `supplier_ops.PRODUCT_FAMILIES` ·
  `supplier_ops.mode_allows()` · `supplier_ops._day_range()` · `feasibility_gate.coverage(path, mode)` ·
  `feasibility_gate.NEEDS_SUPPLIER_CHECK` · `feasibility_gate.LABELS`.
- `opportunity_inbox._data_stamp()` now includes `data/suppliers/supplier_products.csv`, so importing
  a supplier revives badges immediately — that is the gate's "revivable" promise.
- `PUBLISH_AUTOMATION = False` (`team_ops.py:2227`, `ops.py:335`) · no Seller-Central connection ·
  honest-nulls · **`ranking_engine.py` frozen and untouched** · `opportunity_score.py` untouched.
  Nothing this session changed scoring; a test pins it.
- All changed `.py` files verified to parse under **Python 3.10** (`ast.parse(feature_version=(3,10))`)
  — the VPS runs 3.10.12, which has no PEP 701 f-strings.

---

## 7 · How the owner wants this work run

Stated three times now and worth honouring: **review first, propose a ranked plan, get sign-off, then
fix in that order.** No broad refactors, no unrelated modules, no new features while the current
workflow is unstable. *"Do not blind fix — check the code, check the process."* — and this session
added: **read the data too.** The `match()` bug, the answer to the supplier-library question, and the
dropped shipping window were all found by measuring the real files, not by reading the code.

**Show measurements, not assertions.** Every number here was measured against the live master, the
real supplier library, or a rendered page — and where a probe could not settle a question (the deploy
state, §0), this file says so instead of guessing.
