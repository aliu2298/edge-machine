#!/usr/bin/env python3
"""NBA quarter lines: Sandbox PAPER lane (Olu via the coordinator, 2026-11-23). Pre-registration: docs/nba_qlines_2026-11-23.md.

Six sections (1Q 2Q 3Q 4Q 1H 2H), each with an OVER line and an UNDER line on Kalshi's game-total series. A TRACKER rebuilds each team's season hit rate
at every line from ESPN's period scores, only from games already played. A GATE, checked at the entry read: a team qualifies on a line when its hit rate on
games before tonight is 90% or better over 10+ games; either team qualifying makes the game ONE entry. The entry is the Kalshi ask 15-40 minutes before
the tip (over = YES ask, under = NO at 1 - YES bid), spread 5c or less, taker fee, held to settlement. Each lane has a BLIND control: the same line in every
game that night with the same rung rule. Nothing is placed anywhere.
"""
import collections
import datetime as dt
import json
import math
import os
import sys
import urllib.parse
from zoneinfo import ZoneInfo

import daily_track as D
import fillsim as F
import nba_spotter as S
import settle_only

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data", "nba_qlines")
GAMES_PATH = os.path.join(DATA, "games.json")
PATH = os.path.join(ROOT, "data", "nba_qlines_ledger.json")
VERSION = "nba-qlines-v1"
REGISTERED = "2026-11-23"
ET = ZoneInfo("America/New_York")
SEASON_START = "2026-10-20"

# The lines are config: a change is a new registration (the rows keep the line they were entered at).
LINES = {
    "1Q": dict(series="KXNBA1QTOTAL", periods=(1,), over=51.5, under=59.5),
    "2Q": dict(series="KXNBA2QTOTAL", periods=(2,), over=50.5, under=63.5),
    "3Q": dict(series="KXNBA3QTOTAL", periods=(3,), over=53.5, under=64.5),
    "4Q": dict(series="KXNBA4QTOTAL", periods=(4,), over=48.5, under=62.5),
    "1H": dict(series="KXNBA1HTOTAL", periods=(1, 2), over=104.5, under=119.5),
    "2H": dict(series="KXNBA2HTOTAL", periods=(3, 4), over=100.5, under=115.5, ot=True),   # Kalshi's 2H total counts overtime (checked on settled games)
}
SECTIONS = tuple(LINES)
DIRS = ("over", "under")
THRESHOLD = 0.90          # hit rate to qualify
MIN_GAMES = 10            # games played before the rate counts
MAX_SPREAD = 0.05
WINDOW_MIN = (15, 40)     # minutes before tip: the read target is about 30
OFFSETS = (0, 1, 2, 3)    # points from the configured line, in the HARDER direction only
REVIEW_AT = (10, 30)
EPS = 1e-9
MAX_PER_RUN = 60
NAMES = {"1Q": "1st quarter", "2Q": "2nd quarter", "3Q": "3rd quarter", "4Q": "4th quarter", "1H": "1st half", "2H": "2nd half"}


def lane(sec, d, blind=False):
    return f"qlines_{sec}_{d}" + ("_blind" if blind else "")


ALL_LANES = tuple(lane(s, d, b) for s in SECTIONS for d in DIRS for b in (False, True))


def fee(p):
    return F.fee(p)


def cost(p):
    return p + fee(p)


def lane_label(sec, d, blind=False):
    return f"{NAMES[sec]} {d} {LINES[sec][d]}" + (" · blind control" if blind else "")


# ---------------------------------------------------------------- state
def empty():
    return {"version": VERSION, "registered": REGISTERED, "rules": {k: {"picks": []} for k in ALL_LANES}, "looks": {}, "runs": [], "schedule": [],
            "last_run": None, "error": None}


def load(path=PATH):
    if os.path.exists(path):
        with open(path) as f:
            st = json.load(f)
        for k in ALL_LANES:
            st.setdefault("rules", {}).setdefault(k, {"picks": []})
        return st
    return empty()


def save(state, path=PATH):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=1, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


def load_games(path=GAMES_PATH):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"games": []}


def save_games(doc, path=GAMES_PATH):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(doc, f, separators=(",", ":"))
    os.replace(tmp, path)


def night_of(tip):
    return tip.astimezone(ET).date().isoformat()


# ---------------------------------------------------------------- the pulls (ESPN period scores)
def game_from_event(e):
    """One finished regular-season game from the scoreboard: {id, t, day, home, away, ls: {team: [period points]}} or None."""
    c = e["competitions"][0]
    if e.get("season", {}).get("type") != 2 or c["status"]["type"]["name"] != "STATUS_FINAL":
        return None
    ls, home, away = {}, None, None
    for t in c["competitors"]:
        ab = t["team"]["abbreviation"]
        pts = [int(float(x.get("value", 0))) for x in sorted(t.get("linescores") or [], key=lambda x: x.get("period", 0))]
        ls[ab] = pts
        if t["homeAway"] == "home":
            home = ab
        else:
            away = ab
    if not home or not away or any(len(v) < 4 for v in ls.values()):
        return None
    tip = dt.datetime.fromisoformat(e["date"].replace("Z", "+00:00"))
    return dict(id=str(e["id"]), t=tip.timestamp(), day=night_of(tip), home=home, away=away, ls=ls)


def refresh_games(doc, now, get=S.espn_get, limit=MAX_PER_RUN):
    """Add every finished game from the day before the last stored day to today (ET). Returns (new, errors)."""
    have = {g["id"] for g in doc["games"]}
    last_day = max((g["day"] for g in doc["games"]), default=SEASON_START)
    d = dt.date.fromisoformat(last_day) - dt.timedelta(days=1)
    today = now.astimezone(ET).date()
    new, errs = 0, []
    while d <= today:
        try:
            evs = get(S.ESPN_SB % d.strftime("%Y%m%d")).get("events", [])
        except Exception as e:                                       # noqa: BLE001
            errs.append(f"scoreboard {d}: {str(e)[:60]}")
            d += dt.timedelta(days=1)
            continue
        for e in evs:
            try:
                g = game_from_event(e)
            except Exception as ex:                                  # noqa: BLE001
                errs.append(f"event {e.get('id')}: {str(ex)[:60]}")
                continue
            if g and g["id"] not in have:
                doc["games"].append(g)
                have.add(g["id"])
                new += 1
        d += dt.timedelta(days=1)
    doc["games"].sort(key=lambda g: (g["t"], g["id"]))
    return new, errs


# ---------------------------------------------------------------- the tracker
def total(game, periods, ot=False):
    """The game's combined points over the given regulation periods (1-4), plus every overtime period when ot; None if a period is missing."""
    s = 0
    for ab in (game["home"], game["away"]):
        v = game["ls"].get(ab) or []
        if len(v) < max(periods):
            return None
        s += sum(v[p - 1] for p in periods) + (sum(v[4:]) if ot else 0)
    return s


def hit(game, sec, d):
    """True/False: did the game land on the over (above) or under (below) side of the configured line; None if unscorable."""
    cfg = LINES[sec]
    t = total(game, cfg["periods"], cfg.get("ot", False))
    if t is None:
        return None
    return t > cfg[d] if d == "over" else t < cfg[d]


def team_rows(games, sec, d, before=None, threshold=THRESHOLD, min_games=MIN_GAMES):
    """{team: dict(hits, n, rate, qualifies, since)} from the games played (before the night `before`, an ISO date, when given).
    `since` is the night a team's current qualifying run began: the first night after the game that put it over the bar."""
    played = collections.defaultdict(list)
    for g in sorted(games, key=lambda g: (g["t"], g["id"])):
        if before is not None and g["day"] >= before:
            continue
        h = hit(g, sec, d)
        if h is None:
            continue
        for ab in (g["home"], g["away"]):
            played[ab].append((g["day"], h))
    out = {}
    for team, seq in played.items():
        hits = n = 0
        since, ok_prev = None, False
        for i, (day, h) in enumerate(seq):
            n += 1
            hits += 1 if h else 0
            ok = n >= min_games and hits / n >= threshold - EPS
            if ok and not ok_prev:
                since = day                      # qualified after this game; eligible from the next night
            if not ok:
                since = None
            ok_prev = ok
        out[team] = dict(hits=hits, n=n, rate=hits / n if n else None, qualifies=ok_prev, since=since if ok_prev else None)
    return out


# ---------------------------------------------------------------- Kalshi markets
def event_teams(m):
    suf = m["event_ticker"].split("-")[1][7:]
    return S.K2E.get(suf[:3], suf[:3]), S.K2E.get(suf[3:], suf[3:])      # (away, home)


def kalshi_markets(day_tags, fetch=D.get):
    """{section: [market]}: open markets of each section's series for events dated in day_tags (e.g. '26NOV23')."""
    out = {}
    for sec, cfg in LINES.items():
        v, cur = [], None
        for _ in range(4):
            r = fetch(f"markets?series_ticker={cfg['series']}&status=open&limit=1000" + (f"&cursor={urllib.parse.quote(cur, safe='')}" if cur else ""))
            v += r.get("markets") or []
            cur = r.get("cursor")
            if not cur or not r.get("markets"):
                break
        out[sec] = [m for m in v if m["event_ticker"].split("-")[1][:7] in day_tags]
    return out


def pick_rung(markets, g, sec, d):
    """The rung for one game, section and direction: (row or None, why). The configured line if listed, else the nearest listed rung 1-3 points away in the
    HARDER direction only (higher for an over, lower for an under). The nearest listed rung is used; a bad quote on it is no entry."""
    mine = [m for m in markets.get(sec, []) if event_teams(m) == (g["away"], g["home"]) and m.get("floor_strike") is not None]
    if not mine:
        return None, "no market"
    L = LINES[sec][d]
    sign = 1 if d == "over" else -1
    by = {round(float(m["floor_strike"]), 2): m for m in mine}
    for off in OFFSETS:
        m = by.get(round(L + sign * off, 2))
        if m is None:
            continue
        bid, ask = D.number(m.get("yes_bid_dollars")), D.number(m.get("yes_ask_dollars"))
        if bid is None or ask is None or not 0 < ask < 1 or not 0 <= bid <= ask:
            return None, "no quote"
        if ask - bid > MAX_SPREAD + EPS:
            return None, "wide"
        price = ask if d == "over" else round(1 - bid, 4)
        if not 0 < price < 1:
            return None, "no quote"
        return dict(ticker=m["ticker"], rung=float(m["floor_strike"]), offset=off, bid=bid, ask=ask, price=price, side="yes" if d == "over" else "no"), None
    return None, "no rung within 3 points"


# ---------------------------------------------------------------- entries
def due(games, now, looks):
    if settle_only.on():
        return []
    lo, hi = WINDOW_MIN
    return [g for g in games if g["id"] not in looks and lo <= (g["tip"] - now).total_seconds() / 60 <= hi]


def _row(sec, d, blind, g, night, rung, now, extra):
    ln = lane(sec, d, blind)
    return dict(id=f"{ln}:{rung['ticker']}", rule=ln, section=sec, direction=d, night=night, game=f"{g['away']} @ {g['home']}", game_id=g["id"],
                start=g["tip"].isoformat(), ticker=rung["ticker"], line=LINES[sec][d], rung=rung["rung"], offset=rung["offset"], side=rung["side"],
                bid=rung["bid"], ask=rung["ask"], price=rung["price"], entered=now.isoformat(), lead_min=round((g["tip"] - now).total_seconds() / 60, 1),
                status="open", **extra)


def look_many(state, games_doc, due_games, markets, now):
    """Enter the lane and blind rows of every game read in this run. Returns the new row ids."""
    new = []
    for g in due_games:
        night = night_of(g["tip"])
        skips = collections.Counter()
        entered = collections.Counter()
        seen = 0
        for sec in SECTIONS:
            for d in DIRS:
                rung, why = pick_rung(markets, g, sec, d)
                if rung is None:
                    skips[f"{sec} {d}: {why}"] += 1
                    continue
                seen += 1
                rows = team_rows(games_doc["games"], sec, d, before=night)
                qual = [t for t in (g["home"], g["away"]) if (rows.get(t) or {}).get("qualifies")]
                info = {t: f"{rows[t]['hits']}/{rows[t]['n']}" for t in (g["home"], g["away"]) if t in rows}
                blind = _row(sec, d, True, g, night, rung, now, dict(teams=info))
                state["rules"][lane(sec, d, True)]["picks"].append(blind)
                new.append(blind["id"])
                entered[f"{sec} {d} blind"] += 1
                if qual:
                    pk = _row(sec, d, False, g, night, rung, now, dict(qualifying=qual, teams=info, matches=blind["id"]))
                    state["rules"][lane(sec, d)]["picks"].append(pk)
                    new.append(pk["id"])
                    entered[f"{sec} {d}"] += 1
        if seen or now >= g["tip"] - dt.timedelta(minutes=WINDOW_MIN[0] + 1):
            state["looks"][g["id"]] = dict(at=now.isoformat(), game=f"{g['away']} @ {g['home']}", night=night, priced=seen, skipped=dict(skips),
                                           entered=dict(entered), lead_min=round((g["tip"] - now).total_seconds() / 60, 1))
    return new


# ---------------------------------------------------------------- settle
def settle_row(row, payout):
    """payout is 1 or 0 for YES. The side bought pays 1 - payout for a NO. profit is dollars a contract after fees; ret a fraction of the cost."""
    px = row["price"]
    c = cost(px)
    pay = payout if row["side"] == "yes" else 1.0 - payout
    row["fee_in"] = round(fee(px), 4)
    row["payout"] = pay
    row["profit"] = round(pay - c, 4)
    row["ret"] = round(row["profit"] / c, 4)
    row["status"] = "won" if pay == 1 else "lost"
    return row


def settle(state, now, fetch=D.get):
    errs = []
    for ln in state["rules"].values():
        for row in ln["picks"]:
            if row["status"] != "open":
                continue
            if now < dt.datetime.fromisoformat(row["start"]) + dt.timedelta(hours=2):
                continue
            try:
                mk = fetch("markets/" + urllib.parse.quote(row["ticker"], safe="")).get("market", {})
                px = D.payout(mk)
                if px is None:
                    continue
                if 0 < px < 1:                                           # a scalar settlement is no result: left out of every record
                    row.update(status="void", payout=px, settled=now.isoformat())
                    continue
                settle_row(row, float(px))
                row["settled"] = now.isoformat()
            except Exception as e:                                   # noqa: BLE001
                errs.append(row["id"] + ": " + str(e)[:80])
    return errs


# ---------------------------------------------------------------- the record
def stats(picks):
    """n settled, won, open, return on cost, mean price, nights."""
    done = [p for p in picks if p.get("profit") is not None]
    out = dict(n=len(done), won=sum(1 for p in done if p["profit"] > 0), open=sum(1 for p in picks if p["status"] == "open"), ret=None, price=None, nights=0)
    if done:
        out["ret"] = sum(p["profit"] for p in done) / sum(cost(p["price"]) for p in done)
        out["price"] = sum(p["price"] for p in done) / len(done)
        out["nights"] = len({p["night"] for p in done})
    return out


def status_text(n):
    if n < REVIEW_AT[0]:
        return f"{n} of {REVIEW_AT[0]} settled · read at {REVIEW_AT[0]}"
    if n < REVIEW_AT[1]:
        return f"{n} settled · first read ({REVIEW_AT[0]}) due · next at {REVIEW_AT[1]}"
    return f"{n} settled · second read ({REVIEW_AT[1]}) due"


# ---------------------------------------------------------------- run
def slate(now, get=S.espn_get):
    """Games not yet started with the tip inside the next day: [dict(id, tip, home, away)]."""
    out = {}
    for d in {now.astimezone(ET).date(), (now + dt.timedelta(hours=20)).astimezone(ET).date(), now.date()}:
        for e in get(S.ESPN_SB % d.strftime("%Y%m%d")).get("events", []):
            c = e["competitions"][0]
            if e.get("season", {}).get("type") != 2 or c["status"]["type"]["name"] != "STATUS_SCHEDULED":
                continue
            tip = dt.datetime.fromisoformat(e["date"].replace("Z", "+00:00"))
            out[str(e["id"])] = dict(id=str(e["id"]), tip=tip, home=next(t["team"]["abbreviation"] for t in c["competitors"] if t["homeAway"] == "home"),
                                     away=next(t["team"]["abbreviation"] for t in c["competitors"] if t["homeAway"] == "away"))
    return sorted(out.values(), key=lambda g: (g["tip"], g["id"]))


def run(state, games_doc, now=None, get=S.espn_get, fetch=D.get):
    """One pass: new finals into the played games, entries for games 15-40 minutes from tip, then settle. Returns (new row ids, errors)."""
    now = now or dt.datetime.now(dt.timezone.utc)
    for k in ALL_LANES:
        state["rules"].setdefault(k, {"picks": []})
    errs, new, nnew = [], [], 0
    try:
        nnew, e = refresh_games(games_doc, now, get)
        errs += e
    except Exception as e:                                           # noqa: BLE001
        errs.append(f"games refresh: {str(e)[:80]}")
    try:
        games = slate(now, get)
    except Exception as e:                                           # noqa: BLE001
        games = []
        errs.append(f"slate: {str(e)[:80]}")
    state["schedule"] = [g["tip"].isoformat() for g in games]
    todo = due(games, now, state["looks"])
    if todo:
        try:
            tags = {S.day_tag(g["tip"].astimezone(ET).date()) for g in todo}
            new += look_many(state, games_doc, todo, kalshi_markets(tags, fetch), now)
        except Exception as e:                                       # noqa: BLE001
            errs.append(f"entries: {str(e)[:100]}")
    errs += settle(state, now, fetch)
    state["last_run"] = now.isoformat()
    state["games_through"] = max((g["day"] for g in games_doc["games"]), default=None)
    state["error"] = "; ".join(errs)[:1000] or None
    state["runs"] = (state.get("runs") or [])[-50:] + [dict(at=now.isoformat(), new=len(new), due=len(todo), games=nnew)]
    return new, errs


def main(argv=None):
    now = dt.datetime.now(dt.timezone.utc)
    games_doc = load_games()
    state = load()
    new, errs = run(state, games_doc, now)
    save(state)
    save_games(games_doc)
    print("nba_qlines", state["runs"][-1], "new", new, "errors", errs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
