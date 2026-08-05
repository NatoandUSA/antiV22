# 22etsy-agent — Handoff · 2026-08-05 22:47 (+07)

_Session owner: Alex (Hue, Vietnam). **Supersedes `22etsy_agent_handoff_2026-08-05_1426.md`**,
which supersedes 2026-08-04 00:16 → 2026-08-03 11:08 → V37.11 → V37.8 → V37.5.
Read this file first; where they disagree, the newest wins._

Repo `D:\Claude\22etsy-agent` · GitHub `NatoandUSA/etsy-agent` · VPS `~/etsy-agent`, service `etsy-web`.
Live: https://etsy.theglobalserviceteam.site

---

## 0 · Status — everything shipped and verified

| | |
|---|---|
| **Tests** | **620 collected, 620 pass, 0 fail** |
| **Code** | `local == origin == VPS == de2e8f1` · `systemctl is-active` → `active` |
| **Data** | VPS `keyword_data.csv` **1,701 rows**, sha256 matches local **byte for byte** |
| **Untouched** | VPS `agent.db` (12,543 rows) and `app.db` (7 users / 18 tasks) verified unchanged |
| **Backups** | `~/etsy-agent/backups/*.20260805_224528.bak` — master + both databases |

```
de2e8f1  fix(deploy): a failed download is not an empty server; stop shipping agent.db
71e1a7d  fix(deploy): push-to-vps.sh destroyed 178 keywords the team added on the VPS
fa79b41  docs: handoff 2026-08-05 14:26
6b96782  V37.13: honest inputs to the scorer, and the backlog it was starving on
```

---

## 1 · What the shop actually has now

The engine was starved of inputs, not mis-tuned. Fixing the enricher and backfilling the
master changed the picture completely. **LIVE on the VPS:**

| metric | session start | now | Δ |
|---|---|---|---|
| Master rows | 1,523 (PC) / 1,701 (VPS) | **1,701 both** | unified |
| Rows the engine can score | 680 | **1,685** | +1,005 |
| Unscored backlog | 843 | **16** | −827 |
| **BUILD_NOW** | **0** | **6** | +6 |
| CONFIRM_FIRST | 112 | **375** | +263 |
| WATCH | 1,266 | **792** | −474 |
| SKIP | 113 | **494** | +381 |
| Rows with sales evidence | 140 | **347** (47 PUSH) | +207 |
| Rows showing a trend | **0** | **619** | +619 |
| Etsy-proof rows | — | 4 proven · 111 selling | |

The SKIP growth matters as much as the promotions — those are rows correctly demoted out of a
WATCH pile nobody could triage.

**The 6 BUILD_NOW rows (live):**

```
mens carry on bag      82.4  sellability 88.4 PUSH
mini bride tote bags   81.2  sellability 87.0 PUSH
funny vintage shirt    63.2  sellability 54.0     <- promoted by Etsy PROOF, not market score
vintage funny shirt    57.8  sellability 44.1     <- ditto
6 7 funny shirt        54.0  sellability 47.8     <- ditto
embroidered sweatshirt 59.8  sellability —        <- ditto
```

> **Local shows 2 BUILD_NOW, the VPS shows 6, and both are correct.** The master is byte-identical;
> the four extra come from the L1 Etsy-proof override, and the proof exports live only on the
> server. Do not "fix" this discrepancy — it is the proof tier working. If you want parity on the
> PC, copy `data/imports/etsy_proof/` down.

`mini bride tote bags` is the clearest illustration: it sat in the master from **2026-07-09**
carrying `etsy_listings 7` and nothing else, scored `None`, and sat in WATCH for 27 days. One
enrich call revealed $58,415 niche revenue, 4.36% conversion, 169 views/24h, 3 sellers holding
7 listings → 81.2 GO → BUILD_NOW.

---

## 2 · The root cause (V37.13, `6b96782`)

`ytrends_mcp.research_keyword()` has always returned `total_revenue`, `avg_revenue` and
`avg_views_24h`. `shortlister_integration._enrich_row()` read **none of them**.
`opportunity_score._demand_from()` needs revenue or views, so without either a row is
`core_missing` → `overall_score = None` → WATCH. **Every Keyword Lab and winner-derived candidate
was capped at WATCH by construction** — a missing copy, not a scoring bias.

The same call also **fabricated a competitive advantage**: for a keyword it has never indexed the
MCP answers `total_listings 0 / total_sellers 0` with nulls elsewhere, and the old guard accepted
that zero *and returned True*. `_competition()` reads 0 listings as **90.0 — a better market than
a genuinely open 38-listing niche at 75.2.** Measured, the fake zero moved one keyword from
"WATCH, competition unknown" to CONDITIONAL 67.6, and `0.0` was written to the master permanently.

Ten more fixes shipped in that commit — the stuck home-page pointer, the enrichment queue that
could not reach anything, the test suite writing into `data/history/`, `python main.py` broken
since `c65c1b5`, day-long caching of empty MCP answers, `agent.db` 10.9 MB → 3.4 MB, the live-API
guard probing the wrong transport, `seller_count` never reaching the long-tail lane, and the
"unfixable" pagination selftest. See `22etsy_agent_handoff_2026-08-05_1426.md` §2 for the detail;
it remains accurate.

**Three things built:** `py main.py enrich` (`src/enrich.py`), the sellability overlay in the
Inbox action cell, and keyword trend history read from `discovered_keywords`.

---

## 3 · The deploy scripts — two rounds, and why the first was not enough

### Round 1 (`71e1a7d`) — the deletion bug

`push-to-vps.sh` ended with a raw `scp keyword_data.csv` over the server's file. The PC harvests,
but the TEAM adds keywords ON the VPS through the web UI. `harvest.merge_master()` was written for
exactly this and had been wired into the `.ps1` **only** — the `.sh`, which `main.py expand`
advertises to Mac users, kept the old behaviour.

**Measured before syncing: the server held 1,701 rows to the PC's 1,523, and all 178 of the
difference were VPS-only.** Rather than merely avoid the bug, those 178 were rescued via
`merge_master` (0 lost, 0 of the PC's enriched values clobbered) and are in the master today.

### Round 2 (`de2e8f1`) — a code review found round 1 re-opened it

Five real defects, three of them in the tests I had claimed pinned the invariant:

1. **A failed download was treated as an empty server.** `if scp … 2>/dev/null; then merge; else
   echo "no keyword_data.csv on the VPS yet"; fi` followed by an unconditional upload — so a
   mistyped password, a network blip or a changed host key silently skipped the merge and then
   overwrote the master, destroying the same 178 keywords. Both scripts now probe with
   `ssh test -f` and branch on the exit code: **0** download+merge · **1** genuine first deploy ·
   **anything else ABORT**.
2. **`agent.db` was being shipped wholesale.** It is not a disposable cache: the VPS writes it on
   two crons (`warm --fresh` every 6h, `vps-build.sh` at 06:00 — the file had been modified that
   afternoon) and it holds `discovered_keywords`, which `_history_from_db()` now reads for the
   Inbox trend arrows. **The server holds 12,543 rows to the PC's 11,680** — copying ours up
   destroys 863 rows of the server's own history. Removed from **both** scripts.
3. **The tests were not trustworthy.** Three of four assertions were vacuous: the "downloads the
   server's copy" regex also matched the UPLOAD line's destination; the ordering check used
   `src.index("merge_master")`, which found the word in a **comment**; and the `app.db` guard had
   an `or "NOT touched" in src` escape hatch both scripts' own comments satisfied permanently.
4. **`src/selftest.py` audited the `.ps1` only** — the single-sided check that let the `.sh` drift
   for weeks while reporting deploy green. It also still *required* shipping `agent.db`.
5. **Ordering:** the merge ran *after* `daily` built the reports, so the shipped CSV contained the
   team's keywords next to reports rendered without them.

**Both scripts now:** merge first (step 1 of 5) → harvest+build → warm (local only) → timestamped
VPS backups of all three data files → upload `keyword_data.csv` (temp + atomic `mv`) and
`reports/latest`, **and nothing else**. The `.ps1` no longer gates the merge on `Test-Path` (a
stale temp file from an aborted run would be merged as if fresh); it uses scp's exit code like the
`.sh`.

`tests/test_deploy_scripts.py` now runs on **comment-stripped command lines**, classifies scp by
**parsed operand** (local source = an upload) rather than substring, treats a **missing script as
a failure not a skip**, and ships **mutation tests** that break each guarded line and assert the
matching check goes red. I also weakened a guard to `assert True` and confirmed its mutation test
fails — otherwise a mutation test that never bites looks identical to one that does, which is
exactly how the first version shipped.

---

## 4 · How the data sync was actually done (repeat this shape)

Neither deploy script was run. The sync was performed manually under the same rules, which is the
safe pattern when you only want data and not a full rebuild:

```bash
# 1. back up all three, timestamped
ssh -p 55317 etsy@51.79.200.65 "cd ~/etsy-agent && mkdir -p backups && \
  for f in keyword_data.csv data/agent.db data/app.db; do \
    [ -f \"\$f\" ] && cp -p \"\$f\" \"backups/\$(basename \$f).\$(date +%Y%m%d_%H%M%S).bak\"; done"

# 2. probe, then download + merge (never assume 'absent' on failure)
ssh -p 55317 etsy@51.79.200.65 "test -f '/home/etsy/etsy-agent/keyword_data.csv'"   # 0/1/else
scp -P 55317 etsy@51.79.200.65:/home/etsy/etsy-agent/keyword_data.csv data/vps_keyword_data.csv
python -c "from src.harvest import merge_master; print(merge_master('data/vps_keyword_data.csv'))"

# 3. upload the MASTER ONLY, atomically
scp -P 55317 keyword_data.csv etsy@51.79.200.65:/home/etsy/etsy-agent/keyword_data.csv.tmp
ssh -p 55317 etsy@51.79.200.65 "cd ~/etsy-agent && mv -f keyword_data.csv.tmp keyword_data.csv"
```

Verified after: **sha256 identical local↔VPS**, 1,701 rows / 14 cols / 1,701 unique both sides,
`agent.db` and `app.db` byte sizes and row counts unchanged.

**Deploying CODE is separate and does not carry data** (`keyword_data.csv`, `data/agent.db`,
`data/suppliers/supplier_products.csv` are all gitignored):

```bash
ssh -p 55317 etsy@51.79.200.65 "cd ~/etsy-agent && git pull --ff-only && \
  .venv/bin/python -m compileall -q src && sudo systemctl restart etsy-web && \
  systemctl is-active etsy-web"
```

SSH keys and passwordless sudo are configured — this runs from the agent session without prompts.
**Verify by probing, never by quoting the deploy output**: every interesting route is behind
`@login_required`, so HTTP codes cannot discriminate a release. Run the VPS's own venv over SSH and
assert the new behaviour directly.

---

## 5 · Known broken / next up

1. **Long-tail supply is now provably the binding constraint.** With real data in, the market
   signal is finding niches; the word-count rule is what holds them below BUILD. Converting 2–3
   word GO rows into 4+ word buyer-intent phrases is the bottleneck — which is exactly what
   phase 3 → 4 (Pattern Miner → Keyword Lab → Send to Re-rank) exists to do. **That loop is the
   highest-leverage step in the workflow now.**
2. **16 rows remain unscored** — YTrends genuinely has no data for them. Re-run `py main.py enrich`
   after the next harvest to catch new arrivals; it derives its own work list.
3. **No `api_cache` seeding for the VPS.** Removing the `agent.db` upload also removed the only way
   the server got a warm keyword cache (its IP is blocked from YTrends). If the live
   Trending/Opportunities pages feel slow, build an **`api_cache`-only merge** that leaves
   `discovered_keywords` untouched. Deliberately not built — do not shortcut it by shipping the
   whole file.
4. **The interactive-password race** between merge and upload is documented in both script headers,
   not engineered around. Use key auth, or sync when the team is offline.
5. **`/longtail` MIN_WORDS=3 vs the engine's 4** — deliberately unchanged. Raising it collapses the
   lane from 140 scored / 13 PUSH to 8 / 2, and every top lane row is CONFIRM_FIRST or WATCH in the
   engine. They answer different questions.
6. **`discovered_keywords` grows unbounded** (12,543 rows on the VPS, heavy duplication). It now has
   one reader (the trend map) but no pruning. Deleting rows deletes history — owner's call.
7. **`data/db/etsy.db`** (Local Capture Index, `src/data_store.py`, 647 lines) still does not exist
   locally; it fills only from extension SERP captures. Pattern Miner's DB lookup, Winner Finder
   "My data" and Build Queue's mined rows all return empty. Dormant, not broken.
8. **`/team/ops` has no phase strip** (11 of 12 step routes carry it) — a full-page sub-app needing a
   9th parameter through `team_ui.register()`.
9. **`WORKFLOW.md` claims to be generated from `workflow_spine.py` and is not.**
10. **Nobody has clicked any of this in a browser.** Every claim here is from a rendered page behind
    a Flask test client or a direct module call over SSH.
11. **Supplier library still `partial`** — 25 rows, 1 of 8 registered suppliers, 0 confirmed. Adding
    `product_url` + `processing_days` to `data/suppliers/Embroidery.csv` and re-uploading at
    `/suppliers` flips embroidery coverage to `complete` and switches enforcement on.

---

## 6 · Traps — do not repeat

Carried forward, still true: **a 200 proves nothing** · `class="stgnav"` is not a reliable phase
marker · do not cache `/trending`/`/opportunities`/`/gems` · `"learn"` is ambiguous · never plumb
`discovered_keywords.opportunity` into the O leg (reading its `momentum` as a time series is a
different thing and is what the trend map does) · `_h_esc` escapes `&` → `&amp;` · never say
"deploy unconfirmed" from a doc — probe · a probe can be non-discriminating · a score floor is
worse than a wrong score — check the **distribution** · "unknown" and "no match" are different
answers · derived data can silently drop source data.

Added this session:

1. **A zero from an API usually means "I don't know", not "the answer is zero".** Any code treating
   a count of 0 as a measurement hands the scorer its most attractive possible input.
2. **A failed fetch is not an empty source.** Distinguish "absent" from "unreachable" before acting
   on the difference — `ssh test -f` and branch on the exit code.
3. **Check which transport a probe actually tests.** The REST cookie was dead while the MCP was
   healthy, and the CLI guard refused to run a working command.
4. **A "one-click" queue can be scoped to a population that does not exist** and read as "nothing to
   do" for months.
5. **A function honouring a `path=` argument can still write to a hardcoded sibling path.**
6. **Verify a leak before fixing it.** A thread-leak claim made mid-session was wrong — CPython
   reclaims the executor by refcount; both trees settle to 0 extra threads. The change was reverted.
7. **The selftest pins `README.md` to `src/version.py`.** Bump both.
8. **"Do not fix offline" in a handoff is a hypothesis, not a fact.** The pagination check needed no
   network and stayed red for weeks because nobody re-read the assertion.
9. **A test that passes against the known-bad input is not the same as a test that pins the
   invariant.** Three of four assertions in the first deploy-test file were vacuous while "passing".
   Strip comments before asserting on code, anchor on parsed structure not substrings, and write
   **mutation tests** — then weaken a guard on purpose and confirm its mutation test goes red.
10. **A one-sided audit is how two files drift.** `selftest.py` checked the `.ps1` only and reported
    deploy green while the `.sh` carried a data-loss bug.
11. **Fixing a data-loss bug can re-open it through a different door.** Round 1 removed the raw
    overwrite and added a failure path that overwrote anyway.

---

## 7 · Data + guardrails

- `keyword_data.csv` — **1,701 rows, 14 columns**, identical on both machines. Local backup:
  `keyword_data.bak.csv`. VPS backups: `~/etsy-agent/backups/*.20260805_224528.bak`.
- `data/agent.db` — PC 3.4 MB (vacuumed) · VPS 10.9 MB, 12,543 `discovered_keywords`. **Never
  shipped in either direction.**
- `data/app.db` — server-only, 7 users / 18 tasks. **Never shipped.**
- `PUBLISH_AUTOMATION = False` · no Seller-Central connection · honest-nulls ·
  **`ranking_engine.py` and `opportunity_score.py` frozen and untouched.** A before/after probe over
  the whole master with only the *code* changed returned every lane count identical — all movement
  in §1 is data.
- Everything verified to parse under **Python 3.10** (VPS runs 3.10.12).
- **620 tests**, all green. New this session: `tests/test_enrich.py`, `tests/test_deploy_scripts.py`.
- New public API: `src/enrich.py` (`run`, `unscored`, `FIELD_MAP`) ·
  `opportunity_inbox._needs_enrichment` / `TREND_DELTA` / `_history_from_db` / `_history_from_csv` ·
  `main._MCP_CMDS`.

---

## 8 · How the owner wants this work run

Unchanged and honoured: **review first, propose a ranked plan, get sign-off, then fix in that
order.** No broad refactors, no unrelated modules. *"Do not blind fix — check the code, check the
process."* — and **read the data too.**

**Show measurements, not assertions.** And when a claim turns out to be wrong — the thread leak,
and the first deploy-test file — say so plainly and revert it. Two of this session's most useful
findings came from a code review of work that had already been called done.
