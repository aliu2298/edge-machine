#!/usr/bin/env python3
"""Offline checks for the Nasdaq open breakout paper lane (nasdaq_orb.py) and its Trading section."""
import datetime as dt
import os
import sys
import tempfile

import nasdaq_orb as N
import nasdaq_orb_build as NB
import sandbox_audit

FAILS = []
UTC = dt.timezone.utc
DAY = dt.date(2026, 10, 19)                 # a Monday, EDT (UTC-4)
WINTER = dt.date(2026, 11, 16)              # a Monday, EST (UTC-5)


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


def bar(day, hm, o, h, l, c):
    t = N.at(day, hm)
    return dict(t=t.strftime("%Y-%m-%dT%H:%M:%SZ"), o=o, h=h, l=l, c=c, v=1000)


def minutes(day, start, end):
    t = N.at(day, start)
    while t < N.at(day, end):
        et = t.astimezone(N.ET)
        yield (et.hour, et.minute)
        t += dt.timedelta(minutes=1)


def flat(day, start=(9, 20), end=(11, 45), px=100.0, skip=()):
    """A quiet tape at `px` (high/low 0.05 either side), every minute but `skip`."""
    return [bar(day, hm, px, px + 0.05, px - 0.05, px) for hm in minutes(day, start, end) if hm not in skip]


def put(bars, day, hm, **kw):
    t = N.at(day, hm).strftime("%Y-%m-%dT%H:%M:%SZ")
    for b in bars:
        if b["t"] == t:
            b.update(kw)
    return bars


print("ET clock: 9:30 New York is 13:30 UTC in October and 14:30 UTC in November")
check("summer (EDT)", N.at(DAY, (9, 30)), dt.datetime(2026, 10, 19, 13, 30, tzinfo=UTC))
check("winter (EST)", N.at(WINTER, (9, 30)), dt.datetime(2026, 11, 16, 14, 30, tzinfo=UTC))
wb = put(flat(WINTER), WINTER, (10, 5), c=101.0, h=101.0)
check("a winter day's 10:05 ET break is read at 15:05 UTC, not 14:05",
      (N.grade(WINTER, "A", wb)["signal_min"], N.grade(WINTER, "A", wb)["entry_min"]), ("10:05", "10:06"))

print("\nthe range: highs and lows of the bars inside the window only")
b = flat(DAY)
put(b, DAY, (9, 31), h=100.40)
put(b, DAY, (9, 58), l=99.70)
put(b, DAY, (10, 0), h=105.0, l=95.0)            # the first minute AFTER the 30-min window
put(b, DAY, (9, 29), h=103.0)                     # premarket: in C's range, not A's
check("A: 9:30-10:00 (30 bars), the 10:00 bar excluded",
      N.build_range(b, DAY, (9, 30), (10, 0)), (100.40, 99.70, 30))
check("B: 9:30-9:35, 5 bars", N.build_range(b, DAY, (9, 30), (9, 35)), (100.40, 99.95, 5))
check("C: premarket 9:25-9:30", N.build_range(b, DAY, (9, 25), (9, 30)), (103.0, 99.95, 5))
check("no bars in the window: no range, and the row says no_data",
      (N.build_range([], DAY, (9, 25), (9, 30)), N.grade(DAY, "C15", [])["status"]), (None, "no_data"))

print("\nthe signal is a CLOSE beyond the range, and the entry the next minute's open")
b = flat(DAY)
put(b, DAY, (10, 3), h=100.30)                    # pokes above 100.05 but closes inside
put(b, DAY, (10, 4), c=100.20, h=100.25)          # closes above: the signal
put(b, DAY, (10, 5), o=100.22)                    # entry here
put(b, DAY, (10, 19), c=100.50)                   # the bar ending 15 min after the 10:05 entry
r = N.grade(DAY, "A", b)
check("a high through the range that closes back inside is not a signal; the 10:04 close is",
      (r["side"], r["signal_min"]), ("long", "10:04"))
check("entry = 10:05 open, exit = close of the 10:19 bar (10:20)",
      (r["entry_min"], r["entry"], r["exit_min"], r["exit"]), ("10:05", 100.22, "10:20", 100.50))
check("gross bp long = (exit - entry) / entry", r["gross_bp"], round((100.50 - 100.22) / 100.22 * 1e4, 2))
s = put(flat(DAY), DAY, (9, 37), c=99.80, l=99.80)
put(s, DAY, (9, 38), o=99.81)
put(s, DAY, (9, 52), c=99.50)
rs = N.grade(DAY, "B", s)
check("B short: close below the 9:30-9:35 low, entry next open, gross = entry - exit",
      (rs["side"], rs["signal_min"], rs["entry"], rs["gross_bp"]), ("short", "09:37", 99.81, round((99.81 - 99.50) / 99.81 * 1e4, 2)))
c = put(flat(DAY), DAY, (9, 30), c=100.30, h=100.30)
put(c, DAY, (10, 0), c=101.0)
put(c, DAY, (9, 45), c=100.9)
check("C15 and C30: the same 9:30 signal, exits at 9:46 and 10:01",
      [(N.grade(DAY, k, c)["signal_min"], N.grade(DAY, k, c)["exit_min"], N.grade(DAY, k, c)["exit"]) for k in ("C15", "C30")],
      [("09:30", "09:46", 100.9), ("09:30", "10:01", 101.0)])
check("B's range is not read before 9:35: a 9:33 close above it is inside its own window",
      N.grade(DAY, "B", put(flat(DAY), DAY, (9, 33), c=100.50, h=100.50))["status"], "no_break")

print("\npoint in time: later bars never change the decision")
early = [x for x in b if N.bar_time(x) <= N.at(DAY, (10, 4))]
check("the signal from bars up to 10:04 is the signal from the whole day",
      N.signal(early, DAY, N.build_range(early, DAY, (9, 30), (10, 0)), (10, 0))[1]["t"], N.signal(b, DAY, N.build_range(b, DAY, (9, 30), (10, 0)), (10, 0))[1]["t"])
check("without the exit bar yet, the row is open, not settled",
      N.grade(DAY, "A", [x for x in b if N.bar_time(x) <= N.at(DAY, (10, 10))])["status"], "open")

print("\nno break by 11:00, and a 10:59 signal still counts")
check("a quiet tape to 11:45 is no_break", N.grade(DAY, "A", flat(DAY))["status"], "no_break")
check("a close above at 11:00 is too late", N.grade(DAY, "A", put(flat(DAY), DAY, (11, 0), c=101.0))["status"], "no_break")
late = put(flat(DAY), DAY, (10, 59), c=101.0)
check("a close above at 10:59 enters at 11:00", (N.grade(DAY, "A", late)["signal_min"], N.grade(DAY, "A", late)["entry_min"]), ("10:59", "11:00"))

print("\nnet at the bid and ask, from the quotes at the entry and exit minutes")
q = {"10:05": dict(bp=100.21, ap=100.23), "10:20": dict(bp=100.49, ap=100.51)}
rq = N.grade(DAY, "A", b, quotes=q, quote_feed="iex")
check("long: buy at the 10:05 ask, sell at the 10:20 bid", rq["net_bp"], round((100.49 - 100.23) / 100.23 * 1e4, 2))
check("the bid/ask in and out are recorded, and the spread in bp (mean of both)",
      (rq["bid_in"], rq["ask_in"], rq["bid_out"], rq["ask_out"], rq["spread_bp"]),
      (100.21, 100.23, 100.49, 100.51, round((N.spread_bp(q["10:05"]) + N.spread_bp(q["10:20"])) / 2, 2)))
check("short: sell at the entry bid, buy back at the exit ask",
      N.net_bp("short", dict(bp=99.80, ap=99.82), dict(bp=99.49, ap=99.51)), round((99.80 - 99.51) / 99.80 * 1e4, 2))
check("a missing quote leaves net empty, gross kept", (N.grade(DAY, "A", b, quotes={"10:05": q["10:05"]})["net_bp"], rq["gross_bp"]), (None, r["gross_bp"]))

print("\nholidays and half-days are skipped, from the calendar or the fallback list")
cal_full = [dict(date="2026-10-19", open="09:30", close="16:00")]
check("a full day", N.session(DAY, cal_full), "full")
check("an early close is a half-day", N.session(dt.date(2026, 11, 27), [dict(date="2026-11-27", close="13:00")]), "half_day")
check("a day missing from the calendar is a holiday", N.session(dt.date(2026, 11, 26), []), "holiday")
check("the fallback list knows Thanksgiving and the day after",
      (N.session(dt.date(2026, 11, 26)), N.session(dt.date(2026, 11, 27))), ("holiday", "half_day"))
sk = N.grade_day(dt.date(2026, 11, 27), flat(dt.date(2026, 11, 27)), cal=[dict(date="2026-11-27", close="13:00")])
check("a half-day logs every variant as skipped", ([x["status"] for x in sk], sk[0]["note"]), (["skipped"] * 4, "half-day (early close)"))
check("a Saturday is never a session", N.session(dt.date(2026, 10, 24)), "holiday")

print("\nthe ledger: one row per variant per day, settled rows final")
st = N.merge({"rows": []}, N.grade_day(DAY, b, q, cal_full, "iex"))
check("four rows for the day, ids day:variant", [x["id"] for x in st["rows"]],
      [f"2026-10-19:{k}" for k in ("A", "B", "C15", "C30")])
N.merge(st, [dict(st["rows"][0], status="open")])
check("a later open row never replaces a settled one", st["rows"][0]["status"], "settled")
summ = N.summary(st)
check("summary counts days (settled + no break), trades, and t on net", (summ["A"]["days"], summ["A"]["trades"], summ["A"]["t_on"]),
      (1, 1, "net"))

print("\nthe live run, on a fake clock and a fake API")
clock = {"t": dt.datetime(2026, 10, 19, 13, 5, tzinfo=UTC)}       # 9:05 ET, the cron start


def sleeper(sec):
    clock["t"] += dt.timedelta(seconds=sec)


calls = []


def get(url):
    calls.append(url)
    if "calendar" in url:
        return cal_full
    if "quotes/latest" in url:
        if "feed=sip" in url:
            raise RuntimeError("HTTP 403")
        et = clock["t"].astimezone(N.ET)
        return {"quote": dict(bp=100.21, ap=100.23, t=clock["t"].isoformat()) if (et.hour, et.minute) == (10, 5)
                else dict(bp=100.49, ap=100.51, t=clock["t"].isoformat())}
    if "/bars" in url:
        return {"bars": b}
    raise AssertionError(url)


with tempfile.TemporaryDirectory() as tmp:
    day_path = os.path.join(tmp, "day.json")
    out = N.live(day_path, now_fn=lambda: clock["t"], sleeper=sleeper, get=get)
    check("the SIP quote is refused, so the run uses IEX and says so", out["quote_feed"], "iex")
    check("bars are read only after 11:49 ET (15 minutes past the last exit)", clock["t"] >= N.at(DAY, (11, 49)), True)
    check("one quote snapshot a minute from 9:24 to 11:32 ET", (len(out["quotes"]), min(out["quotes"]), max(out["quotes"])),
          (129, "09:24", "11:32"))
    a = [x for x in out["rows"] if x["variant"] == "A"][0]
    check("variant A settles with the live quotes", (a["status"], a["ask_in"], a["bid_out"]), ("settled", 100.23, 100.49))
    check("no order endpoint is ever called", any("/orders" in u or "/positions" in u for u in calls), False)
    hol = {"t": dt.datetime(2026, 11, 26, 14, 5, tzinfo=UTC)}
    sk = N.live(day_path, now_fn=lambda: hol["t"], sleeper=lambda s: None, get=lambda u: [] if "calendar" in u else {})
    check("on a holiday the live run logs skips and polls nothing", [x["status"] for x in sk["rows"]], ["skipped"] * 4)

print("\nthe Trading section")
h = NB.section(st)
check("title, paper note, review rule and all four variants",
      ("Nasdaq open breakout (paper)" in h, "never places an order" in h, "10+ settled days per variant" in h,
       all(f"<b>{k}</b>" in h for k in N.VARIANTS)), (True, True, True, True))
check("the daily table carries the bid/ask and net", ("100.21/100.23 → 100.49/100.51" in h, "IEX top of book" in h), (True, True))
check("an empty ledger says when the first read is", "Monday 2026-10-19" in NB.section({"rows": []}), True)
check("no guarded public phrase in the section", sandbox_audit.COPY_RE.findall(h + NB.section({"rows": []})), [])

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
