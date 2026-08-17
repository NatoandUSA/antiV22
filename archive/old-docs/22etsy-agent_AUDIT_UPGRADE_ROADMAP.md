# 22etsy-agent — Audit & Upgrade Roadmap (v1)

**Scope:** full code audit of the `22etsy-agent` platform (V28.1) by 5 specialist reviewers reading the real `src/` modules, tests, and skills.
**Goal:** make it the best tool for the team — more sales, stronger competitive edge, correct money math, safe and reliable.
**Date:** July 2026 · Etsy fees & SEO rules verified for 2026.

---

## First: is v2 / the HTML "Studio" relevant?

No. Your `22etsy-agent` already does everything the HTML Studio did — and for real: live ytuong data, a database, a publish gate, team roles, reports, learning, deploy. **Retire the Studio.** All effort below goes into the real platform. The Studio's only lasting value was surfacing a few rules (keyword-in-first-40-chars, plural-tag dedupe) that — it turns out — your platform *also* doesn't fully enforce yet. Those are now fixes below, in the right place.

---

## Overall assessment

This is a genuinely strong, disciplined system. It refuses to invent numbers, it never auto-publishes, the publish gate is real, auth is mostly correct, and the code shows real restraint (caching, backoff, fail-fast on API drift). It is far above typical "Etsy generator" tools.

But it has **three classes of problem that silently cost you money or sales**, and they're the priority:

1. **The money math is optimistic.** Profit is overstated (a missing fee) and the "raise price / publish-ready" decisions use the wrong margin — so the tool green-lights listings that actually miss your 35–40% target.
2. **A few decision bugs point the team at the wrong work.** Declining niches can be labeled "CONFIRMED," the "can we win" edge is essentially the same optimistic guess for every niche, and some generated titles don't even contain the main keyword.
3. **Reliability + security gaps.** A data-source outage can wipe your keyword file; several POST routes and one GET delete lack CSRF; an ADMIN can promote themselves to OWNER.

None of these are visible day-to-day — which is exactly why they're dangerous. Fix these first, then invest in the competitive-edge upgrades that grow sales.

---

## The critical bug list (silent value-losers — fix first)

| # | Problem | Where | Why it hurts |
|---|---|---|---|
| 1 | **Currency-conversion fee (~2.5%) missing** from profit math | `profit.py:16-54` | Every net-profit figure is overstated ~2.5% of price. You're paid out in VND on USD sales — this fee always applies. |
| 2 | **"Raise price" & publish-gate use the wrong margin** — gross margin / flat `$6`, not net vs 35–40% | `feedback.py:71-85`, `publish_gate.py:110` | A listing showing 35% "margin" actually nets ~18–20%. The tool approves sub-target products as profitable. |
| 3 | **Declining/flat niches can be labeled CONFIRMED** | `signals.py:87-88` | STABLE or STABLE+DECLINING with no RISING falls through to a green "CONFIRMED" — sends the team to build dying niches. |
| 4 | **A source outage overwrites `keyword_data.csv` with an empty file** | `harvest.py:299` | One bad ytuong pull wipes the fuel for every report until the next good pull. No guard. |
| 5 | **Main keyword not guaranteed in the title** (no first-40-char rule; 3 shipped packages omit the primary phrase entirely) | `validators.py:28`, `product_manager.py:453-479` | Relevancy is the #1 Etsy 2026 ranking signal and mobile shows ~40 chars. A title without its keyword up front loses the ranking. |
| 6 | **CSRF holes:** GET delete with no token; token checked on only ~5 of ~24 POST routes | `web.py:1118`, `web.py:1989` | A single malicious link can delete data; the app looks protected but isn't. |
| 7 | **Privilege escalation:** an ADMIN can promote anyone (incl. themselves) to OWNER | `web.py:2543-2555` | Any admin account can seize full control. |

---

## Domain findings (condensed)

**A · Listing & SEO generation.** Good: `validate_title`/`validate_tags` enforce ≤140, exactly-13, ≤20 chars, and a smart reordered-near-dup catch. Weak: no keyword-in-first-40-chars; `listing_factory.write_pack` **bypasses the publish gate and validators entirely** (a second, ungated generator path, `listing_factory.py:130-255`); no plural dedupe, no "≥3 tags echo the title," no "≥2 occasion/buyer" enforcement; trademark check has a precedence bug and misses slogans (`trademark.py:58`).

**B · Discovery & competition edge.** Good: `age_profile()` reads the *age of winning listings* to judge if a new shop can rank (`discover.py:236`) — your single best winnability signal; sources stay honest ("no data" not fake numbers). Weak: `can_we_win()` is hardcoded optimism — every niche scores ~70–80 "we can win" (`workspace.py:428`); `edge.py` is a static checklist that gives near-identical advice for every niche; `scoring.py` is orphaned dead code; clusters carry no winnability score.

**C · Data ingestion.** Good: fail-fast on API drift, backoff, per-day cache, staleness gate exists. Weak: **single-vendor (ytuong)** with no independent fallback; empty-pull overwrite (bug #4); imported records aren't range/schema-validated (conversion>1, price=0 pass); freshness uses server-local date with a 7-day window against a 6-hour refresh, so week-old data reads "fresh."

**D · Web app & team UX.** Good: never-auto-publish is genuinely enforced server-side (`web.py:632`); auth fundamentals solid (pbkdf2, lockout, HttpOnly/SameSite, CSP); Command Center already collapses the pipeline to one keyword. Weak: CSRF + privilege-escalation holes (bugs #6, #7); **the mandatory supplier step has no web panel — it tells non-dev staff to run `py main.py supplier` in a terminal** (`workspace.py:1002`); a module-level `_last` global can cross-wire two users' verdicts under concurrency; 181KB single web file is a regression risk.

**E · Profit, suppliers, learning, tests.** Good: transaction/processing/listing fees match 2026; embroidery vs POD supplier matching is correct and never invents data; the learning note *does* nudge real pick scores. Weak: money bugs #1–#2; supplier net-profit is logged but never used in supplier scoring (cosmetic learning); image/tag magnitudes recorded but never read; only one profit test, and it locks in the wrong (fee-missing) number (`selftest.py:891`).

---

## Ranked upgrade roadmap

### P0 — Fix First (small, safe, high value; ~1 focused session)
These are correctness/safety fixes. Low risk, mostly small edits, each independently testable via your `selftest`.

1. **Add the currency-conversion fee (~2.5%)** to `profit.compute()`; update the selftest expected value. *(bug #1)*
2. **Make margin decisions use true net vs 35–40%** in `feedback.py` and `publish_gate.py`. *(bug #2)*
3. **Fix the `signals.py` verdict** so STABLE/DECLINING never returns CONFIRMED. *(bug #3)*
4. **Guard `harvest.py`** to keep the prior CSV when a pull is empty/below a floor. *(bug #4)*
5. **Enforce keyword-in-first-40-chars** in `validate_title` (pass the primary keyword in); this also auto-catches the 3 broken package titles. *(bug #5)*
6. **Blanket CSRF** via one `before_request` + convert the GET delete to POST. *(bug #6)*
7. **Lock role changes** — forbid granting OWNER unless the actor is OWNER; block self-role-change. *(bug #7)*
8. **Offsite-ads fee on item+shipping** (not item only), in `profit.py`.

### P1 — Grow sales & beat competitors (medium effort)
9. **Real competitor-diff edge engine** — replace the static `edge.py`/`can_we_win` constants with per-niche gaps *measured* from the actual competitor audit (who lacks video, personalization, ≥7 photos, weak tags), then rank the exploitable weakness. *This is the single biggest "beat competitor" lever — right now the tool gives the same advice for every niche.*
10. **Route `listing_factory` through the publish gate + validators** — kill the ungated second path so every listing meets one standard.
11. **Tag-quality rules** — plural dedupe, ≥3 title-echo, ≥2 occasion/buyer.
12. **Score the clusters** with one calibrated engine (age_profile + saturation + conversion); delete orphan `scoring.py`.
13. **In-app Supplier panel** — remove the terminal step so the pipeline is fully button-driven.
14. **Make the learning loop real** — feed stored supplier net-profit into supplier scoring, and weight tag/image patterns by orders, not mere presence.

### P2 — Foundations (larger, do after P0/P1)
15. **Second, independent data source** so ytuong isn't a single point of failure; surface a visible "data degraded" state.
16. **Embroidery producibility scorer** in `product_fit` (color count / detail / thin-line risk), not just the word "embroidery."
17. **Trend velocity over time** (rising vs already-peaked) + auto-rolling seasonal dates.
18. **Templatize `web.py`** into Jinja + blueprints by pipeline stage; production WSGI server + pinned secret key.
19. **Profit-path tests** (refund, offsite, currency) so fee regressions can't slip in.

---

## Best next action

Do the **P0 Fix-First batch** now — it stops the tool from overstating profit, approving sub-target listings, green-lighting declining niches, wiping data, and leaking security. It's small, reversible, and each fix is covered by your existing `selftest`. Then move to **#9 (real edge engine)**, which is the biggest sales/competitive lever.

Recommended sequence: **P0 (safety + money) → #9 edge engine → #10–#11 listing standard → #13 supplier panel.**
