#!/usr/bin/env python3
"""Offline checks for the seven NBA label rules (nba_rules.py) and their page section."""
import datetime as dt
import sys

import nba_rules as NR
import nba_rules_build as NB

FAILS = []
UTC = dt.timezone.utc
NOW = dt.datetime(2026, 10, 20, 22, 0, tzinfo=UTC)


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


def game(home_ft, away_ft, home_h1="O+D+", away_h1="O+D+", mins=45, home="SA", away="HOU"):
    return dict(id="g1", home=home, away=away, start=(NOW + dt.timedelta(minutes=mins)).isoformat(),
                completed=False, roll_lab_home_ft=home_ft, roll_lab_away_ft=away_ft,
                roll_lab_home_h1=home_h1, roll_lab_away_h1=away_h1)


def mkt(team, strike, bid, ask):
    code = NR.E2K.get(team, team)
    return dict(ticker=f"KXNBATEAMTOTAL-26OCT20HOUSAS-{code}{int(strike)}", floor_strike=strike, status="active",
                yes_bid_dollars=str(bid), yes_ask_dollars=str(ask), yes_sub_title=f"{team} over {strike} points")


print("names and rungs")
check("the event tag is the ET date, then Kalshi's away and home codes",
      NR.event_tag("2026-10-21T00:30:00+00:00", "HOU", "SA"), "26OCT20HOUSAS")
check("a team-total market names its team", NR.team_of(mkt("SA", 109.5, .6, .62)), "SA")
ladder = [mkt("SA", 104.5, .80, .82), mkt("SA", 109.5, .68, .70), mkt("SA", 114.5, .50, .53)]
check("110+ is the 109.5 rung", NR.rung(ladder, 110)["floor_strike"], 109.5)
check("no rung within 1.5 points means no entry", NR.rung(ladder, 120), None)
check("a wide market is not quoted", NR.quote(mkt("SA", 109.5, .50, .60)), None)

print("\nthe seven rules")
g = game("O+D+", "O-D+")
ms = ladder + [mkt("HOU", 114.5, .40, .43), mkt("HOU", 109.5, .55, .58)]
picks = NR.team_picks(g, ms, NOW)
got = sorted((p["rule"], p["team"], p["side"], p["strike"], p["price"]) for p in picks)
check("an O+ home side: R1 110+ YES at 70c, R2 115+ YES at 53c, R6 105+ YES at 82c; the O- away side: R3 115+ NO at 60c",
      got, [("R1", "SA", "yes", 109.5, 0.70), ("R2", "SA", "yes", 114.5, 0.53),
            ("R3", "HOU", "no", 114.5, 0.6), ("R6", "SA", "yes", 104.5, 0.82)])
pricey = NR.team_picks(g, [mkt("SA", 109.5, .82, .84)], NOW)
check("R1 refuses 110+ above 80c", [p["rule"] for p in pricey if p["rule"] == "R1"], [])
dd = game("O+D-", "O-D-")
r7 = NR.team_picks(dd, [mkt("SA", 109.5, .52, .55), mkt("SA", 114.5, .40, .42), mkt("HOU", 109.5, .45, .48)], NOW)
check("both D-: R7 takes the NO nearer 50c, and R1 and R2 stand aside",
      sorted((p["rule"], p["team"], p["strike"]) for p in r7 if p["rule"] in ("R1", "R2", "R7")),
      [("R7", "HOU", 109.5), ("R7", "SA", 109.5)])
ww = game("O-D-", "O-D-")
r4 = NR.team_picks(ww, [mkt("SA", 101.5, .62, .64), mkt("SA", 104.5, .55, .58), mkt("SA", 109.5, .40, .42)], NOW)
check("weak v weak: R4 takes the cheapest NO between 100 and 110, at 45c or less",
      [(p["rule"], p["strike"], p["price"]) for p in r4 if p["rule"] == "R4" and p["team"] == "SA"], [("R4", 101.5, 0.38)])
h1 = [dict(ticker="KXNBA1HTOTAL-26OCT20HOUSAS-114", floor_strike=114.5, status="active",
           yes_bid_dollars="0.52", yes_ask_dollars="0.55")]
check("R5: an O-D- first-half label, 115+ NO at 48c", [(p["rule"], p["price"]) for p in NR.half_picks(game("O+D+", "O+D+", home_h1="O-D-"), h1, NOW)],
      [("R5", 0.48)])
check("R5 stays out without an O-D- first-half label", NR.half_picks(game("O+D+", "O+D+"), h1, NOW), [])

print("\ntiming, freezing and settlement")
check("due: 45 minutes out yes, 2 hours out no, 10 minutes out no",
      [len(NR.due([game("O+D+", "O+D+", mins=m)], NOW)) for m in (45, 120, 10)], [1, 0, 0])
st = {"rules": {k: {"picks": []} for k in NR.RULES}}
fake = lambda path: ({"markets": ms} if "event_ticker=KXNBATEAMTOTAL" in path else {"markets": []}) if path.startswith("markets?") \
    else {"market": {"ticker": path.split("/")[-1], "status": "finalized", "result": "yes"}}
NR.D.pages = lambda path, key, fetch: fetch(path).get(key) or []
NR.run(st, [g], NOW, fake)
first = sum(len(v["picks"]) for v in st["rules"].values())
NR.run(st, [g], NOW + dt.timedelta(minutes=15), fake)
check("a second run adds nothing: one frozen entry per rule, team and game",
      sum(len(v["picks"]) for v in st["rules"].values()), first)
check("settled on Kalshi's result: a YES on yes wins, a NO on yes loses",
      sorted({(p["side"], p["status"]) for v in st["rules"].values() for p in v["picks"]}),
      [("no", "lost"), ("yes", "won")])

print("\nthe page section")
html = NB.section(st)
check("all seven rules are listed", all(f"<b>{k}</b>" in html for k in NR.RULES), True)
check("and the entries table carries them", "R1" in html and "HOU @ SA" in html, True)

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
