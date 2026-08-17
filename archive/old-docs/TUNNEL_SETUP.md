# Team dashboard online — permanent URL setup

> **For always-on hosting, use [DEPLOY_VPS.md](DEPLOY_VPS.md) instead** — it runs
> the dashboard 24/7 on a server (no computer left on). This guide is the
> run-it-from-your-own-Mac/PC method, kept for local testing. It uses a tunnel
> named `etsy-agent`; the VPS uses `etsy-vps` (Cloudflare tunnel names are
> unique per account, so the two don't collide).

Goal: your team opens **https://etsy.theglobalserviceteam.site** and gets the
web dashboard (`python main.py web`) running on your Mac — always the same URL,
gated by your `WEB_PASSWORD`.

How it works: a **Cloudflare Tunnel** makes an outbound connection from your Mac
to Cloudflare, so there are **no ports to open** on your router and no IP to
expose. Cloudflare terminates HTTPS and forwards to `localhost:8000`.

> **Reality check:** the app runs on *your Mac*, so the URL is live only while
> your Mac is on and both `python main.py web` and `cloudflared` are running.
> For true 24/7 you'd move it to a small always-on server — ask me when you want
> that.

---

## Part A — Point the domain at Cloudflare (once)

You bought `theglobalserviceteam.site` at Namecheap. Move its DNS to Cloudflare:

1. **Cloudflare dashboard** → **Add a site** → enter `theglobalserviceteam.site`
   → choose the **Free** plan. Cloudflare scans existing records, then shows you
   **two nameservers** (e.g. `xxx.ns.cloudflare.com`, `yyy.ns.cloudflare.com`).
2. **Namecheap** → **Domain List** → **Manage** next to the domain →
   **Nameservers** → switch to **Custom DNS** → paste Cloudflare's two
   nameservers → save (the green check).
3. Wait for Cloudflare to email **"theglobalserviceteam.site is active"**
   (usually minutes, up to a few hours). Don't continue until it's **Active**.

Skip Namecheap's PremiumDNS / hosting add-ons — Cloudflare's free plan does DNS
and HTTPS.

---

## Part B — Install cloudflared (once)

```bash
brew install cloudflared      # macOS (Apple Silicon)
cloudflared --version         # confirm it's installed
```

---

## Part C — Create the tunnel (once)

Run these from anywhere:

```bash
# 1. Authorize cloudflared for your Cloudflare account (opens a browser;
#    pick theglobalserviceteam.site). Creates ~/.cloudflared/cert.pem
cloudflared login

# 2. Create the tunnel. Prints a Tunnel ID and writes
#    ~/.cloudflared/<TUNNEL-ID>.json  (this file is a SECRET)
cloudflared tunnel create etsy-agent

# 3. Point the subdomain at the tunnel (adds the DNS record for you)
cloudflared tunnel route dns etsy-agent etsy.theglobalserviceteam.site
```

Then open **[deploy/cloudflared-config.yml](deploy/cloudflared-config.yml)** and
set `credentials-file:` to the full path printed in step 2, for example:
`/Users/yourname/.cloudflared/1234abcd-....json`

---

## Part D — Run it (every time you want the team to have access)

Two processes must be running on your Mac:

```bash
# Terminal 1 — the dashboard (needs WEB_PASSWORD in .env)
cd ~/etsy-agent && source .venv/bin/activate
python main.py web

# Terminal 2 — the tunnel
cloudflared tunnel --config ~/etsy-agent/deploy/cloudflared-config.yml run etsy-agent
```

Now the team visits **https://etsy.theglobalserviceteam.site** and logs in with
the `WEB_PASSWORD`.

### Keep it running without babysitting (optional)
Install the tunnel as a background service so it survives reboots:

```bash
sudo cloudflared service install --config ~/etsy-agent/deploy/cloudflared-config.yml
```

(The dashboard itself still needs `python main.py web` running — start it in a
`screen`/`tmux` session, or ask me to add a small launch-at-login setup.)

---

## Security checklist
- **`WEB_PASSWORD` is the only gate.** Make it long and random; share it
  privately (not in the same email/chat as the URL).
- Set **`WEB_SECRET`** in `.env` too, so logins survive a restart.
- **Never commit** `~/.cloudflared/cert.pem`, the `<TUNNEL-ID>.json`, or any
  tunnel **token** — they let someone run your tunnel. (`.gitignore` already
  blocks the common spots.)
- Your `.env` holds live API keys — anyone who guesses the password can trigger
  runs, so treat the password like a key.

## If it doesn't work
- **502 / "web page not available":** the dashboard isn't running — start
  Terminal 1 (`python main.py web`) and confirm `http://localhost:8000` works
  locally first.
- **DNS / SSL error on the subdomain:** the zone isn't Active yet (Part A step 3)
  or the `route dns` step didn't run. Check the record exists in Cloudflare →
  DNS: a `CNAME` for `etsy` pointing to `<TUNNEL-ID>.cfargotunnel.com`.
- **`cloudflared` says "tunnel credentials file not found":** the
  `credentials-file:` path in the config is wrong — paste the exact path from
  `cloudflared tunnel create`.
