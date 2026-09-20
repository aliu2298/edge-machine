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

print("\nthe day lane: one session, one trade, entered at the next bar")
def m5(day, hhmm, o, h, l, c, v=100000):
    return {"t": f"{day}T{hhmm}:00Z", "o": o, "h": h, "l": l, "c": c, "v": v}
def session(day, path):
    """path: list of (hh:mm, o, h, l, c) tuples, from 13:30 UTC."""
    return [m5(day, row[0], *row[1:]) for row in path]
_D = "2026-09-18"
# first 30 min ranges 100-102, then a clean break up that holds to the close
_up_day = session(_D, [("13:30",100,102,100,101),("13:35",101,102,100,101),("13:40",101,102,100,100.5),
                       ("13:45",100.5,101,100,100.8),("13:50",100.8,101.5,100.2,101),("13:55",101,102,100.5,101.5),
                       ("14:00",101.5,103,101.4,102.5),("14:05",102.6,104,102.5,103.5),("14:10",103.5,105,103,104.5),
                       ("19:55",104.5,105,104,104.8)])
_t = T.day_trades(_up_day, "dt_orb30")
eq((_t[0], _t[2]), (1, 102.6), "the break above the range enters LONG at the next bar's open, not the signal close")
eq(round(_t[4], 2), 104.8, "and with no stop hit it leaves at the session's last close")
# same range, break down, then the stop (the range high) is taken out
_rev = session(_D, [("13:30",100,102,100,101),("13:35",101,102,100,101),("13:40",101,102,100,100.5),
                    ("13:45",100.5,101,100,100.8),("13:50",100.8,101.5,100.2,101),("13:55",101,102,100.5,101.5),
                    ("14:00",101,101.5,99,99.5),("14:05",99.4,100,99,99.8),("14:10",99.8,103,99.5,102.5),
                    ("19:55",102.5,103,102,102.8)])
_t2 = T.day_trades(_rev, "dt_orb30")
eq((_t2[0], _t2[2], _t2[4]), (-1, 99.4, 102), "a break DOWN goes short, and stops out at the range high")
eq(T.day_trades(_up_day[:4], "dt_orb30"), None, "a session too short to have an opening range trades nothing")
_dd = {"trades": [], "meta": {}}
_n5 = T.scan_day({"AAA": _up_day, "SPY": _up_day}, _dd, rules={"dt_orb30": T.RULES["dt_orb30"]})
eq(_n5, 1, "one session, one logged day trade")
_dt = _dd["trades"][0]
eq((_dt["lane"], _dt["status"], _dt["entry_day"] == _dt["exit_day"]), ("day", "closed", True),
   "a day trade is logged already closed, inside its own session")
eq(round(_dt["ret_gross"] - _dt["ret_net"], 6), round(2 * M.COST_BPS_PER_SIDE / 10000, 6),
   "and is charged a cost on both sides like every other trade")
eq(T.scan_day({"AAA": _up_day, "SPY": _up_day}, _dd, rules={"dt_orb30": T.RULES["dt_orb30"]}), 0,
   "a second pass over the same session logs nothing twice")
ok_(T.DAY_UNIVERSE and len(T.DAY_UNIVERSE) <= 25, "the day lane's universe is a small pre-registered list")

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
