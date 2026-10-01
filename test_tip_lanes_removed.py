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
import sandbox_audit as A
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
PROD_PAIRS = {
    "mma_fav_band|mma",
    "oddspedia|cricket",
    "pm_combo4|tennis_pmcombo",
    "team1_form_l5|soccer_team1",
}


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
    for name, html in sorted(pages.items()):
        text = html_lib.unescape(html)
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

    print("\nProduction leads are unchanged")
    with open(os.path.join(ROOT, "data", "production_leads.json"), encoding="utf-8") as f:
        blob = json.load(f)
    eq(len(blob["leads"]), 11, "the live Production file still has 11 leads")
    live_pairs = {lead["pair"] for lead in blob["leads"].values()}
    ok(live_pairs <= PROD_PAIRS, f"every live lead is one of the four Production pairs ({live_pairs})")
    ok(all(not S.lane_removed(*pair.split("|", 1)) for pair in live_pairs),
       "no live lead is a removed lane")
    stages = T.load_stages()
    prod = {k for k, v in (stages.get("pairs") or {}).items() if v.get("stage") == "production"}
    eq(prod, PROD_PAIRS, "Production is still those four pairs")
    with open(os.path.join(ROOT, "data", "streak_leads.json"), encoding="utf-8") as f:
        streak = json.load(f)
    stray = [lead.get("pair") or lead.get("source") for lead in streak.get("leads", {}).values()
             if S.lane_removed((lead.get("pair") or "|").split("|", 1)[0],
                               (lead.get("pair") or "|").split("|", 1)[-1]
                               if "|" in (lead.get("pair") or "") else None)
             or lead.get("source") in S.REMOVED_SOURCES]
    eq(stray, [], "the streak file has no removed-lane lead")

    ledger = T.load()
    before_ids = set(production.build_feed(ledger, stages, now=NOW)["leads"])
    extra = dict(ledger)
    extra["quotes"] = list(ledger.get("quotes") or []) + [dict(
        id="scores24:extra-removal", source="scores24", sport="soccer", market_id="extra",
        venue="kalshi", bet=True, pick="a", price=0.44, price_a=0.44, price_b=0.30,
        side_a="Alpha", side_b="Beta", status="open", start=(NOW + timedelta(hours=20)).isoformat(),
        logged="2026-09-30T06:00:00+00:00", start_source="espn")]
    after_ids = set(production.build_feed(extra, stages, now=NOW)["leads"])
    eq(before_ids, after_ids, "a removed-lane quote does not change the Production lead set")
    eq(len(blob["leads"]), len(before_ids),
       "rebuilding the feed from the ledger returns the same 11 leads")

    print("\naudit stays clean with no network")
    rep = A.run(network=False)
    mentioned = [m for _c, m in rep.errors if _ID.search(m) or "Scores24" in m
                 or "SoccerPredictions" in m or "SportsGambler" in m]
    eq(rep.errors, [], "sandbox audit --no-network has no errors"
       + (f" — {rep.errors[:3]}" if rep.errors else ""))
    eq(mentioned, [], "and no error names a removed lane")

    print(f"\n{'FAILED: ' + str(len(FAILS)) if FAILS else 'tip-lane removal passed'}")
    for item in FAILS:
        print(f"  - {item}")
    return 1 if FAILS else 0


# (source, sport) pairs the spy must not record. Built once so the filter stays readable.
SCOPED_CALLS = {(src, {"MLB": "mlb", "Table Tennis": "table_tennis"}[sport])
                for src, sport, _short in SCOPED}


if __name__ == "__main__":
    sys.exit(main())
