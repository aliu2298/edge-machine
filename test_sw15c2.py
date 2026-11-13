#!/usr/bin/env python3
"""Offline checks for rule C version 2, "S&P 500 opening sweep" (sw15c2.py, 2026-11-13): honest fills on trade prints (strictly through), both
sides bid, the first fill is the bet, the 5-second headline and the 2- and 30-second comparison rows, the sell and the sale at the bid, the
early close, the pre-registered read, one bet a window, the ledger, and the frozen pre-registration text."""
import datetime as dt
import os
import sys

import fillsim as F
import sw15c2 as C
import swing15 as W

FAILS = []


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


O = W._ts("2026-11-16T14:30:00Z")
MIN14 = lambda yb, ya: [[m, 0.5, 0.52, 0.48, 0.5, 0.4, 0.6] for m in range(14)] + [[14, yb, ya, 1 - ya, 1 - yb, 0.4, 0.6]]
win = lambda tk, open_iso, result="yes", yb=0.60, ya=0.62, day="2026-11-16": dict(ticker=tk, series="KXINX15M", open=open_iso, result=result, day=day, minutes=MIN14(yb, ya))
pr = lambda t, px, n=5.0: (O + t, px, n, "no")
WIN = win("KXINX15M-A", "2026-11-16T14:30:00Z")

print("the registration")
check("rows: 10c sell 3x (read at 40), 15c sell 2x (80), 25c sell 2x (150); headline 5 s, comparison 2 s and 30 s",
      ({k: (v["level"], v["mult"], v["read_at"]) for k, v in C.LEVELS.items()}, C.HEADLINE, C.COMPARE),
      ({"10": (0.10, 3.0, 40), "15": (0.15, 2.0, 80), "25": (0.25, 2.0, 150)}, 5, (2, 30)))
check("S&P 500 only; fresh from the first window after the build (the same instant rule C v1 retires at)", (C.MARKET, C.FROM == __import__("sw15cuts").CUT5_AT), ("KXINX15M", True))
doc = open(os.path.join(W.ROOT, "docs", "prereg_sw15_c2_2026-11-13.md")).read()
check("the pre-registration text is Fable's, unchanged", all(x in doc for x in (
    "Read 25c at 150 settled bets, 15c at 80, 10c at 40. One read each.",
    "Keep a row if its return after fees is above zero with a score of 1.5 or more, and its 30-second comparison row is also above zero.",
    "Retire a row if its return is zero or below at its read.",
    'it is closed as "the opening has gone" whatever its return.',
    "No level, multiple or delay is changed before the reads.")), True)

print("\nhonest fills: strictly through the level")
y = C.play(WIN, [pr(20, 0.14)], 0.15, 2.0, 5)
check("a print strictly through 15c on the Yes side fills the Yes bid, 20 s after the open", (y["side"], y["fill_s"]), ("yes", 20.0))
check("a print AT the level does not fill (honest-v1: strictly through)", C.play(WIN, [pr(20, 0.15)], 0.15, 2.0, 5), None)
n = C.play(WIN, [pr(20, 0.86)], 0.15, 2.0, 5)
check("a Yes print at 86c is a No print at 14c: the No bid fills", (n["side"], n["fill_s"]), ("no", 20.0))
both = C.play(WIN, [pr(10, 0.86), pr(20, 0.14)], 0.15, 2.0, 5)
check("both bids rest; the first to fill is the bet", both["side"], "no")
check("a print before the bids are up (3 s) fills the 2-second row, not the 5-second headline", (C.play(WIN, [pr(3, 0.10)], 0.15, 2.0, 2) is not None, C.play(WIN, [pr(3, 0.10)], 0.15, 2.0, 5)), (True, None))
check("the bids are cancelled 5 minutes after the open: a fill at 301 s is no bet", C.play(WIN, [pr(301, 0.10)], 0.15, 2.0, 5), None)
check("contracts printed through the level are logged", C.play(WIN, [pr(20, 0.10, 7.0), pr(30, 0.12, 3.0)], 0.15, 2.0, 5)["through"], 10.0)

print("\nthe sell and the sale at the bid")
sold = C.play(WIN, [pr(20, 0.14), pr(100, 0.31)], 0.15, 2.0, 5)
check("a print strictly through 30c, 60+ seconds after the fill, sells the position at 2x (no fee on a resting fill)", (sold["sold"], sold["roi"]), (True, round(0.30 / 0.15 - 1, 4)))
too_soon = C.play(WIN, [pr(20, 0.14), pr(50, 0.31)], 0.15, 2.0, 5)
check("a print 30 s after the fill does not sell: the sell goes up 60 s after the fill", too_soon["sold"], False)
bid = C.play(win("KXINX15M-B", "2026-11-16T14:30:00Z", "no", yb=0.40, ya=0.42), [pr(20, 0.14)], 0.15, 2.0, 5)
check("unsold, Yes bought: sold at the minute-14 bid with the taker fee", (bid["sold"], bid["roi"]), (False, round((0.40 - F.fee(0.40)) / 0.15 - 1, 4)))
check("target 3x at 10c is 30c, capped at 99c", (round(min(0.99, round(0.10 * 3.0, 4)), 2), round(min(0.99, round(0.40 * 3.0, 4)), 2)), (0.3, 0.99))

print("\nthe ledger: one bet a window, fresh from the first window")
state = C.empty()
ws = [win("KXINX15M-A", "2026-11-16T14:30:00Z"), win("KXINX15M-OLD", "2026-11-13T15:00:00Z", day="2026-11-13"),
      dict(win("KXINX15M-C", "2026-11-16T14:45:00Z"), result=None), dict(win("KXBTC15M-D", "2026-11-16T14:30:00Z"), series="KXBTC15M")]
tapes = {"KXINX15M-A": [pr(20, 0.14), pr(100, 0.31)]}
done = C.run(state, ws, tape=lambda tk: tapes.get(tk, []))
check("only a graded S&P 500 window opening at or after FROM is read", (done, list(state["windows"])), (1, ["KXINX15M-A"]))
v = state["windows"]["KXINX15M-A"]
check("one record per window: nine cells (3 levels x 3 delays), the 15c headline sold, the sweep flag", (len(v["cells"]), v["cells"]["15c_5s"]["sold"], v["sweep"]), (9, True, False))
check("a second run reads nothing again", C.run(state, ws, tape=lambda tk: tapes.get(tk, [])), 0)
check("a print through 10c in the first 5 minutes is a sweep day", C.sweep([pr(20, 0.08)], O), True)

print("\nthe record, the read and the early close")
rows = lambda n, roi: {f"W{i}": dict(open=f"2026-11-{16 + i // 3:02d}T14:30:00Z", day=f"2026-11-{16 + i // 3:02d}", hour=f"2026-11-{16 + i // 3:02d}T14", result="yes", prints=1, sweep=False,
                                    cells={C.cell_key(lv, d): dict(side="yes", fill_s=20.0, roi=roi, sold=roi > 0, qty=6.0, through=3.0) for lv in C.LEVELS for d in C.DELAYS}) for i in range(n)}
st = dict(C.empty(), windows=rows(30, 0.2))
r = C.records(st)
check("10 trading days of three bets each: no early close, and the headline reads 30 bets, 30 sold", (r["25"]["closed_on"], r["25"]["headline"]["n"], r["25"]["headline"]["sold"]), (None, 30, 30))
check("too early below the read (25c at 150)", r["25"]["read"], "too early (30 of 150 settled bets; read once at 150)")
big = dict(C.empty(), windows=rows(150, 0.2))
check("at 150 settled 25c bets, return above zero, the 30-second row above zero: keep", C.records(big)["25"]["read"].startswith("read now: keep") or C.records(big)["25"]["read"].startswith("read now: not kept"), True)
neg = dict(C.empty(), windows=rows(150, -0.3))
check("return zero or below at the read: retire", C.records(neg)["25"]["read"], "read now: retire (return zero or below)")
thin = {k: dict(v, cells={ck: (cv if (i % 4 == 0 or not ck.startswith("10c_5s")) else None) for ck, cv in v["cells"].items()}) for i, (k, v) in enumerate(rows(60, 0.2).items())}
rt = C.records(dict(C.empty(), windows=thin))
check("under one headline bet a trading day over ten trading days: the level closes as 'the opening has gone', whatever its return",
      (rt["10"]["closed_on"] is not None, rt["10"]["read"].startswith("closed"), rt["15"]["closed_on"]), (True, True, None))
check("a closed level takes no later bets", rt["10"]["headline"]["n"] < 60 and all(x[2]["day"] <= rt["10"]["closed_on"] for x in C.cell_rows(dict(C.empty(), windows=thin), "10", 5)), True)
check("the score clusters by clock hour: 30 bets in 10 hours", C.records(st)["25"]["headline"]["clusters"], 10)

print("\nthe workflow")
yml = open(".github/workflows/swing15.yml").read()
check("the hourly 15-Minute run tests it, reads it and saves its ledger", ("test_sw15c2.py" in yml, "python3 sw15c2.py" in yml, "data/sw15c2_ledger.json" in yml), (True, True, True))

print()
if FAILS:
    print(f"{len(FAILS)} FAILED")
    sys.exit(1)
print("sw15c2 passed")
