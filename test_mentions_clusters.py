#!/usr/bin/env python3
"""Trump-mentions records are judged per word with an event-clustered variance (2026-10-23).

Reproduces the failure that stopped every Sandbox Tracker run from 06:36Z on 2026-10-23: two
settled KXTRUMPSAY weeks of NO bets priced 0.5-0.9 raised DegenerateCluster ('MENTIONS_KXTRUMPSAY').
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


def word(event, w, price, won, pick="b"):
    tk = f"{event}-{w}"
    return dict(id=f"mentions_rate:{tk}", source="mentions_rate", sport="culture_mentions", market_id=tk, event=event,
                venue="kalshi_binary", pick=pick, price=price, bet=True, status="won" if won else "lost",
                result=pick if won else ("a" if pick == "b" else "b"), stake=T.STAKE,
                pnl=round(T.STAKE * (1 / price - 1), 2) if won else -T.STAKE, date=event[-7:],
                start="2026-10-19T14:00:00+00:00", logged="2026-10-19T13:00:00+00:00", settled="2026-10-26T04:00:00+00:00")


W1, W2 = "KXTRUMPSAY-26OCT19", "KXTRUMPSAY-26OCT26"
week1 = [word(W1, w, p, won) for w, p, won in (("CEAS", .83, True), ("LISA", .92, True), ("ANTI", .72, True),
                                                ("GOLD", .80, False), ("UFO", .55, True), ("EPST", .66, True),
                                                ("PEAC", .90, True), ("MAKE", .60, False))]
week2 = [word(W2, w, p, won) for w, p, won in (("PANA", .58, True), ("VERI", .70, False), ("SDN", .66, True))]
d = {"meta": {}, "quotes": week1 + week2, "coverage": {}}

print("today's failure: two settled weeks of NOs at 0.5-0.9 no longer raise")
try:
    a = T.assess(d, "mentions_rate", "culture_mentions")
    raised = None
except T.DegenerateCluster as e:                                # noqa: PERF203
    a, raised = None, str(e)[:80]
check("assess returns a record", raised, None)
check("each word counts: 11 bets, 8 won, judged per bet", (a["n"], a["won"], a["unit"]), (11, 8, "bet"))
check("the expectation is the summed prices", round(a["expected"], 2), round(sum(q["price"] for q in d["quotes"]), 2))

print("\nthe variance is clustered by event, never below the independent one")
iid = sum(q["price"] * (1 - q["price"]) for q in d["quotes"])
ev = sum(sum((q["status"] == "won") - q["price"] for q in wk) ** 2 for wk in (week1, week2))
check("z uses max(independent, event-clustered)", round(a["z"], 4),
      round((a["won"] - a["expected"]) / max(iid, ev) ** 0.5, 4))
together = [word(W1, f"W{i}", .70, True) for i in range(8)]
b = T.assess({"meta": {}, "quotes": together, "coverage": {}}, "mentions_rate", "culture_mentions")
check("a week whose 8 words all came in together reads as one week, not 8 coin flips",
      round(b["z"], 3), round((8 - 5.6) / max(8 * .21, 2.4 ** 2) ** 0.5, 3))
check("each word is its own cluster; the event key groups the variance",
      (S.outcome_cluster(week1[0]), S.event_key(week1[0])), ("KXTRUMPSAY-26OCT19-CEAS", W1))
check("the mentions sport is per word, not market-day", ("culture_mentions" in S.DAY_CLUSTERED, S.EVENT_CLUSTERED),
      (False, ("culture_mentions", "nba_tt")))

print("\nthe ladder guard is intact")
ladder = [dict(id=f"x:{i}", source="spot", sport="climate", market_id=f"KXHIGHNY-26OCT{10 + i}-T{j}", venue="kalshi_binary",
               pick="a", price=.7, bet=True, status="won", result="a", stake=T.STAKE, pnl=42.86, date=f"2026-10-{10 + i}",
               start=f"2026-10-{10 + i}T20:00:00+00:00", logged=f"2026-10-{10 + i}T10:00:00+00:00") for i in range(3) for j in range(2)]
try:
    T.cluster_stats({S.outcome_cluster(q): [] for q in ladder} | {
        k: [(q["price"], q["price"], True) for q in ladder if S.outcome_cluster(q) == k] for k in {S.outcome_cluster(q) for q in ladder}})
    guard = False
except T.DegenerateCluster:
    guard = True
check("exclusive buckets priced past 1 in every cluster still raise DegenerateCluster", guard, True)
unit = T.day_units([dict(q, sport="crypto_fav", market_id=f"KXSOLD-26OCT1{i}17-T{i}", date=f"2026-10-1{i}") for i, q in enumerate(ladder[:3])])
check("a collapsed market-day is its own cluster, whatever its id holds",
      [S.outcome_cluster(u) for u in unit], [u["id"] for u in unit])

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
