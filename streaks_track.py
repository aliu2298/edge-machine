#!/usr/bin/env python3
"""streaks_track.py — log every streak lead when it is published, grade it once the
fixture is played, and measure whether the confluence actually carried information.

WHAT THIS MEASURES, AND WHAT IT DOES NOT
----------------------------------------
Lift first. A hit rate on its own is useless: "over 2.5 landed 60%" means nothing without
something to compare it against.

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

PRICES (added 2026-09-12)
-------------------------
Lift against the teams' own rate answers "does the confluence carry information". It does
not answer "does it pay", because a sportsbook already prices what the teams do: on the
day this was added, over 1.5 on lead fixtures traded at ~1.20 — a break-even hit rate of
83.4%, which is exactly what leads hit. So every lead is also priced: the Bovada line is
captured the FIRST build where one is listed (see price()), never revised and never taken
after kickoff, and three fixture-level markets are logged on every lead — the claim
(over 1.5) plus over 2.5 and BTTS, pre-registered in PRICED_MARKETS so no market is chosen
after seeing which one paid. P/L is a flat 1 unit at the captured price. The yardstick for
that section is the book's own vig-free probability, not the teams' rate.

Usage:  python3 streaks_track.py [--report]
        (streaks_build.py calls record() and grade() automatically each build)
"""
import json, os, math, datetime, collections

ROOT = os.path.dirname(os.path.abspath(__file__))
LEDGER = os.path.join(ROOT, "data", "streak_leads.json")

# Only grade leads whose fixture is comfortably finished. ESPN can carry a fixture as
# scheduled past kickoff, and a postponed match must not silently grade as a miss.
GRADE_GRACE_DAYS = 1

# Fixture-level markets priced on EVERY lead, whatever its headline claims. Fixed here,
# in advance, so the record shows ROI on the same fixture set for all three and none is
# picked after the fact. Keys match venues.parse_bovada_prices().
PRICED_MARKETS = {
    "over15": {"kind": "total_gte", "n": 2},
    "over25": {"kind": "total_gte", "n": 3},
    "btts":   {"kind": "btts"},
}
MARKET_LABEL = {"over15": "Over 1.5 goals", "over25": "Over 2.5 goals",
                "btts": "Both teams to score"}
# Per build. One paced request each (~1.5s), so this bounds the step at ~90s; anything
# left over is picked up next build — lines beyond three days out rarely exist anyway.
MAX_PRICE_FETCHES = 60


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


def utc_today():
    """UTC date. ESPN stamps fixtures in UTC, so comparing them against a LOCAL date makes
    the board non-deterministic: on a US-timezone Mac `date.today()` was 2026-08-28 while
    CI (UTC) saw 2026-08-29, and the two produced different lead sets from identical data.
    """
    return datetime.datetime.now(datetime.timezone.utc).date()


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
            "first_seen": utc_today().isoformat(),
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


def _kickoff(e):
    ko = e.get("kickoff")
    if not ko:
        return None
    try:
        return datetime.datetime.fromisoformat(ko.replace("Z", "+00:00"))
    except ValueError:
        return None


def price(blob, leads, fetch, now=None):
    """Capture the book's price on pending leads that do not have one yet.

    `leads` are the leads as published this build (they carry the venue link; the ledger
    never does). `fetch(link)` returns {market: {price, fair}}, {} when no line is up
    yet, or None when the book could not be read. Rules, each of which is a test:

      * ONCE. A priced lead is never touched again, whatever the line does afterwards.
      * BEFORE KICKOFF ONLY. A lead whose fixture has started is never priced, so a price
        can never be captured with the result already known.
      * NO LINE, NO PRICE. An empty or failed read leaves the lead unpriced and it is
        retried next build — a sportsbook posts distant fixtures closer to kickoff.
      * THE CLAIM MUST BE PRICED. A book that lists BTTS but not over 1.5 (Bovada often
        posts the alternate totals ladder later than the props — 8 of the first 47 leads
        priced came back that way) is treated as no line: nothing is stored, so the lead
        is retried until the claim's own market is up. Storing the companions alone would
        mark the lead priced and lose the one market it is actually about.

    Returns (blob, n_priced, n_fetched).
    """
    now = now or datetime.datetime.now(datetime.timezone.utc)
    today = now.date().isoformat()
    link_of = {lead_id(l): l.get("market") for l in leads if l.get("market")}
    cache = {}                                    # link -> result, within this run
    n_priced = n_fetched = 0
    for lid, e in blob["leads"].items():
        if e.get("status") != "pending" or e.get("prices"):
            continue
        link = link_of.get(lid)
        if not link:
            continue
        ko = _kickoff(e)
        if ko is not None:
            if ko <= now:
                continue
        elif (e.get("date") or "") <= today:
            continue                              # no kickoff time: date must be ahead
        if link not in cache:
            if n_fetched >= MAX_PRICE_FETCHES:
                break
            n_fetched += 1
            cache[link] = fetch(link)
        got = cache[link]
        if not got or "over15" not in got:      # the claim's own line must be up
            continue
        e["prices"] = {k: dict(v) for k, v in got.items() if k in PRICED_MARKETS}
        e["priced_at"] = now.isoformat(timespec="seconds")
        n_priced += 1
    return blob, n_priced, n_fetched


def _settle_prices(e, hg, ag):
    """P/L per priced market at a flat 1 unit. Only called with a real final score."""
    out = {}
    for mk, pr in (e.get("prices") or {}).items():
        bet = PRICED_MARKETS.get(mk)
        if not bet:
            continue
        got = settle_bet(bet, e["home"], e["away"], hg, ag)
        if got is None:
            continue
        out[mk] = {"hit": bool(got), "pnl": round(pr["price"] - 1, 4) if got else -1.0}
    return out


def grade(fixtures, blob=None):
    """Settle pending leads whose fixture has a final score."""
    blob = blob if blob is not None else load()
    results = {}
    for f in fixtures:
        if f["played"] and f["home_goals"] is not None:
            results[(f["date"], f["home"], f["away"])] = (f["home_goals"], f["away_goals"])

    today = utc_today()
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
        if e.get("prices"):
            e["pnl"] = _settle_prices(e, hg, ag)
        e["graded_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat(
            timespec="seconds")
        graded += 1
    return blob, graded


def price_report(blob):
    """Per priced market: hit rate against the book's break-even and its vig-free
    probability, and flat-stake ROI. Only leads that were priced BEFORE kickoff and have
    since settled count; a lead graded before pricing existed is simply absent."""
    settled = [e for e in blob["leads"].values()
               if e.get("prices") and e.get("pnl") and e["status"] in ("hit", "miss")]
    rows = []
    for mk in PRICED_MARKETS:
        es = [e for e in settled if mk in e["pnl"] and mk in e["prices"]]
        n = len(es)
        if not n:
            continue
        hits = sum(1 for e in es if e["pnl"][mk]["hit"])
        pnl = sum(e["pnl"][mk]["pnl"] for e in es)
        avg_price = sum(e["prices"][mk]["price"] for e in es) / n
        fair = sum(e["prices"][mk]["fair"] for e in es) / n
        breakeven = 1 / avg_price
        p, lo, hi = _wilson(hits, n)
        rows.append({
            "market": mk, "label": MARKET_LABEL[mk], "n": n, "hits": hits,
            "rate": p, "lo": lo, "hi": hi, "avg_price": avg_price, "fair": fair,
            "breakeven": breakeven, "pnl": pnl, "roi": pnl / n,
            "lift": p - fair,
            # Only a hit rate whose interval clears the break-even line is a result.
            "significant": bool(lo > breakeven or hi < breakeven),
        })
    pending = sum(1 for e in blob["leads"].values()
                  if e.get("prices") and e["status"] == "pending")
    claim = next((r for r in rows if r["market"] == "over15"), None)
    return {"rows": rows, "graded": len(settled), "pending": pending,
            "claim_roi": claim["roi"] if claim else None}


# ---------------------------------------------------------------- measurement
def population_rates(fixtures):
    """How often each bet kind lands across EVERY played fixture in the window.

    This is the yardstick. Without it a hit rate is unreadable — the whole question is
    whether flagging a fixture beats not flagging it.
    """
    # COMPETITIVE only. Friendlies are in the pull to give barely-started teams a form
    # line, but they are higher-scoring and less serious — letting them into the baseline
    # would shift the very yardstick the leads are measured against.
    played = [f for f in fixtures if f["played"] and f["home_goals"] is not None
              and f.get("competitive", True)]
    n = len(played)
    if not n:
        return {}
    team_games = 2 * n
    out = {
        "btts": sum(1 for f in played
                    if f["home_goals"] >= 1 and f["away_goals"] >= 1) / n,
        "total_gte:3": sum(1 for f in played
                           if f["home_goals"] + f["away_goals"] >= 3) / n,
        "total_gte:2": sum(1 for f in played
                           if f["home_goals"] + f["away_goals"] >= 2) / n,
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


def team_kind_rates(fixtures):
    """team -> {bet_kind: that team's own rate for the outcome}.

    ⚠️ THE LEAGUE BASELINE IS NOT ENOUGH, and for team-specific bets it is close to
    meaningless. "Go Ahead Eagles to score 2+" should be judged against how often GAE
    score 2+, not against how often anyone in the Eredivisie does — and the confluence
    SELECTS free-scoring teams, so a league average systematically understates what these
    sides do anyway and manufactures lift out of team quality.

    Measured on the first 18 graded leads:

        team to score    +9.3pp vs league  ->  -1.5pp vs the team    (sign flips)
        team to score 2+ +48.7pp           ->  +7.7pp
        BTTS             +18.0pp           -> +11.7pp

    Same confound already found in fire_track: teams on long scoring runs are good teams.
    Fixture-level outcomes (BTTS, totals) use the mean of the two sides' own rates, which
    is an approximation but far closer than a league average.
    """
    tot = collections.defaultdict(lambda: collections.defaultdict(list))
    for f in fixtures:
        if not f.get("played") or f.get("home_goals") is None:
            continue
        if not f.get("competitive", True):
            continue                      # friendlies would shift the yardstick
        hg, ag = f["home_goals"], f["away_goals"]
        for team, gf, ga in ((f["home"], hg, ag), (f["away"], ag, hg)):
            d = tot[team]
            d["btts"].append(1 if (gf >= 1 and ga >= 1) else 0)
            d["total_gte:3"].append(1 if gf + ga >= 3 else 0)
            d["total_gte:2"].append(1 if gf + ga >= 2 else 0)
            d["total_lte:2"].append(1 if gf + ga <= 2 else 0)
            d["team_gte:1"].append(1 if gf >= 1 else 0)
            d["team_gte:2"].append(1 if gf >= 2 else 0)
            d["team_eq:0"].append(1 if gf == 0 else 0)
    return {t: {k: (sum(v) / len(v) if v else None) for k, v in d.items()}
            for t, d in tot.items()}


def team_baseline(entry, kind, team_rates):
    """Baseline for ONE graded entry, from the teams involved rather than the league."""
    bet = entry.get("bet") or {}
    if bet.get("team"):                                  # the claim names a side
        return team_rates.get(bet["team"], {}).get(kind)
    a = team_rates.get(entry.get("home"), {}).get(kind)  # fixture-level outcome
    b = team_rates.get(entry.get("away"), {}).get(kind)
    if a is None or b is None:
        return a if b is None else b
    return (a + b) / 2


def league_baselines(fixtures):
    """league -> its own population rates. Needed because a GLOBAL baseline is confounded
    by league mix.

    Measured, not hypothetical: BTTS leads cluster in high-scoring leagues, and on the
    backtest that inflated an apparent +17.1pp BTTS lift to a real +10.7pp once each lead
    was compared against its own league. Reading the global number would have reported a
    significant edge that was really 'MLS and the Eredivisie score a lot'.
    """
    out = {}
    for lg in {f["league"] for f in fixtures
               if f["played"] and f.get("competitive", True)}:
        sub = [f for f in fixtures if f["played"] and f["league"] == lg
               and f["home_goals"] is not None and f.get("competitive", True)]
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
    tr = team_kind_rates(fixtures)
    settled = [e for e in blob["leads"].values() if e["status"] in ("hit", "miss")]

    by_kind = {}
    for e in settled:
        by_kind.setdefault(bet_key(e["bet"]), []).append(e)

    rows = []
    for k, entries in sorted(by_kind.items()):
        n = len(entries)
        hits = sum(1 for e in entries if e["status"] == "hit")
        p, lo, hi = _wilson(hits, n)
        # TEAM baseline is the one judged against — a claim about a named side must be
        # measured against that side, and the confluence selects free-scoring teams so a
        # league average manufactures lift out of team quality. League kept for contrast.
        lbase = mixed_baseline(per_league, k, [e["league"] for e in entries]) or pop.get(k)
        tvals = [team_baseline(e, k, tr) for e in entries]
        tvals = [v for v in tvals if v is not None]
        base = (sum(tvals) / len(tvals)) if tvals else lbase
        rows.append({
            "kind": k, "n": n, "hits": hits, "rate": p, "lo": lo, "hi": hi,
            "base": base, "league_base": lbase, "global_base": pop.get(k),
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
    priced = price_report(blob)
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
        "priced": priced,
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
    pr = r["priced"]
    if pr["rows"]:
        print(f"\npriced: {pr['graded']} settled at a price | {pr['pending']} pending")
        print(f"{'market':22s} {'n':>4s} {'hit':>7s} {'b/e':>7s} {'fair':>7s} {'price':>6s} {'ROI':>8s}")
        for row in pr["rows"]:
            print(f"{row['label']:22s} {row['n']:4d} {row['rate']:7.1%} {row['breakeven']:7.1%} "
                  f"{row['fair']:7.1%} {row['avg_price']:6.2f} {row['roi']:+8.1%}"
                  f"  {'SIG' if row['significant'] else ''}")
