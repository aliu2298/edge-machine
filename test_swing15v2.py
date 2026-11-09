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
check("ids and version (sw15-v3 since 2026-11-09 18:00Z)", (tuple(V.CELLS), V.VERSION), (("swing15v2_s1", "swing15v2_s2", "swing15v2_s3"), "sw15-v3"))
check("the sw15-v2 registration is kept as it was: S1 10 markets, S2 9, S3 14", tuple(len(v) for v in V.CELLS_V2.values()), (10, 9, 14))
check("series tickers are KX<NAME>15M", (V.CELLS_V2["swing15v2_s1"][-2:], V.CELLS_V2["swing15v2_s3"][-1]),
      (("KX10YRRATE15M", "KX30YRRATE15M"), "KX2YRRATE15M"))
check("S1 is the 35c band, 3x, held", (V.S1_CELL, V.v1_key("swing15v2_s1")), (("0.35", "3.0", "hold"), ("swing15_s1", "0.35", "3.0", "hold")))
check("S2/S3 read the v1 favourite cells", (V.v1_key("swing15v2_s2"), V.v1_key("swing15v2_s3")), (("swing15_s2",), ("swing15_s3",)))
check("the record starts after the 06:00-12:00Z selection windows", W._ts(V.FROM) >= W._ts("2026-11-09T12:00:00+00:00"), True)

print("\nsw15-v3: the frozen keep list (Olu, 2026-11-09, from the 17:02Z ledgers)")
check("S1 keeps NATGAS, GBPUSD, ZEC, GOLD", V.CELLS_V3["swing15v2_s1"], ("KXNATGAS15M", "KXGBPUSD15M", "KXZEC15M", "KXGOLD15M"))
check("S2 keeps WTI, BTC, SOL", V.CELLS_V3["swing15v2_s2"], ("KXWTI15M", "KXBTC15M", "KXSOL15M"))
check("S3 keeps USDJPY, 2YRRATE, GOLD, ETH, BNB, BTC", V.CELLS_V3["swing15v2_s3"],
      ("KXUSDJPY15M", "KX2YRRATE15M", "KXGOLD15M", "KXETH15M", "KXBNB15M", "KXBTC15M"))
check("every kept market was registered, and removed = registered - kept",
      all(set(V.CELLS_V3[k]) <= set(V.CELLS_V2[k]) and set(V.REMOVED[k]) == set(V.CELLS_V2[k]) - set(V.CELLS_V3[k]) for k in V.CELLS), True)
check("S1 retired 2026-11-09 22:00Z (Olu): no live S1 cell; S2/S3 unchanged; the retired set is the v3 S1 keep list",
      (V.CELLS["swing15v2_s1"], V.CELLS["swing15v2_s2"] == V.CELLS_V3["swing15v2_s2"], V.RETIRED, V.RETIRED_AT),
      ((), True, {"swing15v2_s1": V.CELLS_V3["swing15v2_s1"]}, "2026-11-09T22:00:00+00:00"))
check("the cut", V.REMOVED_AT, "2026-11-09T18:00:00+00:00")

print("\nthe filter over the v1 rows (on the sw15-v2 cells)")
KEEP = V.CELLS
V.CELLS = V.CELLS_V2
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
V.CELLS = KEEP

print("\nsw15-v3 records: survivors keep running, removed cells stop at the cut")
ws.append(row("KXGOLD15M", "2026-11-09T18:15:00Z", 2.0, True, s2=fav(.6, 1.0)))     # GOLD S2 after the cut
state = dict(W.empty(), windows={w["ticker"]: w for w in ws})
rec = V.records(state)
ws.append(row("KXGOLD15M", "2026-11-09T22:00:00Z", 2.0, True))                     # S1 GOLD after the retirement
state = dict(W.empty(), windows={w["ticker"]: w for w in ws})
rec = V.records(state)
ret = V.records(state, retired=True)
check("S1 GOLD's final record runs past the 18:00 cut and stops at retirement (13:00, 13:15, 18:15; not 22:00)",
      (ret["swing15v2_s1"]["series"]["KXGOLD15M"]["n"], rec["swing15v2_s1"]["all"]), (3, None))
check("since the 18:00 cut: the 18:15 window only",
      V.records(state, retired=True, start=V.REMOVED_AT)["swing15v2_s1"]["all"]["n"], 1)
check("S2: GOLD is removed; BTC survives", (set(rec["swing15v2_s2"]["series"]), rec["swing15v2_s2"]["all"]["n"]),
      ({"KXWTI15M", "KXBTC15M", "KXSOL15M"}, 1))
gone = V.records(state, removed=True)
check("S2 GOLD's final record: the two windows before the cut, not the 18:15 one", gone["swing15v2_s2"]["series"]["KXGOLD15M"]["n"], 2)
blob = V.ledger(state)
check("the ledger carries v3 cells, the v2 registration, the cut and the removed records",
      (blob["version"], len(blob["cells"]["swing15v2_s3"]), len(blob["cells_v2"]["swing15v2_s3"]), blob["removed_at"],
       blob["removed_records"]["swing15v2_s2"]["series"]["KXGOLD15M"]["n"]), ("sw15-v3", 6, 14, V.REMOVED_AT, 2))

print("\nthe page")
html = WB.section(state)
check("the v3 block sits above v1", html.index("15-Minute Swing v3") < html.index('data-source="swing15_s2"'), True)
check("the cut line", "sw15-v3 from 2026-11-09 18:00 UTC: negative markets removed after ~4h of results." in html, True)
check("a collapsed Removed fold with readable names", ('<details class="fold sw15-removed"><summary>Removed 2026-11-09 18:00 UTC' in html,
      '<span title="KXGOLD15M">Gold</span>' in html.split("sw15-removed")[1]), (True, True))
check("the line under the header", "Cells picked from one overnight session; fresh record from 2026-11-09 13:00 UTC; "
      "review at 10, decide at 30." in html, True)
check("S1 is gone as a lane in v3 and v1; S2/S3 stay", (re.findall(r'data-source="(swing15v2_s\d)"', html),
      re.findall(r'data-source="(swing15_s\d)"', html)), (["swing15v2_s2", "swing15v2_s3"], ["swing15_s2", "swing15_s3"]))
v3 = html.split('id="swing15v2"')[1].split('id="flipside_v2"')[0]
check("v3's Retired fold: S1 final, since the cut, collapsed, above the Removed fold",
      (bool(re.search(r'<details class="fold sw15-removed"><summary>Retired 2026-11-09 22:00 UTC', v3)),
       "S1 final: 2/3 sells filled" in v3, "since the 18:00 UTC cut, 1/1" in v3, v3.index("Retired 2026") < v3.index("Removed 2026")),
      (True, True, True, True))
check("v1's Retired fold: S1's headline record and the whole grid", ("S1 Swing, final records" in html, "15c · 1.5x · else hold" in html.split("S1 Swing, final records")[1]),
      (True, True))
check("no dollar sign, no guarded phrase", (re.search(r"\$\d", html), sandbox_audit.COPY_RE.findall(html + WB.index_html(state))), (None, []))
check("the Sandbox index: v3 S2/S3 after v1's, no S1 rows", ([r["lane"] for r in WB.index_rows(state)][6:8],
      [r["lane"] for r in WB.index_rows(state) if r["lane"].endswith("_s1")]), (["swing15v2_s2", "swing15v2_s3"], []))

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
