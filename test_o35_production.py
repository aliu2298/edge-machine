#!/usr/bin/env python3
"""The o35 Production feed (o35_production.py): offline checks."""
import datetime as dt
import sys

import o35_cheap_no as O
import o35_production as X

FAILS = []
UTC = dt.timezone.utc


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


NOW = dt.datetime(2026, 11, 1, 12, 0, tzinfo=UTC)


def occ(hours_from_now):
    return (NOW + dt.timedelta(hours=hours_from_now + 4)).strftime("%Y-%m-%dT%H:%M:%SZ")


def mkt(ev, hours, status="active", strike=3.5, suffix="-4", result=""):
    return dict(ticker=ev + suffix, floor_strike=strike, status=status, result=result, occurrence_datetime=occ(hours))


EVENTS = {"KXMLSTOTAL": [dict(event_ticker="KXMLSTOTAL-A", title="A v B", markets=[mkt("KXMLSTOTAL-A", 3, strike=2.5, suffix="-3"), mkt("KXMLSTOTAL-A", 3)]),
                         dict(event_ticker="KXMLSTOTAL-OLD", title="old", markets=[mkt("KXMLSTOTAL-OLD", -5)]),
                         dict(event_ticker="KXMLSTOTAL-FAR", title="far", markets=[mkt("KXMLSTOTAL-FAR", 48)]),
                         dict(event_ticker="KXMLSTOTAL-CLOSED", title="c", markets=[mkt("KXMLSTOTAL-CLOSED", 2, status="closed")]),
                         dict(event_ticker="KXMLSTOTAL-MID", title="m", markets=[mkt("KXMLSTOTAL-MID", -2.5)]),
                         dict(event_ticker="KXMLSTOTAL-JUST", title="j", markets=[mkt("KXMLSTOTAL-JUST", -0.2)])],
          "KXSAUDIPLTOTAL": [dict(event_ticker="KXSAUDIPLTOTAL-S", title="s", markets=[mkt("KXSAUDIPLTOTAL-S", 2)])]}


def fetch(path):
    ser = path.split("series_ticker=")[1].split("&")[0]
    return {"events": EVENTS.get(ser, []), "cursor": None}


rows, errs = X.leads(NOW, fetch)
print("the listing")
check("only the open over 3.5 rung inside the window, kicked off at occurrence minus 4h; a match deep in the second half stays (the follower bids from kickoff + 60); over 4h in, far, closed out",
      [r["event"] for r in rows], ["KXMLSTOTAL-MID", "KXMLSTOTAL-JUST", "KXMLSTOTAL-A"])
check("Saudi Pro League is not scanned", any("SAUDI" in r["event"] for r in rows), False)
a = rows[2]
check("the lead carries the rule: NO side, 10c bid, 40c sell, $1", (a["side"], a["bid"], a["sell"], a["stake_usd"], a["ticker"]),
      ("no", 0.1, 0.4, 1.0, "KXMLSTOTAL-A-4"))
check("kickoff is the occurrence time less 4 hours", a["kickoff"], (NOW + dt.timedelta(hours=3)).isoformat())
b = X.feed(NOW, fetch)
check("the feed header names the rule and version", (b["lane"], b["version"], b["rule"]["bid"], b["rule"]["sell"], len(b["rule"]["leagues"])),
      ("o35_cheap_no_wave", "o35-v3", 0.1, 0.4, 11))


def broken(path):
    raise ValueError("boom")


b2 = X.feed(NOW, broken)
check("every league failing is reported, not hidden", (len(b2["errors"]), b2["leads"]), (11, []))
print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
