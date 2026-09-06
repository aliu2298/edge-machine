#!/usr/bin/env python3
"""fire_track.py — log teams on a long run and measure whether the run actually continues.

THE QUESTION
------------
A 12-game BTTS run is a striking fact. It is not, on its own, a reason to expect a 13th.
This records every team on a run of FIRE_MIN+ along with the fixture that will test it,
then grades that fixture: did the run EXTEND, or BREAK?

WHY THERE IS NO "LIFT" COLUMN ANY MORE
--------------------------------------
There were three baselines tried here, and the first two were both wrong:

  1. the POPULATION rate      -> "scored in" runs extend +12.8pp, SIGNIFICANT
  2. the TEAM's own rate      ->  the same runs come out -8.7pp, SIGNIFICANT
  3. the team's rate with the run games removed -> +10.3pp

Same games, three answers, two of them flagged significant in opposite directions. (1) is
the hot-hand fallacy: teams on long scoring runs are good teams and good teams score more
anyway. (2) is circular — a team's own rate is computed over all its games INCLUDING the
run being tested, so a 20-game run stuffs 20 guaranteed successes into its own yardstick
and drags the lift down by construction. (3) over-corrects, because deleting the run
deletes only successes.

None of them can be fixed by picking a better average, because of this:

THE STREAK-SELECTION FLOOR
--------------------------
Take a team's real games and SHUFFLE THE ORDER. Runs now carry zero information by
construction. Measure anyway, and being "on a run" still predicts a next-game rate
17-39pp LOWER than the same team's off-run games. That gap is not football. It is the
arithmetic of conditioning on a run: a run ends the moment it fails, so the games that
follow one are pre-selected against.

So the reference point is not a base rate at all — it is that shuffled distribution. A
result only means something if it lands OUTSIDE the band a random schedule produces.
permutation_test() below computes it the same way on the real order and on 400 shuffles.

Measured at n=145 (Sep 2026), every streak type sits INSIDE its own null band, p 0.72-0.98:
long runs are indistinguishable from a shuffled fixture list. That is the finding.

Nothing here is a bet. The ledger is descriptive; significance comes only from the test.

Usage:  python3 fire_track.py [--report]
"""
import json, os, datetime, collections, random

import streaks_build as B
import streaks_track as T

ROOT = os.path.dirname(os.path.abspath(__file__))
LEDGER = os.path.join(ROOT, "data", "fire_runs.json")

# Only grade a run against a fixture we can actually resolve; a postponement must not
# count as a break.
VOID_AFTER_DAYS = 7

# Shuffles used to build the streak-selection floor. Seeded, so CI and the Mac agree —
# an unseeded null would make "significant" flicker between runs of the same data.
PERMUTATIONS = 400
SEED = 20260906


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


def hit_series(fixtures):
    """team -> {streak key: [1/0, ...]} in date order, competitive games only.

    One boolean per game per predicate, computed once. The permutation below shuffles
    these lists rather than re-deriving form 400 times over.
    """
    games = collections.defaultdict(list)
    for f in sorted(fixtures, key=lambda x: x["date"]):
        if not f.get("played") or f.get("home_goals") is None:
            continue
        if not f.get("competitive", True):
            continue                     # friendlies would shift the yardstick
        for team, gf, ga in ((f["home"], f["home_goals"], f["away_goals"]),
                             (f["away"], f["away_goals"], f["home_goals"])):
            games[team].append((gf, ga))
    return {t: {key: [1 if pred(gf, ga) else 0 for gf, ga in gl]
                for key, _l, _s, pred in B.STREAKS}
            for t, gl in games.items()}


def _split(hits, fire_min):
    """Walk one team's games; split each into on-run / off-run by PRIOR games only.

    Returns (on_hits, on_n, off_hits, off_n). The run length is carried forward as the
    walk goes, so the classification of game i can never see game i's own result.

    ⚠️ THE FIRST `fire_min` GAMES ARE DISCARDED, AND THAT CHOICE IS THE WHOLE RESULT.
    A team cannot be on a run before it has played fire_min games, so scoring those games
    forces every one of them into the off-run control arm. That is not neutral: measured
    here, a team's opening 8 games hit 4.3pp LOWER than its later ones ("scored in":
    73.9% vs 78.2%). In the real chronological order all of that weak stretch lands in
    the control; under a shuffle it is scattered across both arms. The control is
    therefore depressed in the observation and not in the null, and the difference is
    pure calendar position.

    It is worth exactly this much: counting those games flags "scored in", "conceded in"
    and "over 1.5" as SIGNIFICANT (p 0.000-0.050). Discarding them leaves only "scored
    in" at a marginal p=0.033 — which, across six streak types, is nothing. Every game
    used here has a full fire_min-game history behind it, in both arms.
    """
    on_h = on_n = off_h = off_n = 0
    run = 0
    for i, v in enumerate(hits):
        if i >= fire_min:                # warm-up: no run was reachable yet
            if run >= fire_min:
                on_n += 1
                on_h += v
            else:
                off_n += 1
                off_h += v
        run = run + 1 if v else 0
    return on_h, on_n, off_h, off_n


def paired_diff(series, key, fire_min):
    """Mean over teams of (on-run rate − off-run rate) — each team its own control.

    Pairing within team is what cancels team quality: the same side supplies both arms,
    so "good teams are good" cannot show up as a lift. Teams that never go on a run, or
    that are always on one, contribute no pair and are skipped.

    ⚠️ THERE IS DELIBERATELY NO `teams=` FILTER. Narrowing this to the sides in the
    ledger looks like the obvious way to make the test answer the ledger's question, and
    it is wrong: a team reaches the ledger only by going on a REAL run, so it always
    contributes an on-run arm in the real order but frequently none in a shuffle. That
    culls ~25% of teams from the null and none from the observation, and the resulting
    mismatch alone flipped three streak types to "SIGNIFICANT" (p 0.005-0.015). Measured:
    ledger-only gave 36 teams real vs 29 shuffled; unfiltered gives 57 vs 56.
    """
    diffs, on_tot, off_tot = [], 0, 0
    for team, per_key in series.items():
        hits = per_key.get(key)
        if not hits:
            continue
        on_h, on_n, off_h, off_n = _split(hits, fire_min)
        if on_n and off_n:
            diffs.append(on_h / on_n - off_h / off_n)
            on_tot += on_n
            off_tot += off_n
    if not diffs:
        return None
    return {"diff": sum(diffs) / len(diffs), "teams": len(diffs),
            "on_n": on_tot, "off_n": off_tot}


def permutation_test(series, key, fire_min, iters=PERMUTATIONS, seed=SEED):
    """Compare the real fixture order against `iters` shuffles of each team's own games.

    A shuffle keeps every game, every scoreline and every team identical and destroys
    ONLY the order — so any run in a shuffled series is chance by construction. The band
    this returns is therefore what "no signal" actually looks like, and it is nowhere
    near zero: conditioning on a run selects against the games that follow it.
    """
    obs = paired_diff(series, key, fire_min)
    if obs is None:
        return None
    rng = random.Random(seed)
    null = []
    for _ in range(iters):
        shuffled = {}
        for team, per_key in series.items():
            hits = per_key.get(key)
            if hits:
                shuffled[team] = {key: rng.sample(hits, len(hits))}
        s = paired_diff(shuffled, key, fire_min)
        if s is not None:
            null.append(s["diff"])
    if len(null) < 20:
        return None
    null.sort()
    n = len(null)
    below = sum(1 for x in null if x <= obs["diff"]) / n
    above = sum(1 for x in null if x >= obs["diff"]) / n
    obs.update({
        "null_lo": null[int(0.025 * n)], "null_hi": null[min(n - 1, int(0.975 * n))],
        "null_mid": null[n // 2],
        "p": min(1.0, 2 * min(below, above)),
        "outside_band": None,            # filled by report(), which knows the family size
    })
    obs["outside_band"] = obs["diff"] < obs["null_lo"] or obs["diff"] > obs["null_hi"]
    return obs


def report(fixtures, blob=None, iters=PERMUTATIONS):
    """Two separate things, deliberately not mixed.

    `rows` is the LEDGER: what was published and how it settled. It carries no lift and
    no significance, because a ledger of runs has no uncontaminated control inside it.

    `test` is the MEASUREMENT: the paired within-team comparison against the shuffled
    null, computed identically on real and permuted order. Significance lives only here.
    """
    blob = load() if blob is None else blob
    decided = [r for r in blob["runs"].values() if r["status"] in ("extended", "broke")]

    by_key = collections.defaultdict(list)
    for r in decided:
        by_key[r["key"]].append(r)

    series = hit_series(fixtures)

    rows, test = [], []
    for key, rs in sorted(by_key.items(), key=lambda kv: -len(kv[1])):
        n = len(rs)
        ext = sum(1 for r in rs if r["status"] == "extended")
        p, lo, hi = T._wilson(ext, n)
        label = B.STREAK_BY_KEY[key][1]
        rows.append({"key": key, "label": label, "n": n, "extended": ext,
                     "rate": p, "ci_lo": lo, "ci_hi": hi})
        t = permutation_test(series, key, B.FIRE_MIN, iters=iters)
        if t:
            t.update({"key": key, "label": label})
            test.append(t)

    # Six streak types are tested at once, so an uncorrected p is the wrong threshold:
    # at p<0.05 each, one false flag per run is the EXPECTED outcome, not a surprise.
    # Bonferroni is conservative, which is the right way to be wrong here — this repo has
    # already published three confident findings that measurement later erased.
    fam = len(test) or 1
    for t in test:
        t["p_adj"] = min(1.0, t["p"] * fam)
        t["family"] = fam
        t["significant"] = bool(t["outside_band"] and t["p_adj"] < 0.05)

    n = len(decided)
    ext = sum(1 for r in decided if r["status"] == "extended")
    return {
        "graded": n, "extended": ext,
        "rate": (ext / n) if n else None,
        "pending": sum(1 for r in blob["runs"].values() if r["status"] == "pending"),
        "rows": rows, "test": test,
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
    if not rep["graded"]:
        print("nothing graded yet — runs settle as their next fixtures are played")
        raise SystemExit

    print(f"\nLEDGER — what was published and how it settled (no lift: see module docstring)")
    print(f"extension rate: {rep['extended']}/{rep['graded']} = {rep['rate']:.1%}\n")
    print(f"{'streak':22s} {'n':>4s} {'extended':>9s}")
    for r in rep["rows"]:
        print(f"{r['label']:22s} {r['n']:4d} {r['rate']:9.1%}")

    print(f"\nTEST — on-run vs off-run within the same team, vs {PERMUTATIONS} shuffles")
    print(f"{'streak':22s} {'teams':>6s} {'on':>5s} {'off':>5s} {'diff':>9s} "
          f"{'shuffled 95%':>20s} {'p':>6s} {'p adj':>6s}")
    for t in rep["test"]:
        band = f"[{t['null_lo']*100:+.1f},{t['null_hi']*100:+.1f}]pp"
        print(f"{t['label']:22s} {t['teams']:6d} {t['on_n']:5d} {t['off_n']:5d} "
              f"{t['diff']*100:+8.1f}pp {band:>20s} {t['p']:6.3f} {t['p_adj']:6.3f}"
              f"  {'SIG' if t['significant'] else ''}")
    print(f"\np adj = Bonferroni over the {rep['test'][0]['family'] if rep['test'] else 0}"
          f" streak types tested together.")
    print("A diff inside the shuffled band is NOT a negative result — it is no result.")
