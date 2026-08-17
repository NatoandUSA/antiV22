# YTrends Exporter (for 22etsy-agent)

One-click **CSV export** of any YTrends data table — Hidden Gems, Trending Keywords,
Categories, Newest, Rankings — plus an optional **push to your local 22etsy-agent**.

It reads only the table you are already viewing (the same data "Save Page As" would
capture) and turns it into a clean CSV. It never touches Etsy or Amazon and never
automates any marketplace — it's a research-data exporter only.

Validated on the live table markup (`table[data-slot="table"]`): pulls all columns
and all rendered rows (e.g. 16 columns × 50 rows on Hidden Gems, 14 × 50 on Categories).

---

## Install (takes ~30 seconds)

1. Open Chrome and go to `chrome://extensions`.
2. Turn on **Developer mode** (top-right toggle).
3. Click **Load unpacked**.
4. Select this `ytrends-exporter` folder.
5. Done — pin it if you like.

## Use

1. Open any YTrends table page (e.g. `https://trends.ytuong.ai/en/hidden-gems`,
   `/en/trending`, `/en/categories`, `/en/newest`, and the sort variants).
2. A small **YTrends → CSV** toolbar appears at the bottom-right.
3. Click **Export CSV** — it downloads `ytrends_<view>_<date>.csv` with every
   column and every row currently shown.
4. Feed that CSV into the 22etsy-agent Import Center (or the FBM toolkit).

## Optional: send straight to your agent

1. Click the extension icon → paste your agent's import URL
   (e.g. `https://your-agent/api/import`) **and your import token** → **Save**.
   The token must match `YTX_IMPORT_TOKEN` in the agent's `.env`. You invent this
   value — it is not issued by YTrends. Generate one with:
   `python -c "import secrets; print(secrets.token_urlsafe(32))"`
2. On a YTrends page, click **Send to agent**. It POSTs the table as JSON, with
   the token in an `X-Import-Token` header:
   ```json
   { "view": "hidden-gems", "captured_at": "...", "source": "...",
     "headers": ["Rank","Keyword", ...], "rows": [[...], ...] }
   ```
3. 22etsy-agent has this endpoint (`POST /api/import`): it allows CORS from
   `https://trends.ytuong.ai` and answers the preflight the custom header triggers.

**If Send to agent fails:**

| Response | Meaning |
|---|---|
| `401` | token missing/wrong — popup value ≠ `YTX_IMPORT_TOKEN` in the agent's `.env` |
| `503` | the agent has no `YTX_IMPORT_TOKEN` set at all (import disabled by design) |
| CORS / network error | wrong URL, or the agent isn't running |

Note the agent reads `.env` only at startup — after editing it, restart the
service (`sudo systemctl restart etsy-web`) or the old value stays live.

## Notes & limits

- **Table views only.** The card-layout pages (Age Spy, Market Pulse) have no HTML
  table, so nothing is exported there yet — those need a custom reader (can add).
- Exports exactly what's rendered (YTrends shows up to ~50 rows per view).
- Works on `trends.ytuong.ai`, `ytuong.me`, and `heyetsy.com`.
- No credentials are stored; the only saved setting is your optional agent URL.

## Files

| File | Purpose |
|---|---|
| `manifest.json` | MV3 manifest (minimal permissions: storage, downloads) |
| `content.js` | Finds the table, builds CSV, download / send |
| `content.css` | Toolbar styling |
| `popup.html` / `popup.js` | Set the optional agent import URL |
| `icons/` | Toolbar icons |
