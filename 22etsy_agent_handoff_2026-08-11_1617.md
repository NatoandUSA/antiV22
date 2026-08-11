# 22etsy-agent — Handoff · 2026-08-11 16:17 (+07)

_Session owner: Alex (Hue, Vietnam). **Supersedes `22etsy_agent_handoff_2026-08-11_0100.md`**,
which supersedes 2026-08-10 11:00 → 2026-08-08 00:15 → 2026-08-07 15:48 → 2026-08-06 02:49 →
01:45 → 2026-08-05 22:47 → 14:26 → 2026-08-04 00:16 → V37.11. Read this file first; where
they disagree, the newest wins._

Repo `D:\Claude\22etsy-agent` · GitHub `NatoandUSA/etsy-agent` · VPS `~/etsy-agent`, service `etsy-web`.
Live: https://etsy.theglobalserviceteam.site

---

## 0 · Status — 1 commit shipped this session, deployed and verified live

| | |
|---|---|
| **Commit** | `a09c2ca` — local == origin/main == VPS, verified by direct comparison, not assumed |
| **Service** | active, restart timestamp (16:02:02) confirmed AFTER the deployed file's mtime (15:32:11) |
| **Tests** | local full suite green (exit 0) + VPS full suite green (exit 0), 1 pre-existing skip |
| **selftest** | ALL CHECKS PASSED, both local and VPS |
| **Live acceptance** | called the deployed `launch_kit_page.build()` directly on the VPS — output matches local exactly |
| `PUBLISH_AUTOMATION` | `False`, untouched |
| **Frozen files** | zero edits |
| **Ranking logic** | zero edits (opportunity_score.py, ranking_engine.py, workspace.py untouched) |
| **Working tree** | clean |

**Standing rules carried forward, unchanged:** Claude has the owner's full authorization to
commit, push, and deploy without asking first (2026-08-10). Verification (tests, selftest,
live probe) is still mandatory every time. See `[[deploy-runs-from-user-side]]`.

---

## 1 · How this session ran — the golden rule did real work again

The owner ran a parallel ChatGPT session producing a rapid sequence of JSON "handoff/decision"
docs (7 pasted this session), each reviewed against real code/data before acting — never
executed blind. See `[[json-handoff-review-golden-rule]]`. **Concretely, this is what the
discipline caught this session:**

1. **The single biggest catch:** a JSON plan ("LEAN_PUBLISH_FIRST") assumed the sprint
   bottleneck was that `mens carry on bag` couldn't reach "the canonical `publish_gate()`"
   without adding an entry to `product_manager.PACKAGES`. Traced the actual code instead of
   accepting it: `launch_kit_page.py` has **zero** references to `product_manager` anywhere.
   `/launch-kit` and `/launch-kit/submit` are fully keyword-generic — no PACKAGES lookup in
   that path at all. `product_manager.PACKAGES`/`listing_package()`/`publish_gate()` only feeds
   an unrelated, separate feature: the daily "Etsy Product Manager AI" batch report
   (`run_manager()`, 5 hardcoded evergreen names), called only from `allreports.py`. There are
   in fact **two different functions named `publish_gate()`** in this codebase
   (`product_manager.py`'s dict-based one, and `workspace.py`'s keyword-based one used by
   `strict_verdict`/`launch_readiness`) — neither requires PACKAGES membership. **Net result:
   zero code work was actually needed for "Phase A."** The keyword already had a live
   CONDITIONAL 76.4 Launch Kit verdict before this session started — proof it was already
   reaching the real gate. Reported this back instead of building the (unnecessary) PACKAGES
   entry a pasted doc assumed was required.
2. **A tag-truthfulness cleanup list was incomplete.** A JSON doc listed 4 unsupported tags to
   remove for the chosen Duffel #372 product (`leather travel bag`, `waterproof duffle`,
   `suit bag for wedding`, `shoe compartment bag`). Re-ran the actual live tag generator
   (`interactive.tags_with_sources`) instead of trusting the list and found **3 more** with the
   identical garment/suit-bag framing problem: `groomsmen suit bag`, `mens suit travel bag`,
   `garment duffle bag`. Real removal count was 7, not 4 — meaningfully more replacement-tag
   research than the doc implied.
3. **A "personalization feasibility unconfirmed" flag was resolved with real data instead of
   left open.** A later JSON QA doc correctly flagged that the shop's generic personalization
   claim didn't by itself prove Duffel #372 specifically could be customized. Pulled Printify's
   real print-provider/variant data (`/catalog/blueprints/372/print_providers/10/variants.json`)
   and found genuine dye-sublimation print placeholders on **both** size variants (front + both
   sides, real pixel dimensions) — upgrading `custom duffel bag` from conditional to confirmed,
   rather than leaving it blocked on a question the API could actually answer.
4. **A follow-up plan claimed dimensions/cost/processing-time could be "gathered in parallel"**
   as if they were three separate research tasks. Pulled the raw JSON for all three relevant
   Printify endpoints (blueprint, variants, print-provider) and confirmed **none** of the three
   fields exist anywhere in the public catalog API — all three only surface in Printify's own
   account dashboard once the product is drafted into a store. Corrected the plan: it's one
   owner action (open Printify, add Duffel #372 as a draft), not three lookups.
5. **Two duplicate JSON uploads were caught and skipped**, not silently re-processed — same
   filename pattern, byte-identical content, already-completed work. Flagged as duplicates
   instead of burning a cycle re-deriving the same output.

---

## 2 · Sprint keyword state — `mens carry on bag`

**Product locked:** Printify **Duffel Bag #372**, provider **MWW On Demand**, material
**100% polyester Oxford canvas**, 2 real size variants (Small/Large), decoration method
**dye-sublimation**, US shipping **$10.09 first item / $2.39 additional** (confirmed via live
Printify catalog API, not estimated).

**Real print-area data (pixels, not inches — see §3):**

| Variant | Front | Left side | Right side |
|---|---|---|---|
| Small | 3075×4875 | 1650×1650 | 1650×1650 |
| Large | 3675×5775 | 1920×1920 | 1920×1920 |

**Why Duffel #372 over the other two candidates found last session:** most literal semantic
match to "mens carry on bag," real size options, no brand-name entanglement. Weekender Bag #326
was rejected — Printify's own copy calls it a beach "Weekender Tote" with rope handles (wrong
audience/form-factor for a men's carry-on) and it has only 1 variant. Matte Carryall Tote #5113
was rejected — branded "Port Authority" SKU, and its US shipping cost was never retrievable
(the shipping API returned nothing usable for provider "Fulfill Engine").

**Tags — locked, deployed, live.** Final 13, all trademark-clear, all ≤20 chars:

`mens carry on bag, father's day gift, graduation gift men, carry on flight bag, gym duffel
bag, carry on bag, travel bag, mens canvas bag, groomsmen duffel bag, duffel bag for men, mens
carry bag, mens carry gift, custom duffel bag`

7 tags removed as unsupported by the real product (not by the pasted doc's shorter list — see
§1.2): `leather travel bag`, `waterproof duffle`, `suit bag for wedding`, `shoe compartment
bag`, `groomsmen suit bag`, `mens suit travel bag`, `garment duffle bag`.

**How the tags were integrated (`a09c2ca`):** inspected the contract first — the shared
evidence-backed tag path is `interactive.tags_with_sources()`, consumed by the Launch Kit HTML
page, the markdown kit, the manager-review submit summary, and the Ads plan. No existing
per-keyword override mechanism existed. Added a small `_VERIFIED_TAGS` dict, keyed by lowercased
keyword, that feeds into the **same** `add()` helper the live cascade already uses — same
trademark/length/dedup checks, same `{tag, source, why, count}` return shape, same 5-value
source vocabulary the rendering layer (`launch_kit_page._TAG_SRC`) already understands. Nothing
was hardcoded into rendering logic; every other keyword still runs the normal live discovery
cascade untouched (spot-checked 4 unrelated keywords post-deploy — all generated normally).

**Regression checklist run and passed:** exactly 13 tags · every tag ≤20 chars · all 13 render
in the actual generated Launch Kit page · none of the 7 rejected tags remain · `custom duffel
bag` present · no leather/waterproof/suit-bag/shoe-compartment leakage · unrelated keywords
unaffected. Full local + VPS pytest green, selftest ALL CHECKS PASSED on both, restart-timestamp
freshness confirmed, live acceptance confirmed against the deployed function.

**Owner's instruction: tag layer is now frozen.** No further tag optimization unless new
evidence appears.

---

## 3 · Remaining owner checks — none are Claude-executable, verified by API inspection

Confirmed by pulling the raw JSON for all three relevant Printify endpoints directly (not
inferred):

- `/catalog/blueprints/372.json` → fields are only `id, title, description, brand, model,
  images`. **No dimension field anywhere**, in inches or otherwise.
- `/catalog/blueprints/372/print_providers/10/variants.json` → fields are only `id, title,
  options, placeholders, decoration_methods`. **No price/cost field.**
- `/catalog/print_providers/10.json` → fields are `id, title, location` (Hendersonville, NC —
  confirmed US-based) and a blueprint list. **No production/processing-time field.**

**None of dimensions, base cost, or processing time are reachable through this codebase's
Printify integration.** All three only exist in Printify's own account dashboard, and only
appear once Duffel #372 is added there as a draft product — that's one owner action that
surfaces all three together, not three separate lookups.

**Open items, all owner-side (not automatable per the standing no-marketplace/supplier-account-
automation rule):**
1. Open Printify, add Duffel Bag #372 as a draft product → capture exact Small/Large
   dimensions, exact Small/Large base cost, currency, whether Printify Premium pricing applies,
   and MWW On Demand's stated processing/production time.
2. Order/shoot real product or customized sample photos — separate, physical-world action, can
   run in parallel with #1, may take longer. AI mockups remain planning-only evidence.

**Owner chose to wait** rather than have Claude draft placeholder content ahead of real numbers
this round — no listing-content work is in flight right now.

---

## 4 · What happens after the owner returns with data (agreed sequence, not yet started)

1. Record exact values with source/provenance — no invented numbers.
2. Update seller-facing size/material/processing/cost fields only where the real contract
   expects them.
3. Run final title/tag/description/personalization/photo-prompt truthfulness QA against the
   real numbers (esp. design placement vs. the real print-area pixel dimensions above).
4. Run the real Launch Kit publish-readiness path (`/launch-kit` + `workspace.publish_gate()` —
   **not** `product_manager.PACKAGES`, see §1.1).
5. Resolve only the blockers the gate actually reports.
6. Manually publish on Etsy. Record `PUBLISHED_MANUALLY` + timestamp.
7. Day-3 and Day-7 learning review (real data: impressions/clicks/favorites/orders/revenue,
   decision, kill_reason, one next variable to test).

**Freeze rules still in force, unchanged from the owner's LEAN_PUBLISH_FIRST decision:** no L5
niche taxonomy, no 8-keyword batch QA campaign, no generalized PACKAGES/publish-gate
architecture rewrite — none of it until this one listing is actually through the real gate and
Day-7 evidence says otherwise. No auto-publish, ever.

---

## 5 · Traps hit this session (new)

1. **A pasted doc's own premise can be wrong at the architecture level, not just on a data
   fact.** The PACKAGES/publish_gate confusion (§1.1) wasn't a wrong number — it was a wrong
   model of which code path the sprint keyword actually runs through. Only caught by tracing
   real imports/callers (`grep` for every consumer of `publish_gate` and `PACKAGES`), not by
   re-reading the doc more carefully.
2. **A truthfulness-cleanup list can be right in kind but incomplete in count.** Trusting "4
   tags to remove" without re-running the live generator would have shipped 3 more unsupported
   claims (`groomsmen suit bag`, `mens suit travel bag`, `garment duffle bag`).
3. **"Missing data" isn't always still missing — check before deferring.** The personalization-
   feasibility question in §1.3 could have been left as an open owner-check indefinitely; a
   direct API call answered it in one request.
4. **"Can be gathered" doesn't mean "is available via this integration."** Confirmed by reading
   raw endpoint JSON, not by assuming the tool's existing wrapper (`printify.py`) was just
   missing a convenience function — the underlying Printify catalog API genuinely does not
   expose dimensions, cost, or processing time at all.
5. **Duplicate uploads should be named as duplicates, not silently re-executed** — two
   byte-identical JSON re-pastes this session were caught by comparing content, not filename.

---

## 6 · How the owner wants this work run (unchanged, carried forward)

**Do not blind fix — check the code, check the process, verify claims against the actual
codebase and live data before building anything on top of them, including claims from a pasted
"handoff" doc, even one framed as evidence, even when it's ChatGPT reviewing Claude's own prior
output.** Show measurements, not assertions. Prefer the smallest safe change over a broad one.

**Commit/push/deploy no longer needs pre-approval — verification still does.**

**English-only output · never auto-publish a listing · `PUBLISH_AUTOMATION` stays False · no
Etsy/Printify API automation that takes account actions (read-only catalog lookups are fine) ·
frozen L0–L4 files are frozen · ranking logic untouched unless explicitly asked.**

---

## 7 · Open items for next session

1. **Owner check data** — dimensions, base cost, processing time (one Printify dashboard
   session) and real sample photos (separate, physical) are the only remaining blockers to
   Launch Kit content finalization for `mens carry on bag`.
2. **`mini bride tote bags`** (CONDITIONAL 74.8) and **`embroidered sweatshirt`** (WATCH 60.6)
   — both still open, both unactioned this session; per LEAN_PUBLISH_FIRST, intentionally not
   touched until `mens carry on bag` is through the real gate.
3. **The Printify matcher's `≤3`-char word-exclusion bug** (from 2026-08-11 01:00 handoff,
   §5) — still flagged, not fixed, affects every future POD pull for a short-word product.
4. **`PRODUCT_FAMILIES` vocabulary** for HPW/HogoToPod specialty products — still not extended,
   not touched this session.
5. **`product_manager.PACKAGES`/`run_manager()`** — confirmed disconnected from the live sprint
   flow (§1.1). No action needed unless the owner specifically wants the daily batch-report
   feature itself worked on — that is a genuinely separate feature, not a sprint blocker.
