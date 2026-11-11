#!/usr/bin/env python3
"""market_track's close-out at retirement (2026-11-11): the two rules retired 2026-11-03 close every row still open
after its own exit at the close of CLOSE_OUT_DAY, so the Retired block reads as final; their own exits come first."""
import sys

import market_track as MT

FAILS = []


def check(why, got, want):
    good = got == want
    print(f"  {'ok  ' if good else 'FAIL'} {why}" + ("" if good else f" — got {got!r}, want {want!r}"))
    if not good:
        FAILS.append(why)


def bar(day, o, c):
    return dict(t=f"{day}T05:00:00Z", o=o, h=max(o, c), l=min(o, c), c=c, v=1e6)


days = ["2026-11-0%d" % d for d in (4, 5, 6, 9)] + ["2026-11-10", "2026-11-11"]
hist = [bar(f"2025-{m:02d}-{d:02d}", 100, 100) for m in range(1, 13) for d in (5, 15, 25)][:210]
flat = hist + [bar(d, 100, 100 - i * 0.1) for i, d in enumerate(days)]       # falling: the rsi2 exit never comes
bars = {"AAA": flat, MT.BENCH: flat}
row = lambda rule, entry_day: dict(id=f"{rule}|AAA|{entry_day}", rule=rule, symbol="AAA", entry_day=entry_day,
                                   signal_day=entry_day, entry=100.0, status="open", lane="swing")
d = {"trades": [row("sw_rsi2_pullback", "2026-11-04"), row("sw_52w_breakout", "2026-11-04")]}
n = MT.grade(bars, d)
a, b = d["trades"]
check("the retired rule's open row closes at the close-out day's close, costs charged, marked",
      (a["status"], a["exit_day"], a["exit"], a["exit_why"], round(a["ret_net"], 6)),
      ("closed", "2026-11-11", 99.5, "closed out at retirement", round(-0.005 - MT.cost_of(MT.RULES["sw_rsi2_pullback"]), 6)))
check("a removed rule (not in the close-out set) is left exactly as it was", (b["status"], n), ("open", 1))
check("no close-out bar yet (the run before the close-out day): the row stays open",
      MT.grade({"AAA": flat[:-1], MT.BENCH: flat[:-1]}, {"trades": [row("etf_double7", "2026-11-04")]}), 0)
check("the set and the day", (sorted(MT.CLOSE_OUT_RULES), MT.CLOSE_OUT_DAY), (["etf_double7", "sw_rsi2_pullback"], "2026-11-11"))

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
