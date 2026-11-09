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
check("ids, version and cells", (tuple(H.CELLS), H.VERSION, tuple(len(v) for v in H.CELLS.values())),
      (("holdtoend_25", "holdtoend_35"), "hte-v1", (3, 6)))
check("tickers", (H.CELLS["holdtoend_25"], H.CELLS["holdtoend_35"][-1]), (("KXUSDCAD15M", "KX30YRRATE15M", "KX5YRRATE15M"), "KXGOLD15M"))
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
rec = H.records(state)
check("25c: USDCAD's two fresh windows, one won", (rec["holdtoend_25"]["all"]["n"], rec["holdtoend_25"]["all"]["hits"]), (2, 1))
check("35c: USDCAD once (BTC is no cell)", (rec["holdtoend_35"]["all"]["n"], rec["holdtoend_35"]["series"]["KXGOLD15M"]), (1, None))

print("\nthe page")
html = WB.section(state)
check("under The Flip Side v2, above v1",
      html.index("The Flip Side v2") < html.index(">Hold to End<") < html.index('data-source="swing15_s1"'), True)
check("the header line", "Cheap side bought at 25c/35c in the first 5 minutes, held to settlement, no sell; cells over +10% "
      "in one overnight session; fresh record from 2026-11-09 14:00 UTC; review at 10, decide at 30." in html, True)
check("two rows", re.findall(r'data-source="(holdtoend_\d+)"', html), ["holdtoend_25", "holdtoend_35"])
check("the Sandbox index lists them after the Flip Side", [r["lane"] for r in WB.index_rows(state)][10:12], list(H.CELLS))
check("no dollar sign, no guarded phrase", (re.search(r"\$\d", html), sandbox_audit.COPY_RE.findall(html + WB.index_html(state))), (None, []))

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
