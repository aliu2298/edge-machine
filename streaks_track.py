#!/usr/bin/env python3
"""streaks_track.py — log every streak lead when it is published, grade it once the
fixture is played, and measure whether the confluence actually carried information.

WHAT THIS MEASURES, AND WHAT IT DOES NOT
----------------------------------------
There are no odds here — the board links no price, so **profitability cannot be measured**
and nothing in this file should be read as ROI. A hit rate on its own is equally useless:
"over 2.5 landed 60%" means nothing without something to compare it against.

So the comparison is to the **population base rate** — the same outcome measured across
every played fixture in the window, flagged or not. If leads hit over-2.5 at 60% while all
fixtures do 55%, the confluence carried +5pp of information. That is a real, answerable
question that needs no prices.

**Lift is the number that matters. Hit rate alone is not evidence.** A Wilson interval on
the difference is reported so a lift that is indistinguishable from zero says so out loud —
this repo has already falsified three signals that looked fine until they were measured
([[tips-lane-no-edge]]), each time by reading a rate without asking what it should be
compared to.

Leads are recorded ONCE, when first published, and graded ONCE, after the match. A lead is
never re-scored or re-priced after the fact.

Usage:  python3 streaks_track.py [--report]
        (streaks_build.py calls record() and grade() automatically each build)
"""
import json, os, math, datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
LEDGER = os.path.join(ROOT, "data", "streak_leads.json")

# Only grade leads whose fixture is comfortably finished. ESPN can carry a fixture as
# scheduled past kickoff, and a postponed match must not silently grade as a miss.
GRADE_GRACE_DAYS = 1


# ---------------------------------------------------------------- bet evaluation
def settle_bet(bet, home, away, hg, ag):
    """True/False for a bet against a final score, or None if it cannot be judged.

    Returning None (rather than False) for an unresolvable bet matters: scoring an
    ungradeable lead as a miss is exactly the silent-loss bug that corrupted an earlier
    lane's numbers.
    """
    k = bet.get("kind")
    if k == "btts":
        return hg >= 1 and ag >= 1
    if k == "total_gte":
        return (hg + ag) >= bet["n"]
    if k == "total_lte":
        return (hg + ag) <= bet["n"]
    if k in ("team_gte", "team_eq"):
        team = bet.get("team")
        if team == home:
            gf = hg
        elif team == away:
            gf = ag
        else:
            return None                     # team name drifted — do not guess
        return gf >= bet["n"] if k == "team_gte" else gf == bet["n"]
    return None


def lead_id(l):
    """Stable across rebuilds: a lead is the same lead if it is the same claim about the
    same fixture. Deliberately excludes run lengths, which grow as games are played."""
    return f"{l['date']}|{l['home']}|{l['away']}|{l['headline']}"


# ---------------------------------------------------------------- ledger
def load():
    if os.path.exists(LEDGER):
        try:
            return json.load(open(LEDGER))
        except Exception:
            pass
    return {"leads": {}}


def save(blob):
    blob["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat(
        timespec="seconds")
    os.makedirs(os.path.dirname(LEDGER), exist_ok=True)
    with open(LEDGER, "w") as f:
        json.dump(blob, f, indent=1, sort_keys=True)


def record(leads, blob=None):
    """Log leads not seen before. Existing entries are left untouched — the snapshot is
    what was claimed at publish time, and rewriting it later would be marking our own
    homework."""
    blob = blob if blob is not None else load()
    added = 0
    for l in leads:
        lid = lead_id(l)
        if lid in blob["leads"]:
            continue
        blob["leads"][lid] = {
            "id": lid,
            "first_seen": datetime.date.today().isoformat(),
            "date": l["date"], "kickoff": l.get("kickoff"), "league": l["league"],
            "match": l["match"], "home": l["home"], "away": l["away"],
            "headline": l["headline"], "bet": l["bet"],
            "a": l["a"], "b": l["b"], "a_run": l["a_run"], "b_run": l["b_run"],
            "a_key": l["a_key"], "b_key": l["b_key"],
            "base_rate": l["base_rate"], "strength": l["strength"],
            "status": "pending",
        }
        added += 1
    return blob, added


def grade(fixtures, blob=None):
    """Settle pending leads whose fixture has a final score."""
    blob = blob if blob is not None else load()
    results = {}
    for f in fixtures:
        if f["played"] and f["home_goals"] is not None:
            results[(f["date"], f["home"], f["away"])] = (f["home_goals"], f["away_goals"])

    today = datetime.date.today()
    graded = 0
    for lid, e in blob["leads"].items():
        if e["status"] != "pending":
            continue
        key = (e["date"], e["home"], e["away"])
        if key not in results:
            # Not played yet, or the fixture moved. Flag only once it is clearly overdue,
            # so a postponement shows up instead of sitting pending forever.
            try:
                age = (today - datetime.date.fromisoformat(e["date"])).days
            except ValueError:
                continue
            if age > GRADE_GRACE_DAYS + 6:
                e["status"] = "void"
                e["note"] = "no final score found — postponed, or the fixture moved"
            continue
        hg, ag = results[key]
        got = settle_bet(e["bet"], e["home"], e["away"], hg, ag)
        if got is None:
            e["status"] = "void"
            e["note"] = "bet could not be judged from the final score"
        else:
            e["status"] = "hit" if got else "miss"
        e["final"] = f"{hg}-{ag}"
        e["graded_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat(
            timespec="seconds")
        graded += 1
    return blob, graded


# ---------------------------------------------------------------- measurement
def population_rates(fixtures):
    """How often each bet kind lands across EVERY played fixture in the window.

    This is the yardstick. Without it a hit rate is unreadable — the whole question is
    whether flagging a fixture beats not flagging it.
    """
    played = [f for f in fixtures if f["played"] and f["home_goals"] is not None]
    n = len(played)
    if not n:
        return {}
    team_games = 2 * n
    out = {
        "btts": sum(1 for f in played
                    if f["home_goals"] >= 1 and f["away_goals"] >= 1) / n,
        "total_gte:3": sum(1 for f in played
                           if f["home_goals"] + f["away_goals"] >= 3) / n,
        "total_lte:2": sum(1 for f in played
                           if f["home_goals"] + f["away_goals"] <= 2) / n,
    }
    for nn in (1, 2):
        out[f"team_gte:{nn}"] = sum(
            (1 if f["home_goals"] >= nn else 0) + (1 if f["away_goals"] >= nn else 0)
            for f in played) / team_games
    out["team_eq:0"] = sum(
        (1 if f["home_goals"] == 0 else 0) + (1 if f["away_goals"] == 0 else 0)
        for f in played) / team_games
    out["_fixtures"] = n
    return out


def bet_key(bet):
    k = bet.get("kind")
    return k if k == "btts" else f"{k}:{bet.get('n')}"


def league_baselines(fixtures):
    """league -> its own population rates. Needed because a GLOBAL baseline is confounded
    by league mix.

    Measured, not hypothetical: BTTS leads cluster in high-scoring leagues, and on the
    backtest that inflated an apparent +17.1pp BTTS lift to a real +10.7pp once each lead
    was compared against its own league. Reading the global number would have reported a
    significant edge that was really 'MLS and the Eredivisie score a lot'.
    """
    out = {}
    for lg in {f["league"] for f in fixtures if f["played"]}:
        sub = [f for f in fixtures if f["played"] and f["league"] == lg
               and f["home_goals"] is not None]
        if sub:
            out[lg] = population_rates(sub)
    return out


def mixed_baseline(per_league, kind, leagues):
    """The `kind` rate reweighted to the league mix of the leads being judged."""
    acc = weight = 0.0
    for lg in leagues:
        r = (per_league.get(lg) or {}).get(kind)
        if r is None:
            continue
        acc += r
        weight += 1
    return (acc / weight) if weight else None


def _wilson(hits, n, z=1.96):
    if not n:
        return (0.0, 0.0, 0.0)
    p = hits / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return p, c - h, c + h


def report(fixtures, blob=None):
    """Per bet type: flagged hit rate vs population base rate, with a CI on the lift."""
    blob = blob if blob is not None else load()
    pop = population_rates(fixtures)
    per_league = league_baselines(fixtures)
    settled = [e for e in blob["leads"].values() if e["status"] in ("hit", "miss")]

    by_kind = {}
    for e in settled:
        by_kind.setdefault(bet_key(e["bet"]), []).append(e)

    rows = []
    for k, entries in sorted(by_kind.items()):
        n = len(entries)
        hits = sum(1 for e in entries if e["status"] == "hit")
        p, lo, hi = _wilson(hits, n)
        # league-adjusted baseline is the one judged against; global kept for contrast
        base = mixed_baseline(per_league, k, [e["league"] for e in entries])
        if base is None:
            base = pop.get(k)
        rows.append({
            "kind": k, "n": n, "hits": hits, "rate": p, "lo": lo, "hi": hi,
            "base": base, "global_base": pop.get(k),
            "lift": (p - base) if base is not None else None,
            # A lift is only meaningful if the interval clears the baseline.
            "significant": bool(base is not None and n and (lo > base or hi < base)),
        })
    rows.sort(key=lambda r: -r["n"])

    # Backtest of the same rules over already-played fixtures. The live ledger starts
    # empty and fills slowly, so without this the track view would say nothing for weeks —
    # and the rules would go unvalidated exactly when a reader most wants to judge them.
    backtest_rows = []
    try:
        import streaks_backtest
        bt = streaks_backtest.backtest(fixtures, 3)
        by_bk = {}
        for g in bt:
            by_bk.setdefault(g["kind"], []).append(g)
        for k, gs in sorted(by_bk.items(), key=lambda kv: -len(kv[1])):
            bn = len(gs)
            bh = sum(1 for g in gs if g["hit"])
            bp, blo, bhi = _wilson(bh, bn)
            bbase = mixed_baseline(per_league, k, [g["league"] for g in gs]) or pop.get(k)
            backtest_rows.append({
                "kind": k, "n": bn, "hits": bh, "rate": bp,
                "base": bbase, "global_base": pop.get(k),
                "lift": (bp - bbase) if bbase is not None else None,
                "significant": bool(bbase is not None and (blo > bbase or bhi < bbase)),
            })
    except Exception as e:
        print(f"  (backtest skipped: {e})")

    tot_n = sum(r["n"] for r in rows)
    tot_h = sum(r["hits"] for r in rows)
    bt_n = sum(r["n"] for r in backtest_rows)
    bt_h = sum(r["hits"] for r in backtest_rows)
    return {
        "graded": tot_n, "hits": tot_h,
        "backtest_rows": backtest_rows, "backtest_n": bt_n,
        "backtest_rate": (bt_h / bt_n) if bt_n else None,
        "backtest_any_sig": any(r["significant"] for r in backtest_rows),
        "pending": sum(1 for e in blob["leads"].values() if e["status"] == "pending"),
        "void": sum(1 for e in blob["leads"].values() if e["status"] == "void"),
        "overall_rate": (tot_h / tot_n) if tot_n else None,
        "population_fixtures": pop.get("_fixtures", 0),
        "rows": rows,
        "recent": sorted([e for e in settled if e.get("graded_at")],
                         key=lambda e: e["date"], reverse=True)[:25],
    }


if __name__ == "__main__":
    import streaks_fetch
    fx = streaks_fetch.load_or_fetch()["fixtures"]
    b, added = record([], load())
    b, n = grade(fx, b)
    save(b)
    r = report(fx, b)
    print(f"ledger: {len(b['leads'])} leads | graded now: {n}")
    print(f"settled {r['graded']} | pending {r['pending']} | void {r['void']}")
    if r["graded"]:
        print(f"overall hit rate: {r['overall_rate']:.1%}")
        print(f"{'bet':16s} {'n':>4s} {'hit':>7s} {'base':>7s} {'lift':>8s}  sig")
        for row in r["rows"]:
            b_ = f"{row['base']:.1%}" if row["base"] is not None else "—"
            l_ = f"{row['lift']:+.1%}" if row["lift"] is not None else "—"
            print(f"{row['kind']:16s} {row['n']:4d} {row['rate']:7.1%} {b_:>7s} {l_:>8s}"
                  f"  {'YES' if row['significant'] else 'no'}")
    else:
        print("nothing graded yet — leads settle as their fixtures are played")
