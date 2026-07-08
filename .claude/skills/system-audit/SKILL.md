---
name: system-audit
description: Internal maintenance checklist. Run a full audit of the Etsy Product Manager before saying "done" — verify commands, routes, data, publish-gate safety, and the no-auto-publish rule. Use when asked to audit, review, "is it ready", pre-release check, or before committing a large change.
---

# System Audit (internal)

Do NOT report the tool as ready until every step below passes or the failure is documented.

## When to use
Before delivering a release, after a large change, or when the user asks for an audit / "is it safe for the team".

## Files to inspect
`main.py`, `src/web.py`, `src/workspace.py`, `src/publish_gate.py`,
`src/feedback.py`, `src/learning.py`, `src/alerts.py`, `src/tracking.py`,
`src/profit.py`, `src/launchpad.py`, `src/supplier_ops.py`, `src/ops.py`,
`src/data_validate.py`, `tests/`, `AUDIT_REPORT.md`.

## Required commands (all must pass)
```
py main.py selftest        # must print ALL CHECKS PASSED
pytest -q                  # all green
py main.py healthcheck     # PASS (cron WARN on Windows is fine)
py main.py daily-run       # completes, writes a summary, publishes nothing
py main.py validate data   # no critical issues
py main.py workspace build --keyword "taylor swift hoodie" --mode pod --country US   # -> BLOCKED
```

## Pass/fail criteria
- selftest + pytest green; healthcheck only-cron-WARN.
- Every dashboard route returns 200 (test client); no route 500s on normal input.
- `PUBLISH_AUTOMATION` is false everywhere; no code path publishes to Etsy.
- The publish-gate safety invariant holds: PUBLISH_READY=true ⟺ zero failed checks.
- BLOCKED verdict on a known-brand keyword; no publish button when not ready.

## What NOT to do
- Do not mark any readiness flag true without running the commands.
- Do not enable auto-publishing or weaken the publish gate to "make it pass".
- Do not delete the user's real data or `.env`.
