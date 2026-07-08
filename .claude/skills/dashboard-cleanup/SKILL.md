---
name: dashboard-cleanup
description: Internal checklist. Keep the dashboard tidy and logical — above-the-fold summary, collapsible detail, no Archive card, no clutter. Use when touching the home page, the workspace layout, or adding a new card/section.
---

# Dashboard Cleanup (internal)

## Files to inspect
`src/web.py` (home `index`, tool cards, CSS), `src/workspace.py` (section order,
hero glance chips).

## Rules
- Home page must NOT show an "Archive — reports" card; Cheat Sheet stays.
- Above the fold on a run: mode, keyword, verdict, publish status, main reason,
  next action (the hero glance chips: Overall / Can-We-Win / Launch / First image /
  Offer / Publish-ready / TM / Next).
- Keep the grouped section order (Decision → Listing → Design → Do-next → Export);
  do not scatter or duplicate sections.
- New cards go in the right home group (Discover / Library / Execute & improve).
- Every secondary page has the sticky Home button (`.rbar` sticky).

## Pass/fail
- `test_home_is_clean` passes (no Archive, has Cheat Sheet + core cards).
- No duplicated report blocks, no dead links, no more than a tidy row of buttons.

## What NOT to do
- Do not re-introduce the Archive card or big static report lists on the home page.
- Do not do a risky full re-layout of a working page just to reorder sections —
  prefer collapsible sections and small, safe moves.
