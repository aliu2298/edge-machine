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
# process parses the whole file before the update. After the fast-forward it execs the pulled
# file once, with MARKET_DAILY_REEXEC set to the verified HEAD. That second process only
# fetches (no pull) and runs when HEAD is still that SHA and still origin/main. Any other
# value, including 1 or empty, is a fresh start.
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

# fetch, pull, and push. -q, and stdio discarded, so a remote URL cannot reach the journal.
# The exit code is logged; the remote output is not.
git_remote() {
  local cmd=$1 status=0
  shift
  git "$cmd" -q "$@" >/dev/null 2>&1 || status=$?
  if [ "$status" -ne 0 ]; then
    echo "${cmd} failed (git exit ${status})"
    return "$status"
  fi
}

HAND_RECOVERY="Recover by hand without force-pushing: if a rebase is still in progress run git rebase --abort, then either git reset --hard origin/main to drop the leftover ledger commit or rebase it yourself."
LEDGER_CONFLICT_MSG="refusing: rebase of the ledger commit onto origin/main conflicted. ${HAND_RECOVERY}"

main() {
  local source script guard
  source=${BASH_SOURCE[0]}
  script=$(cd "$(dirname "$source")" && pwd)/$(basename "$source")
  cd "$(dirname "$script")/.."

  guard=${MARKET_DAILY_REEXEC:-}
  # Only a full SHA is a re-exec guard. 1, empty, or anything else starts over.
  if [[ "$guard" =~ ^[0-9a-f]{40}$ ]]; then
    verify_reexec "$guard"
  else
    sync_origin "$script" "$@"
  fi
  verify_checkout
  publish_ledger
}

sync_origin() {
  local script=$1
  shift
  echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) market daily ==="
  if ! git_remote fetch origin main; then
    echo "refusing: git fetch origin main failed"
    exit 1
  fi
  if rebase_or_merge; then
    echo "refusing: a rebase or merge is in progress. ${HAND_RECOVERY}"
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
  # A dirty tracked tree is refused before leftover-ledger recovery. Recovery
  # rebases, and a dirty tree makes that rebase fail closed as "local commits".
  if tracked_dirty; then
    echo "refusing: tracked tree is dirty"
    exit 1
  fi
  local ahead recover_status
  ahead=$(git rev-list --count origin/main..HEAD)
  if [ "$ahead" != "0" ]; then
    if ! ahead_is_ledger_only; then
      echo "refusing: ${ahead} local commit(s) not on origin/main"
      exit 1
    fi
    echo "recovering ${ahead} ledger commit(s) left off origin/main"
    recover_status=0
    rebase_ledger_only || recover_status=$?
    if [ "$recover_status" -ne 0 ]; then
      if [ "$recover_status" -eq 2 ]; then
        echo "$LEDGER_CONFLICT_MSG"
      else
        echo "refusing: ${ahead} local commit(s) not on origin/main"
      fi
      exit 1
    fi
    if ! ledger_files_are_pushable; then
      exit 1
    fi
    if ! git_remote push origin main; then
      echo "refusing: could not push the recovered ledger commit"
      exit 1
    fi
    echo "recovered the leftover ledger commit"
  fi
  if ! git_remote pull --no-rebase --ff-only origin main; then
    echo "refusing: git pull --ff-only origin main failed"
    exit 1
  fi
  export MARKET_DAILY_REEXEC
  MARKET_DAILY_REEXEC=$(git rev-parse HEAD)
  exec bash "$script" "$@"
}

verify_reexec() {
  local guard=$1
  echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) market daily (re-exec) ==="
  if ! git_remote fetch origin main; then
    echo "refusing: git fetch origin main failed"
    exit 1
  fi
  local head upstream
  head=$(git rev-parse HEAD)
  upstream=$(git rev-parse origin/main)
  if [ "$head" != "$upstream" ] || [ "$head" != "$guard" ]; then
    echo "refusing: HEAD ${head} != origin/main ${upstream} or != re-exec SHA ${guard}"
    echo "MARKET_DAILY_REEXEC is internal and must not be set in the service environment"
    exit 1
  fi
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
  local attempt branch recover_status
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
    if ! ledger_files_are_pushable; then
      exit 1
    fi
    if git_remote push origin main; then
      echo "published on attempt ${attempt}"
      exit 0
    fi
    echo "push rejected — rebasing ledger commit onto origin/main (attempt ${attempt})"
    recover_status=0
    rebase_ledger_only || recover_status=$?
    if [ "$recover_status" -ne 0 ]; then
      if [ "$recover_status" -eq 2 ]; then
        echo "$LEDGER_CONFLICT_MSG"
      else
        echo "refusing: retry would rebase or push more than the ledger data files"
      fi
      exit 1
    fi
  done
  echo "could not publish after 3 attempts"
  exit 1
}

rebase_or_merge() {
  local path
  # A failing rev-parse is treated as in progress: fail closed, do not run.
  path=$(git rev-parse --git-path rebase-merge 2>/dev/null) || return 0
  [ -d "$path" ] && return 0
  path=$(git rev-parse --git-path rebase-apply 2>/dev/null) || return 0
  [ -d "$path" ] && return 0
  path=$(git rev-parse --git-path MERGE_HEAD 2>/dev/null) || return 0
  [ -f "$path" ] && return 0
  path=$(git rev-parse --git-path CHERRY_PICK_HEAD 2>/dev/null) || return 0
  [ -f "$path" ] && return 0
  path=$(git rev-parse --git-path REVERT_HEAD 2>/dev/null) || return 0
  [ -f "$path" ] && return 0
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

# Commits ahead of origin/main may be pushed only when each one adds or
# modifies a ledger path as a regular file, and that path is still a
# non-symlink regular file of JSON in the working tree.
ledger_files_are_pushable() {
  local commits c raw line meta path oldmode newmode status seen="" f
  commits=$(git rev-list origin/main..HEAD) || {
    echo "refusing: could not list commits ahead of origin/main"
    return 1
  }
  if [ -z "$commits" ]; then
    echo "refusing: nothing to push on top of origin/main"
    return 1
  fi
  while IFS= read -r c; do
    [ -z "$c" ] && continue
    raw=$(git diff-tree --raw --no-commit-id --no-renames -r "$c") || {
      echo "refusing: git diff-tree failed for ${c}"
      return 1
    }
    if [ -z "$raw" ]; then
      echo "refusing: commit ${c} does not touch the ledger data files"
      return 1
    fi
    while IFS= read -r line; do
      [ -z "$line" ] && continue
      meta=${line%%$'\t'*}
      path=${line#*$'\t'}
      # :oldmode newmode oldsha newsha status
      read -r oldmode newmode _ _ status <<< "${meta#:}"
      case "$path" in
        data/market_ledger.json|data/sp500.json) ;;
        *)
          echo "refusing: commit ${c} touches ${path}, not only ledger data"
          return 1
          ;;
      esac
      case "$newmode" in
        120000)
          echo "refusing: commit ${c} sets ${path} to mode 120000, a symlink"
          return 1
          ;;
        100644|100755) ;;
        *)
          echo "refusing: commit ${c} sets ${path} to mode ${newmode}, not a regular file"
          return 1
          ;;
      esac
      case "$status" in
        A|M) ;;
        *)
          echo "refusing: commit ${c} ${status} ${path}; only a normal-file add or modify may be pushed"
          return 1
          ;;
      esac
      case "$oldmode" in
        000000|100644|100755) ;;
        *)
          echo "refusing: commit ${c} changes ${path} from mode ${oldmode}, not a regular file"
          return 1
          ;;
      esac
      case " ${seen} " in
        *" ${path} "*) ;;
        *) seen="${seen} ${path}" ;;
      esac
    done <<< "$raw"
  done <<< "$commits"
  for f in $seen; do
    if [ -L "$f" ]; then
      echo "refusing: ${f} is a symlink"
      return 1
    fi
    if [ ! -f "$f" ]; then
      echo "refusing: ${f} is not a regular file in the working tree"
      return 1
    fi
    if ! python3 -c 'import json,sys; json.load(open(sys.argv[1], encoding="utf-8"))' "$f"; then
      echo "refusing: ${f} is not valid JSON"
      return 1
    fi
  done
  return 0
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
  if ! git_remote fetch origin main; then
    echo "refusing: git fetch origin main failed during push retry"
    return 1
  fi
  if ! ahead_is_ledger_only; then
    return 1
  fi
  if ! git -c rebase.autoStash=false rebase --no-autostash origin/main; then
    local path in_rebase=0
    path=$(git rev-parse --git-path rebase-merge 2>/dev/null) || path=""
    [ -n "$path" ] && [ -d "$path" ] && in_rebase=1
    path=$(git rev-parse --git-path rebase-apply 2>/dev/null) || path=""
    [ -n "$path" ] && [ -d "$path" ] && in_rebase=1
    if [ "$in_rebase" -eq 1 ]; then
      git rebase --abort >/dev/null 2>&1 || true
      return 2
    fi
    return 1
  fi
  if rebase_or_merge; then
    git rebase --abort >/dev/null 2>&1 || true
    return 2
  fi
  ahead_is_ledger_only
}

main "$@"
exit
