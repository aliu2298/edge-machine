#!/bin/bash
# vps_commodities_window.sh — ask for a tracker run from inside commod_fav_band's windows.
#
# The commodity favourite-band lane reads the Kalshi commodity ladders 2-3.5h before
# their close, and there are TWO closes: WTI at 14:30 Eastern (window 10:00-11:30
# Central) and Brent, gold, silver, copper and natural gas at 17:00 Eastern (window
# 12:30-14:00 Central, the crypto lane's own). GitHub's cron cannot hold a 90-minute
# window (see vps_crypto_window.sh for the measurement), so this host asks for a run from
# inside each window the same way the crypto script does: one line in a stamp file, pushed
# with the deploy key, which sandbox-tracker.yml triggers on.
#
# WHY IT DEFERS TO THE CRYPTO REQUEST IN THE 17:00 WINDOW. One tracker run serves every
# lane whose window is open, so when data/crypto_window/request.txt already carries
# today's date the 17:00 ET run has been asked for and asking again would only queue a
# second run. If the crypto lane ever stops asking, this script asks instead, so the
# commodity read does not silently depend on another lane's schedule.
#
# WHY IT RUNS EVERY 15 MINUTES ON WEEKDAYS. The stamp is the close's own date and hour, so
# git is the once-a-window guard: a second run inside a window finds nothing to commit.
# Every later run is a free retry of a failed earlier one. The ladders do not exist on
# weekends or exchange holidays; the repo's own calendar refuses those days, and the
# crontab simply does not fire on Saturday or Sunday.
#
# Live on edge-vps as a USER CRONTAB (no root; see edge-crypto.timer for why):
#   */15 15-20 * * 1-5 /home/<user>/edge-machine-closes/scripts/vps_commodities_window.sh >> ~/edge-commodities.log 2>&1
# 15:00-20:59 UTC covers both windows under daylight and standard time: the WTI window is
# 15:00-16:30Z under EDT and 16:00-17:30Z under EST; the 17:00 ET window is 17:30-19:00Z
# under EDT and 18:30-20:00Z under EST. The script's own check decides what is inside.
set -uo pipefail
DIR="${EDGE_COMMOD_DIR:-$HOME/edge-machine-closes}"
PY="${EDGE_COMMOD_PY:-/usr/bin/python3}"
stamp() { date -u +%Y-%m-%dT%H:%M:%SZ; }
cd "$DIR" || { echo "$(stamp) no clone at $DIR"; exit 1; }

git pull -q --rebase origin main || { echo "$(stamp) pull failed"; exit 0; }

# The repo's own constants and calendar decide, so this can never drift from the lane.
# Prints "<close date> <close HH:MM ET>" when now is inside a window on a trading day.
WHEN="$("$PY" - <<'PYEOF'
import datetime, sys
sys.path.insert(0, ".")
import sandbox_sources as S
now = datetime.datetime.now(datetime.timezone.utc)
for label, series, start, end, close in S.commod_fav_windows(now):
    if start <= now <= end:
        et = close.astimezone(S.COMMOD_FAV_TZ)
        print(f"{et.date().isoformat()} {et:%H:%M}")
        sys.exit(0)
print("outside every window", file=sys.stderr)
sys.exit(1)
PYEOF
)" || { echo "$(stamp) outside the windows, nothing asked"; exit 0; }

DAY="${WHEN%% *}"
HOUR="${WHEN##* }"
# The 17:00 ET window is the crypto lane's window. If that lane has already asked for
# today's run, one run serves both and a second request would only queue another.
if [ "$HOUR" = "17:00" ] && [ -f data/crypto_window/request.txt ] \
   && grep -qx "$DAY" data/crypto_window/request.txt; then
  echo "$(stamp) the $DAY 17:00 ET window was already asked for by the crypto lane"
  exit 0
fi

mkdir -p data/commodities_window
echo "$WHEN" > data/commodities_window/request.txt
git add data/commodities_window/request.txt
if git diff --cached --quiet; then
  echo "$(stamp) the $WHEN window was already asked for"
  exit 0
fi
git commit -q -m "Commodities window $WHEN ($(date -u +%H:%MZ))"
for attempt in 1 2 3; do
  if git push -q origin HEAD:main; then
    echo "$(stamp) asked for a tracker run in the $WHEN window"
    exit 0
  fi
  git pull -q --rebase origin main
done
echo "$(stamp) push failed after 3 attempts — the next 15-minute run retries"
exit 0
