#!/usr/bin/env python3
"""test_market.py — the trading lane's logic, on bars built by hand.

No network and no credentials: every test drives market_track with synthetic bars, so the
rules, the no-lookahead entry, the cost charge and the per-entry-day scoring are all checked
on a machine with no Alpaca account at all.
"""
import datetime
import sys

import market_sources as M
import market_track as T

FAILS = []


def eq(got, want, why):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {why}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(why)


def ok_(cond, why):
    eq(bool(cond), True, why)


def bar(day, o, h, l, c, v=1_000_000):
    return {"t": f"{day}T00:00:00Z", "o": o, "h": h, "l": l, "c": c, "v": v}


def series(n, start=100.0, step=0.1, first_day=datetime.date(2025, 1, 1)):
    """A gently rising series, one bar a trading day, with dollar volume well over the floor."""
    out = []
    for i in range(n):
        p = start + i * step
        d = first_day + datetime.timedelta(days=i)
        out.append(bar(d.isoformat(), p, p * 1.01, p * 0.99, p, 2_000_000))
    return out


print("indicators")
eq(T.sma([1, 2, 3, 4], 2), 3.5, "the simple average uses the last n closes")
eq(T.sma([1], 5), None, "and is None before there are n of them")
eq(round(T.rsi([10, 11, 12], 2), 1), 100.0, "RSI is 100 when nothing fell")
ok_(T.rsi([12, 11, 10], 2) < 5, "and near zero when nothing rose")

print("\nthe rules fire where they should")
_up = series(260, step=0.3)          # a real uptrend: the last close sits well above the 200-day
ok_(not T._sw_rsi2(_up), "a steadily rising stock is never an RSI(2) pullback")
_dip = _up[:-3] + [bar("2025-09-20", 177, 177, 176, 176.0), bar("2025-09-21", 176, 176, 173, 173.0),
                   bar("2025-09-22", 173, 173, 170, 170.0)]
ok_(T._sw_rsi2(_dip), "three sharp down days under the 5-day average, still above the 200-day, fires")
_flat = series(260, step=0.0)
ok_(not T._sw_breakout(_flat), "a flat series never makes a 52-week high")
_brk = _flat[:-1] + [bar("2025-09-22", 100, 106, 100, 105.0, 5_000_000)]
ok_(T._sw_breakout(_brk), "a new high on 2.5x volume fires the breakout rule")
_nov = _flat[:-1] + [bar("2025-09-22", 100, 106, 100, 105.0, 1_000_000)]
ok_(not T._sw_breakout(_nov), "the same high WITHOUT the volume does not")
_prev = _up[-2]["c"]
_gap = _up[:-1] + [bar("2025-09-22", _prev * 0.96, _prev * 1.01, _prev * 0.95, _prev * 1.005)]
ok_(T._sw_gap_reversal(_gap), "a 3%+ gap down that closes above its own open fires")

print("\nentries never use the signal bar, and costs are charged")
_bars = {"AAA": _dip + [bar("2025-09-23", 171.0, 174.0, 170.0, 173.0),
                        bar("2025-09-24", 173.0, 176.0, 172.0, 175.5),
                        bar("2025-09-25", 175.5, 177.0, 175.0, 176.5)],
         "SPY": series(263, start=500.0, step=0.5) + [bar("2025-09-23", 631.0, 632.0, 630.0, 631.5),
                                                      bar("2025-09-24", 631.5, 633.0, 631.0, 632.5),
                                                      bar("2025-09-25", 632.5, 634.0, 632.0, 633.5)]}
_d = {"trades": [], "meta": {}}
_n = T.scan(_bars, _d, rules={"sw_rsi2_pullback": T.RULES["sw_rsi2_pullback"]})
eq(_n, 2, "both down days fire, one trade each")
_t = _d["trades"][-1]
eq((_t["signal_day"], _t["entry_day"], _t["entry"]), ("2025-09-22", "2025-09-23", 171.0),
   "it enters at the NEXT bar's open (171.0), never the signal bar's close (170.0)")
eq(T.scan(_bars, _d, rules={"sw_rsi2_pullback": T.RULES["sw_rsi2_pullback"]}), 0,
   "a second run logs the same signal again: no")
_c = T.grade(_bars, _d, rules={"sw_rsi2_pullback": T.RULES["sw_rsi2_pullback"]})
eq(_c, 2, "both trades close once their exit has happened")
_t = _d["trades"][-1]
eq(_t["status"], "closed", "and is marked closed")
eq(round(_t["ret_gross"] - _t["ret_net"], 6), round(2 * M.COST_BPS_PER_SIDE / 10000, 6),
   "the net return is the gross minus a cost on BOTH sides")
ok_(_t["bench_ret"] is not None, "and it carries SPY's move over the same days")

print("\njudged per entry day, against SPY")
_d2 = {"trades": [
    dict(id=f"r|S{i}|d", rule="r", lane="swing", symbol=f"S{i}", signal_day="2025-05-01",
         entry_day="2025-05-02", entry=100.0, status="closed", exit=101.0, exit_day="2025-05-05",
         ret_gross=0.01, ret_net=0.009, bench_ret=0.004, bars_held=3) for i in range(8)], "meta": {}}
_a = T.assess(_d2, "r")
eq((_a["days"], _a["trades"]), (1, 8), "eight names bought the same morning are ONE result")
eq(_a["verdict"], "early", "one entry day is too early for any verdict")
eq(round(_a["edge"], 4), 0.005, "the edge is the net return minus SPY over the same days")
_d3 = {"trades": [
    dict(id=f"r|S|d{i}", rule="r", lane="swing", symbol="S", signal_day=f"2025-05-{i+1:02d}",
         entry_day=f"2025-06-{i+1:02d}", entry=100.0, status="closed", exit=101.0,
         exit_day=f"2025-06-{i+2:02d}", ret_gross=0.01, ret_net=0.009,
         bench_ret=0.004 if i % 2 else 0.006, bars_held=2) for i in range(31)], "meta": {}}
_a3 = T.assess(_d3, "r")
eq((_a3["days"], _a3["verdict"]), (31, "proven"), "31 entry days ahead of SPY reads as a proven edge")
_d4 = {"trades": [dict(t, ret_net=-0.004, bench_ret=0.004) for t in _d3["trades"]], "meta": {}}
eq(T.assess(_d4, "r")["verdict"], "noedge", "the same sample behind SPY reads as no edge")
eq(T.assess({"trades": [], "meta": {}}, "r")["verdict"], "waiting", "a rule with no trades is waiting")

print("\nhousekeeping")
ok_(all(r["lane"] in ("swing", "day") for r in T.RULES.values()), "every rule declares its lane")
ok_(all(len(r["note"]) > 200 for r in T.RULES.values()),
    "and carries a note saying what it does and why")
ok_(all("Pre-registered" in r["note"] or "registered" in r["note"] for r in T.RULES.values()),
    "and says it was registered before it logged anything")
eq(M.configured.__doc__ is not None, True, "the credentials check is documented")
ok_("APCA" not in open("market_track.py").read(), "the tracker never touches credentials itself")

print(f"\n{'FAILED: ' + str(len(FAILS)) if FAILS else 'all market tests passed'}")
for f in FAILS:
    print("   -", f)
sys.exit(1 if FAILS else 0)
