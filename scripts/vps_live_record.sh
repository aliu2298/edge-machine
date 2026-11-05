#!/bin/bash
# vps_live_record.sh — the follower's live record per Production pair, pushed to main for the Production page (2026-11-04).
#
# Hourly from edge-vps (a USER crontab, like vps_window_requests.sh and the NBA win margin decisions snapshot):
#   7 * * * * /home/<user>/edge-machine-closes/scripts/vps_live_record.sh >> /home/<user>/edge-live-record.log 2>&1
# live_record_publish.py reads the follower's own files (orders_placed.json, results.json, ledger.jsonl, o35_state.json, nba_wm_state.json: read-only),
# reads Kalshi's PUBLIC market results (cached in ~/live_record_results.json), and writes data/live_record.json after refusing anything outside
# its whitelist of public fields (no balance, order id, account, key or dollar figure). This script commits only that file. It shares the
# edge-machine-closes clone with the other VPS jobs, so it takes the same lock and pulls with --rebase. No new secret: it uses the push route
# the other jobs already use.
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
"$PY" live_record_publish.py || { echo "$(stamp) publish refused or failed"; exit 1; }
git add data/live_record.json 2>/dev/null
if ! git diff --cached --quiet; then
  git commit -q -m "Live record per Production pair via vps ($(date -u +%Y-%m-%d\ %H:%MZ))"
fi
if [ -n "$(git log origin/main..HEAD --oneline 2>/dev/null)" ]; then
  for attempt in 1 2 3; do
    if git push -q origin HEAD:main; then
      echo "$(stamp) pushed"
      exit 0
    fi
    git pull -q --rebase origin main
  done
  echo "$(stamp) push failed after 3 attempts; will retry next run"
fi
exit 0
