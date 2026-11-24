#!/usr/bin/env python3
"""Club 82: two Sandbox PAPER soccer lanes (Olu via the coordinator, 2026-11-23). Pre-registration: docs/club82_2026-11-23.md.

  club82_u35   back the match total UNDER 3.5 (NO on Kalshi's over 3.5) when EITHER team is at 82%+ for "under 3.5" this season.
  club82_tt15  back a qualifying team to score 2+ (YES on its team-total over 1.5) when THAT team is at 82%+ for "scored 2+".
The qualifier is recomputed from the games already played (season 2026-27, EPL, La Liga, Serie A, Bundesliga, Ligue 1 and the Champions League
together, 90 minutes, 8+ games, hit rate 0.818 or better, only games before the kickoff being read). Entry 30-60 minutes before kickoff at the
Kalshi price with the 7% fee, spread 5c or less, held to settlement. A market that is missing or unquoted is a logged skip, not a silent drop.
Each lane has a control read at the same moment: every game's under 3.5, every team's over 1.5. Nothing is placed anywhere.
"""
import collections
import datetime as dt
import json
import os
import sys

import daily_track as D
import settle_only
import soccer_rules as SR
import soccer_team_rules as STR

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "data", "club82_ledger.json")
VERSION = "club82-v1"
REGISTERED = "2026-11-23"
SEASON_FROM = "2026-07-01"
LEAGUES = ("Premier League", "La Liga", "Serie A", "Bundesliga", "Ligue 1", "Champions League")
MIN_GAMES = 8
THRESHOLD = 0.818            # 9/11 counts
WATCH = 0.75                 # the "watch" table: at least this, under the bar
WINDOW_MIN = (30, 60)        # minutes before kickoff
MAX_SPREAD = SR.MAX_SPREAD
PRICE_LO, PRICE_HI = 0.03, 0.97
REVIEW_AT = (10, 30)
EPS = 1e-9
KINDS = ("u35", "tt15")
NAMES = {"u35": "Under 3.5 (either team at 82%+)", "tt15": "Team 2+ goals (that team at 82%+)"}
HITS = {"u35": "under 3.5", "tt15": "scored 2+"}
LANES = ("club82_u35", "club82_u35_blind", "club82_tt15", "club82_tt15_blind")
LINE = {"u35": 3.5, "tt15": 1.5}


def lane(kind, blind=False):
    return f"club82_{kind}" + ("_blind" if blind else "")


def fee(p):
    return SR.FEE * p * (1 - p)


def cost(p):
    return p + fee(p)


def empty():
    return {"version": VERSION, "registered": REGISTERED, "rules": {k: {"picks": []} for k in LANES}, "skips": {}, "runs": [], "last_run": None, "error": None}


def load(path=PATH):
    if os.path.exists(path):
        with open(path) as f:
            st = json.load(f)
        for k in LANES:
            st.setdefault("rules", {}).setdefault(k, {"picks": []})
        st.setdefault("skips", {})
        return st
    return empty()


def save(state, path=PATH):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=1, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


# ---------------------------------------------------------------- the qualifier
def season_games(fixtures, before=None):
    """The played games of the six competitions this season that kicked off before `before` (an ISO instant), oldest first."""
    out = []
    for f in fixtures:
        if f.get("league") not in LEAGUES or not f.get("played") or f.get("home_goals") is None or f.get("away_goals") is None:
            continue
        ko = f.get("kickoff") or ""
        if ko[:10] < SEASON_FROM or (before is not None and ko >= before):
            continue
        out.append(f)
    return sorted(out, key=lambda f: (f["kickoff"], f.get("home", "")))


def _team_key(f, side):
    return str(f.get(f"{side}_id") or f[side])


def hit(f, kind, side):
    """Did the team on `side` ('home'/'away') hit in game f: u35 = the match total is 3 goals or fewer; tt15 = the team scored 2+."""
    h, a = f["home_goals"], f["away_goals"]
    if kind == "u35":
        return h + a <= 3
    return (h if side == "home" else a) >= 2


def team_rows(fixtures, kind, before=None, threshold=THRESHOLD, min_games=MIN_GAMES):
    """{team key: dict(name, hits, n, rate, qualifies, since)} from games before `before`. `since` is the day of the game after which the team's
    current qualifying run began."""
    seq = collections.defaultdict(list)
    names = {}
    for f in season_games(fixtures, before):
        for side in ("home", "away"):
            k = _team_key(f, side)
            names[k] = f[side]
            seq[k].append((f["kickoff"][:10], hit(f, kind, side)))
    out = {}
    for k, s in seq.items():
        hits = n = 0
        since, was = None, False
        for day, h in s:
            n += 1
            hits += 1 if h else 0
            ok = n >= min_games and hits / n >= threshold - EPS
            if ok and not was:
                since = day
            was = ok
        out[k] = dict(name=names[k], hits=hits, n=n, rate=hits / n, qualifies=was, since=since if was else None)
    return out


# ---------------------------------------------------------------- entries
def due(fixtures, now):
    """Unplayed fixtures of the six competitions kicking off 30-60 minutes from now."""
    if settle_only.on():
        return []
    out = []
    for f in fixtures:
        if f.get("played") or f.get("league") not in LEAGUES:
            continue
        t = D.instant(f.get("kickoff"))
        if t and WINDOW_MIN[0] * 60 <= (t - now).total_seconds() <= WINDOW_MIN[1] * 60:
            out.append(f)
    return out


def _row(kind, blind, f, ev, m, team, px, b, a, now, extra):
    ident = f"{lane(kind, blind)}:{ev['event_ticker']}" + (f":{team}" if team else "")
    r = dict(id=ident, rule=lane(kind, blind), kind=kind, league=f["league"], event=ev["event_ticker"], match=f"{f['home']} v {f['away']}", start=f["kickoff"],
             ticker=m["ticker"], line=LINE[kind], side="no" if kind == "u35" else "yes", price=round(px, 4), bid=b, ask=a,
             lead_min=round((D.instant(f["kickoff"]) - now).total_seconds() / 60, 1), logged=now.isoformat(), status="open")
    if team:
        r.update(team=f[team], team_side=team, opponent=f["away" if team == "home" else "home"])
    r.update(extra)
    return r


def _skip(state, key, f, kind, team, why, qualifying, now):
    sk = state.setdefault("skips", {})
    sk[key] = dict(kind=kind, match=f"{f['home']} v {f['away']}", league=f["league"], start=f["kickoff"], team=f[team] if team else None, reason=why,
                   qualifying=qualifying, at=now.isoformat())
    if len(sk) > 400:
        for k in sorted(sk, key=lambda k: sk[k]["at"])[:len(sk) - 400]:
            del sk[k]


def _quoted(m):
    """((bid, ask), None) inside the entry rules, or (None, reason)."""
    if not m:
        return None, "no market"
    q = SR.quote(m)
    if not q:
        return None, "no quote, or a spread over 5c"
    return q, None


def read_game(state, f, events, rows_by_kind, now, seen):
    """One game's read: for each lane's market, the control row and (when the qualifier says so) the lane row. Returns the new row ids."""
    new = []
    for kind in KINDS:
        series_events = events.get(kind)
        ev = SR.find_event(f, series_events) if series_events is not None else None
        teams = [None] if kind == "u35" else ["home", "away"]
        rows = rows_by_kind[kind]
        quals = {s: bool(rows.get(_team_key(f, s), {}).get("qualifies")) for s in ("home", "away")}
        for team in teams:
            qual = any(quals.values()) if kind == "u35" else quals[team]
            ctl_id = f"{lane(kind, True)}:{ev['event_ticker'] if ev else f['home'] + 'v' + f['away']}" + (f":{team}" if team else "")
            if ev and ctl_id in seen:
                continue
            skey = f"{kind}:{f['kickoff']}:{f['home']} v {f['away']}" + (f":{team}" if team else "")
            if not ev:
                _skip(state, skey, f, kind, team, "no Kalshi event for the match", qual, now)
                continue
            m = SR.market_at(ev, 3.5) if kind == "u35" else STR.market_for(ev, team, 1.5)
            q, why = _quoted(m)
            if q:
                b, a = q
                px = round(1 - b, 4) if kind == "u35" else a
                if not PRICE_LO - EPS <= px <= PRICE_HI + EPS:
                    q, why = None, "price outside 3-97c"
            if not q:
                _skip(state, skey, f, kind, team, why, qual, now)
                continue
            info = {s: f"{rows[_team_key(f, s)]['hits']}/{rows[_team_key(f, s)]['n']}" for s in ("home", "away") if _team_key(f, s) in rows}
            ctl = _row(kind, True, f, ev, m, team, px, b, a, now, dict(rates=info, qualifying=qual))
            state["rules"][lane(kind, True)]["picks"].append(ctl)
            seen.add(ctl["id"])
            new.append(ctl["id"])
            if qual:
                qside = [s for s in ("home", "away") if quals[s]] if kind == "u35" else [team]
                pk = _row(kind, False, f, ev, m, team, px, b, a, now, dict(rates=info, qualifying_teams=[f[s] for s in qside], matches=ctl["id"]))
                state["rules"][lane(kind)]["picks"].append(pk)
                new.append(pk["id"])
            state["skips"].pop(skey, None)
    return new


def settle(state, now, fetch):
    """Kalshi's own result (soccer_rules.settle: profit per $100 after the fee; payout 1 or 0 for the side bought)."""
    return SR.settle(state, now, fetch)


def run(state, fixtures, now=None, fetch=D.get):
    now = now or dt.datetime.now(dt.timezone.utc)
    for k in LANES:
        state["rules"].setdefault(k, {"picks": []})
    seen = {p["id"] for ln in state["rules"].values() for p in ln["picks"]}
    new, errs, cache = [], [], {}
    todo = due(fixtures, now)
    for f in todo:
        try:
            ev_by_kind = {}
            for kind, table in (("u35", SR.SERIES), ("tt15", STR.SERIES)):
                series = table.get(f["league"])
                if series is None:
                    ev_by_kind[kind] = None
                    continue
                if series not in cache:
                    cache[series] = SR.series_events(series, fetch)
                ev_by_kind[kind] = cache[series]
            rows_by_kind = {k: team_rows(fixtures, k, before=f["kickoff"]) for k in KINDS}
            new += read_game(state, f, ev_by_kind, rows_by_kind, now, seen)
        except Exception as e:                                       # noqa: BLE001
            errs.append(f"{f['home']} v {f['away']}: {str(e)[:80]}")
    errs += settle(state, now, fetch)
    state["schedule"] = sorted({f["kickoff"] for f in fixtures if f.get("league") in LEAGUES and not f.get("played") and f.get("kickoff")
                                and now - dt.timedelta(hours=2) <= (D.instant(f["kickoff"]) or now - dt.timedelta(days=9)) <= now + dt.timedelta(hours=27)})
    state["last_run"] = now.isoformat()
    state["games_through"] = max((f["kickoff"][:10] for f in season_games(fixtures)), default=None)
    state["tracker"] = {k: list(team_rows(fixtures, k).values()) for k in KINDS}      # the page reads these (the fixtures file is not committed)
    state["error"] = "; ".join(errs)[:1000] or None
    state["runs"] = (state.get("runs") or [])[-50:] + [dict(at=now.isoformat(), new=len(new), due=len(todo))]
    return new


# ---------------------------------------------------------------- the record
def stats(picks):
    """n settled, won, open, return on cost after fees."""
    done = [p for p in picks if p.get("status") in ("won", "lost")]
    out = dict(n=len(done), won=sum(1 for p in done if p["status"] == "won"), open=sum(1 for p in picks if p["status"] == "open"), ret=None, price=None)
    if done:
        out["ret"] = sum(p["payout"] - cost(p["price"]) for p in done) / sum(cost(p["price"]) for p in done)
        out["price"] = sum(p["price"] for p in done) / len(done)
    return out


def status_text(n):
    if n < REVIEW_AT[0]:
        return f"{n} of {REVIEW_AT[0]} settled · read at {REVIEW_AT[0]}"
    if n < REVIEW_AT[1]:
        return f"{n} settled · first read ({REVIEW_AT[0]}) due · next at {REVIEW_AT[1]}"
    return f"{n} settled · second read ({REVIEW_AT[1]}) due"


def main(argv=None):
    import streaks_fetch
    now = dt.datetime.now(dt.timezone.utc)
    state = load()
    fixtures = streaks_fetch.load_or_fetch()["fixtures"]
    new = run(state, fixtures, now)
    save(state)
    print("club82", state["runs"][-1], "new", new, "error", state["error"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
