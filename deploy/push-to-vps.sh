#!/usr/bin/env bash
# push-to-vps.sh — build reports locally (where YTrends fetching works), then
# copy the fresh data + reports to the VPS so the team dashboard shows the
# latest. The VPS itself can't fetch YTrends (its datacenter IP is blocked),
# so this is how the server stays up to date.
#
# Usage (from anywhere):   bash deploy/push-to-vps.sh
# Override python if needed:  PYTHON=python3 bash deploy/push-to-vps.sh
set -euo pipefail

VPS_HOST=51.79.200.65
VPS_PORT=55317
VPS_USER=etsy
VPS_PATH=/home/etsy/etsy-agent

cd "$(dirname "$0")/.."   # repo root
PYTHON=${PYTHON:-$([ -x .venv/bin/python ] && echo .venv/bin/python || echo python)}

echo "== 1/2  Harvest fresh keywords, then build POD + Embroidery =="
"$PYTHON" main.py harvest || true   # enrich keywords.csv from the live YTrends index
"$PYTHON" main.py daily pod || { echo "daily pod failed - not syncing."; exit 1; }
"$PYTHON" main.py daily embroidery || { echo "daily embroidery failed - not syncing."; exit 1; }

echo
echo "== 2/2  Copying to the VPS (enter the etsy password when asked) =="
scp -P "$VPS_PORT" keyword_data.csv "$VPS_USER@$VPS_HOST:$VPS_PATH/keyword_data.csv"
scp -P "$VPS_PORT" -r reports/latest "$VPS_USER@$VPS_HOST:$VPS_PATH/reports/"

echo
echo "Done -> https://etsy.theglobalserviceteam.site"
