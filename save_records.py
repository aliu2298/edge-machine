#!/usr/bin/env python3
"""Commit a workflow's records and push them to main, surviving a race on a DERIVED file (2026-11-01).

The soccer paper workflows commit their ledgers (append data only they write) together with a Production
feed built from those ledgers. The Feeds heartbeat (feeds-heartbeat.yml) restamps the same feeds a few times
an hour, so it sometimes pushes between a workflow's checkout and its push. The old save then rebased, hit a
content conflict in the feed, and failed, dropping the run's ledger rows with it.

Here, when the push is rejected:
  1. fetch and rebase this run's commit onto origin/main. The ledgers merge as git merges them; a conflict in
     any file that is not derived is a genuine conflict: the rebase is aborted and the run fails, with nothing
     on main changed and nothing taken from either side.
  2. every derived file is REBUILT, not picked: main's copy is put back as the builder's previous feed (it
     carries each lead's first-publication stamp), then the builder reruns on the merged ledgers.
  3. the result is amended into the commit and pushed again (4 attempts, a short random pause before each retry).

A rebuild that leaves nothing to push (another job's identical or newer write already covers this run: the
heartbeat's restamp, say) ends the run green with nothing pushed.

    python3 save_records.py --message "..." --add data/a.json data/b.json \
        --derived data/feed.json "python3 build_feed.py" \
        [--optional data/maybe.json] [--regenerate "python3 rerun_the_job.py"] [--after "gh workflow run x.yml"]

  --add        may be repeated (each use extends the list; until 2026-11-06 the last use silently replaced the earlier ones)
  --optional   records saved only if the job wrote them (a missing file is skipped, not an error)
  --regenerate on a genuine conflict in a ledger (a file that is not derived), instead of failing: abort the
               rebase, reset to origin/main and rerun the job's steps on top of it. Never picks a side of a ledger.
  --after      run once, only after the push lands (e.g. asking for the page build)

Every file named is checked to parse as JSON before anything is committed.
"""
import argparse
import json
import os
import subprocess
import random
import sys
import time

ATTEMPTS = 4
BACKOFF_S = (1.0, 4.0)        # a random pause in this range before a retry, so two racing jobs do not collide again
SLEEP = time.sleep           # patched by the tests


def git(*args, check=True, cwd=None):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr.strip()[:400]}")
    return r


def check_json(paths, cwd=None):
    for p in paths:
        with open(os.path.join(cwd or ".", p)) as f:
            json.load(f)


def rebuild(derived, cwd=None, every=()):
    """Put main's copy of each derived file back as its builder's previous state, rerun the builder, stage it.

    A builder may write SEVERAL derived files (nba_wm_production.py writes both Win margin feeds), so a later run rewrites a file
    an earlier step had already staged, leaving it modified and unstaged, and the next `git rebase` refuses ("cannot rebase: You
    have unstaged changes"). So every derived file (`every`) is staged again once the builders have all run."""
    for path, cmd in derived:
        shown = git("show", f"origin/main:{path}", check=False, cwd=cwd)
        if shown.returncode == 0:
            with open(os.path.join(cwd or ".", path), "w") as f:
                f.write(shown.stdout)
        subprocess.run(cmd, shell=True, check=True, cwd=cwd)
        check_json([path], cwd)
        git("add", path, cwd=cwd)
    for path in every:
        if os.path.exists(os.path.join(cwd or ".", path)):
            git("add", path, cwd=cwd)


def integrate(derived, cwd=None, log=print):
    """Rebase onto origin/main, rebuilding the derived files. False on a genuine (non-derived) conflict."""
    names = {p for p, _ in derived}
    every = [p for p, _ in derived]
    r = git("rebase", "origin/main", check=False, cwd=cwd)
    while r.returncode != 0:
        conflicted = set(git("diff", "--name-only", "--diff-filter=U", cwd=cwd).stdout.split())
        if not conflicted:                                  # a rebase failure that is not a content conflict
            git("rebase", "--abort", check=False, cwd=cwd)
            log("rebase failed: " + (r.stderr or r.stdout).strip()[:400])
            return False
        real = sorted(conflicted - names)
        if real:
            git("rebase", "--abort", check=False, cwd=cwd)
            log("conflict in records only this workflow should write, left for review: " + ", ".join(real))
            return False
        log("rebuilding derived file(s) after a concurrent write: " + ", ".join(sorted(conflicted)))
        rebuild([d for d in derived if d[0] in conflicted], cwd, every)
        if git("diff", "--cached", "--quiet", check=False, cwd=cwd).returncode == 0:
            r = git("rebase", "--skip", check=False, cwd=cwd)          # the rebuild equals main: nothing of this run's commit is left
        else:
            r = git("-c", "core.editor=true", "rebase", "--continue", check=False, cwd=cwd)
    # A clean rebase can still splice a JSON feed line by line: rebuild every derived file on the merged state.
    if git("rev-parse", "HEAD", cwd=cwd).stdout == git("rev-parse", "origin/main", cwd=cwd).stdout:
        return True                                         # this run's commit became empty and was dropped: main already has it all
    rebuild(derived, cwd, every)
    if git("diff", "--cached", "--quiet", check=False, cwd=cwd).returncode != 0:
        git("commit", "--amend", "--no-edit", cwd=cwd)
    return True


def regenerate_on_main(message, add, derived, regenerate, cwd=None, log=print):
    """A genuine ledger conflict: put the work on top of origin/main by rerunning the job, never by picking a side."""
    log("regenerating on top of origin/main: " + regenerate)
    git("reset", "--hard", "origin/main", cwd=cwd)
    subprocess.run(regenerate, shell=True, check=True, cwd=cwd)
    check_json(list(add) + [p for p, _ in derived], cwd)
    git("add", *add, *[p for p, _ in derived], cwd=cwd)
    if git("diff", "--cached", "--quiet", check=False, cwd=cwd).returncode == 0:
        return False
    git("commit", "-m", message, cwd=cwd)
    return True


def save(message, add, derived, cwd=None, log=print, remote="origin", branch="main", optional=(), regenerate=None, after=None):
    """0 when the records are on main (or there was nothing to save), 1 otherwise."""
    add = list(add) + [p for p in optional if os.path.exists(os.path.join(cwd or ".", p))]
    check_json(list(add) + [p for p, _ in derived], cwd)
    git("add", *add, *[p for p, _ in derived], cwd=cwd)
    if git("diff", "--cached", "--quiet", check=False, cwd=cwd).returncode == 0:
        log("nothing to save")
        return 0
    git("commit", "-m", message, cwd=cwd)

    def landed(attempt):
        log(f"saved on attempt {attempt}")
        if after:
            subprocess.run(after, shell=True, check=False, cwd=cwd)
        return 0

    for attempt in range(1, ATTEMPTS + 1):
        if git("push", remote, f"HEAD:{branch}", check=False, cwd=cwd).returncode == 0:
            return landed(attempt)
        SLEEP(random.uniform(*BACKOFF_S))
        git("fetch", remote, branch, cwd=cwd)
        if not integrate(derived, cwd, log):
            if not regenerate:
                return 1
            if not regenerate_on_main(message, add, derived, regenerate, cwd, log):
                log("nothing to save after regenerating on main")
                return 0
            continue
        if git("rev-parse", "HEAD", cwd=cwd).stdout == git("rev-parse", f"{remote}/{branch}", cwd=cwd).stdout:
            log("main already holds everything this run produced")
            return 0
    log(f"push still rejected after {ATTEMPTS} attempts")
    return 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--message", required=True)
    ap.add_argument("--add", nargs="+", action="extend", default=[], help="records to commit (merged by git); may be repeated")
    ap.add_argument("--derived", nargs=2, action="append", default=[], metavar=("PATH", "CMD"),
                    help="a file rebuilt by CMD from the records; rebuilt, never picked, after a concurrent write")
    ap.add_argument("--optional", nargs="+", action="extend", default=[], help="records saved only if the job wrote them")
    ap.add_argument("--regenerate", default=None, help="rerun the job on top of origin/main after a genuine ledger conflict")
    ap.add_argument("--after", default=None, help="a command run once, after the push lands")
    a = ap.parse_args(argv)
    return save(a.message, a.add, [tuple(d) for d in a.derived], optional=a.optional, regenerate=a.regenerate, after=a.after)


if __name__ == "__main__":
    sys.exit(main())
