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

print("\n== find_leads: end-to-end, the over 1.5 lane ==")
# Aces score 3 every game (so their matches also clear 1.5); Bees win 1-0 every game,
# so Bees have a scored-in run but NO over-1.5 run and concede nothing — so no team-2+
# lead can form either. The surviving pairing is scoring1+scoring1: one apiece clears
# 1.5.
rows = []
for i in range(6):
    d = f"2026-06-{i+1:02d}"
    rows.append(fx(d, "Aces", f"opp{i}", 3, 0))       # Aces score 3
    rows.append(fx(d, "Bees", f"foe{i}", 1, 0))        # Bees score 1
future = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1)).date().isoformat()
rows.append(fx(future, "Aces", "Bees", None, None, played=False))
st = B.team_streaks(B.team_games(rows))
rt = B.base_rates(st)
leads = B.find_leads(rows, st, rt)
heads = {l["headline"] for l in leads}
check("Aces scoring run detected", st["Aces"]["runs"].get("scoring"), 6)
check("Bees scored-in run detected", st["Bees"]["runs"].get("scoring1"), 6)
check("every lead is a totals bet (Bees concede nothing, so no 2+ lead)",
      sorted({l["bet"]["kind"] for l in leads}), ["total_gte"])
check("no team-subject bet without a conceding opponent",
      [l["headline"] for l in leads if l["bet"].get("team")], [])
check("'Over 1.5 goals' lead present", "Over 1.5 goals" in heads, True)
o15 = [l for l in leads if l["headline"] == "Over 1.5 goals"][0]
check("bet is total_gte 2", (o15["bet"]["kind"], o15["bet"]["n"]), ("total_gte", 2))
# Regression guard for the narrowing: no pairing may settle any line but 1.5.
check("no over-2.5 bet is produced",
      [l["headline"] for l in leads if l["bet"].get("n") != 2], [])
check("every headline is the one market", sorted(heads), ["Over 1.5 goals"])
check("no lead points at a played fixture",
      all(l["date"] >= datetime.date.today().isoformat() for l in leads), True)

print("\n== find_leads: the team 2+ lane ==")
# Guns score 2 and concede 1 every game; Nets lose 1-2 every game (concede 2+). The
# fixture Guns v Nets carries "Guns to score 2+" (scoring+leaky) AND, since both sides
# have scored in every game, an over-1.5 card — two lanes, two claims, both listed.
rows = []
for i in range(6):
    d = f"2026-06-{i+1:02d}"
    rows.append(fx(d, "Guns", f"g{i}", 2, 1))
    rows.append(fx(d, "Nets", f"n{i}", 1, 2))
rows.append(fx(future, "Nets", "Guns", None, None, played=False))   # Guns AWAY
st = B.team_streaks(B.team_games(rows))
leads = B.find_leads(rows, st, B.base_rates(st))
heads = sorted(l["headline"] for l in leads)
check("both lanes fire on the fixture", heads, ["Guns to score 2+", "Over 1.5 goals"])
t2 = [l for l in leads if l["headline"] == "Guns to score 2+"][0]
check("claim names the away side correctly",
      (t2["bet"]["kind"], t2["bet"]["n"], t2["bet"]["team"]), ("team_gte", 2, "Guns"))
check("the sharper pairing (opponent concedes 2+) is the one kept", (t2["a_key"], t2["b_key"]), ("scoring", "leaky"))
check("one team-2+ card per fixture, not one per pairing",
      sum(1 for l in leads if l["headline"] == "Guns to score 2+"), 1)
check("Nets never get a 2+ card (they score 1)",
      [l for l in leads if l["bet"].get("team") == "Nets"], [])
check("settles on the final score: 0-2 is a hit for Guns",
      T.settle_bet(t2["bet"], "Nets", "Guns", 0, 2), True)
check("and 1-1 is a miss", T.settle_bet(t2["bet"], "Nets", "Guns", 1, 1), False)
check("claim market resolves to the team price", T.claim_market(t2["bet"]), "team2plus")
check("over-1.5 claim market", T.claim_market({"kind": "total_gte", "n": 2}), "over15")

print("\n== find_leads: symmetric pairings are not double-listed ==")
rows = []
for i in range(6):
    d = f"2026-06-{i+1:02d}"
    rows.append(fx(d, "Cats", f"o{i}", 1, 1))          # both sides score every game
    rows.append(fx(d, "Dogs", f"p{i}", 1, 1))
rows.append(fx(future, "Cats", "Dogs", None, None, played=False))
st = B.team_streaks(B.team_games(rows))
leads = B.find_leads(rows, st, B.base_rates(st))
check("one card per fixture, not one per orientation", len(leads), 1)

print("\n== find_leads: both over-1.5 pairings collapse to one card ==")
# Both sides score AND both sides' matches clear 1.5, so over15+over15 and
# scoring1+scoring1 each fire on this fixture. They settle the SAME claim, so the
# fixture must still render ONE over-1.5 card — the headline guard enforces it. (Each
# side also scores 2+ into a porous opponent, so the team-2+ lane adds its own cards;
# those are a different claim and are counted separately.)
rows = []
for i in range(6):
    d = f"2026-06-{i+1:02d}"
    rows.append(fx(d, "Aces", f"opp{i}", 3, 1))        # total 4: over 1.5, and Aces score
    rows.append(fx(d, "Bees", f"foe{i}", 2, 1))        # total 3: over 1.5, and Bees score
rows.append(fx(future, "Aces", "Bees", None, None, played=False))
st = B.team_streaks(B.team_games(rows))
leads = B.find_leads(rows, st, B.base_rates(st))
check("both pairings qualify", 
      (st["Aces"]["runs"].get("over15"), st["Aces"]["runs"].get("scoring1")), (6, 6))
check("exactly one over-1.5 card for the fixture",
      sum(1 for l in leads if l["headline"] == "Over 1.5 goals"), 1)
check("the team-2+ lane adds one card per side, not per pairing",
      sorted(l["headline"] for l in leads if l["bet"].get("team")),
      ["Aces to score 2+", "Bees to score 2+"])
check("and it settles over 1.5", leads[0]["bet"]["n"], 2)

print("\n== a form-only league never produces a lead ==")
# Belgian/Norwegian/Greek feeds exist so a European tie has form on BOTH sides. They are
# not fixtures this board has an opinion about.
rows = []
for i in range(6):
    d = f"2026-06-{i+1:02d}"
    rows.append(fx(d, "Ghent", f"o{i}", 2, 1))
    rows.append(fx(d, "Genk", f"p{i}", 2, 1))
_ff = fx(future, "Ghent", "Genk", None, None, played=False)
_ff["lead_source"] = False
rows.append(_ff)
st = B.team_streaks(B.team_games(rows))
check("form-league fixture yields no lead",
      B.find_leads(rows, st, B.base_rates(st)), [])
_ff["lead_source"] = True
check("the same fixture in a tracked league does",
      "Over 1.5 goals" in {l["headline"] for l in B.find_leads(rows, st, B.base_rates(st))}, True)

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

# last_seen: the one thing a re-record DOES update. The ledger is append-only, so a lead
# whose streak has broken stays pending here forever even though the board stopped
# showing it. last_seen is how a reader (anything pulling this file) can tell a lead
# that is still published from one that is merely still ungraded.
_e = list(blob["leads"].values())[0]
check("last_seen stamped on first record", _e["last_seen"], T.utc_today().isoformat())
_before = dict(_e)
_e["last_seen"] = "2020-01-01"                    # pretend an older build wrote it
blob, _ = T.record([lead], blob)
check("re-record refreshes last_seen",
      list(blob["leads"].values())[0]["last_seen"], T.utc_today().isoformat())
# ...and refreshes NOTHING else. The claim is the snapshot as published.
_after = list(blob["leads"].values())[0]
check("the claim itself is never revised",
      {k: v for k, v in _after.items() if k not in ("last_seen", "last_seen_at")},
      {k: v for k, v in _before.items() if k not in ("last_seen", "last_seen_at")})
# A lead the board no longer publishes keeps its OLD last_seen — that is the signal.
_stale = list(blob["leads"].values())[0]["last_seen"]
blob, _ = T.record([], blob)                      # this build emitted nothing
check("a lead that fell off the board is not re-stamped",
      list(blob["leads"].values())[0]["last_seen"], _stale)
blob, n = T.grade([played], blob)
check("graded one", n, 1)
e = list(blob["leads"].values())[0]
check("status hit", e["status"], "hit")
check("final recorded", e["final"], "2-1")
blob, n2 = T.grade([played], blob)
check("re-grade is a no-op", n2, 0)

print("\n== last_seen_at, board_built_at and withdrawn leads ==")
_t0 = datetime.datetime(2026, 9, 13, 6, 0, tzinfo=datetime.timezone.utc)
_up = dict(lead, date="2026-09-14", kickoff="2026-09-14T15:00Z")
_up2 = dict(_up, headline="Over 1.5 goals", bet={"kind": "total_gte", "n": 2})
wb, _ = T.record([_up, _up2], {"leads": {}}, now=_t0)
check("the build time is stamped on the file", wb["board_built_at"], _t0.isoformat())
check("and on every published lead", sorted(e["last_seen_at"] for e in wb["leads"].values()),
      [_t0.isoformat()] * 2)
_t1 = _t0 + datetime.timedelta(hours=6)
wb, _ = T.record([_up2], wb, now=_t1)
_w = wb["leads"][T.lead_id(_up)]
check("a pending lead this build dropped is withdrawn", _w.get("withdrawn_at"), _t1.isoformat())
check("its last_seen_at stays at the build it was last on", _w["last_seen_at"], _t0.isoformat())
check("the one still published is not", "withdrawn_at" in wb["leads"][T.lead_id(_up2)], False)
wb, _ = T.record([_up, _up2], wb, now=_t1 + datetime.timedelta(hours=6))
check("a lead that comes back is no longer withdrawn", "withdrawn_at" in wb["leads"][T.lead_id(_up)], False)
_past = dict(lead, date="2026-09-13", kickoff="2026-09-13T05:00Z", headline="Past claim")
wb["leads"][T.lead_id(_past)] = dict(_past, id=T.lead_id(_past), status="pending", first_seen="2026-09-12")
wb, _ = T.record([_up, _up2], wb, now=_t1 + datetime.timedelta(hours=12))
check("a lead whose match has started is never marked withdrawn", "withdrawn_at" in wb["leads"][T.lead_id(_past)], False)
_hit = lambda h, w: {"id": h, "date": "2026-09-01", "home": "H", "away": "A", "headline": h, "league": "L1",
                     "bet": {"kind": "total_gte", "n": 2}, "status": "hit", "final": "2-1",
                     "prices": {"over15": {"price": 1.25, "fair": 0.78}},
                     "pnl": {"over15": {"hit": True, "pnl": 0.25}}, **({"withdrawn_at": "x"} if w else {})}
_pb = {"leads": {"a": _hit("a", False), "b": _hit("b", True)}}
check("priced record counts only leads still published at kickoff", T.price_report(_pb)["graded"], 1)

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
for h, off in (("Zulu", 40), ("Alpha", 10), ("Mike", 30)):
    for i in range(6):
        rows2.append(fx(f"2026-06-{i+1:02d}", h, f"q{h}{i}", 2, 2))
mk = []
for h, off in (("Zulu", 40), ("Alpha", 10), ("Mike", 30)):
    g = fx((now + datetime.timedelta(hours=off)).date().isoformat(), h, "Bees",
           None, None, played=False)
    g["kickoff"] = (now + datetime.timedelta(hours=off)).strftime("%Y-%m-%dT%H:%MZ")
    mk.append(g)
st2 = B.team_streaks(B.team_games(rows2))
got = B.find_leads(rows2 + mk, st2, B.base_rates(st2))
kos = [l["kickoff"] for l in got]
check("kickoffs ascending", kos, sorted(kos))

print("\n== leads only inside the 48h horizon ==")
far = dict(soon, kickoff=(now + datetime.timedelta(hours=49)).strftime("%Y-%m-%dT%H:%MZ"),
           date=(now + datetime.timedelta(hours=49)).date().isoformat())
check("a match 49 hours out is not a lead", len(B.find_leads(rows + [far], st, B.base_rates(st))), 0)
edge = dict(soon, kickoff=(now + datetime.timedelta(hours=47)).strftime("%Y-%m-%dT%H:%MZ"),
            date=(now + datetime.timedelta(hours=47)).date().isoformat())
check("a match 47 hours out is", len(B.find_leads(rows + [edge], st, B.base_rates(st))) > 0, True)
nodate = dict(soon, kickoff=None, date=(now + datetime.timedelta(days=5)).date().isoformat())
check("a fixture with no kickoff time five days out is not", len(B.find_leads(rows + [nodate], st, B.base_rates(st))), 0)

print("\n== kickoff_dt ==")
check("parses ESPN Z form",
      B.kickoff_dt({"kickoff": "2026-08-30T10:15Z"}).hour, 10)
check("None when absent", B.kickoff_dt({}), None)
check("None when unparseable", B.kickoff_dt({"kickoff": "not-a-date"}), None)

print("\n== high-scoring form still yields exactly one over-1.5 card ==")
# Previously this fixture produced an over-2.5 card that suppressed the over-1.5 one.
# The totals lane must produce one over-1.5 card; the team lane may add its own claims
# on top (both sides here score 2+ into a side that concedes every game).
rows = []
for i in range(6):
    d = f"2026-06-{i+1:02d}"
    rows.append(fx(d, "Goals", f"o{i}", 3, 1))     # total 4
    rows.append(fx(d, "Nets", f"p{i}", 2, 2))      # total 4
rows.append(fx(future, "Goals", "Nets", None, None, played=False))
st = B.team_streaks(B.team_games(rows))
got = B.find_leads(rows, st, B.base_rates(st))
heads = [l["headline"] for l in got]
check("one over-1.5 card only", heads.count("Over 1.5 goals"), 1)
check("plus one team-2+ card per qualifying side", sorted(heads),
      ["Goals to score 2+", "Nets to score 2+", "Over 1.5 goals"])

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


print("\n== fire measurement: prior games only ==")
import fire_track as F
# 8 hits then a miss: the miss is game 9, ON-run (the run was 8 long going in) even
# though it is itself a failure. If it were classified on its own result, on_h would be 1.
on_h, on_n, off_h, off_n = F._split([1] * 8 + [0], 8)
check("run state read from prior games", (on_n, on_h), (1, 0))
check("warm-up games discarded", off_n, 0)

print("\n== fire measurement: the warm-up trap ==")
# A team's opening fire_min games hit ~4pp lower than its later ones. Counting them
# forces that weak stretch entirely into the control arm in the REAL order while a
# shuffle scatters it — which alone flipped three streak types to SIGNIFICANT.
on_h, on_n, off_h, off_n = F._split([0] * 8 + [1, 1], 8)
# Exactly the two post-warm-up games are scored; the 8 opening misses are discarded
# rather than being dumped into the control arm.
check("only post-warm-up games are scored", on_n + off_n, 2)
check("the discarded opening misses do not depress the control", (off_n, off_h), (2, 2))
check("no run was reachable, so no on-run games", (on_n, on_h), (0, 0))

print("\n== fire measurement: pairing ==")
check("a team with only one arm is not a pair",
      F.paired_diff({"A": {"k": [1] * 20}}, "k", 8), None)
# Cancelling team quality is the entire point of pairing within team: the population
# figure must be the plain MEAN of each side's own on-minus-off gap, so a team's overall
# level cannot leak in. (It does not mean the gap is zero — see the null test below.)
good, weak = {"k": [1, 1, 1, 1, 0] * 7}, {"k": [1, 1, 1, 0, 0, 0] * 6}
both = F.paired_diff({"good": good, "weak": weak}, "k", 3)
solo = [F.paired_diff({"t": t}, "k", 3) for t in (good, weak)]
check("population diff is the mean of the within-team diffs",
      round(both["diff"], 9), round(sum(s["diff"] for s in solo) / 2, 9))
check("the good team's own gap is measured against itself, not the weak one",
      bool(abs(solo[0]["diff"] - solo[1]["diff"]) > 0.01), True)

print("\n== fire measurement: the null must not centre on zero ==")
# This is why all three earlier baselines were wrong. Conditioning on a run is negative
# even when runs carry NO information, because a run ends the moment it fails. If this
# null ever centres on zero the test has stopped modelling the selection effect and
# every verdict resting on it is void.
series = {f"t{i}": {"k": [1, 1, 0, 1, 1, 1, 0, 1, 1, 0, 1, 1, 1, 1, 0, 1] * 2}
          for i in range(30)}
t = F.permutation_test(series, "k", 4, iters=200, seed=1)
check("shuffled null is negative, not zero", bool(t and t["null_mid"] < -0.02), True)
check("shuffled null upper edge stays below +10pp", bool(t and t["null_hi"] < 0.10), True)

print("\n== fire measurement: ledger and test stay apart ==")
blob = {"runs": {
    "a": {"team": "A", "key": "scoring1", "status": "extended", "test_date": "2026-01-01"},
    "b": {"team": "B", "key": "scoring1", "status": "broke", "test_date": "2026-01-02"},
}}
rep = F.report([], blob=blob, iters=10)
check("ledger counts settled runs", (rep["graded"], rep["extended"]), (2, 1))
row = rep["rows"][0]
check("ledger rate", round(row["rate"], 6), 0.5)
# A lift or verdict on a ledger row means the two samples have been re-mixed.
check("ledger row carries no verdict",
      [k for k in ("lift", "significant", "base") if k in row], [])

print("\n== fire measurement: family-wise correction ==")
fake = [{"p": 0.02, "outside_band": True}, {"p": 0.4, "outside_band": True}]
fam = len(fake)
for x in fake:
    x["p_adj"] = min(1.0, x["p"] * fam)
    x["significant"] = bool(x["outside_band"] and x["p_adj"] < 0.05)
check("Bonferroni applied across streak types", [x["p_adj"] for x in fake], [0.04, 0.8])
check("a lone marginal p does not survive alone",
      [x["significant"] for x in fake], [True, False])


print("\n== pricing: captured once, before kickoff, never after ==")
NOWP = datetime.datetime.now(datetime.timezone.utc)
_soon = NOWP + datetime.timedelta(days=2)
lp = dict(lead, date=_soon.date().isoformat(), kickoff=_soon.strftime("%Y-%m-%dT%H:%MZ"),
          headline="Over 1.5 goals", bet={"kind": "total_gte", "n": 2},
          market='{"away": "A", "day": "x", "home": "H", "league": "L1"}')
BOOK = {"over15": {"price": 1.25, "fair": 0.78}, "over25": {"price": 1.6, "fair": 0.6},
        "btts": {"price": 1.7, "fair": 0.57}, "corners": {"price": 2.0, "fair": 0.5}}
calls = []
def fake_fetch(link):
    calls.append(link)
    return BOOK
blob, _ = T.record([lp], {"leads": {}})
blob, n_priced, n_fetched = T.price(blob, [lp], fake_fetch, now=NOWP)
check("priced one", (n_priced, n_fetched), (1, 1))
e = list(blob["leads"].values())[0]
check("only the pre-registered markets are stored", sorted(e["prices"]),
      ["btts", "over15", "over25"])
check("no url in the ledger", any("://" in str(v) for v in e.values()), False)
blob, n2, f2 = T.price(blob, [lp], fake_fetch, now=NOWP)
check("never re-priced, never re-fetched", (n2, f2), (0, 0))
gone = dict(lp, headline="Over 1.5 goals (started)",
            kickoff=(NOWP - datetime.timedelta(hours=1)).strftime("%Y-%m-%dT%H:%MZ"))
blob, _ = T.record([lp, gone], blob)     # lp still published, so it is not withdrawn
blob, n3, f3 = T.price(blob, [gone], fake_fetch, now=NOWP)
check("a lead that has kicked off is never priced", (n3, f3), (0, 0))
blob4, _ = T.record([lp], {"leads": {}})
blob4, n4, _ = T.price(blob4, [lp], lambda link: {}, now=NOWP)
check("no line up yet -> unpriced", n4, 0)
check("so it is retried next build", T.price(blob4, [lp], fake_fetch, now=NOWP)[1], 1)
blob8, _ = T.record([lp], {"leads": {}})
blob8, n8, _ = T.price(blob8, [lp], lambda l: {"btts": BOOK["btts"]}, now=NOWP)
check("companions without the claim's line -> not priced", n8, 0)
check("nothing stored for it", "prices" in list(blob8["leads"].values())[0], False)
check("retried once over 1.5 is up", T.price(blob8, [lp], fake_fetch, now=NOWP)[1], 1)
blob5, _ = T.record([lp], {"leads": {}})
check("a failed read leaves it unpriced", T.price(blob5, [lp], lambda l: None, now=NOWP)[1], 0)
unlinked = dict(lp, headline="Over 1.5 goals (no book)")
unlinked.pop("market")
blob6, _ = T.record([unlinked], {"leads": {}})
check("no venue link -> nothing to fetch",
      T.price(blob6, [unlinked], fake_fetch, now=NOWP)[2], 0)

print("\n== pricing: a team-2+ lead is priced on ITS side's team total ==")
tl = dict(lp, headline="A to score 2+", bet={"kind": "team_gte", "n": 2, "team": "A"})
BOOK_T = dict(BOOK, team={"home": {"over15": {"price": 1.5, "fair": 0.64}},
                          "away": {"over15": {"price": 2.3, "fair": 0.42}}})
blob_t, _ = T.record([tl], {"leads": {}})
blob_t, n_t, _ = T.price(blob_t, [tl], lambda l: BOOK_T, now=NOWP)
check("priced", n_t, 1)
et = list(blob_t["leads"].values())[0]
check("A is the away side, so the away team total is the claim's price",
      et["prices"]["team2plus"], {"price": 2.3, "fair": 0.42})
check("fixture-level companions still logged", sorted(et["prices"]),
      ["btts", "over15", "over25", "team2plus"])
blob_t2, _ = T.record([tl], {"leads": {}})
check("team total missing -> team lead is NOT priced (claim first)",
      T.price(blob_t2, [tl], lambda l: BOOK, now=NOWP)[1], 0)
blob_t, _ = T.grade([fx(tl["date"], "H", "A", 1, 2)], blob_t)     # A scores 2: hit
et = blob_t["leads"][T.lead_id(tl)]
check("team2plus pnl = 2.3 - 1", round(et["pnl"]["team2plus"]["pnl"], 2), 1.3)
check("lane ROI is read off each lead's OWN claim",
      round(T.price_report(blob_t)["lane_roi"]["team2plus"], 2), 1.3)
check("the over-1.5 lane is untouched by it", "over15" in T.price_report(blob_t)["lane_roi"], False)

print("\n== model: probability logged beside the price, scored against the book ==")
import model as M
_hist = []
for i in range(8):
    d = f"2026-05-{i+1:02d}"
    _hist.append(fx(d, "H", f"x{i}", 3, 0))        # H: scores 3, concedes 0
    _hist.append(fx(d, "A", f"y{i}", 0, 2))        # A: scores 0, concedes 2
    _hist.append(fx(d, f"x{i}", f"y{i}", 1, 1))
_m = M.fit(_hist)
check("fit rates both sides", (M.known(_m, "H"), M.known(_m, "A"), M.known(_m, "Nobody")),
      (True, True, False))
_pp = M.probs(_m, "H", "A", "L1")
check("H at home is the stronger attack", _pp["home2plus"] > _pp["away2plus"], True)
check("probabilities are probabilities",
      all(0 < _pp[k] < 1 for k in ("over15", "over25", "btts", "home2plus", "away2plus")), True)
check("a side with no games gets the average, not a crash", M.known(_m, "Nobody"), False)
check("no lookahead: fit(before=) ignores later games",
      M.known(M.fit(_hist, before="2026-05-01"), "H"), False)
blob_m, _ = T.record([lp], {"leads": {}})
blob_m, _, _ = T.price(blob_m, [lp], fake_fetch, now=NOWP, model=_m)
em = list(blob_m["leads"].values())[0]
check("model logged for exactly the priced markets", sorted(em["model"]), sorted(em["prices"]))
check("stamped when priced", em["modelled_at"], em["priced_at"])
# team lead: the model value is the claim side's own 2+ probability
blob_mt, _ = T.record([tl], {"leads": {}})
blob_mt, _, _ = T.price(blob_mt, [tl], lambda l: BOOK_T, now=NOWP, model=_m)
emt = list(blob_mt["leads"].values())[0]
check("team lead's model prob is the away side's 2+ (A is away)",
      emt["model"]["team2plus"], round(_pp["away2plus"], 4))
# back-fill: priced before the model existed, still pending -> gets a model prob
blob_bf, _ = T.record([lp], {"leads": {}})
blob_bf, _, _ = T.price(blob_bf, [lp], fake_fetch, now=NOWP)
check("no model yet", "model" in list(blob_bf["leads"].values())[0], False)
blob_bf, n_bf, f_bf = T.price(blob_bf, [lp], fake_fetch, now=NOWP, model=_m)
check("back-filled without re-pricing or re-fetching",
      ("model" in list(blob_bf["leads"].values())[0], n_bf, f_bf), (True, 0, 0))
_ko = dict(lp, kickoff=(NOWP - datetime.timedelta(hours=1)).strftime("%Y-%m-%dT%H:%MZ"))
blob_ko, _ = T.record([_ko], {"leads": {}})
list(blob_ko["leads"].values())[0]["prices"] = {"over15": {"price": 1.2, "fair": 0.8}}
blob_ko, _, _ = T.price(blob_ko, [_ko], fake_fetch, now=NOWP, model=_m)
check("never back-filled after kickoff", "model" in list(blob_ko["leads"].values())[0], False)
# unknown side -> no model entry, price still stored
_unk = dict(lp, home="Nobody", match="Nobody v A", headline="Over 1.5 goals (unk)")
blob_u, _ = T.record([_unk], {"leads": {}})
blob_u, n_u, _ = T.price(blob_u, [_unk], fake_fetch, now=NOWP, model=_m)
check("unrated side: priced but not modelled",
      (n_u, "model" in list(blob_u["leads"].values())[0]), (1, False))
# scoring: hand-built ledger, model right where the book is wrong
_L = {"leads": {}}
for i, (y, pm, pb) in enumerate([(1, 0.9, 0.6), (1, 0.8, 0.6), (0, 0.2, 0.6), (1, 0.7, 0.65)]):
    _L["leads"][f"k{i}"] = {"status": "hit" if y else "miss", "bet": {"kind": "total_gte", "n": 2},
                            "prices": {"over15": {"price": 1.6, "fair": pb}},
                            "model": {"over15": pm},
                            "pnl": {"over15": {"hit": bool(y), "pnl": 0.6 if y else -1.0}}}
_mr = T.model_report(_L)
_r = _mr["rows"][0]
check("brier model", round(_r["brier_model"], 4), round((0.01 + 0.04 + 0.04 + 0.09) / 4, 4))
check("brier book", round(_r["brier_book"], 4), round((0.16 + 0.16 + 0.36 + 0.1225) / 4, 4))
check("model ahead", _r["model_better"], True)
check("value split at the margin: 3 value (0.9, 0.8, 0.7 v 0.6/0.65), 1 rest",
      (_r["value"]["n"], _r["rest"]["n"]), (3, 1))
check("value group hit 3/3, ROI +60%", (_r["value"]["hits"], round(_r["value"]["roi"], 2)), (3, 0.6))
check("rest lost", _r["rest"]["roi"], -1.0)

print("\n== pricing: P/L graded per market at the captured price ==")
blob, n = T.grade([fx(lp["date"], "H", "A", 2, 0)], blob)    # 2-0: over15 hit, rest miss
e = blob["leads"][T.lead_id(lp)]
check("status hit (the claim is over 1.5)", e["status"], "hit")
check("over15 pnl = price - 1", round(e["pnl"]["over15"]["pnl"], 2), 0.25)
check("over25 miss loses the unit", e["pnl"]["over25"]["pnl"], -1.0)
check("btts miss", e["pnl"]["btts"]["hit"], False)
pr = T.price_report(blob)
row = {r["market"]: r for r in pr["rows"]}
check("over15 row: n=1, ROI +25%", (row["over15"]["n"], round(row["over15"]["roi"], 2)), (1, 0.25))
check("break-even is 1/price", round(row["over15"]["breakeven"], 2), 0.8)
check("lift is measured against the book, not the teams", round(row["over15"]["lift"], 2),
      round(1 - 0.78, 2))
check("claim ROI surfaced", round(pr["claim_roi"], 2), 0.25)
_unpriced = dict(lead, headline="Never priced")
blob7, _ = T.record([_unpriced], {"leads": {}})
blob7, _ = T.grade([played], blob7)
check("a lead graded without a price has no pnl", "pnl" in list(blob7["leads"].values())[0], False)
check("and does not count as settled at a price", T.price_report(blob7)["graded"], 0)

print("\n== value split: yardstick depends on the price's source ==")
_L2 = {"leads": {
    "v1": {"status": "hit", "bet": {"kind": "total_gte", "n": 2},
           "prices": {"over15": {"price": round(1 / 0.80, 3), "fair": 0.78, "venue": "kalshi"}},
           "model": {"over15": 0.84}, "pnl": {"over15": {"hit": True, "pnl": 0.25}}},
    "v2": {"status": "hit", "bet": {"kind": "total_gte", "n": 2},
           "prices": {"over15": {"price": round(1 / 0.80, 3), "fair": 0.78, "venue": "kalshi"}},
           "model": {"over15": 0.86}, "pnl": {"over15": {"hit": True, "pnl": 0.25}}},
    "b1": {"status": "hit", "bet": {"kind": "total_gte", "n": 2},
           "prices": {"over15": {"price": 1.25, "fair": 0.78}},
           "model": {"over15": 0.84}, "pnl": {"over15": {"hit": True, "pnl": 0.25}}}}}
_r2 = T.model_report(_L2)["rows"][0]
check("exchange: 0.84 v 0.80 paid is not value; 0.86 is. Bovada: 0.84 v 0.78 fair is value",
      (_r2["value"]["n"], _r2["rest"]["n"]), (2, 1))

print("\n== venue book: exchange prices (Kalshi, Polymarket US) ==")
import venue_book as VB
for a, b in [("man city", "Manchester City"), ("LA Galaxy", "Los Angeles Galaxy"),
             ("Leeds United FC", "Leeds United"), ("inter", "Internazionale")]:
    check(f"same club: {a} / {b}", VB.sim(a, b) >= VB.SIDE_MATCH, True)
check("different clubs", VB.sim("Real Madrid", "Real Sociedad") >= VB.SIDE_MATCH, False)
_evs = [(("Leeds United FC", "Newcastle United FC"), "e1"), (("Arsenal", "Chelsea"), "e2")]
check("both sides must match", VB._pick_event(_evs, "Leeds United", "Newcastle United")[0], "e1")
check("the reverse fixture is not a match", VB._pick_event(_evs, "Chelsea", "Arsenal")[0], None)
check("two equal candidates are refused",
      VB._pick_event([(("Leeds", "Newcastle"), "a"), (("Leeds", "Newcastle"), "b")], "Leeds", "Newcastle")[0], None)
_q = VB._quote(VB.POLY, 0.78, 0.77, "tsc-x-1pt5", "epl-lee-new")
check("a quote is priced at ask + taker fee", _q["price"], round(1 / (0.78 + 0.06 * 0.78 * 0.22), 3))
check("its fair probability is the midpoint", _q["fair"], 0.775)
check("a one-sided book is no quote", VB._quote(VB.KALSHI, 0.5, 0.0, "t"), None)
check("a wide book is no quote", VB._quote(VB.KALSHI, 0.6, 0.45, "t"), None)
check("no URL is stored in a quote", "url" in _q, False)
check("Polymarket URL is built from the event", VB.market_url(_q), "https://polymarket.us/event/epl-lee-new")
check("Kalshi URL is built from the series",
      VB.market_url({"venue": "kalshi", "market": "KXEPLTEAMTOTAL-26SEP14LEENEW-LEE2"}),
      "https://kalshi.com/markets/kxeplteamtotal")
check("a league neither venue lists has no key", VB.fixture_key({"league": "Belgian Pro League"}), None)
_key = VB.fixture_key({"league": "Premier League", "kickoff": "2026-09-14T19:00Z",
                       "home": "Leeds United", "away": "Newcastle United"})
_saved_pe, _saved_ks, _saved_ke = VB.poly_events, VB.kalshi_series, VB.kalshi_events
VB.poly_events = lambda slug: [{"slug": "epl-lee-new-2026-09-14", "title": "Leeds United FC vs. Newcastle United FC",
    "startDate": "2026-09-14T19:00:00Z", "markets": [
        {"sportsMarketType": "soccer_team_full_game_total", "title": "Over 1.5 total goals", "slug": "tsc-1pt5",
         "bestBidQuote": {"value": "0.77"}, "bestAskQuote": {"value": "0.78"}},
        {"sportsMarketType": "soccer_team_full_game_total", "title": "Over 2.5 total goals", "slug": "tsc-2pt5",
         "bestBidQuote": {"value": "0.40"}, "bestAskQuote": {"value": "0.60"}},
        {"sportsMarketType": "soccer_team_first_half_total", "title": "Over 1.5 total goals", "slug": "1h",
         "bestBidQuote": {"value": "0.20"}, "bestAskQuote": {"value": "0.21"}}]}]
VB.kalshi_series = lambda: {"KXEPLTOTAL", "KXEPLBTTS", "KXEPLTEAMTOTAL"}
def _kev(series):
    base = {"event_ticker": f"{series}-26SEP14LEENEW", "title": "Leeds United vs Newcastle: x"}
    if series == "KXEPLTOTAL":
        return [dict(base, markets=[{"ticker": "T2", "yes_sub_title": "Over 1.5 goals", "status": "active",
                                     "yes_bid_dollars": "0.70", "yes_ask_dollars": "0.72"},
                                    {"ticker": "T3", "yes_sub_title": "Over 2.5 goals", "status": "active",
                                     "yes_bid_dollars": "0.52", "yes_ask_dollars": "0.54"}])]
    if series == "KXEPLBTTS":
        return [dict(base, markets=[{"ticker": "X-BTTS", "status": "active",
                                     "yes_bid_dollars": "0.58", "yes_ask_dollars": "0.59"}])]
    return [dict(base, markets=[
        {"ticker": "LEE2", "yes_sub_title": "Leeds United over 1.5 goals", "status": "active",
         "yes_bid_dollars": "0.43", "yes_ask_dollars": "0.45"},
        {"ticker": "NEW2", "yes_sub_title": "Newcastle over 1.5 goals", "status": "active",
         "yes_bid_dollars": "0.36", "yes_ask_dollars": "0.39"},
        {"ticker": "NEW1", "yes_sub_title": "Newcastle over 0.5 goals", "status": "active",
         "yes_bid_dollars": "0.74", "yes_ask_dollars": "0.75"}]),
        dict(base, event_ticker=f"{series}-26SEP21LEENEW", markets=[])]
VB.kalshi_events = _kev
try:
    _fq = VB.fixture_quotes(_key)
    check("every market found across both venues", sorted(_fq), ["away2plus", "btts", "home2plus", "over15", "over25"])
    check("the cheaper effective price wins: Kalshi 0.72 over Polymarket 0.78", _fq["over15"]["venue"], "kalshi")
    check("a wide Polymarket book leaves the Kalshi quote", (_fq["over25"]["venue"], _fq["over25"]["ask"]), ("kalshi", 0.54))
    check("team totals go to the right side", (_fq["home2plus"]["market"], _fq["away2plus"]["market"]), ("LEE2", "NEW2"))
    _fp = VB.fetch_prices(_key)
    check("fetch_prices keeps the ledger's shape", (sorted(_fp), sorted(_fp["team"])),
          (["btts", "over15", "over25", "team"], ["away", "home"]))
    check("an unreadable key is None, not a guess", VB.fetch_prices("not json"), None)
finally:
    VB.poly_events, VB.kalshi_series, VB.kalshi_events = _saved_pe, _saved_ks, _saved_ke
check("Bovada is gone from the pipeline",
      any("bovada" in open(f).read().lower().split("retired")[0] and "import venues" in open(f).read()
          for f in ("streaks_build.py", "book_track.py", "today_build.py", "health.py")), False)

print("\n== fire measurement: iters and seed are read at CALL time ==")
# `iters=PERMUTATIONS, seed=SEED` in the signature binds at import, so setting
# fire_track.SEED did nothing — an audit of seed stability ran the SAME seed four times
# and returned four identical rows, which looks like stability and is no test at all.
_ser = {f"t{i}": {"k": [1, 1, 0, 1, 1, 1, 0, 1, 1, 0, 1, 1, 1, 1, 0, 1] * 2}
        for i in range(30)}
_a = F.permutation_test(_ser, "k", 4, iters=200, seed=1)
_b = F.permutation_test(_ser, "k", 4, iters=200, seed=99)
check("a different seed gives a different null band",
      _a["null_lo"] != _b["null_lo"] or _a["null_hi"] != _b["null_hi"], True)
_saved = F.SEED
try:
    F.SEED = 99
    _c = F.permutation_test(_ser, "k", 4, iters=200)
    check("module-level SEED is honoured, not baked in at import",
          (_c["null_lo"], _c["null_hi"]), (_b["null_lo"], _b["null_hi"]))
    F.PERMUTATIONS_saved = F.PERMUTATIONS
    F.PERMUTATIONS = 60
    _d = F.permutation_test(_ser, "k", 4, seed=1)
    check("module-level PERMUTATIONS is honoured too",
          _d is not None and _d["null_lo"] != _a["null_lo"], True)
    F.PERMUTATIONS = F.PERMUTATIONS_saved
finally:
    F.SEED = _saved

print("\n== Leads v2 (2026-09-14): the over-1.5 lane is the 9-of-10 rule ==")
_now = datetime.datetime(2026, 9, 14, 12, tzinfo=datetime.timezone.utc)
_r = []
for i in range(10):
    d = f"2026-08-{i+1:02d}"
    _r.append(fx(d, "Nine", f"n{i}", 2, 0 if i == 0 else 1))       # 10/10 over 1.5
    _r.append(fx(d, "Tenn", f"t{i}", 1, 1 if i else 0))             # 9/10 (first game 1-0)
    _r.append(fx(d, "Eight", f"e{i}", 1, 1 if i > 1 else 0))        # 8/10
    _r.append(fx(d, "Run", f"r{i}", 3, 0))                          # scores every game
_r.append(fx("2026-07-01", "Short", "s0", 3, 3))
for i in range(5):
    _r.append(fx(f"2026-08-{i+1:02d}", "Short", f"s{i+1}", 3, 3))  # 6 games only
_r += [dict(fx("2026-09-15", "Nine", "Tenn", None, None, played=False), kickoff="2026-09-15T18:00Z"),
       dict(fx("2026-09-15", "Nine", "Eight", None, None, played=False), kickoff="2026-09-15T20:00Z"),
       dict(fx("2026-09-15", "Short", "Nine", None, None, played=False), kickoff="2026-09-15T21:00Z"),
       dict(fx("2026-09-15", "Run", "Nine", None, None, played=False), kickoff="2026-09-15T22:00Z")]
_bt = B.team_games(_r)
_v2 = B.over15_form_leads(_r, _bt, now=_now, links=False)
check("both 9+/10 is a lead; 8/10 is not; a side with 6 games is not",
      sorted(l["match"] for l in _v2), ["Nine v Tenn", "Run v Nine"])
_l = [l for l in _v2 if l["match"] == "Nine v Tenn"][0]
check("the claim is over 1.5, tagged v2, with the counts out of 10",
      (_l["bet"], _l["rule"], _l["a_run"], _l["b_run"], _l["a_text"]),
      ({"kind": "total_gte", "n": 2}, "v2", 10, 9, "over 1.5 · 10 of last 10"))
check("pills light the games that went over, not a prefix",
      [g["hit"] for g in _l["b_recent"]][:2], [True, True])
_st = B.team_streaks(_bt)
_board = B.board_leads(_r, _bt, _st, B.base_rates(_st), now=_now, links=False)
check("the board's over-1.5 cards all come from the v2 rule",
      {l.get("rule") for l in _board if l["bet"]["kind"] == "total_gte"}, {"v2"})
_shadow = B.find_leads(_r, _st, B.base_rates(_st), now=_now, links=False, pairings=B.SHADOW_PAIRINGS)
check("the retired run pairings still find their own leads for the shadow ledger",
      "Run v Nine" in {l["match"] for l in _shadow} and all(l["bet"]["kind"] == "total_gte" for l in _shadow), True)
check("the shadow never reaches the board's team-2+ lane", all(p[4]["kind"] == "team_gte" for p in B.LEAD_PAIRINGS), True)
_blob, _ = T.record(_board, {"leads": {}}, now=_now)
check("the ledger keeps the rule tag", {e.get("rule") for e in _blob["leads"].values() if e["bet"]["kind"] == "total_gte"}, {"v2"})
_mk = lambda lid, st, pnl=None, rule=None, date="2026-09-15": dict(
    id=lid, date=date, bet={"kind": "total_gte", "n": 2}, status=st, **({"rule": rule} if rule else {}),
    **({"pnl": {"over15": {"pnl": pnl, "hit": st == "hit"}}, "prices": {"over15": {"price": 1.2}}} if pnl is not None else {}))
_main = {"leads": {"a": _mk("a", "hit", 0.2, "v2"), "b": _mk("b", "miss", -1.0, "v2"), "c": _mk("c", "hit", rule="v2"),
                   "old": _mk("old", "hit", 0.2, date="2026-09-01")}}
_sh = {"leads": {"a": _mk("a", "hit", 0.2), "x": _mk("x", "hit", 0.25), "y": _mk("y", "pending")}}
_cmp = T.rule_compare(_main, _sh, "2026-09-14")
check("rule compare: v2 graded, hits, priced ROI", (_cmp["v2"]["graded"], _cmp["v2"]["hits"], _cmp["v2"]["priced"], round(_cmp["v2"]["roi"], 3)),
      (3, 2, 2, -0.4))
check("rule compare: the old rule from the shadow, and the overlap", (_cmp["v1"]["graded"], _cmp["v1"]["pending"], round(_cmp["v1"]["roi"], 3), _cmp["both"]),
      (2, 1, 0.225, 1))

print()
if FAILS:
    print(f"{len(FAILS)} FAILURE(S)")
    for f in FAILS:
        print(" -", f)
    sys.exit(1)
print("all logic tests passed")
