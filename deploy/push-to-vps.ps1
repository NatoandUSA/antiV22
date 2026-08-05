# push-to-vps.ps1 - build reports locally (where YTrends fetching works), then
# copy the fresh data + reports to the VPS so the team dashboard shows the
# latest. The VPS itself can't fetch YTrends (its datacenter IP is blocked),
# so this is how the server stays up to date.
#
# Run from anywhere:   powershell -ExecutionPolicy Bypass -File deploy\push-to-vps.ps1
#
# KEEP IN STEP WITH deploy/push-to-vps.sh. `tests/test_deploy_scripts.py` pins
# both scripts to the same data-safety invariants and will fail if they drift.
#
# THREE RULES THIS SCRIPT EXISTS TO ENFORCE
#   1. The team adds keywords ON the VPS through the web UI (Keyword Lab,
#      long-tail pulls, extension drops). Never scp the local keyword_data.csv
#      over the server's without unioning the server's copy in first - that
#      deletes all of them. Measured 2026-08-05: the server held 178 keywords
#      this machine did not.
#   2. A FAILED download is not an empty server. Only a genuinely absent remote
#      file may fall through to "first deploy"; auth/network/host-key/timeout
#      must ABORT, or the upload below destroys the server's master.
#   3. data/agent.db is NOT shipped. The VPS writes it on two crons (warm
#      --fresh every 6h, vps-build.sh at 06:00) and it holds discovered_keywords,
#      which opportunity_inbox._history_from_db() reads for the Inbox trend
#      arrows. Measured 2026-08-05: the server held 12,543 rows to this
#      machine's 11,680. Copying ours up destroys 863 rows of the server's own
#      history. data/app.db (team logins/tasks/activity) is server-only and is
#      never touched either.
#
# KNOWN LIMITATION (deliberately not engineered around): between the merge and
# the upload the script may block on interactive password prompts. Anything the
# team adds in that window is still overwritten. Use key auth to shrink it to
# seconds, or run the sync when the team is offline.
$ErrorActionPreference = "Stop"

$VPS_HOST = "51.79.200.65"
$VPS_PORT = "55317"
$VPS_USER = "etsy"
$VPS_PATH = "/home/etsy/etsy-agent"
$PYTHON   = "py"          # use "python" if "py" isn't on your PATH

Set-Location (Split-Path $PSScriptRoot -Parent)   # repo root

$STAMP = Get-Date -Format "yyyyMMdd_HHmmss"
$vpsCopy = "data/vps_keyword_data.csv"

Write-Host "== 1/5  Merging the VPS keyword base into this one =="
# BEFORE the build, so today's reports include what the team added on the server.
# Running this after the build shipped a CSV containing their keywords alongside
# reports rendered without them - the keywords looked like they had vanished.
#
# ssh `test -f` first, so we can tell the three cases apart:
#   exit 0   -> the remote master exists      -> download + merge
#   exit 1   -> it genuinely does not exist   -> first deploy, local is the seed
#   anything -> auth / network / host key /   -> ABORT (never upload blind)
#               timeout / unknown
ssh -p $VPS_PORT -o ConnectTimeout=20 "${VPS_USER}@${VPS_HOST}" "test -f '$VPS_PATH/keyword_data.csv'"
$probeRc = $LASTEXITCODE

if ($probeRc -eq 0) {
    New-Item -ItemType Directory -Force -Path "data" | Out-Null
    # Gate on scp's EXIT CODE, never on Test-Path: a stale vps_keyword_data.csv
    # left behind by an aborted earlier run would otherwise be merged as if it
    # had just been downloaded, resurrecting deleted rows and hiding the failure.
    if (Test-Path $vpsCopy) { Remove-Item $vpsCopy -Force }
    scp -P $VPS_PORT "${VPS_USER}@${VPS_HOST}:${VPS_PATH}/keyword_data.csv" $vpsCopy
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  ABORT: the VPS master exists but could not be downloaded."
        Write-Host "  Uploading now would destroy every keyword added on the server."
        exit 1
    }
    & $PYTHON -c "from src.harvest import merge_master; c,e = merge_master(r'$vpsCopy'); print(f'  carried in {c} VPS-only keyword(s), enriched {e}')"
    Remove-Item $vpsCopy -Force
} elseif ($probeRc -eq 1) {
    Write-Host "  no keyword_data.csv on the VPS yet - first deploy, local is the seed"
} else {
    Write-Host "  ABORT: could not reach the VPS to check for keyword_data.csv (ssh exit $probeRc)."
    Write-Host "  This is NOT the same as 'the server has no master'. Fix the connection and retry."
    exit 1
}

Write-Host "`n== 2/5  Harvest fresh keywords, then build POD + Embroidery =="
& $PYTHON main.py harvest        # enrich keywords.csv from the live YTrends index
& $PYTHON main.py daily pod
if ($LASTEXITCODE -ne 0) { Write-Host "daily pod failed - not syncing."; exit 1 }
& $PYTHON main.py daily embroidery
if ($LASTEXITCODE -ne 0) { Write-Host "daily embroidery failed - not syncing."; exit 1 }

Write-Host "`n== 3/5  Warm the local Trending/Opportunities cache (deep pull) =="
# Local only. This used to exist so data/agent.db could be shipped to the server;
# that upload has been removed (see rule 3 above), so this now just keeps THIS
# machine's pages fast. Seeding the server's cache needs an api_cache-only merge
# that leaves discovered_keywords alone - deliberately not built yet.
& $PYTHON main.py warm

Write-Host "`n== 4/5  Backing up the VPS data before writing to it =="
ssh -p $VPS_PORT "${VPS_USER}@${VPS_HOST}" "set -e; mkdir -p '$VPS_PATH/data' '$VPS_PATH/reports' '$VPS_PATH/backups'; for f in keyword_data.csv data/agent.db data/app.db; do if [ -f '$VPS_PATH'/`$f ]; then cp -p '$VPS_PATH'/`$f '$VPS_PATH/backups'/`$(basename `$f).$STAMP.bak; echo `"  backed up `$f`"; fi; done"
if ($LASTEXITCODE -ne 0) { Write-Host "  ABORT: could not back up the VPS data."; exit 1 }

Write-Host "`n== 5/5  Copying to the VPS (enter the etsy password when asked) =="
# keyword_data.csv lands via a temp name + atomic mv, so a dashboard read can
# never see a half-written master.
scp -P $VPS_PORT keyword_data.csv "${VPS_USER}@${VPS_HOST}:${VPS_PATH}/keyword_data.csv.tmp"
if ($LASTEXITCODE -ne 0) { Write-Host "  ABORT: upload failed."; exit 1 }
ssh -p $VPS_PORT "${VPS_USER}@${VPS_HOST}" "mv -f '$VPS_PATH/keyword_data.csv.tmp' '$VPS_PATH/keyword_data.csv'"
scp -P $VPS_PORT -r reports/latest "${VPS_USER}@${VPS_HOST}:${VPS_PATH}/reports/"
# NOTE: data/agent.db and data/app.db are deliberately NOT copied. See rule 3.

Write-Host "`nDone -> https://etsy.theglobalserviceteam.site"
Write-Host "Backups on the VPS: $VPS_PATH/backups/*.$STAMP.bak"
Write-Host "Tip: on the VPS run 'sudo systemctl restart etsy-web' only if code changed (data alone needs no restart)."
