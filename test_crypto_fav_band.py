#!/usr/bin/env python3
"""The crypto favourite-band rule, pre-registered 2026-10-05.

Every number here was fixed before the lane logged anything, so this file is the
registration as much as the test: a later edit to the band, the window, the rung choice or
the clustering has to change an assertion, which is the point.
"""
import datetime
import json
import os
import sys
import tempfile
from datetime import timezone
from zoneinfo import ZoneInfo

import sandbox_sources as S
import sandbox_track as T

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
eq(S.CRYPTO_FAV_CLOSE_ET, 17, "and it is the 17:00 Eastern close")
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

print("\nthe close is matched in EASTERN, so the DST change moves it with the exchange")
eq(S.CRYPTO_FAV_CLOSE_ET, 17, "the close is 17:00 Eastern")
ok(not hasattr(S, "CRYPTO_FAV_CLOSE_UTC"),
   "and is NOT pinned to a UTC hour -- 17:00 ET is 21:00Z under CDT and 22:00Z under CST, "
   "so an hour-21 test would have silently refused every bet from 2026-11-01")
_CT = ZoneInfo("America/Chicago")
for _d, _utc in ((datetime.date(2026, 10, 15), 21), (datetime.date(2026, 11, 15), 22),
                 (datetime.date(2027, 3, 20), 21)):
    _exp = datetime.datetime.combine(_d, datetime.time(17, 5), S.CRYPTO_FAV_TZ)
    eq(_exp.astimezone(timezone.utc).hour, _utc,
       f"{_d}: the 17:05 ET expiry is {_utc:02d}:05Z")
    # 13:15 local Central is the launchd slot. Central and Eastern shift on the same date,
    # so it is permanently 2.83h before the close -- that is why the timer is local time.
    _run = datetime.datetime.combine(_d, datetime.time(13, 15), _CT)
    _r = rung("KXBTCD", "1", 0.75, start=_exp)
    eq([p["market_id"] for p in picks([_r], now=_run)], ["KXBTCD-26OCT0517-T1"],
       f"...and the 13:15 CT timer still lands in the window on {_d}")

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

print("\none bet per coin per close, across two tracker runs")
# The fetcher keeps one rung per coin inside a single run. publish() was keying
# the ledger on the whole ticker, and the ticker includes the strike, so a
# second run whose lowest in-band rung had moved logged a second bet. Each
# case below calls publish() twice on a temp ledger. data/ is never opened.
BAND_CLOSE = datetime.datetime(2026, 10, 6, 21, 0, tzinfo=timezone.utc)  # 17:00 ET
RUN_1 = datetime.datetime(2026, 10, 6, 17, 50, tzinfo=timezone.utc)       # 3.17h out
RUN_2 = datetime.datetime(2026, 10, 6, 18, 15, tzinfo=timezone.utc)       # 2.75h out
NEXT_CLOSE = datetime.datetime(2026, 10, 7, 21, 0, tzinfo=timezone.utc)
NEXT_RUN = datetime.datetime(2026, 10, 7, 17, 50, tzinfo=timezone.utc)


def temp_ledger():
    """A ledger publish() can append to, loaded from a temp file.

    The live ledger under data/ is not read and not written. A later real row
    cannot change what these cases count.
    """
    raw = {"meta": {}, "quotes": [], "coverage": {}}
    fd, path = tempfile.mkstemp(prefix="crypto-fav-ledger-", suffix=".json")
    os.close(fd)
    try:
        with open(path, "w") as f:
            json.dump(raw, f)
        with open(path) as f:
            return json.load(f)
    finally:
        os.remove(path)


def close_rung(series, strike, price, token="26OCT0617", when=None, day="2026-10-06"):
    """One 17:00 ET ladder rung, ticker dated by `token` (26OCT0617)."""
    bid = round(price - 0.01, 2)
    when = when or BAND_CLOSE
    tk = f"{series}-{token}-T{strike}"
    return dict(sport="crypto_fav", venue="kalshi_binary", market_id=tk, series=series,
                label=f"{series} {strike} or above",
                side_a=f"${strike} or above", side_b="No",
                price_a=price, price_b=round(1 - bid, 2), price_draw=None,
                tradeable={"a": True, "b": True}, untraded=False,
                start=when.isoformat(), date=day, volume=0.0,
                market={"ticker": tk, "yes_bid_dollars": bid, "yes_ask_dollars": price,
                        "yes_ask_size_fp": 500},
                url="https://kalshi.com/markets/x")


def publish_lane(d, rows, now):
    """publish() with only this lane fetching, pinned to `now`."""
    saved = S.CHALLENGERS
    S.CHALLENGERS = {"crypto_fav_band": lambda sport, now=now: S.fetch_crypto_fav_band(sport, now=now)}
    try:
        return T.publish(d, {"crypto_fav": rows}, {}, verbose=False, now=now)
    finally:
        S.CHALLENGERS = saved


def lane_rows(d):
    return [q for q in d["quotes"] if q.get("source") == "crypto_fav_band"]


def brief(rows):
    return [(q["market_id"], q["price"]) for q in rows]


def show(tag, d):
    rows = lane_rows(d)
    text = ", ".join(f"{mid} @{px}" for mid, px in brief(rows)) or "(none)"
    print(f"  {tag}: {len(rows)} row(s): {text}")


def would_pick(rows, now):
    return [(p["market_id"], next(r["price_a"] for r in rows if r["market_id"] == p["market_id"]))
            for p in S.fetch_crypto_fav_band("crypto_fav", universe={"crypto_fav": rows}, now=now)]


ok(not S.SOURCES["crypto_fav_band"].get("one_per_day"),
   "one_per_day stays off: that flag is one bet for the whole day, not one per coin")

btc = [close_rung("KXBTCD", 84500, 0.82), close_rung("KXBTCD", 84750, 0.73),
       close_rung("KXBTCD", 85000, 0.66)]
same = btc
moved = [close_rung("KXBTCD", 84500, 0.78), close_rung("KXBTCD", 84750, 0.69),
         close_rung("KXBTCD", 85000, 0.62)]
lower = [close_rung("KXBTCD", 84500, 0.82), close_rung("KXBTCD", 84750, 0.74),
         close_rung("KXBTCD", 85000, 0.71)]
first = ("KXBTCD-26OCT0617-T84750", 0.73)

eq(would_pick(btc, RUN_1), [first], "the first clock takes T84750 at 0.73")
eq(would_pick(same, RUN_2), [first], "unchanged prices would take that same rung again")
eq(would_pick(moved, RUN_2), [("KXBTCD-26OCT0617-T84500", 0.78)],
   "once 0.73 has left the band, the second clock would take the 0.78 rung")
eq(would_pick(lower, RUN_2), [("KXBTCD-26OCT0617-T85000", 0.71)],
   "a 0.71 rung entering the band is lower, so the second clock would take it")

print("  (1) same prices on the second run")
d = temp_ledger()
a1 = publish_lane(d, btc, RUN_1)
a2 = publish_lane(d, same, RUN_2)
show("same prices", d)
eq(a1, 1, "the first run logs the rung")
eq(a2, 0, "the second run, at the same prices, logs nothing")
eq(brief(lane_rows(d)), [first], "one row, still T84750 at its first price 0.73")
eq(lane_rows(d)[0]["logged"], "2026-10-06T17:50:00+00:00",
   "and still stamped at the first run")

print("  (2) the first rung left the band")
d = temp_ledger()
publish_lane(d, btc, RUN_1)
a2 = publish_lane(d, moved, RUN_2)
show("rung left band", d)
eq(a2, 0, "the 0.78 rung is not logged")
eq(brief(lane_rows(d)), [first],
   "one crypto_fav_band row for KXBTCD 26OCT0617, still 0.73")

print("  (3) a lower rung entered the band")
d = temp_ledger()
publish_lane(d, btc, RUN_1)
a2 = publish_lane(d, lower, RUN_2)
show("lower rung entered", d)
eq(a2, 0, "the 0.71 rung is not logged")
eq(brief(lane_rows(d)), [first],
   "one crypto_fav_band row for KXBTCD 26OCT0617, still 0.73")

print("  two coins on the same close")
eth = [close_rung("KXETHD", 4400, 0.84), close_rung("KXETHD", 4500, 0.76),
       close_rung("KXETHD", 4600, 0.64)]
eth_moved = [close_rung("KXETHD", 4400, 0.77), close_rung("KXETHD", 4500, 0.68),
             close_rung("KXETHD", 4600, 0.60)]
d = temp_ledger()
publish_lane(d, btc + eth, RUN_1)
publish_lane(d, moved + eth_moved, RUN_2)
show("btc and eth", d)
eq(sorted(brief(lane_rows(d))), sorted([
    ("KXBTCD-26OCT0617-T84750", 0.73),
    ("KXETHD-26OCT0617-T4500", 0.76),
]), "BTC and ETH on 26OCT0617 each keep one row, at the first price")

print("  a later close of the same coin")
nxt = [close_rung("KXBTCD", 84500, 0.82, token="26OCT0717", when=NEXT_CLOSE, day="2026-10-07"),
       close_rung("KXBTCD", 84750, 0.73, token="26OCT0717", when=NEXT_CLOSE, day="2026-10-07"),
       close_rung("KXBTCD", 85000, 0.66, token="26OCT0717", when=NEXT_CLOSE, day="2026-10-07")]
d = temp_ledger()
publish_lane(d, btc, RUN_1)
a2 = publish_lane(d, nxt, NEXT_RUN)
show("next close", d)
eq(a2, 1, "the next day's close is logged")
eq(sorted(brief(lane_rows(d))), sorted([
    ("KXBTCD-26OCT0617-T84750", 0.73),
    ("KXBTCD-26OCT0717-T84750", 0.73),
]), "KXBTCD on 26OCT0617 and 26OCT0717 are two bets")

print("  an archived row for that coin and close")
d = temp_ledger()
d["_archive"] = [dict(
    id="crypto_fav_band:KXBTCD-26OCT0617-T84000", source="crypto_fav_band",
    sport="crypto_fav", market_id="KXBTCD-26OCT0617-T84000", price=0.75,
    bet=True, status="lost", date="2026-10-06", start=BAND_CLOSE.isoformat())]
a1 = publish_lane(d, btc, RUN_1)
show("archive blocks", d)
eq(a1, 0, "a new strike is not logged over the archived row")
eq(lane_rows(d), [], "the ledger gains no second crypto_fav_band row")
eq(d["_archive"][0]["price"], 0.75, "the archived row keeps its price")

print("  a decimal strike is the same close")
d = temp_ledger()
d["_archive"] = [dict(
    id="crypto_fav_band:KXSOLD-26OCT0617-T119.9999", source="crypto_fav_band",
    sport="crypto_fav", market_id="KXSOLD-26OCT0617-T119.9999", price=0.74,
    bet=True, status="lost", date="2026-10-06", start=BAND_CLOSE.isoformat())]
sol = [close_rung("KXSOLD", "118.9999", 0.72)]
a1 = publish_lane(d, sol, RUN_1)
show("decimal strike", d)
eq(a1, 0, "T118.9999 is the same KXSOLD 26OCT0617 close as the archived T119.9999")
eq(lane_rows(d), [], "the decimal strike did not open a second row")

print("  two strikes offered in one pass")
d = temp_ledger()
saved = S.CHALLENGERS
S.CHALLENGERS = {"crypto_fav_band": lambda sport: [
    dict(market_id="KXBTCD-26OCT0617-T84750", pick="a"),
    dict(market_id="KXBTCD-26OCT0617-T84500", pick="a"),
]}
try:
    publish_lane_rows = [close_rung("KXBTCD", 84750, 0.73), close_rung("KXBTCD", 84500, 0.78)]
    T.publish(d, {"crypto_fav": publish_lane_rows}, {}, verbose=False, now=RUN_1)
finally:
    S.CHALLENGERS = saved
show("same pass", d)
eq(brief(lane_rows(d)), [first],
   "a second strike logged later in the same pass is skipped; the first price stands")

print()
if FAILS:
    print(f"FAILED: {len(FAILS)}")
    sys.exit(1)
print("all passed")
