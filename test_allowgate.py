#!/usr/bin/env python3
"""allowgate.py: the shared "Every Positive Setting" gate (s3v2.py, flipf1v2.py)."""
import sys

import allowgate as G

FAILS = []


def check(why, got, want):
    good = got == want
    print(f"  {'ok  ' if good else 'FAIL'} {why}" + ("" if good else f" — got {got!r}, want {want!r}"))
    if not good:
        FAILS.append(why)


A = {"KXA15M": {"price": ["x", "y"], "time_ct": ["07-11"]}, "KXB15M": {"price": ["x"], "time_ct": []}}
check("every setting in the list: allowed", G.allowed(A, "KXA15M", {"price": "y", "time_ct": "07-11"}), True)
check("one setting out: not allowed", G.allowed(A, "KXA15M", {"price": "z", "time_ct": "07-11"}), False)
check("an empty list never bets", G.allowed(A, "KXB15M", {"price": "x", "time_ct": "07-11"}), False)
check("an unknown bucket (None, e.g. an hour outside 07-22 CT) never bets", G.allowed(A, "KXA15M", {"price": "x", "time_ct": None}), False)
check("a market not listed never bets", G.allowed(A, "KXC15M", {"price": "x", "time_ct": "07-11"}), False)
check("a missing setting never bets", G.allowed(A, "KXA15M", {"price": "x"}), False)
check("never(): markets with an empty list, and which", G.never(A), {"KXB15M": ["time_ct"]})
check("the fingerprint is order-independent and changes with any edit",
      (G.fingerprint(A) == G.fingerprint(dict(reversed(list(A.items())))),
       G.fingerprint(A) != G.fingerprint(dict(A, KXB15M={"price": ["x"], "time_ct": ["07-11"]}))), (True, True))
check("time buckets in CT (CST): 13:00Z 7 AM, 04:00Z 10 PM, 05:00Z 11 PM, 12:59Z 6:59 AM",
      [G.time_bucket(t) for t in ("2026-11-10T13:00:00Z", "2026-11-11T04:00:00Z", "2026-11-11T05:00:00Z", "2026-11-10T12:59:00Z")],
      ["07-11", "17-22", None, None])
cols = ["m", "yes_bid", "yes_ask"]
w = dict(minute_cols=cols, minutes=[[0, .59, .61], [1, .39, .41], [2, .49, .51], [3, .59, .61], [4, .39, .41]])
check("lead changes count crossings up to the given row, skipping an exact 50c mid",
      [G.lead_changes(w, k) for k in (0, 1, 2, 3, 4)], ["0", "1", "1", "2+", "2+"])
check("no quotes: None", G.lead_changes({"minutes": []}, 3), None)

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
