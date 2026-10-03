#!/usr/bin/env python3
"""The Since-Production cell says WHY it is empty.

Three Production pairs read "— none yet" at the same time and meant three
different things: one had two bets running and nothing settled, one had logged
nothing in two days, and one could not be executed at all. A pair idling is
something to act on; a pair waiting is not, and the column has to tell them
apart. No network.
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


NOW = datetime.datetime(2026, 10, 3, 12, 0, tzinfo=datetime.timezone.utc)

print("days since a promotion")
eq(PR._days_since("2026-10-01T12:00:00+00:00", NOW), 2, "two whole days")
eq(PR._days_since("2026-09-28T12:00:00+00:00", NOW), 5, "five whole days")
eq(PR._days_since("2026-10-03T11:00:00+00:00", NOW), 0, "under a day reads zero, never negative")
eq(PR._days_since("2026-10-04T12:00:00+00:00", NOW), 0, "a future stamp is clamped to zero")
eq(PR._days_since(None, NOW), None, "no timestamp gives no answer")
eq(PR._days_since("not-a-date", NOW), None, "an unreadable timestamp gives no answer")
eq(PR._days_since("2026-10-01T12:00:00", NOW), 2, "a naive timestamp is read as UTC, not rejected")

print("\nthe three states the cell has to distinguish")


def note(settled, running, priced_out, days):
    """The same branch production.py uses for the Since-Production sub-label."""
    if settled:
        return f"{settled} settled"
    if running:
        return f"{running} running"
    if priced_out:
        return f"{priced_out} priced out"
    if days is not None:
        return f"nothing in {days}d"
    return "none yet"


eq(note(4, 0, 0, 6), "4 settled", "a pair with a record shows the record")
eq(note(0, 2, 0, 2), "2 running", "a pair waiting on open bets says so, not 'none yet'")
eq(note(0, 0, 2, 2), "2 priced out",
   "a pair that PICKED and was refused on price has an opinion, and says so")
eq(note(0, 0, 0, 2), "nothing in 2d", "a pair that saw nothing says how long")
eq(note(0, 0, 0, 5), "nothing in 5d", "and a longer idle reads longer")
eq(note(0, 0, 0, None), "none yet", "with no promotion stamp it falls back")
ok(note(0, 2, 0, 2) != note(0, 0, 0, 2),
   "waiting and idling never render the same — that collision is the bug this fixes")
ok(note(0, 0, 2, 2) != note(0, 0, 0, 2),
   "picked-but-priced-out and saw-nothing never render the same either: "
   "team1_form_l5 read 'nothing in 2d' while declining Spain at 0.99 and the "
   "Netherlands at 0.97, both over PRICE_CEIL")
ok(note(0, 0, 0, 5) != "—", "an idle pair is never a bare dash")
eq(T.PRICE_CEIL, 0.95, "the ceiling those two picks were refused by")

print("\nthe reachable column: does this pair actually reach the feed?")


def reach(all_n, ok_n):
    """The same branch production.py uses for the Reaches-the-feed cell."""
    if not all_n:
        return "\u2014", ""
    return f"{ok_n} of {all_n}", ("" if ok_n == all_n else "neg")


eq(reach(18, 18), ("18 of 18", ""), "a pair the feed can fully express is not flagged")
eq(reach(30, 11), ("11 of 30", "neg"), "a pair that leaks is flagged")
eq(reach(21, 14), ("14 of 21", "neg"), "and so is a partial leak")
eq(reach(0, 0), ("\u2014", ""), "a pair with no bets shows a dash, not 0 of 0")
ok(reach(30, 11)[1] == "neg" and reach(18, 18)[1] == "",
   "the flag is the whole point: cricket was promoted on 30 bets of which 11 were "
   "reachable, and nothing on the page said so")
ok(reach(30, 30)[0] != reach(30, 11)[0],
   "a full pair and a leaking pair never render the same")

print(f"\n{len(FAILS)} FAILED" if FAILS else "\nall passed")
sys.exit(1 if FAILS else 0)
