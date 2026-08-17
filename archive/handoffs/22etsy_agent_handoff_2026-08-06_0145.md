# 22etsy-agent — Handoff · 2026-08-06 01:45 (+07)

_Session owner: Alex (Hue, Vietnam). **Supersedes `22etsy_agent_handoff_2026-08-05_2247.md`**,
which supersedes 2026-08-05 14:26 → 2026-08-04 00:16 → 2026-08-03 11:08 → V37.11 → V37.8 → V37.5.
Read this file first; where they disagree, the newest wins._

Repo `D:\Claude\22etsy-agent` · GitHub `NatoandUSA/etsy-agent` · VPS `~/etsy-agent`, service `etsy-web`.
Live: https://etsy.theglobalserviceteam.site

---

## 0 · Status

| | |
|---|---|
| **Tests** | **679 collected, 679 pass, 0 fail** (session start: 620) |
| **LIVE on the VPS** | `a470a9b` — service restarted 01:30:43, **probed live** |
| **Committed, NOT deployed** | `93b0b32`, `658688b` — local is 2 commits ahead of the VPS |
| **Frozen files** | zero edits, now machine-enforced by sha256 baseline |
| `PUBLISH_AUTOMATION` | `False` |

```
658688b  fix(pattern-miner): a Halloween query was mining teacher shirts        <- local only
93b0b32  feat(freshness): keyword age column + Trend Feeds back on home         <- local only
a470a9b  fix(feasibility): correct Pinterest signal contract and advisory badges  <- LIVE
9d45537  docs: handoff 2026-08-05 22:47
de2e8f1  fix(deploy): a failed download is not an empty server; stop shipping agent.db
```

> **The last two commits are not pushed and not deployed.** They are finished and tested; the
> owner had not reviewed the rendered pages yet. Deploy is §7 — and remember the service keeps
> serving the old code until someone runs the restart.

---

## 1 · What shipped and is live — `a470a9b`

**`feasibility_gate.pinterest_label()` was dead in production.** It read
`growth` / `direction` / `found` / `volume` / `interest`. `crosscheck.pinterest_signal()`
returns `{"status": ok|no_data|auth_error|no_access|error}` plus, when ok,
`{"on_growing_list": bool}`. **No key overlapped**, so every real answer fell through to
UNKNOWN and RISING was unreachable. The test passed because it asserted against invented
payloads the function never receives — trap #9 from the last handoff, in the wild.

Probed on the VPS after restart: `RISING` reachable, `on_growing_list=False → FLAT`.

`on_growing_list=False` maps to **FLAT, never NONE**. That endpoint sees only the top-50
*growing* list, so it cannot establish absence; NONE would be the zero-means-I-don't-know
mistake.

Also in that commit:

- **Badges are cache-only on the Inbox row.** `pinterest_signal()` is a live HTTP call with a
  25s timeout. Per row on 1,701 rows that is up to 1,701 requests on the first render each
  day. Proven by rendering all 1,701 rows with `socket.connect` / `getaddrinfo` /
  `requests.get` raising.
- `SUPPLIER_BLOCKED` is an **alias** of `NOT_MAKEABLE` (one object, two names) — a rename
  would orphan stored rows.
- `koozie` split out of the `mug` family. Verified a no-op on the live library.
- `workflow_spine` step 2 reports whether the live signal is configured. The `_ok`/`_todo`
  branch condition is unchanged; only the detail string gained a suffix.

**Enforcement is off structurally, not by flag** — `NOT_MAKEABLE` needs `coverage == complete`,
which no mode reaches. Measured over all 1,701 VPS rows: `NOT_MAKEABLE 0`,
`supplier_blocked 0`, `build_allowed=False 0`. `build_allowed()` has **zero external callers**,
so Pattern Miner / Build Queue / Launch Kit / Team Ops cannot be gated by it.

---

## 2 · The freeze is now baseline-aware — read this before touching frozen files

`opportunity_inbox.py` imported `feasibility_gate` in V37.12, **before** the freeze. That
wiring is legal and must stay. The rule enforced now is:

- no new **edits** to a frozen file
- no new **dependencies** on one
- no behaviour change **inside** an L0–L4 file
- **pre-freeze wiring may remain**

Pinned by `tests/test_feasibility_gate.py::test_no_frozen_file_was_edited` — sha256 over the
five frozen files, newline-normalised so it survives the CRLF/LF split with the VPS, and
content-hashed rather than git-diffed so it works from a tarball. **Mutation-tested**: a
comment was appended to `product_fit.py`, the guard went red, the file was restored.

**Unfreezing is a deliberate act: update the hash in the same commit that edits the file.**

Frozen: `opportunity_score.py` · `product_fit.py` · `ranking_engine.py` · `etsy_proof.py` ·
`opportunity_inbox.py`.

---

## 3 · `93b0b32` — freshness column + Trend Feeds on home (committed, not deployed)

Owner asked for the Trend Feeds card block back on the home page, and a timestamp on every
keyword table so staff can see how fresh the data is.

**Files:** `src/freshness.py` (new) · `tests/test_freshness.py` (new, 25 tests) ·
`src/interactive.py` · `src/build_shortlist.py` · `src/web.py`

**Trend Feeds** was never deleted — it was folded into the collapsed `🧭 All tools` drawer.
Only that one grid is promoted back out. Verified by parsing rendered HTML: 9 cards at
`<details>` depth 0, 23 still in drawers. Home gains 9 cards, not 32 — the `dashboard-cleanup`
skill's rule against re-opening the 19-card wall still holds.

**`Added` column** on Trending / Opportunities / Hidden gems / Build Queue. Takes the
**earlier** of `discovered_keywords.MIN(captured_at)` and the master's `collected_at` — the
feed usually sees a keyword days before it reaches the master, so the master alone makes
keywords look fresher than they are. Renders `NEW` / `today` / `3d` / `32d`.

> **Only ONE of the three requested timestamps exists.** `added` is real. `analyzed` is not
> separately stored (the master has one `collected_at`, no enriched-at). `ranked` happens on
> page load and is stored nowhere. So each table carries one line — *"Ranked live <time>.
> **Added** = when the keyword first entered your data; **NEW** = first seen in this pull."* —
> instead of two more columns that would repeat the render clock 40 times and look like
> measurements. **A real `analyzed` date needs a new `enriched_at` column written by
> `enrich.py`. Not built — owner's call.**

**Newest winners deliberately has no `Added` column**: its rows are Etsy *listings*, not our
keywords, so there is nothing in our base to have been added. Its existing `Age` column is the
honest per-row date; it gained only a "Pulled live" stamp.

**Batched on purpose.** One SQLite read + one CSV read per page, cached by mtime. The naive
shape is ~240 round trips across six tables. Pinned by a test asserting exactly 1 lookup for
Build Queue's open + done tables combined.

---

## 4 · `658688b` — Pattern Miner root cause, mixed clusters (committed, not deployed)

Owner's brief: build a 7-phase Pattern Miner Pro / Evidence Explorer, because staff cannot
verify the 385 listings behind "Mined 385 listings across 227 shops", and mixed clusters create
misleading patterns.

**Investigation found the mixed clusters are MANUFACTURED BY THE MATCHER, not just displayed.**

`_title_matches` used `hits >= min(2, len(qtoks))` — a **fixed floor of 2 whatever the query
length**. For the owner's real query `personalized embroidery halloween shirt`, the two
GENERIC tokens carried the match:

```
"Personalized Teacher Shirt, Comfort Colors Back to School Tee"
    shares {personalized, shirt} -> 2 -> MATCHED
```

The tokens carrying the niche — `halloween` — were **never required**. That is why the owner's
own run came back **teacher 52% · school 38% · back 33% · appreciation 24%** under a Halloween
query, and why bride/engagement tags (`future mrs`, `fiancee shirt`, `honeymoon outfit`) appear
in its winners'-structure block.

**Same defect in three places, one root cause:**

| file | function | symptom |
|---|---|---|
| `pattern_miner.py` | `_title_matches` | teacher shirts mined as Halloween |
| `pattern_miner.py` | `_view_matches` | a SERP captured from "teacher shirt" swept in wholesale |
| `feed_evidence_router.py` | `_bridge` | bride/engagement tags in winners' structure |

**Fix:** new `src/niche_match.py` splits a query into three kinds of token:

```
"personalized embroidery halloween shirt"
   modifier : personalized
   product  : embroidery, shirt
   theme    : halloween        <- the only token that says WHICH niche
```

A listing must share enough tokens **and**, when the query names a theme, at least one theme
token. `personalized` + `shirt` can no longer carry a match. A query with no theme
(`tote bag`, all product nouns) falls back to the old rule — nothing regresses.

`why(text, query)` returns `(matched, kind, shared)` with kinds
`exact` / `theme` / `product` / `modifier` / `none`. **That is already the match-type +
confidence column Phase 2 needs.**

**Files:** `src/niche_match.py` (new) · `tests/test_niche_match.py` (new, 22 tests) ·
`src/pattern_miner.py` · `src/feed_evidence_router.py`

Two guards worth keeping, both **computed, not hardcoded**:

- `test_the_old_rule_would_have_let_the_contaminants_through` reimplements the old threshold
  and asserts ≥4 fixtures leaked under it. Restore the old rule and it goes red.
- `test_the_new_rule_is_strictly_narrower_never_wider` — the fix may only REMOVE matches. A
  "fix" that pulls in different noise fails here.

---

## 5 · Pattern Miner — what remains (phases 1–7)

Owner signed off on: **fix matcher first → then Phase 1–2**, and **synthetic fixtures now,
VPS verify later**. The matcher is done. Next:

1. **Phase 1 — Evidence Health panel** at the top of `/pattern-miner`: seed keyword, mode,
   captured/unique-shop/opened-detail/HeyEtsy/review/photo counts, newest+oldest capture date,
   exact/tag/synonym/cluster-only/weak match counts, price-confidence distribution, warnings
   (mixed clusters · low opened-detail coverage · low review coverage · low price confidence ·
   stale captures · cluster-only evidence · single-listing cap).
2. **Phase 2 — full evidence table** before the conclusions, every aggregate linking back to
   its source rows (clicking "teacher 52%" filters the table).
3. **Phases 3–7** — cluster separation · Broad vs Winner Deep-Dive modes · shop-weighted vs
   listing-weighted stats · candidate cleaner · tests.

> **BLOCKER for Phase 2 — the capture schema is thinner than the spec.**
> `pattern_miner._from_import` reads only **title, price, shop, star, ad, freeship, tags, view**
> ([pattern_miner.py:175](src/pattern_miner.py#L175)). The spec asks for `views`, `favorites`,
> `favorite rate`, `conversion`, `revenue`, `shop_country`, `shop rating`, `image count`,
> `listing age`, `review count`. **Show what exists and mark the rest absent — do not
> blank-fill.** Whether VPS captures carry richer headers was never checked (the box was down).
> **Check `data/imports/etsy_search/*.json` headers on the VPS before building the table.**

> **Phase 3 note:** now that the matcher is fixed, "mixed clusters detected" reports a genuine
> multi-angle niche rather than matcher noise — a rarer and far more meaningful signal.

**Local capture data is nearly empty** — `data/imports/etsy_spy` 0 files, `etsy_search` missing,
`data/db` missing, `etsy_listings.csv` 65 rows. The 385/227 dataset is VPS-only. Phase 1–2 can
be built and unit-tested with fixtures, but "verify the 385 listings" needs the server.

Untracked in the repo root and never inspected: `22Etsy_Evidence_Exporter_v3.3/`,
`22Etsy_Evidence_Exporter_v3.4.0 (1)/`, `Etsy_4412078408_Reviews.csv`,
`HeyEtsy_4412078408_Detail.csv` — possibly a real capture sample. **Do not commit them** unless
they are deliberately part of a change.

---

## 6 · The VPS outage — what actually happened

At **2026-08-05 18:23 UTC (01:23 +07)** the site returned **Cloudflare error 1033** (tunnel
unresolvable). Measured at the time: ping 100% loss, ports 55317/22/80/443 all
closed/filtered, SSH timing out — while SSH had worked 20 minutes earlier.

**It was upstream network, not the host and not the app.** `uptime -p` after recovery read
**"up 2 weeks, 1 day"** — the box never rebooted. The service restarted at 01:30:43 and is
`active` on `a470a9b`.

**Do not chase this as an application bug if it recurs.** Diagnose in this order: `ping` →
port probe → SSH → `systemctl is-active` → `uptime`. A live-site 5xx/1033 with a 2-week
`uptime` is a network or Cloudflare-tunnel event.

---

## 7 · Deploy — corrected, the last handoff was wrong

**Handoff §4 of 2026-08-05 22:47 claimed "SSH keys and passwordless sudo are configured — this
runs from the agent session without prompts". That is FALSE.** Measured twice:
`sudo -n true` → `sudo: a password is required`.

- Claude **can** move code: `git fetch origin && git reset --hard origin/main` over
  `BatchMode=yes` works.
- Claude **cannot** restart the service. Hand the owner:

```
ssh -p 55317 etsy@51.79.200.65 "sudo systemctl restart etsy-web.service && systemctl is-active etsy-web.service"
```

**A deploy is not done when the code lands — the service runs the OLD code until that restart,
and `systemctl is-active` says `active` the whole time.** The discriminator:

```
systemctl show etsy-web.service -p ActiveEnterTimestamp --value   # service start
stat -c %y src/<file you changed>                                  # code arrival
```

If the service started BEFORE the code landed, it has not picked it up. This session sat in
exactly that state for ~40 minutes while every test on disk passed.

`git reset --hard origin/main` is **data-safe** — `keyword_data.csv`, `data/agent.db`,
`data/app.db`, `data/suppliers/supplier_products.csv` are all gitignored. **Verify with
`git check-ignore` before running it rather than assuming.**

---

## 8 · Data — the VPS is not a copy of local

| | local | VPS |
|---|---|---|
| `keyword_data.csv` | 1,701 rows | 1,701 rows, sha256 identical |
| supplier library | embroidery `partial`, **25** products | POD `partial`, **1,010** products; embroidery `unknown` |
| BUILD_NOW | 2 | 6 (four from the L1 Etsy-proof override; exports are server-only) |
| `data/agent.db` | 11,680 `discovered_keywords` | 12,543 |
| capture pool | ~empty | the real 385/227 dataset |

**Both sides are correct.** `supplier_products.csv` is gitignored and server-only — the team
imports there. This means **enforcement will trip on the VPS first**: POD is `partial` only
because `confirmed=0`. Once those 1,010 rows gain their CORE fields, coverage flips to
`complete` and the gate starts blocking for real. Watch it.

---

## 9 · Traps — do not repeat

Carried forward, still true: **a 200 proves nothing** · `class="stgnav"` is not a reliable
phase marker · do not cache `/trending`/`/opportunities`/`/gems` · `"learn"` is ambiguous ·
`_h_esc` escapes `&` → `&amp;` · never say "deploy unconfirmed" from a doc — probe · a probe
can be non-discriminating · a score floor is worse than a wrong score — check the
**distribution** · "unknown" and "no match" are different answers · derived data can silently
drop source data · **a zero from an API usually means "I don't know"** · **a failed fetch is
not an empty source** · **a test that passes against a known-bad input is not a test that pins
the invariant**.

Added this session:

1. **A function can be dead in production while its tests pass — if the tests invent the input
   shape.** `pinterest_label` read five keys its own data source never emits. **Test against the
   literal payloads the real callee returns**, not a plausible dict.
2. **A fixed threshold over a variable-length query is a bug waiting to happen.**
   `hits >= min(2, len(qtoks))` let the two most generic tokens satisfy a four-token query.
   Ask *which* tokens matched, not how many.
3. **Generic tokens must never carry a match.** `personalized` and `shirt` appear in most POD
   titles; they cannot be the reason two listings are the same niche.
4. **The same defect can live in three functions across two files.** Fixing one leaves the
   symptom. Grep for the *shape* of the bug, not its location.
5. **A fix that changes a filter may only narrow it.** Pin that with a test, or a "fix" can
   quietly swap one contamination for another.
6. **A guard that cannot go red is worthless — mutate the input and watch it fail.** Done for
   the frozen-file hash; the earlier deploy-test file shipped three vacuous assertions without it.
7. **Count the thing you mean.** A perf test counting raw `sqlite3.connect` calls also counted
   `analyze()`'s own connections and passed or failed depending on test order. Count calls into
   the module under test.
8. **`is-active` cannot discriminate a release.** Compare service start time against code mtime.
9. **A live-site error with a 2-week `uptime` is a network event**, not your deploy.
10. **Only build the columns the data supports.** Three timestamps were requested; one exists.
    Printing the render clock per row would look like 40 measurements.
11. **A handoff is a hypothesis.** This one corrected the previous handoff's passwordless-sudo
    claim and its "only the `.ps1` is safe" warning (`de2e8f1` fixed both scripts).

---

## 10 · How the owner wants this work run

Unchanged and honoured: **review first, propose a ranked plan, get sign-off, then fix in that
order.** No broad refactors, no unrelated modules. *"Do not blind fix — check the code, check
the process."* — and **read the data too.**

**Show measurements, not assertions.** When a claim turns out to be wrong, say so plainly and
correct it. This session's most valuable findings both came from re-reviewing work that had
already been called done: the Pinterest contract, and the Pattern Miner matcher under a request
that was framed as a UI problem.

**English-only output · never auto-publish a listing · `PUBLISH_AUTOMATION` stays False ·
no Etsy API/OAuth/publish automation.**
