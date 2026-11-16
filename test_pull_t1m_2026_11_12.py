#!/usr/bin/env python3
"""2026-11-12 (Olu: "return Over 3.5 when two attacking, tight sides meet to sandbox"): T1-M (st_t1m, soccer_u35) is out of Production.
Offline. Its paper record stays, its live bets stay on the Production page as history, T1-H and T7 are untouched."""
import sandbox_audit
import soccer_lanes as L
import soccer_team_rules as TR
import soccer_team_rules_production as TRP

fails = []


def check(name, ok):
    print(("  ok   " if ok else "  FAIL ") + name)
    if not ok:
        fails.append(name)


check("T1-M is not a Production pair; T1-H and T7 still are", sorted(TRP.PAIRS) == ["T1H", "T7"])
check("no pair for st_t1m is published", not any(k.startswith("st_t1m|") for k in TRP.pairs()))
check("the other T-family pairs are unchanged", {"st_t1h|soccer_team2", "st_t7|soccer_team3"} <= set(TRP.pairs()))
check("the pull is dated", TRP.T1M_PULLED == ("2026-11-08", "2026-11-12"))
check("T1-M is still a logged paper rule", "T1M" in TR.SIBLINGS and "T1M" in TR.LANES)
live, _gone, _q = L.team_rows({"rules": {"T1M": {"picks": []}, "T1H": {"picks": []}}})
rows = {r["name"]: r for r in live}
d = rows["st_t1m"]["own"]["details"]
check("the Soccer page row is Sandbox paper, not Production", rows["st_t1m"]["prod"] is False)
check("its history says it was in Production 2026-11-08 to 2026-11-12", "Production 2026-11-08 to 2026-11-12, back in the Sandbox" in d)
check("T1-H is still a Production row", rows["st_t1h"]["prod"] is True)
check("no guarded public phrase", sandbox_audit.COPY_RE.search(d) is None)
print(f"\n{'ALL PASS' if not fails else str(len(fails)) + ' FAILED'}")
raise SystemExit(1 if fails else 0)
