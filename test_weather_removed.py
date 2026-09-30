#!/usr/bin/env python3
"""Weather is off the board.

Fails while weather is still fetched, bet, graded, priced, or rendered.
Passes once those lanes are removed. Stored ledger rows are not deleted
and are not settled or repriced. No network.
"""
import copy
import os
import re
import sys
from datetime import datetime, timedelta, timezone

import production
import sandbox_build as SB
import sandbox_close as SC
import sandbox_sources as S
import sandbox_track as T
import site_root

FAILS = []
NOW = datetime(2026, 9, 30, 16, 0, tzinfo=timezone.utc)
NEEDLES = (
    "National Weather Service",
    "weather.gov",
    "nws_fade",
    "KXHIGH",
    "kxhigh",
    "city-day",
    "maximum temperature",
    ">Climate<",
    ">Climate</b>",
)
# Whole words, so nws_fade and a longer token do not count as "nws".
_WORD = re.compile(r"\b(?:nws|climate)\b", re.I)


def ok(cond, why):
    print(f"  {'ok  ' if cond else 'FAIL'} {why}")
    if not cond:
        FAILS.append(why)


def eq(got, want, why):
    ok(got == want, why if got == want else f"{why} — got {got!r}, want {want!r}")


def _pages():
    sandbox, index, weeks = SB.render_pages(NOW)
    out = {
        "sandbox.html": sandbox,
        "archive/index.html": index,
        "production.html": production.page(
            T.load(), T.load_stages(), production.load_feed(), "", now=NOW),
        "trading.html": SB.trading_page(NOW),
        "index.html": site_root.root_stub(NOW),
    }
    root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "public_site", "index.html")
    with open(root, encoding="utf-8") as f:
        out["public_site/index.html"] = f.read()
    out.update({f"archive/{slug}.html": html for slug, html in weeks.items()})
    return out


def _hit(html):
    found = next((n for n in NEEDLES if n in html), None)
    if found:
        return found
    word = _WORD.search(html)
    return word.group(0) if word else None


def _climate_row():
    start = (datetime.now(timezone.utc) + timedelta(hours=20)).isoformat()
    return dict(sport="climate", venue="kalshi_binary", market_id="KXHIGHNY-26SEP12-B77.5",
                series="KXHIGHNY", date="2026-09-12", label="bucket",
                side_a="Yes", side_b="No", price_a=0.34, price_b=0.66, mid_a=0.50,
                untraded=False, tradeable={"a": True, "b": True}, start=start,
                volume=1.0, url="")


def _mlb_row():
    start = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    return dict(market_id="probe-mlb", sport="mlb", label="Alpha vs Beta",
                side_a="Alpha", side_b="Beta", price_a=0.40, price_b=0.62, mid_a=0.50,
                price_draw=None, untraded=False, tradeable={"a": True, "b": True},
                start=start, date=start[:10], volume=10.0, url="", venue="polymarket_us")


def _spy(name, calls):
    def fetch(sport, _name=name):
        calls.append((_name, sport))
        return [dict(market_id="KXHIGHNY-26SEP12-B77.5" if sport == "climate" else f"probe-{sport}",
                     pick="b" if sport == "climate" else "a",
                     a="Yes" if sport == "climate" else "Alpha",
                     b="No" if sport == "climate" else "Beta",
                     date="2026-09-12" if sport == "climate" else None)]
    return fetch


def _weather_quote(quotes):
    return [q for q in quotes if q.get("source") in ("nws", "nws_fade") or q.get("sport") == "climate"]


def main():
    print("\nno built page renders a weather rule or bet")
    pages = _pages()
    ok(len(pages) > 4, "sandbox, production, trading, and the archive are built")
    for name, html in sorted(pages.items()):
        hit = _hit(html)
        ok(hit is None, f"{name} has no weather rule or bet" + (f" ({hit})" if hit else ""))

    print("\nno weather source is fetched or bet")
    ok(S.lane_paused("nws", "climate") and S.lane_paused("nws_fade", "climate"),
       "neither weather lane may log a new entry")
    ok(S.source_fully_paused("nws") and S.source_fully_paused("nws_fade"),
       "the tracker skips both weather fetchers")

    saved_lanes = dict(S.PAUSED_LANES)
    S.PAUSED_LANES = {k: v for k, v in S.PAUSED_LANES.items() if k != "nws"}
    try:
        ok(S.lane_paused("nws", "climate") and S.source_fully_paused("nws_fade"),
           "deleting the nws pause line does not resume weather")
    finally:
        S.PAUSED_LANES = saved_lanes

    fetched = []
    saved_sports = S.SPORTS
    saved_binary = S.fetch_kalshi_binary

    def _binary(sport, stats=None):
        fetched.append(sport)
        return []

    S.SPORTS = {"climate": "Climate"}
    S.fetch_kalshi_binary = _binary
    try:
        universe, _cov = T.collect(verbose=False)
    finally:
        S.SPORTS = saved_sports
        S.fetch_kalshi_binary = saved_binary
    eq(fetched, [], "the tracker does not fetch Kalshi climate markets")
    eq(universe.get("climate"), [], "climate contributes no markets to the run")

    calls = []
    saved_ch = S.CHALLENGERS
    saved_universe = S.UNIVERSE
    S.CHALLENGERS = {name: _spy(name, calls) for name in saved_ch}
    logged = {"quotes": [], "meta": {}, "coverage": {}}
    logged_on = {"quotes": [], "meta": {}, "coverage": {}}
    try:
        T.publish(logged, {"climate": [_climate_row()], "mlb": [_mlb_row()]}, {}, verbose=False)
        S.PAUSED_LANES = {k: v for k, v in saved_lanes.items() if k != "nws"}
        T.publish(logged_on, {"climate": [_climate_row()], "mlb": [_mlb_row()]}, {}, verbose=False)
    finally:
        S.PAUSED_LANES = saved_lanes
        S.CHALLENGERS = saved_ch
        S.UNIVERSE = saved_universe
        S.clear_nws_run()
    weather_calls = [c for c in calls if c[0] in ("nws", "nws_fade") or c[1] == "climate"]
    eq(weather_calls, [], "no weather source is fetched")
    ok(("espn_fpi", "mlb") in calls, "a non-weather lane is still fetched")
    eq(_weather_quote(logged["quotes"]), [], "the run logs no weather bet")
    eq(_weather_quote(logged_on["quotes"]), [],
       "taking nws off the pause list still logs no weather bet")

    print("\nstored weather rows are not priced or graded")
    window = datetime(2026, 9, 30, 16, 0, tzinfo=timezone.utc)

    def _open(**kw):
        row = dict(status="open", bet=True, pick="a", price=0.40, stake=100.0,
                   price_a=0.40, price_b=0.62, pnl=0.0, result=None, settled=None,
                   start=(window + timedelta(minutes=20)).isoformat(),
                   venue="polymarket_us")
        row.update(kw)
        return row

    by_source = _open(id="nws_fade:open", source="nws_fade", sport="mlb",
                      market_id="KXHIGHNY-26SEP30-B70.5")
    by_sport = _open(id="covers:climate", source="covers", sport="climate",
                     market_id="KXHIGHCHI-26SEP30-B68.5")
    plain = _open(id="covers:mlb", source="covers", sport="mlb", market_id="probe-mlb")
    due_ids = [q["id"] for q in SC.due({"quotes": [by_source, by_sport, plain]}, window)]
    ok("nws_fade:open" not in due_ids and "covers:climate" not in due_ids,
       "due() returns no weather rows")
    ok("covers:mlb" in due_ids, "due() still returns a non-weather row in the window")
    fetched_ids = []

    def _price(q):
        fetched_ids.append(q["id"])
        return 0.5

    SC.run({"quotes": [by_source, by_sport, plain]}, {"closes": {}}, now=window, price=_price)
    ok(fetched_ids == ["covers:mlb"], "a closing price is fetched only for the non-weather row")

    past = "2026-09-28T12:00:00+00:00"
    weather = dict(id="nws:KXHIGHNY-26SEP28-B70.5", source="nws", sport="climate",
                   venue="kalshi_binary", market_id="KXHIGHNY-26SEP28-B70.5",
                   status="open", bet=True, pick="a", price=0.40, stake=100.0,
                   price_a=0.40, price_b=0.62, side_a="Yes", side_b="No",
                   start=past, logged="2026-09-27T12:00:00+00:00",
                   pnl=0.0, result=None, settled=None)
    other = dict(id="espn_fpi:probe-mlb", source="espn_fpi", sport="mlb",
                 venue="polymarket_us", market_id="probe-mlb",
                 status="open", bet=True, pick="a", price=0.40, stake=100.0,
                 price_a=0.40, price_b=0.62, side_a="Alpha", side_b="Beta",
                 start=past, logged="2026-09-27T12:00:00+00:00",
                 pnl=0.0, result=None, settled=None)
    before = copy.deepcopy(weather)
    resolved = []
    saved_kalshi = S.resolve_kalshi_market
    saved_pm = S.resolve_polymarket_us

    def _kalshi(mid):
        resolved.append(("kalshi_binary", mid))
        return "a"

    def _pm(mid):
        resolved.append(("polymarket_us", mid))
        return "a"

    S.resolve_kalshi_market = _kalshi
    S.resolve_polymarket_us = _pm
    try:
        T.grade({"quotes": [weather, other], "meta": {}}, verbose=False,
                now=datetime(2026, 10, 1, 18, 0, tzinfo=timezone.utc), mismatches=set())
    finally:
        S.resolve_kalshi_market = saved_kalshi
        S.resolve_polymarket_us = saved_pm
    ok(weather == before, "grade() leaves an open weather row unchanged")
    eq(other.get("status"), "won", "grade() still settles a non-weather row")
    ok(("kalshi_binary", weather["market_id"]) not in resolved,
       "grade() does not resolve a weather market")
    ok(("polymarket_us", other["market_id"]) in resolved,
       "grade() still resolves the non-weather market")

    print(f"\n{'FAILED: ' + str(len(FAILS)) if FAILS else 'weather removal passed'}")
    for item in FAILS:
        print(f"  - {item}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
