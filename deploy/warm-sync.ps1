# warm-sync.ps1 - lightweight: refresh the live keyword cache on THIS PC (where
# YTrends fetching works) and push just the cache DB to the VPS. Much lighter than
# push-to-vps.ps1 (no full report rebuild), so it's safe to run every few hours.
#
# Manual:   powershell -ExecutionPolicy Bypass -File deploy\warm-sync.ps1
# Scheduled: see deploy\schedule-warm.ps1 (registers this in Task Scheduler).
#
# Needs PASSWORDLESS SSH (key auth) to the VPS, or the scp step will prompt for a
# password and an unattended run will hang. Set up a key once with ssh-copy-id (or
# ssh-keygen + paste the .pub into the VPS ~/.ssh/authorized_keys).
$ErrorActionPreference = "Stop"

$VPS_HOST = "51.79.200.65"
$VPS_PORT = "55317"
$VPS_USER = "etsy"
$VPS_PATH = "/home/etsy/etsy-agent"
$PYTHON   = "py"          # use "python" if "py" isn't on your PATH

Set-Location (Split-Path $PSScriptRoot -Parent)   # repo root
$stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Write-Host "[$stamp] warm-sync: refreshing keyword cache (live)..."

& $PYTHON main.py warm --fresh
if ($LASTEXITCODE -ne 0) { Write-Host "warm failed (YTrends unreachable?) - not syncing."; exit 1 }

Write-Host "Shipping data/agent.db to the VPS (atomic rename)..."
# agent.db = keyword cache only. Team logins/tasks/activity are in data/app.db and
# are NOT synced. Copy to a temp name, then atomic mv so a live read never tears.
# BatchMode=yes: no password prompt -> without SSH keys this FAILS FAST in the log
# instead of hanging the unattended task for its whole 20-min time limit.
$sshOpt = "-o", "BatchMode=yes", "-o", "ConnectTimeout=15"
scp -q @sshOpt -P $VPS_PORT data/agent.db "${VPS_USER}@${VPS_HOST}:${VPS_PATH}/data/agent.db.tmp"
if ($LASTEXITCODE -ne 0) {
  Write-Host "scp failed - is passwordless SSH set up? (warm cache is still fresh locally)"; exit 1
}
ssh @sshOpt -p $VPS_PORT "${VPS_USER}@${VPS_HOST}" "mv -f ${VPS_PATH}/data/agent.db.tmp ${VPS_PATH}/data/agent.db"

Write-Host "[$stamp] warm-sync done -> team sees fresh lists at https://etsy.theglobalserviceteam.site"
