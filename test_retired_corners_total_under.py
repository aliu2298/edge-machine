#!/usr/bin/env python3
"""2026-11-22 (Olu): corners_total_under retired (paper; it was in Production 2026-10-15 to 2026-10-27)."""
import sys

import sandbox_sources as S
import sandbox_track as T

FAILS = []


def check(why, got, want):
    good = got == want
    print(f"  {'ok  ' if good else 'FAIL'} {why}" + ("" if good else f" — got {got!r}, want {want!r}"))
    if not good:
        FAILS.append(why)


m = S.SOURCES["corners_total_under"]
check("off the run, with its reason", (m["sports"], list(m["retired_sports"])), ([], ["soccer_corners"]))
check("the reason carries the date and the record it stopped on", all(x in S.CORNERS_TOTAL_UNDER_RETIRED_WHY for x in ("Retired 2026-11-22 by Olu", "11–19", "−15.7%")), True)
check("not in Production, its 2026-10-27 removal stands as the record it left on",
      ("corners_total_under|soccer_corners" in T.PAIR_OVERRIDES, T.PAIR_REMOVALS["corners_total_under|soccer_corners"]["removed_on"]), (False, "2026-10-27"))
print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
