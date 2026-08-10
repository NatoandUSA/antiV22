# 22etsy-agent — Handoff · 2026-08-10 11:00 (+07)

_Session owner: Alex (Hue, Vietnam). **Supersedes `22etsy_agent_handoff_2026-08-08_0015.md`**,
which supersedes 2026-08-07 15:48 → 2026-08-06 02:49 → 01:45 → 2026-08-05 22:47 → 14:26 →
2026-08-04 00:16 → V37.11. Read this file first; where they disagree, the newest wins._

Repo `D:\Claude\22etsy-agent` · GitHub `NatoandUSA/etsy-agent` · VPS `~/etsy-agent`, service `etsy-web`.
Live: https://etsy.theglobalserviceteam.site

---

## 0 · What this session was

Closed the 3 open items the 08-08 handoff left hanging. No `src/` code changed — no test
suite run required, no service restart needed. Data patch + docs/extension only.

---

## 1 · Sprint keyword state — verified live on the VPS (SSH, read-only queries + one guarded patch)

| keyword | class | actioned? |
|---|---|---|
| `mens carry on bag` | PROVEN, in Build Queue | not yet — still open |
| `mini bride tote bags` | PROVEN, in Build Queue | not yet — still open |
| `embroidered sweatshirt` | **was PARTIAL (absent) → now PROVEN, in Build Queue** | not yet — still open |

**Root cause of the `embroidered sweatshirt` absence, confirmed (not guessed):** the VPS is
IP-blocked from YTrends (documented 08-07 handoff §5), so its own daily cron can never refresh
this row's `views_24h` — it will sit blank forever regardless of how many more crons run. Fetched
the live value directly via the YTrends MCP (`ytrends_research_keyword`): `avg_views_24h = 0.42`,
matching the value already sitting in the **local** (non-VPS) `keyword_data.csv` — so nothing
was invented, just carried across.

**Patched on the VPS**, one field, one row:
- Backed up first: `backups/keyword_data.csv.20260810_102929.pre_single_field_patch.bak`
- Guarded: aborts if the keyword isn't found, aborts if `views_24h` is already non-blank (won't
  clobber a value that arrived some other way), aborts if row count changes after write
- Verified after: `_classify()` → `PROVEN`, and it now appears in `build_shortlist.analyze()`'s
  `buildable` list (791 total)

All three sprint keywords are open and unactioned — the sprint itself has not moved since
08-07. That is real state, not something this session should paper over: **nobody has clicked
🚀 Kit → published → 🏷 Published on any of the three yet.**

---

## 2 · Untracked items — resolved (owner decided, not guessed)

The 4 items carried forward across every handoff since ~08-06 were finally inspected:

1. **Root `22Etsy_Evidence_Exporter_v3.3/`** — byte-identical duplicate of the code already
   committed at `extension/22Etsy_Evidence_Exporter_v3.3/`. **Deleted** (zero information loss).
2. **`22Etsy_Evidence_Exporter_v3.4.0 (1)/` + its `.zip`** — a real version bump, not previously
   in git. Diffed against v3.3: `manifest.json`, `background.js`, `content.js` (+291/-lines),
   `popup.html/js`, `README.md` all changed. **Swapped into `extension/`, replacing the v3.3
   copy** (`git mv` → content overwrite, so git sees it as a rename+modify, not a delete+add).
   Staging folder + zip deleted after the swap.
   - Safety-checked before committing: the only network write in the new code is
     `background.js`'s `fetch(..., POST)`, hardcoded-allowlisted to
     `https://etsy.theglobalserviceteam.site/api/import` (or localhost for dev) — same
     evidence-import design as before, still no Etsy/marketplace write capability.
3. **`Etsy_4412078408_Reviews.csv`** + **`HeyEtsy_4412078408_Detail.csv`** — a one-off test
   capture (23 rows total) of a competitor listing (TinyBarns personalized tote bag): public
   reviews + HeyEtsy stats, nothing sensitive beyond what's already public on the Etsy listing
   page. **Deleted** — easily re-captured with the extension if needed again.

---

## 3 · Deploy record

**Nothing was deployed to the VPS this session in the usual git-push sense.** The only VPS
change is the one-field CSV patch in §1, applied directly (backed up, guarded, verified) — it
does not require a service restart since `keyword_data.csv` is read fresh on each request, not
loaded once at boot. `git rev-parse HEAD` on the VPS is still `35aa43e`, same as 08-08 — local
is currently AHEAD of the VPS by this handoff commit + the extension swap (docs/extension only,
nothing in `src/`).

```bash
# what's staged locally, not yet pushed:
git add extension/22Etsy_Evidence_Exporter_v3.4.0 22etsy_agent_handoff_2026-08-08_0015.md \
        22etsy_agent_handoff_2026-08-10_1100.md
git commit -m "..."
# push + VPS sync deliberately left to the owner — see §5
```

---

## 4 · Traps hit this session

1. **A gate that requires all-of-N signals can strand a keyword forever if the source that
   feeds ONE signal is structurally broken for that environment** (VPS IP-blocked from
   YTrends) — the 08-07 harvest fix (fractional views) could never have closed this on its own,
   no matter how many more crons ran. Traced to the actual upstream cause via a live MCP query
   instead of re-guessing at "maybe tomorrow's cron will fix it."
2. **This file (`keyword_data.csv`) has a documented history of catastrophic overwrites**
   (harvest merge blanking enrichment, int-truncating fractional views, a disabled PC→VPS bulk
   sync that used to destroy non-mcp keywords). A single-field, backed-up, guarded, verified
   patch is a categorically different risk than any of those — but it's the same file, so the
   guard-and-verify discipline from those past incidents was reused here on purpose, not skipped
   because "it's just one field."
3. **"Untracked and never inspected" doesn't mean "risky."** All 4 items turned out to be
   low-stakes (a duplicate, a legitimate version bump, and disposable test output) — but that
   was only knowable after actually diffing/reading them, not from the file names alone.

---

## 5 · Open items for next session

1. **Commit + push + VPS sync is NOT done as of this handoff** — local has the extension swap
   and both handoff docs staged/ready, but nothing has been pushed to `origin` and the VPS has
   not been touched beyond the one CSV field. Confirm with the owner before pushing.
2. **The 3-listing launch sprint is now fully unblocked but still fully unactioned.** All three
   keywords are open in the Build Queue with nothing published. This is a "go actually build and
   publish" item, not a code item.
3. Standing rule unchanged: **nothing gets pushed or deployed without explicit go-ahead**, even
   though this session's local commit was pre-authorized.

---

## 6 · How the owner wants this work run (unchanged, carried forward)

**Do not blind fix — check the code, check the process, verify claims against the actual
codebase and live data before building anything on top of them.** Show measurements, not
assertions. Prefer the smallest safe change over a broad one, especially on files with a known
history of data-loss bugs.

**English-only output · never auto-publish a listing · `PUBLISH_AUTOMATION` stays False · no
Etsy API/OAuth/publish automation · frozen L0–L4 files are frozen · nothing gets pushed/deployed
without explicit approval.**
