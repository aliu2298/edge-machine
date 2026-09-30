#!/usr/bin/env python3
"""Oddspedia is unpaused. The other paused lanes stay paused.

Fails on main before the line is removed: source_fully_paused("oddspedia") is
true, and the tracker skips its fetch. Passes once the line is gone. No network.
"""
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import sandbox_sources as S
import sandbox_track as T

FAILS = []
STILL_PAUSED = {
    "covers", "kalshi", "scores24", "polymarket", "draftkings", "mlb_fade_streak", "nws",
    "tt_band_55_60", "olbg", "pinnacle", "cmd_tail", "btts_form_l10", "o15_form_l10",
    "sportsgambler", "tennis_combo3", "tennis_combo4", "pm_combo3", "pm_combo4",
    "nhl_dog_pl", "gas_nochange", "espn_fpi",
}


def ok(cond, why):
    print(f"  {'ok  ' if cond else 'FAIL'} {why}")
    if not cond:
        FAILS.append(why)


def eq(got, want, why):
    ok(got == want, why if got == want else f"{why} — got {got!r}, want {want!r}")


def main():
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    print(f"HEAD {head}")

    ok(not S.source_fully_paused("oddspedia"),
       "oddspedia is not fully paused")
    ok(not S.lane_paused("oddspedia", "cricket"),
       "oddspedia cricket may log a new entry")
    ok("oddspedia" not in S.PAUSED_LANES, "oddspedia is off the pause list")

    eq(set(S.PAUSED_LANES), STILL_PAUSED,
       "every other paused lane is still on the list")
    ok(S.PAUSED_LANES.get("polymarket") is None and S.source_fully_paused("polymarket"),
       "polymarket stays fully paused")
    ok(S.PAUSED_LANES.get("tennis_combo4") is None
       and S.lane_paused("tennis_combo4", "tennis_combo"),
       "tennis_combo4 stays paused")
    ok(S.PAUSED_LANES.get("pm_combo4") is None
       and S.lane_paused("pm_combo4", "tennis_pmcombo"),
       "pm_combo4 stays paused")

    start = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    row = dict(market_id="probe-cricket", sport="cricket", label="Alpha vs Beta",
               side_a="Alpha", side_b="Beta", price_a=0.40, price_b=0.62, mid_a=0.50,
               price_draw=None, untraded=False, tradeable={"a": True, "b": True},
               start=start, date=start[:10], volume=10.0, url="", venue="polymarket_us")
    calls = []

    def spy(name):
        def fetch(sport, _name=name):
            calls.append((_name, sport))
            return []
        return fetch

    saved_ch = S.CHALLENGERS
    saved_universe = S.UNIVERSE
    S.CHALLENGERS = {name: spy(name) for name in saved_ch}
    try:
        T.publish({"quotes": [], "meta": {}, "coverage": {}},
                  {"cricket": [row]}, {}, verbose=False)
    finally:
        S.CHALLENGERS = saved_ch
        S.UNIVERSE = saved_universe
    ok(("oddspedia", "cricket") in calls,
       "the tracker fetches oddspedia cricket")
    ok(("polymarket", "cricket") not in calls,
       "a still-paused lane is not fetched")

    print(f"\n{'FAILED: ' + str(len(FAILS)) if FAILS else 'oddspedia unpause passed'}")
    for item in FAILS:
        print(f"  - {item}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
