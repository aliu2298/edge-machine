#!/usr/bin/env python3
"""Offline checks for the 2026-10-31 soccer retirements (Olu): label rules D1 and C5-C7, team rules T6 and T8, the
contender over 3.5 variant and the u35_low_scoring Clubs pair. None is in Production; nothing in Production moves."""
import datetime as dt
import sys

import contender_overs as CO
import contender_overs_build as COB
import sandbox_audit
import sandbox_sources as S
import sandbox_track as T
import soccer_rules as SR
import soccer_rules_build as SRB
import soccer_rules_production as SRP
import soccer_team_rules as TR
import soccer_team_rules_build as TRB
import soccer_team_rules_production as TRP

FAILS = []
UTC = dt.timezone.utc
BEFORE = dt.datetime(2026, 10, 31, 3, 0, tzinfo=UTC)      # still Oct 30 in New York
AFTER = dt.datetime(2026, 10, 31, 5, 0, tzinfo=UTC)       # Oct 31 01:00 ET


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


print("label rules: D1, C5, C6, C7 retired (D2 already since 2026-10-24); the Production rules are not")
gone = {k for k, v in SR.RETIRED.items() if v["on"] == "2026-10-31"}
check("the four rules", gone, {"D1", "C5", "C6", "C7"})
check("Eastern date gate: 03:00Z is not yet retired, 05:00Z is",
      [(SR.retired(k, BEFORE), SR.retired(k, AFTER)) for k in ("D1", "C5")], [(False, True)] * 2)
check("each carries its record and reason", [SR.RETIRED[k]["reason"] for k in ("D1", "C5", "C6", "C7")],
      ["retired at 27: 14 won, 13 lost, −19.4% after fees", "0–3; 0–10 across C5-C7, retired early by Olu",
       "0–5; 0–10 across C5-C7, retired early by Olu", "0–2; 0–10 across C5-C7, retired early by Olu"])
check("A6, A7 and D3 (Production) are never retired", [SR.retired(k, AFTER) for k in ("A6", "A7", "D3")], [False] * 3)
check("live_rules drops a retired rule where it applies and keeps the others",
      all(k not in SR.live_rules(lg, a, b, AFTER) for lg in SR.SERIES for a in ("O+D-", "O-D-", "O-D+") for b in ("O+D-", "O+", "O+D+", "O-D+")
          for k in ("D1", "C5", "C6", "C7")), True)

print("\nteam rules: T6 and T8 retired; T1, T5 and T7 untouched")
check("the two rules, dated and with records", {k: v["on"] for k, v in TR.RETIRED.items()}, {"T6": "2026-10-31", "T8": "2026-10-31"})
check("date gate", (TR.retired("T6", BEFORE), TR.retired("T6", AFTER), TR.retired("T8", AFTER), TR.retired("T5", AFTER), TR.retired("T7", AFTER)),
      (False, True, True, False, False))
f = dict(league="Premier League", home="A", away="B", kickoff="2026-11-01T15:00:00Z", played=False)
import re
import inspect
check("picks_for skips a retired rule before building any entry", "if retired(rule, now):" in inspect.getsource(TR.picks_for), True)
check("the Production team-rule pairs are exactly what they were", sorted(TRP.PAIRS), ["T5", "T7"])

print("\ncontender overs: the over 3.5 variant only")
check("O35 retired, O15 and O25 not", (CO.retired("O35", AFTER), CO.retired("O15", AFTER), CO.retired("O25", AFTER),
                                       CO.retired("O35", BEFORE)), (True, False, False, False))
ev = {"event_ticker": "KXEREDIVISIETOTAL-26NOV01AJAPSV", "markets": []}
check("picks_for skips the retired variant", "if retired(key, now):" in inspect.getsource(CO.picks_for), True)

print("\nthe page sections")
state = {"rules": {k: {"picks": [dict(id=f"{k}:x", rule=k, status="lost", profit=-100.0, price=0.5, side="yes", match="a v b",
                                      start="2026-10-20T00:00:00+00:00", title="t", labels={}, league="EPL")]}
                   for k in list(SR.RULES)}}
sec = SRB.section(state)
marked = sorted(set(re.findall(r'data-rule="([A-Z]\d)"[^>]*data-retired="([^"]+)"', sec)))
check("the label-rules section marks D1, C5-C7 (2026-10-31) and D2 (2026-10-24), dated with their records",
      (marked, "retired at 27: 14 won, 13 lost" in sec and "0–10 across C5-C7" in sec),
      ([("C5", "2026-10-31"), ("C6", "2026-10-31"), ("C7", "2026-10-31"), ("D1", "2026-10-31"), ("D2", "2026-10-24")], True))
tsec = TRB.section({"rules": {k: {"picks": []} for k in TR.RULES}})
check("the team-rules section marks T6 and T8 only, with their records",
      (sorted(re.findall(r'data-rule="(T\d)" data-retired', tsec)), "−23.0% after fees on 15 bets" in tsec, "−51.6% after fees on 11 bets" in tsec),
      (["T6", "T8"], True, True))
csec = COB.section({"rules": {k: {"picks": []} for k in CO.VARIANTS}})
check("the contender section marks O35 only, retired early",
      (re.findall(r'data-rule="(O\d+)" data-retired', csec), "retired early by Olu" in csec), (["O35"], True))

print("\nu35_low_scoring Clubs pair: retired; Cups, Internationals and the over 1.5 lane keep running")
src = S.SOURCES["u35_low_scoring"]
check("Clubs moved from sports to retired_sports with a dated record; Cups and Internationals stay",
      (src["sports"], sorted(src["retired_sports"]), src["retired_sports"]["soccer_u35"].startswith("Retired 2026-10-31 by Olu: no edge at 36 settled"),
       "25 won v 25.8 priced" in src["retired_sports"]["soccer_u35"]), (["soccer_u35_cup", "soccer_u35_intl"], ["soccer_u35"], True, True))
check("the Internationals pair is still in Production and the Clubs pair never was",
      ("u35_low_scoring|soccer_u35_intl" in T.PAIR_OVERRIDES, "u35_low_scoring|soccer_u35" in T.PAIR_OVERRIDES), (True, False))
check("u35_low_o15 still runs on its own sport and selects through the shared predicate",
      (S.SOURCES["u35_low_o15"]["sports"], "u35_low_selected" in inspect.getsource(S.fetch_u35_low_o15), S.SOURCES["u35_low_o15"].get("retired_sports")),
      (["soccer_o15"], True, None))
rows = [dict(market_id="KXEPLTOTAL-26NOV01-1", price_a=0.80, mid_a=0.78, tradeable={"a": True}, espn_home="H", espn_away="A", league="Premier League")]
S._rule_rows, _old = (lambda sport, universe: [(r, dt.datetime(2026, 11, 1, tzinfo=UTC)) for r in rows]), S._rule_rows
S.u35_low_selected, _sel = (lambda r, ko, fx: True), S.u35_low_selected
try:
    out = S.fetch_u35_low_o15("soccer_o15", universe=rows, fixtures=[])
finally:
    S._rule_rows, S.u35_low_selected = _old, _sel
check("fetch_u35_low_o15 still selects a low-scoring match (retiring the Clubs under pair changed nothing for it)",
      [x["market_id"] for x in out], ["KXEPLTOTAL-26NOV01-1"])

print("\nProduction soccer feeds still publish the Production rules")
check("rules feed pairs A6, A7, D3, Argentina; team feed T5, T7", (sorted(SRP.PAIRS), sorted(TRP.PAIRS)),
      (sorted(SRP.PAIRS), ["T5", "T7"]))
check("none of the retired rules is a Production pair",
      sorted((set(SRP.PAIRS) | set(TRP.PAIRS)) & {"D1", "C5", "C6", "C7", "T6", "T8", "O35"}), [])
check("no guarded phrase in the retirement copy",
      sandbox_audit.COPY_RE.search(sec + tsec + csec + str(SR.RETIRED) + str(TR.RETIRED) + str(CO.RETIRED) + str(src["retired_sports"])), None)

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
