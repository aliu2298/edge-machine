#!/usr/bin/env python3
"""An open bet more than 24h past its start is named by the settler, not left "in play".

grade() prints one ::warning:: line per overdue bet after it has settled what the
venues could answer. The tennis page shows the same rows as "unsettled · Nh".
Removed lanes and rows retired as unplaceable are left out, the rows grade()
does not settle. Nothing here settles, guesses, or writes a ledger.
"""
import datetime
import io
import re
import contextlib
import sys
from datetime import timedelta, timezone

import sandbox_track as T
import sandbox_sources as S
import tennis_cards as C

FAILS = []
NOW = datetime.datetime(2026, 10, 8, 15, 0, tzinfo=timezone.utc)


def ok(cond, msg):
    print(f"  {'ok  ' if cond else 'FAIL'} {msg}")
    if not cond:
        FAILS.append(msg)


def eq(got, want, msg):
    ok(got == want, msg if got == want else f"{msg} — got {got!r}, want {want!r}")


def bet(pid, hours, source="tennis_fav_band_3h", sport="tennis", venue="kalshi", status="open",
        bet=True, **extra):
    start = NOW - timedelta(hours=hours)
    q = dict(id=pid, source=source, sport=sport, bet=bet, status=status, pick="a", price=0.8,
             venue=venue, market_id=f"m-{pid}", label=f"Alpha v Beta {pid}", side_a="Alpha",
             side_b="Beta", start=start.isoformat(), logged=(start - timedelta(hours=1)).isoformat(),
             date=start.date().isoformat(), tier="atp", url="https://kalshi.com/x", stake=100.0)
    q.update(extra)
    return q


d = {"quotes": [
    bet("fresh", 2),                                  # 2h past: not overdue
    bet("edge", T.OVERDUE_H - 0.5),                   # just inside the flag
    bet("late", 30),                                  # overdue
    bet("later", 60, venue="combo", source="tennis_combo2", sport="tennis_combo",
        legs=[dict(market_id="L1", name="Alpha", pick="a", venue="kalshi"),
              dict(market_id="L2", name="Gamma", pick="a", venue="kalshi")],
        label="2-leg tennis combo: Alpha + Gamma", pick="a", side_a="All 2 win", side_b="Any one loses"),
    bet("settled", 50, status="won", result="a", pnl=25.0),   # settled: not open
    bet("fixture", 50, bet=False),                            # a stored fixture, no stake
    bet("unplaceable", 50, note=T.KALSHI_UNPLACEABLE),        # retired as unplaceable
    bet("nostart", 0, start=None),                            # no start to read
]}

print("overdue_bets")
got = [(q["id"], round(age)) for q, age in T.overdue_bets(d, NOW)]
eq(got, [("later", 60), ("late", 30)], "every open bet more than 24h past its start, oldest first")
eq(T.OVERDUE_H, 24, "the flag is 24 hours")

print("\ngrade() names them")
settled_now = {}


def _none(q):
    return None


saved = T._resolve_market
T._resolve_market = _none
try:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        n = T.grade(d, verbose=True, now=NOW, mismatches=set())
finally:
    T._resolve_market = saved
out = buf.getvalue()
eq(n, 0, "nothing settles when the venues have no answer")
lines = [ln for ln in out.splitlines() if ln.startswith("::warning::")]
eq(len(lines), 2, "one warning per overdue bet")
ok(any(ln.startswith("::warning::later is still open 60h past its start") for ln in lines),
   "the warning names the bet and its age")
ok(any("::warning::late is still open 30h" in ln for ln in lines), "the single-match bet is named too")
ok(not any("fresh" in ln or "edge" in ln or "fixture" in ln or "unplaceable" in ln for ln in lines),
   "a fresh bet, a stored fixture and an unplaceable row are not flagged")
ok(all(q["status"] == "open" for q in d["quotes"] if q["id"] in ("late", "later")),
   "flagging never settles or guesses a result")

print("\nthe tennis page says so")
rows = [dict(name="tennis_fav_band_3h", sport="tennis", meta=S.SOURCES["tennis_fav_band_3h"],
             prod=False, v="waiting", a=dict(n=0, won=0), open=3, since=None),
        dict(name="tennis_combo2", sport="tennis_combo", meta=S.SOURCES["tennis_combo2"],
             prod=False, v="waiting", a=dict(n=0, won=0), open=1, since=None)]
html = C.picks_html(d, rows, NOW)
eq(C.state_of(d["quotes"][2], NOW), ("unsettled · 30h", "is-late"), "an overdue pick reads unsettled · Nh")
eq(C.state_of(d["quotes"][0], NOW), ("in play", "is-live"), "a pick 2h past its start is in play")
eq(C.state_of(d["quotes"][1], NOW), ("in play", "is-live"), "a pick inside 24h is still in play")
ok('class="tn-state is-late">unsettled · 60h<' in html, "the basket's line carries the badge")
badges = re.findall(r'<span class="tn-state (is-[a-z]+)">', html)
eq(sorted(badges), ["is-late", "is-late", "is-live", "is-live", "is-next"],
   "two overdue, two in play, one with no start to read")

if FAILS:
    print(f"\nFAILED {len(FAILS)}")
    sys.exit(1)
print("\nPASSED")
