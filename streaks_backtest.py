#!/usr/bin/env python3
"""streaks_backtest.py — walk-forward test of the streak-confluence idea on fixtures that
have already been played.

WHY THIS EXISTS
---------------
The live ledger only settles as new fixtures are played, so without a backtest the whole
idea is unfalsifiable for weeks — and the grader itself would go unverified. This replays
the same lead-finding logic over history and grades it against known results, which both
proves the machinery works and gives an immediate read on whether the confluence carries
any information at all.

NO LOOKAHEAD
------------
For a fixture on date D, each side's form is computed from games strictly BEFORE D. That is
the whole discipline of a walk-forward test: at no point may a fixture's own result, or any
later result, inform the lead that is being graded on it.

WHAT IT MEASURES
----------------
There are no odds, so this is NOT profitability. It is: do flagged fixtures hit the outcome
more often than the population of all fixtures does? Lift, with a 95% interval — a lift
whose interval spans zero is not a finding.

Usage:  python3 streaks_backtest.py [--min-run N]
"""
import sys, math, collections, datetime

import streaks_fetch
from streaks_build import (STREAKS, STREAK_BY_KEY, PAIRINGS, FORM_GAMES,
                           MIN_PLAYED, run_length)
from streaks_track import settle_bet, bet_key, population_rates, _wilson


def build_history(fixtures):
    """team -> [games ascending by date]. Ascending so a prefix is 'everything before D'."""
    by_team = collections.defaultdict(list)
    for f in fixtures:
        if not f["played"] or f["home_goals"] is None:
            continue
        by_team[f["home"]].append({"date": f["date"], "opp": f["away"], "home": True,
                                   "gf": f["home_goals"], "ga": f["away_goals"]})
        by_team[f["away"]].append({"date": f["date"], "opp": f["home"], "home": False,
                                   "gf": f["away_goals"], "ga": f["home_goals"]})
    for t in by_team:
        by_team[t].sort(key=lambda g: g["date"])
    return by_team


def runs_before(games, date, min_run):
    """Runs a team carried into `date`, using only games strictly before it."""
    prior = [g for g in games if g["date"] < date]
    if len(prior) < MIN_PLAYED:
        return None
    recent = list(reversed(prior))          # newest first, as run_length expects
    out = {}
    for key, _label, _side, pred in STREAKS:
        r = run_length(recent, pred)
        if r >= min_run:
            out[key] = r
    return out


def backtest(fixtures, min_run):
    hist = build_history(fixtures)
    played = sorted([f for f in fixtures if f["played"] and f["home_goals"] is not None],
                    key=lambda f: f["date"])

    graded, seen = [], set()
    for f in played:
        d, home, away = f["date"], f["home"], f["away"]
        rh = runs_before(hist.get(home, []), d, min_run)
        ra_ = runs_before(hist.get(away, []), d, min_run)
        if rh is None or ra_ is None:
            continue
        for a_key, b_key, headline, _why, bet in PAIRINGS:
            for (a, b, sa, sb) in ((home, away, rh, ra_), (away, home, ra_, rh)):
                na, nb = sa.get(a_key, 0), sb.get(b_key, 0)
                if na < min_run or nb < min_run:
                    continue
                # same dedup as the live board: symmetric pairings carry no orientation
                key = ((d, home, away, a_key) if a_key == b_key
                       else (d, home, away, a, a_key))
                if key in seen:
                    continue
                seen.add(key)
                resolved = dict(bet, team=(a if bet.get("subject") == "a" else b)) \
                    if bet.get("subject") else dict(bet)
                got = settle_bet(resolved, home, away, f["home_goals"], f["away_goals"])
                if got is None:
                    continue
                graded.append({"kind": bet_key(resolved), "hit": got,
                               "league": f["league"], "date": d,
                               "strength": na + nb})
    return graded


def league_adjusted_baseline(fixtures, rows):
    """Baseline matched to the LEAGUE MIX of the flagged leads.

    A global baseline is confounded: BTTS leads cluster in high-scoring leagues, so a
    naive comparison credits the streak for what is really MLS being MLS. This reweights
    each league's own rate by how often that league appears among the flagged leads, which
    is the comparison that isolates the signal from the schedule.
    """
    per_league = {}
    for lg in {f["league"] for f in fixtures if f["played"]}:
        sub = [f for f in fixtures if f["played"] and f["league"] == lg
               and f["home_goals"] is not None]
        if sub:
            per_league[lg] = population_rates(sub)
    mix = collections.Counter(r["league"] for r in rows)
    total = sum(mix.values())
    if not total:
        return None
    acc, weight = 0.0, 0.0
    for lg, cnt in mix.items():
        rate = (per_league.get(lg) or {}).get(rows[0]["kind"])
        if rate is None:
            continue
        acc += rate * cnt
        weight += cnt
    return (acc / weight) if weight else None


def main():
    min_run = 3
    if "--min-run" in sys.argv:
        min_run = int(sys.argv[sys.argv.index("--min-run") + 1])

    fixtures = streaks_fetch.load_or_fetch()["fixtures"]
    pop = population_rates(fixtures)
    graded = backtest(fixtures, min_run)

    print(f"\nWALK-FORWARD BACKTEST (min_run={min_run}, form window={FORM_GAMES})")
    print(f"population: {pop['_fixtures']} played fixtures")
    print(f"flagged and graded: {len(graded)} leads\n")
    if not graded:
        print("no leads generated — nothing to measure")
        return

    by_kind = collections.defaultdict(list)
    for g in graded:
        by_kind[g["kind"]].append(g)

    print(f"{'bet':16s} {'n':>5s} {'hit rate':>10s} {'global':>8s} {'lg-adj':>8s} "
          f"{'lift':>8s} {'95% CI on rate':>18s}  verdict")
    print("-" * 96)
    any_sig = False
    for kind, rows in sorted(by_kind.items(), key=lambda kv: -len(kv[1])):
        n = len(rows)
        hits = sum(1 for r in rows if r["hit"])
        p, lo, hi = _wilson(hits, n)
        gbase = pop.get(kind)
        if gbase is None:
            continue
        # league-adjusted is the baseline that counts; global is shown for contrast
        base = league_adjusted_baseline(fixtures, rows)
        base = gbase if base is None else base
        lift = (p - base) * 100
        sig = lo > base or hi < base
        any_sig |= sig
        print(f"{kind:16s} {n:5d} {p:9.1%} {gbase:8.1%} {base:8.1%} "
              f"{lift:+7.1f}pp "
              f"{'[' + format(lo, '.1%') + ', ' + format(hi, '.1%') + ']':>18s}  "
              f"{'SIGNIFICANT' if sig else 'not sig'}")

    n = len(graded)
    hits = sum(1 for g in graded if g["hit"])
    print(f"\noverall: {hits}/{n} = {hits/n:.1%}")
    if not any_sig:
        print("\nNo bet type's interval clears its baseline. On this sample the confluence\n"
              "is not distinguishable from the population — i.e. no measurable edge yet.")
    else:
        print("\nAt least one bet type clears its baseline. Treat with care: several types\n"
              "are tested at once, so some separation is expected by chance alone.")


if __name__ == "__main__":
    main()
