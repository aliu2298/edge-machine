#!/bin/bash
# vps_gold_orb.sh — one night of the Gold Asia-open breakout paper lane (gold_orb.py).
#
# Paper · never places an order. It reads Coinbase's public candles and book for the GOL gold
# future, writes the night into data/gold_orb_ledger.json and pushes that one file, so the
# Sandbox Tracker's next page build shows it.
#
# Live on edge-vps as a USER CRONTAB (no root on that box; see edge-crypto.service for why). The box
# runs UTC and the night has two anchors, 8:00 pm America/Chicago and the fixed 01:00 UTC
# shadow, so ONE start time covers both seasons: 00:54 UTC is 7:54 pm CDT and 6:54 pm CST,
# six minutes before the earlier anchor either way (after Nov 1 the run waits from 6:54 pm CST
# for the 7:00 pm shadow, then the 8:00 pm anchor). The 7:30 pm range is read back from
# Coinbase's candles, so the run need not be up for it. Mon-Fri UTC = Sun-Thu evenings in Chicago.
#   54 0 * * 1-5 /home/<user>/edge-machine-closes/scripts/vps_gold_orb.sh >> ~/edge-gold-orb.log 2>&1
# gold_orb.py itself refuses a non Sun-Thu night and stops once both anchors resolve (by about
# 9:20 pm CT at the latest).
#
# The run lasts up to 2.5 hours in a clone that local_closes.sh and vps_window_requests.sh pull,
# commit and push every 15 minutes. So the night is written OUTSIDE the clone ($WORK) while it
# runs — an uncommitted change to a tracked file would make their `git pull --rebase` fail —
# and the shared lock is held only for the pull at the start and the commit and push at the end.
# The body is one function called on the last line: bash reads a script as it runs, and a pull
# mid-run replaces this file.
set -uo pipefail

main() {
  local DIR PY WORK stamp
  DIR="${EDGE_GOLD_DIR:-$HOME/edge-machine-closes}"
  PY="${EDGE_GOLD_PY:-/usr/bin/python3}"
  WORK="${EDGE_GOLD_WORK:-$HOME/gold-orb}"
  stamp() { date -u +%Y-%m-%dT%H:%M:%SZ; }
  cd "$DIR" || { echo "$(stamp) no clone at $DIR"; exit 1; }
  mkdir -p "$WORK"

  locked() {
    if command -v flock >/dev/null 2>&1; then
      ( flock -w 120 9 || { echo "$(stamp) the clone is busy (lock held for 2 min)"; exit 1; }; "$@" ) 9>"$(git rev-parse --git-dir)/edge-shared.lock"
    else
      "$@"
    fi
  }

  echo "=== $(stamp) gold orb ==="
  locked git pull -q --rebase origin main || echo "$(stamp) pull failed; running on the checkout as it is"
  if [ -f data/gold_orb_ledger.json ]; then
    cp data/gold_orb_ledger.json "$WORK/ledger.json"
  fi
  "$PY" gold_orb.py --run --from "$WORK/ledger.json" --out "$WORK/ledger.json" || { echo "$(stamp) gold_orb.py failed"; exit 1; }
  "$PY" -c 'import json,sys; json.load(open(sys.argv[1]))' "$WORK/ledger.json" || { echo "$(stamp) the night is not valid JSON"; exit 1; }

  publish() {
    git pull -q --rebase origin main || { echo "$(stamp) pull failed before publishing"; return 1; }
    cp "$WORK/ledger.json" data/gold_orb_ledger.json
    git add -- data/gold_orb_ledger.json
    if git diff --cached --quiet; then
      echo "$(stamp) nothing new to publish"
      return 0
    fi
    git commit -q -m "Gold Asia-open breakout paper night ($(date -u +%Y-%m-%d))"
    local attempt
    for attempt in 1 2 3; do
      if git push -q origin HEAD:main; then
        echo "$(stamp) published"
        return 0
      fi
      git pull -q --rebase origin main
    done
    echo "$(stamp) push failed after 3 attempts; the ledger stays at $WORK/ledger.json"
    return 1
  }
  locked publish
}

main "$@"
exit
