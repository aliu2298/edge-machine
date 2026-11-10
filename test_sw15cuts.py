#!/usr/bin/env python3
"""The 15-Minute market cuts (sw15cuts.py, Olu 2026-11-10): frozen lists; a cut market is skipped from the cut; a market
with no bets stays eligible; retired lanes stop entering; comparisons keep the full set; the page and the archive."""
import re
import sys

import flipf1v2 as R3
import flipf4v2 as R6
import lossreader as LR
import steadyfav as SF
import sw15cuts as C
import swing15 as W
import swing15_build as WB
import swing15v2 as V

FAILS = []


def check(why, got, want):
    good = got == want
    print(f"  {'ok  ' if good else 'FAIL'} {why}" + ("" if good else f" — got {got!r}, want {want!r}"))
    if not good:
        FAILS.append(why)


CUT = W._ts(C.CUT_AT)
check("frozen: the cut lists and retirements as relayed, fingerprinted, one cut time on a window boundary",
      (C.fingerprint() == C.CUTS_SHA256, CUT % 900, C.RETIRED, C.CUTS["lossreader"], C.CUTS["flipf2v2"], C.CUTS["swing15v2_s2"]),
      (True, 0, ("flipf4v2", "steadyfav_a"), ("KXBTC15M", "KXWTI15M"), ("KXBTC15M", "KXHYPE15M", "KXPLATINUM15M"),
       ("KXSOL15M", "KXWTI15M")))
check("is_cut: only listed markets, only from the cut", (C.is_cut("lossreader", "KXBTC15M", CUT - 900),
      C.is_cut("lossreader", "KXBTC15M", CUT), C.is_cut("lossreader", "KXSOL15M", CUT)), (False, True, False))

print("\nthe Loss Reader: a cut market is never a candidate from the cut; learning still watches it")
win = lambda m, t, won: dict(m=m, t=t, quoted=True, won=won, price=0.6, roi=round(won / (0.6 + W.fee(0.6, W.TAKER)) - 1, 4))
T0 = CUT - 6 * 900
ws = [win("KXBTC15M", T0 + i * 900, 1.0) for i in range(12)]           # Bitcoin wins every window, before and after
bets, st = LR.replay(ws)
check("Bitcoin is bet before the cut (from its 5th window), never from the cut on",
      ([(b["t"] - CUT) // 900 for b in bets], ), ([-2, -1],))
check("its observed windows still count after the cut (learning unchanged)", len(st["markets"]["KXBTC15M"].obs), 12)
check("the Now line says cut", "Bitcoin cut" in LR.now_line(st, CUT + 900), True)
ws2 = ws + [win("KXSOL15M", T0 + i * 900, 1.0) for i in range(12)]
b2, _ = LR.replay(ws2)
check("after the cut, Solana (kept) is bet in the windows Bitcoin can no longer take",
      sorted({b["m"] for b in b2 if b["t"] >= CUT}), ["KXSOL15M"])

print("\nan EPS lane: cut markets skipped, a no-bet market eligible, every bet keeps the full set")
COLS = ["m", "yes_bid", "yes_ask", "no_bid", "no_ask", "low", "high", "last", "volume", "open_interest"]


def fw(series, open_iso, result="no"):
    yb = 0.25
    minutes = [[i, 0.395, 0.405, None, None, None, None, None, 0, 0] for i in range(5)]
    minutes[1][1], minutes[1][2] = yb, 0.26
    return dict(ticker=f"{series}-{open_iso}", series=series, group="Crypto", open=open_iso, day=open_iso[:10], us_hours=False,
                fee_multiplier=1.0, result=result, minute_cols=COLS, minutes=minutes,
                s1={"0.25": dict(side="yes", trigger=dict(minute=1), exits={})}, s2=dict(status="no_quote"), s3=dict(status="no_quote"))


after = "2026-11-10T23:15:00Z"                                       # 5:15 PM CT, after the cut
ws3 = [fw("KXETH15M", after), fw("KXPLATINUM15M", after), fw("KXBTC15M", after),
       fw("KXETH15M", "2026-11-10T18:45:00Z")]                          # Ethereum before the cut: its final record
state = dict(W.empty(), windows={x["ticker"]: x for x in ws3})
r = R3.records(state)
check("Rule 3: Ethereum (cut) skipped; Platinum (no bets before) eligible; Bitcoin (kept) counts",
      (sorted(m for m, x in r["lane"]["series"].items() if x), "KXETH15M" in r["lane"]["series"]), (["KXBTC15M", "KXPLATINUM15M"], False))
check("every bet (old F1) keeps the full set, Ethereum included", r["every"]["all"]["n"], 4)
check("Ethereum's final record: the window before the cut only", r["cut"]["series"]["KXETH15M"]["n"], 1)
ws4 = [fw("KXZEC15M", "2026-11-10T18:45:00Z"), fw("KXZEC15M", after)]
for x in ws4:
    x["s3"] = dict(status="filled", side="no", yes_bid=0.29, yes_ask=0.30, price=0.71, won=0.0, roi=-1.0)
st4 = dict(W.empty(), windows={x["ticker"]: x for x in ws4})
check("Rule 6 retired: windows before the cut stay in its final record; nothing after the cut enters",
      (R6.retired(), R6.records(st4)["lane"]["all"]["n"]), (True, 1))
check("Steady Favourites A retired (no live rows); B continues without Gold", (SF.records(dict(W.empty(), windows={}))["steadyfav_a"]["series"],
      "KXGOLD15M" in SF.records(dict(W.empty(), windows={}))["steadyfav_b"]["series"]), ({}, False))
check("Swing v3 S2 keeps Bitcoin only", V.CELLS["swing15v2_s2"], ("KXBTC15M",))

print("\nthe page")
html = WB.section(state)
live = html.split('id="sw15-archive"')[0]
check("retired lanes are gone from the live area and the index",
      ('data-source="flipf4v2"' in live, 'data-source="steadyfav_a"' in live,
       [x["lane"] for x in WB.index_rows(state) if x["lane"] in ("flipf4v2", "steadyfav_a")]), (False, False, []))
check("each cut lane names its cut in Rule details", live.count('class="sm sw15-cuts"'), 7)
check("Rule 4 says it has no market with a positive record yet", "No market with a positive record yet." in live, True)
check("the archive has the one Market cuts group", "<h4>Market cuts (Nov 10)</h4>" in html, True)
check("no inline style, no dollar sign", ("style=" in html, re.search(r"\$\d", html)), (False, None))

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
