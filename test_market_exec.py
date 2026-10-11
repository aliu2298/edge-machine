#!/usr/bin/env python3
"""test_market_exec.py — the execution half lines up with the record, and cannot overrun it.

The property that matters is COMPLEMENTARITY. market_track deliberately ignores a signal on
the last printed bar (there is no open to enter at yet) and an exit triggered on the last bar
(there is no open to leave at yet). market_exec exists to trade exactly those, and nothing
else. If the two ever disagree, the account and the record drift apart silently — the account
holds a position the ledger never logged, or the ledger logs a trade the account never took.

So each test here pins both sides at once: the case market_exec claims is live is checked to
be a case market_track really does skip, and vice versa.
"""
import sys, os, json, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import market_track as T
import market_exec as X

FAILS = 0


def check(label, got, want):
    global FAILS
    ok = got == want
    if not ok:
        FAILS += 1
    print(f"  {'ok  ' if ok else 'FAIL'}  {label}" + ("" if ok else f"\n          got {got!r}\n         want {want!r}"))


def bars(n=215, close=100.0, last=None):
    """n daily bars, flat, with an optional different close on the final bar."""
    out = []
    day = datetime.date(2026, 1, 1)
    for i in range(n):
        c = close if (last is None or i < n - 1) else last
        out.append({"t": (day + datetime.timedelta(days=i)).isoformat(),
                    "o": c, "h": c, "l": c, "c": c, "v": 5_000_000})
    return out


# A rule whose signal fires ONLY on a bar closing at 99 — so we control exactly which bar it
# sees, instead of reverse-engineering a real rule's thresholds.
def _sig99(h):
    return h[-1]["c"] == 99.0


def _exit_never(after, entry):
    return None


def _exit_on_last(after, entry):
    return len(after) - 1 if after else None


RULES = {
    "t_open": dict(lane="swing", universe=["AAA"], signal=_sig99, exit=_exit_never,
                   entry="open", label="test", note="test"),
}
EXIT_RULES = {
    "t_exit": dict(lane="swing", universe=["AAA"], signal=lambda h: False, exit=_exit_on_last,
                   entry="open", label="test", note="test"),
}


print("which rules may be executed at all")
ok, skipped = X.executable_rules()
check("etf_overnight is excluded", "etf_overnight" in skipped, True)
check("  ...because it enters at the close",
      "close" in skipped.get("etf_overnight", ""), True)
check("the open-entry swing rules are executable",
      sorted(ok) == sorted(n for n, r in T.RULES.items()
                           if not T.rule_removed(n) and r.get("lane") == "swing"
                           and r.get("entry") != "close" and r.get("signal")), True)
check("nothing executable enters at the close",
      [n for n, r in ok.items() if r.get("entry") == "close"], [])
check("nothing executable is off the swing lane",
      [n for n, r in ok.items() if r.get("lane") != "swing"], [])


print("\nan ENTRY signal on the last bar: the record skips it, execution takes it")
b = {"AAA": bars(last=99.0)}
d = {"trades": [], "meta": {}}
logged = T.scan(b, d, rules=RULES, research_before=None)
check("market_track logs nothing (no open to enter at yet)", (logged, len(d["trades"])), (0, 0))
pend = X.pending_entries(b, d, rules=RULES)
check("market_exec sees exactly one entry", len(pend), 1)
check("  for the right symbol and side", (pend[0]["symbol"], pend[0]["action"]), ("AAA", "buy"))
check("  with the id market_track will use tomorrow",
      pend[0]["id"], T.trade_id("t_open", "AAA", T._day(b["AAA"][-1])))

print("\nthe same signal one bar earlier: the record takes it, execution leaves it alone")
b2raw = bars(last=99.0)
b2raw.append(dict(b2raw[-1], t="2026-12-31", c=100.0, o=100.0, h=100.0, l=100.0))
b2 = {"AAA": b2raw}
d2 = {"trades": [], "meta": {}}
logged2 = T.scan(b2, d2, rules=RULES, research_before=None)
check("market_track logs it", logged2, 1)
check("market_exec does NOT (it is already in the record)",
      len(X.pending_entries(b2, d2, rules=RULES)), 0)
check("no double-trade: logged + pending == 1 in both arrangements",
      (logged + len(pend), logged2 + len(X.pending_entries(b2, d2, rules=RULES))), (1, 1))

print("\nan already-logged signal is never re-sent")
check("a trade already in the ledger is skipped",
      len(X.pending_entries(b, {"trades": [{"id": pend[0]["id"], "status": "open"}], "meta": {}},
                            rules=RULES)), 0)


print("\nan EXIT triggered on the last bar: the record holds, execution sells")
bx = {"AAA": bars(n=215)}
entry_day = T._day(bx["AAA"][200])
led = {"trades": [dict(id="t_exit|AAA|x", rule="t_exit", lane="swing", symbol="AAA",
                       entry_day=entry_day, entry=100.0, status="open", exit=None,
                       exit_day=None, ret_gross=None, ret_net=None, bench_ret=None,
                       bars_held=None, signal_day=entry_day)], "meta": {}}
closed = T.grade(bx, led, rules=EXIT_RULES)
check("market_track leaves it open (no open to leave at yet)",
      (closed, led["trades"][0]["status"]), (0, "open"))
pex = X.pending_exits(bx, led, rules=EXIT_RULES)
check("market_exec sees exactly one exit", len(pex), 1)
check("  for the right trade and side", (pex[0]["id"], pex[0]["action"]), ("t_exit|AAA|x", "sell"))

print("\nan exit with a bar still to come belongs to the record, not to execution")
bx2 = {"AAA": bars(n=216)}
led2 = json.loads(json.dumps(led))
led2["trades"][0]["status"] = "open"


def _exit_second_to_last(after, entry):
    return len(after) - 2 if len(after) > 1 else None


R2 = {"t_exit": dict(EXIT_RULES["t_exit"], exit=_exit_second_to_last)}
closed2 = T.grade(bx2, led2, rules=R2)
check("market_track closes it", (closed2, led2["trades"][0]["status"]), (1, "closed"))
check("market_exec does not also sell it",
      len(X.pending_exits(bx2, led2, rules=R2)), 0)


# The case the test above could not see: grade() had already flipped the status to "closed",
# so the status check was masking the length guard. A trade that is STILL OPEN but whose exit
# triggered a bar ago belongs to grade(), which will close it at the open that printed — if
# market_exec also sold it, the account would leave at tomorrow's open and the ledger at
# yesterday's, and the two records would drift apart with nothing reporting it.
print("\nan exit that triggered BEFORE the last bar is grade's, even while still open")
bx3 = {"AAA": bars(n=216)}
led3 = {"trades": [dict(id="t_exit|AAA|x", rule="t_exit", lane="swing", symbol="AAA",
                        entry_day=T._day(bx3["AAA"][200]), entry=100.0, status="open",
                        exit=None, exit_day=None, ret_gross=None, ret_net=None,
                        bench_ret=None, bars_held=None,
                        signal_day=T._day(bx3["AAA"][200]))], "meta": {}}
R3 = {"t_exit": dict(EXIT_RULES["t_exit"], exit=_exit_second_to_last)}
check("the trade is still open in the ledger", led3["trades"][0]["status"], "open")
check("market_exec leaves it to grade", len(X.pending_exits(bx3, led3, rules=R3)), 0)
# ...and only takes it when the trigger really is the last bar.
check("while a last-bar trigger IS taken",
      len(X.pending_exits(bx3, led3, rules=EXIT_RULES)), 1)


print("\ntwo rules in the same name: one leaving does not close the other")
# The ledger logs these as two independent trades and grades them separately. The ACCOUNT has
# one position. Selling the account's whole position when one rule exits would close a trade
# the record still has open, and the two would drift apart with nothing reporting it.
st = {"orders": [
    dict(id="rule_a|DAL|2026-10-09", action="buy", symbol="DAL", qty=12,
         status="filled", filled_qty=12),
    dict(id="rule_b|DAL|2026-10-09", action="buy", symbol="DAL", qty=12,
         status="filled", filled_qty=12),
], "meta": {}}
check("this module tracks shares per TRADE, not per symbol",
      X.held_by_trade(st), {"rule_a|DAL|2026-10-09": 12, "rule_b|DAL|2026-10-09": 12})

_real_pos, _real_acct, _real_pex = X.positions, X.account, X.pending_exits
_real_ex = X.exchange_orders
X.exchange_orders = lambda days=120: {}
X.positions = lambda: {"DAL": {"qty": "24"}}          # the account's single 24-share position
X.account = lambda: {"cash": "50000"}
X.pending_exits = lambda b, d, r=None: [dict(id="rule_a|DAL|2026-10-09", rule="rule_a",
                                             symbol="DAL", action="sell", ref_price=82.0)]
X.pending_entries_real = X.pending_entries
X.pending_entries = lambda b, d, r=None: []
try:
    orders, refused = X.plan({}, {"trades": [], "meta": {}}, state=st)
    check("only rule_a's shares are sold", [(o["symbol"], o["qty"]) for o in orders], [("DAL", 12)])
    check("  not the whole 24-share position",
          any(o["qty"] == 24 for o in orders), False)
    # And a sell for a trade this module never filled is refused by name, not guessed at.
    X.pending_exits = lambda b, d, r=None: [dict(id="never|XYZ|2026-10-09", rule="r",
                                                 symbol="XYZ", action="sell", ref_price=10.0)]
    orders2, refused2 = X.plan({}, {"trades": [], "meta": {}}, state=st)
    check("a trade this module never bought is refused, not sold",
          (len(orders2), (refused2[0]["reason"] if refused2 else "NOTHING REFUSED")),
          (0, "never bought, here or at the broker"))
finally:
    X.positions, X.account, X.pending_exits = _real_pos, _real_acct, _real_pex
    X.pending_entries = X.pending_entries_real
    X.exchange_orders = _real_ex


print("\na trade bought on ANOTHER host is still sellable here")
# data/market_orders.json is per host and gitignored, so a buy placed from a laptop is invisible
# to the VPS. The client_order_id is a pure function of (trade, side), so the broker's own order
# list answers "was this bought?" for every host. Without this the VPS would refuse every exit
# for those trades and the positions would sit open while the ledger recorded a clean exit.
TID = "rule_x|GOOG|2026-10-09"
elsewhere = {X.client_order_id(TID, "buy"): {"status": "filled", "filled_qty": "7",
                                             "symbol": "GOOG"}}
_p2, _a2, _e2, _x2 = X.positions, X.account, X.pending_exits, X.exchange_orders
X.positions = lambda: {"GOOG": {"qty": "7"}}
X.account = lambda: {"cash": "50000"}
X.pending_exits = lambda b, d, r=None: [dict(id=TID, rule="rule_x", symbol="GOOG",
                                             action="sell", ref_price=180.0)]
_pe2 = X.pending_entries
X.pending_entries = lambda b, d, r=None: []
try:
    empty = {"orders": [], "meta": {}}          # this host has never seen the trade
    X.exchange_orders = lambda days=120: {}
    o_none, r_none = X.plan({}, {"trades": [], "meta": {}}, state=empty)
    check("with nothing at the broker it is refused",
          (len(o_none), (r_none[0]["reason"] if r_none else "NOTHING REFUSED")),
          (0, "never bought, here or at the broker"))
    X.exchange_orders = lambda days=120: elsewhere
    o_ex, _ = X.plan({}, {"trades": [], "meta": {}}, state=empty)
    check("but the broker's filled buy makes it sellable",
          [(o["symbol"], o["qty"]) for o in o_ex], [("GOOG", 7)])
    # The entry side of the same problem, and the one that happens first: the VPS runs with an
    # empty state file while orders placed from elsewhere are live at the broker. Without this
    # it re-plans every one of them, and only the duplicate client_order_id stops the send —
    # after the dry run has already announced orders it was never going to place.
    X.pending_entries = lambda b, d, r=None: [dict(id=TID, rule="rule_x", symbol="GOOG",
                                                   action="buy", ref_price=180.0)]
    X.pending_exits = lambda b, d, r=None: []
    X.positions = lambda: {}
    X.exchange_orders = lambda days=120: {}
    o_fresh, _ = X.plan({}, {"trades": [], "meta": {}}, state=empty)
    check("with nothing at the broker the buy is planned", len(o_fresh), 1)
    X.exchange_orders = lambda days=120: {X.client_order_id(TID, "buy"): {"status": "accepted"}}
    o_known, r_known = X.plan({}, {"trades": [], "meta": {}}, state=empty)
    check("a buy live at the broker is not planned again",
          (len(o_known), (r_known[0]["reason"] if r_known else "NOTHING REFUSED")),
          (0, "already bought or queued"))
    # A cancelled order at the broker is not a commitment — the trade may be entered again.
    X.exchange_orders = lambda days=120: {X.client_order_id(TID, "buy"): {"status": "canceled"}}
    o_cxl, _ = X.plan({}, {"trades": [], "meta": {}}, state=empty)
    check("a CANCELLED broker order does not block it", len(o_cxl), 1)
    X.pending_entries = lambda b, d, r=None: []
    X.pending_exits = lambda b, d, r=None: [dict(id=TID, rule="rule_x", symbol="GOOG",
                                                 action="sell", ref_price=180.0)]
    X.positions = lambda: {"GOOG": {"qty": "7"}}
    # ...and a sell already placed from the other host is not placed twice.
    both = dict(elsewhere); both[X.client_order_id(TID, "sell")] = {"status": "accepted"}
    X.exchange_orders = lambda days=120: both
    o_dup, r_dup = X.plan({}, {"trades": [], "meta": {}}, state=empty)
    check("a sell already placed elsewhere is not repeated",
          (len(o_dup), (r_dup[0]["reason"] if r_dup else "NOTHING REFUSED")),
          (0, "a sell for this trade is already placed"))
finally:
    X.positions, X.account, X.pending_exits, X.exchange_orders = _p2, _a2, _e2, _x2
    X.pending_entries = _pe2


print("\nan accepted-but-unfilled order is not re-planned")
# A market-on-open order sits accepted and unfilled from the evening it is sent until the open.
# It holds zero shares and is a real order. Planning on shares alone would re-plan it on every
# run between those two moments, and only the client_order_id would stop the second send —
# while the dry run cheerfully described an order it was never going to place.
queued = {"orders": [dict(id="r|DAL|2026-10-09", action="buy", symbol="DAL", qty=12,
                          status="accepted", filled_qty=0)], "meta": {}}
check("it holds no shares yet", X.held_by_trade(queued), {})
check("but it IS committed", X.committed(queued, "buy"), {"r|DAL|2026-10-09"})
_rp, _ra, _rpe, _rpn = X.positions, X.account, X.pending_exits, X.pending_entries
_rex = X.exchange_orders
X.exchange_orders = lambda days=120: {}
X.positions = lambda: {}
X.account = lambda: {"cash": "50000"}
X.pending_exits = lambda b, d, r=None: []
X.pending_entries = lambda b, d, r=None: [dict(id="r|DAL|2026-10-09", rule="r", symbol="DAL",
                                               action="buy", ref_price=82.0)]
try:
    orders, refused = X.plan({}, {"trades": [], "meta": {}}, state=queued)
    check("so it is refused, not sent again",
          (len(orders), (refused[0]["reason"] if refused else "NOTHING REFUSED")),
          (0, "already bought or queued"))
finally:
    X.positions, X.account, X.pending_exits, X.pending_entries = _rp, _ra, _rpe, _rpn
    X.exchange_orders = _rex

print("\nsizing and caps")
check("whole shares near the notional", X.size({"ref_price": 100.0}, 1e9),
      int(X.NOTIONAL_USD // 100.0))
check("a share dearer than the notional is refused", X.size({"ref_price": 99999.0}, 1e9), 0)
check("no cash, no order", X.size({"ref_price": 100.0}, 10.0), 0)
check("a nonsense price is refused, not divided by", X.size({"ref_price": 0.0}, 1e9), 0)


print("\nthe order id is stable, and differs per side")
a1 = X.client_order_id("r|S|2026-10-09", "buy")
a2 = X.client_order_id("r|S|2026-10-09", "buy")
b1 = X.client_order_id("r|S|2026-10-09", "sell")
check("same trade and side -> same id (Alpaca then refuses the repeat)", a1, a2)
check("buy and sell are different ids", a1 == b1, False)
check("it fits Alpaca's 128-char limit", len(a1) <= 128, True)


print("\nthe ledger is never written by execution")
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "market_exec.py")).read()
check("market_exec never calls market_track.save", "T.save" in src or "track.save" in src, False)
check("market_exec writes only its own state file",
      [ln for ln in src.splitlines() if "open(" in ln and "\"w\"" in ln and "STATE" not in ln
       and "tmp" not in ln], [])

print("\ndefaults are paper, and live takes a deliberate act")
os.environ.pop("ALPACA_LIVE", None)
check("paper by default", X.live(), False)
os.environ["ALPACA_LIVE"] = "1"
check("ALPACA_LIVE=1 switches hosts", X.live(), True)
os.environ.pop("ALPACA_LIVE", None)
check("and back", X.host(), X.PAPER_HOST)

print(f"\n{'ALL PASS' if not FAILS else str(FAILS) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
