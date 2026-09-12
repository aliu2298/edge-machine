#!/usr/bin/env python3
"""test_book.py — logic tests for the book ledger (book_track.py).

Synthetic fixtures with hand-computed answers. Usage:  python3 test_book.py
"""
import datetime, sys

import book_track as K
import model as M

FAILS = []


def check(name, got, want):
    if got != want:
        FAILS.append(f"{name}: got {got!r}, want {want!r}")
        print(f"  FAIL {name}: got {got!r}, want {want!r}")
    else:
        print(f"  ok   {name}")


NOW = datetime.datetime(2026, 9, 12, 12, 0, tzinfo=datetime.timezone.utc)


def fx(hours, home="H", away="A", league="L1", played=False, hg=None, ag=None, **kw):
    ko = NOW + datetime.timedelta(hours=hours)
    f = {"date": ko.date().isoformat(), "kickoff": ko.strftime("%Y-%m-%dT%H:%MZ"),
         "league": league, "home": home, "away": away, "played": played,
         "home_goals": hg, "away_goals": ag}
    f.update(kw)
    return f


BOOK = {"over15": {"price": 1.25, "fair": 0.78}, "over25": {"price": 1.7, "fair": 0.57},
        "btts": {"price": 1.8, "fair": 0.54},
        "team": {"home": {"over15": {"price": 1.9, "fair": 0.51}},
                 "away": {"over15": {"price": 2.6, "fair": 0.37}}}}
calls = []


def fetch(link):
    calls.append(link)
    return BOOK


link_for = lambda f: f"https://x/{f['home']}-{f['away']}"

print("\n== record: only fixtures inside the window, before kickoff, once ==")
fixtures = [fx(6), fx(30, "B", "C"), fx(-1, "D", "E"), fx(6, "F", "G", played=True, hg=1, ag=1),
            fx(6, "P", "Q", competitive=False)]
blob, n, fetched = K.record(fixtures, {"rows": {}}, link_for, fetch, now=NOW)
check("one fixture priced (6h out)", (n, fetched), (1, 1))
row = list(blob["rows"].values())[0]
check("all five markets, team totals mapped by side", sorted(row["prices"]),
      ["away2plus", "btts", "home2plus", "over15", "over25"])
check("away side's 2+ is the away team total", row["prices"]["away2plus"]["price"], 2.6)
check("30h out is not priced yet", "2026-09-13|B|C" in blob["rows"], False)
check("kicked off is never priced", any(r["home"] == "D" for r in blob["rows"].values()), False)
check("played and friendlies skipped", [r["home"] for r in blob["rows"].values()], ["H"])
blob, n2, f2 = K.record(fixtures, blob, link_for, fetch, now=NOW)
check("never re-priced or re-fetched", (n2, f2), (0, 0))
blob, n3, f3 = K.record([fx(6, "B", "C")], {"rows": {}}, link_for, lambda l: None, now=NOW)
check("no book -> nothing stored, will retry", (n3, f3, blob["rows"]), (0, 1, {}))
blob, n4, _ = K.record([fx(6, "B", "C")], {"rows": {}}, lambda f: None, fetch, now=NOW)
check("no venue link -> not fetched", n4, 0)
check("no url stored in the ledger",
      any("://" in str(v) for v in list(K.record(fixtures, {"rows": {}}, link_for, fetch, now=NOW)[0]["rows"].values())[0].values()), False)

print("\n== record: model logged beside the price ==")
hist = []
for i in range(6):
    hist.append(fx(-24 * (i + 2), "H", f"x{i}", played=True, hg=2, ag=0))
    hist.append(fx(-24 * (i + 2), "A", f"y{i}", played=True, hg=1, ag=1))
    hist.append(fx(-24 * (i + 2), f"x{i}", f"y{i}", played=True, hg=1, ag=1))
m = M.fit(hist)
blob, _, _ = K.record([fx(6)], {"rows": {}}, link_for, fetch, model=m, now=NOW)
row = list(blob["rows"].values())[0]
check("model probs for every priced market", sorted(row["model"]), sorted(row["prices"]))
check("home2plus is the home side's own 2+",
      row["model"]["home2plus"], round(M.probs(m, "H", "A", "L1")["home2plus"], 4))
blob, _, _ = K.record([fx(6, "Z", "A")], {"rows": {}}, link_for, fetch, model=m, now=NOW)
check("unrated side: priced, not modelled", "model" in list(blob["rows"].values())[0], False)

print("\n== grade: per-market result and flat-stake P/L ==")
blob, _, _ = K.record([fx(6)], {"rows": {}}, link_for, fetch, now=NOW)
later = NOW + datetime.timedelta(hours=10)
blob, n = K.grade([fx(6, played=True, hg=2, ag=0)], blob, now=later)
row = list(blob["rows"].values())[0]
check("graded one", n, 1)
check("2-0: over15 yes, over25 no, btts no, home2+ yes, away2+ no",
      row["result"], {"over15": True, "over25": False, "btts": False,
                      "home2plus": True, "away2plus": False})
check("pnl at the captured prices", (row["pnl"]["over15"], row["pnl"]["home2plus"], row["pnl"]["btts"]),
      (0.25, 0.9, -1.0))
blob, n = K.grade([fx(6, played=True, hg=2, ag=0)], blob, now=later)
check("re-grade is a no-op", n, 0)
blob, _, _ = K.record([fx(6, "B", "C")], {"rows": {}}, link_for, fetch, now=NOW)
blob, n = K.grade([], blob, now=NOW + datetime.timedelta(days=3))
check("missing score inside the void window stays pending", (n, list(blob["rows"].values())[0]["status"]), (0, "pending"))
blob, n = K.grade([], blob, now=NOW + datetime.timedelta(days=9))
check("voids once clearly overdue", list(blob["rows"].values())[0]["status"], "void")

print("\n== report: excess over the book, z, teams pooled by side ==")
blob = {"rows": {}}
for i, (h, a, hg, ag) in enumerate([("H", "A", 2, 0), ("H", "B", 3, 1), ("C", "H", 0, 2)]):
    f = fx(6 + i, h, a)
    blob, _, _ = K.record([f], blob, link_for, fetch, now=NOW)
    blob, _ = K.grade([fx(6 + i, h, a, played=True, hg=hg, ag=ag)], blob, now=later)
rep = K.report(blob)
check("3 fixtures x 5 markets", rep["observations"], 15)
o15 = next(m for m in rep["by_market"] if m["market"] == "over15")
check("over15: 3/3 hit v 0.78 expected each", (o15["hits"], round(o15["expected"], 2)), (3, 2.34))
import math
check("z = excess / sqrt(sum fair(1-fair))", round(o15["z"], 4),
      round((3 - 2.34) / math.sqrt(3 * 0.78 * 0.22), 4))
teams = K.team_index(blob)
check("H pooled: 3 fixtures x (over15, over25, btts) + own 2+ three times = 12",
      teams["H"]["n"], 12)
check("H scored 2+ every time: all three own-2+ obs hit",
      sum(1 for r in blob["rows"].values() for mk, hit in r["result"].items()
          if (mk == "home2plus" and r["home"] == "H" or mk == "away2plus" and r["away"] == "H") and hit), 3)
check("A: 3 fixture markets + its own away 2+ (0 goals, miss) = 4", teams["A"]["n"], 4)
check("no tag below the floor", any(a["paying"] for a in teams.values()), False)
check("teams tested reported", rep["teams_tested"], 4)
big = {"rows": {}}
for i in range(8):
    f = fx(6 + i, "H", f"o{i}")
    big, _, _ = K.record([f], big, link_for, fetch, now=NOW)
    big, _ = K.grade([fx(6 + i, "H", f"o{i}", played=True, hg=3, ag=2)], big, now=later)
ti = K.team_index(big)["H"]
check("floor reached: 8 x 4 = 32 obs", ti["n"], 32)
check("everything hit v ~0.6 expected -> z well over 2 -> PAYING", (ti["z"] > 2, ti["paying"]), (True, True))
val = K.report(big)
check("league rollup present", val["by_league"][0]["league"], "L1")
check("price bands cover every observation", sum(b["n"] for b in val["bands"]), 32 + 8)

print()
if FAILS:
    print(f"{len(FAILS)} FAILURE(S)")
    for f in FAILS:
        print(" -", f)
    sys.exit(1)
print("all book tests passed")
