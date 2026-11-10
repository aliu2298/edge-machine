#!/usr/bin/env python3
"""Rule 5 v2 · Every Positive Setting (flipf3v2.py, flip-f3v2): the frozen allow-list, the early move (read before the
entry only), the gate, the page."""
import sys

import flipf3v2 as R
import flipside_v2 as F
import swing15 as W
import swing15_build as WB

FAILS = []


def check(why, got, want):
    good = got == want
    print(f"  {'ok  ' if good else 'FAIL'} {why}" + ("" if good else f" — got {got!r}, want {want!r}"))
    if not good:
        FAILS.append(why)


COLS = ["m", "yes_bid", "yes_ask", "no_bid", "no_ask", "low", "high", "last", "volume", "open_interest"]


def win(series, open_iso, mids, result="yes"):
    """v1's S2 favourite is NO at the row-1 quote when its mid < 0.5; F3 buys the underdog YES at yes_ask."""
    minutes = [[i, round(m - 0.005, 4), round(m + 0.005, 4), None, None, None, None, None, 0, 0] for i, m in enumerate(mids)]
    m1 = minutes[1]
    side = "no" if mids[1] < 0.5 else "yes"
    return dict(ticker=f"{series}-{open_iso}", series=series, group="Financials", open=open_iso, day=open_iso[:10],
                us_hours=False, fee_multiplier=1.0, result=result, minute_cols=COLS, minutes=minutes, s1={},
                s2=dict(status="filled", side=side, yes_bid=m1[1], yes_ask=m1[2], price=0.6, won=0.0, roi=-1.0),
                s3=dict(status="no_quote"))


T = "2026-11-10T14:00:00Z"                                         # 8 AM CT
check("frozen: the fingerprint is the registered one", R.fingerprint(), R.ALLOW_SHA256)
check("the start is a window boundary and F3's cut", (W._ts(R.FROM) % 900, R.FROM == F.RETIRED_TIMES["flipside_v2_f3"]), (0, True))
check("the early move reads rows 0 and 1 only (both before the minute-2 entry)", (R.FIRST_ROW, R.ENTRY_ROW), (0, 1))
check("price bands", [R.price_band(p) for p in (0.29, 0.30, 0.399, 0.40)], ["<30", "30-40", "30-40", "40+"])
# underdog YES: its mid 0.40 -> 0.35 fell; 0.30 -> 0.35 rose; flat between; minute 3 (row 2) is never read
fell = win("KXNATGAS15M", T, [0.40, 0.35, 0.90, 0.9])
check("fell (-5c on the underdog's mid, the boundary counts)", R.settings(fell)["early_move"], "fell")
check("a move after the entry (row 2) changes nothing", R.settings(win("KXNATGAS15M", T, [0.40, 0.35, 0.10, 0.1]))["early_move"], "fell")
check("rose / flat", (R.settings(win("KXUSDCAD15M", T, [0.30, 0.35, 0.3]))["early_move"],
      R.settings(win("KXUSDCAD15M", T, [0.34, 0.35, 0.3]))["early_move"]), ("rose", "flat"))
check("underdog NO: the move is on the NO side's mid", R.early_move(win("KXEURUSD15M", T, [0.60, 0.65, 0.6]), "no"), "fell")
check("allowed: NatGas 30-40c, fell, 8 AM", R.allowed(fell), True)
check("NatGas rose is not listed", R.allowed(win("KXNATGAS15M", T, [0.30, 0.35, 0.3])), False)
check("EUR/USD only 07-11 (6 PM CT is out); outside 07-22 never bets",
      (R.allowed(win("KXEURUSD15M", "2026-11-11T00:00:00Z", [0.40, 0.35, 0.3])),
       R.allowed(win("KXNATGAS15M", "2026-11-11T05:00:00Z", [0.40, 0.35, 0.3]))), (False, False))
ws = [fell, win("KXNATGAS15M", "2026-11-10T14:15:00Z", [0.30, 0.35, 0.3])]
state = dict(W.empty(), windows={x["ticker"]: x for x in ws})
rec = R.records(state)
check("the lane counts the allowed window; every bet counts both", (rec["lane"]["all"]["n"], rec["every"]["all"]["n"]), (1, 2))
html = WB.section(state)
row = html.split('data-source="flipf3v2"')[1].split('data-source="flipf4v2"')[0]
check("the row: comparison 'every bet (old F3 on the same 3 markets)'; the in-sample line says what was read",
      ("Every bet (old F3 on the same 3 markets)" in row, "15/27, +39% with the early move read before the entry" in html,
       "17/25, +65% as relayed read the minute-3 quote, after the entry" in html), (True, True, True))

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
