#!/bin/bash
# local_crypto_window.sh — dispatch the tracker from this Mac inside the crypto band's window.
#
# WHY THIS EXISTS. crypto_fav_band reads the Kalshi coin ladders 2-3.5h before their 17:00 ET
# close, a 90-minute window. GitHub's cron cannot hit it: measured over 18 days the tracker
# ran 4.2 times a day against 8 scheduled, with start minutes scattered across all sixty and
# no concentration at the nominal :11, and a run landed inside the window on only 10 of 18
# days. A 90-minute window is narrower than that scheduler's jitter, so adding cron slots
# does not fix it -- the slots are not honoured.
#
# WHY IT DISPATCHES INSTEAD OF RUNNING THE TRACKER. The lane needs collect() and publish(),
# which write data/sandbox_ledger.json. GitHub's tracker writes the same file, and two
# writers on one JSON file is a rebase conflict waiting to happen -- the closes job avoids
# exactly that by owning data/sandbox_closes/mac.json and nothing else. So this supplies
# only what GitHub lacks, which is a reliable clock: launchd fires on time, `gh workflow
# run` starts the run within seconds, and GitHub stays the single writer of the ledger.
#
# WHY 13:15 LOCAL AND NOT A UTC TIME. Kalshi's close is 17:00 EASTERN and this Mac keeps
# Central time, and the two shift on the same date, so 13:15 local is permanently 2.83h
# before the close -- 18:15Z under CDT, 19:15Z under CST, in the window either way. A fixed
# UTC slot would have fallen out of the window at the November DST change.
#
# Install: see scripts/com.aliu.edge-machine-crypto.plist.
set -uo pipefail
DIR="${EDGE_CLOSES_DIR:-$HOME/edge-machine-closes}"
PY="${EDGE_CLOSES_PY:-/opt/homebrew/bin/python3}"
stamp() { date -u +%Y-%m-%dT%H:%M:%SZ; }
cd "$DIR" || { echo "$(stamp) no clone at $DIR"; exit 1; }

git pull -q --rebase origin main || echo "$(stamp) pull failed, checking the window anyway"

# Refuse outside the window rather than spend a tracker run. launchd also fires at load and
# can fire late after a wake, and the lane's own gate would log nothing then -- but the run
# would still cost a Kalshi sweep and an Odds API slice. The repo's own constants decide,
# so this check can never drift from the lane.
if ! "$PY" - <<'PYEOF'
import datetime, sys
sys.path.insert(0, ".")
import sandbox_sources as S
now = datetime.datetime.now(datetime.timezone.utc)
et = now.astimezone(S.CRYPTO_FAV_TZ)
close = et.replace(hour=S.CRYPTO_FAV_CLOSE_ET, minute=5, second=0, microsecond=0)
hours = (close - et).total_seconds() / 3600
inside = S.CRYPTO_FAV_MIN_H <= hours <= S.CRYPTO_FAV_MAX_H
print(f"{hours:.2f}h to the {S.CRYPTO_FAV_CLOSE_ET}:05 ET close -> "
      f"{'inside' if inside else 'outside'} the {S.CRYPTO_FAV_MIN_H}-{S.CRYPTO_FAV_MAX_H}h window")
sys.exit(0 if inside else 1)
PYEOF
then
  echo "$(stamp) outside the window, not dispatching"
  exit 0
fi

# STOPGAP, and it is labelled as one. The VPS (scripts/vps_crypto_window.sh) is taking
# this over; this host keeps it only until that timer is installed, because a laptop is
# the wrong place for a clock. Remove this plist once the VPS timer is running, or both
# will ask for the same run.
#
# RETRIES, because the first live window died without one. launchd ran this on WAKE at
# 18:27Z rather than at 18:15, and a Mac waking from sleep has no DNS for a few seconds:
# "Could not resolve host: github.com". It then gave up and logged that the three-hourly
# cron was the fallback -- which had already been measured at 4.2 runs a day against 8
# scheduled, and on that day delivered no run inside the window at all. The window is 90
# minutes wide, so a few attempts over a minute cost nothing and cover exactly that race.
#
# gh reads its own keychain token; no secret lives in this file or the plist.
if ! command -v gh >/dev/null 2>&1; then
  echo "$(stamp) gh not on PATH, cannot dispatch"
  exit 0
fi
for attempt in 1 2 3 4 5; do
  if gh workflow run sandbox-tracker.yml --ref main --repo aliu2298/edge-machine 2>&1; then
    echo "$(stamp) dispatched sandbox-tracker for the crypto window (attempt $attempt)"
    exit 0
  fi
  echo "$(stamp) dispatch attempt $attempt failed, retrying in 20s"
  sleep 20
done
echo "$(stamp) dispatch failed after 5 attempts"
exit 0
