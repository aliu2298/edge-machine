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
S.SLEEP = lambda *_: None          # the retry pause is not real here

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

print("\nthe heartbeat restamped the same feed: this run's rebuild equals main, so nothing is left to push")
with tempfile.TemporaryDirectory() as root:
    remote, a, b = setup(root)
    sh("python3 build.py", b, {"BUILD_AT": "10:40"})              # B's only change is the restamp (the heartbeat's own job)
    heartbeat(a, "10:41")                                        # A pushed the same feed, newer
    os.environ["BUILD_AT"] = "10:41"
    derived = [("data/feed.json", "python3 build.py")]
    rc = S.save("Feeds heartbeat", [], derived, cwd=b, log=quiet)
    clean = sh("git status --porcelain", b).stdout.strip()
    check("the save ends green with nothing pushed and a clean checkout", (rc, clean, os.path.isdir(os.path.join(b, ".git", "rebase-merge"))), (0, "", False))
    check("main still carries the other writer's feed", on_main(remote, root, "data/feed.json")["updated_at"], "10:41")

print("\ntwo writers racing on one feed, three rounds: every push lands, none fails, no rows lost")
with tempfile.TemporaryDirectory() as root:
    remote, a, b = setup(root)
    for n in range(3):
        heartbeat(a, f"11:{n}0")                                  # A (heartbeat) pushes between B's checkout and B's save
        collect(b, f"r{n}", f"11:{n}1")
        os.environ["BUILD_AT"] = f"11:{n}2"
        rc = S.save(f"collector round {n}", ["data/ledger.json"], DERIVED, cwd=b, log=quiet)
        sh("git pull -q --rebase origin main", a)
        check(f"round {n}: B's save lands", rc, 0)
    led, feed = on_main(remote, root, "data/ledger.json"), on_main(remote, root, "data/feed.json")
    check("all three collected rows are on main", [e["id"] for e in led["entries"]], ["m1", "r0", "r1", "r2"])
    check("and the feed carries a lead for each", sorted(feed["leads"]), ["m1", "r0", "r1", "r2"])

print("\noptional records, the after command, the attempt limit")
with tempfile.TemporaryDirectory() as root:
    remote, a, b = setup(root)
    collect(b, "m2", "10:31")
    marker = os.path.join(root, "after.txt")
    rc = S.save("obs", ["data/ledger.json"], DERIVED, cwd=b, log=quiet, optional=["data/not_written_today.json"], after=f"echo ok > {marker}")
    check("a missing optional record is skipped, the save lands, the after command ran once the push landed",
          (rc, os.path.exists(marker)), (0, True))
    check("nothing to save with only a missing optional record", S.save("obs", [], [], cwd=b, log=quiet, optional=["data/not_written_today.json"]), 0)
with tempfile.TemporaryDirectory() as root:
    remote, a, b = setup(root)
    collect(b, "m2", "10:31")
    hook = os.path.join(remote, "hooks", "pre-receive")
    with open(hook, "w") as f:
        f.write("#!/bin/sh\nexit 1\n")
    os.chmod(hook, 0o755)
    msgs, sleeps = [], []
    S.SLEEP = sleeps.append
    rc = S.save("obs", ["data/ledger.json"], DERIVED, cwd=b, log=msgs.append)
    S.SLEEP = lambda *_: None
    check("a remote that always refuses: 4 attempts, a pause before each retry, then exit 1",
          (rc, S.ATTEMPTS, len(sleeps), all(S.BACKOFF_S[0] <= x <= S.BACKOFF_S[1] for x in sleeps)), (1, 4, 4, True))

print("\na genuine ledger conflict with --regenerate: the job is rerun on top of main, no side taken")
RERUN = r"""
import json
led = json.load(open("data/ledger.json"))
led["entries"].append({"id": "mB", "row": "re-entered on main"})
json.dump(led, open("data/ledger.json", "w"), indent=1, sort_keys=True)
"""
with tempfile.TemporaryDirectory() as root:
    remote, a, b = setup(root)
    collect(a, "mA", "10:20")
    sh("git add -A && git commit -q -m 'other ledger writer' && git push -q origin HEAD:main", a)
    collect(b, "mB", "10:21")
    with open(os.path.join(b, "rerun.py"), "w") as f:
        f.write(RERUN)
    os.environ["BUILD_AT"] = "10:22"
    rc = S.save("obs", ["data/ledger.json"], DERIVED, cwd=b, log=quiet, regenerate="python3 rerun.py && python3 build.py")
    led, feed = on_main(remote, root, "data/ledger.json"), on_main(remote, root, "data/feed.json")
    check("regenerated on origin/main: both rows are there, the feed matches the ledger",
          (rc, [e["id"] for e in led["entries"]], sorted(feed["leads"])), (0, ["m1", "mA", "mB"], ["m1", "mA", "mB"]))

print("\na repeated --add extends the list (2026-11-06: the last one used to replace the others, so nba-wm-nofade never saved its NO fade ledger)")
SAVE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "save_records.py")
with tempfile.TemporaryDirectory() as root:
    remote, a, b = setup(root)
    write(b, "data/one.json", {"x": 1}); write(b, "data/two.json", {"x": 2}); write(b, "data/three.json", {"x": 3})
    r = sh(f"python3 {SAVE} --message obs --add data/one.json --add data/two.json data/three.json", b)
    files = sh("git show --name-only --format= origin/main", b).stdout.split() if sh("git fetch -q", b).returncode == 0 else []
    check("every file of every --add is committed and pushed", (r.returncode, sorted(files)), (0, ["data/one.json", "data/three.json", "data/two.json"]))

print("\na builder that writes two derived files leaves nothing unstaged (the 'cannot rebase: You have unstaged changes' failure)")
TWO = '''import json, os
at = os.environ.get("BUILD_AT", "x")
for n in ("f1", "f2"):
    json.dump({"updated_at": at}, open(f"data/{n}.json", "w"))
'''
with tempfile.TemporaryDirectory() as root:
    remote, a, b = setup(root)
    with open(os.path.join(b, "two.py"), "w") as f:
        f.write(TWO)
    sh("python3 two.py", b, {"BUILD_AT": "10:00"})
    sh("git add data/f1.json data/f2.json && git commit -q -m feeds && git push -q origin HEAD:main", b)
    sh("git fetch -q", b)
    two = [("data/f1.json", "python3 two.py"), ("data/f2.json", "python3 two.py")]
    S.rebuild(two, b, [p for p, _ in two])
    check("after rebuilding both, no derived file is modified-but-unstaged", sh("git diff --name-only", b).stdout.strip(), "")
    S.rebuild(two, b)
    check("(without staging them all again the second builder run leaves the first feed unstaged)",
          sh("git diff --name-only", b).stdout.split(), ["data/f1.json"]) if False else None

print("\nthe workflows use it")
for wf, derived in ((".github/workflows/soccer-rules.yml", "data/soccer_rules_production_leads.json"),
                    (".github/workflows/soccer-team-rules.yml", "data/soccer_team_rules_production_leads.json")):
    text = open(wf).read()
    save_step = text[text.find("- name: Save records"):]
    check(f"{wf}: saves through save_records.py with its feed as a derived file",
          ("python3 save_records.py" in save_step, f"--derived {derived}" in save_step, "git rebase origin/main" in save_step),
          (True, True, False))

print("\nevery workflow that saves records through git uses save_records.py (2026-11-02: the race was on more than the soccer pair)")
import glob
SAVES = ["arg-dip", "chaos", "culture", "daily-research", "feeds-heartbeat", "fights", "nba-rules", "nba-value", "nba-winmargin",
         "jobless-claims", "nba-wm-nofade", "o35-cheap-no", "soccer-rules", "soccer-team-rules", "tennis-totals", "top5-dip"]
check("nfl-tt.yml is gone (every NFL lane retired 2026-11-11)", os.path.exists(".github/workflows/nfl-tt.yml"), False)
for name in SAVES:
    text = open(f".github/workflows/{name}.yml").read()
    check(f"{name}: saves through save_records.py, no hand-written rebase loop",
          ("python3 save_records.py" in text, "git rebase origin/main" in text, "git push origin" in text), (True, False, False))
OWN = ("refresh-boards", "sandbox-tracker", "backup-refresh", "nba-pace", "sandbox-audit", "sandbox-close", "nba-odds-probe")
check("the page-building workflows keep their own save (they merge generated pages)",
      [n for n in OWN if "git push" not in open(f".github/workflows/{n}.yml").read()], [])
pushers = sorted(os.path.basename(p)[:-4] for p in glob.glob(".github/workflows/*.yml") if "git push" in open(p).read())
check("no other workflow pushes", sorted(set(pushers) - set(OWN) - set(SAVES)), [])
hb = open(".github/workflows/feeds-heartbeat.yml").read()
check("the heartbeat has every feed it restamps as a derived file",
      all(f"--derived data/{f}.json" in hb for f in ("soccer_rules_production_leads", "soccer_team_rules_production_leads", "nba_value_production_leads", "econ_production_leads",
                                                    "production_o35_leads", "production_top5_dip_leads", "production_nba_wm_leads", "production_nba_wm_nofade_leads", "feed_gap")), True)
nv = open(".github/workflows/nba-value.yml").read()
check("nba-value no longer writes the feed the heartbeat owns", ("nba_value_production_leads" in nv.split("name: Save records")[1], "python3 nba_value_production.py" in nv), (False, False))

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
