#!/usr/bin/env python3
"""The promotion gate, enforced (2026-11-12, Olu): no lane is in Production without a passing honest record.

This test is the gate. It runs on every pull request, offline. A promotion is a code change (PAIR_OVERRIDES, a feed module's
registry), so a pull request that promotes a lane fails here until data/promotion_gate.json holds that lane's passing record."""
import glob
import os
import sys

import fillsim as F
import promotion_gate as PG

FAILS = []


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


def rec(roi=0.12, n=40, evidence=True, waiver=None, rules=F.VERSION):
    checks = {"30+ bets": evidence, "10+ outcomes": True, "both halves up": True, "up without its best outcome": True, "t of 2+": evidence}
    return dict(rules=rules, honest=dict(n=n, roi=roi, outcomes=12, t=2.4), honest_positive=bool(n and roi > 0), checks=checks,
                evidence=all(checks.values()), waiver=waiver)


print("THE GATE: every lane the code puts in Production has a passing record, or was live before the gate")
bad = PG.verify()
for key, why in bad:
    print(f"  REFUSED {key}: {why}")
check("no lane is in Production without its record", bad, [])
live = PG.production_lanes()
check("the code's Production list is read", len(live) >= 1, True)
check("no Production feed or module goes around the gate", PG.unknown_feeds(), [])

print("the rule")
check("no record: refused", PG.verdict(None)[0], False)
check("positive honest return and the evidence test: passes", PG.verdict(rec()), (True, []))
check("a negative honest return is refused", PG.verdict(rec(roi=-0.03))[0], False)
check("a zero honest return is refused", PG.verdict(rec(roi=0.0))[0], False)
check("no surviving entry is refused", PG.verdict(rec(n=0))[0], False)
check("positive but thin evidence is refused", PG.verdict(rec(evidence=False))[0], False)
waiver = dict(by="Olu", on="2026-11-20", why="small stake trial")
check("... unless Olu's waiver is on the record", PG.verdict(rec(evidence=False, waiver=waiver))[0], True)
check("... a waiver with no reason is not a waiver", PG.verdict(rec(evidence=False, waiver=dict(by="Olu", on="2026-11-20", why="")))[0], False)
check("NOTHING waives a return that is not positive", PG.verdict(rec(roi=-0.03, evidence=False, waiver=waiver))[0], False)
check("a record graded under another rule set is refused", PG.verdict(rec(rules="page"))[0], False)

print("a promotion without a record fails; with one it passes")
blob = dict(lanes={})
new = dict(live, **{"new_rule|soccer_o25": "a new lane"})
got = PG.verify(blob, new, feeds=[])
check("a newly promoted lane with no record is refused", [k for k, _w in got], ["new_rule|soccer_o25"])
check("... with a failing record too", [k for k, _w in PG.verify(dict(lanes={"new_rule|soccer_o25": rec(roi=-0.2)}), new, feeds=[])],
      ["new_rule|soccer_o25"])
check("... and passes with a passing one", PG.verify(dict(lanes={"new_rule|soccer_o25": rec()}), new, feeds=[]), [])
check("a grandfathered lane is not refused for its figure", PG.verify(dict(lanes={}), {k: live[k] for k in live if k in PG.GRANDFATHERED}, feeds=[]), [])
check("an unknown Production feed is refused", [k for k, _w in PG.verify(blob, {}, feeds=["production_new_leads.json"])], ["production_new_leads.json"])
check("a lane that has left Production needs nothing", PG.verify(blob, {}, feeds=[]), [])

print("the record")
blob = PG.load()
check("the record names its rule set", blob.get("rules"), F.VERSION)
missing = sorted(k for k in live if k not in blob["lanes"])
check("every lane now in Production has its honest figure on record", missing, [])
check("each record carries the honest figure, the page figure, the checks and the touch note",
      all({"honest", "page", "checks", "note_touch", "honest_positive", "waiver"} <= set(r) for r in blob["lanes"].values()), True)
check("the gate reads the strict figure, never the touch note", "note_touch" in PG.verdict.__code__.co_names + PG.verdict.__code__.co_consts, False)

print("grading")
check("a tracker rule, a rule-ledger lane, a daily lane and an own-engine lane can all be graded",
      [PG.grader(k) is not None for k in ("team2_ranked|soccer_team2", "sr_a7|soccer_u35", "econ_nc_yes|econ_daily", "nba_wm_nofade")], [True] * 4)
check("a name nothing knows cannot", PG.grader("nothing_here"), None)
g = PG.grade("sr_c3|soccer_o25", lambda tk: [])
check("with no prints at all a logged quote still counts, unconfirmed", (g["honest"]["n"] > 0, g["honest"]["confirmed"]), (True, 0))
check("its figure after the exchange's fee is the gate's figure", g["honest_positive"], g["honest"]["roi"] > 0)

print("pages do not read the gate record")
root = os.path.dirname(os.path.abspath(__file__))
readers = sorted(os.path.basename(p) for p in glob.glob(os.path.join(root, "*.py"))
                 if os.path.basename(p) not in ("promotion_gate.py", "test_promotion_gate.py") and "promotion_gate" in open(p).read())
check("no page builder or other module imports it", readers, [])

print()
if FAILS:
    print(f"{len(FAILS)} FAILED: " + "; ".join(FAILS))
    sys.exit(1)
print("the promotion gate holds")
