#!/usr/bin/env python3
"""The crypto angle lanes of 2026-10-20 (offline).

crypto_eth_fav_both / crypto_sol_fav_both: ETH / SOL, the cheapest YES and the cheapest NO priced
0.60-0.80, one per side per close, yielding a NO rung crypto_fav_band_below holds. With the below
lane they replace crypto_fav_band in Production; the feed learned the No of a ladder rung.
"""
import datetime
import sys
from datetime import timezone

import production as PR
import sandbox_audit
import sandbox_sources as S
import sandbox_track as T

FAILS = []
BOTH = ("crypto_eth_fav_both", "crypto_sol_fav_both")


def ok(cond, why):
    print(f"  {'ok  ' if cond else 'FAIL'} {why}")
    if not cond:
        FAILS.append(why)


def eq(got, want, why):
    ok(got == want, why if got == want else f"{why} — got {got!r}, want {want!r}")


# Shaped as test_crypto_fav_band_siblings' rungs (copied: importing that file runs it).
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


def picks(lane, rows, now=RUN_1):
    return [(p["market_id"].rsplit("-T", 1)[1], p["pick"])
            for p in S.CHALLENGERS[lane]("crypto_fav", universe={"crypto_fav": rows}, now=now)]


print("registration")
for lane in BOTH:
    m = S.SOURCES[lane]
    eq((m["sports"], m["baseline"], m.get("one_per_coin_close_side"), m.get("yields_to"), m.get("favourite_side"),
        m["connected"]), (["crypto_fav"], "favourite_population", True, ("crypto_fav_band_below",), None, True),
       f"{lane}: crypto_fav, the favourites on both sides, one per side per close, yields to the below lane")
    ok("PRE-REGISTERED 2026-10-20" in m["note"] and "CAVEAT" in m["note"] and "FOUND on" in m["note"],
       f"{lane}: pre-registered with the research figures and the in-sample caveat")
ok("28/30" in S.SOURCES["crypto_eth_fav_both"]["note"] and "z +3.76" in S.SOURCES["crypto_eth_fav_both"]["note"], "ETH cites 28/30, z +3.76")
ok("32/38" in S.SOURCES["crypto_sol_fav_both"]["note"] and "z +1.92" in S.SOURCES["crypto_sol_fav_both"]["note"], "SOL cites 32/38, z +1.92")
order = list(S.CHALLENGERS)
ok(all(order.index("crypto_fav_band_below") < order.index(l) for l in BOTH), "the below lane runs first, so it takes a shared rung")
eq(S.CRYPTO_BOTH_BAND, (0.60, 0.80), "both bands are 0.60-0.80 inclusive")

print("\nthe picks: one coin, the cheapest Yes and every in-band No cheapest first")
eth = [rung("KXETHD", 3900, 0.82), rung("KXETHD", 3950, 0.78), rung("KXETHD", 4000, 0.65),
       rung("KXETHD", 4050, 0.34), rung("KXETHD", 4100, 0.27), rung("KXETHD", 4150, 0.15),
       rung("KXBTCD", 84000, 0.70), rung("KXSOLD", 190, 0.70)]
# No asks are 1 - (yes_ask - 0.01): 4050 -> 0.67, 4100 -> 0.74, 4150 -> 0.86 (out of band).
eq(picks("crypto_eth_fav_both", eth), [("4000", "a"), ("4050", "b"), ("4100", "b")],
   "ETH: Yes 0.65 (cheapest in band; 0.78 is dearer, 0.82 out), then No 0.67 and No 0.74")
eq(picks("crypto_sol_fav_both", eth), [("190", "a")], "SOL reads its own coin only")
eq(picks("crypto_eth_fav_both", [rung("KXETHD", 4000, 0.60), rung("KXETHD", 4050, 0.41)]), [("4000", "a"), ("4050", "b")],
   "0.60 on both ends is in band (No 0.60 = 1 - 0.40)")
eq(picks("crypto_eth_fav_both", [rung("KXETHD", 4000, 0.65, spread=0.04)]), [], "a 4c spread: skipped")
eq(picks("crypto_eth_fav_both", [rung("KXETHD", 4100, 0.27, no_size=10)]), [], "a thin No: skipped")
late = datetime.datetime(2026, 10, 6, 19, 30, tzinfo=timezone.utc)
eq(picks("crypto_eth_fav_both", eth, now=late), [], "1.5h before the close: outside the 2-3.5h window")

print("\none per side per close, and one market, one lane")


def publish_all(d, rows, now, lanes=("crypto_fav_band_below",) + BOTH):
    saved = S.CHALLENGERS
    S.CHALLENGERS = {k: (lambda sport, now=now, k=k: saved[k](sport, now=now)) for k in lanes}
    try:
        return T.publish(d, {"crypto_fav": rows}, {}, verbose=False, now=now)
    finally:
        S.CHALLENGERS = saved


d = {"meta": {}, "quotes": [], "coverage": {}}
publish_all(d, eth, RUN_1)
by = {}
for q in d["quotes"]:
    by.setdefault(q["source"], []).append((q["market_id"].rsplit("-T", 1)[1], q["pick"], q["price"]))
eq(by.get("crypto_fav_band_below"), [("4100", "b", 0.74)], "the below lane takes ETH's No 0.74 (its 0.70-0.80 band)")
eq(by.get("crypto_eth_fav_both"), [("4000", "a", 0.65), ("4050", "b", 0.67)],
   "ETH both: the Yes, and its cheapest No (0.67) — the below lane's 0.74 rung is not its first choice here")
# Now the below lane's rung IS the ETH lane's cheapest No: it must yield and take the next one.
d2 = {"meta": {}, "quotes": [], "coverage": {}}
eth2 = [rung("KXETHD", 4000, 0.65), rung("KXETHD", 4100, 0.27), rung("KXETHD", 4120, 0.22)]   # No 0.74, No 0.79
publish_all(d2, eth2, RUN_1)
by2 = {}
for q in d2["quotes"]:
    by2.setdefault(q["source"], []).append((q["market_id"].rsplit("-T", 1)[1], q["pick"]))
eq(by2.get("crypto_fav_band_below"), [("4100", "b")], "below takes the cheapest No 0.70-0.80: 4100 at 0.74")
eq(by2.get("crypto_eth_fav_both"), [("4000", "a"), ("4120", "b")],
   "ETH both yields 4100 (held by the below lane) and takes its next cheapest in-band No, 4120 at 0.79")
# A later read with moved prices adds nothing: one per side per close.
moved = [dict(r, price_a=round(r["price_a"] - 0.02, 2), price_b=round(r["price_b"] + 0.02, 2)) for r in eth2]
publish_all(d2, moved, RUN_2)
eq(sum(q["source"] == "crypto_eth_fav_both" for q in d2["quotes"]), 2, "a second read logs no third ETH bet")
# Nothing left to yield to: with only the held rung in band, the No side logs nothing.
d3 = {"meta": {}, "quotes": [], "coverage": {}}
publish_all(d3, [rung("KXETHD", 4000, 0.65), rung("KXETHD", 4100, 0.27)], RUN_1)
eq([(q["market_id"].rsplit("-T", 1)[1], q["pick"]) for q in d3["quotes"] if q["source"] == "crypto_eth_fav_both"],
   [("4000", "a")], "no free in-band No: the ETH lane logs its Yes only")
# Without the below lane in the run (or in the ledger) nothing is held.
d4 = {"meta": {}, "quotes": [], "coverage": {}}
publish_all(d4, eth2, RUN_1, lanes=BOTH)
eq([(q["market_id"].rsplit("-T", 1)[1], q["pick"]) for q in d4["quotes"] if q["source"] == "crypto_eth_fav_both"],
   [("4000", "a"), ("4100", "b")], "with nothing held, the cheapest No is its own")

print("\nProduction: crypto_fav_band out, the three angle lanes in")
eq(sorted(k for k in T.PAIR_OVERRIDES if k.endswith("|crypto_fav")),
   ["crypto_eth_fav_both|crypto_fav", "crypto_fav_band_below|crypto_fav", "crypto_sol_fav_both|crypto_fav"],
   "the three angle lanes are the crypto Production pairs")
eq({k: T.PAIR_OVERRIDES[k]["moved_on"] for k in T.PAIR_OVERRIDES if k.endswith("|crypto_fav")},
   {k: "2026-10-20" for k in ("crypto_eth_fav_both|crypto_fav", "crypto_fav_band_below|crypto_fav", "crypto_sol_fav_both|crypto_fav")},
   "all listed 2026-10-20")
eq(T.PAIR_REMOVALS["crypto_fav_band|crypto_fav"], dict(removed_on="2026-10-20", keep_record=True), "crypto_fav_band keeps its record")
st = {"pairs": {"crypto_fav_band|crypto_fav": dict(stage="production", by_hand="2026-10-08", promoted_at="2026-10-08T17:50:08+00:00",
                                                   ready_at="2026-10-08T17:50:08+00:00", entry_since=None)}, "events": []}
T.evaluate_stages({"quotes": []}, st, now=datetime.datetime(2026, 10, 20, 23, tzinfo=timezone.utc), verbose=False)
eq({k: (st["pairs"][k]["stage"], st["pairs"][k].get("since")) for k in sorted(st["pairs"]) if k.endswith("|crypto_fav")},
   {"crypto_eth_fav_both|crypto_fav": ("production", None), "crypto_fav_band_below|crypto_fav": ("production", None),
    "crypto_fav_band|crypto_fav": ("sandbox", None), "crypto_sol_fav_both|crypto_fav": ("production", None)},
   "one run moves all four: the band back on its whole record, the three in")
T.evaluate_stages({"quotes": []}, st, now=datetime.datetime(2026, 10, 21, 2, tzinfo=timezone.utc), verbose=False)
eq(st["pairs"]["crypto_fav_band|crypto_fav"]["stage"], "sandbox", "and the band does not flip back on a later run")

print("\nthe feed: the No of a ladder rung")
q = dict(rung("KXSOLD", 190, 0.27), id="crypto_sol_fav_both:KXSOLD-26OCT0617-T190", source="crypto_sol_fav_both", pick="b",
         price=0.74, bet=True, status="open", logged=RUN_1.isoformat(), venue_start=None, start_source=None)
ok(T.placeable(q), "a ladder No is publishable")
lead = PR.lead_from_quote(q, "crypto_sol_fav_both|crypto_fav", RUN_1.isoformat())
eq((lead["headline"], lead["bet"], lead["route"]["outcome_side"], lead["route"]["market"]),
   ("Below $190 at the close", {"kind": "ladder", "side": "no"}, "no", "KXSOLD-26OCT0617-T190"),
   "it names the exact contract's No, read as the close landing below the rung")
yes = PR.lead_from_quote(dict(q, pick="a", price=0.65), "crypto_sol_fav_both|crypto_fav", RUN_1.isoformat())
ok(yes["id"] != lead["id"] and yes["bet"] == {"kind": "ladder", "side": "yes"}, "the Yes of the same lane is its own lead")
ok(sandbox_audit.COPY_RE.search(S.SOURCES["crypto_eth_fav_both"]["note"] + S.SOURCES["crypto_sol_fav_both"]["note"]
                                + S.SOURCES["crypto_eth_fav_both"]["label"]) is None, "the copy passes the audit's guarded phrases")

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
