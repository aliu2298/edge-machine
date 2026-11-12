#!/usr/bin/env python3
"""Offline checks for fdr_check.py: the maths against known values, the guards against a too-good t, and a run over the committed ledgers."""
import math
import sys

import fdr_check as F

FAILS = []


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


def near(label, got, want, tol):
    ok = got is not None and abs(got - want) <= tol
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


print("Student t and the normal tail, against table values")
near("t 2.228 on 10 df is the 2.5% point", F.t_sf(2.228, 10), 0.025, 2e-4)
near("t 2.0 on 4 df", F.t_sf(2.0, 4), 0.0581, 2e-4)
near("t 12.706 on 1 df", F.t_sf(12.706, 1), 0.025, 2e-4)
near("symmetric", F.t_sf(-1.5, 7) + F.t_sf(1.5, 7), 1.0, 1e-9)
near("a t on many df is the normal", F.t_sf(1.96, 5000), F.norm_sf(1.96), 2e-4)
near("normal 2.0", F.norm_sf(2.0), 0.02275, 1e-5)

print("Benjamini-Hochberg")
q = F.bh([0.01, 0.04, 0.03, 0.5])
near("smallest p x m", q[0], 0.04, 1e-12)
near("monotone from the top", q[1], 0.04 * 4 / 3, 1e-12)
near("... and never above a larger p's q", q[2], 0.04 * 4 / 3, 1e-12)
near("largest", q[3], 0.5, 1e-12)
check("order kept", sorted(range(4), key=lambda i: q[i])[0], 0)

print("one lane's read")
fav = [(0.075, f"d{i}") for i in range(15)]                       # 15 wins of 15 at about 93c
s = F.lane_stats(fav)
near("a favourites lane that has not lost yet is not a 9-sigma find", s["t"], 0.075 / math.sqrt(0.075 / 15), 0.02)
check("... its t is near 1", 0.9 < s["t"] < 1.2, True)
one_day = [(1.0, "d1")] * 8 + [(-1.0, "d2")] * 2 + [(-1.0, "d3")] * 2
s = F.lane_stats(one_day)
plain = (4 / 12) / math.sqrt(sum((v - 4 / 12) ** 2 for v, _ in one_day) / 11 / 12)
check("eight wins on one day are one outcome: the clustered t is under the plain one", s["t"] < round(plain, 2), True)
check("its best outcome carries it", (s["without_best"], s["halves"][0] > 0, s["halves"][1] < 0), (-1.0, True, True))
check("under 10 bets or 3 outcomes is not tested", (F.lane_stats(fav[:9])["tested"], F.lane_stats([(1.0, "a")] * 12)["tested"]), (False, False))
check("an empty lane", F.lane_stats([])["n"], 0)
near("fair spread = the mean size of a win", F.fair_var([(0.5, "a"), (1.5, "b"), (-1.0, "c")]), 1.0, 1e-12)

print("the shuffled Sandbox")
recs = [dict(vals=[((1.0 if (i * 7 + k) % 3 else -1.0), f"d{i}") for i in range(12)]) for k in range(20)]
null = F.max_t_null(recs, draws=300, seed=1)
check("the same seed gives the same null", null, F.max_t_null(recs, draws=300, seed=1))
check("sorted", null, sorted(null))
check("the best of 20 fair lanes is usually above 1", null[len(null) // 2] > 1.0, True)
near("adj p of an impossible t", F.adj_p(99.0, null), 1 / 301, 1e-9)
check("adj p of a low t is 1", F.adj_p(-99.0, null), 1.0)

print("families, power, gate")
check("a tipster is its own family", F.family_of("sandbox", "covers", "mlb", True), "Tipsters and outside models")
check("crypto bands", F.family_of("sandbox", "crypto_fav_band_below", "crypto_fav"), "Crypto price bands")
check("a soccer tracker rule", F.family_of("sandbox", "team2_ranked", "soccer_team2"), "Soccer form and price rules (tracker)")
check("soccer label rules", F.family_of("soccer_rules_ledger.json", "A7", None), "Soccer total-goals label rules")
check("NBA win margin", F.family_of("fillsim", "nba_wm_nofade", None), "NBA win margin")
check("the dips", F.family_of("fillsim", "top5_dip", None), "Goalless dips and cheap NO (soccer in-play)")
near("no edge shows z 2 one time in 44", F.power(0.0, 1.0, 30), 0.02275, 1e-5)
check("a real 10% edge rarely shows at 30 bets", F.power(0.10, 0.87, 30) < 0.12, True)
check("... and needs hundreds", 500 < F.bets_needed(0.10, 0.87) < 700, True)
good = [((1.2 if i % 3 else -1.0), f"2026-10-{i + 1:02d}") for i in range(30)] + [(1.2, f"2026-11-{i + 1:02d}") for i in range(6)]
g = F.gate(F.lane_stats(good))
check("36 bets on 36 days, up in both halves and without its best day, t over 2: passes step 1", (all(g.values()), len(g)), (True, 5))
check("outcomes sort by date, not by text (26OCT26 is before 26NOV16)", sorted(["KXTRUMPSAY-26NOV16", "KXTRUMPSAY-26OCT26"], key=F.when),
      ["KXTRUMPSAY-26OCT26", "KXTRUMPSAY-26NOV16"])
check("step 1 names what fails", [k for k, v in F.gate(F.lane_stats(fav)).items() if not v], ["30+ bets", "t of 2+"])

print("a run over the committed ledgers (no network)")
out = F.run(draws=200)
check("lanes found", out["lanes"] > 100, True)
check("every tested lane has p, q and adj p", all(r["p"] is not None and 0 <= r["q"] <= 1 and 0 < r["adj_p"] <= 1 for r in out["records"] if r["tested"]), True)
check("no lane shows a t above 6 (the too-good guard)", max(r["t"] for r in out["records"] if r["tested"]) < 6, True)
check("every lane has a family", all(r["family"] for r in out["records"]), True)
check("family lane counts add up", sum(f["lanes"] for f in out["families"].values()), out["lanes"])
check("the live records are read", len(out["live"]) > 10, True)
check("promotion shrinkage has rows", len(out["shrinkage"]) > 3, True)
check("the report prints", "Benjamini-Hochberg" in F.report(out), True)
honest = F.run(regrade={"lanes": {"top5_dip": {"label": "x", "exit": "sell", "retired": False, "live_lane": None,
                                               "rows": [{"cluster": f"d{i}", "honest": 0.1, "honest_hold": -1.0} for i in range(12)]}}}, draws=50)
r = next(r for r in honest["records"] if r["lane"] == "top5_dip")
check("a re-graded lane is read at its honest figure", (r["basis"], r["n"], r["roi"], r["stage"]), ("honest", 12, 0.1, "Sandbox"))

print()
if FAILS:
    print(f"{len(FAILS)} FAILED: " + "; ".join(FAILS))
    sys.exit(1)
print("all fdr checks passed")
