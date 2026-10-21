#!/usr/bin/env python3
"""NBA value model (2026-10-21): a team's points, and a game's first-quarter total, as Normals.

    team points  ~ Normal(mu_team, SD_TEAM)
        mu_team = (team's expected scoring + opponent's expected allowing) / 2  [+ HOME_HALF at home]
    1Q game total ~ Normal(mu_q1, SD_Q1)
        mu_q1   = (home 1Q scoring + away 1Q allowing) / 2 + (away 1Q scoring + home 1Q allowing) / 2

Each "expected" rate blends the team's 2025-26 regular-season per-game average (the prior) with
its current-season per-game average, shrinking toward the prior with weight w = n / (n + K) on
the current season (n = the team's games played before this tip, K = 8). At n = 0 it is the prior
alone, so the model is usable from game 1; by game 24 the current season carries 75%.

The prior, the sd and the home term come from data/nba_value_history.json: every completed
regular-season game of 2023-24, 2024-25 and 2025-26 on ESPN's scoreboard, with the final and the
first-quarter score of each side (3,693 games). `python3 nba_value_model.py --backtest` re-runs
the fit and the calibration below from that file; the numbers here are its output.

FIT AND VALIDATION (point-in-time: every mu uses only games before that tip).
  Fit season 2024-25 (prior 2023-24), validated out of sample on 2025-26 (prior 2024-25), with the
  final constants refit on both seasons' residuals. See BACKTEST below for the printed tables.

Probabilities are for Kalshi's rungs, which are all "over N.5": P(over L) = 1 - Phi((L - mu) / sd);
a half-point line has no push, so no continuity term is needed.
"""
import datetime as dt
import json
import math
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
HISTORY = os.path.join(ROOT, "data", "nba_value_history.json")
K = 8                      # shrinkage: w = n / (n + K) on the current season
PRIOR_SEASON = 2026        # ESPN season.year of 2025-26, the prior for 2026-27
# Fitted by --backtest on 2024-25 + 2025-26 residuals (BACKTEST below).
B_TEAM = 0.894             # slope on (own offence - L) + (opponent allowing - L)
B_Q1 = 0.5                 # slope on the four 1Q deviations: the plain halves form
SD_TEAM = 11.83
SD_Q1 = 8.28
HOME_HALF = 0.85           # points added to the home side (and taken from the away side)
TEAMS = ("ATL BKN BOS CHA CHI CLE DAL DEN DET GS HOU IND LAC LAL MEM MIA MIL MIN NO NY OKC ORL PHI "
         "PHX POR SA SAC TOR UTAH WSH").split()
COLS = ("season", "start", "espn_id", "home", "away", "pts_home", "pts_away", "q1_home", "q1_away")
BACKTEST = """(filled in from --backtest)"""


# ---------- the normal ----------

def phi(z):
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def p_over(line, mu, sd):
    """P(X > line) for X ~ Normal(mu, sd)."""
    if sd <= 0:
        return 1.0 if mu > line else 0.0
    return 1 - phi((line - mu) / sd)


# ---------- history and the prior ----------

def load_history(path=HISTORY):
    with open(path) as f:
        blob = json.load(f)
    cols = blob.get("columns") or list(COLS)
    return [dict(zip(cols, r)) for r in blob["games"]]


def blank():
    return dict(n=0, pts_for=0.0, pts_against=0.0, q1_for=0.0, q1_against=0.0)


def add(acc, team, g):
    """Add one completed game (a history-shaped row) to `team`'s running sums in `acc`."""
    home = g["home"] == team
    a = acc.setdefault(team, blank())
    a["n"] += 1
    a["pts_for"] += g["pts_home"] if home else g["pts_away"]
    a["pts_against"] += g["pts_away"] if home else g["pts_home"]
    a["q1_for"] += g["q1_home"] if home else g["q1_away"]
    a["q1_against"] += g["q1_away"] if home else g["q1_home"]


def season_sums(games, season):
    acc = {}
    for g in games:
        if g["season"] == season:
            add(acc, g["home"], g)
            add(acc, g["away"], g)
    return acc


def averages(sums):
    """{team: {n, off, dfn, q1_off, q1_dfn}} per-game averages from running sums."""
    out = {}
    for t, a in sums.items():
        if a["n"]:
            out[t] = dict(n=a["n"], off=a["pts_for"] / a["n"], dfn=a["pts_against"] / a["n"],
                          q1_off=a["q1_for"] / a["n"], q1_dfn=a["q1_against"] / a["n"])
    return out


_PRIOR = {}


def prior(games=None, season=PRIOR_SEASON):
    """Each team's per-game averages over one regular season (2025-26 by default, read once)."""
    if games is None:
        if season not in _PRIOR:
            _PRIOR[season] = averages(season_sums(load_history(), season))
        return _PRIOR[season]
    return averages(season_sums(games, season))


# ---------- the blend ----------

def weight(n, k=K):
    return n / (n + k) if n > 0 else 0.0


def blend(prior_v, cur_mean, n, k=K):
    """w * current + (1 - w) * prior, w = n / (n + k). No prior: the current mean; neither: None."""
    if prior_v is None:
        return cur_mean if n else None
    if not n or cur_mean is None:
        return prior_v
    w = weight(n, k)
    return w * cur_mean + (1 - w) * prior_v


def form(team, pri, cur_sums, k=K):
    """{n, off, dfn, q1_off, q1_dfn} for one team before a tip: the prior blended with this season."""
    p = pri.get(team) or {}
    c = cur_sums.get(team) or blank()
    n = c["n"]
    cur = averages({team: c}).get(team) or {}
    return dict(n=n, **{f: blend(p.get(f), cur.get(f), n, k) for f in ("off", "dfn", "q1_off", "q1_dfn")})


def league(pri, cur_sums, k=K, teams=TEAMS):
    """The league level of the blended rates: {pts, q1} per team-game, from all 30 teams' forms."""
    fs = [form(t, pri, cur_sums, k) for t in teams]
    vals = lambda f: [x[f] for x in fs if x.get(f) is not None]
    off, dfn, qo, qd = vals("off"), vals("dfn"), vals("q1_off"), vals("q1_dfn")
    if not (off and dfn and qo and qd):
        return None
    return dict(pts=(sum(off) / len(off) + sum(dfn) / len(dfn)) / 2,
                q1=(sum(qo) / len(qo) + sum(qd) / len(qd)) / 2)


def mu_team(own, opp, home, lg, b=None, home_half=None):
    """Expected points of the team with form `own` against `opp`, at league level `lg`.

    mu = L + B_TEAM * ((own offence - L) + (opponent's allowing - L)) +/- HOME_HALF."""
    b = B_TEAM if b is None else b
    h = HOME_HALF if home_half is None else home_half
    if own.get("off") is None or opp.get("dfn") is None or not lg:
        return None
    L = lg["pts"]
    return L + b * ((own["off"] - L) + (opp["dfn"] - L)) + (h if home else -h)


def mu_q1(home, away, lg, b=None):
    """Expected first-quarter game total: 2L + B_Q1 * (the four 1Q deviations from L)."""
    b = B_Q1 if b is None else b
    vals = (home.get("q1_off"), away.get("q1_dfn"), away.get("q1_off"), home.get("q1_dfn"))
    if any(v is None for v in vals) or not lg:
        return None
    L = lg["q1"]
    return 2 * L + b * sum(v - L for v in vals)


def prior_level(pri):
    """(points per team-game, 1Q game total) of a prior: its league means."""
    if not pri:
        return None, None
    v = list(pri.values())
    pts = (sum(x["off"] for x in v) + sum(x["dfn"] for x in v)) / (2 * len(v))
    q1 = (sum(x["q1_off"] for x in v) + sum(x["q1_dfn"] for x in v)) / len(v)
    return pts, q1


def shift_prior(pri, level_pts=None, level_q1=None):
    """The prior re-anchored to the current scoring level (2026-10-21, Olu's main session).

    team prior = level now + (team's 2025-26 rate - 2025-26 league rate), for scoring and allowing,
    full game and 1Q (a 1Q game-total level is split evenly between the two sides). A level of
    None leaves that part unchanged."""
    p_pts, p_q1 = prior_level(pri)
    dp = 0.0 if level_pts is None or p_pts is None else level_pts - p_pts
    dq = 0.0 if level_q1 is None or p_q1 is None else (level_q1 - p_q1) / 2
    return {t: dict(v, off=v["off"] + dp, dfn=v["dfn"] + dp, q1_off=v["q1_off"] + dq, q1_dfn=v["q1_dfn"] + dq)
            for t, v in pri.items()}


def game_model(home, away, pri, cur_sums, k=K):
    """The model for one game: both teams' mu and the 1Q mu, with each team's form."""
    fh, fa = form(home, pri, cur_sums, k), form(away, pri, cur_sums, k)
    lg = league(pri, cur_sums, k)
    return dict(home=home, away=away, form={home: fh, away: fa}, league=lg,
                mu={home: mu_team(fh, fa, True, lg), away: mu_team(fa, fh, False, lg)},
                mu_q1=mu_q1(fh, fa, lg), sd=SD_TEAM, sd_q1=SD_Q1)


def current_sums(games, before=None):
    """Running sums over completed current-season games that tipped before `before` (ISO or datetime).

    `games` are history-shaped rows (home, away, pts_*, q1_*, start)."""
    acc = {}
    cut = _t(before) if before is not None else None
    for g in sorted(games, key=lambda g: str(g.get("start"))):
        if cut is not None and (_t(g.get("start")) is None or _t(g["start"]) >= cut):
            continue
        if any(g.get(c) is None for c in ("pts_home", "pts_away", "q1_home", "q1_away")):
            continue
        add(acc, g["home"], g)
        add(acc, g["away"], g)
    return acc


def _t(v):
    if isinstance(v, dt.datetime):
        return v if v.tzinfo else v.replace(tzinfo=dt.timezone.utc)
    try:
        x = dt.datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return x if x.tzinfo else x.replace(tzinfo=dt.timezone.utc)


# ---------- backtest ----------

def residuals(games, season, prior_season, k=K):
    """Point-in-time rows for one season, before any fitted constant is applied.

    Per team-game: L (league level), d (own offence + opponent allowing, each minus L), pts, home, n.
    Per game: L (1Q level), d (the four 1Q deviations), q1, n. Each tip sees only earlier games."""
    pri = averages(season_sums(games, prior_season))
    cur, team_rows, q1_rows = {}, [], []
    for g in sorted((g for g in games if g["season"] == season), key=lambda g: (g["start"], str(g["espn_id"]))):
        fh, fa = form(g["home"], pri, cur, k), form(g["away"], pri, cur, k)
        lg = league(pri, cur, k)
        for team, own, opp, home, pts in ((g["home"], fh, fa, True, g["pts_home"]),
                                          (g["away"], fa, fh, False, g["pts_away"])):
            base = mu_team(own, opp, home, lg, b=0.0, home_half=0.0)
            if base is not None:
                d = mu_team(own, opp, home, lg, b=1.0, home_half=0.0) - base
                team_rows.append(dict(team=team, L=base, d=d, pts=pts, home=home, n=own["n"], start=g["start"]))
        base = mu_q1(fh, fa, lg, b=0.0)
        if base is not None:
            q1_rows.append(dict(L=base, d=mu_q1(fh, fa, lg, b=1.0) - base, q1=g["q1_home"] + g["q1_away"],
                                n=min(fh["n"], fa["n"]), start=g["start"]))
        add(cur, g["home"], g)
        add(cur, g["away"], g)
    return team_rows, q1_rows


def ols_slope(xs, ys):
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)


def fit(team_rows, q1_rows, home=True, b_q1=None):
    """dict(b, home_half, sd, bias, b_q1, sd_q1, bias_q1) from residual rows.

    b is the OLS slope of (points - L) on d; the home term is half the home-minus-away mean
    residual (0 when `home` is False); sd is the residual standard deviation around the bias.
    `b_q1` fixes the 1Q slope instead of fitting it."""
    b = ols_slope([r["d"] for r in team_rows], [r["pts"] - r["L"] for r in team_rows])
    res = {r_i: r["pts"] - r["L"] - b * r["d"] for r_i, r in enumerate(team_rows)}
    hr = [res[i] for i, r in enumerate(team_rows) if r["home"]]
    ar = [res[i] for i, r in enumerate(team_rows) if not r["home"]]
    hh = (sum(hr) / len(hr) - sum(ar) / len(ar)) / 2 if home and hr and ar else 0.0
    fin = [res[i] - (hh if r["home"] else -hh) for i, r in enumerate(team_rows)]
    bias = sum(fin) / len(fin)
    sd = (sum((x - bias) ** 2 for x in fin) / (len(fin) - 1)) ** 0.5
    bq = ols_slope([r["d"] for r in q1_rows], [r["q1"] - r["L"] for r in q1_rows]) if b_q1 is None else b_q1
    qres = [r["q1"] - r["L"] - bq * r["d"] for r in q1_rows]
    qbias = sum(qres) / len(qres)
    qsd = (sum((x - qbias) ** 2 for x in qres) / (len(qres) - 1)) ** 0.5
    return dict(b=b, home_half=hh, sd=sd, bias=bias, b_q1=bq, sd_q1=qsd, bias_q1=qbias)


def _sd(xs):
    m = sum(xs) / len(xs)
    return (sum((x - m) ** 2 for x in xs) / (len(xs) - 1)) ** 0.5


def team_mu(r, f):
    return r["L"] + f["b"] * r["d"] + (f["home_half"] if r["home"] else -f["home_half"])


def q1_mu(r, f):
    return r["L"] + f["b_q1"] * r["d"]


def reliability(pairs, edges=(0, .1, .2, .3, .4, .5, .6, .7, .8, .9, 1.0001)):
    """[(lo, hi, n, mean model P, hit rate)] and the Brier score for (P, outcome) pairs."""
    out = []
    for lo, hi in zip(edges, edges[1:]):
        bk = [(p, y) for p, y in pairs if lo <= p < hi]
        if bk:
            out.append((lo, min(hi, 1.0), len(bk), sum(p for p, _ in bk) / len(bk), sum(y for _, y in bk) / len(bk)))
    brier = sum((p - y) ** 2 for p, y in pairs) / len(pairs) if pairs else None
    return out, brier


def pairs_team(rows, f, lines):
    return [(p_over(L, team_mu(r, f), f["sd"]), int(r["pts"] > L)) for r in rows for L in lines]


def pairs_q1(rows, f, lines):
    return [(p_over(L, q1_mu(r, f), f["sd_q1"]), int(r["q1"] > L)) for r in rows for L in lines]


TEAM_LINES = tuple(x + 0.5 for x in range(95, 140))
Q1_LINES = tuple(x + 0.5 for x in range(45, 76))
EXP_BINS = ((0, 109), (109, 111), (111, 113), (113, 115), (115, 117), (117, 119), (119, 999))
Q1_BINS = ((0, 56), (56, 58), (58, 60), (60, 62), (62, 64), (64, 999))


def backtest(games=None, log=print):
    """Fit on 2024-25 (prior 2023-24), validate on 2025-26 (prior 2024-25), refit on both."""
    games = load_history() if games is None else games
    t25, q25 = residuals(games, 2025, 2024)
    t26, q26 = residuals(games, 2026, 2025)
    f25, f26, fall = fit(t25, q25), fit(t26, q26), fit(t25 + t26, q25 + q26)
    f25_nohome = fit(t25, q25, home=False)
    # The plain (offence + opponent allowing) / 2 form is b = 0.5 on the same deviations.
    half = dict(f25, b=0.5, sd=_sd([r["pts"] - r["L"] - 0.5 * r["d"] for r in t25]))
    f25_q = fit(t25, q25, b_q1=B_Q1)        # the 1Q slope used: 0.5, the best out of sample
    for name, f in (("2024-25 fit", f25), ("2025-26 alone", f26), ("both seasons", fall),
                    ("both seasons, 1Q b 0.5", fit(t25 + t26, q25 + q26, b_q1=B_Q1))):
        log(f"{name}: b {f['b']:.3f}  home_half {f['home_half']:+.2f}  sd {f['sd']:.2f}  bias {f['bias']:+.2f} | "
            f"1Q b {f['b_q1']:.3f}  sd {f['sd_q1']:.2f}  bias {f['bias_q1']:+.2f}")
    log(f"rows: 2024-25 {len(t25)} team-games / {len(q25)} games; 2025-26 {len(t26)} / {len(q26)}")
    for name, f in (("additive + home (2024-25 fit)", f25), ("additive, no home term", f25_nohome),
                    ("(off + opp allowed) / 2, b 0.5", half)):
        log(f"2025-26 team-total Brier, {name}: {reliability(pairs_team(t26, f, TEAM_LINES))[1]:.5f}")
    for name, f in (("1Q b fitted on 2024-25", f25), ("1Q b 0.5", f25_q)):
        log(f"2025-26 1Q Brier, {name}: {reliability(pairs_q1(q26, f, Q1_LINES))[1]:.5f}")
    rel, br = reliability(pairs_team(t26, f25, TEAM_LINES))
    log("2025-26 team totals, out of sample (2024-25 constants), lines 95.5-139.5 (model P bucket: n, mean P, hit):")
    for lo, hi, n, mp, hr in rel:
        log(f"  {lo:.1f}-{hi:.1f}  n {n:6d}  P {mp:.3f}  hit {hr:.3f}  gap {hr - mp:+.3f}")
    log(f"  Brier {br:.5f}")
    log("2025-26 by model mu x line, model P / hit rate (all team-games):")
    for lo, hi in EXP_BINS:
        rs = [r for r in t26 if lo <= team_mu(r, f25) < hi]
        cells = []
        for L in (105.5, 109.5, 113.5):
            ps = [p_over(L, team_mu(r, f25), f25["sd"]) for r in rs]
            hits = [r["pts"] > L for r in rs]
            cells.append(f"{L}: {sum(ps) / len(ps):.0%} / {sum(hits) / len(hits):.0%}" if rs else f"{L}: -")
        log(f"  mu {lo}-{hi if hi < 999 else '+'}  n {len(rs):4d}  " + "  ".join(cells))
    log("2025-26 residual by games played (2024-25 constants):")
    for lo, hi in ((0, 5), (5, 10), (10, 20), (20, 99)):
        rs = [r["pts"] - team_mu(r, f25) for r in t26 if lo <= r["n"] < hi]
        if rs:
            m = sum(rs) / len(rs)
            log(f"  n {lo}-{hi - 1}: {len(rs)} team-games, mean {m:+.2f}, sd {(sum((x - m) ** 2 for x in rs) / len(rs)) ** 0.5:.2f}")
    f25 = f25_q
    rel, br = reliability(pairs_q1(q26, f25, Q1_LINES))
    log("2025-26 1Q game totals, out of sample (b 0.5, 2024-25 sd), lines 45.5-75.5:")
    for lo, hi, n, mp, hr in rel:
        log(f"  {lo:.1f}-{hi:.1f}  n {n:6d}  P {mp:.3f}  hit {hr:.3f}  gap {hr - mp:+.3f}")
    log(f"  Brier {br:.5f}")
    log("2025-26 1Q by model mu x line, model P / hit rate:")
    for lo, hi in Q1_BINS:
        rs = [r for r in q26 if lo <= q1_mu(r, f25) < hi]
        cells = []
        for L in (55.5, 59.5, 63.5):
            ps = [p_over(L, q1_mu(r, f25), f25["sd_q1"]) for r in rs]
            hits = [r["q1"] > L for r in rs]
            cells.append(f"{L}: {sum(ps) / len(ps):.0%} / {sum(hits) / len(hits):.0%}" if rs else f"{L}: -")
        log(f"  mu {lo}-{hi if hi < 999 else '+'}  n {len(rs):4d}  " + "  ".join(cells))
    return dict(fit_2025=f25, fit_2026=f26, fit_all=fall)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if "--backtest" in argv:
        backtest()
        return 0
    pri = prior()
    for t in sorted(pri):
        p = pri[t]
        print(f"{t:5} n {p['n']:2d}  off {p['off']:.1f}  dfn {p['dfn']:.1f}  1Q {p['q1_off']:.1f}/{p['q1_dfn']:.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
