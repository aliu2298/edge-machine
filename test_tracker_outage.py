#!/usr/bin/env python3
"""The 9/28–9/29 tracker outage is on the ledger and on the Sandbox page.

The record is meta.outages. The page note is rendered from that record, on the
recently-settled days and the lane tables when those counts cover the window,
and on an archive week once that week holds the days.

Nothing here is pinned to a commit. The ledger gains quotes every tracker run,
and the page builder will change; the checks below stay true either way.
"""
import copy
import json
import re
import subprocess
import sys
from datetime import datetime, timezone

import sandbox_build as SB

START = "2026-09-28T22:15:10Z"
END = "2026-09-29T15:48:58Z"
# Recovery collect 36592324626 stamped its rows at 15:48:21Z, 37 seconds
# before the step's completedAt (`END`). Those stamps are the catch-up, not
# quotes dated into the downtime.
RECOVERY_LOGGED = "2026-09-29T15:48:21Z"
RUNS = [
    "36502541397",
    "36519115131",
    "36537615454",
    "36542201298",
    "36565274933",
]
NOTE = ("No quotes were logged from 5:15 PM CT Sep 28 to 10:48 AM CT Sep 29 "
        "because of a tracker failure. Counts for those days are lower for that "
        "reason, not because of fewer opportunities.")
NOW = datetime(2026, 9, 30, 2, 7, 28, tzinfo=timezone.utc)
LATER = datetime(2026, 10, 15, 16, 0, tzinfo=timezone.utc)

FAILS = []
_NOTE_DIV = re.compile(r'<div class="note">No quotes were logged from .*?</div>\n')
_TILE = re.compile(r'<div class="tile"><b[^>]*>(.*?)</b><span>(.*?)</span></div>')


def ok(cond, why):
    print(f"  {'ok  ' if cond else 'FAIL'} {why}")
    if not cond:
        FAILS.append(why)


def eq(got, want, why):
    ok(got == want, why if got == want else f"{why} — got {got!r}, want {want!r}")


def _instant(value):
    text = str(value).strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _tiles(html):
    return _TILE.findall(html)


def _section(html, start, end):
    i = html.index(start)
    return html[i:html.index(end, i)]


def _page(d, st, now):
    return SB.label_cells(SB.build(now=now, d=copy.deepcopy(d), st=copy.deepcopy(st)))


def main():
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    print(f"HEAD {head}")
    print(f"window {START} .. {END}")
    print("runs " + " ".join(RUNS))

    d = json.loads(open("data/sandbox_ledger.json").read())
    outages = (d.get("meta") or {}).get("outages") or []
    match = [o for o in outages
             if o.get("start") == START and o.get("end") == END
             and [str(x) for x in o.get("runs") or []] == RUNS]
    eq(len(match), 1, "meta.outages has the 9/28–9/29 outage, with this start, end, and these runs")
    if match:
        o = match[0]
        eq(o.get("logged"), False, "nothing was logged")
        eq(o.get("backfilled"), False, "nothing was back-filled")
        ok("DegenerateCluster" in str(o.get("cause")), "the cause names DegenerateCluster")
        ok("test_sandbox.py:3890" in str(o.get("cause")), "the cause names test_sandbox.py:3890")

    start, recovery = _instant(START), _instant(RECOVERY_LOGGED)
    hole = []
    for q in d.get("quotes") or []:
        logged = q.get("logged")
        if not logged:
            continue
        try:
            when = _instant(logged)
        except (TypeError, ValueError):
            continue
        if start < when < recovery:
            hole.append(q.get("id"))
    eq(len(hole), 0, "no quote has a logged time inside the window")
    if hole:
        print("  inside " + ", ".join(str(i) for i in hole[:8]))

    st = json.loads(open("data/stages.json").read())
    page = _page(d, st, NOW)
    ok(NOTE in page, "the built Sandbox page shows the note")
    eq(page.count(NOTE), 2,
       "the note is on the recent days and on the lane tables, and nowhere else")
    ok(NOTE in _section(page, 'id="recently-settled"', 'id="archive"'),
       "recently settled, which covers those days, carries the note")
    ok(NOTE in _section(page, 'id="by-sport"', 'id="reference"'),
       "the lane tables carry the note")
    ok(NOTE not in _section(page, 'id="running"', 'id="recently-settled"'),
       "the running list, which is not that window, has no note")

    plain = copy.deepcopy(d)
    (plain.get("meta") or {}).pop("outages", None)
    without = _page(plain, st, NOW)
    stripped = _NOTE_DIV.sub("", page)
    eq(stripped, without,
       "dropping meta.outages, and stripping the note divs, build the same page")
    eq(_tiles(page), _tiles(without), "headline tiles are unchanged")
    print("  tiles " + " | ".join(f"{n} {label}" for n, label in _tiles(page)))

    _sandbox, _index, weeks = SB.render_pages(
        now=LATER, d=copy.deepcopy(d), st=copy.deepcopy(st))
    week = weeks.get("2026-W40", "")
    ok(NOTE in week, "once those days are archived, that week page shows the note")
    later = _page(d, st, LATER)
    ok(NOTE in _section(later, 'id="by-sport"', 'id="reference"'),
       "lane totals still carry the note after the days leave the recent list")
    ok(NOTE not in _section(later, 'id="recently-settled"', 'id="archive"'),
       "recently settled drops the note once the window has moved past the outage")

    print(f"\n{'FAILED: ' + str(len(FAILS)) if FAILS else 'tracker outage note passed'}")
    for item in FAILS:
        print(f"  - {item}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
