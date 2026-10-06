#!/bin/bash
# vps_crypto_window.sh — ask for a tracker run from inside crypto_fav_band's window.
#
# WHY THE VPS AND NOT THE MAC. crypto_fav_band reads the Kalshi coin ladders 2-3.5h
# before their 17:00 ET close, a 90-minute window. GitHub's cron cannot hold it: over 18
# days the tracker ran 4.2 times a day against 8 scheduled and landed inside the window on
# 10 of 18. The first fix put a launchd timer on the Mac, which was the wrong host and
# failed on its first day in exactly the way a laptop fails -- it woke 12 minutes late and
# had no DNS yet, so the dispatch died on "Could not resolve host". This box has been up
# 19 days and already runs five timers on this cadence.
#
# WHY A STAMP FILE AND NOT AN API DISPATCH. This host authenticates to GitHub with an SSH
# deploy key and holds no API token. Rather than add a credential, it writes one line to
# data/crypto_window/request.txt and pushes; sandbox-tracker.yml triggers on a push to that
# path alone. A push from a deploy key is a real event and does start a workflow, where a
# dispatch made with the repository's own GITHUB_TOKEN would not.
#
# WHY IT RUNS EVERY 15 MINUTES. The content is the close's own date, so git itself is the
# once-a-day guard: the second run of a window finds nothing to commit and pushes nothing.
# That makes every later run a free retry of a failed earlier one, which is the whole of
# what went wrong on the Mac, and it needs no state of its own.
#
# Install: see scripts/edge-crypto.timer.
set -uo pipefail
DIR="${EDGE_CRYPTO_DIR:-$HOME/edge-machine-closes}"
PY="${EDGE_CRYPTO_PY:-/usr/bin/python3}"
stamp() { date -u +%Y-%m-%dT%H:%M:%SZ; }
cd "$DIR" || { echo "$(stamp) no clone at $DIR"; exit 1; }

git pull -q --rebase origin main || { echo "$(stamp) pull failed"; exit 0; }

# The repo's own constants decide, so this can never drift from the lane. Prints the
# close's date on success, which becomes the stamp.
WHEN="$("$PY" - <<'PYEOF'
import datetime, sys
sys.path.insert(0, ".")
import sandbox_sources as S
now = datetime.datetime.now(datetime.timezone.utc)
et = now.astimezone(S.CRYPTO_FAV_TZ)
close = et.replace(hour=S.CRYPTO_FAV_CLOSE_ET, minute=5, second=0, microsecond=0)
hours = (close - et).total_seconds() / 3600
if not (S.CRYPTO_FAV_MIN_H <= hours <= S.CRYPTO_FAV_MAX_H):
    print(f"outside: {hours:.2f}h to the close", file=sys.stderr)
    sys.exit(1)
print(close.date().isoformat())
PYEOF
)" || { echo "$(stamp) outside the window, nothing asked"; exit 0; }

mkdir -p data/crypto_window
echo "$WHEN" > data/crypto_window/request.txt
git add data/crypto_window/request.txt
if git diff --cached --quiet; then
  echo "$(stamp) the $WHEN window was already asked for"
  exit 0
fi
git commit -q -m "Crypto window $WHEN ($(date -u +%H:%MZ))"
for attempt in 1 2 3; do
  if git push -q origin HEAD:main; then
    echo "$(stamp) asked for a tracker run in the $WHEN window"
    exit 0
  fi
  git pull -q --rebase origin main
done
echo "$(stamp) push failed after 3 attempts — the next 15-minute run retries"
exit 0
