#!/usr/bin/env python3
"""Offline checks for feed_gap.py (the Production feed build gap alert)."""
import datetime as dt
import io
import json
import sys

import feed_gap as G

FAILS = []
UTC = dt.timezone.utc
NOW = dt.datetime(2026, 11, 2, 12, 0, tzinfo=UTC)


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


def at(h):
    return NOW - dt.timedelta(hours=h)


hourly = [at(h) for h in range(0, 24)]
check("hourly builds: green, worst gap 1h", (G.status(hourly, NOW)["status"], G.status(hourly, NOW)["gap_hours"]), ("green", 1.0))
gap = [at(h) for h in (0, 1, 2, 3, 4, 5, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23)]
s = G.status(gap, NOW)
check("a 6h hole between builds is amber and named", (s["status"], s["gap_hours"], s["gap_from"][11:16], s["gap_to"][11:16]), ("amber", 6.0, "01:00", "07:00"))
check("exactly 2h is not over", G.status([at(h) for h in range(0, 24, 2)], NOW)["status"], "green")
check("no build since 3h ago is a gap to now", (G.status([at(3), at(4)] + hourly[6:], NOW)["status"], G.status([at(3)] + hourly[6:], NOW)["gap_hours"] >= 2.5), ("amber", True))
check("no builds at all in 24h is amber for the whole window", (G.status([], NOW)["status"], G.status([], NOW)["gap_hours"]), ("amber", 24.0))


class R(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): return False


calls = []
def opener(req, timeout=0):
    calls.append(req.full_url)
    return R(json.dumps([{"commit": {"committer": {"date": at(h).strftime("%Y-%m-%dT%H:%M:%SZ")}}} for h in range(3)]).encode())
got = G.fetch_builds(NOW, opener=opener)
check("fetch_builds reads the commits API for the feed file and returns instants", (len(got), "path=data/production_leads.json" in calls[0]), (3, True))

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
