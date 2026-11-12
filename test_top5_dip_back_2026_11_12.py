#!/usr/bin/env python3
"""2026-11-12 (Olu: "return it back to production ... top 5 goalless dip"): the dip is a Production lane again, live at the default stake, on a FRESH
live record; its first run (2026-11-05 to 2026-11-08) stays as a Retired line. Offline."""
import json

import production_live as PL
import production_overview as PO
import promotion_gate as PG
import soccer_lanes as SL
import top5_dip_production as TD

fails = []


def check(name, ok):
    print(("  ok   " if ok else "  FAIL ") + name)
    if not ok:
        fails.append(name)


check("the lane is running: no end date, moved 2026-11-12, first run kept", TD.ENDED_ON == "" and TD.MOVED_ON == "2026-11-12" and TD.FIRST_RUN == ("2026-11-05", "2026-11-08"))
check("one Production pair, at the default stake", list(TD.pairs()) == ["top5_goalless_dip_live|soccer_o15"] and TD.STAKE_USD == 1.0)
gate = json.load(open("data/promotion_gate.json"))["lanes"]
for k in ("top5_dip", "top5_goalless_dip_live"):
    w = gate[k]["waiver"]
    check(f"{k}: Olu's waiver on the evidence test, dated 2026-11-12, honest return positive", w["by"] == "Olu" and w["on"] == "2026-11-12" and gate[k]["honest_positive"])

rows = [dict(id="a", ko="2026-11-06T15:00", side="yes", st="won", w=1.0, r=0.8, legs="", src="fills"),
        dict(id="b", ko="2026-11-07T15:00", side="yes", st="lost", w=1.0, r=-1.0, legs="", src="fills"),
        dict(id="c", ko="2026-11-21T15:00", side="yes", st="won", w=1.0, r=0.8, legs="", src="fills")]
blob = dict(generated="x", pairs={}, pulled={}, lanes={"top5_dip": rows})
check("production_live reads only the fresh rows for the pair", [r["id"] for r in PL.own_rows(blob, "top5_goalless_dip_live|soccer_o15")] == ["c"])
pairs = {"top5_goalless_dip_live|soccer_o15": dict(name="Top-5 goalless dip (live)", market="Over 1.5", paper=dict(n=0, won=0, roi_fee=None), note="", clv=None, rule="")}
m = PO.build(blob, pairs)
run = [l for l in m["running"] if l["key"] == "top5_dip"]
check("overview: the running lane counts only the fresh bet", len(run) == 1 and run[0]["live"]["n"] == 1)
hist = [r for r in m["retired"] if r["key"] == "top5_dip#first-run"]
check("overview: the first run (2 bets) is a Retired line named as the earlier run", len(hist) == 1 and hist[0]["live"]["n"] == 2 and "earlier run" in hist[0]["name"])
check("overview: the all-lanes total still counts all three", m["tiles"]["everything"]["n"] == 3)
lanes = PL.lanes_table(blob)
check("the own-state table has the earlier run and the fresh record as two lines", "Top-5 goalless dip · earlier run" in lanes and "Top-5 goalless dip · from Nov 12" in lanes)
check("public copy: no dollar amount", "$" not in lanes)
print(f"\n{'ALL PASS' if not fails else str(len(fails)) + ' FAILED'}")
raise SystemExit(1 if fails else 0)
