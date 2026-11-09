#!/usr/bin/env python3
"""15-Minute Swing v2 (swing15v2.py, sw15-v2): the frozen cells, the fresh record, the page block. No network."""
import copy
import re
import sys

import sandbox_audit
import swing15 as W
import swing15_build as WB
import swing15v2 as V

FAILS = []


def check(why, got, want):
    good = got == want
    print(f"  {'ok  ' if good else 'FAIL'} {why}" + ("" if good else f" — got {got!r}, want {want!r}"))
    if not good:
        FAILS.append(why)


def row(series, open_iso, s1_roi, s1_filled, s2=None, s3=None, s1_band="0.35"):
    ex = {m: dict(filled=False, roi_hold=-1.0, roi_bid=-1.0) for m in ("1.5", "2.0", "3.0")}
    ex["3.0"] = dict(filled=s1_filled, roi_hold=s1_roi, roi_bid=s1_roi)
    s1 = {b: None for b in ("0.15", "0.25", "0.35")}
    s1[s1_band] = dict(side="yes", won=1.0, exits=ex)
    return dict(ticker=f"{series}-{open_iso}", series=series, group="Crypto", open=open_iso, day=open_iso[:10],
                us_hours=False, s1=s1, s2=s2 or dict(status="no_quote"), s3=s3 or dict(status="no_quote"))


print("the pre-registration")
check("ids and version", (tuple(V.CELLS), V.VERSION), (("swing15v2_s1", "swing15v2_s2", "swing15v2_s3"), "sw15-v2"))
check("cell counts: S1 10 markets, S2 9, S3 14", tuple(len(v) for v in V.CELLS.values()), (10, 9, 14))
check("series tickers are KX<NAME>15M", (V.CELLS["swing15v2_s1"][-2:], V.CELLS["swing15v2_s3"][-1]),
      (("KX10YRRATE15M", "KX30YRRATE15M"), "KX2YRRATE15M"))
check("S1 is the 35c band, 3x, held", (V.S1_CELL, V.v1_key("swing15v2_s1")), (("0.35", "3.0", "hold"), ("swing15_s1", "0.35", "3.0", "hold")))
check("S2/S3 read the v1 favourite cells", (V.v1_key("swing15v2_s2"), V.v1_key("swing15v2_s3")), (("swing15_s2",), ("swing15_s3",)))
check("the record starts after the 06:00-12:00Z selection windows", W._ts(V.FROM) >= W._ts("2026-11-09T12:00:00+00:00"), True)

print("\nthe filter over the v1 rows")
fav = lambda roi, won, price=.6: dict(status="filled", side="yes", price=price, won=won, roi=roi)
ws = [row("KXGOLD15M", "2026-11-09T13:00:00Z", 2.0, True, s2=fav(.6, 1.0), s3=fav(.6, 1.0)),
      row("KXGOLD15M", "2026-11-09T13:15:00Z", -1.0, False, s2=fav(-1.0, 0.0)),
      row("KXGOLD15M", "2026-11-09T11:45:00Z", 2.0, True, s2=fav(.6, 1.0)),       # in the selection session: never counts
      row("KXBTC15M", "2026-11-09T13:00:00Z", 2.0, True, s2=fav(.6, 1.0), s3=fav(.6, 1.0)),  # BTC is not an S1 cell
      row("KXDOGE15M", "2026-11-09T13:00:00Z", 2.0, True, s2=fav(.6, 1.0), s3=fav(.6, 1.0))]  # DOGE is in no cell
state = dict(W.empty(), windows={w["ticker"]: w for w in ws})
rec = V.records(state)
check("S1: GOLD's two fresh windows only (not BTC, DOGE or the 11:45Z window)",
      (rec["swing15v2_s1"]["all"]["n"], rec["swing15v2_s1"]["all"]["hits"], rec["swing15v2_s1"]["series"]["KXGOLD15M"]["n"]),
      (2, 1, 2))
check("S1's ROI is the mean of the 3x hold ROIs", rec["swing15v2_s1"]["all"]["mean_roi"], 0.5)
check("S2: GOLD 2 + BTC 1", (rec["swing15v2_s2"]["all"]["n"], rec["swing15v2_s2"]["series"]["KXBTC15M"]["n"]), (3, 1))
check("S3: GOLD 1 + BTC 1; a market with no windows is None", (rec["swing15v2_s3"]["all"]["n"], rec["swing15v2_s3"]["series"]["KXETH15M"]), (2, None))
before = copy.deepcopy(state)
check("v1's own record is untouched: v1 S2 counts every window", W.cells(before)[("swing15_s2",)]["n"], 5)
blob = V.ledger(state)
check("the ledger carries the frozen cells and the start", (blob["version"], blob["from"], len(blob["cells"]["swing15v2_s3"])),
      ("sw15-v2", V.FROM, 14))

print("\nthe page")
html = WB.section(state)
check("the v2 block sits above v1", html.index("15-Minute Swing v2") < html.index('data-source="swing15_s1"'), True)
check("the line under the header", "Cells picked from one overnight session; fresh record from 2026-11-09 13:00 UTC; "
      "review at 10, decide at 30." in html, True)
check("three v2 rows", re.findall(r'data-source="(swing15v2_s\d)"', html), ["swing15v2_s1", "swing15v2_s2", "swing15v2_s3"])
check("v1's three rows are still there", re.findall(r'data-source="(swing15_s\d)"', html), ["swing15_s1", "swing15_s2", "swing15_s3"])
check("no dollar sign, no guarded phrase", (re.search(r"\$\d", html), sandbox_audit.COPY_RE.findall(html + WB.index_html(state))), (None, []))
check("the Sandbox index lists v2 too", [r["lane"] for r in WB.index_rows(state)][3:6], list(V.CELLS))

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
