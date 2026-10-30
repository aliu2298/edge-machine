#!/usr/bin/env python3
"""Team 3+ NO bets (st_t7, soccer_team3) are one outcome each, not one exclusive set per match (2026-10-29).

The Production page showed "record unavailable: DegenerateCluster: 3 of 3 outcome clusters" for st_t7:
soccer_team3 was missing from the soccer goals domains, so outcome_cluster keyed its two teams' No legs
of one match (0.68 + 0.74) by the event and summed them past 1. Both teams can stay under 3, so they are
two outcomes. The DegenerateCluster guard itself is unchanged and still fires on a true exclusive set.
"""
import sys

import sandbox_sources as S
import sandbox_track as T

FAILS = []


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


def leg(tk, price, won, sport="soccer_team3", source="st_t7", pick="b"):
    return dict(id=f"{source}:{tk}", source=source, sport=sport, market_id=tk, venue="kalshi_binary", pick=pick,
                price=price, bet=True, status="won" if won else "lost", result=pick if won else "a", stake=T.STAKE)


ev = "KXMLSTEAMTOTAL-26OCT17LAGSD"
a, b = leg(f"{ev}-LAG3", 0.68, True), leg(f"{ev}-SD3", 0.74, True)
check("the two teams' No legs of one match are two outcomes", S.outcome_cluster(a) != S.outcome_cluster(b), True)
check("each leg is its own outcome (its id)", (S.outcome_cluster(a), S.outcome_cluster(b)), (a["id"], b["id"]))
t2 = [leg(f"{ev}-LAG2", 0.6, True, "soccer_team2", "st_t5", "a"), leg(f"{ev}-SD2", 0.7, True, "soccer_team2", "st_t5", "a")]
check("team 2+ (st_t5) was already one outcome per leg", len({S.outcome_cluster(q) for q in t2}), 2)

clusters = {}
for q in (a, b, leg("KXMLSTEAMTOTAL-26OCT28MINSKC-MIN3", 0.53, False), leg("KXMLSTEAMTOTAL-26OCT28MINSKC-SKC3", 0.9, True)):
    clusters.setdefault(S.outcome_cluster(q), []).append((q["price"], q["price"], q["status"] == "won"))
try:
    stats = T.cluster_stats(clusters)
    check("cluster_stats gives st_t7's bets a record", stats is not None, True)
except T.DegenerateCluster as e:
    check(f"cluster_stats gives st_t7's bets a record ({e})", False, True)

bad = {"X": [(0.6, 0.6, True), (0.7, 0.7, True)], "Y": [(0.6, 0.6, True), (0.7, 0.7, True)]}
try:
    T.cluster_stats(bad)
    raised = False
except T.DegenerateCluster:
    raised = True
check("the guard still raises on exclusive buckets priced past 1", raised, True)

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
