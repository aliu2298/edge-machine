#!/bin/bash
# vps_nba_wm_decisions.sh — the NBA win margin executor's T-1h decision snapshots, pushed to main for paper v3 (installed 2026-11-03).
#
# Every 10 minutes from edge-vps (a USER crontab, like vps_window_requests.sh and the health snapshot):
#   */10 * * * * /home/<user>/edge-machine-closes/scripts/vps_nba_wm_decisions.sh >> /home/<user>/edge-nba-wm.log 2>&1
# nba_wm_publish.py reads the executor's own file (nba_wm_decisions.json in its working directory, never its ledger), refuses to write if
# anything outside its whitelist of PUBLIC market fields is present, and this script commits only data/nba_wm_decisions.json and data/top5_dip_decisions.json. It shares the
# edge-machine-closes clone with the other VPS jobs, so it takes the same lock and pulls with --rebase; no other writer touches that file.
# It uses the push route the other jobs already use: no new secret.
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
"$PY" nba_wm_publish.py || { echo "$(stamp) publish refused or failed"; exit 1; }
# the top-5 dip executor's snapshots ride the same entry (2026-11-05): a refusal there must not stop the NBA ones, so it only reports
"$PY" top5_dip_publish.py || echo "$(stamp) top-5 dip publish refused or failed"
git add data/nba_wm_decisions.json 2>/dev/null
git add data/top5_dip_decisions.json 2>/dev/null   # a missing file must not stop the NBA add above
if ! git diff --cached --quiet; then
  git commit -q -m "NBA win margin decision snapshots via vps ($(date -u +%Y-%m-%d\ %H:%MZ))"
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
