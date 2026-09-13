#!/usr/bin/env python3
"""test_today.py — logic tests for the Today page (today_build.py).

Synthetic fixtures and ledgers, no network. Usage:  python3 test_today.py
"""
import datetime, sys

import streaks_build as B
import today_build as TB

FAILS = []


def check(name, got, want):
    if got != want:
        FAILS.append(f"{name}: got {got!r}, want {want!r}")
        print(f"  FAIL {name}: got {got!r}, want {want!r}")
    else:
        print(f"  ok   {name}")


B.venue_market_link = lambda f: None             # no venue scan in tests
UTC = datetime.timezone.utc
NOW = datetime.datetime(2026, 9, 12, 20, 0, tzinfo=UTC)     # 3pm Central, Sep 12


def ko(dt):
    return dt.strftime("%Y-%m-%dT%H:%MZ")


def played(day, home, away, hg, ag, league="L1"):
    d = datetime.datetime(2026, 9, day, 15, 0, tzinfo=UTC)
    return {"date": d.date().isoformat(), "kickoff": ko(d), "league": league, "home": home,
            "away": away, "played": True, "home_goals": hg, "away_goals": ag}


def sched(dt, home, away, league="L1"):
    return {"date": dt.date().isoformat(), "kickoff": ko(dt), "league": league,
            "home": home, "away": away, "played": False, "home_goals": None,
            "away_goals": None}


# H scores 2+ in its six games before today; A has only 3 games. Both play today.
history = [played(d, "H", f"X{d}", 3, 1) for d in range(1, 7)]
history += [played(d, f"Y{d}", "A", 1, 1) for d in (2, 4, 6)]
history += [played(d, "C", f"Z{d}", 0, 0) for d in range(1, 7)]
history += [played(d, f"W{d}", "D", 2, 2) for d in range(1, 7)]

morning = datetime.datetime(2026, 9, 12, 15, 0, tzinfo=UTC)
evening = datetime.datetime(2026, 9, 12, 19, 0, tzinfo=UTC)   # kicked off 1h ago
tomorrow = datetime.datetime(2026, 9, 13, 17, 0, tzinfo=UTC)

fixtures = history + [
    played(12, "H", "A", 2, 0),                 # finished today
    # C v D kicked off at 19:00Z and is in progress: ESPN drops it from the feed
    sched(tomorrow, "C", "H"),
]
# played(12,...) is stamped 15:00Z = morning
ledger = {
    "2026-09-12|H|A|H to score 2+": {
        "date": "2026-09-12", "home": "H", "away": "A", "headline": "H to score 2+",
        "kickoff": ko(morning), "league": "L1", "status": "hit", "final": "2-0",
        "bet": {"kind": "team_gte", "n": 2, "team": "H"},
        "prices": {"team2plus": {"price": 1.8, "fair": 0.52}},
        "pnl": {"team2plus": {"hit": True, "pnl": 0.8}}},
    "2026-09-12|H|A|H to score": {
        "date": "2026-09-12", "home": "H", "away": "A", "headline": "H to score",
        "kickoff": ko(morning), "league": "L1", "status": "hit", "final": "2-0",
        "bet": {"kind": "team_gte", "n": 1, "team": "H"}},
    "2026-09-12|C|D|Over 1.5 goals": {
        "date": "2026-09-12", "home": "C", "away": "D", "headline": "Over 1.5 goals",
        "kickoff": ko(evening), "league": "L1", "status": "pending",
        "bet": {"kind": "total_gte", "n": 2}},
}
book = {
    "2026-09-12|H|A": {
        "date": "2026-09-12", "home": "H", "away": "A", "kickoff": ko(morning),
        "league": "L1", "status": "graded", "final": "2-0",
        "prices": {"over15": {"price": 1.25, "fair": 0.78},
                   "btts": {"price": 1.8, "fair": 0.52}},
        "model": {"over15": 0.90, "btts": 0.40},
        "result": {"over15": True, "btts": False},
        "pnl": {"over15": 0.25, "btts": -1.0}},
    "2026-09-12|C|D": {
        "date": "2026-09-12", "home": "C", "away": "D", "kickoff": ko(evening),
        "league": "L1", "status": "pending",
        "prices": {"over25": {"price": 2.1, "fair": 0.45}}, "model": {"over25": 0.46}},
}
published = [{"date": "2026-09-13", "home": "C", "away": "H", "headline": "Over 1.5 goals",
              "kickoff": ko(tomorrow), "league": "L1"}]

data = TB.gather(now=NOW, fixtures=fixtures, ledger=ledger, published=published, book=book)
today = {r["match"]: r for r in data["today"]["rows"]}

print("leads survive kickoff (read from the ledger)")
ha = today["H v A"]
check("finished fixture keeps its leads", len(ha["leads"]), 2)
lead2 = next(l for l in ha["leads"] if l["headline"] == "H to score 2+")
check("lead price from its claim market", (lead2["price"], lead2["fair"]), (1.8, 0.52))
check("lead result and pnl", (lead2["status"], lead2["pnl"]), ("hit", 0.8))
lead1 = next(l for l in ha["leads"] if l["headline"] == "H to score")
check("unpriceable claim: hit, no pnl", (lead1["status"], lead1["pnl"], lead1["claim"]),
      ("hit", None, None))
check("finished fixture has no why-not", ha["why_not"], [])

print("in-play games are filled in")
check("C v D present though missing from the feed", "C v D" in today, True)
cd = today["C v D"]
check("state live", (cd["state"], cd["in_feed"], cd["played"]), ("live", False, False))
check("live fixture carries its lead", [l["headline"] for l in cd["leads"]], ["Over 1.5 goals"])
check("live fixture carries its book line", [m["mk"] for m in cd["markets"]], ["over25"])
check("ungraded market has no result", cd["markets"][0]["hit"], None)
check("summary counts in play", data["today"]["summary"]["live"], 1)

print("results on markets and the scoreboard")
mk = {m["mk"]: m for m in ha["markets"]}
check("over15 hit + value flag", (mk["over15"]["hit"], mk["over15"]["pnl"], mk["over15"]["value"]),
      (True, 0.25, True))
check("btts miss", (mk["btts"]["hit"], mk["btts"]["pnl"]), (False, -1.0))
board = {r["key"]: r for r in data["today"]["summary"]["board"]}
check("leads row: 2 graded, 2 hits, 1 priced, +0.8",
      (board["leads"]["n"], board["leads"]["hits"], board["leads"]["priced"], board["leads"]["pnl"]),
      (2, 2, 1, 0.8))
check("all markets", (board["all"]["n"], board["all"]["hits"], board["all"]["pnl"]), (2, 1, -0.75))
check("split on/off lead fixtures", (board["on"]["n"], board["off"]["n"]), (2, 0))
check("value flags", (board["flags"]["n"], board["flags"]["pnl"]), (1, 0.25))
check("leads priced tile", (data["today"]["summary"]["leads"],
                            data["today"]["summary"]["leads_priced"]), (3, 1))

print("tomorrow view")
tm = {r["match"]: r for r in data["tomorrow"]["rows"]}
check("tomorrow has its fixture", list(tm), ["C v H"])
check("published lead not yet in the ledger shows", [l["headline"] for l in tm["C v H"]["leads"]],
      ["Over 1.5 goals"])
check("tomorrow upcoming", tm["C v H"]["state"], "upcoming")
check("tomorrow not in today", "C v H" in today, False)

print("why-not uses form at kickoff and names thin teams correctly")
by_team = B.team_games(fixtures)
check("thin team: game count, not 'no games'",
      TB.why_not("H", "A", by_team, "2026-09-12"),
      ["A: only 3 games (needs 5)"])
check("unknown team", TB.why_not("Q", "H", by_team, "2026-09-12")[0],
      "Q: no competitive games on record")
# the finished 2-0 today must not count toward form going into it
check("form before excludes the day itself",
      len(TB.form_before(by_team, "H", "2026-09-12")), 6)
check("form after includes it", len(TB.form_before(by_team, "H", "2026-09-13")), 7)

print("rescheduled fixtures are not ghosts; withdrawn leads are not scored")
import streaks_track as T
# ESPN first listed C v D on the 12th (a placeholder), then moved it to the 14th. The ledger
# still holds a lead under the old date; the feed only knows the new one.
_moved_ledger = dict(ledger)
_moved_ledger["2026-09-12|C|D|Old placeholder lead"] = {
    "date": "2026-09-12", "home": "C", "away": "D", "headline": "Old placeholder lead",
    "kickoff": ko(evening - datetime.timedelta(hours=2)), "league": "L1", "status": "pending",
    "bet": {"kind": "total_gte", "n": 2}}
_fx_moved = fixtures + [sched(datetime.datetime(2026, 9, 14, 17, 0, tzinfo=UTC), "C", "D")]
_d2 = TB.gather(now=NOW, fixtures=_fx_moved, ledger=_moved_ledger, published=[], book={})
check("a ledger row for a fixture ESPN has moved is not shown as in play",
      [r["match"] for r in _d2["today"]["rows"] if not r["in_feed"]], [])
_d3 = TB.gather(now=NOW, fixtures=fixtures, ledger=ledger, published=published, book=book)
check("a game genuinely missing from the feed is still filled in",
      [r["match"] for r in _d3["today"]["rows"] if not r["in_feed"]], ["C v D"])

_wd_ledger = dict(ledger)
_wd_ledger["2026-09-12|H|A|H to score 2+"] = dict(ledger["2026-09-12|H|A|H to score 2+"],
                                                  withdrawn_at="2026-09-12T06:00:00+00:00")
_d4 = TB.gather(now=NOW, fixtures=fixtures, ledger=_wd_ledger, published=[], book=book)
_ha = {r["match"]: r for r in _d4["today"]["rows"]}["H v A"]
check("a withdrawn lead is still shown, tagged",
      sorted((l["headline"], l["withdrawn"]) for l in _ha["leads"]),
      [("H to score", False), ("H to score 2+", True)])
_b4 = {r["key"]: r for r in _d4["today"]["summary"]["board"]}
check("but not scored: the leads row counts only the lead still published at kickoff",
      (_b4["leads"]["n"], _b4["leads"]["priced"]), (1, 0))
check("and the summary counts it apart", (_d4["today"]["summary"]["leads"], _d4["today"]["summary"]["withdrawn"]), (2, 1))

print("value flags against the price paid")
_venue_q = {"price": round(1 / 0.62, 3), "fair": 0.60, "venue": "kalshi"}
_bov_q = {"price": 1.67, "fair": 0.57}
check("exchange quote: model 0.66 v midpoint 0.60 is +6pp, but v 0.62 paid only +4pp -> not value",
      T.is_value(0.66, _venue_q), False)
check("exchange quote: model 0.68 v 0.62 paid -> value", T.is_value(0.68, _venue_q), True)
check("Bovada quote keeps the pre-registered rule: model 0.62 v fair 0.57 -> value", T.is_value(0.62, _bov_q), True)
check("no model, no flag", T.is_value(None, _venue_q), False)
_vbook = {k: dict(v) for k, v in book.items()}
_vbook["2026-09-12|H|A"]["prices"] = {"over15": {"price": round(1 / 0.80, 3), "fair": 0.78, "venue": "polymarket_us"}}
_vbook["2026-09-12|H|A"]["model"] = {"over15": 0.84}
_vbook["2026-09-12|H|A"]["result"] = {"over15": True}
_vbook["2026-09-12|H|A"]["pnl"] = {"over15": 0.25}
_d5 = TB.gather(now=NOW, fixtures=fixtures, ledger=ledger, published=[], book=_vbook)
_m5 = {r["match"]: r for r in _d5["today"]["rows"]}["H v A"]["markets"][0]
check("a venue chip carries its source", _m5["source"], "polymarket_us")
check("and is not flagged when the model clears the midpoint but not the price", _m5["value"], False)

print("page renders")
html = TB.page_html(data, "now")
check("day tabs present", 'data-dy="tomorrow"' in html, True)
check("payload embedded", '"tomorrow"' in html and "const DATA" in html, True)

print()
if FAILS:
    print(f"{len(FAILS)} FAILED")
    sys.exit(1)
print("all passed")
