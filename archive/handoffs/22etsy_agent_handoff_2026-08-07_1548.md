# 22etsy-agent — Handoff · 2026-08-07 15:48 (+07)

_Session owner: Alex (Hue, Vietnam). **Supersedes `22etsy_agent_handoff_2026-08-06_0249.md`**,
which supersedes 2026-08-06 01:45 → 2026-08-05 22:47 → 14:26 → 2026-08-04 00:16 → V37.11.
Read this file first; where they disagree, the newest wins._

Repo `D:\Claude\22etsy-agent` · GitHub `NatoandUSA/etsy-agent` · VPS `~/etsy-agent`, service `etsy-web`.
Live: https://etsy.theglobalserviceteam.site

---

## 0 · Status — everything shipped and LIVE

| | |
|---|---|
| **Tests** | **827 pass, 1 skipped, 0 fail** (session start 620) |
| **Deployed** | `5edfbb6` — local == origin == VPS, service restarted 15:39:08, probed |
| **Frozen files** | zero edits, sha256 baseline enforced |
| `PUBLISH_AUTOMATION` | `False` |
| **Working tree** | clean except 4 untracked exporter items (never inspected, do not commit) |

```
5edfbb6  feat(build-queue): PUBLISHED_MANUALLY + day 3/7 review
6f23072  fix(harvest): preserve fractional views in keyword master
1e9855a  feat(recovery): safe extension-keyword recovery helper, dry-run by default
34851b9  feat(inbox): add the Added column to the ranked worklist
8635bba  fix(harvest): preserve enriched keyword fields during cron merge
3bab7c0  test(pattern-miner): isolate seeded capture fixture from sqlite index
```

---

## 1 · THE DECISION THAT MATTERS — read before doing anything

The owner stopped feature work. The audit found the real bottleneck:

```
792 buildable keywords · 0 built · 7 Build Now · 345 Confirm First
```

**The constraint is launch throughput, not keyword discovery.** A month of ranking
produced zero listings. That is also why the owner kept seeing "the same keywords for
many days" — nothing ever left the queue, so nothing changed.

**Standing instructions from the owner:**

- Do **not** run Set C recovery (ready and safe, deliberately unused — see §4)
- Do **not** start Pattern Miner Phases 2–7
- Do **not** add more discovery features or reports
- Do **not** change ranking math or touch frozen L0–L4
- Manual publish only, `PUBLISH_AUTOMATION` stays `False`

The one active job is the **3-listing launch sprint** (§2).

---

## 2 · The launch loop — built this session, ready to use

`mark_done()` existed but was binary: "designed" and "live on Etsy" were the same state,
and nothing scheduled a follow-up. Extended, not rebuilt — no new page, no new storage.

- **`PUBLISHED_MANUALLY`** joins `DONE`. It is the ONLY way the system learns a listing
  went live: the tool never publishes, the owner records the fact by hand.
- Publishing **stamps day-3 and day-7 review dates**, so follow-up is scheduled by the
  ACT of publishing rather than remembered. Due reviews show above the queue.
- Plain `DONE` = "worked it, not publishing" → schedules no review.
- An unknown status falls back to `DONE`, never `PUBLISHED` — a typo must not claim a
  listing is live.
- Backwards compatible: `data/build_actioned.csv` is append-only and predates these
  columns; old `(keyword,user,ts)` rows load as `DONE`. Last write wins.

**How to run the sprint:**

```
/build-queue → 🚀 Kit → work the listing → publish on Etsy BY HAND
            → return, click 🏷 Published
            → leaves the queue, day 3 + day 7 reviews auto-scheduled
```

| keyword | state |
|---|---|
| `mens carry on bag` | OPEN in Build Queue |
| `mini bride tote bags` | OPEN in Build Queue |
| `embroidered sweatshirt` | **ABSENT from Build Queue** — see below |

> **`embroidered sweatshirt` has `views_24h` blank** (listings 43, revenue 46,111,
> conv 0.0134 all present). `_classify` needs views > 0 to call a row proven, so it
> never reaches the Build Queue — while the Inbox still shows it Build Now off Etsy
> proof. Two surfaces, two gates. Almost certainly one of the 127 fractional views the
> 06:00 cron truncated this morning before the fix deployed.
> **Work it from `/launch-kit?q=embroidered+sweatshirt` directly**, or substitute
> `transparent bag` (62.1, top of queue), or re-enrich on the PC.

---

## 3 · Data integrity — three bugs found and fixed, one PROVEN in production

### 3.1 Harvest blanked enrichment daily (`8635bba`)

`merge_existing` carried only keywords the pull MISSED. For a keyword the pull
RETURNED it kept the thin fresh row and copied nothing but `source`. The VPS IP is
blocked from YTrends so its pulls are always thin — every thin row overwrote a rich one.

```
Aug 6 00:42 backup   1,701 rows  revenue 998  conversion 1,458
Aug 6 06:06 cron     1,798 rows  revenue 256  conversion   721
```

Now merged field-by-field: a fresh value wins only when it IS a value. `_f()` maps
blank AND zero to None, so a zero from an API cannot overwrite a measurement.
Plus a density guard that ABORTS the write if revenue/conversion/price/views fall >10%.

> **PROVEN IN PRODUCTION.** The Aug 7 06:00 cron ran against the fix: rows 1,798 →
> 1,887 (+89) and enrichment went **UP** — revenue 1,005 → 1,017, conversion
> 1,499 → 1,524, price 1,493 → 1,518. The previous unfixed run took revenue 998 → 256.

### 3.2 Fractional views truncated on every write (`6f23072`)

`write_keyword_data` serialised `views_24h` through `_opt(v, int)`:

```
0.81 → 0     0.97 → 0     0.43 → 0
```

155 rows held fractional views and lost them on EVERY write, the cron included, so the
loss repeated daily and looked like the data had never existed. Surfaced only because
the recovery guard counts POSITIVE views and refused to write when it fell 1,438 → 1,283.

New `_views()` keeps positive fractions, still writes integers as integers, zero
behaviour unchanged. **Deployed 13:47 — AFTER this morning's cron, so 127 more were
lost today. Tomorrow's 06:00 is the first protected run.**

> Known and NOT fixed: `write_raw_and_processed()` has the same `int` truncation for its
> own `data/processed` dump. Different file, outside the approved scope.

### 3.3 data_store bypassed Phase 0 (`098573e`, previous session)

`_kw_match` was a FOURTH copy of the old shared-token rule, on the FASTEST path
(`load_batch` tries the index first), so the matcher fix was a no-op wherever the index
was populated. Fixed at both levels.

---

## 4 · Extension recovery — built, tested, deliberately NOT run

`src/ext_recovery.py` + `tests/test_ext_recovery.py` (22 tests). **Dry-run by default**,
refuses a production write without a backup path, aborts if any guarded count falls,
touches `keyword_data.csv` only.

Clean dry-run on the VPS (`1e9855a` + views fix):

```
rows            1,887 → 2,194  (+307)     revenue    1,017 → 1,017
unique          1,887 → 2,194             conversion 1,524 → 1,524
aborted         False                     price      1,518 → 1,518
                                          views pos  1,311 → 1,311
all 3 DBs UNCHANGED · production keyword_data.csv UNCHANGED
```

**The owner decided NOT to run it.** Those 307 keywords arrive unenriched — same as the
97 the cron added, of which only 5 have revenue — so they would land in WATCH and never
surface. It adds a dashboard number, not a sellable idea.

To run it later, the exact command is in §7 of the 2026-08-06_0249 handoff, or:

```bash
cp -p keyword_data.csv "backups/keyword_data.csv.$(date +%Y%m%d_%H%M%S).pre_recovery.bak"
.venv/bin/python -c "
from src import ext_recovery as er
fresh,_ = er.orphans(); C,_ = er.set_c(sorted(fresh.values()))
print(er.recover(C, write=True, backup='backups/keyword_data.csv.recovery_inline.bak'))"
```

---

## 5 · The production audit — corrected findings

Two of my own conclusions were WRONG and the owner caught both. Do not repeat them.

1. **"The extension stopped Aug 2" — FALSE.** It is active: `etsy_proof` newest Aug 6
   10:59, `etsy_listing_detail` Aug 5. Staff capture **Etsy listings**, which correctly
   route to evidence lanes. Only the **YTrends keyword-table** lane went quiet. The
   ledger's `RESULT` column says **"leads"** (listing rows), not **"new kw"** — read it.
2. **"18,649 imports" is import EVENTS, not keywords.** `discovered_keywords` holds
   12,839 rows but only **1,141 unique tags** — the same keywords re-imported every pull.

**Why only ~1,900 keywords after a month:** the master is 99.7% `mcp:*`. Extension and
Keyword-Lab keywords were repeatedly destroyed by the old PC→VPS overwrite —
`ext` 455→0 on Jul 29, 432→2 on Jul 31, all non-mcp gone by Aug 3 (which is the PC's
1,523-row master landing on the server). That door is closed now.

**Why old keywords sit on top:** 62% of the master arrived in one Jul 9 backfill, and new
keywords arrive UNENRICHED — only 5 of 97 got revenue — so they cannot outrank a July row
with $58K behind it. Not a sorting bug. The sort has no freshness dimension by design.

**Staff instruction, if asked:**
> To add new **keywords** → capture the YTrends **keyword table**.
> To add **evidence** → capture Etsy **listing/detail** pages.

---

## 6 · Deploy — Claude CAN do this, with the exact string

**`/etc/sudoers.d/etsy-web` grants passwordless restart, but sudoers matches LITERALLY:**

```
(root) NOPASSWD: /usr/bin/systemctl restart etsy-web, restart etsy-tunnel,
                 status etsy-web, status etsy-tunnel
```

`restart etsy-web` **works**. `restart etsy-web.service` **does not** — the suffix makes
it a different string and it falls through to the password rule. That single character
misled an entire session into believing passwordless sudo was unconfigured, and into
"correcting" a handoff that was right. Run `sudo -n -l` rather than guessing.

```bash
git push origin HEAD:main
ssh -p 55317 etsy@51.79.200.65 "cd ~/etsy-agent && git fetch origin -q && git reset --hard origin/main"
ssh -p 55317 etsy@51.79.200.65 "sudo -n systemctl restart etsy-web && systemctl is-active etsy-web"
```

**A deploy is not done when the code lands.** `is-active` says `active` throughout.
Compare `systemctl show etsy-web -p ActiveEnterTimestamp --value` against the mtime of a
file you changed. `git reset --hard` is data-safe — all data files are gitignored; verify
with `git check-ignore` rather than assuming.

---

## 7 · Tomorrow — the one open item, 2 minutes

The 06:00 cron will be the **first run protected by both harvest fixes**.

```bash
ssh -p 55317 etsy@51.79.200.65 "cd ~/etsy-agent && tail -20 cron.log"
ssh -p 55317 etsy@51.79.200.65 "cd ~/etsy-agent && .venv/bin/python -c \"
from src import ext_recovery as er; print(er.counts())\""
```

Expect revenue ≥ 1,017, conversion ≥ 1,524, **positive views to stop falling** (~1,311).
If the density guard fires instead, the log says so and the file is untouched — also a pass.

After that, data integrity is closed. Everything else is shipping listings.

---

## 8 · Data — the VPS is not a copy of local

| | local | VPS |
|---|---|---|
| `keyword_data.csv` | 1,701 rows | **1,887**, revenue 1,017 |
| capture pool | ~empty | 156 spy · 154 ytrends_ext · 109 headers |
| `data/db/etsy.db` | absent | 2.6 MB, 6,460 listings, **user_version 0 = STALE** |
| supplier library | 25 products | **1,010** (POD partial) |

Capture and supplier data are gitignored and server-only. **Rebuilding `etsy.db` is an
unrun operational step — do not do it without asking.** Read-time filters mean the miner
is correct regardless; the Evidence Health panel just flags the index stale.

---

## 9 · Traps — do not repeat

Carried forward: **a 200 proves nothing** · probe, never quote a doc · `is-active` cannot
discriminate a release · "unknown" and "no match" are different answers · **a zero from an
API usually means "I don't know"** · a failed fetch is not an empty source · **a test that
passes against a known-bad input is not a test that pins the invariant**.

Added this session:

1. **The same defect can live in FOUR files.** Grep for the SHAPE of the bug
   (`min(2, len(`), not its location — and **fix the fastest path first**, or the fix is
   theatre.
2. **Do not hardcode a schema you have only seen locally.** The panel's "not captured"
   list came from a near-empty PC pool and would have denied 123 files' worth of
   `views_24h`. **A false "not available" is worse than a blank cell.**
3. **A guard that cannot go red is worthless** — mutate the input and watch it fail.
4. **Count the thing you mean.** A perf test counting raw `sqlite3.connect` also counted
   `analyze()`'s connections and passed or failed by test order.
5. **A warning that fires on good data teaches staff to ignore the panel.** Test BOTH
   directions of every threshold.
6. **Verify the requirement, not your own work.** The freshness column shipped on five
   tables and missed the Inbox — the one the owner works from all day — because I checked
   the tables I had edited instead of asking which tables show a keyword.
7. **sudoers matches literally.** `restart etsy-web` ≠ `restart etsy-web.service`.
8. **An int cast is a data-loss bug when the value can be fractional.**
9. **Read the legend before drawing a conclusion.** "leads" ≠ "new kw"; that one column
   turned an "extension outage" into "staff changed what they capture".
10. **Cumulative import counters count EVENTS, not entities.** 18,649 imports = 1,141
    unique keywords.
11. **When the owner says the data looks wrong, believe them and go measure.** Both times
    they pushed back this session, they were right and the bug was worse than described.

---

## 10 · How the owner wants this work run

**Review first, propose a ranked plan, get sign-off, then fix in that order.** No broad
refactors, no unrelated modules. *"Do not blind fix — check the code, check the process."*
— and **read the data too.**

**Show measurements, not assertions.** Rank recommendations #1/#2/#3. Be direct: what is
good, what is weak, what to fix first. If an idea is not worth building, say so plainly —
the owner acted on exactly that advice to stop feature work this session.

**English-only output · never auto-publish a listing · `PUBLISH_AUTOMATION` stays False ·
no Etsy API/OAuth/publish automation · do not touch Launch Kit's internals · supplier
enforcement stays off · frozen L0–L4 files are frozen.**
