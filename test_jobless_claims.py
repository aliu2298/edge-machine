#!/usr/bin/env python3
"""Offline checks for the jobless claims NO 70-85c paper lane (jobless_claims.py, 2026-11-11, Olu)."""
import datetime as dt
import os
import re
import sys

import jobless_claims as J
import jobless_build as JB
import lane_windows as W
import sandbox_audit

FAILS = []
UTC = dt.timezone.utc


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


CLOSE = int(dt.datetime(2026, 11, 12, 13, 29, tzinfo=UTC).timestamp())
EV = "KXJOBLESSCLAIMS-26NOV12"


def candle(ts, yb, ya, lo=None, hi=None, vol=0):
    c = {"end_period_ts": ts, "yes_bid": {"close_dollars": str(yb)}, "yes_ask": {"close_dollars": str(ya)},
         "volume_fp": str(vol)}
    if lo is not None:
        c["price"] = {"low_dollars": str(lo), "high_dollars": str(hi), "close_dollars": str(hi)}
    return c


def minutes(cs, end=CLOSE):
    return J.C.dense(cs, J.window(CLOSE)[0] - 1800, end)


print("the window: 3h to 1h before the close")
a, b = J.window(CLOSE)
check("from 10:29 to 12:29Z for an 13:29Z close", (dt.datetime.fromtimestamp(a, UTC).strftime("%H:%M"),
                                                  dt.datetime.fromtimestamp(b, UTC).strftime("%H:%M")), ("10:29", "12:29"))
# NO ask = 1 - YES bid. YES 0.20/0.25 -> NO ask 0.80, spread 5c.
check("a quote before the window is not an entry", J.pick(minutes([candle(a - 60, 0.20, 0.25)]), "no", CLOSE) is not None
      and minutes([candle(a - 60, 0.20, 0.25)])[J.pick(minutes([candle(a - 60, 0.20, 0.25)]), "no", CLOSE)]["ts"] >= a, True)
check("the window's first minute is", minutes([candle(a, 0.20, 0.25)])[J.pick(minutes([candle(a, 0.20, 0.25)]), "no", CLOSE)]["ts"], a)
check("after the window ends: none", J.pick(minutes([candle(b + 60, 0.20, 0.25)]), "no", CLOSE), None)
for yb, ya, want in ((0.30, 0.35, True), (0.15, 0.20, True), (0.31, 0.36, False), (0.14, 0.19, False), (0.20, 0.31, False)):
    i = J.pick(minutes([candle(a, yb, ya)]), "no", CLOSE)
    check(f"YES {yb}/{ya}: NO ask {1 - yb:.2f}, spread {ya - yb:.2f} -> entry {want}", i is not None, want)
check("the YES side is read the same way (YES ask 0.78, spread 3c)", J.pick(minutes([candle(a, 0.75, 0.78)]), "yes", CLOSE) is not None, True)

print("\nthe run: freeze after the window, check the ask after an hour, settle on the result")
MK = [dict(ticker=f"{EV}-200000", floor_strike=200000, close_time="2026-11-12T13:29:00Z", status="active"),
      dict(ticker=f"{EV}-185000", floor_strike=185000, close_time="2026-11-12T13:29:00Z", status="active")]
T0 = b - 600                                               # an entry 10 minutes before the window ends
CS = {f"{EV}-200000": [candle(T0, 0.20, 0.24)] + [candle(T0 + 60 * k, 0.20, 0.24, 0.19, 0.20, 4) for k in range(1, 4)],
      f"{EV}-185000": [candle(T0, 0.75, 0.80)]}             # YES ask 80c: a comparison entry, no prints


def fake(markets):
    def fetch(path):
        if path.startswith("events?"):
            return {"events": [{"event_ticker": EV}] if "status=open" in path else []}
        if path.startswith("markets?"):
            return {"markets": markets}
        if "candlesticks" in path:
            return {"market_tickers": list(CS), "market_candlesticks": list(CS.values())}
        return {}
    return fetch


st = J.empty()
J.run(st, dt.datetime.fromtimestamp(b - 60, UTC), fake(MK))
check("inside the window: nothing frozen", st["events"].get(EV, {}).get("frozen"), False)
J.run(st, dt.datetime.fromtimestamp(b + 120, UTC), fake(MK))
es = st["events"][EV]["entries"]
check("after it: one NO and one YES entry, at the ask", sorted((e["side"], e["price"]) for e in es), [("no", 0.8), ("yes", 0.8)])
check("the ask check waits for the hour", {e["ask_check"]["status"] for e in es}, {"checking"})
J.run(st, dt.datetime.fromtimestamp(CLOSE + 600, UTC), fake(MK))
by = {e["side"]: e for e in st["events"][EV]["entries"]}
check("12 contracts at or through the NO ask: verified; none for the YES: unverified",
      (by["no"]["ask_check"]["status"], by["yes"]["ask_check"]["status"]), ("verified", "unverified"))
settled = [dict(m, status="finalized", result="no") for m in MK]
J.run(st, dt.datetime.fromtimestamp(CLOSE + 7200, UTC), fake(settled))
by = {e["side"]: e for e in st["events"][EV]["entries"]}
check("settled: NO won, held ROI after the taker fee", (by["no"]["won"], by["no"]["roi"]),
      (True, round(1 / (0.8 + 0.07 * 0.8 * 0.2) - 1, 4)))
check("the event is done", st["events"][EV]["done"], True)
frozen = [dict(e) for e in st["events"][EV]["entries"]]
J.run(st, dt.datetime.fromtimestamp(CLOSE + 9000, UTC), fake(settled))
check("a frozen entry is never re-picked", st["events"][EV]["entries"], frozen)

print("\nthe record, by weeks")
def mk(ev, side, roi, won, status="verified"):
    return dict(event=ev, side=side, price=0.8, roi=roi, won=won, result="no", ask_check=dict(status=status))
es = [mk("W1", "no", 0.2, True), mk("W1", "no", -1.0, False), mk("W2", "no", 0.2, True), mk("W3", "no", 0.2, True),
      mk("W4", "no", 0.2, True, "unverified")]
r = J.week_record(es)
check("weeks, positive, won v priced (an unverified entry is left out)", (r["weeks"], r["positive"], r["won"], r["priced"], r["unverified"]),
      (3, 2, 3, 3.2, 1))
check("mean week ROI is the mean of each week's mean", round(r["roi_week"], 4), round((-0.4 + 0.2 + 0.2) / 3, 4))
check("z over weeks from 3 weeks; none under 3", (r["z"] is not None, J.week_record(es[:2])["z"]), (True, None))
check("stage: early under 8, review at 8, decide at 12",
      [J.stage(dict(weeks=n)) for n in (7, 8, 12)], ["early", "review", "decide"])

print("\nthe schedule: Wednesdays and Thursdays from 07:30 ET, ET-aware")
def jw(t):
    return [w for w in W.windows(t) if w["lane"] == "jobless"]
w = jw(dt.datetime(2026, 11, 12, 12, 40, tzinfo=UTC))
check("Thu Nov 12 (EST): 12:30Z to 16:30Z", (w[0]["start"].strftime("%H:%M"), w[0]["end"].strftime("%H:%M")), ("12:30", "16:30"))
w = jw(dt.datetime(2026, 7, 9, 12, 40, tzinfo=UTC))
check("a summer Thursday (EDT): 11:30Z", w[0]["start"].strftime("%H:%M"), "11:30")
check("the Wednesday before Thanksgiving has a window; a Tuesday has none",
      (len(jw(dt.datetime(2026, 11, 25, 13, 0, tzinfo=UTC))), len(jw(dt.datetime(2026, 11, 10, 13, 0, tzinfo=UTC)))), (1, 0))
due = [k for w_, k in W.due(dt.datetime(2026, 11, 12, 13, 31, tzinfo=UTC)) if w_["lane"] == "jobless"]
check("one read due each hour (read 2 at 08:31 ET)", due, [2])
check("the stamp file, the VPS script's allow-list and the workflow agree",
      (W.STAMP["jobless"], "|data/jobless_window/request.txt)" in open("scripts/vps_window_requests.sh").read(),
       "data/jobless_window/**" in open(".github/workflows/jobless-claims.yml").read()),
      ("data/jobless_window/request.txt", True, True))

print("\nthe page")
h = JB.section(st)
check("labelled as a price-band test, both lines, review and decide",
      ("selects by price only; no filter yet" in h, J.LABEL in h, J.COMPARE_LABEL in h, "review 8 weeks, decide 12" in h), (True,) * 4)
check("the folds are closed", re.findall(r"<details[^>]*\bopen\b", h), [])
check("the study evidence sits in the rule fold", "8 of 8" in h[h.find('id="jobless-rule"'):] and "+1.54" in h, True)
check("no dollar amounts, no guarded phrase", ("$" in h, sandbox_audit.COPY_RE.search(h)), (False, None))
import daily_markets_build as DM
check("Daily Markets carries it in the Econ section",
      DM.build().find('id="econ-weekly"') > DM.build().find('id="econ"') > 0, True)

print("\npre-registered before the first entry")
pre = open(J.PREREG).read()
check("the file names the rule, the window, the honest fill, the comparison and the judging",
      all(x in pre for x in ("KXJOBLESSCLAIMS", "3h to 1h before", "70-85c", "10 or more contracts", "YES side",
                             "Review at 8 settled weeks, decide at 12", "selects by price only", "2026-11-12")), True)
check("the ledger starts empty from 2026-11-12", (J.SINCE, os.path.exists(J.PATH)), ("2026-11-12", True))

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
