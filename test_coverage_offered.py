#!/usr/bin/env python3
"""Offered-row denominator on coverage[sport][source].

A lane that was offered nothing records 0 of 0. A lane that was offered rows
and took none records 0 of n. The denominator is the rows that lane examined:
the right series and venue, before its own band.

Fails on a tree that still stores a bare match count. Passes once publish
writes picked and offered.
"""
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import sandbox_build as BUILD
import sandbox_sources as S
import sandbox_track as T

FAILS = []
LANES = (
    "ere_draw", "ere_o15", "bund_o35", "bund_o35_fav", "liga_btts_even",
    "liga_u15_dog", "turkey_o25_dog", "turkey_btts_dog", "mls_away_band",
    "mls_fade_home",
)
START = (datetime.now(timezone.utc) + timedelta(days=3)).replace(microsecond=0).isoformat()


def ok(cond, why):
    print(f"  {'ok  ' if cond else 'FAIL'} {why}")
    if not cond:
        FAILS.append(why)


def eq(got, want, why):
    ok(got == want, why if got == want else f"{why} — got {got!r}, want {want!r}")


def cell(d, sport, name):
    return ((d.get("coverage") or {}).get(sport) or {}).get(name)


def board(**kw):
    side_a = kw.get("side_a") or f"H-{kw.get('market_id', 'x')[-8:]}"
    side_b = kw.get("side_b") or f"A-{kw.get('market_id', 'x')[-8:]}"
    row = dict(
        side_a=side_a, side_b=side_b, label=f"{side_a} vs {side_b}",
        date=START[:10], start=START, url="https://kalshi.com/markets/x",
        untraded=False, tradeable={"a": True, "draw": True, "b": True},
        price_draw=None, venue="kalshi",
    )
    row.update(kw)
    return row


def run(name, universe, prior=None):
    saved_ch, saved_u = S.CHALLENGERS, S.UNIVERSE
    S.CHALLENGERS = {name: saved_ch[name]}
    d = {"quotes": [], "meta": {}, "coverage": {}}
    try:
        T.publish(d, universe, {} if prior is None else prior, verbose=False)
    finally:
        S.CHALLENGERS, S.UNIVERSE = saved_ch, saved_u
    return d


def main():
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    print(f"HEAD {head}")

    eq((S.ERE_DRAW_BAND, S.ERE_DRAW_MAX_ASK, S.ERE_DRAW_SERIES),
       ((0.20, 0.25), 0.26, "KXEREDIVISIEGAME"),
       "ere_draw band, ceiling and series are unchanged")
    eq((S.ERE_O15_DOG_BAND, S.ERE_O15_MAX_ASK, S.ERE_O15_TOTAL),
       ((0.234, 0.296), 0.81, "KXEREDIVISIETOTAL"),
       "ere_o15 band, ceiling and series are unchanged")
    eq((S.BUND_O35_FAV_BAND, S.BUND_O35_FAV_MAX_ASK, S.BUND_O35_MAX_HOLD, S.BUND_O35_TOTAL),
       ((0.363, 0.481), 0.41, 0.06, "KXBUNDESLIGATOTAL"),
       "bund_o35 band, ceiling, hold and series are unchanged")
    eq((S.LIGA_BTTS_FAV_BAND, S.LIGA_BTTS_MAX_ASK, S.LIGA_U15_DOG_MAX, S.LIGA_U15_MAX_ASK,
        S.LIGA_MAX_HOLD),
       ((0.470, 0.590), 0.54, 0.135, 0.20, 0.06),
       "La Liga bands, ceilings and hold are unchanged")
    eq((S.TURKEY_O25_DOG_MAX, S.TURKEY_O25_MAX_ASK, S.TURKEY_BTTS_MAX_ASK, S.TURKEY_MAX_HOLD),
       (0.135, 0.70, 0.65, 0.06),
       "Turkey ceilings and hold are unchanged")
    eq((S.MLS_AWAY_BAND, S.MLS_AWAY_MAX_ASK, S.MLS_FADE_HOME_BAND, S.MLS_FADE_HOME_MAX_ASK,
        S.MLS_MAX_HOLD, S.MLS_GAME),
       ((0.20, 0.25), 0.26, (0.40, 0.45), 0.66, 0.06, "KXMLSGAME"),
       "MLS bands, ceilings, hold and series are unchanged")
    eq(sorted(T.PAIR_OVERRIDES),
       ["mma_fav_band|mma", "o15_ranked|soccer_o15_intl", "oddspedia|cricket",
        "team1_form_l5|soccer_team1", "team1_form_l5|soccer_team1_intl",
        "u35_low_scoring|soccer_u35_intl"],
       "PAIR_OVERRIDES is unchanged")

    print("\n0 of 0 — nothing offered")
    d = run("ere_draw", {"soccer": []})
    eq(cell(d, "soccer", "ere_draw"), {"picked": 0, "offered": 0},
       "a lane offered 0 rows records 0 of 0")

    print("\n0 of 19 — offered, none qualified")
    offered = [board(market_id=f"KXEREDIVISIEGAME-OUT{i:02d}", price_a=0.15, price_draw=0.19,
                     price_b=0.67) for i in range(19)]
    # In band on the wrong league, and in band on the wrong venue. Neither is examined.
    decoys = [board(market_id=f"KXEPLGAME-EPL{i:02d}", price_a=0.42, price_draw=0.24,
                    price_b=0.36) for i in range(5)]
    decoys.append(board(market_id="KXEREDIVISIEGAME-PM", price_a=0.58, price_draw=0.22,
                        price_b=0.21, venue="polymarket_us"))
    uni = {"soccer": offered + decoys}
    d = run("ere_draw", uni)
    eq(cell(d, "soccer", "ere_draw"), {"picked": 0, "offered": 19},
       "a lane offered 19 rows that picks nothing records 0 of 19")
    eq(S.fetch_ere_draw("soccer", universe=uni), [],
       "those 19 are the right series and still outside the band, so the pick list is empty")
    eq([q for q in d["quotes"] if q["source"] == "ere_draw"], [],
       "an empty pick list logs no ere_draw quote")

    print("\nk of n — some of the offered rows qualify")
    chosen = [board(market_id=f"KXEREDIVISIEGAME-IN{i:02d}", price_a=0.58, price_draw=0.22,
                    price_b=0.21) for i in range(4)]
    # Same prices, right series, but the book is not a price yet. Counted before the band.
    idle = [board(market_id="KXEREDIVISIEGAME-UNTR", price_a=0.58, price_draw=0.22,
                  price_b=0.21, untraded=True)]
    outside = [board(market_id=f"KXEREDIVISIEGAME-OUT{i:02d}", price_a=0.15, price_draw=0.19,
                     price_b=0.67) for i in range(14)]
    others = [board(market_id=f"KXEPLGAME-EPL{i:02d}", price_a=0.42, price_draw=0.24,
                    price_b=0.36) for i in range(5)]
    rows = chosen + idle + outside + others
    ok(sum(1 for r in rows if str(r["market_id"]).startswith("KXEREDIVISIEGAME")) == 19,
       "the fixture offers 19 Eredivisie rows")
    uni = {"soccer": rows}
    picks = [p["market_id"] for p in S.fetch_ere_draw("soccer", universe=uni)]
    d = run("ere_draw", uni)
    eq(cell(d, "soccer", "ere_draw"), {"picked": 4, "offered": 19},
       "a lane offered 19 rows that picks 4 records 4 of 19")
    eq(sorted(picks), [f"KXEREDIVISIEGAME-IN{i:02d}" for i in range(4)],
       "the four in-band ties are the picks, and the untraded tie is not")
    logged = sorted(q["market_id"] for q in d["quotes"] if q["source"] == "ere_draw")
    eq(logged, sorted(picks),
       "the quotes logged are the same market ids the lane returned")
    ok(not any(m.startswith("KXEPLGAME") for m in logged),
       "a wrong-series row is not a pick")

    print("\neach of the ten lanes — right series only, before the band")
    # Three rows of the lane's series that do not qualify, plus two of another
    # series. offered must be 3, not 5 and not 0.
    cases = [
        ("ere_draw", "soccer", {"soccer": [
            board(market_id=f"KXEREDIVISIEGAME-X{i}", price_a=0.15, price_draw=0.19, price_b=0.67)
            for i in range(3)] + [
            board(market_id=f"KXEPLGAME-Y{i}", price_a=0.58, price_draw=0.22, price_b=0.21)
            for i in range(2)]}, None),
        ("ere_o15", "soccer_o15", {
            "soccer_o15": [
                board(market_id=f"KXEREDIVISIETOTAL-DOG{i}-2", venue="kalshi_binary",
                      price_a=0.70, price_b=0.32) for i in range(3)] + [
                board(market_id=f"KXEPLTOTAL-Z{i}-2", venue="kalshi_binary",
                      price_a=0.70, price_b=0.32) for i in range(2)],
            # Dogs are out of band, so the band is what rejects the three totals.
            "soccer": [
                board(market_id=f"KXEREDIVISIEGAME-DOG{i}", price_a=0.90, price_draw=0.08,
                      price_b=0.04) for i in range(3)]}, "soccer_o15"),
        ("bund_o35", "soccer_u35", {"soccer_u35": [
            board(market_id=f"KXBUNDESLIGATOTAL-W{i}-4", venue="kalshi_binary",
                  price_a=0.70, price_b=0.50) for i in range(3)] + [
            board(market_id=f"KXEPLTOTAL-W{i}-4", venue="kalshi_binary",
                  price_a=0.40, price_b=0.62) for i in range(2)]}, None),
        ("bund_o35_fav", "soccer_u35", {"soccer_u35": [
            board(market_id=f"KXBUNDESLIGATOTAL-F{i}-4", venue="kalshi_binary",
                  price_a=0.40, price_b=0.62) for i in range(3)] + [
            board(market_id=f"KXEPLTOTAL-F{i}-4", venue="kalshi_binary",
                  price_a=0.40, price_b=0.62) for i in range(2)]}, None),
        ("liga_btts_even", "soccer_btts", {"soccer_btts": [
            board(market_id=f"KXLALIGABTTS-B{i}", venue="kalshi_binary",
                  price_a=0.50, price_b=0.53) for i in range(3)] + [
            board(market_id=f"KXEPLBTTS-B{i}", venue="kalshi_binary",
                  price_a=0.50, price_b=0.53) for i in range(2)]}, None),
        ("liga_u15_dog", "soccer_o15", {"soccer_o15": [
            board(market_id=f"KXLALIGATOTAL-U{i}-2", venue="kalshi_binary",
                  price_a=0.85, price_b=0.18) for i in range(3)] + [
            board(market_id=f"KXEPLTOTAL-U{i}-2", venue="kalshi_binary",
                  price_a=0.85, price_b=0.18) for i in range(2)]}, None),
        ("turkey_o25_dog", "soccer_o25", {"soccer_o25": [
            board(market_id=f"KXSUPERLIGTOTAL-T{i}-3", venue="kalshi_binary",
                  price_a=0.55, price_b=0.48) for i in range(3)] + [
            board(market_id=f"KXEPLTOTAL-T{i}-3", venue="kalshi_binary",
                  price_a=0.55, price_b=0.48) for i in range(2)]}, None),
        ("turkey_btts_dog", "soccer_btts", {"soccer_btts": [
            board(market_id=f"KXSUPERLIGBTTS-T{i}", venue="kalshi_binary",
                  price_a=0.50, price_b=0.53) for i in range(3)] + [
            board(market_id=f"KXEPLBTTS-T{i}", venue="kalshi_binary",
                  price_a=0.50, price_b=0.53) for i in range(2)]}, None),
        ("mls_away_band", "soccer", {"soccer": [
            board(market_id=f"KXMLSGAME-M{i}", price_a=0.40, price_draw=0.30, price_b=0.32)
            for i in range(3)] + [
            board(market_id=f"KXEPLGAME-M{i}", price_a=0.50, price_draw=0.28, price_b=0.22)
            for i in range(2)]}, None),
        ("mls_fade_home", "soccer_p05", {"soccer_p05": [
            board(market_id=f"KXMLSGAME-P{i}", venue="kalshi_binary",
                  price_a=0.42, price_b=0.60) for i in range(3)] + [
            board(market_id=f"KXEPLGAME-P{i}", venue="kalshi_binary",
                  price_a=0.42, price_b=0.60) for i in range(2)]}, None),
    ]
    seen = []
    for name, sport, universe, pick_sport in cases:
        seen.append(name)
        d = run(name, universe)
        eq(cell(d, sport, name), {"picked": 0, "offered": 3},
           f"{name} records 0 of 3: the three series rows, not the two from another league")
        picks = S.CHALLENGERS[name](pick_sport or sport, universe=universe)
        eq(picks, [], f"{name} qualifies none of those rows")
    eq(seen, list(LANES), "the ten league lanes are the ones this counts")

    print("\nother coverage writers keep a denominator, and venue counts stay ints")
    mixed = [
        board(market_id="KXEREDIVISIEGAME-ONE", price_a=0.58, price_draw=0.22, price_b=0.21),
        board(market_id="KXEPLGAME-A", price_a=0.58, price_draw=0.22, price_b=0.21),
        board(market_id="KXEPLGAME-B", price_a=0.58, price_draw=0.22, price_b=0.21),
    ]
    saved_ch, saved_u = S.CHALLENGERS, S.UNIVERSE
    S.CHALLENGERS = {"ere_draw": lambda sp: [dict(market_id=mixed[0]["market_id"], pick="draw")]}
    try:
        stubbed = {"quotes": [], "meta": {}, "coverage": {}}
        T.publish(stubbed, {"soccer": mixed},
                  {"soccer": {"kalshi_venue": 6, "polymarket_us_listed": 40}}, verbose=False)
    finally:
        S.CHALLENGERS, S.UNIVERSE = saved_ch, saved_u
    eq(cell(stubbed, "soccer", "ere_draw"), {"picked": 1, "offered": 3},
       "a lane that does not report its own count is offered the pool it was matched against")
    eq(stubbed["coverage"]["soccer"]["kalshi_venue"], 6,
       "a venue count written by collect stays an int")
    eq(stubbed["coverage"]["soccer"]["polymarket_us_listed"], 40,
       "the listed-book count stays an int")
    real = run("ere_draw", {"soccer": mixed})
    eq(cell(real, "soccer", "ere_draw"), {"picked": 1, "offered": 1},
       "the same board, counted by the lane, is 1 of 1 — the EPL rows were not examined")

    cricket = board(market_id="c1", sport="cricket", venue="polymarket_us",
                    price_a=0.40, price_b=0.62, side_a="Alpha", side_b="Beta")
    saved_ch = S.CHALLENGERS
    saved_pause, saved_plan = S.source_fully_paused, S.plan_pinnacle
    S.CHALLENGERS = {}
    S.source_fully_paused = lambda n, _r=saved_pause: False if n == "pinnacle" else _r(n)
    S.plan_pinnacle = lambda universe, covered, retired=None: {
        "cricket": [dict(market_id="c1", prob_a=0.55)]}
    try:
        both = {"quotes": [], "meta": {}, "coverage": {}}
        T.publish(both, {"cricket": [cricket]}, {}, verbose=False)
    finally:
        S.CHALLENGERS = saved_ch
        S.source_fully_paused = saved_pause
        S.plan_pinnacle = saved_plan
        S.UNIVERSE = None
    eq(cell(both, "cricket", "cricket_consensus"), {"picked": 0, "offered": 1},
       "consensus records picks of the rows it was offered")
    eq(cell(both, "cricket", "pinnacle"), {"picked": 1, "offered": 1},
       "pinnacle records picks of the rows it was offered")
    ok(not any(q["source"] == "pinnacle" for q in both["quotes"]),
       "a paused pinnacle lane still logs nothing")

    print("\nreaders")
    dark = BUILD.feed_health({"coverage": {"boxing": {"olbg": 0}, "mma": {"olbg": 0}}, "quotes": []})
    ok("Feed check" in dark and "OLBG" in dark,
       "a stored int 0 across every sport is still a dark feed")
    empty_offer = BUILD.feed_health({"coverage": {
        "boxing": {"olbg": {"picked": 0, "offered": 0}},
        "mma": {"olbg": {"picked": 0, "offered": 0}},
    }, "quotes": []})
    eq(empty_offer, "", "0 of 0 is nothing offered, not a dark feed")
    missed = BUILD.feed_health({"coverage": {
        "boxing": {"olbg": {"picked": 0, "offered": 4}},
        "mma": {"olbg": {"picked": 0, "offered": 2}},
    }, "quotes": []})
    ok("Feed check" in missed and "OLBG" in missed,
       "0 of n, with n above zero, is still a dark feed for a tipster")
    try:
        html = BUILD.coverage_table({
            "soccer": {"ere_draw": {"picked": 4, "offered": 19},
                       "nws": {"picked": 7, "offered": 8}},
            "boxing": {"olbg": 12},
            "mma": {"olbg": 0},
        })
    except (TypeError, ValueError) as e:
        ok(False, f"the coverage table renders a denominator cell — {type(e).__name__}: {e}")
    else:
        ok("4 of 19" in html, "the page shows 4 of 19")
        ok("7 of 8" not in html, "a removed lane's cell is not rendered")
        ok("National Weather Service" not in html, "a removed lane's name is not rendered")
        ok(">12</td>" in html, "a stored int still renders as the count")
        ok(">0</td>" in html, "a stored int 0 still renders as 0")
        ok("0 of 0" not in html, "a stored int 0 is not rewritten as 0 of 0")
    hidden = BUILD.hide_removed({"quotes": [], "coverage": {
        "soccer": {"ere_draw": {"picked": 4, "offered": 19},
                   "covers": {"picked": 1, "offered": 2}},
        "climate": {"nws": 3},
    }})
    eq(hidden["coverage"]["soccer"].get("ere_draw"), {"picked": 4, "offered": 19},
       "a kept lane's denominator survives the page copy")
    ok("covers" not in hidden["coverage"]["soccer"], "a removed source is dropped from the page copy")
    ok("climate" not in hidden["coverage"], "a removed sport is dropped from the page copy")

    print("\n" + ("FAILED: %d" % len(FAILS) if FAILS else "all coverage denominator tests passed"))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
