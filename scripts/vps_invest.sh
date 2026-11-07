#!/bin/bash
# vps_invest.sh — the Kalshi Invest big-move lane (invest.py): the 1-minute collector and, every 15 minutes, the tracker.
#
# PAPER ONLY. invest.py reads Kalshi's PUBLIC perps market data, holds no key and never places, amends or cancels an
# order. Every minute it appends one snapshot (bid, ask, last, reference price of every Invest stock and index) to
# $WORK/ticks (outside the clone, 14 days kept). On minutes 0/15/30/45 it also logs and grades the big-move events
# and the Kalshi-only gaps into data/invest_state.json and pushes that one file, so the next page build shows it.
#
# Proposed USER CRONTAB line on edge-vps (installed only with Olu's OK, after `crontab -l > ~/crontab.bak.$(date +%F)`):
#   * * * * * /home/<user>/edge-machine-closes/scripts/vps_invest.sh >> ~/edge-invest.log 2>&1
# The body is one function called on the last line: bash reads a script as it runs, and a pull mid-run replaces it.
set -uo pipefail

main() {
  local DIR PY WORK minute stamp
  DIR="${EDGE_INVEST_DIR:-$HOME/edge-machine-closes}"
  PY="${EDGE_INVEST_PY:-/usr/bin/python3}"
  WORK="${EDGE_INVEST_WORK:-$HOME/invest}"
  stamp() { date -u +%Y-%m-%dT%H:%M:%SZ; }
  cd "$DIR" || { echo "$(stamp) no clone at $DIR"; exit 1; }
  mkdir -p "$WORK"
  # One collector at a time: a slow API call must not stack runs.
  exec 8>"$WORK/.collect.lock"
  if command -v flock >/dev/null 2>&1 && ! flock -n 8; then
    echo "$(stamp) previous run still going"; exit 0
  fi
  "$PY" invest.py collect --work "$WORK" >/dev/null || echo "$(stamp) collect failed"

  minute=$((10#$(date -u +%M)))
  [ $((minute % 15)) -eq 0 ] || exit 0

  locked() {
    if command -v flock >/dev/null 2>&1; then
      ( flock -w 120 9 || { echo "$(stamp) the clone is busy (lock held for 2 min)"; exit 1; }; "$@" ) 9>"$(git rev-parse --git-dir)/edge-shared.lock"
    else
      "$@"
    fi
  }
  locked git pull -q --rebase origin main || echo "$(stamp) pull failed; tracking on the checkout as it is"
  [ -f data/invest_state.json ] && cp data/invest_state.json "$WORK/state.json"
  "$PY" invest.py track --work "$WORK" --state "$WORK/state.json" >/dev/null || { echo "$(stamp) track failed"; exit 1; }
  "$PY" -c 'import json,sys; json.load(open(sys.argv[1]))' "$WORK/state.json" || { echo "$(stamp) state is not valid JSON"; exit 1; }

  publish() {
    git pull -q --rebase origin main || { echo "$(stamp) pull failed before publishing"; return 1; }
    cp "$WORK/state.json" data/invest_state.json
    git add -- data/invest_state.json
    if git diff --cached --quiet; then
      return 0
    fi
    git commit -q -m "Kalshi Invest paper tracker ($(date -u +%Y-%m-%dT%H:%MZ))"
    local attempt
    for attempt in 1 2 3; do
      if git push -q origin HEAD:main; then
        echo "$(stamp) published"
        return 0
      fi
      git pull -q --rebase origin main
    done
    echo "$(stamp) push failed after 3 attempts; the state stays at $WORK/state.json"
    return 1
  }
  # Publish hourly (minute 0) to keep commits few; the state is current in $WORK in between.
  [ "$minute" -eq 0 ] && locked publish
}

main "$@"
exit
