#!/usr/bin/env python3
"""The commodities near-certain lanes, pre-registered 2026-10-20.

commod_nc_yes backs the Yes at 0.90-0.98 and commod_nc_no the No at 0.90-0.98 (No ask =
1 - Yes bid), the cheapest in band per commodity, 75 to 45 minutes before that series'
close. Every other term is commod_fav_band's. Like test_commodities_fav_band.py this file
is the registration as much as the test: a later edit to the band, the window, the rung
choice, the floor, the calendar or the lane order has to change an assertion here.
"""
import datetime
import json
import os
import sys
import tempfile
from datetime import timezone
from zoneinfo import ZoneInfo

import commodities_build as CB
import lane_windows as W
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
CT = ZoneInfo("America/Chicago")
# Thursday 2026-10-22. WTI closes 14:30 ET, the rest 17:00 ET.
WTI_CLOSE = datetime.datetime(2026, 10, 22, 14, 30, tzinfo=ET).astimezone(timezone.utc)
FIVE_CLOSE = datetime.datetime(2026, 10, 22, 17, 0, tzinfo=ET).astimezone(timezone.utc)
WTI_NOW = WTI_CLOSE - datetime.timedelta(minutes=60)
FIVE_NOW = FIVE_CLOSE - datetime.timedelta(minutes=60)


def rung(series, strike, yes_ask, yes_bid=None, size=200, bid_size=200, start=None,
         sport="commodities_fav", token="26OCT2217"):
    """One universe row, shaped as fetch_kalshi_binary builds them (No ask = 1 - Yes bid)."""
    yes_bid = round(yes_ask - 0.01, 2) if yes_bid is None else yes_bid
    close = start or (WTI_CLOSE if series == "KXWTI" else FIVE_CLOSE)
    no_ask, no_bid = round(1 - yes_bid, 4), round(1 - yes_ask, 4)
    return dict(sport=sport, venue="kalshi_binary",
                market_id=f"{series}-{token}-T{strike}", series=series,
                label=f"{series} above {strike}",
                side_a=f"${strike} or above", side_b="No",
                price_a=yes_ask, price_b=no_ask, price_draw=None,
                tradeable={"a": True, "b": True}, untraded=False,
                start=close.isoformat(), date=close.strftime("%Y-%m-%d"), volume=0.0,
                market={"ticker": f"{series}-{token}-T{strike}", "yes_bid_dollars": yes_bid,
                        "yes_ask_dollars": yes_ask, "no_bid_dollars": no_bid, "no_ask_dollars": no_ask,
                        "yes_ask_size_fp": size, "yes_bid_size_fp": bid_size},
                url="https://kalshi.com/markets/x")


def no_rung(series, strike, no_ask, **kw):
    """A rung whose NO ask is `no_ask` (Yes bid = 1 - no_ask, Yes ask a cent above)."""
    yes_bid = round(1 - no_ask, 4)
    return rung(series, strike, round(yes_bid + 0.01, 4), yes_bid=yes_bid, **kw)


def ids(fetch, rows, now):
    return sorted(p["market_id"] for p in fetch("commodities_fav", universe={"commodities_fav": rows}, now=now))


yes = lambda rows, now: ids(S.fetch_commod_nc_yes, rows, now)
no = lambda rows, now: ids(S.fetch_commod_nc_no, rows, now)

print("registered parameters")
eq(S.COMMOD_NC_BAND, (0.90, 0.98), "the band is 0.90-0.98")
eq((S.COMMOD_NC_FROM_MIN, S.COMMOD_NC_TO_MIN), (75, 45), "the window is 75 to 45 minutes before the close")
eq((S.COMMOD_NC_MAX_SPREAD, S.COMMOD_NC_MIN_ASK_SIZE), (S.COMMOD_FAV_MAX_SPREAD, S.COMMOD_FAV_MIN_ASK_SIZE),
   "the liquidity floor is commod_fav_band's")
eq((S.COMMOD_NC_MAX_SPREAD, S.COMMOD_NC_MIN_ASK_SIZE), (0.03, 25), "and that is 3c and 25 contracts")
eq(S.COMMOD_NC_READ_DAYS, T.READ_FLOOR, "read at 30 market-days")
eq(S.COMMOD_LANE_PRIORITY, ("commod_fav_band", "commod_nc_yes", "commod_nc_no"), "the lane order")
for name, side in (("commod_nc_yes", "a"), ("commod_nc_no", "b")):
    m = S.SOURCES[name]
    eq(m["sports"], ["commodities_fav"], f"{name}: the commodity lane's own sport")
    eq((m["baseline"], m["favourite_side"], m["favourite_band"]), ("favourite_population", side, (0.90, 0.98)),
       f"{name}: judged against every in-band rung on its side")
    ok(m.get("one_per_coin_close") is True and m.get("store_book") is True and not m.get("one_per_day"),
       f"{name}: one per commodity per close, the book stored")
    ok(S.CHALLENGERS.get(name) is (S.fetch_commod_nc_yes if side == "a" else S.fetch_commod_nc_no),
       f"{name}: the fetcher is wired")
    note = " ".join(m["note"].split())
    for phrase in ("PRE-REGISTERED 2026-10-20", "Sandbox only and on paper only", "0.90-0.98", "75 to 45 minutes",
                   "CHEAPEST", "229 settled", "47 trading days", "z clustered by day", "2026-09-14",
                   "only in the last hour", "16 wins", "starts from zero", "30 independent market-days",
                   "every in-band rung", "ONE MARKET, ONE LANE", "7% taker fee", "trading days only"):
        ok(phrase in note, f"{name}: the registration says {phrase!r}")
yes_note, no_note = S.SOURCES["commod_nc_yes"]["note"], S.SOURCES["commod_nc_no"]["note"]
ok("148/152" in yes_note and "+3.5%" in yes_note and "z +2.65" in yes_note and "-1.8%" in yes_note,
   "the Yes figures: 148/152, +3.5%, z +2.65, -1.8% at 3h")
ok("150/155" in no_note and "+2.7%" in no_note and "z +2.09" in no_note and "-3.3%" in no_note,
   "the No figures: 150/155, +2.7%, z +2.09, -3.3% at 3h")
ok("commod_nc_yes|commodities_fav" not in T.PAIR_OVERRIDES and "commod_nc_no|commodities_fav" not in T.PAIR_OVERRIDES,
   "no Production override: Sandbox only")
eq(T.price_band("commodities_fav"), (T.PRICE_FLOOR, 0.98), "the sport may log up to 0.98")
eq(S.KALSHI_BINARY["commodities_fav"]["lead_h"], 0.5, "the universe keeps rungs down to 30 minutes out")
ok(list(S.CHALLENGERS).index("commod_fav_band") < list(S.CHALLENGERS).index("commod_nc_yes")
   < list(S.CHALLENGERS).index("commod_nc_no"), "publish() logs the lanes in priority order")

print("\nthe band, both ends inclusive")
eq(yes([rung("KXGOLDD", "4006", 0.90)], FIVE_NOW), ["KXGOLDD-26OCT2217-T4006"], "Yes 0.90 is in")
eq(yes([rung("KXGOLDD", "4006", 0.98)], FIVE_NOW), ["KXGOLDD-26OCT2217-T4006"], "Yes 0.98 is in")
eq(yes([rung("KXGOLDD", "4006", 0.89)], FIVE_NOW), [], "Yes 0.89 is out")
eq(yes([rung("KXGOLDD", "4006", 0.99)], FIVE_NOW), [], "Yes 0.99 is out")
eq(no([no_rung("KXGOLDD", "4100", 0.90)], FIVE_NOW), ["KXGOLDD-26OCT2217-T4100"], "No 0.90 is in")
eq(no([no_rung("KXGOLDD", "4100", 0.98)], FIVE_NOW), ["KXGOLDD-26OCT2217-T4100"], "No 0.98 is in")
eq(no([no_rung("KXGOLDD", "4100", 0.89)], FIVE_NOW), [], "No 0.89 is out")
eq(no([no_rung("KXGOLDD", "4100", 0.99)], FIVE_NOW), [], "No 0.99 is out")
eq(yes([no_rung("KXGOLDD", "4100", 0.94)], FIVE_NOW), [], "a 94c No is not a Yes pick")
eq(no([rung("KXGOLDD", "4006", 0.94)], FIVE_NOW), [], "and a 94c Yes is not a No pick")
eq(yes([rung("KXGOLDD", "4006", 0.75)], FIVE_NOW), [], "the 70-80c band is commod_fav_band's, not this lane's")

print("\nthe last-hour window")
wti = [rung("KXWTI", "81.49", 0.95, token="26OCT2214")]
eq(yes(wti, WTI_NOW), ["KXWTI-26OCT2214-T81.49"], "WTI 1h before its 14:30 ET close")
eq(yes(wti, WTI_CLOSE - datetime.timedelta(minutes=75)), ["KXWTI-26OCT2214-T81.49"], "exactly 75 minutes is in")
eq(yes(wti, WTI_CLOSE - datetime.timedelta(minutes=45)), ["KXWTI-26OCT2214-T81.49"], "exactly 45 minutes is in")
eq(yes(wti, WTI_CLOSE - datetime.timedelta(minutes=76)), [], "76 minutes is too early")
eq(yes(wti, WTI_CLOSE - datetime.timedelta(minutes=44)), [], "44 minutes is too late")
eq(yes(wti, WTI_CLOSE - datetime.timedelta(hours=3)), [], "3h out is the favourite band's window, not this one")
gold = [rung("KXGOLDD", "4006", 0.95)]
eq(yes(gold, WTI_NOW), [], "gold is not taken in the WTI window")
eq(yes(wti, FIVE_NOW), [], "WTI is not taken in the 17:00 window, its close has passed")
eq(yes([rung("KXWTI", "81.49", 0.95, start=FIVE_CLOSE, token="26OCT2217")], FIVE_NOW), [],
   "a WTI rung closing at 17:00 is not WTI's daily close")
w = S.commod_nc_windows(datetime.datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc))
eq([(x[2].astimezone(CT).strftime("%H:%M"), x[3].astimezone(CT).strftime("%H:%M"), x[4].astimezone(ET).strftime("%H:%M"))
    for x in w], [("12:15", "12:45", "14:30"), ("14:45", "15:15", "17:00")],
   "windows in Central: 12:15-12:45 for WTI, 14:45-15:15 for the 17:00 group")
# After the November clock change the window still sits 75-45 minutes before the Eastern close.
nov = datetime.datetime(2026, 11, 16, 17, 0, tzinfo=ET)
eq(yes([rung("KXGOLDD", "4006", 0.95, start=nov, token="26NOV1617")], nov.astimezone(timezone.utc)
       - datetime.timedelta(minutes=60)), ["KXGOLDD-26NOV1617-T4006"], "after the clock change too")

print("\ncheapest in band, one per commodity, ties to the lower ticker")
ladder = [rung("KXGOLDD", "3990", 0.97), rung("KXGOLDD", "4000", 0.92), rung("KXGOLDD", "4010", 0.95),
          rung("KXGOLDD", "4020", 0.85)]
eq(yes(ladder, FIVE_NOW), ["KXGOLDD-26OCT2217-T4000"], "the cheapest in-band Yes, the rung nearest the price")
eq(len(S.fetch_commod_nc_yes("commodities_fav", universe={"commodities_fav": ladder}, now=FIVE_NOW)), 1,
   "one nested ladder makes one bet")
noladder = [no_rung("KXGOLDD", "4100", 0.97), no_rung("KXGOLDD", "4080", 0.91), no_rung("KXGOLDD", "4090", 0.94)]
eq(no(noladder, FIVE_NOW), ["KXGOLDD-26OCT2217-T4080"], "the cheapest in-band No")
tie = [rung("KXGOLDD", "4010", 0.93), rung("KXGOLDD", "4000", 0.93)]
eq(yes(tie, FIVE_NOW), ["KXGOLDD-26OCT2217-T4000"], "equal prices go to the lower ticker")
multi = ladder + [rung("KXSILVERD", "47.5", 0.96), rung("KXSILVERD", "47", 0.91)]
eq(yes(multi, FIVE_NOW), ["KXGOLDD-26OCT2217-T4000", "KXSILVERD-26OCT2217-T47"], "a second commodity is a second bet")
eq({p["pick"] for p in S.fetch_commod_nc_no("commodities_fav", universe={"commodities_fav": noladder}, now=FIVE_NOW)},
   {"b"}, "the No lane always backs No")
eq(yes([rung("KXZECD", "1", 0.95)], FIVE_NOW), [], "a series not on the list is refused")
eq(yes([rung("KXGOLDD", "4006", 0.95, sport="commodities")], FIVE_NOW), [], "a price-baseline row is not this lane's")

print("\nthe liquidity floor, on the side bought")
eq(yes([rung("KXGOLDD", "4006", 0.95, yes_bid=0.92)], FIVE_NOW), ["KXGOLDD-26OCT2217-T4006"], "a 3c spread is kept")
eq(yes([rung("KXGOLDD", "4006", 0.95, yes_bid=0.91)], FIVE_NOW), [], "a 4c spread is refused")
eq(yes([rung("KXGOLDD", "4006", 0.95, size=24)], FIVE_NOW), [], "24 at the Yes ask is refused")
eq(yes([rung("KXGOLDD", "4006", 0.95, size=25)], FIVE_NOW), ["KXGOLDD-26OCT2217-T4006"], "25 is kept")
eq(no([no_rung("KXGOLDD", "4100", 0.94, bid_size=24)], FIVE_NOW), [], "24 at the No ask (the Yes bid) is refused")
eq(no([no_rung("KXGOLDD", "4100", 0.94, bid_size=25, size=1)], FIVE_NOW), ["KXGOLDD-26OCT2217-T4100"],
   "the No floor reads the size at the Yes bid, not the Yes ask")
_wide = rung("KXGOLDD", "4100", 0.10, yes_bid=0.06)        # No ask 0.94, No bid 0.90: 4c
eq(no([_wide], FIVE_NOW), [], "a 4c No spread is refused")
_one = rung("KXGOLDD", "4100", 0.07, yes_bid=0.06)
_one["market"].pop("no_bid_dollars"), _one["market"].pop("no_ask_dollars")
eq(no([_one], FIVE_NOW), ["KXGOLDD-26OCT2217-T4100"], "with no No quote the No book is the Yes book's complement")
_untr = rung("KXGOLDD", "4006", 0.95)
_untr["tradeable"] = {"a": False, "b": True}
eq(yes([_untr], FIVE_NOW), [], "an untradeable Yes is refused")
_mixed = [rung("KXGOLDD", "4000", 0.91, size=5), rung("KXGOLDD", "4010", 0.94)]
eq(yes(_mixed, FIVE_NOW), ["KXGOLDD-26OCT2217-T4010"], "a thin cheapest rung falls through to the next that passes")

print("\ntrading days only")
sat = datetime.datetime(2026, 10, 24, 17, 0, tzinfo=ET)
eq(yes([rung("KXGOLDD", "4006", 0.95, start=sat, token="26OCT2417")],
       sat.astimezone(timezone.utc) - datetime.timedelta(minutes=60)), [], "a Saturday rung is refused")
thanks = datetime.datetime(2026, 11, 26, 14, 30, tzinfo=ET)
eq(yes([rung("KXWTI", "81", 0.95, start=thanks, token="26NOV2614")],
       thanks.astimezone(timezone.utc) - datetime.timedelta(minutes=60)), [], "Thanksgiving is refused")
fri = datetime.datetime(2026, 10, 23, 14, 30, tzinfo=ET)
eq(yes([rung("KXWTI", "81", 0.95, start=fri, token="26OCT2314")],
       fri.astimezone(timezone.utc) - datetime.timedelta(minutes=60)), ["KXWTI-26OCT2314-T81"], "a Friday WTI rung is taken")
fri5 = datetime.datetime(2026, 10, 23, 17, 0, tzinfo=ET)
eq(yes([rung("KXGOLDD", "4006", 0.95, start=fri5, token="26OCT2317")],
       fri5.astimezone(timezone.utc) - datetime.timedelta(minutes=60)), [], "a Friday 17:00 rung is the weekly series: refused")
w = S.commod_nc_windows(datetime.datetime(2026, 10, 23, 22, 0, tzinfo=timezone.utc))
eq([x[4].astimezone(ET).strftime("%a %H:%M") for x in w], ["Mon 14:30", "Mon 17:00"],
   "after Friday the next windows are Monday's")

print("\none market, one lane: commod_fav_band, then Yes, then No")
# Not reachable with real prices (a rung cannot sit in two bands at once), so the guard is
# exercised by a fixture whose price fields disagree with each other on purpose.
both = rung("KXGOLDD", "4006", 0.95)
both["price_b"] = 0.95
eq((yes([both], FIVE_NOW), no([both], FIVE_NOW)), (["KXGOLDD-26OCT2217-T4006"], []),
   "a rung in band on both sides goes to the Yes lane only")
saved = S.fetch_commod_fav_band
S.fetch_commod_fav_band = lambda sport, universe=None, now=None, quiet=False: [dict(market_id=both["market_id"], pick="a")]
try:
    eq((yes([both], FIVE_NOW), no([both], FIVE_NOW)), ([], []), "a rung commod_fav_band takes goes to neither")
finally:
    S.fetch_commod_fav_band = saved

print("\npublish: one per commodity per close, the book of the side bought, the ledger guard")


def temp_ledger():
    raw = {"meta": {}, "quotes": [], "coverage": {}}
    fd, path = tempfile.mkstemp(prefix="commod-nc-ledger-", suffix=".json")
    os.close(fd)
    try:
        with open(path, "w") as f:
            json.dump(raw, f)
        with open(path) as f:
            return json.load(f)
    finally:
        os.remove(path)


def publish(d, rows, now, lanes=("commod_nc_yes", "commod_nc_no")):
    saved = S.CHALLENGERS
    S.CHALLENGERS = {n: (lambda sp, n=n: saved[n](sp, now=now)) for n in lanes}
    try:
        return T.publish(d, {"commodities_fav": rows}, {}, verbose=False, now=now)
    finally:
        S.CHALLENGERS = saved


def lane_rows(d, lane):
    return [q for q in d["quotes"] if q.get("source") == lane]


d = temp_ledger()
day = ladder + noladder + [rung("KXSILVERD", "47", 0.91)]
eq(publish(d, day, FIVE_NOW), 3, "gold Yes, silver Yes and gold No log")
y = next(q for q in lane_rows(d, "commod_nc_yes") if q["market_id"] == "KXGOLDD-26OCT2217-T4000")
eq((y["pick"], y["price"], y["bid"], y["ask"], y["ask_size"]), ("a", 0.92, 0.91, 0.92, 200),
   "the Yes row is the Yes ask, with the Yes book")
n = lane_rows(d, "commod_nc_no")[0]
eq((n["market_id"], n["pick"], n["price"], n["ask"]), ("KXGOLDD-26OCT2217-T4080", "b", 0.91, 0.91),
   "the No row is the No ask, with the No book")
ok(n["bet"] and y["bet"] and n["stake"] == T.STAKE, "both are bets at the flat stake")
moved = [rung("KXGOLDD", "4030", 0.90), no_rung("KXGOLDD", "4070", 0.90)]
eq(publish(d, moved, FIVE_NOW + datetime.timedelta(minutes=10)), 0, "a second read logs no second gold rung")
eq(publish(d, [rung("KXGOLDD", "4006", 0.95, start=FIVE_CLOSE + datetime.timedelta(days=4), token="26OCT2617")],
           FIVE_NOW + datetime.timedelta(days=4)), 1, "the next trading day's close is a new bet")

d = temp_ledger()
held = rung("KXGOLDD", "4006", 0.95)
d["quotes"].append(dict(id="commod_fav_band:" + held["market_id"], source="commod_fav_band", sport="commodities_fav",
                        market_id=held["market_id"], bet=True, status="open", date=held["date"], start=held["start"],
                        pick="a", price=0.78, logged=(FIVE_NOW - datetime.timedelta(hours=2)).isoformat()))
eq(publish(d, [held], FIVE_NOW), 0, "a market commod_fav_band already holds is never logged by another lane")

print("\nlane windows: three reads 10 minutes apart, skipped once both lanes hold every series")
win = [x for x in W.windows(WTI_NOW, ledger={"quotes": []}, games=[], fixtures=[]) if x["lane"] == "commod_nc"]
eq(sorted((x["start"].astimezone(CT).strftime("%H:%M"), x["end"].astimezone(CT).strftime("%H:%M"))
          for x in win if x["close"].date() == WTI_CLOSE.date()),
   [("12:15", "12:45"), ("14:45", "15:15")], "two windows on a Thursday, in Central")
eq(W.STAMP["commod_nc"], W.STAMP["commod_fav_band"], "the commodity stamp file the tracker triggers on")
eq(W.WINDOW_LANES["commod_nc"], ("commod_nc_yes", "commod_nc_no"), "the window serves both lanes")
start = WTI_CLOSE - datetime.timedelta(minutes=75)
reads = [k for t in (0, 10, 20) for x, k in W.due(start + datetime.timedelta(minutes=t), {"quotes": []}, [], [])
         if x["lane"] == "commod_nc"]
eq(reads, [1, 2, 3], "read 1, 2 and 3 at 75, 65 and 55 minutes before the close")
eq([k for x, k in W.due(WTI_CLOSE - datetime.timedelta(minutes=49), {"quotes": []}, [], []) if x["lane"] == "commod_nc"],
   [], "nothing asked for in the last 5 minutes of the window")
one = {"quotes": [dict(source="commod_nc_yes", bet=True, market_id="KXWTI-26OCT2214-T81")]}
eq([k for x, k in W.due(start, one, [], []) if x["lane"] == "commod_nc"], [1], "the Yes lane alone does not stop the reads")
full = {"quotes": one["quotes"] + [dict(source="commod_nc_no", bet=True, market_id="KXWTI-26OCT2214-T85")]}
eq([k for x, k in W.due(start, full, [], []) if x["lane"] == "commod_nc"], [], "both lanes holding WTI does")
sat_now = datetime.datetime(2026, 10, 24, 13, 30, tzinfo=ET).astimezone(timezone.utc)
eq([x for x in W.windows(sat_now, {"quotes": []}, [], []) if x["lane"] == "commod_nc"
    and x["close"].astimezone(ET).date() == sat_now.astimezone(ET).date()], [], "no window on a Saturday")

print("\nthe commodities page lists both lanes under the Sandbox")
names = [r["name"] for r in CB.page_rows({"meta": {}, "quotes": [], "coverage": {}}, {"pairs": {}})]
ok("commod_nc_yes" in names and "commod_nc_no" in names, "both lanes have a rule row before they bet")
ok(not any(r["prod"] for r in CB.page_rows({"meta": {}, "quotes": [], "coverage": {}}, {"pairs": {}})
           if r["name"] in CB.NC_LANES), "and neither is in Production")
eq((CB.rule_name({"name": "commod_nc_yes"}), CB.rule_name({"name": "commod_nc_no"})),
   ("Near-certain · last hour · YES", "Near-certain · last hour · NO"), "their names")
eq(dict(CB.params("commod_nc_no"))["Entry"], "No ask (1 − Yes bid) 90–98¢, 75–45 min before the close",
   "the No lane's entry line")
eq(CB.pick_text(dict(pick="b", side_a="$4,100 or above", market_id="KXGOLDD-26OCT2217-T4100")),
   "No · Gold above $4,100", "a No pick names the rung it backs against")
html = CB.build(d={"meta": {}, "quotes": [], "coverage": {}}, st={"pairs": {}}, now=FIVE_NOW)
ok("Near-certain · last hour · YES" in html and "Near-certain · last hour · NO" in html, "the page shows both")

print()
if FAILS:
    print(f"FAILED: {len(FAILS)}")
    sys.exit(1)
print("all passed")
