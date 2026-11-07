#!/usr/bin/env python3
"""Since Production is the follower's own fills on every Production pair (2026-11-07): priced from the exchange's fills and fees, attributed by
the order's own id, a pair with no order reads "no live orders yet" with a reason, never the paper record. No network, nothing read from data/."""
import live_fills_export as X
import live_record_publish as P
import production_live as PL

fails = []


def check(name, ok):
    print(("  ok   " if ok else "  FAIL ") + name)
    if not ok:
        fails.append(name)


# the exporter: buys only, quantity-weighted price, fees summed per order, NO fills priced on the no side
raw = [dict(order_id="a", action="buy", side="yes", yes_price_dollars="0.40", count_fp="2", fee_cost="0.03"),
       dict(order_id="a", action="buy", side="yes", yes_price_dollars="0.50", count_fp="2", fee_cost="0.04"),
       dict(order_id="a", action="sell", side="yes", yes_price_dollars="0.90", count_fp="4", fee_cost="0.01"),
       dict(order_id="b", action="buy", side="no", no_price_dollars="0.45", yes_price_dollars="0.55", count_fp="3", fee_cost="0.05")]
got = X.per_order(raw)
check("buys are summed per order, sells left out", got["a"] == dict(qty=4.0, px=0.45, fee=0.07))
check("a NO fill is priced on the no side", got["b"]["px"] == 0.45)

# the publisher prices an order from its fills, not its recorded fill and fee
o = dict(order_id="a", filled=2, avg_px=0.40, commission=0.0, lead=dict(sandbox_quote="q", kickoff="2026-11-06T20:00:00+00:00", pair="p|s"), side="Yes",
         market="KXTEST-1", order_state="ORDER_STATE_FILLED")
row, stake = P.order_row("k", o, {}, {"KXTEST-1": "yes"}, fills=got)
check("stake is the fills' cost plus the exchange's fee", abs(stake - (4 * 0.45 + 0.07)) < 1e-9)
check("the return is after that fee", row["st"] == "won" and abs(row["r"] - round((4 * 0.55 - 0.07) / stake, 4)) < 1e-9)
row2, stake2 = P.order_row("k", o, {}, {"KXTEST-1": "yes"}, fills={})
check("no fills on file: the recorded fill and fee are used", abs(stake2 - 0.8) < 1e-9)
check("another lane's order id does not lend its fills", P.order_fills(dict(order_id="zzz"), got) is None)

# the page side
orders = [dict(id="q1", ko="2026-11-05T20:00", side="yes", st="won", w=1.0, r=0.5), dict(id="q2", ko="2026-11-06T20:00", side="yes", st="lost", w=1.0, r=-1.0),
          dict(id="q3", ko="2026-11-06T22:00", side="yes", st="open", w=None, r=None)]
blob = dict(pairs={"p|s": dict(orders=orders, refused={}), "empty|s": dict(orders=[], refused={"q9": "price above the cap"})})
win, _ = PL.fill_window(blob, "p|s", "2026-11-06T00:00")
rec = PL.record(win)
check("the window counts from the Production date or the raise", (rec["won"], rec["lost"], rec["open"]) == (0, 1, 1))
live = PL.fill_live(dict(n=9, won=9, roi_fee=1.0, n_price=3), rec)
check("live fills replace the paper counts", (live["n"], live["won"], live["n_price"], live["roi_fee"]) == (1, 0, 0, -1.0))
none, _ = PL.fill_window(blob, "empty|s", None)
check("a pair with no order has an empty list", none == [])
check("no live file: nothing to replace", PL.fill_window(None, "p|s", None) == (None, None))
check("refusals are the reason", "price above the cap" in PL.no_orders_reason("empty|s", {"q9": "price above the cap"}, 0))
check("the internationals under has its known reason", "event" in PL.no_orders_reason("u35_low_scoring|soccer_u35_intl", {}, 0))
fold = PL.no_orders_fold([("Pair A", "why a")])
check("one fold lists the pairs", "No live orders yet" in fold and "Pair A" in fold and "why a" in fold and "$" not in fold)

raise SystemExit(1 if fails else print("PASS live since production") or 0)
