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
#
# Bash reads a script as it runs. A pull that replaces this file mid-run can execute a mix of
# the old bytes and the new ones. The body is one function, called on the last line, so this
# process parses the whole file before fetch or pull. After the fast-forward it execs the
# pulled file once (MARKET_DAILY_REEXEC=1). That second process only verifies and runs.
#
# Untracked files are ignored. The VPS holds logs, editor leftovers, and the ledger's atomic
# temp file, and none of those are the code under test. A tracked change is refused: the run
# must be the origin/main tree, not a local edit carried across the update.
set -euo pipefail
unset CDPATH

# /opt/homebrew/bin exists only on a Mac. Prepend it there; leave PATH alone on Linux.
if [ -d /opt/homebrew/bin ]; then
  PATH="/opt/homebrew/bin:${PATH:-/usr/bin:/bin}"
  export PATH
fi

main() {
  local source script
  source=${BASH_SOURCE[0]}
  script=$(cd "$(dirname "$source")" && pwd)/$(basename "$source")
  cd "$(dirname "$script")/.."

  if [ "${MARKET_DAILY_REEXEC:-}" != "1" ]; then
    sync_origin "$script" "$@"
  fi
  verify_checkout
  publish_ledger
}

sync_origin() {
  local script=$1
  shift
  echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) market daily ==="
  if ! git fetch origin main; then
    echo "refusing: git fetch origin main failed"
    exit 1
  fi
  if rebase_or_merge; then
    echo "refusing: a rebase or merge is in progress"
    exit 1
  fi
  local branch
  branch=$(git rev-parse --abbrev-ref HEAD)
  if [ "$branch" != "main" ]; then
    if tracked_dirty; then
      echo "refusing: on ${branch} with tracked local changes; not checking out main"
      exit 1
    fi
    if ! git checkout main; then
      echo "refusing: could not check out main from ${branch}"
      exit 1
    fi
    echo "checked out main"
  fi
  local ahead
  ahead=$(git rev-list --count origin/main..HEAD)
  if [ "$ahead" != "0" ]; then
    echo "refusing: ${ahead} local commit(s) not on origin/main"
    exit 1
  fi
  # A tracked edit that does not overlap the incoming commit would otherwise
  # survive the fast-forward. Pull first, then the re-exec'd copy refuses to run.
  if ! git pull --no-rebase --ff-only origin main; then
    if tracked_dirty; then
      echo "refusing: tracked tree is dirty"
    fi
    echo "refusing: git pull --ff-only origin main failed"
    exit 1
  fi
  export MARKET_DAILY_REEXEC=1
  exec bash "$script" "$@"
}

verify_checkout() {
  echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) market daily (verified checkout) ==="
  if rebase_or_merge; then
    echo "refusing: a rebase or merge is in progress"
    exit 1
  fi
  local head upstream ahead branch
  head=$(git rev-parse HEAD)
  upstream=$(git rev-parse origin/main)
  if [ "$head" != "$upstream" ]; then
    echo "refusing: HEAD ${head} != origin/main ${upstream}"
    exit 1
  fi
  ahead=$(git rev-list --count origin/main..HEAD)
  if [ "$ahead" != "0" ]; then
    echo "refusing: ${ahead} local commit(s) not on origin/main"
    exit 1
  fi
  if tracked_dirty; then
    echo "refusing: tracked tree is dirty"
    exit 1
  fi
  branch=$(git rev-parse --abbrev-ref HEAD)
  if [ "$branch" != "main" ]; then
    echo "refusing: checkout is ${branch}, not main"
    exit 1
  fi
}

publish_ledger() {
  local sha
  sha=$(git rev-parse HEAD)
  export MARKET_CODE_SHA="$sha"
  # ledger-run
  if ! python3 market_track.py; then
    echo "market_track failed"
    exit 1
  fi
  if [ ! -f data/market_ledger.json ]; then
    echo "refusing: data/market_ledger.json is missing after market_track"
    exit 1
  fi
  git add -- data/market_ledger.json
  if [ -f data/sp500.json ]; then
    git add -- data/sp500.json
  fi
  if git diff --cached --quiet; then
    echo "no change — nothing to publish"
    exit 0
  fi
  if ! staged_only_ledger; then
    echo "refusing: commit would contain files other than the ledger data files"
    exit 1
  fi
  if ! git commit -q -m "Trading lane ($(date -u +%Y-%m-%d\ %H:%MZ))"; then
    echo "refusing: ledger commit failed"
    exit 1
  fi
  local attempt branch
  for attempt in 1 2 3; do
    branch=$(git rev-parse --abbrev-ref HEAD)
    if [ "$branch" != "main" ]; then
      echo "refusing: not on main (${branch}); not pushing"
      exit 1
    fi
    if ! ahead_is_ledger_only; then
      echo "refusing: would push a commit that is not only ledger data"
      exit 1
    fi
    if git push origin main; then
      echo "published on attempt ${attempt}"
      exit 0
    fi
    echo "push rejected — rebasing ledger commit onto origin/main (attempt ${attempt})"
    if ! rebase_ledger_only; then
      echo "refusing: retry would rebase or push more than the ledger data files"
      exit 1
    fi
  done
  echo "could not publish after 3 attempts"
  exit 1
}

rebase_or_merge() {
  [ -d "$(git rev-parse --git-path rebase-merge)" ] && return 0
  [ -d "$(git rev-parse --git-path rebase-apply)" ] && return 0
  [ -f "$(git rev-parse --git-path MERGE_HEAD)" ] && return 0
  [ -f "$(git rev-parse --git-path CHERRY_PICK_HEAD)" ] && return 0
  [ -f "$(git rev-parse --git-path REVERT_HEAD)" ] && return 0
  return 1
}

tracked_dirty() {
  local status=0
  git diff --quiet || status=$?
  if [ "$status" -gt 1 ]; then
    echo "refusing: git diff failed (status ${status})"
    exit 1
  fi
  if [ "$status" -eq 1 ]; then
    return 0
  fi
  status=0
  git diff --cached --quiet || status=$?
  if [ "$status" -gt 1 ]; then
    echo "refusing: git diff --cached failed (status ${status})"
    exit 1
  fi
  [ "$status" -eq 1 ]
}

staged_only_ledger() {
  local names f any=0
  names=$(git diff --cached --name-only)
  while IFS= read -r f; do
    [ -z "$f" ] && continue
    any=1
    case "$f" in
      data/market_ledger.json|data/sp500.json) ;;
      *)
        echo "refusing: staged path ${f} is not ledger data"
        return 1
        ;;
    esac
  done <<< "$names"
  [ "$any" = 1 ]
}

ahead_is_ledger_only() {
  local commits c files f
  commits=$(git rev-list origin/main..HEAD)
  if [ -z "$commits" ]; then
    echo "refusing: nothing to push on top of origin/main"
    return 1
  fi
  while IFS= read -r c; do
    [ -z "$c" ] && continue
    files=$(git diff-tree --no-commit-id --name-only -r "$c")
    if [ -z "$files" ]; then
      echo "refusing: commit ${c} does not touch the ledger data files"
      return 1
    fi
    while IFS= read -r f; do
      [ -z "$f" ] && continue
      case "$f" in
        data/market_ledger.json|data/sp500.json) ;;
        *)
          echo "refusing: commit ${c} touches ${f}, not only ledger data"
          return 1
          ;;
      esac
    done <<< "$files"
  done <<< "$commits"
  return 0
}

rebase_ledger_only() {
  if ! git fetch origin main; then
    echo "refusing: git fetch origin main failed during push retry"
    return 1
  fi
  if ! ahead_is_ledger_only; then
    return 1
  fi
  if ! git -c rebase.autoStash=false rebase --no-autostash origin/main; then
    git rebase --abort || true
    echo "refusing: rebase of the ledger commit onto origin/main failed"
    return 1
  fi
  if rebase_or_merge; then
    git rebase --abort || true
    echo "refusing: rebase left a rebase or merge in progress"
    return 1
  fi
  ahead_is_ledger_only
}

main "$@"
exit
