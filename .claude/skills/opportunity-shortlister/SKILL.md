---
name: opportunity-shortlister
description: Rank the current YTuong Trending / Opportunities / Hidden Gems data into an actionable top 5-10 shortlist for POD or Embroidery, using the tool's REAL scores (never invented ones), with a Verdict (GO / CONDITIONAL / WATCH / SKIP) + reason + next action, ready to feed the Research Queue. Use for "shortlist best opportunities", "filter top niches", "what should I build next", or daily research. Not for a single-niche deep decision (use /should-i-sell) or a weekly market digest (use /whats-hot).
---

# Opportunity Shortlister

**Goal**: turn the *current* YTuong data into a ranked, actionable shortlist of the
best opportunities. Fast, transparent, data-first. **This skill produces a shortlist
and next actions, not code and not a publish decision.**

## Ground everything in the tool's REAL data (do this first)

Do NOT invent rows or numbers. Pull from the actual modules in this repo:

- **Candidates**: `src/ytrends_mcp.py` -> `trending_keywords()`, `hidden_gems()`,
  `scout_opportunities()`, `market_snapshot()`; or the dashboard's `/trending` /
  `/opportunities` pages; or a fresh import. These already carry real YTrends fields
  (momentum, competition_level, conversion, listing counts).
- **Product fit + junk filter**: `src/product_fit.py` `classify(kw, mode)` -> fit
  status + `launchable`. Only rank launchable fits (POD_FIT / EMBROIDERY_FIT /
  JEWELRY_FIT / ACRYLIC_FIT / THEME_FIT_READY). Drop shop-names, policy, digital,
  broad seeds; surface THEME_FIT_NEEDS_PRODUCT separately as "pick a product first".
- **Clusters**: `src/clusters.py` `build_opportunity_clusters()` -> rank the
  *cluster* (one sellable listing) above single keywords.
- **Trademark**: `src/trademark.py` `check(kw)` -> flag HIGH (never launch) / CAUTION
  immediately.
- **Cross-check**: `src/crosscheck.py` `confirm(kw)` -> Google Trends direction
  (live); Pinterest / X only if their tokens are set (else mark "off").
- **Real scores**: the workspace engine (`/run`) computes the 8 scores + Overall +
  Verdict. Prefer those. On the Opportunities/Trending lists, use the real per-row
  YTrends fields. **If a signal is missing, mark it `pending` and lower confidence —
  never fabricate a number.**
- **Seasonality**: `src/seasonal.py` `upcoming_holidays()`.
- **Private boost (optional)**: `src/learning.py` — only if real logged wins/losses
  exist; otherwise omit, don't guess.

Mode: `pod` | `embroidery` | `both` (default: **embroidery**, the shop's focus).

## Composite score (0-100)

Rank by a weighted blend of the tool's real signals. These weights are the
*shortlisting lens*; the numbers themselves come from the modules above, and every
score shown must match what the dashboard would show (no parallel math):

- Demand 25% · Momentum 20% · Competition 20% (lower concentration = higher) ·
  Conversion 15% · Design room 10% · Production feasibility (mode match) 5% ·
  Seasonality 5%.
- **Private boost** (bonus, only from real learning data).

Always show the **breakdown**, and mark any `pending` signal explicitly.

**Verdict**: **GO** >=75 · **CONDITIONAL** 60-74 (validate with 1-2 tests) ·
**WATCH** 45-59 (monitor 1-2 weeks) · **SKIP** <45.

## Output format (always use this)

1. **Summary table** — one row per shortlisted opportunity:

   `Rank | Cluster/Keyword | Mode | Composite | Verdict | Top signal | Weakest | TM | Next action`

2. **Per-opportunity breakdown** (top 5-10), each with:
   - the score breakdown (Demand/Momentum/Competition/Conversion/Design/Production/Season + any `pending`)
   - trademark flag (HIGH/CAUTION/OK) and cross-check direction
   - 2-3 line reason
   - **Next action** (e.g. "Confirm & Assign in Embroidery -> supplier check")

3. **CSV block** (export-ready) with the same columns as the summary table.

## Rules
- Always show the composite **breakdown**; never a bare score.
- **Never fabricate** a signal — missing = `pending`, and say so. (Same rule the
  cluster engine follows.)
- Flag trademark risks immediately; HIGH is never launchable.
- Prefer **product + theme clusters** over single keywords.
- Embroidery: prioritize stitch-safe themes (bold shapes, <=6 colors, readable text).
- Never recommend launch without a supplier + profit check — the shortlist ends at
  "worth building", not "publish".
- Bilingual (Vietnamese + English) output if the user's query is Vietnamese.

## Not this skill
- One niche, deep GO/NO-GO -> `/should-i-sell`.
- Weekly "what's rising / cooling" digest -> `/whats-hot`.
- Publish readiness -> the workspace publish gate (never here).

## Integration
- Run after a YTuong import or daily run.
- Feed the GO / CONDITIONAL winners into the **Research Queue** (via Confirm &
  Assign, Embroidery mode) -> Workspace.
