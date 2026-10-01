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
import tempfile
from datetime import datetime, timedelta, timezone

import production
import sandbox_audit as A
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
        T.publish(logged, {"climate": [_climate_row()], "mlb": [_mlb_row()],
                           "nfl": [_mlb_row()]}, {}, verbose=False)
        S.PAUSED_LANES = {k: v for k, v in saved_lanes.items() if k != "nws"}
        T.publish(logged_on, {"climate": [_climate_row()], "mlb": [_mlb_row()],
                              "nfl": [_mlb_row()]}, {}, verbose=False)
    finally:
        S.PAUSED_LANES = saved_lanes
        S.CHALLENGERS = saved_ch
        S.UNIVERSE = saved_universe
        S.clear_nws_run()
    weather_calls = [c for c in calls if c[0] in ("nws", "nws_fade") or c[1] == "climate"]
    eq(weather_calls, [], "no weather source is fetched")
    ok(("espn_fpi", "nfl") in calls and ("espn_fpi", "mlb") not in calls,
       "ESPN FPI NFL is still fetched and its MLB lane is not")
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
    plain = _open(id="olbg:boxing", source="olbg", sport="boxing", market_id="probe-box")
    due_ids = [q["id"] for q in SC.due({"quotes": [by_source, by_sport, plain]}, window)]
    ok("nws_fade:open" not in due_ids and "covers:climate" not in due_ids,
       "due() returns no weather rows")
    ok("olbg:boxing" in due_ids, "due() still returns a non-weather row in the window")
    fetched_ids = []

    def _price(q):
        fetched_ids.append(q["id"])
        return 0.5

    SC.run({"quotes": [by_source, by_sport, plain]}, {"closes": {}}, now=window, price=_price)
    ok(fetched_ids == ["olbg:boxing"], "a closing price is fetched only for the non-weather row")

    past = "2026-09-28T12:00:00+00:00"
    weather = dict(id="nws:KXHIGHNY-26SEP28-B70.5", source="nws", sport="climate",
                   venue="kalshi_binary", market_id="KXHIGHNY-26SEP28-B70.5",
                   status="open", bet=True, pick="a", price=0.40, stake=100.0,
                   price_a=0.40, price_b=0.62, side_a="Yes", side_b="No",
                   start=past, logged="2026-09-27T12:00:00+00:00",
                   pnl=0.0, result=None, settled=None)
    other = dict(id="espn_fpi:probe-nfl", source="espn_fpi", sport="nfl",
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

    print("\naudit does not ask or flag a frozen weather row")
    audit_now = datetime(2026, 10, 3, 0, 0, tzinfo=timezone.utc)
    audit_start = (audit_now - timedelta(days=3)).isoformat()
    graded_at = (audit_now - timedelta(hours=1)).isoformat()
    final_at = audit_now - timedelta(hours=5)

    def _audit_open(qid, source, sport, market):
        return dict(id=qid, source=source, sport=sport, venue="kalshi_binary",
                    market_id=market, bet=True, pick="a", price=0.40, price_a=0.40,
                    price_b=0.62, stake=100.0, status="open", result=None, pnl=0.0,
                    settled=None, start=audit_start,
                    logged="2026-09-27T12:00:00+00:00")

    weather_open = _audit_open("nws_fade:KXHIGHNY-26SEP29-B71.5", "nws_fade", "climate",
                               "KXHIGHNY-26SEP29-B71.5")
    plain_open = _audit_open("olbg:stale-boxing", "olbg", "boxing", "probe-stale-boxing")
    asked = []

    def _ask(mid):
        asked.append(mid)
        return "b"

    def _final(q):
        asked.append(("final", q.get("market_id")))
        return final_at

    saved_resolvers = (S.resolve_kalshi_market, S.resolve_kalshi, S.resolve_polymarket,
                       S.resolve_polymarket_us, S.resolve_combo, A._final_at, S._get)
    S.resolve_kalshi_market = _ask
    S.resolve_kalshi = _ask
    S.resolve_polymarket = _ask
    S.resolve_polymarket_us = _ask
    S.resolve_combo = lambda legs: _ask("combo")
    A._final_at = _final
    S._get = lambda *a, **k: {}
    try:
        stale_rep = A.Report()
        A.check_stale({"quotes": [weather_open, plain_open],
                       "meta": {"updated": graded_at}}, stale_rep, True, now=audit_now)
    finally:
        (S.resolve_kalshi_market, S.resolve_kalshi, S.resolve_polymarket,
         S.resolve_polymarket_us, S.resolve_combo, A._final_at, S._get) = saved_resolvers
    stale_text = " ".join(m for _c, m in stale_rep.errors + stale_rep.warnings)
    ok(weather_open["market_id"] not in asked and ("final", weather_open["market_id"]) not in asked,
       "a stale open weather bet is not resolved")
    ok(weather_open["id"] not in stale_text and "KXHIGH" not in stale_text,
       "a stale open weather bet is not an error or a warning")
    ok(any(plain_open["id"] in m for _c, m in stale_rep.errors),
       "a non-weather bet open 3 days is still flagged")
    ok(plain_open["market_id"] in asked,
       "the non-weather stale bet is still resolved")

    def _settled_row(qid, source, sport, market):
        return dict(id=qid, source=source, sport=sport, venue="kalshi_binary",
                    market_id=market, bet=True, pick="a", price=0.40, price_a=0.40,
                    price_b=0.62, stake=100.0, status="won", result="a",
                    pnl=round(100.0 * (1.0 / 0.40 - 1.0), 2),
                    start="2026-09-20T19:00:00+00:00",
                    logged="2026-09-19T12:00:00+00:00",
                    settled="2026-09-21T19:00:00+00:00")

    weather_settled = _settled_row("nws:KXHIGHNY-26SEP20-B70.5", "nws", "climate",
                                   "KXHIGHNY-26SEP20-B70.5")
    plain_settled = _settled_row("espn_fpi:probe-settle", "espn_fpi", "nfl", "probe-settle")
    settle_calls = []

    def _settle(mid):
        settle_calls.append(mid)
        return "a"

    fd, watch_path = tempfile.mkstemp(prefix="settle-", suffix=".json")
    os.close(fd)
    os.remove(watch_path)
    S.resolve_kalshi_market = _settle
    try:
        settle_rep = A.Report()
        A.check_settlement({"quotes": [weather_settled, plain_settled], "meta": {}},
                           settle_rep, 25, path=watch_path)
    finally:
        S.resolve_kalshi_market = saved_resolvers[0]
        try:
            os.remove(watch_path)
        except OSError:
            pass
    ok(weather_settled["market_id"] not in settle_calls,
       "check_settlement does not sample a settled weather row")
    ok(plain_settled["market_id"] in settle_calls,
       "check_settlement still samples a settled non-weather row")
    settle_text = " ".join(m for _c, m in settle_rep.errors + settle_rep.warnings)
    ok("KXHIGH" not in settle_text and weather_settled["id"] not in settle_text,
       "a sampled settlement check does not warn about the weather row")

    fd, watch_path = tempfile.mkstemp(prefix="settle-", suffix=".json")
    os.close(fd)
    T.save_settlement_watch([{"venue": "kalshi_binary", "market_id": weather_settled["market_id"],
                              "stored": "a", "venue_result": "b",
                              "quote_id": weather_settled["id"]}], watch_path)
    watched_calls = []

    def _watched(mid):
        watched_calls.append(mid)
        return "b"

    S.resolve_kalshi_market = _watched
    try:
        watch_rep = A.Report()
        A.check_settlement({"quotes": [weather_settled], "meta": {}},
                           watch_rep, 0, path=watch_path)
    finally:
        S.resolve_kalshi_market = saved_resolvers[0]
        try:
            os.remove(watch_path)
        except OSError:
            pass
    watch_text = " ".join(m for _c, m in watch_rep.errors + watch_rep.warnings)
    ok(watched_calls == [], "a remembered weather mismatch is not re-resolved")
    ok("KXHIGH" not in watch_text and weather_settled["id"] not in watch_text,
       "a remembered weather mismatch is not a warning")

    def _fight(qid, **kw):
        q = dict(id=qid, source="mma_fav_band", sport="mma",
                 side_a="Vanessa Demopoulos", side_b="Yazmin Jauregui",
                 start="2026-09-26T23:00:00+00:00", date="2026-09-26",
                 logged="2026-09-22T00:41:36+00:00", venue="kalshi",
                 market_id="KXUFCFIGHT-26SEP26DEMJAU",
                 bet=True, pick="a", price=0.60, price_a=0.60, price_b=0.42,
                 stake=100.0, result="a", status="won",
                 pnl=round(100.0 * (1.0 / 0.60 - 1.0), 2),
                 settled="2026-09-27T00:00:00+00:00")
        q.update(kw)
        return q

    weather_kept = _fight("nws:kept", source="nws")
    weather_later = _fight("nws:later", source="nws",
                           id="nws:aec-ufc-vandem-yazjau-2026-09-26",
                           market_id="aec-ufc-vandem-yazjau-2026-09-26",
                           venue="polymarket_us",
                           start="2026-09-26T18:30:00+00:00",
                           logged="2026-09-22T21:47:04+00:00")
    plain_kept = _fight("mma_fav_band:KXUFCFIGHT-26SEP26DEMJAU")
    plain_later = _fight("mma_fav_band:aec-ufc-vandem-yazjau-2026-09-26",
                         market_id="aec-ufc-vandem-yazjau-2026-09-26",
                         venue="polymarket_us",
                         start="2026-09-26T18:30:00+00:00",
                         logged="2026-09-22T21:47:04+00:00")
    dup_weather = A.Report()
    A.check_duplicates({"quotes": [weather_kept, weather_later]}, dup_weather)
    dup_plain = A.Report()
    A.check_duplicates({"quotes": [plain_kept, plain_later]}, dup_plain)
    ok(not dup_weather.errors and not dup_weather.warnings,
       "a settled weather pair on two venues is not flagged")
    ok(any("duplicates" == c for c, _m in dup_plain.errors),
       "a settled non-weather pair on two venues is still flagged")

    def _mentions_weather(msg):
        low = msg.lower()
        return ("nws" in low or "kxhigh" in low or "climate" in low
                or "national weather service" in low)

    ledger = T.load()

    def _ledger_stale(when):
        hits = []
        saved = (S.resolve_kalshi_market, S.resolve_kalshi, S.resolve_polymarket,
                 S.resolve_polymarket_us, S.resolve_combo, A._final_at, S._get)
        calls = []

        def _rec(mid):
            calls.append(mid)
            return "b"

        S.resolve_kalshi_market = _rec
        S.resolve_kalshi = _rec
        S.resolve_polymarket = _rec
        S.resolve_polymarket_us = _rec
        S.resolve_combo = lambda legs: _rec("combo")
        def _no_network(*_a, **_k):
            raise RuntimeError("no network")

        A._final_at = lambda q: datetime(2020, 1, 1, tzinfo=timezone.utc)
        S._get = _no_network
        try:
            rep = A.Report()
            A.check_stale(ledger, rep, True, now=when)
        finally:
            (S.resolve_kalshi_market, S.resolve_kalshi, S.resolve_polymarket,
             S.resolve_polymarket_us, S.resolve_combo, A._final_at, S._get) = saved
        flagged = [m for _c, m in rep.errors + rep.warnings if _mentions_weather(m)]
        weather_calls = [m for m in calls if isinstance(m, str) and "KXHIGH" in m.upper()]
        return rep, flagged, weather_calls

    for label, when in (("10/3", datetime(2026, 10, 3, tzinfo=timezone.utc)),
                        ("10/5", datetime(2026, 10, 5, tzinfo=timezone.utc))):
        rep, flagged, weather_calls = _ledger_stale(when)
        ok(not flagged and not weather_calls,
           f"ledger weather rows are not errors or warnings at {label}"
           + (f" — {flagged[:2]} {weather_calls[:2]}" if flagged or weather_calls else ""))
        ok(any(c == "stale" for c, _m in rep.errors),
           f"a non-weather stale bet on the ledger is still flagged at {label}")

    print(f"\n{'FAILED: ' + str(len(FAILS)) if FAILS else 'weather removal passed'}")
    for item in FAILS:
        print(f"  - {item}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
