# 22etsy-agent — Handoff (V37.4, consolidated)

_Updated 2026-07-27. Owner: Alex (Hue, Vietnam). Supersedes the V37.2 handoff. Everything below is
additive; the frozen L0–L4 ranking math (product_fit, trademark, opportunity_score, ranking_engine.decide)
was NOT touched in any of this work._

Repo: `D:\Claude\22etsy-agent` (Windows) · GitHub `github.com/NatoandUSA/etsy-agent` · VPS `~/etsy-agent`,
service `etsy-web`. Live: https://etsy.theglobalserviceteam.site

---

## 0 · Deploy status at a glance
- **Batch 1 — PUSHED + (deploy on VPS when ready).** Evidence Router + workflow wiring + Import card +
  Photo Studio + Team Command Center + subpage polish + README/selftest green-suite fix. Commits up to
  `f6ed880` + the README/selftest commit are on GitHub `main`.
- **Batch 2 — CODE NOW ON THE PC (written this session), not yet committed.** Engine-test fixes +
  ads-plan fix + Rank/Pattern/KeywordLab improvements. Commit + push, then VPS deploy. Commands in §6.

No new Python deps, no DB migration, no Chrome-extension change across either batch.

---

## 1 · Batch 1 — what shipped (already on GitHub)

**Feed Center Evidence Router** — `src/feed_evidence_router.py` (new, stdlib-only). Four validated,
`{listing_id}`-keyed lanes under `data/imports/` (etsy_listing_detail / etsy_listing_reviews /
etsy_review_summary / listing_keyword_map). Safeguards: conversion 4→0.04, K/M parse, html.unescape,
summary-once dedup, has_review_photo split, honest-null variation, broad-tag→modifier, match_confidence +
action_cap. Single-listing evidence caps at CONFIRM_FIRST; PROVEN needs shop_spread≥2. Never writes
keyword_data.csv (L2 untouched). Wired into `/api/import` + `/import-file` ahead of proof/spy.

**Wired into the workflow** — Pattern Miner "Buyer voice" section; Keyword Lab review-derived candidates
(CONFIRM_FIRST); `evidence_for_keyword()` join.

**Import Center card** (`/imports`) — read-only "Listing evidence (v3.4.0 lanes)" table.

**Photo Studio** — `photo_brief.build(evidence=…)` maps rival-review complaints to the slots that answer
them (material→macro/fabric, size→size chart, shipping→care, etc.). Backward compatible.

**Team Command Center** (`/team` + `/team/command-center`) — KPI strip, Today board, process pipeline,
activity timeline, module cards. Reuses tasks/activity/users/feedback data; all 10 module routes preserved.

**Team subpage polish** — My Tasks grouped (Overdue/Today/This week/Awaiting/Open/Done); Review Queue
urgency-sorted; Activity Log filter form + CSV export.

**Green-suite fix** — restored two source-string literals the selftest greps (`href="/team/feedback"`,
`href="/team/calendar"`) that a refactor removed; synced README to V37.0; dropped a stale V36 selftest clause.

---

## 2 · Batch 2 — engine bug fixes (code on PC, pending commit)

Found via a 5-keyword end-to-end test through every layer; 0 crashes, but real logic bugs:

- **`feed_evidence_router.py` — CF007 cross-product attachment.** `evidence_for_keyword("custom name
  necklace")` was matching the tote-handbag listing via the generic words "custom name". Fixed: a match now
  requires a shared SUBJECT word or the SAME product noun, and rejects conflicting products (necklace ≠ tote).
- **`keyword_lab.py` — trademark suggestions.** A trademarked seed ("disney princess shirt") emitted 8+
  build-ready infringing candidates. Fixed: screen every candidate through `trademark.check()`, drop HIGH.
- **`keyword_lab.py` — doubled-modifier junk.** `_subject` fallback didn't exclude modifiers →
  "personalized personalized name tote". Fixed.
- **`interactive.py` — Ads plan identical for every keyword.** `_price_cost_for` pulled price/conversion
  only from a live MCP call; when it was unreachable, every keyword got the same "no price on file" plan.
  Fixed: fall back to `keyword_data.csv` for avg_price + conversion_rate (honest-null on 0/blank); render
  now surfaces real price + conversion + clicks-per-sale even before a supplier cost exists.

---

## 3 · Batch 2 — Rank / Pattern / Keyword Lab / Re-rank improvements (code on PC, pending commit)

- **Rank / Opportunity Inbox** (`opportunity_inbox.py`): within a proof-tier + action, a LAUNCHABLE product
  now ranks above a non-launchable theme/broad fragment ("next 12 month" no longer outranks "indoor
  decals"). Ordering only — scores/verdicts/actions unchanged.
- **Pattern Miner** (`pattern_miner.py`): excludes the query's own tokens from top_words/leading/seed_words
  → surfaces the real differentiators (crewneck/rn/personalized) instead of "nurse 100%, sweatshirt 100%".
- **Keyword Lab** (`keyword_lab.py` + `interactive.py` + `web.py`): mode-aware material AND recombination
  modifier (no "embroidered" for POD; kept for embroidery); product taken from the keyword, not a
  pattern-derived noun (sweatshirt, not crewneck); crewneck/hoodie/tee/tote still offered as swaps. `mode`
  threaded through `generate()`.
- **Re-rank loop**: verified working — `save_candidates()` appends source=keyword-lab rows the Inbox
  re-ranks as honest WATCH. No change needed.

---

## 4 · Files changed in Batch 2 (10)
src/keyword_lab.py, src/feed_evidence_router.py, src/interactive.py, src/web.py, src/opportunity_inbox.py,
src/pattern_miner.py, tests/test_feed_evidence_router.py, tests/test_keyword_lab.py,
tests/test_pattern_miner.py, tests/test_ads_plan.py.

## 5 · Verification (all in the cloud sandbox with the real corpus)
26 router tests pass; the pattern-miner, keyword-lab, ads-plan suites pass. The real Flask app builds and
`/inbox`, `/pattern-miner`, `/keyword-lab`, `/ads-plan`, `/imports`, `/team`, `/photo-brief` all return 200.
All changed files py-compile clean. (PC/Mac `pytest` is the final gate before push.)

## 6 · Deploy Batch 2
**Windows PC (PowerShell, each line separately):**
```
cd D:\Claude\22etsy-agent
py -m pytest -q
git add src/keyword_lab.py src/feed_evidence_router.py src/interactive.py src/web.py src/opportunity_inbox.py src/pattern_miner.py tests/test_feed_evidence_router.py tests/test_keyword_lab.py tests/test_pattern_miner.py tests/test_ads_plan.py
git commit -m "V37.4 b2: evidence CF007 + trademark screen + doubled-modifier + ads-plan keyword data + Rank/Pattern/KwLab improvements"
git push origin main
```
**MacBook / VS Code (zsh):** `git clone` (or `git pull`) → extract `22etsy_v37_4_changes.zip` →
`python3 -m venv .venv && source .venv/bin/activate && pip3 install -r requirements.txt pytest markdown` →
`python3 -m pytest -q` → same `git add/commit/push`. (Full guide: `DEPLOY_macbook.md`.)
**VPS (both):** `cd ~/etsy-agent && git fetch origin && git reset --hard origin/main && sudo systemctl restart etsy-web`

---

## 7 · Open / next
1. Commit + push Batch 2, then VPS deploy.
2. Optional: `git rm src/design_analyzer.py tests/test_design_analyzer.py` (audited dead file — see
   `cleanup_inventory.json` / `removal_plan.md`).
3. **Parked (owner decision):** Promax v38 ranking-math changes — backtest on the real 1,123-keyword corpus
   said don't adopt as written (uniformly inflationary; 69% of rows have seller_count=0). See
   `v38_backtest.html`. The v38 L2 re-weight (P .15→.25) also untested/parked.
4. **Known design boundary (not a bug):** listing evidence doesn't yet lift the L4 Rank verdict (Evidence
   Router is intentionally separate from frozen L4). A single-listing → CONFIRM_FIRST L4 hook is the logical
   next enhancement — behind the freeze, needs a decision.
5. Deeper Team subpages (User Management workload, My Profile dashboard, Review "request changes").

## 8 · Guardrails upheld (unchanged all session)
PUBLISH_AUTOMATION=false · no Seller-Central connection · honest-nulls · real-photo rule · owner approval
gates · L0–L4 ranking math frozen (90-day). Nothing this session touched any of these.
