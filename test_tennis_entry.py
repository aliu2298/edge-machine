#!/usr/bin/env python3
"""Tennis entry correctness: Challenger leaks and unverified Kalshi starts.

Polymarket US files ATP Challenger matches under the atp league, so the slug
reads as ATP. A Kalshi row whose Polymarket copy was cut by the cap carries
Kalshi's estimated start. Both have to tighten the lane.

A Challenger cross-matched to KXATPCHALLENGERMATCH is dropped. An atp-league
row with no confirming listing is unknown, never ATP. tennis_fav_band_3h does
not treat an unverified Kalshi start as inside the 3-hour window.

Inline fixtures only. No ledger, no network. Fails on main: the Challenger
slug is kept, and the estimated start is treated as inside the window.
"""
import io
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone

import sandbox_sources as S

FAILS = []
NOW = datetime(2026, 10, 3, 23, 30, tzinfo=timezone.utc)
START = datetime(2026, 10, 4, 2, 0, tzinfo=timezone.utc)


def ok(cond, why):
    print(f"  {'ok  ' if cond else 'FAIL'} {why}")
    if not cond:
        FAILS.append(why)


def eq(got, want, why):
    ok(got == want, why if got == want else f"{why} — got {got!r}, want {want!r}")


def _row(mid, venue, side_a, side_b, start=START, **extra):
    return dict(market_id=mid, sport="tennis", venue=venue, side_a=side_a, side_b=side_b,
                label=f"{side_a} vs {side_b}", price_a=0.78, price_b=0.24, price_draw=None,
                tradeable={"a": True, "b": True}, untraded=False, start=start.isoformat(),
                date=start.strftime("%Y-%m-%d"), volume=1.0, url="", mid_a=0.78, **extra)


def _ids(rows):
    return sorted(q["market_id"] for q in rows)


def _picks(rows):
    buf = io.StringIO()
    with redirect_stdout(buf):
        got = S.fetch_tennis_fav_band_3h("tennis", {"tennis": rows}, now=NOW)
    return got, buf.getvalue()


def _basket(logged, legs):
    return dict(id="pm_combo2:pmcombo2:2026-10-04:fixture", source="pm_combo2",
                sport="tennis_pmcombo", bet=True, venue="combo", status="open",
                logged=logged, date="2026-10-04", legs=legs)


def main():
    print("\nthe band and the window are unchanged")
    eq(S.BAND_BY_SPORT["tennis"], (0.77, 0.81), "the price band is still 0.77-0.81")
    eq(S.TENNIS_FAV_3H, timedelta(hours=3), "the window is still 3 hours")
    eq(S.TENNIS_FAV_KEEP, frozenset({"atp", "wtadb", "utr"}),
       "the keep set is still ATP, WTA Doubles, and UTR")
    eq(S.MAX_PER_SPORT, 40, "the per-sport cap is unchanged")

    print("\na Polymarket US Challenger is dropped, the same way Kalshi drops it")
    pm_ch = _row("aec-atp-ajerai-grilom-2026-10-03", "polymarket_us",
                 "Ajeet Rai", "Grigoriy Lomakin", pm_league="atp")
    ks_ch = _row("KXATPCHALLENGERMATCH-26OCT03RAILOM", "kalshi",
                 "Ajeet Rai", "Grigoriy Lomakin")
    ch_picks, _ch_log = _picks([pm_ch, ks_ch])
    eq(_ids(ch_picks), [],
       "Rai vs Lomakin is a Challenger on Kalshi, so the Polymarket atp slug is not a bet")
    legs = S.pm_combo_legs_by_day({"tennis": [pm_ch, ks_ch]})
    leg_ids = sorted(leg[0]["market_id"] for group in legs.values() for leg in group)
    eq(leg_ids, [], "a Challenger leg does not enter a Polymarket basket")
    after = "2026-10-03T17:58:43+00:00"
    basket = _basket(after, [
        dict(market_id="aec-atp-ajerai-grilom-2026-10-03", name="Ajeet Rai",
             pick="b", venue="polymarket_us", start=START.isoformat()),
        dict(market_id="aec-wtadb-tangxu-dabrowstefan-2026-10-03",
             name="Dabrowski G / Stefani L", pick="a", venue="polymarket_us",
             start=START.isoformat()),
    ])
    ok(S.tennis_refused_row(basket),
       "a post-reset basket with an unconfirmed Polymarket atp leg is left out of the record")
    ok(not S.tennis_refused_row(dict(basket, logged="2026-10-01T12:00:00+00:00")),
       "the same shape logged before the reset is not reclassified")
    confirmed = _basket(after, [
        dict(market_id="aec-atp-valvac-artfil-2026-10-03", name="Arthur Fils",
             pick="b", venue="polymarket_us", start=START.isoformat(), tour="atp"),
        dict(market_id="aec-wtadb-tangxu-dabrowstefan-2026-10-03",
             name="Dabrowski G / Stefani L", pick="a", venue="polymarket_us",
             start=START.isoformat(), tour="wtadb"),
    ])
    ok(not S.tennis_refused_row(confirmed),
       "a post-reset basket whose Polymarket leg was confirmed ATP stays in the record")

    print("\nan atp-league row with no listing is unknown, never ATP")
    pm_unk = _row("aec-atp-newpl-othpl-2026-10-04", "polymarket_us",
                  "Someone New", "Someone Else", pm_league="atp")
    unk_picks, _unk_log = _picks([pm_unk])
    eq(_ids(unk_picks), [],
       "no Kalshi ATP or Challenger listing means the tour is unknown and the bet is skipped")
    window = getattr(S, "tennis_start_window", lambda *a, **k: "in")
    # The Polymarket row's own start is the venue's. Unknown here is the tour,
    # which the pick list already refused. The start resolver still answers.
    ok(window(pm_unk, NOW) == "in",
       "Polymarket US publishes the start, so the window itself is readable")

    print("\nan unverified Kalshi start is not inside the 3-hour window")
    ks_est = _row("KXATPMATCH-26OCT03VACFIL", "kalshi",
                  "Valentin Vacherot", "Arthur Fils")
    est_picks, est_log = _picks([ks_est])
    eq(_ids(est_picks), [],
       "Kalshi's estimated start, unverified, is not a within-3h bet")
    ok("unverified start" in est_log and "window unknown" in est_log,
       "the skip says the start is unverified and the window is unknown")
    eq(window(ks_est, NOW), "unknown",
       "the start resolver returns unknown rather than calling the estimate inside the window")
    ks_ok = _row("KXATPMATCH-26OCT03VACFIL-OK", "kalshi",
                 "Valentin Vacherot", "Arthur Fils", start_source="tennisexplorer")
    ok_picks, _ok_log = _picks([ks_ok])
    eq(_ids(ok_picks), ["KXATPMATCH-26OCT03VACFIL-OK"],
       "the same match is a bet once Tennis Explorer has confirmed the start")
    eq(window(ks_ok, NOW), "in", "a Tennis Explorer start inside 3 hours is in the window")
    late = _row("KXATPMATCH-26OCT03LATE", "kalshi",
                "Alex de Minaur", "Andrey Rublev",
                start=NOW + timedelta(hours=3, seconds=1), start_source="tennisexplorer")
    late_picks, _late_log = _picks([late])
    eq(_ids(late_picks), [], "a confirmed start more than 3 hours out is still out")

    print("\na confirmed ATP listing is still kept")
    pm_atp = _row("aec-atp-valvac-artfil-2026-10-03", "polymarket_us",
                  "Valentin Vacherot", "Arthur Fils", pm_league="atp")
    ks_atp = _row("KXATPMATCH-26OCT03VACFIL", "kalshi",
                  "Valentin Vacherot", "Arthur Fils", start_source="tennisexplorer")
    atp_picks, _atp_log = _picks([pm_atp, ks_atp])
    eq(_ids(atp_picks), ["KXATPMATCH-26OCT03VACFIL", "aec-atp-valvac-artfil-2026-10-03"],
       "Kalshi's ATP series confirms the Polymarket row, and both verified starts are bets")

    print(f"\n{'FAILED: ' + str(len(FAILS)) if FAILS else 'tennis entry passed'}")
    for item in FAILS:
        print(f"  - {item}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    raise SystemExit(main())
