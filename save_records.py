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
  3. the result is amended into the commit and pushed again (3 attempts).

    python3 save_records.py --message "..." --add data/a.json data/b.json \
        --derived data/feed.json "python3 build_feed.py"

Every file named is checked to parse as JSON before anything is committed.
"""
import argparse
import json
import os
import subprocess
import sys

ATTEMPTS = 3


def git(*args, check=True, cwd=None):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr.strip()[:400]}")
    return r


def check_json(paths, cwd=None):
    for p in paths:
        with open(os.path.join(cwd or ".", p)) as f:
            json.load(f)


def rebuild(derived, cwd=None):
    """Put main's copy of each derived file back as its builder's previous state, rerun the builder, stage it."""
    for path, cmd in derived:
        shown = git("show", f"origin/main:{path}", check=False, cwd=cwd)
        if shown.returncode == 0:
            with open(os.path.join(cwd or ".", path), "w") as f:
                f.write(shown.stdout)
        subprocess.run(cmd, shell=True, check=True, cwd=cwd)
        check_json([path], cwd)
        git("add", path, cwd=cwd)


def integrate(derived, cwd=None, log=print):
    """Rebase onto origin/main, rebuilding the derived files. False on a genuine (non-derived) conflict."""
    names = {p for p, _ in derived}
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
        rebuild([d for d in derived if d[0] in conflicted], cwd)
        r = git("-c", "core.editor=true", "rebase", "--continue", check=False, cwd=cwd)
    # A clean rebase can still splice a JSON feed line by line: rebuild every derived file on the merged state.
    rebuild(derived, cwd)
    if git("diff", "--cached", "--quiet", check=False, cwd=cwd).returncode != 0:
        git("commit", "--amend", "--no-edit", cwd=cwd)
    return True


def save(message, add, derived, cwd=None, log=print, remote="origin", branch="main"):
    """0 when the records are on main (or there was nothing to save), 1 otherwise."""
    check_json(list(add) + [p for p, _ in derived], cwd)
    git("add", *add, *[p for p, _ in derived], cwd=cwd)
    if git("diff", "--cached", "--quiet", check=False, cwd=cwd).returncode == 0:
        log("nothing to save")
        return 0
    git("commit", "-m", message, cwd=cwd)
    for attempt in range(1, ATTEMPTS + 1):
        if git("push", remote, f"HEAD:{branch}", check=False, cwd=cwd).returncode == 0:
            log(f"saved on attempt {attempt}")
            return 0
        git("fetch", remote, branch, cwd=cwd)
        if not integrate(derived, cwd, log):
            return 1
    log(f"push still rejected after {ATTEMPTS} attempts")
    return 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--message", required=True)
    ap.add_argument("--add", nargs="+", default=[], help="records to commit (merged by git)")
    ap.add_argument("--derived", nargs=2, action="append", default=[], metavar=("PATH", "CMD"),
                    help="a file rebuilt by CMD from the records; rebuilt, never picked, after a concurrent write")
    a = ap.parse_args(argv)
    return save(a.message, a.add, [tuple(d) for d in a.derived])


if __name__ == "__main__":
    sys.exit(main())
