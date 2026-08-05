#!/usr/bin/env bash
# push-to-vps.sh — build reports locally (where YTrends fetching works), then
# copy the fresh data + reports to the VPS so the team dashboard shows the
# latest. The VPS itself can't fetch YTrends (its datacenter IP is blocked),
# so this is how the server stays up to date.
#
# Usage (from anywhere):   bash deploy/push-to-vps.sh
# Override python if needed:  PYTHON=python3 bash deploy/push-to-vps.sh
#
# KEEP IN STEP WITH deploy/push-to-vps.ps1. This script used to stop at "scp the
# local keyword_data.csv over the server's", which DELETED every keyword the team
# had added on the VPS through the web UI — Keyword Lab, long-tail pulls,
# extension drops. The union step below is the fix. It landed in the .ps1 and was
# never applied here, so the Mac path kept the deletion bug: measured on
# 2026-08-05 the server held 178 keywords this machine did not.
# `tests/test_deploy_scripts.py` now pins both scripts to merge before they push.
set -euo pipefail

VPS_HOST=51.79.200.65
VPS_PORT=55317
VPS_USER=etsy
VPS_PATH=/home/etsy/etsy-agent

cd "$(dirname "$0")/.."   # repo root
PYTHON=${PYTHON:-$([ -x .venv/bin/python ] && echo .venv/bin/python || echo python)}

echo "== 1/4  Harvest fresh keywords, then build POD + Embroidery =="
"$PYTHON" main.py harvest || true   # enrich keywords.csv from the live YTrends index
"$PYTHON" main.py daily pod || { echo "daily pod failed - not syncing."; exit 1; }
"$PYTHON" main.py daily embroidery || { echo "daily embroidery failed - not syncing."; exit 1; }

echo
echo "== 2/4  Warm the live Trending/Opportunities cache (deep pull) =="
# The VPS IP is blocked from YTrends, so its live keyword pages can't fetch. We
# warm the cache here and ship data/agent.db up, so the team gets the same deep,
# instant lists on the server. (agent.db is the KEYWORD cache + discovered-keyword
# history only; team logins/tasks/activity live in data/app.db and are NOT touched.)
"$PYTHON" main.py warm

echo
echo "== 3/4  Merging the VPS keyword base into this one =="
# The PC harvests but the TEAM adds keywords on the VPS through the web UI. Pull
# the server's copy down, union the two, then push the union: neither machine can
# destroy the other's keywords. merge_master() never deletes — local metrics win,
# blanks are filled from the server, and the earliest collected_at survives.
VPS_COPY=data/vps_keyword_data.csv
mkdir -p data
if scp -P "$VPS_PORT" "$VPS_USER@$VPS_HOST:$VPS_PATH/keyword_data.csv" "$VPS_COPY" 2>/dev/null; then
    "$PYTHON" -c "from src.harvest import merge_master; c,e = merge_master('$VPS_COPY'); print(f'  carried in {c} VPS-only keyword(s), enriched {e}')"
    rm -f "$VPS_COPY"
else
    echo "  no keyword_data.csv on the VPS yet - nothing to merge"
fi

echo
echo "== 4/4  Copying to the VPS (enter the etsy password when asked) =="
scp -P "$VPS_PORT" keyword_data.csv "$VPS_USER@$VPS_HOST:$VPS_PATH/keyword_data.csv"
scp -P "$VPS_PORT" -r reports/latest "$VPS_USER@$VPS_HOST:$VPS_PATH/reports/"
# agent.db is a live SQLite file the dashboard reads; copy to a temp name then
# atomically rename on the VPS so a concurrent read can never see a half-written db.
scp -P "$VPS_PORT" data/agent.db "$VPS_USER@$VPS_HOST:$VPS_PATH/data/agent.db.tmp"
ssh -p "$VPS_PORT" "$VPS_USER@$VPS_HOST" "mv -f $VPS_PATH/data/agent.db.tmp $VPS_PATH/data/agent.db"

echo
echo "Done -> https://etsy.theglobalserviceteam.site"
echo "Tip: on the VPS run 'sudo systemctl restart etsy-web' only if code changed (data alone needs no restart)."
