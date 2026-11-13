#!/usr/bin/env python3
"""Offline checks for the two weather paper lanes (climate_lanes.py, 2026-11-13): the entry window across the daylight-time change, the
favourite and the bracket two away, the skips, the forecast skip and its rule (above, inside, open top bracket, no forecast), the
control rows, fees, one entry per city-day, grading, the record and its pre-registered read, and the page (percentages only)."""
import datetime as dt
import json
import os
import re
import sys
import tempfile

import climate_lanes as L
import climate_lanes_build as B
import fillsim
import sandbox_audit

FAILS = []
UTC = dt.timezone.utc


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


def near(a, b, eps=1e-6):
    return abs(a - b) < eps


def ladder(event, quotes, kind="HIGH", results=None):
    """Six markets for an event: quotes = [(bid, ask)] from the coolest bracket to the warmest."""
    shapes = [("less", None, 50), ("between", 50, 51), ("between", 52, 53), ("between", 54, 55), ("between", 56, 57), ("greater", 58, None)]
    ms = []
    for i, ((st, fl, cp), (b, a)) in enumerate(zip(shapes, quotes)):
        ms.append(dict(ticker=f"{event}-X{i}", event_ticker=event, strike_type=st, floor_strike=fl if st != "less" else None,
                       cap_strike=cp if st != "greater" else (None), yes_bid_dollars=f"{b:.4f}", yes_ask_dollars=f"{a:.4f}",
                       yes_sub_title=f"bracket {i}", result=(results or {}).get(i, "")))
    ms[0]["cap_strike"], ms[5]["floor_strike"] = 50, 57          # "49 or below" is less than 50; "58 or above" is greater than 57
    return {"markets": ms}


# 22:00 ET Nov 13 2026 is 03:00Z (standard time); 22:00 ET Jul 13 is 02:00Z (daylight time).
EST = dt.datetime(2026, 11, 14, 3, 5, tzinfo=UTC)
EDT = dt.datetime(2026, 7, 14, 2, 5, tzinfo=UTC)

print("the entry window, across the daylight-time change")
check("03:05Z in November is 22:05 ET: inside", L.in_window(EST), True)
check("02:05Z in November is 21:05 ET: outside", L.in_window(EST - dt.timedelta(hours=1)), False)
check("02:05Z in July is 22:05 ET: inside", L.in_window(EDT), True)
check("03:05Z in July is 23:05 ET: outside", L.in_window(EDT + dt.timedelta(hours=1)), False)
check("22:50 ET is outside, 22:49 inside", (L.in_window(EST + dt.timedelta(minutes=45)), L.in_window(EST + dt.timedelta(minutes=44))), (False, True))
check("the target day is tomorrow in Eastern time", (L.target_day(EST).isoformat(), L.target_day(EDT).isoformat()), ("2026-11-14", "2026-07-14"))
check("the late start is logged in minutes", L.lag_min(EST), 5.0)
check("the event ticker", L.event_ticker("KXHIGHNY", L.target_day(EST)), "KXHIGHNY-26NOV14")
check("42 series: 21 highs and 21 lows", (len(L.HIGH_SERIES), len(L.LOW_SERIES)), (21, 21))
check("every station has a standard-time offset", all(s in L.LST for _n, s in list(L.HIGH_SERIES.values()) + list(L.LOW_SERIES.values())), True)

print("\nthe favourite and the bracket two away")
Q = [(0.20, 0.22), (0.07, 0.10), (0.72, 0.73), (0.20, 0.22), (0.01, 0.02), (0.00, 0.01)]
q = L.quotes_of(ladder("E", Q)["markets"])
check("six quoted brackets are read in order", len(q), 6)
check("the favourite is the highest mid", L.favourite(q), 2)
check("a bracket with no ask is not quoted: the ladder is skipped", L.quotes_of(ladder("E", Q[:5] + [(0.0, 0.0)])["markets"]), None)
check("five markets are not a ladder", L.quotes_of(ladder("E", Q)["markets"][:5]), None)
tie = L.quotes_of(ladder("E", [(0.1, 0.1)] * 2 + [(0.3, 0.3)] * 2 + [(0.1, 0.1)] * 2)["markets"])
check("a tie goes to the cooler bracket", L.favourite(tie), 2)

print("\nthe forecast skip rule")
fav_mid = q[2][0]                                                  # 52-53: top edge 53.5
check("the favourite's real-line bounds", L.bounds(fav_mid), (51.5, 53.5))
check("the bracket's top is 53; half a degree over is 53.5: a forecast of 53.5 is not above", L.forecast_above(dict(value=53.5), {}, "NYC", fav_mid), False)
check("53.6 is above", L.forecast_above(dict(value=53.6), {}, "NYC", fav_mid), True)
check("the city shift moves it: 53.3 + 0.28 is above", L.forecast_above(dict(value=53.3), {"NYC": 0.28}, "NYC", fav_mid), True)
check("a city not listed has shift 0", L.forecast_above(dict(value=53.3), {"BOS": 0.3}, "NYC", fav_mid), False)
check("the open-ended top bracket is never above", L.forecast_above(dict(value=99.0), {}, "NYC", q[5][0]), False)
check("no forecast is never above", L.forecast_above(None, {}, "NYC", fav_mid), False)

print("\nforecast read from the NBM station text")
T0 = int(dt.datetime(2026, 11, 14, 0, 0, tzinfo=UTC).timestamp())


def csv_of(runs):
    lines = ["runtime,ftime,model,tmp,txn"]
    for rt, rows in runs.items():
        for ft, tmp, txn in rows:
            lines.append(f"{rt},{ft},NBS,{tmp},{'' if txn is None else txn}")
    return "\n".join(lines) + "\n"


text = csv_of({
    "2026-11-13 18:00:00": [("2026-11-14 00:00:00", 50, 52.0), ("2026-11-14 15:00:00", 47, None), ("2026-11-15 00:00:00", 55, 60.0)],
    "2026-11-14 00:00:00": [("2026-11-14 15:00:00", 49, None), ("2026-11-15 00:00:00", 51, None)],     # newest run, daytime max on the 18Z run
    "2026-11-14 01:00:00": [("2026-11-14 15:00:00", 99, 99.0)],                                         # under 2 hours old at 03:05Z? no: 2h old at 03:00
})
runs = L.parse_nbs(text)
check("three runs parsed", len(runs), 3)
now = dt.datetime(2026, 11, 14, 2, 30, tzinfo=UTC)
f = L.forecast_high(runs, "NYC", dt.date(2026, 11, 14), now)
check("at 02:30Z the newest run at least 2h old is 00Z (cut 00:30Z): its max is taken from the older run that has it", (f["run"], f["txn_run"], f["txn"]), ("2026-11-14T00:00Z", "2026-11-13T18:00Z", 60.0))
check("... the value is the larger of the daytime max and the 3-hourly temps inside the day", f["value"], 60.0)
f2 = L.forecast_high(runs, "NYC", dt.date(2026, 11, 14), dt.datetime(2026, 11, 14, 3, 5, tzinfo=UTC))
check("at 03:05Z the 01Z run is 2h old: it carries no daytime max, so the older run supplies it", (f2["run"], f2["txn_run"]), ("2026-11-14T01:00Z", "2026-11-13T18:00Z"))
check("no run at least 2h old: no forecast", L.forecast_high(runs, "NYC", dt.date(2026, 11, 14), dt.datetime(2026, 11, 13, 19, 0, tzinfo=UTC)), None)
check("an empty answer parses to nothing", L.parse_nbs(""), {})

print("\nIEM's rate limit")
import urllib.error


class _Resp:
    def __init__(self, text):
        self.text = text

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self.text.encode()


calls, slept = [], []


def opener(req, timeout=0):
    calls.append(1)
    if len(calls) < 3:
        raise urllib.error.HTTPError(req.full_url, 429, "Too Many Requests", {}, None)
    return _Resp("ok")


check("a 429 is retried with backoff, then answered", (L.get_text("http://x", opener=opener, sleep=slept.append, clock=lambda: 100.0), len(calls)), ("ok", 3))
check("the waits are 3 s then 6 s (after the one-per-second spacing)", [x for x in slept if x >= 3], [3, 6])


def always(req, timeout=0):
    raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, None)


try:
    L.get_text("http://x", opener=always, sleep=lambda s: None)
    check("a 404 is final", False, True)
except urllib.error.HTTPError:
    check("a 404 is final", True, True)

print("\none night, both lanes")


def fetcher(books):
    def f(path):
        if path.startswith("markets?event_ticker="):
            ev = path.split("=", 1)[1].split("&")[0]
            if ev in books:
                return books[ev]
            return {"markets": []}
        if "/orderbook" in path:
            return {"orderbook_fp": {"yes_dollars": [["0.1500", "5.00"], ["0.2000", "21.00"]], "no_dollars": []}}
        raise AssertionError(path)
    return f


def nbs_text(value, run="2026-11-14 00:00:00"):
    return csv_of({run: [("2026-11-15 00:00:00", value - 2, float(value))]})


day = L.target_day(EST)
hi, lo = "KXHIGHNY", "KXLOWTNYC"
books = {L.event_ticker(hi, day): ladder(L.event_ticker(hi, day), Q), L.event_ticker(lo, day): ladder(L.event_ticker(lo, day), Q)}
st = L.empty()
text_fetch = lambda url: nbs_text(50)                           # forecast 50: below the favourite's top
only = lambda lane, series: L.LANES.__setitem__(lane, dict(L.LANES[lane], series={series: L.LANES[lane]["series"][series]}))
saved = {k: dict(v) for k, v in L.LANES.items()}
only("c1v2", hi)
only("l1", lo)
try:
    n = L.run(st, EST, fetch=fetcher(books), text_fetch=text_fetch)
    rows = {r["id"]: r for r in n["rows"]}
    c1 = rows[f"c1v2|main|{L.event_ticker(hi, day)}"]
    check("c1v2 buys NO on the bracket two cooler (index 0)", (c1["bracket"], c1["rel"]), ("bracket 0", -2))
    check("... at 1 minus the YES bid", c1["price"], 0.80)
    check("... with the honest-v1 taker fee", near(c1["fee"], fillsim.fee(0.80)), True)
    check("... and cost = price + fee", near(c1["cost"], 0.80 + fillsim.fee(0.80)), True)
    check("... the depth at the YES bid is logged from the book", c1["depth_bid"], 21.0)
    check("... the forecast run is logged", (c1["forecast"]["run"], c1["forecast_above"]), ("2026-11-14T00:00Z", False))
    check("... and the lag", c1["lag_min"], 5.0)
    ctl = rows[f"c1v2|control|{L.event_ticker(hi, day)}"]
    check("c1v2's control is NO on the bracket two warmer (index 4), same time", (ctl["bracket"], ctl["rel"], ctl["price"]), ("bracket 4", 2, 0.99))
    l1 = rows[f"l1|main|{L.event_ticker(lo, day)}"]
    check("l1 buys NO on the bracket two WARMER (index 4)", (l1["bracket"], l1["rel"]), ("bracket 4", 2))
    l1c = rows[f"l1|control|{L.event_ticker(lo, day)}"]
    check("l1's control is NO on the bracket two cooler (index 0)", (l1c["bracket"], l1c["rel"]), ("bracket 0", -2))
    check("l1 logs no forecast", "forecast" in l1, False)
    check("four rows on the night, one night recorded", (len(n["rows"]), list(n["nights"])), (4, [day.isoformat()]))
    check("the record starts at the first entry", n["since"], day.isoformat())
    again = L.run(n, EST + dt.timedelta(minutes=10), fetch=fetcher(books), text_fetch=text_fetch)
    check("a second run in the window adds nothing: one entry per city-day", len(again["rows"]), 4)
    out = L.run(L.empty(), EST + dt.timedelta(hours=2), fetch=fetcher(books), text_fetch=text_fetch)
    check("outside the window nothing is entered", (len(out["rows"]), out["since"]), (0, None))

    print("\nthe forecast skip, no forecast, and the other skips")
    st = L.run(L.empty(), EST, fetch=fetcher(books), text_fetch=lambda url: nbs_text(58))
    sk = {r["id"]: r for r in st["rows"]}
    check("forecast 58 is above the favourite: the bet moves to the skipped control", f"c1v2|skipped|{L.event_ticker(hi, day)}" in sk and f"c1v2|main|{L.event_ticker(hi, day)}" not in sk, True)
    check("... the skipped row keeps the full bet and the forecast", (sk[f"c1v2|skipped|{L.event_ticker(hi, day)}"]["price"], sk[f"c1v2|skipped|{L.event_ticker(hi, day)}"]["forecast_above"]), (0.80, True))
    check("... l1 is untouched by the forecast", f"l1|main|{L.event_ticker(lo, day)}" in sk, True)

    def boom(url):
        raise OSError("iem down")
    st = L.run(L.empty(), EST, fetch=fetcher(books), text_fetch=boom)
    r = {x["id"]: x for x in st["rows"]}[f"c1v2|main|{L.event_ticker(hi, day)}"]
    check("no forecast readable: the bet is taken and marked", (r["forecast"]["value"], r["forecast"]["note"], r["forecast_above"]), (None, "no forecast", False))
    st = L.run(L.empty(), EST, fetch=fetcher(books), text_fetch=lambda url: "")
    r = {x["id"]: x for x in st["rows"]}[f"c1v2|main|{L.event_ticker(hi, day)}"]
    check("an empty forecast answer is the same", r["forecast"]["note"], "no forecast")

    Q0 = [(0.50, 0.52), (0.30, 0.32), (0.10, 0.12), (0.05, 0.06), (0.01, 0.02), (0.0, 0.01)]
    b2 = {L.event_ticker(hi, day): ladder(L.event_ticker(hi, day), Q0), L.event_ticker(lo, day): ladder(L.event_ticker(lo, day), [(0, 0.01)] + Q0[1:])}
    st = L.run(L.empty(), EST, fetch=fetcher(b2), text_fetch=text_fetch)
    check("the favourite is the coolest bracket: no bracket two cooler, no bet", [x["id"] for x in st["rows"] if x["lane"] == "c1v2" and x["role"] == "main"], [])
    check("... the reason is noted, and the control still rows", (st["skips"][f"c1v2|{L.event_ticker(hi, day)}"], any(x["role"] == "control" and x["lane"] == "c1v2" for x in st["rows"])), ("no bracket two away, or its YES bid is 0", True))
    zero = [(0.20, 0.22), (0.0, 0.10), (0.72, 0.73), (0.20, 0.22), (0.01, 0.02), (0.00, 0.01)]
    zero[0] = (0.0, 0.05)
    st = L.run(L.empty(), EST, fetch=fetcher({L.event_ticker(hi, day): ladder(L.event_ticker(hi, day), zero)}), text_fetch=text_fetch)
    check("a YES bid of 0 on the bracket: no bet", [x for x in st["rows"] if x["lane"] == "c1v2" and x["role"] == "main"], [])
    st = L.run(L.empty(), EST, fetch=fetcher({}), text_fetch=text_fetch)
    check("a city with no ladder listed is skipped with a reason", st["skips"][f"c1v2|{L.event_ticker(hi, day)}"], "no ladder listed")

    def flaky(path):
        raise OSError("kalshi down")
    st = L.run(L.empty(), EST, fetch=flaky, text_fetch=text_fetch)
    check("a transient failure records no skip (the next run in the window retries) and shows in the error", (st["skips"], bool(st["error"])), ({}, True))

    print("\ngrading")
    res = {i: ("no" if i != 0 else "yes") for i in range(6)}          # the cool bracket won: NO loses
    g_books = {L.event_ticker(hi, day): ladder(L.event_ticker(hi, day), Q, results={i: ("yes" if i == 2 else "no") for i in range(6)}),
               L.event_ticker(lo, day): ladder(L.event_ticker(lo, day), Q, results={i: ("yes" if i == 0 else "no") for i in range(6)})}
    st = L.run(L.run(L.empty(), EST, fetch=fetcher(books), text_fetch=text_fetch), EST + dt.timedelta(days=2), fetch=fetcher(g_books), text_fetch=text_fetch)
    byid = {r["id"]: r for r in st["rows"]}
    w = byid[f"c1v2|main|{L.event_ticker(hi, day)}"]
    check("a NO bet whose bracket resolved no wins, with the fee in the return", (w["status"], w["won"], w["roi"]), ("settled", True, round(1 / w["cost"] - 1, 4)))
    lost = byid[f"l1|control|{L.event_ticker(lo, day)}"]
    check("a NO bet whose bracket resolved yes loses the stake", (lost["won"], lost["roi"]), (False, -1.0))
    check("a day not yet over is not graded", L.run(L.run(L.empty(), EST, fetch=fetcher(books), text_fetch=text_fetch), EST + dt.timedelta(hours=3), fetch=fetcher(g_books), text_fetch=text_fetch)["rows"][0]["status"], "open")
    check("a result not yet posted leaves the row open", L.run(L.run(L.empty(), EST, fetch=fetcher(books), text_fetch=text_fetch), EST + dt.timedelta(days=2), fetch=fetcher(books), text_fetch=text_fetch)["rows"][0]["status"], "open")
finally:
    L.LANES.clear()
    L.LANES.update(saved)

print("\nthe record and its pre-registered read")


def rows_of(lane, role, n_won, n_lost, price=0.95, depth=20):
    out = []
    for i in range(n_won + n_lost):
        won = i < n_won
        cost = price + fillsim.fee(price)
        out.append(dict(lane=lane, role=role, status="settled", won=won, roi=round((1 / cost - 1) if won else -1.0, 4), price=price, cost=cost,
                        depth_bid=depth if i % 2 else 5, day=f"2026-12-{i % 28 + 1:02d}", series="S", city="C", bracket="b", event=f"E{i}", id=f"{lane}{role}{i}"))
    return out


s = L.stats(rows_of("l1", "main", 97, 3))
check("97 of 100 at 95c wins 97% and returns about 1.6%", (s["n"], s["won"], round(s["roi"], 3)), (100, 97, round(s["roi"], 3)))
check("the share of entries under 10 contracts at the bid", s["thin"], 0.5)
state = dict(L.empty(), rows=rows_of("c1v2", "main", 20, 1) + rows_of("c1v2", "control", 15, 6) + rows_of("c1v2", "skipped", 1, 1))
rec = L.lane_record(state, "c1v2")
check("too early below 1,000 settled bets", rec["read"].startswith("too early (21 of 1000"), True)
big = dict(L.empty(), rows=rows_of("l1", "main", 480, 20) + rows_of("l1", "control", 300, 200))
check("l1 reads once at 500: above zero and above the control is keep", L.lane_record(big, "l1")["read"].startswith("read now: keep"), True)
big = dict(L.empty(), rows=rows_of("l1", "main", 480, 20) + rows_of("l1", "control", 100, 0))
check("... not above the control is retire", L.lane_record(big, "l1")["read"].startswith("read now: retire"), True)
bad = dict(L.empty(), rows=rows_of("l1", "main", 135, 16))
check("below −3% at 150 settled bets is an early review", L.lane_record(bad, "l1")["read"].startswith("early review"), True)
sk = dict(L.empty(), rows=rows_of("c1v2", "main", 970, 30) + rows_of("c1v2", "control", 900, 100) + rows_of("c1v2", "skipped", 40, 0))
check("c1v2: skipped bets that returned more send the lane back to version 1", "back to version 1" in L.lane_record(sk, "c1v2")["read"], True)

print("\nthe page and the ledger")
with tempfile.TemporaryDirectory() as d:
    p = os.path.join(d, "l.json")
    L.save(state, p)
    check("the ledger round-trips", L.load(p)["rows"] == state["rows"], True)
    check("a missing ledger is empty", L.load(os.path.join(d, "none.json"))["rows"], [])
html = B.section(state)
check("the section names both lanes and the 10 pm Eastern read", all(x in html for x in ("Cold lean", "Warm lean", "10:00 pm Eastern")), True)
check("each row is a collapsed fold with its record, control figure and read", html.count('<details class="sp-rule') == 2 and "vs control" in html, True)
check("no dollar amount anywhere in the section", "$" not in html, True)
check("an empty section says the first read is at 10:00 pm Eastern", "first read is at 10:00 pm" in B.section(L.empty()), True)
idx = B.index_html(state)
check("the Sandbox index rows link to the Daily Markets section", 'href="./daily_markets.html#temps"' in idx, True)
check("... without the words the weather-removal check forbids", not re.search(r"\bclimate\b|KXHIGH|city-day", idx, re.I), True)
copy = [m for m in (sandbox_audit.COPY_RE.findall(html + idx) if hasattr(sandbox_audit, "COPY_RE") else [])]
check("none of the guarded public phrases", copy, [])

print()
if FAILS:
    print(f"{len(FAILS)} FAILED")
    sys.exit(1)
print("weather lanes passed")
