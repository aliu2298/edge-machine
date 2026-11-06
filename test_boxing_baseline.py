#!/usr/bin/env python3
"""Offline checks (2026-11-04, Olu): Boxing · cheap dog (3-15c) picks on its price band alone, so under the 2026-11-01
no-blind-selection rule it is a BASELINE, not a lane. Same entry and exit rules, whole record kept, still read every hour.
It has no review status and no lane count, it is listed in the Chaos baselines line, and no filtered boxing lane is
registered (Olu has not chosen a filter)."""
import inspect
import re
import sys

import chaos_build as CH
import fights_build as FB
import fights_split as FS
import lane_windows as W
import mentions_split as MS
import sandbox_audit
import sandbox_build as B

FAILS = []


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


print("the config: a baseline, same rules, still run")
g = FS.BOXING.get("baseline") or {}
check("dated, with its record", (g.get("on"), g.get("at")), ("2026-11-04", "4 settled events, 1 won; split +75.0%, hold +57.3%"))
check("blind selection is the reason", "price band only, no fighter or matchup filter" in g.get("reason", ""), True)
check("same series, band, spread and anchor", (FS.BOXING["series"], FS.BOXING["band"], FS.BOXING["spread"], FS.BOXING["anchor"]),
      ("KXBOXING", (0.03, 0.15), 0.05, "boxing-cheap-dog"))
check("not retired: the run still enters it", (FS.BOXING.get("retired"), MS.retired(FS.BOXING, __import__("datetime").datetime.now(
    __import__("datetime").timezone.utc))), (None, False))
check("the run reads every ledger, baselines included", ([c["lane"] for c in FS.LANES], "for cfg in LANES:" in inspect.getsource(FS.main)),
      (["boxing_cheap_dog", "ufc_dog"], True))
check("live lanes, baselines, retired", ([c["lane"] for c in FS.LIVE], [c["lane"] for c in FS.BASES], [c["lane"] for c in FS.GONE]),
      ([], ["boxing_cheap_dog"], ["ufc_dog"]))
check("UFC (a copy of BOXING) did not inherit the baseline", FS.UFC.get("baseline"), None)
check("the VPS still asks for the hourly fights read", W.STAMP.get("fights"), "data/fights_window/request.txt")
check("no filtered boxing lane is registered", [c["lane"] for c in FS.LANES if c["series"] == "KXBOXING" and not c.get("baseline")], [])

print("\nthe record stays whole")
st = FS.load(FS.BOXING)
r = MS.record(MS.counted(st))
# The record grows and regrades with the hourly fights read (4 settled events and a +75.0% split on 2026-11-04, 8 and +27.9% on
# 2026-11-06), so only a floor is pinned: the record must stay whole, never shrink; the dated registry text above keeps the snapshot.
check("at least the 4 settled events and 1 win of 2026-11-04; split and hold are numbers",
      (r["settled_events"] >= 4, r["won"] >= 1, isinstance(r["roi"], float), isinstance(r["roi_held"], float)),
      (True, True, True, True))

print("\nno review status, no lane count")
check("lane_status of a baseline", (MS.lane_status(FS.BOXING, 40), MS.lane_status(FS.UFC, 3)),
      ("baseline, not a lane", MS.status(3)))
h = FB.build()
k, j = h.find('id="baseline-boxing_cheap_dog"'), h.find('id="retired"')
base = h[k:j]
check("the Fights page: no live lane, so the lanes summary is a note", "No filtered fights lane yet. A filtered boxing lane must beat the baseline below." in h,
      True)
check("the baseline block, in the Chaos baselines' layout", ('<details class="section-disclosure baseline" data-lane="boxing_cheap_dog"' in h,
      "Baseline · Boxing cheap dog (blind, price band only)" in base, "not a lane" in base), (True, True, True))
check("it says a filtered boxing lane must beat it", "A filtered boxing lane must beat this record." in base, True)
check("no review status anywhere in it", ("review at 10" in base, "decide at 30" in base, "baseline, not a lane" in base), (False, False, True))
check("its card and trades are inside the block", 'id="boxing-cheap-dog"' in base, True)

print("\nthe Chaos baselines line lists it")
check("the extra baseline link", CH._extra_baselines(), ['<a href="./fights.html#baseline-boxing_cheap_dog">Boxing cheap dog</a>'])
idx = B.build()
m = re.search(r'<p class="sm mut chaos-baselines">(.*?)</p>', idx, re.S)
check("on the Sandbox page, beside the College football and Challenger baselines",
      (bool(m) and "Boxing cheap dog" in m.group(1), bool(m) and "College football underdog" in m.group(1)), (True, True))
check("not a row in the Chaos index", '<tr data-lane="boxing_cheap_dog"' in idx, False)

check("no guarded phrase in the new copy", sandbox_audit.COPY_RE.search(str(g) + base + (m.group(1) if m else "")), None)

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
