#!/usr/bin/env python3
"""Rule 2 v2 · Every Positive Setting (s3v2.py, sw15-s3v2): the frozen allow-list, the settings, the gate, the page."""
import re
import sys

import s3v2 as S
import sandbox_audit
import swing15 as W
import swing15_build as WB
import swing15v2 as V
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


COLS = ["m", "yes_bid", "yes_ask", "no_bid", "no_ask", "low", "high", "last", "volume", "open_interest"]


def win(series, open_iso, price=0.85, won=1.0, mids=(0.6,) * 10, status="filled"):
    """A v1 window row: minute quotes with the given YES mids (minutes 1-10), an S3 entry at `price`."""
    minutes = [[i, round(m - 0.005, 4), round(m + 0.005, 4), None, None, None, None, None, 0, 0] for i, m in enumerate(mids)]
    roi = round(won / (price + W.fee(price, W.TAKER)) - 1, 4) if status == "filled" else None
    s3 = dict(status=status, side="yes", price=price, won=won, roi=roi) if status == "filled" else dict(status=status, price=price)
    return dict(ticker=f"{series}-{open_iso}", series=series, group="Crypto", open=open_iso, day=open_iso[:10], us_hours=False,
                fee_multiplier=1.0, minute_cols=COLS, minutes=minutes, s1={}, s2=dict(status="no_quote"), s3=s3)


print("the pre-registration")
check("the allow-list is frozen: its fingerprint is the registered one", S.fingerprint(), S.ALLOW_SHA256)
check("six markets, each with only known buckets",
      (len(S.ALLOW), all(set(a["price"]) <= set(S.PRICE_BANDS) and set(a["lead_changes"]) <= set(S.LEAD_BUCKETS)
                         and set(a["time_ct"]) <= set(S.TIME_BUCKETS) for a in S.ALLOW.values())), (6, True))
check("a one-setting edit changes the fingerprint (so main() refuses it)",
      S.fingerprint(dict(S.ALLOW, KXBTC15M=dict(S.ALLOW["KXBTC15M"], price=["50-80"]))) != S.ALLOW_SHA256, True)
check("the start is a window boundary and S3's cut", (W._ts(S.FROM) % 900, S.FROM == V.RETIRED_S3_AT), (0, True))

print("\nthe settings")
check("price bands", [S.price_band(p) for p in (0.5, 0.79, 0.8, 0.89, 0.9, 0.949, 0.95, 0.99)],
      ["50-80", "50-80", "80-90", "80-90", "90-95", "90-95", "95+", "95+"])
check("open hour in CT (Nov 10 is CST, UTC-6): 13:00Z = 7 AM, 04:00Z = 10 PM, 05:00Z = 11 PM, 12:45Z = 6:45 AM",
      [S.time_bucket(t) for t in ("2026-11-10T13:00:00Z", "2026-11-10T18:00:00Z", "2026-11-10T23:00:00Z",
                                  "2026-11-11T04:00:00Z", "2026-11-11T05:00:00Z", "2026-11-10T12:45:00Z")],
      ["07-11", "12-16", "17-22", "17-22", None, None])
check("lead changes: crossings of 50c by the mid over minutes 1-10; exactly 50c is skipped; minute 11 is too late",
      [S.lead_changes(win("KXBTC15M", "2026-11-10T14:00:00Z", mids=m)) for m in
       ((0.6,) * 10, (0.6, 0.4) + (0.4,) * 8, (0.6, 0.4, 0.6) + (0.6,) * 7, (0.6, 0.5, 0.6) + (0.6,) * 7,
        (0.6,) * 10 + (0.4,))], ["0", "1", "2+", "0", "0"])

print("\nthe gate")
T = "2026-11-10T14:00:00Z"                                          # 8 AM CT
check("all three settings allowed: bet", S.allowed(win("KXBTC15M", T, price=0.97)), True)
check("one setting out (Bitcoin 80-90c is not listed): no bet", S.allowed(win("KXBTC15M", T, price=0.85)), False)
check("lead changes out (BNB only 0)", S.allowed(win("KXBNB15M", T, price=0.85, mids=(0.6, 0.4) + (0.4,) * 8)), False)
check("hour out (USD/JPY only 07-11; 6 PM CT)", S.allowed(win("KXUSDJPY15M", "2026-11-11T00:00:00Z", price=0.97)), False)
check("any hour outside 07-22 CT is never bet, whatever the list (11 PM, 3 AM CT)",
      [S.allowed(win("KXBTC15M", t, price=0.97)) for t in ("2026-11-11T05:00:00Z", "2026-11-11T09:00:00Z")], [False, False])
check("a market not on the list is never bet", S.allowed(win("KXSOL15M", T, price=0.97)), False)
check("no S3 quote: no bet", S.allowed(win("KXBTC15M", T, price=None, status="no_quote")), False)

print("\nthe record")
ws = [win("KXBTC15M", "2026-11-10T14:00:00Z", price=0.97, won=1.0),       # bet, won
      win("KXBTC15M", "2026-11-10T14:15:00Z", price=0.85, won=1.0),       # filtered out (80-90c)
      win("KXGOLD15M", "2026-11-10T14:00:00Z", price=0.70, won=0.0),      # bet, lost
      win("KXBTC15M", "2026-11-10T04:45:00Z", price=0.97, won=1.0),       # before FROM: not counted
      win("KXSOL15M", "2026-11-10T14:00:00Z", price=0.97, won=1.0)]       # not one of the 6 markets
state = dict(W.empty(), windows={w["ticker"]: w for w in ws})
rec = S.records(state)
check("the lane: 2 bets (Bitcoin won, Gold lost); the 04:45Z window is before the start",
      (rec["lane"]["all"]["n"], rec["lane"]["all"]["hits"], rec["lane"]["series"]["KXBTC15M"]["n"]), (2, 1, 1))
check("every bet = the old S3 on the same 6 markets over the same windows (3; not Solana)", rec["every"]["all"]["n"], 3)
led = S.ledger(state)
check("the ledger stores the frozen allow-list and its fingerprint, and the entries",
      (led["allow"] == S.ALLOW, led["allow_sha256"], len(led["entries"]), led["entries"][0]["settings"]),
      (True, S.ALLOW_SHA256, 2, {"price": "95+", "lead_changes": "0", "time_ct": "07-11"}))

print("\nthe page")
html = WB.section(state)
blk = html.split('id="s3v2"')[1].split('<div class="sw15-lane">')[0]
check("one collapsed row, second after the Loss Reader", (len(re.findall(r'data-source="s3v2"', blk)),
      bool(re.search(r'<details class="sp-rule[^"]*"[^>]* open', blk)),
      html.index('id="lossreader"') < html.index('id="s3v2"') < html.index('id="steadyfav"')), (1, False, True))
check("one intro line", re.findall(r'sw15-intro">(.*?)</p>', blk),
      [f"Paper · fresh record from {WB._start(S.FROM)} · review 30, decide 100 bets"])
check("the split, the comparison row and the allow-list table in Rule details",
      ("1 doing well · 1 not" in blk, "Every bet (old S3 on the same 6 markets)" in blk,
       "Lead changes before the entry" in blk.split("Rule details")[-1]), (True, True, True))
check("the in-sample line, muted, not counted", 'class="sm mut s3v2-in-sample">Nov 9 in-sample, these settings would have gone '
      '125/131, +14.1% — not counted' in blk, True)
check("Swing v3 S3 is gone as a lane and sits in the archive as Retired", (re.findall(r'data-source="swing15v2_s3"', html),
      "S3 final:" in html.split('id="sw15-archive"')[1]), ([], True))
check("the Sandbox index lists it second", [r["lane"] for r in WB.index_rows(state)][:2], ["lossreader", "s3v2"])
check("no dollar sign, no guarded phrase, no inline style", (re.search(r"\$\d", html), sandbox_audit.COPY_RE.findall(html),
      "style=" in html), (None, [], False))

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
