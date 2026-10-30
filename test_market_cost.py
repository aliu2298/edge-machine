#!/usr/bin/env python3
"""The stock and ETF records are judged at the cost the Alpaca fills measured (2026-10-29).

The ledger stores each trade's ret_net at the 5bp a side first assumed. The page charges the
measured cost instead: a rule's own mean once it has MIN_RULE_FILLS matched fills, else the
mean over every matched fill. The 5bp figures stay beside it. Offline, no network.
"""
import copy
import json
import os
import sys
import tempfile

import market_sources as M
import market_track as MT
import sandbox_audit
import sandbox_build as SB

FAILS = []


def ok(cond, msg):
    print(f"  {'ok  ' if cond else 'FAIL'} {msg}")
    if not cond:
        FAILS.append(msg)


def eq(a, b, msg):
    ok(a == b, f"{msg} (got {a!r}, want {b!r})")


def close(a, b, msg, tol=1e-9):
    ok(a is not None and abs(a - b) < tol, f"{msg} (got {a!r}, want ~{b!r})")


FILLS = {"summary": dict(fills=60, mean_bps=20.0, assumed_bps_per_side=5.0,
                         orders=dict(since="2026-10-12", sent=70, filled=60),
                         by_rule={"sw_rsi2_pullback": dict(n=40, mean_bps=30.0),
                                  "etf_double7": dict(n=12, mean_bps=2.0)})}


def trade(rule, day, gross, bench, sym="AAA"):
    return dict(id=f"{rule}|{sym}|{day}", rule=rule, lane="swing", symbol=sym, signal_day=day,
                entry_day=day, entry=100.0, status="closed", exit=100.0 * (1 + gross),
                exit_day=day, ret_gross=gross, ret_net=round(gross - 2 * M.COST_BPS_PER_SIDE / 1e4, 6),
                bench_ret=bench, bars_held=3)


LEDGER = {"meta": {}, "trades": [
    trade("sw_rsi2_pullback", "2026-10-13", 0.010, 0.002),
    trade("sw_rsi2_pullback", "2026-10-13", -0.004, 0.002, sym="BBB"),
    trade("sw_rsi2_pullback", "2026-10-14", 0.003, -0.001),
    trade("etf_double7", "2026-10-13", 0.0015, 0.0),
    trade("etf_double7", "2026-10-15", 0.0010, 0.0),
]}

print("the measured cost, from the published fill check")
mc = MT.measured_cost(FILLS)
eq((mc["pooled"], mc["n"], mc["since"], mc["assumed"]), (20.0, 60, "2026-10-12", 5.0), "pooled mean, fill count, since")
eq(MT.measured_cost(None), None, "no fill check: no measured cost")
eq(MT.measured_cost({"summary": dict(fills=0, mean_bps=None)}), None, "a fill check with no fills: none either")
with tempfile.TemporaryDirectory() as tmp:
    path = os.path.join(tmp, "market_fills.json")
    json.dump(FILLS, open(path, "w"))
    eq(MT.load_fills(path)["summary"]["fills"], 60, "load_fills reads the report")
    open(path, "w").write("{nope")
    eq(MT.load_fills(path), None, "a corrupt report reads as None")

print("\nwhich figure each rule is charged")
eq(MT.rule_cost_bps("sw_rsi2_pullback", mc), (30.0, "its own 40 fills"),
   f"{MT.MIN_RULE_FILLS}+ fills of its own: its own mean")
eq(MT.rule_cost_bps("etf_double7", mc), (20.0, "all 60 fills (its own 12: +2.0bp)"),
   "fewer than that: the mean over all fills, its own shown beside")
eq(MT.rule_cost_bps("etf_tom", mc), (20.0, "all 60 fills"), "no fills of its own: the pooled mean")
eq(MT.rule_cost_bps("cr_trend20", mc), (M.CRYPTO_COST_BPS_PER_SIDE, "assumed"),
   "a rule with its own cost (crypto) keeps it: no Alpaca fill measures a coin")
eq(MT.rule_cost_bps("sw_rsi2_pullback", None), (M.COST_BPS_PER_SIDE, "assumed"), "no fill check: the assumed 5bp")

print("\nthe record at the measured cost")
d = copy.deepcopy(LEDGER)
before = json.dumps(d, sort_keys=True)
plain = MT.assess(d, "sw_rsi2_pullback")
at5 = MT.assess(d, "sw_rsi2_pullback", bps=M.COST_BPS_PER_SIDE)
for k in ("mean", "edge", "total", "t", "edge_t"):
    close(at5[k], plain[k], f"charging 5bp again reproduces the stored record: {k}", tol=1e-6)
at30 = MT.assess(d, "sw_rsi2_pullback", bps=30.0)
day1 = ((0.010 - 0.006) + (-0.004 - 0.006)) / 2
day2 = 0.003 - 0.006
close(at30["mean"], (day1 + day2) / 2, "mean per entry day is gross less 2 x 30bp, day by day")
close(at30["edge"], ((day1 - 0.002) + (day2 + 0.001)) / 2, "and the edge v SPY uses the same net")
close(at30["total"], (0.010 + -0.004 + 0.003 - 3 * 0.006) * MT.STAKE, "P/L charges every trade")
eq(at30["wins"], 1, "a trade that won at 5bp can lose at the measured cost")

rows = {r["rule"]: r for r in MT.report(d, cost=mc)}
eq(rows["sw_rsi2_pullback"]["cost_bps"], 30.0, "report charges each rule its own figure")
eq(rows["etf_double7"]["cost_from"], "all 60 fills (its own 12: +2.0bp)", "and says where it came from")
plain_rows = {r["rule"]: r for r in MT.report(d)}
eq(rows["sw_rsi2_pullback"]["assumed"], plain_rows["sw_rsi2_pullback"], "each row carries the 5bp record beside it")
close(rows["etf_double7"]["total"], (0.0015 + 0.0010 - 2 * 0.004) * MT.STAKE, "Double 7s at the pooled 20bp")
ok(rows["etf_double7"]["assumed"]["total"] > 0 > rows["etf_double7"]["total"],
   "its P/L is positive at 5bp and negative at the measured cost")
eq(json.dumps(d, sort_keys=True), before, "judging at the measured cost never rewrites the ledger")
eq(MT.READ_FLOOR, 30, "still read at 30 entry days")

print("\nthe Trading page shows both")
html = SB.trading_rows(d, mc)
eq(SB.TRADE_HEAD.count("<th"), 8, "no extra column: a wider table loses its sticky header on Linux Chrome")
ok("cost 30.0bp a side, measured" in html, "RSI(2) shows its measured cost under its name")
ok("Charged 30.0bp a side, measured over its own 40 fills" in html, "and where it came from, in its fold")
ok("Charged 20.0bp a side, measured over all 60 fills (its own 12: +2.0bp)" in html,
   "Double 7s names the pooled figure and its own")
ok(html.count('class="sm mut trade-assumed">5bp:') >= 6, "mean, edge and P/L each show the 5bp figure beneath")
ok('colspan="8"' in html, "the definition row spans the table")
note = SB.cost_note_html(mc)
ok("measured" in note and "60 fills" in note and "+20.0bp" in note and "120 days" in note
   and f"{MT.MIN_RULE_FILLS}+" in note and "5bp a side the record first assumed" in note,
   "the note says how the cost is derived, and keeps the 5bp beside it")
ok("assumed" in SB.cost_note_html(None) and "measured" not in SB.cost_note_html(None).split("nothing has")[0],
   "without a fill check the page says the cost is assumed")
page = SB.trading_page()
ok("trade-cost-line" in page and "Cost a side is <b>measured</b>" in page, "the live page carries the cost line and its note")
eq(sandbox_audit.COPY_RE.findall(html + note + SB.cost_note_html(None)), [], "no guarded public phrase in the new copy")

print(f"\n{'all passed' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
