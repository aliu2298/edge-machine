#!/usr/bin/env python3
"""NBA Safe Card (2026-10-22): a Sandbox PAPER lane, one card of "safe" legs per NBA slate.

Paper only: not in Production, not in the Production feed, no PAIR_OVERRIDES entry, on its own
fresh record (data/nba_safe_card.json). Nothing is placed.

Once per slate (the ET game night), about 60-90 minutes before the slate's FIRST tip, it reads every
rung of four Kalshi ladders for every game still to tip that night and publishes a card of 3-4 legs
whose combined odds (1 / product of the prices) reach 1.70, or "no card tonight" with the reason.
Every leg carries a one-line written rationale built from the data, so Olu can learn from it and
revise the rules; every leg the funnel looked at is logged with the step that cut it.

MARKETS: KXNBATEAMTOTAL (both teams), KXNBA1QTOTAL, KXNBA1HTOTAL, KXNBATOTAL. Every rung, both
  sides: YES = over at the YES ask, NO = under at 1 - the YES bid.
MODEL P: Normal, mu from nba_ladder_track.model_for (nba_value_model, re-anchored to this season's
  level). Team total: mu_team, sd 11.83. 1Q game total: mu_q1, sd 8.28. Game total: mu_home +
  mu_away, sd 18.9 (point-in-time residuals of the model: 18.44 on 2024-25, the fit season, 19.11
  out of sample on 2025-26). 1H game total: 0.505 x the game mu, sd 13.0 -- NOT fitted: the model's
  history holds no first-half scores (the 2026-27 games in nba_pace.json put the 1H share at 0.510
  on 69 games, a check only). P(over L) = 1 - Phi((L - mu) / sd).
THE FUNNEL (the count after each step is logged every night):
  1. Price band: the side's price 0.84-0.95 inclusive, a two-sided quote, spread 3c or less.
  2. Model safety: model P 0.90 or more.
  3. Value: P at least the price + 0.03.
  4. Labels agree (data/nba_pace.json rolling labels: FT for team and game totals, q1 for 1Q, h1
     for 1H). Team-total OVER: own O+ and opponent D+; UNDER: own O- and opponent D-. Game total
     OVER: both D+; UNDER: both D-. 1Q/1H OVER: both O+; UNDER: both O-.
  5. Clean leg, team totals only: the team cleared (OVER) or stayed under (UNDER) that line in 8 of
     its last 10 games (2026-27 preseason plus regular season; with 5-9 games, 80% of them rounded
     up; fewer than 5 games: no check).
  6. Card: survivors ranked by edge (P - price), at most one leg per game, added until the combined
     odds reach 1.70 with at least 3 legs, at most 4. Four legs short of 1.70, or fewer than 3
     survivors, is "no card tonight" with the reason. (Arithmetic: three legs at 0.84 or more give
     at most 1.687, so in practice a card is four legs from four games.)
  7. Level check (amended 2026-10-24, below): the slate's mean model-minus-Kalshi-median gap on team
     totals; a data problem blocks, a one-sided slate is a lean label.
TIMING: built once, the first read 20-90 minutes before the slate's first tip, from the prices at
  that moment (legs for later games are priced then too). The price is read again 60-90 minutes
  before each leg's own tip as "price at tip", for comparison. The card is frozen once published.
SETTLEMENT: each leg on Kalshi's own result; the card wins only if every leg wins. Paper P/L: $1 a
  card (a win pays the combined odds), and $1 a leg after the 7% taker fee.

PRE-REGISTERED 2026-10-22. Wednesday 2026-10-21's back-run of this exact funnel: 62 legs after
steps 1-3, 16 after labels, and the card PHX@POR game U249.5 @84c, MIL@WSH 1Q U68.5 @85c,
UTAH@MEM 1H O104.5 @87c, GS@LAL game U253.5 @86c, combined odds 1.87, model combo chance about 70%.
2025-26 backtest: the model's 95% lines hit 94.4-94.9% across markets; a label-filtered daily 3-leg
card at the 95% line went 64/73 days. Caveat: the model sits about 2 points below Kalshi's lines
this season, so the funnel leans to unders, which is what the level guard is for. Read at 20+ cards.

AMENDMENT 2026-10-22 (Olu, before the first card): on a slate of fewer than 4 games a game may
supply up to 2 legs (still 3-4 legs, combined odds 1.70+, ranked by edge); on 4+ games, one leg per
game as before. Two legs of one game must be different markets (a team total of each team counts as
two), and never a pair where one largely implies the other in the same direction: game total with a
team total, 1H with the game total, or 1Q with 1H, both overs or both unders, is refused. Allowed,
e.g.: team total OVER + 1Q UNDER; home and away team-total OVERs; 1Q OVER + game UNDER. The card says
which game gave two legs and why, and its combo chance (the product of P) then assumes the legs are
independent. The 84-95c band is unchanged. The funnel logs the surviving legs per game.

AMENDMENT 2026-10-24 (Olu): the model's own season-data level stays the driver (no change to mu);
Kalshi's slate level is logged as a CHECK (nba_ladder_track.night_levels). Step 7 no longer blocks a
one-sided slate: more than 80% of 5+ label survivors on one side becomes a LABEL on the card, "model
leans under (or over): Kalshi lines running X pts above (below) results season to date" (the
season-to-date average of points minus Kalshi's 50c team-total line), named in the card rationale.
Only a data problem blocks: no model or Kalshi team-total level to compare, or a gap over 8 points.
A gap over 4 points is a warning on the card.

AMENDMENT 2026-10-24 (Olu), label step, until 2026-11-15 (Eastern): step 4 needs ONE side's label to
back the leg, not both. Team total OVER: own O+ OR opponent D+; UNDER: own O- OR opponent D-. Game
total OVER: at least one D+; UNDER: at least one D-. 1Q/1H OVER: at least one O+; UNDER: at least
one O-. The rule is chosen by the card's game night (LABEL_RULE_LOOSE_UNTIL = 2026-11-15): nights
before it use the loose rule, the night of 2026-11-15 and every later one the strict rule above,
automatically. A leg carries "labels: both agree" or "labels: one side (early-season rule)"; ranking
is by edge as before with a small bonus (BOTH_BONUS, half a cent) for both-agree legs; the funnel
counts both-agree and one-side survivors separately, and the page splits their hit rates, so the
two can be compared later. Cards already built are not rewritten: a leg with no label mode passed
under the strict rule and counts as both-agree.

How it runs: nba-safe-card.yml, asked for by the VPS 90-60 minutes before each tip
(lane_windows.nba_safe_windows, scripts/vps_window_requests.sh), with an hourly fallback that settles.
"""
import datetime as dt
import json
import math
import os
import urllib.parse

import daily_track as D
import nba_ladder_track as T
import nba_value as NV
import nba_value_model as M

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "data", "nba_safe_card.json")
PACE = os.path.join(ROOT, "data", "nba_pace.json")
REGISTERED = "2026-10-22"
FIRST_NIGHT = "2026-10-22"
SERIES = {"tt": "KXNBATEAMTOTAL", "q1": "KXNBA1QTOTAL", "h1": "KXNBA1HTOTAL", "game": "KXNBATOTAL"}
MARKET_WORD = {"tt": "", "q1": "1Q", "h1": "1H", "game": "game"}
LABEL_KEY = {"tt": "ft", "game": "ft", "q1": "q1", "h1": "h1"}
SD_TEAM = M.SD_TEAM            # 11.83
SD_Q1 = 8.28
SD_GAME = 18.9
SD_H1 = 13.0
H1_SHARE = 0.505
BAND = (0.84, 0.95)
MAX_SPREAD = 0.03
P_MIN = 0.90
VALUE_MIN = 0.03
ODDS_MIN = 1.70
LEGS_MIN, LEGS_MAX = 3, 4
CLEAN_N, CLEAN_SHARE, CLEAN_MIN_GAMES = 10, 0.8, 5
GAP_WARN = 4.0            # model v Kalshi's team-total level: a warning on the card
GAP_BLOCK = 8.0           # beyond this the level itself is a data problem: no card
SIDE_MAX, SIDE_MIN_N = 0.80, 5   # one side this often among 5+ label survivors: a lean LABEL, no block
BUILD_MIN = (20, 90)           # minutes before the slate's first tip: the card is built at the first read in here
TIP_MIN = (60, 90)             # minutes before a leg's own tip: "price at tip"
FEE = 0.07
EPS = 1e-9
SCHEDULE_DAYS = 3
PRESEASON = (dt.date(2026, 10, 2), dt.date(2026, 10, 19))
LABEL_RULE_LOOSE_UNTIL = "2026-11-15"   # Eastern game nights before this use the one-side label rule
BOTH_BONUS = 0.005                      # ranking edge bonus for a leg whose labels BOTH agree
LABEL_BOTH = "labels: both agree"
LABEL_ONE = "labels: one side (early-season rule)"
STEPS = ("band", "safety", "value", "labels", "clean", "card")
STEP_WORDS = {"band": "1 price 84-95c", "safety": "2 model P ≥ 0.90", "value": "3 P ≥ price + 3c",
              "labels": "4 labels agree", "clean": "5 clean 8/10 (team totals)", "card": "6 on the card"}


def fee(p):
    return FEE * p * (1 - p)


def empty():
    return {"version": "nba-safe-card-v1", "registered": REGISTERED, "cards": {}, "runs": [], "schedule": []}


def load(path=PATH):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return empty()


# ---------- model ----------

def mus(model):
    """{kind: (mu or {team: mu}, sd)} for one game's model."""
    home_away = model.get("mu") or {}
    game = sum(home_away.values()) if len(home_away) == 2 and None not in home_away.values() else None
    return {"tt": (home_away, SD_TEAM), "q1": (model.get("mu_q1"), SD_Q1),
            "game": (game, SD_GAME), "h1": (None if game is None else H1_SHARE * game, SD_H1)}


def p_over(line, mu, sd):
    return M.p_over(line, mu, sd)


# ---------- quotes and legs ----------

def quote(m):
    """(bid, ask) for a two-sided YES quote with spread at most 3c, else None."""
    b, a = D.number(m.get("yes_bid_dollars")), D.number(m.get("yes_ask_dollars"))
    if b is None or a is None or not 0 < b < a < 1 or a - b > MAX_SPREAD + EPS:
        return None
    return b, a


def side_price(side, bid, ask):
    return round(ask, 4) if side == "yes" else round(1 - bid, 4)


def in_band(p):
    return BAND[0] - EPS <= p <= BAND[1] + EPS


def legs_for(g, kind, ms, model):
    """Every side of every two-sided, 3c-or-tighter rung of one ladder, priced and modelled."""
    mu_kind, sd = mus(model)[kind]
    out = []
    for m in ms:
        if str(m.get("status") or "").lower() not in ("active", "open"):
            continue
        line, q = T.strike(m), quote(m)
        if line is None or q is None:
            continue
        if kind == "tt":
            unit = T.team_of(m.get("ticker"), g)
            mu = mu_kind.get(unit) if unit else None
        else:
            unit, mu = "game", mu_kind
        if unit is None or mu is None:
            continue
        p_yes = p_over(line, mu, sd)
        for side in ("yes", "no"):
            price = side_price(side, *q)
            p = p_yes if side == "yes" else 1 - p_yes
            out.append(dict(game=g["id"], match=f"{g['away']}@{g['home']}", kind=kind, unit=unit,
                            ticker=m["ticker"], line=line, side=side, price=price, p=round(p, 4),
                            edge=round(p - price, 4), mu=round(mu, 1), sd=sd, bid=q[0], ask=q[1],
                            start=g["start"]))
    return out


# ---------- labels and the clean-leg check ----------

def labels_by_game(path=PACE):
    """{espn game id: {home_ft, away_ft, home_q1, ...}} from nba_pace.json's rolling labels."""
    try:
        with open(path) as f:
            rows = json.load(f).get("games") or []
    except (OSError, ValueError):
        return {}
    out = {}
    for r in rows:
        out[str(r.get("id"))] = {f"{s}_{k}": r.get(f"roll_lab_{s}_{k}") for s in ("home", "away") for k in ("ft", "q1", "h1")}
    return out


def _o(lab):
    return (lab or "")[:2].replace("−", "-")


def _d(lab):
    return (lab or "")[2:].replace("−", "-")


def loose_labels(night):
    """Does the one-side label rule apply to this Eastern game night? (Amendment 2026-10-24.)"""
    return bool(night) and str(night) < LABEL_RULE_LOOSE_UNTIL


def label_check(leg, g, labs, loose=False):
    """(ok, words, mode) for step 4. `mode` is "both" when both labels the leg's market reads back its
    side, "one" when exactly one does (a pass only under the loose rule), None when none does or a
    label is missing. Strict: both. Loose: at least one."""
    k = LABEL_KEY[leg["kind"]]
    h, a = labs.get(f"home_{k}"), labs.get(f"away_{k}")
    if not h or not a:
        return False, "no labels", None
    over = leg["side"] == "yes"
    if leg["kind"] == "tt":
        own, opp = (h, a) if leg["unit"] == g["home"] else (a, h)
        parts = [_o(own) == ("O+" if over else "O-"), _d(opp) == ("D+" if over else "D-")]
        words = f"{leg['unit']} {own} v {opp}"
    elif leg["kind"] == "game":
        want = "D+" if over else "D-"
        parts = [_d(h) == want, _d(a) == want]
        words = f"{a} v {h}"
    else:
        want = "O+" if over else "O-"
        parts = [_o(h) == want, _o(a) == want]
        words = f"{k} {a} v {h}"
    mode = "both" if all(parts) else "one" if any(parts) else None
    ok = mode == "both" or (loose and mode == "one")
    return ok, words.replace("-", "−"), mode


def labels_agree(leg, g, labs):
    """(ok, words) for step 4 under the STRICT rule: both labels back the leg's side."""
    ok, words, _mode = label_check(leg, g, labs, loose=False)
    return ok, words


def team_points(track_games, preseason_rows, before):
    """{team: [(start, points)]} of games finished before `before`, oldest first."""
    out = {}
    for g in track_games.values():
        t = T.start_of(g)
        if not g.get("completed") or t is None or t >= before or g.get("pts_home") is None:
            continue
        out.setdefault(g["home"], []).append((t, g["pts_home"]))
        out.setdefault(g["away"], []).append((t, g["pts_away"]))
    for r in preseason_rows or ():
        t = D.instant(str(r["start"]).replace("Z", "+00:00"))
        if t and t < before:
            out.setdefault(r["team"], []).append((t, r["pts"]))
    return {k: sorted(v) for k, v in out.items()}


def clean(leg, pts):
    """(ok, words, hits, n) for step 5: the team's last 10 games against the line on the leg's side."""
    last = [p for _t, p in (pts.get(leg["unit"]) or [])][-CLEAN_N:]
    n = len(last)
    if n < CLEAN_MIN_GAMES:
        return True, f"clean check skipped ({n} games)", None, n
    hits = sum((p > leg["line"]) if leg["side"] == "yes" else (p < leg["line"]) for p in last)
    need = math.ceil(CLEAN_SHARE * n - EPS)
    word = "cleared" if leg["side"] == "yes" else "stayed under"
    return hits >= need, f"{word} {leg['line']:g} in {hits}/{n}", hits, n


# ---------- the funnel and the card ----------

def funnel(legs, games, labs_all, pts, loose=False):
    """Run steps 1-5 over every leg. Returns (logged legs with `passed` and `cut`, counts).
    `loose`: the one-side label rule (Amendment 2026-10-24); counts then also split the labels
    survivors into labels_both and labels_one."""
    counts = dict(quoted=len(legs), band=0, safety=0, value=0, labels=0, clean=0, labels_both=0, labels_one=0)
    logged = []
    for leg in legs:
        if not in_band(leg["price"]):
            continue
        counts["band"] += 1
        leg = dict(leg, passed=["band"], cut=None)
        g = games[leg["game"]]
        if leg["p"] < P_MIN - EPS:
            leg["cut"] = "safety"
        else:
            leg["passed"].append("safety")
            counts["safety"] += 1
            if leg["p"] < leg["price"] + VALUE_MIN - EPS:
                leg["cut"] = "value"
            else:
                leg["passed"].append("value")
                counts["value"] += 1
                ok, words, mode = label_check(leg, g, labs_all.get(str(g["id"])) or {}, loose)
                leg["labels"] = words
                if not ok:
                    leg["cut"] = "labels"
                else:
                    leg["passed"].append("labels")
                    counts["labels"] += 1
                    counts["labels_both" if mode == "both" else "labels_one"] += 1
                    leg["label_mode"] = mode
                    leg["label_note"] = LABEL_BOTH if mode == "both" else LABEL_ONE
                    if leg["kind"] == "tt":
                        ok, words, hits, n = clean(leg, pts)
                        leg.update(clean=words, clean_hits=hits, clean_n=n)
                    else:
                        ok = True
                    if not ok:
                        leg["cut"] = "clean"
                    else:
                        leg["passed"].append("clean")
                        counts["clean"] += 1
        logged.append(leg)
    return logged, counts


def odds_of(legs):
    prod = 1.0
    for leg in legs:
        prod *= leg["price"]
    return 1 / prod if prod > 0 else None


# AMENDED 2026-10-22 (Olu): on a slate of fewer than 4 games a game may supply up to 2 legs.
SMALL_SLATE = 4
# Two legs of one game where one largely implies the other in the same direction are refused:
# {game, team total}, {1H, game}, {1Q, 1H}, both overs or both unders.
IMPLIES = ({"game", "tt"}, {"h1", "game"}, {"q1", "h1"})


def per_game_cap(n_games):
    return 2 if n_games < SMALL_SLATE else 1


def pair_ok(a, b):
    """(ok, why) for two legs of the same game (the 2026-10-22 correlation guard)."""
    if a["kind"] == b["kind"] and a["unit"] == b["unit"]:
        return False, "the same market"
    if a["side"] == b["side"] and {a["kind"], b["kind"]} in IMPLIES:
        return False, f"{MARKET_WORD[a['kind']] or 'team total'} and {MARKET_WORD[b['kind']] or 'team total'} in the same direction"
    return True, None


def pick_card(survivors, cap=1):
    """(legs, reason): best edge first, at most `cap` legs per game (two only where pair_ok allows),
    until odds >= 1.70 with 3-4 legs."""
    ranked = sorted(survivors, key=lambda x: (-(x["edge"] + (BOTH_BONUS if x.get("label_mode") == "both" else 0.0)),
                                              x["price"], x["ticker"], x["side"]))
    card = []
    for leg in ranked:
        mine = [x for x in card if x["game"] == leg["game"]]
        if len(mine) >= cap or not all(pair_ok(x, leg)[0] for x in mine):
            continue
        card.append(leg)
        if len(card) >= LEGS_MIN and odds_of(card) >= ODDS_MIN - EPS:
            return card, None
        if len(card) == LEGS_MAX:
            break
    each = "one per game" if cap == 1 else "up to two per game"
    if len(card) < LEGS_MIN:
        return [], (f"no card tonight: only {len(card)} leg{'s' if len(card) != 1 else ''} can go on a card "
                    f"(a card needs {LEGS_MIN} to {LEGS_MAX} legs, {each})")
    return [], (f"no card tonight: {len(card)} legs reach only {odds_of(card):.2f}x, short of {ODDS_MIN:.2f}x "
                f"(prices 84-95c need four legs)")


def lean_text(side, season_gap):
    """The lean label: which way the model leans, and what the results say about Kalshi's lines.

    season_gap is nba_ladder_track.season_climb: points minus Kalshi's 50c team-total line, season to
    date (a negative average is Kalshi's lines running above the results)."""
    word = "under" if side == "no" else "over"
    if not season_gap or not season_gap.get("n") or season_gap.get("avg") is None:
        return f"model leans {word}: no season-to-date results gap yet"
    avg = season_gap["avg"]
    return (f"model leans {word}: Kalshi lines running {abs(avg):.1f} pts {'above' if avg < 0 else 'below'} "
            f"results season to date ({season_gap['n']} team-games)")


def level_check(medians, mu_by_team, survivor_sides, season_gap=None):
    """The slate's level check (step 7), 2026-10-24: dict(ok, reason, gap, share, lean, warning).

    The model's season-data level drives and Kalshi's is the check. A one-sided slate is no longer
    blocked: it becomes a lean LABEL on the card. Only a data problem blocks: no model or Kalshi
    team-total level to compare, or a gap over 8 points. A gap over 4 points is a warning."""
    gaps = [mu_by_team[t] - medians[t] for t in medians if t in mu_by_team and medians[t] is not None
            and mu_by_team[t] is not None]
    mean = sum(gaps) / len(gaps) if gaps else None
    n = len(survivor_sides)
    share = max(survivor_sides.count("yes"), survivor_sides.count("no")) / n if n else None
    out = dict(ok=True, reason=None, gap=mean, share=share, lean=None, warning=None)
    if mean is None:
        out.update(ok=False, reason="no card tonight: no Kalshi team-total level to compare with the model (a data problem)")
        return out
    if abs(mean) > GAP_BLOCK + EPS:
        out.update(ok=False, reason=f"no card tonight: model level {mean:+.1f} pts from Kalshi's team-total lines "
                                    f"(over {GAP_BLOCK:g}: a data problem)")
        return out
    if abs(mean) > GAP_WARN + EPS:
        out["warning"] = f"warning: model {mean:+.1f} pts from Kalshi's team-total lines (over {GAP_WARN:g})"
    if n >= SIDE_MIN_N and share > SIDE_MAX + EPS:
        out["lean"] = lean_text("no" if survivor_sides.count("no") > survivor_sides.count("yes") else "yes", season_gap)
    return out


def rationale(leg):
    """One line per leg, from the data."""
    what = (f"{leg['unit']} team total" if leg["kind"] == "tt" else f"{MARKET_WORD[leg['kind']]}")
    side = "OVER" if leg["side"] == "yes" else "UNDER"
    gap = leg["line"] - leg["mu"]
    where = f"line {gap:+.1f} {'above' if gap >= 0 else 'below'} mu"
    bits = [f"{leg['match']} {what} {side} {leg['line']:g} @{leg['price'] * 100:.0f}c: "
            f"model {leg['p'] * 100:.1f}% (mu {leg['mu']:.1f}, {where})"]
    if leg.get("labels"):
        held = {"tt": "attack and opposing defence agree", "game": "both defences agree",
                "q1": "both attacks agree", "h1": "both attacks agree"}[leg["kind"]]
        if leg.get("label_mode") == "one":
            bits.append(f"{LABEL_ONE}: {leg['labels']}")
        elif leg.get("label_mode") == "both":
            bits.append(f"{LABEL_BOTH}: {leg['labels']} ({held})")
        else:
            bits.append(f"labels {leg['labels']} ({held})")
    if leg.get("clean"):
        bits.append(leg["clean"])
    bits.append(f"edge {leg['edge'] * 100:+.1f}c")
    return "; ".join(bits)


def _label_words(counts):
    """'6 labels' or, under the loose rule, '6 labels (2 both agree, 4 one side)'."""
    if counts.get("labels_one") or counts.get("labels_both"):
        return f"{counts['labels']} labels ({counts.get('labels_both', 0)} both agree, {counts.get('labels_one', 0)} one side)"
    return f"{counts['labels']} labels"


def card_rationale(card, counts):
    note = "".join(f" {t}." for t in (card.get("lean"), card.get("warning")) if t)
    if not card["legs"]:
        return (f"{card['reason']}.{note} Funnel: {counts['quoted']} sides quoted → {counts['band']} in 84-95c → "
                f"{counts['safety']} model ≥0.90 → {counts['value']} with value → {_label_words(counts)} → "
                f"{counts['clean']} clean.")
    combo = 1.0
    for leg in card["legs"]:
        combo *= leg["p"]
    by = {}
    for leg in card["legs"]:
        by.setdefault(leg["match"], []).append(leg)
    shared = [m for m, ls in by.items() if len(ls) > 1]
    two = "".join(f" 2 legs from {m}: small slate, legs not same-direction." for m in shared)
    indep = " (assumes legs independent)" if shared else ""
    return (f"{len(card['legs'])} legs, combined odds {card['odds']:.2f}, the model's combo chance {combo * 100:.0f}%{indep}.{two}{note} "
            f"Funnel: {counts['quoted']} sides quoted → {counts['band']} in 84-95c → {counts['safety']} model ≥0.90 → "
            f"{counts['value']} with value → {_label_words(counts)} → {counts['clean']} clean → {len(card['legs'])} on the card.")


# ---------- preseason points (for the clean check) ----------

def preseason(state, fetch_day=None):
    """Per-team 2026-27 preseason points, fetched once from ESPN and kept in the ledger."""
    if state.get("preseason"):
        return state["preseason"]
    if fetch_day is None:
        import nba_pace
        fetch_day = nba_pace.fetch_day
    rows, d = [], PRESEASON[0]
    while d <= PRESEASON[1]:
        for r in fetch_day(d) or []:
            if r.get("season_type") != 1 or not r.get("completed") or r.get("ft_home") is None:
                continue
            if r.get("home") in M.TEAMS:
                rows.append(dict(start=r["start"], team=r["home"], pts=r["ft_home"]))
            if r.get("away") in M.TEAMS:
                rows.append(dict(start=r["start"], team=r["away"], pts=r["ft_away"]))
        d += dt.timedelta(days=1)
    state["preseason"] = rows
    return rows


# ---------- the build ----------

def slate(games, night, now):
    """The night's games still to tip, by tip time."""
    out = [g for g in games.values() if T.night(g) == night and not g.get("completed")
           and (T.start_of(g) or now) > now]
    return sorted(out, key=lambda g: (str(g.get("start")), g["id"]))


def first_tip(games, night):
    ts = [T.start_of(g) for g in games.values() if T.night(g) == night and T.start_of(g)]
    return min(ts) if ts else None


def build(night, games, now, fetch, pri, labs_all, pre_rows, season_gap=None):
    """The card for one night, from the prices now. `season_gap`: nba_ladder_track.season_climb."""
    todo = slate(games, night, now)
    pts = team_points(games, pre_rows, now)
    legs, medians, mu_team = [], {}, {}
    for g in todo:
        model = T.model_for(g, games, pri, at=now)
        for team, mu in (model.get("mu") or {}).items():
            mu_team[team] = mu
        for kind, series in SERIES.items():
            _ev, ms = T.event_markets(series, g, fetch)
            legs += legs_for(g, kind, ms, model)
            if kind == "tt":
                medians.update(NV.ladder_medians(ms, g, "tt"))
    loose = loose_labels(night)
    logged, counts = funnel(legs, {g["id"]: g for g in todo}, labs_all, pts, loose=loose)
    survivors = [leg for leg in logged if leg["cut"] is None]
    label_sides = [leg["side"] for leg in logged if "labels" in leg["passed"]]
    chk = level_check(medians, mu_team, label_sides, season_gap)
    ok, reason, gap, share = chk["ok"], chk["reason"], chk["gap"], chk["share"]
    card_legs = []
    cap = per_game_cap(len(todo))
    if len(todo) * cap < LEGS_MIN:
        reason = (f"no card tonight: only {len(todo)} game{'s' if len(todo) != 1 else ''} on the slate "
                  f"(a card needs {LEGS_MIN} to {LEGS_MAX} legs, at most {cap} per game)")
    elif ok:
        card_legs, reason = pick_card(survivors, cap)
    chosen = {(leg["ticker"], leg["side"]) for leg in card_legs}
    for leg in logged:
        if (leg["ticker"], leg["side"]) in chosen:
            leg["passed"].append("card")
        elif leg["cut"] is None:
            leg["cut"] = "card" if ok else "guard"
        leg.update(status="open", rationale=rationale(leg))
    card_legs = [leg for leg in logged if "card" in leg["passed"]]
    card_legs.sort(key=lambda x: (x["start"], x["ticker"]))
    card = dict(night=night, built_at=now.isoformat(), first_tip=None, games=len(todo),
                legs=card_legs, odds=None if not card_legs else round(odds_of(card_legs), 3),
                combo_p=None if not card_legs else round(math.prod(leg["p"] for leg in card_legs), 4),
                reason=reason, status="open" if card_legs else "no_card", counts=dict(counts, card=len(card_legs)),
                per_game_cap=cap, label_rule="loose" if loose else "strict",
                survivors_by_game={m: sum(1 for x in survivors if x["match"] == m)
                                                     for m in sorted({x["match"] for x in survivors})},
                legs_by_game={m: sum(1 for x in card_legs if x["match"] == m) for m in sorted({x["match"] for x in card_legs})},
                guard=dict(ok=ok, gap=None if gap is None else round(gap, 2), share=None if share is None else round(share, 3),
                           lean=chk["lean"], warning=chk["warning"]),
                lean=chk["lean"], warning=chk["warning"],
                candidates=[leg for leg in logged if "card" not in leg["passed"]])
    ft = first_tip(games, night)
    card["first_tip"] = ft.isoformat() if ft else None
    card["lead_min"] = round((ft - now).total_seconds() / 60, 1) if ft else None
    card["rationale"] = card_rationale(card, counts)
    return card


def price_now(leg, fetch):
    m = fetch("markets/" + urllib.parse.quote(leg["ticker"], safe="")).get("market", {})
    q = quote(m) or (lambda b, a: (b, a) if b is not None and a is not None and 0 < b < a < 1 else None)(
        D.number(m.get("yes_bid_dollars")), D.number(m.get("yes_ask_dollars")))
    return None if q is None else side_price(leg["side"], *q)


def tip_prices(state, now, fetch):
    """'Price at tip': each card leg's price again 60-90 minutes before its own tip, once."""
    errs = []
    for card in state["cards"].values():
        for leg in card.get("legs") or []:
            t = D.instant(str(leg["start"]).replace("Z", "+00:00"))
            if leg.get("price_at_tip") is not None or t is None:
                continue
            lead = (t - now).total_seconds() / 60
            if TIP_MIN[0] <= lead <= TIP_MIN[1]:
                try:
                    leg["price_at_tip"] = price_now(leg, fetch)
                    leg["price_at_tip_at"] = now.isoformat()
                except Exception as e:                          # noqa: BLE001
                    errs.append(f"{leg['ticker']} tip price: {str(e)[:60]}")
    return errs


def settle(state, now, fetch):
    """Every logged leg (card and cut) on Kalshi's result, then each card."""
    errs = []
    for card in state["cards"].values():
        for leg in (card.get("legs") or []) + (card.get("candidates") or []):
            if leg.get("status") != "open":
                continue
            try:
                m = fetch("markets/" + urllib.parse.quote(leg["ticker"], safe="")).get("market", {})
                px = D.payout(m)
                if px is None:
                    continue
                pay = px if leg["side"] == "yes" else 1 - px
                leg.update(payout=pay, status="won" if pay == 1 else "lost" if pay == 0 else "no_result",
                           profit=round(pay / (leg["price"] + fee(leg["price"])) - 1, 4), settled=now.isoformat())
            except Exception as e:                              # noqa: BLE001
                errs.append(f"{leg['ticker']}: {str(e)[:60]}")
        legs = card.get("legs") or []
        if card.get("status") == "open" and legs:
            st = [leg["status"] for leg in legs]
            if "lost" in st:
                card.update(status="lost", profit=-1.0, settled=now.isoformat())
            elif all(s == "won" for s in st):
                card.update(status="won", profit=round(card["odds"] - 1, 4), settled=now.isoformat())
            elif "open" not in st:
                card.update(status="no_result", profit=0.0, settled=now.isoformat())
    return errs


def schedule(games, now):
    out = set()
    for g in games.values():
        t = T.start_of(g)
        if t and not g.get("completed") and now - dt.timedelta(hours=1) <= t <= now + dt.timedelta(days=SCHEDULE_DAYS):
            out.add(t.astimezone(dt.timezone.utc).isoformat())
    return sorted(out)


def run(state, games, now=None, fetch=D.get, pri=None, labs_all=None, fetch_day=None, season_gap=None):
    """Build tonight's card when its window is open, log tip prices, settle. Returns new card nights."""
    now = now or dt.datetime.now(dt.timezone.utc)
    state.setdefault("cards", {})
    pri = M.prior() if pri is None else pri
    labs_all = labels_by_game() if labs_all is None else labs_all
    built, errs = [], []
    nights = sorted({T.night(g) for g in games.values() if T.night(g) and T.night(g) >= FIRST_NIGHT})
    for night in nights:
        if night in state["cards"]:
            continue
        ft = first_tip(games, night)
        if ft is None:
            continue
        lead = (ft - now).total_seconds() / 60
        if not BUILD_MIN[0] <= lead <= BUILD_MIN[1]:
            continue
        try:
            pre_rows = preseason(state, fetch_day)
            state["cards"][night] = build(night, games, now, fetch, pri, labs_all, pre_rows, season_gap)
            built.append(night)
        except Exception as e:                                  # noqa: BLE001
            errs.append(f"{night} build: {str(e)[:120]}")
    errs += tip_prices(state, now, fetch)
    errs += settle(state, now, fetch)
    state["schedule"] = schedule(games, now)
    state["last_run"] = now.isoformat()
    state["error"] = "; ".join(errs)[:1000] or None
    state["runs"] = (state.get("runs") or [])[-50:] + [dict(at=now.isoformat(), built=built)]
    return built


# ---------- records (for the page) ----------

def records(state):
    cards = list(state.get("cards", {}).values())
    played = [c for c in cards if c.get("legs")]
    done = [c for c in played if c.get("status") in ("won", "lost")]
    legs = [leg for c in played for leg in c["legs"]]
    legs_done = [leg for leg in legs if leg.get("status") in ("won", "lost")]
    every = [leg for c in cards for leg in (c.get("legs") or []) + (c.get("candidates") or [])]
    steps = []
    for s in STEPS:
        rows = [leg for leg in every if s in (leg.get("passed") or []) and leg.get("status") in ("won", "lost")]
        n = len(rows)
        steps.append(dict(step=s, n=n, won=sum(leg["status"] == "won" for leg in rows),
                          price=sum(leg["price"] for leg in rows) / n if n else None,
                          p=sum(leg["p"] for leg in rows) / n if n else None))
    calib = []
    for lo, hi in ((0.90, 0.93), (0.93, 0.96), (0.96, 1.0001)):
        rows = [leg for leg in legs_done if lo <= leg["p"] < hi]
        if rows:
            calib.append(dict(lo=lo, hi=min(hi, 1.0), n=len(rows), won=sum(leg["status"] == "won" for leg in rows),
                              p=sum(leg["p"] for leg in rows) / len(rows)))
    # Every logged leg that passed the labels and settled, split by how many labels backed it (a leg
    # logged before the 2026-10-24 amendment has no mode: it passed under the strict rule, so both).
    modes = {}
    for m in ("both", "one"):
        rows = [leg for leg in every if "labels" in (leg.get("passed") or []) and leg.get("status") in ("won", "lost")
                and (leg.get("label_mode") or "both") == m]
        modes[m] = dict(n=len(rows), won=sum(leg["status"] == "won" for leg in rows),
                        price=sum(leg["price"] for leg in rows) / len(rows) if rows else None,
                        p=sum(leg["p"] for leg in rows) / len(rows) if rows else None)
    return dict(cards=len(played), label_modes=modes,
                won=sum(c["status"] == "won" for c in done), lost=sum(c["status"] == "lost" for c in done),
                open=sum(c["status"] == "open" for c in played), no_card=sum(1 for c in cards if not c.get("legs")),
                profit=sum(c.get("profit") or 0 for c in done),
                legs=len(legs_done), legs_won=sum(leg["status"] == "won" for leg in legs_done),
                leg_profit=sum(leg.get("profit") or 0 for leg in legs_done), steps=steps, calibration=calib)


def main(argv=None):
    import sys
    argv = sys.argv[1:] if argv is None else argv
    now = dt.datetime.now(dt.timezone.utc)
    track = T.load()
    T.refresh_games(track, now)                     # fresh ESPN games, in memory only (nba_value saves the tracker)
    out = argv[argv.index("--out") + 1] if "--out" in argv else PATH
    state = load(out)
    if "--build-now" in argv:                       # a dry run: build tonight's card at this moment, write to --out
        night = argv[argv.index("--build-now") + 1]
        state["cards"][night] = build(night, track.get("games") or {}, now, D.get, M.prior(), labels_by_game(),
                                      preseason(state), T.season_climb(track.get("tracked") or {}))
        new = [night]
    else:
        new = run(state, track.get("games") or {}, now, season_gap=T.season_climb(track.get("tracked") or {}))
    tmp = out + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=1, sort_keys=True)
        f.write("\n")
    os.replace(tmp, out)
    for night in new:
        c = state["cards"][night]
        print(night, c["status"], c.get("odds"), c["rationale"])
        for leg in c["legs"]:
            print("  ", leg["rationale"])
    print("built", new, "schedule", len(state["schedule"]), "error", state.get("error"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
