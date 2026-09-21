#!/usr/bin/env python3
"""test_audit.py — the audit catches what it claims to. No network.

An audit that has only ever passed proves nothing, so every check here is fed a record with
one planted fault and must fire, and the same record with the fault removed must not.
"""
import sys
from datetime import datetime, timedelta, timezone

import sandbox_audit as A
import sandbox_sources as S

FAILS = []


def ok(cond, why):
    print(f"  {'ok  ' if cond else 'FAIL'} {why}")
    if not cond:
        FAILS.append(why)


NOW = datetime.now(timezone.utc)


def bet(i, won=True, price=0.60, **kw):
    q = dict(id=f"src:m{i}", source="src", sport="mlb", market_id=f"m{i}", venue="kalshi",
             bet=True, pick="a", price=price, price_a=price, price_b=round(1.02 - price, 2),
             price_draw=None, stake=100.0, result="a" if won else "b",
             status="won" if won else "lost",
             pnl=round(100.0 * (1 / price - 1), 2) if won else -100.0,
             start=(NOW - timedelta(days=3)).isoformat(),
             logged=(NOW - timedelta(days=4)).isoformat(),
             settled=(NOW - timedelta(days=2)).isoformat())
    q.update(kw)
    return q


def run(check, quotes, *a):
    rep = A.Report()
    check({"quotes": quotes, "meta": {}}, rep, *a)
    return rep


def errs(rep, check):
    return [m for c, m in rep.errors if c == check]


print("bets: a clean record passes, and every planted fault is caught")
ok(not run(A.check_bets, [bet(1), bet(2, won=False)]).errors, "a correct won and a correct lost bet pass")
ok(errs(run(A.check_bets, [bet(1, pnl=99.0)]), "bets"), "a won bet paid the wrong amount is caught")
ok(errs(run(A.check_bets, [bet(1, won=False, pnl=-50.0)]), "bets"), "a lost bet that lost the wrong amount is caught")
ok(errs(run(A.check_bets, [bet(1, status="won", result="b")]), "bets"),
   "a bet marked won although its side lost is caught")
ok(errs(run(A.check_bets, [bet(1), bet(1)]), "bets"), "a quote logged twice is caught")
ok(errs(run(A.check_bets, [bet(1, price_a=0.50)]), "bets"), "a price that is not its side's ask is caught")
ok(errs(run(A.check_bets, [bet(1, stake=250.0)]), "bets"), "a stake other than the flat stake is caught")
ok(errs(run(A.check_bets, [bet(1, price=0.99, price_a=0.99, pnl=round(100 * (1 / 0.99 - 1), 2))]), "bets"),
   "a bet priced outside its domain's band is caught")
_late = dict(logged=(NOW - timedelta(days=3) + timedelta(minutes=1)).isoformat())
ok(errs(run(A.check_bets, [bet(1, **_late)]), "bets"), "a bet logged after its start is caught")
ok(not run(A.check_bets, [bet(1, status="void", pnl=0.0, **_late)]).errors,
   "but a late bet already voided for it is correctly handled, not an error")
ok(errs(run(A.check_bets, [bet(1, status="void", pnl=40.0)]), "bets"), "a void that still carries P/L is caught")
ok(errs(run(A.check_bets, [bet(1, bet=False, status="won")]), "bets"), "a non-bet marked won is caught")

print("\nstale: an old open bet is a fault only if the grader had its chance")
_G = NOW - timedelta(hours=1)                      # the ledger's last grading run


def stale(final, final_at, start_days=3):
    """One open bet, the venue answering `final` and finalising at `final_at`."""
    q = bet(7, status="open", result=None, pnl=0.0, settled=None, venue="kalshi_binary",
            market_id="KXWTI-26SEP18-T99", start=(NOW - timedelta(days=start_days)).isoformat())
    saved = (S.resolve_kalshi_market, A._final_at)
    S.resolve_kalshi_market, A._final_at = (lambda mid: final), (lambda q: final_at)
    try:
        rep = A.Report()
        A.check_stale({"quotes": [q], "meta": {"updated": _G.isoformat()}}, rep, True, now=NOW)
        return rep
    finally:
        S.resolve_kalshi_market, A._final_at = saved


r = stale("b", _G - timedelta(hours=5))
ok(errs(r, "stale"), "final BEFORE the last grading run and still open: the grader missed it")
r = stale("b", _G + timedelta(minutes=8))
ok(not r.errors and r.warnings, "final AFTER the last grading run: a warning, the next run settles it")
r = stale(None, None)
ok(not r.errors and r.warnings, "the venue has no result yet: a warning that the venue is late")
r = stale("b", None)
ok(not r.errors and r.warnings, "final but the venue cannot say when: a warning, not a guess")
r = stale("b", None, start_days=9)
ok(errs(r, "stale"), "final, time unknown, and open nine days: an error whatever the reason")
_fresh = bet(8, status="open", result=None, pnl=0.0, settled=None, start=(NOW - timedelta(hours=5)).isoformat())
_r = A.Report()
A.check_stale({"quotes": [_fresh], "meta": {"updated": _G.isoformat()}}, _r, True, now=NOW)
ok(not _r.warnings and not _r.errors, "a bet open a few hours past its start is not stale")

print("\nfresh: the grader has to be running for any of this to mean anything")


def fresh(hours_ago):
    rep = A.Report()
    meta = {} if hours_ago is None else {"updated": (NOW - timedelta(hours=hours_ago)).isoformat()}
    A.check_fresh({"quotes": [], "meta": meta}, rep, now=NOW)
    return rep


ok(not fresh(1.5).errors and not fresh(1.5).warnings, "graded 1.5h ago: fine")
ok(not fresh(5).errors and fresh(5).warnings, "graded 5h ago: one late run, a warning")
ok(errs(fresh(8), "fresh"), "graded 8h ago: two runs missed, the grader has stopped")
ok(errs(fresh(None), "fresh"), "no last-graded time at all: an error")

print("\nsettlement: the stored result must be the venue's")
_saved_k = S.resolve_kalshi
try:
    S.resolve_kalshi = lambda mid: "a"
    ok(not run(A.check_settlement, [bet(i) for i in range(5)], 5).errors, "results that match the venue pass")
    S.resolve_kalshi = lambda mid: "b"
    ok(errs(run(A.check_settlement, [bet(i) for i in range(5)], 5), "settlement"),
       "a stored win the venue calls a loss is caught")
    S.resolve_kalshi = lambda mid: None
    r = run(A.check_settlement, [bet(i) for i in range(5)], 5)
    ok(not r.errors and r.warnings, "a market that no longer answers is a warning, not a false alarm")
finally:
    S.resolve_kalshi = _saved_k

print("\ncopy: the public files stay free of the guarded phrases")
_plain = "".join(chr(c) for c in (116, 104, 101, 32, 98, 111, 116))      # built, not written
ok(A.COPY_RE.search(f"# and {_plain} reads this"), "a guarded phrase is caught")
ok(not A.COPY_RE.search("the bottom of the list"), "a word that merely starts the same way is not")
ok(A._IDENT.search("if T." + A._FN + "(q):"), "an internal function name is recognised as one")
ok(A.COPY_RE.pattern == A._COPY and "\\b" in A._COPY, "the patterns decode to word-bounded phrases")
ok(A._FN not in open("sandbox_audit.py").read().replace('"place" + "able"', ""),
   "and the audit's own source never spells the function name out")

print("\nthe live repository")
# Freshness is left to the audit step itself: a stalled tracker should fail THAT step, with
# its own message, not make this one claim the auditor is broken.
_rep = A.run(network=False)
_live = [e for e in _rep.errors if e[0] != "fresh"]
ok(not _live, "the Sandbox as committed passes every offline check" + ("" if not _live else f" — {_live[:3]}"))

print(f"\n{'FAILED: ' + str(len(FAILS)) if FAILS else 'all audit tests passed'}")
for f in FAILS:
    print("   -", f)
sys.exit(1 if FAILS else 0)
