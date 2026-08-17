# 22etsy-agent — Handoff · 2026-08-06 02:49 (+07)

_Session owner: Alex (Hue, Vietnam). **Supersedes `22etsy_agent_handoff_2026-08-06_0145.md`**,
which supersedes 2026-08-05 22:47 → 14:26 → 2026-08-04 00:16 → V37.11 → V37.8 → V37.5.
Read this file first; where they disagree, the newest wins._

Repo `D:\Claude\22etsy-agent` · GitHub `NatoandUSA/etsy-agent` · VPS `~/etsy-agent`, service `etsy-web`.
Live: https://etsy.theglobalserviceteam.site

---

## 0 · Status

| | |
|---|---|
| **Tests** | **759 collected, 759 pass, 0 fail** (session start: 620) |
| **LIVE on the VPS** | `a470a9b` only — service `active` |
| **Local** | **6 commits ahead, none pushed, none deployed** — owner is reviewing rendered pages |
| **Frozen files** | zero edits, enforced by sha256 baseline |
| `PUBLISH_AUTOMATION` | `False` |

```
098573e  fix(pattern-miner): close the DB fast-path hole that bypassed Phase 0   <- local only
3744533  feat(pattern-miner): Evidence Health panel (Phase 1)                    <- local only
77b4087  fix(pattern-miner): require niche theme match (Phase 0 refinement)      <- local only
ecf406a  docs: handoff 2026-08-06 01:45                                          <- local only
658688b  fix(pattern-miner): a Halloween query was mining teacher shirts         <- local only
93b0b32  feat(freshness): keyword age column + Trend Feeds on home               <- local only
a470a9b  fix(feasibility): Pinterest signal contract + advisory badges           <- LIVE
```

> **Deploy is deliberately held.** The owner wants the rendered pages reviewed first. Do not
> push or deploy without being asked. §6 has the commands and the trap.

---

## 1 · Where Pattern Miner work stands

Owner's brief: a 7-phase Pattern Miner Pro / Evidence Explorer, because staff cannot verify the
385 listings behind "Mined 385 listings across 227 shops", and mixed clusters produce misleading
patterns.

| Phase | State |
|---|---|
| **0 · input correctness** | **DONE + protected** — `658688b`, `77b4087`, `098573e` |
| **1 · Evidence Health panel** | **DONE** — `3744533` |
| **2 · evidence table** | **NOT STARTED.** First step agreed: widen the capture parser (§4) |
| 3 · cluster separation | not started |
| 4 · broad vs winner deep-dive | not started |
| 5 · shop-weighted stats | not started |
| 6 · candidate cleaner | not started |
| 7 · tests | rolling; each phase ships its own |

---

## 2 · Phase 0 — the same defect lived in FOUR files

Pattern Miner matched a listing when it shared >=2 query tokens —
`hits >= min(2, len(qtoks))`, a fixed floor of 2 whatever the query length. For the owner's real
query `personalized embroidery halloween shirt` the two GENERIC tokens carried the match:

```
"Personalized Teacher Shirt, Comfort Colors Back to School Tee"
    shares {personalized, shirt} -> 2 -> MATCHED
```

That is why the owner's run returned **teacher 52% · school 38% · back 33% · appreciation 24%**
under a Halloween query, with bride/engagement tags in the winners'-structure block.

| file | function | symptom |
|---|---|---|
| `pattern_miner.py` | `_title_matches` | teacher shirts mined as Halloween |
| `pattern_miner.py` | `_view_matches` | a SERP captured from "teacher shirt" swept in wholesale |
| `feed_evidence_router.py` | `_bridge` | bride/engagement tags in winners' structure |
| `data_store.py` | `_kw_match` | **found last** — see §3, it made Phase 0 a no-op in production |

**`src/niche_match.py` is now the one rule.** Four buckets decide what a token can prove:

```
modifier   personalized, custom, name, monogram, gift   proves nothing
style      crew, v-neck, oversized, comfort, colors     proves nothing
technique  embroidery, embroidered, printed, engraved   HOW it is made
product    shirt, hoodie, tote, cap, mug, blanket       WHAT it is
theme      halloween, teacher, nurse, bride, birthday   WHICH niche
```

> Three bucket traps found by testing the owner's own edge cases, all of which broke the FIRST
> version of the fix:
> * **`embroidery` is a TECHNIQUE, not a product.** `product_fit`'s noun set contains it, so an
>   embroidered mug satisfied the product requirement for "embroidered hoodie". `TECHNIQUES` is
>   subtracted from that set.
> * **`crew` is a CUT, not a niche.** In the residual theme bucket it would be *required*, so
>   "custom crew t-shirt" rejected a plain "Custom Tee".
> * **`handbag` is missing from `product_fit`'s nouns** and also read as a theme, so "custom name
>   tote handbag" rejected "Personalized Name Tote Bag". `bucket()` now asks
>   `supplier_ops.product_family()` before falling through to theme.

Rule: **themes present → a theme must match; else products present → a product must match**
(family-aware, so tee/t-shirt/shirt count as one another); else overall overlap only. The
historical overlap floor still applies, so the rule is strictly narrower and can only ever
REMOVE matches.

`why(text, query)` returns `(matched, reason, shared_tokens)` with reasons
`exact · theme · synonym · product_only · modifier_only · rejected_missing_theme ·
rejected_product_mismatch · none`, plus `serp_view` from the audit. **That is already the
match-type + confidence column Phase 2 needs — do not build a second one.**

Two guards, both **computed, not hardcoded**, and both **mutation-tested** (restoring the old
rule turns 20 tests red):

- `test_the_old_rule_would_have_let_the_contaminants_through`
- `test_the_new_rule_is_strictly_narrower_never_wider`

---

## 3 · The DB fast-path — Phase 0 was a no-op in production for two commits

`load_batch` tries the SQLite index **first**. `data_store._kw_match` was a fourth copy of the
old rule, so a populated index bypassed the entire fix. Measured against stored SERP names:

```
personalized halloween shirt      -> pulled in   correct
personalized teacher shirt        -> pulled in   contaminant
personalized dog mom shirt        -> pulled in   contaminant
embroidered halloween sweatshirt  -> EXCLUDED    the actual niche
```

It over-included contaminants **and dropped real matches**.

Fixed at both levels the index works at: `_kw_match` uses the shared rule when selecting which
SEARCHES to pull (falling back to old behaviour if `niche_match` cannot be imported, so a broken
import degrades to today's results rather than zero rows), and `_from_db` post-filters the
returned ROWS by title, because the index selects whole SERPs and its listings arrive unfiltered.

### The VPS index is STALE — measured, not assumed

```
data/db/etsy.db   2026-08-02 11:51   2.6 MB
PRAGMA user_version = 0        (built before the rule was versioned)
6,460 listings across 102 distinct source_keyword searches
```

`niche_match.MATCHER_VERSION = 2` is stamped into `PRAGMA user_version` — no schema migration
needed. The read-time filters mean the **miner is correct regardless**, but the panel will keep
flagging the index stale until it is rebuilt.

> **Rebuilding `data/db/etsy.db` on the VPS is an unrun operational step.** It rewrites a
> server-only file. Nobody has done it; do not do it without asking.

---

## 4 · Phase 1 — Evidence Health panel (`3744533`)

Renders **above** the markdown summary on `/pattern-miner`, verified through the Flask client
(200; panel at byte 35763, `<article class="md">` at 38812). Five labelled layers: SERP capture ·
why each listing matched · opened-listing/HeyEtsy/review · recency & price confidence · field
coverage.

`pattern_miner.audit()` classifies EVERY captured row with `niche_match.why()` — the same call
that does the filtering — so the panel can never disagree with the batch it describes (pinned by
a test). `audit()` **deliberately reverses `load_batch`'s source order** and prefers RAW captures,
because they are the only layer that still contains the rejected rows.

Honest-null rules the panel enforces:

- `source=db` → `rejected: n/a`, `rejects_observable: false`, and the warning *"DB pre-filtered
  source — rejected rows are not observable. Rebuild the index after matcher changes before
  trusting strict-match counts."* **Never a fabricated `0`** — the index cannot know what it
  never returned.
- A stale index raises its own warning and can never be labelled a strong sample, however many
  rows it holds.
- Warnings only fire on what is observable. Low-detail triggers below 10% coverage, so 1 opened
  behind 4 matched (25%) stays silent and 6 behind 385 (1.6%) does not — **both directions are
  tested.** A warning that fires on good coverage teaches staff to ignore the panel.
- Review evidence carries an explicit "does not change the market score" chip.

### The capture schema is far richer than the PC suggests — measured on the VPS

A header sweep found **109 distinct columns**, not the 8 the parser reads:

```
price 150 · country 140 · listing_id 130 · title 130 · url 128 · sold_24h 123 · views_24h 123
star_seller 118 · shop 115 · he_sold 114 · he_views 114 · he_revenue_usd 114 · he_tags 114
price_num 113 · price_was 113 · reviews 113 · ad 113 · bestseller 113 · free_shipping 113
he_favorites 113 · he_fav_pct 113 · he_created 113 · conversion_pct 106 · age_days 105
he_views_avg 105 · shop_daily_sold 105 · he_categories 105 · price_usd 18 · favorites_24h 18
```

> A hardcoded `NOT_IN_SERP` list built from the local pool shipped in the first cut of the panel
> and was **wrong**: it would have said *"views: Not captured in SERP data"* while 123 capture
> files carried it. A false negative is worse than a blank — it stops staff looking for data they
> already have. `field_availability()` now measures `pattern_miner.capture_fields()` and lists
> what IS captured alongside what is not. Only `shop_rating` and `image_count` are genuinely
> absent from the SERP layer.

---

## 5 · Phase 2 — start here, and what to watch

**First step (agreed with the owner): widen the capture parser.** `_from_import` maps only 8 of
those 109 columns into its row dict; revenue, views, favourites, conversion, country, review
count, listing age, `listing_id` and `url` are discarded at parse time. **The table does not need
new capture work — it needs the parser widened.** Build that before any table markup, or the
table renders a wall of "not captured" against data the shop already holds.

Two things to resolve as part of it, neither settled:

1. **Header drift across extension generations.** Column counts differ (`country` 140,
   `listing_id` 130, `views_24h` 123, `age_days` 105) and parallel spellings exist
   (`sold_24h` 123 vs `sold 24h` 36; `price_num` 113 vs `price_usd` 18). Captures come from at
   least three extension versions. **The parser needs alias resolution, not a fixed column list**,
   and rows from older captures will legitimately lack newer fields — that is **per-row**
   availability, not per-pool. `evidence_health.FIELD_ALIASES` already holds a starting alias map.
2. **`etsy_listing_reviews/` does not exist on the VPS** (81 `etsy_listing_detail` + 77
   `etsy_listing_structure` files do). The review lane is empty there, so review-derived panel
   counts will read 0 legitimately.

Remaining Phase 2 scope after the parser: the sortable/filterable table, every aggregate linking
back to its source rows (clicking "teacher 52%" filters the table). Phase 3's "mixed clusters
detected" warning now reports a genuine multi-angle niche rather than matcher noise.

---

## 6 · Deploy — held, and the trap

**The owner has NOT approved deploying the 6 stacked commits.** When asked:

```bash
git push origin HEAD:main
ssh -p 55317 etsy@51.79.200.65 "cd ~/etsy-agent && git fetch origin && git reset --hard origin/main"
# then, by the OWNER — Claude cannot: sudo -n true -> "a password is required"
ssh -p 55317 etsy@51.79.200.65 "sudo systemctl restart etsy-web.service && systemctl is-active etsy-web.service"
```

**A deploy is not done when the code lands — the service runs the OLD code until that restart,
and `systemctl is-active` says `active` the whole time.** The discriminator:

```
systemctl show etsy-web.service -p ActiveEnterTimestamp --value   # service start
stat -c %y src/<file you changed>                                  # code arrival
```

Started BEFORE the code landed → it has not picked it up. Last session sat in exactly that state
for ~40 minutes while every test on disk passed.

`git reset --hard origin/main` is **data-safe** — `keyword_data.csv`, `data/agent.db`,
`data/app.db`, `data/suppliers/supplier_products.csv`, `data/db/etsy.db` are all gitignored.
**Verify with `git check-ignore` rather than assuming.**

---

## 7 · Data — the VPS is not a copy of local

| | local | VPS |
|---|---|---|
| `keyword_data.csv` | 1,701 rows | 1,701, sha256 identical |
| supplier library | embroidery `partial`, 25 products | POD `partial`, **1,010** products |
| capture pool | `etsy_spy` 0 files, `etsy_search` absent | **156 spy + 12 search**, 109 headers |
| `data/db/etsy.db` | **absent** | 2.6 MB, 6,460 listings, 102 searches, **stale** |
| opened-listing lanes | 1 proof file | 81 detail + 77 structure, **no reviews dir** |
| BUILD_NOW | 2 | 6 (four from the L1 Etsy-proof override) |

**Both sides are correct.** Capture and supplier data are gitignored and server-only. Phase 1–2
cannot be verified against the real 385-listing dataset from the PC — only fixtures.

**Enforcement will trip on the VPS first:** POD supplier coverage is `partial` only because
`confirmed=0`. When those 1,010 rows gain their CORE fields, coverage flips to `complete` and the
supplier gate starts blocking for real. Watch it.

---

## 8 · Traps — do not repeat

Carried forward: **a 200 proves nothing** · never say "deploy unconfirmed" from a doc — probe ·
a probe can be non-discriminating · **"unknown" and "no match" are different answers** · a score
floor is worse than a wrong score — check the distribution · **a zero from an API usually means
"I don't know"** · a failed fetch is not an empty source · **a test that passes against a
known-bad input is not a test that pins the invariant** · `_h_esc` escapes `&` → `&amp;`.

Added this session:

1. **The same defect can live in FOUR files across three modules.** Fixing three left the fourth
   silently bypassing the fix in production. **Grep for the SHAPE of the bug, not its location** —
   `min(2, len(` found the last one.
2. **Fix the fastest path first, or the fix is theatre.** `load_batch` tries the index first, so
   the three "fixed" copies never ran on a populated server.
3. **A function can be dead in production while its tests pass — if the tests invent the input
   shape.** Test against the literal payloads the real callee returns.
4. **A fixed threshold over a variable-length query is a bug waiting to happen.** Ask *which*
   tokens matched, not how many.
5. **Generic tokens must never carry a match.** `personalized` and `shirt` are in most POD titles.
6. **Do not hardcode a schema you have only seen locally.** The panel's "not captured" list was
   built from a near-empty PC pool and would have denied 123 files' worth of `views_24h`.
   **A false "not available" is worse than a blank cell.**
7. **A fix that changes a filter may only narrow it** — pin it, or a "fix" swaps one contamination
   for another.
8. **A guard that cannot go red is worthless.** Mutate the input and watch it fail. Done for the
   frozen-file hash and the matcher.
9. **Count the thing you mean.** A perf test counting raw `sqlite3.connect` also counted
   `analyze()`'s own connections and passed or failed by test order.
10. **A warning that fires on good data teaches staff to ignore the panel.** Test both directions
    of every threshold.
11. **`is-active` cannot discriminate a release.** Compare service start against code mtime.
12. **A live-site error with a 2-week `uptime` is a network event**, not your deploy.
13. **Only build the columns the data supports.** Three timestamps were requested; one exists.
14. **A handoff is a hypothesis.** The 22:47 one claimed passwordless sudo works — it does not.

---

## 9 · How the owner wants this work run

Unchanged and honoured: **review first, propose a ranked plan, get sign-off, then fix in that
order.** No broad refactors, no unrelated modules. *"Do not blind fix — check the code, check the
process."* — and **read the data too.**

**Show measurements, not assertions.** Every finding in §2–§4 came from a probe, not a reading.
The owner catches real problems in proposed work (the `embroidery` bucket, the DB fast-path risk)
— **take those seriously and go verify rather than agreeing.** Both turned out to be worse than
first described.

**English-only output · never auto-publish a listing · `PUBLISH_AUTOMATION` stays False ·
no Etsy API/OAuth/publish automation · do not touch Launch Kit · supplier enforcement stays off ·
frozen L0–L4 files are frozen.**
