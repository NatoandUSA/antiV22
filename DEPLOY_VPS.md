# Always-on deploy — move the dashboard to a VPS

Right now the team URL is live only while your Mac is on. Moving the app to a
small always-on Linux server (VPS) makes **https://etsy.theglobalserviceteam.site**
available 24/7, independent of your laptop.

Good news for this tool: your `YTRENDS_API_TOKEN` is set, which is long-lived —
so a headless server does **not** need the every-few-days cookie refresh.

**What you'll do:** rent a ~$5/mo Ubuntu server, put the code + secrets on it,
move the Cloudflare tunnel to it, and run both as auto-restarting services.
Everything below is copy-paste. Do it with me one step at a time if you like.

> Security shape: cloudflared makes an **outbound** connection, so the server
> needs **no inbound ports open except SSH**. Your `.env` secrets live on the
> VPS — lock SSH down (key-only) and keep the box updated.

---

## 1. Rent the server
Any provider works. Cheapest reliable options (pick one):
- **Hetzner** CX22 — ~€4/mo, 2 vCPU / 4 GB (best value). 
- **DigitalOcean** — $6/mo droplet (simplest UI). 
- **Vultr / Linode** — ~$5/mo.

Create the smallest **Ubuntu 24.04 LTS** instance. When it asks, add your **SSH
key** (or set a root password). Note the server's **IP address**.

## 2. First login + a non-root user
```bash
ssh root@YOUR_SERVER_IP

# create a normal user to run the app (replace the password prompt)
adduser etsy
usermod -aG sudo etsy

# basic firewall: allow only SSH (the tunnel is outbound, needs no app port)
ufw allow OpenSSH && ufw --force enable

# switch to the new user for the rest
su - etsy
```

## 3. Install the tools
```bash
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip git

# cloudflared (Cloudflare's apt repo)
sudo mkdir -p --mode=0755 /usr/share/keyrings
curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null
echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main" | sudo tee /etc/apt/sources.list.d/cloudflared.list
sudo apt-get update && sudo apt-get install -y cloudflared
cloudflared --version
```

## 4. Get the code (private repo → read-only deploy key)
```bash
# make an SSH key on the server
ssh-keygen -t ed25519 -C "vps-etsy-agent" -f ~/.ssh/id_ed25519 -N ""
cat ~/.ssh/id_ed25519.pub
```
Copy that line → GitHub → repo **NatoandUSA/etsy-agent** → **Settings → Deploy
keys → Add deploy key** → paste, name it `vps`, leave **Allow write access
unchecked** → Add.
```bash
cd ~
git clone git@github.com:NatoandUSA/etsy-agent.git   # accept the fingerprint (yes)
cd etsy-agent
```

## 5. Python environment
```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python main.py selftest      # should end: ALL CHECKS PASSED
```

## 6. Put your secrets on the server
Create `~/etsy-agent/.env` with the same values as your Mac. **Use the API
token** (not the cookie) so it stays working unattended:
```bash
nano ~/etsy-agent/.env
```
```
YTRENDS_API_TOKEN=your-token
PRINTIFY_API_TOKEN=your-token
OPENAI_API_KEY=            # optional, only if you use `images`
WEB_PASSWORD=your-strong-team-password
WEB_SECRET=any-long-random-string
```
Save (Ctrl+O, Enter) and exit (Ctrl+X). `.env` is git-ignored — it never leaves
this box.

## 7. Create the Cloudflare tunnel on the server
Do this entirely on the VPS — no other machine needed. It creates a tunnel named
`etsy-vps`, which the config and service files already expect.

> **Paste tip:** some SSH terminals scramble multi-line pastes (you'll see
> `^[[200~` junk). If that happens, type `bind 'set enable-bracketed-paste off'`
> once, then paste **one command per line**.

Authorize the server with your Cloudflare account:
```bash
cloudflared tunnel login
```
It prints a URL — open it in any browser, pick **theglobalserviceteam.site**,
click **Authorize**. The cert saves to `~/.cloudflared/cert.pem`.

Create the tunnel and point your domain at it (run each line on its own):
```bash
cloudflared tunnel create etsy-vps
cloudflared tunnel route dns --overwrite-dns etsy-vps etsy.theglobalserviceteam.site
```
`--overwrite-dns` replaces any earlier record for the hostname (e.g. from an
old test tunnel). The credentials land in `~/.cloudflared/<TUNNEL-ID>.json`; the
config auto-finds them, so nothing else to edit.

> Already ran a tunnel from your Mac/PC earlier? It's now orphaned (DNS points at
> the VPS). Ignore it, or delete it later with `cloudflared tunnel delete <name>`.

## 8. Run both as auto-restarting services
Run this as a **single line** (chained with `&&`) so a scrambled multi-line
paste can't reorder it. It asks for your `etsy` password once:
```bash
sudo cp ~/etsy-agent/deploy/etsy-web.service /etc/systemd/system/ && sudo cp ~/etsy-agent/deploy/etsy-tunnel.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable --now etsy-web && sudo systemctl enable --now etsy-tunnel && echo ALL_DONE
```
`ALL_DONE` at the end means it worked. Then confirm both are healthy:
```bash
systemctl status etsy-web --no-pager ; systemctl status etsy-tunnel --no-pager
```
Look for **`Active: active (running)`** on each. They now start on boot and
restart on crash. Visit **https://etsy.theglobalserviceteam.site** — done. 🎉

---

## Refreshing the data (this VPS can't fetch YTrends)
YTrends blocks datacenter IPs (the VPS gets `403`), so the fetch commands
(`discover`, `ideas`, `grow`, and the fetch half of `daily`) run **only on your
laptop** — a normal residential IP. The VPS just **serves** the reports.

To refresh what the team sees, run one command **on your laptop**:

```bash
# macOS / Linux
bash deploy/push-to-vps.sh
```
```powershell
# Windows
powershell -ExecutionPolicy Bypass -File deploy\push-to-vps.ps1
```

It builds the reports locally (fetching fresh data) and copies `keyword_data.csv`
+ `reports/latest/` to the VPS. Enter the `etsy` password when prompted (twice —
once per copy; set up an SSH key to skip that).

Data counts as "fresh" for **`YTRENDS_FRESH_DAYS`** days (default **7**), so a
weekly run is enough — the dashboard serves valid reports in between, and a
no-data day never wipes the last good ones. Want a different window? add
`YTRENDS_FRESH_DAYS=14` to `.env`.

The dashboard is a **read-only report portal** — the team just reads the
reports (no command buttons), so nothing on the server can try to fetch.

### Passwordless sync (optional)
- Append your laptop's SSH public key
  (`~/.ssh/id_ed25519.pub`) to the server's `~etsy/.ssh/authorized_keys`, and the
  sync script stops asking for the `etsy` password:
  ```bash
  ssh -p 55317 etsy@51.79.200.65 \
    "mkdir -p ~/.ssh && chmod 700 ~/.ssh && echo '<PASTE PUBLIC KEY>' >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
  ```

### Passwordless restart (optional)
- Let `etsy` restart the services without a `sudo` password (scoped to just
  those two services — nothing else). **On the VPS**, once:
  ```bash
  echo 'etsy ALL=(root) NOPASSWD: /usr/bin/systemctl restart etsy-web, /usr/bin/systemctl restart etsy-tunnel, /usr/bin/systemctl status etsy-web, /usr/bin/systemctl status etsy-tunnel' | sudo tee /etc/sudoers.d/etsy-web >/dev/null && sudo chmod 440 /etc/sudoers.d/etsy-web && sudo visudo -cf /etc/sudoers.d/etsy-web
  ```
  It should print `... parsed OK`. After this, `sudo systemctl restart etsy-web`
  never prompts. Combined with the SSH key, updating from your laptop is fully
  passwordless:
  ```powershell
  ssh -p 55317 etsy@51.79.200.65 "cd ~/etsy-agent && git pull && .venv/bin/python -m compileall -q src && sudo systemctl restart etsy-web && sleep 2 && systemctl is-active etsy-web"
  ```
  (Run that from your **laptop**, not from the VPS itself — VPS→VPS SSH won't use
  the key.)

  > 🛡️ **The `compileall` step is a safety gate:** it compiles the new code under
  > the VPS's own Python **before** the restart. If anything won't parse (e.g. a
  > newer-Python-only syntax the VPS doesn't support), the `&&` chain stops and the
  > service is **not** restarted — so the live site stays up on the old code instead
  > of 502'ing. Fix the syntax, push, and re-run.

## Running it day to day
- **Update the tool:** `cd ~/etsy-agent && git pull && .venv/bin/python -m pip install -r requirements.txt && .venv/bin/python -m compileall -q src && sudo systemctl restart etsy-web`
- **See logs:** `journalctl -u etsy-web -f` (app) · `journalctl -u etsy-tunnel -f` (tunnel)
- **Restart / stop:** `sudo systemctl restart etsy-web` · `sudo systemctl stop etsy-tunnel`
- **Rotate the team password:** edit `.env`, then `sudo systemctl restart etsy-web`.
- **If YTrends ever rejects the token:** get a fresh `YTRENDS_API_TOKEN` from your
  account, update `.env`, restart `etsy-web`.

## Security checklist
- SSH: prefer **key-only** login (disable password auth once your key works).
- `WEB_PASSWORD` is the only gate on the public URL — keep it long and private.
- Keep the box patched: `sudo apt-get update && sudo apt-get upgrade -y` occasionally.
- Never commit `.env` or `~/.cloudflared/*` (already git-ignored).

## Notes
- The app uses Flask's built-in server (fine for a small team behind Cloudflare).
  If you ever need more, run it under gunicorn with a **single worker + threads**
  (`gunicorn -w 1 --threads 8 wsgi:app`) — one worker matters because the
  run-a-command job status is kept in memory. Ask me and I'll add the `wsgi.py`.
- Cost is just the VPS (~$5/mo) + the domain you already bought.
