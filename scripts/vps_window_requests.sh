#!/bin/bash
# vps_window_requests.sh — ask for every ladder lane's reads from inside its own window.
#
# Replaces vps_crypto_window.sh and vps_commodities_window.sh (2026-10-13). Those asked for
# ONE read a day each, and the commodities one was never installed in the crontab, so the
# 14:30 ET WTI window got a read only when some unrelated run happened to land in it. The
# Econ and Finance Daily lanes had no request at all and waited on GitHub's hourly cron,
# which never fired in their first four hours.
#
# lane_windows.py decides everything from each lane's own constants: the windows (2-3.5h
# before each close, measured to the CLOSE), up to three reads 30 minutes apart, and no
# later read once every series of that close holds an entry. This script only writes what
# it prints into the stamp files and pushes them in ONE commit, so a crypto and a commodity
# read due in the same 17:00 ET window start one tracker run, not two:
#   data/crypto_window/**, data/commodities_window/**,
#   data/ftts_window/**                                -> sandbox-tracker.yml
#   data/daily_window/**                               -> daily-research.yml
#   data/nba_window/**                                 -> nba-rules.yml (2026-10-17)
#   data/culture_window/**                             -> culture.yml (2026-10-17)
#   data/soccer_rules_window/**                        -> soccer-rules.yml (2026-10-17)
#   data/soccer_team_rules_window/**                   -> soccer-team-rules.yml (2026-10-17)
#   data/tennis_totals_window/**                       -> tennis-totals.yml (2026-10-21)
#   data/nfl_tt_window/**                              -> nfl-tt.yml (2026-10-21)
#   data/nba_value_window/**                           -> nba-value.yml (2026-10-21)
#   data/chaos_window/**                               -> chaos.yml (2026-10-25)
#   data/fights_window/**                              -> fights.yml (2026-11-01)
#
# The stamp names the close and the read number, so git is the once-per-read guard: the
# second 15-minute run inside a read finds nothing to commit, and every later run is a free
# retry of a failed push.
#
# Live on edge-vps as a USER CRONTAB (no root; see edge-crypto.timer for why):
#   */15 * * * * /home/<user>/edge-machine-closes/scripts/vps_window_requests.sh >> ~/edge-windows.log 2>&1
#
# HARDENING (2026-11-01): #277 added the fights stamp and the first run after the merge refused it ("refusing
# unexpected stamp path") and exited 1 AFTER it had already staged culture's stamp, so the next run failed on
# "cannot pull with rebase: Your index contains uncommitted changes", for every lane, until a hand repair. Four fixes:
#   a) every path is checked against the allow-list BEFORE any file is written or staged, so a refusal touches nothing;
#   b) a trap unstages the stamp files on any exit that did not commit them;
#   c) the script re-executes itself after the pull when the pull changed it (bash reads a running script
#      incrementally, so a pull that rewrote it mid-run ran the old text with the new lane_windows.py), and the
#      work lives in a function that is parsed whole before the pull;
#   d) a stale index or worktree that holds only stamp files (an aborted earlier run) is restored at the start
#      instead of failing every later run for ever.
set -uo pipefail
DIR="${EDGE_WINDOWS_DIR:-$HOME/edge-machine-closes}"
PY="${EDGE_WINDOWS_PY:-/usr/bin/python3}"
STAMP_GLOB='data/*_window/request.txt'
stamp() { date -u +%Y-%m-%dT%H:%M:%SZ; }

allowed_path() {
  case "$1" in
    data/crypto_window/request.txt|data/commodities_window/request.txt|data/daily_window/request.txt|data/ftts_window/request.txt|data/nba_window/request.txt|data/culture_window/request.txt|data/soccer_rules_window/request.txt|data/soccer_team_rules_window/request.txt|data/tennis_totals_window/request.txt|data/nfl_tt_window/request.txt|data/nba_value_window/request.txt|data/chaos_window/request.txt|data/fights_window/request.txt) return 0 ;;
  esac
  return 1
}

STAGED=0
cleanup() {
  # (b) any exit that did not commit what it staged leaves the index as it found it.
  if [ "$STAGED" = "1" ]; then
    git reset -q -- $STAMP_GLOB 2>/dev/null || true
    git checkout -q -- $STAMP_GLOB 2>/dev/null || true
  fi
}

main() {
  cd "$DIR" || { echo "$(stamp) no clone at $DIR"; exit 1; }

  # ONE GIT USER AT A TIME. local_closes.sh and vps_window_requests.sh share this clone on
  # edge-vps and both pull, commit and push every 15 minutes; on 2026-10-13 they met twice
  # ("cannot lock ref", "Cannot rebase onto multiple branches"). Both take this lock, waiting
  # up to two minutes, and a run that cannot get it exits and leaves the retry to the next one.
  # flock is util-linux: on a Mac without it the script runs as before.
  if command -v flock >/dev/null 2>&1; then
    exec 9>"$(git rev-parse --git-dir)/edge-shared.lock"
    flock -w 120 9 || { echo "$(stamp) the clone is busy (lock held for 2 min); next run retries"; exit 0; }
  fi
  trap cleanup EXIT

  # (d) a stale index or worktree from an aborted earlier run: if it holds ONLY stamp files, restore them;
  # anything else is somebody's work and is left alone (the pull below will then say so).
  DIRTY="$(git status --porcelain --untracked-files=no | sed 's/^...//')"
  if [ -n "$DIRTY" ]; then
    OTHER="$(printf '%s\n' "$DIRTY" | grep -v -E '^data/[a-z_]+_window/request\.txt$' || true)"
    if [ -n "$OTHER" ]; then
      echo "$(stamp) the clone has changes that are not stamp files; leaving them, next run retries"
      exit 0
    fi
    echo "$(stamp) restoring stamp files left by an aborted run: $(printf '%s' "$DIRTY" | tr '\n' ' ')"
    printf '%s\n' "$DIRTY" | while IFS= read -r f; do git reset -q -- "$f"; git checkout -q -- "$f"; done
  fi

  BEFORE="$(git hash-object "$0" 2>/dev/null || true)"
  git pull -q --rebase origin main || { echo "$(stamp) pull failed"; exit 0; }
  # (c) the pull may have rewritten this very script: run the new text, once, so the allow-list and
  # lane_windows.py agree.
  AFTER="$(git hash-object "$0" 2>/dev/null || true)"
  if [ -n "$BEFORE" ] && [ "$BEFORE" != "$AFTER" ] && [ -z "${EDGE_WINDOWS_REEXEC:-}" ]; then
    echo "$(stamp) the script changed in the pull; running the new one"
    EDGE_WINDOWS_REEXEC=1 exec "$0" "$@"
  fi

  DUE="$("$PY" lane_windows.py --due)" || { echo "$(stamp) lane_windows.py failed"; exit 0; }
  if [ -z "$DUE" ]; then
    echo "$(stamp) no read due"
    exit 0
  fi

  # (a) check every path BEFORE writing or staging any: a refusal leaves the tree exactly as it was.
  while IFS=$'\t' read -r path text; do
    [ -z "$path" ] && continue
    if ! allowed_path "$path"; then
      echo "$(stamp) refusing unexpected stamp path $path"
      exit 1
    fi
  done <<< "$DUE"

  while IFS=$'\t' read -r path text; do
    [ -z "$path" ] && continue
    mkdir -p "$(dirname "$path")"
    printf '%s\n' "$text" > "$path"
    git add -- "$path"
    STAGED=1
  done <<< "$DUE"

  if git diff --cached --quiet; then
    STAGED=0
    echo "$(stamp) every due read was already asked for"
    exit 0
  fi
  if ! git commit -q -m "Lane windows: $(echo "$DUE" | cut -f2 | tr '\n' ' ' | cut -c1-150) ($(date -u +%H:%MZ))"; then
    echo "$(stamp) commit failed; the staged stamps are unstaged and the next run retries"
    exit 1
  fi
  STAGED=0                      # committed: the commit now owns them, the trap leaves them alone
  for attempt in 1 2 3; do
    if git push -q origin HEAD:main; then
      echo "$(stamp) asked: $(echo "$DUE" | cut -f2 | tr '\n' ' ')"
      exit 0
    fi
    git pull -q --rebase origin main
  done
  echo "$(stamp) push failed after 3 attempts — the next 15-minute run retries"
  exit 0
}

# The whole body is parsed before anything runs; nothing after this line is ever read from the file.
main "$@"; exit $?
