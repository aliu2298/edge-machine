#!/usr/bin/env python3
"""fire_track.py — log teams on a long run and measure whether the run actually continues.

THE QUESTION
------------
A 12-game BTTS run is a striking fact. It is not, on its own, a reason to expect a 13th.
This records every team on a run of FIRE_MIN+ along with the fixture that will test it,
then grades that fixture: did the run EXTEND, or BREAK?

WHAT IT IS COMPARED AGAINST — AND THE TRAP IN GETTING THAT WRONG
----------------------------------------------------------------
Against the TEAM'S OWN rate, never the population's. This distinction is the whole result:

    long "scored in" runs, extension rate 88.8% (n=178)
      vs population base 75.9%  ->  +12.8pp, statistically SIGNIFICANT
      vs the team's own  91.9%  ->   -3.1pp, not significant

Both numbers describe the same games. The first is an artifact — teams on long scoring
runs are good teams, and good teams score more than average anyway — and reporting it
would be publishing the hot-hand fallacy as a finding.

Measured over history, no streak type extends faster than the team's own baseline. A long
streak is the most seductive pattern on the board and also pure survivorship: of course
the side still on a 12-game run is the one whose run has not broken yet.

Nothing here is a bet. Extension rate is measured against the base rate, not against odds.

Usage:  python3 fire_track.py [--report]
"""
import json, os, datetime, collections

import streaks_build as B
import streaks_track as T

ROOT = os.path.dirname(os.path.abspath(__file__))
LEDGER = os.path.join(ROOT, "data", "fire_runs.json")

# Only grade a run against a fixture we can actually resolve; a postponement must not
# count as a break.
VOID_AFTER_DAYS = 7


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc)


def run_id(team, key, next_fx):
    """One record per (team, streak, fixture-being-tested)."""
    return f"{team}|{key}|{next_fx}"


def load(path=LEDGER):
    if os.path.exists(path):
        try:
            blob = json.load(open(path))
            blob.setdefault("runs", {})
            return blob
        except Exception:
            pass
    return {"runs": {}}


def save(blob, path=LEDGER):
    blob["updated_at"] = utc_now().isoformat(timespec="seconds")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(blob, f, indent=1, sort_keys=True)


def record(fire, blob=None, now=None):
    """Log each on-fire run against the fixture that will test it."""
    blob = load() if blob is None else blob
    now = now or utc_now()
    added = 0
    for t in fire:
        nxt = t.get("next")
        if not nxt or not nxt.get("date"):
            continue                      # nothing scheduled to test the run
        fx = f"{nxt['date']}|{t['team']}|{nxt['opp']}"
        for r in t["runs"]:
            rid = run_id(t["team"], r["key"], fx)
            if rid in blob["runs"]:
                continue
            blob["runs"][rid] = {
                "id": rid, "team": t["team"], "league": t["league"],
                "key": r["key"], "label": r["label"], "length": r["n"], "rate": r["rate"],
                "logged_at": now.isoformat(timespec="seconds"),
                "test_date": nxt["date"], "opp": nxt["opp"],
                "home": nxt.get("home", True), "kickoff": nxt.get("kickoff"),
                "status": "pending",
            }
            added += 1
    return blob, added


def grade(fixtures, blob=None, now=None):
    """Did the run extend or break in its test fixture?"""
    blob = load() if blob is None else blob
    now = now or utc_now()

    # (date, team) -> that team's goals for/against in the fixture
    played = {}
    for f in fixtures:
        if not f.get("played") or f.get("home_goals") is None:
            continue
        played[(f["date"], f["home"])] = (f["home_goals"], f["away_goals"])
        played[(f["date"], f["away"])] = (f["away_goals"], f["home_goals"])

    n = 0
    for r in blob["runs"].values():
        if r["status"] != "pending":
            continue
        key = (r["test_date"], r["team"])
        if key not in played:
            try:
                age = (now.date() - datetime.date.fromisoformat(r["test_date"])).days
            except ValueError:
                continue
            if age > VOID_AFTER_DAYS:
                r["status"] = "void"
                r["note"] = "test fixture never resolved"
                n += 1
            continue
        gf, ga = played[key]
        pred = B.STREAK_BY_KEY[r["key"]][3]
        r["status"] = "extended" if pred(gf, ga) else "broke"
        r["result"] = f"{gf}-{ga}"
        r["graded_at"] = now.isoformat(timespec="seconds")
        n += 1
    return blob, n


def team_rates(fixtures):
    """Each TEAM's own rate for each predicate — the only valid yardstick here.

    ⚠️ MEASURED, NOT ASSUMED. Comparing extensions against the POPULATION rate says a
    long "scored in" run extends at 88.8% against a 75.9% base: +12.8pp and statistically
    significant. That number is an artifact. Teams on long scoring runs are good teams,
    and good teams score more than average anyway. Against each team's OWN rate (91.9%)
    the same runs extend at 88.8% — a lift of **−3.1pp**, not significant.

    The entire apparent effect was "good teams are good". Use the team's own rate, or the
    tab reports the hot-hand fallacy as a finding.
    """
    tot = collections.defaultdict(lambda: collections.defaultdict(list))
    for f in fixtures:
        if not f.get("played") or f.get("home_goals") is None:
            continue
        if not f.get("competitive", True):
            continue                     # friendlies would shift the yardstick
        for team, gf, ga in ((f["home"], f["home_goals"], f["away_goals"]),
                             (f["away"], f["away_goals"], f["home_goals"])):
            for key, _l, _s, pred in B.STREAKS:
                tot[team][key].append(1 if pred(gf, ga) else 0)
    return {t: {k: (sum(v) / len(v) if v else None) for k, v in d.items()}
            for t, d in tot.items()}


def report(fixtures, blob=None):
    blob = load() if blob is None else blob
    rates = team_rates(fixtures)
    decided = [r for r in blob["runs"].values() if r["status"] in ("extended", "broke")]

    by_key = collections.defaultdict(list)
    for r in decided:
        by_key[r["key"]].append(r)

    rows = []
    for key, rs in sorted(by_key.items(), key=lambda kv: -len(kv[1])):
        n = len(rs)
        ext = sum(1 for r in rs if r["status"] == "extended")
        p, lo, hi = T._wilson(ext, n)
        # baseline is each run's OWN team rate — see team_rates() for why the
        # population rate produces a false +12.8pp here
        vals = [rates.get(r["team"], {}).get(key) for r in rs]
        vals = [v for v in vals if v is not None]
        base = (sum(vals) / len(vals)) if vals else None
        rows.append({
            "key": key, "label": B.STREAK_BY_KEY[key][1], "n": n, "extended": ext,
            "rate": p, "base": base,
            "lift": (p - base) if base is not None else None,
            "significant": bool(base is not None and (lo > base or hi < base)),
        })

    n = len(decided)
    ext = sum(1 for r in decided if r["status"] == "extended")
    return {
        "graded": n, "extended": ext,
        "rate": (ext / n) if n else None,
        "pending": sum(1 for r in blob["runs"].values() if r["status"] == "pending"),
        "rows": rows,
        "history": sorted(decided, key=lambda r: r["test_date"], reverse=True)[:40],
    }


if __name__ == "__main__":
    import streaks_fetch
    fx = streaks_fetch.load_or_fetch()["fixtures"]
    by_team = B.team_games(fx)
    lg, nxt = B.team_lookups(by_team, fx)
    fire = B.fire_rows(by_team, fx, lg, nxt)
    b, added = record(fire)
    b, graded = grade(fx, b)
    save(b)
    rep = report(fx, b)
    print(f"fire runs: {len(b['runs'])} logged (+{added}), graded now {graded}, "
          f"{rep['pending']} pending")
    if rep["graded"]:
        print(f"extension rate: {rep['extended']}/{rep['graded']} = {rep['rate']:.1%}\n")
        print(f"{'streak':22s} {'n':>4s} {'extended':>9s} {'own-team base':>14s} {'lift':>9s}")
        for r in rep["rows"]:
            base = f"{r['base']:.1%}" if r["base"] is not None else "—"
            lift = f"{r['lift']*100:+.1f}pp" if r["lift"] is not None else "—"
            print(f"{r['label']:22s} {r['n']:4d} {r['rate']:9.1%} {base:>12s} {lift:>9s}"
                  f"  {'SIG' if r['significant'] else ''}")
    else:
        print("nothing graded yet — runs settle as their next fixtures are played")
