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
# The committed stage file is rewritten by every tracker run, so the pull-back lives in code (T.apply_removals, read through T.load_stages) and is proved
# here on STALE data: a stage file that still says Production for the three pairs, written to a temp path.
import tempfile

STALE_PAIRS = PAIRS
stale = {"pairs": {k: dict(stage="production", promoted_at="2026-10-11T00:00:00+00:00", entry_since="2026-10-11T00:00:00+00:00", by_hand="2026-10-11",
                           ready_since="2026-10-11T00:00:00+00:00", ready_at="2026-10-11T00:00:00+00:00") for k in STALE_PAIRS}, "events": []}
with tempfile.TemporaryDirectory() as tmp:
    path = os.path.join(tmp, "stages.json")
    json.dump(stale, open(path, "w"))
    st = T.load_stages(path)
    check("read with stale data, the two pairs are Sandbox pairs, record kept, demoted on the removal day",
          [(k, st["pairs"][k]["stage"], st["pairs"][k]["demoted_at"][:10], st["pairs"][k]["since"]) for k in PAIRS],
          [(k, "sandbox", "2026-11-25", "2026-10-11T00:00:00+00:00") for k in PAIRS])
    check("one event each, with the reason evaluate_stages gives", sorted((e["pair"], e["to"], e["reason"]) for e in st["events"] if e["pair"] in PAIRS),
          sorted((k, "sandbox", "taken off the Production list by hand, record kept") for k in PAIRS))
    check("applying it again changes nothing", T.apply_removals(st), [])
    check("a pair still on the live list is left alone", T.apply_removals({"pairs": {"o15_ranked|soccer_o15_intl": dict(stage="production")}, "events": []}), [])
    import production as P
    check("production_pairs (what prune_feed keeps) no longer names them", [k for k in PAIRS if k in P.production_pairs(st)], [])
    dump = os.path.join(tmp, "dump.json")
    T.save_stages(st, dump)
    check("evaluate_stages on the read stage file has nothing left to demote", [c["pair"] for c in T.evaluate_stages({"quotes": []}, T.load_stages(dump), verbose=False)
                                                                           if c.get("to") == "sandbox" and c["pair"] in PAIRS], [])
print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
raise SystemExit(1 if FAILS else 0)
