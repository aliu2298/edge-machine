#!/usr/bin/env python3
"""The NBA page's reorganised top half (2026-10-31): glance table, one card per active lane in one layout, the tracker with
its folds, the matchup board order, and the jump pills. Presentation only."""
import json
import os
import re
import sys

import nba_layout as L
import nba_pace_build as NB
import sandbox_audit

FAILS = []


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


if not os.path.exists(NB.SRC):
    print("no pace data; layout checks skipped")
    sys.exit(0)
page = NB.build(json.load(open(NB.SRC)))
main = page[page.find("<main"):]
ids = re.findall(r'<section id="([^"]+)"', main)
print("order")
check("glance, active lanes (YES, NO fade), the ML underdog baseline, tracker, then the matchup board, Ladder after Teams, Retired last",
      [i for i in ids if i in ("glance", "wm-yes", "wm-no", "ml-dog", "tracker", "matchups", "graded", "teams", "ladder", "retired")],
      ["glance", "wm-yes", "wm-no", "ml-dog", "tracker", "matchups", "graded", "teams", "ladder", "retired"])
check("the #cheap-side anchor (the Sandbox index links to it) still holds the lane cards",
      "cheap-side" in ids and ids.index("cheap-side") < ids.index("wm-yes"), True)
check("the jump pills match the sections",
      re.findall(r'<nav class="toc".*?</nav>', page, re.S)[0].count("<a "), 10)

print("\nthe glance table")
g = page[page.find('<section id="glance"'):page.find('<section id="cheap-side"')]
check("one row per active lane, each linking to its card; the ML underdog baseline is not one (2026-11-01)",
      re.findall(r'<a href="#([^"]+)"><b>', g), ["wm-yes", "wm-no"])
check("columns: lane, settled events, split ROI, hold ROI, z, status",
      [re.sub(r"<[^>]+>", "", c) for c in re.findall(r"<th[^>]*>.*?</th>", g.split("<table")[1].split("</tr>")[0])],
      ["Lane", "Settled events", "Split ROI", "Hold ROI", "z (by night)", "Status"])
check("the glance has no moneyline underdog row", "Moneyline underdog" in g, False)
check("one short fold replaces the repeated copy in each card", g.count('id="how-read"'), 1)

print("\nthe lane cards")
for anchor in ("wm-yes", "wm-no"):
    sec = page[page.find(f'<section id="{anchor}"'):]
    sec = sec[:sec.find("</section>")]
    check(f"{anchor}: opens on its rule and record; folds for other exits, trades (and in-sample where it has one), all collapsed",
          ("Trades" in sec, "Other exits / variants" in sec,
           sec.find("Other exits / variants") > sec.find("<table"), "open>" in sec.split("<summary>")[0] + ">"), (True, True, True, True))
    inner = [m for m in re.findall(r"<details[^>]*>", sec)[1:]]
    check(f"{anchor}: no inner fold starts open", [d for d in inner if " open" in d], [])
check("the YES and NO fade cards carry their in-sample research fold, labelled",
      ("In-sample research (not evidence)" in page[page.find('id="wm-yes"'):page.find('id="wm-no"')],
       "In-sample research (not evidence)" in page[page.find('id="wm-no"'):page.find('id="ml-dog"')]), (True, True))
print("\nthe moneyline underdog baseline (2026-11-01)")
b = page[page.find('<section id="ml-dog"'):]
b = b[:b.find('<section id="tracker"')]
check("its own Baselines block after the active lanes, titled blind, saying a filtered lane must beat it, with no status",
      ("Baseline · NBA moneyline underdog (blind, price band only)" in b, "must beat" in b, "Status" in b, "decide at" in b,
       page.find('<section id="ml-dog"') > page.find('<section id="wm-no"')), (True, True, False, False, True))
check("its record: split v hold, then other exits and trades folded", ("chaos-split" in b, "Other exits" in b, "Trades" in b,
      [d for d in re.findall(r"<details[^>]*>", b)[1:] if " open" in d]), (True, True, True, []))
check("the NO fade card puts the overlap with the YES split in view", "Overlap" in page[page.find('id="wm-no"'):page.find('id="ml-dog"')], True)

print("\nthe tracker")
t = page[page.find('<section id="tracker"'):page.find('<section id="matchups"')]
check("the bucket table and both halves are visible", ("By bucket" in t, "Older and newer halves" in t,
      t.find("Older and newer halves") < t.find("By favourite or underdog")), (True, True, True))
check("favourite/underdog and entry-price splits are folds", ("<summary><b>By favourite or underdog</b>" in t, "<summary><b>By entry price</b>" in t), (True, True))
check("the Comeback underdog spread line is a titled sub-card with its by-game table visible, the rest folded",
      ('<h3 id="comeback-spread">Comeback underdog spread line</h3>' in t, "Any rung reached 2x" in t.split("Rung detail and how it is read")[0],
       "Rung detail and how it is read" in t), (True, True, True))

print("\nthe matchup board")
check("Teams and Ladder are collapsed by default", ("<details class=\"section-disclosure nba-teams\">" in page, "<details class=\"section-disclosure nba-ladder\">" in page), (True, True))

print("\nstyle rules")
top = page[page.find('<section id="glance"'):page.find('<section id="matchups"')]
check("no inline style or SVG in the top half (the NBA page forbids both)", ("style=" in top, "<svg" in top), (False, False))
check("public copy passes the guard", sandbox_audit.COPY_RE.search(top), None)

print("\n" + ("ALL PASS" if not FAILS else f"{len(FAILS)} FAILED"))
sys.exit(1 if FAILS else 0)
