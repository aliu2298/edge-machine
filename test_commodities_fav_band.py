#!/usr/bin/env python3
"""The commodities favourite-band rule, pre-registered 2026-10-08.

Every number here was fixed before the lane logged anything, so this file is the
registration as much as the test: a later edit to the band, the windows, the rung
choice, the calendar or the clustering has to change an assertion, which is the point.
The crypto lane's own constants are untouched by this lane and are asserted unchanged.
"""
import datetime
import json
import os
import sys
import tempfile
from datetime import timezone
from zoneinfo import ZoneInfo

import market_track
import sandbox_sources as S
import sandbox_track as T

FAILS = []


def ok(cond, why):
    print(f"  {'ok  ' if cond else 'FAIL'} {why}")
    if not cond:
        FAILS.append(why)


def eq(got, want, why):
    ok(got == want, why if got == want else f"{why} — got {got!r}, want {want!r}")


ET = ZoneInfo("America/New_York")
# Thursday 2026-10-08. WTI closes 14:30 ET (18:30Z), the rest 17:00 ET (21:00Z).
WTI_CLOSE = datetime.datetime(2026, 10, 8, 14, 30, tzinfo=ET).astimezone(timezone.utc)
FIVE_CLOSE = datetime.datetime(2026, 10, 8, 17, 0, tzinfo=ET).astimezone(timezone.utc)
WTI_NOW = WTI_CLOSE - datetime.timedelta(hours=2, minutes=30)
FIVE_NOW = FIVE_CLOSE - datetime.timedelta(hours=2, minutes=30)


def rung(series, strike, price, bid=None, size=200, start=None, sport="commodities_fav",
         token="26OCT0817"):
    """One universe row, shaped as fetch_kalshi_binary builds them."""
    bid = round(price - 0.01, 2) if bid is None else bid
    close = start or (WTI_CLOSE if series == "KXWTI" else FIVE_CLOSE)
    return dict(sport=sport, venue="kalshi_binary",
                market_id=f"{series}-{token}-T{strike}", series=series,
                label=f"{series} above {strike}",
                side_a=f"${strike} or above", side_b="No",
                price_a=price, price_b=round(1 - price, 2), price_draw=None,
                tradeable={"a": True, "b": True}, untraded=False,
                start=close.isoformat(), date=close.strftime("%Y-%m-%d"), volume=0.0,
                market={"ticker": f"{series}-{token}-T{strike}", "yes_bid_dollars": bid,
                        "yes_ask_dollars": price, "yes_ask_size_fp": size},
                url="https://kalshi.com/markets/x")


def picks(rows, now):
    return S.fetch_commod_fav_band("commodities_fav", universe={"commodities_fav": rows}, now=now)


def ids(rows, now):
    return sorted(p["market_id"] for p in picks(rows, now))


print("registered parameters, copied from the crypto lane and held separately")
eq(S.COMMOD_FAV_BAND, S.CRYPTO_FAV_BAND, "the band is the crypto band, 0.70-0.80")
eq(S.COMMOD_FAV_BAND, (0.70, 0.80), "and that is 0.70-0.80")
eq((S.COMMOD_FAV_MIN_H, S.COMMOD_FAV_MAX_H), (S.CRYPTO_FAV_MIN_H, S.CRYPTO_FAV_MAX_H),
   "the window is the crypto window, 2-3.5h to the close")
eq(S.COMMOD_FAV_MAX_SPREAD, 0.03, "the spread floor is 3c")
eq(S.COMMOD_FAV_MIN_ASK_SIZE, 25, "the ask-size floor is 25")
eq(S.COMMOD_FAV_READ_DAYS, T.READ_FLOOR, "the planned read is the Sandbox's 30")
eq(sorted(S.COMMOD_FAV_SERIES), ["KXBRENTD", "KXCOPPERD", "KXGOLDD", "KXNATGASD", "KXSILVERD", "KXWTI"],
   "six series: WTI, Brent, gold, silver, copper, natural gas")
eq(S.commod_fav_close_et("KXWTI"), (14, 30), "WTI closes at 14:30 Eastern")
for s in ("KXBRENTD", "KXGOLDD", "KXSILVERD", "KXCOPPERD", "KXNATGASD"):
    eq(S.commod_fav_close_et(s), (17, 0), f"{s} closes at 17:00 Eastern")
eq(S.KALSHI_BINARY["commodities_fav"]["series"], list(S.COMMOD_FAV_SERIES),
   "the universe is built from the same six series")
eq(S.KALSHI_BINARY["commodities_fav"]["lead_h"], 2, "the domain accepts rungs 2h out")
ok(S.KALSHI_BINARY["commodities_fav"]["ladders_per_series"] >= 2, "today's and tomorrow's ladder both enter")
eq(S.SOURCES["commod_fav_band"]["sports"], ["commodities_fav"],
   "the lane has its own sport, so its record never pools with the commodity price baseline")
eq(S.SOURCES["commod_fav_band"]["baseline"], "favourite_population",
   "and is judged against backing every in-band rung")
ok(S.SOURCES["commod_fav_band"].get("one_per_coin_close") is True, "one bet per series per close")
ok(S.SOURCES["commod_fav_band"].get("store_book") is True, "its rows store the book they were taken at")
ok(not S.SOURCES["commod_fav_band"].get("one_per_day"), "one_per_day stays off: that is one bet for the whole day")
ok(S.CHALLENGERS.get("commod_fav_band") is S.fetch_commod_fav_band, "the fetcher is wired")
eq(S.SPORTS["commodities_fav"], "Commodities · Favourite band", "the domain is labelled")
note = S.SOURCES["commod_fav_band"]["note"]
for phrase in ("PRE-REGISTERED 2026-10-08", "14:30 Eastern", "17:00 Eastern", "trading day",
               "seven weeks", "gold and silver", "WTI and Brent", "commodities_ladders.md",
               "ICE", "Pyth", "Monday to Thursday"):
    ok(phrase.lower() in note.lower(), f"the registration says {phrase!r}")
ok(S.COMMOD_FAV_CORRELATION[("KXGOLDD", "KXSILVERD")] > 0.8
   and S.COMMOD_FAV_CORRELATION[("KXWTI", "KXBRENTD")] > 0.8,
   "the measured pair correlations are recorded")

print("\nthe crypto lane is untouched")
eq(S.CRYPTO_FAV_BAND, (0.70, 0.80), "crypto band")
eq((S.CRYPTO_FAV_MIN_H, S.CRYPTO_FAV_MAX_H, S.CRYPTO_FAV_CLOSE_ET), (2.0, 3.5, 17), "crypto window and close")
eq(S.SOURCES["crypto_fav_band"]["sports"], ["crypto_fav"], "crypto sport")
ok(not S.SOURCES["crypto_fav_band"].get("store_book"), "crypto rows do not change shape")
eq(S.KALSHI_BINARY["crypto_fav"]["series"], list(S.COINS), "crypto universe")

print("\nthe calendar")
eq(set(S.COMMOD_FAV_HOLIDAYS), set(market_track.NYSE_HOLIDAYS),
   "the holiday set is the one market_track already keeps")
ok(S.commod_fav_trading_day(datetime.date(2026, 10, 8)), "a Thursday is a trading day")
ok(not S.commod_fav_trading_day(datetime.date(2026, 10, 10)), "a Saturday is not")
ok(not S.commod_fav_trading_day(datetime.date(2026, 10, 11)), "a Sunday is not")
ok(not S.commod_fav_trading_day(datetime.date(2026, 11, 26)), "Thanksgiving is not")
ok("commodities_fav" in S.DAY_CLUSTERED, "commodities_fav is day-clustered")
key = lambda series, mid, day: S.market_day(dict(sport="commodities_fav", market_id=mid, date=day))
eq(key("KXGOLDD", "KXGOLDD-26OCT0817-T4006", "2026-10-08"), "COMMODFAV|20261008",
   "the key is the date, not the series")
eq(key("KXGOLDD", "KXGOLDD-26OCT0817-T4006", "2026-10-08"),
   key("KXWTI", "KXWTI-26OCT0814-T81.49", "2026-10-08"),
   "WTI and gold on one day share a cluster, across the two closes")
ok(key("KXGOLDD", "KXGOLDD-26OCT0817-T4006", "2026-10-08")
   != key("KXGOLDD", "KXGOLDD-26OCT0917-T4006", "2026-10-09"), "a different day is a different outcome")
ok(S.market_day(dict(sport="commodities", market_id="KXGOLDD-26OCT0817-T4006", date="2026-10-08"))
   == "KXGOLDD|20261008", "the commodity price baseline keeps its own per-series key")
ok(S.market_day(dict(sport="crypto_fav", market_id="KXBTCD-26OCT0817-T1", date="2026-10-08"))
   == "CRYPTOFAV|20261008", "the crypto key is unchanged")

print("\nthe band, both ends inclusive")
eq(ids([rung("KXGOLDD", "4006", 0.70)], FIVE_NOW), ["KXGOLDD-26OCT0817-T4006"], "0.70 is in")
eq(ids([rung("KXGOLDD", "4006", 0.80)], FIVE_NOW), ["KXGOLDD-26OCT0817-T4006"], "0.80 is in too")
eq(ids([rung("KXGOLDD", "4006", 0.69)], FIVE_NOW), [], "0.69 is out")
eq(ids([rung("KXGOLDD", "4006", 0.81)], FIVE_NOW), [], "0.81 is out")

print("\nthe lowest rung in band, one per commodity")
ladder = [rung("KXGOLDD", "3996", 0.80), rung("KXGOLDD", "4006", 0.73),
          rung("KXGOLDD", "4016", 0.71), rung("KXGOLDD", "3900", 0.95)]
eq(ids(ladder, FIVE_NOW), ["KXGOLDD-26OCT0817-T4016"],
   "of three in-band gold rungs only the LOWEST-priced is taken")
eq(len(picks(ladder, FIVE_NOW)), 1, "so one nested ladder can never produce two bets")
two = ladder + [rung("KXSILVERD", "47.5", 0.72), rung("KXSILVERD", "48", 0.78)]
eq(ids(two, FIVE_NOW), ["KXGOLDD-26OCT0817-T4016", "KXSILVERD-26OCT0817-T47.5"],
   "a second commodity is a second bet, its own lowest rung")
eq([p["pick"] for p in picks(two, FIVE_NOW)], ["a", "a"], "always the Yes side")
eq(ids([rung("KXZECD", "100", 0.75)], FIVE_NOW), [], "a series not on the list is refused")
eq(ids([rung("KXGOLDD", "4006", 0.75, sport="commodities")], FIVE_NOW), [],
   "a row from the price-baseline domain is not this lane's")

print("\ntwo closes, two windows")
wti = [rung("KXWTI", "81.49", 0.80, token="26OCT0814"), rung("KXWTI", "81.99", 0.74, token="26OCT0814")]
eq(ids(wti, WTI_NOW), ["KXWTI-26OCT0814-T81.99"], "WTI is taken 2.5h before its 14:30 ET close")
eq(ids(wti, FIVE_NOW), [], "and not in the 17:00 group's window, when its close has passed")
eq(ids(ladder, WTI_NOW), [], "gold is not taken in the WTI window, 5h before its own close")
eq(ids(wti, WTI_CLOSE - datetime.timedelta(hours=1, minutes=59)), [], "1h59m before the close is too late")
eq(ids(wti, WTI_CLOSE - datetime.timedelta(hours=3, minutes=31)), [], "3h31m is too early")
eq(ids(wti, WTI_CLOSE - datetime.timedelta(hours=2)), ["KXWTI-26OCT0814-T81.99"], "exactly 2h is in")
eq(ids(wti, WTI_CLOSE - datetime.timedelta(hours=3, minutes=30)), ["KXWTI-26OCT0814-T81.99"],
   "and exactly 3h30m is in")
hourly = FIVE_CLOSE.replace(hour=19)
eq(ids([rung("KXGOLDD", "4006", 0.75, start=hourly)], hourly - datetime.timedelta(hours=2, minutes=30)), [],
   "an expiry at another hour on the series is a different contract and is refused")
wti_at_17 = [rung("KXWTI", "81.99", 0.74, start=FIVE_CLOSE, token="26OCT0817")]
eq(ids(wti_at_17, FIVE_NOW), [], "a WTI rung closing at 17:00 is not WTI's daily close")
both = wti + ladder
eq(ids(both, WTI_NOW), ["KXWTI-26OCT0814-T81.99"], "the morning read takes WTI alone")
eq(ids(both, FIVE_NOW), ["KXGOLDD-26OCT0817-T4016"], "the afternoon read takes the 17:00 group alone")
# A Thursday in October, a Monday after the November change, a Thursday after the March one.
for day in (datetime.date(2026, 10, 15), datetime.date(2026, 11, 16), datetime.date(2027, 3, 18)):
    for series, (h, m) in (("KXWTI", (14, 30)), ("KXGOLDD", (17, 0))):
        close = datetime.datetime.combine(day, datetime.time(h, m), ET)
        r = rung(series, "1", 0.75, start=close, token=close.strftime("%y%b%d%H").upper())
        slot = datetime.datetime.combine(day, datetime.time(10 if series == "KXWTI" else 13, 15),
                                         ZoneInfo("America/Chicago"))
        eq([p["market_id"] for p in picks([r], slot)], [r["market_id"]],
           f"{day} {series}: the Central timer slot lands inside the window on either side of the clock change")

print("\ntrading days only")
sat = datetime.datetime(2026, 10, 10, 17, 0, tzinfo=ET)
eq(ids([rung("KXGOLDD", "4006", 0.75, start=sat, token="26OCT1017")],
       sat.astimezone(timezone.utc) - datetime.timedelta(hours=2, minutes=30)), [],
   "a rung listed on a Saturday is refused")
thanks = datetime.datetime(2026, 11, 26, 17, 0, tzinfo=ET)
eq(ids([rung("KXGOLDD", "4006", 0.75, start=thanks, token="26NOV2617")],
       thanks.astimezone(timezone.utc) - datetime.timedelta(hours=2, minutes=30)), [],
   "a rung listed on Thanksgiving is refused")
fri = datetime.datetime(2026, 10, 9, 14, 30, tzinfo=ET)
eq(ids([rung("KXWTI", "81.99", 0.74, start=fri, token="26OCT0914")],
       fri.astimezone(timezone.utc) - datetime.timedelta(hours=2, minutes=30)), ["KXWTI-26OCT0914-T81.99"],
   "a Friday is a trading day")
windows = S.commod_fav_windows(datetime.datetime(2026, 10, 9, 22, 0, tzinfo=timezone.utc))
eq([w[4].astimezone(ET).strftime("%a %H:%M") for w in windows], ["Mon 14:30", "Mon 17:00"],
   "after Friday's closes the next windows are Monday's, skipping the weekend")
# Per-series calendar since 2026-10-09 (the move to Production): WTI lists Monday to
# Friday, the 17:00 group Monday to Thursday, so after Thanksgiving WTI's next window is
# Friday's and the 17:00 group's is Monday's.
windows = S.commod_fav_windows(datetime.datetime(2026, 11, 25, 23, 0, tzinfo=timezone.utc))
eq([w[4].astimezone(ET).date().isoformat() for w in windows], ["2026-11-27", "2026-11-30"],
   "the evening before Thanksgiving, the next windows are Friday's for WTI and Monday's for the 17:00 group")
ok(S.commod_fav_trading_day(datetime.date(2026, 10, 9), "KXWTI")
   and not S.commod_fav_trading_day(datetime.date(2026, 10, 9), "KXGOLDD")
   and S.commod_fav_trading_day(datetime.date(2026, 10, 8), "KXGOLDD"),
   "a Friday is a trading day for WTI and not for a 17:00 series")
fri_gold = datetime.datetime(2026, 10, 9, 17, 0, tzinfo=ET)
eq(ids([rung("KXGOLDD", "4006", 0.75, start=fri_gold, token="26OCT0917")],
       fri_gold.astimezone(timezone.utc) - datetime.timedelta(hours=2, minutes=30)), [],
   "a 17:00 rung listed on a Friday is refused: that close is the weekly series, not this lane's")
windows = S.commod_fav_windows(datetime.datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc))
eq([(w[4].astimezone(ET).strftime("%H:%M"), sorted(w[1])) for w in windows],
   [("14:30", ["KXWTI"]), ("17:00", ["KXBRENTD", "KXCOPPERD", "KXGOLDD", "KXNATGASD", "KXSILVERD"])],
   "a trading morning lists the WTI window first, then the 17:00 group")

print("\nthe liquidity floor")
eq(ids([rung("KXGOLDD", "4006", 0.75, bid=0.72)], FIVE_NOW), ["KXGOLDD-26OCT0817-T4006"],
   "an exactly 3c spread is kept")
eq(ids([rung("KXGOLDD", "4006", 0.75, bid=0.71)], FIVE_NOW), [], "a 4c spread is refused")
eq(ids([rung("KXGOLDD", "4006", 0.75, bid=0.715)], FIVE_NOW), [], "a 3.5c spread is refused")
eq(ids([rung("KXGOLDD", "4006", 0.75, size=24)], FIVE_NOW), [], "24 on the ask is refused")
eq(ids([rung("KXGOLDD", "4006", 0.75, size=25)], FIVE_NOW), ["KXGOLDD-26OCT0817-T4006"], "25 is kept")
_untr = rung("KXGOLDD", "4006", 0.75)
_untr["tradeable"] = {"a": False, "b": True}
eq(ids([_untr], FIVE_NOW), [], "an untradeable Yes is refused")
_mixed = [rung("KXGOLDD", "4016", 0.71, bid=0.60), rung("KXGOLDD", "4006", 0.73)]
eq(ids(_mixed, FIVE_NOW), ["KXGOLDD-26OCT0817-T4006"],
   "an illiquid lowest rung falls through to the next lowest that passes the floor")

print("\npublish: one bet per commodity per close, and the book is stored")


def temp_ledger():
    raw = {"meta": {}, "quotes": [], "coverage": {}}
    fd, path = tempfile.mkstemp(prefix="commod-fav-ledger-", suffix=".json")
    os.close(fd)
    try:
        with open(path, "w") as f:
            json.dump(raw, f)
        with open(path) as f:
            return json.load(f)
    finally:
        os.remove(path)


def publish_lane(d, rows, now, lane="commod_fav_band", sport="commodities_fav"):
    saved = S.CHALLENGERS
    fetch = S.fetch_commod_fav_band if lane == "commod_fav_band" else S.fetch_crypto_fav_band
    S.CHALLENGERS = {lane: lambda sp, now=now: fetch(sp, now=now)}
    try:
        return T.publish(d, {sport: rows}, {}, verbose=False, now=now)
    finally:
        S.CHALLENGERS = saved


def lane_rows(d, lane="commod_fav_band"):
    return [q for q in d["quotes"] if q.get("source") == lane]


d = temp_ledger()
a1 = publish_lane(d, ladder + two[4:], FIVE_NOW)
eq(a1, 2, "gold and silver each log one rung")
row = next(q for q in lane_rows(d) if q["market_id"] == "KXGOLDD-26OCT0817-T4016")
eq((row["bid"], row["ask"], row["ask_size"]), (0.70, 0.71, 200), "the row stores bid, ask and ask size")
eq(row["price"], 0.71, "at the ask it was taken at")
moved = [rung("KXGOLDD", "4006", 0.78), rung("KXGOLDD", "4016", 0.69)]
a2 = publish_lane(d, moved, FIVE_NOW + datetime.timedelta(minutes=25))
eq(a2, 0, "a second run inside the window logs no second gold rung")
eq(sorted(q["market_id"] for q in lane_rows(d)), ["KXGOLDD-26OCT0817-T4016", "KXSILVERD-26OCT0817-T47.5"],
   "one row per commodity per close")
# The next trading day for a 17:00 series after Thursday Oct 8 is Monday Oct 12; its
# Friday close is the weekly series and is refused (per-series calendar, 2026-10-09).
nxt = [rung("KXGOLDD", "4006", 0.73, start=FIVE_CLOSE + datetime.timedelta(days=4), token="26OCT1217")]
a3 = publish_lane(d, nxt, FIVE_NOW + datetime.timedelta(days=4))
eq(a3, 1, "the next trading day's close is a new bet")

d = temp_ledger()
coin = dict(rung("KXBTCD", "84750", 0.73, start=FIVE_CLOSE + datetime.timedelta(minutes=5),
                 sport="crypto_fav", token="26OCT0817"))
publish_lane(d, [coin], FIVE_NOW, lane="crypto_fav_band", sport="crypto_fav")
crypto_row = lane_rows(d, "crypto_fav_band")
ok(len(crypto_row) == 1 and not any(k in crypto_row[0] for k in ("bid", "ask", "ask_size")),
   "a crypto row logged through the same publish keeps its shape")

print()
if FAILS:
    print(f"FAILED: {len(FAILS)}")
    sys.exit(1)
print("all passed")
