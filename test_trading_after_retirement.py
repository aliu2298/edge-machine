#!/usr/bin/env python3
"""Offline checks (2026-11-04): an empty rule set scans nothing, and a retired rule's rows from after its retirement
stay in the ledger, still grade, and are not its record. Every rule on the board is retired or removed from 2026-11-03,
so market_track.ACTIVE is empty, and `rules or RULES` read that as every rule: the retired RSI(2) pullback logged 29
rows on 2026-11-04 (signal 2026-11-03). market_exec never sent an order for them: it gates entries on executable_rules."""
import inspect
import sys

import control_center as CC
import market_exec as X
import market_track as MT

FAILS = []


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


def bars(n=260, drop_at=None):
    """Daily bars rising 0.5 a day, with a sharp three-day drop at the end (an RSI(2) pullback in an uptrend)."""
    out, px = [], 100.0
    for i in range(n):
        px += -6.0 if drop_at is not None and i >= drop_at else 0.5
        day = f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}"
        out.append(dict(t=f"{day}T21:00:00Z", o=px, h=px + 1, l=px - 1, c=px, v=5_000_000))
    return out


print("an empty rule set scans nothing (None is every rule)")
check("every rule on the board is retired or removed, so ACTIVE is empty", MT.ACTIVE, {})
b = {"AAA": bars(drop_at=255) + [dict(bars(1)[0], t="2026-10-30T21:00:00Z")]}
d0 = {"trades": []}
check("scan(rules=ACTIVE) logs nothing", (MT.scan(b, d0, rules=MT.ACTIVE), d0["trades"]), (0, []))
check("scan_day and scan_hours with an empty set log nothing", (MT.scan_day({}, {"trades": []}, rules={}),
                                                               MT.scan_hours({}, {"trades": []}, rules={})), (0, 0))
check("no `rules or RULES` fallback is left in market_track", "rules or RULES" in inspect.getsource(MT).replace(
    "`rules or RULES` read", ""), False)
check("the live run still scans ACTIVE", "added = scan(bars, d, rules=ACTIVE" in inspect.getsource(MT.main), True)
check("report(rules={}) is empty, report() is the board", (MT.report({"trades": []}, rules={}),
                                                           len(MT.report({"trades": []})) > 0), ([], True))

print("\na retired rule's rows from after its retirement: kept, graded, off the record")
retired_on = MT.RULES["sw_rsi2_pullback"]["retired"][:10]
check("RSI(2) pullback retired 2026-11-03", retired_on, "2026-11-03")
row = lambda sig, status="open", **kw: dict(dict(id=f"sw_rsi2_pullback|X|{sig}", rule="sw_rsi2_pullback", lane="swing", symbol="X",
                                                 signal_day=sig, entry_day=sig, entry=10.0, status=status, exit=None, exit_day=None,
                                                 ret_gross=None, ret_net=None, bench_ret=None, bars_held=None), **kw)
check("after_retirement: a signal on the retirement day or later, on a retired rule only",
      (MT.after_retirement(row("2026-11-02")), MT.after_retirement(row("2026-11-03")), MT.after_retirement(row("2026-11-04")),
       MT.after_retirement(dict(row("2026-11-04"), rule="no_such_rule"))), (False, True, True, False))
d = {"trades": [row("2026-11-02", "closed", exit=11.0, exit_day="2026-11-03", ret_gross=0.1, ret_net=0.099, bench_ret=0.0),
                row("2026-11-02"), row("2026-11-03"), row("2026-11-03", "closed", exit=11.0, exit_day="2026-11-04",
                                                          ret_gross=0.1, ret_net=0.099, bench_ret=0.0)]}
a = MT.assess(d, "sw_rsi2_pullback")
check("assess counts the pre-retirement rows only", (a["days"], a["trades"], a["open"], a["verdict"]), (1, 1, 1, "retired"))
check("they stay in the ledger", len(d["trades"]), 4)
check("grade still closes them (it reads every open row of a retired rule)",
      "after_retirement" in inspect.getsource(MT.grade), False)
check("the Control Center's Trading tile leaves them out", CC._trading_area(d, __import__("datetime").datetime(2026, 11, 5,
      tzinfo=__import__("datetime").timezone.utc))["open"], 1)

print("\nthe broker side: no new entry for a retired rule, its open trades still sell")
ok_rules, skipped = X.executable_rules()
check("RSI(2) pullback is not executable, and says why", ("sw_rsi2_pullback" in ok_rules, skipped.get("sw_rsi2_pullback")),
      (False, "retired: sells its open trades, never a new entry"))
check("a sell is refused for a trade never bought", "never bought, here or at the broker" in inspect.getsource(X.plan), True)

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
