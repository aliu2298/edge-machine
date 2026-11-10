#!/usr/bin/env python3
"""Rule 4 v2 · Every Positive Setting (flipf2v2.py, flip-f2v2): the frozen allow-list, the settings, the gate, the page."""
import re
import sys

import flipf2v2 as R
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


def win(series, open_iso, flip_price=0.70, minute=1, result="no", mids=None):
    """S1's 35c trigger fires on YES at `minute`; the flip buys NO at 1 - yes_bid = flip_price."""
    yb = round(1 - flip_price, 4)
    mids = mids or [0.4] * 5
    minutes = [[i, round(m - 0.005, 4), round(m + 0.005, 4), None, None, None, None, None, 0, 0] for i, m in enumerate(mids)]
    minutes[minute][1], minutes[minute][2] = yb, round(yb + 0.01, 4)
    return dict(ticker=f"{series}-{open_iso}", series=series, group="Crypto", open=open_iso, day=open_iso[:10], us_hours=False,
                fee_multiplier=1.0, result=result, minute_cols=COLS, minutes=minutes,
                s1={"0.35": dict(side="yes", trigger=dict(minute=minute), exits={})}, s2=dict(status="no_quote"),
                s3=dict(status="no_quote"))


T = "2026-11-10T14:00:00Z"                                         # 8 AM CT
check("frozen: the fingerprint is the registered one", R.fingerprint(), R.ALLOW_SHA256)
check("Brent never bets: every list empty", R.G.never(R.ALLOW), {"KXBRENT15M": ["price", "trigger_minute", "lead_changes", "time_ct"]})
check("the start is a window boundary and F2's cut", (W._ts(R.FROM) % 900, R.FROM == F.RETIRED_TIMES["flipside_v2_f2"]), (0, True))
check("price bands: <63 (< 62.5c), 63-67 (to < 67.5c), 68+", [R.price_band(p) for p in (0.6, 0.624, 0.625, 0.674, 0.675)],
      ["<63", "<63", "63-67", "63-67", "68+"])
check("settings read the 35c trigger", R.settings(win("KXBTC15M", T, flip_price=0.65, minute=1)),
      dict(price="63-67", trigger_minute="0-1", lead_changes="0", time_ct="07-11"))
check("allowed: BTC 63-67, minute 0-1, 0 changes, 8 AM", R.allowed(win("KXBTC15M", T, flip_price=0.65)), True)
check("BTC trigger minute 2-3 is not listed", R.allowed(win("KXBTC15M", T, flip_price=0.65, minute=2)), False)
check("WTI needs exactly 1 lead change", (R.allowed(win("KXWTI15M", T, flip_price=0.70, minute=2)),
      R.allowed(win("KXWTI15M", T, flip_price=0.70, minute=2, mids=[0.6, 0.4, 0.4, 0.4, 0.4]))), (False, True))
check("Brent never bets", R.allowed(win("KXBRENT15M", T, flip_price=0.70)), False)
check("outside 07-22 CT never bets (11 PM CT)", R.allowed(win("KXBTC15M", "2026-11-11T05:00:00Z", flip_price=0.65)), False)
ws = [win("KXBTC15M", T, flip_price=0.65, result="no"), win("KXBRENT15M", T, flip_price=0.70, result="no"),
      win("KXBTC15M", "2026-11-10T05:00:00Z", flip_price=0.65)]
state = dict(W.empty(), windows={x["ticker"]: x for x in ws})
rec = R.records(state)
check("the lane counts BTC only; every bet counts BTC and Brent; before FROM never counts",
      (rec["lane"]["all"]["n"], rec["every"]["all"]["n"]), (1, 2))
html = WB.section(state)
row = html.split('data-source="flipf2v2"')[1].split('data-source="flipf3v2"')[0]
check("the row: collapsed, comparison 'every bet (old F2 on the same 6 markets)', allow-list in Rule details",
      ("Every bet (old F2 on the same 6 markets)" in row, "none (never bets)" in row.split("Rule details")[-1]), (True, True))
check("the in-sample line and Brent as no positive setting in the archive",
      ("Nov 9 in-sample, these settings would have gone 88/109, +15% — not counted" in html,
       "Brent Crude Oil</span> (no positive setting at all)" in html.split('id="sw15-archive"')[1]), (True, True))

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
