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
import subprocess
import urllib.error
import urllib.request
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
    print("\nthe parent band stays narrow; the 3-hour lane is the wide one")
    eq(S.BAND_BY_SPORT["tennis"], (0.77, 0.81),
       "tennis_fav_band is still 0.77-0.81")
    eq(S.TENNIS_3H_BAND, (0.70, 0.85), "the 3-hour lane backs 0.70-0.85 from 2026-10-04")
    edge = [_row(f"aec-atp-p{int(p * 100)}-bb-2026-10-04", "polymarket_us", "A", "B")
            for p in (0.69, 0.70, 0.84, 0.85)]
    for r, p in zip(edge, (0.69, 0.70, 0.84, 0.85)):
        r["price_a"], r["price_b"], r["pm_league"], r["tour"] = p, round(1.02 - p, 2), "atp", "atp"
    got = sorted(q["market_id"] for q in S.fetch_tennis_fav_band_3h(
        "tennis", {"tennis": edge}, now=NOW))
    eq(got, ["aec-atp-p70-bb-2026-10-04", "aec-atp-p84-bb-2026-10-04"],
       "0.70 and 0.84 are in the 3-hour band; 0.69 and 0.85 are not")
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

    print("\na silent Kalshi outage stays well under a minute")
    clock = {"t": 0.0}
    curls = {"n": 0}
    opens = {"n": 0, "timeouts": []}
    real_sleep, real_open, real_run = S.time.sleep, urllib.request.urlopen, subprocess.run

    def _urlopen_timeout(req, timeout=None, *args, **kwargs):
        opens["n"] += 1
        opens["timeouts"].append(timeout)
        clock["t"] += float(timeout)
        raise TimeoutError("timed out")

    def _curl_hangs(cmd, **kwargs):
        curls["n"] += 1
        if "--max-time" in cmd:
            clock["t"] += float(cmd[cmd.index("--max-time") + 1])
        raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout") or 0)

    def _sleep(seconds):
        clock["t"] += float(seconds)

    saved = _save_kalshi()
    try:
        for series in S.KALSHI_VENUE_SERIES["tennis"]:
            _drop_series(series)
        S.time.sleep = _sleep
        urllib.request.urlopen = _urlopen_timeout
        subprocess.run = _curl_hangs
        buf = io.StringIO()
        with redirect_stdout(buf):
            silenced = S._kalshi_open("KXATPMATCH")
        eq(silenced, [], "a timeout does not invent markets")
        eq(curls["n"], 0, "a timeout does not fall through to curl")
        eq(opens["n"], getattr(S, "_KALSHI_OPEN_ATTEMPTS", 3), "a timeout is still retried")
        short = getattr(S, "_KALSHI_HTTP_TIMEOUT", None)
        ok(short is not None and opens["timeouts"]
           and all(t == short for t in opens["timeouts"]),
           "each attempt uses the short timeout")
        bound = (S.kalshi_silent_outage_seconds()
                 if hasattr(S, "kalshi_silent_outage_seconds") else None)
        ok(bound is not None and round(clock["t"], 3) == round(bound, 3),
           "the fake clock equals the stated outage bound"
           if bound is not None and round(clock["t"], 3) == round(bound, 3)
           else f"the fake clock equals the stated outage bound — clock {clock['t']}, bound {bound}")
        ok(bound is not None and bound < 45,
           "one series fails well under a minute"
           if bound is not None and bound < 45
           else f"one series fails well under a minute — bound {bound}, clock {clock['t']}")
        workers = getattr(S, "_KALSHI_OPEN_WORKERS", None)
        ok(workers is not None and len(S.KALSHI_VENUE_SERIES["tennis"]) <= workers,
           "the tennis series share one fetch wave, so a full outage costs one series")
        ok("fetch failed" in buf.getvalue() and "not listed" not in buf.getvalue(),
           "the timeout is logged as a fetch failure, not as 'not listed'")

        _drop_series("KXATPMATCH")

        def _urlopen_wrapped(req, timeout=None, *args, **kwargs):
            raise urllib.error.URLError(TimeoutError("timed out"))

        urllib.request.urlopen = _urlopen_wrapped
        curls["n"] = 0
        with redirect_stdout(io.StringIO()):
            S._kalshi_open("KXATPMATCH")
        eq(curls["n"], 0, "a URLError timeout does not fall through to curl")

        _drop_series("KXWTAMATCH")

        def _urlopen_refused(req, timeout=None, *args, **kwargs):
            raise ConnectionRefusedError("refused")

        def _curl_fast(cmd, **kwargs):
            curls["n"] += 1

            class _Done:
                stdout = "\n0"

            return _Done()

        urllib.request.urlopen = _urlopen_refused
        subprocess.run = _curl_fast
        curls["n"] = 0
        with redirect_stdout(io.StringIO()):
            S._kalshi_open("KXWTAMATCH")
        ok(curls["n"] >= 1, "a connection refusal still tries curl")
    finally:
        S.time.sleep = real_sleep
        urllib.request.urlopen = real_open
        subprocess.run = real_run
        _restore_kalshi(saved)

    print("\na Challenger failure does not blank a confirmed ATP match")

    def _atp_book(url, timeout=None):
        if "KXATPCHALLENGERMATCH" in url:
            return 429, {}
        if "KXATPMATCH" in url:
            return 200, {"markets": [
                dict(event_ticker="KXATPMATCH-26OCT04VACFIL",
                     ticker="KXATPMATCH-26OCT04VACFIL-VAC",
                     yes_sub_title="Valentin Vacherot",
                     yes_bid_dollars="0.21", yes_ask_dollars="0.22"),
                dict(event_ticker="KXATPMATCH-26OCT04VACFIL",
                     ticker="KXATPMATCH-26OCT04VACFIL-FIL",
                     yes_sub_title="Arthur Fils",
                     yes_bid_dollars="0.77", yes_ask_dollars="0.79"),
            ], "cursor": ""}
        return 200, {"markets": [], "cursor": ""}

    def _fils():
        row = _row("aec-atp-valvac-artfil-2026-10-03", "polymarket_us",
                   "Valentin Vacherot", "Arthur Fils", pm_league="atp")
        row["price_a"], row["price_b"] = 0.22, 0.79
        return row

    def _rai():
        return _row("aec-atp-ajerai-grilom-2026-10-03", "polymarket_us",
                    "Ajeet Rai", "Grigoriy Lomakin", pm_league="atp")

    saved = _save_kalshi()
    S._KALSHI_OPEN_BACKOFF_S = (0, 0)
    try:
        for series in ("KXATPMATCH", "KXATPCHALLENGERMATCH", "KXWTAMATCH"):
            _drop_series(series)
        S._kalshi_http = _atp_book
        buf = io.StringIO()
        with redirect_stdout(buf):
            S._kalshi_open("KXATPMATCH")
            S._kalshi_open("KXATPCHALLENGERMATCH")
        ch_log = buf.getvalue()
        eq(S.kalshi_tour_fetch(), "ok",
           "a Challenger 429 does not fail the ATP book")
        ok("KXATPCHALLENGERMATCH" in ch_log and "fetch failed" in ch_log
           and "not listed" not in ch_log,
           "the Challenger 429 is its own fetch-failed line, not 'not listed'")
        fils, rai = _fils(), _rai()
        S.apply_pm_atp_tours([fils, rai], [])
        eq(fils.get("tour"), "atp",
           "Fils stays ATP when the ATP book names both players")
        eq(rai.get("tour"), "unknown",
           "Rai is not in the ATP book, so a missing Challenger book leaves him unknown")
        buf = io.StringIO()
        with redirect_stdout(buf):
            kept = S.fetch_tennis_fav_band_3h("tennis", {"tennis": [fils, rai]}, now=NOW)
        eq(_ids(kept), ["aec-atp-valvac-artfil-2026-10-03"],
           "the confirmed ATP match is still a bet")
        ok("not listed" in buf.getvalue() and "ajerai" in buf.getvalue(),
           "the unlisted row says not listed")
        ok("fetch failed" not in buf.getvalue().split("ajerai")[-1],
           "that not-listed line is not a fetch failure")

        for series in ("KXATPMATCH", "KXATPCHALLENGERMATCH"):
            _drop_series(series)

        def _atp_book_empty_ch(url, timeout=None):
            if "KXATPCHALLENGERMATCH" in url:
                return 200, {"markets": [], "cursor": ""}
            return _atp_book(url, timeout)

        S._kalshi_http = _atp_book_empty_ch
        buf = io.StringIO()
        with redirect_stdout(buf):
            S._kalshi_open("KXATPMATCH")
            S._kalshi_open("KXATPCHALLENGERMATCH")
        eq(S.kalshi_tour_fetch(), "ok",
           "an empty Challenger body does not fail the ATP book")
        ok("came back empty" in buf.getvalue() and "KXATPCHALLENGERMATCH" in buf.getvalue(),
           "the empty Challenger book is logged on its own line")
        fils = _fils()
        S.apply_pm_atp_tours([fils], [])
        eq(fils.get("tour"), "atp",
           "an empty Challenger book does not wipe an ATP confirmation")

        for series in ("KXATPMATCH", "KXATPCHALLENGERMATCH"):
            _drop_series(series)

        def _atp_down(url, timeout=None):
            if "KXATPMATCH" in url:
                return 429, {}
            if "KXATPCHALLENGERMATCH" in url:
                return 200, {"markets": [
                    dict(event_ticker="KXATPCHALLENGERMATCH-26OCT04RAILOM",
                         ticker="KXATPCHALLENGERMATCH-26OCT04RAILOM-RAI",
                         yes_sub_title="Ajeet Rai"),
                    dict(event_ticker="KXATPCHALLENGERMATCH-26OCT04RAILOM",
                         ticker="KXATPCHALLENGERMATCH-26OCT04RAILOM-LOM",
                         yes_sub_title="Grigoriy Lomakin"),
                ], "cursor": ""}
            return 200, {"markets": [], "cursor": ""}

        S._kalshi_http = _atp_down
        buf = io.StringIO()
        with redirect_stdout(buf):
            S._kalshi_open("KXATPMATCH")
            S._kalshi_open("KXATPCHALLENGERMATCH")
            down_fils, down_rai = _fils(), _rai()
            S.apply_pm_atp_tours([down_fils, down_rai], [])
            S.fetch_tennis_fav_band_3h(
                "tennis", {"tennis": [down_fils, down_rai]}, now=NOW)
        down_log = buf.getvalue()
        eq(S.kalshi_tour_fetch(), "failed",
           "a failed ATP book still fails closed")
        eq(down_fils.get("tour"), "unknown",
           "with the ATP book down, a real ATP match is unknown")
        eq(down_rai.get("tour"), "unknown",
           "a good Challenger book is not used when the ATP book failed")
        ok("KXATPMATCH" in down_log and "fetch failed" in down_log,
           "the ATP failure has its own line")
        ok("not listed" not in down_log,
           "that line does not say the match is not listed")
    finally:
        _restore_kalshi(saved)

    print("\na shared given name on the same day is not the same match")
    same_pm = _row("aec-atp-alemol-danrin-2026-10-01", "polymarket_us",
                   "Alex Molcan", "Daniel Rincon",
                   start=datetime(2026, 10, 1, 18, 0, tzinfo=timezone.utc),
                   pm_league="atp")
    same_ks = _row("KXATPMATCH-26OCT01ALEMIN", "kalshi",
                   "Alex de Minaur", "Daniel Altmaier",
                   start=datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc))
    S.apply_pm_atp_tours([same_pm], [same_ks])
    eq(same_pm.get("tour"), "unknown",
       "Molcan/Rincon does not inherit ATP from de Minaur/Altmaier on the same day")
    ordered = _row("aec-atp-artfil-valvac-2026-10-03", "polymarket_us",
                   "Fils Arthur", "Vacherot Valentin", pm_league="atp")
    listed = _row("KXATPMATCH-26OCT03VACFIL", "kalshi",
                  "Valentin Vacherot", "Arthur Fils")
    S.apply_pm_atp_tours([ordered], [listed])
    eq(ordered.get("tour"), "atp",
       "surname-first writing still matches both players")
    initial = _row("aec-atp-artfil-valvac-2026-10-03b", "polymarket_us",
                   "A. Fils", "V. Vacherot", pm_league="atp")
    S.apply_pm_atp_tours([initial], [listed])
    eq(initial.get("tour"), "atp",
       "an initial plus the surname still matches both players")

    print("\na later Kalshi page failure keeps the pages already read")
    saved = _save_kalshi()
    S._KALSHI_OPEN_BACKOFF_S = (0, 0)
    try:
        pages = {"n": 0}

        def _page2_down(url, timeout=None):
            pages["n"] += 1
            if "cursor=" in url:
                return 429, {}
            return 200, {"markets": [
                {"ticker": "KXNFLGAME-26OCT10XX-H",
                 "event_ticker": "KXNFLGAME-26OCT10XX",
                 "yes_sub_title": "Home"}], "cursor": "next"}

        _drop_series("KXNFLGAME")
        S._kalshi_http = _page2_down
        buf = io.StringIO()
        with redirect_stdout(buf):
            kept_page = S._kalshi_open("KXNFLGAME")
        page_log = buf.getvalue()
        eq([m.get("ticker") for m in kept_page], ["KXNFLGAME-26OCT10XX-H"],
           "page 1 is kept when page 2 fails")
        eq(pages["n"], 4, "page 2 is retried, and page 1 is not fetched again")
        ok("page 2" in page_log and "fetch failed" in page_log and "keeping 1" in page_log
           and "KXNFLGAME" in page_log,
           "the page-2 failure is logged on its own line, with the series")
        ok("not listed" not in page_log,
           "a page failure is not logged as 'not listed'")

        _drop_series("KXNFLGAME")

        def _page1_down(url, timeout=None):
            return 503, {}

        S._kalshi_http = _page1_down
        buf = io.StringIO()
        with redirect_stdout(buf):
            dropped = S._kalshi_open("KXNFLGAME")
        eq(dropped, [], "a failure on page 1 still returns no markets")
        ok("fetch failed" in buf.getvalue() and "keeping" not in buf.getvalue(),
           "page 1 has nothing to keep, and the log says so")
    finally:
        _restore_kalshi(saved)

    print("\nthe combo notes print the reset instant, and the 3-hour note matches the baskets")
    for name in sorted(S.TENNIS_COMBO_RESET):
        note = S.SOURCES[name]["note"]
        ok(S.TENNIS_COMBO_BAND_SINCE in note,
           f"{name} prints {S.TENNIS_COMBO_BAND_SINCE}")
        ok("TENNIS_COMBO_BAND_SINCE" not in note,
           f"{name} does not print the constant name")
    band_note = S.SOURCES["tennis_fav_band_3h"]["note"]
    ok("0.77-0.81 legs" not in band_note,
       "the 3-hour note does not say the baskets keep 0.77-0.81 legs")
    ok("the same 0.70-0.85 legs" in band_note,
       "the 3-hour note says the baskets cut the same 0.70-0.85 legs")

    print(f"\n{'FAILED: ' + str(len(FAILS)) if FAILS else 'tennis entry passed'}")
    for item in FAILS:
        print(f"  - {item}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    raise SystemExit(main())
