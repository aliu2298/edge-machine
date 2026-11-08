#!/usr/bin/env python3
"""2026-11-08 (Olu): the commodities favourite band and the top-5 goalless dip are back in the Sandbox; over 3.5 cheap NO already was (2026-11-06).
Their records stay, the feeds name nothing for them, and their live fills stay on the Production page as history. No network."""
import json

import production as P
import production_live as PL
import sandbox_track as T
import top5_dip_production as TD

fails = []


def check(name, ok):
    print(("  ok   " if ok else "  FAIL ") + name)
    if not ok:
        fails.append(name)


K = "commod_fav_band|commodities_fav"
check("commodities band: off the live list, record kept", K not in T.PAIR_OVERRIDES and T.PAIR_REMOVALS[K] == dict(removed_on="2026-11-08", keep_record=True))
st = json.load(open("data/stages.json"))
check("commodities band: the committed stage is the Sandbox, with the date it left", st["pairs"][K]["stage"] == "sandbox" and st["pairs"][K].get("demoted_at"))
feed = json.load(open("data/production_leads.json"))
check("commodities band: the Production feed names no lead or pair for it", not any(l.get("pair") == K for l in feed["leads"].values()) and K not in feed["pairs"])
dip = json.load(open("data/production_top5_dip_leads.json"))
check("top-5 dip: its feed is valid and names no match", dip["lane"] == TD.LANE and dip["leads"] == [] and dip["ended_on"] == "2026-11-08")
check("top-5 dip: no Production pair", TD.pairs() == {})

blob = dict(generated="x", pairs={}, pulled={K: [dict(id="q1", ko="2026-11-02T18:00", side="yes", st="won", w=1.0, r=0.3),
                                                    dict(id="q2", ko="2026-11-03T18:00", side="yes", st="lost", w=1.0, r=-1.0)]},
            lanes={"top5_dip": [dict(id="a", ko="2026-11-06T15:00", side="yes", st="won", w=1.0, r=0.4, legs="", src="fills")],
                   "o35_cheap_no": [dict(id="b", ko="2026-11-04T15:00", side="no", st="lost", w=1.0, r=-1.0, legs="", src="fills")]})
html = PL.pulled_table(blob, lambda p: "Commodities favourite band")
check("commodities band: its live fills stay listed as history", "Commodities favourite band" in html and "1–1" in html)
lanes = PL.lanes_table(blob)
check("the two ended own-state lanes say when they went back", "back in the Sandbox Nov 8" in lanes and "back in the Sandbox Nov 6" in lanes)
check("public copy: no dollar amount", "$" not in html and "$" not in lanes)

raise SystemExit(1 if fails else print("PASS back to the Sandbox 2026-11-08") or 0)
