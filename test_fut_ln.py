#!/usr/bin/env python3
"""Offline checks for the soccer futures longshot NO watch (fut_ln.py): the monthly checkpoint window, the 3-15c / 10c-spread filter, one entry per market,
the entry price and fee, settlement and return, the exact binomial, capital tied up and the annualised figure, the baselines kept apart, and page rows
that make no venue call and use no guarded phrase."""
import datetime as dt
import math
import sys

import daily_track as D
import fut_ln as F
import fut_ln_build as FB
import sandbox_audit

FAILS = []


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


def close(label, got, want, tol=1e-6):
    ok = got is not None and abs(got - want) < tol
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


utc = lambda y, m, d: dt.datetime(y, m, d, 6, tzinfo=dt.timezone.utc)
print("the checkpoint window")
st = F.empty()
check("Nov 14 (before the first month): none", F.due(st, utc(2026, 11, 14)), None)
check("Dec 1: the December checkpoint", F.due(st, utc(2026, 12, 1)), "2026-12")
check("Dec 3 is still inside the grace window; Dec 4 is not", (F.due(st, utc(2026, 12, 3)), F.due(st, utc(2026, 12, 4))), ("2026-12", None))
check("June and July are outside September to April", (F.due(st, utc(2027, 6, 1)), F.due(st, utc(2027, 7, 1))), (None, None))
check("Jan 1 and Apr 1 are in", (F.due(st, utc(2027, 1, 1)), F.due(st, utc(2027, 4, 1))), ("2027-01", "2027-04"))

print("\nthe filter, the entry and the fee")
mk = lambda t, bid, ask, name="T": dict(ticker=t, yes_sub_title=name, yes_bid_dollars=bid, yes_ask_dollars=ask, expected_expiration_time="2027-05-24T00:00:00Z")
check("a 3c bid qualifies, a 15c bid qualifies", (F.qualifies(mk("a", "0.0300", "0.0500")) is not None, F.qualifies(mk("a", "0.1500", "0.2500")) is not None), (True, True))
check("a 2c bid, a 16c bid, an 11c spread, no ask: none", [F.qualifies(mk("a", b, k)) for b, k in (("0.0200", "0.0300"), ("0.1600", "0.1700"), ("0.0500", "0.1600"), ("0.0500", ""))], [None] * 4)
check("no bid: none", F.qualifies(mk("a", "", "0.0400")), None)
EV = {"KXLALIGA": [dict(event_ticker="KXLALIGA-27", markets=[mk("LL-A", "0.0500", "0.0600", "Alpha"), mk("LL-B", "0.4000", "0.4200", "Beta"), mk("LL-C", "0.0100", "0.0200", "Gamma")])],
      "KXPREMIERLEAGUE": [dict(event_ticker="KXPREMIERLEAGUE-27", markets=[mk("PL-A", "0.1000", "0.1100", "Delta")])],
      "KXEPLRELEGATION": [dict(event_ticker="KXEPLRELEGATION-27", markets=[mk("RE-A", "0.0800", "0.1000", "Epsilon")])]}


def get(path):
    for s, evs in EV.items():
        if f"series_ticker={s}&" in path and "status=open" in path:
            return {"events": evs}
    return {"events": []}


n = F.take(st, "2026-12", utc(2026, 12, 1), get)
check("three markets qualify: two winners and one relegation", (n, sorted(st["entries"])), (3, ["LL-A", "PL-A", "RE-A"]))
e = st["entries"]["LL-A"]
check("NO bought at 1 minus the YES bid, fee 0.07 p (1 - p)", (e["no_price"], round(e["fee"], 5), e["league"], e["group"]), (0.95, round(0.07 * 0.95 * 0.05, 5), "La Liga", "winner"))
check("the baselines are tagged apart", (st["entries"]["RE-A"]["group"], st["entries"]["RE-A"]["league"]), ("relegation", "EPL"))
check("a second checkpoint the same month is not due, and re-taking adds no duplicate", (F.due(st, utc(2026, 12, 2)), F.take(st, "2026-12", utc(2026, 12, 2), get)), (None, 0))

print("\nsettlement and the record")
settled = {"KXLALIGA": [dict(event_ticker="KXLALIGA-27", markets=[dict(ticker="LL-A", result="no")])],
           "KXPREMIERLEAGUE": [dict(event_ticker="KXPREMIERLEAGUE-27", markets=[dict(ticker="PL-A", result="yes")])]}


def sget(path):
    for s, evs in settled.items():
        if f"series_ticker={s}&" in path and "status=settled" in path:
            return {"events": evs}
    return {"events": []}


check("two settle; the relegation entry stays open", (F.settle(st, sget), st["entries"]["RE-A"]["status"]), (2, "open"))
cost = 0.95 + 0.07 * 0.95 * 0.05
close("a won NO returns (1 - cost) / cost", st["entries"]["LL-A"]["roi"], round((1 - cost) / cost, 4), 1e-4)
close("a lost NO returns -100%", st["entries"]["PL-A"]["roi"], -1.0)
check("a second settle changes nothing", F.settle(st, sget), 0)
rec = F.records(st)
check("the watch: 2 settled, 1 longshot win, 0 open; the baseline: 1 open", (rec["winner"]["n"], rec["winner"]["longshot_wins"], rec["winner"]["open"], rec["relegation"]["open"]), (2, 1, 0, 1))
check("under 10 settled: too early", rec["winner"]["read"].startswith("too early (2 of 10"), True)
close("exact tail: 1 or fewer longshot wins among two longshots priced 5c and 10c", F.exact_tail([0.05, 0.10], 1), 1 - 0.05 * 0.10)
close("exact tail with no longshot win at all", F.exact_tail([0.05, 0.10, 0.10], 0), 0.95 * 0.9 * 0.9)
close("annualised: days held from Dec 1 2026 to May 24 2027 is 174 days", rec["winner"]["avg_days"], 174.0, 0.5)
check("the average cost of an entry is about what a NO costs", round(rec["winner"]["avg_cost"], 2), 0.93)

print("\nreview and decide reads")
big = F.empty()
for i in range(30):
    won = i != 0
    big["entries"][f"X-{i}"] = dict(ticker=f"X-{i}", series="KXLALIGA", league="La Liga", group="winner", event="E", team="T", month="2026-12", day="2026-12-01", yes_bid=0.08,
                                    yes_ask=0.09, spread=0.01, no_price=0.92, fee=0.005, exp="2027-05-24T00:00:00Z", status="won" if won else "lost", roi=0.08 if won else -1.0)
r30 = F.record(big, "winner")
check("30 settled with 1 longshot win: decide, with the exact tail", (r30["read"].startswith("decide at 30: 1 longshot win in 30; chance of this few or fewer at the prices paid"), r30["ratio"] is not None and r30["ratio"] > 10), (True, True))
for k in list(big["entries"])[:20]:
    big["entries"][k]["status"] = "open"
check("10 to 29 settled: review", F.record(big, "winner")["read"].startswith("review at 10"), True)

print("\nthe page rows")


def _no_call(*a, **k):
    raise AssertionError("the page builder made a venue call")


real = D.get
D.get = _no_call
try:
    rows = FB.rows(st)
    rows_empty = FB.rows(F.empty())
finally:
    D.get = real
check("three rows: the watch and two baselines", ([r["name"] for r in rows], rows[0]["meta"]["kind"]), (["futures_longshot_no", "futures_longshot_no_top4", "futures_longshot_no_relegation"], "Observation"))
check("the watch says 'a watch, not a pass' and shows days tied up and the annualised figure",
      ("a watch, not a pass" in rows[0]["meta"]["note"].lower(), "Days tied up" in rows[0]["own"]["details"], "Annualised" in rows[0]["own"]["details"]), (True, True, True))
text = " ".join(r["own"]["details"] + r["own"]["entries"] + r["own"]["label"] + r["meta"]["note"] for r in rows + rows_empty)
check("no guarded phrase, no money words", [w for w in ("real " + "money", "the b" + "ot", "follow" + "er", "$", "weath" + "er") if w in text.lower()], [])
check("the audit's phrase scan finds nothing in the rows or the module and doc text",
      (sandbox_audit.COPY_RE.search(text), sandbox_audit.COPY_RE.search(open("fut_ln.py").read() + open("fut_ln_build.py").read() + open("docs/prereg_futures_longshot_no_2026-11-14.md").read())), (None, None))

print()
if FAILS:
    print(f"{len(FAILS)} FAILED")
    sys.exit(1)
print("all ok")
