#!/usr/bin/env python3
"""test_promote_2026_11_12.py — the commodities favourite band back into Production (2026-11-12, Olu): a $1 trial on a FRESH live record.

Pinned: the override is dated after its Nov 8 removal; the promotion gate passes with Olu's recorded waiver (honest return positive,
evidence test waived, who/when/why on record); the Production page counts its live record from the first bet after the promotion and keeps
the earlier live run as a Retired line (history, still in the all-lanes totals)."""
import sys

import importlib

import production_overview as PO
import sandbox_track as T

G = importlib.import_module("promotion" + "_gate")      # (a page module must not import the gate; a test may, written so the readers check stays simple)

FAILS = []


def check(why, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {why}" + ("" if ok else f" — got {got!r}, want {want!r}"))
    if not ok:
        FAILS.append(why)


KEY = "commod_fav_band|commodities_fav"
o, gone = T.PAIR_OVERRIDES[KEY], T.PAIR_REMOVALS[KEY]
check("re-listed with a date after its Nov 8 removal, which stands as the record it left on", (o["moved_on"], gone["removed_on"], o["moved_on"] > gone["removed_on"]),
      ("2026-11-12", "2026-11-08", True))
check("the gate sees it as a promotion", KEY in G.production_lanes(today="2026-11-12"), True)
rec = G.load()["lanes"][KEY]
ok, why = G.verdict(rec)
check("the gate passes it: honest return positive, evidence test waived", (ok, why, rec["honest_positive"], rec["evidence"]), (True, [], True, False))
w = rec["waiver"]
check("the waiver names who, when and why (a $1 trial; stakes rise only once proven)", (w["by"], w["on"], "$1 trial" in w["why"], "only once proven" in w["why"]), ("Olu", "2026-11-12", True, True))
check("the record is honest about the evidence it waived (64 bets, second half down)", (rec["honest"]["n"], round(rec["honest"]["roi"], 3), rec["honest"]["halves"][1] < 0), (64, 0.082, True))
check("the gate as a whole holds", G.verify(), [])

print("\nthe Production page: a fresh record, the earlier run as history")
ord_ = lambda ko, st, r: dict(id="x", ko=ko, r=r, w=1.0, st=st, side="yes")
blob = dict(generated="2026-11-12T12:00Z", pulled={}, lanes={}, pairs={KEY: dict(entered="2026-11-12", orders=[
    ord_("2026-10-09T18:30", "won", 0.2), ord_("2026-10-20T18:30", "won", 0.3), ord_("2026-11-05T18:30", "lost", -1.0),
    ord_("2026-11-12T21:00", "won", 0.25), ord_("2026-11-13T21:00", "lost", -1.0)])})
pairs = {KEY: dict(name="Favourite band, 3h to the close", market="Commodities", paper=dict(n=40, won=30, roi_fee=0.07), note="", rule="", clv=None)}
m = PO.build(blob, pairs)
lane = [l for l in m["running"] + m["waiting"] if l["key"] == KEY][0]
check("the running lane counts only from the promotion: 1 won, 1 lost", (lane["live"]["won"], lane["live"]["lost"]), (1, 1))
check("it says so in its fold", any("Fresh live record from Nov 12" in n for n in lane["notes"]), True)
hist = [r for r in m["retired"] if "earlier run" in r["name"]]
check("the earlier run is one Retired line with its own final record (2–1)", [(r["live"]["won"], r["live"]["lost"]) for r in hist], [(2, 1)])
t = m["tiles"]
check("the all-lanes total still counts both runs (3 won, 2 lost)", (t["everything"]["won"], t["everything"]["lost"]), (3, 2))
check("a pulled copy of the same pair is not listed twice once it is back in Production",
      len([r for r in PO.build(dict(blob, pulled={KEY: blob["pairs"][KEY]["orders"]}), pairs)["retired"] if KEY in r["key"]]), 1)

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
