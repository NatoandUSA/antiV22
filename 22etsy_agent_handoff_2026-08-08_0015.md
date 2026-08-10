# 22etsy-agent — Handoff · 2026-08-08 00:15 (+07)

_Session owner: Alex (Hue, Vietnam). **Supersedes `22etsy_agent_handoff_2026-08-07_1548.md`**,
which supersedes 2026-08-06 02:49 → 01:45 → 2026-08-05 22:47 → 14:26 → 2026-08-04 00:16 → V37.11.
Read this file first; where they disagree, the newest wins._

Repo `D:\Claude\22etsy-agent` · GitHub `NatoandUSA/etsy-agent` · VPS `~/etsy-agent`, service `etsy-web`.
Live: https://etsy.theglobalserviceteam.site

---

## 0 · Status — shipped and LIVE, but this was NOT a launch-sprint session

| | |
|---|---|
| **Commit** | `35aa43e` "V38.2: tighten publish gate and supplier detail readiness" |
| **Deployed** | local == origin == VPS (`git rev-parse HEAD` on the VPS matches `35aa43e` exactly) |
| **VPS selftest** | `.venv/bin/python main.py selftest` → **ALL CHECKS PASSED - install is healthy** |
| **VPS tests** | `.venv/bin/python -m pytest tests/test_units.py -q` → green |
| **Local tests** | 3 full-suite runs this session, all exit 0, dots only + the one pre-existing skip, zero F/E |
| **Live site** | probed directly (WebFetch, not just told) — normal login page, not 502 |
| **Frozen files** | `ranking_engine.py`, `opportunity_score.py` — zero edits, not in this diff |
| `PUBLISH_AUTOMATION` | `False` (defined `src/team_ops.py`, untouched) |
| **Working tree** | clean except the 4 untracked exporter items — still never inspected, still not committed |

**Important scope note:** this session did **not** touch the 3-listing launch sprint, Build
Queue, the cron/harvest pipeline, or Pattern Miner. The previous handoff's §2/§7 (sprint
progress, `embroidered sweatshirt` queue bug, tomorrow's cron check) is **unverified** as of
this handoff — re-check it before assuming anything there is still accurate.

```
35aa43e  V38.2: tighten publish gate and supplier detail readiness
3614e7c  docs: handoff 2026-08-07 15:48 — supersedes 2026-08-06 02:49
5edfbb6  feat(build-queue): PUBLISHED_MANUALLY + day 3/7 review
6f23072  fix(harvest): preserve fractional views in keyword master
```

---

## 1 · What this session actually was

The owner pasted a large third-party bundle — "Global Ecom Academy PROMAX V3" (35-module
Etsy/Amazon curriculum, source registry, guru-vs-official cross-check, video audit) plus a
"V38.2 Launch Coach Overlay" JSON handoff claiming to know exactly how to wire it into
22etsy. Task: figure out what's **actually** learnable/usable from it, not just summarize it.

**Verdict on the doc bundle:** mostly a training-course scaffold with a video library that's
42/48 transcript-blocked (i.e. mostly a channel list with a risk score, not analyzed content).
A few genuinely useful, dated, sourced facts came out of it (Etsy's 2026 title guidance,
fee-stack completeness, production-partner disclosure, physical-sew-out-before-scale) — see
the conversation for the full read. **Two of three initially-suspected gaps turned out to
already be correctly implemented** (the Etsy fee stack in `profit.py`, the title-length/
stuffing rules in `validators.py`) — did not touch either, since they weren't broken.

**The JSON handoff's specific architecture claim was wrong** — it assumed `/launch-kit`
builds the `publish_gate()` candidate directly. It doesn't. See §3.

---

## 2 · What shipped (commit `35aa43e`)

1. **`real_photo_confirmed` evidence gate** (`src/publish_gate.py`) — closes a real gap: the
   codebase repeatedly warns everywhere else (`interactive.py`, `photo_brief.py`,
   `launch_kit_page.py`) that an AI mockup must never be published as the real photo, but the
   canonical gate never actually checked it. A listing could hit `PUBLISH_READY` with zero
   real photos confirmed. Now blocked until a human sets `real_photo_confirmed: yes`.
2. **Title promotional/price-spam check** (`src/validators.py`) — `TITLE_SPAM_TERMS` catches
   "% off", "free shipping", "clearance", "best seller", etc. in a title (against Etsy policy
   and the 2026 title guidance). The existing length/stuffing/product-noun rules were already
   correct; this was the one real gap.
3. **Dated fee-model citation** (`src/profit.py`) — comment only, no rate changed. Cites the
   Etsy fees page and a 2026-08-06 verified-through date so a future session knows when to
   re-check the hardcoded rates instead of trusting them silently forever.
4. **Fixed a pre-existing bug that made `PUBLISH_READY` unreachable** — `listing_package()`'s
   description builder hardcoded `material = "NEED_SUPPLIER_DETAILS (material & size from
   supplier page)"` **unconditionally**, regardless of what `supplier_products.csv` actually
   had on file. `sup_rec`/`sup_status` were also computed *after* the description was already
   built, so the real record was never even in scope. Now: `material`, `available_sizes`
   (shown as "Size:"), and `product_name_from_supplier` (shown as "Product:", only when
   present) come from the real saved record; `NEED_SUPPLIER_DETAILS` only appears for a field
   that is genuinely still blank. Confirmed via a real `listing_package()` call:
   `PUBLISH_READY` is now actually reachable for a fully-evidenced candidate — it never was
   before this fix, for any candidate, ever.

**Deliberately not changed:** `processing_time` in the description still reads from the
separate `sup` cost-dict argument (not `sup_rec`) — a different, pre-existing data source, not
one of the four fields asked for. Left alone.

**Deliberately not added:** the supplier catalog URL (`product_url`) is **not** embedded in
the customer-facing description, even though it was one of the four fields named. It's
already correctly surfaced separately as `supplier_product_name`, `wait — supplier_product_url`
in the internal package dict (for manager use). Putting the raw Printify/supplier link into
public Etsy copy would leak the sourcing to buyers and competitors — flagged this instead of
doing it silently.

---

## 3 · Architecture finding: `publish_gate.py` is CLI/report-only

`src/publish_gate.py`'s canonical gate is called from exactly one place in production:
`product_manager.py: listing_package()`, which runs from a CLI command and writes markdown
reports to `reports/`. **It is never called from the live web app.** `/launch-kit`
(`launch_kit_page.py`) is a fully separate system — free-text keywords, its own hardcoded
static checklist (the old "③ Real photos" row was literally `False` in the source,
permanently, regardless of reality), no supplier-CSV linkage, no `publish_gate()` call
anywhere in it.

Given this, and asked directly, the owner chose: **CSV field only, no new web UI** — same
mechanism `manual_review` and `seller_original_design_confirmed` already use (owner
hand-edits `supplier_products.csv`; there is no web form for any of these three fields).
`real_photo_confirmed` was added to `supplier_pull.py`'s `FIELDS` schema and flows into
`listing_package()`'s candidate dict exactly like `manual_review` does.

**Do not build a `/launch-kit` checkbox assuming it reaches `publish_gate()` — it currently
cannot, without separately wiring `launch_kit_page.py` to the supplier-CSV + `listing_package`
system, which nobody has asked for and which uses an incompatible keying scheme** (fixed
5-name `PACKAGES` dict vs. arbitrary free-text keywords).

---

## 4 · Tests added (all against the real `listing_package()` path, not hand-built dicts)

In `tests/test_units.py`:
- `test_real_listing_package_path_blocks_without_real_photo_confirmed`
- `test_real_listing_package_path_clears_once_real_photo_confirmed`
- `test_listing_package_blocks_on_missing_material_and_size`
- `test_listing_package_uses_real_material_and_size`
- `test_listing_package_reaches_publish_ready_when_fully_valid`
- `test_listing_package_still_blocked_without_real_photo_even_if_material_ok` (proves the two
  fixes are independent — fixing material/size does not accidentally widen the photo gate)

`_ready_candidate()` (used by the older direct `publish_gate()` tests) was updated to include
`real_photo_confirmed: "yes"`, since it models a fully-cleared listing.

---

## 5 · Traps hit this session

1. **A pasted third-party "handoff" describing your own system's wiring can simply be
   wrong.** The V38.2 JSON confidently described a Launch Kit → publish_gate connection that
   does not exist in the code. Verified by tracing actual call sites before building anything
   — did not take the doc's word for it.
2. **Adding a new required gate breaks "fully evidenced" test fixtures silently.** Adding
   `real_photo_confirmed` to `EVIDENCE` immediately failed `test_fully_evidenced_candidate_is_
   publish_ready` until the fixture was updated. Expected, not a regression — but check for it
   every time a gate is added.
3. **A hardcoded placeholder can hide in production code indefinitely** if no existing test
   ever builds a "fully complete" candidate through the *real* function (only through hand-built
   dicts). The `no_placeholders` bug only surfaced when the actual `listing_package()` path was
   exercised end-to-end while chasing a different, unrelated task.
4. **On the VPS: `py` does not exist (Linux, not Windows) and bare `python`/`python3` do not
   have the project's dependencies** (`ModuleNotFoundError: No module named 'dotenv'`) — the
   systemd service uses `.venv/bin/python`; manual verification commands must too, or they
   fail on environment grounds that have nothing to do with the code.
5. **A live login page proves the process restarted, not which commit is running.** WebFetch-
   probing `https://etsy.theglobalserviceteam.site` confirmed the service was up (not 502)
   immediately after `systemctl restart`, but only `git rev-parse HEAD` on the VPS actually
   confirmed the right commit was live. Did both, did not stop at the first.

---

## 6 · Deploy record

```bash
git add src/product_manager.py src/profit.py src/publish_gate.py src/supplier_pull.py \
        src/validators.py tests/test_units.py
git commit -m "V38.2: tighten publish gate and supplier detail readiness"
git push origin main
# owner, on VPS:
cd ~/etsy-agent && git fetch origin && git reset --hard origin/main
sudo systemctl restart etsy-web && sudo systemctl status etsy-web --no-pager
```

Verified: `git rev-parse HEAD` on VPS = `35aa43e3a56d48493fab09aaf9a7abf2aee2ba4a` (exact
match) · `.venv/bin/python -m pytest tests/test_units.py -q` green · `.venv/bin/python
main.py selftest` → ALL CHECKS PASSED · live site probed independently, healthy · `git status
--short` on VPS shows only an untracked `cron.log` (runtime log, unrelated, expected).

**4 untracked local items were never staged, inspected, or committed** (per owner
instruction): `22Etsy_Evidence_Exporter_v3.3/`, `22Etsy_Evidence_Exporter_v3.4.0 (1)/`,
`Etsy_4412078408_Reviews.csv`, `HeyEtsy_4412078408_Detail.csv`. Carry this forward — same as
the last handoff.

---

## 7 · Open items for next session

1. **The 3-listing launch sprint (previous handoff §2) was not checked this session.**
   Re-verify Build Queue state, whether `mens carry on bag` / `mini bride tote bags` moved,
   and whether the `embroidered sweatshirt` Build-Queue absence bug was ever addressed.
2. **This handoff file itself is not committed.** Same rule as everything else this session —
   nothing gets committed without the owner's explicit go-ahead.
3. If `real_photo_confirmed` or the material/size fix need a live web UI later (not just CSV),
   that is new scope — the owner explicitly declined it this session in favor of the
   zero-new-surface-area option.

---

## 8 · How the owner wants this work run (unchanged, carried forward)

**Do not blind fix — check the code, check the process, verify claims against the actual
codebase before building anything on top of them**, including claims from pasted docs that
sound authoritative. Show measurements, not assertions. If an idea or a proposed field is not
worth building the way it was described, say so and offer the correct alternative instead of
silently either overbuilding or silently doing something that only looks connected.

**English-only output · never auto-publish a listing · `PUBLISH_AUTOMATION` stays False · no
Etsy API/OAuth/publish automation · frozen L0–L4 files are frozen · nothing gets committed
without explicit approval, even after approval was given for a previous, narrower commit.**
