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


def _save_kalshi():
    return dict(
        cache=dict(S._kalshi_open_cache),
        good=dict(getattr(S, "_kalshi_tour_good", {})),
        fetch=dict(getattr(S, "_kalshi_open_fetch", {})),
        get=S._get,
        http=getattr(S, "_kalshi_http", None),
        backoff=getattr(S, "_KALSHI_OPEN_BACKOFF_S", None),
    )


def _restore_kalshi(saved):
    S._kalshi_open_cache.clear()
    S._kalshi_open_cache.update(saved["cache"])
    if hasattr(S, "_kalshi_tour_good"):
        S._kalshi_tour_good.clear()
        S._kalshi_tour_good.update(saved["good"])
    if hasattr(S, "_kalshi_open_fetch"):
        S._kalshi_open_fetch.clear()
        S._kalshi_open_fetch.update(saved["fetch"])
    S._get = saved["get"]
    if saved["http"] is not None:
        S._kalshi_http = saved["http"]
    elif hasattr(S, "_kalshi_http"):
        del S._kalshi_http
    if saved["backoff"] is not None:
        S._KALSHI_OPEN_BACKOFF_S = saved["backoff"]


def _drop_series(series):
    S._kalshi_open_cache.pop(series, None)
    good = getattr(S, "_kalshi_tour_good", None)
    fetch = getattr(S, "_kalshi_open_fetch", None)
    if good is not None:
        good.pop(series, None)
    if fetch is not None:
        fetch.pop(series, None)


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

    print("\nan open ATP listing still confirms the tour after Kalshi's estimate has passed")
    # Tonight's Fils case: Kalshi estimate 02:00Z, Polymarket start 07:00Z. At 04:30Z
    # the estimate is already past, so fetch_kalshi_venue returns nothing. The open
    # market is still in the per-run cache and must confirm ATP. No further fetch.
    gone_now = datetime(2026, 10, 4, 4, 30, tzinfo=timezone.utc)
    gone_exp = datetime(2026, 10, 4, 5, 0, tzinfo=timezone.utc)
    def _mk(code, name, ask):
        return dict(event_ticker="KXATPMATCH-26OCT03VACFIL",
                    ticker=f"KXATPMATCH-26OCT03VACFIL-{code}",
                    yes_sub_title=name, yes_bid_dollars=str(ask - 0.01),
                    yes_ask_dollars=str(ask),
                    expected_expiration_time=gone_exp.isoformat().replace("+00:00", "Z"))
    saved = _save_kalshi()
    fetches = {"n": 0}

    def _counting_http(*_a, **_k):
        fetches["n"] += 1
        raise RuntimeError("stubbed fetch")

    S._kalshi_open_cache.clear()
    for series in S.KALSHI_VENUE_SERIES["tennis"]:
        S._kalshi_open_cache[series] = []
    S._kalshi_open_cache["KXATPMATCH"] = [
        _mk("VAC", "Valentin Vacherot", 0.23), _mk("FIL", "Arthur Fils", 0.78)]
    S._kalshi_http = _counting_http
    try:
        gone_ks = S.fetch_kalshi_venue("tennis", now=gone_now)
        eq(len(gone_ks), 0,
           "the passed estimate drops the Kalshi row, so the venue list is empty")
        gone_pm = _row("aec-atp-valvac-artfil-2026-10-03", "polymarket_us",
                       "Valentin Vacherot", "Arthur Fils",
                       start=datetime(2026, 10, 4, 7, 0, tzinfo=timezone.utc),
                       pm_league="atp")
        gone_pm["price_a"], gone_pm["price_b"] = 0.22, 0.79
        S.apply_pm_atp_tours([gone_pm], gone_ks)
        eq(gone_pm.get("tour"), "atp",
           "the open KXATPMATCH market still classifies the Polymarket row as ATP")
        buf = io.StringIO()
        with redirect_stdout(buf):
            gone_picks = S.fetch_tennis_fav_band_3h(
                "tennis", {"tennis": [gone_pm]}, now=gone_now)
        eq(_ids(gone_picks), ["aec-atp-valvac-artfil-2026-10-03"],
           "Fils at 0.79, 2.5h ahead, is a bet once the open listing confirms ATP")
        eq(fetches["n"], 0,
           "reading the open-market cache does not fetch again")
    finally:
        _restore_kalshi(saved)

    print("\na shared given name on another day is not the same match")
    far_pm = _row("aec-atp-alemol-danrin-2026-10-05", "polymarket_us",
                  "Alex Molcan", "Daniel Rincon",
                  start=datetime(2026, 10, 5, 15, 0, tzinfo=timezone.utc),
                  pm_league="atp")
    far_ks = _row("KXATPMATCH-26OCT01ALEMIN", "kalshi",
                  "Alex de Minaur", "Daniel Altmaier",
                  start=datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc))
    S.apply_pm_atp_tours([far_pm], [far_ks])
    eq(far_pm.get("tour"), "unknown",
       "Molcan/Rincon does not inherit ATP from de Minaur/Altmaier four days earlier")
    near_pm = _row("aec-atp-alemol-danrin-2026-10-02", "polymarket_us",
                   "Alex Molcan", "Daniel Rincon",
                   start=datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc),
                   pm_league="atp")
    near_ks = _row("KXATPMATCH-26OCT01ALEMIN", "kalshi",
                   "Alex Molcan", "Daniel Rincon",
                   start=datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc))
    S.apply_pm_atp_tours([near_pm], [near_ks])
    eq(near_pm.get("tour"), "atp",
       "the same two players a day apart are still the ATP listing")

    print("\na failed or empty Kalshi fetch is not a listing")
    ok(getattr(S, "_KALSHI_OPEN_ATTEMPTS", 99) <= 3,
       "a refused series is retried only a few times")
    ok(sum(getattr(S, "_KALSHI_OPEN_BACKOFF_S", (9, 9))) <= 2,
       "the backoff between those tries stays under two seconds")
    saved = _save_kalshi()
    S._KALSHI_OPEN_BACKOFF_S = (0, 0)
    try:
        calls = {"n": 0}

        def _deny(url, timeout=30):
            calls["n"] += 1
            return 429, {"error": {"code": "too_many_requests"}}

        def _empty_body(url, timeout=30):
            calls["n"] += 1
            return 200, {"markets": [], "cursor": ""}

        def _then_ok(url, timeout=30):
            calls["n"] += 1
            if calls["n"] == 1:
                return 503, {}
            return 200, {"markets": [
                _mk("VAC", "Valentin Vacherot", 0.23),
                _mk("FIL", "Arthur Fils", 0.78)], "cursor": ""}

        _drop_series("KXATPMATCH")
        S._kalshi_http = _deny
        S._get = lambda url, tries=2, timeout=30: {"error": {"code": "too_many_requests"}}
        buf = io.StringIO()
        with redirect_stdout(buf):
            refused = S._kalshi_open("KXATPMATCH")
        log = buf.getvalue()
        eq(refused, [], "a 429 does not invent markets")
        ok(calls["n"] >= 2, "a 429 is retried")
        ok("fetch failed" in log and "KXATPMATCH" in log and "429" in log,
           "a 429 is logged with the series and the status")
        basis = getattr(S, "kalshi_tour_fetch", lambda: "ok")()
        eq(basis, "failed", "a 429 is a failed fetch, not a finished book")
        denied_pm = _row("aec-atp-ajerai-grilom-2026-10-03", "polymarket_us",
                         "Ajeet Rai", "Grigoriy Lomakin", pm_league="atp")
        denied_ks = _row("KXATPCHALLENGERMATCH-26OCT03RAILOM", "kalshi",
                         "Ajeet Rai", "Grigoriy Lomakin")
        S.apply_pm_atp_tours([denied_pm], [denied_ks])
        eq(denied_pm.get("tour"), "unknown",
           "with no good cached listing the tour is unknown")
        ok(denied_pm.get("tour") != "atpch" and basis != "ok",
           "a failed fetch is not Challenger and is not 'not listed'")

        for series in ("KXATPMATCH", "KXATPCHALLENGERMATCH"):
            _drop_series(series)
        calls["n"] = 0
        S._kalshi_http = _empty_body
        buf = io.StringIO()
        with redirect_stdout(buf):
            S._kalshi_open("KXATPMATCH")
            S._kalshi_open("KXATPCHALLENGERMATCH")
        empty_basis = getattr(S, "kalshi_tour_fetch", lambda: "ok")()
        eq(empty_basis, "empty", "an empty 200 is not a book of who is playing")
        ok("came back empty" in buf.getvalue() and "KXATPMATCH" in buf.getvalue(),
           "an empty book is logged with the series")
        empty_pm = _row("aec-atp-valvac-artfil-2026-10-03", "polymarket_us",
                        "Valentin Vacherot", "Arthur Fils", pm_league="atp")
        S.apply_pm_atp_tours([empty_pm], [])
        eq(empty_pm.get("tour"), "unknown",
           "an empty fetch with no good listing leaves the tour unknown")
        ok(empty_pm.get("tour") != "atpch" and empty_basis != "ok",
           "an empty fetch is not Challenger and is not 'not listed'")

        for series in ("KXATPMATCH", "KXATPCHALLENGERMATCH"):
            _drop_series(series)
        calls["n"] = 0
        S._kalshi_http = _then_ok
        recovered = S._kalshi_open("KXATPMATCH")
        eq(len(recovered), 2, "a 503 is retried and the following 200 is the book")
        ok(calls["n"] >= 2, "the retry is a second fetch, not a silent empty")

        for series in ("KXATPMATCH", "KXATPCHALLENGERMATCH"):
            _drop_series(series)
        if hasattr(S, "_kalshi_tour_good") and hasattr(S, "_kalshi_open_fetch"):
            S._kalshi_tour_good["KXATPMATCH"] = [
                _mk("VAC", "Valentin Vacherot", 0.23), _mk("FIL", "Arthur Fils", 0.78)]
            S._kalshi_tour_good["KXATPCHALLENGERMATCH"] = [
                dict(event_ticker="KXATPCHALLENGERMATCH-26OCT03OTHER",
                     ticker="KXATPCHALLENGERMATCH-26OCT03OTHER-AAA",
                     yes_sub_title="Ajeet Rai"),
                dict(event_ticker="KXATPCHALLENGERMATCH-26OCT03OTHER",
                     ticker="KXATPCHALLENGERMATCH-26OCT03OTHER-BBB",
                     yes_sub_title="Grigoriy Lomakin")]
            for series in S.KALSHI_VENUE_SERIES["tennis"]:
                S._kalshi_open_fetch[series] = {"status": "failed", "http": 429}
        calls["n"] = 0
        S._kalshi_http = _deny
        kept = S.fetch_kalshi_venue("tennis", now=gone_now)
        eq(len(kept), 0, "the last good book is not returned as venue rows")
        eq(calls["n"], 0, "a stored failure is not fetched again")
        kept_pm = _row("aec-atp-valvac-artfil-2026-10-03", "polymarket_us",
                       "Valentin Vacherot", "Arthur Fils",
                       start=datetime(2026, 10, 4, 7, 0, tzinfo=timezone.utc),
                       pm_league="atp")
        S.apply_pm_atp_tours([kept_pm], [])
        eq(kept_pm.get("tour"), "atp",
           "the last good same-day listing confirms the tour and nothing else")
    finally:
        _restore_kalshi(saved)

    print(f"\n{'FAILED: ' + str(len(FAILS)) if FAILS else 'tennis entry passed'}")
    for item in FAILS:
        print(f"  - {item}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    raise SystemExit(main())
