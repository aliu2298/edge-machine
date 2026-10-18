#!/bin/bash
# vps_nasdaq_orb.sh — one trading day of the Nasdaq open breakout PAPER lane (nasdaq_orb.py).
#
# Reads market data only (Alpaca, keys in ~/.alpaca-credentials) and never places an order.
# nasdaq_orb.py --live sleeps until 9:20 New York time, snapshots QQQ's quote once a minute to
# 11:32 ET, waits for the SIP bars to be 15 minutes old, and grades the four variants into a day
# file OUTSIDE the clone (so the other scripts' 15-minute pulls never meet a dirty tree). This
# script then merges that file into data/nasdaq_orb_ledger.json and pushes it, under the same
# lock as local_closes.sh and vps_window_requests.sh.
#
# Live on edge-vps as a USER CRONTAB, one line, before 9:20 ET in both EST and EDT (13:05 UTC
# is 8:05 EST / 9:05 EDT; the script sleeps on the New York clock, so it is DST-safe):
#   5 13 * * 1-5 /home/<user>/edge-machine-closes/scripts/vps_nasdaq_orb.sh >> ~/nasdaq-orb.log 2>&1
set -uo pipefail
DIR="${EDGE_WINDOWS_DIR:-$HOME/edge-machine-closes}"
PY="${EDGE_WINDOWS_PY:-/usr/bin/python3}"
STATE="${NASDAQ_ORB_STATE:-$HOME/nasdaq_orb}"
stamp() { date -u +%Y-%m-%dT%H:%M:%SZ; }
cd "$DIR" || { echo "$(stamp) no clone at $DIR"; exit 1; }
mkdir -p "$STATE"
DAY="$(TZ=America/New_York date +%Y-%m-%d)"
DAYFILE="$STATE/day-$DAY.json"

echo "$(stamp) start $DAY"
"$PY" nasdaq_orb.py --live "$DAYFILE" || { echo "$(stamp) live run failed"; exit 0; }

if command -v flock >/dev/null 2>&1; then
  exec 9>"$(git rev-parse --git-dir)/edge-shared.lock"
  flock -w 600 9 || { echo "$(stamp) the clone is busy; day file kept at $DAYFILE"; exit 0; }
fi
for attempt in 1 2 3; do
  git pull -q --rebase origin main || { echo "$(stamp) pull failed"; sleep 30; continue; }
  "$PY" nasdaq_orb.py --merge "$DAYFILE" || { echo "$(stamp) merge failed"; exit 0; }
  git add -- data/nasdaq_orb_ledger.json
  if git diff --cached --quiet; then
    echo "$(stamp) nothing new for $DAY"
    exit 0
  fi
  git commit -q -m "Nasdaq open breakout paper observations ($DAY)"
  if git push -q origin HEAD:main; then
    echo "$(stamp) pushed $DAY"
    exit 0
  fi
  git reset -q --soft HEAD~1
  git restore -q --staged --worktree -- data/nasdaq_orb_ledger.json 2>/dev/null || true
done
echo "$(stamp) push failed after 3 attempts; day file kept at $DAYFILE"
exit 0
