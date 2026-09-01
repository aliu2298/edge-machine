#!/usr/bin/env python3
"""test_streaks.py — logic tests for the streaks pipeline.

Runs against synthetic fixtures with hand-computed answers (so a wrong result is a real
bug, not a data quirk) plus consistency checks over the live ESPN pull.

Usage:  python3 test_streaks.py
"""
import datetime, collections, sys

import streaks_build as B
import streaks_track as T

FAILS = []


def check(name, got, want):
    if got != want:
        FAILS.append(f"{name}: got {got!r}, want {want!r}")
        print(f"  FAIL {name}: got {got!r}, want {want!r}")
    else:
        print(f"  ok   {name}")


def fx(date, home, away, hg, ag, league="L1", played=True):
    return {"date": date, "kickoff": f"{date}T12:00Z", "league": league,
            "league_slug": "x", "home": home, "away": away,
            "home_id": home, "away_id": away,
            "home_goals": hg if played else None,
            "away_goals": ag if played else None, "played": played}


print("\n== run_length ==")
# newest first; run must stop at the first failure
games = [{"gf": 2, "ga": 1}, {"gf": 3, "ga": 0}, {"gf": 0, "ga": 1}, {"gf": 5, "ga": 2}]
check("scored2+ stops at the 0", B.run_length(games, lambda gf, ga: gf >= 2), 2)
check("conceded1+ stops at the clean sheet",
      B.run_length(games, lambda gf, ga: ga >= 1), 1)
check("no run", B.run_length(games, lambda gf, ga: gf > 99), 0)
check("caps at FORM_GAMES",
      B.run_length([{"gf": 9, "ga": 9}] * 20, lambda gf, ga: gf >= 1), B.FORM_GAMES)

print("\n== team_games: perspective flip ==")
bt = B.team_games([fx("2026-01-01", "A", "B", 3, 1)])
check("home gf", bt["A"][0]["gf"], 3)
check("home ga", bt["A"][0]["ga"], 1)
check("away gf (flipped)", bt["B"][0]["gf"], 1)
check("away ga (flipped)", bt["B"][0]["ga"], 3)
check("home flag A", bt["A"][0]["home"], True)
check("home flag B", bt["B"][0]["home"], False)

print("\n== team_games: ordering is newest-first ==")
bt = B.team_games([fx("2026-01-01", "A", "B", 1, 0),
                   fx("2026-03-01", "A", "C", 2, 0),
                   fx("2026-02-01", "A", "D", 3, 0)])
check("dates descending", [g["date"] for g in bt["A"]],
      ["2026-03-01", "2026-02-01", "2026-01-01"])

print("\n== team_games: unplayed and null scores excluded ==")
bt = B.team_games([fx("2026-01-01", "A", "B", None, None, played=False),
                   fx("2026-01-02", "A", "C", 1, 1)])
check("only the played game counts", len(bt["A"]), 1)

print("\n== form_seq: highlight is a clean prefix of length run_len ==")
seq = B.form_seq([{"gf": 2, "ga": 2, "opp": "X", "home": True}] * 6, 3)
check("first 3 lit", [g["hit"] for g in seq], [True, True, True, False, False, False])
check("run 0 lights nothing", [g["hit"] for g in B.form_seq(
    [{"gf": 1, "ga": 1, "opp": "X", "home": True}] * 3, 0)], [False, False, False])

print("\n== base_rates ==")
streaks = {
    "t1": {"runs": {"btts": 6}, "played": 9, "recent": []},
    "t2": {"runs": {"btts": 3}, "played": 9, "recent": []},
    "t3": {"runs": {}, "played": 9, "recent": []},
    "t4": {"runs": {}, "played": 9, "recent": []},
}
r = B.base_rates(streaks)
check("btts >=3 is 2 of 4", round(r["btts"][3], 3), 0.5)
check("btts >=6 is 1 of 4", round(r["btts"][6], 3), 0.25)
check("unseen streak is 0", r["solid"][3], 0.0)

print("\n== settle_bet ==")
check("btts yes", T.settle_bet({"kind": "btts"}, "A", "B", 1, 1), True)
check("btts no", T.settle_bet({"kind": "btts"}, "A", "B", 3, 0), False)
check("over2.5 boundary 2-1", T.settle_bet({"kind": "total_gte", "n": 3}, "A", "B", 2, 1), True)
check("over2.5 boundary 1-1", T.settle_bet({"kind": "total_gte", "n": 3}, "A", "B", 1, 1), False)
check("under2.5 boundary 1-1", T.settle_bet({"kind": "total_lte", "n": 2}, "A", "B", 1, 1), True)
check("team_gte away side",
      T.settle_bet({"kind": "team_gte", "n": 2, "team": "B"}, "A", "B", 0, 2), True)
check("team_eq 0 home", T.settle_bet({"kind": "team_eq", "n": 0, "team": "A"}, "A", "B", 0, 1), True)
check("unknown team voids",
      T.settle_bet({"kind": "team_gte", "n": 1, "team": "Z"}, "A", "B", 1, 1), None)
check("unknown kind voids", T.settle_bet({"kind": "nope"}, "A", "B", 1, 1), None)

print("\n== find_leads: end-to-end on a built scenario ==")
# A scores 2+ in 6 straight; B concedes 2+ in 6 straight; they meet in the future.
rows = []
for i in range(6):
    d = f"2026-06-{i+1:02d}"
    rows.append(fx(d, "Aces", f"opp{i}", 3, 0))       # Aces score 3, concede 0
    rows.append(fx(d, f"foe{i}", "Bees", 2, 0))        # Bees concede 2, score 0
future = (datetime.date.today() + datetime.timedelta(days=3)).isoformat()
rows.append(fx(future, "Aces", "Bees", None, None, played=False))
st = B.team_streaks(B.team_games(rows))
rt = B.base_rates(st)
leads = B.find_leads(rows, st, rt)
heads = {l["headline"] for l in leads}
check("Aces scoring run detected", st["Aces"]["runs"].get("scoring"), 6)
check("Bees leaky run detected", st["Bees"]["runs"].get("leaky"), 6)
check("'to score 2+' lead present", "Aces to score 2+" in heads, True)
sc = [l for l in leads if l["headline"] == "Aces to score 2+"][0]
check("bet subject resolved to the right team", sc["bet"]["team"], "Aces")
check("bet is team_gte 2", (sc["bet"]["kind"], sc["bet"]["n"]), ("team_gte", 2))
check("no lead points at a played fixture",
      all(l["date"] >= datetime.date.today().isoformat() for l in leads), True)

print("\n== find_leads: symmetric pairings are not double-listed ==")
rows = []
for i in range(6):
    d = f"2026-06-{i+1:02d}"
    rows.append(fx(d, "Cats", f"o{i}", 1, 1))          # BTTS every game
    rows.append(fx(d, "Dogs", f"p{i}", 2, 1))          # BTTS every game
rows.append(fx(future, "Cats", "Dogs", None, None, played=False))
st = B.team_streaks(B.team_games(rows))
leads = B.find_leads(rows, st, B.base_rates(st))
btts = [l for l in leads if l["headline"] == "Both teams to score"]
check("one BTTS card, not two orientations", len(btts), 1)

print("\n== find_leads: weaker restatement is dropped ==")
# Aces/Bees again: scoring+leaky and scoring+porous both qualify; keep the sharper one.
rows = []
for i in range(6):
    d = f"2026-06-{i+1:02d}"
    rows.append(fx(d, "Aces", f"opp{i}", 3, 0))
    rows.append(fx(d, f"foe{i}", "Bees", 2, 0))
rows.append(fx(future, "Aces", "Bees", None, None, played=False))
st = B.team_streaks(B.team_games(rows))
leads = B.find_leads(rows, st, B.base_rates(st))
aces = [l for l in leads if l["a"] == "Aces" and l["a_key"] == "scoring"]
check("only one scoring-side card for Aces", len(aces), 1)
check("kept the sharper (leaky) leg", aces[0]["b_key"], "leaky")

print("\n== population_rates ==")
pool = [fx("2026-01-01", "A", "B", 1, 1),    # btts, total 2
        fx("2026-01-02", "C", "D", 3, 0),    # no btts, total 3
        fx("2026-01-03", "E", "F", 2, 2)]    # btts, total 4
p = T.population_rates(pool)
check("btts 2 of 3", round(p["btts"], 3), round(2/3, 3))
check("over2.5 2 of 3", round(p["total_gte:3"], 3), round(2/3, 3))
check("under2.5 1 of 3", round(p["total_lte:2"], 3), round(1/3, 3))
check("team scored 1+ = 5 of 6 team-games", round(p["team_gte:1"], 3), round(5/6, 3))
check("team failed to score = 1 of 6", round(p["team_eq:0"], 3), round(1/6, 3))

print("\n== record / grade lifecycle ==")
played = fx("2026-01-05", "H", "A", 2, 1)
lead = {"date": "2026-01-05", "kickoff": None, "league": "L1", "match": "H v A",
        "home": "H", "away": "A", "headline": "Both teams to score",
        "bet": {"kind": "btts"}, "a": "H", "b": "A", "a_run": 4, "b_run": 4,
        "a_key": "btts", "b_key": "btts", "base_rate": 0.1, "strength": 8}
blob, added = T.record([lead], {"leads": {}})
check("recorded once", added, 1)
blob, added2 = T.record([lead], blob)
check("re-record is a no-op", added2, 0)
blob, n = T.grade([played], blob)
check("graded one", n, 1)
e = list(blob["leads"].values())[0]
check("status hit", e["status"], "hit")
check("final recorded", e["final"], "2-1")
blob, n2 = T.grade([played], blob)
check("re-grade is a no-op", n2, 0)

print("\n== grade: a miss is a miss, not a void ==")
blob, _ = T.record([dict(lead, headline="Over 2.5 goals",
                         bet={"kind": "total_gte", "n": 3})], {"leads": {}})
blob, _ = T.grade([fx("2026-01-05", "H", "A", 1, 1)], blob)
check("miss", list(blob["leads"].values())[0]["status"], "miss")

print("\n== grade: unplayed fixture stays pending ==")
blob, _ = T.record([dict(lead, date=future)], {"leads": {}})
blob, n = T.grade([], blob)
check("still pending", list(blob["leads"].values())[0]["status"], "pending")

print("\n== lead_id stability ==")
a = T.lead_id(lead)
b = T.lead_id(dict(lead, a_run=6, b_run=5, base_rate=0.02))
check("id ignores run lengths", a, b)
c = T.lead_id(dict(lead, headline="Over 2.5 goals"))
check("id distinguishes different claims", a != c, True)

print("\n== find_leads: a match already under way is not a lead ==")
now = datetime.datetime.now(datetime.timezone.utc)
rows = []
for i in range(6):
    d = f"2026-06-{i+1:02d}"
    rows.append(fx(d, "Aces", f"opp{i}", 3, 0))
    rows.append(fx(d, f"foe{i}", "Bees", 2, 0))
# same UTC DAY as now, but kicked off two hours ago — the date-only filter kept these
started = fx(now.date().isoformat(), "Aces", "Bees", None, None, played=False)
started["kickoff"] = (now - datetime.timedelta(hours=2)).strftime("%Y-%m-%dT%H:%MZ")
st = B.team_streaks(B.team_games(rows + [started]))
check("no lead on an in-progress match",
      len(B.find_leads(rows + [started], st, B.base_rates(st))), 0)
# the same fixture two hours from now IS a lead
soon = dict(started, kickoff=(now + datetime.timedelta(hours=2)).strftime("%Y-%m-%dT%H:%MZ"))
check("a match two hours out is a lead",
      len(B.find_leads(rows + [soon], st, B.base_rates(st))) > 0, True)

print("\n== leads are ordered by kickoff ==")
rows2 = list(rows)
for h, off in (("Zulu", 50), ("Alpha", 10), ("Mike", 30)):
    for i in range(6):
        rows2.append(fx(f"2026-06-{i+1:02d}", h, f"q{h}{i}", 2, 2))
mk = []
for h, off in (("Zulu", 50), ("Alpha", 10), ("Mike", 30)):
    g = fx((now + datetime.timedelta(hours=off)).date().isoformat(), h, "Bees",
           None, None, played=False)
    g["kickoff"] = (now + datetime.timedelta(hours=off)).strftime("%Y-%m-%dT%H:%MZ")
    mk.append(g)
st2 = B.team_streaks(B.team_games(rows2))
got = B.find_leads(rows2 + mk, st2, B.base_rates(st2))
kos = [l["kickoff"] for l in got]
check("kickoffs ascending", kos, sorted(kos))

print("\n== kickoff_dt ==")
check("parses ESPN Z form",
      B.kickoff_dt({"kickoff": "2026-08-30T10:15Z"}).hour, 10)
check("None when absent", B.kickoff_dt({}), None)
check("None when unparseable", B.kickoff_dt({"kickoff": "not-a-date"}), None)

print("\n== over 2.5 implies over 1.5: only the sharper card survives ==")
rows = []
for i in range(6):
    d = f"2026-06-{i+1:02d}"
    rows.append(fx(d, "Goals", f"o{i}", 3, 1))     # total 4 -> over 2.5 AND over 1.5
    rows.append(fx(d, "Nets", f"p{i}", 2, 2))      # total 4 -> both
rows.append(fx(future, "Goals", "Nets", None, None, played=False))
st = B.team_streaks(B.team_games(rows))
got = B.find_leads(rows, st, B.base_rates(st))
heads = [l["headline"] for l in got]
check("Over 2.5 card present", "Over 2.5 goals" in heads, True)
check("Over 1.5 card suppressed", "Over 1.5 goals" in heads, False)

print("\n== one claim, one card: identical headline never duplicates ==")
import collections as _c
dupes = [k for k, v in _c.Counter((l["match"], l["headline"]) for l in got).items() if v > 1]
check("no duplicated headline on a fixture", dupes, [])

print("\n== live-data consistency ==")
try:
    import streaks_fetch
    live = streaks_fetch.load_or_fetch()["fixtures"]
    seen = collections.Counter((f["date"], f["home"], f["away"]) for f in live)
    dupes = [k for k, v in seen.items() if v > 1]
    check("no duplicate fixtures in the ESPN pull", len(dupes), 0)
    if dupes:
        print("      e.g.", dupes[:3])
    bad = [f for f in live if f["played"] and
           (f["home_goals"] is None or f["away_goals"] is None)]
    check("every played fixture has both scores", len(bad), 0)
    neg = [f for f in live if f["played"] and
           (f["home_goals"] < 0 or f["away_goals"] < 0)]
    check("no negative scores", len(neg), 0)
    fut = [f for f in live if not f["played"] and f["home_goals"] is not None]
    check("unplayed fixtures carry no score", len(fut), 0)
except Exception as ex:
    print(f"  (live checks skipped: {ex})")

print()
if FAILS:
    print(f"{len(FAILS)} FAILURE(S)")
    for f in FAILS:
        print(" -", f)
    sys.exit(1)
print("all logic tests passed")
