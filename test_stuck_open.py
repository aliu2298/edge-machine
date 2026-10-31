#!/usr/bin/env python3
"""Rows that never settled (2026-10-31): 88 rows of removed lanes sat open for 22-48 days because grade() skipped
removed lanes for good, and one Polymarket row the venue never settled stayed open for ever.

A removed-lane row is left alone while fresh, closed once from the venue after CLOSE_REMOVED_H; a row the venue has
not answered 14 days after its start is refunded with a note, never guessed."""
import sys
from datetime import datetime, timedelta, timezone

import sandbox_sources as S
import sandbox_track as T

FAILS = []


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


NOW = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)


def row(source, sport, days, venue="kalshi_binary", bet=True, mid=None, **kw):
    start = (NOW - timedelta(days=days)).isoformat()
    return dict(id=f"{source}:{mid or source + str(days)}", source=source, sport=sport, market_id=mid or f"{source}{days}",
                venue=venue, status="open", bet=bet, pick="b" if bet else None, price=0.5, price_a=0.5, price_b=0.5, stake=T.STAKE,
                pnl=0.0, start=start, side_a="Yes", side_b="No", label="x", **kw)


answers = {}
_real = (S.resolve_kalshi_market, S.resolve_kalshi, S.resolve_polymarket)
S.resolve_kalshi_market = lambda mid: answers.get(mid)
S.resolve_kalshi = lambda mid: answers.get(mid)
S.resolve_polymarket = lambda mid: answers.get(mid)


def grade(*rows):
    T.grade({"quotes": list(rows), "meta": {}}, verbose=False, now=NOW, mismatches=set())
    return rows


try:
    print("removed lanes")
    check("nws_fade is a removed lane", S.lane_removed("nws_fade", "climate"), True)
    old, fresh = row("nws_fade", "climate", 5, mid="OLD"), row("nws_fade", "climate", 1, mid="FRESH")
    answers.update(OLD="b", FRESH="b")
    grade(old, fresh)
    check("a removed-lane row 5 days past its start is closed from the venue, once",
          (old["status"], old["result"], old["pnl"]), ("won", "b", round(T.STAKE * (1 / 0.5 - 1), 2)))
    check("a removed-lane row 1 day past its start stays frozen", (fresh["status"], fresh["pnl"]), ("open", 0.0))
    two_days = row("nws_fade", "climate", 2, mid="TWO")
    answers["TWO"] = "b"
    grade(two_days)
    check("and so does one 2 days old (the old rule held it as long as the lane is removed; the cut is 72h)", two_days["status"], "open")
    unplaceable = row("olbg", "boxing", 30, venue="kalshi", mid="UNP", note=T.KALSHI_UNPLACEABLE)
    answers["UNP"] = "a"
    grade(unplaceable)
    check("a row retired as unplaceable is still not graded", unplaceable["status"], "open")
    nobet = row("polymarket_us", "table_tennis", 10, venue="polymarket_us", bet=False, mid="NB")
    S_us = S.resolve_polymarket_us
    S.resolve_polymarket_us = lambda mid: "a"
    try:
        grade(nobet)
    finally:
        S.resolve_polymarket_us = S_us
    check("an old removed observation is graded, never staked", (nobet["status"], nobet["pnl"]), ("graded", 0.0))

    print("kept lanes")
    kept = row("o15_form_l10", "soccer_o15", 4, mid="KEPT")
    answers["KEPT"] = "a"
    grade(kept)
    check("a kept lane settles exactly as before", kept["status"], "lost")

    print("no venue answer")
    gone = row("polymarket", "cricket", 15, venue="polymarket", bet=False, mid="GONE")
    young = row("polymarket", "cricket", 10, venue="polymarket", bet=False, mid="YOUNG")
    grade(gone, young)
    check("a row with no venue answer 15 days after its start is refunded with a note",
          (gone["status"], gone["result"], gone["pnl"], gone["note"]), ("void", "void", 0.0, T.NO_ANSWER_NOTE))
    check("one 10 days old is left open: the venue may still settle it", young["status"], "open")
    test_cricket = row("polymarket", "cricket", 15, venue="polymarket", bet=False, mid="testcr-sao-aus-2026-10-16")
    grade(test_cricket)
    check("a five-day Test match gets its own length on top (15 days is not enough)", test_cricket["status"], "open")
    bet_gone = row("o15_form_l10", "soccer_o15", 20, mid="BETGONE")
    grade(bet_gone)
    check("a bet the venue never answered is refunded, not left open or guessed", (bet_gone["status"], bet_gone["pnl"]), ("void", 0.0))
    late = row("o15_form_l10", "soccer_o15", 20, mid="LATE")
    answers["LATE"] = "a"
    grade(late)
    check("a late venue answer still wins over the refund", late["status"], "lost")
    check("a settled row keeps its time on a later pass", gone["settled"] is not None, True)
finally:
    S.resolve_kalshi_market, S.resolve_kalshi, S.resolve_polymarket = _real

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
