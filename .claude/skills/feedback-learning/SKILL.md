---
name: feedback-learning
description: Internal checklist. Verify the sales feedback loop and private learning system actually affect future scoring. Use when touching feedback.py, learning.py, or the scoring that reads private data.
---

# Feedback + Private Learning (internal)

## Files to inspect
`src/feedback.py` (schema, `recommend`, `add`), `src/learning.py`
(`record_feedback`, `learning_note`, the 5 pattern files), `src/workspace.py`
(where `learning_note` nudges Can-We-Win + shows notes).

## Rules
- Feedback saves to `data/performance/listing_feedback.{json,csv}` + mirrors
  `feedback_tracking.json` into the matching run.
- Day-3/7 `recommend` returns one of the fixed decisions (KEEP / CHANGE_* /
  RAISE/LOWER_PRICE / MAKE_VARIANTS / KILL_LISTING / SCALE_PRODUCT_LINE /
  NEEDS_MORE_DATA). A logged 0 is data; missing = NEEDS_MORE_DATA.
- `record_feedback` updates winner/failed/image/tag/supplier patterns.
- `learning_note` MUST change scoring: a keyword/tag that sold for us raises
  Can-We-Win (`private_learning_boost`); a failed keyword or a refund-prone
  supplier lowers it (`private_learning_warning`), with a visible reason.

## Commands
```
pytest tests/test_os_modules.py -q
py main.py validate feedback
```

## Pass/fail
Pass only if logging a winner raises the next run's Can-We-Win for that keyword,
and a problem supplier lowers its score — verifiable via `learning.learning_note`.

## What NOT to do
- Do not let the feedback loop be a dead form — it MUST feed scoring.
- Do not fabricate learning data; only real logged outcomes update patterns.
