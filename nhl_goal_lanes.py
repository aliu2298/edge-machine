"""nhl_goal_lanes: two NHL in-play lanes 3 minutes after a goal (2026-11-08, Olu: "yes, assign both"). Sandbox PAPER.

WHERE THEY COME FROM. ~/edge-research/nhl_shapes_2026-11-08/ (README; screen pre-registered 2026-11-08T05:04Z): a full
breakdown of the Kalshi NHL markets (moneyline, totals, puck line, period markets, team totals, props) at five moments,
both sides, six pre-match filters. Nothing passed Bonferroni (6,287 tests, 53 positive v ~314 expected by chance), so
there is no edge claim here. Two cells pointed the same way in discovery, on every trade print and on a holdout, and are
kept as WATCH cells. These lanes are their forward test, frozen exactly as the study measured them.

THE RULES, pre-registered here (2026-11-08T07:45Z) before any game they read had started:

  GOAL MOMENT  ESPN's NHL play-by-play gives each goal (periods 1-3 and overtime, not the shootout) a wallclock. The goal is
               timed by the moneyline's own reaction: the first minute candle in [wall - 4 min, wall + 6 min] where the
               home-win mid (the mean of the home market's mid and 1 - the away market's mid) has moved 3c+ toward the
               scorer from its value at wall - 4 min, one minute per goal. The ENTRY is 3 minutes after that minute,
               dropped when another goal lands in between. One entry per goal moment and market rung, each its own row.
  QUOTE        the last 1-minute candle at or before the entry: bid and ask both present, ask above bid, spread 5c or less,
               the candle no older than 3 minutes, the market not within a minute of its close. NO ask = 1 - YES bid.
  STATE        "none" (the study's headline): no check of the game state beyond the score at the entry. "v2" is recorded
               on every row and shown in the fold: every ESPN goal up to 5 minutes after the entry was price-timed, each
               to its own minute. No later goal decides which rows count.
  FILL         taker at the ask, real only when 50+ contracts print at or through it on our side within 5 minutes of the
               entry (a NO print = 1 - the YES price). Taker fee 0.07 p(1-p). Held to settlement. A row with no such
               depth is logged as "no fill" and is not in the record.
  MAKER (fold) a resting bid at the side's bid, filled by a print strictly through it within 15 minutes, maker fee
               0.0175 p(1-p), held. Shown beside the taker record, never its headline.

  nhl_pl_no_goal   KXNHLSPREAD, the pre-match FAVOURITE's rung that needs exactly 2 more goals of margin at the entry
                   (e.g. "wins by over 1.5" with the score tied), NO at 65-80c, THIN pre-match book only.
                   Favourite = the side of the home-win mid an hour before ESPN's start (T-1h). Thin book = KXNHLGAME volume
                   over T-80 min -> T-1h, both team markets, under 4,873 contracts (the discovery median, frozen).
     research    discovery Oct 6 - Nov 7 2026: +15.8% on 71 games (binomial p 0.012); every trade print, taker with depth:
                 +17.8% (46 games), maker +20.5%; halves +33% / +8%; holdout Mar 6 - Apr 17 2026: +19.0% on 25 games
                 (p 0.095). Fails Bonferroni. Its headline read is at about 60 games.
  nhl_pl_no_goal_all   BASELINE: the same rule on every game, thin or deep book.

  nhl_over_goal    KXNHLTOTAL, YES at 91-95c on every rung still needing a goal at the entry (the study's blind cell).
     research    discovery +3.7% on 197 games; trade check taker with depth +4.1% (p 0.008), maker +6.0% (p 0.004),
                 halves +4% / +4%; holdout +3.8% on 56 games (p 0.43).
  nhl_over_goal_all    BASELINE: every YES over rung at 65-99c after a goal. The study's cell is already every 91-95c rung,
                   so the baseline is the whole expensive over side it was cut from.

RECORD: fresh from REGISTERED: only games ESPN starts at or after it count; nothing is replayed (an earlier game would be
in-sample and is skipped with a reason). One row per entry, z clustered by game, ROI per entry after fees. Review at 10
settled entries, decide at 30.

Read after the fact: every settled KXNHLGAME event is read once, from its 1-minute candles, its puck-line and totals
markets and their trade prints. Own ledger data/nhl_goal_lanes_ledger.json, hourly by .github/workflows/nhl-goal.yml.
Paper only: no order is placed.
"""
import datetime as dt
import json
import math
import os
import re
import statistics as stat
import sys

import chaos_lanes as CL
import chaos_replay as C
import daily_track as D

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "data", "nhl_goal_lanes_ledger.json")
VERSION = "nhlgoal-v1"
REGISTERED = "2026-11-08T07:45:00Z"
SINCE = "2026-11-08"
GAME, SPREAD, TOTAL = "KXNHLGAME", "KXNHLSPREAD", "KXNHLTOTAL"
ESPN_PATH = "hockey/nhl"
EPS = 1e-9
UTC = dt.timezone.utc

# --- the study's frozen numbers
PRE_S = 3600                    # T-1h
VOL_WIN_S = 1200                # volume over T-80 min -> T-1h
THIN_VOL = 4873.485             # the discovery median of that volume
GOAL_LO_S, GOAL_HI_S = 240, 360  # the price-timing window around ESPN's wallclock
GOAL_MOVE = 0.03
ENTRY_S = 180
MAX_SPREAD = 0.05
STALE_S = 180
DEPTH_S, DEPTH_MIN = 300, 50.0
MAKER_S = 900
TAKER_K, MAKER_K = 0.07, 0.0175
NEED = 2
SKIP_AFTER_D = 3
MAX_GAMES_PER_RUN = 40
REVIEW_N, DECIDE_N, HEADLINE_GAMES = 10, 30, 60

LANES = (
    dict(lane="nhl_pl_no_goal", kind="pl", band=(0.65, 0.80), thin=True, baseline=False,
         label="NHL puck line NO after a goal · favourite needs 2 · thin book", market="Puck line · NO",
         research="Discovery +15.8% on 71 games, every trade print +17.8%, holdout +19.0% on 25 games (p 0.095). "
                  "Fails the multiple-test bar: a forward test, not a bet. Headline read at about 60 games."),
    dict(lane="nhl_pl_no_goal_all", kind="pl", band=(0.65, 0.80), thin=None, baseline=True,
         label="Baseline · puck line NO after a goal, every book", market="Puck line · NO",
         research="The same rule without the thin-book filter. The lane must beat it."),
    dict(lane="nhl_over_goal", kind="over", band=(0.91, 0.95), thin=None, baseline=False,
         label="NHL over YES 91-95c after a goal", market="Total goals · YES",
         research="Discovery +3.7% on 197 games, every trade print +4.1% taker and +6.0% maker, holdout +3.8% on 56 games. "
                  "Not significant on its own: a forward test, not a bet."),
    dict(lane="nhl_over_goal_all", kind="over", band=(0.65, 0.99), thin=None, baseline=True,
         label="Baseline · over YES 65-99c after a goal", market="Total goals · YES",
         research="Every expensive over rung after a goal. The lane must beat it."),
)
BY_LANE = {c["lane"]: c for c in LANES}


# ------------------------------------------------------------------ pure pieces (the study's screen.py, unchanged)
def compact(cs):
    """Kalshi candles -> [ts, yes_bid_close, yes_ask_close, yes_bid_high, price_high, price_close, volume, yes_ask_low].
    Archived candles carry "close", live ones "close_dollars"."""
    out = []
    for c in sorted(cs or [], key=lambda c: c.get("end_period_ts") or 0):
        p, yb, ya = c.get("price") or {}, c.get("yes_bid") or {}, c.get("yes_ask") or {}
        out.append([c.get("end_period_ts"), C._f(yb, "close"), C._f(ya, "close"), C._f(yb, "high"), C._f(p, "high"),
                    C._f(p, "close"), D.number(c.get("volume_fp", c.get("volume"))) or 0.0, C._f(ya, "low")])
    return out


def series_at(rows, ts):
    """(bid, ask, last row ts) at or before ts, each side carried from its last printed value."""
    b = a = last = None
    for r in rows or []:
        if r[0] is None or r[0] > ts:
            break
        if r[1] is not None:
            b = r[1]
        if r[2] is not None:
            a = r[2]
        last = r[0]
    return b, a, last


def home_mid(hc, ac, ts):
    xs = []
    b1, a1, _ = series_at(hc, ts)
    b2, a2, _ = series_at(ac, ts)
    if b1 is not None and a1 is not None:
        xs.append((b1 + a1) / 2)
    if b2 is not None and a2 is not None:
        xs.append(1 - (b2 + a2) / 2)
    return sum(xs) / len(xs) if xs else None


def time_goals(goals, hmid):
    """Set goal["tj"]: the first minute in [wall-4m, wall+6m] where the home-win mid moved 3c+ toward the scorer, one
    minute per goal, else None. `goals` sorted by wall, each {wall, side}."""
    used = set()
    for x in goals:
        x["tj"] = None
        dirn = 1 if x["side"] == "home" else -1
        lo = x["wall"] - GOAL_LO_S
        lo -= lo % 60
        base = hmid(lo)
        if base is None:
            continue
        for t in range(lo + 60, x["wall"] + GOAL_HI_S + 1, 60):
            v = hmid(t)
            if v is not None and (v - base) * dirn >= GOAL_MOVE - EPS and t not in used:
                x["tj"] = t
                used.add(t)
                break
    return goals


def _seen(y):
    return min(y["wall"], y["tj"] or 1e18)


def moments(goals):
    """[(entry ts, goal)]: 3 min after each price-timed goal, unless another goal lands in between."""
    out = []
    for x in goals:
        if not x.get("tj"):
            continue
        ent = x["tj"] + ENTRY_S
        if any(y is not x and x["tj"] < _seen(y) <= ent for y in goals):
            continue
        out.append((ent, x))
    return out


def valid_v2(goals, ts):
    near = [x.get("tj") for x in goals if x["wall"] <= ts + 300 or (x.get("tj") and x["tj"] <= ts)]
    return all(near) and len(set(near)) == len(near)


def score(goals, ts):
    h = sum(1 for x in goals if _seen(x) <= ts and x["side"] == "home")
    a = sum(1 for x in goals if _seen(x) <= ts and x["side"] == "away")
    return h, a


def quote(rows, ts, close):
    """(yes bid, yes ask) usable at ts under the study's rules, else None."""
    if close and ts >= close - 60:
        return None
    yb, ya, last = series_at(rows, ts)
    if last is None or yb is None or ya is None or ya - yb > MAX_SPREAD + EPS or ya <= yb or ts - last > STALE_S:
        return None
    return yb, ya


def pre_match(hc, ac, ko):
    """(favourite side or None, favourite mid, GAME volume T-80m -> T-1h)."""
    pre = ko - PRE_S
    hp = home_mid(hc, ac, pre)
    fav = None if hp is None or abs(hp - 0.5) < 0.01 else ("home" if hp > 0.5 else "away")
    vol = sum(r[6] or 0 for c in (hc, ac) for r in c if r[0] is not None and pre - VOL_WIN_S < r[0] <= pre)
    return fav, (None if hp is None else max(hp, 1 - hp)), vol


def team_of(ticker, home, away):
    code = re.sub(r"\d+$", "", str(ticker).rsplit("-", 1)[-1])
    return "home" if code == home else "away" if code == away else None


def candidates(goals, fav, home, away, spread_mk, total_mk, rows_of):
    """Every in-band row at every goal moment. spread_mk / total_mk: [{ticker, strike, close}]; rows_of(ticker) -> rows."""
    out = []
    for ts, g in moments(goals):
        h, a = score(goals, ts)
        base = dict(ts=ts, goal_side=g["side"], period=g.get("per"), home_goals=h, away_goals=a, v2=valid_v2(goals, ts))
        for m in spread_mk:
            team = team_of(m["ticker"], home, away)
            if fav is None or team != fav or m.get("strike") is None:
                continue
            marg = (h - a) if team == "home" else (a - h)
            if math.floor(m["strike"]) + 1 - marg != NEED:
                continue
            q = quote(rows_of(m["ticker"]), ts, m.get("close"))
            if q is None:
                continue
            ask, bid = round(1 - q[0], 4), round(1 - q[1], 4)
            if 0.65 - EPS <= ask <= 0.80 + EPS:
                out.append(dict(base, kind="pl", ticker=m["ticker"], strike=m["strike"], side="no", ask=ask, bid=bid))
        for m in total_mk:
            if m.get("strike") is None or math.floor(m["strike"]) + 1 - (h + a) <= 0:
                continue
            q = quote(rows_of(m["ticker"]), ts, m.get("close"))
            if q is None:
                continue
            bid, ask = round(q[0], 4), round(q[1], 4)
            if 0.65 - EPS <= ask <= 0.99 + EPS:
                out.append(dict(base, kind="over", ticker=m["ticker"], strike=m["strike"], side="yes", ask=ask, bid=bid))
    return out


def side_px(side, yes):
    return yes if side == "yes" else 1 - yes


def fills(e, prints, won):
    """Taker (depth 50+ at or through the ask within 5 min) and maker (a print through the bid within 15 min), held."""
    ts, ask, bid = e["ts"], e["ask"], e["bid"]
    pay = 1.0 if won else 0.0
    depth = sum(n for t, y, n in prints if ts < t <= ts + DEPTH_S and side_px(e["side"], y) <= ask + EPS)
    c = ask + TAKER_K * ask * (1 - ask)
    taker = dict(filled=depth >= DEPTH_MIN - EPS, depth=round(depth, 2), cost=round(c, 5), roi=round((pay - c) / c, 4))
    hit = next((t for t, y, n in prints if ts < t <= ts + MAKER_S and side_px(e["side"], y) < bid - EPS), None)
    cm = bid + MAKER_K * bid * (1 - bid)
    maker = dict(filled=hit is not None, cost=round(cm, 5), roi=round((pay - cm) / cm, 4) if hit is not None else None)
    return taker, maker


# ------------------------------------------------------------------ fetching
def espn_game(event, board_fn=None):
    """The ESPN scoreboard event whose away + home abbreviations spell the ticker's codes, or None."""
    board_fn = board_fn or (lambda day: CL._board(ESPN_PATH, day))
    day = C.event_date(event)
    if not day:
        return None
    want = re.sub(r"^.*?-\d\d[A-Z]{3}\d\d", "", event)
    for k in (0, -1, 1):
        for ev in board_fn(day + dt.timedelta(days=k)) or []:
            comp = (ev.get("competitions") or [{}])[0]
            side = {c.get("homeAway"): c for c in comp.get("competitors") or []}
            ab = lambda s: ((side.get(s) or {}).get("team") or {}).get("abbreviation", "")   # noqa: E731
            if ab("away") + ab("home") == want and ev.get("date"):
                return dict(id=ev.get("id"), date=ev["date"], home=ab("home"), away=ab("away"),
                            home_id=str(((side.get("home") or {}).get("team") or {}).get("id")),
                            away_id=str(((side.get("away") or {}).get("team") or {}).get("id")),
                            done=bool((((comp.get("status") or {}).get("type")) or {}).get("completed")))
    return None


def espn_goals(game_id, summary_fn=None):
    """[(wall ts, team id, period)] of the scoring plays in periods 1-4 (overtime in, shootout out)."""
    summary_fn = summary_fn or (lambda gid: CL._get_json(f"{CL.ESPN_SITE}/{ESPN_PATH}/summary?event={gid}"))
    s = summary_fn(game_id) or {}
    out = []
    for p in s.get("plays") or []:
        if not p.get("scoringPlay"):
            continue
        per = (p.get("period") or {}).get("number") or 0
        wall = C._ts(p.get("wallclock"))
        if wall and per <= 4:
            out.append((wall, str((p.get("team") or {}).get("id")), per))
    return out, bool(s.get("plays"))


def fetch_prints(ticker, lo, hi, fetch):
    """[(ts, yes price, contracts)] of the market's trades in [lo, hi], live endpoint first, then the archive."""
    for base in ("markets/trades", "historical/trades"):
        rows, cur = [], None
        for _ in range(10):
            d = fetch(f"{base}?ticker={ticker}&min_ts={lo}&max_ts={hi}&limit=1000" + (f"&cursor={cur}" if cur else ""))
            rows += d.get("trades") or []
            cur = d.get("cursor")
            if not cur or not d.get("trades"):
                break
        if rows:
            out = [(C._ts(t.get("created_time")), D.number(t.get("yes_price_dollars")), D.number(t.get("count_fp")) or 0.0)
                   for t in rows]
            return sorted(x for x in out if x[0] is not None and x[1] is not None)
    return []


def _mk(ms):
    return [dict(ticker=m["ticker"], strike=D.number(m.get("floor_strike")), close=C._ts(m.get("close_time")),
                 result=C.settled_result(m)) for m in ms]


def replay(event, fetch, now, board_fn=None, summary_fn=None):
    """(game record, None) for a settled game, (None, reason) to skip it for good, (None, None) to retry later."""
    gms, archived = C.event_markets(event, fetch)
    if not gms or any(C.settled_result(m) is None for m in gms):
        return None, None
    g = espn_game(event, board_fn)
    day = C.event_date(event)
    stale = day is not None and (now.date() - day).days > SKIP_AFTER_D
    if g is None or not g["done"]:
        return (None, "no completed ESPN game for the team codes") if stale else (None, None)
    ko = C._ts(g["date"])
    if ko is None:
        return None, "no ESPN start time"
    if ko < C._ts(REGISTERED):
        return None, "started before the lanes were registered (in-sample, not replayed)"
    plays, have = espn_goals(g["id"], summary_fn)
    if not have:
        return (None, "no ESPN play-by-play") if stale else (None, None)
    suf = event.split("-", 1)[1]
    hm = next((m for m in gms if team_of(m["ticker"], g["home"], g["away"]) == "home"), None)
    am = next((m for m in gms if team_of(m["ticker"], g["home"], g["away"]) == "away"), None)
    if hm is None or am is None:
        return None, "moneyline markets do not match the team codes"
    close = max((C._ts(m.get("close_time")) or 0) for m in gms) or (ko + 4 * 3600)
    lo, hi = ko - PRE_S - VOL_WIN_S - 300, close - close % 60 + 60
    gc = C.fetch_candles(GAME, event, gms, lo, hi, fetch, archived)
    hc, ac = compact(gc.get(hm["ticker"])), compact(gc.get(am["ticker"]))
    fav, favmid, vol = pre_match(hc, ac, ko)
    goals = sorted([dict(wall=w, side="home" if tid == g["home_id"] else "away" if tid == g["away_id"] else None, per=per)
                    for w, tid, per in plays], key=lambda x: x["wall"])
    goals = [x for x in goals if x["side"]]
    time_goals(goals, lambda t: home_mid(hc, ac, t))
    rows, mk = {}, {}
    for ser in (SPREAD, TOTAL):
        ev = f"{ser}-{suf}"
        ms, arch = C.event_markets(ev, fetch)
        mk[ser] = _mk(ms)
        if ms and moments(goals):
            rows.update({t: compact(c) for t, c in C.fetch_candles(ser, ev, ms, lo, hi, fetch, arch).items()})
    cands = candidates(goals, fav, g["home"], g["away"], mk[SPREAD], mk[TOTAL], lambda t: rows.get(t) or [])
    res = {m["ticker"]: m["result"] for ser in mk for m in mk[ser]}
    if any(res.get(c["ticker"]) is None for c in cands):
        return None, None
    entries = []
    for c in cands:
        won = res[c["ticker"]] == c["side"]
        taker, maker = fills(c, fetch_prints(c["ticker"], c["ts"], c["ts"] + MAKER_S, fetch), won)
        entries.append(dict(c, won=won, taker=taker, maker=maker))
    title = f'{g["away"]} at {g["home"]}'
    return dict(event=event, title=title, ko=ko, day=day.isoformat() if day else None, fav=fav, favmid=favmid,
                vol=round(vol, 2), thin=vol < THIN_VOL, goals=len(goals), timed=sum(1 for x in goals if x["tj"]),
                entries=entries, logged=now.isoformat(), version=VERSION), None


# ------------------------------------------------------------------ the ledger
def empty():
    return dict(version=VERSION, registered=REGISTERED, since=SINCE, games=[], skips={}, last_run=None, error=None)


def load(path=PATH):
    try:
        with open(path) as f:
            s = json.load(f)
    except FileNotFoundError:
        return empty()
    for k, v in empty().items():
        s.setdefault(k, v)
    return s


def save(state, path=PATH):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=1, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


def run(state, now=None, fetch=D.get, board_fn=None, summary_fn=None):
    """Read every settled NHL game since the record began, once."""
    now = now or dt.datetime.now(UTC)
    lo = dt.date.fromisoformat(state["since"])
    seen = {g["event"] for g in state["games"]} | set(state["skips"])
    errors, done = [], 0
    try:
        events = C.list_events(GAME, lo, fetch, until=now.date(), cap=600)
    except Exception as exc:                                    # noqa: BLE001
        events, _ = [], errors.append(f"listing: {str(exc)[:80]}")
    for event in sorted(events):
        day = C.event_date(event)
        if event in seen or day is None or day < lo:
            continue
        if done >= MAX_GAMES_PER_RUN:
            break
        try:
            rec, why = replay(event, fetch, now, board_fn, summary_fn)
        except Exception as exc:                                # noqa: BLE001
            errors.append(f"{event}: {str(exc)[:80]}")
            continue
        if rec is None and why is None:
            continue
        if why:
            state["skips"][event] = why
        else:
            state["games"].append(rec)
        done += 1
    state["games"].sort(key=lambda g: (g["ko"], g["event"]))
    state["last_run"] = now.isoformat()
    state["error"] = "; ".join(errors)[:600] or None
    return state


# ------------------------------------------------------------------ the record
def rows_for(state, lane):
    """Every logged row of one lane (filled or not), oldest first, each with its game's fields."""
    cfg = BY_LANE[lane]
    lo, hi = cfg["band"]
    out = []
    for g in state.get("games") or []:
        if cfg["thin"] is not None and bool(g.get("thin")) != cfg["thin"]:
            continue
        for e in g.get("entries") or []:
            if e["kind"] == cfg["kind"] and lo - EPS <= e["ask"] <= hi + EPS:
                out.append(dict(e, event=g["event"], title=g["title"], ko=g["ko"], day=g["day"]))
    return sorted(out, key=lambda r: (r["ts"], r["ticker"]))


def z_by_game(xs):
    """Mean over its standard error with every game's deviations summed first (rows in a game move together)."""
    if len({g for _, g in xs}) < 3:
        return None
    mu = stat.mean(v for v, _ in xs)
    by = {}
    for v, g in xs:
        by[g] = by.get(g, 0.0) + (v - mu)
    var = sum(s * s for s in by.values()) / len(xs) ** 2
    return mu / math.sqrt(var) if var > 0 else None


def summary(rows, mode="taker"):
    """The record of the rows that filled under `mode`: entries, games, wins v priced, ROI per entry, z by game, halves."""
    fr = [r for r in rows if r[mode]["filled"]]
    mean = lambda xs: stat.mean(xs) if xs else None   # noqa: E731
    k = len(fr) // 2
    rois = [r[mode]["roi"] for r in fr]
    return dict(n=len(fr), logged=len(rows), games=len({r["event"] for r in fr}), won=sum(1 for r in fr if r["won"]),
                priced=sum(r[mode]["cost"] for r in fr), roi=mean(rois), z=z_by_game([(r[mode]["roi"], r["event"]) for r in fr]),
                old=mean(rois[:k]) if len(fr) >= 4 else None, new=mean(rois[k:]) if len(fr) >= 4 else None,
                v2=mean([r[mode]["roi"] for r in fr if r["v2"]]), v2_n=sum(1 for r in fr if r["v2"]))


def read_of(n, games, lane):
    if n < REVIEW_N:
        return f"too early ({n} of {REVIEW_N} settled entries)"
    if n < DECIDE_N:
        return f"review ({n} of {DECIDE_N} to decide)"
    if lane == "nhl_pl_no_goal" and games < HEADLINE_GAMES:
        return f"decide; headline read at {HEADLINE_GAMES} games ({games} so far)"
    return "decide"


def main(argv=None):
    state = run(load())
    save(state)
    parts = [f"{c['lane']} {summary(rows_for(state, c['lane']))['n']}" for c in LANES]
    print(f"nhl_goal_lanes: {len(state['games'])} games, {len(state['skips'])} skipped; " + ", ".join(parts)
          + f"; error {state['error']}")
    return 1 if state["error"] else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
