#!/usr/bin/env python3
"""Offline checks for the 2026-11-01 soccer retirements (Olu): team rule T2, contender overs O25 and O15 (with O35 the whole
contender_overs lane), and label rule D3 (back in the Sandbox since 2026-10-28). T1 stays in the Sandbox with a re-read at 50.
Nothing in Production moves."""
import datetime as dt
import inspect
import re
import sys

import contender_overs as CO
import contender_overs_build as COB
import sandbox_audit
import sandbox_track as T
import soccer_rules as SR
import soccer_rules_build as SRB
import soccer_rules_production as SRP
import soccer_team_rules as TR
import soccer_team_rules_build as TRB
import soccer_team_rules_production as TRP

FAILS = []
UTC = dt.timezone.utc
BEFORE = dt.datetime(2026, 11, 1, 3, 0, tzinfo=UTC)       # still Oct 31 in New York (Eastern time is UTC-4 until 02:00 local on Nov 1)
AFTER = dt.datetime(2026, 11, 1, 10, 0, tzinfo=UTC)


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


print("the four retirements, dated and with the record each was retired on")
check("T2", (TR.RETIRED["T2"]["on"], TR.RETIRED["T2"]["reason"]),
      ("2026-11-01", "4 won of 10, −21.8% after fees at the 10-bet review; research was +29%"))
check("D3", (SR.RETIRED["D3"]["on"], SR.RETIRED["D3"]["reason"]),
      ("2026-11-01", "23 won of 38, +1.6% after fees past the 30-bet decision; flat, and it lost its Production week"))
check("O25", (CO.RETIRED["O25"]["on"], CO.RETIRED["O25"]["reason"]),
      ("2026-11-01", "5 won of 10, −30.8% after fees; contender matches are not scoring"))
check("O15", (CO.RETIRED["O15"]["on"], CO.RETIRED["O15"]["reason"]), ("2026-11-01", "8 won of 10 at 82-92c, −10.4% after fees"))
check("Eastern date gate: Oct 31 evening is not retired, Nov 1 is",
      [(f(k, BEFORE), f(k, AFTER)) for f, k in ((TR.retired, "T2"), (SR.retired, "D3"), (CO.retired, "O25"), (CO.retired, "O15"))],
      [(False, True)] * 4)
check("the whole contender_overs lane is retired now: every variant", sorted(CO.RETIRED), sorted(CO.VARIANTS))
check("a retired rule makes no new entry (the gate is before any entry is built)",
      ("if retired(rule, now):" in inspect.getsource(TR.picks_for), "if retired(key, now):" in inspect.getsource(CO.picks_for),
       "retired(" in inspect.getsource(SR.live_rules)), (True, True, True))
check("T1, T5, T7 and the Production label rules are not retired",
      (TR.retired("T1", AFTER), TR.retired("T5", AFTER), TR.retired("T7", AFTER), SR.retired("A6", AFTER), SR.retired("A7", AFTER)),
      (False,) * 5)

print("\nD3 cannot come back to Production")
check("it is not a Production pair, and was never added to the stage overrides",
      ("D3" in SRP.PAIRS, any("sr_d3" in k for k in T.PAIR_OVERRIDES)), (False, False))
check("retired, the rule stops logging, so the Production feed has no D3 lead to publish",
      (SR.retired("D3", AFTER), sorted(SRP.PAIRS)), (True, sorted(SRP.PAIRS)))
check("the Production pairs are what they were", (sorted(SRP.PAIRS), sorted(TRP.PAIRS)), (["A6", "A7", "C1", "C3", "C4"], ["T5", "T7"]))

print("\nthe pages")
state = {"rules": {k: {"picks": []} for k in TR.RULES}}
tsec = TRB.section(state)
check("the team section marks T2 retired 2026-11-01 with its record, and T1 carries the re-read note",
      (re.findall(r'data-rule="(T\d)" data-retired="2026-11-01"', tsec), "−21.8% after fees at the 10-bet review" in tsec,
       "Re-read at 50 settled (Olu, 2026-11-01)" in tsec, tsec.count("data-rule=\"T1\"")), (["T2"], True, True, 1))
check("T1 is not marked retired", 'data-rule="T1" data-retired' in tsec, False)
srules = SRB.section({"rules": {k: {"picks": []} for k in SR.RULES}})
check("the label-rules section marks D3 retired 2026-11-01 with its record",
      (re.findall(r'data-rule="(D3)"[^>]*data-retired="([^"]+)"', srules), "+1.6% after fees past the 30-bet decision" in srules),
      ([("D3", "2026-11-01")], True))
csec = COB.section({"rules": {k: {"picks": []} for k in CO.VARIANTS}})
check("the contender section marks all three variants retired and its header says so",
      (sorted(re.findall(r'data-rule="(O\d+)" data-retired', csec)), "Retired 2026-11-01 (over 3.5 on 2026-10-31): no new entries" in csec),
      (["O15", "O25", "O35"], True))
check("no guarded phrase in the retirement copy",
      sandbox_audit.COPY_RE.search(tsec + srules + csec + str(TR.RETIRED) + str(SR.RETIRED) + str(CO.RETIRED)), None)

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
