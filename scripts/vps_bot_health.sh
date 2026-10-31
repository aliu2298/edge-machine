#!/bin/bash
# vps_bot_health.sh — the trading engine's health as status only, hourly, from edge-vps (edge-health.timer).
#
# Installed 2026-10-30 for the twice-daily cloud health check, which reads data/bot_health.json from main
# instead of a shell on the server. bot_health.py builds the file read-only from the engine's local status API
# and files (no secret is read, no exchange is called), refuses to write it if it carries a $ amount, a
# money field holding a number or a key-like string, and this script commits only that one file. It
# shares the edge-machine-closes clone with local_closes.sh and vps_window_requests.sh, so it takes the
# same lock and pulls with --rebase; no other writer touches data/bot_health.json, so a rebase cannot
# conflict. The LOW-balance threshold lives here only: BOT_HEALTH_LOW_USD in the unit (default 50).
set -uo pipefail
DIR="${EDGE_CLOSES_DIR:-$HOME/edge-machine-closes}"
PY="${EDGE_CLOSES_PY:-/usr/bin/python3}"
stamp() { date -u +%Y-%m-%dT%H:%M:%SZ; }
cd "$DIR" || { echo "$(stamp) no clone at $DIR"; exit 1; }
if command -v flock >/dev/null 2>&1; then
  exec 9>"$(git rev-parse --git-dir)/edge-shared.lock"
  flock -w 120 9 || { echo "$(stamp) the clone is busy (lock held for 2 min); next run retries"; exit 0; }
fi
git pull -q --rebase origin main || { echo "$(stamp) pull failed"; exit 0; }
"$PY" bot_health.py --out data/bot_health.json || { echo "$(stamp) health snapshot refused or failed"; exit 1; }
git add data/bot_health.json
if ! git diff --cached --quiet; then
  git commit -q -m "Engine health (status only) via vps ($(date -u +%Y-%m-%d\ %H:%MZ))"
fi
if [ -n "$(git log origin/main..HEAD --oneline 2>/dev/null)" ]; then
  for attempt in 1 2 3; do
    if git push -q origin HEAD:main; then
      echo "$(stamp) pushed"
      exit 0
    fi
    git pull -q --rebase origin main
  done
  echo "$(stamp) push failed after 3 attempts — will retry next run"
fi
exit 0
