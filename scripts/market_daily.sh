#!/bin/bash
# market_daily.sh — the trading lane's daily run (weekdays, after the US close).
#
# It runs on the VPS, not in GitHub Actions, for one reason: the Alpaca keys live on machines
# we control and must not go to a CI runner. The run scans for new signals, grades the trades
# whose exit has happened, and publishes the updated ledger.
#
# It never places an order. The lane is a paper record of what the rules would have done.
#
# It publishes the LEDGER ONLY. public_site/*.html is built by the sandbox-tracker workflow in
# CI and by nothing else: two machines regenerating the same page collided on every push
# (2026-09-20), and the conflict was always in generated output neither side had edited by
# hand. CI rebuilds the page from this ledger on its next run, within three hours.
#
# Installed on the VPS as edge-market.timer -> edge-market.service:
#   OnCalendar=Mon-Fri 16:10 America/New_York
set -u
cd "$(dirname "$0")/.." || exit 1
export PATH="/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"

echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) market daily ==="

# Someone else may have published since the last run; rebase onto them before touching files.
git pull -q --rebase --autostash || { echo "pull failed — skipping this run"; exit 0; }

python3 market_track.py || { echo "market_track failed"; exit 1; }

git add data/market_ledger.json data/sp500.json
if git diff --cached --quiet; then
  echo "no change — nothing to publish"
  exit 0
fi
git commit -q -m "Trading lane ($(date -u +%Y-%m-%d\ %H:%MZ))"

# Only the ledger is in the commit, so a lost race is settled by a plain rebase.
for attempt in 1 2 3; do
  if git push -q origin main; then
    echo "published on attempt $attempt"
    exit 0
  fi
  echo "push rejected — rebasing onto the newer main (attempt $attempt)"
  git pull -q --rebase || break
done
echo "could not publish after 3 attempts"
exit 1
