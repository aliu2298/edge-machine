#!/usr/bin/env python3
"""Three Production lanes back to the Sandbox on 2026-11-25 (Olu): the UCL either team O+D- over 3.5 (A7), Clubs team 2+ ranked by margin, first to
score NO 0.70-0.80. Paper keeps running; the Production list and the Production feeds no longer name them."""
import json
import os

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
check("none of the three is in the stage table's Production pairs", [k for k, v in T.load_stages()["pairs"].items()
      if v.get("stage") == "production" and k in PAIRS + ("sr_a7|soccer_u35",)], [])
root = os.path.dirname(os.path.abspath(__file__))
feeds = ("production_leads.json", "soccer_rules_production_leads.json")
named = []
for f in feeds:
    blob = json.load(open(os.path.join(root, "data", f)))
    named += [(f, l.get("pair")) for l in (blob.get("leads") or {}).values() if l.get("pair") in PAIRS + ("sr_a7|soccer_u35",)]
check("no Production feed names any of the three", named, [])
print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
raise SystemExit(1 if FAILS else 0)
