#!/usr/bin/env python3
"""NBA ladder tracker (2026-10-21): an observation record of Kalshi's NBA team-total and 1Q ladders.

No bets. For every finished 2026-27 regular-season game it keeps, in data/nba_ladder_track.json:
  * the full KXNBATEAMTOTAL ladder (both teams' "<team> over N.5" rungs, 2-point steps) and the
    KXNBA1QTOTAL ladder (the first-quarter game total, "Over N.5", 2-point steps), each rung's
    YES bid and ask 24, 12, 6, 3 and 1 hours before the ESPN tip, read from Kalshi's hourly event
    candlesticks (series/{s}/events/{e}/candlesticks) from the ladder's open to the tip, and the
    rung's official Kalshi result;
  * the final score and first-quarter score of each side (ESPN scoreboard linescores);
  * the value model's view at the tip (nba_value_model.py): each team's mu, the 1Q mu, the sds
    and every rung's model P, computed point-in-time from games before that tip.
Everything is retained. The first run backfills from opening night, 2026-10-20.

A candlestick only exists for an hour in which something changed, so the quote "h hours before
tip" is the close of the last candle that ended at or before tip - h hours. A YES bid of 0 or an
ask of 1 is a one-sided book and is recorded as it is; the derived tables use two-sided quotes.
Kalshi also lists a first-quarter TEAM total series (KXNBA1QTEAMTOTAL); it had no events on
2026-10-21, so it is not tracked.

THE DERIVED TABLES (shown in the NBA page's Ladder tracker section, nba_value_build.py):
  climb       per team, points minus Kalshi's 50c line (the rung of its ladder whose 1h mid is
              nearest 0.50, a tie to the lower strike), its average and beat rate; the defence
              view is the opponents' climb against their own 50c line.
  drift       the YES ask 1h before tip minus the ask 24h before, on rungs two-sided at both
              times with a 1h mid of 0.15-0.85, by team and overall, plus how often a move of
              2c or more pointed the way the rung settled; and the 50c line's move in points.
  calibration the model's P against the hit rate against Kalshi's average YES ask, by model-P
              bucket, on every rung two-sided 1h before tip.
  levels      (2026-10-24) per game night, the model's mean mu against the mean of Kalshi's
              interpolated 50c lines (team totals; 1Q totals), the gap and what the teams scored,
              stored in state["levels"]; state["season_climb"] is the season-to-date points minus
              Kalshi's 50c line. A CHECK on the model's season-data level: the model's level is never
              moved to Kalshi's (the 2026-10-24 decision; points ran below Kalshi's lines).
"""
import datetime as dt
import json
import os
import urllib.parse
from zoneinfo import ZoneInfo

import daily_track as D
import nba_rules as NR
import nba_value_model as M

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "data", "nba_ladder_track.json")
SERIES_TT, SERIES_Q1 = "KXNBATEAMTOTAL", "KXNBA1QTOTAL"
SEASON_START = dt.date(2026, 10, 20)       # 2026-27 opening night
SEASON = 2027                              # ESPN season.year of 2026-27
OFFSETS_H = (24, 12, 6, 3, 1)
ET = ZoneInfo("America/New_York")
EPS = 1e-9
GIVE_UP = dt.timedelta(days=3)             # a game Kalshi has not settled by then is stored as it is
ESPN_LOOKBACK_D = 3


def empty():
    return {"version": "nba-ladder-track-v1", "season_start": SEASON_START.isoformat(), "games": {},
            "tracked": {}, "runs": []}


def load(path=PATH):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return empty()


def save(state, path=PATH):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=1, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


# ---------- ESPN: the season's games ----------

def _espn_day(day):
    import nba_pace
    return nba_pace.fetch_day(day)


def espn_row(r):
    """A tracker game from an nba_pace.fetch_day row (ESPN codes, scores when completed)."""
    g = dict(id=str(r["id"]), start=r.get("start"), day=r.get("day"), home=r.get("home"), away=r.get("away"),
             completed=bool(r.get("completed")))
    if g["completed"]:
        g.update(pts_home=r.get("ft_home"), pts_away=r.get("ft_away"), q1_home=r.get("q1_home"),
                 q1_away=r.get("q1_away"))
    return g


def refresh_games(state, now, fetch_day=_espn_day):
    """Read ESPN's scoreboard into state["games"]: every 2026-27 regular-season game between NBA teams.

    The first run reads every day from opening night; later runs read yesterday to two days ahead,
    plus the days of any recent game still not completed. Returns a list of error strings."""
    games = state.setdefault("games", {})
    today = now.astimezone(ET).date()
    if state.get("backfilled"):
        days = {today + dt.timedelta(days=i) for i in range(-1, 3)}
        for g in games.values():
            t = D.instant(str(g.get("start") or "").replace("Z", "+00:00"))
            if not g.get("completed") and t and now - dt.timedelta(days=ESPN_LOOKBACK_D) <= t <= now and g.get("day"):
                days.add(dt.date.fromisoformat(g["day"]))
    else:
        days, d = set(), SEASON_START
        while d <= today + dt.timedelta(days=2):
            days.add(d)
            d += dt.timedelta(days=1)
    errs, ok = [], True
    for day in sorted(days):
        if day < SEASON_START:
            continue
        try:
            rows = fetch_day(day)
        except Exception as e:                                  # noqa: BLE001
            errs.append(f"ESPN {day}: {str(e)[:80]}")
            ok = False
            continue
        for r in rows:
            if r.get("season_type") != 2 or r.get("home") not in M.TEAMS or r.get("away") not in M.TEAMS:
                continue
            g = espn_row(r)
            old = games.get(g["id"]) or {}
            if old.get("completed") and not g["completed"]:
                continue                                       # never un-finish a game
            games[g["id"]] = g
    if ok:
        state["backfilled"] = True
    return errs


def start_of(g):
    return D.instant(str(g.get("start") or "").replace("Z", "+00:00"))


def night(g):
    """The game-night cluster: the ET date of the tip."""
    t = start_of(g)
    return t.astimezone(ET).date().isoformat() if t else None


def history_rows(games, before=None):
    """Completed games as nba_value_model history rows, optionally only those tipped before `before`."""
    out = []
    for g in games.values():
        if not g.get("completed") or any(g.get(c) is None for c in ("pts_home", "pts_away", "q1_home", "q1_away")):
            continue
        t = start_of(g)
        if before is not None and (t is None or t >= before):
            continue
        out.append(dict(season=SEASON, start=g["start"], espn_id=g["id"], home=g["home"], away=g["away"],
                        pts_home=g["pts_home"], pts_away=g["pts_away"], q1_home=g["q1_home"], q1_away=g["q1_away"]))
    return out


PACE = os.path.join(ROOT, "data", "nba_pace.json")
_PRE = []


def preseason_games(path=PACE):
    """2026-27 preseason games with a final and a 1Q total (nba_pace.json), read once: [(start, ft, q1)]."""
    if not _PRE:
        try:
            with open(path) as f:
                rows = json.load(f).get("games") or []
        except (OSError, ValueError):
            rows = []
        _PRE.append([(r.get("start"), r["act_ft"], r["act_q1"]) for r in rows
                     if r.get("act_ft") is not None and r.get("act_q1") is not None
                     and str(r.get("day") or "") < SEASON_START.isoformat()])
    return _PRE[0]


def level_now(games, before=None, pre=None):
    """(points per team-game, 1Q game total, games) of the 2026-27 environment: the preseason plus
    the regular-season games completed before `before`."""
    pre = preseason_games() if pre is None else pre
    ft = [x[1] for x in pre]
    q1 = [x[2] for x in pre]
    for r in history_rows(games, before):
        ft.append(r["pts_home"] + r["pts_away"])
        q1.append(r["q1_home"] + r["q1_away"])
    if not ft:
        return None, None, 0
    return sum(ft) / (2 * len(ft)), sum(q1) / len(q1), len(ft)


def model_for(g, games, pri=None, at=None, pre=None):
    """nba_value_model.game_model for one game, from this season's games before `at` (default the tip).

    The 2025-26 prior is first re-anchored to the 2026-27 scoring level (level_now)."""
    pri = M.prior() if pri is None else pri
    cut = at or start_of(g)
    lp, lq, _n = level_now(games, cut, pre)
    model = M.game_model(g["home"], g["away"], M.shift_prior(pri, lp, lq) if pri else pri,
                         M.current_sums(history_rows(games, cut)))
    model["level"] = dict(pts=None if lp is None else round(lp, 2), q1=None if lq is None else round(lq, 2), games=_n)
    return model


# ---------- Kalshi: events, rungs, quotes ----------

def event_tickers(series, g):
    """Both orders of Kalshi's event ticker for a game: away+home first (KX...-26OCT21ATLORL)."""
    return [f"{series}-{NR.event_tag(g['start'], g['away'], g['home'])}",
            f"{series}-{NR.event_tag(g['start'], g['home'], g['away'])}"]


def event_markets(series, g, fetch=D.get):
    """(event ticker, markets) for a game's ladder in one series, either order, else (None, [])."""
    for ev in event_tickers(series, g):
        ms = D.pages(f"markets?limit=200&event_ticker={ev}", "markets", fetch)
        if ms:
            return ev, ms
    return None, []


def strike(m):
    v = D.number(m.get("floor_strike"))
    if v is None or abs((v % 1) - 0.5) > EPS or m.get("strike_type") not in (None, "", "greater"):
        return None
    return v


def team_of(ticker, g):
    """The ESPN code of a team-total rung (...-SAS112 -> SA), if it is one of the game's teams."""
    code = "".join(ch for ch in str(ticker or "").rsplit("-", 1)[-1] if ch.isalpha())
    t = NR.K2E.get(code, code)
    return t if t in (g.get("home"), g.get("away")) else None


def candle_quotes(cs, tip_ts):
    """{ticker: {"24": [bid, ask], ...}} from an event-candlesticks payload, h hours before tip.

    The quote at time T is the close of the last candle that ended at or before T."""
    out = {}
    for tk, candles in zip(cs.get("market_tickers") or [], cs.get("market_candlesticks") or []):
        rows = sorted((c for c in candles or [] if isinstance(c.get("end_period_ts"), (int, float))),
                      key=lambda c: c["end_period_ts"])
        q = {}
        for h in OFFSETS_H:
            t = tip_ts - h * 3600
            last = None
            for c in rows:
                if c["end_period_ts"] <= t:
                    last = c
                else:
                    break
            if last is None:
                continue
            b = D.number((last.get("yes_bid") or {}).get("close_dollars"))
            a = D.number((last.get("yes_ask") or {}).get("close_dollars"))
            if b is not None and a is not None:
                q[str(h)] = [round(b, 4), round(a, 4)]
        out[tk] = q
    return out


def two_sided(q):
    return bool(q) and 0 < q[0] < q[1] < 1


def result_of(m):
    p = D.payout(m)
    return None if p is None else ("yes" if p == 1 else "no" if p == 0 else "void")


def ladder_rows(series, ms, g, quotes, model):
    """Tracker rungs for one event: ticker, team ("game" for 1Q), line, result, quotes, model P."""
    out = []
    for m in ms:
        s = strike(m)
        if s is None:
            continue
        if series == SERIES_TT:
            team = team_of(m.get("ticker"), g)
            if team is None:
                continue
            mu, sd = (model["mu"].get(team), model["sd"]) if model else (None, None)
        else:
            team = "game"
            mu, sd = (model["mu_q1"], model["sd_q1"]) if model else (None, None)
        out.append(dict(ticker=m["ticker"], team=team, line=s, result=result_of(m), q=quotes.get(m["ticker"]) or {},
                        p=None if mu is None else round(M.p_over(s, mu, sd), 4)))
    return sorted(out, key=lambda r: (r["team"], r["line"]))


def track_event(series, g, model, fetch=D.get):
    """{event, open, rungs, settled} for one game's ladder, or None when Kalshi lists no event."""
    ev, ms = event_markets(series, g, fetch)
    if not ev:
        return None
    tip = start_of(g)
    opens = [D.instant(m.get("open_time")) for m in ms if D.instant(m.get("open_time"))]
    t0 = int(min(opens).timestamp()) if opens else int(tip.timestamp()) - 3 * 86400
    t1 = int(tip.timestamp())
    cs = fetch(f"series/{series}/events/{urllib.parse.quote(ev, safe='')}/candlesticks"
               f"?start_ts={t0 - 3600}&end_ts={t1}&period_interval=60")
    rungs = ladder_rows(series, ms, g, candle_quotes(cs, t1), model)
    return dict(event=ev, open=min(opens).isoformat() if opens else None, rungs=rungs,
                settled=all(r["result"] is not None for r in rungs))


def track(state, now, fetch=D.get, pri=None):
    """Add every finished, not yet tracked game. Returns (new ids, errors)."""
    games, done = state.get("games") or {}, state.setdefault("tracked", {})
    pri = M.prior() if pri is None else pri
    new, errs = [], []
    for gid, g in sorted(games.items(), key=lambda kv: str(kv[1].get("start"))):
        if not g.get("completed") or (gid in done and done[gid].get("final")):
            continue
        tip = start_of(g)
        if tip is None:
            continue
        try:
            model = model_for(g, games, pri)
            tt, q1 = track_event(SERIES_TT, g, model, fetch), track_event(SERIES_Q1, g, model, fetch)
        except Exception as e:                                  # noqa: BLE001
            errs.append(f"track {g['away']}@{g['home']}: {str(e)[:80]}")
            continue
        settled = all(x is None or x["settled"] for x in (tt, q1)) and (tt or q1)
        late = now - tip > GIVE_UP
        if not settled and not late:
            continue                                           # Kalshi has not settled yet: next run
        done[gid] = dict(id=gid, start=g["start"], night=night(g), home=g["home"], away=g["away"],
                         pts={g["home"]: g["pts_home"], g["away"]: g["pts_away"]},
                         q1={g["home"]: g["q1_home"], g["away"]: g["q1_away"]},
                         model=dict(mu={k: _r(v) for k, v in model["mu"].items()}, mu_q1=_r(model["mu_q1"]),
                                    sd=model["sd"], sd_q1=model["sd_q1"], level=model.get("level"),
                                    n={t: model["form"][t]["n"] for t in model["form"]}),
                         tt=tt, q1_ladder=q1, tracked=now.isoformat(), final=bool(settled))
        new.append(gid)
    return new, errs


def _r(v):
    return None if v is None else round(v, 2)


# ---------- derived tables ----------

def mid(q):
    return (q[0] + q[1]) / 2


def line50(rungs, h="1"):
    """The rung whose two-sided mid at `h` hours is nearest 0.50 (a tie to the lower strike), or None."""
    c = [r for r in rungs if two_sided(r["q"].get(h))]
    return min(c, key=lambda r: (round(abs(mid(r["q"][h]) - 0.5), 6), r["line"])) if c else None


def climbs(tracked):
    """[(team, opponent, points, 50c line, climb, night)] per team per tracked game."""
    out = []
    for row in tracked.values():
        tt = row.get("tt") or {}
        for team, opp in ((row["home"], row["away"]), (row["away"], row["home"])):
            r = line50([x for x in tt.get("rungs") or [] if x["team"] == team])
            pts = (row.get("pts") or {}).get(team)
            if r and pts is not None:
                out.append((team, opp, pts, r["line"], round(pts - r["line"], 1), row.get("night")))
    return out


def climb_table(tracked):
    """{team: {off_n, off_avg, off_beat, def_n, def_avg, def_beat}}: own climbs and opponents' climbs."""
    out = {}
    for team, opp, _pts, _line, c, _night in climbs(tracked):
        o = out.setdefault(team, dict(off=[], dfn=[]))
        out.setdefault(opp, dict(off=[], dfn=[]))["dfn"].append(c)
        o["off"].append(c)
    res = {}
    for t, v in out.items():
        res[t] = dict(off_n=len(v["off"]), off_avg=_avg(v["off"]), off_beat=_rate([x > 0 for x in v["off"]]),
                      def_n=len(v["dfn"]), def_avg=_avg(v["dfn"]), def_beat=_rate([x > 0 for x in v["dfn"]]))
    return res


def _avg(xs):
    return sum(xs) / len(xs) if xs else None


def _rate(bs):
    return sum(bs) / len(bs) if bs else None


DRIFT_MOVE = 0.02
DRIFT_MID = (0.15, 0.85)


def drifts(tracked, frm="24", to="1"):
    """[(kind, team, ask move, result, ticker)] on rungs two-sided at both times with a mid in DRIFT_MID."""
    out = []
    for row in tracked.values():
        for kind, lad in (("tt", row.get("tt")), ("q1", row.get("q1_ladder"))):
            for r in (lad or {}).get("rungs") or []:
                a, b = r["q"].get(frm), r["q"].get(to)
                if not (two_sided(a) and two_sided(b)) or not DRIFT_MID[0] <= mid(b) <= DRIFT_MID[1]:
                    continue
                out.append((kind, r["team"], round(b[1] - a[1], 4), r.get("result"), r["ticker"]))
    return out


def drift_table(tracked):
    """{"all": {...}, "tt": {...}, "q1": {...}, team: {...}}: n, avg ask move, moves >= 2c, matched rate."""
    groups = {}
    for kind, team, d, res, _tk in drifts(tracked):
        for key in ("all", kind) + ((team,) if kind == "tt" else ()):
            groups.setdefault(key, []).append((d, res))
    out = {}
    for k, v in groups.items():
        moved = [(d, r) for d, r in v if abs(d) >= DRIFT_MOVE - EPS and r in ("yes", "no")]
        out[k] = dict(n=len(v), avg=_avg([d for d, _ in v]), moved=len(moved),
                      matched=_rate([(d > 0) == (r == "yes") for d, r in moved]))
    return out


def line_moves(tracked):
    """{team: [50c line at 1h minus at 24h]} on each team's ladder."""
    out = {}
    for row in tracked.values():
        tt = row.get("tt") or {}
        for team in (row["home"], row["away"]):
            rs = [x for x in tt.get("rungs") or [] if x["team"] == team]
            a, b = line50(rs, "24"), line50(rs, "1")
            if a and b:
                out.setdefault(team, []).append(b["line"] - a["line"])
    return out


CAL_EDGES = (0, .1, .2, .3, .4, .5, .6, .7, .8, .9, 1.0001)


def calibration(tracked, kind="tt", h="1", by="model"):
    """[(lo, hi, n, mean model P, hit rate, mean YES ask)] on rungs two-sided `h` hours before tip.

    `by` "model" buckets on the model's P; "ask" buckets on Kalshi's YES ask."""
    pts = []
    for row in tracked.values():
        lad = row.get("tt") if kind == "tt" else row.get("q1_ladder")
        for r in (lad or {}).get("rungs") or []:
            q = r["q"].get(h)
            if r.get("p") is None or r.get("result") not in ("yes", "no") or not two_sided(q):
                continue
            pts.append((r["p"], int(r["result"] == "yes"), q[1]))
    out = []
    for lo, hi in zip(CAL_EDGES, CAL_EDGES[1:]):
        b = [x for x in pts if lo <= (x[0] if by == "model" else x[2]) < hi]
        if b:
            out.append((lo, min(hi, 1.0), len(b), _avg([x[0] for x in b]), _avg([x[1] for x in b]),
                        _avg([x[2] for x in b])))
    return out


def median_line(rungs, h="1"):
    """The line where the two-sided YES mid crosses 0.50 at `h` hours, interpolated, else None."""
    rows = sorted((r["line"], mid(r["q"][h])) for r in rungs if two_sided(r["q"].get(h)))
    if not rows:
        return None
    for (l1, m1), (l2, m2) in zip(rows, rows[1:]):
        if m1 >= 0.5 >= m2 and m1 != m2:
            return l1 + (m1 - 0.5) / (m1 - m2) * (l2 - l1)
    return min(rows, key=lambda r: (abs(r[1] - 0.5), r[0]))[0]


def level_gaps(tracked, h="1"):
    """{"tt": [model mu - Kalshi's median line], "q1": [...]} per team (1Q per game) at `h` hours."""
    out = {"tt": [], "q1": []}
    for row in tracked.values():
        m = row.get("model") or {}
        for team in (row["home"], row["away"]):
            med = median_line([x for x in (row.get("tt") or {}).get("rungs") or [] if x["team"] == team], h)
            mu = (m.get("mu") or {}).get(team)
            if med is not None and mu is not None:
                out["tt"].append(round(mu - med, 2))
        med = median_line((row.get("q1_ladder") or {}).get("rungs") or [], h)
        if med is not None and m.get("mu_q1") is not None:
            out["q1"].append(round(m["mu_q1"] - med, 2))
    return out


def season_climb(tracked):
    """Season to date, every tracked team-game: {n, avg, beat} of points minus Kalshi's 50c team-total
    line (the Safe Card's lean label reads it: a negative average is Kalshi's lines above the results)."""
    c = [x[4] for x in climbs(tracked)]
    return dict(n=len(c), avg=_avg(c), beat=_rate([x > 0 for x in c]))


def night_levels(tracked, h="1"):
    """{night: the model's level, Kalshi's level and the gap, team totals and 1Q} (2026-10-24).

    The CHECK on the model's season-data level, never a driver: per game night, the mean model mu
    against the mean of Kalshi's interpolated 50c lines `h` hours before tip (team totals per team,
    the 1Q game total per game), the gap, and what the teams actually scored. `season` is the season
    level the model was anchored to (preseason plus regular-season games so far)."""
    nights = {}
    for row in tracked.values():
        n = nights.setdefault(row.get("night"), dict(tt=[], q1=[], pts=[], q1_pts=[], season=[], games=0, climb=[]))
        n["games"] += 1
        m = row.get("model") or {}
        lad = (row.get("tt") or {}).get("rungs") or []
        for team in (row["home"], row["away"]):
            mine = [x for x in lad if x["team"] == team]
            med, mu, pts = median_line(mine, h), (m.get("mu") or {}).get(team), (row.get("pts") or {}).get(team)
            if med is not None and mu is not None:
                n["tt"].append((mu, med))
                if pts is not None:
                    n["pts"].append(pts)
            r = line50(mine, h)
            if r and pts is not None:
                n["climb"].append(pts - r["line"])
        med = median_line((row.get("q1_ladder") or {}).get("rungs") or [], h)
        if med is not None and m.get("mu_q1") is not None:
            n["q1"].append((m["mu_q1"], med))
            q1 = row.get("q1") or {}
            if len(q1) == 2 and None not in q1.values():
                n["q1_pts"].append(sum(q1.values()))
        lv = (m.get("level") or {}).get("pts")
        if lv is not None:
            n["season"].append(lv)

    def level(pairs):
        if not pairs:
            return None, None, None
        mu, k = _avg([a for a, _b in pairs]), _avg([b for _a, b in pairs])
        return round(mu, 2), round(k, 2), round(mu - k, 2)

    out = {}
    for night, n in sorted(nights.items(), key=lambda kv: str(kv[0])):
        mu, kal, gap = level(n["tt"])
        qmu, qkal, qgap = level(n["q1"])
        out[night] = dict(games=n["games"], tt_n=len(n["tt"]), model_tt=mu, kalshi_tt=kal, gap_tt=gap,
                          actual_tt=None if not n["pts"] else round(_avg(n["pts"]), 2),
                          climb_tt=None if not n["climb"] else round(_avg(n["climb"]), 2),
                          season_tt=None if not n["season"] else round(_avg(n["season"]), 2),
                          q1_n=len(n["q1"]), model_q1=qmu, kalshi_q1=qkal, gap_q1=qgap,
                          actual_q1=None if not n["q1_pts"] else round(_avg(n["q1_pts"]), 2))
    return out


def median(xs):
    xs = sorted(xs)
    if not xs:
        return None
    k = len(xs) // 2
    return xs[k] if len(xs) % 2 else (xs[k - 1] + xs[k]) / 2


def summary(state):
    tr = state.get("tracked") or {}
    rungs = sum(len((r.get("tt") or {}).get("rungs") or []) + len((r.get("q1_ladder") or {}).get("rungs") or [])
                for r in tr.values())
    return dict(games=len(tr), rungs=rungs, nights=len({r.get("night") for r in tr.values()}))


def run(state, now=None, fetch=D.get, fetch_day=_espn_day, pri=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    errs = refresh_games(state, now, fetch_day)
    new, e2 = track(state, now, fetch, pri)
    errs += e2
    # The model's level against Kalshi's, per night (2026-10-24): a check, not a driver.
    state["levels"] = night_levels(state.get("tracked") or {})
    state["season_climb"] = season_climb(state.get("tracked") or {})
    state["last_run"] = now.isoformat()
    state["error"] = "; ".join(errs)[:1000] or None
    state["runs"] = (state.get("runs") or [])[-50:] + [dict(at=now.isoformat(), new=len(new), **summary(state))]
    return new


def main(argv=None):
    state = load()
    new = run(state)
    save(state)
    print("tracked", summary(state), "new", new, "error", state["error"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
