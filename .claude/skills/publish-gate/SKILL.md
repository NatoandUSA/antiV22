---
name: publish-gate
description: Internal safety checklist for the PUBLISH_READY logic. Verify the publish gate blocks unsafe listings, requires manager sign-off, and never shows publish instructions when not ready. Use when touching publish_gate, strict_verdict, launch_readiness, or anything that affects PUBLISH_READY.
---

# Publish Gate (internal safety)

The single most important safety area. Nothing may auto-publish; PUBLISH_READY is
reachable ONLY by explicit manager sign-off.

## Files to inspect
`src/workspace.py` (`publish_gate`, `strict_verdict`, `launch_readiness`,
`MANAGER_CHECKS`), `src/web.py` (`_OPT_FIELDS` must include the `confirm_*` params;
the manager sign-off form), `tests/test_publish_gate.py`.

## Rules PUBLISH_READY must enforce (all true)
product mode selected · primary keyword verified · exactly 13 clean tags · no
typo/HIGH-trademark tags · no placeholders · supplier confirmed (URL + base +
shipping + material + size + processing) · profit target met · competitor audit
complete · Can-We-Win ≥70 · Launch ≥85 · First-Image ≥75 · Offer ≥70 · category
confirmed · image/mockup checklist complete · trademark verified or manager-approved.

## Invariants (never violate)
- PUBLISH_READY=true ⟺ `failed_checks == []`. Never "failed checks: none" while false.
- A HIGH trademark (known brand) can NEVER be cleared by any confirmation.
- WATCH / SKIP / BLOCKED never show a publish instruction — show `DRAFT ONLY — DO NOT PUBLISH`.
- The build button says "Save Draft" unless PUBLISH_READY.

## Commands
```
pytest tests/test_publish_gate.py -q
py main.py validate run --path reports/latest/runs/<folder>   # PUBLISH_READY vs failed_checks
```

## Pass/fail
Pass only if every test in test_publish_gate.py is green AND a fresh run with no
manager sign-off shows PUBLISH_READY=false with a non-empty failed list.

## What NOT to do
- Never hardcode PUBLISH_READY=true or remove a gate check to make a demo pass.
- Never let CAUTION/HIGH trademark auto-clear without the manager confirm (HIGH: never).
