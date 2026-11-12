#!/usr/bin/env python3
"""test_crypto_fav_band_v2.py — the crypto Yes twin reopened as a Sandbox paper lane on a FRESH record (2026-11-12, Olu).

crypto_fav_band_v2 is crypto_fav_band's rule, unchanged: same band (0.70-0.80 inclusive), same window, one per coin per close, the lowest rung, the same
liquidity floor. A separate source, so its record starts at zero; crypto_fav_band (retired 2026-11-03) keeps its record as its own line. Paper only."""
import datetime
import sys
from datetime import timezone

import sandbox_sources as S
import sport_rows_testlib

FAILS = []


def check(why, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {why}" + ("" if ok else f" — got {got!r}, want {want!r}"))
    if not ok:
        FAILS.append(why)


CLOSE = datetime.datetime(2026, 10, 5, 21, 5, tzinfo=timezone.utc)
NOW = CLOSE - datetime.timedelta(hours=2, minutes=30)


def rung(series, strike, price, size=200, start=None):
    return dict(sport="crypto_fav", venue="kalshi_binary", market_id=f"{series}-26OCT0517-T{strike}", series=series, side_a=f"${strike} or above",
                side_b="No", price_a=price, price_b=round(1 - price, 2), price_draw=None, tradeable={"a": True, "b": True}, untraded=False,
                start=(start or CLOSE).isoformat(), date="2026-10-05",
                market={"yes_bid_dollars": price - 0.01, "yes_ask_dollars": price, "yes_ask_size_fp": size})


print("registered: a live Sandbox paper lane, the old source still retired")
m = S.SOURCES["crypto_fav_band_v2"]
check("v2 logs crypto_fav and is not retired", (m["sports"], "retired_sports" in m), (["crypto_fav"], False))
check("the old source stays retired, with its own reason (its record is untouched)", (S.SOURCES["crypto_fav_band"]["sports"], list(S.SOURCES["crypto_fav_band"]["retired_sports"])),
      ([], ["crypto_fav"]))
check("v2 has a fetcher in the run", "crypto_fav_band_v2" in S.FETCHERS if hasattr(S, "FETCHERS") else callable(S.fetch_crypto_fav_band_v2), True)
check("same shape as the old lane: favourite side a, one per coin per close", (m["favourite_side"], m["one_per_coin_close"], m["baseline"]),
      ("a", True, "favourite_population"))
check("the note cites the review's replay and says a replay is a reason to test, not a result",
      all(x in m["note"] for x in ("+11.1% after fees on 134 bets", "reason to test, not a result", "starts at zero", "docs/prereg_crypto_fav_band_v2_2026-11-12.md")), True)

print("\nthe same rule, unchanged: v2 picks exactly what the old rule picks")
with sport_rows_testlib.running_again("crypto_fav_band|crypto_fav"):
    ladder = [rung("KXBTCD", 84750, 0.78), rung("KXBTCD", 84500, 0.80), rung("KXBTCD", 84250, 0.81), rung("KXBTCD", 85000, 0.69),
              rung("KXETHD", 3000, 0.73), rung("KXETHD", 3050, 0.72, size=5), rung("KXSOLD", 150, 0.70), rung("KXXRPD", 2.5, 0.82)]
    old = S.fetch_crypto_fav_band("crypto_fav", universe={"crypto_fav": ladder}, now=NOW)
new = S.fetch_crypto_fav_band_v2("crypto_fav", universe={"crypto_fav": ladder}, now=NOW)
strip = lambda ps: [(p["market_id"], p["pick"]) for p in ps]
check("the same picks on the same ladders", strip(new), strip(old))
check("one per coin, the lowest rung in band (both ends inclusive; 0.81 and 0.69 out; a thin book skipped)",
      sorted(strip(new)), [("KXBTCD-26OCT0517-T84750", "a"), ("KXETHD-26OCT0517-T3000", "a"), ("KXSOLD-26OCT0517-T150", "a")])
check("outside the 2-3.5h window nothing is picked", S.fetch_crypto_fav_band_v2("crypto_fav", universe={"crypto_fav": ladder}, now=NOW - datetime.timedelta(hours=2)), [])
check("another sport: nothing", S.fetch_crypto_fav_band_v2("tennis", universe={"tennis": ladder}, now=NOW), [])

print("\nthe page, the windows and the paper-only rule")
import crypto_build as CB
import lane_windows as W
check("v2 is one of the crypto lanes the page reads, and the VPS window waits for it too", ("crypto_fav_band_v2" in CB.LANES, "crypto_fav_band_v2" in W.WINDOW_LANES["crypto_fav_band"]), (True, True))
check("it is a live lane in the Crypto section", "crypto_fav_band_v2" in CB.live_lanes(), True)
html = CB.build()
check("its row is in the page's Rules (Sandbox), the old lane's in Retired", ('data-source="crypto_fav_band_v2"' in html, 'data-source="crypto_fav_band"' in html.split('id="retired"')[1]), (True, True))
import sandbox_track as T
check("never in Production: no override, no feed", "crypto_fav_band_v2|crypto_fav" not in T.PAIR_OVERRIDES, True)
doc = open("docs/prereg_crypto_fav_band_v2_2026-11-12.md").read()
check("the pre-registration says: same rule, fresh record, review 30 decide 100, and that the replay is not a result",
      all(x in doc for x in ("unchanged", "fresh record", "Review at 30", "decide at 100", "+11.1%", "reason to test, not a result")), True)

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
