#!/usr/bin/env python3
"""2026-11-22 (Olu): commod_fav_band pulled from Production and retired; the paper rules commod_nc_yes and crypto_fav_band_v2 retired."""
import sys

import sandbox_sources as S
import sandbox_track as T

FAILS = []


def check(why, got, want):
    good = got == want
    print(f"  {'ok  ' if good else 'FAIL'} {why}" + ("" if good else f" — got {got!r}, want {want!r}"))
    if not good:
        FAILS.append(why)


K = "commod_fav_band|commodities_fav"
check("commod_fav_band is off the Production list, its record kept, removed 2026-11-22", (K in T.PAIR_OVERRIDES, T.PAIR_REMOVALS[K]), (False, dict(removed_on="2026-11-22", keep_record=True)))
check("and off the Sandbox run, with its reason", (S.SOURCES["commod_fav_band"]["sports"], list(S.SOURCES["commod_fav_band"]["retired_sports"])), ([], ["commodities_fav"]))
why = S.COMMOD_FAV_BAND_RETIRED_WHY
check("the reason says why nothing was counted live", all(x in why for x in ("Retired 2026-11-22 by Olu", "counted nothing", "placed no order", "65 won, 19 lost")), True)
print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
