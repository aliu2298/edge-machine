#!/usr/bin/env python3
"""Offline checks for the 2026-11-12 retirements (Olu). The second, at the foot: La Liga under 1.5 in heavy mismatches, version 1 (liga_u15_dog),
replaced by version 2 (liga_u15_dog_24h): the same matches, bet inside 24 hours of kickoff. The first: the Eredivisie draw band, version 1 (ere_draw), replaced by version 2 (ere_draw_home).
Why: v1 placed its bets a median 4.5 days before kickoff, while its research was on prices at the close. No new entries; its rows stay on file
and its open bets still settle. Its final paper record and its earlier live run (4–13, −4.3%) are on the retired line, the live run as history."""
import re
import sys

import sandbox_audit
import sandbox_build as B
import sandbox_sources as S
import soccer_build as SB

FAILS = []


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


print("the registry: retired with a dated record, rows still settle")
m = S.SOURCES["ere_draw"]
check("no live scope, retired on soccer", (m["sports"], list(m["retired_sports"])), ([], ["soccer"]))
why = S.ERE_DRAW_RETIRED_WHY
check("the reason carries the date, the replacement and the cause", all(x in why for x in ("Retired 2026-11-12", "ere_draw_home", "median 4.5 days", "prices at the close")), True)
check("the final paper record is on the line", all(x in why for x in ("9 won v 6.9 priced on 29", "+22.6%")), True)
check("the earlier live run is on the line, as history", all(x in why for x in ("Earlier live run", "history", "4 won, 13 lost", "17 settled", "−4.3%")), True)
check("no new entries, rows stay, open bets settle", "No new entries from 2026-11-12" in why and "still settle" in why, True)
check("its stored rows are not removed rows", S.removed_row(dict(source="ere_draw", sport="soccer")), False)
check("version 2 keeps running, and the maker lane is untouched", (S.SOURCES["ere_draw_home"]["sports"], S.SOURCES["ere_draw_maker"]["label"] if "ere_draw_maker" in S.SOURCES else "maker"),
      (["soccer"], "maker"))
check("the stamp-of-approval table tags it retired", B.source_retired("ere_draw"), True)

print("\nthe Soccer page: a Retired row, not a live one")
html = SB.build()
r_at, e_at, t_at = html.find('id="rules"'), html.find('id="events"'), html.find('id="retired"')
check("ere_draw is not in the live rules table", 'data-source="ere_draw" ' in html[r_at:e_at], False)
ret = html[t_at:]
check("it is in the Retired block, with its paper record and the reason", ('data-source="ere_draw"' in ret, "median 4.5 days" in html, "9–20" in ret), (True, True, True))
check("ere_draw_maker still shows beside it in the live table", 'data-source="ere_draw_maker"' in html[r_at:e_at], True)
check("plain copy: no dollar amount, no guarded phrase", (re.search(r"\$\d", why), sandbox_audit.COPY_RE.findall(why)), (None, []))

print("\nLa Liga under 1.5 in heavy mismatches, version 1 (liga_u15_dog): retired the same day, replaced by version 2 (liga_u15_dog_24h)")
m = S.SOURCES["liga_u15_dog"]
check("no live scope, retired on over 1.5", (m["sports"], list(m["retired_sports"])), ([], ["soccer_o15"]))
why = S.LIGA_U15_DOG_RETIRED_WHY
check("the reason carries the date, the replacement and the cause", all(x in why for x in ("Retired 2026-11-12", "liga_u15_dog_24h", "median 4 days", "inside 24 hours")), True)
check("the final paper record is on the line", all(x in why for x in ("3 won v 1.2 priced on 9", "+112.2%")), True)
check("it was never in Production, and says so", ("Never in Production" in why, "liga_u15_dog" in S.BACK_IN_SANDBOX), (True, False))
check("no new entries, rows stay, open bets settle", "No new entries from 2026-11-12" in why and "still settle" in why, True)
check("its stored rows are not removed rows", S.removed_row(dict(source="liga_u15_dog", sport="soccer_o15")), False)
check("version 2 runs on the same market, under its own key", (S.SOURCES["liga_u15_dog_24h"]["sports"], S.CHALLENGERS["liga_u15_dog_24h"] is S.fetch_liga_u15_dog_24h),
      (["soccer_o15"], True))
check("the stamp-of-approval table tags v1 retired, not v2", (B.source_retired("liga_u15_dog"), B.source_retired("liga_u15_dog_24h")), (True, False))
check("v1 is not in the live rules table", 'data-source="liga_u15_dog" ' in html[r_at:e_at], False)
check("it is in the Retired block, with its paper record and the reason", ('data-source="liga_u15_dog"' in ret, "median 4 days" in ret, "3–6" in ret), (True, True, True))
check("version 2 is on the Soccer page", "La Liga under 1.5 in heavy mismatches v2 (inside 24h)" in html, True)
check("the La Liga BTTS lane is untouched", (S.SOURCES["liga_btts_even"]["sports"], 'data-source="liga_btts_even" ' in html[r_at:e_at]), (["soccer_btts"], True))
check("plain copy: no dollar amount, no guarded phrase", (re.search(r"\$\d", why), sandbox_audit.COPY_RE.findall(why)), (None, []))
v2 = S.SOURCES["liga_u15_dog_24h"]
check("version 2's label and note: no dollar amount, no guarded phrase",
      (re.search(r"\$\d", v2["label"] + v2["note"]), sandbox_audit.COPY_RE.findall(v2["label"] + v2["note"])), (None, []))

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
