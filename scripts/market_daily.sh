#!/bin/bash
# market_daily.sh — the trading lane's daily run, on THIS Mac (weekdays, after the close).
#
# It lives here rather than in GitHub Actions for one reason: the Alpaca keys are on this
# machine and must stay here. The run scans for new signals, grades the trades whose exit has
# happened, rebuilds the Sandbox page and publishes the updated record.
#
# It never places an order. The lane is a paper record of what the rules would have done.
#
# Installed in cron as:
#   10 15 * * 1-5 /Users/oluwarotimialiu/Predictions/scripts/market_daily.sh >> ~/Predictions/data/market_daily.log 2>&1
set -u
cd "$(dirname "$0")/.." || exit 1
export PATH="/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"

echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) market daily ==="

# Someone else may have published since the last run; rebase onto them before touching files.
git pull -q --rebase --autostash || { echo "pull failed — skipping this run"; exit 0; }

python3 market_track.py || { echo "market_track failed"; exit 1; }
python3 sandbox_build.py >/dev/null || echo "page build failed — keeping the previous page"

git add data/market_ledger.json data/sp500.json public_site/sandbox.html public_site/production.html
if git diff --cached --quiet; then
  echo "no change — nothing to publish"
  exit 0
fi
git commit -q -m "Trading lane ($(date -u +%Y-%m-%d\ %H:%MZ))"

# The Sandbox tracker publishes the same page from CI, so a push can lose a race. Rebase onto
# whatever won and try again; the ledger is accumulative, so re-deriving on top is always safe.
for attempt in 1 2 3; do
  if git push -q origin main; then
    echo "published on attempt $attempt"
    exit 0
  fi
  echo "push rejected — rebuilding on top of the newer board (attempt $attempt)"
  git pull -q --rebase --autostash || break
  python3 sandbox_build.py >/dev/null
  git add public_site/sandbox.html public_site/production.html data/market_ledger.json
  git diff --cached --quiet || git commit -q --amend --no-edit
done
echo "could not publish after 3 attempts"
exit 1
