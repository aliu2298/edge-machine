#!/usr/bin/env python3
"""Offline checks for fillsim.py. Each known paper v live failure is a fixture here: the fill rule that caused it must not come back."""
import sys

import fillsim as F

FAILS = []
R = F.Rules(queue_ahead=10.0, latency_s=60.0, offer_fills=True)        # the tests pin their own rules: the calibrated defaults may move


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


def near(label, got, want, tol=1e-4):
    ok = got is not None and abs(got - want) <= tol
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


def P(ts, yes, n, taker=None):
    return (float(ts), yes, float(n), taker)


def no(ts, no_px, n, taker=None):
    """A print quoted on the NO side."""
    return (float(ts), round(1 - no_px, 4), float(n), taker)


print("prints")
rows = [
    {"created_time": "2026-11-01T12:00:01Z", "yes_price_dollars": "0.9000", "no_price_dollars": "0.1000", "count_fp": "5.00", "taker_side": "yes"},
    {"created_time": "2026-11-01T12:00:00.500000Z", "yes_price_dollars": "0.8800", "count_fp": "2.50", "taker_side": "no"},
    {"created_time": "2026-11-01T12:00:02Z", "yes_price_dollars": "0.5000", "count_fp": "900", "taker_side": "yes", "is_block_trade": True},
    {"created_time": "2026-11-01T12:00:03Z", "no_price_dollars": "0.2000", "count_fp": "1"},
]
ps = F.prints_from_trades(rows)
check("oldest first, the block trade dropped", [(p[1], p[2], p[3]) for p in ps], [(0.88, 2.5, "no"), (0.9, 5.0, "yes"), (0.8, 1.0, None)])
check("fractional second kept", ps[1][0] - ps[0][0], 0.5)
same = [{"created_time": "2026-11-01T12:00:00Z", "yes_price_dollars": "0.30", "count_fp": "1", "taker_side": "yes"},
        {"created_time": "2026-11-01T12:00:00Z", "yes_price_dollars": "0.20", "count_fp": "1", "taker_side": "yes"}]
check("same instant: the exchange's order (newest first on the wire)", [p[1] for p in F.prints_from_trades(same)], [0.2, 0.3])
check("a NO price", F.px_of(P(0, 0.9, 1), "no"), 0.1)
check("a lane's NO rows become YES prints", F.as_prints([(5, 0.1, 3)], "no"), [(5.0, 0.9, 3.0, None)])

print("fees: the exchange's")
near("taker, one contract at 15c: 0.07 x .15 x .85 = .008925 -> .0090", F.fee(0.15), 0.0090, 1e-9)
near("taker, rounded up per contract then times the size", F.fee(0.15, 5), 0.0450, 1e-9)
near("taker at 50c lands on the grid exactly", F.fee(0.50), 0.0175, 1e-9)
check("a resting fill pays nothing", F.fee(0.40, 10, taker=False), 0.0)
check("settlement prices pay nothing", (F.fee(1.0), F.fee(0.0)), (0.0, 0.0))
check("$1 buys 6 contracts at 15c", F.stake_qty(0.15), 6.0)
check("never under one contract", F.stake_qty(0.65), 1.0)

print("taker buy: the Album fixture (asks nobody could trade)")
thin = [P(0, 0.10, 5, "yes"), P(600, 0.08, 3, "yes")]
r = F.taker_buy(thin, 100, 0.08, "yes", rules=R)
check("3 contracts at the ask is not an entry", (r["ok"], r["printed"]), (False, 3.0))
r = F.taker_buy([P(0, 0.30, 5, "yes"), P(600, 0.08, 40, "yes")], 100, 0.08, "yes", rules=R)
check("an ask under half the last trade is refused even when it prints", (r["ok"], "half the last trade" in r["reason"]), (False, True))
ok10 = [P(0, 0.10, 5, "yes"), P(600, 0.08, 6, "yes"), P(900, 0.07, 4, "yes")]
check("10 contracts at or under the ask inside the hour verify", F.taker_buy(ok10, 100, 0.08, "yes", rules=R)["ok"], True)
check("a print after the hour does not count", F.taker_buy([P(0, 0.10, 5), P(100 + 3601, 0.08, 50, "yes")], 100, 0.08, rules=R)["ok"], False)
check("a print before the quote does not count", F.taker_buy([P(50, 0.08, 50, "yes")], 100, 0.08, rules=R)["ok"], False)
sold_into_bid = [P(0, 0.10, 5, "yes"), P(600, 0.08, 50, "no")]
check("contracts SOLD into a bid at that price show no offer", F.taker_buy(sold_into_bid, 100, 0.08, "yes", rules=R)["ok"], False)
check("prints with no taker side count (an old tape)", F.taker_buy([P(0, 0.10, 5), P(600, 0.08, 50)], 100, 0.08, rules=R)["ok"], True)
check("an order larger than 10 needs its own size", F.taker_buy(ok10, 100, 0.08, "yes", qty=20, rules=R)["ok"], False)
check("a live book that covers the order verifies alone", F.taker_buy([], 100, 0.08, qty=5, rules=R, book_size=12)["how"], "book")
check("a NO ask reads the NO side", F.taker_buy([no(0, 0.2, 1, "no"), no(60, 0.15, 12, "no")], 30, 0.15, "no", rules=R)["ok"], True)
Q = F.QUOTED
check("a quoted lane: an ask the prints cannot confirm still counts", (F.taker_buy([P(0, 0.10, 5)], 100, 0.08, rules=Q)["status"],
                                                                         F.taker_buy([P(0, 0.10, 5)], 100, 0.08, rules=Q)["ok"]), ("unconfirmed", True))
check("... and a confirmed one says so", F.taker_buy(ok10, 100, 0.08, "yes", rules=Q)["status"], "verified")
check("... but trades all more than 5c above it refute it", (F.taker_buy([P(0, 0.10, 5), P(600, 0.14, 9, "yes"), P(700, 0.20, 9, "no")], 100, 0.08, rules=Q)["status"],
                                                               F.taker_buy([P(0, 0.10, 5), P(600, 0.14, 9, "yes")], 100, 0.08, rules=Q)["ok"]), ("refuted", False))
check("... one trade within 5c keeps it", F.taker_buy([P(0, 0.10, 5), P(600, 0.13, 1, "no"), P(700, 0.20, 9, "no")], 100, 0.08, rules=Q)["ok"], True)
check("... and half the last trade still refuses it", F.taker_buy([P(0, 0.30, 5)], 100, 0.08, rules=Q)["ok"], False)
check("honest-v1 itself never counts an unconfirmed ask", F.taker_buy([P(0, 0.10, 5)], 100, 0.08)["ok"], False)
check("taker sell = taker buy of the other side", F.taker_sell([P(0, 0.5, 1), P(60, 0.40, 12, "no")], 30, 0.40, "yes", rules=R)["ok"], True)

print("resting buy: through, offer, queue")
check("a print strictly under the bid fills", F.resting_buy([P(10, 0.09, 10, "no")], 0, 0.10, qty=10, rules=R)["status"], "filled")
r = F.resting_buy([P(10, 0.09, 4, "no")], 0, 0.10, qty=10, rules=R)
check("... only for the size that printed", (r["status"], r["qty"], r["via"]), ("partial", 4.0, "through"))
r = F.resting_buy([P(10, 0.10, 8, "no")], 0, 0.10, qty=1, rules=R)
check("the ATHRSO fixture: a touch at exactly the bid, behind the queue, is no fill", (r["status"], r["touched"], r["queue_n"]), ("unfilled", True, 8.0))
r = F.resting_buy([P(10, 0.10, 8, "no"), P(20, 0.10, 5, "no")], 0, 0.10, qty=2, rules=R)
check("the queue clears after 10 contracts, then we fill", (r["status"], r["qty"], r["via"], r["fill_ts"]), ("filled", 2.0, "queue", 20.0))
r = F.resting_buy([P(10, 0.10, 3, "yes")], 0, 0.10, qty=2, rules=R)
check("an offer lifted AT our price had no bid ahead of it: it meets us", (r["status"], r["via"]), ("filled", "offer"))
check("... unless the rule set turns that off", F.resting_buy([P(10, 0.10, 3, "yes")], 0, 0.10, qty=2,
                                                              rules=F.Rules(queue_ahead=10, offer_fills=False))["status"], "unfilled")
check("a print before the order went up never fills it", F.resting_buy([P(5, 0.05, 99, "no")], 10, 0.10, rules=R, check_cross=False)["status"], "unfilled")
check("a print after the cancel never fills it (o35 v5: minute 80)", F.resting_buy([P(50, 0.05, 99, "no")], 0, 0.10, rules=R, cancel_ts=50)["status"], "unfilled")
check("a NO bid fills on the NO price", F.resting_buy([no(10, 0.08, 20, "yes")], 0, 0.10, "no", qty=10, rules=R)["status"], "filled")
check("a higher price never touches", F.resting_buy([P(10, 0.11, 99, "no")], 0, 0.10, rules=R)["touched"], False)

print("resting buy: the post-only cross (SANRMA, NSHNYRB, BASSAM, TELFCU, GROSPA on Nov 1)")
tape = [no(0, 0.08, 5), no(4000, 0.06, 50, "yes")]
r = F.resting_buy(tape, 3600, 0.10, "no", qty=10, rules=R)
check("NO already at or under the bid when it went up: refused, no entry", (r["status"], r["saw"], r["qty"]), ("crossed", 0.08, 0.0))
check("a print older than the lookback says nothing", F.resting_buy([no(0, 0.08, 5), no(9000, 0.06, 50, "yes")], 6000, 0.10, "no", qty=10, rules=R)["status"], "filled")
check("a quote at that minute decides it", F.resting_buy(tape, 3600, 0.10, "no", qty=10, rules=R, quote=(0.11, 0.13))["status"], "filled")
check("... both ways", F.resting_buy([no(0, 0.20, 5), no(4000, 0.06, 50, "yes")], 3600, 0.10, "no", rules=R, quote=(0.07, 0.09))["status"], "crossed")

print("resting sell: prints, not the bid (the Edwards 5+ threes fixture)")
edwards = [P(0, 0.25, 10, "yes"), P(500, 0.55, 30, "yes"), P(900, 0.80, 30, "yes")]
r = F.resting_sell(edwards, 0, 0.50, "yes", qty=4, rules=R)
check("a trade above the target sells it, whatever the bid showed", (r["status"], r["via"], r["fill_ts"]), ("filled", "through", 500.0))
r = F.resting_sell([P(500, 0.50, 6, "yes"), P(600, 0.50, 6, "yes")], 0, 0.50, "yes", qty=1, rules=R)
check("buyers lifting offers AT the target: we wait behind the queue", (r["status"], r["fill_ts"]), ("filled", 600.0))
check("... and a thin touch does not sell", F.resting_sell([P(500, 0.50, 6, "yes")], 0, 0.50, "yes", qty=1, rules=R)["status"], "unfilled")
check("a bid that rested AT the target would have met our offer", F.resting_sell([P(500, 0.50, 6, "no")], 0, 0.50, "yes", qty=1, rules=R)["via"], "offer")
check("a NO sell reads the NO price", F.resting_sell([no(500, 0.45, 20, "no")], 0, 0.40, "no", qty=10, rules=R)["status"], "filled")

print("resting sell: the over 3.5 flash-print fixture (sells that printed seconds after the fill)")
flash = [no(1000, 0.08, 20, "yes"), no(1020, 0.45, 80, "no"), no(1030, 0.09, 10, "yes")]
t = F.trade(flash, "no", dict(kind="rest", ts=0, price=0.10), [dict(target=0.40, share=1.0)], payout=0.0, qty=10, rules=R)
check("filled at 10c", (t["status"], t["qty"], t["fill_ts"]), ("settled", 10.0, 1000.0))
check("the 45c print 20 seconds later is not a sale: the sell was not up yet", (t["legs"][0]["status"], t["sold"]), ("unfilled", 0.0))
check("held to a lost settlement", t["roi"], -1.0)
later = flash + [no(1100, 0.45, 80, "no")]
t = F.trade(later, "no", dict(kind="rest", ts=0, price=0.10), [dict(target=0.40, share=1.0)], payout=0.0, qty=10, rules=R)
check("the same print 100 seconds after the fill sells", (t["legs"][0]["status"], t["sold"]), ("filled", 10.0))
near("no fee either way on resting fills: 10c -> 40c is +300%", t["roi"], 3.0)

print("resting sell: the gas daily fixture (opening-minute prints from before the entry)")
gas = [no(0, 0.44, 40, "no"), no(30, 0.22, 15, "no"), no(45, 0.21, 15, "no"), no(5000, 0.25, 30, "no")]
t = F.trade(gas, "no", dict(kind="taker", ts=20, price=0.22), [dict(target=0.44, share=0.5), dict(target=0.66, share=0.5)],
            payout=0.0, qty=4, rules=R)
check("the entry verifies on the prints after it", (t["status"], t["entry"]["printed"]), ("settled", 30.0))
check("the 44c opening print, before the entry, sells nothing", [l["status"] for l in t["legs"]], ["unfilled", "unfilled"])
check("held to the end", t["roi"], -1.0)

print("resting sell: the KASBES fixture (the target was already under the market when the sell went up)")
kas = [no(1000, 0.08, 20, "yes"), no(1005, 0.55, 30, "no"), no(1050, 0.60, 30, "no"), no(1200, 0.52, 30, "no")]
t = F.trade(kas, "no", dict(kind="rest", ts=0, price=0.10), [dict(target=0.40, share=1.0)], payout=0.0, qty=10, rules=R)
leg = t["legs"][0]
check("a post-only sell would cross: it is sold as a taker at the target", (leg["status"], leg["taker"], leg["sold"]), ("crossed", True, 10.0))
near("... and pays the taker fee: (4.00 - .168) / 1.00 - 1", t["roi"], 2.832)
near("... the return before fees is still +300%", t["gross"], 3.0)
check("... at the first print that confirms the price was still there", leg["ts"], 1200.0)
t = F.trade(kas[:3], "no", dict(kind="rest", ts=0, price=0.10), [dict(target=0.40, share=1.0)], payout=0.0, qty=10, rules=R)
check("prints from before the sell went up confirm nothing: unsold", (t["legs"][0]["status"], t["roi"]), ("unfilled", -1.0))
q = F.resting_sell(kas[:3], 1000, 0.40, "no", qty=10, rules=R, quote=(0.55, 0.57))
check("a quote showing the bid above the target sells at once", (q["status"], q["taker"], q["fill_ts"]), ("crossed", True, 1060.0))

print("a whole trade")
wm = [P(0, 0.15, 30, "yes"), P(100, 0.15, 30, "yes"), P(4000, 0.31, 40, "yes"), P(5000, 0.46, 40, "yes"), P(6000, 0.05, 10, "no")]
legs = [dict(target=0.30, share=0.5, from_ts=3600), dict(target=0.45, share=0.5, from_ts=3600)]
t = F.trade(wm, "yes", dict(kind="taker", ts=50, price=0.15), legs, payout=0.0, rules=R)
check("$1 at 15c is 6 contracts, both halves sold", (t["qty"], [l["sold"] for l in t["legs"]]), (6.0, [3.0, 3.0]))
near("cost = 6 x .15 + 6 x .0090 taker fee", t["cost"], 0.954, 1e-6)
near("return = (3 x .30 + 3 x .45) / .954 - 1", t["roi"], 2.25 / 0.954 - 1)
near("the same entry held lost everything", t["hold"], -1.0)
t = F.trade(wm[:3], "yes", dict(kind="taker", ts=50, price=0.15), legs, payout=1.0, rules=R)
check("an unsold half is paid at settlement", (t["legs"][1]["status"], t["sold"]), ("unfilled", 3.0))
near("... (3 x .30 + 3 x 1) / .954 - 1", t["roi"], 3.9 / 0.954 - 1)
t = F.trade(wm[:3], "yes", dict(kind="taker", ts=50, price=0.15), legs, payout=None, rules=R)
check("an unsold half with no result yet is open", (t["status"], t["roi"]), ("open", None))
t = F.trade([P(0, 0.15, 3, "yes")], "yes", dict(kind="taker", ts=50, price=0.15), legs, payout=1.0, rules=R)
check("no entry when the ask never traded", (t["status"], t["why"].startswith("unverified ask")), ("no_entry", True))
t = F.trade([P(10, 0.50, 3, "no")], "yes", dict(kind="rest", ts=0, price=0.40), [], payout=1.0, rules=R)
check("no entry when the price never reached the bid", (t["status"], t["why"]), ("no_entry", "the price never reached the bid"))
t = F.trade([P(10, 0.40, 3, "no")], "yes", dict(kind="rest", ts=0, price=0.40), [], payout=1.0, rules=R)
check("... and a touch behind the queue says so", t["why"], "touched, never filled (behind the queue)")
pre = [P(0, 0.20, 50, "yes"), P(10, 0.19, 50, "no"), P(15, 0.45, 5, "yes"), P(40, 0.21, 5, "no"), P(500, 0.45, 5, "yes")]
t = F.trade(pre, "yes", dict(kind="rest", ts=5, price=0.20, check_cross=False), [dict(target=0.40, share=1.0, from_ts=1)],
            payout=0.0, qty=5, rules=R)
check("a from_ts earlier than the fill cannot put the sell up before the position exists", (t["legs"][0]["ts"], t["sold"]), (500.0, 5.0))
s = F.settle(0.10, 10, [(0.40, 4, False)], 1.0, entry_taker=False, rules=R)
near("settle: 4 sold at 40c, 6 paid at 1", s["roi"], (1.6 + 6.0) / 1.0 - 1)
check("the default rule set is the named one", (F.HONEST.name, F.VERSION), ("honest-v1", "honest-v1"))
check("honest-v1: a touch never fills", F.resting_buy([P(10, 0.10, 5000, "no"), P(11, 0.10, 5000, "yes")], 0, 0.10, qty=1)["status"], "unfilled")
check("honest-v1: a print through the bid does", F.resting_buy([P(10, 0.0999, 1, "no")], 0, 0.10, qty=1)["status"], "filled")
check("honest-v1: the sell waits 60 seconds", F.resting_sell([P(30, 0.9, 9), P(45, 0.3, 1), P(61, 0.9, 9)], 0, 0.5, qty=1)["fill_ts"], 61.0)

print()
if FAILS:
    print(f"{len(FAILS)} FAILED: " + "; ".join(FAILS))
    sys.exit(1)
print("all fillsim checks passed")
