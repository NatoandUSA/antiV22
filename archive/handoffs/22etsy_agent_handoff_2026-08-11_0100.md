# 22etsy-agent — Handoff · 2026-08-11 01:00 (+07)

_Session owner: Alex (Hue, Vietnam). **Supersedes `22etsy_agent_handoff_2026-08-10_1100.md`**,
which supersedes 2026-08-08 00:15 → 2026-08-07 15:48 → 2026-08-06 02:49 → 01:45 →
2026-08-05 22:47 → 14:26 → 2026-08-04 00:16 → V37.11. Read this file first; where
they disagree, the newest wins._

Repo `D:\Claude\22etsy-agent` · GitHub `NatoandUSA/etsy-agent` · VPS `~/etsy-agent`, service `etsy-web`.
Live: https://etsy.theglobalserviceteam.site

---

## 0 · Status — 10 commits shipped, all deployed and verified live

| | |
|---|---|
| **Commit** | `e239657` — local == origin/main == VPS, verified by direct comparison each deploy, not assumed |
| **Service** | active, restart timestamp confirmed AFTER each deploy's file mtime (not just `is-active`) |
| **Tests** | full suite green every deploy this session: 0 failures, 1 pre-existing skip |
| **selftest** | ALL CHECKS PASSED, every deploy |
| `PUBLISH_AUTOMATION` | `False`, untouched |
| **Frozen files** | zero edits |
| **Working tree** | clean |

**New standing rule this session: Claude now has the owner's full authorization to commit,
push, and deploy without asking first** (2026-08-10, explicit chat instruction, saved to
memory). Verification (tests, selftest, live probe) is still mandatory every time — the
authorization is for the *action*, not a license to skip checking. See `[[deploy-runs-from-user-side]]`.

```
e239657  feat(suppliers): register HPW and HogoToPod in the tracked source registry
b4815f4  feat(suppliers): add HPW and HogoToPod price-sheet importers
4dbb8c6  fix(launch-kit): stop defaulting every bag keyword's product label to Tote Bag
019b319  fix(photo-brief): remove [X]-business-days placeholder from image prompts
b154f96  fix(launch-kit): remove title placeholders and make care copy mode-safe
c7531f9  fix(launch-kit): make bag copy and photo briefs product-appropriate
dd38073  fix(evidence-router): correct 0a8fb76 to a real 3-tier rating/review_count fallback
0a8fb76  fix(evidence-router): use jsonld_rating/review_count/availability when the DOM scrape is blank
9c7dbd9  feat(extension): track Pattern Evidence Harvester v3.6.3 — never in git before now
113e708  docs: handoff 2026-08-10 11:00 — upgrade evidence exporter to v3.4.0
```

---

## 1 · How this session actually ran

The owner is running a **parallel ChatGPT session** on this project. ChatGPT periodically
produces structured JSON "handoff" files (diagnoses, decisions, next steps), the owner pastes
them in, and says "review and proceed." **The owner gave an explicit standing protocol for
this** (2026-08-10, saved as `[[json-handoff-review-golden-rule]]`): read the whole JSON,
never treat it as guaranteed truth, verify every important claim against the real
code/data/logs before acting, trace root causes, never blind-fix, report what matched vs.
differed. That discipline is why most of this session's real fixes were found — not by
following what a JSON doc said was wrong, but by checking.

**Concretely, this paid off three times:**
1. A "2-tier jsonld fallback" fix (`0a8fb76`) that passed all its own tests was still wrong —
   only found by writing a *live* acceptance test against the actual deployed code, which
   showed tier 2 (`listing_rating`) was structurally unreachable. See §3.
2. A pasted doc's "check hero prompt against product form factor" note led to catching that
   *I* had defaulted every bag keyword to "Tote Bag" earlier the same session — a bug I
   introduced, caught by someone else's review prompt, not self-caught.
3. `seller.hogotopod.com/catalog` and two "spreadsheets" were claimed as EXACT_EVIDENCE in a
   pasted doc; the URL turned out to be an unrenderable JS shell, and nothing was imported
   from those claims until the owner supplied real, fetchable spreadsheet URLs. See §5.

---

## 2 · Evidence pipeline fixes (v3.6.3 extension verification)

Owner: "I am now using v3.6.3, make sure all the data works well with the tool."

- **`0a8fb76`**: `feed_evidence_router.normalize_listing_structure()` folded `jsonld_rating`
  into the same header lookup as `listing_rating` — `_ci()` returns the FIRST header matching
  ANY needle in file order, so the DOM column always won even when its value was blank. Fixed
  as a 2-tier `or` fallback. **This fix was itself incomplete.**
- **`dd38073`**: live acceptance-testing the "fixed" code on the VPS showed `rating`/
  `review_count` actually have THREE independent scrapes (buy-box widget, reviews-section
  regex `listing_rating` — added in v3.6.2 specifically as a DOM fallback — and v3.6.3's
  `jsonld_rating`), not two. Corrected to a real 3-tier chain. Caught by testing the deployed
  fix's actual behavior, not by re-reading the code.
- Also tracked the **Pattern Evidence Harvester v3.6.3** extension in git for the first time
  (`9c7dbd9`) — it was live in production, actively posting to `/api/import`, with zero
  version history anywhere. Reviewed for safety first (only POSTs to the project's own
  allow-listed endpoint, no marketplace write capability).
- `rank_position` (the other v3.6.3 addition) is preserved raw in capture files but nothing
  parses it into Pattern Miner's analysis yet — **left alone on purpose**, the 2026-08-07
  handoff has a standing hold on further Pattern Miner work.

---

## 3 · Launch Kit output-quality audit (the bulk of this session)

Owner pivoted priority mid-session: stop supplier/backend work, focus on
**keyword → listing → photo prompts → product page**, get the first real sale. A pasted
"priority reset" doc proposed building a whole new 5-step pipeline for this — checked first,
found it **already exists, end-to-end, as Launch Kit** (`/launch-kit?q=<keyword>`), including
Pattern Miner already wired into the tag/evidence builder. Did not rebuild it.

Instead, ran `mens carry on bag` through the real, live Launch Kit and audited the actual
output. Found a real, structural bug, not a cosmetic one:

**`c7531f9`** — every content-generation function (`_description`, `_personalization`,
`_how_to_order`, `_policies` in `launch_kit_page.py`, and all 12 slots in `photo_brief.py`)
was hardcoded to apparel regardless of actual product: "Sizes S–3XL," "garment color," "Do not
iron directly on the print," and photo prompts describing "a printed t-shirt... worn by a
smiling model," "cuff, collar," even for a **bag**. 2 of the 3 open Build Queue sprint
keywords are bags — this wasn't an edge case. Added a minimal, keyword-based `_is_bag()`
branch (not a full product-category system) across both files.

Then, working through a full audit checklist against real output (not assumption), found and
fixed three more real issues on the same keyword, each with a failing-test-first, each
verified against the actual deployed output:

- **`b154f96`** — `_title()` always appended the literal string `"Gift for [Recipient]"`,
  unconditionally, no evidence lookup at all. Now pulls a real review-derived recipient via
  `feed_evidence_router.evidence_for_keyword()` when one exists; omits the clause entirely —
  never a placeholder, never a guess — when it doesn't. Also caught, before committing (owner
  review): the POD durability replacement ("Vibrant print won't fade") was itself an
  unsupported absolute claim; softened to "Follow the care instructions to help preserve print
  quality." Embroidery's claim ("won't crack or fade") stayed — it's a near-universally true
  claim about the stitching method itself, not a per-supplier promise.
- **`019b319`** — `photo_brief.py`'s Care+processing prompt said `"Ships in [X] business
  days"` **inside the literal text an AI image generator would render as pixels** — no human
  edit step exists between that prompt and the image tool, unlike listing copy. Dropped the
  clause rather than guess a number. (Left alone, correctly: `launch_kit_page.py`'s own
  `[X] business days [confirm your real production time]` — that one IS seller-facing text
  with an edit step before publish, same pattern as the page's other bracketed fields.)
- **`4dbb8c6`** — self-caught via a doc's "check hero prompt against product form factor"
  prompt: the `c7531f9` bag-branch fix had defaulted EVERY bag keyword's product label to
  `"Tote Bag"`, unconditionally — same class of bug as the original apparel confusion, one
  level narrower. `mens carry on bag` names no bag sub-type; a tote isn't what "carry on"
  implies. `_bag_style()` now echoes a real sub-type when the keyword names one
  (`mini bride tote bags` → "Tote Bag") and falls back to neutral "Bag" — never a guess —
  when it doesn't.

**`mens carry on bag` is clean of P0/P1 issues as of this handoff.** One P2 remains, not
fixed: the title's `"Personalized Custom Gift, Custom Name"` segment is generic rather than
pulling a real evidence-backed occasion term (e.g. "Groomsmen Gift" — present in the real tag
data). Judgment call, not a bug — left for the owner.

**Also surfaced, not fixed (blocked on a real-world decision, not a code gap):** the 13-tag
list includes market-adjacent terms ("leather travel bag," "suit bag for wedding," "waterproof
duffle") whose truthfulness depends on which supplier candidate the owner ends up sourcing —
duffel, weekender, or the original tote match. Nothing to fix until that sourcing decision is
made; flagged as a pre-publish check.

---

## 4 · Sprint state — verified live, not assumed

| keyword | Launch Kit verdict | supplier candidate | published? |
|---|---|---|---|
| `mens carry on bag` | CONDITIONAL 76.4 | Duffel Bag #372, Weekender Bag #326, Matte Carryall Tote #5113 (all real Printify catalog matches, none cost-verified) | **no** |
| `mini bride tote bags` | CONDITIONAL 74.8 | none sourced | **no** |
| `embroidered sweatshirt` | WATCH 60.6 (PROVEN_WINNER niche proof, 8799 sold/$164K) | none sourced | **no** |

**Still true from the 08-07 handoff: the bottleneck is publishing, not discovery.** All three
have been open the entire time this session ran real fixes on top of them. That has not
changed tonight.

**Also still true, unresolved from earlier sessions:** none of the 3 can reach the canonical
`publish_gate()` — `product_manager.PACKAGES` only recognizes 5 hardcoded bag/pouch product
names from months ago. The V38.2 gate hardening (`real_photo_confirmed`, material/size) is
still orphaned relative to the actual live sprint. Not touched this session — it's a real
content-authoring decision (what title/tags/category to hand-curate for a 6th+ entry), not a
bug fix.

---

## 5 · Supplier data — mens carry on bag sourcing + HPW/HogoToPod import

**mens carry on bag**: ran the real `supplier pod` pull against the live Printify API. The
matcher's own scoring bug was found in the process — `_printify_matches()` drops any keyword
word `≤3` chars from scoring, silently excluding "bag" itself from "mens carry on bag." That's
why the auto-match (`Matte Carryall Tote`, 0.50 confidence) was weak. Manually searched the
full 1984-blueprint catalog and found two much better literal matches — `Duffel Bag` (#372),
`Weekender Bag` (#326) — recorded all three for comparison, per owner's choice. **The matcher
bug itself was flagged, not fixed** (separate scope, would affect every future POD pull for
any product whose defining word is ≤3 chars — bag, hat, cap, mug, tee).

**HPW + HogoToPod import** (`b4815f4`, `e239657`): owner supplied two Google Sheets URLs.
Fetched the raw CSV export (not WebFetch's AI-paraphrased summary — that gave approximate
ranges, not the exact cell values a cost import needs). Wrote real importers into
`supplier_ops.py`:
- **HPW** (26 rows, 5 products incl. Tote Bag + Quarter Zip): blank/processing cost is in
  VND, kept raw and unconverted in `notes` — no live FX rate available, and guessing one would
  silently corrupt margin math downstream. Real USD fast-line shipping used directly.
- **HogoToPod** (130 rows, 32 products incl. Dog Bandana, Gingham Tote Bag, Wreath Sash): 3
  header rows, product names forward-filled across size groups (merged cells in the source),
  mixed `$9.00`/`13,88`-style decimal separators normalized. Specialty items with no
  unbundled base cost get `shipping_cost` explicitly zeroed with a note, so nothing
  downstream double-counts a bundled fulfillment price as base+shipping.

Live supplier library: **1047 → 1202 rows.** Backed up before import.

**One real mistake, caught and corrected the same session:** registered "hogotopod" directly
on the VPS's live `data/suppliers/supplier_sources.json`, on the wrong assumption it was
gitignored `data/` bulk content. It's actually one of a handful of files under an explicit
gitignore **negation** (`!data/suppliers/supplier_sources.json`) — genuinely git-tracked. The
next `git reset --hard` correctly discarded the uncommitted edit. Not data loss (a backup
existed), but it needed to go through git to survive a deploy — redone properly as `e239657`.
**Lesson: check `git ls-files`/`git check-ignore` for a SPECIFIC file before assuming its
status from a directory-level `.gitignore` pattern.**

**Not done:** `supplier_ops.PRODUCT_FAMILIES` (the vocabulary `match()`/`feasibility_gate`
use to recognize a keyword's product type) has no entries yet for "dog bandana," "quarter
zip," "wreath sash," etc. New imported products won't score well against a matching keyword
until that's extended — deliberately tuned logic, didn't touch it without being asked.

---

## 6 · Traps hit this session (new, beyond the carried-forward list)

1. **A fix that passes its own tests can still be wrong** — the 2-tier jsonld fallback
   (`0a8fb76`) had full test coverage and was still broken; only a live acceptance test against
   the *deployed* behavior caught it. "Tests pass" and "the code is correct" are not the same
   claim.
2. **`is-active` proved nothing about a restart, twice** — one SSH restart command timed out
   silently; the fix was caught only by comparing `ActiveEnterTimestamp` against the changed
   file's mtime, not by trusting the next command's success. Do this every deploy, not just
   when something looks wrong.
3. **A directory-level `.gitignore` pattern can have file-level exceptions** — `data/*` is
   ignored, but `!data/suppliers/supplier_sources.json` isn't. Checking `git ls-files` for the
   *specific* file, not inferring from the folder pattern, is the only reliable check.
4. **WebFetch summarizes; it doesn't transcribe.** For the two Google Sheets, WebFetch gave a
   fluent but approximate paraphrase ("$7–$13," "130,000–150,000 VND"). The raw
   `/export?format=csv` URL gave exact cell values. Anything feeding a real cost/decision
   number needs the raw fetch, not the AI summary of it.
5. **A supplier's own product name can be an unverified claim if pasted straight into buyer
   copy.** "Tote Bag" as a generic default was exactly as wrong as "T-Shirt" had been —
   introduced by me, in the same session, fixing the first version of that exact bug.
6. **An image-generation prompt has no human-edit step the way listing copy does.** A bracket
   placeholder that's fine in seller-facing description text (there's a "DELETE this line
   before publishing" step) is a real bug in a prompt meant to go straight to an AI image
   tool — it gets rendered as literal pixels instead of caught.

---

## 7 · How the owner wants this work run (unchanged, carried forward + this session's addition)

**Do not blind fix — check the code, check the process, verify claims against the actual
codebase and live data before building anything on top of them, including claims from a
pasted "handoff" doc, even one framed as evidence.** Show measurements, not assertions. Prefer
the smallest safe change over a broad one, especially on files/data with a known history of
loss bugs.

**New this session:** commit/push/deploy no longer needs pre-approval — verification still
does.

**English-only output · never auto-publish a listing · `PUBLISH_AUTOMATION` stays False · no
Etsy API/OAuth/publish automation · frozen L0–L4 files are frozen.**

---

## 8 · Open items for next session

1. **All 3 sprint keywords are still unpublished.** This is the actual constraint — everything
   else this session was infrastructure quality, not throughput.
2. **`mens carry on bag`'s P2** (generic title segment) — optional, owner's call.
3. **The tag-truthfulness question** (leather/waterproof/suit-bag terms) — blocked on which
   supplier candidate actually gets sourced.
4. **`PRODUCT_FAMILIES` vocabulary** doesn't recognize any of the newly-imported HPW/HogoToPod
   specialty products yet.
5. **The Printify matcher's `≤3`-char word-exclusion bug** — flagged, not fixed, affects every
   future POD pull for a product whose defining word is short.
6. **`product_manager.PACKAGES`** still only has 5 hardcoded names; none of the 3 sprint
   keywords (or the newly-imported dog bandana/quarter zip/tote candidates) can reach the
   canonical `publish_gate()` without a real content-authoring decision to add an entry.
7. **The "embroidered dog bandana next candidate" proposal** was based on a doc's claims that
   turned out to be only partially verifiable — the HogoToPod catalog URL itself is
   unrenderable to this tool. Real cost data for it now exists (this session's import), but the
   decision to pursue it as the next Launch Kit candidate was never actually confirmed.
