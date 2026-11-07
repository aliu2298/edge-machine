#!/usr/bin/env python3
"""Offline checks for the Earnings & news calls paper lane (earnings_news.py) and its Trading section."""
import datetime as dt
import json
import re
import sys
import urllib.parse

import earnings_news as E
import earnings_news_build as EB
import sandbox_audit

FAILS = []
UTC = dt.timezone.utc


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


def ts(y, m, d, h, mi=0):
    return int(dt.datetime(y, m, d, h, mi, tzinfo=UTC).timestamp())


class Fake:
    """A stand-in for the public API: per ticker, minute quotes and prints over a window."""

    def __init__(self, quotes, trades):
        self.quotes, self.trades = quotes, trades      # {ticker: [(end_ts, bid, ask)]}, {ticker: [(ts, px)]}

    def __call__(self, url, headers=None):
        u = urllib.parse.urlparse(url)
        q = dict(urllib.parse.parse_qsl(u.query))
        if "/candlesticks" in u.path:
            tk = u.path.split("/markets/")[1].split("/")[0]
            t0, t1, per = int(q["start_ts"]), int(q["end_ts"]), int(q["period_interval"])
            rows = [r for r in self.quotes.get(tk, []) if t0 <= r[0] <= t1]
            if per == 60:                                # hourly: the last minute quote of each hour
                hours = {}
                for r in rows:
                    hours[(r[0] - 1) // 3600 * 3600 + 3600] = r
                rows = [(h, r[1], r[2]) for h, r in sorted(hours.items())]
            return {"candlesticks": [{"end_period_ts": e, "bid": {"close": str(b)}, "ask": {"close": str(a)}}
                                     for e, b, a in rows]}
        if u.path.endswith("/trades"):
            tk, t0, t1 = q["ticker"], int(q["min_ts"]), int(q["max_ts"])
            return {"trades": [{"price": str(p), "created_time": dt.datetime.fromtimestamp(t, UTC).isoformat()}
                               for t, p in self.trades.get(tk, []) if t0 <= t <= t1], "cursor": ""}
        raise AssertionError(url)


def flat_book(t0, t1, bid, ask, step=60):
    return [(t, bid, ask) for t in range(t0, t1 + 1, step)]


print("pre-registration")
check("the families file is the one registered (edit = a NEW family, never an edit)",
      E.families_sha(), E.FAMILIES_SHA256)
check("five families", list(E.FAMILIES), ["kpi_drift", "runup", "post_drift", "news", "sentiment"])

print("\nsessions and report anchors")
check("Thanksgiving is not a session", E.add_sessions(dt.date(2026, 11, 25), 1), dt.date(2026, 11, 27))
t, D, P = E.report_time({"date": "2026-11-17", "time": "after-hours"})
check("after close: reaction session is the next day, P is the report day's close",
      (D, P.astimezone(E.ET).strftime("%m-%d %H")), (dt.date(2026, 11, 18), "11-17 16"))
t, D, P = E.report_time({"date": "2026-11-17", "time": "pre-market"})
check("before open: reaction session is the report day, P the previous close",
      (D, P.astimezone(E.ET).strftime("%m-%d %H"), t.astimezone(E.ET).hour), (dt.date(2026, 11, 17), "11-16 16", 7))

print("\nperp hours")
fri_close = dt.datetime(2026, 11, 6, 17, 0, tzinfo=E.ET).timestamp()
check("closed Friday 17:00 ET to Sunday 18:00 ET",
      (E.perp_open(fri_close - 60), E.perp_open(fri_close), E.perp_open(fri_close + 49 * 3600 - 60),
       E.perp_open(fri_close + 49 * 3600)), (True, False, False, True))

print("\nthe honest fill")
T0 = ts(2026, 11, 10, 15)                       # Tuesday 10:00 ET
book = {"KXAAAPERP": flat_book(T0 - 600, T0 + 7200, 10.0, 10.1)}
now = dt.datetime.fromtimestamp(T0 + 7200, UTC)
g = Fake(book, {"KXAAAPERP": [(T0 + 90, 10.1)]})
check("a print at the ask inside 5 minutes fills the buy at the ask",
      E.honest_fill("KXAAAPERP", dt.datetime.fromtimestamp(T0, UTC), True, get=g, now=now), ("filled", T0, 10.1))
g = Fake(book, {"KXAAAPERP": [(T0 + 90, 10.05)]})
check("a print inside the spread does not fill a buy at the ask",
      E.honest_fill("KXAAAPERP", dt.datetime.fromtimestamp(T0, UTC), True, get=g, now=now)[0], "no_fill")
g = Fake(book, {"KXAAAPERP": [(T0 + 1000, 10.0)]})
check("no print on the first quote: the next quote 5 minutes later fills (a sell at the bid)",
      E.honest_fill("KXAAAPERP", dt.datetime.fromtimestamp(T0, UTC), False, get=g, now=now), ("filled", T0 + 900, 10.0))
check("a quote too recent to have its 5-minute window is pending",
      E.honest_fill("KXAAAPERP", dt.datetime.fromtimestamp(T0, UTC), True, get=g,
                    now=dt.datetime.fromtimestamp(T0 + 120, UTC))[0], "pending")
SAT = ts(2026, 11, 7, 15)
check("a call logged while the perp is closed waits for the reopen",
      E.honest_fill("KXAAAPERP", dt.datetime.fromtimestamp(SAT, UTC), True,
                    get=Fake({"KXAAAPERP": flat_book(SAT - 3600 * 20, SAT + 3600, 10, 10.1)}, {}),
                    now=dt.datetime.fromtimestamp(SAT + 3600, UTC))[0], "pending")

print("\na graded leg")
book = {"KXAAAPERP": flat_book(T0 - 600, T0 + 3600, 10.0, 10.1) + flat_book(T0 + 3660, T0 + 9000, 11.0, 11.1)}
g = Fake(book, {"KXAAAPERP": [(T0 + 30, 10.1), (T0 + 7200 + 30, 11.0)]})
r = E.leg("KXAAAPERP", 1, dt.datetime.fromtimestamp(T0, UTC), dt.datetime.fromtimestamp(T0 + 7200, UTC), get=g,
          now=dt.datetime.fromtimestamp(T0 + 9000, UTC))
check("Up: buy the ask, sell the bid, two taker fees", (r["status"], r["net"]),
      ("settled", round((11.0 - 10.1) / 10.1 - 0.0024, 6)))
r = E.leg("KXAAAPERP", -1, dt.datetime.fromtimestamp(T0, UTC), dt.datetime.fromtimestamp(T0 + 7200, UTC),
          get=Fake(book, {"KXAAAPERP": [(T0 + 30, 10.0), (T0 + 7200 + 30, 11.1)]}),
          now=dt.datetime.fromtimestamp(T0 + 9000, UTC))
check("Down: sell the bid, buy back the ask", r["net"], round(-(11.1 - 10.0) / 10.0 - 0.0024, 6))

print("\nthe KPI ladder read")
lad = [{"strike_type": "greater", "floor_strike": k, "yes_bid_dollars": b, "yes_ask_dollars": a}
       for k, b, a in ((380, .86, .94), (385, .74, .82), (390, .51, .60), (395, .24, .33), (400, .07, .15),
                       (405, .02, .08))]
r = E.ladder_read(lad)
check("median interpolated at the 50% crossing", round(r["median"], 3), round(390 + (0.555 - 0.5) / (0.555 - 0.285) * 5, 3))
check("an empty book (a 0/97 rung) is dropped and the ladder is unread",
      E.ladder_read([{"strike_type": "greater", "floor_strike": k, "yes_bid_dollars": 0.0, "yes_ask_dollars": 0.97}
                     for k in (1, 2, 3, 4)]), None)

print("\nrule logging")
st = {"registered": E.REGISTERED, "calendar": [
    {"sym": "AAA", "perp": "KXAAAPERP", "date": "2026-11-17", "time": "pre-market", "kpi": [
        {"event": "KXAAA-26NOVX", "title": "AAA widgets in Q3"}], "mentions": []}],
    "kpi_reads": [{"event": "KXAAA-26NOVX", "sym": "AAA", "at": "2026-11-07T04:00:00Z",
                   "read": {"median": 100.0, "width": 8.0, "rungs": 5}},
                  {"event": "KXAAA-26NOVX", "sym": "AAA", "at": "2026-11-16T13:30:00Z",
                   "read": {"median": 103.0, "width": 8.0, "rungs": 5}}],
    "predictions": []}
early = dt.datetime(2026, 11, 7, 4, 0, tzinfo=UTC)
got = E.log_rules(st, now=early, get=None, perps=[])
check("runup logged ahead of its entry, 5 sessions before P", got, ["runup:AAA:2026-11-17"])
p = st["predictions"][0]
check("runup entry/exit: 16:00 ET Nov 9 to 16:00 ET Nov 16",
      (p["entry_due"], p["exit_due"]), ("2026-11-09T21:00:00Z", "2026-11-16T21:00:00Z"))
check("logging is idempotent", E.log_rules(st, now=early, get=None, perps=[]), [])
late = dt.datetime(2026, 11, 10, 22, 0, tzinfo=UTC)
check("a runup is never logged after its entry",
      E.log_rules({"calendar": [dict(st["calendar"][0], sym="BBB")], "kpi_reads": [], "predictions": []},
                  now=late, get=None, perps=[]), [])
win = dt.datetime(2026, 11, 16, 14, 0, tzinfo=UTC)         # 17 hours before a 07:00 ET report
check("outside 30-6 hours before the report nothing is logged",
      E.log_rules(st, now=dt.datetime(2026, 11, 16, 4, 0, tzinfo=UTC), get=None, perps=[]), [])
got = E.log_rules(st, now=win, get=None, perps=[])
k = [q for q in st["predictions"] if q["family"] == "kpi_drift"][0]
check("KPI drift: +3 v threshold 2 is an Up call, entry now, exit at D's close",
      (got, k["side"], k["exit_due"]), (["kpi_drift:AAA:KXAAA-26NOVX"], 1, "2026-11-17T21:00:00Z"))

print("\nnews calls")
nst = {"calendar": [], "kpi_reads": [], "predictions": []}
perps = [{"title": "NVDA", "ticker": "KXNVDAPERP"}]
n0 = dt.datetime(2026, 11, 9, 15, 0, tzinfo=UTC)
p = E.log_news(nst, "NVDA", "up", "1d", 0.6, "Guidance raised.", "https://example.com/a",
               "2026-11-09T13:00:00Z", now=n0, perps=perps)
check("a 1d call exits the same clock time the next session",
      (p["entry_due"], p["exit_due"]), ("2026-11-09T15:00:00Z", "2026-11-10T15:00:00Z"))
for label, kw in (("a source older than 6 hours is refused", dict(published="2026-11-09T08:00:00Z")),
                  ("a source from the future is refused", dict(published="2026-11-09T16:00:00Z"))):
    try:
        E.log_news(nst, "NVDA", "up", "1d", 0.6, "x", "u", kw["published"], now=n0, perps=perps)
        check(label, "logged", "refused")
    except ValueError:
        check(label, "refused", "refused")
check("the random baseline's side is fixed by the id", (E.coin("x"), E.coin("x")) in ((1, 1), (-1, -1)), True)

print("\nsummary and the section")
sp = {"calendar": st["calendar"], "kpi_reads": [], "predictions": [
    {"id": f"sentiment:S{i}:d", "family": "sentiment", "sym": f"S{i}", "side": 1, "status": "settled",
     "logged_at": "2026-11-09T20:00:00Z", "entry_due": "2026-11-09T20:00:00Z", "exit_due": "2026-11-10T20:00:00Z",
     "reason": "r", "net": 0.01 * (i % 3), "random_side": 1,
     "baselines": {k: {"status": "settled", "net": 0.0} for k in ("up", "random", "spy")}} for i in range(12)]}
s = E.summary(sp)["sentiment"]
check("12 settled is a review, not a decision", (s["settled"], s["verdict"]), (12, "review due"))
check("the fade pays the costs again", round(s["fade_avg_net"], 6), round(-s["avg_net"] - 4 * E.TAKER, 6))
h, n, settled, open_ = EB.section_and_counts(sp)
check("one row per family", h.count('class="sp-rule"'), 5)
check("the caveat fold leads", h.index("a headline is not an edge") < h.index('class="sp-rule"'), True)
check("counts", (n, settled), (5, 12))
check("no guarded public phrase", sandbox_audit.COPY_RE.findall(h + EB.CAVEAT + str(EB.DEFS)), [])
check("no dollar amounts in the public copy", re.findall(r"\$\s?\d", h), [])
check("no market ids in the public copy", re.findall(r"\bKX[A-Z0-9-]{3,}", h), [])
real = E.load()
check("the committed ledger renders", "earnings-news" in EB.safe_section(), True)
check("every committed prediction was logged before its entry",
      all(q["logged_at"] <= q["entry_due"] for q in real["predictions"] if q.get("entry_due")), True)

print("\n" + ("FAILED: " + ", ".join(FAILS) if FAILS else "all earnings & news checks pass"))
sys.exit(1 if FAILS else 0)
