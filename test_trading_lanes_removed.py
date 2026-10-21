#!/usr/bin/env python3
"""Twelve retired trading rules taken off the board the same way a Sandbox lane is: the eight
of 2026-10-04 and four swing rules of 2026-10-20.

They do not render, and they never log or send a new trade. The rows already
in the ledger stay, count and content, except that the four of 2026-10-20 are
EXIT-ONLY: their open rows still close on each rule's own exit, market_exec
still sells their paper shares, and an orphan fill of theirs (no ledger row) is
sold on the same exit. A rule with no trades that is not in the removed set
still renders. No network, and nothing is written.
"""
import copy
import datetime
import os
import sys

import cricket_build
import market_track as MT
import production
import sandbox_build as SB
import sandbox_track as T
import site_root
import soccer_build
import tennis_build

FAILS = []
NOW = datetime.datetime(2026, 10, 4, 12, tzinfo=datetime.timezone.utc)
ROOT = os.path.dirname(os.path.abspath(__file__))
EIGHT = (
    "cr_btc_2200",
    "dt_intraday_mom",
    "sw_52w_breakout",
    "sw_ma_cross_rsi",
    "cr_trend20",
    "dt_orb30",
    "dt_orb30_long",
    "dt_vwap_reclaim",
    # 2026-10-20, as asked (Olu)
    "sw_gap_down_reversal",
    "etf_ibs_band",
    "etf_tom",
    "etf_overnight",
)
# Closed and open counts on the ledger this test reads. The headline is the
# sum of the rules that stay.
LANE_COUNTS = {
    "cr_btc_2200": (9, 0),
    "dt_intraday_mom": (15, 0),
    "sw_52w_breakout": (2, 11),
    "sw_ma_cross_rsi": (1, 19),
    "cr_trend20": (0, 0),
    "dt_orb30": (158, 0),
    "dt_orb30_long": (56, 0),
    "dt_vwap_reclaim": (153, 0),
    "sw_gap_down_reversal": (18, 26),
    "etf_ibs_band": (6, 8),
    "etf_tom": (1, 0),
    "etf_overnight": (38, 0),
}
KEPT = "sw_rsi2_pullback"
# The four removed 2026-10-20 had paper positions at Alpaca: they still exit, never enter.
EXIT_ONLY = ("sw_gap_down_reversal", "etf_ibs_band", "etf_tom", "etf_overnight")


def ok(cond, why):
    print(f"  {'ok  ' if cond else 'FAIL'} {why}")
    if not cond:
        FAILS.append(why)


def eq(got, want, why):
    ok(got == want, why if got == want else f"{why} — got {got!r}, want {want!r}")


def bar(day, o, h, l, c, v=2_000_000):
    return {"t": f"{day}T00:00:00Z", "o": o, "h": h, "l": l, "c": c, "v": v}


def _day(offset, first=datetime.date(2025, 1, 1)):
    return (first + datetime.timedelta(days=offset)).isoformat()


def _pages():
    sandbox, index, weeks = SB.render_pages(NOW)
    out = {
        "sandbox.html": sandbox,
        "archive/index.html": index,
        "production.html": production.page(
            T.load(), T.load_stages(), production.load_feed(), "", now=NOW),
        "trading.html": SB.trading_page(NOW),
        "index.html": site_root.root_stub(NOW),
    }
    root = os.path.join(ROOT, "public_site", "index.html")
    with open(root, encoding="utf-8") as f:
        out["public_site/index.html"] = f.read()
    out.update({f"archive/{slug}.html": html for slug, html in weeks.items()})
    out["soccer.html"] = soccer_build.build(now=NOW)
    out["tennis.html"] = tennis_build.build(now=NOW)
    out["cricket.html"] = cricket_build.build(now=NOW)
    return out


def _counts(trades, rule):
    rows = [t for t in trades if t.get("rule") == rule]
    closed = sum(1 for t in rows if t.get("status") == "closed")
    opened = sum(1 for t in rows if t.get("status") == "open")
    return rows, closed, opened


def _board_tiles(trades):
    """Closed and open tiles: the sum of lanes that are not in the removed set.

    Read from the ledger the page renders, so a later close on a lane still
    on the board moves the page and this expectation together.
    """
    kept = [t for t in trades
            if t.get("rule") not in set(EIGHT) and not t.get("research")]
    closed = sum(1 for t in kept if t.get("status") == "closed")
    opened = sum(1 for t in kept if t.get("status") == "open")
    return closed, opened


print("\nthe twelve retired rules are the removed set")
removed = getattr(MT, "REMOVED_RULES", None)
ok(removed is not None and set(removed) == set(EIGHT),
   "exactly these twelve rules are removed")
retired = {name for name, meta in MT.RULES.items() if meta.get("retired")}
ok(retired == set(EIGHT), "every retired trading rule is one of the twelve, and no other rule is")
gate = getattr(MT, "rule_removed", lambda _name: False)
ok(all(gate(name) for name in EIGHT), "the entry gate blocks each of the eight")
ok(not gate(KEPT), "a rule still on the board is not blocked")

print("\nthe ledger rows are unchanged")
ledger = MT.load()
snapshot = copy.deepcopy(ledger["trades"])
for name, (want_closed, want_open) in LANE_COUNTS.items():
    rows, closed, opened = _counts(snapshot, name)
    if name in EXIT_ONLY:
        # Exit-only: open rows close on the rule's own exit, so only the total is fixed.
        ok(len(rows) == want_closed + want_open and closed >= want_closed
           and closed + opened == len(rows),
           f"{name} keeps its {want_closed + want_open} rows (open ones may only close)")
        continue
    eq((closed, opened, len(rows)), (want_closed, want_open, want_closed + want_open),
       f"{name} still has {want_closed} closed and {want_open} open")

book = copy.deepcopy(ledger)
# Session bars the opening-range rule would take. Times are UTC, summer hours.
def m5(hhmm, o, h, l, c):
    return {"t": f"2026-09-18T{hhmm}:00Z", "o": o, "h": h, "l": l, "c": c, "v": 100000}

session = [m5(*row) for row in (
    ("13:30", 100, 102, 100, 101), ("13:35", 101, 102, 100, 101),
    ("13:40", 101, 102, 100, 100.5), ("13:45", 100.5, 101, 100, 100.8),
    ("13:50", 100.8, 101.5, 100.2, 101), ("13:55", 101, 102, 100.5, 101.5),
    ("14:00", 101.5, 103, 101.4, 102.5), ("14:05", 102.6, 104, 102.5, 103.5),
    ("14:10", 103.5, 105, 103, 104.5), ("19:55", 104.5, 105, 104, 104.8),
)]
flat = []
for i in range(260):
    flat.append(bar(_day(i), 100, 101, 99, 100))
flat[-1] = bar(flat[-1]["t"][:10], 100, 106, 100, 105, v=5_000_000)
flat.append(bar("2025-09-18", 105, 106, 104, 105))
btc = [
    {"t": "2026-09-24T21:00:00Z", "o": 99, "h": 99, "l": 99, "c": 99, "v": 1},
    {"t": "2026-09-24T22:00:00Z", "o": 100, "h": 101, "l": 99, "c": 100.5, "v": 1},
    {"t": "2026-09-24T23:00:00Z", "o": 100.5, "h": 102, "l": 100, "c": 101.8, "v": 1},
    {"t": "2026-09-25T00:00:00Z", "o": 102, "h": 102, "l": 101, "c": 101.5, "v": 1},
]
MT.scan({"AAA": flat, "SPY": flat}, book, rules=MT.RULES)
MT.scan_day({"AAA": session, "SPY": session}, book, rules=MT.RULES)
MT.scan_hours({"BTC/USD": btc}, book, rules=MT.RULES, research_before="2026-09-19")
fresh = {"trades": [], "meta": {}}
MT.scan_day({"AAA": session, "SPY": session}, fresh, rules=MT.RULES)
MT.scan_hours({"BTC/USD": btc}, fresh, research_before="2026-09-19")
MT.scan({"AAA": flat}, fresh, rules=MT.RULES)
by_id_before = {t["id"]: t for t in snapshot if t.get("rule") in set(EIGHT)}
by_id_after = {t["id"]: t for t in book["trades"] if t.get("rule") in set(EIGHT)}
eq(set(by_id_after), set(by_id_before), "no removed rule gains or loses a trade id")
eq(by_id_after, by_id_before, "every removed rule's trades keep the same content")
eq([t for t in fresh["trades"] if t.get("rule") in set(EIGHT)], [],
   "a fresh book logs nothing on the eight, even when the scan is handed every rule")

open_row = next(t for t in snapshot if t.get("rule") == "sw_52w_breakout" and t.get("status") == "open")
grade_book = {"trades": [copy.deepcopy(open_row)], "meta": {}}
entry = open_row["entry_day"]
bars = [bar(entry, 100, 101, 99, 100)]
for i in range(1, 45):
    day = (datetime.date.fromisoformat(entry) + datetime.timedelta(days=i)).isoformat()
    bars.append(bar(day, 50, 51, 40, 45))
before_grade = copy.deepcopy(grade_book["trades"][0])
MT.grade({open_row["symbol"]: bars, "SPY": bars}, grade_book)
eq(grade_book["trades"][0], before_grade, "grading leaves an open removed trade unchanged")

print("\na rule still on the board still enters and still renders")
kept_book = {"trades": [], "meta": {}}
rise = []
for i in range(215):
    p = 100 + i * 0.1
    rise.append(bar(_day(i), p, p * 1.01, p * 0.99, p))
rise.append(bar("2025-08-04", 121.0, 122, 118, 118.5))   # a 7-day closing low above the 200-day: Double 7s
rise.append(bar("2025-08-05", 118.6, 119, 118, 118.8))   # the next open it enters at
n_kept = MT.scan({"SPY": rise}, kept_book)
ok(n_kept > 0 and all(t.get("rule") in MT.ACTIVE for t in kept_book["trades"]),
   "a rule still on the board still logs a trade")
ok(all(t.get("rule") not in set(EIGHT) for t in kept_book["trades"]),
   "that same scan does not log one of the eight")

print("\nthe eight are hidden on every built page, and an empty lane is not")
pages = _pages()
labels = {name: MT.RULES[name]["label"] for name in EIGHT}
for name, html in pages.items():
    hit = next((rule for rule in EIGHT if rule in html), None)
    if hit is None:
        hit = next((labels[rule] for rule in EIGHT if labels[rule] in html), None)
    ok(hit is None, f"{name} does not show a removed trading rule" + (f" ({hit})" if hit else ""))
trading = pages["trading.html"]
ok(MT.RULES[KEPT]["label"] in trading, "a rule still on the board is on the trading page")
logged, opened = _board_tiles(snapshot)
ok(f'<div class="tile"><b>{logged:,}</b><span>trades logged</span></div>' in trading
   and f'<div class="tile"><b>{opened:,}</b><span>open now</span></div>' in trading,
   "the trading headline counts only the rules still on the board")

saved_rules = MT.RULES
try:
    MT.RULES = dict(saved_rules)
    MT.RULES["zz_empty_untested"] = dict(
        lane="swing", label="Empty untested lane",
        signal=lambda h: False, exit=lambda _after, _entry: None,
        note="Registered with no trades. Emptiness is not removal.",
    )
    shown = SB.trading_page(NOW)
finally:
    MT.RULES = saved_rules
ok("Empty untested lane" in shown, "a rule with no trades still renders")
ok("zz_empty_untested" in shown, "and its id is on the page")

print("\nthe four removed 2026-10-20 are exit-only; the eight before them are not")
eq(set(getattr(MT, "EXIT_ONLY_RULES", ())), set(EXIT_ONLY), "EXIT_ONLY_RULES is exactly the four")
ok(all(MT.rule_exit_only(n) and MT.rule_removed(n) for n in EXIT_ONLY),
   "each of the four is removed AND exit-only")
ok(not any(MT.rule_exit_only(n) for n in EIGHT if n not in EXIT_ONLY),
   "none of the eight removed 2026-10-04 is exit-only")
ok(not MT.rule_exit_only(KEPT), "a rule on the board is not exit-only")

import market_exec as X


def weekdays(n, first=datetime.date(2026, 1, 5)):
    out, d = [], first
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += datetime.timedelta(days=1)
    return out


# A clean gap-down reversal: a slow rise above the 200-day, then a 5% gap down that closes up.
DAYS = weekdays(260)
gap = [bar(DAYS[i], 100 + i * 0.1, 100 + i * 0.1 + 0.5, 100 + i * 0.1 - 0.5, 100 + i * 0.1)
       for i in range(230)]
pc = gap[-1]["c"]
gap.append(bar(DAYS[230], pc * 0.95, pc * 0.98, pc * 0.94, pc * 0.97))   # the signal bar
ok(MT._sw_gap_reversal(gap), "the fixture fires sw_gap_down_reversal on its last bar")

print("\nan exit-only rule never opens a new trade")
GAP_RULES = {"sw_gap_down_reversal": MT.RULES["sw_gap_down_reversal"]}
never = {"trades": [], "meta": {}}
with_next = gap + [bar(DAYS[231], pc * 0.97, pc * 0.99, pc * 0.96, pc * 0.98)]
eq(MT.scan({"STLD": with_next}, never, rules=GAP_RULES), 0,
   "scan logs nothing for it when its signal fires with the next open in")
MT.scan({"STLD": with_next}, never, rules=MT.RULES)
eq([t["rule"] for t in never["trades"] if MT.rule_removed(t["rule"])], [],
   "nor when handed every rule (a rule on the board may still take it)")
eq(X.pending_entries({"STLD": gap}, never, rules=GAP_RULES), [],
   "market_exec plans no entry for it on a last-bar signal")
eq(X.pending_entries({"STLD": gap}, never), [], "nor from the full rule set")
ok("sw_gap_down_reversal" in X.executable_rules()[1]
   and "sw_gap_down_reversal" not in X.executable_rules()[0],
   "it is still not an executable (entry) rule")
ok(set(EXIT_ONLY) - {"etf_overnight"} <= set(X.exit_rules()),
   "its exits are sent (exit_rules) — etf_overnight aside, which never bought at Alpaca")
ok(not any(n in X.exit_rules() for n in EIGHT if n not in EXIT_ONLY),
   "the eight removed 2026-10-04 get no exits either")

print("\nan exit-only rule exits its open trades on its own schedule")


def open_row(rule, sym, entry_day, entry=100.0):
    return dict(id=MT.trade_id(rule, sym, "sig"), rule=rule, lane="swing", symbol=sym,
                signal_day="sig", entry_day=entry_day, entry=entry, status="open", exit=None,
                exit_day=None, ret_gross=None, ret_net=None, bench_ret=None, bars_held=None)


def flat_bars(days, px=100.0):
    return [bar(d, px, px + 1, px - 1, px) for d in days]


E = 210
sw = flat_bars(DAYS[:E + 1 + 5])                     # entry day + 5 sessions after it
book_sw = {"trades": [open_row("sw_gap_down_reversal", "DELL", DAYS[E])], "meta": {}}
eq(MT.grade({"DELL": sw, "SPY": sw}, book_sw), 0, "after 5 sessions the row is still open")
pend = X.pending_exits({"DELL": sw}, book_sw)
eq([(p["symbol"], p["action"]) for p in pend], [("DELL", "sell")],
   "and market_exec queues its sell for the next open that evening")
sw6 = flat_bars(DAYS[:E + 1 + 6])
eq(MT.grade({"DELL": sw6, "SPY": sw6}, book_sw), 1, "the next run closes it")
t = book_sw["trades"][0]
eq((t["status"], t["exit_day"], t["bars_held"]), ("closed", DAYS[E + 6], 5),
   "at the open after 5 sessions held, as registered")
eq(X.pending_exits({"DELL": sw6}, book_sw), [], "and no second sell is planned")

ibs = flat_bars(DAYS[:E + 1 + 3])
ibs[E + 3] = bar(DAYS[E + 3], 100, 102, 99, 101.5)  # first close above the prior day's high
book_ibs = {"trades": [open_row("etf_ibs_band", "IWM", DAYS[E])], "meta": {}}
eq(X.pending_exits({"IWM": ibs}, book_ibs)[0]["symbol"], "IWM",
   "etf_ibs_band sells the evening of the first close above the prior high")
ibs.append(bar(DAYS[E + 4], 101, 101, 101, 101))
eq(MT.grade({"IWM": ibs, "SPY": ibs}, book_ibs), 1, "and the ledger closes it the next run")
eq(book_ibs["trades"][0]["exit_day"], DAYS[E + 4], "at that next open")
cap = flat_bars(DAYS[:E + 1 + 11])
book_cap = {"trades": [open_row("etf_ibs_band", "QQQ", DAYS[E])], "meta": {}}
MT.grade({"QQQ": cap, "SPY": cap}, book_cap)
eq((book_cap["trades"][0]["status"], book_cap["trades"][0]["bars_held"]), ("closed", 10),
   "with no trigger it leaves after 10 sessions")

print("\nthe account side: the sell goes out, a buy never does, an orphan is sold after 5 sessions")
_saved = (X.positions, X.account, X.exchange_orders)
try:
    # The DELL row due tonight is held 2 shares; STLD is a filled buy with no ledger row (the
    # order sent the evening before the rule came off); a fresh gap signal also fires tonight.
    stld_tid = MT.trade_id("sw_gap_down_reversal", "STLD", DAYS[E - 1])
    stld_cid = X.client_order_id(stld_tid, "buy")
    dell_tid = book_sw["trades"][0]["id"]
    EXO = {X.client_order_id(dell_tid, "buy"): {"side": "buy", "symbol": "DELL",
                                                "status": "filled", "filled_qty": "2"},
           stld_cid: {"side": "buy", "symbol": "STLD", "status": "filled", "filled_qty": "4",
                      "filled_avg_price": "100", "filled_at": DAYS[E] + "T13:30:01Z"}}
    X.exchange_orders = lambda days=120: EXO
    X.positions = lambda: {"DELL": {"qty": "2"}, "STLD": {"qty": "4"}}
    X.account = lambda: {"cash": "50000", "equity": "100000", "last_equity": "100000"}
    st = {"orders": [], "meta": {}}
    live_row = open_row("sw_gap_down_reversal", "DELL", DAYS[E])
    led = {"trades": [live_row], "meta": {}}
    stld4 = flat_bars(DAYS[:E + 1 + 4])
    orders, refused = X.plan({"DELL": sw, "STLD": stld4, "GGG": gap}, led, state=st)
    eq([(o["symbol"], o["action"], o["qty"]) for o in orders if o["action"] == "sell"],
       [("DELL", "sell", 2)], "4 sessions after entry: DELL's scheduled sell, no orphan sell yet")
    ok(not [o for o in orders + refused if o["action"] == "buy" and MT.rule_removed(o["rule"])],
       "no entry is planned or refused for the exit-only rule at all")
    ok(any(o["action"] == "buy" and o["rule"] == KEPT for o in orders),
       "while a rule on the board still buys the same bar")
    stld5 = flat_bars(DAYS[:E + 1 + 5])
    orders, refused = X.plan({"DELL": sw, "STLD": stld5, "GGG": gap}, led, state=st)
    got = {(o["symbol"], o["action"], o["qty"]) for o in orders if o["action"] == "sell"}
    eq(got, {("DELL", "sell", 2), ("STLD", "sell", 4)},
       "5 sessions after entry the orphan STLD is sold too, all 4 shares")
    orph = next(o for o in orders if o["symbol"] == "STLD")
    eq((orph["id"], orph.get("orphan")), (stld_tid, True),
       "under the trade id its buy was sent with, marked as an orphan")
    ok("orphan fill, no ledger row" in orph.get("note", "") and "5 session" in orph["note"],
       "and the reason is recorded with it")
    EXO[X.client_order_id(stld_tid, "sell")] = {"side": "sell", "symbol": "STLD",
                                                "status": "accepted", "filled_qty": "0"}
    orders, refused = X.plan({"DELL": sw, "STLD": stld5}, led, state=st)
    eq([o["symbol"] for o in orders], ["DELL"], "once its sell is placed the orphan is not re-sold")
    ok(not [r for r in refused if r["symbol"] == "STLD"], "and is not reported every night")
    # A missed run: the ledger closed DELL without its sell going out. Sold late, not stranded.
    closed_row = dict(live_row, status="closed", exit_day="2026-10-22", exit=100.0)
    orders, _ = X.plan({"DELL": sw6}, {"trades": [closed_row], "meta": {}}, state=st)
    eq([(o["symbol"], o.get("overdue")) for o in orders], [("DELL", True)],
       "an exit-only row closed with no sell placed is sold the next run")
    EXO[X.client_order_id(dell_tid, "sell")] = {"side": "sell", "symbol": "DELL",
                                                "status": "filled", "filled_qty": "2"}
    orders, refused = X.plan({"DELL": sw6}, {"trades": [closed_row], "meta": {}}, state=st)
    eq((orders, refused), ([], []), "once sold, the rule is dormant: nothing planned, nothing noted")
    # The fill check names the orphan and counts it as held until its sell fills.
    del EXO[X.client_order_id(stld_tid, "sell")]
    rep = X.reconcile(d=led)
    o_row = next(o for o in rep["orphans"] if o["symbol"] == "STLD")
    eq((o_row.get("rule"), o_row.get("id"), o_row.get("exit_only")),
       ("sw_gap_down_reversal", stld_tid, True), "the fill check names the orphan's rule")
    held = {h["symbol"]: h["qty"] for h in rep["held"]}
    eq(held.get("STLD"), 4, "and counts its 4 shares as held")
    EXO[X.client_order_id(stld_tid, "sell")] = {"side": "sell", "symbol": "STLD",
                                                "status": "filled", "filled_qty": "4",
                                                "filled_at": DAYS[E + 6] + "T13:30:02Z"}
    rep = X.reconcile(d=led)
    ok("STLD" not in {h["symbol"] for h in rep["held"]}, "until its sell fills")
    # The live pilot trades sw_rsi2_pullback alone: no exit-only rule is ever sold there.
    _only = X.ONLY_RULES
    X.ONLY_RULES = {KEPT}
    try:
        ok(not any(MT.rule_exit_only(n) for n in X.exit_rules()),
           "an account limited by ALPACA_RULES sells no exit-only rule")
    finally:
        X.ONLY_RULES = _only
finally:
    X.positions, X.account, X.exchange_orders = _saved

print("\nthe execution line counts the exits without naming the rule")
fills = {"summary": {"orders": {"sent": 3, "filled": 3, "unfilled": 0, "working": 0}, "fills": 0},
         "held": [{"symbol": "DELL", "qty": 2,
                   "rules": [{"rule": "sw_gap_down_reversal", "id": "x", "qty": 2}]}]}
line = SB.trade_exec_html(fills, 3)
ok("removed rule · exiting (3 open)" in line, "it says 'removed rule · exiting (3 open)'")
ok(not any(n in line for n in EIGHT), "and names none of the removed rules")
ok("exiting" not in SB.trade_exec_html(fills, 0), "nothing is said once nothing is open")
eq(MT.exiting({"trades": [open_row("etf_ibs_band", "IWM", "d"), open_row("sw_52w_breakout", "A", "d"),
                          dict(open_row("sw_gap_down_reversal", "B", "d"), status="closed")]}), 1,
   "exiting() counts only the exit-only rules' open rows")

print(f"\n{'FAILED: ' + str(len(FAILS)) if FAILS else 'trading lane removal passed'}")
for item in FAILS:
    print("   -", item)
sys.exit(1 if FAILS else 0)
