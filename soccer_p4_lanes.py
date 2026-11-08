"""soccer_p4_lanes: the three phase-4 WATCH cells of the soccer price study as Sandbox PAPER lanes (2026-11-08, Olu: "put
the 3 phase-4 WATCH cells in the Sandbox as paper lanes").

WHERE THEY COME FROM. ~/edge-research/soccer_shapes_2026-11-07/ (README "Phase 4", pre-registered 2026-11-08T17:48Z with
the mid-band amendment at 17:53Z). The study used team labels as a MATCH FILTER on the Kalshi soccer prices. No label
family beat a shuffled-label null (the real labels beat 16, 16, 11 and 9 of 20 shuffles against a bar of 19), so there is
no edge claim here. Three cells were positive in discovery, in both halves and on an August holdout. They are kept as
WATCH cells, and these lanes are their forward test, frozen exactly as the study measured them.

THE RULES, pre-registered here (2026-11-08T21:30Z) before any match they read had started:

  LEAGUES   the study's nine: Premier League, La Liga, Serie A, Bundesliga, Ligue 1, Champions League, MLS, Eredivisie,
            Primeira Liga (Kalshi KX<league>GAME / TOTAL / SPREAD / 1HSCORE or 1HSPREAD).
  LABELS    soccer_rules.labels, POINT IN TIME: each team's last 10 competitive matches against its league's mean goals per
            team over the last 400 team-games, from ESPN fixtures that kicked off strictly before this match (its own
            fixture never counts). O+/O- scores at least / less than the mean, D+/D- concedes at least / less. Fewer than 6
            prior matches, or 40 league team-games, means no label and no lane entry. The labels are frozen on the row.
  PRE       an hour before ESPN's kickoff (T-1h), the last 1-minute candle at or before it, spread 5c or less.
  HALF-TIME the close of the match's 1st-half correct-score market (else its 1st-half spread market) when it closes 44-75
            minutes after kickoff. No such close: no in-play moment for that match.
  GOALS     ESPN's goals, each placed by its match clock and then timed by the market's own price: the first minute in
            [clock estimate - 8 min, + 22 min] where the scorer's summed spread mids jump 4c+ above their running
            3-minute high. An untimed goal keeps its clock estimate (STATE "none"). "v2" is recorded on every row and
            shown in the fold: every goal by entry + 5 min has its own distinct price-timed minute.
  MINUTE 75 second half start = half-time + 15 min; minute 75 = that + 30 min, only when the score then equals the
            half-time score. The quote: the last candle at or before it, no older than 3 minutes, spread 5c or less, the
            market not within a minute of its close.
  FILL      taker at the ask, real only when 50+ contracts print at or through it on our side within 5 minutes of the
            entry (a NO print = 1 - the YES price). Kalshi's taker fee, rounded up to the cent on a $1 stake. Held to
            settlement. A row with no such depth is logged as "no fill" and is not in the record.
  MAKER     (fold only) a resting bid at the side's bid, filled by a print strictly through it within 15 minutes, maker
            fee, held. Never the headline.

  p4_mid_no       "Mid NO Mismatch": KX<league>GAME at T-1h, NO at 36-64c on the O+D+ team's win market when its
                  opponent is O-D+.
     research     discovery +40.5% on 47 matches (z +3.24), halves +69% / +22%; Aug holdout +29.2% on 11, halves +18% / +35%.
  p4_late_over    "Late Over Calm": KX<league>TOTAL at minute 75 with the score unchanged since half-time, YES at 46-55c on
                  any over rung still needing a goal, neither team D+.
     research     discovery +44.3% on 29 matches, halves +53% / +35%; Aug holdout +13.5% on 20, halves +20% / +9%.
  p4_late_under   "Late Under Leaky": KX<league>TOTAL at minute 75 (same moment), NO at 81-90c on any over rung still needing
                  a goal, both teams D+.
     research     discovery +15.1% on 35 matches, halves +15% / +15%; Aug holdout +14.4% on 7 (thin).
  Each has a BASELINE (<id>_all): the same moment, market, side and band with no label filter. The lane must beat it.

RECORD: fresh from REGISTERED: only matches ESPN starts at or after it count; nothing is replayed. One row per entry, z
clustered by match, ROI per entry after fees. Review at 10 settled entries, decide at 30.

Read after the fact: every settled KX<league>GAME event is read once, from the 1-minute candles of its moneyline, totals
and spread markets and the trade prints of the in-band contracts. Own ledger data/soccer_p4_lanes_ledger.json, read
hourly by .github/workflows/soccer-p4.yml on the VPS's stamp. Paper only: no order is placed.
"""
import datetime as dt
import json
import math
import os
import re
import statistics as stat
import sys
import unicodedata

import chaos_lanes as CL
import chaos_replay as C
import daily_track as D
import nhl_goal_lanes as NG

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "data", "soccer_p4_lanes_ledger.json")
VERSION = "soccerp4-v1"
REGISTERED = "2026-11-09T00:00:00Z"
SINCE = "2026-11-08"
EPS = 1e-9
UTC = dt.timezone.utc

# Kalshi league code -> (ESPN slug, ESPN league name in the fixtures soccer_rules labels from)
LEAGUES = {
    "EPL": ("eng.1", "Premier League"), "LALIGA": ("esp.1", "La Liga"), "SERIEA": ("ita.1", "Serie A"),
    "BUNDESLIGA": ("ger.1", "Bundesliga"), "LIGUE1": ("fra.1", "Ligue 1"), "UCL": ("uefa.champions", "Champions League"),
    "MLS": ("usa.1", "MLS"), "EREDIVISIE": ("ned.1", "Eredivisie"), "LIGAPORTUGAL": ("por.1", "Primeira Liga"),
}

# --- the study's frozen numbers
PRE_S = 3600
HT_LO_S, HT_HI_S = 44 * 60, 75 * 60
HT_EST_S = 48 * 60
BREAK_S = 15 * 60
M75_AFTER_S2 = 30 * 60
GOAL_BACK_S, GOAL_SPAN_S, GOAL_JUMP = 8 * 60, 30 * 60, 0.04
MAX_SPREAD = 0.05
STALE_S = 180
DEPTH_S, DEPTH_MIN = 300, 50.0
MAKER_S = 900
TAKER_K, MAKER_K = 0.07, 0.0175
SKIP_AFTER_D = 3
MAX_MATCHES_PER_RUN = 40
REVIEW_N, DECIDE_N = 10, 30


def _no_od_plus(h, a):
    return bool(h and a) and h[2:] != "D+" and a[2:] != "D+"


def _both_d_plus(h, a):
    return bool(h and a) and h[2:] == "D+" and a[2:] == "D+"


LANES = (
    dict(lane="p4_mid_no", name="Mid NO Mismatch", kind="GAME", mom="pre", side="no", band=(0.36, 0.64), baseline=False,
         test="own_opp", label="Mid NO Mismatch", market="Match winner · NO",
         words="An hour before kickoff, NO at 36-64c on the win market of an O+D+ team playing an O−D+ team.",
         research="Discovery +40.5% on 47 matches (z +3.24), halves +69% / +22%; August holdout +29.2% on 11, halves "
                  "+18% / +35%."),
    dict(lane="p4_mid_no_all", name="Baseline · Mid NO, every match", kind="GAME", mom="pre", side="no", band=(0.36, 0.64),
         baseline=True, test=None, label="Baseline · match winner NO 36-64c an hour before, every match",
         market="Match winner · NO", words="The same moment and band on every team's win market, no label filter.",
         research="The population the lane is cut from. The lane must beat it."),
    dict(lane="p4_late_over", name="Late Over Calm", kind="TOTAL", mom="m75", side="yes", band=(0.46, 0.55), baseline=False,
         test="no_d_plus", label="Late Over Calm", market="Total goals · YES",
         words="Minute 75 with the score unchanged since half-time, YES at 46-55c on any over rung still needing a goal, "
               "neither team D+.",
         research="Discovery +44.3% on 29 matches, halves +53% / +35%; August holdout +13.5% on 20, halves +20% / +9%."),
    dict(lane="p4_late_over_all", name="Baseline · Late over, every match", kind="TOTAL", mom="m75", side="yes",
         band=(0.46, 0.55), baseline=True, test=None, label="Baseline · over YES 46-55c at minute 75, every match",
         market="Total goals · YES", words="The same moment and band, no label filter.",
         research="The population the lane is cut from. The lane must beat it."),
    dict(lane="p4_late_under", name="Late Under Leaky", kind="TOTAL", mom="m75", side="no", band=(0.81, 0.90), baseline=False,
         test="both_d_plus", label="Late Under Leaky", market="Total goals · NO",
         words="Minute 75 with the score unchanged since half-time, NO at 81-90c on any over rung still needing a goal, "
               "both teams D+.",
         research="Discovery +15.1% on 35 matches, halves +15% / +15%; August holdout +14.4% on 7 (thin)."),
    dict(lane="p4_late_under_all", name="Baseline · Late under, every match", kind="TOTAL", mom="m75", side="no",
         band=(0.81, 0.90), baseline=True, test=None, label="Baseline · under NO 81-90c at minute 75, every match",
         market="Total goals · NO", words="The same moment and band, no label filter.",
         research="The population the lane is cut from. The lane must beat it."),
)
BY_LANE = {c["lane"]: c for c in LANES}
HEADLINES = tuple(c["lane"] for c in LANES if not c["baseline"])
BASELINE = {"p4_mid_no": "p4_mid_no_all", "p4_late_over": "p4_late_over_all", "p4_late_under": "p4_late_under_all"}
SHUFFLE_NOTE = ("The study's label families failed a shuffled-label null (the real labels beat 16, 16, 11 and 9 of 20 "
                "random relabellings against a bar of 19), so these cells are WATCH forward tests, not edge claims.")


# ------------------------------------------------------------------ the study's name matching (screen.py, unchanged)
STOP = {"fc", "cf", "afc", "sc", "ac", "as", "ssc", "us", "club", "de", "cd", "rc", "rcd", "ud", "sd", "ca", "vfb", "vfl",
        "fsv", "tsg", "bv", "sv", "1", "fk", "sk", "ogc", "stade", "olympique", "the", "and", "calcio", "hotspur", "city",
        "united", "real"}
ALIAS = {"bilbao": "athletic club", "koln": "cologne", "fc koln": "cologne", "celta vigo": "celta",
         "stade brest 29": "brest", "los angeles f": "lafc", "los angeles g": "la galaxy", "enschede": "twente",
         "madeira": "maritimo", "vicente barcelos": "gil vicente", "new york rb": "new york red bulls",
         "saint louis": "st louis", "dc united": "d c united"}


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.findall(r"[a-z0-9]+", s)


def sim(a, b):
    a = ALIAS.get(" ".join(norm(a)), a)
    b = ALIAS.get(" ".join(norm(b)), b)
    A, B = set(norm(a)), set(norm(b))
    if not A or not B:
        return 0
    s = len((A - STOP) & (B - STOP)) * 2 + len(A & B) * 0.5
    na, nb = "".join(norm(a)), "".join(norm(b))
    if na[:5] == nb[:5]:
        s += 1
    if na in nb or nb in na:
        s += 2
    return s


def team_of(name, kal_home, kal_away):
    n = re.split(r" wins| over \d", name or "")[0]
    sh, sa = sim(n, kal_home), sim(n, kal_away)
    return "home" if sh > sa else "away" if sa > sh else None


def match_espn(games, day, names):
    """(ESPN game, (Kalshi name of ESPN home, of ESPN away)) for the Kalshi team names, or (None, None). `games`:
    [{date, teams: {home: {name, short}, away: {...}}}] near the event's date code (noon UTC of `day`)."""
    if len(names) != 2:
        return None, None
    h, a = names
    d0 = dt.datetime(day.year, day.month, day.day, 12, tzinfo=UTC).timestamp()
    best = (0, None, None)

    def m(x, t):
        return max(sim(x, t["name"]), sim(x, t.get("short") or ""))
    for g in games:
        if abs(C._ts(g["date"]) - d0) > 1.6 * 86400:
            continue
        th, ta = g["teams"]["home"], g["teams"]["away"]
        s1, s2 = min(m(h, th), m(a, ta)), min(m(h, ta), m(a, th))
        f1 = s1 + 0.01 * (m(h, th) + m(a, ta))
        f2 = s2 + 0.01 * (m(h, ta) + m(a, th))
        if f1 > best[0]:
            best = (f1, g, (h, a))
        if f2 > best[0]:
            best = (f2, g, (a, h))
    return (best[1], best[2]) if best[0] >= 0.03 else (None, None)


# ------------------------------------------------------------------ the study's moments
def fee(p, rate):
    """Kalshi's fee per contract on a $1 stake, rounded up to the cent (the study's p4 fee)."""
    c = max(1, math.floor(1 / max(p, 0.01)))
    return math.ceil(round(rate * c * p * (1 - p) * 100, 6)) / 100 / c


def series_at(rows, ts):
    return NG.series_at(rows, ts)


def half_time(ko, closes):
    """The 1st-half market's close if it reads as the whistle (44-75 min after kickoff), else None. `closes`: the
    1HSCORE close first, then the 1HSPREAD one (each the latest close among its markets, or None)."""
    for c in closes:
        if c and ko + HT_LO_S <= c <= ko + HT_HI_S:
            return c
    return None


def goal_estimates(espn_goals, ko, ht):
    """[(clock estimate ts, side, period)]: period 1 from kickoff, period 2 from the 2nd-half start."""
    s2 = (ht or ko + HT_EST_S) + BREAK_S
    out = []
    for per, sec, side in espn_goals:
        if side not in ("home", "away") or sec is None or per not in (1, 2):
            continue
        out.append((ko + sec if per == 1 else s2 + (sec - 2700), side, per))
    return sorted(out)


def time_goals(est, side_sum):
    """[tj or None] per estimate: the first max jump of the scorer's summed spread mids over its running 3-minute high,
    in [est - 8 min, est + 22 min], when it is 4c or more. `side_sum(side, ts)` -> the summed mids."""
    out = []
    for t, s, _p in est:
        lo = int(t - GOAL_BACK_S)
        lo -= lo % 60
        vals = [(x, side_sum(s, x)) for x in range(lo, lo + GOAL_SPAN_S, 60)]
        jumps = [(vals[i + 1][1] - max(v for _, v in vals[max(0, i - 2):i + 1]), vals[i + 1][0]) for i in range(len(vals) - 1)]
        j, tj = max(jumps) if jumps else (0, None)
        out.append(tj if j >= GOAL_JUMP - EPS else None)
    return out


def m75_moment(ko, ht, goals):
    """The minute-75 entry ts when the half-time is known and the score then equals the half-time score, else None.
    `goals`: [(ts, side, period)] with the price-timed ts where there is one."""
    if ht is None:
        return None
    ts = ht + BREAK_S + M75_AFTER_S2
    return ts if score(goals, ts) == score(goals, ht) else None


def score(goals, ts):
    return (sum(1 for t, s, _ in goals if t <= ts and s == "home"), sum(1 for t, s, _ in goals if t <= ts and s == "away"))


def valid_v2(est, tjs, ts, have_spread):
    """Every goal whose clock estimate is by ts + 5 min, or whose timed minute is by ts, has its own distinct timed minute."""
    if not est:
        return True
    if not have_spread:
        return False
    near = [tj for (t, _s, _p), tj in zip(est, tjs) if t <= ts + 300 or (tj and tj <= ts)]
    return all(near) and len(set(near)) == len(near)


def quote(rows, ts, close, in_play):
    """(yes bid, yes ask) usable at ts under the study's rules, else None."""
    if close and ts >= close - 60:
        return None
    yb, ya, last = series_at(rows, ts)
    if last is None or yb is None or ya is None or ya - yb > MAX_SPREAD + EPS:
        return None
    if in_play and ts - last > STALE_S:
        return None
    return yb, ya


def wants(cfg, labs, side=None):
    """Does a row with these labels pass the lane's label filter? `side`: the market's team (GAME rows)."""
    t = cfg["test"]
    if t is None:
        return True
    h, a = labs.get("home"), labs.get("away")
    if t == "own_opp":
        own, opp = (h, a) if side == "home" else (a, h) if side == "away" else (None, None)
        return own == "O+D+" and opp == "O-D+"
    if t == "no_d_plus":
        return _no_od_plus(h, a)
    if t == "both_d_plus":
        return _both_d_plus(h, a)
    raise ValueError(t)


def in_band(ask, band):
    return band[0] - EPS <= ask <= band[1] + EPS


def candidates(ko, ht, goals, v2_at, game_mk, total_mk, rows_of, kh, ka):
    """Every row any lane or baseline could take, label-blind (the labels filter at read time). game_mk / total_mk:
    [{ticker, name, strike, close}]; rows_of(ticker) -> compact candles."""
    out = []
    pre = ko - PRE_S
    for m in game_mk:
        if (m["name"] or "").lower() == "tie":
            continue
        side = team_of(m["name"], kh, ka)
        q = quote(rows_of(m["ticker"]), pre, m.get("close"), False) if side else None
        if q is None:
            continue
        ask, bid = round(1 - q[0], 4), round(1 - q[1], 4)
        if in_band(ask, BY_LANE["p4_mid_no"]["band"]):
            out.append(dict(kind="GAME", mom="pre", ts=pre, ticker=m["ticker"], name=m["name"], team=side, side="no",
                            ask=ask, bid=bid, v2=True, score="0-0"))
    t75 = m75_moment(ko, ht, goals)
    if t75 is not None:
        h, a = score(goals, t75)
        for m in total_mk:
            if m.get("strike") is None or math.floor(m["strike"]) + 1 - (h + a) <= 0:
                continue
            q = quote(rows_of(m["ticker"]), t75, m.get("close"), True)
            if q is None:
                continue
            base = dict(kind="TOTAL", mom="m75", ts=t75, ticker=m["ticker"], name=m["name"], strike=m["strike"], team=None,
                        v2=v2_at(t75), score=f"{h}-{a}")
            if in_band(q[1], BY_LANE["p4_late_over"]["band"]):
                out.append(dict(base, side="yes", ask=round(q[1], 4), bid=round(q[0], 4)))
            no_ask = round(1 - q[0], 4)
            if in_band(no_ask, BY_LANE["p4_late_under"]["band"]):
                out.append(dict(base, side="no", ask=no_ask, bid=round(1 - q[1], 4)))
    return out


def fills(e, prints, won):
    """Taker (50+ contracts at or through the ask within 5 min) and maker (a print through the bid within 15 min), held,
    after the study's rounded fees."""
    ts, ask, bid = e["ts"], e["ask"], e["bid"]
    pay = 1.0 if won else 0.0
    depth = sum(n for t, y, n in prints if ts < t <= ts + DEPTH_S and NG.side_px(e["side"], y) <= ask + EPS)
    c = ask + fee(ask, TAKER_K)
    taker = dict(filled=depth >= DEPTH_MIN - EPS, depth=round(depth, 2), cost=round(c, 5), roi=round((pay - c) / c, 4))
    hit = next((t for t, y, n in prints if ts < t <= ts + MAKER_S and NG.side_px(e["side"], y) < bid - EPS), None)
    ok = hit is not None and bid >= 0.01
    cm = bid + fee(bid, MAKER_K) if bid >= 0.01 else None
    maker = dict(filled=ok, cost=round(cm, 5) if cm else None, roi=round((pay - cm) / cm, 4) if ok else None)
    return taker, maker


# ------------------------------------------------------------------ fetching
def espn_games(slug, day, board_fn=None):
    """ESPN scoreboard games of one league from the day before to the day after, in the study's shape."""
    board_fn = board_fn or (lambda d: CL._board(f"soccer/{slug}", d))
    out = []
    for k in (-1, 0, 1):
        for ev in board_fn(day + dt.timedelta(days=k)) or []:
            comp = (ev.get("competitions") or [{}])[0]
            side = {c.get("homeAway"): c for c in comp.get("competitors") or []}
            if "home" not in side or "away" not in side or not ev.get("date"):
                continue
            t = {k2: dict(id=str((side[k2].get("team") or {}).get("id")), name=(side[k2].get("team") or {}).get("displayName"),
                          short=(side[k2].get("team") or {}).get("shortDisplayName")) for k2 in ("home", "away")}
            out.append(dict(id=str(ev.get("id")), date=ev["date"], teams=t,
                            done=bool((((comp.get("status") or {}).get("type")) or {}).get("completed"))))
    return out


def espn_goals(slug, game, summary_fn=None):
    """([(period, clock seconds, side)], summary read): ESPN key events that scored, shootout out, periods 1-2."""
    summary_fn = summary_fn or (lambda gid: CL._get_json(f"{CL.ESPN_SITE}/soccer/{slug}/summary?event={gid}"))
    s = summary_fn(game["id"]) or {}
    side = {game["teams"]["home"]["id"]: "home", game["teams"]["away"]["id"]: "away"}
    out = []
    for k in s.get("keyEvents") or []:
        if not k.get("scoringPlay") or k.get("shootout"):
            continue
        out.append(((k.get("period") or {}).get("number"), (k.get("clock") or {}).get("value"),
                    side.get(str((k.get("team") or {}).get("id")))))
    return out, bool(s)


def labels_for(fixtures, league, game):
    """(home label, away label) from fixtures that kicked off strictly before the match (soccer_rules.labels)."""
    import soccer_rules as SR
    f = dict(kickoff=game["date"], league=league, home=game["teams"]["home"]["name"], away=game["teams"]["away"]["name"],
             home_id=game["teams"]["home"]["id"], away_id=game["teams"]["away"]["id"])
    return SR.labels(fixtures, f)


def _mk(ms):
    return [dict(ticker=m["ticker"], name=m.get("yes_sub_title") or "", strike=D.number(m.get("floor_strike")),
                 close=C._ts(m.get("close_time")), result=C.settled_result(m)) for m in ms]


def _close(ms):
    cs = [C._ts(m.get("close_time")) for m in ms if m.get("close_time")]
    cs = [c for c in cs if c]
    return max(cs) if cs else None


def replay(event, lg, fetch, now, fixtures_fn, board_fn=None, summary_fn=None):
    """(match record, None) for a settled match, (None, reason) to skip it for good, (None, None) to retry later."""
    slug, league = LEAGUES[lg]
    gms, garch = C.event_markets(event, fetch)
    if not gms or any(C.settled_result(m) is None for m in gms):
        return None, None
    day = C.event_date(event)
    stale = day is not None and (now.date() - day).days > SKIP_AFTER_D
    names = [m.get("yes_sub_title") for m in gms if (m.get("yes_sub_title") or "").lower() != "tie"]
    g, kt = match_espn(espn_games(slug, day, board_fn), day, names) if day else (None, None)
    if g is None or not g["done"]:
        return (None, "no completed ESPN match for the Kalshi names") if stale or (g is None and day is None) else (None, None)
    ko = C._ts(g["date"])
    if ko is None:
        return None, "no ESPN kickoff"
    if ko < C._ts(REGISTERED):
        return None, "kicked off before the lanes were registered (in-sample, not replayed)"
    plays, have = espn_goals(slug, g, summary_fn)
    if not have:
        return (None, "no ESPN summary") if stale else (None, None)
    kh, ka = kt
    suf = event.split("-", 1)[1]
    mk, arch = {}, {}
    for kind in ("TOTAL", "SPREAD", "1HSCORE", "1HSPREAD"):
        ms, a = C.event_markets(f"KX{lg}{kind}-{suf}", fetch)
        mk[kind], arch[kind] = ms, a
    ht = half_time(ko, (_close(mk["1HSCORE"]), _close(mk["1HSPREAD"])))
    close = max([c for c in (_close(gms), _close(mk["TOTAL"])) if c] or [ko + 3 * 3600])
    lo, hi = ko - PRE_S - 1800, close - close % 60 + 60
    rows = {t: NG.compact(c) for t, c in C.fetch_candles(f"KX{lg}GAME", event, gms, lo, hi, fetch, garch).items()}
    est = goal_estimates(plays, ko, ht)
    sp = _mk(mk["SPREAD"])
    have_spread = bool(sp)
    if ht is not None and mk["TOTAL"]:
        rows.update({t: NG.compact(c) for t, c in
                     C.fetch_candles(f"KX{lg}TOTAL", f"KX{lg}TOTAL-{suf}", mk["TOTAL"], lo, hi, fetch, arch["TOTAL"]).items()})
    tjs = [None] * len(est)
    if have_spread and est:
        spc = {t: NG.compact(c) for t, c in
               C.fetch_candles(f"KX{lg}SPREAD", f"KX{lg}SPREAD-{suf}", mk["SPREAD"], lo, hi, fetch, arch["SPREAD"]).items()}

        def side_sum(side, ts):
            tot = 0.0
            for m in sp:
                if team_of(m["name"], kh, ka) != side:
                    continue
                b, a, _ = series_at(spc.get(m["ticker"]) or [], ts)
                if a is not None:
                    tot += ((b or 0) + a) / 2
            return tot
        tjs = time_goals(est, side_sum)
    goals = sorted((tj or t, s, p) for (t, s, p), tj in zip(est, tjs))
    tm = _mk(mk["TOTAL"])
    cands = candidates(ko, ht, goals, lambda ts: valid_v2(est, tjs, ts, have_spread), _mk(gms), tm,
                       lambda t: rows.get(t) or [], kh, ka)
    res = {m["ticker"]: m["result"] for m in _mk(gms) + tm}
    if any(res.get(c["ticker"]) is None for c in cands):
        return None, None
    fx = fixtures_fn() if cands else None
    h_lab, a_lab = labels_for(fx, league, g) if fx is not None else (None, None)
    entries = []
    for c in cands:
        won = res[c["ticker"]] == c["side"]
        taker, maker = fills(c, NG.fetch_prints(c["ticker"], c["ts"], c["ts"] + MAKER_S, fetch), won)
        entries.append(dict(c, won=won, taker=taker, maker=maker))
    home, away = g["teams"]["home"]["name"], g["teams"]["away"]["name"]
    return dict(event=event, league=lg, title=f"{home} v {away}", ko=ko, day=day.isoformat() if day else None,
                espn_id=g["id"], labels=dict(home=h_lab, away=a_lab), ht=ht, goals=len(est), timed=sum(1 for x in tjs if x),
                entries=entries, logged=now.isoformat(), version=VERSION), None


# ------------------------------------------------------------------ the ledger
def empty():
    return dict(version=VERSION, registered=REGISTERED, since=SINCE, matches=[], skips={}, last_run=None, error=None)


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
    NG.save(state, path)


def _fixtures():
    import streaks_fetch
    return streaks_fetch.load_or_fetch()["fixtures"]


def run(state, now=None, fetch=D.get, fixtures_fn=None, board_fn=None, summary_fn=None):
    """Read every settled match of the nine leagues since the record began, once."""
    now = now or dt.datetime.now(UTC)
    lo = dt.date.fromisoformat(state["since"])
    seen = {g["event"] for g in state["matches"]} | set(state["skips"])
    cache = {}

    def fx():
        if "fx" not in cache:
            cache["fx"] = (fixtures_fn or _fixtures)()
        return cache["fx"]
    errors, done = [], 0
    for lg in LEAGUES:
        try:
            events = C.list_events(f"KX{lg}GAME", lo, fetch, until=now.date(), cap=300)
        except Exception as exc:                                # noqa: BLE001
            errors.append(f"{lg} listing: {str(exc)[:80]}")
            continue
        for event in sorted(events):
            day = C.event_date(event)
            if event in seen or day is None or day < lo:
                continue
            if done >= MAX_MATCHES_PER_RUN:
                break
            try:
                rec, why = replay(event, lg, fetch, now, fx, board_fn, summary_fn)
            except Exception as exc:                            # noqa: BLE001
                errors.append(f"{event}: {str(exc)[:80]}")
                continue
            if rec is None and why is None:
                continue
            if why:
                state["skips"][event] = why
            else:
                state["matches"].append(rec)
            done += 1
    state["matches"].sort(key=lambda g: (g["ko"], g["event"]))
    state["last_run"] = now.isoformat()
    state["error"] = "; ".join(errors)[:600] or None
    return state


# ------------------------------------------------------------------ the record
def rows_for(state, lane):
    """Every logged row of one lane (filled or not), oldest first, each with its match's fields."""
    cfg = BY_LANE[lane]
    out = []
    for g in state.get("matches") or []:
        labs = g.get("labels") or {}
        for e in g.get("entries") or []:
            if (e["kind"], e["mom"], e["side"]) != (cfg["kind"], cfg["mom"], cfg["side"]) or not in_band(e["ask"], cfg["band"]):
                continue
            if not wants(cfg, labs, e.get("team")):
                continue
            out.append(dict(e, event=g["event"], title=g["title"], ko=g["ko"], day=g["day"], league=g["league"],
                            labels=labs))
    return sorted(out, key=lambda r: (r["ts"], r["ticker"]))


def summary(rows, mode="taker"):
    """The record of the rows that filled under `mode`, z clustered by match (NHL's summary, the same shape)."""
    return NG.summary(rows, mode)


def read_of(n):
    if n < REVIEW_N:
        return f"too early ({n} of {REVIEW_N} settled entries)"
    if n < DECIDE_N:
        return f"review ({n} of {DECIDE_N} to decide)"
    return "decide"


def main(argv=None):
    state = run(load())
    save(state)
    parts = [f"{c['lane']} {summary(rows_for(state, c['lane']))['n']}" for c in LANES]
    print(f"soccer_p4_lanes: {len(state['matches'])} matches, {len(state['skips'])} skipped; " + ", ".join(parts)
          + f"; error {state['error']}")
    return 1 if state["error"] else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
