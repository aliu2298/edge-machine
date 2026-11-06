#!/usr/bin/env python3
"""Offline checks for the 2026-11-06 hand promotions (Olu, on tiny samples): under 3.5 low-scoring, CUPS scope, and team 2+ form,
INTERNATIONALS scope. Each is one Production pair at the default stake with a fresh record from the move."""
import datetime as dt
import sys

import production as P
import sandbox_audit
import sandbox_sources as S
import sandbox_track as T

FAILS = []
CUP, INTL = "u35_low_scoring|soccer_u35_cup", "team2_form_l10|soccer_team2_intl"


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


print("the listings")
check("both are listed by hand on 2026-11-06 for the next run", (T.PAIR_OVERRIDES[CUP], T.PAIR_OVERRIDES[INTL]),
      (dict(moved_on="2026-11-06", production_at=None), dict(moved_on="2026-11-06", production_at=None)))
check("the rest of each rule stays out: Clubs under, Cups team 2+, Clubs team 2+",
      [k in T.PAIR_OVERRIDES for k in ("u35_low_scoring|soccer_u35", "team2_form_l10|soccer_team2_cup", "team2_form_l10|soccer_team2")], [False, False, False])
check("the Internationals under stays in Production", "u35_low_scoring|soccer_u35_intl" in T.PAIR_OVERRIDES, True)
check("the feed bets", (T.FEED_BETS["soccer_u35_cup"], T.FEED_BETS["soccer_team2_intl"]),
      ({"kind": "total_lte", "n": 3}, {"kind": "team_gte", "n": 2}))
check("every cup competition is a feed league now", set(S.CUP_FRAGS.values()) <= S.feed_binary_leagues(), True)

print("\nthe leads their own recorded bets make")
d = T.load()
built = dt.datetime.now(dt.timezone.utc)
for pair, kind, side in ((CUP, "total_lte", "no"), (INTL, "team_gte", "yes")):
    src, sport = pair.split("|")
    qs = [q for q in T.bet_rows(d) if q.get("source") == src and q.get("sport") == sport]
    check(f"{pair}: it has recorded bets to publish", bool(qs), True)
    for q in qs:
        lead = P.lead_from_quote(q, pair, built)
        check(f"{pair}: {q['label'][:44]} is publishable, ESPN-verified, on a feed league",
              (T.placeable(q), P.start_verified(q), S.quote_league(q) is not None), (True, True, True))
        check(f"{pair}: the exact contract and side", (lead["bet"]["kind"], lead["route"]["outcome_side"], lead["route"]["venue"]), (kind, side, "kalshi"))

print("\nthe notes and public copy")
check("the registry notes carry the move", ("Cups scope: in Production from 2026-11-06" in S.SOURCES["u35_low_scoring"]["note"],
                                           "Internationals scope: in Production from 2026-11-06" in S.SOURCES["team2_form_l10"]["note"]), (True, True))
check("neither note trips the copy guard", (bool(sandbox_audit.COPY_RE.search(S.SOURCES["u35_low_scoring"]["note"])),
                                            bool(sandbox_audit.COPY_RE.search(S.SOURCES["team2_form_l10"]["note"]))), (False, False))

if FAILS:
    print(f"\nFAILED {len(FAILS)}")
    sys.exit(1)
print("ALL PASS")
