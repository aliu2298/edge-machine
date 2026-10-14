#!/usr/bin/env python3
"""The Trading page and the Alpaca fill check (decided 2026-10-14).

1. Two rules on one stock stay as they are: each rule's trade is its own order, sized
   separately, so the fill check and the page attribute each share to its rule.
2. The overnight rule is record only: its row says it is not sent to Alpaca.
3. The page says what runs it and that the table is the paper record, and gives the
   Alpaca execution counts in one line, with the detail in a closed fold.
No network: the broker's order list is a fixture. Nothing is written outside a temp dir.
"""
import datetime
import json
import os
import re
import subprocess
import tempfile
import uuid

import market_exec as X
import market_track as MT
import sandbox_build as SB

FAILS = []
ROOT = os.path.dirname(os.path.abspath(__file__))
NOW = datetime.datetime(2026, 10, 14, 12, tzinfo=datetime.timezone.utc)


def ok(cond, why):
    print(f"  {'ok  ' if cond else 'FAIL'} {why}")
    if not cond:
        FAILS.append(why)


def eq(got, want, why):
    ok(got == want, why if got == want else f"{why} — got {got!r}, want {want!r}")


def _ord(status="filled", px=None, qty=10, sym="AAA", side="buy", day="2026-10-10"):
    return {"status": status, "filled_avg_price": (str(px) if px is not None else None),
            "filled_qty": str(qty if status == "filled" else 0), "qty": str(qty), "symbol": sym,
            "side": side, "filled_at": f"{day}T13:30:00Z", "submitted_at": f"{day}T20:10:00Z"}


GAP = "sw_gap_down_reversal|DAL|2026-10-09"
RSI = "sw_rsi2_pullback|DAL|2026-10-10"
DONE = "etf_double7|SPY|2026-10-09"
LED = {"trades": [
    dict(id=GAP, rule="sw_gap_down_reversal", symbol="DAL", entry=50.0, exit=None,
         entry_day="2026-10-10", status="open"),
    dict(id=RSI, rule="sw_rsi2_pullback", symbol="DAL", entry=51.0, exit=None,
         entry_day="2026-10-13", status="open"),
    dict(id=DONE, rule="etf_double7", symbol="SPY", entry=600.0, exit=606.0,
         entry_day="2026-10-10", exit_day="2026-10-13", status="closed"),
    dict(id="etf_tom|QQQ|2026-10-10", rule="etf_tom", symbol="QQQ", entry=500.0, exit=None,
         entry_day="2026-10-13", status="open"),
], "meta": {}}
EX = {
    X.client_order_id(GAP, "buy"): _ord(px=50.05, qty=12, sym="DAL"),
    X.client_order_id(RSI, "buy"): _ord(px=51.02, qty=12, sym="DAL", day="2026-10-13"),
    X.client_order_id(DONE, "buy"): _ord(px=600.3, qty=1, sym="SPY"),
    X.client_order_id(DONE, "sell"): _ord(px=605.7, qty=1, sym="SPY", side="sell", day="2026-10-13"),
    # a day order that reached no fill and expired
    X.client_order_id("etf_tom|QQQ|2026-10-10", "buy"): _ord(status="expired", qty=2, sym="QQQ", day="2026-10-12"),
    # queued for tomorrow's open, no trade in the record yet
    "em-" + str(uuid.uuid5(X.NS, "etf_ibs_band|IWM|2026-10-13|buy")): _ord(status="accepted", qty=4, sym="IWM",
                                                                           day="2026-10-13"),
}

print("two rules on one stock: each share is attributed to its rule")
saved = X.exchange_orders
X.exchange_orders = lambda days=120: EX
try:
    rep = X.reconcile(LED)
finally:
    X.exchange_orders = saved
ok(X.client_order_id(GAP, "buy") != X.client_order_id(RSI, "buy"),
   "the two DAL trades have two different order ids")
dal = next(h for h in rep["held"] if h["symbol"] == "DAL")
eq(dal["qty"], 24, "the account's DAL position is the two trades together")
eq([(p["rule"], p["qty"]) for p in dal["rules"]], [("sw_gap_down_reversal", 12), ("sw_rsi2_pullback", 12)],
   "and each rule keeps its own 12")
ok(all(h["symbol"] != "SPY" for h in rep["held"]), "a trade whose sell filled is not held")
eq({r["rule"] for r in rep["rows"] if r["symbol"] == "DAL"}, {"sw_gap_down_reversal", "sw_rsi2_pullback"},
   "the fill rows name both rules")
eq(sorted(rep["summary"]["by_rule"]), ["etf_double7", "sw_gap_down_reversal", "sw_rsi2_pullback"],
   "the measured cost is broken down per rule")
orders = rep["summary"]["orders"]
eq((orders["sent"], orders["filled"], orders["unfilled"], orders["working"]), (6, 4, 1, 1),
   "orders: 6 sent, 4 filled, 1 expired unfilled, 1 still working")
eq(orders["sent"], orders["filled"] + orders["unfilled"] + orders["working"], "the three always add up to sent")
eq(orders["since"], "2026-10-10", "since is the day the first order was submitted")
eq(X.order_counts({}), dict(sent=0, filled=0, unfilled=0, working=0, since=None), "no orders, zero counts")
part = {"a": {"status": "partially_filled", "filled_qty": "3", "submitted_at": "2026-10-11T20:10:00Z"},
        "b": {"status": "canceled", "filled_qty": "2", "submitted_at": "2026-10-11T20:10:00Z"}}
eq((X.order_counts(part)["filled"], X.order_counts(part)["working"], X.order_counts(part)["unfilled"]),
   (1, 1, 0), "an active partial is working, but a cancelled partial is finished with a fill")

# The real SWKS pattern: 11/13 executed, then the opening-auction order expired.
swks = "sw_rsi2_pullback|SWKS|2026-10-09"
partial_buy = _ord(status="expired", px=77.05, qty=13, sym="SWKS")
partial_buy["filled_qty"] = "11"
fixture = {X.client_order_id(swks, "buy"): partial_buy}
saved = X.exchange_orders
X.exchange_orders = lambda days=120: fixture
try:
    partial_rep = X.reconcile({"trades": [dict(id=swks, rule="sw_rsi2_pullback", symbol="SWKS",
                                              entry=77.05, entry_day="2026-10-12", status="open")]})
finally:
    X.exchange_orders = saved
eq(partial_rep["held"][0]["qty"], 11, "expired SWKS buy still contributes all 11 executed shares")
eq((partial_rep["summary"]["orders"]["filled"], partial_rep["summary"]["orders"]["working"]),
   (1, 0), "expired partial fill is finished, not waiting for the open")
ok("waiting for the open" not in SB.trade_exec_html(partial_rep),
   "the page does not label an expired partial as queued")
partial_sell = dict(id=swks, rule="sw_rsi2_pullback", symbol="SWKS", side="sell", status="canceled", qty=3)
eq(X.held_positions(partial_rep["rows"] + [partial_sell])[0]["qty"], 8,
   "a canceled sell's executed shares reduce the holding")
active_buy = dict(partial_rep["rows"][0], status="partially_filled")
eq(X.held_positions([active_buy])[0]["qty"], 11, "active partial fills also count as held shares")

print("\nthe overnight rule is record only")
eq(MT.RULES["etf_overnight"].get("entry"), "close", "the overnight rule enters at the close")
eq(X.executable_rules()[1].get("etf_overnight"),
   "enters at the close — needs a market-on-close order before 15:50 ET",
   "market_exec does not send it")
md = MT.load()
rows = SB.trading_rows(md)
night = rows[rows.find("Swing · etf_overnight"):]
night = night[:night.find("</td>")]
ok(SB.RECORD_ONLY in night and SB.RECORD_ONLY == "record only — not sent to Alpaca (needs a market-on-close order)",
   "its row says: record only — not sent to Alpaca (needs a market-on-close order)")
eq(rows.count(SB.RECORD_ONLY), 1, "and no other row says it")

print("\nthe page: what runs it, what the table is, what Alpaca did")
fills = dict(rep, updated="2026-10-13T20:31:00+00:00")
with tempfile.TemporaryDirectory() as tmp:
    path = os.path.join(tmp, "market_fills.json")
    json.dump(fills, open(path, "w"))
    eq(SB.load_fills(path)["summary"]["orders"]["sent"], 6, "load_fills reads the published report")
    eq(SB.load_fills(os.path.join(tmp, "none.json")), None, "a missing report reads as None")
    open(path, "w").write("{not json")
    eq(SB.load_fills(path), None, "a corrupt report reads as None, not a crash")
line = SB.trade_exec_html(fills)
head = re.search(r'<p class="sm trade-exec">(.*?)</p>', line).group(1)
ok(head.startswith("Alpaca paper execution since Oct 10: 6 sent · 4 filled · 1 unfilled · 1 waiting for the open"),
   "one line: since the first order, sent · filled · unfilled, and what is still waiting")
ok('<span class="trade-shared">DAL 24: <span class="badge">sw_gap_down_reversal 12</span> '
   '<span class="badge">sw_rsi2_pullback 12</span></span>' in head,
   "a stock two rules hold is tagged with each rule's share, one badge per rule")
ok("SPY" not in head, "a stock one rule held is not tagged")
fold = line[line.find('<details class="fold trade-exec-detail">'):]
ok(fold.startswith('<details class="fold trade-exec-detail"><summary>Execution detail</summary>'),
   "the detail is in a fold")
ok("<details open" not in line, "and the fold is closed on load")
ok("DAL 24: sw_gap_down_reversal 12, sw_rsi2_pullback 12" in fold, "the fold lists what is held, by rule")
ok("4 fills matched to the record" in fold and "against the 5bp the record assumes" in fold,
   "and the measured cost against the assumed one")
ok(SB.RECORD_ONLY in fold, "and names the overnight rule as record only")
ok("Fill check published 3:31 PM CT Oct 13." in fold, "and when the report was published, in CT once")
orphan = dict(fills, summary=dict(fills["summary"], orphans=2))
ok("2 fill(s) have no trade in the record" in SB.trade_exec_html(orphan), "a fill with no trade is flagged")
none = SB.trade_exec_html(None)
ok("no fill check has been published yet" in none and "<details" not in none,
   "with no report the line says so, and there is no fold")
single = dict(fills, held=[dict(symbol="DAL", qty=12, rules=[dict(rule="sw_rsi2_pullback", id=RSI, qty=12)])])
ok("badge" not in SB.trade_exec_html(single).split("</p>")[0], "one rule on a stock gets no tag")

saved_load = SB.load_fills
SB.load_fills = lambda path=None: fills
try:
    html = SB.trading_page(NOW)
finally:
    SB.load_fills = saved_load
src = re.search(r'<p class="sm trade-source">(.*?)</p>', html).group(1)
ok("market_track.py and market_exec.py in edge-machine, on edge-vps" in src
   and "edge-market.timer, weekdays 16:10 ET" in src, "the page names the scripts, the host and the timer")
ok("<b>paper record</b> since its registration" in src and "not the Alpaca account" in src,
   "and says the table is each rule's paper record, not the Alpaca account")
for old in ("scanned and graded", "market data keys", "built elsewhere"):
    ok(old not in html, f"the old wording is gone ({old!r})")
ok(html.count('<p class="sm trade-exec">') == 1, "the execution line is on the page once")
ok(html.find('class="sm trade-source"') < html.find('class="sm trade-exec"') < html.find("<h2>Stock and ETF rules"),
   "source line, then the execution line, then the table")
method = html[html.find('<details class="fold trade-method">'):]
ok(method.startswith('<details class="fold trade-method"><summary>How the record is kept</summary>'),
   "the long method note is in a closed fold")
main_text = html[html.find("<h1>Trading"):html.find("<footer>")]
shown = re.sub(r"<details.*?</details>", "", main_text, flags=re.S)
loose = [p for p in re.findall(r'<(?:p|div) class="(?:note[^"]*|sm[^"]*)">(.*?)</(?:p|div)>', shown, re.S)
         if len(re.sub(r"<[^>]+>", "", p)) > 400]
eq(loose, [], "no paragraph over 400 characters is open on load")

print("\nthe VPS publishes the report")
script = open(os.path.join(ROOT, "scripts", "market_daily.sh")).read()
ok("git add -- data/market_fills.json" in script, "market_daily.sh stages data/market_fills.json")
eq(script.count("data/market_ledger.json|data/sp500.json|data/market_fills.json) ;;"), 3,
   "and all three publish guards accept it")
ignored = subprocess.run(["git", "check-ignore", "-q", "data/market_fills.json"], cwd=ROOT).returncode
eq(ignored, 1, "data/market_fills.json is no longer git-ignored")

print()
if FAILS:
    print(f"{len(FAILS)} FAILED")
    for f in FAILS:
        print(" -", f)
    raise SystemExit(1)
print("all checks passed")
