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

Write-Host "== 1/2  Fetching data + building reports locally =="
& $PYTHON main.py daily
if ($LASTEXITCODE -ne 0) { Write-Host "daily failed - not syncing."; exit 1 }

Write-Host "`n== 2/2  Copying to the VPS (enter the etsy password when asked) =="
scp -P $VPS_PORT keyword_data.csv "${VPS_USER}@${VPS_HOST}:${VPS_PATH}/keyword_data.csv"
scp -P $VPS_PORT -r reports/latest "${VPS_USER}@${VPS_HOST}:${VPS_PATH}/reports/"

Write-Host "`nDone -> https://etsy.theglobalserviceteam.site"
