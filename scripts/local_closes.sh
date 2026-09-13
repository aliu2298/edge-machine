#!/bin/bash
# local_closes.sh — Sandbox closing prices from the always-on Mac, every 15 minutes (launchd).
#
# GitHub ran the 30-minute close job 3 times in 13 hours, so only ~53% of bets got a closing
# price inside 60 minutes of the start (38% on Kalshi soccer) — below the QA ready gate's
# half-of-bets bar for reasons that had nothing to do with any source. This runs the same
# sandbox_close.py from a DEDICATED clone (never the working copy) and commits only
# data/sandbox_closes/mac.json, which no other writer touches, so a rebase cannot conflict.
#
# Install: see scripts/com.aliu.edge-machine-closes.plist.
set -uo pipefail
DIR="${EDGE_CLOSES_DIR:-$HOME/edge-machine-closes}"
PY="${EDGE_CLOSES_PY:-/opt/homebrew/bin/python3}"
stamp() { date -u +%Y-%m-%dT%H:%M:%SZ; }
cd "$DIR" || { echo "$(stamp) no clone at $DIR"; exit 1; }

# Start from main. Only mac.json is ever written here, so rebasing cannot conflict, and an
# earlier commit that failed to push is kept rather than thrown away.
git pull -q --rebase origin main || { echo "$(stamp) pull failed"; exit 0; }

"$PY" sandbox_close.py --writer mac || { echo "$(stamp) close snapshot failed"; exit 0; }

git add data/sandbox_closes/mac.json
if ! git diff --cached --quiet; then
  git commit -q -m "Sandbox closing prices via mac ($(date -u +%Y-%m-%d\ %H:%MZ))"
fi
# Push whatever is ahead of origin (this run's commit, or an earlier one that failed to push).
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
