#!/usr/bin/env python3
"""Steady Favourites (steadyfav.py, sw15-sf1): the frozen markets, the fresh record, the pooled controls, the page."""
import json
import os
import re
import sys
import tempfile

import sandbox_audit
import steadyfav as S
import swing15 as W
import swing15_build as WB

FAILS = []


def check(why, got, want):
    good = got == want
    print(f"  {'ok  ' if good else 'FAIL'} {why}" + ("" if good else f" — got {got!r}, want {want!r}"))
    if not good:
        FAILS.append(why)


def row(series, open_iso, s2=None, s3=None):
    return dict(ticker=f"{series}-{open_iso}", series=series, group="Crypto", open=open_iso, day=open_iso[:10],
                us_hours=False, fee_multiplier=1.0, s1={}, s2=s2 or dict(status="no_quote"), s3=s3 or dict(status="no_quote"))


fav = lambda won, price=.6: dict(status="filled", side="yes", price=price, won=won,
                                 roi=round(won / (price + W.fee(price, W.TAKER)) - 1, 4))

print("the pre-registration")
check("version, the four frozen markets, the start", (S.VERSION, S.MARKETS, S.FROM),
      ("sw15-sf1", ("KXBTC15M", "KXUSDJPY15M", "KXGOLD15M", "KX2YRRATE15M"), "2026-11-10T00:00:00+00:00"))
check("rule A is v1's S2, rule B v1's S3", S.RULES, {"steadyfav_a": ("swing15_s2",), "steadyfav_b": ("swing15_s3",)})
check("the start is a window boundary after S1's retirement", (W._ts(S.FROM) % 900, S.FROM > "2026-11-09T22:00"), (0, True))

print("\nthe record")
T, T2 = "2026-11-10T00:00:00Z", "2026-11-10T00:15:00Z"
ws = [row("KXBTC15M", T, s2=fav(1.0), s3=fav(1.0, .8)),
      row("KXBTC15M", T2, s2=fav(0.0)),
      row("KXGOLD15M", T, s3=fav(0.0, .7)),
      row("KXBTC15M", "2026-11-09T23:45:00Z", s2=fav(1.0), s3=fav(1.0)),        # before FROM: earlier, never counted
      row("KXETH15M", T, s2=fav(1.0), s3=fav(0.0)),                             # control
      row("KXWTI15M", T, s2=fav(0.0)),                                          # control
      row("KXCRYPTOLEAD15M", T, s2=fav(1.0))]                                   # not a price series: no control
state = dict(W.empty(), windows={w["ticker"]: w for w in ws})
rec = S.records(state)
a, b = rec["steadyfav_a"], rec["steadyfav_b"]
check("A: BTC's two fresh windows (1 won), not the 23:45Z one", (a["all"]["n"], a["all"]["hits"], a["series"]["KXBTC15M"]["n"]), (2, 1, 2))
check("B: BTC 1 + GOLD 1; a market with no windows is None", (b["all"]["n"], b["series"]["KXGOLD15M"]["hits"], b["series"]["KXUSDJPY15M"]), (2, 0, None))
check("won v priced: fair is the mean entry price", round(b["all"]["fair"], 2), .75)
check("controls pool the other markets (ETH, WTI), not CRYPTOLEAD, not the four",
      (rec["steadyfav_a_ctrl"]["all"]["n"], rec["steadyfav_a_ctrl"]["all"]["hits"], rec["steadyfav_b_ctrl"]["all"]["n"],
       rec["steadyfav_a_ctrl"]["markets"]), (2, 1, 1, 2))
old = S.records(state, earlier=True)
check("earlier (shown, not counted): the 23:45Z BTC window", (old["steadyfav_a"]["all"]["n"], "steadyfav_a_ctrl" in old), (1, False))
led = S.ledger(state)
check("the ledger", (led["version"], led["from"], led["records"]["steadyfav_a"]["all"]["n"], led["records"]["steadyfav_b_ctrl"]["markets"]),
      ("sw15-sf1", S.FROM, 2, 2))

print("\nthe page")
import leadswap as L
tmp = tempfile.mkdtemp()
L.PATH = os.path.join(tmp, "leadswap_ledger.json")
with open(L.PATH, "w") as f:
    json.dump(L.update(state, L.empty()), f)
html = WB.section(state)
sf = html.split('id="steadyfav"')[1].split('id="leadswap"')[0]
ids = ('id="steadyfav"', 'id="leadswap"', 'id="swing15v2"', 'id="flipside_v2"', 'id="holdtoend"', 'id="sw15-v1"',
       'id="sw15-archive"')
pos = [html.index(x) for x in ids if x in html]
check("the order after #378/#379: Steady Favourites, Lead Swap, Swing v3, Flip v3, Hold to End v3, v1, archive; no scoreboard",
      (pos == sorted(pos), all(x in html for x in ('id="steadyfav"', 'id="leadswap"', 'id="sw15-v1"')), "sw15-scoreboard" in html),
      (True, True, False))
check("the copy: markets, fresh start time, review/decide, the sort line",
      ("Bitcoin, USD/JPY (Japanese Yen), Gold, 2-Year Treasury Yield" in sf, "fresh record from Nov 9, 6:00 PM CT" in sf,
       "review 10, decide 30" in sf, WB.SORT_LINE in sf), (True, True, True, True))
check("two rows, A and B; the pooled controls are not rows", re.findall(r'data-source="(steadyfav_[a-z_]+)"', html),
      ["steadyfav_a", "steadyfav_b"])
check("each rule's control is a muted vs-control figure in its row", sf.count('title="Control: '), 2)
check("A's split: BTC (2 bets, one win at 60c) is not doing well; counts on top", ("0 doing well · 1 not" in sf, "under 10" in sf), (True, True))
check("z reads 'needs 2+ days' on one day", "needs 2+ days" in sf, True)
check("the control sits beside each rule", "Control (the same rule on the other markets, pooled): 1/2 won" in sf, True)
check("one muted earlier line, not counted", len(re.findall(r'sf-earlier">Earlier result, not counted', sf)), 1)
check("the Sandbox index lists the four rows after the Loss Reader", [r["lane"] for r in WB.index_rows(state)][:6], ["lossreader", "s3v2"] + list(S.LABELS))
check("no dollar sign, no guarded phrase", (re.search(r"\$\d", html), sandbox_audit.COPY_RE.findall(html + WB.index_html(state))), (None, []))

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
