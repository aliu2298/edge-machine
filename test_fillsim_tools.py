#!/usr/bin/env python3
"""Offline checks for the fillsim tools: the re-grade adapters read every committed ledger, the calibration scoring, the paid-price maths.
No network: the tape is a stub."""
import sys

import fillsim as F
import fillsim_calibrate as C
import fillsim_paid as P
import fillsim_regrade as G

FAILS = []


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


print("re-grade: every adapter reads its committed ledger (an empty tape: nothing can fill)")
log = []
out = G.run(tape=lambda tk: [], log=log.append, result=lambda tk: "no")
check("no lane failed", [n for n, L in out["lanes"].items() if "error" in L], [])
check("every registered lane ran", sorted(out["lanes"]), sorted(G.lanes()))
check("an empty tape fills no resting bid", sum(out["lanes"][n]["summary"]["honest"]["n"] for n in
                                                 ("o35_cheap_no_v4", "o35_cheap_no_v5", "nba_wm_nofade", "top5_dip", "arg_dip", "mentions_dip_hold")), 0)
check("the rule set is named in the output", out["rules"], "honest-v1")
dropped = out["lanes"]["o35_cheap_no_v4"]["summary"]["dropped"]
check("page fills the simulator refuses are counted with a reason", dropped["n"] > 0 and set(dropped["why"]) == {"the price never reached the bid"}, True)
check("the live column is read where the lane traded live", out["lanes"]["o35_cheap_no_v4"]["summary"]["live"]["n"] > 0, True)

print("re-grade: one entry end to end on a stub tape")
import o35_cheap_no as O
e = next(x for x in G.load("o35_cheap_no_ledger")["entries"] if x.get("version") == O.VERSION and x["result"] == "yes")
t0 = e["kickoff"] + O.BID_AFTER_MIN * 60
tape = {e["id"]: [(t0 - 60.0, 0.80, 5.0, "yes"), (t0 + 600.0, 0.92, 30.0, "yes"), (t0 + 620.0, 0.55, 30.0, "no"), (t0 + 640.0, 0.91, 5.0, "yes"),
                  (t0 + 900.0, 0.55, 30.0, "no")]}
rows = [r for r in G.o35_lane(lambda tk: tape.get(tk, []), "v4") if r["key"] == e["id"]]
check("filled at 10c through an 8c print, sold at 40c only on the print 5 minutes later", (rows[0]["status"], rows[0]["honest"], rows[0]["legs"]),
      ("settled", 3.0, [(0.4, "filled")]))
rows = [r for r in G.o35_lane(lambda tk: tape.get(tk, [])[:4], "v4") if r["key"] == e["id"]]
check("with only the print 20 seconds after the fill it is held, and lost", (rows[0]["honest"], rows[0]["legs"]), (-1.0, [(0.4, "unfilled")]))

print("stats")
s = G.stats([(1.0, "a"), (1.0, "a"), (-1.0, "b"), (-1.0, "c"), (1.0, "d")])
check("mean", (s["n"], s["roi"], s["clusters"]), (5, 0.2, 4))
check("z is never above the plain z when a cluster moves together", s["z"] <= round(0.2 / ((sum((v - 0.2) ** 2 for v in (1, 1, -1, -1, 1)) / 4) ** 0.5 / 5 ** 0.5), 2), True)
check("no z under 3 clusters", G.stats([(1.0, "a"), (0.5, "b")])["z"], None)
check("empty", G.stats([])["n"], 0)

print("calibration scoring")
cases = [dict(live=True), dict(live=True), dict(live=False), dict(live=False)]
sc = C.score(cases, lambda c: c is cases[0] or c is cases[2])
check("hit rate, over and under", (sc["n"], sc["hit"], sc["over"], sc["under"], sc["sim"], sc["live"]), (4, 0.5, 1, 1, 2, 2))
check("the split is fixed by the ticker", (C.half("KXA-1"), C.half("KXA-1")) in (("A", "A"), ("B", "B")), True)
table = [("loose", {"A": {"hit": 0.9}}), ("strict", {"A": {"hit": 0.9}}), ("bad", {"A": {"hit": 0.5}})]
check("a tie goes to the stricter variant (the later one)", C.pick(table)[0], "strict")

print("paid price")
for px in (0.12, 0.50, 0.77, 0.93):
    ret = 1.0 / (px + F.fee(px)) - 1
    check(f"a win bought at {px:.2f} reads back as {px:.2f}", round(P.paid_price(ret), 2), px)
check("a paper entry is found by its bet id", P.paper_for({"id": "x:KXA"}, {"x:KXA": {"price": 0.5}}, {})["price"], 0.5)
check("... or by its ticker and rule", P.paper_for({"id": "sr_a7:KXA"}, {}, {"KXA": [{"price": 0.4, "rule": "A7"}, {"price": 0.6, "rule": "C1"}]})["price"], 0.4)
check("... and not guessed when two entries share the ticker", P.paper_for({"id": "zz:KXA"}, {}, {"KXA": [{"price": 0.4}, {"price": 0.6}]}), None)

print()
if FAILS:
    print(f"{len(FAILS)} FAILED: " + "; ".join(FAILS))
    sys.exit(1)
print("all fillsim tool checks passed")
