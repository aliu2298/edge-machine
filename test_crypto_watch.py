#!/usr/bin/env python3
"""Offline checks for the two display-only watch splits on the Crypto below row (crypto_watch.py, 2026-11-13): the close date in Eastern time, the
quiet range as the research defined it (copied), the fixed cut, no look-ahead, the counted-from-Nov-13 record with the full record as background,
the dated note, and a page builder that makes no venue call."""
import datetime as dt
import sys

import crypto_watch as W
import sandbox_audit

FAILS = []
UTC = dt.timezone.utc


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


print("the close date in Eastern time")
sat, fri = "KXBTCD-26NOV1417-T99000", "KXBTCD-26NOV1317-T99000"
check("the ticker's 17:00 ET close, in standard time and in daylight time", (W.close_of(sat).isoformat(), W.close_of("KXETHD-26JUL1517-T3000").isoformat()),
      ("2026-11-14T22:00:00+00:00", "2026-07-15T21:00:00+00:00"))
check("Saturday Nov 14 is a weekend close, Friday Nov 13 and Monday Nov 16 are not",
      (W.is_weekend(W.close_of(sat)), W.is_weekend(W.close_of(fri)), W.is_weekend(W.close_of("KXBTCD-26NOV1617-T1"))), (True, False, False))
check("Sunday counts as a weekend, by the Eastern date, not the UTC date (a Sunday 17:00 ET close is 22:00Z, still Sunday)",
      W.is_weekend(W.close_of("KXBTCD-26NOV1517-T1")), True)
check("a ticker with no close reads as nothing", W.close_of("KXBTCD-T99"), None)

print("\nthe quiet range (the research's definition)")
CLOSE = int(W.close_of(fri).timestamp())


def candle(h, bid, ask):
    return (CLOSE - h * 3600, bid, ask)


# NO mid = 1 - the YES mid; the six hours 3..8 before the close.
cs = [candle(3, 0.20, 0.22), candle(4, 0.22, 0.24), candle(5, 0.18, 0.20), candle(6, 0.21, 0.23), candle(7, 0.25, 0.27), candle(8, 0.30, 0.32)]
r = W.quiet_range(cs, CLOSE)
check("range = highest minus lowest NO mid over the six hourly quotes", round(r, 4), round(0.81 - 0.69, 4))
check("at least 4 of the 6 quotes are needed: 3 give nothing, 4 give a range", (W.quiet_range(cs[:3], CLOSE), W.quiet_range(cs[:4], CLOSE) is not None), (None, True))
check("a candle after the 3-hour quote (the entry) is never read", W.quiet_range(cs + [(CLOSE - 2 * 3600, 0.95, 0.97)], CLOSE), r)
check("a sparse archived market carries the last candle before each hour, a live one does not",
      (W.quiet_range(cs[:3], CLOSE), W.quiet_range([candle(3, 0.2, 0.22), candle(8, 0.3, 0.32)], CLOSE, carry=True) is not None, W.quiet_range([candle(3, 0.2, 0.22), candle(8, 0.3, 0.32)], CLOSE)),
      (None, True, None))
check("the cut is the research's period-A median, fixed at 0.33", round(W.QUIET_MAX, 4), 0.33)
check("exactly at the cut is quiet, a hair over is busy (the research used <=)",
      ((0.32999999999999996 <= W.QUIET_MAX), (0.3301 <= W.QUIET_MAX)), (True, False))
check("the hours are 3 to 8 before the close: all known before the lane's entry (about 2.8h before the close)", (min(W.HOURS), max(W.HOURS), 3 >= 2.8), (3, 8, True))

print("\nreading the rungs")
state = W.load("/nonexistent")


class FakeNet:
    def __init__(self, cs):
        self.cs, self.calls = cs, []

    def __call__(self, path):
        self.calls.append(path)
        return dict(candlesticks=[dict(end_period_ts=e, yes_bid=dict(close_dollars=str(b)), yes_ask=dict(close_dollars=str(a))) for e, b, a in self.cs])


bet = lambda tk, date, status="won", price=0.78, logged=None: dict(id=f"crypto_fav_band_below:{tk}", source=W.LANE, sport=W.SPORT, market_id=tk, bet=True, pick="b",
                                                                   price=price, status=status, date=date, start=f"{date}T22:05:00+00:00", venue="kalshi_binary",
                                                                   logged=logged or f"{date}T19:30:00+00:00", pnl=22.0 if status == "won" else -100.0, result="no" if status == "won" else "yes")
d = dict(quotes=[bet(fri, "2026-11-13", "open")], meta={}, coverage={}, _archive=[])
net = FakeNet(cs)
before = dt.datetime.fromtimestamp(CLOSE - 3 * 3600, UTC)
check("not read before the hour of the entry quote is final (close - 3h + 5 min)", W.run(state, d, before, net), 0)
check("read once after it", (W.run(state, d, before + dt.timedelta(minutes=6), net), round(state["rungs"][fri]["range"], 4), state["rungs"][fri]["quotes"]), (1, round(r, 4), 6))
check("and not read again", (W.run(state, d, before + dt.timedelta(hours=2), net), len(net.calls)), (0, 1))

print("\nthe splits and the record")
st = dict(rungs={"A-26NOV1217-T1": dict(range=0.10), "A-26NOV1417-T1": dict(range=0.50), "A-26NOV1317-T1": dict(range=None)})
b1, b2, b3 = bet("A-26NOV1217-T1", "2026-11-12"), bet("A-26NOV1417-T1", "2026-11-14", "lost"), bet("A-26NOV1317-T1", "2026-11-13")
check("Thursday and quiet", W.split_of(b1, st), dict(day="weekday", calm="quiet"))
check("Saturday and busy", W.split_of(b2, st), dict(day="weekend", calm="busy"))
check("too few quotes: no quiet/busy class, a weekday", W.split_of(b3, st), dict(day="weekday", calm=None))
d2 = dict(quotes=[b1, b2, b3], meta={}, coverage={}, _archive=[])
mine, full = W.records(d2, st, True), W.records(d2, st, False)
check("counted from Nov 13: the Nov 12 bet is not in the watch", (mine["weekday"]["n"], mine["quiet"]["n"], mine["weekend"]["n"], mine["busy"]["n"]), (1, 0, 1, 1))
check("the full record, background: every bet", (full["weekday"]["n"], full["quiet"]["n"], full["weekend"]["n"], full["busy"]["n"]), (2, 1, 1, 1))
check("a market-day is one outcome, after fees (a winner at 78c returns about 26%, a loser -100%)", (full["quiet"]["won"], round(full["quiet"]["roi_fee"], 2), round(full["busy"]["roi_fee"], 2)), (1, 0.26, -1.0))

print("\nthe page block")
html = W.block(d2, st)
check("the dated note and the label are there", ("Two watches added Nov 13 by Olu; read at 30 days each." in html, "Watch, not a rule" in html), (True, True))
check("counted from the date, read date, full record marked not counted", ("2026-11-13" in html, "Dec 13" in html, "background and not counted" in html), (True, True, True))
check("both definitions and the known-at-entry line are said", all(x in html for x in ("close date in Eastern time", "known at entry", "33 points", "median")), True)
check("percentages only; passes the public copy guard", ("$" in html, bool(sandbox_audit.COPY_RE.search(html))), (False, False))
src = open("crypto_build.py").read()
check("the page builder only reads the ledger file: crypto_watch is imported inside the row's definition, and the builder has no fetch",
      ("import crypto_watch as W" in src and "W.block(d)" in src and "daily_track" not in src), True)
check("only the below row shows it", 'row.get("name") == "crypto_fav_band_below"' in src, True)
wf = open(".github/workflows/crypto-watch.yml").read()
check("the workflow runs the tests, the read, and saves only its own file", ("test_crypto_watch.py" in wf, "python3 crypto_watch.py" in wf, "data/crypto_watch_ledger.json" in wf), (True, True, True))

print()
if FAILS:
    print(f"{len(FAILS)} FAILED")
    sys.exit(1)
print("crypto watch passed")
