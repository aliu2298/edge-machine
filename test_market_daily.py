#!/usr/bin/env python3
"""Offline checks for scripts/market_daily.sh.

A temp bare origin and a clone stand in for the VPS. No network and no keys.
MARKET_DAILY_SCRIPT, when set, is the script copied into each clone; otherwise
the repo's scripts/market_daily.sh is used.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

FAILS = []
ROOT = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.environ.get("MARKET_DAILY_SCRIPT") or os.path.join(ROOT, "scripts", "market_daily.sh")

STUB = r'''#!/usr/bin/env python3
import json, os
from pathlib import Path
root = Path(__file__).resolve().parent
log = root / "stub_runs.log"
with log.open("a", encoding="utf-8") as handle:
    handle.write(os.environ.get("STUB_MARKER", "ran") + "\n")
data = root / "data"
data.mkdir(exist_ok=True)
ledger = {
    "meta": {
        "code_sha": os.environ.get("MARKET_CODE_SHA", ""),
        "updated": "2026-10-04T00:00:00+00:00",
    },
    "trades": [],
}
path = data / "market_ledger.json"
tmp = path.with_suffix(".json.tmp")
tmp.write_text(json.dumps(ledger), encoding="utf-8")
os.replace(tmp, path)
sp = data / "sp500.json"
if not sp.exists():
    sp.write_text("{}", encoding="utf-8")
'''


def ok(cond, why):
    print(f"  {'ok  ' if cond else 'FAIL'} {why}")
    if not cond:
        FAILS.append(why)


def eq(got, want, why):
    ok(got == want, why if got == want else f"{why} — got {got!r}, want {want!r}")


def git(repo, *args, check=True):
    proc = subprocess.run(
        ["git", "-C", repo, *args],
        text=True, capture_output=True,
    )
    if check and proc.returncode != 0:
        raise RuntimeError(
            f"git -C {repo} {' '.join(args)} failed ({proc.returncode})\n"
            f"{proc.stdout}{proc.stderr}")
    return proc


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def script_text():
    with open(SCRIPT, encoding="utf-8") as handle:
        return handle.read()


class Repo:
    def __init__(self, stub=STUB, script=None):
        self.tmp = tempfile.TemporaryDirectory()
        self.origin = os.path.join(self.tmp.name, "origin.git")
        self.clone = os.path.join(self.tmp.name, "clone")
        self.script = script if script is not None else script_text()
        self.stub = stub
        subprocess.run(["git", "init", "--bare", "-b", "main", self.origin],
                       check=True, capture_output=True, text=True)
        subprocess.run(["git", "clone", self.origin, self.clone],
                       check=True, capture_output=True, text=True)
        for key, value in (
            ("user.email", "market-daily-test@example.com"),
            ("user.name", "market-daily-test"),
            ("commit.gpgsign", "false"),
            ("core.fsmonitor", "false"),
            ("gc.auto", "0"),
        ):
            git(self.clone, "config", key, value)
        self._place()
        git(self.clone, "add", "--", "scripts/market_daily.sh", "market_track.py",
            "data/market_ledger.json", "data/sp500.json")
        git(self.clone, "commit", "-m", "base")
        git(self.clone, "branch", "-M", "main")
        git(self.clone, "push", "-u", "origin", "main")
        self.base = git(self.clone, "rev-parse", "HEAD").stdout.strip()

    def _place(self):
        write(os.path.join(self.clone, "scripts", "market_daily.sh"), self.script)
        os.chmod(os.path.join(self.clone, "scripts", "market_daily.sh"), 0o755)
        write(os.path.join(self.clone, "market_track.py"), self.stub)
        write(os.path.join(self.clone, "data", "market_ledger.json"),
              '{"meta": {"updated": "2026-10-01T00:00:00+00:00"}, "trades": []}\n')
        write(os.path.join(self.clone, "data", "sp500.json"), "{}\n")

    def close(self):
        self.tmp.cleanup()

    def run(self, extra_env=None):
        env = os.environ.copy()
        for key in ("MARKET_DAILY_REEXEC", "MARKET_CODE_SHA", "GIT_DIR",
                    "GIT_WORK_TREE", "GIT_INDEX_FILE"):
            env.pop(key, None)
        if extra_env:
            env.update(extra_env)
        env["GIT_TERMINAL_PROMPT"] = "0"
        return subprocess.run(
            ["bash", os.path.join(self.clone, "scripts", "market_daily.sh")],
            cwd=self.clone, env=env, text=True, capture_output=True,
        )

    def head(self):
        return git(self.clone, "rev-parse", "HEAD").stdout.strip()

    def branch(self):
        return git(self.clone, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()

    def stub_lines(self):
        path = os.path.join(self.clone, "stub_runs.log")
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8") as handle:
            return [line.strip() for line in handle if line.strip()]

    def origin_ledger(self):
        proc = git(self.origin, "show", "main:data/market_ledger.json")
        return json.loads(proc.stdout)

    def origin_names(self, rev="main"):
        proc = git(self.origin, "diff-tree", "--no-commit-id", "--name-only", "-r", rev)
        return [line for line in proc.stdout.splitlines() if line]


def combined(proc):
    return (proc.stdout or "") + (proc.stderr or "")


def print_failure(proc):
    print("--- stdout ---")
    print(proc.stdout)
    print("--- stderr ---")
    print(proc.stderr)


def case_static():
    print("static script")
    text = script_text()
    ok('PATH="/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"' not in text,
       "the Mac PATH assignment is not unconditional")
    ok("/opt/homebrew/bin" in text and "[ -d /opt/homebrew/bin ]" in text,
       "homebrew is prepended only when that directory exists")
    ok("set -euo pipefail" in text, "the script sets -euo pipefail")
    ok("--autostash" not in text, "the script does not autostash")
    ok("pull --no-rebase --ff-only origin main" in text,
       "the update is a fast-forward pull of origin/main")
    ok("MARKET_DAILY_REEXEC" in text and 'main "$@"' in text and text.rstrip().endswith("exit"),
       "the body is a function, re-exec'd once, then exit")
    ok("MARKET_CODE_SHA" in text, "the code SHA is passed into market_track")
    ok("git_remote()" in text and ">/dev/null" in text and '"$cmd" -q' in text,
       "fetch, pull, and push are quiet and discard output")
    invoked = [
        line.strip() for line in text.splitlines()
        if line.strip().startswith("git ") and not line.strip().startswith("git_remote")
        and not line.strip().startswith("git -c") and not line.strip().startswith("git rebase")
        and not line.strip().startswith("git rev-parse") and not line.strip().startswith("git diff")
        and not line.strip().startswith("git checkout") and not line.strip().startswith("git commit")
        and not line.strip().startswith("git add") and not line.strip().startswith("git reset")
    ]
    ok(not any(line.startswith("git fetch") or line.startswith("git pull") or line.startswith("git push")
               for line in invoked),
       "fetch, pull, and push are only reached through the quiet wrapper")
    ok("git push --force" not in text and "push -f" not in text,
       "the script does not force-push")


def case_clean_main():
    print("clean main")
    repo = Repo()
    try:
        write(os.path.join(repo.clone, "scratch-untracked.txt"), "leftover\n")
        before = repo.head()
        proc = repo.run()
        text = combined(proc)
        if proc.returncode != 0:
            print_failure(proc)
        eq(proc.returncode, 0, "clean main exits 0")
        eq(repo.stub_lines(), ["ran"], "the stub ran once")
        ok("published on attempt 1" in text, "the ledger push succeeded on the first attempt")
        ledger = repo.origin_ledger()
        eq(ledger["meta"].get("code_sha"), before,
           "meta.code_sha equals the code HEAD the run executed")
        eq(git(repo.clone, "rev-parse", "HEAD^").stdout.strip(), before,
           "that SHA is the parent of the ledger commit")
        names = repo.origin_names()
        ok(names and set(names) <= {"data/market_ledger.json", "data/sp500.json"},
           f"the pushed commit is only ledger data ({names})")
        ok(os.path.exists(os.path.join(repo.clone, "scratch-untracked.txt")),
           "an untracked file is left in place")
        eq(repo.branch(), "main", "the run stays on main")
    finally:
        repo.close()


def case_other_branch_clean():
    print("other branch, clean tree")
    repo = Repo()
    try:
        git(repo.clone, "checkout", "-b", "feature")
        write(os.path.join(repo.clone, "feature.txt"), "feature work\n")
        git(repo.clone, "add", "--", "feature.txt")
        git(repo.clone, "commit", "-m", "feature work")
        proc = repo.run()
        text = combined(proc)
        if proc.returncode != 0:
            print_failure(proc)
        eq(proc.returncode, 0, "a clean non-main branch exits 0 after switching")
        ok("checked out main" in text, "the script checked out main")
        eq(repo.branch(), "main", "the checkout is main after the run")
        eq(repo.stub_lines(), ["ran"], "the stub ran on main")
        show = git(repo.origin, "ls-tree", "-r", "--name-only", "main").stdout
        ok("feature.txt" not in show.splitlines(),
           "the feature commit was not pushed")
    finally:
        repo.close()


def case_other_branch_dirty():
    print("other branch, tracked local change")
    repo = Repo()
    try:
        git(repo.clone, "checkout", "-b", "feature")
        path = os.path.join(repo.clone, "market_track.py")
        with open(path, "a", encoding="utf-8") as handle:
            handle.write("\n# local edit\n")
        before = open(path, encoding="utf-8").read()
        proc = repo.run()
        text = combined(proc)
        ok(proc.returncode != 0, f"dirty non-main branch exits non-zero ({proc.returncode})")
        ok("tracked local changes" in text, "the log says it will not force checkout")
        eq(repo.branch(), "feature", "the checkout stays on the other branch")
        eq(repo.stub_lines(), [], "the stub did not run")
        eq(open(path, encoding="utf-8").read(), before, "the local edit was not discarded")
    finally:
        repo.close()


def case_dirty_plus_leftover():
    print("dirty tree with a leftover ledger commit")
    repo = Repo()
    try:
        write(os.path.join(repo.clone, "data", "market_ledger.json"),
              '{"meta": {"marker": "leftover"}, "trades": []}\n')
        git(repo.clone, "add", "--", "data/market_ledger.json")
        git(repo.clone, "commit", "-m", "leftover ledger")
        path = os.path.join(repo.clone, "market_track.py")
        with open(path, "a", encoding="utf-8") as handle:
            handle.write("\n# local edit\n")
        before = open(path, encoding="utf-8").read()
        proc = repo.run()
        text = combined(proc)
        if "tracked tree is dirty" not in text:
            print_failure(proc)
        ok(proc.returncode != 0, f"a dirty tree with a leftover commit exits non-zero ({proc.returncode})")
        ok("tracked tree is dirty" in text, "the log names the dirty tree, not the leftover commit")
        ok("local commit(s) not on origin/main" not in text,
           "the log does not blame the leftover commit")
        eq(repo.stub_lines(), [], "the stub did not run")
        eq(open(path, encoding="utf-8").read(), before, "the local edit was not discarded")
        log = git(repo.origin, "log", "--format=%s", "main").stdout
        ok("leftover ledger" not in log, "the leftover ledger commit was not pushed")
    finally:
        repo.close()


def case_rebase_already_in_progress():
    print("rebase already in progress names the hand recovery")
    repo = Repo()
    try:
        write(os.path.join(repo.clone, "data", "market_ledger.json"),
              '{"meta": {"marker": "origin"}, "trades": []}\n')
        git(repo.clone, "add", "--", "data/market_ledger.json")
        git(repo.clone, "commit", "-m", "origin ledger")
        git(repo.clone, "push", "origin", "main")
        git(repo.clone, "reset", "--hard", "HEAD~1")
        write(os.path.join(repo.clone, "data", "market_ledger.json"),
              '{"meta": {"marker": "local"}, "trades": []}\n')
        git(repo.clone, "add", "--", "data/market_ledger.json")
        git(repo.clone, "commit", "-m", "local ledger")
        started = git(repo.clone, "-c", "rebase.autoStash=false", "rebase", "--no-autostash",
                      "origin/main", check=False)
        rebase_dir = git(repo.clone, "rev-parse", "--git-path", "rebase-merge").stdout.strip()
        if not os.path.isabs(rebase_dir):
            rebase_dir = os.path.join(repo.clone, rebase_dir)
        if not os.path.isdir(rebase_dir):
            raise RuntimeError(f"rebase did not stop in progress\n{started.stdout}{started.stderr}")
        proc = repo.run()
        text = combined(proc)
        if "git rebase --abort" not in text:
            print_failure(proc)
        ok(proc.returncode != 0, f"a rebase already in progress exits non-zero ({proc.returncode})")
        ok("rebase or merge is in progress" in text, "the log names the rebase")
        ok("git rebase --abort" in text and "git reset --hard origin/main" in text
           and "without force-pushing" in text,
           "the log says how to recover from the leftover rebase without force-pushing")
        eq(repo.stub_lines(), [], "the stub did not run")
        ok(os.path.isdir(rebase_dir), "the in-progress rebase was left for hand recovery")
        eq(repo.origin_ledger()["meta"].get("marker"), "origin",
           "the in-progress rebase was not force-pushed")
    finally:
        repo.close()


def case_dirty_tracked():
    print("tracked dirty market_track.py")
    repo = Repo()
    try:
        path = os.path.join(repo.clone, "market_track.py")
        with open(path, "a", encoding="utf-8") as handle:
            handle.write("\n# local edit\n")
        proc = repo.run()
        text = combined(proc)
        ok(proc.returncode != 0, f"a dirty tracked file exits non-zero ({proc.returncode})")
        ok("tracked tree is dirty" in text, "the log names the dirty tree")
        eq(repo.stub_lines(), [], "the stub did not run")
        eq(repo.head(), repo.base, "nothing was pushed")
    finally:
        repo.close()


def case_local_commit():
    print("local unpushed commit")
    repo = Repo()
    try:
        write(os.path.join(repo.clone, "notes.txt"), "not ledger\n")
        git(repo.clone, "add", "--", "notes.txt")
        git(repo.clone, "commit", "-m", "local only")
        proc = repo.run()
        text = combined(proc)
        ok(proc.returncode != 0, f"a local commit exits non-zero ({proc.returncode})")
        ok("local commit(s) not on origin/main" in text, "the log names the unpushed commit")
        eq(repo.stub_lines(), [], "the stub did not run")
        show = git(repo.origin, "ls-tree", "-r", "--name-only", "main").stdout
        ok("notes.txt" not in show.splitlines(), "the local commit was not pushed")
    finally:
        repo.close()


def case_origin_ahead():
    print("origin ahead")
    new_stub = STUB.replace(
        'os.environ.get("STUB_MARKER", "ran")',
        'os.environ.get("STUB_MARKER", "ran-new")',
        1,
    )
    repo = Repo()
    try:
        write(os.path.join(repo.clone, "market_track.py"), new_stub)
        git(repo.clone, "add", "--", "market_track.py")
        git(repo.clone, "commit", "-m", "new stub")
        git(repo.clone, "push", "origin", "main")
        new_head = repo.head()
        git(repo.clone, "reset", "--hard", "HEAD~1")
        proc = repo.run()
        text = combined(proc)
        if proc.returncode != 0:
            print_failure(proc)
        eq(proc.returncode, 0, "a fast-forward exits 0")
        eq(repo.stub_lines(), ["ran-new"], "the run used the stub from origin/main")
        ok("ran\n" not in text and repo.stub_lines() != ["ran"], "the old stub did not run")
        eq(repo.head() and git(repo.clone, "rev-parse", "HEAD^").stdout.strip(), new_head,
           "the ledger commit sits on the fast-forwarded stub")
        eq(repo.origin_ledger()["meta"].get("code_sha"), new_head,
           "meta.code_sha is the fast-forwarded code HEAD")
    finally:
        repo.close()


def case_script_reexec():
    print("upstream script change re-execs once")
    text = script_text()
    anchor = "  # ledger-run\n"
    if anchor in text:
        updated = text.replace(anchor, anchor + "  echo REEXEC_NEW >> reexec.log\n", 1)
    else:
        # Main's runner has no re-exec point. Appending the marker still leaves it
        # outside the process that is already reading the old file.
        updated = text if text.endswith("\n") else text + "\n"
        updated += "echo REEXEC_NEW >> reexec.log\n"
    repo = Repo()
    try:
        write(os.path.join(repo.clone, "scripts", "market_daily.sh"), updated)
        git(repo.clone, "add", "--", "scripts/market_daily.sh")
        git(repo.clone, "commit", "-m", "new daily script")
        git(repo.clone, "push", "origin", "main")
        git(repo.clone, "reset", "--hard", "HEAD~1")
        proc = repo.run()
        out = combined(proc)
        if proc.returncode != 0:
            print_failure(proc)
        eq(proc.returncode, 0, "the re-exec'd script exits 0")
        log_path = os.path.join(repo.clone, "reexec.log")
        lines = []
        if os.path.exists(log_path):
            with open(log_path, encoding="utf-8") as handle:
                lines = [line.strip() for line in handle if line.strip()]
        eq(lines, ["REEXEC_NEW"], "the pulled script ran once")
        eq(repo.stub_lines(), ["ran"], "market_track ran once, not twice")
        ok("syntax error" not in out.lower() and "unexpected EOF" not in out,
           "the run did not execute a spliced script")
    finally:
        repo.close()


def case_fetch_fails():
    print("failed fetch")
    repo = Repo()
    try:
        git(repo.clone, "remote", "set-url", "origin",
            os.path.join(repo.tmp.name, "missing.git"))
        proc = repo.run()
        text = combined(proc)
        ok(proc.returncode != 0, f"a failed fetch exits non-zero ({proc.returncode})")
        ok("git fetch origin main failed" in text, "the log names the failed fetch")
        ok("fetch failed (git exit " in text, "the log names the git exit code")
        ok("missing.git" not in text, "a failed fetch does not echo the remote URL")
        eq(repo.stub_lines(), [], "the stub did not run")
    finally:
        repo.close()


def case_merge_in_progress():
    print("merge in progress")
    repo = Repo()
    try:
        write(os.path.join(repo.clone, "notes.txt"), "base\n")
        git(repo.clone, "add", "--", "notes.txt")
        git(repo.clone, "commit", "-m", "notes")
        git(repo.clone, "checkout", "-b", "side")
        write(os.path.join(repo.clone, "notes.txt"), "side\n")
        git(repo.clone, "commit", "-am", "side")
        git(repo.clone, "checkout", "main")
        write(os.path.join(repo.clone, "notes.txt"), "main\n")
        git(repo.clone, "commit", "-am", "main side")
        git(repo.clone, "merge", "side", check=False)
        proc = repo.run()
        text = combined(proc)
        ok(proc.returncode != 0, f"a merge in progress exits non-zero ({proc.returncode})")
        ok("rebase or merge is in progress" in text, "the log names the merge")
        eq(repo.stub_lines(), [], "the stub did not run")
    finally:
        repo.close()


def case_push_retry():
    print("push retry stays on ledger files")
    repo = Repo()
    try:
        hook = os.path.join(repo.origin, "hooks", "pre-receive")
        write(hook, """#!/bin/bash
flag="$GIT_DIR/reject-once"
if [ ! -f "$flag" ]; then
  : > "$flag"
  echo "rejecting first push" >&2
  exit 1
fi
exit 0
""")
        os.chmod(hook, 0o755)
        proc = repo.run()
        text = combined(proc)
        if proc.returncode != 0:
            print_failure(proc)
        eq(proc.returncode, 0, "a rejected first push still publishes")
        ok("published on attempt 2" in text, "the second attempt publishes")
        names = repo.origin_names()
        ok(set(names) <= {"data/market_ledger.json", "data/sp500.json"} and names,
           f"the retried push is only ledger data ({names})")
        eq(repo.origin_ledger()["meta"].get("code_sha"), repo.base,
           "the retried publish still stamps the code HEAD")
    finally:
        repo.close()


def _ahead_with_new_stub(repo, rewind_tracking=False):
    new_stub = STUB.replace(
        'os.environ.get("STUB_MARKER", "ran")',
        'os.environ.get("STUB_MARKER", "ran-new")',
        1,
    )
    write(os.path.join(repo.clone, "market_track.py"), new_stub)
    git(repo.clone, "add", "--", "market_track.py")
    git(repo.clone, "commit", "-m", "new stub")
    git(repo.clone, "push", "origin", "main")
    git(repo.clone, "reset", "--hard", "HEAD~1")
    old = repo.head()
    if rewind_tracking:
        # push moved refs/remotes/origin/main. The stale-guard bug is the
        # checkout whose local origin/main was never refreshed, so HEAD still
        # matches that ref while the bare origin is ahead.
        git(repo.clone, "update-ref", "refs/remotes/origin/main", old)
    return old


def case_stale_reexec():
    print("stale MARKET_DAILY_REEXEC does not grade old code")
    repo = Repo()
    try:
        _ahead_with_new_stub(repo, rewind_tracking=True)
        proc = repo.run(extra_env={"MARKET_DAILY_REEXEC": "1"})
        graded_old = proc.returncode == 0 and repo.stub_lines() == ["ran"]
        if graded_old or (proc.returncode != 0 and repo.stub_lines() != ["ran-new"]):
            print_failure(proc)
        ok(not graded_old, "a stale MARKET_DAILY_REEXEC=1 did not grade the old code and succeed")
        ok(proc.returncode != 0 or repo.stub_lines() == ["ran-new"],
           "a stale 1 refused or fast-forwarded onto the new stub")
    finally:
        repo.close()
    repo = Repo()
    try:
        old = _ahead_with_new_stub(repo, rewind_tracking=True)
        proc = repo.run(extra_env={"MARKET_DAILY_REEXEC": old})
        text = combined(proc)
        if not (proc.returncode != 0 and repo.stub_lines() == []):
            print_failure(proc)
        ok(proc.returncode != 0, f"a stale re-exec SHA exits non-zero ({proc.returncode})")
        eq(repo.stub_lines(), [], "a stale re-exec SHA did not grade")
        ok("re-exec SHA" in text, "the log names the stale re-exec SHA")
        ok("must not be set in the service environment" in text,
           "the log says MARKET_DAILY_REEXEC must not be set in the service")
    finally:
        repo.close()


def case_recover_ledger_commit():
    print("leftover ledger commit is recovered")
    repo = Repo()
    try:
        write(os.path.join(repo.clone, "data", "market_ledger.json"),
              '{"meta": {"marker": "leftover"}, "trades": []}\n')
        git(repo.clone, "add", "--", "data/market_ledger.json")
        git(repo.clone, "commit", "-m", "leftover ledger")
        proc = repo.run()
        text = combined(proc)
        if proc.returncode != 0:
            print_failure(proc)
        eq(proc.returncode, 0, "a leftover ledger commit exits 0")
        eq(repo.stub_lines(), ["ran"], "the run continued and graded")
        log = git(repo.origin, "log", "--format=%s", "main").stdout
        ok("leftover ledger" in log, "the leftover ledger commit was pushed")
        ok("recovered the leftover ledger commit" in text, "the log says the leftover was recovered")
    finally:
        repo.close()


def case_conflicting_leftover():
    print("conflicting leftover ledger commit refuses")
    repo = Repo()
    try:
        write(os.path.join(repo.clone, "data", "market_ledger.json"),
              '{"meta": {"marker": "origin"}, "trades": []}\n')
        git(repo.clone, "add", "--", "data/market_ledger.json")
        git(repo.clone, "commit", "-m", "origin ledger")
        git(repo.clone, "push", "origin", "main")
        git(repo.clone, "reset", "--hard", "HEAD~1")
        write(os.path.join(repo.clone, "data", "market_ledger.json"),
              '{"meta": {"marker": "local"}, "trades": []}\n')
        git(repo.clone, "add", "--", "data/market_ledger.json")
        git(repo.clone, "commit", "-m", "local ledger")
        proc = repo.run()
        text = combined(proc)
        ok(proc.returncode != 0, f"a conflicting leftover exits non-zero ({proc.returncode})")
        ok("conflicted" in text and "git reset --hard origin/main" in text
           and "without force-pushing" in text,
           "the log says how to recover from the conflict without force-pushing")
        eq(repo.stub_lines(), [], "the stub did not run")
        ok(not os.path.isdir(os.path.join(repo.clone, ".git", "rebase-merge")),
           "a conflicted rebase was aborted")
        ok(not os.path.isdir(os.path.join(repo.clone, ".git", "rebase-apply")),
           "no rebase-apply directory was left behind")
        eq(repo.origin_ledger()["meta"].get("marker"), "origin",
           "the conflicting commit was not force-pushed")
    finally:
        repo.close()


def case_remote_url_quiet():
    print("remote URL stays out of the log")
    repo = Repo()
    try:
        url = git(repo.clone, "remote", "get-url", "origin").stdout.strip()
        proc = repo.run()
        text = combined(proc)
        if proc.returncode != 0:
            print_failure(proc)
        eq(proc.returncode, 0, "a clean run still exits 0 with quiet remotes")
        ok(url not in text, "the remote URL is not in the log")
    finally:
        repo.close()


def _load_market_track():
    path = os.environ.get("MARKET_TRACK_FILE")
    if not path:
        import market_track as MT
        return MT
    import importlib.util
    spec = importlib.util.spec_from_file_location("market_track_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    # The copy may live outside the repo. Grade against this checkout.
    if hasattr(mod, "ROOT"):
        mod.ROOT = ROOT
    return mod


def case_save_stamps_sha():
    print("market_track.save stamps code_sha with the ledger")
    MT = _load_market_track()
    trade = {
        "id": "frozen-sample",
        "rule": "sw_rsi2_pullback",
        "status": "closed",
        "ret_net": 0.01,
    }
    tmp = tempfile.TemporaryDirectory()
    try:
        path = os.path.join(tmp.name, "market_ledger.json")
        previous = MT.LEDGER
        MT.LEDGER = path
        saved = os.environ.pop("MARKET_CODE_SHA", None)
        try:
            os.environ["MARKET_CODE_SHA"] = "abc123def456"
            payload = {"trades": [dict(trade)], "meta": {"live_from": "2026-09-19"}}
            MT.save(payload)
            written = json.loads(open(path, encoding="utf-8").read())
            eq(written["trades"], [trade], "save leaves the trades alone")
            eq(written["meta"].get("live_from"), "2026-09-19", "save leaves the other meta alone")
            eq(written["meta"].get("code_sha"), "abc123def456",
               "save writes MARKET_CODE_SHA with the ledger")
            ok("updated" in written["meta"], "save still stamps updated")
            ok(not os.path.exists(path + ".tmp"), "the temp ledger file is replaced")
            os.environ.pop("MARKET_CODE_SHA", None)
            MT.save({"trades": [dict(trade)], "meta": {}})
            fallback = json.loads(open(path, encoding="utf-8").read())
            head = subprocess.run(
                ["git", "-C", ROOT, "rev-parse", "HEAD"],
                check=True, capture_output=True, text=True,
            ).stdout.strip()
            eq(fallback["meta"].get("code_sha"), head,
               "save without the env var reads git rev-parse HEAD")
            os.environ["GIT_DIR"] = os.path.join(tmp.name, "missing-git")
            MT.save({"trades": [dict(trade)], "meta": {
                "code_sha": "stale-sha", "live_from": "2026-09-19"}})
            unknown = json.loads(open(path, encoding="utf-8").read())
            eq(unknown["meta"].get("code_sha"), "unknown",
               "a missing SHA overwrites a stale code_sha with unknown")
            eq(unknown["meta"].get("live_from"), "2026-09-19",
               "unknown does not drop the other meta")
            eq(unknown["trades"], [trade], "unknown does not change the trades")
            os.environ.pop("GIT_DIR", None)
            removed = {
                "cr_btc_2200", "dt_intraday_mom", "sw_52w_breakout", "sw_ma_cross_rsi",
                "cr_trend20", "dt_orb30", "dt_orb30_long", "dt_vwap_reclaim",
            }
            eq(MT.REMOVED_RULES, removed, "REMOVED_RULES is unchanged")
        finally:
            MT.LEDGER = previous
            os.environ.pop("GIT_DIR", None)
            if saved is None:
                os.environ.pop("MARKET_CODE_SHA", None)
            else:
                os.environ["MARKET_CODE_SHA"] = saved
    finally:
        tmp.cleanup()


def main():
    digest = hashlib.sha256(open(SCRIPT, "rb").read()).hexdigest()
    print(f"script {SCRIPT}")
    print(f"script sha256 {digest}")
    case_static()
    case_clean_main()
    case_other_branch_clean()
    case_other_branch_dirty()
    case_dirty_plus_leftover()
    case_rebase_already_in_progress()
    case_dirty_tracked()
    case_local_commit()
    case_origin_ahead()
    case_script_reexec()
    case_fetch_fails()
    case_merge_in_progress()
    case_push_retry()
    case_stale_reexec()
    case_recover_ledger_commit()
    case_conflicting_leftover()
    case_remote_url_quiet()
    case_save_stamps_sha()
    print()
    if FAILS:
        print(f"FAILED: {len(FAILS)}")
        for item in FAILS:
            print(f"   - {item}")
        return 1
    print("all market daily tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
