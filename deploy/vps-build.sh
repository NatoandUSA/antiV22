#!/usr/bin/env bash
# Build the team reports ON the VPS, straight from the live YTrends MCP — no
# laptop needed. Reports land in reports/latest, which the portal already serves,
# so the dashboard refreshes itself. Point a cron job at this script (see
# DEPLOY_VPS.md) to keep the reports current 24/7 with your PC off.
cd "$(dirname "$0")/.." || exit 1
PY="${PYTHON:-.venv/bin/python}"
[ -x "$PY" ] || PY="python3"

echo "=== vps-build start: $(date) ==="
"$PY" main.py harvest            || echo "harvest failed (continuing)"
"$PY" main.py daily pod          || echo "daily pod failed"
"$PY" main.py daily embroidery   || echo "daily embroidery failed"
"$PY" main.py autopull           || echo "autopull failed (continuing)"
echo "=== vps-build done:  $(date) ==="
