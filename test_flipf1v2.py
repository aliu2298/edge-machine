#!/usr/bin/env python3
"""Rule 3 v2 · Every Positive Setting (flipf1v2.py, flip-f1v2): the frozen allow-list, the settings, the gate, the page."""
import re
import sys

import flipf1v2 as R
import flipside_v2 as F
import sandbox_audit
import swing15 as W
import swing15_build as WB
import sw15cuts as _CUTS
_CUTS.CUTS, _CUTS.RETIRED = {}, ()   # these tests check the rule itself; test_sw15cuts.py covers the Nov 10 cuts

FAILS = []


def check(why, got, want):
    good = got == want
    print(f"  {'ok  ' if good else 'FAIL'} {why}" + ("" if good else f" — got {got!r}, want {want!r}"))
    if not good:
        FAILS.append(why)


COLS = ["m", "yes_bid", "yes_ask", "no_bid", "no_ask", "low", "high", "last", "volume", "open_interest"]


def win(series, open_iso, flip_price=0.75, minute=1, result="no", mids=None):
    """A v1 window where S1's 25c trigger fires on YES at `minute`; the flip buys NO at 1 - yes_bid = flip_price."""
    yb = round(1 - flip_price, 4)
    mids = mids or [0.4] * 5
    minutes = [[i, round(m - 0.005, 4), round(m + 0.005, 4), None, None, None, None, None, 0, 0] for i, m in enumerate(mids)]
    minutes[minute][1], minutes[minute][2] = yb, round(yb + 0.01, 4)
    return dict(ticker=f"{series}-{open_iso}", series=series, group="Crypto", open=open_iso, day=open_iso[:10], us_hours=False,
                fee_multiplier=1.0, result=result, minute_cols=COLS, minutes=minutes,
                s1={"0.25": dict(side="yes", trigger=dict(minute=minute), exits={})}, s2=dict(status="no_quote"), s3=dict(status="no_quote"))


print("the pre-registration")
check("the allow-list is frozen: its fingerprint is the registered one", R.fingerprint(), R.ALLOW_SHA256)
check("8 markets; XRP and WTI can never bet (empty lists)", (len(R.ALLOW), R.G.never(R.ALLOW)),
      (8, {"KXXRP15M": ["time_ct"], "KXWTI15M": ["lead_changes"]}))
check("the start is a window boundary and F1's cut", (W._ts(R.FROM) % 900, R.FROM == F.RETIRED_F1_AT), (0, True))

print("\nthe settings")
check("flip price bands: <73, 73-76 (73c to < 76.5c), 77+", [R.price_band(p) for p in (0.6, 0.729, 0.73, 0.764, 0.765, 0.8)],
      ["<73", "<73", "73-76", "73-76", "77+", "77+"])
check("trigger minute buckets", [R.minute_bucket(m) for m in (0, 1, 2, 3, 4, 5)], ["0-1", "0-1", "2-3", "2-3", "4", None])
T = "2026-11-10T14:00:00Z"                                         # 8 AM CT
w = win("KXETH15M", T, flip_price=0.75, minute=2)
check("a window's four settings (flip NO at 1 - yes_bid; lead changes over rows 0..the trigger minute)", R.settings(w),
      dict(price="73-76", trigger_minute="2-3", lead_changes="0", time_ct="07-11"))

print("\nthe gate")
check("all four in the list: bet (ETH allows everything 07-22)", R.allowed(win("KXETH15M", T)), True)
check("price out (BTC has no <73)", R.allowed(win("KXBTC15M", T, flip_price=0.70)), False)
check("trigger minute out (Gold has no 4)", R.allowed(win("KXGOLD15M", T, minute=4)), False)
check("lead changes out (BTC has no 2+)",
      R.allowed(win("KXBTC15M", T, minute=3, mids=[0.6, 0.4, 0.6, 0.4, 0.4])), False)
check("time out (Platinum has no 07-11)", R.allowed(win("KXPLATINUM15M", T)), False)
check("XRP never bets (no positive time of day); WTI never bets (no positive lead-change setting)",
      (R.allowed(win("KXXRP15M", T, flip_price=0.70, minute=0)), R.allowed(win("KXWTI15M", T, minute=4))), (False, False))
check("any hour outside 07-22 CT is never bet (11 PM and 3 AM CT on ETH)",
      [R.allowed(win("KXETH15M", t)) for t in ("2026-11-11T05:00:00Z", "2026-11-11T09:00:00Z")], [False, False])
check("no F1 trigger: no bet", R.allowed(dict(win("KXETH15M", T), s1={})), False)

print("\nthe record")
ws = [win("KXETH15M", "2026-11-10T14:00:00Z", result="no"),           # bet, won (NO)
      win("KXGOLD15M", "2026-11-10T14:00:00Z", result="yes"),         # bet, lost
      win("KXGOLD15M", "2026-11-10T14:15:00Z", minute=4),             # F1 entered, filtered out (Gold minute 4)
      win("KXETH15M", "2026-11-10T05:00:00Z"),                        # before FROM: not counted
      win("KXSOL15M", "2026-11-10T14:00:00Z")]                        # not one of the 8 markets
state = dict(W.empty(), windows={x["ticker"]: x for x in ws})
rec = R.records(state)
check("the lane: ETH won, Gold lost; the 05:00Z window is before the start",
      (rec["lane"]["all"]["n"], rec["lane"]["all"]["hits"], rec["lane"]["series"]["KXETH15M"]["n"]), (2, 1, 1))
check("every bet = old F1 on the same 8 markets over the same windows (3; not Solana)", rec["every"]["all"]["n"], 3)
led = R.ledger(state)
check("the ledger stores the frozen allow-list, its fingerprint, the never-bet markets and the entries",
      (led["allow"] == R.ALLOW, led["allow_sha256"], led["never"], len(led["entries"])),
      (True, R.ALLOW_SHA256, {"KXXRP15M": ["time_ct"], "KXWTI15M": ["lead_changes"]}, 2))

print("\nthe page")
html = WB.section(state)
flip = html.split('id="flipside_v2"')[1].split('<div class="sw15-lane">')[0]
check("one collapsed row, first in The Flip Side's list; F1 gone as a row",
      (re.findall(r'data-source="(flipf\dv2|flipside_v2_f\d)"', flip), bool(re.search(r'<details class="sp-rule[^"]*"[^>]* open', flip))),
      (["flipf1v2", "flipf2v2", "flipf3v2", "flipf4v2"], False))
row = flip.split('data-source="flipf1v2"')[1].split('data-source="flipf2v2"')[0]
check("inside: the split, the comparison row, the allow-list table (with 'none (never bets)') in Rule details",
      ("1 doing well · 1 not" in row, "Every bet (old F1 on the same 8 markets)" in row,
       "Trigger minute" in row.split("Rule details")[-1], "none (never bets)" in row), (True, True, True, True))
check("the in-sample line, muted, not counted, in the How-kept fold",
      'class="sm mut flipf1v2-in-sample">Nov 9 in-sample, these settings would have gone 122/133, +20% — not counted' in
      flip.split("How the record is kept")[1], True)
arc = html.split('id="sw15-archive"')[1]
check("the archive: F1 retired with its final record, and XRP / WTI as no positive setting",
      ("F1 final:" in arc, "no positive time of day" in arc, "no positive lead-change setting" in arc), (True, True, True))
check("the Sandbox index lists it", "flipf1v2" in [r["lane"] for r in WB.index_rows(state)], True)
check("no dollar sign, no guarded phrase, no inline style", (re.search(r"\$\d", html), sandbox_audit.COPY_RE.findall(html),
      "style=" in html), (None, [], False))

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
