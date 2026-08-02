# push-to-vps.ps1 - build reports locally (where YTrends fetching works), then
# copy the fresh data + reports to the VPS so the team dashboard shows the
# latest. The VPS itself can't fetch YTrends (its datacenter IP is blocked),
# so this is how the server stays up to date.
#
# Run from anywhere:   powershell -ExecutionPolicy Bypass -File deploy\push-to-vps.ps1
$ErrorActionPreference = "Stop"

$VPS_HOST = "51.79.200.65"
$VPS_PORT = "55317"
$VPS_USER = "etsy"
$VPS_PATH = "/home/etsy/etsy-agent"
$PYTHON   = "py"          # use "python" if "py" isn't on your PATH

Set-Location (Split-Path $PSScriptRoot -Parent)   # repo root

Write-Host "== 1/4  Harvest fresh keywords, then build POD + Embroidery =="
& $PYTHON main.py harvest        # enrich keywords.csv from the live YTrends index
& $PYTHON main.py daily pod
if ($LASTEXITCODE -ne 0) { Write-Host "daily pod failed - not syncing."; exit 1 }
& $PYTHON main.py daily embroidery
if ($LASTEXITCODE -ne 0) { Write-Host "daily embroidery failed - not syncing."; exit 1 }

Write-Host "`n== 2/4  Warm the live Trending/Opportunities cache (deep pull) =="
# The VPS IP is blocked from YTrends, so its live keyword pages can't fetch. We
# warm the cache here and ship data/agent.db up, so the team gets the same deep,
# instant lists on the server. (agent.db is the KEYWORD cache only; team logins/
# tasks/activity live in data/app.db and are NOT touched by this.)
& $PYTHON main.py warm

Write-Host "`n== 3/4  Merging the VPS keyword base into this one =="
# The PC harvests (the VPS IP is blocked from YTrends) but the TEAM adds keywords
# on the VPS through the web UI - Keyword Lab, long-tail pulls, extension drops.
# This step used to be a straight scp over the server's file, which deleted every
# one of those. Pull the server's copy down, union the two, then push the union:
# neither machine can destroy the other's keywords.
$vpsCopy = "data/vps_keyword_data.csv"
$ErrorActionPreference = "Continue"
scp -P $VPS_PORT "${VPS_USER}@${VPS_HOST}:${VPS_PATH}/keyword_data.csv" $vpsCopy 2>$null
$ErrorActionPreference = "Stop"
if (Test-Path $vpsCopy) {
    & $PYTHON -c "from src.harvest import merge_master; c,e = merge_master(r'$vpsCopy'); print(f'  carried in {c} VPS-only keyword(s), enriched {e}')"
    Remove-Item $vpsCopy -Force
} else {
    Write-Host "  no keyword_data.csv on the VPS yet - nothing to merge"
}

Write-Host "`n== 4/4  Copying to the VPS (enter the etsy password when asked) =="
scp -P $VPS_PORT keyword_data.csv "${VPS_USER}@${VPS_HOST}:${VPS_PATH}/keyword_data.csv"
scp -P $VPS_PORT -r reports/latest "${VPS_USER}@${VPS_HOST}:${VPS_PATH}/reports/"
# agent.db is a live SQLite file the dashboard reads; copy to a temp name then
# atomically rename on the VPS so a concurrent read can never see a half-written db.
scp -P $VPS_PORT data/agent.db "${VPS_USER}@${VPS_HOST}:${VPS_PATH}/data/agent.db.tmp"
ssh -p $VPS_PORT "${VPS_USER}@${VPS_HOST}" "mv -f ${VPS_PATH}/data/agent.db.tmp ${VPS_PATH}/data/agent.db"

Write-Host "`nDone -> https://etsy.theglobalserviceteam.site"
Write-Host "Tip: on the VPS run 'sudo systemctl restart etsy-web' only if code changed (data alone needs no restart)."
