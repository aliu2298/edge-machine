#!/usr/bin/env python3
"""Offline checks for Favourite 1-0 and Quiet First Half (under_piggyback.py) and their Soccer rows."""
import datetime as dt
import sys

import sandbox_audit
import soccer_rules as SR
import under_piggyback as UP

FAILS = []
UTC = dt.timezone.utc
NOW = dt.datetime(2026, 11, 22, 12, 0, tzinfo=UTC)
KO = NOW + dt.timedelta(minutes=45)


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


def mk(t, title, b, a, sub=None):
    return dict(ticker=t, title=title, yes_sub_title=sub or title, status="active", yes_bid_dollars=str(b), yes_ask_dollars=str(a))


TAG = "26NOV22MCIFUL"
fx = [dict(kickoff=KO.strftime("%Y-%m-%dT%H:%MZ"), league="Premier League", home="Manchester City", away="Fulham", played=False, competitive=True,
           home_goals=None, away_goals=None),
      dict(kickoff=KO.strftime("%Y-%m-%dT%H:%MZ"), league="Bundesliga", home="A", away="B", played=False, competitive=True, home_goals=None, away_goals=None)]
SR.labels = lambda fixtures, f: ("O-D-", "O+D+")          # A6: an O-D- team v an O+ opponent
total = dict(event_ticker=f"KXEPLTOTAL-{TAG}", title="Manchester City vs Fulham FC: Total Goals",
             markets=[mk(f"KXEPLTOTAL-{TAG}-3", "Will over 2.5 goals be scored?", 0.50, 0.52)])      # under NO 50c, inside A6's <=55c band
game = dict(event_ticker=f"KXEPLGAME-{TAG}", title="Manchester City vs Fulham",
            markets=[mk(f"KXEPLGAME-{TAG}-MCI", "Manchester City wins", 0.70, 0.72, "Manchester City"), mk(f"KXEPLGAME-{TAG}-FUL", "Fulham wins", 0.11, 0.12, "Fulham"),
                     mk(f"KXEPLGAME-{TAG}-TIE", "Tie", 0.17, 0.18, "Tie")])
score = dict(event_ticker=f"KXEPLSCORE-{TAG}", title="Manchester City vs Fulham FC: Correct Score",
             markets=[mk(f"KXEPLSCORE-{TAG}-MCI1FUL0", "Final score Manchester City wins 1-0?", 0.07, 0.08), mk(f"KXEPLSCORE-{TAG}-MCI0FUL0", "Draw 0-0", 0.02, 0.03),
                      mk(f"KXEPLSCORE-{TAG}-MCI0FUL1", "Fulham wins 1-0", 0.02, 0.03)])
btts = dict(event_ticker=f"KXEPL1HBTTS-{TAG}", title="Manchester City vs Fulham: First Half BTTS", markets=[mk(f"KXEPL1HBTTS-{TAG}-BTTS", "1H BTTS", 0.23, 0.25)])
events = {"KXEPLTOTAL": [total], "KXEPLGAME": [game], "KXEPLSCORE": [score], "KXEPL1HBTTS": [btts]}


def fake(path):
    if path.startswith("events?"):
        return {"events": events.get(path.split("series_ticker=")[1].split("&")[0], [])}
    t = path.split("/")[-1]
    return {"market": {"ticker": t, "status": "finalized", "result": "yes" if t.endswith("MCI1FUL0") else "no" if "BTTS" not in t else "no"}}


print("selection and the window")
check("series prefixes", UP.PREFIX, {"UEFA Nations League": "KXUEFANL", "Premier League": "KXEPL"})
check("due: only the Nations League and Premier League", [f["home"] for f in UP.due(fx, NOW)], ["Manchester City"])
check("A6 selects it: label and its price band on the under's NO side (50c)", UP.selected("Premier League", ("O-D-", "O+D+"), total, NOW), ["A6"])
out = dict(total, markets=[mk(f"KXEPLTOTAL-{TAG}-3", "Will over 2.5 goals be scored?", 0.30, 0.32)])
check("under NO at 70c is above A6's 55c cap: not selected", UP.selected("Premier League", ("O-D-", "O+D+"), out, NOW), [])

print("\nfavourite and tickers")
check("favourite is the higher-priced side, mids logged", UP.favourite(game), ("MCI", "FUL", 0.71, 0.115))
close = dict(game, markets=[mk(f"KXEPLGAME-{TAG}-MCI", "x", 0.40, 0.42), mk(f"KXEPLGAME-{TAG}-FUL", "y", 0.40, 0.41), mk(f"KXEPLGAME-{TAG}-TIE", "t", 0.2, 0.21)])
check("two sides within 2c: no favourite", UP.favourite(close), None)
check("score ticker follows the event's code order", (UP.score_ticker(score, "MCI", "FUL", 1, 0), UP.score_ticker(score, "FUL", "MCI", 1, 0)),
      (f"KXEPLSCORE-{TAG}-MCI1FUL0", f"KXEPLSCORE-{TAG}-MCI0FUL1"))

print("\nthe run")
states = {k: UP.load(k, "/nonexistent") for k in UP.LANES}
log = UP.run(states, fx, NOW, fake)
f1 = states["fav_one_nil"]["rules"]["PB"]["picks"]
q1 = states["quiet_first_half"]["rules"]["PB"]["picks"]
check("Favourite 1-0: the home favourite 1-0, YES at the 8c ask, sources listed", [(p["ticker"][-8:], p["side"], p["price"], p["sources"]) for p in f1], [("MCI1FUL0", "yes", 0.08, ["A6"])])
check("it logs fav/dog prices and the 0-0 and dog-1-0 asks", (f1[0]["fav_price"], f1[0]["dog_price"], f1[0]["ask_0_0"], f1[0]["ask_dog_1_0"]), (0.71, 0.115, 0.03, 0.03))
check("Quiet First Half: 1H BTTS NO at 1 - the YES bid (77c)", [(p["side"], p["price"], p["sources"]) for p in q1], [("no", 0.77, ["A6"])])
UP.run(states, fx, NOW + dt.timedelta(minutes=30), fake)
check("a second read adds nothing: once per match per lane", (len(f1), len(q1)), (1, 1))
check("graded from Kalshi: the 1-0 landed, the quiet half won", (f1[0]["status"], f1[0]["profit"], q1[0]["status"], q1[0]["profit"]),
      ("won", round(100 * (1 / (0.08 + UP.FU.fee(0.08)) - 1), 2), "won", round(100 * (1 / (0.77 + UP.FU.fee(0.77)) - 1), 2)))
wide = dict(score, markets=[mk(f"KXEPLSCORE-{TAG}-MCI1FUL0", "x", 0.04, 0.08)])
check("a 1-0 spread over 3c: no entry", UP.pick_fav(fx[0], ("O-D-", "O+D+"), total, ["A6"], game, wide, NOW), None)
check("no 1H BTTS market for the match: no entry", UP.pick_quiet(fx[0], ("O-D-", "O+D+"), total, ["A6"], None, NOW), None)
check("a 1H BTTS spread over 3c: no entry", UP.pick_quiet(fx[0], ("O-D-", "O+D+"), total, ["A6"], dict(btts, markets=[mk(f"KXEPL1HBTTS-{TAG}-BTTS", "x", 0.20, 0.25)]), NOW), None)

print("\nthe Soccer rows")
import soccer_lanes
rows = soccer_lanes.piggyback_rows(states)
check("two rows, each with its own record", [(r["name"], r["a"]["n"], r["a"]["won"]) for r in rows], [("fav_one_nil", 1, 1), ("quiet_first_half", 1, 1)])
html = "".join(r["own"]["details"] + r["own"]["entries"] for r in rows)
check("per-source table, the in-sample rows, no dollars, no guarded phrase", ("Break-even after fees" in html, "In-sample, not counted" in html, "$" in html,
      sandbox_audit.COPY_RE.findall(html + open("under_piggyback.py").read())), (True, True, False, []))

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
