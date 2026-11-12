#!/usr/bin/env python3
"""Offline checks for liga_u15_dog_24h (2026-11-12): La Liga under 1.5 in heavy mismatches, version 2. v1's selection, unchanged, taken
only inside 24 hours of an ESPN-listed kickoff; a fresh record under its own key; v1 retired with its record; not in Production."""
import datetime as dt
import sys

import promotion_gate as PG
import sandbox_sources as S
import sport_rows_testlib

FAILS = []
NOW = dt.datetime(2026, 11, 20, 12, 0, tzinfo=dt.timezone.utc)


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


def game(code, pa, pd, pb):
    return dict(venue="kalshi", market_id=f"KXLALIGAGAME-{code}", price_a=pa, price_draw=pd, price_b=pb)


def total(code, over, no, hours=12.0, series="KXLALIGATOTAL", **k):
    start = (NOW + dt.timedelta(hours=hours)).isoformat()
    return dict(dict(venue="kalshi_binary", market_id=f"{series}-{code}-2", price_a=over, price_b=no, start=start, start_source="espn",
                     tradeable={"a": True, "b": True}, untraded=False), **k)


def uni(*totals, games=None):
    return {"soccer": games if games is not None else [game("MIS", 0.90, 0.08, 0.04), game("EVEN", 0.50, 0.28, 0.24)],
            "soccer_o15": list(totals)}


def picks(*totals, now=NOW, games=None):
    return [p["market_id"].split("-")[1] for p in S.fetch_liga_u15_dog_24h("soccer_o15", uni(*totals, games=games), now)]


def v1(*totals, games=None):
    with sport_rows_testlib.running_again("liga_u15_dog|soccer_o15"):
        return [p["market_id"].split("-")[1] for p in S.fetch_liga_u15_dog("soccer_o15", uni(*totals, games=games))]


print("the rule")
check("heavy mismatch, No ask 0.17, inside 24h: backed", picks(total("MIS", 0.86, 0.17)), ["MIS"])
check("the pick is the No side of over 1.5", {p["pick"] for p in S.fetch_liga_u15_dog_24h("soccer_o15", uni(total("MIS", 0.86, 0.17)), NOW)}, {"b"})
check("more than 24h out: not backed, though v1 backed it", (picks(total("MIS", 0.86, 0.17, hours=24.5)), v1(total("MIS", 0.86, 0.17, hours=24.5))), ([], ["MIS"]))
check("four days out, where v1 logged: not backed", picks(total("MIS", 0.86, 0.17, hours=95.0)), [])
check("exactly 24h out: backed", picks(total("MIS", 0.86, 0.17, hours=24.0)), ["MIS"])
check("three hours out: backed", picks(total("MIS", 0.86, 0.17, hours=3.0)), ["MIS"])
check("already started: not backed", picks(total("MIS", 0.86, 0.17, hours=-0.5)), [])
check("no kickoff on the row: not backed", picks(total("MIS", 0.86, 0.17, start=None)), [])
check("a kickoff that is only Kalshi's estimate: not backed", picks(total("MIS", 0.86, 0.17, start_source=None)), [])
check("a naive clock is read as UTC", picks(total("MIS", 0.86, 0.17), now=NOW.replace(tzinfo=None)), ["MIS"])

print("the selection is v1's")
cases = [("a balanced match", total("EVEN", 0.74, 0.17), None),
         ("an underdog at the cut (0.1442)", total("CUT", 0.86, 0.17), [game("CUT", 0.71, 0.18, 0.15)]),
         ("an underdog just inside the cut (0.1346)", total("IN", 0.86, 0.17), [game("IN", 0.72, 0.18, 0.14)]),
         ("a No ask of 0.21", total("MIS", 0.80, 0.21), None),
         ("a No ask of 0.20", total("MIS", 0.82, 0.20), None),
         ("a board holding more than 6%", total("MIS", 0.90, 0.17), None),
         ("an untradeable No side", total("MIS", 0.86, 0.17, tradeable={"a": True, "b": False}), None),
         ("an untraded board", total("MIS", 0.86, 0.17, untraded=True), None),
         ("no winner board", total("MIS", 0.86, 0.17), []),
         ("another league's total", total("MIS", 0.86, 0.17, series="KXEPLTOTAL"), None),
         ("another venue", total("MIS", 0.86, 0.17, venue="polymarket_us"), None)]
for label, t, games in cases:
    check(f"{label}: v2 inside 24h picks what v1 picks", picks(t, games=games), v1(t, games=games))
check("and those cases cover both answers", sorted({bool(v1(t, games=g)) for _l, t, g in cases}), [False, True])
check("no other domain", S.fetch_liga_u15_dog_24h("soccer_btts", uni(total("MIS", 0.86, 0.17)), NOW), [])

print("registration")
src = S.SOURCES["liga_u15_dog_24h"]
check("registered as a rule on over 1.5, judged against the population", (src["kind"], src["sports"], src["baseline"], src["connected"]),
      ("Rule", ["soccer_o15"], "population", True))
check("wired to its fetcher", S.CHALLENGERS["liga_u15_dog_24h"] is S.fetch_liga_u15_dog_24h, True)
check("v1's terms are unchanged", (S.LIGA_U15_DOG_MAX, S.LIGA_U15_MAX_ASK, S.LIGA_MAX_HOLD), (0.135, 0.20, 0.06))
check("the window is 24 hours", S.LIGA_U15_DOG_24H_MAX_H, 24.0)
check("the note names its pre-registration, its weak parts and its review points",
      all(x in src["note"] for x in ("prereg_liga_u15_dog_v2_2026-11-12.md", "Weak parts", "fresh record", "Review at 10 settled")), True)
check("a different record from v1's", "liga_u15_dog_24h" != "liga_u15_dog" and S.SOURCES["liga_u15_dog"]["sports"] == [], True)

print("not in Production")
check("v2 is not a Production lane", "liga_u15_dog_24h|soccer_o15" in PG.production_lanes(), False)
check("the promotion gate can grade it when the time comes", PG.grader("liga_u15_dog_24h|soccer_o15") is not None, True)
check("the promotion gate still holds", PG.verify(), [])

print()
if FAILS:
    print(f"{len(FAILS)} FAILED: " + "; ".join(FAILS))
    sys.exit(1)
print("all liga_u15_dog_24h checks passed")
