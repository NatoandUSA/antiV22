---
name: test-runner
description: Internal checklist. Run the project's required commands and tests, then report pass/fail honestly. Use before committing, before a release, or when asked "did the tests pass".
---

# Test Runner (internal)

## When to use
Before any commit that changes behavior, before a release, or on request.

## Required commands
```
py main.py selftest        # MUST end with "ALL CHECKS PASSED"
pytest -q                  # all pass
py main.py healthcheck
py main.py daily-run       # no publishing; writes summary
py main.py validate data
py main.py workspace build --keyword "usa raccoon shirt" --mode pod --country US
py main.py workspace build --keyword "chenille name bag" --mode embroidery --country US
py main.py workspace build --keyword "custom travel pouch" --mode both --country US
py main.py workspace build --keyword "gift for her" --mode both --country US
py main.py workspace build --keyword "taylor swift hoodie" --mode pod --country US   # BLOCKED
py main.py supplier match --product "chenille name bag" --mode embroidery --country US
py main.py supplier match --product "usa raccoon shirt" --mode pod --country US
```

## Pass/fail
- Commit is gated on `selftest` printing ALL CHECKS PASSED **and** `pytest` green.
- Report the ACTUAL output. If a command fails, say so with the error — never claim green when it isn't.
- taylor swift hoodie must be BLOCKED; all fresh runs must be PUBLISH_READY=false.

## What NOT to do
- Do not skip selftest/pytest before committing.
- Do not mark readiness true on untested paths; document any failure instead.
