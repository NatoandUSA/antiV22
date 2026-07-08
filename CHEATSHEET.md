# Etsy Product Manager — Command Cheat Sheet (V23.0)

**The short version:** the tool mostly runs itself now. The **VPS refreshes the
data every day at 6:00 AM on its own**, and your **team uses the dashboard in the
browser — no terminal, no commands**. You only open a terminal for the occasional
admin task below.

**Where you type, and how to start Python:**

| Place | How to open it | Python command |
|---|---|---|
| 🌍 **The dashboard** (etsy.theglobalserviceteam.site) | A web browser | *none — you click buttons* |
| 🖥️ **The VPS** (the server) | SSH, then `cd ~/etsy-agent` | `python` (inside the `.venv`) |
| 💻 **Your laptop** | PowerShell (Windows) / Terminal (Mac), in the project folder | `py` on Windows · `python3` on Mac |

> ⚠️ On the VPS it's `python` (not `py`). On Windows it's `py`. That's the only
> difference — the commands after it are identical.

---

## 🌍 The dashboard — what the TEAM uses (no commands, ever)

Your teammates just open the website and click. Everything below is a button, and
it works 24/7 whether your laptop is on or off:

| On the dashboard | What they do | What they get |
|---|---|---|
| ⚡ **Command Center** | type a keyword + pick a mode | the full workspace: verdict, all scores, listing draft, design prompt, publish gate |
| **Analyze / Should I sell? / Expand** | a keyword | demand + competition, a GO/NO-GO read, related keywords |
| **Build listing** | a keyword | title + 13 tags + description (**draft only**) |
| 🕵️ **Spy** | a keyword | who's winning + who dominates the niche |
| 📈 **Trending / 💎 Opportunities** | click (per mode) | rising keywords · low-competition sweet spots |
| 📅 **Seasonal calendar** | click | upcoming holidays + launch-by dates + keywords |
| 🏪 **Saved shops / 📌 Saved listings** | click **Auto-pull** | new shops already selling · young winning listings |
| 📝 **Grade my listing** | paste title+tags+description | a 0–100 score + exact fixes |
| 🏭 **Suppliers** | open catalog / upload CSV | the supplier library |
| 📉 **Sales feedback** | log real numbers after a manual publish | a Day-3/7 KEEP / CHANGE / KILL / SCALE action |

Every result has the **trademark check** built in, and nothing is ever
auto-published — publishing stays a manual human decision.

---

## 🖥️ On the VPS — the few admin commands (run rarely)

**Connect to the server** (from PowerShell on your PC), then go to the project:
```bash
ssh -p 55317 etsy@51.79.200.65
cd ~/etsy-agent
```
Enter your password when asked (it won't show as you type — that's normal). The
daily data refresh already runs itself at 6 AM, so you'll rarely need the rest.

| Command | Where | What it does |
|---|---|---|
| `git pull` | VPS | Get the latest code I pushed. Updates the site + this cheat sheet **instantly** (no restart needed for the cheat sheet). |
| `sudo systemctl restart etsy-web` | VPS | Restart the dashboard **only after a code change** so it loads the new version. ~5 seconds, not a reboot. |
| `python main.py daily-run` | VPS | **The daily auto-job.** Pulls fresh keywords + refreshes the shop/listing feeds + writes a summary. Runs by itself at 6 AM; run it by hand to refresh now. **Never publishes.** |
| `python main.py healthcheck` | VPS | Confirms folders, data, dashboard, and cron are all OK. |
| `python main.py cron status` | VPS | Shows the 6 AM job: installed? last run? log path? |
| `python main.py cron install --time "06:00"` | VPS | (Re)installs the 6 AM schedule. You already did this once. |
| `python main.py autopull` | VPS | Just refresh Saved shops + Saved listings now. |
| `python main.py daily pod` / `daily embroidery` | VPS | Rebuild the read-only daily reports for one line. |

**To update the live site after I push new code:**
```bash
cd ~/etsy-agent
git pull
sudo systemctl restart etsy-web    # only needed when code changed
```
(If `git pull` ever complains about a local file, run `git stash` then `git pull`.)

---

## 💻 On your laptop — optional (you don't need this daily anymore)

Since the VPS refreshes itself at 6 AM, the old "push every day" step is now
**optional** — use it only when you want an **instant** refresh instead of waiting
for the morning.

| Command | Where | What it does |
|---|---|---|
| `py main.py selftest` | laptop | Health check after any change. Must say **ALL CHECKS PASSED**. Fast, no internet. |
| `py main.py web` | laptop | Preview the whole dashboard locally in your browser. `Ctrl+C` to stop. |
| `.\deploy\push-to-vps.ps1` | laptop | **Instant publish** — build the reports and upload now (instead of waiting for 6 AM). Optional. |
| `py main.py workspace build --keyword "usa raccoon shirt" --mode pod` | laptop | Build one full workspace from the terminal + save it. |
| `py main.py expand "chenille bag"` | laptop | Deep related-keyword research for one niche. |

> A few deep-research commands (`expand`, `discover`, `ideas`, `grow`) use the
> older cookie-based data source, which is blocked from the server's IP — so run
> **those** on the laptop. The everyday stuff (`daily`, `harvest`, `autopull`,
> `daily-run`, the whole dashboard) uses the YTrends MCP, which **works fine on
> the VPS** — that's why the 6 AM auto-run works.

---

## Golden rules
1. **The team uses the dashboard; you rarely touch the terminal.** The VPS
   refreshes itself at 6 AM.
2. After I push code: on the VPS run `git pull` (+ `sudo systemctl restart
   etsy-web` if the dashboard code changed).
3. **Never auto-publish.** A listing is only ever listed **manually**, and only
   when the workspace shows **PUBLISH_READY = true**.
4. Run `py main.py selftest` after any change — it must say **ALL CHECKS PASSED**.
5. Never share your `.env` — it holds your passwords and tokens.
