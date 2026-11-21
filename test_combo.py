#!/usr/bin/env python3
"""test_combo.py — the paper crypto No + S&P No combo (combo_lane.py, combo_build.py), 2026-11-21."""
import datetime as dt
import sys

import combo_build as B
import combo_lane as CL
import leaderboard_build as LB
import site_chrome as C

FAILS = []


def check(why, got, want):
    good = got == want
    print(f"  {'ok  ' if good else 'FAIL'} {why}" + ("" if good else f" — got {got!r}, want {want!r}"))
    if not good:
        FAILS.append(why)


UTC = dt.timezone.utc
WED = dt.datetime(2026, 11, 25, 18, 36, tzinfo=UTC)          # 13:36 ET, a Wednesday
SAT = dt.datetime(2026, 11, 28, 18, 36, tzinfo=UTC)


def crypto_row(price, ticker="KXBTCD-26NOV2517-T1", minutes_before=2, now=WED):
    return dict(source=CL.CRYPTO_LANE, bet=True, price=price, market_id=ticker, label="Bitcoin", status="open",
                logged=(now - dt.timedelta(minutes=minutes_before)).isoformat())


print("price")
p, f, cost = CL.combo_price(0.75, 0.93)
check("0.994 x 1.03 x the product of the asks", p, round(0.994 * 1.03 * 0.75 * 0.93, 6))
check("plus the taker fee 0.07 x p x (1 - p)", (f, cost), (round(0.07 * p * (1 - p), 6), round(p + 0.07 * p * (1 - p), 6)))

print("\nthe day's decision")
real_sp = CL.sp_pick
CL.sp_pick = lambda fetch, now: (dict(ticker="KXINXU-26NOV25H1600-T6000", ask=0.93, bid=0.92, size=40, title="6,000 or above"), None)
st = CL.add_day(CL.empty(), [crypto_row(0.74), crypto_row(0.78, "KXETHD-26NOV2517-T2")], now=WED)
d = st["days"][0]
check("both legs: the highest-priced crypto pick and the S&P rung", (d["status"], d["crypto"]["ticker"], d["sp"]["ticker"]), ("open", "KXETHD-26NOV2517-T2", "KXINXU-26NOV25H1600-T6000"))
check("priced at the formula, the singles beside it", (d["price"], d["cost"], d["singles"]["crypto"]), (CL.combo_price(0.78, 0.93)[0], CL.combo_price(0.78, 0.93)[2], CL.single_cost(0.78)))
check("one decision a day", len(CL.add_day(st, [crypto_row(0.74)], now=WED)["days"]), 1)
check("weekends: nothing", CL.add_day(CL.empty(), [crypto_row(0.74, now=SAT)], now=SAT)["days"], [])
check("a stale crypto pick is not the same minute", CL.add_day(CL.empty(), [crypto_row(0.74, minutes_before=45)], now=WED)["days"][0]["status"], "no_combo")
early = dt.datetime(2026, 11, 25, 17, 0, tzinfo=UTC)         # 12:00 ET: the lane may still pick
check("no crypto pick yet before 14:30 ET: wait", CL.add_day(CL.empty(), [], now=early)["days"], [])
late = dt.datetime(2026, 11, 25, 19, 45, tzinfo=UTC)         # 14:45 ET
check("no crypto pick by 14:30 ET: no combo, with the reason", [(x["status"], "crypto No lane made no pick" in x["reason"]) for x in CL.add_day(CL.empty(), [], now=late)["days"]], [("no_combo", True)])
CL.sp_pick = lambda fetch, now: (None, "no S&P rung in the 90-98c, 3c-spread, 25-contract rule at that minute")
nc = CL.add_day(CL.empty(), [crypto_row(0.74)], now=WED)["days"][0]
check("no S&P rung: no combo with the S&P reason", (nc["status"], "no S&P rung" in nc["reason"]), ("no_combo", True))
CL.sp_pick = real_sp

print("\nsettling")
vals = {}
fetch = lambda path: {"market": dict(ticker=path.split("/")[-1], status="finalized", result=vals[path.split("/")[-1]][0], settlement_value_dollars=vals[path.split("/")[-1]][1])}
CL.D.payout, _orig = (lambda m: {"yes": 1.0, "no": 0.0}.get(m["result"], m.get("settlement_value_dollars"))), CL.D.payout
try:
    def settled(c_res, s_res):
        vals.clear()
        vals.update({"KXBTCD-26NOV2517-T1": (c_res, None), "KXINXU-26NOV25H1600-T6000": (s_res, None)})
        CL.sp_pick = lambda fetch, now: (dict(ticker="KXINXU-26NOV25H1600-T6000", ask=0.93, bid=0.92, size=40, title="x"), None)
        s = CL.add_day(CL.empty(), [crypto_row(0.75)], now=WED)
        CL.settle(s, fetch)
        return s["days"][0]
    w = settled("no", "no")
    check("both No win: the combo lands and pays 1", (w["status"], w["value"], w["roi"]), ("won", 1.0, round(1 / w["cost"] - 1, 4)))
    l = settled("yes", "no")
    check("one leg loses: the whole combo loses", (l["status"], l["value"], l["roi"]), ("lost", 0.0, -1.0))
    check("the singles are scored on their own legs", (l["roi_crypto"], l["roi_sp"] > 0), (-1.0, True))
finally:
    CL.D.payout = _orig
    CL.sp_pick = real_sp
# A part-value S&P leg (settled at 0.4 yes, so 0.6 No) multiplies in: the combo is worth 1.0 x 0.6, with no refund.
CL.D.payout, _orig = (lambda m: {"yes": 1.0, "no": 0.0}.get(m["result"], 0.4)), CL.D.payout
try:
    vals.clear()
    vals.update({"KXBTCD-26NOV2517-T1": ("no", None), "KXINXU-26NOV25H1600-T6000": ("scalar", 0.4)})
    CL.sp_pick = lambda fetch, now: (dict(ticker="KXINXU-26NOV25H1600-T6000", ask=0.93, bid=0.92, size=40, title="x"), None)
    s = CL.add_day(CL.empty(), [crypto_row(0.75)], now=WED)
    CL.settle(s, fetch)
    check("a part-value leg multiplies in, no refund", (s["days"][0]["status"], s["days"][0]["value"]), ("no_result", 0.6))
finally:
    CL.D.payout = _orig
    CL.sp_pick = real_sp

print("\nthe record")
days = [dict(day=f"2026-11-{10 + i:02d}", status=s, crypto=dict(ask=0.75), sp=dict(ask=0.93), cost=0.7, roi=(1 / 0.7 - 1) if s == "won" else -1.0,
             roi_crypto=0.3 if s == "won" else -1.0, roi_sp=0.05 if s == "won" else -1.0) for i, s in enumerate(["won", "won", "lost", "lost", "won"])]
rec = CL.record(dict(days=days + [dict(day="2026-11-20", status="no_combo", reason="x")]))
check("settled, landed, longest losing run, days with no combo", (rec["n"], rec["landed"], rec["run"], rec["no_combo"]), (5, 3, 2, 1))
check("the read waits for 30", CL.verdict(rec).startswith("too early (5 of 30"), True)
rec30 = dict(rec, n=30, mean_roi=0.1, single_both=0.12)
check("at 30 the combo at or below the singles is retired", CL.verdict(rec30).startswith("retire"), True)

print("\nthe page and the move")
html = B.build(CL.empty(), now=WED)
check("Combo page: today, record, days, pre-registration, the buy-at-the-ask note", all(x in html for x in ('id="today"', 'id="record"', 'id="days"', 'id="prereg"', "bought at the ask")), True)
check("percentages only: no dollar amount", "$" in html.replace("S&amp;P", ""), False)
check("Combo is in the menu, Leaderboard is not", ('href="./combo.html"' in html, 'href="./leaderboard.html"' in html), (True, False))
arch = LB.build(bets=[], contracts=[], now=WED)
check("the Leaderboard page lives under Archives", ('href="../archive/index.html"' in arch, 'aria-current="page">Leaderboard' in arch), (True, True))
check("its old URL forwards", "./archive/leaderboard.html" in LB.redirect_page(), True)
check("Combo registered", (C.PAGE_FILES["combo"], "combo" in C.MARKET_GROUP), ("combo.html", True))
check("the workflow runs the combo step and adds its ledger", all(x in open(".github/workflows/sandbox-tracker.yml").read() for x in ("python3 combo_lane.py", "data/combo_ledger.json", "public_site/combo.html")), True)
doc = open("docs/prereg_combo_crypto_sp_2026-11-21.md").read()
check("the pre-registration exists, with the read at 30 and the zero start", ("30 settled combos" in doc, "starts at zero" in doc), (True, True))

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
