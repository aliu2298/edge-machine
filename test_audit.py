#!/usr/bin/env python3
"""test_audit.py — the audit catches what it claims to. No network.

An audit that has only ever passed proves nothing, so every check here is fed a record with
one planted fault and must fire, and the same record with the fault removed must not.
"""
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

import sandbox_audit as A
import sandbox_sources as S
import sandbox_track as T

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

print("\nproduction: only a pair published without being listed is a fault")
import sandbox_track as _T
_saved_ov = dict(_T.PAIR_OVERRIDES)
_st = {"pairs": {"a|x": {"stage": "production"}}}
try:
    _T.PAIR_OVERRIDES.clear(); _T.PAIR_OVERRIDES.update({"a|x": {}, "b|y": {}})
    _rp = A.Report()
    A.check_production({"quotes": []}, _st, _rp)
    ok(not [m for c, m in _rp.errors if "off the hand-kept list" in m] and
       any("not in Production" in m for c, m in _rp.warnings),
       "listed but not yet promoted, or demoted by the net: a warning, never an error")
    _T.PAIR_OVERRIDES.clear(); _T.PAIR_OVERRIDES.update({"b|y": {}})
    _rp = A.Report()
    A.check_production({"quotes": []}, _st, _rp)
    ok(any("off the hand-kept list" in m for c, m in _rp.errors),
       "in Production but taken off the list: an error — it is still being published")
finally:
    _T.PAIR_OVERRIDES.clear(); _T.PAIR_OVERRIDES.update(_saved_ov)

print("\ncombos: a basket must agree with its own legs")


def _leg_q(mid, res):
    return dict(id=f"t:{mid}", source="tennis_fav_band", sport="tennis", market_id=mid, result=res,
                bet=False, status="graded")


def _basket(i, legs, result, status):
    return dict(id=f"c{i}", source="tennis_combo2", sport="tennis_combo", market_id=f"combo2:2026-09-22:{i}",
                legs=[dict(market_id=m, pick="a") for m in legs], result=result, status=status, bet=False)


_ok = [_leg_q("L1", "a"), _leg_q("L2", "a"), _leg_q("L3", "b"), _leg_q("L4", "a")]
_rc = A.Report(); A.check_combos({"quotes": _ok + [_basket(1, ["L1", "L2"], "a", "won"),
                                                   _basket(2, ["L3", "L4"], "b", "lost")]}, _rc)
ok(not _rc.errors, "baskets settled as their legs say pass")
_rc = A.Report(); A.check_combos({"quotes": _ok + [_basket(1, ["L1", "L3"], "a", "won")]}, _rc)
ok(errs(_rc, "combos"), "a basket marked won with a losing leg is caught")
_rc = A.Report(); A.check_combos({"quotes": _ok + [_basket(1, ["L1", "L2"], "a", "won"),
                                                   _basket(2, ["L2", "L4"], "a", "won")]}, _rc)
ok(errs(_rc, "combos"), "a leg sitting in two baskets of one size is caught: they are not independent")

def settlement(quotes, sample, prior=None):
    """check_settlement against a private watch file, so the test never touches the repo's."""
    fd, path = tempfile.mkstemp(prefix="settle-", suffix=".json")
    os.close(fd)
    if prior:
        T.save_settlement_watch(prior, path)
    else:
        os.remove(path)
    saved = A.MISMATCHES
    A.MISMATCHES = path
    try:
        rep = A.Report()
        A.check_settlement({"quotes": quotes, "meta": {}}, rep, sample)
        return rep, T.load_settlement_watch(path)
    finally:
        A.MISMATCHES = saved
        try:
            os.remove(path)
        except OSError:
            pass


print("\nsettlement: the stored result must be the venue's")
_saved_k = S.resolve_kalshi
try:
    S.resolve_kalshi = lambda mid: "a"
    r, watched = settlement([bet(i) for i in range(5)], 5)
    ok(not r.errors, "results that match the venue pass")
    ok(not watched, "a match is not remembered")
    S.resolve_kalshi = lambda mid: "b"
    r, watched = settlement([bet(i) for i in range(5)], 5)
    ok(errs(r, "settlement"), "a stored win the venue calls a loss is caught")
    ok(len(watched) == 5, "each disagreed market is remembered")
    S.resolve_kalshi = lambda mid: None
    r, watched = settlement([bet(i) for i in range(5)], 5)
    ok(not r.errors and r.warnings, "a market that no longer answers is a warning, not a false alarm")
    ok(not watched, "a venue that never answered is not a mismatch to remember")
finally:
    S.resolve_kalshi = _saved_k

print("\nsettlement: a remembered mismatch keeps failing until the ledger matches")
_prior = [{"venue": "kalshi", "market_id": "stuck", "stored": "a", "venue_result": "b",
           "quote_id": "src:stuck"}]
_stuck = bet(0, market_id="stuck", id="src:stuck")
_others = [bet(i) for i in range(1, 30)]
try:
    S.resolve_kalshi = lambda mid: "b" if mid == "stuck" else "a"
    r, watched = settlement([_stuck] + _others, 0, prior=_prior)
    ok(errs(r, "settlement"), "a remembered mismatch fails even when the sample is empty")
    ok(any(w.get("market_id") == "stuck" for w in watched),
       "it stays remembered while the venue still disagrees")

    S.resolve_kalshi = lambda mid: None
    r, watched = settlement([_stuck] + _others, 0, prior=_prior)
    ok(errs(r, "settlement"), "a remembered mismatch is not cleared when the venue does not answer")
    ok(any(w.get("market_id") == "stuck" for w in watched),
       "silence leaves the market on the watch list")

    _fixed = bet(0, market_id="stuck", id="src:stuck", won=False)
    _self = dict(id="self:stuck", source="polymarket_us", sport="mlb", market_id="stuck",
                 venue="kalshi", bet=False, status="graded", result="a", pnl=0.0)
    S.resolve_kalshi = lambda mid: "b" if mid == "stuck" else "a"
    r, watched = settlement([_fixed, _self] + _others, 0, prior=_prior)
    ok(errs(r, "settlement"), "a self-quote still storing the old side keeps the mismatch open")
    ok(any(w.get("market_id") == "stuck" for w in watched),
       "and the market stays remembered until that quote is corrected too")

    _self["result"] = "b"
    r, watched = settlement([_fixed, _self] + _others, 0, prior=_prior)
    ok(not errs(r, "settlement"), "once the ledger matches the venue, the remembered mismatch passes")
    ok(not any(w.get("market_id") == "stuck" for w in watched),
       "and the market is dropped from the watch list")
finally:
    S.resolve_kalshi = _saved_k

print("\nwatch list: a rewrite replaces the file instead of truncating it")
_wd = tempfile.mkdtemp(prefix="watch-")
_wp = os.path.join(_wd, "settlement_mismatches.json")
T.save_settlement_watch(
    [{"venue": "kalshi", "market_id": "m1", "stored": "a", "venue_result": "b"}], _wp)
_on_disk = json.load(open(_wp))
ok(_on_disk == {"markets": [{"market_id": "m1", "stored": "a", "venue": "kalshi",
                             "venue_result": "b"}]},
   "the watch list is stored as {markets: [...]} and nothing else")
ok(not any(n.startswith(".settlement-watch-") for n in os.listdir(_wd)),
   "the temp file is gone after a successful write")
_before = open(_wp).read()
_real_replace = os.replace


def _replace_fails(src, dst):
    raise OSError("replaced nothing")


os.replace = _replace_fails
try:
    _raised = False
    try:
        T.save_settlement_watch(
            [{"venue": "kalshi", "market_id": "m2", "stored": "b", "venue_result": "a"}], _wp)
    except OSError:
        _raised = True
finally:
    os.replace = _real_replace
ok(_raised, "a failed replace does not report the watch list as saved")
ok(open(_wp).read() == _before, "a failed replace leaves the previous watch list intact")
ok(not any(n.startswith(".settlement-watch-") for n in os.listdir(_wd)),
   "a failed replace removes its temp file")

print("\ncopy: the public files stay free of the guarded phrases")
_plain = "".join(chr(c) for c in (116, 104, 101, 32, 98, 111, 116))      # built, not written
ok(A.COPY_RE.search(f"# and {_plain} reads this"), "a guarded phrase is caught")
ok(not A.COPY_RE.search("the bottom of the list"), "a word that merely starts the same way is not")
_w = _plain.split(" ")
ok(A.COPY_RE.search(f"# ends with {_w[0]}\n    # {_w[1]} starts the next line"),
   "a phrase wrapped across two comment lines is still caught")
ok(A._IDENT.search("if T." + A._FN + "(q):"), "an internal function name is recognised as one")
ok(A.COPY_RE.pattern == A._COPY.replace(" ", r"[\s#/*]+") and "\\b" in A._COPY,
   "the patterns decode to word-bounded phrases, spaced to survive a line wrap")
ok(A._FN not in open("sandbox_audit.py").read().replace('"place" + "able"', ""),
   "and the audit's own source never spells the function name out")

print("\nmilestones: a watch counts only what settled since its own date")
import sandbox_milestones as M
_mw = dict(key="t", source="src", sport="mlb", since="2026-09-10", settled=3, title="t", why="w")
_md = {"quotes": [bet(i, logged="2026-09-12T00:00:00+00:00") for i in range(2)]
                 + [bet(9, logged="2026-09-01T00:00:00+00:00")], "meta": {}}
eq_ = M.status(_md, _mw)[0]
ok(eq_ == 2, "bets logged before the watch began do not count toward it")
ok(M.status(_md, dict(_mw, since="2026-08-01"))[0] == 3, "and every settled one after it does")
ok(M.WATCHES and all(w["settled"] > 0 and w["since"] for w in M.WATCHES), "every watch names a size and a start")

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
