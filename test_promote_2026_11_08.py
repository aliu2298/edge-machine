#!/usr/bin/env python3
"""2026-11-08 (Olu: "promote all four"): T1-H, T1-M and the Champions League corners fade go to Production at the default stake, on fresh
records; the Argentina goalless dip follows with its own executor. Offline."""
import json

import sandbox_track as T
import soccer_team_rules as TR
import soccer_team_rules_production as TRP

fails = []


def check(name, ok):
    print(("  ok   " if ok else "  FAIL ") + name)
    if not ok:
        fails.append(name)


check("T1-H and T1-M are team-rule Production pairs: the home 2+ claim and the match over 3.5 YES",
      (TRP.PAIRS["T1H"][:2], TRP.PAIRS["T1M"][:2]) == (("st_t1h", "soccer_team2"), ("st_t1m", "soccer_u35")))
check("their promotion is dated 2026-11-08, later than T1's own return to the Sandbox", TRP.MOVED["T1H"] == TRP.MOVED["T1M"] == "2026-11-08")
p = TRP.pairs()
check("each is a production stage by hand", all(p[f"{TRP.PAIRS[k][0]}|{TRP.PAIRS[k][1]}"]["stage"] == "production" for k in ("T1H", "T1M")))
st = TR.load()
q = TRP.quotes(st)
check("their entries publish on T1's five leagues only, one source each",
      {x["source"] for x in q if x["rule"] in ("T1H", "T1M")} <= {"st_t1h", "st_t1m"}
      and all(x["league"] in TR.RULES["T1"]["leagues"] for x in q if x["rule"] in ("T1H", "T1M")))
t1m = [x for x in q if x["rule"] == "T1M"]
check("T1-M names the match's over 3.5 contract, the Yes (pick a)", all(x["kalshi_title"] == "Over 3.5 goals scored" and x["pick"] == "a" and x["market_id"].endswith("-4") for x in t1m))
f = TRP.feed(st)
check("the feed's band for both is the rule's 3-97c", f["bands"]["st_t1h|soccer_team2"] == f["bands"]["st_t1m|soccer_u35"] == [0.03, 0.97])

K = "corners_ucl_fade|soccer_corners"
check("the corners fade is listed again with a date after its 2026-10-21 removal, the removal kept as its history",
      T.PAIR_OVERRIDES[K] == dict(moved_on="2026-11-08", production_at=None) and T.PAIR_REMOVALS[K]["removed_on"] == "2026-10-21")
raise SystemExit(1 if fails else print("PASS promotions 2026-11-08") or 0)
