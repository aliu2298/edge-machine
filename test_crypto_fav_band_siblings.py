#!/usr/bin/env python3
"""The three sibling crypto favourite-band lanes, pre-registered 2026-10-18.

crypto_fav_band_below      No 0.70-0.80 (both ends inclusive), the rung above the price
crypto_fav_band_60         Yes 0.60 to under 0.70
crypto_fav_band_below_60   No 0.60 to under 0.70

Every term but the side and the band is crypto_fav_band's. Sandbox only, fresh records.
"""
import datetime
import sys
from datetime import timezone

import crypto_build as CB
import lane_windows as W
import sandbox_audit
import sandbox_sources as S
import sandbox_track as T

FAILS = []
NEW = ("crypto_fav_band_below", "crypto_fav_band_60", "crypto_fav_band_below_60")


def ok(cond, why):
    print(f"  {'ok  ' if cond else 'FAIL'} {why}")
    if not cond:
        FAILS.append(why)


def eq(got, want, why):
    ok(got == want, why if got == want else f"{why} — got {got!r}, want {want!r}")


CLOSE = datetime.datetime(2026, 10, 6, 21, 0, tzinfo=timezone.utc)     # 17:00 ET, daylight time
RUN_1 = datetime.datetime(2026, 10, 6, 17, 50, tzinfo=timezone.utc)     # 3.17h out
RUN_2 = datetime.datetime(2026, 10, 6, 18, 15, tzinfo=timezone.utc)     # 2.75h out


def rung(series, strike, yes_ask, token="26OCT0617", when=None, no_size=500, yes_size=500,
         spread=0.01, tradeable_b=True):
    """One 17:00 ET ladder rung shaped like fetch_kalshi_binary's rows: NO ask = 1 - YES bid."""
    yes_bid = round(yes_ask - spread, 2)
    no_ask, no_bid = round(1 - yes_bid, 2), round(1 - yes_ask, 2)
    tk = f"{series}-{token}-T{strike}"
    when = when or CLOSE
    return dict(sport="crypto_fav", venue="kalshi_binary", market_id=tk, series=series,
                label=f"{series} {strike} or above", side_a=f"${strike} or above", side_b="No",
                price_a=yes_ask, price_b=no_ask, price_draw=None,
                tradeable={"a": True, "b": tradeable_b}, untraded=False,
                start=when.isoformat(), date=when.strftime("%Y-%m-%d"), volume=0.0,
                market={"ticker": tk, "yes_bid_dollars": yes_bid, "yes_ask_dollars": yes_ask,
                        "no_bid_dollars": no_bid, "no_ask_dollars": no_ask, "close_time": when.isoformat(),
                        "yes_ask_size_fp": yes_size, "yes_bid_size_fp": no_size},
                url="https://kalshi.com/markets/x")


def got(lane, rows, now=RUN_1):
    side = "b" if "below" in lane else "a"
    return [(p["market_id"].rsplit("-T", 1)[1], p["pick"],
             next(r[f"price_{side}"] for r in rows if r["market_id"] == p["market_id"]))
            for p in S.CHALLENGERS[lane]("crypto_fav", universe={"crypto_fav": rows}, now=now)]


print("registration")
for lane in NEW:
    m = S.SOURCES[lane]
    eq((m["sports"], m["baseline"], m.get("one_per_coin_close"), m["connected"]),
       (["crypto_fav"], "favourite_population", True, True), f"{lane}: crypto_fav, favourite population, one per coin per close")
eq({k: S.SOURCES[k]["favourite_side"] for k in ("crypto_fav_band",) + NEW},
   {"crypto_fav_band": "a", "crypto_fav_band_below": "b", "crypto_fav_band_60": "a", "crypto_fav_band_below_60": "b"},
   "each lane's population is the favourites on its own side")
eq(S.CRYPTO_FAV_BAND_60, (0.60, 0.70), "the lower band is 0.60 to 0.70, the upper end exclusive")
ok(all(lane + "|crypto_fav" not in T.PAIR_OVERRIDES for lane in NEW), "none of the three is listed for Production")
ok(all(S.CHALLENGERS.get(lane) for lane in NEW), "all three fetchers are wired")
ok("63/75 at 75c, +9.4%, z +1.65" in S.SOURCES["crypto_fav_band_below"]["note"], "the below note cites its research")
ok("42/52 at 65c, +21.3%, z +2.50" in S.SOURCES["crypto_fav_band_below_60"]["note"], "the below-60 note cites its research")
ok("37/49 at 65c, +13.5%, z +1.53" in S.SOURCES["crypto_fav_band_60"]["note"], "the 60 note cites its research")
ok(not any(sandbox_audit.COPY_RE.search(S.SOURCES[k]["label"] + " " + S.SOURCES[k]["note"]) for k in NEW),
   "labels and notes pass the public-copy guard")

print("\nselection: the cheapest in-band rung on the lane's side, per coin")
# YES asks 0.18-0.42 on rungs above the price: NO asks 0.83, 0.79, 0.73, 0.69, 0.65, 0.59.
btc = [rung("KXBTCD", 86000, y) for y in ()] + [
    rung("KXBTCD", 85000, 0.18), rung("KXBTCD", 84750, 0.22), rung("KXBTCD", 84500, 0.28),
    rung("KXBTCD", 84250, 0.32), rung("KXBTCD", 84000, 0.36), rung("KXBTCD", 83750, 0.42),
    # and Yes favourites below the price: 0.62, 0.66, 0.70, 0.74
    rung("KXBTCD", 83000, 0.62), rung("KXBTCD", 82750, 0.66), rung("KXBTCD", 82500, 0.70), rung("KXBTCD", 82250, 0.74)]
eq(got("crypto_fav_band_below", btc), [("84500", "b", 0.73)], "below: No 0.73 is the cheapest No in 0.70-0.80")
eq(got("crypto_fav_band_below_60", btc), [("84000", "b", 0.65)], "below 60: No 0.65 is the cheapest No in 0.60-0.70")
eq(got("crypto_fav_band_60", btc), [("83000", "a", 0.62)], "60: Yes 0.62 is the cheapest Yes in 0.60-0.70")
eq(got("crypto_fav_band", btc)[0][:2], ("82500", "a"), "the existing Yes lane still takes the 0.70 rung")

print("\nthe 0.70 edge belongs to the 0.70-0.80 lanes only")
edge_yes = [rung("KXETHD", 4500, 0.70)]
edge_no = [rung("KXETHD", 4700, 0.31)]                         # NO ask 1 - 0.30 = 0.70
eq((got("crypto_fav_band_60", edge_yes), [p[1] for p in got("crypto_fav_band", edge_yes)]), ([], ["a"]),
   "a 0.70 Yes is the 0.70-0.80 lane's, not the 0.60 lane's")
eq((got("crypto_fav_band_below_60", edge_no), got("crypto_fav_band_below", edge_no)), ([], [("4700", "b", 0.70)]),
   "a 0.70 No is the below lane's, not the below-60 lane's")
eq(got("crypto_fav_band_below_60", [rung("KXETHD", 4800, 0.41)]), [("4800", "b", 0.6)], "a 0.60 No is in the lower band")
eq(got("crypto_fav_band_below", [rung("KXETHD", 4900, 0.21)]), [("4900", "b", 0.8)], "a 0.80 No is in the upper band")
tie = [rung("KXSOLD", 205, 0.27), rung("KXSOLD", 200, 0.27)]
eq([p[0] for p in got("crypto_fav_band_below", tie)], ["200"], "equal No prices go to the lower ticker")

print("\nthe close and the window, either side of the clock change")
eq(got("crypto_fav_band_below", btc, now=CLOSE - datetime.timedelta(hours=4)), [], "4h out: too early")
eq(got("crypto_fav_band_below", btc, now=CLOSE - datetime.timedelta(hours=1, minutes=50)), [], "1h50 out: too late")
hourly = [rung("KXBTCD", 84500, 0.28, token="26OCT0616", when=CLOSE - datetime.timedelta(hours=1))]
eq(got("crypto_fav_band_below", hourly, now=RUN_1 - datetime.timedelta(hours=1)), [], "the 16:00 ET hourly close is not this lane's")
winter = datetime.datetime(2026, 11, 3, 22, 0, tzinfo=timezone.utc)   # 17:00 EST
w_rows = [rung("KXBTCD", 84500, 0.28, token="26NOV0317", when=winter)]
eq([p[0] for p in got("crypto_fav_band_below", w_rows, now=winter - datetime.timedelta(hours=3))], ["84500"],
   "after the clock change 17:00 ET is 22:00Z and still enters")

print("\nliquidity on the side bought")
eq(got("crypto_fav_band_below", [rung("KXBTCD", 84500, 0.28, no_size=10)]), [], "under 25 at the No ask: skipped")
eq(got("crypto_fav_band_below", [rung("KXBTCD", 84500, 0.28, yes_size=1)]), [("84500", "b", 0.73)],
   "a thin Yes ask does not block a No")
eq(got("crypto_fav_band_below", [rung("KXBTCD", 84500, 0.29, spread=0.04)]), [], "a 4c spread: skipped")
eq(got("crypto_fav_band_below", [rung("KXBTCD", 84500, 0.28, tradeable_b=False)]), [], "No side not tradeable: skipped")
eq(got("crypto_fav_band_60", [rung("KXBTCD", 83000, 0.64, yes_size=10)]), [], "the Yes 60 lane reads the Yes ask size")

print("\none entry per series per close, across runs")


def publish_all(d, rows, now):
    saved = S.CHALLENGERS
    S.CHALLENGERS = {k: (lambda sport, now=now, k=k: saved[k](sport, now=now)) for k in ("crypto_fav_band",) + NEW}
    try:
        return T.publish(d, {"crypto_fav": rows}, {}, verbose=False, now=now)
    finally:
        S.CHALLENGERS = saved


d = {"meta": {}, "quotes": [], "coverage": {}}
publish_all(d, btc, RUN_1)
moved = [dict(r) for r in btc]
for r in moved:
    r.update(price_b=round(r["price_b"] - 0.02, 2))
publish_all(d, moved, RUN_2)
by = {}
for q in d["quotes"]:
    by.setdefault(q["source"], []).append((q["market_id"].rsplit("-T", 1)[1], q["pick"], q["price"]))
eq(by.get("crypto_fav_band_below"), [("84500", "b", 0.73)], "below: one row, kept at its first price")
eq(by.get("crypto_fav_band_below_60"), [("84000", "b", 0.65)], "below 60: one row")
eq(by.get("crypto_fav_band_60"), [("83000", "a", 0.62)], "60: one row")
eq(len(by.get("crypto_fav_band") or []), 1, "and the existing lane still logs its own one")

print("\nsettled on Kalshi's result: a No wins on 'no'")
row = next(q for q in d["quotes"] if q["source"] == "crypto_fav_band_below")
T._apply_result(row, "b", "2026-10-06T21:05:00+00:00")
eq((row["status"], row["pnl"]), ("won", round(T.STAKE * (1 / 0.73 - 1), 2)), "No at 0.73 on a 'no' result wins")
lost = next(q for q in d["quotes"] if q["source"] == "crypto_fav_band_below_60")
T._apply_result(lost, "a", "2026-10-06T21:05:00+00:00")
eq((lost["status"], lost["pnl"]), ("lost", -T.STAKE), "No on a 'yes' result loses the stake")
eq(T.pnl_after_fee(row), round(T.STAKE * (1 / (0.73 + 0.07 * 0.73 * 0.27) - 1), 2), "the fee is taken on the No price")
f = T.faded(d, "crypto_fav_band_below", "crypto_fav")
eq((f["n"], f["won"]), (1, 0), "the fade of a winning No is the Yes, and it lost")

print("\nthe population is the favourites on the lane's own side")
for q in d["quotes"]:
    if q["status"] == "open":
        T._apply_result(q, "b", "2026-10-06T21:05:00+00:00")
a = T.assess(d, "crypto_fav_band_below", "crypto_fav")
yes = T.assess(d, "crypto_fav_band", "crypto_fav")
# No favourites in the ledger: the two No lanes' rows (0.73 won, 0.65 lost above). Yes favourites:
# the two Yes rows, both lost. Pooled together the below lane's blind rule would read -65.8%.
eq(round(a["base_roi"], 3), round(((1 / 0.73 - 1) - 1) / 2, 3),
   "the below lane is judged against the No favourites only")
eq(round(yes["base_roi"], 4), -1.0, "and the Yes lane against the Yes favourites only")

print("\nthe Crypto page lists all four lanes")
html = CB.build({"quotes": [], "meta": {}}, {"pairs": {}}, RUN_1)
for lane in ("crypto_fav_band",) + NEW:
    ok(CB.RULE_NAMES[lane] in html, f"the page names {lane}")
eq([n for n, _v in CB.params("crypto_fav_band_below")], ["Entry", "Selection", "Liquidity", "Close"], "the below lane's parameters")
ok("No ask, on the rung above the price, 70–80¢" in dict(CB.params("crypto_fav_band_below"))["Entry"], "below: No ask 70–80¢")
ok("60¢ to under 70¢" in dict(CB.params("crypto_fav_band_60"))["Entry"], "60: 60¢ to under 70¢")
eq(CB.pick_text(dict(pick="b", side_a="$84,500 or above", side_b="No")), "No · $84,500 or above", "a No pick names its rung")
ev = CB.events(d, CB.page_rows(d, {"pairs": {}}), RUN_1)
eq(len([e for e in ev if "KXBTCD" in str(e)]), 1, "one Bitcoin event that day, holding every lane's pick")

print("\nthe VPS reads serve all four lanes")
eq(W.WINDOW_LANES["crypto_fav_band"], ("crypto_fav_band",) + NEW, "the crypto window names the four lanes")

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
