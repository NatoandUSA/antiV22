# Etsy Product Manager — Command Cheat Sheet (V28.0)

## 🧭 YTuong vs. this Dashboard — know the difference

> **YTuong is where we DISCOVER market data. This dashboard is where we turn that
> data into TEAM ACTION.** We never clone YTuong — we link to it and import from it.

| Use **YTuong / HeyEtsy** to FIND | Use **this Dashboard** to EXECUTE |
|---|---|
| trending & hot listings, Etsy's Picks | assign work to staff |
| top shops, shop analytics | check supplier + profit |
| views / favorites / sold data | build listing drafts (English) |
| tags, images, categories | write design briefs / first-image plans |
| seasonal calendar | review the publish gate (Approve/Reject) |
| — research links: [trending](https://trends.ytuong.ai/en/trending) · [hidden gems](https://trends.ytuong.ai/en/hidden-gems) · [spy](https://trends.ytuong.ai/en/spy) · [HeyEtsy hot](https://ytuong.me/hot) | track Day 3 / Day 7, and learn what works for OUR shop |

**Flow:** research on YTuong → **📥 Import Center** → **🧭 Research Queue** →
tasks → draft → **manager review** → *publish by hand only if approved* → Day 3/7.

### The team workflow (who does what)

| Step | Role | Tool | Action | Output |
|---|---|---|---|---|
| 1 | Researcher | YTuong | Find hot listing / shop / keyword | Candidate idea |
| 2 | Researcher | Dashboard | Import URL or keyword | Saved candidate |
| 3 | Researcher | Dashboard | Classify product fit | Research status |
| 4 | Researcher | Dashboard | Assign supplier / competitor task | Team task |
| 5 | Seller | Dashboard | Check supplier and profit | Supplier status |
| 6 | Designer | Dashboard | Prepare first image / design | Design task |
| 7 | Seller | Dashboard | Build listing draft | Draft listing |
| 8 | Manager | Dashboard | Review publish gate | Approve / reject |
| 9 | Seller | **Etsy, by hand** | Publish manually **only if approved** | Live listing |
| 10 | Seller / Manager | Dashboard | Update Day 3 / Day 7 results | Keep / fix / kill / scale |

> ⚠️ **PUBLISH_AUTOMATION = false.** The dashboard never posts to Etsy. A listing
> is only ever published **by a human, by hand**, and only when the workspace shows
> **Publish-ready = yes** with manager sign-off.

---

**The short version:** the tool runs itself. The **VPS refreshes the keyword data
by itself every 6 hours**, and your **team just uses the dashboard in a browser —
no terminal, no commands**. Closing your SSH window does **NOT** take the site
down (it runs as a background service). You only open a terminal for the rare
admin task below.

## Where you type — and which Python to use

| Place | How to open it | Python to type |
|---|---|---|
| 🌍 **The dashboard** (etsy.theglobalserviceteam.site) | a web browser | *none — you click buttons* |
| 🖥️ **The VPS** (the server) | SSH, then `cd ~/etsy-agent` | **`.venv/bin/python`** |
| 💻 **Your laptop** | PowerShell (Windows) / Terminal (Mac) | `py` (Windows) · `python3` (Mac) |

> ⚠️ **On the VPS always use `.venv/bin/python`, never plain `python3`.** Plain
> `python3` misses the installed packages and fails with `No module named 'dotenv'`.
> Tip: run `source .venv/bin/activate` once per session, then plain `python` works
> until you close the window.

---

## 🆘 Reopen the VPS (if you closed this window / after a reboot)

Closing your terminal does **not** stop the dashboard — `etsy-web` and `etsy-tunnel`
are background services that keep running (and auto-start if the server reboots).
To get back in and confirm everything is up:

```bash
# 1. Reconnect (from PowerShell on Windows, or Terminal on Mac)
ssh -p 55317 etsy@51.79.200.65
#    (password won't show as you type — that's normal)

# 2. Go to the project
cd ~/etsy-agent

# 3. Check both services are running (look for "active (running)")
systemctl status etsy-web --no-pager
systemctl status etsy-tunnel --no-pager

# 4. If either is NOT running, start/restart them:
sudo systemctl restart etsy-web etsy-tunnel

# 5. Confirm the site is live — open in any browser:
#    https://etsy.theglobalserviceteam.site
```

That's it — the site was almost certainly up the whole time. `q` exits a `status`
screen; `exit` closes the SSH session (the site stays up).

---

## 🌍 The dashboard — what the TEAM uses (no commands, ever)

Teammates open the website and click. Works 24/7 whether your laptop is on or off:

| On the dashboard | They do | They get |
|---|---|---|
| ⚡ **Command Center** | type a keyword + pick a mode | full workspace: verdict, scores, listing draft, design prompt, publish gate |
| **Analyze / Should I sell? / Expand** | a keyword | demand + competition, GO/NO-GO, related keywords |
| **Build listing** | a keyword | title + 13 tags + description (**draft only**) |
| 🕵️ **Spy** | a keyword | who's winning + who dominates the niche |
| 📈 **Trending / 💎 Opportunities** | click (per mode) | ~50 rising keywords + **product clusters** (build one listing per cluster) |
| 📅 **Team Calendar** | click | tasks by due date — today / this week / overdue |
| 📅 **Seasonal calendar** | click | upcoming holidays + launch-by dates |
| 🏪 **Saved shops / 📌 Saved listings** | click **Auto-pull** | new shops already selling · young winning listings |
| 📝 **Grade my listing** | paste title+tags+description | 0–100 score + exact fixes |
| 📉 **Sales feedback** | log real numbers after a manual publish | Day-3/7 KEEP / CHANGE / KILL / SCALE |

Every result has the **trademark check** built in. Nothing is ever auto-published.

---

## 🖥️ On the VPS — admin commands (run rarely)

Connect first (see the reopen box above), then `cd ~/etsy-agent`. Remember the
`.venv/bin/` prefix.

| Command | What it does |
|---|---|
| `git pull` | Get the latest code I pushed. |
| `sudo systemctl restart etsy-web` | Load new code into the live site (~5s). Only needed **after `git pull` changed code**. |
| `.venv/bin/python main.py warm --fresh` | Refresh the Trending/Opportunities keyword lists **right now** (the team sees current data). Runs itself every 6h. |
| `.venv/bin/python main.py cron install --every-hours 6 --command warm` | (Re)install the every-6-hour auto-refresh. Do this once. |
| `.venv/bin/python main.py cron status` | Is the auto-refresh installed? last run? log path? |
| `.venv/bin/python main.py clean` | **Reclaim disk** — trims old report archives, prunes stale cache, drops caches. Safe anytime. Run monthly. |
| `.venv/bin/python main.py healthcheck` | Confirms folders, data, dashboard, cron are OK. |
| `.venv/bin/python main.py daily-run` | Full nightly job: fresh keywords + feeds + warm + summary. **Never publishes.** |

**Check the server's disk / memory** (answer to "is there room?"):
```bash
df -h ~            # disk free on your home partition
free -h            # RAM free
du -sh ~/etsy-agent/*   # what's using space inside the project
```
If disk is tight, run `.venv/bin/python main.py clean`.

**Update the live site after I push new code:**
```bash
cd ~/etsy-agent && git pull && sudo systemctl restart etsy-web
```
(If `git pull` complains about a local change, run `git stash` then `git pull`.)

---

## 💻 On your laptop — optional (not needed daily)

The VPS refreshes itself, so you rarely need this.

| Command | What it does |
|---|---|
| `py main.py selftest` | Health check after any change. Must say **ALL CHECKS PASSED**. Fast, offline. |
| `py main.py web` | Preview the whole dashboard locally. `Ctrl+C` to stop. |
| `py main.py warm --fresh` | Refresh the keyword cache on the laptop. |
| `py main.py clean` | Reclaim disk on the laptop (same as on the VPS). |
| `py main.py workspace build --keyword "usa raccoon shirt" --mode pod` | Build one full workspace from the terminal. |
| `.\deploy\push-to-vps.ps1` | Only if you build the **reports** locally — uploads reports + cache to the VPS. |

> Mac: use `python3` instead of `py`. A few deep-research commands (`expand`,
> `discover`, `ideas`, `grow`) use the older cookie data source — run those on the
> laptop. Everyday keyword data uses the public YTrends MCP, which **works on the
> VPS too** (that's why the 6-hour auto-refresh runs server-side).

---

## Golden rules
1. **Team uses the dashboard; you rarely touch the terminal.** The VPS refreshes
   itself every 6 hours.
2. **On the VPS, always `.venv/bin/python …`** (never bare `python3`).
3. After I push code: on the VPS `git pull` (+ `sudo systemctl restart etsy-web`
   if the site code changed).
4. **Never auto-publish.** A listing is listed **manually**, only when the
   workspace shows **PUBLISH_READY = true**.
5. Run `py main.py selftest` after any change — must say **ALL CHECKS PASSED**.
6. Run `main.py clean` monthly (either machine) to keep disk lean.
7. Never share your `.env` — it holds your passwords and tokens.
