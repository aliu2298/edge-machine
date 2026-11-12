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
check("commodities band: its Nov 8 removal stands as the record it left on, and it is re-listed 2026-11-12 (later), so it is a new promotion",
      T.PAIR_REMOVALS[K] == dict(removed_on="2026-11-08", keep_record=True) and T.PAIR_OVERRIDES[K]["moved_on"] == "2026-11-12")
check("top-5 dip: back in the Sandbox 2026-11-08 and back in Production 2026-11-12 (test_top5_dip_production.py), its first run kept as history",
      TD.ENDED_ON == "" and TD.FIRST_RUN == ("2026-11-05", "2026-11-08") and TD.MOVED_ON == "2026-11-12")

blob = dict(generated="x", pairs={}, pulled={K: [dict(id="q1", ko="2026-11-02T18:00", side="yes", st="won", w=1.0, r=0.3),
                                                    dict(id="q2", ko="2026-11-03T18:00", side="yes", st="lost", w=1.0, r=-1.0)]},
            lanes={"top5_dip": [dict(id="a", ko="2026-11-06T15:00", side="yes", st="won", w=1.0, r=0.4, legs="", src="fills")],
                   "o35_cheap_no": [dict(id="b", ko="2026-11-04T15:00", side="no", st="lost", w=1.0, r=-1.0, legs="", src="fills")]})
html = PL.pulled_table(blob, lambda p: "Commodities favourite band")
check("commodities band: its live fills stay listed as history", "Commodities favourite band" in html and "1–1" in html)
lanes = PL.lanes_table(blob)
check("the cheap NO says when it went back; the top-5 dip's first run is its own earlier-run line, its fresh record from Nov 12",
      "back in the Sandbox Nov 6" in lanes and "Top-5 goalless dip · earlier run" in lanes and "Top-5 goalless dip · from Nov 12" not in lanes)
check("public copy: no dollar amount", "$" not in html and "$" not in lanes)

raise SystemExit(1 if fails else print("PASS back to the Sandbox 2026-11-08") or 0)
