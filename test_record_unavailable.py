#!/usr/bin/env python3
"""One pair whose record raises must not take the page build down.

2026-10-23: the Trump mentions pair's record raised DegenerateCluster inside
production.page and every Sandbox Tracker run failed, the watchdog with it. The pages
now catch it per pair: that pair's row reads "record unavailable: <Type: reason>", a
GitHub ::warning:: names it, and every other pair still builds. The guard itself is
untouched: assess still raises, and the audit's pair_list still raises.
No network, nothing read from data/.
"""
import contextlib
import datetime
import io
import sys
from datetime import timedelta, timezone

import production as P
import sandbox_build as B
import sandbox_track as T
import shell_build

FAILS = []
NOW = datetime.datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)


def ok(cond, why):
    print(f"  {'ok  ' if cond else 'FAIL'} {why}")
    if not cond:
        FAILS.append(why)


def _bet(i, source, sport, hours, status="won", price=0.6):
    start = NOW + timedelta(hours=hours)
    won = status == "won"
    return dict(
        id=f"{source}:{sport}:{i}", source=source, sport=sport, bet=True, status=status,
        pick="a", price=price, result="a" if won else "b", venue="kalshi", stake=100.0,
        pnl=round(100 * (1 / price - 1), 2) if won else -100.0,
        start=start.isoformat(), logged=(start - timedelta(hours=2)).isoformat(),
        date=start.date().isoformat(), settled=(start + timedelta(hours=3)).isoformat(),
        price_a=price, price_b=round(1 - price, 2), side_a="Home", side_b="Away",
        label=f"Home v Away {i}", market_id=f"m-{source}-{i}", url="https://kalshi.com/x",
    )


BAD, GOOD = "o15_form_l10|soccer_o15", "oddspedia|cricket"
PAIRS = {
    BAD: {"stage": "production", "by_hand": "2026-10-01", "ready_at": "2026-10-01T00:00:00+00:00"},
    GOOD: {"stage": "production", "by_hand": "2026-10-01", "ready_at": "2026-10-01T00:00:00+00:00"},
}
d = {"quotes": [_bet(i, s.split("|")[0], s.split("|")[1], -24 * (i + 1), "won" if i % 2 else "lost")
                for s in PAIRS for i in range(6)]}
st = {"pairs": PAIRS}
blob = {"leads": {}, "pairs": {}}

real_assess = T.assess


def flaky_assess(dd, source, sport=None, *a, **kw):
    if source == BAD.split("|")[0] and dd.get("quotes"):
        raise T.DegenerateCluster("1 of 1 outcome clusters hold several bets. First: 'X'.")
    return real_assess(dd, source, sport, *a, **kw)


print("production.page with one pair's record raising")
T.assess = flaky_assess
try:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        html = P.page(d, st, blob, "", now=NOW)
    printed = out.getvalue()
    ok("record unavailable: DegenerateCluster: 1 of 1 outcome clusters" in html,
       "the raising pair's row says record unavailable with the exception type and reason")
    ok('data-pair="o15_form_l10|soccer_o15"' in html, "the warning row names the pair")
    ok("Oddspedia" in html or "oddspedia" in html.lower(), "the other pair still renders")
    ok(html.count('class="unavailable"') == 1, "only the raising pair is marked unavailable")
    ok(f"::warning title=Record unavailable::{BAD}: record unavailable: DegenerateCluster" in printed,
       "a GitHub ::warning:: names the pair")

    print("pair_list: page rows carry the note, the audit still raises")
    # A Sandbox-side pair raising: the page path keeps the row with its note.
    st_sb = {"pairs": {BAD: {"stage": "sandbox"}}}
    with contextlib.redirect_stdout(io.StringIO()):
        rows = B.pair_list(d, st_sb)
    bad = [r for r in rows if f"{r['name']}|{r['sport']}" == BAD]
    ok(len(bad) == 1 and str(bad[0].get("unavailable", "")).startswith("record unavailable: DegenerateCluster"),
       "pair_list keeps the raising pair's row with its note")
    try:
        B.pair_list(d, st_sb, include_retired=True)
        ok(False, "the audit's pair_list (include_retired) still raises DegenerateCluster")
    except T.DegenerateCluster:
        ok(True, "the audit's pair_list (include_retired) still raises DegenerateCluster")

    print("shell_build lane board")
    with contextlib.redirect_stdout(io.StringIO()):
        board = shell_build._lane_board(d, st, BAD, {})
    ok(str(board.get("verdict") or "").startswith("record unavailable: DegenerateCluster"),
       "the home card's verdict says record unavailable")
finally:
    T.assess = real_assess

print("the guard itself is unchanged")
try:
    T.cluster_stats({"k": [(0.6, 0.6, 1), (0.6, 0.6, 0)]})
    raised = False
except T.DegenerateCluster:
    raised = True
ok(raised, "cluster_stats still raises DegenerateCluster on a cluster priced past 1")
ok(T.assess is real_assess, "assess is restored")

if FAILS:
    print(f"\n{len(FAILS)} FAILED")
    sys.exit(1)
print("\nall passed")
