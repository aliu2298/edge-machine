#!/usr/bin/env python3
"""NBA value lanes (2026-10-21): four Sandbox PAPER lanes on Kalshi NBA team totals and 1Q totals.

    nba_tt_value_1h    team totals (KXNBATEAMTOTAL), entered 60-90 minutes before tip
    nba_tt_value_24h   team totals, entered 18-26 hours before tip
    nba_1q_value_1h    first-quarter game total (KXNBA1QTOTAL), 60-90 minutes before tip
    nba_1q_value_24h   first-quarter game total, 18-26 hours before tip

Paper only: not in Production, not in the Production feed, no PAIR_OVERRIDES entry, on their own
fresh record (data/nba_value_ledger.json). Nothing is placed. The seven label rules R1-R7
(nba_rules.py) are a separate family and are not touched.

PRE-REGISTERED 2026-10-21.
THE MODEL (nba_value_model.py). A team's points ~ Normal(mu, 11.83); the 1Q game total ~
  Normal(mu_q1, 8.28). Each team's scoring and allowing rates blend its 2025-26 regular-season
  per-game average with this season's, weight n / (n + 8) on this season (n = games played).
  mu = L + 0.894 * ((own scoring - L) + (opponent's allowing - L)) +/- 0.85 at home/away, L the
  league level of the same blended rates; mu_q1 = 2L + 0.5 * (the four 1Q deviations). Fitted
  on 2024-25, checked out of sample on 2025-26 (prior 2024-25), point-in-time: the model's P sat
  within 1.6pp of the hit rate in every 10pp bucket (team totals, Brier 0.142) and within 1.9pp
  (1Q, Brier 0.143). The plain (own scoring + opponent's allowing) / 2 form was too flat
  (points rose 1.7 per point of it) and is not used for team totals; a home term of +/-0.85 was
  kept because it lowered the out-of-sample Brier (0.14227 v 0.14265).
RESEARCH TABLE (the last two seasons, 4,304 team-games, ESPN): how often a team crossed a line
  by expected points = (season-to-date scored + opponent's season-to-date allowed) / 2, min 10
  games: <109 44/30/20% at 105.5/109.5/113.5; 109-111 59/50/34; 111-113 65/53/39; 113-115
  73/64/51; 115-117 82/73/59; 117-119 87/80/68; 119+ 93/87/78. Stable by month; home/away,
  back-to-backs and last-5 form barely moved it. 2025-26 averaged 115.4 points a team.
THE RULE. At the entry read, for every rung of the ladder (both teams' team-total rungs; every 1Q
  rung), the model's P for the YES (over) and the NO, and the fee-adjusted edge
  P - (price + 0.07 * price * (1 - price)), price = the YES ask for YES, 1 - the YES bid for NO.
  Take the single best-edge side and rung per team (team totals) or per game (1Q) when the edge is
  0.05 or more, the rung quoted two-sided (bid above 0, ask below 1) with a spread of 3c or less,
  and the price of the side bought 0.25 to 0.92 inclusive. A tie goes to the lower strike, then YES.
ONE LOOK. Each lane looks at a game once: the first read inside its window at which Kalshi lists
  the ladder with at least one two-sided rung. If nothing clears the bar at that look there is no
  entry for that game. One frozen entry per lane per team (team totals) or per game (1Q).
ONE MARKET, ONE LANE (within this family): a ticker one of the four lanes holds is never taken by
  another; the 24h lanes look first, so the 1h lanes take their best other qualifying rung.
SETTLEMENT. Kalshi's official result, profit per $100 after the 7% taker fee. Stats are clustered
  by game night (the ET date of the tip): the z uses the night-clustered variance, never below the
  independent-bets variance.
BLIND BASELINE (per lane): the YES on every rung with the same two-sided 3c quote and a YES ask of
  0.25-0.92 at that lane's look, one entry per rung.
LEVEL ANCHOR AND GUARD (added the evening of 2026-10-21, before any entry). The 2025-26 prior is
  re-anchored to the 2026-27 scoring level: team prior = level now + (team 2025-26 - league 2025-26),
  level now = the 2026-27 preseason plus regular-season games so far (nba_ladder_track.level_now).
  Before a lane's first look on a game night the whole slate is checked; if the model's mean mu sits
  more than 4 points (1Q: 3) from Kalshi's median lines, or more than 80% of 5+ would-be picks are
  one side, the night is logged as "model level mismatch" and that lane enters nothing (nor its
  baseline) that night. The 2026-10-21 slate (10 of 13 team-total picks NO) is observed only; the
  first night entered is 2026-10-22 (FIRST_NIGHT).
WHY 18-26h. Team-total ladders open about 48 hours before tip; the 1Q ladder for the 2026-10-21
  slate opened about 20 hours before a 7pm ET tip, so a 20-26h window would have had no 1Q ladder
  to look at. The early window is 18-26h for both, and the look is the first read with a ladder.
CAVEATS. There is no historical Kalshi NBA team-total price data, so this is the first test of
  whether Kalshi's prices sit below the model. Early in the season the model is mostly last
  season's averages (rosters change; 2025-26's first five games ran +3.3 points above the model,
  2024-25's ran -1.0). The model's own calibration must hold on 2026-27; the Ladder tracker on the
  NBA page shows it against Kalshi's prices. Read at 10+ settled entries for Olu's review and at
  30 for a verdict.

AMENDMENT 2026-10-24 (Olu): the model's own season-data level stays the driver (no change to mu);
Kalshi's slate level is logged as a CHECK (nba_ladder_track.night_levels, "Model level v Kalshi level"
on the NBA page). The level guard no longer skips a one-sided night: more than 80% of 5+ would-be
picks on one side is logged as a lean label ("model leans under: ... Kalshi lines running X pts
above results season to date") and the lane still looks. A model-Kalshi gap over 4 points (1Q: 3) is a
warning; only a gap over 8 points (1Q: 6) is a data problem that skips the night. Past entries stand.

How it runs: nba-value.yml, hourly (settles, tracks, refreshes the tip schedule) and asked for by
the VPS from inside each tip's two windows (scripts/vps_window_requests.sh, lane_windows).
"""
import datetime as dt
import json
import os
import urllib.parse
from zoneinfo import ZoneInfo

import daily_track as D
import nba_ladder_track as T
import nba_value_model as M

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "data", "nba_value_ledger.json")
REGISTERED = "2026-10-21"
TT_1H, TT_24H, Q1_1H, Q1_24H = "nba_tt_value_1h", "nba_tt_value_24h", "nba_1q_value_1h", "nba_1q_value_24h"
LANES = (TT_24H, TT_1H, Q1_24H, Q1_1H)       # look order inside one run: the early lanes first
KIND = {TT_1H: "tt", TT_24H: "tt", Q1_1H: "q1", Q1_24H: "q1"}
SERIES = {"tt": T.SERIES_TT, "q1": T.SERIES_Q1}
WINDOW_MIN = {TT_1H: (60, 90), Q1_1H: (60, 90), TT_24H: (18 * 60, 26 * 60), Q1_24H: (18 * 60, 26 * 60)}
EDGE_MIN = 0.05
MAX_SPREAD = 0.03
PRICE = (0.25, 0.92)
FEE = 0.07
EPS = 1e-9
SCHEDULE_DAYS = 3
# The first game night the lanes may enter (2026-10-21, Olu): the level anchor and guard were added
# that evening, after the 2026-10-21 slate showed 10 of 13 team-total picks as NO, so that slate
# is observed by the tracker but never entered.
FIRST_NIGHT = "2026-10-22"
BASE = {lane: "base_" + lane for lane in LANES}
CT = ZoneInfo("America/Chicago")
NAMES = {TT_1H: "NBA team total · model value · 1h", TT_24H: "NBA team total · model value · 24h",
         Q1_1H: "NBA 1Q total · model value · 1h", Q1_24H: "NBA 1Q total · model value · 24h"}
_MODEL = ("Model: team points ~ Normal(mu, 11.83), 1Q game total ~ Normal(mu_q1, 8.28); each team's "
          "rates blend its 2025-26 per-game average with this season's at weight n/(n+8); "
          "mu = L + 0.894·((scoring − L) + (opponent allowing − L)) ± 0.85 home/away, "
          "mu_q1 = 2L + 0.5·(four 1Q deviations). ")
_RULE = ("Per {unit}, the single best side and rung by fee-adjusted edge P − (price + 0.07·price·(1−price)), "
         "taken at edge ≥ 0.05, two-sided quote with spread ≤3c, side price 0.25-0.92. One look per game "
         "(the first read in the window with a ladder), one frozen entry per {unit}; a ticker another "
         "lane of this family holds is skipped. Kalshi's result, 7% fee, z clustered by game night. "
         "Blind baseline: the YES on every rung at 0.25-0.92 with the same quote at the look. Paper, Sandbox only.")
DEFINITION = {
    TT_1H: "Kalshi NBA team totals (KXNBATEAMTOTAL), entered 60-90 min before tip. " + _MODEL + _RULE.format(unit="team"),
    TT_24H: "Kalshi NBA team totals (KXNBATEAMTOTAL), entered 18-26 h before tip. " + _MODEL + _RULE.format(unit="team"),
    Q1_1H: "Kalshi NBA 1st-quarter game total (KXNBA1QTOTAL), entered 60-90 min before tip. " + _MODEL + _RULE.format(unit="game"),
    Q1_24H: "Kalshi NBA 1st-quarter game total (KXNBA1QTOTAL), entered 18-26 h before tip. " + _MODEL + _RULE.format(unit="game"),
}
PREREG = (
    "PRE-REGISTERED 2026-10-21. Fitted on 2024-25 and checked out of sample on 2025-26, point-in-time: "
    "model P within 1.6pp of the hit rate in every 10pp bucket (team totals, Brier 0.142) and 1.9pp (1Q, "
    "Brier 0.143); home term kept (Brier 0.14227 v 0.14265). Research table, last two seasons, 4,304 "
    "team-games, crossing 105.5/109.5/113.5 by expected points (scored + opponent allowed)/2: <109 "
    "44/30/20%, 109-111 59/50/34, 111-113 65/53/39, 113-115 73/64/51, 115-117 82/73/59, 117-119 "
    "87/80/68, 119+ 93/87/78. Caveats: no historical Kalshi NBA team-total prices exist, so this is the "
    "first test of whether Kalshi's prices sit below the model; early-season shrinkage leans on last "
    "season's averages; the model's own calibration must hold. Read at 10+ settled entries for review, "
    "30 for a verdict. Added the evening of 2026-10-21, before any entry: each team's 2025-26 prior is "
    "re-anchored to the 2026-27 scoring level (preseason plus regular season so far: team prior = level now "
    "+ (team 2025-26 − league 2025-26)); a level guard skips a lane's whole night when the model's mean mu "
    "sits more than 4 points (1Q: 3) from Kalshi's median lines or more than 80% of 5+ would-be picks are "
    "one side; the first night entered is 2026-10-22. AMENDMENT 2026-10-24: the model's season-data level stays "
    "the driver and Kalshi's slate level is logged as a check; a one-sided night is logged with a lean label "
    "instead of skipping the lane, a gap over 4 points (1Q: 3) is a warning, and only a gap over 8 points "
    "(1Q: 6) skips the night. Past entries stand.")


def fee(p):
    return FEE * p * (1 - p)


def cost(p):
    return p + fee(p)


def empty():
    return {"version": "nba-value-v1", "registered": REGISTERED,
            "rules": {k: {"picks": []} for k in (*LANES, *BASE.values())},
            "looks": {}, "checks": {}, "runs": [], "schedule": []}


def load(path=PATH):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return empty()


# ---------- quotes, sides and the pick ----------

def quote(m):
    """(bid, ask) for a two-sided YES quote with spread at most 3c, else None."""
    b, a = D.number(m.get("yes_bid_dollars")), D.number(m.get("yes_ask_dollars"))
    if b is None or a is None or not 0 < b < a < 1 or a - b > MAX_SPREAD + EPS:
        return None
    return b, a


def in_price(p):
    return PRICE[0] - EPS <= p <= PRICE[1] + EPS


def sides(line, p_yes, bid, ask):
    """[(side, price, P, edge)] for the YES and the NO of one rung."""
    out = []
    for side, price, p in (("yes", ask, p_yes), ("no", round(1 - bid, 4), 1 - p_yes)):
        out.append((side, price, p, p - cost(price)))
    return out


def candidates(ms, g, kind, model, taken=()):
    """Every side of every quoted rung that clears the bar, as dicts, for one ladder.

    Each carries unit (team code or "game"), ticker, line, side, price, p, edge, bid, ask."""
    out = []
    for m in ms:
        if str(m.get("status") or "").lower() not in ("active", "open"):
            continue
        s, q = T.strike(m), quote(m)
        if s is None or q is None or m.get("ticker") in taken:
            continue
        if kind == "tt":
            unit = T.team_of(m.get("ticker"), g)
            mu, sd = (model["mu"].get(unit), model["sd"]) if unit else (None, None)
        else:
            unit, mu, sd = "game", model.get("mu_q1"), model.get("sd_q1")
        if unit is None or mu is None:
            continue
        p_yes = M.p_over(s, mu, sd)
        for side, price, p, edge in sides(s, p_yes, *q):
            if in_price(price) and edge >= EDGE_MIN - EPS:
                out.append(dict(unit=unit, ticker=m["ticker"], line=s, side=side, price=round(price, 4),
                                p=round(p, 4), edge=round(edge, 4), bid=q[0], ask=q[1], mu=round(mu, 2),
                                title=m.get("yes_sub_title") or m.get("title")))
    return out


def best(cands):
    """{unit: the single best candidate}: highest edge, a tie to the lower strike, then YES."""
    out = {}
    for c in sorted(cands, key=lambda c: (-c["edge"], c["line"], c["side"] != "yes")):
        out.setdefault(c["unit"], c)
    return out


def baseline(ms, g, kind, model):
    """The YES on every rung with the same quote and a YES ask of 0.25-0.92."""
    out = []
    for m in ms:
        if str(m.get("status") or "").lower() not in ("active", "open"):
            continue
        s, q = T.strike(m), quote(m)
        if s is None or q is None or not in_price(q[1]):
            continue
        if kind == "tt":
            unit = T.team_of(m.get("ticker"), g)
            mu, sd = (model["mu"].get(unit), model["sd"]) if unit else (None, None)
        else:
            unit, mu, sd = "game", model.get("mu_q1"), model.get("sd_q1")
        if unit is None:
            continue
        p = M.p_over(s, mu, sd) if mu is not None else None
        out.append(dict(unit=unit, ticker=m["ticker"], line=s, side="yes", price=round(q[1], 4),
                        p=None if p is None else round(p, 4), edge=None if p is None else round(p - cost(q[1]), 4),
                        bid=q[0], ask=q[1], mu=None if mu is None else round(mu, 2),
                        title=m.get("yes_sub_title") or m.get("title")))
    return out


def has_ladder(ms):
    return any(str(m.get("status") or "").lower() in ("active", "open") and T.strike(m) is not None
               and (lambda b, a: b is not None and a is not None and 0 < b < a < 1)(
                   D.number(m.get("yes_bid_dollars")), D.number(m.get("yes_ask_dollars"))) for m in ms)


# ---------- windows ----------

def lead_min(g, now):
    t = T.start_of(g)
    return None if t is None else (t - now).total_seconds() / 60


def in_window(lane, g, now):
    lead = lead_min(g, now)
    lo, hi = WINDOW_MIN[lane]
    return lead is not None and lo <= lead <= hi


def due(lane, games, now):
    return [g for g in games.values() if not g.get("completed") and in_window(lane, g, now)
            and (T.night(g) or "") >= FIRST_NIGHT]


def schedule(games, now):
    """Tip-offs of unplayed games in the next SCHEDULE_DAYS days, ISO UTC, sorted."""
    out = set()
    for g in games.values():
        t = T.start_of(g)
        if t and not g.get("completed") and now - dt.timedelta(hours=1) <= t <= now + dt.timedelta(days=SCHEDULE_DAYS):
            out.add(t.astimezone(dt.timezone.utc).isoformat())
    return sorted(out)


# ---------- entries ----------

def entry(lane, g, c, now, ev):
    t = T.start_of(g)
    unit = c["unit"]
    eid = f"{lane}:{g['id']}:{unit}" if lane in LANES else f"{lane}:{c['ticker']}"
    side_word = "over" if c["side"] == "yes" else "under"
    who = unit if unit != "game" else "1Q"
    return dict(id=eid, rule=lane, game=g["id"], event=ev, ticker=c["ticker"], unit=unit, line=c["line"],
                side=c["side"], price=c["price"], p=c["p"], edge=c["edge"], bid=c["bid"], ask=c["ask"], mu=c["mu"],
                match=f"{g['away']} @ {g['home']}", start=t.astimezone(dt.timezone.utc).isoformat(),
                night=T.night(g), lead_min=round((t - now).total_seconds() / 60, 1), title=c.get("title"),
                logged=now.isoformat(), status="open",
                why=(f"{who} {side_word} {c['line']} {c['side'].upper()} {c['price']:.2f}"
                     + (f" · model {c['p']:.2f} · edge {c['edge']:+.3f}" if c.get("p") is not None else "")))


def held(state):
    """Tickers any lane of the family holds."""
    return {p["ticker"] for lane in LANES for p in state["rules"][lane]["picks"]}


def look(state, lane, g, ms, ev, model, now):
    """One lane's look at one game: (entries, baseline entries). Records the look."""
    kind = KIND[lane]
    taken = held(state)
    picks = [entry(lane, g, c, now, ev) for _u, c in sorted(best(candidates(ms, g, kind, model, taken)).items())]
    base = [entry(BASE[lane], g, c, now, ev) for c in baseline(ms, g, kind, model)]
    state["looks"][f"{lane}:{g['id']}"] = dict(at=now.isoformat(), event=ev, picks=[p["id"] for p in picks],
                                               baseline=len(base), mu=model.get("mu"), mu_q1=model.get("mu_q1"))
    return picks, base


# ---------- settlement and stats ----------

def settle(state, now, fetch):
    errs = []
    for lane in state["rules"].values():
        for row in lane["picks"]:
            if row["status"] != "open":
                continue
            try:
                mk = fetch("markets/" + urllib.parse.quote(row["ticker"], safe="")).get("market", {})
                px = D.payout(mk)
                if px is None:
                    continue
                pay = px if row["side"] == "yes" else 1 - px
                row.update(payout=pay, profit=round(100 * (pay / cost(row["price"]) - 1), 2),
                           status="won" if pay == 1 else "lost" if pay == 0 else "no_result", settled=now.isoformat())
            except Exception as e:                              # noqa: BLE001
                errs.append(row["id"] + ": " + str(e)[:80])
    return errs


def stats(picks):
    """n (won+lost), n_price (no result), won, expected, z (night-clustered), nights, roi_fee, open."""
    wl = [p for p in picks if p["status"] in ("won", "lost")]
    done = wl + [p for p in picks if p["status"] == "no_result"]
    won = sum(p["status"] == "won" for p in wl)
    exp = sum(p["price"] for p in wl)
    iid = sum(p["price"] * (1 - p["price"]) for p in wl)
    nights = {}
    for p in wl:
        nights.setdefault(p.get("night") or p.get("start", "")[:10], []).append(p)
    clus = sum(sum((p["status"] == "won") - p["price"] for p in ps) ** 2 for ps in nights.values())
    var = max(iid, clus)
    return dict(n=len(wl), n_price=len(done) - len(wl), won=won, expected=exp,
                z=(won - exp) / var ** 0.5 if var > 0 else 0.0,
                z_iid=(won - exp) / iid ** 0.5 if iid > 0 else 0.0, nights=len(nights),
                roi_fee=sum(p.get("profit") or 0 for p in done) / (100 * len(done)) if done else None,
                model_exp=sum(p["p"] for p in wl if p.get("p") is not None),
                open=sum(p["status"] == "open" for p in picks))


# ---------- the run ----------

# ---------- the level guard (2026-10-21) ----------
# The model's level can sit away from the market's for reasons it cannot see (rosters, rule or
# pace changes). Before a lane's first look on a night, the whole slate is checked; a night that
# fails is logged as "model level mismatch" and that lane takes no entries (nor baseline) on it.
GAP_MAX = {"tt": 4.0, "q1": 3.0}        # |mean(model mu - Kalshi's median line)|, points: a WARNING since 2026-10-24
GAP_BLOCK = {"tt": 8.0, "q1": 6.0}      # past this the level is a data problem: the lane skips the night
SIDE_MAX = 0.80                         # share of the slate's would-be picks on one side
SIDE_MIN_N = 5


def market_median(rows):
    """The line where Kalshi's YES mid crosses 0.50, interpolated between rungs, from [(line, mid)].

    Outside the quoted range it is the nearest rung's line; None with no rung."""
    rows = sorted(rows)
    if not rows:
        return None
    for (l1, m1), (l2, m2) in zip(rows, rows[1:]):
        if m1 >= 0.5 >= m2 and m1 != m2:
            return l1 + (m1 - 0.5) / (m1 - m2) * (l2 - l1)
    return min(rows, key=lambda r: (abs(r[1] - 0.5), r[0]))[0]


def ladder_medians(ms, g, kind):
    """{unit: Kalshi's median line} from the two-sided YES mids of one event's rungs."""
    by = {}
    for m in ms:
        if str(m.get("status") or "").lower() not in ("active", "open"):
            continue
        s = T.strike(m)
        b, a = D.number(m.get("yes_bid_dollars")), D.number(m.get("yes_ask_dollars"))
        if s is None or b is None or a is None or not 0 < b < a < 1:
            continue
        unit = T.team_of(m.get("ticker"), g) if kind == "tt" else "game"
        if unit:
            by.setdefault(unit, []).append((s, (a + b) / 2))
    return {u: market_median(r) for u, r in by.items()}


def lean_label(sides, season_gap=None):
    """'model leans under: ...' when 5+ would-be picks are more than 80% one side, else None (2026-10-24)."""
    n = len(sides)
    if n < SIDE_MIN_N:
        return None
    yes, no = sides.count("yes"), sides.count("no")
    if max(yes, no) / n <= SIDE_MAX + EPS:
        return None
    word = "under" if no > yes else "over"
    if not season_gap or not season_gap.get("n") or season_gap.get("avg") is None:
        return f"model leans {word}: {max(yes, no) / n:.0%} of {n} would-be picks, no season-to-date results gap yet"
    avg = season_gap["avg"]
    return (f"model leans {word}: {max(yes, no) / n:.0%} of {n} would-be picks; Kalshi lines running {abs(avg):.1f} pts "
            f"{'above' if avg < 0 else 'below'} results season to date ({season_gap['n']} team-games)")


def check_verdict(gaps, sides, kind, season_gap=None):
    """(ok, reason, mean gap, one-side share, lean, warning) for a night's gaps and would-be pick sides.

    Amended 2026-10-24: Kalshi's level is a CHECK, the model's season-data level the driver. A one-sided
    night no longer skips the lane: it is logged with a lean label. A gap past GAP_MAX is a warning; only
    a gap past GAP_BLOCK (a data problem) blocks."""
    mean = sum(gaps) / len(gaps) if gaps else None
    share = max(sides.count("yes"), sides.count("no")) / len(sides) if sides else None
    if mean is not None and abs(mean) > GAP_BLOCK[kind]:
        return False, f"model level mismatch: model {mean:+.1f} pts v Kalshi's median line (a data problem)", mean, share, None, None
    warning = (f"warning: model {mean:+.1f} pts v Kalshi's median line (over {GAP_MAX[kind]:g})"
               if mean is not None and abs(mean) > GAP_MAX[kind] else None)
    return True, None, mean, share, lean_label(sides, season_gap), warning


def slate_check(lane, night, games, now, fetch, pri, cache, season_gap=None):
    """The night's level check for one lane, over every unplayed game of that night with a ladder."""
    kind = KIND[lane]
    gaps, sides, n = [], [], 0
    for g in sorted(games.values(), key=lambda g: (str(g.get("start")), g["id"])):
        t = T.start_of(g)
        if g.get("completed") or T.night(g) != night or t is None or t < now:
            continue
        if (kind, g["id"]) not in cache:
            cache[(kind, g["id"])] = T.event_markets(SERIES[kind], g, fetch)
        ev, ms = cache[(kind, g["id"])]
        if not ev:
            continue
        n += 1
        model = T.model_for(g, games, pri, at=now)
        for unit, med in ladder_medians(ms, g, kind).items():
            mu = model["mu"].get(unit) if kind == "tt" else model.get("mu_q1")
            if med is not None and mu is not None:
                gaps.append(mu - med)
        sides += [c["side"] for c in best(candidates(ms, g, kind, model)).values()]
    ok, reason, mean, share, lean, warning = check_verdict(gaps, sides, kind, season_gap)
    return dict(at=now.isoformat(), games=n, gaps=len(gaps), gap_mean=None if mean is None else round(mean, 2),
                picks=len(sides), yes=sides.count("yes"), no=sides.count("no"),
                share=None if share is None else round(share, 3), ok=ok, reason=reason, lean=lean, warning=warning)


def run(state, track_state, now=None, fetch=D.get, pri=None, season_gap=None):
    """Look at every due game for every lane, then settle. Returns the new lane entry ids."""
    now = now or dt.datetime.now(dt.timezone.utc)
    for k in (*LANES, *BASE.values()):
        state["rules"].setdefault(k, {"picks": []})
    state.setdefault("looks", {})
    games = track_state.get("games") or {}
    pri = M.prior() if pri is None else pri
    seen = {p["id"] for lane in state["rules"].values() for p in lane["picks"]}
    log, errs = [], []
    st = dict(due=0, looked=0, entered=0, baseline=0)
    cache = {}
    for lane in LANES:
        for g in sorted(due(lane, games, now), key=lambda g: (str(g.get("start")), g["id"])):
            if f"{lane}:{g['id']}" in state["looks"]:
                continue
            st["due"] += 1
            kind = KIND[lane]
            try:
                if (kind, g["id"]) not in cache:
                    cache[(kind, g["id"])] = T.event_markets(SERIES[kind], g, fetch)
                ev, ms = cache[(kind, g["id"])]
            except Exception as e:                              # noqa: BLE001
                errs.append(f"{lane} {g['away']}@{g['home']}: {str(e)[:80]}")
                continue
            if not ev or not has_ladder(ms):
                continue                                       # no ladder yet: a later read looks
            model = T.model_for(g, games, pri, at=now)
            ckey = f"{lane}:{T.night(g)}"
            if ckey not in state.setdefault("checks", {}):
                try:
                    state["checks"][ckey] = slate_check(lane, T.night(g), games, now, fetch, pri, cache, season_gap)
                except Exception as e:                          # noqa: BLE001
                    errs.append(f"{ckey} check: {str(e)[:80]}")
                    continue
            chk = state["checks"][ckey]
            if not chk["ok"]:
                state["looks"][f"{lane}:{g['id']}"] = dict(at=now.isoformat(), event=ev, picks=[], baseline=0,
                                                           blocked=chk["reason"], mu=model.get("mu"),
                                                           mu_q1=model.get("mu_q1"))
                st["looked"] += 1
                st["blocked"] = st.get("blocked", 0) + 1
                continue
            picks, base = look(state, lane, g, ms, ev, model, now)
            st["looked"] += 1
            for p in picks + base:
                if p["id"] in seen:
                    continue
                state["rules"][p["rule"]]["picks"].append(p)
                seen.add(p["id"])
                if p["rule"] in LANES:
                    log.append(p["id"])
                    st["entered"] += 1
                else:
                    st["baseline"] += 1
    errs += settle(state, now, fetch)
    state["schedule"] = schedule(games, now)
    state["last_run"] = now.isoformat()
    state["error"] = "; ".join(errs)[:1000] or None
    state["runs"] = (state.get("runs") or [])[-50:] + [dict(at=now.isoformat(), new=len(log), **st)]
    return log


def board(track_state, now=None, fetch=D.get, pri=None, lanes=(TT_1H, Q1_1H)):
    """What the 1h lanes would pick right now on every unplayed game (a probe, no writes)."""
    now = now or dt.datetime.now(dt.timezone.utc)
    games = track_state.get("games") or {}
    pri = M.prior() if pri is None else pri
    out = []
    for g in sorted(games.values(), key=lambda g: (str(g.get("start")), g["id"])):
        t = T.start_of(g)
        if g.get("completed") or t is None or not now <= t <= now + dt.timedelta(hours=30):
            continue
        model = T.model_for(g, games, pri, at=now)
        for lane in lanes:
            kind = KIND[lane]
            ev, ms = T.event_markets(SERIES[kind], g, fetch)
            if not ev:
                out.append(dict(lane=lane, game=f"{g['away']} @ {g['home']}", start=g["start"], pick=None, note="no event"))
                continue
            picks = best(candidates(ms, g, kind, model))
            if not picks:
                out.append(dict(lane=lane, game=f"{g['away']} @ {g['home']}", start=g["start"], pick=None,
                                mu=model["mu"] if kind == "tt" else model["mu_q1"]))
            for u, c in sorted(picks.items()):
                out.append(dict(lane=lane, game=f"{g['away']} @ {g['home']}", start=g["start"], pick=c))
    return out


def main(argv=None):
    import sys
    argv = sys.argv[1:] if argv is None else argv
    now = dt.datetime.now(dt.timezone.utc)
    track_state = T.load()
    if "--board" in argv:
        T.refresh_games(track_state, now)
        for r in board(track_state, now):
            t = D.instant(str(r["start"]).replace("Z", "+00:00")).astimezone(CT)
            c = r["pick"]
            if c:
                print(f"{t:%a %H:%M} CT {r['game']:11} {r['lane']:16} {c['unit']:5} {c['line']:6} {c['side'].upper():3} "
                      f"P {c['p']:.3f} price {c['price']:.2f} edge {c['edge']:+.3f} (mu {c['mu']})")
            else:
                print(f"{t:%a %H:%M} CT {r['game']:11} {r['lane']:16} no pick {r.get('note') or ''} {r.get('mu') or ''}")
        return 0
    errs = T.run(track_state, now)                  # ESPN games, then the tracker
    state = load()
    new = run(state, track_state, now, season_gap=T.season_climb(track_state.get("tracked") or {}))
    T.save(track_state)
    tmp = PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=1, sort_keys=True)
        f.write("\n")
    os.replace(tmp, PATH)
    print("tracker", T.summary(track_state), "new", errs, "error", track_state.get("error"))
    print("lanes", state["runs"][-1], "new", new, "schedule", len(state["schedule"]), "error", state["error"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
