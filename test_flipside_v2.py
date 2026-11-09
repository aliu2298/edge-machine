#!/usr/bin/env python3
"""The Flip Side v2 (flipside_v2.py, flip-v2): the frozen cells, the flipped entries, the fresh record, the page."""
import re
import sys

import sandbox_audit
import swing15 as W
import swing15_build as WB
import flipside_v2 as F

FAILS = []


def check(why, got, want):
    good = got == want
    print(f"  {'ok  ' if good else 'FAIL'} {why}" + ("" if good else f" — got {got!r}, want {want!r}"))
    if not good:
        FAILS.append(why)


def mrow(m, yb, ya):
    return [m, yb, ya, round(1 - ya, 4), round(1 - yb, 4), .1, .9, .5, 100.0, 50.0]


def win(series, open_iso, result, s1=None, s2=None, s3=None, minutes=None):
    return dict(ticker=f"{series}-{open_iso}", series=series, group="Crypto", open=open_iso, day=open_iso[:10],
                us_hours=False, result=result, fee_multiplier=1.0, schema=2, minute_cols=list(W.MINUTE_COLS),
                minutes=minutes or [], s1=s1 or {"0.15": None, "0.25": None, "0.35": None},
                s2=s2 or dict(status="no_quote", minute=2), s3=s3 or dict(status="no_quote", minute=10))


def trig(side, minute):
    return dict(side=side, won=None, exits={}, trigger=dict(band=.25, minute=minute))


print("the pre-registration")
check("ids and version", (tuple(F.CELLS), F.VERSION), (("flipside_v2_f1", "flipside_v2_f2", "flipside_v2_f3", "flipside_v2_f4"), "flip-v2"))
check("cell counts 15 / 12 / 13 / 8", tuple(len(v) for v in F.CELLS.values()), (15, 12, 13, 8))
check("tickers", (F.CELLS["flipside_v2_f1"][0], F.CELLS["flipside_v2_f4"][-1]), ("KX10YRRATE15M", "KXZEC15M"))
check("the record starts after the selection windows", W._ts(F.FROM) >= W._ts("2026-11-09T12:00:00+00:00"), True)

print("\nthe flipped entries")
T = "2026-11-09T14:00:00Z"
w1 = win("KXBTC15M", T, "no", s1={"0.15": None, "0.25": trig("yes", 2), "0.35": None},
         minutes=[mrow(0, .5, .52), mrow(1, .3, .32), mrow(2, .22, .24)])
f = F.flip(w1, "flipside_v2_f1")
cost = .78 + W.fee(.78, W.TAKER)
check("F1: the cheap side was YES at minute 2 -> NO at 1 - that minute's YES bid (78c), won on NO",
      (f["side"], f["price"], f["won"], f["roi"]), ("no", .78, 1.0, round(1 / cost - 1, 4)))
w2 = win("KXBTC15M", T, "no", s1={"0.15": None, "0.25": trig("no", 0), "0.35": None}, minutes=[mrow(0, .74, .76)])
f2 = F.flip(w2, "flipside_v2_f1")
check("F1: the cheap side was NO -> YES at that minute's YES ask (76c), lost on NO", (f2["side"], f2["price"], f2["roi"]), ("yes", .76, -1.0))
check("F2 reads the 35c trigger: none here", F.flip(w1, "flipside_v2_f2"), None)
w3 = win("KXBTC15M", T, "no", s1={"0.15": None, "0.25": trig("yes", 4), "0.35": None}, minutes=[mrow(0, .5, .52)])
check("a trigger minute with no minute row is a skip", F.flip(w3, "flipside_v2_f1"), dict(skip="no_minute_row"))
w4 = win("KXBTC15M", T, "yes", s1={"0.15": None, "0.25": trig("no", 0), "0.35": None}, minutes=[mrow(0, .99, 1.0)])
check("a price above 99c is out of range", F.flip(w4, "flipside_v2_f1")["skip"], "out_of_range")
s2 = dict(status="no_fill", minute=2, yes_bid=.70, yes_ask=.72, side="yes", price=.72)
w5 = win("KXUSDJPY15M", T, "no", s2=s2, s3=dict(status="filled", minute=10, yes_bid=.10, yes_ask=.12, side="no", price=.9))
f5 = F.flip(w5, "flipside_v2_f3")
check("F3: the S2 favourite was YES -> NO at 1 - 70c bid = 30c, whatever S2's own fill was; won on NO",
      (f5["side"], f5["price"], f5["won"]), ("no", .3, 1.0))
f6 = F.flip(w5, "flipside_v2_f4")
check("F4: the S3 favourite was NO -> YES at the 12c ask, lost", (f6["side"], f6["price"], f6["roi"]), ("yes", .12, -1.0))
check("no favourite in v1 (no quote): no flip", F.flip(win("KXUSDJPY15M", T, "no"), "flipside_v2_f3"), None)

print("\nthe record")
old = win("KXBTC15M", "2026-11-09T11:00:00Z", "no", s1=w1["s1"], minutes=w1["minutes"])
doge = win("KXDOGE15M", T, "no", s1=w1["s1"], minutes=w1["minutes"])          # DOGE is not an F1 cell
state = dict(W.empty(), windows={k: w for k, w in (("a", w1), ("b", w2), ("c", old), ("d", doge), ("e", w3), ("f", w5))})
rec = F.records(state)
r1 = rec["flipside_v2_f1"]
check("F1: BTC's two fresh windows (not the 11:00Z window, not DOGE), one won",
      (r1["all"]["n"], r1["all"]["hits"], r1["series"]["KXBTC15M"]["n"]), (2, 1, 2))
check("its fair rate is the mean price paid", round(r1["all"]["fair"], 4), round((.78 + .76) / 2, 4))
check("skips are counted by reason", r1["skips"], {"no_minute_row": 1})
check("F3 and F4: USDJPY counts for F3; F4 has no USDJPY cell",
      (rec["flipside_v2_f3"]["all"]["n"], rec["flipside_v2_f4"]["all"]), (1, None))
check("the ledger", (F.ledger(state)["version"], F.ledger(state)["records"]["flipside_v2_f1"]["all"]["n"]), ("flip-v2", 2))

print("\nthe page")
html = WB.section(state)
check("the block sits under 15-Minute Swing v2 and above v1",
      html.index("15-Minute Swing v2") < html.index("The Flip Side v2") < html.index('data-source="swing15_s1"'), True)
check("the header line", "Opposite side of the 15-Minute Swing; cells picked from one overnight session; 14-day backtest of "
      "the flips ran −0.5% to −16%; fresh record from 2026-11-09 13:15 UTC; review at 10, decide at 30." in html, True)
check("four rows", re.findall(r'data-source="(flipside_v2_f\d)"', html),
      ["flipside_v2_f1", "flipside_v2_f2", "flipside_v2_f3", "flipside_v2_f4"])
check("the Sandbox index lists them", [r["lane"] for r in WB.index_rows(state)][6:10], list(F.CELLS))
check("no dollar sign, no guarded phrase", (re.search(r"\$\d", html), sandbox_audit.COPY_RE.findall(html + WB.index_html(state))), (None, []))

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
