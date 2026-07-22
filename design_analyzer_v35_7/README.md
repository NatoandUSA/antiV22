# Design Analyzer — V35.7 (drop-in for 22etsy-agent)

Turns a design image into: a **trademark read** (Gemini vision + your own
`trademark.py` blocklist), a **safe original redesign prompt** (standard +
embroidery), a **stitch-safety verdict**, and a full **Etsy SEO pack** (title /
13 tags / description, EN + VI). Runs on **Gemini** — free tier is enough at your
volume. Draft-only; the "recreate" prompt is analysis-only (original-designs rule
stands). No auto-publish.

## What's in this folder
```
install.py                     one-shot, idempotent installer (patches web.py in place)
src/design_analyzer.py         the module (Gemini call + your trademark/stitch gates + rendering)
tests/test_design_analyzer.py  offline tests (Gemini mocked)
.env.snippet                   the key line to add
README.md                      this file
```

## Install (on your PC)
Run the installer against your repo — it edits your **current** `web.py` in place
(so any local edits are kept) and is safe to run twice:

```powershell
cd D:\Claude\22etsy-agent
py design_analyzer_v35_7\install.py .
```

It will: copy the module + tests in, add the `/design-analyzer` route, add the
home tool-card, bump `version.py` to 35.7, document `GEMINI_API_KEY` in
`.env.example`, and compile-check `web.py`. If an anchor can't be found it stops
with a clear message (send me that `web.py` region and I'll adapt).

## Add your Gemini key (server-side — never in git)
Your key lives in `.env`, which is git-ignored, so put it straight on the VPS:

```bash
nano ~/etsy-agent/.env          # add this line:
GEMINI_API_KEY=AIza...your-google-ai-studio-key...
```
(Get the key free at https://aistudio.google.com → API keys. Optional:
`GEMINI_MODEL=gemini-2.5-flash` to override the default.)

## Test + deploy
```powershell
# PC
py -m pytest -q                 # expect green (2 pre-existing failures are known)
git add -A
git commit -m "V35.7: Design Analyzer (Gemini vision + trademark/stitch gates)"
git push
```
```bash
# VPS
cd ~/etsy-agent && git fetch origin && git reset --hard origin/main && find . -name __pycache__ -type d -exec rm -rf {} + ; .venv/bin/python -m compileall -q src && sudo systemctl restart etsy-web && sleep 2 && systemctl is-active etsy-web
```

## Verify
- `/status` shows **VERSION 35.7**.
- Home → Advanced grid → **🎨 Design Analyzer** → upload a design → you get the
  trademark verdict, safe redesign prompts, and the Etsy SEO pack.
- If the key is missing you get a clean "GEMINI_API_KEY is not set" message (no crash).

## Cost
Gemini 2.5 Flash on the free tier is effectively **$0** at your volume; if you ever
exceed the free tier it's a fraction of a cent per design.

## Notes / guardrails
- IP verdict = the **more cautious** of the model and your own blocklist. A named
  owner or a blocklist hit forces at least a "verify" (and HIGH → Skip).
- Embroidery mode adds a stitch-safety gate (your `product_fit.producibility`):
  gradients / photoreal / fine detail → "redesign for stitch".
- This is **Phase 1** (safe-to-produce gate). Phase 2 wires the verdict into the
  Opportunity Score for a demand-aware 0–100 rating.
