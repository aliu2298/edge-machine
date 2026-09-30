#!/usr/bin/env python3
"""The 9/28–9/29 tracker outage is on the ledger and on the Sandbox page.

The record is meta.outages. The page note is rendered from that record, on the
recently-settled days and the lane tables when those counts cover the window,
and on an archive week once that week holds the days. Quote rows and every
number on the page stay byte-identical to base 38bdb4f; only the note is new.

Fails on that base commit (no outage, no note) and passes once both are present.
"""
import copy
import importlib.util
import json
import re
import subprocess
import sys
from datetime import datetime, timezone

import sandbox_build as SB

BASE = "38bdb4ff5615bd4d072ce365ee15f3977f7b7345"
START = "2026-09-28T22:15:10Z"
END = "2026-09-29T15:48:58Z"
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
# Collect on the last successful grade finished at START; the recovery collect
# finished at END. Both are the Actions step completion times.
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


def _git_show(path):
    spec = f"{BASE}:{path}"
    got = subprocess.run(["git", "show", spec], capture_output=True)
    if got.returncode != 0:
        fetched = subprocess.run(
            ["git", "fetch", "--depth", "1", "origin", BASE], capture_output=True)
        if fetched.returncode != 0:
            sys.stderr.write(fetched.stderr.decode() or got.stderr.decode())
            raise SystemExit(f"cannot read {spec}")
        got = subprocess.run(["git", "show", spec], capture_output=True)
    if got.returncode != 0:
        sys.stderr.write(got.stderr.decode())
        raise SystemExit(f"cannot read {spec}")
    return got.stdout


def _quotes_region(raw):
    key = b'\n "quotes": '
    return raw[raw.index(key):]


def _load_base_build():
    src = _git_show("sandbox_build.py")
    spec = importlib.util.spec_from_loader("sandbox_build_base", loader=None)
    mod = importlib.util.module_from_spec(spec)
    mod.__dict__["__file__"] = "sandbox_build.py"
    mod.__dict__["__name__"] = "sandbox_build_base"
    exec(compile(src, f"{BASE}:sandbox_build.py", "exec"), mod.__dict__)
    return mod


def _tiles(html):
    return _TILE.findall(html)


def _section(html, start, end):
    i = html.index(start)
    return html[i:html.index(end, i)]


def main():
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    print(f"HEAD {head}")
    print(f"base {BASE}")
    print(f"window {START} .. {END}")
    print("runs " + " ".join(RUNS))

    raw = open("data/sandbox_ledger.json", "rb").read()
    d = json.loads(raw)
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
        ok("nothing was logged" in str(o.get("note") or "").lower()
           or o.get("logged") is False, "the record says nothing was logged")

    base_raw = _git_show("data/sandbox_ledger.json")
    eq(_quotes_region(raw), _quotes_region(base_raw),
       "ledger quote rows are byte-identical to base")

    st = json.loads(open("data/stages.json").read())
    head_html = SB.label_cells(SB.build(now=NOW, d=copy.deepcopy(d), st=copy.deepcopy(st)))
    ok(NOTE in head_html, "the built Sandbox page shows the note")
    eq(head_html.count(NOTE), 2,
       "the note is on the recent days and on the lane tables, and nowhere else")
    ok(NOTE in _section(head_html, 'id="recently-settled"', 'id="archive"'),
       "recently settled, which covers those days, carries the note")
    ok(NOTE in _section(head_html, 'id="by-sport"', 'id="reference"'),
       "the lane tables carry the note")
    ok(NOTE not in _section(head_html, 'id="running"', 'id="recently-settled"'),
       "the running list, which is not that window, has no note")

    base_mod = _load_base_build()
    base_html = base_mod.label_cells(
        base_mod.build(now=NOW, d=copy.deepcopy(d), st=copy.deepcopy(st)))
    ok(NOTE not in base_html, "base has no note to begin with")
    stripped = _NOTE_DIV.sub("", head_html)
    eq(stripped, base_html, "aside from the note, the built page is byte-identical to base")
    head_tiles = _tiles(head_html)
    base_tiles = _tiles(base_html)
    eq(head_tiles, base_tiles, "headline tiles are unchanged")
    print("  tiles " + " | ".join(f"{n} {label}" for n, label in head_tiles))

    _page, _index, weeks = SB.render_pages(
        now=LATER, d=copy.deepcopy(d), st=copy.deepcopy(st))
    week = weeks.get("2026-W40", "")
    ok(NOTE in week, "once those days are archived, that week page shows the note")
    later = SB.label_cells(SB.build(now=LATER, d=copy.deepcopy(d), st=copy.deepcopy(st)))
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
