#!/usr/bin/env python3
"""scripts/vps_window_requests.sh against a throwaway git origin and clone (no network, no VPS).

2026-11-01: #277 added the fights stamp. The first VPS run after the merge pulled the new lane_windows.py
mid-run, still executed the OLD script text, refused the fights path with exit 1 AFTER staging culture's stamp,
and left a dirty index that made every later run fail. Covered here: (a) a refusal touches nothing, (b) an exit
after staging leaves the index clean, (c) a script rewritten by its own pull runs its new text, (d) a stale index
holding only stamp files is restored and the run continues."""
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(ROOT, "scripts", "vps_window_requests.sh")
FAILS = []


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


def git(cwd, *args, check_=True):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                       env=dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t"))
    if check_ and r.returncode:
        raise RuntimeError(f"git {args}: {r.stderr}")
    return r.stdout.strip()


LANE = '''#!/usr/bin/env python3
import sys
for line in open("due.txt").read().splitlines():
    print(line)
'''


def world(tmp, script_text=None, due=""):
    origin = os.path.join(tmp, "origin.git")
    work = os.path.join(tmp, "seed")
    clone = os.path.join(tmp, "clone")
    git(tmp, "init", "-q", "--bare", "-b", "main", origin)
    os.makedirs(os.path.join(work, "scripts"))
    git(work, "init", "-q", "-b", "main")
    shutil.copy(SCRIPT, os.path.join(work, "scripts", "vps_window_requests.sh"))
    if script_text is not None:
        open(os.path.join(work, "scripts", "vps_window_requests.sh"), "w").write(script_text)
    os.chmod(os.path.join(work, "scripts", "vps_window_requests.sh"), 0o755)
    open(os.path.join(work, "lane_windows.py"), "w").write(LANE)
    open(os.path.join(work, "due.txt"), "w").write(due)
    os.makedirs(os.path.join(work, "data", "culture_window"))
    open(os.path.join(work, "data", "culture_window", "request.txt"), "w").write("old\n")
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", "seed")
    git(work, "remote", "add", "origin", origin)
    git(work, "push", "-q", "origin", "main")
    git(tmp, "clone", "-q", origin, clone)
    return origin, work, clone


def run(clone, env_extra=None):
    env = dict(os.environ, EDGE_WINDOWS_DIR=clone, EDGE_WINDOWS_PY=sys.executable,
               GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
    env.update(env_extra or {})
    r = subprocess.run(["bash", os.path.join(clone, "scripts", "vps_window_requests.sh")], capture_output=True, text=True, env=env, timeout=60)
    return r.returncode, r.stdout + r.stderr


def tab(path, text):
    return f"{path}\t{text}\n"


print("a normal run stamps, commits and pushes")
with tempfile.TemporaryDirectory() as tmp:
    origin, work, clone = world(tmp)
    open(os.path.join(clone, "due.txt"), "w").write(tab("data/culture_window/request.txt", "culture 2026-11-01T03:00:00+00:00 read 1"))
    git(clone, "commit", "-q", "-am", "due")
    git(clone, "push", "-q", "origin", "HEAD:main")
    rc, out = run(clone)
    check("exit 0 and 'asked'", (rc, "asked: culture" in out), (0, True))
    check("the stamp is on origin", "culture 2026-11-01T03:00:00+00:00 read 1" in git(tmp, "--git-dir", origin, "show", "main:data/culture_window/request.txt"), True)
    rc, out = run(clone)
    check("a second run finds it already asked for", (rc, "already asked for" in out), (0, True))

print("\n(a) an unexpected path refuses BEFORE staging anything: the index and tree stay clean")
with tempfile.TemporaryDirectory() as tmp:
    origin, work, clone = world(tmp)
    due = tab("data/culture_window/request.txt", "culture x read 1") + tab("data/nope_window/request.txt", "nope x read 1")
    open(os.path.join(clone, "due.txt"), "w").write(due)
    git(clone, "commit", "-q", "-am", "due")
    git(clone, "push", "-q", "origin", "HEAD:main")
    rc, out = run(clone)
    check("exit 1 naming the path", (rc, "refusing unexpected stamp path data/nope_window/request.txt" in out), (1, True))
    check("nothing staged or modified (the valid path before it was not touched either)", git(clone, "status", "--porcelain", "--untracked-files=all"), "")
    check("and no commit was made", git(clone, "log", "--oneline", "origin/main..HEAD"), "")

print("\n(b) an exit after staging leaves the index clean (a commit that fails)")
with tempfile.TemporaryDirectory() as tmp:
    origin, work, clone = world(tmp)
    open(os.path.join(clone, "due.txt"), "w").write(tab("data/culture_window/request.txt", "culture y read 1"))
    git(clone, "commit", "-q", "-am", "due")
    git(clone, "push", "-q", "origin", "HEAD:main")
    hook = os.path.join(clone, ".git", "hooks", "pre-commit")
    open(hook, "w").write("#!/bin/sh\nexit 1\n")
    os.chmod(hook, 0o755)
    rc, out = run(clone)
    check("the failed commit exits 1 and says so", (rc, "commit failed" in out), (1, True))
    check("the staged stamp was unstaged and restored", git(clone, "status", "--porcelain", "--untracked-files=all"), "")
    os.remove(hook)
    rc, out = run(clone)
    check("the next run goes through", (rc, "asked: culture" in out), (0, True))

print("\n(d) a stale index holding only stamp files is restored at the start, then the run continues")
with tempfile.TemporaryDirectory() as tmp:
    origin, work, clone = world(tmp)
    open(os.path.join(clone, "due.txt"), "w").write(tab("data/culture_window/request.txt", "culture z read 1"))
    git(clone, "commit", "-q", "-am", "due")
    git(clone, "push", "-q", "origin", "HEAD:main")
    stale = os.path.join(clone, "data", "culture_window", "request.txt")
    open(stale, "w").write("left by an aborted run\n")
    git(clone, "add", "--", "data/culture_window/request.txt")
    rc, out = run(clone)
    check("it restored the stamp and carried on", (rc, "restoring stamp files left by an aborted run" in out, "asked: culture" in out), (0, True, True))
    check("what it pushed is the new stamp, not the stale text", "culture z read 1" in git(tmp, "--git-dir", origin, "show", "main:data/culture_window/request.txt"), True)
    # other changes are somebody's work: left alone
    open(os.path.join(clone, "notes.txt"), "w").write("x")
    git(clone, "add", "notes.txt")
    rc, out = run(clone)
    check("a staged file that is not a stamp is left alone and the run waits", (rc, "not stamp files" in out, git(clone, "diff", "--cached", "--name-only")),
          (0, True, "notes.txt"))

print("\n(c) a script rewritten by its own pull runs its NEW text (the 2026-11-01 outage)")
with tempfile.TemporaryDirectory() as tmp:
    old_text = open(SCRIPT).read().replace("|data/fights_window/request.txt", "")      # the allow-list before #277
    check("the old text really lacks the fights path", "fights_window" in old_text.split("allowed_path()")[1].split("}")[0], False)
    origin, work, clone = world(tmp, script_text=old_text)
    # origin now moves to the NEW script and a lane_windows that asks for fights
    shutil.copy(SCRIPT, os.path.join(work, "scripts", "vps_window_requests.sh"))
    open(os.path.join(work, "due.txt"), "w").write(tab("data/culture_window/request.txt", "culture n read 1") + tab("data/fights_window/request.txt", "fights n read 1"))
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", "new script and a fights lane")
    git(work, "push", "-q", "origin", "main")
    rc, out = run(clone)
    check("the run re-executed the new script, accepted fights and pushed both", (rc, "the script changed in the pull" in out, "asked: culture" in out), (0, True, True))
    check("both stamps are on origin", ("fights n read 1" in git(tmp, "--git-dir", origin, "show", "main:data/fights_window/request.txt"),
                                          "culture n read 1" in git(tmp, "--git-dir", origin, "show", "main:data/culture_window/request.txt")), (True, True))
    check("the clone is clean afterwards", git(clone, "status", "--porcelain", "--untracked-files=all"), "")

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
