# 22etsy-agent — Handoff · 2026-08-03 11:08 (+07)

_Session owner: Alex (Hue, Vietnam). **Supersedes `22etsy_agent_handoff_V37.11.md`**, which
supersedes V37.8 → V37.5. Read this file first; where they disagree, the newest wins._

Repo `D:\Claude\22etsy-agent` · GitHub `NatoandUSA/etsy-agent` · VPS `~/etsy-agent`, service `etsy-web`.
Live: https://etsy.theglobalserviceteam.site

> **Handoff naming, from this file onward:** `22etsy_agent_handoff_<YYYY-MM-DD>_<HHMM>.md`,
> local time (+07). Sorts chronologically, no more guessing whether V37.8 or V37.11 is newer.
> The old `_V37.x` files stay as-is; do not rename them.

---

## 0 · Status

| Commit | What | Deploy |
|---|---|---|
| `d713405` | V37.11 handoff (previous session's end state) | ✅ |
| `6fc5050` | Home 35× faster · phases 3/4 re-pointed · unified tool header · Back/Next · dead CSS | ✅ |
| `f036319` | auth: pin password hashing to `pbkdf2:sha256` (pre-existing working-tree change) | ✅ |
| `adff73c` | Home rebuilt: one instruction, 5 phase rows naming their tools · `/training` banner | ⬅ **latest** |

`local main == origin main == VPS == adff73c`. Service active since 11:04:13 +07, journal clean.
`src/version.py` still says `VERSION = "37.0"` — it has not tracked any V37.x work and is not
a reliable deploy marker. **Probe the live site instead:**

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://etsy.theglobalserviceteam.site/send-to-rerank
# 405 = route exists (POST-only). 404 = stale.
```

Tests: **531 passed, 1 failed** — `test_full_selftest_pipeline`. **Two** sub-checks fail, not one
(V37.11 documented only the first):

1. `Trending/Opportunities/Gems paginate past the ~10-row server cap` — needs live MCP.
2. `Workflow shown as a table (Vietnamese); decision + reference docs present` — `selftest.py:996`
   looks for a `| Bước | Vai trò | Hành động |` header that `WORKFLOW.md` no longer has.

Both confirmed failing on a stashed baseline, both predate this session. **Do not "fix" #1 offline.**
#2 is a genuine stale assertion and is cheap to correct.

---

## 1 · What the owner reported, and what was actually wrong

Six complaints. All six were real; the causes were **not** what the surface suggested.

**① "Getting back to homepage is slow — heavy code or slow VPS?"** → Heavy code. Measured 0.365 s
locally, of which 0.35 s (97%) was rebuilding the Inbox **twice per request, forever**.
`opportunity_inbox._CACHE` held exactly one entry and called `.clear()` on every miss, but one home
load asks for `mode='pod'` (`pipeline_status.snapshot` + the opportunity queue) *and* `mode=None`
(`workflow_spine.status`). The two evicted each other every single request. Now only entries built
from **older data** are dropped, so sibling modes coexist. **0.365 s → 0.011 s (35×).** Tunnel
baseline is ~0.20 s, so the VPS was never the problem.

**② "Learn from winners and New KW both lead to YTuong Import Center."** → True: both phases had
`"route": "/imports"`. Phase 3 → `/pattern-miner`, phase 4 → `/keyword-lab`.
**The deeper bug V37.11 missed:** `/imports` passed `"feed"` to `_stage_nav`, so arriving from the
phase-3 card highlighted **"1 Find & filter"** — the destination page insisted you were in a
different phase. That mismatch, not the route, is what read as "wrong page".

**③ "There are still 2 workflows."** → True. `WORKFLOW.md` was fine (generated from the spine);
`/training` was the stale one, teaching `BUILD QUEUE → FEED → RANK → PATTERN MINER → KEYWORD LAB →
RE-RANK → BUILD → PHOTO → ADS → LEARN` — and it was linked from home as "Quy trình 9 bước".
Home also carried **three** competing "where do I begin?" answers at once.

**④ "Should have the search bar at Product line switch."** → The two controls were mutually
exclusive by construction: `_mode_tool` rendered the switch and no keyword box, `_kw_mode_tool`
rendered the box and no switch. New `_tool_head()` renders both everywhere.

**⑤ "How to move step to step? Have to go to homepage every time."** → **Seven** routes had no phase
strip, including `/trending` (phase 1's own destination), and `/pinterest-trends` (step 2),
`/suppliers` (step 3), `/team/ops` (step 12) were dead ends. Zero pages had Back; exactly one had
Next. Added ◀ Back / Next ▶ carrying `q` + `mode`, plus a "Phase 3 of 5 · steps 5·6·7·8" readout.

**⑥ "How do I access Pattern Miner, Keyword Lab????"** → You couldn't. Pattern Miner had **no card
anywhere** on home; Keyword Lab existed only as the bare string `/keyword-lab` inside a collapsed
list of raw URLs. Phase rows now name their tools as links.

**Bonus, unreported:** six orphaned CSS declaration blocks (bodies of the deleted 9-step rail,
selectors removed) shipped on every home load. CSS error recovery swallows everything up to the next
`{`, so the entire `.plnudge` rule was discarded and the banner rendered unstyled. Removed.

---

## 2 · The home page now

Always visible, in this order, and nothing else:

```
🧑‍💼 Manager desk / My work        (stat tiles)
▶ DO THIS NEXT — Phase N · Owner   + slim keyword box
WORKFLOW · 5 PHASES                N of 12 steps done
  1 🔎 Find & filter   Trending now · Pinterest trends · Supplier fit
  2 🏆 Rank            Opportunity Inbox · Long-tail lane · Build Queue
  3 🔬 Learn winners   Pattern Miner · Import evidence · Etsy Spy
  4 💡 New keywords    Keyword Lab · Re-rank · Winner candidates
  5 🚀 Build & ship    Launch Kit · Photo brief · Team Ops
🎯 Today's opportunities — act on these
```

Then five disclosures: Import data · Work one keyword · All tools · Advanced · Reports.

The tool links come from a **`tools` tuple on each `PHASES` entry** — add a tool there, not to the
HTML. Rows are full-width because a 5-column grid truncates tool links and status to uselessness.
Each row shows what is outstanding ("next: Supplier feasibility"), replacing chips that only
restated the phase title.

---

## 3 · The workflow model (unchanged in shape, changed in routing)

`src/workflow_spine.py` is still the single source of truth. `STEPS` = the 12-step checklist,
`PHASES` = the 5-phase navigation.

| Phase | Steps | Route | English (UI) | Vietnamese (guide) |
|---|---|---|---|---|
| 1 | 1–3 | `/trending` | Find & filter | Tìm & lọc |
| 2 | 4 | `/inbox` | Rank | Xếp hạng |
| 3 | 5–8 | **`/pattern-miner`** | Learn from winners | Học người thắng |
| 4 | 9–10 | **`/keyword-lab`** | New keywords | Từ khoá mới |
| 5 | 11–12 | `/launch-kit` | Build & ship | Làm & giao |

New helpers: `phase_of(key)`, `neighbours(key)` (powers Back/Next), `tools` on each phase.

Renders from this module: home, `_stage_nav()` on every tool page, `WORKFLOW.md`, and the
`/training` warning banner. Adding a route does **not** mean adding a step — add it to
`SUPPORT_ROUTES`.

### Language rule (unchanged)
UI/home → **English**. How-to-use guide + `WORKFLOW.md` → **Vietnamese**. Listing output (title,
13 tags, description) → **English**, buyers are American. CLI output stays unaccented (Windows
console is cp1252; use `PYTHONIOENCODING=utf-8` locally).

---

## 4 · Traps — do not repeat

1. **A 200 status code proves nothing** (carried forward, still true). All 12 broken-feeling buttons
   returned 200. Check destination **content** — and check which phase the destination page thinks
   you are in, which is what V37.11 missed.
2. **`class="stgnav"` is not a reliable marker for the phase strip.** `_source_toggle`
   (`web.py:1749`) reuses that class for the Live/Local source picker. My first probe reported
   `/trending` as having the strip when it had none. Grep for the phase **label text**
   (`Find &amp; filter`) instead.
3. **Do not add a cache to `/trending` `/opportunities` `/gems`.** I measured them at 15.6 s / 17.4 s
   / 14.0 s and proposed caching — that was a **cold** cache on a laptop that had never fetched those
   queries. Both the MCP and REST paths already cache per-day in SQLite (`db.cache_get/cache_put`),
   and the VPS runs `main.py warm --fresh` on a 6-hourly cron plus `vps-build.sh` at 06:00. Today's
   `api_cache` held 416 rows. Warm, those pages serve in 0.01–0.13 s.
4. **`"learn"` is ambiguous.** In the legacy 9-stage vocabulary it means *post-launch* learning
   (`/feedback`, phase 5). As a phase key it means *Learn from winners* (phase 3). `_STAGE_TO_PHASE`
   maps it to `"ship"`. Use the step keys (`evidence`, `candidates`, …) to name a phase.
5. **Never plumb `discovered_keywords.opportunity` into the O leg** (carried forward). It is
   `discover.score()` = `log10(revenue) × conv × momentum ÷ listings` — every input is already a leg,
   so it double-counts all four. Pinned by `test_o_leg_is_never_fed_a_derived_score`.
6. **`_h_esc` escapes `&` → `&amp;`.** Unescape before asserting in tests.
7. **Never say "deploy unconfirmed" from a doc.** Probe the live site (§0).
8. `DESIGN_PREP_READY`/`PUBLISH_READY` is a **listing-QA** gate (`product_manager.py:588`), unrelated
   to GO.

---

## 5 · Known broken / next up

1. **`/training` is flagged, not fixed.** It now serves with a banner generated from
   `workflow_spine` mapping each chapter to its real phase and naming the three steps it has no
   chapter for — **Pinterest trend signal, Supplier feasibility, HeyEtsy evidence**. The content is
   still the 9-stage flow. Writing those three Vietnamese chapters needs the owner's input; do not
   invent them.
2. **`selftest.py:996`** asserts a `| Bước | Vai trò | Hành động |` header `WORKFLOW.md` no longer
   has. Cheap, real fix.
3. **`supplier_ops.match()`** — still the unfixed bug from V37.8. It scores token overlap between a
   keyword and a supplier product NAME; the real library holds four blank types (`TSHIRT`,
   `SWEATSHIRT`, `HOODIE`, `WASH CAP`, all EMBROIDERY), so every threshold blocks ~100% of keywords
   (`"custom crew t-shirt"` does not token-match `"TSHIRT"`). Used by the supplier UI and the
   `supplier_trend` lane. Needs one canonical matcher shared with `feasibility_gate`, with tests.
4. **`src/feasibility_gate.py` is still committed and UNWIRED** (owner's instruction, dry-run).
   Owner's required order: **A** keep dry-run ✅ · **B** remove frozen import ✅ · **C** tests for
   `supplier_fit`/`build_allowed`/`pinterest_label`/`apply_to_row` + `test_no_frozen_imports` ·
   **D** supplier coverage fields (`complete + no match ⇒ NOT_MAKEABLE`; `partial/unknown + no match
   ⇒ NEEDS_SUPPLIER_CHECK`, not a hard block) · **E** Inbox + spine **badge only** · **F**
   enforcement only after the library is verified complete. **C–F remain.**
   *Open question for the owner:* is the supplier library genuinely embroidery-only, or just
   incomplete? That decides whether its 10% NOT_MAKEABLE is a business fact or an import gap.
5. **Zero BUILD_NOW rows locally.** All GO keywords are 3 words and L4 routes anything <4 words to
   Pattern Miner (`ranking_engine.py:176-186`) — the owner's own rule. **Long-tail supply is the
   binding constraint**, not scoring.
6. **Live data gap:** the VPS shows *71 winners imported · 0 with reviews* — the team runs the
   expensive HeyEtsy Detail export and skips the cheap Reviews export. Reviews are what produce the
   recipient/occasion language behind the candidates. Also **810 candidates from 136 winners waiting
   to be sent** at phase 4: the loop we built, loaded and unused.
7. **Keyword Lab enrich gap:** `shortlister_integration._enrich_row` never fetches revenue or views,
   so Lab candidates are capped at WATCH by construction.
8. **Nobody has clicked the new home in a browser.** Every claim here is from rendered HTML behind a
   test client; the live site sits behind a login this session could not pass. First job next
   session: confirm phase 3 → Pattern Miner and phase 4 → Keyword Lab in a real browser, and that
   each row's three tool links are the right three.

---

## 6 · Data + guardrails

- `keyword_data.csv` — ~1,523 rows locally (VPS ~1,544), sources `mcp:search` 698 / `mcp:ranking` 482
  / `mcp:trending` 259 / `mcp:opportunity` 84. **No test data.**
- Schema carries `total_revenue` (V37.5) and `opportunity_score` (V37.6); `DictReader` keeps old
  files loading. `opportunity_score` only fills on the next `main.py harvest`.
- Evidence lanes for listing **4412078408** retained with the corrected V37.7 parse — a real fixture.
  Tests use `tmp_path` and never touch the real master.
- `PUBLISH_AUTOMATION = False` (`team_ops.py:2227`, `ops.py:335`) · no Seller-Central connection ·
  honest-nulls · **`ranking_engine.py` frozen and untouched**. `opportunity_score.py` was modified in
  V37.6 under explicit owner authorisation, in its own commit. Nothing this session touched scoring.
- VPS cron: `vps-build.sh` 06:00 daily · `main.py warm --fresh` every 6h · plus unrelated
  homestay/zalo keepalives.

---

## 7 · How the owner wants this work run

Stated directly, twice, and worth honouring: **review first, propose a ranked plan, get sign-off,
then fix in that order.** No broad refactors, no unrelated modules, no new features while the current
workflow is unstable. *"Do not blind fix — check the code, check the process. You keep adding stuff
that don't work."*

**Show measurements, not assertions.** Every number in this file was measured against the live
master, a profile, or a click test — and where a measurement turned out to be wrong (the 15 s browse
feeds, the `stgnav` false positive), it is corrected here rather than quietly dropped.
