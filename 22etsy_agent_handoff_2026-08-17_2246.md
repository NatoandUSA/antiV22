# 22etsy-agent — Handoff · 2026-08-17 22:46 (+07)

_Session owner: Alex (Hue, Vietnam). **Supersedes `archive/handoffs/22etsy_agent_handoff_2026-08-12_2230.md`**
(full chain of older docs now lives in `archive/handoffs/`). Read this file first; where they
disagree, the newest wins._

Repo `D:\Claude\22etsy-agent` · GitHub canonical `NatoandUSA/antiV22` (VPS deploys from this),
mirrored to `NatoandUSA/etsy-agent` (`origin`) · VPS `~/etsy-agent`, service `etsy-web`.
Live: https://etsy.theglobalserviceteam.site

---

## 0 · Status — repo root cleaned up, Owner-Check persistence shipped, VPS caught up 16 commits

| | |
|---|---|
| **Commit** | `e2f7c99` — local `main` == `antiV22/main` == `origin/main` == VPS, verified by direct `git rev-parse` comparison on all four, not assumed |
| **Service** | active, restart timestamp (17:38:13) confirmed AFTER the deployed code landed (file mtime 15:45:49) |
| **Tests** | local full suite green (exit 0) + VPS full suite green (exit 0, one pre-existing network-dependent test deselected — see §3) + `compileall` clean on both + `py main.py selftest` all-pass |
| **Live acceptance** | full authenticated round-trip via `requests` against both local and live: login → `/studio` → fill+submit save form → reload → values persisted, `Publish ready` gate flips correctly |
| **Working tree** | clean after this doc's commit |

**Standing rules carried forward, unchanged:** Claude has the owner's full authorization to
commit, push, and deploy without asking first (2026-08-10). Verification (tests, live probe) is
still mandatory every time. See `[[deploy-runs-from-user-side]]`, `[[verify-deploy-dont-quote-handoff]]`.

---

## 1 · What shipped this session

### 1a. P0-A contract hardening series (`src/contracts.py`), PRs merged before this doc's window
Six iterative closure passes (P0-A.1 → P0-A.6) plus a follow-up fix, hardening the deterministic
compile pipeline (`create_master_keyword → compile_cluster → compile_package`): deep immutability,
full revision identity, provenance resolution, schema-driven publish-readiness gates, strict term
provenance, conditional personalization handling, and a single `OWNER_CHECK_SPECS` source of truth
that both `compile_package`'s default owner-check list and `ListingPackage.publish_ready` now derive
from (so the two can't silently drift). CI run 31919418125's real failures were root-caused and
closed in `443453f`, not patched around.

### 1b. Dashboard rebuild — 3-screen model (Queue → Studio → Publish & Learn)
Direct response to explicit feedback: staff barely used the tool because it had "too many
workflow, pipeline... too many function, too many ideas, too many tool, too many decision" and
looked "sophisticated but useless." Rebuilt around one linear path instead of dozens of entry
points:
- **`/start` (Queue)** — single front-door page, browses the ranked queue with no seed required
  (`cd56ba7`, `8fb4864`). Fixed a real priority-sort bug along the way: `ranking_engine._PRI` has
  higher=better (`BUILD_NOW=5`) but the browse path sorted ascending, so WATCH rows ranked ahead of
  BUILD_NOW/CONFIRM_FIRST — confirmed via real-data before/after (100% WATCH → 100% CONFIRM_FIRST
  at the top).
- **`/studio`** — first real caller of `src/contracts.py`'s compile pipeline (`90cf81d`). Gathers
  evidence from the typed keyword AND real neighbors, builds a suggested title from real evidence
  tags only (never invented), attempted a derived reference price from real `revenue/sold` proof
  (`79f5762` — verified correct pairing, but a full-dataset scan found 0 of ~2,000 real keywords
  currently have both fields populated, so it's shipped honest-but-currently-inert, not claimed as
  a working fix).
- **Owner-Check + price persistence** (`0d56ca1`, PR #11, this session) — the piece that makes
  `Publish ready` reachable through the UI at all. See §2.

### 1c. YTrends vs. real staff data reconciliation (`628c5ec`)
Explicit instruction: "I don't want a replicated ytuong... your job after pulling is
analyze/summary/compare to product 1 masterkw list, then compare with real manual data which my
staff send from etsy research pages." `/start` now reconciles the modeled YTrends signal against
real captured proof rather than presenting either in isolation.

### 1d. Repo root cleanup (this session, uncommitted as of writing — see §4)
The repo root had accumulated 30+ historical handoff/audit/planning docs and several superseded
prototype folders going back to July. Archived (not deleted) into `archive/`:

- `archive/handoffs/` — all 17 dated/version-tagged handoff docs + the mid-session JSON handoff.
- `archive/old-docs/` — audit reports (`AUDIT_REPORT.md`, `AUDIT_REPORT_V37.13.md`), the P0 upgrade
  roadmap + diff, a prior cleanup's own leftover planning docs (`cleanup_inventory.json`,
  `removal_plan.md`), the v38 backtest artifacts, superseded pre-repo scratch docs
  (`etsy-tools-*`, `etsy_project_setup.md`), `DEPLOY_V37_4.md` and `TUNNEL_SETUP.md` (both fully
  superseded by `DEPLOY_VPS.md`), `USER_GUIDE.pdf` (superseded by `USER_GUIDE.md`), and
  `etsy_listings.xlsx` (stale manual export duplicate of the live `etsy_listings.csv`).
- `archive/prototypes/` — `22etsy_exporter_v2/` and `ytrends-exporter/` (both superseded by the
  current live extension, `22Etsy_Pattern_Evidence_Harvester_v3.6.3`), `design_analyzer_v35_7/`
  (standalone tool, never wired into `main.py`), `etsy feedbak and improvement/` (33 MB — an old
  prototype whose `opportunity_score.py` logic was already ported into `src/opportunity_score.py`
  and is imported live by `src/opportunity_inbox.py` etc.), `agents/trend_hunter/` (real code, but
  confirmed unimported anywhere and the only doc referencing it is literally named
  `proposed-architecture-NOT-BUILT.md`).
- `archive/extension-old-versions/` — the stale v1.1.0 loose files and `22Etsy_Evidence_Exporter_v3.4.0/`
  that were sitting alongside the current version inside `extension/`. `extension/` now contains
  only the live `22Etsy_Pattern_Evidence_Harvester_v3.6.3/`.

**Verification before moving anything:** grepped `src/`, `tests/`, `main.py`, `wsgi.py`, `deploy/`,
`.github/`, `docs/`, `README.md` for a direct reference to every candidate file/folder. Two of
README.md's changelog lines pointed at `AUDIT_REPORT.md` by bare filename — repointed both to
`archive/old-docs/AUDIT_REPORT.md` so the links stay valid instead of dangling.

**Deliberately NOT touched** (confirmed active by direct code reference, not left out by
oversight): `WORKFLOW.md`, `CHEATSHEET.md`, `HOW_TO_USE.md`, `SUPPLIERS.md`, `SYSTEM_PROMPT.md`,
`USER_GUIDE.md`, `DEPLOY_VPS.md`, `staff_guide_vn.html` (all served directly by `src/web.py` or
read by `src/selftest.py`/tests); every root CSV/`.txt` (`competitor_audit.csv`, `costs.csv`,
`keywords.csv`, `social_signals.csv`, `supplier_costs.csv`, `tm_verified.csv`, `etsy_listings.csv`,
`niches.txt`) is read by name from `src/` — all confirmed live; `keyword_data.bak.csv` is not
history, it's auto-regenerated every enrich run by `src/enrich.py`; `team_workflow/` is referenced
by name in `src/ops_reports.py`'s own generated report text; `dist/`, `logs/`, `backups/` are
already-gitignored generated-output dirs, left in place since scripts write to them at those exact
root paths (moving them would just make the next run recreate them there anyway).

---

## 2 · Owner-Check + price persistence, in detail (PR #11, `0d56ca1`)

**The gap it closes:** `/studio` compiled a fresh `contracts.py` package on every page load, but
nothing about a human's actual field verification ever persisted — `publish_ready` could
structurally never reach `YES` through the UI, no matter what was true in reality.

**What was built:**
- `src/owner_checks.py` (new) — thin SQLite layer over two new tables in `src/appdb.py`'s schema:
  `owner_checks` (per keyword+mode+field: value, verified, note, who, when) and `owner_prices`
  (per keyword+mode: price, currency, who, when). `get_checks()`/`save_check()`/`get_price()`/
  `save_price()`.
- `interactive.studio()` now loads saved state on every visit and rebuilds real
  `ProductTruthFact`/`OwnerCheck`/`PriceFact` objects from it (a saved `OWNER_SET` price always
  outranks the derived `MODELED` reference price from §1b).
- One combined save form embedded directly in Studio's rendered markdown (`POST /studio/save`,
  new route in `src/web.py`) — confirmed `markdown.markdown()` passes raw `<form>` blocks through
  unchanged before building this, so no template engine was needed. Same text-input +
  verified-checkbox shape for every field on purpose — no extra widgets per field type, matching
  the whole point of this rebuild.
- **Real bug caught before shipping:** `compile_package`'s own default owner-check list
  conditionally adds a "Personalization Limits" check when `cluster.personalization_angles` is
  non-empty. A caller-supplied override (which Studio now always provides) has to mirror that
  exactly or a personalized listing could never satisfy `publish_ready` — fixed by reordering
  `studio()` to build the cluster first, then the override, and exposing `contracts.CHECK_FIELD_SLUGS`
  as the single shared source of truth for form-field naming between the render side and the save
  route so the two can't drift.

**Verified, not assumed:** 7 new unit tests (`tests/test_owner_checks.py`) + 6 new
`tests/test_studio.py` tests (saved-checks-reach-YES, checked-box-with-empty-value-stays-NO,
price-alone-insufficient, per-keyword scoping, conditional Personalization Limits field) + 4 new
`tests/test_routes.py` route tests (login-required, missing-field 400, real persist+redirect,
invalid-price ignored) — all passing. Manual end-to-end via `requests` against the running local
server: logged in, loaded `/studio?q=usa+flag+vintage&mode=pod`, submitted material+SKU+price,
confirmed values pre-filled correctly on reload and `Publish ready` stayed `NO` until all six
required fields were verified. Test data cleaned from `data/app.db` afterward.

---

## 3 · VPS catch-up deploy, in detail

**Root cause of "I can't see any updates online":** the VPS was **16 commits behind** `main`
(`0823029` vs `e2f7c99`) — nothing to do with caching or a stale process, the VPS genuinely hadn't
been deployed since PR #3.

**Deploy sequence run this session:**
1. `git fetch origin && git status` on the VPS — confirmed clean fast-forward, no local
   modifications to lose.
2. `git reset --hard origin/main` (VPS's `origin` remote = `antiV22` GitHub URL, matching local's
   canonical remote).
3. Pre-flight per `[[vps-python-version]]`: piped every changed file through the VPS's own Python
   3.10 `ast.parse()` over SSH — the documented authoritative check (local `py_compile` on 3.14
   gives false confidence; PEP 701 nested-quote f-strings compile fine on 3.14 but crash-import on
   3.10). All 5 changed files (`appdb.py`, `contracts.py`, `interactive.py`, `web.py`,
   `owner_checks.py`) parsed clean.
4. Ran the VPS's own full test suite over SSH (`.venv/bin/python -m pytest -q`) — took ~40 minutes
   wall-clock on this box (1.9 GB RAM, load average ~1.5, genuinely modest hardware — not a hang,
   confirmed via `ps`/CPU%). One failure: `test_every_step_route_shows_the_one_workflow_model`,
   which hits `/trending`'s live YTrends call — the VPS's datacenter IP is documented (in
   `deploy/push-to-vps.sh`'s own comments) as blocked from YTrends, so this is an existing,
   environment-specific limitation unrelated to anything in this PR. Re-ran with that one test
   deselected: **fully green**.
5. `compileall` guard + `sudo -n systemctl restart etsy-web && systemctl is-active etsy-web`
   (exact sudoers-permitted string, no `.service` suffix — see `[[deploy-runs-from-user-side]]`).
6. Verified per `[[verify-deploy-dont-quote-handoff]]`: `ActiveEnterTimestamp` (17:38:13) compared
   against the newest changed file's mtime (15:45:49) — restart happened after the code landed, not
   just "service still marked active." Live HTTP probes: `/studio/save` POST (no auth) → 302 to
   login (route exists), a junk path → 404 (proves current code, not a generic catch-all).

**Data was never touched** — `git reset --hard` only moves code; `data/agent.db`, `data/app.db`,
`keyword_data.csv` are all gitignored on the VPS and were confirmed untouched, per the standing
rule in `[[deploy-runs-from-user-side]]`.

---

## 4 · What's not done yet in this session

- **This handoff doc and the archive reorganization are committed together** as one commit on
  `main` (see the commit this doc ships in) — by the time you're reading this from a checked-out
  `main`, that commit already landed. If you're reading it from an editor with uncommitted changes
  still showing, that means the commit step hasn't run yet; check `git status`.
- **VPS was not re-deployed for the archive/handoff commit** as of writing this doc — file moves
  and a new handoff doc don't change any served code path, so there's no functional reason to. Data
  sync (`deploy/push-to-vps.sh`) and code deploy (`git reset --hard` + restart) remain two separate
  paths; this commit only needs the latter, and only if you want the VPS's own working tree to
  match the cleaned-up root (cosmetic — VPS git state, not the live app).
- **Queue's "Build draft" button still points at `/draft-listing`, not `/studio`** — deferred until
  now (Owner-Check persistence was the blocking piece). This is the next real step: cut the button
  over now that Studio actually has a path to `Publish ready: YES`.
- **Publish & Learn screen** (the third of the 3-screen model) — not started.
- **Real per-listing price source** — `etsy_proof.py` doesn't currently expose a real price field
  distinct from `revenue`/`sold`, which is why §1b/§2's `MODELED` price path is honest-but-inert on
  today's real data. Explicitly deferred as its own task, last priority per the agreed work order.

---

## 5 · Open questions for the owner

None blocking — the deploy question that was open at the top of this session ("should I deploy to
the VPS now?") is resolved: yes, done, verified (§3). Next open question is sequencing: cut
Queue→Studio now, or build Publish & Learn first? Recommendation: cut Queue→Studio first — it's a
one-line route change now that persistence exists, and it's the difference between staff finding
Studio at all versus it being a page nobody reaches.
