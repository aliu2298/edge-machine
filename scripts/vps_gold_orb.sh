#!/bin/bash
# vps_gold_orb.sh — one night of the Gold Asia-open breakout paper lane (gold_orb.py).
#
# Paper · never places an order. It reads Coinbase's public candles and book for the GOL gold
# future, writes the night into data/gold_orb_ledger.json and pushes that one file, so the
# Sandbox Tracker's next page build shows it.
#
# Live on edge-vps as a USER CRONTAB (no root on that box; see edge-crypto.service for why). The box
# runs UTC and both anchors are FIXED UTC instants on the night's next UTC day (2026-10-24: the primary
# anchor was the DST-following 8:00 pm CT, an hour early against the 7:30 pm CST spec):
#   01:00 UTC  the China-open shadow  (range 00:30-01:00 UTC)
#   02:00 UTC  the primary            (range 01:30-02:00 UTC = 7:30-8:00 pm CST; 8:30-9:00 pm CDT until Nov 1)
# so ONE start time covers both seasons: 00:54 UTC is 7:54 pm CDT and 6:54 pm CST, six minutes before
# the earliest anchor either way. The ranges are read back from Coinbase's candles, so the run need not
# be up for them. gold_orb.py waits between anchors without polling and ends at the last anchor + 60 min
# of signal + 1 + 15 min hold + 5 margin = 03:21 UTC, which the loop computes from the anchors itself.
# Mon-Fri UTC = Sun-Thu evenings in Chicago.
#   54 0 * * 1-5 /home/<user>/edge-machine-closes/scripts/vps_gold_orb.sh >> ~/edge-gold-orb.log 2>&1
# gold_orb.py itself refuses a non Sun-Thu night.
#
# The run lasts about 2.5 hours (00:54-03:21 UTC) in a clone that local_closes.sh and vps_window_requests.sh pull,
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
  # 2026-11-09: MERGE the repo ledger into the work file, never copy it over: a night whose publish failed lives only in
  # $WORK/ledger.json, and the Nov 8 night was erased by that copy. The repo's rows win on the same id (a re-grade
  # merged by PR is kept); every row only the work file holds is carried.
  if [ -f "$WORK/ledger.json" ] && [ -f data/gold_orb_ledger.json ]; then
    "$PY" gold_orb.py --from data/gold_orb_ledger.json --merge-unpublished "$WORK/ledger.json" --out "$WORK/ledger.merged.json" \
      && mv "$WORK/ledger.merged.json" "$WORK/ledger.json" \
      || echo "$(stamp) could not merge the ledgers; keeping $WORK/ledger.json as it is"
  elif [ -f data/gold_orb_ledger.json ]; then
    cp data/gold_orb_ledger.json "$WORK/ledger.json"
  fi
  "$PY" gold_orb.py --run --from "$WORK/ledger.json" --out "$WORK/ledger.json" || { echo "$(stamp) gold_orb.py failed"; exit 1; }
  "$PY" -c 'import json,sys; json.load(open(sys.argv[1]))' "$WORK/ledger.json" || { echo "$(stamp) the night is not valid JSON"; exit 1; }

  publish() {
    git pull -q --rebase origin main || { echo "$(stamp) pull failed before publishing"; return 1; }
    # Merge, too: a row the repo gained during the night (a restore or re-grade merged by PR) is never overwritten.
    "$PY" gold_orb.py --from data/gold_orb_ledger.json --merge-unpublished "$WORK/ledger.json" --out data/gold_orb_ledger.json \
      || { echo "$(stamp) merge failed before publishing"; git checkout -q -- data/gold_orb_ledger.json; return 1; }
    git add -- data/gold_orb_ledger.json
    if git diff --cached --quiet; then
      if [ "$(git rev-list --count origin/main..HEAD 2>/dev/null || echo 0)" = "0" ]; then
        echo "$(stamp) nothing new to publish"
        return 0
      fi
      echo "$(stamp) pushing the night committed by an earlier attempt"
    else
      git commit -q -m "Gold Asia-open breakout paper night ($(date -u +%Y-%m-%d))"
    fi
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
  # 2026-11-09: one busy-lock wait (2 min) used to end the night unpublished ("the clone is busy"). Retry with backoff,
  # about 40 minutes in all; a night still unpublished after that stays in the work file, is merged into the next
  # night's start (above) and goes out with it.
  local try pause=60
  for try in 1 2 3 4 5 6; do
    if locked publish; then
      return 0
    fi
    [ "$try" -lt 6 ] || break
    echo "$(stamp) publish attempt $try failed; retrying in ${pause}s"
    sleep "$pause"
    pause=$((pause * 2 > 600 ? 600 : pause * 2))
  done
  echo "$(stamp) not published after 6 attempts; the night stays in $WORK/ledger.json and goes out with the next run"
  return 1
}

main "$@"
exit
