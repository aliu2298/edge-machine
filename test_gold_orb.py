#!/usr/bin/env python3
"""Offline checks for the Gold Asia-open breakout paper lane (gold_orb.py) and its Trading section."""
import datetime as dt
import sys

import gold_orb as G
import gold_orb_build as GB
import sandbox_audit

FAILS = []
UTC = dt.timezone.utc


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


def at(*a):
    return dt.datetime(*a, tzinfo=UTC)


def cdl(t, o, h, lo, c):
    return dict(start=str(int(t.timestamp())), open=str(o), high=str(h), low=str(lo), close=str(c), volume="3")


def candles_from(anchor, rng=None, after=None):
    """Range minutes (default 100-102 over 7:55-7:59) plus {minute offset: (o, h, l, c)} after it."""
    rng = rng if rng is not None else [(101, 102, 100, 101)] * 5
    out = [cdl(anchor - dt.timedelta(minutes=5 - i), *x) for i, x in enumerate(rng) if x]
    for k, x in (after or {}).items():
        out.append(cdl(anchor + dt.timedelta(minutes=k), *x))
    return G.by_minute(out)


# Oct 18 2026 is a Sunday under CDT: 8:00 pm CT = 01:00 UTC Monday.
SUN = dt.date(2026, 10, 18)
A = at(2026, 10, 19, 1, 0)

print("the clock: 8:00 pm America/Chicago and the 01:00 UTC shadow")
check("Sun-Thu are nights, Fri and Sat are not",
      [G.is_night(SUN + dt.timedelta(days=i)) for i in range(7)], [True, True, True, True, True, False, False])
check("under daylight time both anchors are 01:00 UTC", [a for _k, a, _s in G.anchors(SUN)], [A, A])
nov = dt.date(2026, 11, 1)        # the clock change: Sunday Nov 1 is CST
check("from Nov 1 the CT anchor is 02:00 UTC and the shadow 01:00 UTC (7:00 pm CST)",
      [(k, a, s) for k, a, s in G.anchors(nov)],
      [("ct_2000", at(2026, 11, 2, 2, 0), False), ("utc_0100", at(2026, 11, 2, 1, 0), True)])
check("Oct 31 (Sat) is no night; Oct 29 (Thu) still CDT",
      (G.is_night(dt.date(2026, 10, 31)), G.anchors(dt.date(2026, 10, 29))[0][1]), (False, at(2026, 10, 30, 1, 0)))
check("a 00:54 UTC start belongs to the Chicago evening before, both seasons",
      (G.night_of(at(2026, 10, 19, 0, 54)), G.night_of(at(2026, 11, 2, 0, 54))), (SUN, nov))

print("\nthe ranges: A = 30 minutes 7:30-7:59 from whatever traded, B = 7:55-7:59 every minute")
cm = candles_from(A, [(100, 101, 99.5, 100), (100, 102, 100, 101), (101, 101.5, 100.5, 101), (101, 101, 99, 100), (100, 100.5, 99.8, 100)])
check("B: max high / min low of the five minutes", G.build_range(cm, A, "B"), (102.0, 99.0))
early = G.by_minute([cdl(A - dt.timedelta(minutes=25), 100, 110, 95, 100)])
check("A reaches back 30 minutes; B does not", (G.build_range({**cm, **early}, A, "A"), G.build_range({**cm, **early}, A, "B")),
      ((110.0, 95.0), (102.0, 99.0)))
check("a minute 31 back is in neither", G.build_range({**cm, **G.by_minute([cdl(A - dt.timedelta(minutes=31), 1, 900, 1, 1)])}, A, "A"),
      (102.0, 99.0))
check("the 8:00 minute is not part of the range",
      G.build_range(candles_from(A, after={0: (100, 150, 50, 100)}), A, "B"), (102.0, 100.0))
gap = candles_from(A, [(1, 2, 0, 1), None, (1, 2, 0, 1), (1, 2, 0, 1), (1, 2, 0, 1)])
check("a missing minute: B has no range, A still does", (G.build_range(gap, A, "B"), G.build_range(gap, A, "A")), (None, (2.0, 0.0)))
check("nothing traded in 30 minutes: A has no range", G.build_range({}, A, "A"), None)

print("\nthe signal: the first minute that CLOSES beyond the range, within 60 minutes")
check("a close above the high is a long", G.find_signal(candles_from(A, after={3: (101, 102.5, 101, 102.2)}), A, 102, 100),
      ("long", int((A + dt.timedelta(minutes=3)).timestamp())))
check("a wick through that closes back inside is no signal",
      G.find_signal(candles_from(A, after={3: (101, 103, 99, 101)}), A, 102, 100), None)
check("a close below the low is a short",
      G.find_signal(candles_from(A, after={2: (101, 101, 99, 100.5), 7: (100, 100, 99.5, 99.8)}), A, 102, 100),
      ("short", int((A + dt.timedelta(minutes=7)).timestamp())))
check("closing ON the edge is not beyond it", G.find_signal(candles_from(A, after={1: (101, 102, 100, 102)}), A, 102, 100), None)
check("a close at minute 60 is outside the window", G.find_signal(candles_from(A, after={60: (101, 103, 101, 102.5)}), A, 102, 100), None)
check("`upto` reads only finished minutes",
      G.find_signal(candles_from(A, after={5: (101, 103, 101, 102.5)}), A, 102, 100, upto=int((A + dt.timedelta(minutes=5)).timestamp())), None)

print("\nentry at the next minute's open, exit at the close 15 minutes later")
sm = int((A + dt.timedelta(minutes=3)).timestamp())          # signal 8:03 -> entry 8:04 open -> exit 8:18 close (8:19:00)
cmx = candles_from(A, after={3: (101, 102.5, 101, 102.2), 4: (102.3, 102.6, 102.2, 102.5), 18: (103, 104, 103, 103.5),
                             19: (103.5, 104, 103, 103.9)})
check("entry 8:04's open, exit 8:18's close", G.fills(cmx, sm), (102.3, False, 103.5, False))
check("the hold ends 15 minutes after entry opens", G.exit_due(G.entry_minute(sm)) - G.entry_minute(sm), 900)
cmy = candles_from(A, after={3: (101, 102.5, 101, 102.2), 6: (102.4, 102.8, 102.4, 102.8)})
check("no trade at 8:04 or 8:18: first open after, last close before, both flagged", G.fills(cmy, sm), (102.4, True, 102.8, True))
check("nothing traded in the hold: the signal close both ways", G.fills(candles_from(A, after={3: (101, 102.5, 101, 102.2)}), sm),
      (102.2, True, 102.2, True))

print("\nreturns: gross from the next open, net at the venue's bid/ask less the fee")
r = G.returns("long", 4000.0, 4002.0, dict(bid=3999.9, ask=4000.3), dict(bid=4001.8, ask=4002.2))
check("long gross: +$2.00, +5bp", (r["gross_usd"], r["gross_bp"]), (2.0, 5.0))
check("long net: buy 4000.3, sell 4001.8, less 2 x $0.10 = +$1.30", (r["fill_in"], r["fill_out"], r["net_usd"], r["net_bp"]),
      (4000.3, 4001.8, 1.3, 3.25))
s = G.returns("short", 4000.0, 4002.0, dict(bid=3999.9, ask=4000.3), dict(bid=4001.8, ask=4002.2))
check("short net: sell 3999.9, buy 4002.2, less $0.20 = -$2.50", (s["gross_usd"], s["net_usd"]), (-2.0, -2.5))
check("no book: gross only", "net_usd" in G.returns("long", 100, 101), False)
check("spread in bp of the mid", G.spread_bp(dict(bid=4180.4, ask=4181.6)), round(1e4 * 1.2 / 4181.0, 3))
check("the fee: $0.10 a side, cited", (G.FEE_PER_SIDE, G.FEE_NOTE),
      (0.10, "fee: $0.10/side (CDE 2024 filing, non-professional, exchange fee only)"))

print("\na row, poll by poll")
st = G.load("/nonexistent/gold.json")
row = G.row_for(st, SUN, "B", "ct_2000", A, False)
book_in, book_out = dict(bid=102.2, ask=102.4, bid_size=2, ask_size=1), dict(bid=103.4, ask=103.6, bid_size=1, ask_size=1)
G.step(row, candles_from(A), book_in, A + dt.timedelta(seconds=5), "GOL-25NOV26-CDE")
check("8:00:05 builds the range", (row["status"], row["range_high"], row["range_low"]), ("ranged", 102.0, 100.0))
live = candles_from(A, after={3: (101, 102.5, 101, 102.4)})
G.step(row, live, dict(bid=1, ask=2), A + dt.timedelta(minutes=3, seconds=20), "P")
check("a minute still running is not a signal", row["status"], "ranged")
G.step(row, live, book_in, A + dt.timedelta(minutes=4, seconds=5), "P")
check("once 8:03 has closed above: long, the book at this poll is the entry book",
      (row["status"], row["side"], row["entry_book"]["ask"], row["entry_at"][11:16], row["exit_at"][11:16]),
      ("open", "long", 102.4, "01:04", "01:19"))
held = candles_from(A, after={3: (101, 102.5, 101, 102.4), 4: (102.3, 102.6, 102.2, 102.5), 18: (103, 104, 103, 103.5)})
G.step(row, held, book_out, A + dt.timedelta(minutes=18, seconds=30), "P")
check("no exit while the last held minute is still running", row["status"], "open")
G.step(row, held, book_out, A + dt.timedelta(minutes=19, seconds=5), "P")
check("settled: entry 102.3, exit 103.5, net at the books",
      (row["status"], row["entry_px"], row["exit_px"], row["gross_usd"], row["net_usd"], row["exit_spread_bp"]),
      ("settled", 102.3, 103.5, 1.2, round(103.4 - 102.4 - 0.2, 4), G.spread_bp(book_out)))
A2 = A + dt.timedelta(days=1)
nr = dict(id="x", night="2026-10-19", variant="B", anchor="ct_2000", anchor_at=A2.isoformat(), status="pending")
G.step(nr, candles_from(A2, [(1, 2, 0, 1)] * 4 + [None]), book_in, A2 + dt.timedelta(seconds=30), "P")
check("a missing range minute waits out the grace", nr["status"], "pending")
G.step(nr, candles_from(A2, [(1, 2, 0, 1)] * 4 + [None]), book_in, A2 + dt.timedelta(seconds=125), "P")
check("then logs no_range", nr["status"], "no_range")
nb = dict(id="y", night="2026-10-19", variant="A", anchor="ct_2000", anchor_at=A2.isoformat(), status="pending")
quiet = candles_from(A2, after={k: (101, 103, 99, 101) for k in range(0, 60, 7)})
G.step(nb, quiet, book_in, A2 + dt.timedelta(minutes=30), "P")
G.step(nb, quiet, book_in, A2 + dt.timedelta(minutes=60, seconds=5), "P")
check("wicks but no close beyond by 9:00 pm: no_break", nb["status"], "no_break")

print("\nthe live run, on a fake clock and a fake Coinbase")
prods = {"products": [
    dict(product_id="GOL-25NOV26-CDE", volume_24h="852", future_product_details=dict(contract_code="GOL", contract_expiry="2026-11-25T18:30:00Z")),
    dict(product_id="GOL-27JAN27-CDE", volume_24h="40", future_product_details=dict(contract_code="GOL", contract_expiry="2027-01-27T18:30:00Z")),
    dict(product_id="BIT-25NOV26-CDE", volume_24h="9999", future_product_details=dict(contract_code="BIT", contract_expiry="2026-11-25T18:30:00Z"))]}
check("the GOL contract with the most 24h volume", G.pick_product(prods["products"], at(2026, 10, 19)), "GOL-25NOV26-CDE")
check("an expired contract is never read", G.pick_product(prods["products"], at(2026, 12, 1)), "GOL-27JAN27-CDE")


def fake_for(feed):
    def fake(path):
        if path.startswith("products?"):
            return prods
        if path.startswith("product_book"):
            return {"pricebook": {"bids": [{"price": "99.9", "size": "2"}], "asks": [{"price": "100.1", "size": "1"}]}}
        end = int(path.split("end=")[1])
        return {"candles": [c for c in feed if int(c["start"]) + 60 <= end]}
    return fake


def live_run(start, feed):
    clock = [start]

    def tick(sec):
        clock[0] += dt.timedelta(seconds=sec)
    state = {"nights": [], "runs": []}
    rows = G.run(state, now_fn=lambda: clock[0], fetch=fake_for(feed), sleep=tick, log=lambda *_: None)
    return state, rows, clock[0]


# A 30-minute range 95-110 (one wide print at 7:35) and a 5-minute range 100-102; 8:02 closes at 99.7.
feed = [cdl(A - dt.timedelta(minutes=25), 100, 110, 95, 100)] + \
       [cdl(A - dt.timedelta(minutes=5 - i), 101, 102, 100, 101) for i in range(5)] + \
       [cdl(A + dt.timedelta(minutes=2), 101, 101.5, 99.5, 99.7), cdl(A + dt.timedelta(minutes=3), 99.6, 99.8, 99.4, 99.5),
        cdl(A + dt.timedelta(minutes=17), 99, 99.5, 98.5, 99.0)]
st2, rows, end = live_run(at(2026, 10, 19, 0, 54), feed)
got = {(r["variant"], r["anchor"]): (r["status"], r.get("side"), r.get("entry_px"), r.get("exit_px")) for r in rows}
check("CDT: four rows; B shorts at 8:03's open, exits at 8:17's close; A's wide range never breaks",
      got, {("A", "ct_2000"): ("no_break", None, None, None), ("A", "utc_0100"): ("no_break", None, None, None),
            ("B", "ct_2000"): ("settled", "short", 99.6, 99.0), ("B", "utc_0100"): ("settled", "short", 99.6, 99.0)})
b = [r for r in rows if r["variant"] == "B"][0]
check("B net: sell at the 99.9 bid, buy back at the 100.1 ask, less the fee", b["net_usd"], round(99.9 - 100.1 - 0.2, 4))
check("the run is logged and ends by 9:20 pm CT", (st2["runs"][0]["night"], st2["runs"][0]["product"], end <= at(2026, 10, 19, 2, 21)),
      ("2026-10-18", "GOL-25NOV26-CDE", True))
# CST (Nov 1): the 00:54 UTC start is 6:54 pm CST; it waits for 7:00 pm (shadow) and 8:00 pm (CT anchor).
B1, B2 = at(2026, 11, 2, 1, 0), at(2026, 11, 2, 2, 0)
cst = [cdl(B1 - dt.timedelta(minutes=5 - i), 101, 102, 100, 101) for i in range(5)] + \
      [cdl(B2 - dt.timedelta(minutes=5 - i), 201, 202, 200, 201) for i in range(5)] + \
      [cdl(B1 + dt.timedelta(minutes=1), 102, 103, 102, 102.5), cdl(B2 + dt.timedelta(minutes=10), 202, 203, 202, 202.5)]
_st, crows, cend = live_run(at(2026, 11, 2, 0, 54), cst)
got = {(r["variant"], r["anchor"]): (r["status"], r.get("side"), r.get("signal_at")) for r in crows}
check("CST: the shadow signals off 7:00 pm, the CT anchor off 8:00 pm, in one run",
      (got[("B", "utc_0100")], got[("B", "ct_2000")]),
      (("settled", "long", "2026-11-02T01:01:00+00:00"), ("settled", "long", "2026-11-02T02:10:00+00:00")))
check("and that run ends by 9:20 pm CST", cend <= at(2026, 11, 2, 3, 21), True)
fri = live_run(at(2026, 10, 24, 0, 54), feed)[1]
check("a Friday evening does nothing", fri, [])

print("\nthe summary and the Trading section")
mk = lambda n, net, gross, v="B", anchor="ct_2000": dict(id=f"{v}:{anchor}:{n}", night=f"2026-10-{n:02d}", variant=v, anchor=anchor,
                                                        shadow=anchor != "ct_2000", status="settled", side="long", entry_px=4000.0,
                                                        exit_px=4001.0, gross_bp=gross, net_bp=net, net_usd=net * 0.4,
                                                        entry_spread_bp=2.0 + n % 2, exit_spread_bp=3.1)
sm = G.summary([mk(19, 4.0, 6.0), mk(20, -2.0, 1.0), dict(status="no_break")])
check("summary: 2 settled, 50% won, gross +3.5, net +1.0, spread 2.5", (sm["n"], sm["win"], sm["gross"], sm["net"], sm["spread"]),
      (2, 0.5, 3.5, 1.0, 2.5))
check("its t", round(sm["t"], 3), round(1.0 / (4.242640687 / 2 ** 0.5), 3))
led = {"nights": [mk(19, 4.0, 6.0), mk(19, 1.0, 2.0, anchor="utc_0100"), mk(19, -3.0, -1.0, v="A"),
                  dict(id="n", night="2026-10-20", variant="B", anchor="ct_2000", status="no_range")],
       "last_run": "2026-10-20T03:00:00+00:00"}
html = GB.section(led)
check("its own id and heading", ('<section id="gold-orb">' in html, "Gold Asia-open breakout (paper)" in html), (True, True))
check("a summary row per variant and anchor", [html.count(G.VARIANTS[v][2]) >= 2 for v in "AB"], [True, True])
check("summary columns", all(c in html for c in ("Settled nights", "Won", "Avg gross bp", "Avg net bp", "Avg spread bp", "t (net)")), True)
check("nightly columns", all(c in html for c in ("Night", "Variant", "Anchor", "Side", "Entry", "Exit", "Gross bp",
                                                  "Spread bp entry / exit", "Net bp · $")), True)
check("paper · never places an order", "Paper · never places an order" in html, True)
check("the review point and the cited fee",
      ("Olu reviews at 10+ settled nights per variant" in html, "fee: $0.10/side (CDE 2024 filing, non-professional, exchange fee only)" in html),
      (True, True))
check("a skipped night says why", "no range (too few minutes traded)" in html, True)
check("an empty ledger says when the first night is", "No nights yet" in GB.section({"nights": []}), True)
check("the copy passes the audit's guarded phrases", sandbox_audit.COPY_RE.search(html + GB.section({"nights": []}) + open("gold_orb.py").read()
                                                                                   + open("scripts/vps_gold_orb.sh").read()), None)
import sandbox_build
page = sandbox_build.trading_page(at(2026, 10, 19, 12, 0))
check("the Trading page carries the section and links it", ('id="gold-orb"' in page, 'href="#gold-orb"' in page), (True, True))

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
