#!/usr/bin/env python3
"""The live Argentina dip paper record (arg_dip_live.py): it follows the executor's decision snapshots. Offline checks."""
import datetime as dt
import os
import sys
import tempfile

import arg_dip as A
import chaos_replay as C
import arg_dip_live as L

L.PATH = os.path.join(tempfile.mkdtemp(), "arg_dip_live_test.json")   # hermetic: never the real ledger, which now holds real entries on the same dates
FAILS = []
UTC = dt.timezone.utc


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


KICK = dt.datetime(2026, 11, 9, 15, 0, tzinfo=UTC)
NOW = KICK + dt.timedelta(hours=6)
TK = "KXARGPREMDIVTOTAL-26NOV09ARSCHE"


def dec(event=TK, **kw):
    d = dict(lane=L.LANE, bot_version=L.VERSION, ticker=event + "-1", event=event, league="Argentina", matchday="2026-11-09",
             kickoff=KICK.isoformat(), outcome="entered", why=None, rule_ok=True, P=0.80, limit=0.52, qty=2, yes_bid=0.78, yes_ask=0.80, spread=0.02,
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
    MARKETS[event] = [dict(ticker=event + "-1", floor_strike=0.5, status=status, result=result, title="Over 0.5?")]


print("a filled dip that sells at P")
settle(TK)
TRADES[TK + "-1"] = [tr(5, 0.52, 30), tr(7, 0.52, 30), tr(40, 0.81, 5)]
st = L.load()
L.run(st, {TK + "-1": dec()}, NOW)
e = st["entries"][0]
b = e["buys"]["65"]
check("one entry at the snapshot's P and limit", (len(st["entries"]), e["p"], b["limit"], b["counted"], b["sold"]), (1, 0.80, 0.52, True, True))
check("the record starts on the snapshot's matchday", st["since"], "2026-11-09")
s = L.summary(st)
check("summary reads the entry", (s["matches"], s["fills"], s["sold"]), (1, 1, 1))
L.run(st, {TK + "-1": dec()}, NOW)
check("an entry is never rewritten or doubled", len(st["entries"]), 1)

print("no fill, thin touch, hold to settlement")
ev2 = "KXARGPREMDIVTOTAL-26NOV09RMABAR"
settle(ev2, result="no")
TRADES[ev2 + "-1"] = [tr(5, 0.52, 30), tr(7, 0.52, 30)]
st = L.load(); L.run(st, {ev2 + "-1": dec(event=ev2, ticker=ev2 + "-1", league="La Liga")}, NOW)
b = st["entries"][0]["buys"]["65"]
check("a fill never sold settles at 0 on a 0-1 goal match", (b["counted"], b["sold"], b["payout"]), (True, False, 0.0))
ev3 = "KXSERIEATOTAL-26NOV09JUVMIL"
settle(ev3)
TRADES[ev3 + "-1"] = [tr(5, 0.70, 30)]
st = L.load(); L.run(st, {ev3 + "-1": dec(event=ev3, ticker=ev3 + "-1")}, NOW)
check("no print at the limit = no fill, still the match's row", (len(st["entries"]), st["entries"][0]["buys"]["65"]), (1, None))
ev4 = "KXLIGUE1TOTAL-26NOV09PSGLYO"
settle(ev4)
TRADES[ev4 + "-1"] = [tr(5, 0.52, 3), tr(30, 0.52, 3)]
st = L.load(); L.run(st, {ev4 + "-1": dec(event=ev4, ticker=ev4 + "-1")}, NOW)
check("a thin touch is recorded and not counted", st["entries"][0]["buys"]["65"]["counted"], False)

print("what counts as an entry")
st = L.load()
L.run(st, {TK + "-1": dec(outcome="no_entry", crossed=True, why="the bid would have crossed the book")}, NOW)
check("a crossed bid is no entry, never a fill", (st["entries"], list(st["no_entry"])), ([], [TK + "-1"]))
st = L.load()
L.run(st, {TK + "-1": dec(outcome="skip", rule_ok=False, P=None)}, NOW)
check("a rule skip is not an entry", (st["entries"], st["no_entry"]), ([], {}))
st = L.load()
L.run(st, {TK + "-1": dec(outcome="veto", why="operational veto (cap, loss cap, funding, shard or halt)")}, NOW)
check("an operational veto still counts in paper", len(st["entries"]), 1)
st = L.load()
L.run(st, {TK + "-1": dec(outcome="bid_late")}, NOW)
check("a late bid still counts in paper", len(st["entries"]), 1)

print("waiting")
st = L.load()
settle(TK, status="active", result="")
TRADES[TK + "-1"] = [tr(5, 0.70, 30)]
L.run(st, {TK + "-1": dec()}, NOW)
check("an unsettled match with no counted fill waits", (st["entries"], st["observations"]["waiting"]), ([], 1))
st = L.load()
settle(TK)
L.run(st, {TK + "-1": dec()}, KICK - dt.timedelta(minutes=30))
check("a match not yet kicked off waits", st["entries"], [])

print("provisional entries: the fill and the sell are known before Kalshi settles the market")
settle(TK, status="active", result="")
TRADES[TK + "-1"] = [tr(5, 0.52, 30), tr(7, 0.52, 30), tr(40, 0.81, 5)]
st = L.load()
L.run(st, {TK + "-1": dec()}, NOW)
e = st["entries"][0]
b = e["buys"]["65"]
check("a sold fill on an unsettled market is an entry at once, provisional, no result", (len(st["entries"]), e.get("provisional"), e["result"], b["counted"], b["sold"], b["payout"]),
      (1, True, None, True, True, None))
check("the observation says how many are provisional", (st["observations"]["new"], st["observations"]["provisional"]), (1, 1))
check("a provisional entry is out of the settled summary", L.summary(st)["matches"], 0)
import arg_dip_production as TP
q = TP._result_quote(e)
check("the page reads it as sold at P, a win, with no result yet", (q["status"], q["rule"], q["result"], q["pnl"] > 0), ("won", "sold at P", None, True))
L.run(st, {TK + "-1": dec()}, NOW + dt.timedelta(minutes=5))
check("re-reading an unsettled market keeps one entry", (len(st["entries"]), st["observations"]["new"]), (1, 0))
settle(TK)
L.run(st, {TK + "-1": dec()}, NOW + dt.timedelta(hours=2))
e = st["entries"][0]
check("settlement completes the same entry in place: result set, no longer provisional, the sale kept",
      (len(st["entries"]), e.get("provisional"), e["result"], e["buys"]["65"]["sold"], e["buys"]["65"]["payout"], e["logged"] == NOW.isoformat()), (1, None, "yes", True, 1.0, True))
check("and it joins the settled summary", L.summary(st)["fills"], 1)

print("a fill still held is filled, open")
ev5 = "KXBUNDESLIGATOTAL-26NOV09HSVBMG"
settle(ev5, status="active", result="")
TRADES[ev5 + "-1"] = [tr(5, 0.52, 30), tr(7, 0.52, 30), tr(20, 0.60, 5)]
st = L.load()
L.run(st, {ev5 + "-1": dec(event=ev5, ticker=ev5 + "-1", league="Bundesliga")}, NOW)
e = st["entries"][0]
q = TP._result_quote(e)
check("held, not sold: provisional, open on the page", (e.get("provisional"), e["buys"]["65"]["sold"], q["status"], q["rule"], q["pnl"]), (True, False, "open", "filled, open", 0.0))
settle(ev5, result="no")
L.run(st, {ev5 + "-1": dec(event=ev5, ticker=ev5 + "-1", league="Bundesliga")}, NOW + dt.timedelta(hours=2))
q = TP._result_quote(st["entries"][0])
check("settled at 0 it completes as a loss", (len(st["entries"]), q["status"], q["rule"], q["result"]), (1, "lost", "held to settlement", "b"))
print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
