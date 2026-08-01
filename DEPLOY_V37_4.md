# Deploy — V37.4 (Evidence Router + Team Command Center)

All files below are already on the PC at `D:\Claude\22etsy-agent`. Nothing is git-committed yet.
No new Python dependencies, no DB schema change, no extension change — a normal Flask deploy.

## Files changed this release

**New**
- `src/feed_evidence_router.py`  (stdlib only — no pip install needed)
- `tests/test_feed_evidence_router.py`

**Edited**
- `src/web.py`            (import lanes + /imports evidence card + Team Command Center + subpage polish)
- `src/pattern_miner.py`  (review-evidence join)
- `src/keyword_lab.py`    (review-derived candidates)
- `src/interactive.py`    (Pattern Miner "Buyer voice" + Photo Studio "prove this")
- `src/photo_brief.py`    (evidence-driven prove notes)
- `tests/test_routes.py`  (Team Command Center + subpage tests)

**Docs / analysis (optional to commit)**
- `removal_plan.md`, `cleanup_inventory.json`  (cleanup audit)
- `v38_backtest.html`, `v38_backtest.py`, `v38_backtest_result.json`  (v38 math backtest)

## Step 1 — PC (PowerShell). Each command on its OWN line, never `&&`.

```powershell
cd D:\Claude\22etsy-agent
py -m pytest -q
```

Expected: green except the known offline non-bug `tests/test_integration.py::test_full_selftest_pipeline`
(needs a live MCP/YTrends connection — leave it). If anything else fails, stop and tell me.

Then commit + push:

```powershell
git add src/feed_evidence_router.py src/web.py src/pattern_miner.py src/keyword_lab.py src/interactive.py src/photo_brief.py tests/test_feed_evidence_router.py tests/test_routes.py
git commit -m "V37.4: Feed Center Evidence Router + workflow wiring + Team Command Center + subpage polish"
git push origin main
```

(Optional — commit the audit/backtest docs separately:)

```powershell
git add removal_plan.md cleanup_inventory.json v38_backtest.html v38_backtest.py v38_backtest_result.json DEPLOY_V37_4.md
git commit -m "docs: cleanup audit + v38 math backtest"
git push origin main
```

## Step 2 — VPS (SSH, bash)

```bash
cd ~/etsy-agent
git fetch origin
git reset --hard origin/main
sudo systemctl restart etsy-web
```

## Step 3 — Verify live (logged in)

- `/team` shows the Team Command Center (KPI strip, Today board, pipeline, activity).
- `/imports` shows the "Listing evidence (v3.4.0 lanes)" card once a HeyEtsy Detail / Etsy Reviews CSV is dropped.
- `/me/tasks` grouped Overdue / Today / This week / Awaiting review / Open / Done.
- `/admin/activity` filter form + Export CSV.
- `PUBLISH_AUTOMATION` still false; ranking math unchanged.

## Notes
- The new evidence lanes (`data/imports/etsy_listing_detail|reviews|review_summary|listing_keyword_map/`)
  auto-create on first import — no migration.
- Not in this release (parked): v38 ranking-math changes (backtest says don't adopt as written),
  and the `git rm src/design_analyzer.py tests/test_design_analyzer.py` cleanup (do that as its own commit).
