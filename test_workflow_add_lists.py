#!/usr/bin/env python3
"""Every ledger a soccer workflow's scripts rewrite is in that workflow's save_records --add list (2026-11-21).

soccer-rules.yml's Save records failed 5 of 8 runs with "cannot rebase: You have unstaged changes": shadows.py rewrote
data/shadows_soccer_ledger.json, which was not in --add. Each workflow below names the script -> ledger files it writes (taken from the
modules' own path constants, so a renamed ledger follows); a script the workflow runs that is not listed here fails the test, so a new lane
has to say what it writes. Derived feeds are staged by --derived and are not part of --add.
"""
import os
import re
import sys

import btts_sa
import contender_overs
import flipped_unders
import sa_o15
import shadows
import soccer_rules
import soccer_team_rules
import under_piggyback
import club82
import nba_qlines

ROOT = os.path.dirname(os.path.abspath(__file__))
FAILS = []


def check(label, ok, extra=""):
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" {extra}"))
    if not ok:
        FAILS.append(label)


def rel(p):
    return os.path.relpath(p, ROOT)


WRITES = {
    "soccer-rules.yml": {
        "soccer_rules.py": [soccer_rules.PATH], "contender_overs.py": [contender_overs.PATH], "sa_o15.py": [sa_o15.PATH],
        "btts_sa.py": [btts_sa.PATH], "flipped_unders.py": [flipped_unders.PATH],
        "under_piggyback.py": [under_piggyback.path(k) for k in under_piggyback.LANES],
        "shadows.py": [shadows.GROUPS["soccer"]],
        "soccer_rules_production.py": [],                  # the derived feed: staged by --derived
    },
    "club82.yml": {"club82.py": [club82.PATH]},
    "nba-qlines.yml": {"nba_qlines.py": [nba_qlines.PATH, nba_qlines.GAMES_PATH]},
    "soccer-team-rules.yml": {
        "soccer_team_rules.py": [soccer_team_rules.PATH], "shadows.py": [shadows.GROUPS["team"]],
        "soccer_team_rules_production.py": [],             # the derived feed
    },
}

for wf, scripts in WRITES.items():
    print(wf)
    text = open(os.path.join(ROOT, ".github", "workflows", wf)).read()
    m = re.search(r"--add((?:[ \t\\\n]+data/\S+)+)", text)
    add = set(re.findall(r"data/[\w./-]+\.json", m.group(1))) if m else set()
    ran = [s for s in dict.fromkeys(re.findall(r"python3 ([\w]+\.py)", text)) if not s.startswith("test_") and s != "save_records.py"]
    check("every script the workflow runs is accounted for here", all(s in scripts for s in ran), [s for s in ran if s not in scripts])
    for s, paths in scripts.items():
        for p in paths:
            check(f"{s} writes {rel(p)}: in --add", rel(p) in add, sorted(add))
    check("every shadow and lane test the workflow's lanes need is in its Tests step",
          all(t in text for t in (["test_shadows.py"] if "shadows.py" in scripts else [])), "test_shadows.py missing")

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
