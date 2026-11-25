#!/usr/bin/env python3
"""Three Production lanes back to the Sandbox on 2026-11-25 (Olu): the UCL either team O+D- over 3.5 (A7), Clubs team 2+ ranked by margin, first to
score NO 0.70-0.80. Paper keeps running; the Production list and the Production feeds no longer name them."""
import json

import sandbox_track as T
import soccer_rules_production as RP

FAILS = []


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


PAIRS = ("team2_ranked|soccer_team2", "ftts_no_70_80|soccer_ftts")
check("the two pairs are off the Production list and keep their whole record", [(k in T.PAIR_OVERRIDES, T.PAIR_REMOVALS[k]) for k in PAIRS],
      [(False, dict(removed_on="2026-11-25", keep_record=True))] * 2)
check("A7 is out of the soccer rules adapter's pairs and listed as pulled", ("A7" in RP.PAIRS, RP.PULLED["A7"]), (False, ("2026-10-21", "2026-11-25")))
# The stage table and the feeds are rebuilt by the tracker's next run (it prunes the feed first); the stage change is replayed here in memory so
# this check does not depend on which run last wrote the committed data.
_st = json.loads(json.dumps(T.load_stages()))
T.evaluate_stages(T.load(), _st, verbose=False)
check("evaluated, none of the three is a Production pair", [k for k, v in _st["pairs"].items() if v.get("stage") == "production" and k in PAIRS], [])
print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
raise SystemExit(1 if FAILS else 0)
