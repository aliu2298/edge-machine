#!/usr/bin/env python3
"""test_slate.py — logic tests for the auto-drawn 3-pick slate.

Synthetic leads with hand-computed answers, so a failure is a real bug rather than a data
quirk. Covers the selection constraints (which exist to stop correlated picks) and the
full draw -> grade -> refill lifecycle.

Usage:  python3 test_slate.py
"""
import datetime, sys

import slate as S

FAILS = []
NOW = datetime.datetime(2026, 8, 29, 12, 0, tzinfo=datetime.timezone.utc)


def check(name, got, want):
    if got != want:
        FAILS.append(f"{name}: got {got!r}, want {want!r}")
        print(f"  FAIL {name}: got {got!r}, want {want!r}")
    else:
        print(f"  ok   {name}")


def lead(home, away, headline="Both teams to score", hours=6, rate=0.10, strength=8,
         bet=None, league="L1"):
    ko = NOW + datetime.timedelta(hours=hours)
    return {
        "date": ko.date().isoformat(), "kickoff": ko.strftime("%Y-%m-%dT%H:%MZ"),
        "league": league, "match": f"{home} v {away}", "home": home, "away": away,
        "headline": headline, "why": "because", "bet": bet or {"kind": "btts"},
        "a": home, "b": away, "a_run": 4, "b_run": 4, "a_key": "btts", "b_key": "btts",
        "a_label": "both teams scored", "b_label": "both teams scored",
        "a_recent": [], "b_recent": [], "base_rate": rate, "strength": strength,
        "kalshi": None,
    }


def fx(date, home, away, hg, ag, played=True):
    return {"date": date, "home": home, "away": away, "home_goals": hg if played else None,
            "away_goals": ag if played else None, "played": played, "league": "L1",
            "competitive": True, "kickoff": f"{date}T12:00Z"}


print("\n== draws exactly SLATE_SIZE ==")
leads = [lead(f"H{i}", f"A{i}", rate=0.05 + i/100) for i in range(10)]
b, drawn = S.draw(leads, {"picks": {}}, NOW)
check("drew 3", len(drawn), 3)
check("3 live", len(S.live_picks(b)), 3)

print("\n== rarest first ==")
check("picked the 3 rarest",
      sorted(round(p["base_rate"], 4) for p in drawn), [0.05, 0.06, 0.07])

print("\n== one pick per FIXTURE (the correlated-bets guard) ==")
# same fixture, three different markets — only one may be drawn
same = [lead("Atlanta", "Charlotte", "Both teams to score", rate=0.05),
        lead("Atlanta", "Charlotte", "Over 2.5 goals", rate=0.06,
             bet={"kind": "total_gte", "n": 3}),
        lead("Atlanta", "Charlotte", "Atlanta to score 2+", rate=0.07,
             bet={"kind": "team_gte", "n": 2, "team": "Atlanta"})]
b2, d2 = S.draw(same, {"picks": {}}, NOW)
check("only one pick from that fixture", len(d2), 1)
check("kept the rarest of them", d2[0]["headline"], "Both teams to score")

print("\n== one TEAM per live slate ==")
# Toronto appears in three different fixtures
tor = [lead("Toronto", "X1", rate=0.05), lead("Y1", "Toronto", rate=0.06),
       lead("Toronto", "Z1", rate=0.07), lead("P", "Q", rate=0.20)]
b3, d3 = S.draw(tor, {"picks": {}}, NOW)
teams = [t for p in d3 for t in (p["home"], p["away"])]
check("Toronto used once", teams.count("Toronto"), 1)
check("filled the rest from other fixtures", len(d3), 2)  # Toronto + P/Q; X1..Z1 blocked

print("\n== window widens only when it must ==")
near = [lead(f"N{i}", f"M{i}", hours=6, rate=0.10 + i/100) for i in range(3)]
far = [lead("F1", "F2", hours=24*10, rate=0.01)]     # rarer, but 10 days out
b4, d4 = S.draw(near + far, {"picks": {}}, NOW)
check("stays inside 24h when 3 fit", all(p["home"].startswith("N") for p in d4), True)
# now only one near lead exists -> must widen to reach 3
b5, d5 = S.draw([near[0]] + [lead("F3", "F4", hours=24*6, rate=0.02),
                             lead("F5", "F6", hours=24*12, rate=0.03)],
                {"picks": {}}, NOW)
check("widens to fill the slate", len(d5), 3)

print("\n== fewer than SLATE_SIZE candidates -> partial slate, no crash ==")
b6, d6 = S.draw([lead("Solo", "Only")], {"picks": {}}, NOW)
check("drew what existed", len(d6), 1)

print("\n== a past kickoff is never drawn ==")
past = lead("Gone", "By", hours=-3)
b7, d7 = S.draw([past], {"picks": {}}, NOW)
check("no pick on a started match", len(d7), 0)

print("\n== re-running draw does not duplicate or over-fill ==")
b8, d8 = S.draw(leads, {"picks": {}}, NOW)
b8, d8b = S.draw(leads, b8, NOW)
check("second draw adds nothing", len(d8b), 0)
check("still exactly 3 live", len(S.live_picks(b8)), 3)

print("\n== a fixture already drawn is never drawn again ==")
one = [lead("Rep", "Eat", rate=0.05)]
b9, _ = S.draw(one, {"picks": {}}, NOW)
# settle it, freeing the slot; the same lead must not come back
b9, _ = S.grade([fx(one[0]["date"], "Rep", "Eat", 1, 1)], b9, NOW)
b9, again = S.draw(one, b9, NOW)
check("not redrawn after settling", len(again), 0)

print("\n== grading ==")
l = lead("H", "A", "Both teams to score", rate=0.05)
bg, _ = S.draw([l], {"picks": {}}, NOW)
bg, n = S.grade([fx(l["date"], "H", "A", 2, 1)], bg, NOW)
p = list(bg["picks"].values())[0]
check("graded one", n, 1)
check("hit", p["status"], "hit")
check("final recorded", p["final"], "2-1")
bg, n2 = S.grade([fx(l["date"], "H", "A", 2, 1)], bg, NOW)
check("re-grade is a no-op", n2, 0)

print("\n== a miss is a miss ==")
l2 = lead("H2", "A2", "Over 2.5 goals", rate=0.05, bet={"kind": "total_gte", "n": 3})
bm, _ = S.draw([l2], {"picks": {}}, NOW)
bm, _ = S.grade([fx(l2["date"], "H2", "A2", 1, 1)], bm, NOW)
check("miss", list(bm["picks"].values())[0]["status"], "miss")

print("\n== unplayed fixture stays live; overdue one voids ==")
l3 = lead("H3", "A3", hours=6)
bv, _ = S.draw([l3], {"picks": {}}, NOW)
bv, _ = S.grade([], bv, NOW)
check("still live", list(bv["picks"].values())[0]["status"], "live")
bv, _ = S.grade([], bv, NOW + datetime.timedelta(days=S.VOID_AFTER_DAYS + 2))
check("voids once overdue", list(bv["picks"].values())[0]["status"], "void")

print("\n== full cycle: grade frees a slot, refill happens in the SAME run ==")
a, bnew = lead("C1", "C2", rate=0.05), lead("C3", "C4", rate=0.06)
bc, _ = S.draw([a], {"picks": {}}, NOW)
check("1 live before", len(S.live_picks(bc)), 1)
bc, g, d = S.run([fx(a["date"], "C1", "C2", 1, 1)], [a, bnew], bc, NOW)
check("graded the finished one", g, 1)
check("refilled in the same run", len(d), 1)
check("new pick is the other fixture", d[0]["home"], "C3")

print("\n== a pick is LOCKED: later lead changes do not rewrite it ==")
orig = lead("L1", "L2", rate=0.05, strength=8)
bl, dl = S.draw([orig], {"picks": {}}, NOW)
moved = dict(orig, a_run=6, b_run=6, base_rate=0.40, strength=12)
bl, _ = S.draw([moved], bl, NOW)
stored = list(bl["picks"].values())[0]
check("run length unchanged", stored["a_run"], 4)
check("rarity unchanged", stored["base_rate"], 0.05)

print("\n== horizon_days reports the real reach ==")
bh, _ = S.draw([lead("Z1", "Z2", hours=24*3)], {"picks": {}}, NOW)
check("3 days out", S.horizon_days(bh, NOW), 3)

print("\n== report ==")
br = {"picks": {}}
picks = [lead(f"R{i}", f"S{i}", rate=0.05 + i/100) for i in range(3)]
br, _ = S.draw(picks, br, NOW)
res = [fx(picks[0]["date"], "R0", "S0", 1, 1),      # btts hit
       fx(picks[1]["date"], "R1", "S1", 2, 0),      # btts miss
       fx(picks[2]["date"], "R2", "S2", 3, 1)]      # btts hit
br, _ = S.grade(res, br, NOW)
rep = S.report(res, br)
check("graded 3", rep["graded"], 3)
check("2 hits", rep["hits"], 2)
check("rate", round(rep["rate"], 3), round(2/3, 3))
check("history populated", len(rep["history"]), 3)

print()
if FAILS:
    print(f"{len(FAILS)} FAILURE(S)")
    for f in FAILS:
        print(" -", f)
    sys.exit(1)
print("all slate tests passed")
