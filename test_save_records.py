#!/usr/bin/env python3
"""The save race (save_records.py, 2026-11-01), reproduced with two real git clones of one bare remote.

Writer A is the Feeds heartbeat: it restamps the derived feed and pushes first. Writer B is a soccer
collector on the same base: it appends a ledger row, rebuilds the feed, and saves second. The old save
(rebase, nothing else) hits a content conflict in the feed and fails; save_records must land B's ledger row
and a feed rebuilt from the merged ledger that keeps A's first-publication stamps. A genuine conflict in a
ledger must fail safely: main untouched, the run's commit left for review. Offline; needs only git.
"""
import json
import os
import subprocess
import sys
import tempfile

import save_records as S

FAILS = []


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


# A toy feed builder shaped like production.build_feed: one lead per ledger entry, each lead keeping the
# first-publication stamp of the previous feed, the feed stamped with the build time (BUILD_AT).
BUILDER = r'''
import json, os
led = json.load(open("data/ledger.json"))
try:
    prev = json.load(open("data/feed.json"))
except (OSError, ValueError):
    prev = {"leads": {}}
now = os.environ["BUILD_AT"]
leads = {e["id"]: {"published_at": (prev.get("leads") or {}).get(e["id"], {}).get("published_at", now)}
         for e in led["entries"]}
json.dump({"updated_at": now, "leads": leads}, open("data/feed.json", "w"), indent=1, sort_keys=True)
'''


def sh(cmd, cwd, env=None):
    return subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True,
                          env={**os.environ, **(env or {})})


def write(cwd, path, obj):
    with open(os.path.join(cwd, path), "w") as f:
        json.dump(obj, f, indent=1, sort_keys=True)


def read(cwd, path):
    with open(os.path.join(cwd, path)) as f:
        return json.load(f)


def setup(root):
    """A bare remote holding a ledger of one entry and its feed, and two clones of it: a (heartbeat), b (collector)."""
    remote, seed = os.path.join(root, "remote.git"), os.path.join(root, "seed")
    sh(f"git init -q --bare -b main {remote}", root)
    sh(f"git clone -q {remote} seed", root)
    os.makedirs(os.path.join(seed, "data"))
    with open(os.path.join(seed, "build.py"), "w") as f:
        f.write(BUILDER)
    write(seed, "data/ledger.json", {"entries": [{"id": "m1", "row": "entered 10:00"}]})
    sh("python3 build.py", seed, {"BUILD_AT": "10:00"})
    sh("git -c user.name=t -c user.email=t@t add -A && git -c user.name=t -c user.email=t@t commit -q -m base "
       "&& git push -q origin HEAD:main", seed)
    for c in ("a", "b"):
        sh(f"git clone -q {remote} {c} && git -C {c} config user.name t && git -C {c} config user.email t@t", root)
    return remote, os.path.join(root, "a"), os.path.join(root, "b")


def heartbeat(a, at):
    """Writer A: restamp the feed and push (the Feeds heartbeat)."""
    sh("python3 build.py", a, {"BUILD_AT": at})
    sh("git add data/feed.json && git commit -q -m 'Feeds heartbeat' && git push -q origin HEAD:main", a)


def collect(b, row_id, at):
    """Writer B's run before its save: append a ledger row and rebuild the feed (the collector's own build)."""
    led = read(b, "data/ledger.json")
    led["entries"].append({"id": row_id, "row": f"entered {at}"})
    write(b, "data/ledger.json", led)
    sh("python3 build.py", b, {"BUILD_AT": at})


def on_main(remote, root, path):
    out = sh(f"git --git-dir={remote} show main:{path}", root)
    return json.loads(out.stdout) if out.returncode == 0 else None


DERIVED = [("data/feed.json", "python3 build.py")]
quiet = lambda *_: None

print("the race, reproduced: the old save (rebase only) fails on the derived feed")
with tempfile.TemporaryDirectory() as root:
    remote, a, b = setup(root)
    heartbeat(a, "10:30")
    collect(b, "m2", "10:31")
    sh("git add -A && git commit -q -m 'Soccer label rules paper observations'", b)
    pushed = sh("git push -q origin HEAD:main", b).returncode
    sh("git fetch -q origin main", b)
    rebased = sh("git rebase origin/main", b)
    check("B's push is rejected after A pushed", pushed != 0, True)
    check("the old rebase stops on a content conflict in the feed",
          (rebased.returncode != 0, "CONFLICT (content): Merge conflict in data/feed.json" in rebased.stdout), (True, True))

print("\nthe fix: save_records rebuilds the feed from the merged ledger")
with tempfile.TemporaryDirectory() as root:
    remote, a, b = setup(root)
    heartbeat(a, "10:30")
    collect(b, "m2", "10:31")
    os.environ["BUILD_AT"] = "10:32"                     # the rebuild during B's save
    rc = S.save("Soccer label rules paper observations", ["data/ledger.json"], DERIVED, cwd=b, log=quiet)
    led, feed = on_main(remote, root, "data/ledger.json"), on_main(remote, root, "data/feed.json")
    check("B's save succeeds", rc, 0)
    check("B's ledger row is on main next to the base row", [e["id"] for e in led["entries"]], ["m1", "m2"])
    check("the feed on main is rebuilt from the merged ledger: a lead per row", sorted(feed["leads"]), ["m1", "m2"])
    check("the base lead keeps its first-publication stamp; B's new lead is published by the rebuild",
          (feed["leads"]["m1"]["published_at"], feed["leads"]["m2"]["published_at"]), ("10:00", "10:32"))
    check("the feed is stamped by the rebuild, newer than the heartbeat", feed["updated_at"], "10:32")
    log = sh(f"git --git-dir={remote} log --format=%s main", root).stdout.split("\n")
    check("A's heartbeat commit stays in history under B's", log[:3], ["Soccer label rules paper observations", "Feeds heartbeat", "base"])
    clean = sh("git status --porcelain", b).stdout.strip()
    check("B's checkout is left clean (no rebase in progress)", (clean, os.path.isdir(os.path.join(b, ".git", "rebase-merge"))), ("", False))

print("\nnothing raced: one push, no rebuild")
with tempfile.TemporaryDirectory() as root:
    remote, a, b = setup(root)
    collect(b, "m2", "10:31")
    os.environ["BUILD_AT"] = "99:99"
    rc = S.save("obs", ["data/ledger.json"], DERIVED, cwd=b, log=quiet)
    check("saved first time, the run's own feed untouched", (rc, on_main(remote, root, "data/feed.json")["updated_at"]), (0, "10:31"))
    check("nothing staged: nothing to save", S.save("obs", ["data/ledger.json"], DERIVED, cwd=b, log=quiet), 0)

print("\na clean rebase still rebuilds: a feed spliced line by line is never trusted")
with tempfile.TemporaryDirectory() as root:
    remote, a, b = setup(root)
    feed_a = read(a, "data/feed.json")
    feed_a["note"] = "written elsewhere"                 # a change git can merge without a conflict
    write(a, "data/feed.json", feed_a)
    sh("git add -A && git commit -q -m other && git push -q origin HEAD:main", a)
    collect(b, "m2", "10:31")
    os.environ["BUILD_AT"] = "10:33"
    rc = S.save("obs", ["data/ledger.json"], DERIVED, cwd=b, log=quiet)
    feed = on_main(remote, root, "data/feed.json")
    check("saved, and the feed on main is the builder's output on the merged ledger",
          (rc, sorted(feed["leads"]), feed["updated_at"], "note" in feed), (0, ["m1", "m2"], "10:33", False))

print("\na genuine conflict in a ledger fails safely")
with tempfile.TemporaryDirectory() as root:
    remote, a, b = setup(root)
    collect(a, "mA", "10:20")                            # a second writer of the LEDGER (never expected)
    sh("git add -A && git commit -q -m 'other ledger writer' && git push -q origin HEAD:main", a)
    collect(b, "mB", "10:21")
    msgs = []
    rc = S.save("obs", ["data/ledger.json"], DERIVED, cwd=b, log=msgs.append)
    led = on_main(remote, root, "data/ledger.json")
    check("the save fails (exit 1) rather than take a side", rc, 1)
    check("main keeps the other writer's row, untouched", [e["id"] for e in led["entries"]], ["m1", "mA"])
    check("B's row is not lost: its commit stays in B's checkout for review, the rebase aborted",
          ("mB" in sh("git show HEAD:data/ledger.json", b).stdout, os.path.isdir(os.path.join(b, ".git", "rebase-merge"))),
          (True, False))
    check("the log names the conflicted record", any("data/ledger.json" in m for m in msgs), True)

print("\nthe workflows use it")
for wf, derived in ((".github/workflows/soccer-rules.yml", "data/soccer_rules_production_leads.json"),
                    (".github/workflows/soccer-team-rules.yml", "data/soccer_team_rules_production_leads.json")):
    text = open(wf).read()
    save_step = text[text.find("- name: Save records"):]
    check(f"{wf}: saves through save_records.py with its feed as a derived file",
          ("python3 save_records.py" in save_step, f"--derived {derived}" in save_step, "git rebase origin/main" in save_step),
          (True, True, False))

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
