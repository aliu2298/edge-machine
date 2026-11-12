#!/usr/bin/env python3
"""Rule 6 v2 · Zcash underdog at 20c+ (flipf4v2.py, flip-f4v2): F4 on Zcash, underdog price >= 20c, every hour."""
import sys

import flipf4v2 as R
import flipside_v2 as F
import swing15 as W
import swing15_build as WB
import sw15cuts as _CUTS
_CUTS.CUTS, _CUTS.RETIRED = {}, ()   # these tests check the rule itself; test_sw15cuts.py covers the Nov 10 cuts
import sw15cuts as _C2, swing15_build as _WB2, leadswap as _L2
_C2.RETIRED2, _C2.RETIRED3, _WB2.NARROWED, _L2.TRADES_RETIRED = (), (), False, {}   # the lane as it ran before the 2026-11-11 narrowing; test_sw15keep.py checks the narrowed page

FAILS = []


def check(why, got, want):
    good = got == want
    print(f"  {'ok  ' if good else 'FAIL'} {why}" + ("" if good else f" — got {got!r}, want {want!r}"))
    if not good:
        FAILS.append(why)


def win(series, open_iso, dog_price, result="yes"):
    """v1's S3 favourite is NO; F4 buys the underdog YES at yes_ask = dog_price."""
    yb = round(dog_price - 0.01, 4)
    return dict(ticker=f"{series}-{open_iso}", series=series, group="Crypto", open=open_iso, day=open_iso[:10], us_hours=False,
                fee_multiplier=1.0, result=result, minute_cols=[], minutes=[], s1={}, s2=dict(status="no_quote"),
                s3=dict(status="filled", side="no", yes_bid=yb, yes_ask=dog_price, price=round(1 - yb, 4), won=0.0, roi=-1.0))


check("frozen: one market, one key, fingerprinted", (R.ALLOW, R.fingerprint() == R.ALLOW_SHA256), ({"KXZEC15M": {"price": ["20+"]}}, True))
check("the start is a window boundary and F4's cut", (W._ts(R.FROM) % 900, R.FROM == F.RETIRED_TIMES["flipside_v2_f4"]), (0, True))
check("price: 20c and up", [R.price_band(p) for p in (0.19, 0.199, 0.20, 0.35)], ["<20", "<20", "20+", "20+"])
T = "2026-11-10T14:00:00Z"
check("20c+ underdog on Zcash: bet; under 20c: no bet", (R.allowed(win("KXZEC15M", T, 0.25)), R.allowed(win("KXZEC15M", T, 0.15))),
      (True, False))
check("every hour: 11 PM and 3 AM CT are bet too", [R.allowed(win("KXZEC15M", t, 0.25)) for t in ("2026-11-11T05:00:00Z", "2026-11-11T09:00:00Z")],
      [True, True])
check("Zcash only", R.allowed(win("KXBTC15M", T, 0.25)), False)
ws = [win("KXZEC15M", T, 0.25, "yes"), win("KXZEC15M", "2026-11-10T14:15:00Z", 0.10, "no"),
      win("KXZEC15M", "2026-11-09T20:00:00Z", 0.30, "no")]             # before the cut: F4's final record only
state = dict(W.empty(), windows={x["ticker"]: x for x in ws})
rec = R.records(state)
check("the lane counts the 25c bet (won); every bet (old F4) counts both", (rec["lane"]["all"]["n"], rec["lane"]["all"]["hits"],
      rec["every"]["all"]["n"]), (1, 1, 2))
html = WB.section(state)
flip = html.split('id="flipside_v2"')[1].split('<div class="sw15-lane">')[0]
row = flip.split('data-source="flipf4v2"')[1]
check("a collapsed row in The Flip Side; no F rows left; 'every hour', not the 07-22 sentence",
      ('data-source="flipside_v2_f' in flip, "Every bet (old F4)" in row, "; every hour." in row, "07-22 CT is never bet" in row.split("Rule details")[1].split("</details>")[0]),
      (False, True, True, False))
check("the in-sample line, and F4's final record in the archive",
      ("Nov 9 in-sample: 9/22, +41.7% — not counted" in flip, "F4 final:" in html.split('id="sw15-archive"')[1]), (True, True))

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
