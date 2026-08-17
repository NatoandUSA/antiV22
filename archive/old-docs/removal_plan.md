# 22etsy — Old-Version Cleanup: Audit & Removal Plan

_Audit date 2026-07-27. Method: reference audit (grep across `src` + `tests`) before any deletion. Nothing was removed blind. This is the deliverable the cleanup handoff asked for (`cleanup_inventory.json` + `removal_plan.md`)._

## Headline: the "obvious" deletions are NOT safe — do not run them

The Promax v38 execution prompt and the cleanup handoff (REMOVE-02) tell an agent to delete
`design_analyzer.py` **and** the `create_pack / build_prompt / build_brief / pack_html / work_html`
functions "as legacy dead code." The audit shows that is **stale and wrong**:

- `build_prompt`, `build_brief`, `work_html` are **live** — reached through `run_view_html`, which the
  active `/design-skill-bridge/run` route renders.
- `create_pack` + `pack_html` are wired to the `/design-skill-bridge/pack` route **and** are covered by
  3 tests in `test_design_skill_bridge.py`.

Deleting them would break the Design Inbox (the V37.2 crown-jewel) and the test suite. **Do not run the
v38 cleanup prompt as written.**

## What is genuinely safe to remove — needs your `git rm`

Only one whole file is provably dead. The Cowork device bridge cannot delete files (it can only write),
so this is a manual step for you on the PC:

```powershell
cd D:\Claude\22etsy-agent
git rm src/design_analyzer.py tests/test_design_analyzer.py
py -m pytest -q          # confirm green
git commit -m "cleanup: remove retired Gemini design_analyzer (unimported) + its test"
```

Proof it is dead: `grep "import design_analyzer"` → 0 matches. The `/design-analyzer` URL is only a
**legacy alias** to the Design Inbox handler, not this module. Its only consumer is its own test.

## Reviewed but NOT executed (your call)

- **`/design-skill-bridge/pack` route + `create_pack` + `pack_html`.** The route is orphaned (no form
  posts to it) and those two functions are called only by it — but they are still exercised by 3 bridge
  tests. If you want them gone, remove the route + both functions + update those 3 tests as **one**
  reviewed change, then run the 26 bridge tests and a live `/design-skill-bridge` smoke. I did not do
  this: it edits the active Design Inbox file for a small reward, so it deserves your explicit sign-off.
- **`/api/design-result` endpoint.** Exporter v3.3.0 no longer calls it; it still calls the live
  `import_pasted`. Harmless. Optional: return `410 Gone`. Low value.
- **`/draft-listing`.** Still registered. If you confirm nothing links to it, **redirect** it to
  `/launch-kit` rather than delete (keeps old bookmarks working).

## Already done in earlier versions (no action)

`/winner-finder`, `/shop-analyzer`, `/listing-analyzer`, root `/pack` — not registered anymore.
ChatGPT injection (`chatgpt.com` / `chat.openai.com`, `fetch-etsy-image`, `/api/design-result`
allowlist) — already stripped from the extension in v3.3.0.

## Bottom line

The safe, high-value cleanup right now is one `git rm` (design_analyzer + its test). Everything else the
old handoffs called "dead" is either live or test-covered, and should be treated as a **reviewed** change,
not a blind delete. Full item-by-item classification with line-level proof is in `cleanup_inventory.json`.
