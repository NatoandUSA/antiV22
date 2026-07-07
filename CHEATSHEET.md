# Etsy Product Manager — Command Cheat Sheet (V20.5)

Every command is typed in a terminal (PowerShell on Windows, Terminal on Mac)
**from inside the project folder**. On Windows use `py`; on Mac use `python3`.

**Legend:** 💻 works offline · 🌐 needs internet · 🔑 needs a token/password in `.env` · 💰 costs money · ⭐ the ones you'll actually use most

`[pod|embroidery]` after a command = do it for **one product line only**. Leave
it off to include everything. Example: `py main.py daily pod`.

---

## ⭐ The 3 you'll use every day

| Command | What it does | Notes |
|---|---|---|
| `.\deploy\push-to-vps.ps1` | **The publish button.** Harvests fresh keywords → builds the POD + Embroidery reports → uploads them to the live team site. Asks for the `etsy` password. | 🌐 🔑 Run on the **laptop** only (the VPS can't fetch trends). Ends with the site URL. |
| `py main.py web` | Opens the team report portal in your browser so you can read everything locally before publishing. | 🔑 needs `WEB_PASSWORD` in `.env`. Press `Ctrl+C` to stop it. |
| `py main.py selftest` | Health check — confirms the whole tool is working. Run it after any change. | 💻 fast, no internet. Should say **ALL CHECKS PASSED**. |

**To update the live site** (after a push), run these **on the VPS**:
```bash
cd /home/etsy/etsy-agent
git checkout -- keywords.csv    # only if git pull complains
git pull
sudo systemctl restart etsy-web
```

---

## Building the reports

| Command | What it does | Notes |
|---|---|---|
| `py main.py daily [pod\|embroidery]` | **THE report command.** Builds the 5 clean team reports (Start Here, Manager, Market & Keyword, Seller, Designer) **+ the live Market Pulse**. | 🌐 The sync runs this for you; run it manually to preview. |
| `py main.py harvest` | Pulls a **deep, fresh keyword pool** from the live YTrends index (rankings + opportunities + trending + POD/embroidery search) into `keyword_data.csv`, which fuels the reports. Runs automatically before each sync. | 🌐 This is what took Embroidery from 13 → 200+ keywords. |
| `py main.py harvest --dry` | Same as above but **previews only** — writes nothing. Good for seeing what's out there. | 🌐 safe, read-only. |
| `py main.py manager [pod\|embroidery]` | The full Manager AI report on its own (verdicts, profit model, publish gate). | 🌐 |
| `py main.py ideas [pod\|embroidery]` | Just the **Best Ideas** report — product clusters + a 7-day validation plan. | 🌐 |
| `py main.py discover [pod\|embroidery]` | Pulls live data and ranks **new** niche ideas (rising, low-competition). | 🌐 |

---

## Digging into a niche (research)

| Command | What it does | Notes |
|---|---|---|
| `py main.py expand "keyword"` | Shows related keywords for a niche you like. Example: `py main.py expand "chenille bag"`. | 🌐 |
| `py main.py categories` | Which Etsy categories pay best per seller. | 🌐 |
| `py main.py grow [pod\|embroidery]` | Older keyword-grower (auto-adds viral/best-selling terms). `harvest` is the newer, bigger version. | 🌐 |
| `py main.py grow "niche keyword"` | Deep-research one specific niche. | 🌐 |
| `py main.py` (nothing after) | Validates your `keywords.csv` seed list against Google Trends. Slow and rarely needed now. | 🌐 (legacy) |

---

## Listings, suppliers & design images

| Command | What it does | Notes |
|---|---|---|
| `py main.py listing "keyword"` | A complete listing draft pack (title, tags, description) — **draft only, never auto-published**. | 🌐 |
| `py main.py supplier pod "clear concert bag"` | Pulls supplier details for a POD product. | 🌐 |
| `py main.py supplier embroidery "chenille name bag"` | Same, for an embroidery product. | 🌐 |
| `py main.py printify "pouch"` | Finds Printify products + real US shipping. | 🌐 🔑 |
| `py main.py printify cost 1090` | Shipping cost per print provider for a product ID. | 🌐 🔑 |
| `py main.py images` | **Lists** the AI design prompts for approved products (no charge). | 💻 |
| `py main.py images --all` | **Generates** the design PNGs via OpenAI. | 🌐 🔑 💰 each image is a paid API call. |

---

## Reading reports & housekeeping

| Command | What it does | Notes |
|---|---|---|
| `py main.py listreports` | Prints the file paths of every latest report. | 💻 |
| `py main.py openreports` | Opens the latest report folder in your file explorer. | 💻 |
| `py main.py rawreports [pod\|embroidery]` | The detailed/debug report set (more than the clean 5). | 🌐 |
| `py main.py tasks` | Daily team tasks report (9 roles). | 💻 |
| `py main.py blockers` | What's blocking products, grouped by severity. | 💻 |
| `py main.py statusboard` | Product status board (csv + md). | 💻 |
| `py main.py finalqa` | Final QA summary. | 💻 |
| `py main.py performance` | Performance report from `shop_performance.csv`. | 💻 |

---

## Inside Claude Code (type these in the chat, not the terminal)

Once the **ytrends** server is approved, you can just ask in plain English, e.g.
*"what's trending in embroidery this week?"* — or use the installed skills:

| Skill | What it does |
|---|---|
| `/whats-hot` | Weekly Etsy scan — what's rising, cooling, and which seasonal events are coming. |
| `/should-i-sell` | A GO / CONDITIONAL GO / NO-GO verdict for a specific niche, with 3 reasons. |
| `/holiday-prep` | A seasonal launch timeline with the "launch 6 weeks early" deadline math. |

---

## Where the data comes from

- **Live trends:** the official YTrends MCP (`mcp.trends.ytuong.ai`) — no token needed.
- **Cross-check:** Google Trends is live; Pinterest + X turn on when you add
  `PINTEREST_ACCESS_TOKEN` / `X_BEARER_TOKEN` to `.env`.
- **Reports are Markdown only** (no PDF). The team reads them on the dashboard.

## Golden rules
1. Build + publish from the **laptop** (`push-to-vps.ps1`) — the VPS can't fetch trends.
2. Run `py main.py selftest` after any change — it must say **ALL CHECKS PASSED**.
3. Never publish a listing straight from a draft — it goes through QA first.
4. Never share your `.env` — it holds your passwords and tokens.
