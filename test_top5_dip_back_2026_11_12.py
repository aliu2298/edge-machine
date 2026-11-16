#!/usr/bin/env python3
"""2026-11-12 (Olu: "return it back to production ... top 5 goalless dip"): the dip was a Production lane again, live at the default stake, on a FRESH
live record; its first run (2026-11-05 to 2026-11-08) stays as a Retired line. 2026-11-16 (Olu): out of Production again (12 fills, -9.2%; the Sandbox research row
z 0.05, newer half +0.3%); the 2026-11-12 record is a second history line and the 100-fill read continues on paper. Offline."""
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


check("the lane has ended 2026-11-16: moved 2026-11-12, first run kept", TD.ENDED_ON == "2026-11-16" and TD.MOVED_ON == "2026-11-12" and TD.FIRST_RUN == ("2026-11-05", "2026-11-08"))
check("no Production pair", TD.pairs() == {})
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
check("overview: when the lane's pair is still passed in, only the fresh bet counts as running (the real build passes none once it has ended)", len(run) == 1 and run[0]["live"]["n"] == 1)
m_ended = PO.build(blob, {})
check("overview: with the pair gone, nothing runs; the Nov 12 record and the first run are two Retired lines that add up to all three bets",
      not [l for l in m_ended["running"] if l["key"] == "top5_dip"]
      and sorted(r["live"]["n"] for r in m_ended["retired"] if r["key"].startswith("top5_dip")) == [1, 2] and m_ended["tiles"]["everything"]["n"] == 3)
hist = [r for r in m["retired"] if r["key"] == "top5_dip#first-run"]
check("overview: the first run (2 bets) is a Retired line named as the earlier run", len(hist) == 1 and hist[0]["live"]["n"] == 2 and "earlier run" in hist[0]["name"])
check("overview: the all-lanes total still counts all three", m["tiles"]["everything"]["n"] == 3)
lanes = PL.lanes_table(blob)
check("the own-state table has the earlier run and the Nov 12 record as two lines, the second saying it went back Nov 16",
      "Top-5 goalless dip · earlier run" in lanes and "Top-5 goalless dip · from Nov 12 · back in the Sandbox Nov 16" in lanes)
import top5_dip_production as _X
html = SL.top5_live_row({}, None)
check("the closed row carries Olu's history line, percentages only", "Out of Production Nov 16 (Olu): Sandbox research row z 0.05, newer half +0.3%; the 100-fill read continues on paper."
      in html["own"]["details"] and "$" not in html["own"]["details"])
check("public copy: no dollar amount", "$" not in lanes)
print(f"\n{'ALL PASS' if not fails else str(len(fails)) + ' FAILED'}")
raise SystemExit(1 if fails else 0)
