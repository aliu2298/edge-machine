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

print("\nloss caps halt BUYING and never halt selling")
# A cap that blocked exits would lock the account into the very positions it exists to limit.
# Each rule's exit is the only thing that ends a trade — there is no stop-loss underneath it —
# so a halted sell is a position held indefinitely while the ledger records a clean exit.
st0 = {"orders": [], "meta": {}}
ok, why = X.risk({"equity": "100000", "last_equity": "100000"}, dict(st0, meta={}))
check("a flat day is fine", (ok, why), (True, []))
ok, why = X.risk({"equity": "96000", "last_equity": "100000"}, {"orders": [], "meta": {}})
check("a 4% daily loss trips the 3% cap", (ok, len(why)), (False, 1))
ok, why = X.risk({"equity": "97500", "last_equity": "100000"}, {"orders": [], "meta": {}})
check("a 2.5% daily loss does not", (ok, why), (True, []))
# Drawdown runs off a high-water mark this module keeps as it goes.
m = {"orders": [], "meta": {"high_water": 120000}}
ok, why = X.risk({"equity": "100000", "last_equity": "100000"}, m)
check("16% off the high-water mark trips the 15% cap", ok, False)
check("  and the high-water mark is kept", m["meta"]["high_water"], 120000)
m2 = {"orders": [], "meta": {"high_water": 100}}
X.risk({"equity": "100000", "last_equity": "100000"}, m2)
check("  and raised by a new high", m2["meta"]["high_water"], 100000.0)
ok, why = X.risk({"equity": "100000", "last_equity": "100000", "trading_blocked": True},
                 {"orders": [], "meta": {}})
check("a broker block stops buying too", ok, False)

# The whole point: with the cap tripped, entries are refused and exits still go out.
_p4, _a4, _e4, _pe4, _x4 = X.positions, X.account, X.pending_exits, X.pending_entries, X.exchange_orders
TID4 = "r|CCC|2026-10-09"
X.account = lambda: {"equity": "90000", "last_equity": "100000", "cash": "50000"}
X.positions = lambda: {"CCC": {"qty": "5"}}
X.exchange_orders = lambda days=120: {X.client_order_id(TID4, "buy"): {"status": "filled",
                                                                      "filled_qty": "5"}}
X.pending_entries = lambda b, d, r=None: [dict(id="r|DDD|2026-10-09", rule="r", symbol="DDD",
                                               action="buy", ref_price=50.0)]
X.pending_exits = lambda b, d, r=None: [dict(id=TID4, rule="r", symbol="CCC",
                                             action="sell", ref_price=50.0)]
try:
    o, r = X.plan({}, {"trades": [], "meta": {}}, state={"orders": [], "meta": {}})
    check("with the cap tripped, the BUY is refused",
          [x["reason"] for x in r if x["action"] == "buy"][:1], ["LOSS CAP: down 10.00% today, cap 3.0%"])
    check("...and the SELL still goes out",
          [(x["symbol"], x["qty"]) for x in o], [("CCC", 5)])
finally:
    X.positions, X.account, X.pending_exits = _p4, _a4, _e4
    X.pending_entries, X.exchange_orders = _pe4, _x4


print("\nlive keys are separate from paper keys")
# Stub both key reads: the CI runner has no ~/.alpaca-credentials, and a machine that
# later stores live keys must not change what these checks see.
_creds0, _live0 = X.M._creds, X._live_creds
X.M._creds = lambda: ("PKTEST", "paper-secret")
X._live_creds = lambda: (None, None)
check("live is not configured until live keys are stored", X.live_configured(), False)
os.environ["ALPACA_LIVE"] = "1"
try:
    X._headers()
    check("ALPACA_LIVE=1 without live keys is refused", "no error", "RuntimeError")
except RuntimeError as e:
    check("ALPACA_LIVE=1 without live keys is refused, by name",
          "live keys" in str(e) and "paper keys are deliberately not reused" in str(e), True)
finally:
    os.environ.pop("ALPACA_LIVE", None)
check("and paper still works", X._headers().get("APCA-API-KEY-ID"), "PKTEST")
X.M._creds, X._live_creds = _creds0, _live0


print("\nrisk limits can be overridden, but never silently")
check("a sane override is taken", X._num("T_OVR_A", 5.0), 5.0)
os.environ["T_OVR_A"] = "250"
check("  from the environment", X._num("T_OVR_A", 5.0), 250.0)
os.environ["T_OVR_A"] = "0"
check("zero falls back to the default (0 would size every order to nothing)",
      X._num("T_OVR_A", 5.0), 5.0)
os.environ["T_OVR_A"] = "-10"
check("a negative falls back too", X._num("T_OVR_A", 5.0), 5.0)
os.environ["T_OVR_A"] = "not a number"
check("so does nonsense, rather than crashing the run", X._num("T_OVR_A", 5.0), 5.0)
os.environ.pop("T_OVR_A", None)


print("\nreconciliation: what the broker filled v what the record says")
# Every net return and every verdict in the lane rests on COST_BPS_PER_SIDE being roughly
# right, and nothing measured it until now. The sign convention is the part that is easy to
# get backwards: ADVERSE must be positive on both sides, or a bad entry and a bad exit cancel
# out and the report says the costs are fine.
LED = {"trades": [
    dict(id="r1|AAA|2026-10-09", rule="r1", symbol="AAA", entry=100.0, exit=110.0,
         entry_day="2026-10-10", exit_day="2026-10-14", status="closed"),
    dict(id="r2|BBB|2026-10-09", rule="r2", symbol="BBB", entry=50.0, exit=None,
         entry_day="2026-10-10", exit_day=None, status="open"),
], "meta": {}}


def _ord(status="filled", px=None, qty=None, sym="AAA", side="buy"):
    qty = (10 if status == "filled" else 0) if qty is None else qty
    return {"status": status, "filled_avg_price": (str(px) if px is not None else None),
            "filled_qty": str(qty), "symbol": sym, "side": side, "filled_at": "2026-10-10T13:30:00Z"}


EX = {
    # bought at 100.10 against a recorded open of 100.00 -> paid 10bp MORE: adverse
    X.client_order_id("r1|AAA|2026-10-09", "buy"): _ord(px=100.10),
    # sold at 109.89 against a recorded open of 110.00 -> got 10bp LESS: also adverse
    X.client_order_id("r1|AAA|2026-10-09", "sell"): _ord(px=109.89, side="sell"),
    # still working
    X.client_order_id("r2|BBB|2026-10-09", "buy"): _ord(status="accepted", px=None, sym="BBB"),
    # a fill no ledger trade claims
    "em-" + str(__import__("uuid").uuid5(X.NS, "ghost|ZZZ|2026-10-09|buy")): _ord(px=7.0, sym="ZZZ"),
}
_rex3 = X.exchange_orders
X.exchange_orders = lambda days=120: EX
try:
    rep = X.reconcile(LED)
    by = {(r["id"], r["side"]): r for r in rep["rows"]}
    buy = by[("r1|AAA|2026-10-09", "buy")]
    sell = by[("r1|AAA|2026-10-09", "sell")]
    check("paying ABOVE the recorded open is adverse (positive)", buy["slip_bps"], 10.0)
    check("selling BELOW the recorded open is adverse (positive too)", sell["slip_bps"], 10.0)
    check("  so a bad entry and a bad exit ADD, they do not cancel",
          round(buy["slip_bps"] + sell["slip_bps"], 2), 20.0)
    check("an unfilled order is counted, not measured",
          (by[("r2|BBB|2026-10-09", "buy")]["status"],
           by[("r2|BBB|2026-10-09", "buy")]["slip_bps"]), ("accepted", None))
    check("summary counts fills and unfilled separately",
          (rep["summary"]["fills"], rep["summary"]["unfilled"]), (2, 1))
    check("the mean is over FILLED sides only", rep["summary"]["mean_bps"], 10.0)
    check("per-rule breakdown", rep["summary"]["by_rule"]["r1"], {"n": 2, "mean_bps": 10.0})
    check("a fill with no trade behind it is an ORPHAN",
          [(o["symbol"], o["qty"]) for o in rep["orphans"]], [("ZZZ", 10)])
    check("  and orphans are not folded into the cost figure", rep["summary"]["orphans"], 1)

    # IN FLIGHT v ORPHAN. Between sending an order in the evening and market_track logging it
    # after the next close, an order legitimately has no trade behind it. Calling that an orphan
    # would cry wolf every night; calling a FILLED unmatched order "in flight" would hide the
    # one case that means the account and the record have actually drifted.
    GHOST = "em-" + str(__import__("uuid").uuid5(X.NS, "ghost|QQQ|2026-10-09|buy"))
    X.exchange_orders = lambda days=120: {GHOST: _ord(status="accepted", px=None, sym="QQQ")}
    rp = X.reconcile(LED)
    check("a placed, unfilled, unmatched order is IN FLIGHT",
          (rp["summary"]["in_flight"], rp["summary"]["orphans"]), (1, 0))
    X.exchange_orders = lambda days=120: {GHOST: _ord(status="filled", px=500.0, sym="QQQ")}
    rp = X.reconcile(LED)
    check("the same order once FILLED is an orphan",
          (rp["summary"]["in_flight"], rp["summary"]["orphans"]), (0, 1))
    X.exchange_orders = lambda days=120: {GHOST: _ord(status="canceled", px=None, sym="QQQ")}
    rp = X.reconcile(LED)
    check("a cancelled order is neither",
          (rp["summary"]["in_flight"], rp["summary"]["orphans"]), (0, 0))

    # A favourable fill is negative, so the average is not a one-way ratchet.
    EX2 = {X.client_order_id("r1|AAA|2026-10-09", "buy"): _ord(px=99.90)}
    X.exchange_orders = lambda days=120: EX2
    rep2 = X.reconcile(LED)
    check("buying BELOW the recorded open is favourable (negative)",
          rep2["summary"]["mean_bps"], -10.0)

    # Nothing filled at all must not divide by zero.
    X.exchange_orders = lambda days=120: {}
    rep3 = X.reconcile(LED)
    check("no fills yet is a clean empty report",
          (rep3["summary"]["fills"], rep3["summary"]["mean_bps"], rep3["orphans"]), (0, None, []))

    # Expiry/cancellation does not undo an executed portion of an order.
    for terminal in ("expired", "canceled", "partially_filled"):
        partial = _ord(status=terminal, px=50.05, qty=11, sym="BBB")
        X.exchange_orders = lambda days=120: {
            X.client_order_id("r2|BBB|2026-10-09", "buy"): partial}
        rp = X.reconcile(LED)
        check(f"{terminal} partial fill keeps quantity, price and broker status",
              (rp["rows"][0]["qty"], rp["rows"][0]["fill"], rp["rows"][0]["status"],
               rp["summary"]["fills"], rp["summary"]["unfilled"], rp["summary"]["mean_bps"]),
              (11, 50.05, terminal, 1, 0, 10.0))
        X.exchange_orders = lambda days=120: {GHOST: partial}
        rp = X.reconcile(LED)
        check(f"{terminal} unmatched partial fill is not silently discarded",
              (rp["summary"]["orphans"], rp["orphans"][0]["qty"]), (1, 11))
finally:
    X.exchange_orders = _rex3


print("\norders are day market orders, and a failed send is retried (2026-10-12)")
import tempfile
_state0, _call0, _tif0 = X.STATE, X._call, X.TIME_IN_FORCE
_sent_bodies = []
X.STATE = os.path.join(tempfile.mkdtemp(), "market_orders.json")
try:
    X._call = lambda method, path, body=None: (_sent_bodies.append(body) or {"id": "x1", "status": "accepted"})
    _o = dict(id="r|AAA|2026-10-12", rule="r", symbol="AAA", action="buy", qty=3, ref_price=10.0)
    check("the default time in force is day", X.TIME_IN_FORCE, "day")
    X.submit(_o)
    check("submit sends a market day order", (_sent_bodies[-1]["type"], _sent_bodies[-1]["time_in_force"]),
          ("market", "day"))

    # A send that failed never reached the broker: the next run must try it again.
    _fail = {"n": 0}
    def _refuse(method, path, body=None):
        _fail["n"] += 1
        raise X.AlpacaError(403, "opg orders must be submitted after 7:00pm and before 9:28am")
    X._call = _refuse
    _s, _f = X.place([_o], dry_run=False)
    check("a refused send is recorded as failed", (len(_s), len(_f)), (0, 1))
    X._call = lambda method, path, body=None: {"id": "x2", "status": "accepted"}
    _s, _f = X.place([_o], dry_run=False)
    check("...and the next run sends it again", ([x["status"] for x in _s], len(_f)), (["accepted"], 0))
    _s, _f = X.place([_o], dry_run=False)
    check("...but an accepted order is never sent twice", (len(_s), len(_f)), (0, 0))

    # opg is still available, and is refused by name outside its window without a broker call.
    X.TIME_IN_FORCE = "opg"
    _o2 = dict(_o, id="r|BBB|2026-10-12", symbol="BBB")
    _calls = []
    X._call = lambda method, path, body=None: (_calls.append(body) or {"id": "x3"})
    _real_win = X.opg_window_open
    X.opg_window_open = lambda now=None: False
    try:
        _s, _f = X.place([_o2], dry_run=False)
    finally:
        X.opg_window_open = _real_win
    check("ALPACA_TIF=opg outside 19:00-09:28 ET is refused before the broker is called",
          (len(_s), len(_f), len(_calls), "19:00-09:28" in (_f[0].get("error") or "")), (0, 1, 0, True))
    _ny = lambda h, m: datetime.datetime(2026, 10, 12, h, m, tzinfo=X._NY)
    check("the opg window: 16:10 closed, 19:05 open, 09:20 open, 09:29 closed",
          [X.opg_window_open(_ny(16, 10)), X.opg_window_open(_ny(19, 5)),
           X.opg_window_open(_ny(9, 20)), X.opg_window_open(_ny(9, 29))], [False, True, True, False])
finally:
    X.STATE, X._call, X.TIME_IN_FORCE = _state0, _call0, _tif0


print("\nthe live pilot (2026-10-15): one rule, ranked, fractional, its own state")
import importlib
_env = {k: os.environ.get(k) for k in ("ALPACA_RULES", "ALPACA_FRACTIONAL", "ALPACA_STATE",
                                        "ALPACA_FILLS", "ALPACA_NOTIONAL_USD")}
os.environ.update(ALPACA_RULES="sw_rsi2_pullback", ALPACA_FRACTIONAL="1", ALPACA_NOTIONAL_USD="100",
                  ALPACA_STATE="data/market_orders_live.json", ALPACA_FILLS="data/market_fills_live.json")
L = importlib.reload(X)
try:
    ok_rules, skipped = L.executable_rules()
    check("only sw_rsi2_pullback is executable", sorted(ok_rules), ["sw_rsi2_pullback"])
    check("the others say why", all(v for v in skipped.values()), True)
    check("its own state file", os.path.relpath(L.STATE, L.ROOT), "data/market_orders_live.json")
    check("its own fills file", os.path.relpath(L.FILLS, L.ROOT), "data/market_fills_live.json")
    check("a $226 stock is bought in fractions, rounded down", L.size({"ref_price": 226.0}, 500), 0.442477)
    check("never past the cash", L.size({"ref_price": 226.0}, 50), 0)
    check("$0 cash is refused", L.size({"ref_price": 20.0}, 0), 0)
    check("broker fractions are kept", L._q("0.442477"), 0.442477)
    # the planner itself must take a fractional position (a qty < 1 guard once refused them all)
    _acct, _pos, _xo, _rules0 = L.account, L.positions, L.exchange_orders, T.RULES
    L.account = lambda: {"cash": "500", "equity": "500", "last_equity": "500", "status": "ACTIVE"}
    L.positions = lambda: {}
    L.exchange_orders = lambda *a, **k: {}          # no broker call: CI holds no keys
    T.RULES = {"sw_rsi2_pullback": dict(lane="swing", universe=["NVDA"], signal=lambda h: h[-1]["c"] == 226.0,
                                        exit=_exit_never, entry="open", label="t", note="t")}
    try:
        _st = {"orders": {}, "meta": {}}
        _o, _r = L.plan({"NVDA": bars(215, 200.0, last=226.0)}, {"trades": [], "signals": []}, state=_st)
    finally:
        L.account, L.positions, L.exchange_orders, T.RULES = _acct, _pos, _xo, _rules0
    check("the plan buys a $226 stock as a fraction", [(o["symbol"], o["qty"]) for o in _o], [("NVDA", 0.442477)])
    sent = {}
    L._call = lambda method, path, body=None: sent.setdefault("b", body) and {"id": "x", "status": "accepted"}
    try:
        L.submit(dict(symbol="NVDA", qty=0.442477, action="buy", id="t1", rule="sw_rsi2_pullback"))
    except Exception:
        pass
    check("a fractional qty is sent as a plain decimal", (sent.get("b") or {}).get("qty"), "0.442477")
    L.TIME_IN_FORCE = "opg"
    try:
        L._fractional_ok(); refused = False
    except L.AlpacaError:
        refused = True
    check("fractional with opg is refused before sending", refused, True)
    L.TIME_IN_FORCE = "day"
    # ranking: three symbols fire; the lowest RSI(2) must come first, not the first letter
    def dip(n_down):
        h = bars(215, 100.0)
        for i in range(n_down):
            h[-1 - i] = dict(h[-1 - i], c=100.0 - (n_down - i) * 0.1 - 0.0)
        return h
    fake = {"AAA": 3.0, "MMM": 0.5, "ZZZ": 1.5}
    _rank = L.RANK["sw_rsi2_pullback"]
    L.RANK["sw_rsi2_pullback"] = lambda h: fake[h[0]["sym"]]
    _rules = T.RULES
    T.RULES = {"sw_rsi2_pullback": dict(lane="swing", universe=list(fake), signal=lambda h: True,
                                        exit=_exit_never, entry="open", label="t", note="t")}
    try:
        bb = {s_: [dict(b, sym=s_) for b in bars(215, 100.0)] for s_ in fake}
        got = [e["symbol"] for e in L.pending_entries(bb, {"trades": [], "signals": []})]
    finally:
        T.RULES, L.RANK["sw_rsi2_pullback"] = _rules, _rank
    check("signals are ranked lowest RSI(2) first, not alphabetically", got, ["MMM", "ZZZ", "AAA"])
    check("the real ranking is RSI(2)", round(_rank([{"c": c} for c in (10, 11, 12, 11, 10)]), 4),
          round(T.rsi([10, 11, 12, 11, 10], 2), 4))
finally:
    for k, v in _env.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    X = importlib.reload(X)
check("paper is back to whole shares and every rule", (X.FRACTIONAL, X.ONLY_RULES), (False, set()))

print(f"\n{'ALL PASS' if not FAILS else str(FAILS) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
