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

## 7. Move the Cloudflare tunnel to the server
You already created the `etsy-agent` tunnel on your Mac. Copy its two credential
files to the server so the same tunnel runs here.

**On your Mac**, find the tunnel ID and copy the files:
```bash
cloudflared tunnel list                       # note the ID for "etsy-agent"
scp ~/.cloudflared/cert.pem ~/.cloudflared/<TUNNEL-ID>.json etsy@YOUR_SERVER_IP:~/.cloudflared/
```
(If `~/.cloudflared` doesn't exist on the server yet: `ssh etsy@YOUR_SERVER_IP 'mkdir -p ~/.cloudflared'` first.)

Quick test **on the server**:
```bash
cloudflared tunnel --config ~/etsy-agent/deploy/cloudflared-config.yml run etsy-agent
```
Leave it running, open **https://etsy.theglobalserviceteam.site** — you should
get the login page served from the VPS. Then Ctrl+C (step 8 makes it permanent).

> Don't run the tunnel on the Mac **and** the VPS long-term — once the VPS works,
> stop the Mac's `cloudflared` and `python main.py web`.

## 8. Run both as auto-restarting services
```bash
sudo cp ~/etsy-agent/deploy/etsy-web.service    /etc/systemd/system/
sudo cp ~/etsy-agent/deploy/etsy-tunnel.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now etsy-web
sudo systemctl enable --now etsy-tunnel

# check they're happy
systemctl status etsy-web --no-pager
systemctl status etsy-tunnel --no-pager
```
They now start on boot and restart on crash. Visit the URL — done. 🎉

---

## Running it day to day
- **Update the tool:** `cd ~/etsy-agent && git pull && .venv/bin/python -m pip install -r requirements.txt && sudo systemctl restart etsy-web`
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
