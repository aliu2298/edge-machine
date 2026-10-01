#!/usr/bin/env python3
"""Tip lanes taken off the board the same way weather was.

Fails while a removed lane is still fetched, bet, or rendered. Passes once
those lanes are hidden. Stored ledger rows are not deleted. No network.
"""
import html as html_lib
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

import production
import sandbox_browser as B
import sandbox_build as SB
import sandbox_sources as S
import sandbox_track as T
import site_root

FAILS = []
NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
ROOT = os.path.dirname(os.path.abspath(__file__))

# Whole sources. Labels are the strings the pages print, including the short
# form a row uses. The id is a word, so tennis_fav_band_3h is not tennis_fav_band.
FULL = {
    "cmd_tail": ("Commodity far-tail rule",),
    "gas_nochange": ("AAA gasoline no-change rule",),
    "draftkings": ("DraftKings",),
    "scores24": ("Scores24",),
    "covers": ("Covers / OddsShark computer picks",),
    "nhl_dog_pl": ("NHL underdog +1.5",),
    "tt_band_55_60": ("Table tennis 0.55-0.60 band",),
    "tennis_fav_band": ("Tennis favourite-band rule",),
    "pinnacle": ("Pinnacle (via The Odds API)",),
    "sportsgambler": ("SportsGambler",),
    "soccerpredictions": ("SoccerPredictions.ai",),
}
# Sport-scoped. The source id and the short label stay on the sports that remain.
SCOPED = (
    ("espn_fpi", "MLB", "ESPN FPI / Matchup Predictor"),
    ("polymarket_us", "Table Tennis", "Polymarket US"),
    ("polymarket_us", "MLB", "Polymarket US"),
    ("polymarket", "Table Tennis", "Polymarket"),
    ("polymarket", "MLB", "Polymarket"),
    ("kalshi", "MLB", "Kalshi"),
)
_ID = re.compile(
    r"\b(?:cmd_tail|gas_nochange|draftkings|scores24|covers|nhl_dog_pl|"
    r"tt_band_55_60|tennis_fav_band|pinnacle|sportsgambler|soccerpredictions)\b")
_TR = re.compile(r"<tr\b.*?</tr>", re.S)
KEPT_LABELS = (
    "MMA favourite-band rule",
    "Tennis favourite band, entered within 3 hours of the start",
    "Pinnacle's goal total v Kalshi's",
    "Tennis 2-leg combo (favourite-band legs)",
    "Tennis 3-leg combo (favourite-band legs)",
    "Tennis 4-leg combo (favourite-band legs)",
    "Tennis 2-leg combo on Polymarket US",
    "Tennis 3-leg combo on Polymarket US",
    "Tennis 4-leg combo on Polymarket US",
    "Oddspedia community tips",
    "Kalshi commodity price",
    "ESPN FPI / Matchup Predictor",
)


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
    root = os.path.join(ROOT, "public_site", "index.html")
    with open(root, encoding="utf-8") as f:
        out["public_site/index.html"] = f.read()
    out.update({f"archive/{slug}.html": html for slug, html in weeks.items()})
    return out


def _full_hit(html):
    for labels in FULL.values():
        found = next((label for label in labels if label in html), None)
        if found:
            return found
    word = _ID.search(html)
    return word.group(0) if word else None


def _scoped_hit(html):
    for tr in _TR.findall(html):
        m = re.search(r'data-id="([^"]*)"', tr)
        src = m.group(1).split(":", 1)[0] if m else ""
        for source, sport_label, short in SCOPED:
            if src == source and sport_label in tr:
                return f"{source} on {sport_label}"
            if f"<b>{short}</b>" in tr and sport_label in tr:
                return f"{short} / {sport_label}"
    return None


def _row(sport, mid, venue="polymarket_us"):
    start = (NOW + timedelta(days=1)).isoformat()
    return dict(market_id=mid, sport=sport, label="Alpha vs Beta", side_a="Alpha",
                side_b="Beta", price_a=0.40, price_b=0.62, mid_a=0.50, price_draw=None,
                untraded=False, tradeable={"a": True, "b": True}, start=start,
                date=start[:10], volume=10.0, url="", venue=venue)


def _spy(name, calls):
    def fetch(sport, _name=name):
        calls.append((_name, sport))
        return [dict(market_id=f"probe-{sport}", pick="a", a="Alpha", b="Beta",
                     date=NOW.strftime("%Y-%m-%d"))]
    return fetch


def main():
    print("\nno built page renders a removed lane")
    pages = _pages()
    ok(len(pages) > 4, "sandbox, production, trading, index, and the archive are built")
    ok(any(name.startswith("archive/") and name != "archive/index.html" for name in pages),
       "every archive week is built")
    # The 3-hour lane's registered note names the retired rule. That sentence
    # was written once and stays. Everywhere else, the id is a removed lane.
    registered = S.SOURCES["tennis_fav_band_3h"]["note"]
    for name, html in sorted(pages.items()):
        text = html_lib.unescape(html).replace(registered, "")
        hit = _full_hit(text)
        ok(hit is None, f"{name} has no removed lane" + (f" ({hit})" if hit else ""))
        scoped = _scoped_hit(text)
        ok(scoped is None, f"{name} has no sport-scoped removed lane"
           + (f" ({scoped})" if scoped else ""))

    sandbox = html_lib.unescape(pages["sandbox.html"])
    for label in KEPT_LABELS:
        ok(label in sandbox, f"sandbox still shows {label}")
    ok("ESPN FPI / Matchup Predictor" in sandbox and ">NFL<" in sandbox,
       "ESPN FPI NFL stays on the sandbox page")
    ok("Pinnacle" in sandbox, "the kept Pinnacle wording stays")
    ok("favourite band" in sandbox.lower() or "favourite-band" in sandbox,
       "the favourite-band wording of the kept lanes stays")

    print("\nshared band code and the reference fetches stay")
    eq(S.fav_band("tennis"), (0.77, 0.81), "fav_band still answers for tennis")
    ok("tennis" in S.BAND_BY_SPORT and callable(S.band_picks), "BAND_BY_SPORT and band_picks stay")
    ok(S.CHALLENGERS["mma_fav_band"] is S.fetch_tennis_fav_band,
       "mma_fav_band still calls fetch_tennis_fav_band")
    ok(callable(S.combo_legs_by_day) and callable(S.pm_combo_legs_by_day),
       "both combo leg builders stay")
    for name in ("tennis_fav_band_3h", "tennis_combo2", "tennis_combo3", "tennis_combo4",
                 "pm_combo2", "pm_combo3", "pm_combo4", "pin_totals", "mma_fav_band",
                 "oddspedia", "cmd_market"):
        ok(name not in S.REMOVED_SOURCES and not S.lane_removed(name, S.SOURCES[name]["sports"][0]),
           f"{name} is not a removed lane")
    ok(not S.lane_paused("tennis_fav_band_3h", "tennis")
       and not S.lane_paused("pin_totals", "soccer_o25")
       and not S.lane_paused("mma_fav_band", "mma"),
       "the 3-hour band, pin totals, and the MMA band may still log")
    ok(S.lane_paused("tennis_combo3", "tennis_combo")
       and S.lane_paused("pm_combo4", "tennis_pmcombo")
       and not S.lane_removed("tennis_combo3", "tennis_combo")
       and not S.lane_removed("pm_combo4", "tennis_pmcombo"),
       "3- and 4-leg combos stay paused and stay visible")
    ok(callable(S.pinnacle_events) and callable(S.apply_pinnacle_starts)
       and callable(S.apply_espn_starts),
       "Pinnacle and ESPN start-time helpers stay")

    print("\nremoved lanes take no new entry, even with the pause line deleted")
    calls = []
    saved_ch = S.CHALLENGERS
    saved_lanes = dict(S.PAUSED_LANES)
    injected = dict(saved_ch)
    for name in FULL:
        injected[name] = _spy(name, calls)
    injected["espn_fpi"] = _spy("espn_fpi", calls)
    injected["polymarket"] = _spy("polymarket", calls)
    injected["polymarket_us"] = _spy("polymarket_us", calls)
    injected["kalshi"] = _spy("kalshi", calls)
    injected["tennis_fav_band_3h"] = _spy("tennis_fav_band_3h", calls)
    injected["pin_totals"] = _spy("pin_totals", calls)
    S.CHALLENGERS = injected
    S.PAUSED_LANES = {k: v for k, v in saved_lanes.items()
                      if k not in FULL and k not in ("espn_fpi", "polymarket", "kalshi")}
    logged = {"quotes": [], "meta": {}, "coverage": {}}
    universe = {
        "soccer": [_row("soccer", "probe-soccer", venue="kalshi")],
        "nfl": [_row("nfl", "probe-nfl")],
        "mlb": [_row("mlb", "probe-mlb")],
        "tennis": [_row("tennis", "probe-tennis")],
        "table_tennis": [_row("table_tennis", "probe-tt")],
        "commodities": [_row("commodities", "probe-cmd", venue="kalshi_binary")],
        "nhl_pl": [_row("nhl_pl", "probe-nhl", venue="kalshi_binary")],
        "soccer_o25": [_row("soccer_o25", "probe-o25", venue="kalshi")],
    }
    try:
        T.publish(logged, universe, {}, verbose=False)
    finally:
        S.CHALLENGERS = saved_ch
        S.PAUSED_LANES = saved_lanes
    removed_calls = [c for c in calls if c[0] in FULL or c in SCOPED_CALLS]
    eq(removed_calls, [], "no removed source or sport-scoped lane is fetched")
    ok(("espn_fpi", "nfl") in calls and ("espn_fpi", "mlb") not in calls,
       "ESPN FPI NFL is fetched and MLB is not")
    ok(("tennis_fav_band_3h", "tennis") in calls and ("pin_totals", "soccer_o25") in calls,
       "the 3-hour band and pin totals are still fetched")
    ok(not any(q.get("source") in FULL or (q.get("source"), q.get("sport")) in S.REMOVED_LANES
               for q in logged["quotes"]),
       "the run logs no removed-lane quote")
    for name in ("covers", "scores24", "pinnacle", "draftkings", "cmd_tail",
                 "tt_band_55_60", "sportsgambler", "nhl_dog_pl", "gas_nochange"):
        ok(name in S.PAUSED_LANES, f"the {name} pause line is still on the list")
    ok("soccerpredictions" not in S.PAUSED_LANES and S.lane_paused("soccerpredictions", "soccer"),
       "soccerpredictions was not on the pause list, and removal still stops it")

    print("\ntable tennis venue listings stop; MLB listings stay")
    fetched_sports = []
    saved_sports = S.SPORTS
    saved_pm = S.fetch_polymarket_us
    saved_ks = S.fetch_kalshi_venue

    def _pm(sport, stats=None):
        fetched_sports.append(("polymarket_us", sport))
        return []

    def _ks(sport, stats=None):
        fetched_sports.append(("kalshi", sport))
        return []

    saved_starts = S.apply_pinnacle_starts
    S.SPORTS = {"table_tennis": "Table Tennis", "mlb": "MLB", "tennis": "Tennis",
                "mma": "MMA", "cricket": "Cricket", "boxing": "Boxing"}
    S.fetch_polymarket_us = _pm
    S.fetch_kalshi_venue = _ks
    S.apply_pinnacle_starts = lambda sport, rows, events=None, now=None: (
        rows, dict(matched=0, dropped=0, shifts=[]))
    try:
        universe_out, _cov = T.collect(verbose=False)
    finally:
        S.SPORTS = saved_sports
        S.fetch_polymarket_us = saved_pm
        S.fetch_kalshi_venue = saved_ks
        S.apply_pinnacle_starts = saved_starts
    ok(("polymarket_us", "table_tennis") not in fetched_sports
       and ("kalshi", "table_tennis") not in fetched_sports,
       "table tennis venue listings are not fetched")
    eq(universe_out.get("table_tennis"), [], "table tennis contributes no markets")
    for sport in ("mlb", "tennis", "mma", "cricket", "boxing"):
        ok(("polymarket_us", sport) in fetched_sports,
           f"Polymarket US {sport} listings are still fetched")
    ok(("kalshi", "mlb") in fetched_sports,
       "Kalshi MLB listings stay, for the fade-the-streak rule")

    print("\nPlaywright stays for Oddspedia")
    ok(os.path.isfile(os.path.join(ROOT, "sandbox_browser.py")),
       "sandbox_browser.py is still in the tree")
    with open(os.path.join(ROOT, ".github", "workflows", "sandbox-tracker.yml"),
              encoding="utf-8") as f:
        workflow = f.read()
    ok("name: Install headless browser" in workflow
       and "playwright install --with-deps chromium" in workflow,
       "the tracker workflow still installs the headless browser")

    print("\nno listed pair is a removed lane")
    stages = T.load_stages()
    prod = [k for k, v in (stages.get("pairs") or {}).items() if v.get("stage") == "production"]
    for key in prod:
        source, _, sport = str(key).partition("|")
        ok("|" in str(key) and not S.lane_removed(source, sport),
           f"Production stage {key} is not a removed lane")
    for key in T.PAIR_OVERRIDES:
        source, _, sport = str(key).partition("|")
        ok("|" in str(key) and not S.lane_removed(source, sport),
           f"PAIR_OVERRIDES {key} is not a removed lane")
    for sport in T.FEED_BETS:
        ok(not S.lane_removed("", sport), f"FEED_BETS {sport} is not a removed lane")
    with open(os.path.join(ROOT, "data", "streak_leads.json"), encoding="utf-8") as f:
        streak = json.load(f)
    stray = [lead.get("pair") or lead.get("source") for lead in streak.get("leads", {}).values()
             if S.lane_removed((lead.get("pair") or "|").split("|", 1)[0],
                               (lead.get("pair") or "|").split("|", 1)[-1]
                               if "|" in (lead.get("pair") or "") else None)
             or lead.get("source") in S.REMOVED_SOURCES]
    eq(stray, [], "the streak file has no removed-lane lead")

    print("\nbuild_feed ignores removed-lane rows")
    ledger = T.load()
    before = production.build_feed(ledger, stages, now=NOW)
    extra_row = dict(
        id="scores24:extra-removal", source="scores24", sport="soccer",
        market_id="KXEPLGAME-26OCT02EXTRA", venue="kalshi", bet=True, pick="a", price=0.44,
        price_a=0.44, price_b=0.30, side_a="Alpha", side_b="Beta", status="open",
        start=(NOW + timedelta(hours=20)).isoformat(), logged="2026-09-30T06:00:00+00:00",
        start_source="espn")
    extra = dict(ledger)
    extra["quotes"] = list(ledger.get("quotes") or []) + [extra_row]
    after = production.build_feed(extra, stages, now=NOW)
    eq(after, before, "build_feed's output is identical with or without an extra removed-lane row")
    forced = {"pairs": {"scores24|soccer": {
        "stage": "production", "ready_at": "2026-09-01T00:00:00+00:00", "by_hand": "2026-09-01"}}}
    blocked = production.build_feed({"quotes": [extra_row]}, forced, now=NOW)
    eq(blocked["leads"], {}, "a removed lane listed as Production publishes no lead")
    eq(blocked["pairs"], {}, "and the removed pair is left out of the feed")

    print("\nOddspedia's browser session does not load a removed source")
    seen = []

    def _browser_spy(jobs, pace_ms=6000):
        seen.extend(jobs)
        return {}

    saved_fetch = B.fetch_rows
    B.fetch_rows = _browser_spy
    S._browser_cache = None
    S._oddspedia_cache = None
    S._scores24_cache = None
    try:
        S.fetch_oddspedia("cricket")
    finally:
        B.fetch_rows = saved_fetch
        S._browser_cache = None
        S._oddspedia_cache = None
        S._scores24_cache = None
    urls = [url for url, _js in seen]
    ok(any("oddspedia.com" in url and "/cricket/" in url for url in urls),
       "the Oddspedia cricket page is still requested")
    ok(not any("scores24" in url for url in urls), "no Scores24 URL is requested")
    ok(urls and all("oddspedia.com" in url for url in urls),
       "every requested page is an Oddspedia page")

    print("\nkept-lane numbers do not move when a removed row is hidden")
    _kept_lane_numbers()

    print("\naggregate tables ignore removed-lane bets")
    _aggregates_ignore_removed_rows()

    print(f"\n{'FAILED: ' + str(len(FAILS)) if FAILS else 'tip-lane removal passed'}")
    for item in FAILS:
        print(f"  - {item}")
    return 1 if FAILS else 0


def _bet(source, sport, market, price, pnl, logged, *, pick="a", status="won", result="a",
         close=None):
    """One settled bet a lane row can be judged on."""
    row = dict(
        id=f"{source}:{market}", source=source, sport=sport, market_id=market,
        venue="polymarket_us", bet=True, pick=pick, price=price, price_a=price,
        price_b=round(1 - price, 2), stake=100.0, pnl=pnl, status=status, result=result,
        side_a="Alpha", side_b="Beta", logged=logged, start="2026-09-20T18:00:00+00:00",
        settled="2026-09-20T20:00:00+00:00")
    if close is not None:
        row["close_price"] = close
        row["close_at"] = "2026-09-20T17:50:00+00:00"
    return row


def _figures(a, verdict):
    return dict(bets=a["n_bets"], settled=a["n"], roi=a["roi_fee"], z=a["z"],
                clv=a["clv"], baseline=a["base_roi"], verdict=verdict)


def _kept_lane_numbers():
    """Every number on a kept lane's built row matches the unfiltered ledger.

    A removed row logged first on another contest of the same sport moves the
    favourite baseline when the page assesses the filtered copy. The page must
    not do that. Headlines still count only the rows they render.
    """
    kept = [
        _bet("mma_fav_band", "mma", "mma-own", 0.50, 100.0, "2026-09-20T12:00:00+00:00",
             close=0.55),
        _bet("tennis_fav_band_3h", "tennis", "ten-own", 0.40, 150.0,
             "2026-09-20T12:00:00+00:00", close=0.45),
    ]
    # Logged earlier, so each is the first price on its contest. Hiding it
    # drops that contest from the favourite population.
    hidden = [
        _bet("pinnacle", "mma", "mma-hid", 0.60, -100.0, "2026-09-19T12:00:00+00:00",
             pick="b", status="lost", result="b"),
        _bet("pinnacle", "tennis", "ten-hid", 0.55, -100.0, "2026-09-19T12:00:00+00:00",
             pick="b", status="lost", result="b"),
    ]
    # The lane's own contest, priced as a favourite that wins, so the population
    # without the hidden contest is a different number.
    population = [
        dict(_bet("mma_fav_band", "mma", "mma-own", 0.80, 25.0, "2026-09-20T11:00:00+00:00"),
             bet=False, pick=None, price=None, stake=0.0, pnl=0.0, status="graded"),
        dict(_bet("tennis_fav_band_3h", "tennis", "ten-own", 0.70, 42.86,
                  "2026-09-20T11:00:00+00:00"),
             bet=False, pick=None, price=None, stake=0.0, pnl=0.0, status="graded"),
    ]
    # price_a on the population rows is the favourite. The helper set price_a
    # from `price`, which is what blind_pnl reads.
    running = dict(_bet("mma_fav_band", "mma", "mma-open", 0.50, 0.0,
                        "2026-09-30T12:00:00+00:00", status="open", result=None),
                   start=(NOW + timedelta(hours=20)).isoformat(), settled=None)
    hidden_open = dict(running, id="pinnacle:mma-open", source="pinnacle", market_id="mma-open-h")
    raw = {"quotes": kept + hidden + population + [running, hidden_open],
           "meta": {}, "coverage": {}}
    st = {"pairs": {}, "events": []}
    page_rows = {(r["name"], r["sport"]): r for r in SB.pair_list(raw, st)
                 if r["a"]["n"]}
    eq(set(page_rows), {("mma_fav_band", "mma"), ("tennis_fav_band_3h", "tennis")},
       "the fixture's measured lanes are the two kept bands")
    ok(all(not S.lane_removed(name, sport) for name, sport in page_rows),
       "every measured row is a kept lane")
    for (name, sport), row in sorted(page_rows.items()):
        tracker = T.assess(raw, name, sport, venues=T.TRADEABLE_VENUES)
        want = _figures(tracker, SB.verdict(tracker))
        got = _figures(row["a"], row["v"])
        eq(got, want, f"{name}|{sport} matches the unfiltered ledger")
        filtered = T.assess(SB.hide_removed(raw), name, sport, venues=T.TRADEABLE_VENUES)
        filtered_figures = _figures(filtered, SB.verdict(filtered))
        for field in ("bets", "settled", "roi", "z", "clv", "verdict"):
            eq(filtered_figures[field], got[field],
               f"{name}|{sport} {field} is the lane's own rows")
        ok(filtered["base_roi"] != tracker["base_roi"],
           f"hiding the removed row would move {name}|{sport}'s baseline "
           f"({filtered['base_roi']} vs {tracker['base_roi']})")
    html = SB.build(now=NOW, d=raw, st=st)
    shown = SB.hide_removed(raw)
    for name in ("mma_fav_band", "tennis_fav_band_3h"):
        full = T.assess(raw, name)["criteria"][2][3]
        gone = T.assess(shown, name)["criteria"][2][3]
        ok(full not in html,
           f"the stamp does not show {name}'s full-ledger baseline ({full})")
        ok(gone in html, f"the stamp shows the filtered baseline ({gone})")
        lane = page_rows[(name, S.SOURCES[name]["sports"][0])]
        eq(lane["a"]["base_roi"], T.assess(raw, name, lane["sport"],
                                           venues=T.TRADEABLE_VENUES)["base_roi"],
           f"{name}'s row still reads the full-ledger baseline")
    ok("2 settled on the record" in html, "the headline counts the kept bets only")
    ok(">1</b><span>bets running</span>" in html, "the running count leaves the removed bet out")


def _built_pages(d, st):
    """Every page render_pages and the other builders emit for one ledger."""
    sandbox, index, weeks = SB.render_pages(NOW, d=d, st=st)
    blob = {"leads": {}, "unlisted_skipped": 0, "unverified_kickoff_skipped": 0}
    out = {
        "sandbox.html": sandbox,
        "archive/index.html": index,
        "production.html": production.page(d, st, blob, "", now=NOW),
        "trading.html": SB.trading_page(NOW),
        "index.html": site_root.root_stub(NOW),
    }
    out.update({f"archive/{slug}.html": html for slug, html in weeks.items()})
    return out


def _region(html, start, end):
    i = html.find(start)
    if i < 0:
        return None
    j = html.find(end, i + len(start))
    return html[i:j if j >= 0 else None]


def _aggregates_ignore_removed_rows():
    """Removed-lane bets move no aggregate, and still move a kept lane's baseline.

    The stamp, the blind baselines, the by-sport section, a leaderboard and a
    source-by-sport matrix are cross-lane totals. Injecting removed-lane bets
    into the full ledger leaves every one of them, on every built page, equal
    to the ledger with those bets absent. The kept lane's own baseline does
    not: that number is read from the full ledger.
    """
    kept = [
        _bet("mma_fav_band", "mma", "mma-own", 0.50, 100.0, "2026-09-20T12:00:00+00:00"),
        _bet("kalshi", "tennis", "kalshi-ten", 0.55, 80.0, "2026-09-20T12:00:00+00:00"),
        _bet("espn_fpi", "nfl", "fpi-nfl", 0.60, -100.0, "2026-09-20T12:00:00+00:00",
             pick="b", status="lost", result="b"),
        _bet("polymarket", "nfl", "pm-nfl", 0.45, 120.0, "2026-09-20T12:00:00+00:00"),
    ]
    # Logged first on the kept contest, so it is the favourite the lane is judged
    # against. A removed quote on another contest of the same sport replaces it
    # when the baseline reads the full ledger.
    population = [
        dict(_bet("mma_fav_band", "mma", "mma-own", 0.80, 25.0, "2026-09-20T11:00:00+00:00"),
             bet=False, pick=None, price=None, stake=0.0, pnl=0.0, status="graded"),
    ]
    removed = [
        _bet("kalshi", "mlb", "kalshi-mlb", 0.40, 150.0, "2026-09-18T12:00:00+00:00"),
        _bet("espn_fpi", "mlb", "fpi-mlb", 0.52, 90.0, "2026-09-18T12:00:00+00:00"),
        _bet("polymarket", "mlb", "pm-mlb", 0.48, -100.0, "2026-09-18T12:00:00+00:00",
             pick="b", status="lost", result="b"),
        _bet("polymarket", "table_tennis", "pm-tt", 0.57, 70.0, "2026-09-18T12:00:00+00:00"),
        _bet("polymarket_us", "table_tennis", "pmus-tt", 0.62, -100.0,
             "2026-09-18T12:00:00+00:00", pick="b", status="lost", result="b"),
        _bet("polymarket_us", "mlb", "pmus-mlb", 0.44, 120.0, "2026-09-18T12:00:00+00:00"),
        _bet("pinnacle", "mma", "pin-mma", 0.70, -100.0, "2026-09-19T12:00:00+00:00",
             pick="b", status="lost", result="b"),
        _bet("scores24", "soccer", "s24-soc", 0.46, 110.0, "2026-09-18T12:00:00+00:00"),
        _bet("soccerpredictions", "soccer", "sp-soc", 0.41, -100.0,
             "2026-09-18T12:00:00+00:00", pick="b", status="lost", result="b"),
    ]
    for i in range(3):
        removed.append(_bet("tt_band_55_60", "table_tennis", f"tt-{i}", 0.58, 70.0,
                            "2026-09-17T12:00:00+00:00"))
    clean = {"quotes": kept + population, "meta": {}, "coverage": {}}
    dirty = {"quotes": kept + population + removed, "meta": {}, "coverage": {}}
    st = {"pairs": {"mma_fav_band|mma": {
        "stage": "production", "ready_at": "2026-09-01T00:00:00+00:00",
        "by_hand": "2026-09-01"}}, "events": []}
    ok(all(S.removed_row(q) for q in removed), "every injected bet is a removed lane")
    ok(T.score(dirty)["kalshi"]["bets"] > T.score(clean)["kalshi"]["bets"],
       "the injected Kalshi MLB bets would raise Kalshi's stamp count")
    ok(T.score(dirty)["espn_fpi"]["bets"] > T.score(clean)["espn_fpi"]["bets"],
       "the injected ESPN FPI MLB bets would raise that stamp count")
    ok(T.score(dirty)["polymarket"]["bets"] > T.score(clean)["polymarket"]["bets"],
       "the injected Polymarket bets would raise that stamp count")
    ok(SB.baseline_table(dirty) != SB.baseline_table(clean),
       "the injected contests would change the blind baselines")
    ok(">Table Tennis<" in SB.baseline_table(dirty)
       and ">Table Tennis<" not in SB.baseline_table(clean),
       "table tennis is a blind-baseline row only on the full ledger")
    ok(">Soccer<" in SB.baseline_table(dirty) and ">Soccer<" not in SB.baseline_table(clean),
       "soccer is a blind-baseline row only on the full ledger")
    ok(SB.leaderboard(T.score(dirty), dirty) != SB.leaderboard(T.score(clean), clean),
       "a leaderboard on the full ledger would count the removed bets")
    ok(SB.sport_matrix(dirty) != SB.sport_matrix(clean),
       "a source-by-sport matrix on the full ledger would count the removed bets")
    shown = SB.hide_removed(dirty)
    eq(SB.approval_table(shown, T.score(shown)), SB.approval_table(clean, T.score(clean)),
       "the stamp built from the filtered rows matches the ledger without them")
    eq(SB.baseline_table(shown), SB.baseline_table(clean),
       "the blind baselines built from the filtered rows match")
    eq(SB.leaderboard(T.score(shown), shown), SB.leaderboard(T.score(clean), clean),
       "a leaderboard built from the filtered rows matches")
    eq(SB.sport_matrix(shown), SB.sport_matrix(clean),
       "a source-by-sport matrix built from the filtered rows matches")
    full_base = T.assess(dirty, "mma_fav_band", "mma", venues=T.TRADEABLE_VENUES)["base_roi"]
    kept_base = T.assess(clean, "mma_fav_band", "mma", venues=T.TRADEABLE_VENUES)["base_roi"]
    ok(full_base != kept_base,
       f"the kept lane's baseline moves when the removed contest is in the ledger "
       f"({full_base} vs {kept_base})")
    row = next(r for r in SB.pair_list(dirty, st)
               if r["name"] == "mma_fav_band" and r["sport"] == "mma")
    eq(row["a"]["base_roi"], full_base, "the built row reads that full-ledger baseline")
    eq(row["v"], SB.verdict(row["a"]), "the built row's verdict is that full-ledger assess")
    pages_dirty = _built_pages(dirty, st)
    pages_clean = _built_pages(clean, st)
    eq(set(pages_dirty), set(pages_clean), "injecting removed bets builds the same pages")
    for name in sorted(pages_dirty):
        eq(pages_dirty[name], pages_clean[name],
           f"{name} is unchanged when removed-lane bets are in the ledger")
    sandbox = pages_dirty["sandbox.html"]
    for start, end, title in (
            ("Stamp of approval", "Blind baselines", "stamp of approval"),
            ("Blind baselines", "Feed coverage", "blind baselines"),
            ('id="by-sport"', 'id="reference"', "by-sport totals"),
    ):
        got = _region(sandbox, start, end)
        want = _region(pages_clean["sandbox.html"], start, end)
        ok(got is not None and got == want, f"the {title} table is unchanged")
    ok(">Table Tennis<" not in sandbox, "the page has no table-tennis baseline row")
    ok(SB.approval_table(dirty, T.score(dirty)) not in sandbox,
       "the page does not show the full-ledger stamp")
    ok(SB.baseline_table(dirty) not in sandbox,
       "the page does not show the full-ledger blind baselines")


# (source, sport) pairs the spy must not record. Built once so the filter stays readable.
SCOPED_CALLS = {(src, {"MLB": "mlb", "Table Tennis": "table_tennis"}[sport])
                for src, sport, _short in SCOPED}


if __name__ == "__main__":
    sys.exit(main())
