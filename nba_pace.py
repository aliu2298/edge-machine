#!/usr/bin/env python3
"""Dynamic last-5 pace labels for NBA teams, exercised on the 2026-27 preseason.

WHAT THIS IS FOR. It tests the MECHANISM, not the signal. The question is whether a label
that is supposed to move -- last five games, oldest dropping out as a new result lands --
actually transitions cleanly: every scheduled game gets a label and an expectation before
tip-off, every completed game gets graded, the window advances, and the regular-season seed
is never contaminated by preseason results. Preseason basketball is indicative of nothing,
because starters play fifteen minutes and the bench decides the result. That is precisely
why it is the right place to shake the plumbing out: if the transition logic breaks, it
breaks here, in October, on games nobody is betting.

NO PRICES, NO BETS, NO VENUE. This lane states an expected total and is graded on the
realised total. It is deliberately NOT wired into sandbox_track.assess(), which judges a
record against the price that existed and would be corrupted by a lane carrying none. The
arrangement matches the trading lane, which also never places an order.

THE LABEL. For each team, over its last WINDOW completed games:
    O = mean points scored        D = mean points allowed
computed separately for the first quarter, the first half and the full game, because a team
can be fast early and slow late. Each is labelled against the league mean of the same
window: O+ scores more than average, D+ allows more than average. Four cells, from O+D+
(expect the highest total) to O-D- (expect the lowest).

THE EXPECTATION. exp = (A.O + B.D)/2 + (B.O + A.D)/2, one per period, recorded before
tip-off and never recomputed. The halves average each side's own rate against the other's,
which is the standard construction and the reason it can separate games the point spread
cannot: a spread measures the GAP between two teams and is blind to two fast, leaky teams
meeting at a pick-'em.

TWO LABELS PER TEAM, ON PURPOSE. `roll` lets preseason results into the window, which is
what "dynamic" means. `seed` freezes the window at the last five REGULAR-season games of
2025-26. Both are logged for every game so that when the regular season starts there is a
record of whether preseason data helped or polluted. Nothing decides that question here.

PER-TEAM WINDOW AND LAST GAME. `teams` stores, for every seeded team, the rolling
offence and defence as of this build (first quarter, first half, full game) and the
highest points + rebounds + assists line from that team's latest completed game in
`games` that has an ESPN event id. A team with no such game stores null. The April
seed is not a last game: those rows have no event id. A finished box score is fetched
once and carried forward; if both ESPN hosts fail, or the payload has no box score,
the run raises and the previous file is left where it is.

WHAT IS ALREADY KNOWN TO BE WRONG WITH IT, measured rather than guessed:

  * PRIOR-SEASON LABELS WERE ANTI-PREDICTIVE. The full-season equivalent of this label,
    built from 2024-25 rates and tested on the 80 games of October 2025, correlated -0.258
    with the actual first quarter, -0.217 with the first half and -0.033 with the final,
    and under-forecast by 3.3, 5.1 and 7.9 points. Rosters turn over and the league itself
    moved 4 points a game. The seed here is a five-game slice of exactly that kind of
    prior, so expect it to be worse, not better.
  * FIVE GAMES IS NOISE, AND THIS IS NOW MEASURED RATHER THAN FEARED. The seed built here
    -- each team's last five regular-season games of 2025-26 -- was compared against the
    SAME team's full 2025-26 season average. Not a different season, not a different
    roster: the same eighty-two games, one window against the whole. The five-game label
    agreed with the full-season label for 15 OF 30 TEAMS. A coin flip. Mean absolute
    divergence was 4.1 points on offence and 4.3 on defence, and the worst case was
    Memphis, which allowed 137.6 over its last five against 120.7 for the season (+16.9) --
    eliminated teams rest starters in April, so the tail of a season is the least
    representative five games in it.
    Two consequences. The seed is poor for a reason that has nothing to do with preseason,
    and WINDOW=5 is too short to carry a label at all. The fix is not a different five
    games; it is either a wider window or shrinkage toward a prior. The in-season model
    this lane descends from used a six-game shrinkage weight and reached +0.208 against
    the final total, where this raw five-game form would be far noisier. WINDOW is left at
    5 for now because the owner specified it and because the point of this run is to
    exercise the transition, but it should not survive into the regular season unchanged.
  * THE WINDOW BARELY MOVES IN PRESEASON. Each team plays four to six games, so most labels
    will still be carrying regular-season results when the regular season begins.
  * THE IN-SEASON VERSION OF THIS IDEA DOES WORK, modestly: built point-in-time across the
    496 games of Oct-Dec 2025 it correlated +0.208 with the final total, against +0.009 for
    |spread|. But the market line correlated +0.326 on the same games, so the book already
    knows this and more. That is a reason to keep the lane honest about what it is -- a
    measurement -- and not to mistake it for an edge.

Usage:
  python3 nba_pace.py --seed                 # build the regular-season seed and save it
  python3 nba_pace.py --run                  # grade finished games, project scheduled ones
  python3 nba_pace.py --report               # print the mechanism and accuracy checks
"""
import argparse
import datetime
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict, deque

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "data", "nba_pace.json")

ESPN = ("https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
        "?dates={date}")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/129.0 Safari/537.36")

WINDOW = 5                 # games in the rolling label
PERIODS = ("q1", "h1", "ft")
# ESPN season types. 1 preseason, 2 regular season, 3 postseason. The seed takes type 2
# only: playoff rotations are as unrepresentative as preseason ones, in the other
# direction, and the owner asked for regular-season games.
PRE, REG, POST = 1, 2, 3
# The seed window. The 2025-26 regular season ended 2026-04-12; this span gives every team
# 9 to 11 completed games, comfortably more than the five needed, and every game in it
# carries linescores.
SEED_FROM = datetime.date(2026, 3, 25)
SEED_TO = datetime.date(2026, 4, 12)
SEED_SEASON = 2026         # ESPN's `season.year` for the 2025-26 season


def _get(url, tries=3):
    """One ESPN call. Raises RuntimeError without leaking the URL into the message."""
    last = None
    for _ in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as f:
                return json.load(f)
        except (urllib.error.URLError, OSError, ValueError) as e:
            last = type(e).__name__
    raise RuntimeError(f"ESPN unreachable ({last})")


def _periods(competitor):
    """(q1, h1, ft) for one side, or None when the linescores cannot be read.

    ESPN gives a value per quarter and extra entries for overtime. The first half is the
    first two quarters; the full game is the reported score, which already includes any
    overtime. Deriving the full game from the linescores instead would silently drop OT.
    """
    ls = [p.get("value") for p in (competitor.get("linescores") or [])]
    if len(ls) < 2 or any(v is None for v in ls[:2]):
        return None
    try:
        ft = int(float(competitor["score"]))
    except (KeyError, TypeError, ValueError):
        return None
    return int(ls[0]), int(ls[0]) + int(ls[1]), ft


def fetch_day(day):
    """Every NBA game ESPN lists for one date, as flat rows. Never raises on a bad game."""
    js = _get(ESPN.format(date=day.strftime("%Y%m%d")))
    out = []
    for ev in js.get("events") or []:
        season = ev.get("season") or {}
        try:
            comp = ev["competitions"][0]
            sides = {c["homeAway"]: c for c in comp["competitors"]}
            home, away = sides["home"], sides["away"]
        except (KeyError, IndexError):
            continue
        done = bool(((comp.get("status") or {}).get("type") or {}).get("completed"))
        row = dict(
            id=str(ev.get("id")), start=ev.get("date"), day=day.isoformat(),
            season_year=season.get("year"), season_type=season.get("type"),
            home=home["team"].get("abbreviation"), away=away["team"].get("abbreviation"),
            home_id=home["team"].get("id"), away_id=away["team"].get("id"),
            completed=done,
        )
        if done:
            h, a = _periods(home), _periods(away)
            if h and a:
                for i, p in enumerate(PERIODS):
                    row[p + "_home"], row[p + "_away"] = h[i], a[i]
                    row[p] = h[i] + a[i]
            else:
                row["completed"] = False          # finished but unreadable: not gradeable
                row["unreadable"] = True
        out.append(row)
    return out


def fetch_range(start, end, keep=None, log=print):
    """Rows for every date in [start, end], optionally filtered to some season types."""
    rows, day = [], start
    while day <= end:
        try:
            got = fetch_day(day)
        except RuntimeError as e:
            log(f"  ! {day}: {e}")
            day += datetime.timedelta(days=1)
            continue
        if keep is not None:
            got = [r for r in got if r.get("season_type") in keep]
        rows += got
        day += datetime.timedelta(days=1)
    rows.sort(key=lambda r: (str(r.get("start")), r["id"]))
    return rows


# ---------------------------------------------------------------------------
# the rolling window and the labels
# ---------------------------------------------------------------------------

def _blank():
    return {p: deque(maxlen=WINDOW) for p in PERIODS}


def push(state, row):
    """Add one completed game to both teams' windows. Each entry is (scored, allowed)."""
    for p in PERIODS:
        if row.get(p + "_home") is None:
            return
    for p in PERIODS:
        h, a = row[p + "_home"], row[p + "_away"]
        state[row["home"]][p].append((h, a))
        state[row["away"]][p].append((a, h))


def rates(state, team, p):
    """(O, D, n) for one team and period: mean scored, mean allowed, games in the window."""
    w = state.get(team, {}).get(p)
    if not w:
        return None, None, 0
    o = sum(x[0] for x in w) / len(w)
    d = sum(x[1] for x in w) / len(w)
    return o, d, len(w)


def league(state, p):
    """The league mean of the same window, which is what O+/D+ are measured against.

    Deliberately not a fixed historical constant: the league moved 4 points a game between
    2024-25 and October 2025, and a label measured against a stale mean would put most of
    the league on one side of it.
    """
    os_, ds = [], []
    for t in state:
        o, d, n = rates(state, t, p)
        if n:
            os_.append(o)
            ds.append(d)
    if not os_:
        return None, None
    return sum(os_) / len(os_), sum(ds) / len(ds)


def label(state, team, p):
    """{'O','D','tag','n'} for one team and period, or None when the window is empty."""
    o, d, n = rates(state, team, p)
    if not n:
        return None
    lo, ld = league(state, p)
    if lo is None:
        return None
    return dict(O=round(o, 2), D=round(d, 2), n=n,
                tag=("O+" if o >= lo else "O-") + ("D+" if d >= ld else "D-"))


def expect(state, home, away, p):
    """The matchup's expected total for one period, or None if either side is unseeded."""
    ho, hd, hn = rates(state, home, p)
    ao, ad, an = rates(state, away, p)
    if not hn or not an:
        return None
    return round(((ho + ad) / 2) + ((ao + hd) / 2), 2)


def project(state, row):
    """Labels and expectations for one game, from the window as it stands right now.

    A side with no window at all gets None rather than a guess. The caller is expected to
    have already marked such a game as skipped: the first run of this module found POR
    hosting LON on 2026-10-12 -- a non-NBA opponent with no NBA history -- and emitted
    silent nulls for it, which would have read as a plumbing failure rather than as a game
    that cannot be labelled by construction.
    """
    out = {}
    for p in PERIODS:
        out["exp_" + p] = expect(state, row["home"], row["away"], p)
        out["lab_home_" + p] = (label(state, row["home"], p) or {}).get("tag")
        out["lab_away_" + p] = (label(state, row["away"], p) or {}).get("tag")
    hl = label(state, row["home"], "ft") or {}
    al = label(state, row["away"], "ft") or {}
    out["home_O"], out["home_D"], out["home_n"] = hl.get("O"), hl.get("D"), hl.get("n", 0)
    out["away_O"], out["away_D"], out["away_n"] = al.get("O"), al.get("D"), al.get("n", 0)
    # how many of the four traits are "+", the compact form of the owner's hypothesis:
    # 4 means both teams score more than average AND allow more than average.
    tags = [out.get("lab_home_ft"), out.get("lab_away_ft")]
    out["pluses"] = (sum(t.count("+") for t in tags if t) if all(tags) else None)
    return out


def _rounded_od(state, team, period):
    """(O, D, n) rounded the same way label() rounds, or (None, None, 0)."""
    o, d, n = rates(state, team, period)
    if not n:
        return None, None, 0
    return round(o, 2), round(d, 2), n


def _roll_block(state, team):
    """The team's current window: q1, h1 and ft, each {O, D, n}."""
    block = {}
    for p in PERIODS:
        o, d, n = _rounded_od(state, team, p)
        block[p] = {"O": o, "D": d, "n": n}
    return block


# Box scores. site.api.espn.com has 403'd the whole site API before (see the
# sandbox_sources note from 2026-08-08); site.web.api.espn.com is the same path
# and is tried first. Both are keyless. A finished box score does not change,
# so a last_game already stored for the same event id is not fetched again.
BOX_HOSTS = ("site.web.api.espn.com", "site.api.espn.com")
BOX_UA = "edge-machine/nba-pace"
BOX_TIMEOUT = 15
BOX_ATTEMPTS = 2          # the request, plus one retry, on each host
BOX_PAUSE = 1.0           # seconds between box-score requests
_PRA_FIELDS = ("name", "pts", "reb", "ast", "pra")
# Set once a request has gone out this run, so the next one waits. attach_teams
# clears it at the start of a build.
_box_gap = {"sent": False}


class BoxScoreError(RuntimeError):
    """A completed game's box score could not be read.

    The message names the event id, the host and the HTTP status. Callers must
    let it propagate: null is only for a team with no qualifying game.
    """


def _sleep(seconds):
    time.sleep(seconds)


def _summary_url(host, event_id):
    eid = urllib.parse.quote(str(event_id), safe="")
    return (f"https://{host}/apis/site/v2/sports/basketball/nba/summary"
            f"?event={eid}")


def _mark_box_request():
    """One request at a time, with BOX_PAUSE between them. The first is immediate."""
    if _box_gap["sent"]:
        _sleep(BOX_PAUSE)
    _box_gap["sent"] = True


def _http_get(url, timeout):
    """GET url. Returns (status, text). text is None unless the status is 200.

    A connection failure returns (None, None). HTTP errors return the status
    and no body. Only GET, only the identifying User-Agent, no key.
    """
    req = urllib.request.Request(url, headers={"User-Agent": BOX_UA}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = getattr(resp, "status", None) or resp.getcode()
            raw = resp.read()
    except urllib.error.HTTPError as e:
        try:
            e.read()
        finally:
            e.close()
        return e.code, None
    except (urllib.error.URLError, OSError):
        return None, None
    if status != 200:
        return status, None
    return status, raw.decode("utf-8")


def _usable_box(payload):
    if not isinstance(payload, dict):
        return False
    box = payload.get("boxscore")
    if not isinstance(box, dict):
        return False
    return isinstance(box.get("players"), list) and len(box["players"]) > 0


def _status_text(status):
    return "none" if status is None else str(status)


def fetch_summary(event_id):
    """(payload, host, status) for one event. Raises BoxScoreError, never None.

    Web host first, api host if that host cannot return a box score. Each host
    gets one retry. A 200 with no boxscore is a failure of that attempt, not a
    silent null.
    """
    failures = []
    for host in BOX_HOSTS:
        url = _summary_url(host, event_id)
        for _attempt in range(BOX_ATTEMPTS):
            _mark_box_request()
            try:
                status, text = _http_get(url, BOX_TIMEOUT)
            except (urllib.error.URLError, OSError) as e:
                failures.append((host, None, type(e).__name__))
                continue
            if status != 200 or not text:
                failures.append((host, status, "no box score"))
                continue
            try:
                payload = json.loads(text)
            except ValueError:
                failures.append((host, status, "malformed json"))
                continue
            if not _usable_box(payload):
                failures.append((host, status, "missing boxscore"))
                continue
            return payload, host, status
    parts = [f"{host} (status {_status_text(status)}): {why}"
             for host, status, why in failures]
    raise BoxScoreError(
        f"ESPN box score failed for event {event_id}: " + "; ".join(parts))


def _cell_int(cell):
    """One box-score cell as an int, or ValueError when it is blank."""
    if isinstance(cell, bool) or cell is None:
        raise ValueError("empty stat")
    if isinstance(cell, str):
        cell = cell.strip()
        if cell == "":
            raise ValueError("empty stat")
    return int(cell)


def _pra_row(ath, i_pts, i_reb, i_ast):
    """One athlete's PRA line, or None for DNP / empty / unreadable stats."""
    if not isinstance(ath, dict) or ath.get("didNotPlay"):
        return None
    stats = ath.get("stats")
    if not isinstance(stats, list) or not stats:
        return None
    athlete = ath.get("athlete")
    name = ""
    if isinstance(athlete, dict):
        name = str(athlete.get("displayName") or "").strip()
    if not name:
        return None
    try:
        pts = _cell_int(stats[i_pts])
        reb = _cell_int(stats[i_reb])
        ast = _cell_int(stats[i_ast])
    except (IndexError, TypeError, ValueError):
        return None
    return {"name": name, "pts": pts, "reb": reb, "ast": ast, "pra": pts + reb + ast}


def _better_pra(row, best):
    """Higher PRA, then more points, then the display name A to Z."""
    if best is None:
        return True
    if row["pra"] != best["pra"]:
        return row["pra"] > best["pra"]
    if row["pts"] != best["pts"]:
        return row["pts"] > best["pts"]
    return row["name"] < best["name"]


def top_pra(payload, team):
    """Highest PTS+REB+AST for one team. Columns come from the labels, not a fixed index.

    Raises BoxScoreError when the box cannot produce a player. That is a broken
    payload, not an empty last game.
    """
    if not isinstance(payload, dict):
        raise BoxScoreError("missing boxscore")
    box = payload.get("boxscore")
    if not isinstance(box, dict) or not isinstance(box.get("players"), list):
        raise BoxScoreError("missing boxscore")
    side = None
    for entry in box["players"]:
        if not isinstance(entry, dict):
            continue
        club = entry.get("team")
        abbr = club.get("abbreviation") if isinstance(club, dict) else None
        if abbr == team:
            side = entry
            break
    if side is None:
        raise BoxScoreError(f"team {team} missing from boxscore")
    groups = side.get("statistics")
    if not isinstance(groups, list) or not groups or not isinstance(groups[0], dict):
        raise BoxScoreError(f"team {team} missing statistics")
    group = groups[0]
    labels = group.get("labels")
    if not isinstance(labels, list):
        raise BoxScoreError(f"team {team} missing stat labels")
    missing = [name for name in ("PTS", "REB", "AST") if name not in labels]
    if missing:
        raise BoxScoreError(
            f"team {team} labels missing {', '.join(missing)}")
    i_pts, i_reb, i_ast = (labels.index("PTS"), labels.index("REB"), labels.index("AST"))
    athletes = group.get("athletes")
    if not isinstance(athletes, list):
        raise BoxScoreError(f"team {team} missing athletes")
    best = None
    for ath in athletes:
        row = _pra_row(ath, i_pts, i_reb, i_ast)
        if row is not None and _better_pra(row, best):
            best = row
    if best is None:
        raise BoxScoreError(f"team {team} has no countable player")
    return best


def _event_id(game):
    """The ESPN event id on a games[] row, or None when the row has none."""
    if not isinstance(game, dict):
        return None
    eid = game.get("id")
    if eid is None or str(eid).strip() == "":
        return None
    return eid


def latest_completed(games, team):
    """The latest completed games[] row for team that has an event id.

    Season type is ignored, so a regular-season row qualifies the same way a
    preseason row does. A row with no id does not qualify. The April seed is
    not in games[] and is never used here.
    """
    found, found_key = None, None
    for game in games or []:
        if not isinstance(game, dict) or not game.get("completed"):
            continue
        eid = _event_id(game)
        if eid is None:
            continue
        if team != game.get("home") and team != game.get("away"):
            continue
        key = (str(game.get("start") or ""), str(eid))
        if found is None or key >= found_key:
            found, found_key = game, key
    return found


def _carry_last_game(prior, team, event_id):
    """The stored last_game when it is already this event, else None.

    A finished box score does not change, so the stored line is reused and the
    event is not fetched again for this team.
    """
    if not isinstance(prior, dict):
        return None
    row = prior.get(team)
    if not isinstance(row, dict):
        return None
    last = row.get("last_game")
    if not isinstance(last, dict):
        return None
    if str(last.get("id")) != str(event_id):
        return None
    pra = last.get("top_pra")
    if not isinstance(pra, dict) or any(k not in pra for k in _PRA_FIELDS):
        return None
    return {
        "id": last.get("id"),
        "date": last.get("date"),
        "opp": last.get("opp"),
        "home_away": last.get("home_away"),
        "top_pra": {k: pra[k] for k in _PRA_FIELDS},
    }


def _prior_teams(path):
    """teams object from the file already on disk, or {} when there is none."""
    if not path or not os.path.exists(path):
        return {}
    with open(path) as f:
        blob = json.load(f)
    if not isinstance(blob, dict):
        return {}
    teams = blob.get("teams")
    return teams if isinstance(teams, dict) else {}


def _last_game_record(game, team, pra):
    home = team == game.get("home")
    return {
        "id": game.get("id"),
        "date": game.get("day"),
        "opp": game.get("away") if home else game.get("home"),
        "home_away": "home" if home else "away",
        "top_pra": pra,
    }


def attach_teams(games, roll, prior, log=print):
    """{team: {roll, last_game}} for every team in the rolling window.

    last_game is null only when that team has no completed games[] row with an
    event id. Newly latest games are fetched one at a time. A fetch or a
    malformed box raises BoxScoreError before the caller writes.
    """
    _box_gap["sent"] = False
    chosen = [(team, latest_completed(games, team)) for team in sorted(roll)]
    payloads = {}
    seen = set()
    for team, game in chosen:
        if game is None or _carry_last_game(prior, team, game.get("id")) is not None:
            continue
        eid = str(game.get("id"))
        if eid in seen:
            continue
        seen.add(eid)
        log(f"  box score {eid}")
        payloads[eid] = fetch_summary(eid)
    teams = {}
    for team, game in chosen:
        entry = {"roll": _roll_block(roll, team), "last_game": None}
        if game is not None:
            carried = _carry_last_game(prior, team, game.get("id"))
            if carried is not None:
                entry["last_game"] = carried
            else:
                payload, host, status = payloads[str(game.get("id"))]
                try:
                    pra = top_pra(payload, team)
                except BoxScoreError as e:
                    raise BoxScoreError(
                        f"ESPN box score malformed for event {game.get('id')} "
                        f"on {host} (status {_status_text(status)}): {e}"
                    ) from e
                entry["last_game"] = _last_game_record(game, team, pra)
        teams[team] = entry
    return teams


# ---------------------------------------------------------------------------
# the two states: a frozen regular-season seed, and a window that keeps moving
# ---------------------------------------------------------------------------

def build_seed(log=print):
    """Each team's last WINDOW regular-season games of 2025-26, as a frozen window."""
    log(f"seeding from {SEED_FROM} to {SEED_TO} (regular season {SEED_SEASON})")
    rows = fetch_range(SEED_FROM, SEED_TO, keep=(REG,), log=log)
    rows = [r for r in rows if r.get("completed") and r.get("season_year") == SEED_SEASON]
    state = defaultdict(_blank)
    for r in rows:
        push(state, r)
    thin = {t: len(state[t]["ft"]) for t in state if len(state[t]["ft"]) < WINDOW}
    log(f"  {len(rows)} games, {len(state)} teams"
        + (f", THIN: {thin}" if thin else f", every team at {WINDOW}"))
    return state, rows


def run(log=print):
    """Grade finished preseason games and project the scheduled ones.

    Chronological, and the window is updated only AFTER a game's expectation is recorded,
    so no game can ever contribute to predicting itself.
    """
    seed_state, seed_rows = build_seed(log=log)
    # the frozen copy, which preseason never touches
    frozen = {t: {p: deque(seed_state[t][p], maxlen=WINDOW) for p in PERIODS}
              for t in seed_state}
    roll = {t: {p: deque(seed_state[t][p], maxlen=WINDOW) for p in PERIODS}
            for t in seed_state}

    today = datetime.date.today()
    start = datetime.date(2026, 9, 29)              # ESPN's 2026-27 season start
    end = max(today + datetime.timedelta(days=10), start)
    log(f"reading preseason {start} to {end}")
    games = fetch_range(start, end, keep=(PRE,), log=log)
    log(f"  {len(games)} preseason games listed "
        f"({sum(1 for g in games if g['completed'])} completed)")

    # The 30 teams the seed knows about. An NBA preseason schedule also carries exhibition
    # games against non-NBA sides -- POR v LON on 2026-10-12 in this very run -- and those
    # cannot carry a label, because the opponent has no NBA record to roll. They are marked
    # skipped so an unlabellable game never reads as a broken label.
    nba = set(frozen)
    out, flips, skipped = [], defaultdict(int), 0
    prev_tag = {}
    for g in games:
        rec = dict(id=g["id"], day=g["day"], start=g["start"],
                   home=g["home"], away=g["away"], completed=g["completed"])
        outside = [t for t in (g["home"], g["away"]) if t not in nba]
        if outside:
            rec["skipped"] = f"non-NBA opponent: {', '.join(outside)}"
            skipped += 1
            out.append(rec)
            continue
        rec.update({("roll_" + k): v for k, v in project(roll, g).items()})
        rec.update({("seed_" + k): v for k, v in project(frozen, g).items()})
        # Pre-tip 1Q and 1H rates, rounded like roll_home_O. The full game is
        # already roll_{home,away}_O/D/n. Written before the window advances.
        for side, club in (("home", g["home"]), ("away", g["away"])):
            for p in ("q1", "h1"):
                o, d, _n = _rounded_od(roll, club, p)
                rec[f"roll_{side}_O_{p}"] = o
                rec[f"roll_{side}_D_{p}"] = d
        for p in PERIODS:
            rec["act_" + p] = g.get(p)
            e = rec.get("roll_exp_" + p)
            rec["err_" + p] = (round(g[p] - e, 2)
                               if g.get(p) is not None and e is not None else None)
        # label transitions: the thing most likely to break
        for t in (g["home"], g["away"]):
            tag = (label(roll, t, "ft") or {}).get("tag")
            if tag and t in prev_tag and prev_tag[t] != tag:
                flips[t] += 1
                rec.setdefault("flipped", []).append(f"{t} {prev_tag[t]}->{tag}")
            if tag:
                prev_tag[t] = tag
        out.append(rec)
        if g["completed"]:
            push(roll, g)                            # frozen is never pushed, by design

    # Box scores are resolved before the temp file exists. A failure here
    # leaves the previous nba_pace.json untouched.
    prior = _prior_teams(OUT)
    teams = attach_teams(out, roll, prior, log=log)
    blob = dict(
        built=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        window=WINDOW, periods=list(PERIODS),
        seed=dict(span=[SEED_FROM.isoformat(), SEED_TO.isoformat()],
                  season=SEED_SEASON, games=len(seed_rows),
                  teams={t: {p: list(frozen[t][p]) for p in PERIODS} for t in frozen}),
        label_flips=dict(sorted(flips.items(), key=lambda kv: -kv[1])),
        skipped=skipped,
        teams=teams,
        games=out,
    )
    tmp = OUT + ".tmp"
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(tmp, "w") as f:
        json.dump(blob, f, indent=1, sort_keys=True)
        f.write("\n")
    os.replace(tmp, OUT)
    log(f"wrote {OUT}  ({len(out)} games, {sum(flips.values())} label flips)")
    return blob


# ---------------------------------------------------------------------------
# the checks: does the mechanism hold, and (secondary) is there any signal
# ---------------------------------------------------------------------------

def report(blob=None, log=print):
    blob = blob or json.load(open(OUT))
    allg = blob["games"]
    skips = [g for g in allg if g.get("skipped")]
    games = [g for g in allg if not g.get("skipped")]
    done = [g for g in games if g["completed"]]
    log(f"\nNBA PACE LABELS — built {blob['built']}, window {blob['window']}\n")

    log("MECHANISM (the pass/fail)")
    miss_exp = [g for g in games if g.get("roll_exp_ft") is None]
    miss_lab = [g for g in games if not g.get("roll_lab_home_ft") or not g.get("roll_lab_away_ft")]
    ungraded = [g for g in done if g.get("act_ft") is None]
    log(f"  games listed                 {len(allg)}")
    log(f"  skipped (unlabellable)       {len(skips)}"
        + (f"   {[g['home']+' v '+g['away'] for g in skips]}" if skips else ""))
    log(f"  labellable                   {len(games)}")
    log(f"  completed                    {len(done)}")
    log(f"  without a rolling expectation {len(miss_exp)}"
        + ("" if not miss_exp else f"  <-- {[g['id'] for g in miss_exp][:5]}"))
    log(f"  without both labels          {len(miss_lab)}")
    log(f"  completed but ungraded       {len(ungraded)}")
    thin = [g for g in games if (g.get("roll_home_n") or 0) < blob["window"]
            or (g.get("roll_away_n") or 0) < blob["window"]]
    log(f"  games with a short window    {len(thin)}")
    log(f"  label flips                  {sum(blob['label_flips'].values())}"
        + (f"   {dict(list(blob['label_flips'].items())[:6])}" if blob["label_flips"] else ""))

    if not done:
        log("\nno completed games yet — accuracy checks wait for results")
        return
    log("\nACCURACY (secondary; preseason is not expected to predict)")
    log(f"  {'period':8s}{'n':>4s}{'exp':>9s}{'actual':>9s}{'bias':>8s}{'MAE':>8s}{'corr':>8s}")
    for p in blob["periods"]:
        rows = [g for g in done if g.get("act_" + p) is not None
                and g.get("roll_exp_" + p) is not None]
        if not rows:
            log(f"  {p:8s}{0:>4d}       --       --      --      --      --")
            continue
        e = [g["roll_exp_" + p] for g in rows]
        a = [g["act_" + p] for g in rows]
        mean = lambda v: sum(v) / len(v)
        bias = mean(a) - mean(e)
        mae = mean([abs(x - y) for x, y in zip(a, e)])
        ma, mb = mean(e), mean(a)
        num = sum((x - ma) * (y - mb) for x, y in zip(e, a))
        den = (sum((x - ma) ** 2 for x in e) * sum((y - mb) ** 2 for y in a)) ** 0.5
        r = (num / den) if (den and len(rows) >= 3) else None
        rtxt = f"{r:>+8.3f}" if r is not None else f"{'n/a':>8s}"
        log(f"  {p:8s}{len(rows):>4d}{mean(e):>9.1f}{mean(a):>9.1f}"
            f"{bias:>+8.1f}{mae:>8.1f}{rtxt}")

    log("\n  by how many of the four traits are '+' (4 = both score more AND allow more)")
    log(f"  {'pluses':>7s}{'n':>4s}{'act ft':>9s}{'exp ft':>9s}")
    for k in (0, 1, 2, 3, 4):
        rows = [g for g in done if g.get("roll_pluses") == k and g.get("act_ft") is not None]
        if not rows:
            continue
        log(f"  {k:>7d}{len(rows):>4d}"
            f"{sum(g['act_ft'] for g in rows)/len(rows):>9.1f}"
            f"{sum(g['roll_exp_ft'] for g in rows)/len(rows):>9.1f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", action="store_true", help="build and print the seed only")
    ap.add_argument("--run", action="store_true", help="fetch, project, grade, save")
    ap.add_argument("--report", action="store_true", help="print the checks from the saved file")
    a = ap.parse_args()
    if a.seed:
        state, rows = build_seed()
        for t in sorted(state):
            o, d, n = rates(state, t, "ft")
            lab = label(state, t, "ft")
            print(f"  {t:4s} n={n}  scored {o:6.1f}  allowed {d:6.1f}  {lab['tag']}")
        return 0
    if a.run:
        report(run())
        return 0
    if a.report:
        report()
        return 0
    print(__doc__.strip().splitlines()[0])
    print("usage: python3 nba_pace.py --seed | --run | --report")
    return 0


if __name__ == "__main__":
    sys.exit(main())
