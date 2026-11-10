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
order = [html.index(x) for x in ('id="leadswap"', 'id="swing15v2"', 'id="flipside_v2"', 'id="holdtoend"', 'id="sw15-v1"',
                                  'id="sw15-archive"')]
check("the order: Lead Swap Board, Swing v3, Flip Side v3, Hold to End v3, v1, archive", order == sorted(order), True)
check("v1 and the archive are collapsed by default", (bool(re.search(r'<details class="fold sw15-v1" id="sw15-v1"><summary>', html)),
      bool(re.search(r'<details class="fold sw15-archive" id="sw15-archive"><summary>', html))), (True, True))
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
check("two routing rows; the controls are a muted vs-control figure, not rows",
      (re.findall(r'data-source="(leadswap_[a-z_]+)"', html), html.split('id="leadswap"')[1].count('title="Control: ')),
      (["leadswap_swing", "leadswap_fav"], 2))
check("the research folds sit under one collapsed 'How the board ranks markets'",
      all(html.index('class="fold sw15-ranks"') < html.index(x) for x in ("Board · last 2 hours", "Persistence:",
                                                                          "When in the window", "by hour of day (CT)")), True)
check("the board shows the most swaps and the most stable", ("Most swaps, last 2 hours" in html, "Most stable, last 24 hours" in html), (True, True))
check("persistence, minute histogram and the hour-of-day heatmap folds",
      all(x in html for x in ("Persistence:", "When in the window", "by hour of day (CT)")), True)
check("the Sandbox index lists the routing rows last", [r["lane"] for r in WB.index_rows(state)][-4:], list(L.STRATS))
check("no dollar sign, no guarded phrase", (re.search(r"\$\d", html), sandbox_audit.COPY_RE.findall(html + WB.index_html(state))), (None, []))

print("\nthe doing-well / not-doing-well groups")
rt_ = {"leadswap_swing": {"series": {"KXA15M": [12, 7, 1.5], "KXB15M": [4, 0, -4.0], "KXC15M": [6, 3, 0.0], "KXD15M": [8, 4, 0.4]}},
       "leadswap_swing_ctrl": {"series": {"KXA15M": [3, 1, -0.5]}},
       "leadswap_fav": {"series": {"KXC15M": [5, 4, 0.2]}}, "leadswap_fav_ctrl": None}
pk_ = {"h1": {"top": ["KXA15M", "KXD15M"], "bottom": ["KXC15M"]}, "h2": {"top": ["KXA15M", "KXC15M"], "bottom": ["KXE15M"]}}
g = WB.ls_groups(rt_, pk_, ranked=["KXA15M", "KXF15M"])
good, bad, none = g["leadswap_swing"]
check("doing well = return > 0, sorted by bets", [r[0] for r in good], ["KXA15M", "KXD15M"])
check("not doing well = return <= 0 (a flat 0 is not doing well), by bets", [r[0] for r in bad], ["KXC15M", "KXB15M"])
check("a market picked both ways sits under each trade it traded in",
      ("KXC15M" in [r[0] for r in bad], [r[0] for r in g["leadswap_fav"][0]]), (True, ["KXC15M"]))
check("control beside the same market; times picked top/bottom", (good[0][2], good[0][3], bad[0][3]), ([3, 1, -0.5], [2, 0], [1, 1]))
check("not picked yet: ranked or picked markets with no bets in the trade", (none, g["leadswap_fav"][2]),
      (["KXE15M", "KXF15M"], ["KXA15M", "KXD15M", "KXE15M", "KXF15M"]))
gh = WB.ls_groups_html(rt_, pk_, ["KXF15M"])
check("the copy line, the red-tinted header, the under-10 tag and the trade headings",
      ("Sorted automatically each hour by return after fees; nothing is removed." in gh, WB.BAD_THEAD in gh and 'style=' not in gh,
       gh.count("under 10"), "Swing on swappy markets" in gh and "Favourite on steady markets" in gh), (True, True, 4, True))
check("each trade's split sits inside its own (collapsed) row, above the board",
      html.index('data-source="leadswap_swing"') < html.index('data-trade="leadswap_swing"') < html.index('data-source="leadswap_fav"')
      < html.index('data-trade="leadswap_fav"') < html.index("Board · last 2 hours"), True)

print("\nevery 15-Minute lane: the same split")
check("split_markets: > 0 doing, <= 0 not, each by return after fees, best first; no-bet markets apart",
      WB.split_markets([("KXA15M", 3, 0.1), ("KXB15M", 9, -0.2), ("KXC15M", 12, 0.3), ("KXD15M", 0, 0), ("KXE15M", 5, 0.0)]),
      ([("KXC15M", 12, 0.3), ("KXA15M", 3, 0.1)], [("KXE15M", 5, 0.0), ("KXB15M", 9, -0.2)], ["KXD15M"]))
check("the live page's bug: Gold +6.1% on fewer bets sits ABOVE Ethereum +0.6%",
      [r[0] for r in WB.split_markets([("KXETH15M", 40, 0.006), ("KXGOLD15M", 12, 0.061)])[0]], ["KXGOLD15M", "KXETH15M"])
g2 = WB.ls_groups({"leadswap_swing": {"series": {"KXA15M": [20, 9, 0.2], "KXB15M": [5, 4, 0.5]}}}, {})
check("Lead Swap groups sort by return too (B +10% on 5 bets above A +1% on 20)", [r[0] for r in g2["leadswap_swing"][0]], ["KXB15M", "KXA15M"])
check("z by day reads 'needs 2+ days' on one day, the number from two",
      (WB._zd(dict(z=1.0, days=1)), WB._zd(dict(z=-1.0, days=0)), WB._zd(dict(z=1.234, days=2))), ("needs 2+ days", "needs 2+ days", "+1.23"))
cell = lambda n, h, r, d=1: dict(n=n, hits=h, hit_rate=h / n, fair=.5, mean_roi=r, z=1.0, days=d)
rec = {"x_s1": dict(all=cell(30, 15, .02), series={"KXA15M": cell(12, 8, .2), "KXB15M": cell(8, 2, -.3), "KXC15M": cell(10, 5, 0.0, 3), "KXD15M": None})}
fb = WB._frozen_block("x", "X v3", "2026-11-09T13:00:00+00:00", "x-v3", {"x_s1": "S1"}, rec, "x", lambda k: "Won",
                      how=("A sentence about the lane.",))
check("a frozen lane: count chip, doing well above the red-headed not doing well, all INSIDE the row's fold",
      ("1 doing well · 2 not" in fb, fb.index('data-source="x_s1"') < fb.index('class="sw15-split"') < fb.index("Doing well")
       < fb.index("Not doing well") < fb.index(WB.BAD_THEAD) < fb.index("</details>"), "sw15-removed" in fb), (True, True, False))
check("the rule's words in a nested Rule details fold; the lane's sentences and the sort line in How the record is kept",
      (fb.index(WB.BAD_THEAD) < fb.index('<details class="fold sw15-rule"><summary>Rule details</summary>'),
       "A sentence about the lane." in fb.split("How the record is kept")[1], WB.SORT_LINE in fb.split("How the record is kept")[1]),
      (True, True, True))
check("one line above the rows and nothing else", re.sub(r"<[^>]+>", "|", fb.split("</h3>")[1].split('<div class="sp-rules-list"')[0]).strip("|"),
      "Paper · fresh record from Nov 9, 7:00 AM CT · review 10, decide 30")
check("frozen rows: under-10 tag only under 10 bets, z needs 2+ days until 2 days, no-bet market listed",
      (fb.count("under 10"), fb.count("needs 2+ days"), "−1.00" not in fb and "+1.00" in fb, "No bets yet" in fb), (1, 2, True, True))
check("the not-doing-well table by return, best first (C 0.0% before B −30%)", fb.index('title="KXC15M"') < fb.index('title="KXB15M"'), True)
check("every lane on the page carries the count and the sort line",
      (len(re.findall(r"\d+ doing well · \d+ not", html)) >= 2 + 3, html.count(WB.SORT_LINE) >= 2), (True, True))

print("\nthe 15-Minute layout (2026-11-10): collapsed, one line per lane, no scoreboard")
check("no fold is a direct child of the section (a #swing15 link would open it)",
      re.findall(r'<h2 class="dm-title">15-Minute</h2>(<details|</div><details)', html), [])
check("no scoreboard, no open per-market tables", ("sw15-scoreboard" in html, "sw15-card" in html), (False, False))
check("every rule row is collapsed by default (no open attribute on a row)", re.findall(r'<details class="sp-rule[^"]*"[^>]* open', html), [])
check("every per-market split sits inside a row's fold",
      all(html.rfind('<details class="sp-rule', 0, m.start()) > html.rfind('</details></details>', 0, m.start())
          for m in re.finditer(r'class="sw15-split"', html)), True)
check("one intro line per lane, nothing else above its rows",
      [re.sub(r"<[^>]+>", "|", seg.split("</h3>")[1].split('<div class="sp-rules-list"')[0]).strip("|").count("|") for seg in
       html.split('<h3 class="dm-title"')[1:]], [0] * len(html.split('<h3 class="dm-title"')[1:]))
check("the status chips", (WB.status_chip({"a": 4}), WB.status_chip({"a": 12, "b": 3}), WB.status_chip({"a": 31, "b": 40})),
      ('<span class="sig n">Too early (4/10)</span>', '<span class="sig w">Review</span>',
       '<span class="sig w">Ready to decide (30+) · 2 markets</span>'))
check("a pooled lane never says 'series at 30+'", ("series at" in html, WB.status_chip({"all": 40})),
      (False, '<span class="sig w">Ready to decide (30+)</span>'))
check("every time in the section reads in CT (no UTC)", ("UTC" in html, WB._start("2026-11-10T00:00:00+00:00"),
      WB._start("2026-11-09T13:15:00Z")), (False, "Nov 9, 6:00 PM CT", "Nov 9, 7:15 AM CT"))
check("no inline style attribute (the CSP blocks them) and no Kalshi market column", ("style=" in html, ">Kalshi</span>" in html),
      (False, False))
check("every Retired/Removed fold sits in the one archive", html.split('id="sw15-archive"')[0].count("sw15-removed"), 0)
check("no empty summary line anywhere in the section",
      [m for m in re.findall(r"<summary[^>]*>(.*?)</summary>", html, re.S) if not re.sub(r"<[^>]+>", "", m).strip()], [])
import daily_markets_build as DMB
check("the sub-nav says 15-Minute", '(("swing15", "15-Minute"),)' in open(DMB.__file__).read(), True)

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
