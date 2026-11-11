#!/usr/bin/env python3
"""Gas weekly cheap NO: hold to the end is the record, judged by weeks (Olu, 2026-11-11)."""
import html
import re
import sys

import commodities_build as CB
import mentions_split as MS

FAILS = []


def check(why, got, want):
    good = got == want
    print(f"  {'ok  ' if good else 'FAIL'} {why}" + ("" if good else f" — got {got!r}, want {want!r}"))
    if not good:
        FAILS.append(why)


G = MS.GAS_WEEK
print("the lane")
check("entry band unchanged (NO ask 15-30c, 10c spread), still live", (G["band"], G["spread"], G["side"], "retired" in G,
      G in MS.LIVE_COMMOD), ((0.15, 0.30), 0.10, "no", False, True))
check("hold is the record, judged by weeks: review 8, decide 10+, stage from Nov 11",
      (G["headline"], G["judge"], G["review_weeks"], G["decide_weeks"], G["stage_from"]), ("hold", "weeks", 8, 10, "2026-11-11"))
check("the daily lane (retired) does not pick these up", [k in MS.GAS for k in ("headline", "judge")], [False, False])

print("\nthe week record: one week is one cluster")
cost = lambda p: p + MS.fee(p, MS.TAKER)
ent = lambda ev, p, pay: dict(id=f"{ev}-{p}", event=ev, price=p, payout=pay, roi_held=round((pay - cost(p)) / cost(p), 4))
es = [ent("W1", 0.2, 1.0), ent("W1", 0.3, 0.0), ent("W2", 0.2, 0.0), ent("W2", 0.25, 0.0), ent("W3", 0.2, 1.0),
      dict(ent("W4", 0.2, 1.0), payout=None)]
w = MS.week_record(es)
check("3 settled weeks (the open one waits), 2 positive", (w["weeks"], w["positive"]), (3, 2))
check("profit per week = the weeks' summed held P/L per contract over the weeks",
      round(w["profit_per_week"], 4), round(((1 - cost(.2) - cost(.3)) + (-cost(.2) - cost(.25)) + (1 - cost(.2))) / 3, 4))
check("t over weeks from 3 weeks, none below", (w["t"] is not None, MS.week_record(es[:4])["t"]), (True, None))
check("stage text", (MS.week_status(G, es), MS.week_status(G, [ent(f"W{i}", .2, 1.0) for i in range(9)]),
      MS.week_status(G, [ent(f"W{i}", .2, 1.0) for i in range(10)])),
      ("early · 3/8 settled weeks to review", "review · 9 settled weeks", "decide · 10 settled weeks"))

print("\nthe Commodities page")
h = CB.build()
i = h.find('data-source="gas_week_cheap_no"')
row = h[i:h.find("</summary>", i)]
card = html.unescape(h[i:h.find("</section>", i)])
check("the row headlines hold, record in weeks, evidence out of 10 weeks",
      ('<span class="mut sm">held</span></span>' in row, " wks</span>" in row, "/10 wks" in row,
       'data-l="ROI after fees">' in row), (True, True, True, True))
check("the card: hold first, the weeks line, the split a secondary line, Olu's evidence in a closed fold",
      ("held (the record)" in card, "settled weeks" in card and "profit per week" in card,
       "Secondary, not the record: the 2x/3x split" in card, "51 bets, 17 won, +31%" in card,
       "<details open" in card), (True, True, True, True, False))
check("no dollar sign in the copy", re.search(r"\$\d", card), None)

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
