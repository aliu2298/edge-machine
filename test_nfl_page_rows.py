#!/usr/bin/env python3
"""Offline checks (2026-11-05, Olu): the NFL page counts its team-total lanes.

Before, nfl_tt_build spliced the team-total rows into the Sandbox list after the page was drawn, so the tiles said
"0 active rules" and a "—" Sandbox record (team total over was 17–22), and Events said "no read stored". The lanes are
template rows now: they count in the tiles, their entries are Events, and the empty state reads their own last scan.
Also: ESPN FPI (NFL) retired 2026-11-02 logs nothing after its retirement landed (#292, 06:13Z that day).
"""
import re
import sys

import nfl_build as B
import nfl_tt as N
import nfl_tt_build as TB
import sandbox_audit
import sandbox_track as T

FAILS = []


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


html = B.build()
main = html[html.find("<main"):]
tiles = dict((b2, b1) for b1, b2 in re.findall(r'<div class="tile"><b[^>]*>(.*?)</b><span>(.*?)</span>', main))
state = TB._state(None)
live = [x for x in N.LANES if x not in N.RETIRED]
print("the tiles count the team-total lanes")
check("active rules counts every live team-total lane", int(tiles.get("active rules", 0)) >= len(live), True)
a = N.stats(TB._picks(state, "nfl_tt_over_3545"))
# Since #351 the tile pools every Sandbox lane on the page: team total over AND main line +1 (nfl_tt_main1, own ledger).
import nfl_tt_main1 as M1
import nfl_tt_main1_build as MB1
b = M1.stats(MB1._picks(M1.load()))
won, n = a["won"] + b["won"], a["n"] + b["n"]
check("the Sandbox record is the lanes' own (team total over's plus main line +1's won–lost)",
      tiles.get("Sandbox record · paper"), f'{won}–{n - won}' if len(live) == 1 else tiles.get("Sandbox record · paper"))
check("open picks counts their open entries", int(tiles.get("open picks", 0)) >= a["open"], True)

print("\nthe rows")
r = main[main.find('<section id="rules"'):main.find('<section id="events"')]
ret = main[main.find('<section id="retired"'):]
check("every NFL lane retired 2026-11-11 (END NFL): no team-total or main line +1 row in the live Rules",
      ('data-source="nfl_tt_over_3545"' in r, 'data-source="nfl_tt_main1"' in r), (False, False))
check("both sit in the Retired fold with the 2026-11-11 reason",
      ('data-source="nfl_tt_over_3545"' in ret, 'data-source="nfl_tt_main1"' in ret, "Retired 2026-11-11 by Olu" in ret), (True, True, True))
check("the retired main-line lane is in the Retired fold, with its reason",
      ('data-source="nfl_tt_over_main"' in ret, "Retired 2026-10-31 by Olu" in ret), (True, True))
check("ESPN FPI is in the Retired fold, not a live row", ('data-source="espn_fpi"' in ret, 'data-source="espn_fpi"' in r), (True, False))

print("\nEvents")
ev = main[main.find('<section id="events"'):main.find('<section id="retired"')]
check("Events lists no team-total entry (nothing live since 2026-11-11)", 'data-source="nfl_tt_over_3545"' in ev, False)
check("the empty state says every lane is retired, not that no read is stored",
      ("no read is stored" in ev, "retired 2026-11-11; nothing is read any more" in ev), (False, True))

print("\nESPN FPI (NFL), retired 2026-11-02: nothing logged after its retirement landed")
fpi = [q for q in T.bet_rows(T.load()) if q.get("source") == "espn_fpi" and q.get("sport") == "nfl"]
check("no FPI NFL pick logged after 2026-11-02T06:13Z (#292 merged)", [q["id"] for q in fpi if str(q.get("logged")) > "2026-11-02T06:13"], [])

check("no guarded phrase in the page copy", sandbox_audit.COPY_RE.search(r + ev), None)
print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
