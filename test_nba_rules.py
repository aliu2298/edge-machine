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
r4no = lambda *noes: [(p["strike"], p["price"]) for p in NR.team_picks(
    ww, [mkt("SA", 100.5 + i, round(1 - n, 2), round(1 - n + 0.02, 2)) for i, n in enumerate(noes)], NOW)
    if p["rule"] == "R4" and p["team"] == "SA"]
check("R4 floor (2026-10-22): a NO at 0.24 is refused", r4no(0.24), [])
check("  0.25 is accepted", r4no(0.25), [(100.5, 0.25)])
check("  0.45 is accepted", r4no(0.45), [(100.5, 0.45)])
check("  0.46 is refused", r4no(0.46), [])
check("  the cheapest at or above the floor is picked: 0.06 and 0.07 pennies skipped, 0.31 over 0.38",
      r4no(0.06, 0.07, 0.38, 0.31), [(103.5, 0.31)])
check("  equal prices go to the higher strike", r4no(0.30, 0.30), [(101.5, 0.3)])
check("the label says NO 25-45c", NR.RULES["R4"]["label"], "O−D− v O−D− · team total 100-110 · cheapest NO 25-45c")
print("\nR2 retired from 2026-10-24: no new entries, rows kept, R1/R6/R7 unchanged")
THEN = dt.datetime(2026, 10, 23, 22, 0, tzinfo=UTC)          # the day before
ON = dt.datetime(2026, 10, 24, 22, 0, tzinfo=UTC)
op = game("O+D+", "O-D+")
opm = [mkt("SA", 104.5, .80, .82), mkt("SA", 109.5, .68, .70), mkt("SA", 114.5, .50, .53)]
rules_at = lambda g_, ms_, when: sorted((p["rule"], p["strike"], p["price"]) for p in NR.team_picks(g_, ms_, when) if p["team"] == "SA")
check("the day before, R2 still enters (115+ YES at 53c)", ("R2", 114.5, 0.53) in rules_at(op, opm, THEN), True)
check("from 2026-10-24 R2 enters nothing", [r for r in rules_at(op, opm, ON) if r[0] == "R2"], [])
check("  and R1 and R6 are exactly as before",
      [r for r in rules_at(op, opm, ON) if r[0] != "R2"], [r for r in rules_at(op, opm, THEN) if r[0] != "R2"])
check("Eastern date: 03:00Z on Oct 24 is still Oct 23 in New York, so R2 is not yet retired",
      NR.retired("R2", dt.datetime(2026, 10, 24, 3, 0, tzinfo=UTC)), False)
check("  and 05:00Z on Oct 24 is retired", NR.retired("R2", dt.datetime(2026, 10, 24, 5, 0, tzinfo=UTC)), True)
check("2026-10-28: every rule is retired, R2 on its own earlier day",
      (sorted(NR.RETIRED), NR.RETIRED["R2"]["on"], {k: v["on"] for k, v in NR.RETIRED.items() if k != "R2"} == {k: "2026-10-28" for k in "R1 R3 R4 R5 R6 R7".split()}),
      (["R1", "R2", "R3", "R4", "R5", "R6", "R7"], "2026-10-24", True))
EDGE = dt.datetime(2026, 10, 28, 5, 0, tzinfo=UTC)           # 01:00 ET on the 28th
check("Eastern date: 03:00Z on Oct 28 is still Oct 27 (not retired), 05:00Z is",
      (NR.retired("R6", dt.datetime(2026, 10, 28, 3, 0, tzinfo=UTC)), NR.retired("R6", EDGE)), (False, True))
allg = game("O+D+", "O-D-")
allm = [mkt("SA", 104.5, .80, .82), mkt("SA", 109.5, .68, .70), mkt("HOU", 114.5, .50, .53), mkt("HOU", 99.5, .30, .33),
        mkt("SA", 114.5, .50, .53)]
check("before the 28th the labels still enter rules; from the 28th team_picks enters nothing",
      (bool(NR.team_picks(allg, allm, dt.datetime(2026, 10, 27, 22, 0, tzinfo=UTC))), NR.team_picks(allg, allm, EDGE)), (True, []))
h1r = [dict(ticker="KXNBA1HTOTAL-26OCT28HOUSAS-114", floor_strike=114.5, status="active", yes_bid_dollars="0.52", yes_ask_dollars="0.55")]
check("R5 (first half) enters nothing from the 28th",
      NR.half_picks(game("O+D+", "O+D+", home_h1="O-D-"), h1r, EDGE), [])
dd2 = game("O+D-", "O-D-")
d7 = [mkt("SA", 109.5, .52, .55), mkt("SA", 114.5, .40, .42), mkt("HOU", 109.5, .45, .48)]
check("both D-: R1 and R2 stand aside and R7 fires, before and after the retirement",
      rules_at(dd2, d7, THEN) == rules_at(dd2, d7, ON) and [r[0] for r in rules_at(dd2, d7, ON)] == ["R7"], True)
st_r2 = {"rules": {k: {"picks": []} for k in NR.RULES}}
st_r2["rules"]["R2"]["picks"].append(dict(id="R2:old", rule="R2", game="g0", team="SA", status="lost", profit=-100.0, price=0.5,
                                          side="yes", match="a @ b", start="2026-10-20T00:00:00+00:00", ticker="T-old"))
before = [dict(p) for p in st_r2["rules"]["R2"]["picks"]]
gm = game("O+D+", "O-D+")
NR.run(st_r2, [gm], ON, lambda path: {"markets": []})
check("run() leaves the existing R2 rows exactly as they were", st_r2["rules"]["R2"]["picks"], before)
html_r2 = NB.section(st_r2)
check("the NBA page shows R2 as Retired with its dated reason and its final record",
      ("Retired 2026-10-24" in html_r2, "overs priced above hit rate in the ladder tracker" in html_r2, "(all retired)" in html_r2),
      (True, True, True))

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
