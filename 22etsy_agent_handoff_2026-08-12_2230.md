# 22etsy-agent — Handoff · 2026-08-12 22:30 (+07)

_Session owner: Alex (Hue, Vietnam). **Supersedes `22etsy_agent_handoff_2026-08-12_0015.md`**,
which supersedes 2026-08-11 16:17 → 01:00 → 2026-08-10 11:00 → 2026-08-08 00:15 → 2026-08-07 15:48
→ 2026-08-06 02:49 → 01:45 → 2026-08-05 22:47 → 14:26 → 2026-08-04 00:16 → V37.11. Read this file
first; where they disagree, the newest wins._

Repo `D:\Claude\22etsy-agent` · GitHub `NatoandUSA/etsy-agent` · VPS `~/etsy-agent`, service `etsy-web`.
Live: https://etsy.theglobalserviceteam.site

---

## 0 · Status — Patch 4 (Phase B + Stage 2) shipped, deployed, verified live

| | |
|---|---|
| **Commit** | `cbdaa5e` — local == origin/main == VPS, verified by direct `git rev-parse` comparison on all three, not assumed |
| **Service** | active, restart timestamp (22:18:51) confirmed AFTER the deployed commit landed |
| **Tests** | local full suite green (exit 0) + VPS full suite green (exit 0) + `compileall` clean on both + `py main.py selftest` all-pass |
| **Live acceptance** | real Flask test-client hit on `/inbox?mode=pod` and `/inbox?mode=pod&exec=changed` (200, new column + filter link present, unmocked); plain HTTP probe on the live domain (`/login` 200, `/inbox` 302 auth-gated as expected) |
| `PUBLISH_AUTOMATION` | untouched |
| **Frozen files** (`ranking_engine`, `opportunity_score`, `product_fit`, `etsy_proof`, `opportunity_inbox`) | zero diff (`git diff --stat` confirmed) — new code reads from them, same as every other consumer module |
| **Working tree** | clean after this doc's commit |

**Standing rules carried forward, unchanged:** Claude has the owner's full authorization to
commit, push, and deploy without asking first (2026-08-10). Verification (tests, live probe) is
still mandatory every time. See `[[deploy-runs-from-user-side]]`.

---

## 1 · How this session ran

Three pasted ChatGPT JSON docs today (best-learning-selection review → Phase B authorization →
Stage 2 build decision), each checked against the real codebase before acting — see
`[[json-handoff-review-golden-rule]]`. Unlike a pure "catch a wrong claim" pass, this session's
verification work directly shaped two real engineering decisions:

1. **Verified the doc's proposed architecture gaps were real, not invented**, before agreeing
   Phase B was the right next step: grepped `src/` for `decision_record`, `Product Truth`,
   `evidence_ref`, `content_hash`, `quarantine`, `execution_action`, `MINE_NICHE` — none existed.
   Confirmed `data_store.py`, `listing_factory.py`, `photo_brief.py`, `design_skill_bridge.py`,
   `harvest.py`, `ytx_import.py` are all real files. This is what let the Phase B recommendation
   be a genuine "yes, do this" rather than trusting the doc's own self-assessment.
2. **Verified "proof_type NONE on all 200 audited rows" was a real data fact, not a plumbing
   bug**, before building Stage 2's proof-capping logic on top of it. Stage 2's own doc explicitly
   flagged this as suspicious and asked for verification first. Checked directly: the live
   `etsy_proof.build_proof()` map (the SAME function `opportunity_inbox` calls) currently holds
   exactly **2 canonical proof phrases**, matching **0 of 2,289** ranked keywords across both
   pod/embroidery modes — not just the 200 audited. The "819 listings" figure from an earlier
   handoff (`sources.proof_listings`) is real for its own point in time; proof capture data is
   time-sensitive (captures/ledger rotate), so it has genuinely shrunk since then. This wasn't a
   bug to fix — it's why Stage 2's v1 rule caps market-score-only `BUILD_NOW` to `CONFIRM_FIRST`
   by default, and it's the reason "re-harvest fresh proof" is now the top open item (§6).
3. **Caught 2 real bugs on my own review before shipping, not after**: `sig({...}[c])` called a
   dict as if it were callable — a `TypeError` waiting to happen, caught reading my own diff
   before ever running it. A reason code (`SPECIFIC_HOBBY_INTEREST`) was reused for both "this
   motif made the row specific" AND "this motif alone was insufficient," so it showed up on
   `BROAD_PARENT` rows looking self-contradictory — renamed the insufficient-alone case to
   `MOTIF_ONLY`. Also found "ask ring bearer" scored zero signal even though `ring bearer` is the
   same wedding-party-role category already covered (`bridesmaid`, `groomsman`) — added it.

**New incident this session — SEC-001 (informational, resolved):** while grepping `.env` broadly
to locate VPS deploy details, a live Printify API token was echoed into this Claude Code session's
tool output/transcript. It was never committed, pushed, or logged anywhere outside that one
session. Flagged to the owner immediately; **the owner rotated the token same session** (added a
new one via the IDE). Going forward: prefer targeted key lookups (`grep -o 'VAR=.*' .env | cut`)
or the deploy docs (`DEPLOY_VPS.md` already documents the SSH/deploy commands) over a broad
`.env` grep, so a secret value never has to pass through a tool result to answer a "where's the
server" question.

---

## 2 · What shipped

**Phase B — Patch 4 read-only actionability audit.** Read-only, zero code/schema/API changes.
Audited the top 100 pod + 100 embroidery `BUILD_NOW`/`CONFIRM_FIRST` rows (200 total) with a
word-list specificity heuristic, kept `engine_final_action` untouched throughout. Found: **98/200
(49%) disagreed** with the engine's own action — mostly broad-parent terms (`funny mug`, `company
tote`) sitting in `CONFIRM_FIRST` with no real buyer angle. Caught and fixed a substring-matching
bug mid-audit (`"rn"` false-matching inside `"newborn"`, `"cat"` inside `"dedication"`, `"cool"`
inside `"cooler"`) before publishing results. Delivered as an interactive sortable/filterable HTML
artifact ("Actionability Ledger") for owner review.

**Patch 4 Stage 2 — actionability overlay, shadow mode (`cbdaa5e`).** New `src/execution_action.py`
+ `src/execution_action_vocab.py`: a pure, deterministic function
(`derive_execution_action(row, mode)`) outside frozen L0-L4 that proposes an `execution_action`
(`BUILD_NOW` / `CONFIRM_FIRST` / `MINE_NICHE` / `REVIEW_ACTIONABILITY`) using a two-axis
specificity model — a STRONG signal (profession/role, occasion, use-case) or a validated
combination of two MEDIUM signals (audience, personalization, motif, generic-gift) is required;
personalization alone, a bare product subtype alone, or a generic audience word alone is no longer
sufficient (tightened from Phase B's looser v0 heuristic, per the owner-approved v1 rule). Proof
handling: a `BUILD_NOW` resting on market score alone (no `EXACT` proof) is capped to
`CONFIRM_FIRST` for this v1, since proof coverage is currently near-empty (§1.2) — `EXACT`-proof
`BUILD_NOW` rows are left alone, and `BLOCKED`/`SKIP` rows are never touched or upgraded. 20 new
tests (`tests/test_execution_action.py`) cover the tokenization regressions, every doc-specified
broad/specific/proof example, and purity (row never mutated).

**Wired live in shadow mode** (`/inbox`): a new **Execution (shadow, Patch 4)** column next to
Final action, computed only for `BUILD_NOW`/`CONFIRM_FIRST` rows (the only slice this was
audited/tested against — `WATCH`/`REVIEW`/`BLOCKED`/`SKIP` rows are left alone entirely, not just
"unchanged by the overlay" but never passed to it), plus a `?exec=changed` filter link. Nothing is
re-sorted; `Final action`, `route`, and every existing CTA (Build/Pattern-Miner/Confirm links)
are still driven by the engine alone. On the live pod queue right now: **137/200 top-slice rows
propose Mine Niche** (68% — stricter than Phase B's 49%, as expected from the tightened v1 rule).

---

## 3 · Sprint state — freshness recovery + Patch 4 actionability

| Item | Status |
|---|---|
| Homepage rename + honest "new today" | Shipped (`24a7eb6`, prior session) |
| Patch 1 — Enrichment drain + observability | Shipped (prior session) |
| Patch 3 — Rank snapshots + homepage truthfulness | Shipped (prior session) |
| **Patch 4 Phase B — read-only actionability audit** | **Shipped this session** |
| **Patch 4 Stage 2 — execution_action overlay, shadow mode** | **Shipped this session, live in `/inbox`** |
| Patch 4 — MINE_NICHE CTA (real child-niche search, not fabricated) | **Not started.** Doc's own `mine_niche_behavior` spec: search existing master/Keyword Lab evidence for real children first; if none exist, mark `NEEDS_NICHE_RESEARCH` rather than inventing metrics. Deliberately deferred — larger scope than the display-only shadow mode shipped this session. |
| Patch 4 — operator default queue uses `execution_action` | **Not started, intentionally.** Acceptance gate (per the authorizing doc) wants the shadow-mode display reviewed in practice first. |
| Phases C–G (decision_record, Product Truth versioning, conflict/quarantine, golden regression) | **Not started, deliberately parked** pending review of how Stage 2 looks in practice — matches both this session's authorization and global CLAUDE.md's "ask before large/speculative work" rule. |
| Patch 2 — seed frontier / discovery expansion | **Not started.** Untouched this session; still flagged for API-cost implications before building (global CLAUDE.md rule). |

---

## 4 · How the owner wants this work run (unchanged, carried forward)

**Do not blind fix — check the code, check the process, verify claims against the actual
codebase and live data before building anything on top of them, including claims from a pasted
"handoff" doc, even one framed as evidence.** Show measurements, not assertions. Prefer the
smallest safe change over a broad one. This session's proof-plumbing check (§1.2) is the clearest
example yet of this rule catching something that mattered — if the module had been built assuming
"NONE means broken," the conservative proof-cap logic would have been designed around a wrong
premise.

**Commit/push/deploy no longer needs pre-approval — verification still does. Every commit this
session:** local full suite green, VPS full suite green, service restarted, restart timestamp
checked against the deploy, live probe (a real Flask test-client hit beats a plain HTTP probe
alone, used together here).

**English-only output · never auto-publish a listing · `PUBLISH_AUTOMATION` stays False · no
Etsy/Printify API automation that takes account actions (read-only catalog lookups are fine) ·
frozen L0–L4 files are frozen (scoring/weights, not read access) · ranking logic untouched unless
explicitly asked.**

---

## 5 · Open items for next session

1. **Re-harvest fresh Etsy proof — the highest-value next move, not automatable by Claude.** The
   proof map is down to 2 canonical phrases matching nothing in the ranked data (§1.2), which is
   what's capping legitimate `BUILD_NOW` rows to `CONFIRM_FIRST` under Stage 2's conservative v1
   rule. Needs a fresh Alura/EverBee product-research CSV export, or a fresh Etsy Spy browser
   capture — both manual/owner-side per the standing no-direct-Etsy-automation rule. Once a fresh
   export lands, re-check `etsy_proof.build_proof()` coverage and re-run the Stage 2 diff to see
   how many `NO_EXACT_OR_GROUP_PROOF`-capped rows actually had real backing.
2. **Watch the shadow-mode disagreement rate over the next few days** as real usage/data changes
   it — does the 68% Mine-Niche-proposal rate on the pod queue hold, or was today's snapshot
   unusually broad-heavy? No action needed yet, just worth tracking before any decision to move
   `execution_action` into the default queue sort.
3. **Decide on the MINE_NICHE CTA build** (real child-niche search vs. `NEEDS_NICHE_RESEARCH`
   flag) — separate, larger scope than what shipped this session, deliberately not started.
4. **Decide Patch 2 (seed frontier) scope and API-cost tolerance**, or confirm it stays deferred —
   unchanged from prior handoffs, still untouched.
5. **`mens carry on bag` Duffel #372** — still waiting on the owner's Printify dashboard session
   (dimensions/cost/processing-time) and real sample photos. Untouched this session, not a
   blocker, deliberately parked. (Note: this keyword is currently the #1 ranked pod row and one of
   only 2 `BUILD_NOW`s resting on market score alone with no proof — a strong first candidate once
   fresh proof data lands, per item 1.)
6. **SEC-001, closed** — Printify token echoed into a session transcript during a `.env` grep,
   never committed/logged elsewhere, owner rotated same session. No further action; noted here so
   future sessions know the old token in any older transcript is dead.
7. **Prior open items, still open, not touched this session:** the Printify matcher's `≤3`-char
   word-exclusion bug; `PRODUCT_FAMILIES` vocabulary for HPW/HogoToPod; `product_manager.PACKAGES`
   (confirmed disconnected from the live sprint flow, no action needed unless the owner wants that
   separate feature worked on).
