#!/usr/bin/env python3
"""Offline checks for the NBA Player of the Month snapshot (nba_potm.py): one snapshot a day, both events, the right fields, the winner recorded once,
nothing recorded for a window with an unsettled market, and no guarded phrase."""
import datetime as dt
import sys

import nba_potm as P
import sandbox_audit

FAILS = []


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


mk = lambda t, name, bid, ask, last, vol, res="": dict(ticker=t, yes_sub_title=name, yes_bid_dollars=bid, yes_ask_dollars=ask, last_price_dollars=last, volume_fp=vol,
                                                        open_interest_fp="5.00", result=res, close_time="2026-12-08T04:59:59Z")
EAST = dict(event_ticker="KXNBAPOTM-NOV26EAST", markets=[mk("E-A", "Alpha", "0.0300", "0.7200", "0.4300", "12.00"), mk("E-B", "Beta", "", "0.0100", "0.0000", "0.00")])
WEST = dict(event_ticker="KXNBAPOTM-NOV26WEST", markets=[mk("W-A", "Gamma", "0.6700", "0.6900", "0.8700", "2.00")])
calls = []


def get(path):
    calls.append(path)
    return {"events": [EAST, WEST] if "status=open" in path else []}


print("the snapshot")
st = P.empty()
t = dt.datetime(2026, 11, 14, 14, 0, tzinfo=dt.timezone.utc)
check("a first snapshot is taken", P.snapshot(st, t, get), True)
check("two requests a day: one open-events call (both events)", len(calls), 1)
ev = st["snapshots"]["2026-11-14"]["events"]
check("both events, every player", {k: len(v) for k, v in ev.items()}, {"KXNBAPOTM-NOV26EAST": 2, "KXNBAPOTM-NOV26WEST": 1})
check("bid, ask, last, volume as cents and contracts; a missing bid is None", ev["KXNBAPOTM-NOV26EAST"], [["E-A", "Alpha", 3, 72, 43, 12.0, 5.0], ["E-B", "Beta", None, 1, 0, 0.0, 5.0]])
check("a rerun the same day changes nothing", (P.snapshot(st, t.replace(hour=22), get), len(st["snapshots"])), (False, 1))
check("the next day adds a path point", (P.snapshot(st, t + dt.timedelta(days=1), get), sorted(st["snapshots"])), (True, ["2026-11-14", "2026-11-15"]))
check("nothing open, nothing written", P.snapshot(P.empty(), t, lambda p: {"events": []}), False)

print("\nthe settled windows")
done = dict(EAST, markets=[mk("E-A", "Alpha", "0", "0", "1", "9", "yes"), mk("E-B", "Beta", "0", "0", "0", "9", "no")])
half = dict(WEST, markets=[mk("W-A", "Gamma", "0", "0", "1", "9", "yes"), mk("W-B", "Delta", "0", "0", "0", "9", "")])
sget = lambda path: {"events": [done, half]}
check("a fully settled window is recorded with its winner; one with an open market is not", (P.settle(st, t, sget), sorted(st["settled"]), st["settled"]["KXNBAPOTM-NOV26EAST"]["winner"]),
      (1, ["KXNBAPOTM-NOV26EAST"], "Alpha"))
check("recorded once", P.settle(st, t, sget), 0)

print("\nthe file and the copy")
import tempfile, os
with tempfile.TemporaryDirectory() as d:
    p = os.path.join(d, "x.json")
    P.save(st, p)
    check("round trip", P.load(p)["settled"]["KXNBAPOTM-NOV26EAST"]["winner"], "Alpha")
check("the audit's phrase scan finds nothing", sandbox_audit.COPY_RE.search(open("nba_potm.py").read() + open("test_nba_potm.py").read()), None)

print()
if FAILS:
    print(f"{len(FAILS)} FAILED")
    sys.exit(1)
print("all ok")
