#!/usr/bin/env python3
"""The crypto favourite-band rule, pre-registered 2026-10-05.

Every number here was fixed before the lane logged anything, so this file is the
registration as much as the test: a later edit to the band, the window, the rung choice or
the clustering has to change an assertion, which is the point.
"""
import datetime
import sys
from datetime import timezone

import sandbox_sources as S

FAILS = []


def ok(cond, why):
    print(f"  {'ok  ' if cond else 'FAIL'} {why}")
    if not cond:
        FAILS.append(why)


def eq(got, want, why):
    ok(got == want, why if got == want else f"{why} — got {got!r}, want {want!r}")


CLOSE = datetime.datetime(2026, 10, 5, 21, 5, tzinfo=timezone.utc)   # Kalshi closes at :05
NOW = CLOSE - datetime.timedelta(hours=2, minutes=30)                # inside the window


def rung(series, strike, price, bid=None, size=200, start=None, sport="crypto_fav"):
    """One universe row, shaped as fetch_kalshi_binary builds them."""
    bid = price - 0.01 if bid is None else bid
    return dict(sport=sport, venue="kalshi_binary",
                market_id=f"{series}-26OCT0517-T{strike}", series=series,
                side_a=f"${strike} or above", side_b="No",
                price_a=price, price_b=round(1 - price, 2), price_draw=None,
                tradeable={"a": True, "b": True}, untraded=False,
                start=(start or CLOSE).isoformat(), date="2026-10-05",
                market={"yes_bid_dollars": bid, "yes_ask_dollars": price,
                        "yes_ask_size_fp": size})


def picks(rows, now=NOW):
    return S.fetch_crypto_fav_band("crypto_fav", universe={"crypto_fav": rows}, now=now)


def ids(rows, now=NOW):
    return sorted(p["market_id"] for p in picks(rows, now))


print("registered parameters")
eq(S.CRYPTO_FAV_BAND, (0.70, 0.80), "the band is 0.70-0.80")
eq((S.CRYPTO_FAV_MIN_H, S.CRYPTO_FAV_MAX_H), (2.0, 3.5), "the window is 2-3.5h to the close")
eq(S.CRYPTO_FAV_CLOSE_UTC, 21, "and it is the 21:00Z (17:00 ET) close")
eq(S.CRYPTO_FAV_MAX_SPREAD, 0.03, "the spread floor is 3c")
eq(S.CRYPTO_FAV_MIN_ASK_SIZE, 25, "the ask-size floor is 25")
eq(S.SOURCES["crypto_fav_band"]["sports"], ["crypto_fav"],
   "the lane has its own sport, so its record never pools with the spot baseline")
eq(S.SOURCES["crypto_fav_band"]["baseline"], "favourite_population",
   "and is judged against backing every in-band rung")
ok(S.CHALLENGERS.get("crypto_fav_band") is S.fetch_crypto_fav_band, "the fetcher is wired")

print("\nthe band, both ends inclusive")
eq(ids([rung("KXBTCD", "1", 0.70)]), ["KXBTCD-26OCT0517-T1"], "0.70 is in")
eq(ids([rung("KXBTCD", "1", 0.80)]), ["KXBTCD-26OCT0517-T1"], "0.80 is in too")
eq(ids([rung("KXBTCD", "1", 0.69)]), [], "0.69 is out")
eq(ids([rung("KXBTCD", "1", 0.81)]), [], "0.81 is out")

print("\nthe lowest rung in band, one per coin")
# A real ladder: three BTC rungs in band, all nested, plus one out of band.
ladder = [rung("KXBTCD", "84499", 0.80), rung("KXBTCD", "84749", 0.73),
          rung("KXBTCD", "85999", 0.71), rung("KXBTCD", "80000", 0.95)]
eq(ids(ladder), ["KXBTCD-26OCT0517-T85999"],
   "of three in-band BTC rungs only the LOWEST-priced is taken")
eq(len(picks(ladder)), 1, "so one nested ladder can never produce two bets")
two = ladder + [rung("KXSOLD", "118", 0.72), rung("KXSOLD", "120", 0.78)]
eq(ids(two), ["KXBTCD-26OCT0517-T85999", "KXSOLD-26OCT0517-T118"],
   "a second coin is a second bet, its own lowest rung")
eq([p["pick"] for p in picks(two)], ["a", "a"], "always the Yes side")

print("\nthe window")
eq(ids(ladder, now=CLOSE - datetime.timedelta(hours=1, minutes=59)), [],
   "1h59m before the close is too late")
eq(ids(ladder, now=CLOSE - datetime.timedelta(hours=3, minutes=31)), [],
   "3h31m is too early")
eq(ids(ladder, now=CLOSE - datetime.timedelta(hours=2)), ["KXBTCD-26OCT0517-T85999"],
   "exactly 2h is in")
eq(ids(ladder, now=CLOSE - datetime.timedelta(hours=3, minutes=30)), ["KXBTCD-26OCT0517-T85999"],
   "and exactly 3h30m is in")
eq(ids(ladder, now=CLOSE + datetime.timedelta(minutes=1)), [], "after the close, nothing")

print("\nonly the 17:00 ET close -- an hourly rung is a different contract")
hourly = CLOSE.replace(hour=19)
eq(ids([rung("KXBTCD", "1", 0.75, start=hourly)],
       now=hourly - datetime.timedelta(hours=2, minutes=30)), [],
   "a 19:00Z expiry is refused even inside its own window")

print("\nthe liquidity floor")
eq(ids([rung("KXBTCD", "1", 0.75, bid=0.72)]), ["KXBTCD-26OCT0517-T1"],
   "an exactly 3c spread is kept (the float boundary: 0.75-0.72 is not 0.03)")
eq(ids([rung("KXBTCD", "1", 0.75, bid=0.71)]), [], "a 4c spread is refused")
eq(ids([rung("KXBTCD", "1", 0.75, bid=0.715)]), [], "a 3.5c spread is refused")
eq(ids([rung("KXBTCD", "1", 0.75, size=24)]), [], "24 on the ask is refused")
eq(ids([rung("KXBTCD", "1", 0.75, size=25)]), ["KXBTCD-26OCT0517-T1"], "25 is kept")
_untr = rung("KXBTCD", "1", 0.75)
_untr["tradeable"] = {"a": False, "b": True}
eq(ids([_untr]), [], "an untradeable Yes is refused")
# The floor must not silently promote a worse rung: if the lowest is illiquid the lane
# takes the next lowest that passes, not nothing and not the illiquid one.
_mixed = [rung("KXBTCD", "85999", 0.71, bid=0.60), rung("KXBTCD", "84749", 0.73)]
eq(ids(_mixed), ["KXBTCD-26OCT0517-T84749"],
   "an illiquid lowest rung falls through to the next lowest that passes the floor")

print("\nthe sport gate")
eq(S.fetch_crypto_fav_band("crypto", universe={"crypto": ladder}, now=NOW), [],
   "the lane does not read the spot baseline's domain")
eq(S.fetch_crypto_fav_band("tennis", universe={"tennis": ladder}, now=NOW), [],
   "nor any other sport")

print("\nevery coin on one day is ONE outcome (measured, not assumed)")
ok("crypto_fav" in S.DAY_CLUSTERED, "crypto_fav is day-clustered")
key = lambda mid: S.market_day(dict(sport="crypto_fav", market_id=mid, date="2026-10-05"))
eq(key("KXBTCD-26OCT0517-T84749.99"), key("KXSOLD-26OCT0517-T118.9999"),
   "BTC and SOL on the same day share a cluster -- the coins move together (+0.757)")
ok(key("KXBTCD-26OCT0517-T1") != S.market_day(
       dict(sport="crypto_fav", market_id="KXBTCD-26OCT0917-T1", date="2026-10-09")),
   "a different day is a different outcome")
eq(key("KXBTCD-26OCT0517-T1"), "CRYPTOFAV|20261005", "the key is the date, not the series")
# The spot baseline keeps its own per-series key: its record is already on that basis.
ok(S.market_day(dict(sport="crypto", market_id="KXSOLD-26OCT0517-T1", date="2026-10-05"))
   != S.market_day(dict(sport="crypto", market_id="KXBTCD-26OCT0517-T1", date="2026-10-05")),
   "the spot baseline is unchanged, still keyed per series")

print("\nthe coin map was corrected 2026-10-05")
eq(sorted(S.COINS), ["KXBTCD", "KXETHD", "KXHYPED", "KXSOLD", "KXXRPD"],
   "five live directional series")
for dead in ("BTCD", "ETHD", "KXXRP", "KXXLM", "KXNEAR", "KXLINKD"):
    ok(dead not in S.COINS, f"{dead} is not a live series")
    ok(dead in S.COIN_OF_SERIES, f"...but {dead} still resolves its coin for stored rows")
eq(S.KALSHI_BINARY["crypto_fav"]["ladders_per_series"], 4,
   "the domain keeps 4 ladders per series, so the 21:00Z one is never hidden by nearer "
   "hourly closes")
ok(S.KALSHI_BINARY["crypto_fav"]["cap"] >= 275,
   "and its cap clears one whole ladder per live coin (275 rungs on 2026-10-05)")

print()
if FAILS:
    print(f"FAILED: {len(FAILS)}")
    sys.exit(1)
print("all passed")
