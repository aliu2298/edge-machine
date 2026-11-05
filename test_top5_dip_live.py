#!/usr/bin/env python3
"""The live top-5 dip paper record (top5_dip_live.py): it follows the executor's decision snapshots. Offline checks."""
import datetime as dt
import sys

import arg_dip as A
import chaos_replay as C
import top5_dip_live as L

FAILS = []
UTC = dt.timezone.utc


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


KICK = dt.datetime(2026, 11, 7, 15, 0, tzinfo=UTC)
NOW = KICK + dt.timedelta(hours=6)
TK = "KXEPLTOTAL-26NOV07ARSCHE"


def dec(event=TK, **kw):
    d = dict(lane=L.LANE, bot_version=L.VERSION, ticker=event + "-2", event=event, league="EPL", matchday="2026-11-07",
             kickoff=KICK.isoformat(), outcome="entered", why=None, rule_ok=True, P=0.80, limit=0.44, qty=2, yes_bid=0.78, yes_ask=0.80, spread=0.02,
             decided_at=(KICK - dt.timedelta(minutes=50)).isoformat())
    d.update(kw)
    return d


def tr(mins, px, n):
    t = (KICK + dt.timedelta(minutes=mins)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return dict(created_time=t, yes_price_dollars=f"{px:.2f}", count_fp=str(n))


MARKETS = {}
TRADES = {}
C.event_markets = lambda ev, fetch: (MARKETS.get(ev, []), False)
A.fetch_trades = lambda ticker, min_ts, fetch, max_pages=30: TRADES.get(ticker, [])


def settle(event, result="yes", status="finalized"):
    MARKETS[event] = [dict(ticker=event + "-2", floor_strike=1.5, status=status, result=result, title="Over 1.5?")]


print("a filled dip that sells at P")
settle(TK)
TRADES[TK + "-2"] = [tr(5, 0.44, 30), tr(7, 0.44, 30), tr(40, 0.81, 5)]
st = L.load()
L.run(st, {TK + "-2": dec()}, NOW)
e = st["entries"][0]
b = e["buys"]["55"]
check("one entry at the snapshot's P and limit", (len(st["entries"]), e["p"], b["limit"], b["counted"], b["sold"]), (1, 0.80, 0.44, True, True))
check("the record starts on the snapshot's matchday", st["since"], "2026-11-07")
s = L.summary(st)
check("summary reads the entry", (s["matches"], s["fills"], s["sold"]), (1, 1, 1))
L.run(st, {TK + "-2": dec()}, NOW)
check("an entry is never rewritten or doubled", len(st["entries"]), 1)

print("no fill, thin touch, hold to settlement")
ev2 = "KXLALIGATOTAL-26NOV07RMABAR"
settle(ev2, result="no")
TRADES[ev2 + "-2"] = [tr(5, 0.44, 30), tr(7, 0.44, 30)]
st = L.load(); L.run(st, {ev2 + "-2": dec(event=ev2, ticker=ev2 + "-2", league="La Liga")}, NOW)
b = st["entries"][0]["buys"]["55"]
check("a fill never sold settles at 0 on a 0-1 goal match", (b["counted"], b["sold"], b["payout"]), (True, False, 0.0))
ev3 = "KXSERIEATOTAL-26NOV07JUVMIL"
settle(ev3)
TRADES[ev3 + "-2"] = [tr(5, 0.70, 30)]
st = L.load(); L.run(st, {ev3 + "-2": dec(event=ev3, ticker=ev3 + "-2")}, NOW)
check("no print at the limit = no fill, still the match's row", (len(st["entries"]), st["entries"][0]["buys"]["55"]), (1, None))
ev4 = "KXLIGUE1TOTAL-26NOV07PSGLYO"
settle(ev4)
TRADES[ev4 + "-2"] = [tr(5, 0.44, 3), tr(30, 0.44, 3)]
st = L.load(); L.run(st, {ev4 + "-2": dec(event=ev4, ticker=ev4 + "-2")}, NOW)
check("a thin touch is recorded and not counted", st["entries"][0]["buys"]["55"]["counted"], False)

print("what counts as an entry")
st = L.load()
L.run(st, {TK + "-2": dec(outcome="no_entry", crossed=True, why="the bid would have crossed the book")}, NOW)
check("a crossed bid is no entry, never a fill", (st["entries"], list(st["no_entry"])), ([], [TK + "-2"]))
st = L.load()
L.run(st, {TK + "-2": dec(outcome="skip", rule_ok=False, P=None)}, NOW)
check("a rule skip is not an entry", (st["entries"], st["no_entry"]), ([], {}))
st = L.load()
L.run(st, {TK + "-2": dec(outcome="veto", why="operational veto (cap, loss cap, funding, shard or halt)")}, NOW)
check("an operational veto still counts in paper", len(st["entries"]), 1)
st = L.load()
L.run(st, {TK + "-2": dec(outcome="bid_late")}, NOW)
check("a late bid still counts in paper", len(st["entries"]), 1)

print("waiting")
st = L.load()
settle(TK, status="active", result="")
L.run(st, {TK + "-2": dec()}, NOW)
check("an unsettled match waits", (st["entries"], st["observations"]["waiting"]), ([], 1))
st = L.load()
settle(TK)
L.run(st, {TK + "-2": dec()}, KICK - dt.timedelta(minutes=30))
check("a match not yet kicked off waits", st["entries"], [])
print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
