#!/bin/bash
# vps_window_requests.sh — ask for every ladder lane's reads from inside its own window.
#
# Replaces vps_crypto_window.sh and vps_commodities_window.sh (2026-10-13). Those asked for
# ONE read a day each, and the commodities one was never installed in the crontab, so the
# 14:30 ET WTI window got a read only when some unrelated run happened to land in it. The
# Econ and Finance Daily lanes had no request at all and waited on GitHub's hourly cron,
# which never fired in their first four hours.
#
# lane_windows.py decides everything from each lane's own constants: the windows (2-3.5h
# before each close, measured to the CLOSE), up to three reads 30 minutes apart, and no
# later read once every series of that close holds an entry. This script only writes what
# it prints into the stamp files and pushes them in ONE commit, so a crypto and a commodity
# read due in the same 17:00 ET window start one tracker run, not two:
#   data/crypto_window/**, data/commodities_window/**,
#   data/ftts_window/**                                -> sandbox-tracker.yml
#   data/daily_window/**                               -> daily-research.yml
#   data/nba_window/**                                 -> nba-rules.yml (2026-10-17)
#   data/culture_window/**                             -> culture.yml (2026-10-17)
#   data/soccer_rules_window/**                        -> soccer-rules.yml (2026-10-17)
#   data/soccer_team_rules_window/**                   -> soccer-team-rules.yml (2026-10-17)
#
# The stamp names the close and the read number, so git is the once-per-read guard: the
# second 15-minute run inside a read finds nothing to commit, and every later run is a free
# retry of a failed push.
#
# Live on edge-vps as a USER CRONTAB (no root; see edge-crypto.timer for why):
#   */15 * * * * /home/<user>/edge-machine-closes/scripts/vps_window_requests.sh >> ~/edge-windows.log 2>&1
set -uo pipefail
DIR="${EDGE_WINDOWS_DIR:-$HOME/edge-machine-closes}"
PY="${EDGE_WINDOWS_PY:-/usr/bin/python3}"
stamp() { date -u +%Y-%m-%dT%H:%M:%SZ; }
cd "$DIR" || { echo "$(stamp) no clone at $DIR"; exit 1; }

# ONE GIT USER AT A TIME. local_closes.sh and vps_window_requests.sh share this clone on
# edge-vps and both pull, commit and push every 15 minutes; on 2026-10-13 they met twice
# ("cannot lock ref", "Cannot rebase onto multiple branches"). Both take this lock, waiting
# up to two minutes, and a run that cannot get it exits and leaves the retry to the next one.
# flock is util-linux: on a Mac without it the script runs as before.
if command -v flock >/dev/null 2>&1; then
  exec 9>"$(git rev-parse --git-dir)/edge-shared.lock"
  flock -w 120 9 || { echo "$(stamp) the clone is busy (lock held for 2 min); next run retries"; exit 0; }
fi

git pull -q --rebase origin main || { echo "$(stamp) pull failed"; exit 0; }

DUE="$("$PY" lane_windows.py --due)" || { echo "$(stamp) lane_windows.py failed"; exit 0; }
if [ -z "$DUE" ]; then
  echo "$(stamp) no read due"
  exit 0
fi

while IFS=$'\t' read -r path text; do
  [ -z "$path" ] && continue
  case "$path" in
    data/crypto_window/request.txt|data/commodities_window/request.txt|data/daily_window/request.txt|data/ftts_window/request.txt|data/nba_window/request.txt|data/culture_window/request.txt|data/soccer_rules_window/request.txt|data/soccer_team_rules_window/request.txt) ;;
    *) echo "$(stamp) refusing unexpected stamp path $path"; exit 1 ;;
  esac
  mkdir -p "$(dirname "$path")"
  printf '%s\n' "$text" > "$path"
  git add -- "$path"
done <<< "$DUE"

if git diff --cached --quiet; then
  echo "$(stamp) every due read was already asked for"
  exit 0
fi
git commit -q -m "Lane windows: $(echo "$DUE" | cut -f2 | tr '\n' ' ' | cut -c1-150) ($(date -u +%H:%MZ))"
for attempt in 1 2 3; do
  if git push -q origin HEAD:main; then
    echo "$(stamp) asked: $(echo "$DUE" | cut -f2 | tr '\n' ' ')"
    exit 0
  fi
  git pull -q --rebase origin main
done
echo "$(stamp) push failed after 3 attempts — the next 15-minute run retries"
exit 0
