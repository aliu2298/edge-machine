#!/usr/bin/env python3
"""slate.py — keep three auto-drawn picks live, grade them, refill the slot.

THE LOOP
--------
    draw -> live (counting down) -> kickoff -> graded (hit/miss/void) -> slot reopens

Picks come from the streak leads the board already publishes, so nothing is entered by
hand. Slots refill INDIVIDUALLY as each settles rather than waiting for all three: batch
replacement stalls for days whenever one pick lands on a Saturday fixture and another on a
Wednesday one, and an empty board reads as broken.

A PICK IS LOCKED AT DRAW TIME
-----------------------------
Run lengths, rarity, the form sequence and the bet text are all snapshotted when the pick
is drawn, and never recomputed. The runs behind a lead keep moving as teams play, so a
"live" recompute would quietly rewrite the claim we are about to be judged on. The record
has to show what was actually claimed, not a tidier version of it discovered later.

WHAT THE SELECTION RULES ARE FOR
--------------------------------
Ranking is rarest-first, which is what the streaks board already argues for: an unusual
confluence beats a long-but-ordinary one. Two exclusions do real work on top of that —

  * ONE PICK PER FIXTURE. Without it the top three on a typical night were Toronto/NYCFC
    BTTS plus Atlanta/Charlotte twice (Over 2.5 AND BTTS on the same match) — two
    correlated bets presented as two picks.
  * ONE TEAM PER LIVE SLATE. A side on a hot run anchors leads in several fixtures, so
    picking two of them doubles the exposure to one team's form.

The window starts at 24h and widens until three qualify. That is not a nicety: days +3
through +6 routinely hold ZERO leads because the European leagues play weekends, so a hard
24h rule would leave the board empty for half of every week.

Nothing here places a bet, and no edge is claimed — see the measurement note in
streaks_track.py. What the fixed cadence buys is a clean, uncorrelated, continuously
accumulating sample, which the manual lane never produced.

Usage:  python3 slate.py [--report]
"""
import json, os, datetime

import streaks_track as T

ROOT = os.path.dirname(os.path.abspath(__file__))
LEDGER = os.path.join(ROOT, "data", "slate.json")
LEADS_IN = os.path.join(ROOT, "data", "streaks.json")

SLATE_SIZE = 3
# Widening horizons, in days. The first that yields a full slate wins.
WINDOWS = (1, 2, 3, 5, 7, 14)
# Match a fixture no later than this after kickoff before calling it void; ESPN can carry a
# postponed game as scheduled indefinitely, and a postponement must not grade as a miss.
VOID_AFTER_DAYS = 7


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc)


def _dt(iso):
    if not iso:
        return None
    try:
        return datetime.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def pick_id(lead):
    """Stable across rebuilds: same claim about the same fixture is the same pick.
    Excludes run lengths, which grow as teams play."""
    return f"{lead['date']}|{lead['home']}|{lead['away']}|{lead['headline']}"


def fixture_key(x):
    return (x["date"], x["home"], x["away"])


# ---------------------------------------------------------------- ledger
def load(path=LEDGER):
    if os.path.exists(path):
        try:
            blob = json.load(open(path))
            blob.setdefault("picks", {})
            return blob
        except Exception:
            pass
    return {"picks": {}}


def save(blob, path=LEDGER):
    blob["updated_at"] = utc_now().isoformat(timespec="seconds")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(blob, f, indent=1, sort_keys=True)


def live_picks(blob):
    """Active picks, soonest kickoff first."""
    return sorted((p for p in blob["picks"].values() if p["status"] == "live"),
                  key=lambda p: p.get("kickoff") or p["date"])


def settled_picks(blob):
    return [p for p in blob["picks"].values() if p["status"] in ("hit", "miss", "void")]


# ---------------------------------------------------------------- draw
def eligible(leads, blob, now):
    """Leads that could still be drawn: in the future, and on a fixture never drawn before.

    Excluding fixtures already in the ledger matters because a lead persists across builds
    until its match is played — without it the same fixture would be drawn again on the
    next run, every run, until kickoff.
    """
    seen_fixtures = {fixture_key(p) for p in blob["picks"].values()}
    out = []
    for l in leads:
        ko = _dt(l.get("kickoff"))
        if ko is None or ko <= now:
            continue
        if fixture_key(l) in seen_fixtures:
            continue
        out.append(l)
    # rarest first; longer run breaks a tie; then soonest
    out.sort(key=lambda l: (l["base_rate"], -l["strength"], l.get("kickoff") or ""))
    return out


def draw(leads, blob=None, now=None, slate_size=SLATE_SIZE):
    """Fill empty slots. Returns (blob, [newly drawn picks])."""
    blob = load() if blob is None else blob
    now = now or utc_now()

    active = live_picks(blob)
    need = slate_size - len(active)
    if need <= 0:
        return blob, []

    # A team already carrying a live pick is off the table for this slate.
    busy_teams = {t for p in active for t in (p["home"], p["away"])}
    pool = eligible(leads, blob, now)

    chosen = []
    for horizon in WINDOWS:
        cutoff = now + datetime.timedelta(days=horizon)
        chosen = []
        taken_fixtures, taken_teams = set(), set(busy_teams)
        for l in pool:
            if len(chosen) >= need:
                break
            ko = _dt(l["kickoff"])
            if ko > cutoff:
                continue
            if fixture_key(l) in taken_fixtures:
                continue
            if l["home"] in taken_teams or l["away"] in taken_teams:
                continue
            chosen.append(l)
            taken_fixtures.add(fixture_key(l))
            taken_teams.update((l["home"], l["away"]))
        if len(chosen) >= need:
            break                      # smallest window that fills the slate wins

    drawn = []
    for l in chosen:
        pid = pick_id(l)
        if pid in blob["picks"]:
            continue
        rec = {
            "id": pid,
            "drawn_at": now.isoformat(timespec="seconds"),
            "date": l["date"], "kickoff": l["kickoff"], "league": l["league"],
            "match": l["match"], "home": l["home"], "away": l["away"],
            "headline": l["headline"], "why": l.get("why"), "bet": l["bet"],
            "a": l["a"], "b": l["b"], "a_run": l["a_run"], "b_run": l["b_run"],
            "a_key": l["a_key"], "b_key": l["b_key"],
            "a_label": l.get("a_label"), "b_label": l.get("b_label"),
            "a_recent": l.get("a_recent", []), "b_recent": l.get("b_recent", []),
            "base_rate": l["base_rate"], "strength": l["strength"],
            "market": l.get("market"),
            "status": "live",
        }
        blob["picks"][pid] = rec
        drawn.append(rec)
    return blob, drawn


# ---------------------------------------------------------------- grade
def grade(fixtures, blob=None, now=None):
    """Settle live picks whose fixture has a final score. Returns (blob, n_graded)."""
    blob = load() if blob is None else blob
    now = now or utc_now()

    results = {}
    for f in fixtures:
        if f.get("played") and f.get("home_goals") is not None:
            results[fixture_key(f)] = (f["home_goals"], f["away_goals"])

    n = 0
    for p in blob["picks"].values():
        if p["status"] != "live":
            continue
        key = fixture_key(p)
        if key not in results:
            # Not played yet, or it moved. Only void once clearly overdue, so a
            # postponement surfaces instead of sitting live forever.
            ko = _dt(p.get("kickoff"))
            if ko and (now - ko).days > VOID_AFTER_DAYS:
                p["status"] = "void"
                p["note"] = "no final score found — postponed, or the fixture moved"
                p["graded_at"] = now.isoformat(timespec="seconds")
                n += 1
            continue
        hg, ag = results[key]
        got = T.settle_bet(p["bet"], p["home"], p["away"], hg, ag)
        if got is None:
            p["status"] = "void"
            p["note"] = "bet could not be judged from the final score"
        else:
            p["status"] = "hit" if got else "miss"
        p["final"] = f"{hg}-{ag}"
        p["graded_at"] = now.isoformat(timespec="seconds")
        n += 1
    return blob, n


# ---------------------------------------------------------------- measurement
def report(fixtures, blob=None):
    """Record to date, judged against the league-adjusted baseline (see streaks_track)."""
    blob = load() if blob is None else blob
    pop = T.population_rates(fixtures)
    per_league = T.league_baselines(fixtures)

    decided = [p for p in settled_picks(blob) if p["status"] in ("hit", "miss")]
    by_kind = {}
    for p in decided:
        by_kind.setdefault(T.bet_key(p["bet"]), []).append(p)

    rows = []
    for k, ps in sorted(by_kind.items(), key=lambda kv: -len(kv[1])):
        n = len(ps)
        hits = sum(1 for p in ps if p["status"] == "hit")
        rate, lo, hi = T._wilson(hits, n)
        base = T.mixed_baseline(per_league, k, [p["league"] for p in ps]) or pop.get(k)
        rows.append({
            "kind": k, "n": n, "hits": hits, "rate": rate,
            "base": base, "global_base": pop.get(k),
            "lift": (rate - base) if base is not None else None,
            "significant": bool(base is not None and (lo > base or hi < base)),
        })

    n = len(decided)
    hits = sum(1 for p in decided if p["status"] == "hit")
    return {
        "graded": n, "hits": hits,
        "rate": (hits / n) if n else None,
        "live": len(live_picks(blob)),
        "void": sum(1 for p in blob["picks"].values() if p["status"] == "void"),
        "rows": rows,
        "history": sorted(settled_picks(blob),
                          key=lambda p: p.get("kickoff") or p["date"], reverse=True),
    }


def horizon_days(blob, now=None):
    """How far out the live slate reaches — what the board should say its window is."""
    now = now or utc_now()
    kos = [_dt(p.get("kickoff")) for p in live_picks(blob)]
    kos = [k for k in kos if k]
    if not kos:
        return None
    return max(1, -(-int((max(kos) - now).total_seconds()) // 86400))


def load_leads(path=LEADS_IN):
    try:
        return json.load(open(path)).get("leads", [])
    except Exception:
        return []


def run(fixtures, leads=None, blob=None, now=None):
    """One full cycle: grade what finished, then refill. Grading FIRST so a slot freed by
    a just-settled pick is available to the same run."""
    blob = load() if blob is None else blob
    leads = load_leads() if leads is None else leads
    blob, graded = grade(fixtures, blob, now)
    blob, drawn = draw(leads, blob, now)
    return blob, graded, drawn


if __name__ == "__main__":
    import streaks_fetch
    fx = streaks_fetch.load_or_fetch()["fixtures"]
    b, graded, drawn = run(fx)
    save(b)
    r = report(fx, b)
    print(f"slate: {r['live']} live | graded now: {graded} | drawn now: {len(drawn)}")
    for p in live_picks(b):
        print(f"   [{p['base_rate']:>4.0%}] {p['headline'][:34]:34s} {p['match'][:30]:30s} "
              f"{p['kickoff'][5:16]}")
    if r["graded"]:
        print(f"\nrecord: {r['hits']}/{r['graded']} = {r['rate']:.1%}")
        for row in r["rows"]:
            b_ = f"{row['base']:.1%}" if row["base"] is not None else "—"
            l_ = f"{row['lift']*100:+.1f}pp" if row["lift"] is not None else "—"
            print(f"   {row['kind']:14s} {row['n']:3d}  {row['rate']:6.1%}  base {b_:>6s}"
                  f"  lift {l_:>8s}  {'SIG' if row['significant'] else ''}")
    else:
        print("nothing graded yet")
