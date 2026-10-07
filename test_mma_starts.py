#!/usr/bin/env python3
"""A Kalshi MMA bet is publishable only once Kalshi's own milestone agrees.

Kalshi publishes no kickoff for a fight, only an estimate, so every Kalshi MMA
bet was refused by placeable() and seven of mma_fav_band's twenty-one bets could
never reach the feed. The milestone carries a real start_date; this verifies it
the way cricket's prose rules are verified, and subtracts the margin a fight card
walks out early by. No network.
"""
import sys
from datetime import datetime, timedelta, timezone

import sandbox_sources as S
import sandbox_track as T

FAILS = []


def ok(cond, why):
    print(("  ok   " if cond else "  FAIL ") + why)
    if not cond:
        FAILS.append(why)


def eq(got, want, why):
    ok(got == want, f"{why} (got {got!r}, want {want!r})")


NOW = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)
ET = "KXUFCFIGHT-26OCT03DOSHER"
LATER = (NOW + timedelta(hours=10)).isoformat()


def mile(**over):
    m = {"type": "mma_match", "start_date": "2026-10-03T20:40:00Z",
         "primary_event_tickers": [ET], "details": {"status": "not_started"}}
    m.update(over)
    return [m]


def row(**over):
    r = dict(market_id=ET, venue="kalshi", sport="mma", pick="a",
             side_a="Dos Anjos", side_b="Hernandez", start=LATER)
    r.update(over)
    return r


print("the verified instant")
v = S._verified_mma_start(ET, mile())
eq(v, datetime(2026, 10, 3, 20, 10, tzinfo=timezone.utc),
   "the milestone instant minus the margin a fight card walks out early by")
eq(S.PINNACLE_START_MARGIN_MIN, 30, "that margin is the one the project already uses for fights")
ok(v < datetime(2026, 10, 3, 20, 40, tzinfo=timezone.utc),
   "it is EARLIER than the listed time, never later — publishing a fight already under way "
   "is the failure the verified-start rule exists to prevent")

print("\nwhat refuses a start")
ok(S._verified_mma_start(ET, mile() + mile()) is None,
   "two mma_match milestones is ambiguity, not a tie to break")
ok(S._verified_mma_start(ET, []) is None, "no milestone is not agreement")
ok(S._verified_mma_start(ET, mile(type="cricket_match")) is None,
   "a milestone of another type does not count")
ok(S._verified_mma_start(ET, mile(primary_event_tickers=["KXUFCFIGHT-OTHER"])) is None,
   "a milestone that does not name this event does not count")
ok(S._verified_mma_start(ET, mile(primary_event_tickers=ET)) is None,
   "primary_event_tickers must be a LIST, not a bare string that happens to match")
ok(S._verified_mma_start(ET, mile(details={"status": "in_progress"})) is None,
   "an unknown status refuses, even though the start is still ahead")
ok(S._verified_mma_start(ET, mile(details={"status": ""})) is None, "a blank status refuses")
ok(S._verified_mma_start(ET, mile(details={})) is None, "a missing status refuses")
ok(S._verified_mma_start(ET, mile(start_date="not-a-date")) is None, "an unparseable start refuses")
ok(S._verified_mma_start(ET, mile(start_date=None)) is None, "no start_date refuses")
eq(S.MMA_OK_STATUS, ("not_started",), "the only pre-match status Kalshi has been seen to publish")

print("\na naive milestone stamp is read as UTC, not rejected")
ok(S._verified_mma_start(ET, mile(start_date="2026-10-03T20:40:00")) is not None,
   "a stamp with no zone still verifies, read as UTC")

print("\napply over a board")
out, st = S.apply_kalshi_mma_starts([row()], milestones={ET: mile()}, now=NOW)
eq((st["matched"], st["unverified"], st["dropped"]), (1, 0, 0), "one row verified")
eq(out[0]["start_source"], "kalshi_milestone", "and tagged with the source placeable() accepts")
eq(out[0]["venue_start"], LATER, "the unverified estimate is kept as venue_start, not lost")
ok(T.placeable(out[0]), "the verified row reaches the feed")

out2, st2 = S.apply_kalshi_mma_starts([row()], milestones={ET: mile(details={"status": "x"})}, now=NOW)
eq((st2["matched"], st2["unverified"]), (0, 1), "a refused status leaves the row unverified")
ok(not T.placeable(out2[0]), "and unverified does not reach the feed")
eq(out2[0].get("start_source"), None, "no start_source is invented")

past = NOW + timedelta(minutes=10)      # milestone 20 min ahead, margin 30 -> already started
out3, st3 = S.apply_kalshi_mma_starts(
    [row()], milestones={ET: mile(start_date=past.isoformat().replace("+00:00", "Z"))}, now=NOW)
eq((st3["matched"], st3["dropped_started"], len(out3)), (0, 1, 0),
   "a fight whose verified start has passed is dropped, counted separately from a status drop")

print("\nit touches nothing else")
other = [dict(market_id="X", venue="kalshi", sport="cricket", start=LATER),
         dict(market_id="Y", venue="polymarket_us", sport="mma", start=LATER)]
out4, _ = S.apply_kalshi_mma_starts(list(other), milestones={}, now=NOW)
eq(out4, other, "cricket rows and Polymarket US rows are returned untouched")

print("\nplaceable: the sport gate")
base = dict(sport="mma", venue="kalshi", pick="a", market_id=ET, side_a="A", side_b="B",
            start_source="kalshi_milestone")
ok(T.placeable(base), "MMA may use a Kalshi milestone")
ok(T.placeable(dict(base, sport="cricket")), "so may cricket")
ok(not T.placeable(dict(base, sport="boxing")),
   "boxing may NOT — it has no checker, and the allowance is per sport, not per venue")
ok(not T.placeable(dict(base, sport="tennis")), "nor tennis")
ok(not T.placeable(dict(base, start_source=None)), "and no start source is still refused")
ok("kalshi_milestone" in T.VERIFIED_STARTS, "the source is a verified start")

print(f"\n{len(FAILS)} FAILED" if FAILS else "\nall passed")
sys.exit(1 if FAILS else 0)
