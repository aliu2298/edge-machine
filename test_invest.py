#!/usr/bin/env python3
"""Kalshi Invest big-move lane (invest.py, invest_build.py): paper only, public data, honest fills.

No network: the API is a fake. Nothing outside a temp dir is written.
"""
import datetime as dt
import json
import os
import re
import sys
import tempfile

import invest as I
import invest_build as IB
import sandbox_audit

FAILS = []
ET = I.ET


def check(why, got, want):
    good = got == want
    print(f"  {'ok  ' if good else 'FAIL'} {why}" + ("" if good else f" — got {got!r}, want {want!r}"))
    if not good:
        FAILS.append(why)


def ts(y, mo, d, h, mi):
    return int(dt.datetime(y, mo, d, h, mi, tzinfo=ET).timestamp())


def row(t, ref, bid=None, ask=None, open_=True):
    return dict(ts=t, sym="XYZ", ref=ref, bid=bid, ask=ask, last=None, open=open_)


print("\nthe module never trades")
src = open(os.path.join(I.ROOT, "invest.py")).read()
check("no order, cancel or auth call anywhere in invest.py",
      [w for w in ("/orders", "DELETE", "KALSHI-ACCESS", "POST", "private_key", "api_key", "method=") if w in src], [])
check("every rule is 1x: no leverage field", [k for k, r in I.RULES.items() if "leverage" in r], [])
check("fade buys a drop and sells a jump; follow the reverse",
      [I.side_of(k) for k in ("fade_drop", "fade_jump", "follow_drop", "follow_jump")], [1, -1, -1, 1])

print("\nthe snapshot")
mk = [dict(asset_class="Equities", status="active", ticker="KXAPERP", title="A", bid="1.0", ask="922337203685477.5807",
           price="1.01", reference_price={"price": "1.02"}, schedule={"is_open": True}),
      dict(asset_class="Crypto", status="active", ticker="KXBTCPERP", title="BTC", bid="1", ask="2", price="1"),
      dict(asset_class="Equities", status="inactive", ticker="KXZPERP", title="Z", bid="1", ask="2", price="1")]
rows = I.snapshot_rows(mk, 100)
check("only active Equities/Indices, and the empty-ask sentinel reads as no ask",
      [(r["ticker"], r["bid"], r["ask"], r["ref"], r["open"]) for r in rows], [("KXAPERP", 1.0, None, 1.02, 1)])
with tempfile.TemporaryDirectory() as tmp:
    n = I.collect(tmp, get=lambda path: {"markets": mk}, now=ts(2026, 11, 9, 10, 0))
    t = I.load_ticks(tmp, 0)
    check("collect writes one row per market and load_ticks reads it back", (n, list(t), t["KXAPERP"][0]["ask"]),
          (1, ["KXAPERP"], None))

print("\nevents on the reference price: the day window")
I.RULES["fade_drop"] = dict(I.RULES["fade_drop"], win="day", size=0.05, tp=0.04, sl=0.04, hold="1h")
prev = [row(ts(2026, 11, 9, 15, 59), 100.0)]
day = [row(ts(2026, 11, 10, 9, 31), 99.0), row(ts(2026, 11, 10, 15, 55), 94.0, bid=93.9, ask=94.1)]
ticks = {"KXXYZPERP": prev + day}
ev = I.detect(ticks, "fade_drop", set())
check("a 6% drop to 15:55 v the prior close is one fade_drop event", [(e["ticker"], e["day"], e["move"]) for e in ev],
      [("KXXYZPERP", "2026-11-10", -0.06)])
check("a 4% drop is not", I.detect({"K": prev + [row(ts(2026, 11, 10, 15, 55), 96.0)]}, "fade_drop", set()), [])
check("an event already known is not logged twice", I.detect(ticks, "fade_drop", {ev[0]["id"]}), [])

print("\ngrading: honest fills")
e = dict(ev[0])
after = [row(ts(2026, 11, 10, 15, 56), 94.0, 93.9, 94.1), row(ts(2026, 11, 10, 15, 57), 94.0, 93.9, 94.1)]
rows_ = prev + day + after
nowt = ts(2026, 11, 10, 16, 30)
check("no print at or through the ask -> still unfilled after 2 tries, then no_fill at 5",
      I.grade(dict(e), rows_ + [row(ts(2026, 11, 10, 15, 58) + 60 * i, 94.0, 93.9, 94.1) for i in range(3)],
              lambda a, b: [(a + 1, 94.0)], nowt)["status"], "no_fill")
filled = I.grade(dict(e), rows_, lambda a, b: [(a + 5, 94.1)] if a == ts(2026, 11, 10, 15, 56) else [], nowt)
check("a print at the ask fills Up at the ask, the spread recorded", (filled["status"], filled["entry"], filled["spread_in"]),
      ("open", 94.1, 21.3))
tp = dict(e, status="open", entry_ts=ts(2026, 11, 10, 15, 56), entry=100.0)
tp_rows = [row(ts(2026, 11, 11, 9, 31 + i), 103, 103.9, 104.1) for i in range(3)]
got = I.grade(dict(tp), tp_rows, lambda a, b: [(a + 1, 104.0)], nowt + 86400)
check("a print AT the take-profit level does not fill it", got["status"], "open")
got = I.grade(dict(tp), tp_rows, lambda a, b: [(a + 1, 104.01)], nowt + 86400)
check("a print through it fills at the level, maker fee", (got["exit_why"], got["exit"], got["net"]),
      ("tp", 104.0, round(0.04 - I.TAKER - I.MAKER, 5)))
st_rows = [row(ts(2026, 11, 11, 9, 31), 97, 95.9, 96.2)]
got = I.grade(dict(tp), st_rows, lambda a, b: [], nowt + 86400)
check("the stop exits at the bid once the bid is at or below the level", (got["exit_why"], got["exit"]), ("stop", 95.9))
hold_rows = [row(ts(2026, 11, 11, 9, 30) + 60 * i, 100.5, 100.4, 100.6) for i in range(61)]
got = I.grade(dict(tp), hold_rows, lambda a, b: [], nowt + 86400)
check("the time exit comes after 60 regular-hours snapshots, at the bid", (got["exit_why"], got["exit"]), ("time", 100.4))
dn = dict(tp, rule="fade_jump")
I.RULES["fade_jump"] = dict(I.RULES["fade_jump"], tp=0.04, sl=0.04, hold="1h")
got = I.grade(dict(dn), [row(ts(2026, 11, 11, 9, 31), 104, 103.9, 104.2)], lambda a, b: [], nowt + 86400)
check("a Down stop pays the ask", (got["exit_why"], got["exit"]), ("stop", 104.2))

print("\nthe venue angle")
vt = {"K": [row(ts(2026, 11, 10, 10, 0), 100, 101.4, 101.6), row(ts(2026, 11, 10, 10, 5), 100, 100.0, 100.2),
            row(ts(2026, 11, 10, 10, 15), 100, 99.9, 100.1), row(ts(2026, 11, 10, 11, 0), 100, 99.9, 100.1),
            row(ts(2026, 11, 10, 10, 30), 100, 101.4, 101.6)]}
vt["K"].sort(key=lambda r: r["ts"])
fl = I.venue_flags(vt, [], 0)
check("a 1.5% perp-over-reference gap is flagged once an hour", [round(f["gap"], 4) for f in fl], [0.015])
I.snap_back(fl[0], vt["K"])
check("and re-read 5, 15, 60 minutes later", (fl[0]["gap_5m"], fl[0]["gap_15m"], fl[0]["gap_60m"]), (0.001, 0.0, 0.0))
check("a closed market is not flagged", I.venue_flags({"K": [row(ts(2026, 11, 10, 10, 0), 100, 101.4, 101.6, open_=False)]}, [], 0), [])

print("\nthe page section")
st = {"events": [dict(filled, rule="fade_drop", status="settled", gross=0.01, net=0.0076, exit_why="time")],
      "flags": fl, "collector": dict(last_ts=ts(2026, 11, 10, 16, 0), markets=60), "last_run": "2026-11-10T21:00:00+00:00"}
html, n_rules, settled, open_ = IB.section_and_counts(st, research={}, rebound_state={"events": []})
check("2026-11-11: all four rules retired; the live section carries only the two rebound observation lanes, says why "
      "the old ones went, keeps the collector folds",
      (I.ACTIVE_RULES, n_rules, re.findall(r'data-source="invest_([a-z0-9_]+)"', html), settled, open_,
       "were retired on Nov 11" in html, "Kalshi-only gaps" in html), ((), 2, ["rb_5d", "rb_24h"], 0, 0, True, True))
check("its id, and paper/1x in the count line", ('id="invest"' in html, "paper · 1x" in html), (True, True))
ret = IB.retired_html(st, research={})
check("the four rules move to the Retired block with their records (Fade a drop: 1 settled), marked retired",
      (len(re.findall(r'class="sp-rule[ "]', ret)), "1 settled trade" in ret, len(re.findall(r">retired Nov 11<", ret))), (4, True, 4))
check("track() logs no new event once retired (detection runs over ACTIVE_RULES only)",
      "for rule in ACTIVE_RULES:" in open(os.path.join(I.ROOT, "invest.py")).read(), True)
check("no dollar amount and no Kalshi id in the copy", (re.search(r"\$\d", html), "trade_id" in html), (None, False))
check("the copy passes the audit's guarded phrases", sandbox_audit.COPY_RE.findall(html), [])

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
