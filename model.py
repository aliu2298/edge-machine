#!/usr/bin/env python3
"""model.py — a calibrated probability for each priced market, to score against the book.

WHY THIS EXISTS
---------------
Every streak rule on this board was measured against the teams' own rates and none lifted
them: a run is the noisiest estimate of a rate there is, so selecting on one guarantees the
next game regresses (top-20% of team-games by raw rate: predicted 65%, actual 56%). The
number that pays is against the BOOK, and the book's vig-free probability is a better
estimate than any form scrape. So the question worth asking is not "streak vs team rate"
but "model vs book": is a calibrated estimate ever better than the price?

THE MODEL
---------
Independent Poissons, the plainest thing that is actually calibrated:

    lambda_home = league_home_avg * attack(home) * defence(away)
    lambda_away = league_away_avg * attack(away) * defence(home)

attack/defence are a team's goals for/against per game relative to the average, pooled
across every tracked competition (form is cross-competition here, see streaks_build) and
SHRUNK toward 1.0 with SHRINK pseudo-games — the shrinkage is the whole point, it is what
the streak rules lacked. League averages are shrunk toward the global mean the same way.
Friendlies are excluded from the fit. No lookahead: fit(before=date) uses only fixtures
played strictly before that date, which is how the walk-forward below is run.

Markets: over15, over25, btts (fixture level) and the home/away side scoring 2+, matching
streaks_track.PRICED_MARKETS / TEAM_MARKETS.

Usage:  python3 model.py            walk-forward calibration + Brier vs the team-rate baseline
"""
import math, collections, datetime

# Pseudo-games toward average for attack/defence. Swept on the walk-forward (Sep 12 2026,
# 964 fixtures): 8 was OVERCONFIDENT at the extremes (a 92% over-1.5 quintile landed 85%),
# 24 was best or tied-best on every market and 32 no better. Heavy shrinkage is the
# lesson of this whole board — see the docstring.
SHRINK = 24
LEAGUE_SHRINK = 40    # pseudo-fixtures toward the global mean for a league's averages
MIN_GAMES = 3         # a side with fewer competitive games gets the average, not a rating


def fit(fixtures, before=None):
    """Ratings from competitive played fixtures (before `before`, if given)."""
    gf = collections.defaultdict(float); ga = collections.defaultdict(float)
    n = collections.defaultdict(int)
    lh = collections.defaultdict(float); la = collections.defaultdict(float)
    ln = collections.defaultdict(int)
    tot_h = tot_a = 0.0; tot_n = 0
    for f in fixtures:
        if not f.get("played") or f.get("home_goals") is None:
            continue
        if not f.get("competitive", True):
            continue
        if before is not None and f["date"] >= before:
            continue
        h, a, hg, ag = f["home"], f["away"], f["home_goals"], f["away_goals"]
        gf[h] += hg; ga[h] += ag; n[h] += 1
        gf[a] += ag; ga[a] += hg; n[a] += 1
        lh[f["league"]] += hg; la[f["league"]] += ag; ln[f["league"]] += 1
        tot_h += hg; tot_a += ag; tot_n += 1
    if not tot_n:
        return None
    mu_h, mu_a = tot_h / tot_n, tot_a / tot_n
    mu = (mu_h + mu_a) / 2                     # goals per team-game
    att, dfn = {}, {}
    for t in n:
        k = SHRINK * mu
        att[t] = (gf[t] + k) / (n[t] * mu + k) if n[t] >= MIN_GAMES else 1.0
        dfn[t] = (ga[t] + k) / (n[t] * mu + k) if n[t] >= MIN_GAMES else 1.0
    league = {}
    for lg in ln:
        w = ln[lg] / (ln[lg] + LEAGUE_SHRINK)
        league[lg] = (w * lh[lg] / ln[lg] + (1 - w) * mu_h,
                      w * la[lg] / ln[lg] + (1 - w) * mu_a)
    return {"att": att, "def": dfn, "league": league, "mu_h": mu_h, "mu_a": mu_a,
            "games": dict(n)}


def lambdas(m, home, away, league):
    mh, ma = m["league"].get(league, (m["mu_h"], m["mu_a"]))
    return (mh * m["att"].get(home, 1.0) * m["def"].get(away, 1.0),
            ma * m["att"].get(away, 1.0) * m["def"].get(home, 1.0))


def _pois_cdf(lam, k):
    return sum(math.exp(-lam) * lam ** i / math.factorial(i) for i in range(k + 1))


def probs(m, home, away, league):
    """{market: probability} for the priced markets, or None if the model is empty."""
    if not m:
        return None
    lh, la = lambdas(m, home, away, league)
    tot = lh + la
    return {
        "over15": 1 - _pois_cdf(tot, 1),
        "over25": 1 - _pois_cdf(tot, 2),
        "btts": (1 - math.exp(-lh)) * (1 - math.exp(-la)),
        "home2plus": 1 - _pois_cdf(lh, 1),
        "away2plus": 1 - _pois_cdf(la, 1),
        "lambda_home": round(lh, 3), "lambda_away": round(la, 3),
    }


def known(m, team):
    """Whether a side has enough games to carry a rating rather than the average."""
    return bool(m) and m["games"].get(team, 0) >= MIN_GAMES


# ---------------------------------------------------------------- validation
def walk_forward(fixtures, step_days=7):
    """Refit each week on everything before it; score that week's fixtures."""
    played = sorted([f for f in fixtures if f.get("played") and f.get("home_goals") is not None
                     and f.get("competitive", True) and f.get("lead_source", True)],
                    key=lambda f: f["date"])
    if not played:
        return []
    start = datetime.date.fromisoformat(played[0]["date"]) + datetime.timedelta(days=28)
    end = datetime.date.fromisoformat(played[-1]["date"])
    out = []
    d = start
    while d <= end:
        nxt = d + datetime.timedelta(days=step_days)
        m = fit(fixtures, before=d.isoformat())
        if m:
            for f in played:
                if d.isoformat() <= f["date"] < nxt.isoformat():
                    if not (known(m, f["home"]) and known(m, f["away"])):
                        continue
                    p = probs(m, f["home"], f["away"], f["league"])
                    hg, ag = f["home_goals"], f["away_goals"]
                    out.append({"date": f["date"], "p": p, "y": {
                        "over15": hg + ag >= 2, "over25": hg + ag >= 3,
                        "btts": hg >= 1 and ag >= 1, "home2plus": hg >= 2, "away2plus": ag >= 2}})
        d = nxt
    return out


if __name__ == "__main__":
    import sys
    import streaks_fetch
    fx = streaks_fetch.load_or_fetch()["fixtures"]
    rows = walk_forward(fx)
    print(f"walk-forward: {len(rows)} fixtures scored (weekly refit, SHRINK={SHRINK})\n")
    mid = rows[len(rows) // 2]["date"] if rows else None
    print(f"{'market':10s}{'n':>6}{'pop':>7}{'model avg':>10}{'actual':>8}{'Brier pop':>11}{'Brier model':>12}{'H1':>8}{'H2':>8}")
    for mk in ("over15", "over25", "btts", "home2plus", "away2plus"):
        n = len(rows)
        pop = sum(r["y"][mk] for r in rows) / n
        b_pop = sum((pop - r["y"][mk]) ** 2 for r in rows) / n
        b_mod = sum((r["p"][mk] - r["y"][mk]) ** 2 for r in rows) / n
        halves = []
        for sel in (lambda r: r["date"] < mid, lambda r: r["date"] >= mid):
            rs = [r for r in rows if sel(r)]
            bp = sum((sum(x["y"][mk] for x in rs) / len(rs) - r["y"][mk]) ** 2 for r in rs) / len(rs)
            bm = sum((r["p"][mk] - r["y"][mk]) ** 2 for r in rs) / len(rs)
            halves.append(bm - bp)
        print(f"{mk:10s}{n:6d}{pop:7.1%}{sum(r['p'][mk] for r in rows)/n:10.1%}{pop:8.1%}"
              f"{b_pop:11.4f}{b_mod:12.4f}{halves[0]:+8.4f}{halves[1]:+8.4f}")
    print("\n(Brier: lower is better; H1/H2 = model minus population Brier in each half — "
          "negative means the model beats a flat rate)")
    print("\ncalibration, over15 and home2plus by quintile of model probability:")
    for mk in ("over15", "home2plus"):
        s = sorted(rows, key=lambda r: r["p"][mk]); q = len(s) // 5
        print(f"  {mk}: " + "  ".join(
            f"[{sum(r['p'][mk] for r in s[i*q:(i+1)*q])/q:.0%} -> {sum(r['y'][mk] for r in s[i*q:(i+1)*q])/q:.0%}]"
            for i in range(5)))
