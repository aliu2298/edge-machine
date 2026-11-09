#!/usr/bin/env python3
"""Lead Swap Board (leadswap.py, lsb-v1): the swap measure, the ranking, frozen picks, routing, the page. No network."""
import datetime as dt
import re
import sys

import leadswap as L
import sandbox_audit
import swing15 as W
import swing15_build as WB

FAILS = []


def check(why, got, want):
    good = got == want
    print(f"  {'ok  ' if good else 'FAIL'} {why}" + ("" if good else f" — got {got!r}, want {want!r}"))
    if not good:
        FAILS.append(why)


def iso(ts):
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def win(series, o, mids, result="yes", group="Crypto", s1won=1.0, s3=None):
    rows = [[m, round(x - .01, 4), round(x + .01, 4), None, None, round(x - .05, 4), round(x + .05, 4), x, 10.0, 5.0]
            for m, x in enumerate(mids)]
    return dict(ticker=f"{series}-{o}", series=series, group=group, open=iso(o), close=iso(o + 900),
                day=iso(o)[:10], us_hours=False, result=result, schema=2, fee_multiplier=1.0,
                minute_cols=list(W.MINUTE_COLS), minutes=rows,
                s1={"0.15": None, "0.25": None, "0.35": dict(side="yes", won=s1won, exits={})},
                s2=dict(status="no_quote"), s3=s3 or dict(status="filled", side="yes", price=.8, won=1.0, roi=.2))


print("the swap measure")
m = L.metrics(win("KXBTC15M", 0, [.6, .4, .5, .45, .7] + [.8] * 10))
check("60 -> 40 is a swap at minute 1; 50c holds the side; 45 -> 70 swaps at minute 4", (m["swaps"], m["minutes"]), (2, [1, 4]))
check("each swing: the low to high of the two minutes' traded range", m["sizes"], [30.0, 35.0])
check("the minute 0-9 mid range in cents", m["range09"], 40.0)
check("the minute-14 favourite (80c YES) won on YES", m["fav14_won"], True)
e = win("KXBTC15M", 0, [.6] * 15)
e["minutes"][3][1:3] = [0, 1]
check("an empty book (0/100c) is skipped, not a swap", L.metrics(e)["quoted"], 14)
check("blocks", [L.block(s, g) for s, g in (("KXBTC15M", "Crypto"), ("KXGOLD15M", "Commodities"), ("KXWTI15M", "Commodities"),
                                            ("KX10YRRATE15M", "Financials"), ("KXUSDJPY15M", "Financials"), ("KXINX15M", "Financials"))],
      ["crypto", "metals", "energy", "yields", "fx", "indices"])
check("a bare ticker resolves like its window (the board once sent every crypto series to indices)",
      [L.block(t) for t in ("KXBTC15M", "KXSOL15M", "KXZEC15M", "KXINX15M", "KXGOLD15M", "KXUSDJPY15M", "KX2YRRATE15M")],
      ["crypto", "crypto", "crypto", "indices", "metals", "fx", "yields"])
check("families fold metals and energy into commodities", (L.family("metals"), L.family("energy"), L.family("fx")),
      ("commodities", "commodities", "fx"))

print("\nthe board, the picks, the routing")
H = int(W._ts(L.FROM))
SW = [.6, .4, .6, .4, .6, .4] + [.6] * 9                       # 6 swaps a window (minutes 1-6)
CALM = [.7] * 15
series = {"KXA15M": SW, "KXB15M": SW, "KXC15M": SW, "KXD15M": CALM, "KXE15M": CALM, "KXF15M": CALM, "KXG15M": CALM}
ws = {}
for s, mids in series.items():
    for k in range(8):                                          # the 8 windows closing in the 2 hours before H
        o = H - 7200 - 900 + 900 * (k + 1)
        ws[f"{s}{o}"] = win(s, o, mids)
    for k in range(4):                                          # the hour H itself
        o = H + 900 * k
        ws[f"{s}{o}"] = win(s, o, mids, s1won=1.0 if s in ("KXA15M", "KXB15M") else 0.0)
ws["lead"] = dict(win("KXCRYPTOLEAD15M", H, SW), series="KXCRYPTOLEAD15M")
state = dict(W.empty(), windows=ws)
rows = L.table(state)
check("the which-coin-leads series is left out", "KXCRYPTOLEAD15M" in {r[0] for r in rows}, False)
r2 = L.rank(rows, H, 2, 4)
check("ranked by swaps a window over the 8 windows closed by H", [(r[0], r[1], r[2]) for r in r2[:3]],
      [("KXA15M", 6.0, 8), ("KXB15M", 6.0, 8), ("KXC15M", 6.0, 8)])
p = L.pick(rows, H)
check("top 3 and bottom 3 (ties: range, then ticker), never both", (p["top"], p["bottom"]),
      (["KXA15M", "KXB15M", "KXC15M"], ["KXG15M", "KXF15M", "KXE15M"]))
led = L.update(state, L.empty(), now=dt.datetime.fromtimestamp(H + 3600 + 300, dt.timezone.utc))
hk = dt.datetime.fromtimestamp(H, dt.timezone.utc).isoformat()
check("the picks for H are frozen in the ledger", led["picks"][hk]["top"], ["KXA15M", "KXB15M", "KXC15M"])
led["picks"][hk]["top"] = ["KXD15M"]
L.update(state, led, now=dt.datetime.fromtimestamp(H + 3600 + 400, dt.timezone.utc))
check("a later run never moves frozen picks", led["picks"][hk]["top"], ["KXD15M"])
led = L.update(state, L.empty(), now=dt.datetime.fromtimestamp(H + 3600 + 300, dt.timezone.utc))
rt = led["routing"]
c = .35 + W.fee(.35, W.TAKER)
check("swing: S1 35c held on the top 3, 12 windows; A and B won, C lost",
      (rt["leadswap_swing"]["n"], rt["leadswap_swing"]["hits"], round(rt["leadswap_swing"]["mean_roi"], 4)),
      (12, 8, round((8 * (1 / c - 1) - 4) / 12, 4)))
check("favourite: S3 on the bottom 3", (rt["leadswap_fav"]["n"], sorted(rt["leadswap_fav"]["series"])), (12, ["KXE15M", "KXF15M", "KXG15M"]))
check("controls take the opposite end", (sorted(rt["leadswap_swing_ctrl"]["series"]), sorted(rt["leadswap_fav_ctrl"]["series"])),
      (["KXE15M", "KXF15M", "KXG15M"], ["KXA15M", "KXB15M", "KXC15M"]))
check("one crypto block a window is one cluster: 4 windows -> 4 clusters", rt["leadswap_swing"]["clusters"], 4)
check("windows before FROM never route", L.routing(rows, {iso(H - 3600).replace("Z", "+00:00"): dict(top=["KXA15M"], bottom=[])})["leadswap_swing"], None)
pr = led["persistence"]
check("the board's block map comes from the windows' own groups: crypto, not indices", set(led["board"]["blocks"].values()), {"crypto"})
check("within-block stay: one crypto block of 7, k = 3, the swappy three stay (chance 3/7)",
      (pr["within"]["crypto"]["stay"], pr["within"]["crypto"]["chance"], pr["within_all"]["stay"]), (1.0, round(3 / 7, 3), 1.0))
check("each routed entry records whether it came before the picks froze (fixtures have no trigger time: None)",
      rt["leadswap_swing"]["before_freeze"], 0)
check("persistence: the swappy three stay on top (100% v chance 3/7)", (pr["top"], pr["chance"]), (1.0, round(3 / 7, 3)))
b = led["board"]
check("the minute histogram: 3 swappy series x 12 windows, one swap at each of minutes 1-6", b["minutes"][:8], [0] + [36] * 6 + [0])

print("\nthe page")
import json, os, tempfile
tmp = tempfile.mkdtemp()
L.PATH = os.path.join(tmp, "leadswap_ledger.json")
with open(L.PATH, "w") as f:
    json.dump(led, f)
html = WB.section(state)
order = [html.index(x) for x in ("Lead Swap Board", "15-Minute Swing v2", "The Flip Side v2", ">Hold to End<",
                                  "15-Minute Swing v1 · every market")]
check("the order: Lead Swap Board, Swing v2, Flip Side v2, Hold to End, v1", order == sorted(order), True)
check("v1 is collapsed by default", bool(re.search(r'<details class="fold sw15-v1"><summary>', html)), True)
check("the page notes a live version could act only from :05", "could only act from :05" in html, True)
check("the within-block persistence table", "Stayed top" in html, True)
import swing15 as W_
real = W_.load()
check("every series in the current shards has a display name (never blank, never the raw ticker)",
      [t for t in sorted({w["series"] for w in real["windows"].values()}) if not WB.name(t) or WB.name(t) == t], [])
check("names: the map, then the KX/15M fallback", (WB.name("KXAUDUSD15M"), WB.name("KXNEWCOIN15M"), WB.name("")),
      ("AUD/USD (Australian Dollar)", "NEWCOIN", "?"))
check("market cells show the name with the ticker in a hover title",
      WB.mkt("KXBTC15M"), '<span title="KXBTC15M">Bitcoin</span>')
check("no raw series ticker as visible text in the section", re.findall(r">(KX[A-Z0-9]+15M)<", html), [])
check("four routing rows", re.findall(r'data-source="(leadswap_[a-z_]+)"', html), list(L.STRATS))
check("the board shows the most swaps and the most stable", ("Most swaps, last 2 hours" in html, "Most stable, last 24 hours" in html), (True, True))
check("persistence, minute histogram and the hour-of-day heatmap folds",
      all(x in html for x in ("Persistence:", "When in the window", "by hour of day (ET)")), True)
check("the Sandbox index lists the routing rows last", [r["lane"] for r in WB.index_rows(state)][-4:], list(L.STRATS))
check("no dollar sign, no guarded phrase", (re.search(r"\$\d", html), sandbox_audit.COPY_RE.findall(html + WB.index_html(state))), (None, []))

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
