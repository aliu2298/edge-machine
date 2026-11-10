#!/usr/bin/env python3
"""Hold to End (holdtoend.py, hte-v1): frozen cells, v1's S1 entry held to settlement, fresh record, the page."""
import re
import sys

import holdtoend as H
import sandbox_audit
import swing15 as W
import swing15_build as WB

FAILS = []


def check(why, got, want):
    good = got == want
    print(f"  {'ok  ' if good else 'FAIL'} {why}" + ("" if good else f" — got {got!r}, want {want!r}"))
    if not good:
        FAILS.append(why)


def win(series, open_iso, s1):
    return dict(ticker=f"{series}-{open_iso}", series=series, group="Financials", open=open_iso, day=open_iso[:10],
                us_hours=False, fee_multiplier=1.0, s1=s1, s2=dict(status="no_quote"), s3=dict(status="no_quote"))


E = lambda side, won: dict(side=side, won=won, exits={"3.0": dict(filled=True, roi_hold=1.0, roi_bid=1.0)})

print("the pre-registration")
check("ids, version and the hte-v1 registration as it was", (tuple(H.CELLS), H.VERSION, tuple(len(v) for v in H.CELLS_V1.values())),
      (("holdtoend_25", "holdtoend_35"), "hte-v3", (3, 6)))
check("tickers", (H.CELLS_V1["holdtoend_25"], H.CELLS_V1["holdtoend_35"][-1]), (("KXUSDCAD15M", "KX30YRRATE15M", "KX5YRRATE15M"), "KXGOLD15M"))
check("hte-v2 keep list (Olu, 2026-11-09): the 25c row removed entirely, 35c on GBPUSD only",
      (H.CELLS_V2["holdtoend_25"], H.CELLS_V2["holdtoend_35"], H.REMOVED["holdtoend_25"]), ((), ("KXGBPUSD15M",), H.CELLS_V1["holdtoend_25"]))
check("hte-v3 (Olu, 2026-11-09): one cell, 35c on USDCAD; the 25c USDCAD cell stays removed",
      (H.CELLS, "KXUSDCAD15M" in H.REMOVED["holdtoend_25"]), ({"holdtoend_25": (), "holdtoend_35": ("KXUSDCAD15M",)}, True))
check("hte-v3's fresh record starts after hte-v2 retires, on a window boundary",
      (W._ts(H.FROM_V3) > W._ts(H.RETIRED_AT) > W._ts(H.REMOVED_AT), W._ts(H.FROM_V3) % 900), (True, 0))
check("the record starts after the selection windows", W._ts(H.FROM) >= W._ts("2026-11-09T12:00:00+00:00"), True)

print("\nheld to settlement, whatever the sell did")
T = "2026-11-09T15:00:00Z"
w = win("KXUSDCAD15M", T, {"0.15": None, "0.25": E("no", 1.0), "0.35": E("no", 1.0)})
x = H.entry(w, "holdtoend_25")
check("25c entry won at settlement: 1 / (25c + taker fee) - 1, even though v1's 3x sell filled",
      (x["side"], x["price"], x["roi"]), ("no", .25, round(1 / (.25 + W.fee(.25, W.TAKER)) - 1, 4)))
check("a loss is -100%", H.entry(win("KXGOLD15M", T, {"0.35": E("yes", 0.0)}), "holdtoend_35")["roi"], -1.0)
check("no v1 entry at the band: nothing", H.entry(win("KXGOLD15M", T, {"0.35": None}), "holdtoend_35"), None)
check("no result yet: a skip", H.entry(win("KXGOLD15M", T, {"0.35": E("yes", None)}), "holdtoend_35")["skip"], "no_result")

print("\nthe record")
ws = [w, win("KXUSDCAD15M", "2026-11-09T15:15:00Z", {"0.25": E("yes", 0.0), "0.35": None}),
      win("KXUSDCAD15M", "2026-11-09T11:00:00Z", {"0.25": E("yes", 1.0), "0.35": None}),   # selection window
      win("KXBTC15M", T, {"0.25": E("yes", 1.0), "0.35": E("yes", 1.0)})]                     # not a cell
state = dict(W.empty(), windows={v["ticker"]: v for v in ws})
KEEP, KEEP_FROM = H.CELLS, H.FROM_V3
H.CELLS, H.FROM_V3 = H.CELLS_V1, H.FROM                         # the filter, on the registered hte-v1 cells
rec = H.records(state)
check("25c: USDCAD's two fresh windows, one won", (rec["holdtoend_25"]["all"]["n"], rec["holdtoend_25"]["all"]["hits"]), (2, 1))
check("35c: USDCAD once (BTC is no cell)", (rec["holdtoend_35"]["all"]["n"], rec["holdtoend_35"]["series"]["KXGOLD15M"]), (1, None))
H.CELLS, H.FROM_V3 = KEEP, KEEP_FROM
gone = H.records(state, removed=True)
check("hte-v2: USDCAD's 25c and 35c records are final in the removed set", (gone["holdtoend_25"]["all"]["n"], gone["holdtoend_35"]["all"]["n"]), (2, 1))

print("\nhte-v2 retired, hte-v3 fresh")
G = "KXGBPUSD15M"
ws2 = ws + [win(G, "2026-11-09T21:45:00Z", {"0.35": E("yes", 1.0)}),        # hte-v2, counted in its final record
            win(G, "2026-11-09T22:00:00Z", {"0.35": E("yes", 1.0)}),        # after retirement: never counted
            win("KXUSDCAD15M", "2026-11-09T22:45:00Z", {"0.35": E("no", 1.0)}),   # before FROM_V3: not counted
            win("KXUSDCAD15M", "2026-11-09T23:00:00Z", {"0.35": E("no", 0.0)})]   # hte-v3's first window
state = dict(W.empty(), windows={v["ticker"]: v for v in ws2})
ret = H.records(state, retired=True)["holdtoend_35"]
check("hte-v2's final record: GBPUSD windows before RETIRED_AT only", (ret["all"]["n"], ret["series"][G]["hits"]), (1, 1))
live = H.records(state)["holdtoend_35"]
check("hte-v3 counts from FROM_V3 only, USDCAD only (the 15:00Z USDCAD 35c win is not carried over)",
      (live["all"]["n"], live["all"]["hits"], list(live["series"])), (1, 0, ["KXUSDCAD15M"]))
led = H.ledger(state)
check("the ledger: version, fresh from, retired record", (led["version"], led["from"], led["retired_records"]["holdtoend_35"]["all"]["n"]),
      ("hte-v3", H.FROM_V3, 1))

print("\nthe page")
html = WB.section(state)
blk = html.split('id="holdtoend"')[1].split('id="leadswap"')[0]
arc = html.split('id="sw15-archive"')[1].split("<h4>15-Minute Swing v1</h4>")[0].split("<h4>Hold to End</h4>")[1]
check("under The Flip Side v3 and Steady Favourites, above the Lead Swap Board and v1",
      html.index('id="flipside_v2"') < html.index('id="steadyfav"') < html.index('id="holdtoend"') < html.index('id="leadswap"')
      < html.index('data-source="swing15_s2"'), True)
check("the section copy (times in CT)", "Hold to End v3 · USD/CAD at 35c · fresh record from Nov 9, 5:00 PM CT · "
      "review at 10, decide at 30." in html, True)
check("one live row (35c), the 25c row only in the archive's Removed fold", (re.findall(r'data-source="(holdtoend_\d+)"', html),
      "Hold to End · 25c" in arc.split("Removed Nov")[1], "sw15-removed" in blk), (["holdtoend_35"], True, False))
check("the earlier USDCAD 35c result: a muted not-counted line",
      bool(re.search(r'class="sm mut hte-earlier">Earlier result, not counted: USD/CAD 35c went 1/1', blk)), True)
check("hte-v2 in the archive's Retired fold with its final record, above the Removed fold",
      ("Retired Nov 9, 4:00 PM CT" in arc, "hte-v2 final (decide at 30): 1/1 against 0.3 priced" in arc,
       arc.index("Retired Nov") < arc.index("Removed Nov")), (True, True, True))
check("the live cell uses the doing-well split, open under its row", ("0 doing well · 1 not" in blk,
      blk.index('data-source="holdtoend_35"') < blk.index('class="sw15-split"')), (True, True))
check("the Sandbox index row is hte-v3", [(r["lane"], r["label"]) for r in WB.index_rows(state) if r["lane"].startswith("holdtoend")],
      [("holdtoend_35", "Hold to End v3 · 35c")])
check("no dollar sign, no guarded phrase", (re.search(r"\$\d", html), sandbox_audit.COPY_RE.findall(html + WB.index_html(state))), (None, []))

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
