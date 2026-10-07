#!/usr/bin/env python3
"""Every Production pair carries a green or red light.

Green: everything it logged lately reached the feed, and it is still publishing.
Red: a fault — and the faults here are the SILENT kind. A bet the feed cannot
express is dropped with no error and no row, which is how mma_fav_band ran with
seven of twenty-one bets unreachable and cricket with nineteen of thirty, both
unnoticed until someone went looking. No network.
"""
import datetime
import sys

import production as PR
import sandbox_track as T

FAILS = []


def ok(cond, why):
    print(("  ok   " if cond else "  FAIL ") + why)
    if not cond:
        FAILS.append(why)


def eq(got, want, why):
    ok(got == want, f"{why} (got {got!r}, want {want!r})")


NOW = datetime.datetime(2026, 10, 3, 20, 0, tzinfo=datetime.timezone.utc)
KEY = "team1_form_l5|soccer_team1_intl"
FEED = {KEY: {"stage": "production"}}


def bet(logged="2026-10-02T00:00:00+00:00", **over):
    """A bet placeable() accepts: a routed sport on Polymarket US, which carries its own start."""
    q = dict(sport="mma", venue="polymarket_us", pick="a", market_id="aec-ufc-a-b-2026-10-04",
             side_a="A", side_b="B", logged=logged)
    q.update(over)
    return q


print("the fixture really is publishable")
ok(T.placeable(bet()), "a Polymarket US routed bet reaches the feed")
ok(not T.placeable(bet(venue="kalshi", start_source=None)),
   "the same bet on Kalshi with no verified start does not")

print("\ngreen")
eq(PR.pair_health(KEY, [bet()], 3, FEED, now=NOW), ("ok", "publishing"),
   "publishing, nothing dropped")
eq(PR.pair_health(KEY, [], 2, FEED, now=NOW), ("ok", "publishing"),
   "quiet but still publishing leads is NOT a fault — between fixtures is not broken")
eq(PR.pair_health(KEY, [bet()], 0, FEED, now=NOW), ("ok", "nothing to publish yet"),
   "logged lately with no leads out yet is not a fault either")
old = bet(logged="2026-08-01T00:00:00+00:00")
eq(PR.pair_health(KEY, [old], 1, FEED, now=NOW)[0], "ok",
   "an OLD unreachable-era bet outside the window does not hold the light red forever")

print("\nred: a bet the feed drops silently")
bad = bet(venue="kalshi", start_source=None)
state, why = PR.pair_health(KEY, [bad], 3, FEED, now=NOW)
eq(state, "bad", "a recent bet that cannot be published is a fault")
ok("silently" in why, "and the reason says it is silent, which is the point")
ok("1 of 1" in why, "and counts how many")
eq(PR.pair_health(KEY, [bet(), bad], 3, FEED, now=NOW)[0], "bad",
   "one bad bet among good ones is still a fault — it is not averaged away")

print("\nred: dark")
eq(PR.pair_health(KEY, [], 0, FEED, now=NOW),
   ("bad", "no leads and nothing logged in 7d"),
   "no leads AND nothing logged is dark, not merely quiet")

print("\nred: unwired")
eq(PR.pair_health(KEY, [bet()], 3, {}, now=NOW),
   ("bad", "listed in Production but missing from the feed"),
   "listed in Production but absent from the feed is a fault, not a blank")
eq(PR.pair_health(KEY, [bet()], 3, None, now=NOW)[0], "ok",
   "no feed map supplied means the check is skipped, not failed")

print("\nthe window")
eq(PR.HEALTH_WINDOW_DAYS, 7, "the window a fault is judged over")
edge = bet(logged=(NOW - datetime.timedelta(days=6, hours=23)).isoformat(),
           venue="kalshi", start_source=None)
eq(PR.pair_health(KEY, [edge], 1, FEED, now=NOW)[0], "bad", "just inside the window counts")
outside = bet(logged=(NOW - datetime.timedelta(days=7, hours=1)).isoformat(),
              venue="kalshi", start_source=None)
eq(PR.pair_health(KEY, [outside], 1, FEED, now=NOW)[0], "ok", "just outside it does not")

print("\nthe states are distinguishable")
seen = {PR.pair_health(KEY, *a, now=NOW)[1] for a in
        ([[bet()], 3, FEED], [[], 0, FEED], [[bet()], 3, {}], [[bad], 3, FEED])}
eq(len(seen), 4, "each fault gives its own reason, so a red light says WHICH")

print(f"\n{len(FAILS)} FAILED" if FAILS else "\nall passed")
sys.exit(1 if FAILS else 0)
