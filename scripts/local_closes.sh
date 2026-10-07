#!/bin/bash
# local_closes.sh — Sandbox closing prices every 15 minutes, from whichever always-on host
# runs it: launchd on the Mac, edge-closes.timer on edge-vps. Both are installed.
#
# GitHub ran the 30-minute close job 3 times in 13 hours, so only ~53% of bets got a closing
# price inside 60 minutes of the start (38% on Kalshi soccer) — below the QA ready gate's
# half-of-bets bar for reasons that had nothing to do with any source. This runs the same
# sandbox_close.py from a DEDICATED clone (never the working copy) and commits only
# data/sandbox_closes/<writer>.json, which no other writer touches, so a rebase cannot
# conflict.
#
# THE WRITER FOLLOWS THE HOST, fixed 2026-10-06. This script was written for the Mac and
# hardcoded "mac" in both the writer flag and the commit message -- then the same script
# was installed on edge-vps, where it has been doing the work ever since while every
# commit on main said "via mac". The label pointed at the wrong machine, which is exactly
# the wrong thing to be told while debugging a gap in closing prices. Worse, the two hosts
# were aimed at the SAME per-writer file, which is the one collision that file layout
# exists to prevent; harmless only because the Mac's agent happened not to be loaded.
# uname decides, so neither host needs a config change and the Mac keeps mac.json and its
# history. The loader globs the directory, so a new name merges without any other edit.
#
# Install: see scripts/com.aliu.edge-machine-closes.plist.
set -uo pipefail
DIR="${EDGE_CLOSES_DIR:-$HOME/edge-machine-closes}"
PY="${EDGE_CLOSES_PY:-/opt/homebrew/bin/python3}"
case "$(uname -s)" in
  Darwin) WRITER="mac" ;;
  *)      WRITER="vps" ;;
esac
WRITER="${EDGE_CLOSES_WRITER:-$WRITER}"
stamp() { date -u +%Y-%m-%dT%H:%M:%SZ; }
cd "$DIR" || { echo "$(stamp) no clone at $DIR"; exit 1; }

# Start from main. Only this host's own writer file is ever written here, so rebasing
# cannot conflict, and an earlier commit that failed to push is kept rather than thrown away.
git pull -q --rebase origin main || { echo "$(stamp) pull failed"; exit 0; }

"$PY" sandbox_close.py --writer "$WRITER" || { echo "$(stamp) close snapshot failed"; exit 0; }

git add "data/sandbox_closes/$WRITER.json"
if ! git diff --cached --quiet; then
  git commit -q -m "Sandbox closing prices via $WRITER ($(date -u +%Y-%m-%d\ %H:%MZ))"
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
