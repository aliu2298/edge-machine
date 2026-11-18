#!/usr/bin/env python3
"""NBA pre-game spotter: Sandbox PAPER lane (Olu via the coordinator, 2026-11-18, "come up with a way to track this in sandbox").
Pre-registration: docs/prereg_nba_spotter_2026-11-18.md. Model: Fable's, FROZEN (data/spotter/model.json, fitted Oct 20 to Nov 6 2026), NO refit.

Two boards a night on Kalshi's player props (points KXNBAPTS, threes KXNBA3PT, rebounds KXNBAREB, assists KXNBAAST, points+rebounds+assists KXNBAPRA):
  spotter_hold   up to 8 rungs where the model's chance is 5+ points above the ask; one a player-stat; held to settlement.
  spotter_spike  up to 8 rungs at 49c or less, ranked by the spike model; a paper resting sell at 2x; held if it never sells.
Each board has a BLIND CONTROL row: a randomly drawn rung from the same game's priced rungs, at about the same price, with the same exit.
INPUTS AT ENTRY TIME ONLY: the ask (spread 5c or less, rungs 5-60c) at the read 80-35 minutes before tip, the ESPN injury report (Out list),
box scores to date, last season's box scores, the ESPN spread. Each pick keeps its reason (the model's largest signed term).
FILLS: bought at the ask (taker fee); the sell fills only on a LATER trade print strictly above the target, 25 seconds after the entry at the
earliest; the fee is charged on both legs. Unsold: held to settlement. Nothing is placed anywhere.
Reading: once, at 200 graded picks per board; keep only if above zero after fees, t 2+ by night, and 2+ points a contract over blind.
"""
import collections
import datetime as dt
import hashlib
import json
import math
import os
import random
import re
import statistics
import sys
import unicodedata
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

import daily_track as D
import fillsim as F
import settle_only

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data", "spotter")
PATH = os.path.join(ROOT, "data", "nba_spotter_ledger.json")
VERSION = "nba-spotter-v1"
REGISTERED = "2026-11-18"
ET = ZoneInfo("America/New_York")
BOARDS = ("spotter_hold", "spotter_spike")
BLIND = {"spotter_hold": "spotter_hold_blind", "spotter_spike": "spotter_spike_blind"}
NAMES = {"spotter_hold": "NBA Spotter, hold", "spotter_spike": "NBA Spotter, spike (sell at 2x)",
         "spotter_hold_blind": "Blind control, hold", "spotter_spike_blind": "Blind control, spike (sell at 2x)"}
SERIES = {"KXNBAPTS": "pts", "KXNBA3PT": "m3", "KXNBAREB": "reb", "KXNBAAST": "ast", "KXNBAPRA": "pra"}
UNIT = {"pts": "points", "m3": "threes", "reb": "rebounds", "ast": "assists", "pra": "points+rebounds+assists"}
STATS = ("pts", "m3", "reb", "ast", "pra")
K2E = {"NYK": "NY", "SAS": "SA", "GSW": "GS", "NOP": "NO", "UTA": "UTAH", "WAS": "WSH"}
NIGHT_CAP, GAME_CAP = 8, 4                 # per board a night; GAME_CAP stops the first game of a night taking every slot
EDGE_MIN = 0.05                            # hold: model chance minus ask
SPIKE_MAX_ASK = 0.49
MAX_SPREAD, PRICE = 0.05, (0.05, 0.60)
WINDOW_MIN = (35, 80)                      # minutes before tip: the VPS asks at about K-75 (the NBA tip stamps, lane_windows.nba_value_windows)
LATENCY_S = 25                             # the sell is not up before this long after the entry
BLIND_BAND = 0.03
READ_AT = 200
EPS = 1e-9
ESPN_SB = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates=%s"
ESPN_SUM = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event=%s"
ESPN_INJ = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries"
MAX_BOX_PER_RUN = 40
SEASON_START = "2026-10-20"

NICE = {"d_blend": ("his projection is above the price", "his projection is below the price"),
        "d_season": ("his season average is above the price", "his season average is below the price"),
        "cold": ("a cold run the price has followed down", "a hot run the price has followed up"),
        "min_up": ("minutes up on last season", "minutes down on last season"),
        "fga_up": ("shots up on last season", "fewer shots than last season"),
        "out_share": ("teammates out", "team at full strength"),
        "top2_out": ("a top scorer on his team is out", "top scorers all playing"),
        "allow": ("opponent gives up a lot of this", "opponent gives up little of this"),
        "pace": ("fast game expected", "slow game expected"), "b2b": ("back-to-back", "rested"), "home": ("home", "away"),
        "fav": ("his team is favoured", "his team is the underdog"), "blowout": ("blowout risk", "close game expected"),
        "started_last": ("started his last game", "came off the bench last game"),
        "no_last": ("no last season to anchor the price", "has a last season to anchor on"),
        "cv": ("a volatile player in this stat", "a steady player in this stat"), "three_share": ("shoots a lot of threes", "shoots few threes"),
        "pf36": ("foul trouble", "rarely in foul trouble"), "mins": ("heavy minutes", "light minutes")}


def fee(p):
    return F.fee(p)


def cost(p):
    return p + fee(p)


# ---------------------------------------------------------------- the frozen model and its data
def _json(name, default=None):
    try:
        with open(os.path.join(DATA, name)) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[.'`]", "", s)
    s = re.sub(r"[^a-z ]", " ", s)
    return " ".join(w for w in s.split() if w not in ("jr", "sr", "ii", "iii", "iv", "v"))


mean = lambda v: sum(v) / len(v) if v else float("nan")   # noqa: E731
logit = lambda p: math.log(max(1e-4, min(1 - 1e-4, p)) / (1 - max(1e-4, min(1 - 1e-4, p))))   # noqa: E731
FLOOR = dict(pts=8, reb=3, ast=2, m3=1)


class World:
    """Everything known before tip: this season's box scores to date, last season's, the frozen model's constants."""

    def __init__(self, model=None, last=None, games=None):
        self.M = model or _json("model.json")
        self.LASTD = last if last is not None else _json("last.json", {})
        self.games = games if games is not None else (_json("games.json", {}) or {}).get("games", [])
        self.index()

    def index(self):
        self.P = collections.defaultdict(list)
        self.NAME = collections.defaultdict(set)
        self.TG = collections.defaultdict(list)
        self.team_of = {}
        for g in sorted(self.games, key=lambda g: g["t"]):
            played = {p[0] for p in g["players"]}
            for p in g["players"]:
                pid, name, team, starter, mn, pts, reb, ast, m3, a3, fga, pf = p
                self.P[pid].append(dict(t=g["t"], gid=g["id"], team=team, min=mn, pts=pts, reb=reb, ast=ast, m3=m3, a3=a3, fga=fga, pf=pf,
                                        pra=pts + reb + ast, starter=bool(starter), name=name))
                self.NAME[norm(name)].add(pid)
            for team, opp in ((g["home"], g["away"]), (g["away"], g["home"])):
                mine, theirs = g["teams"].get(team) or {}, g["teams"].get(opp) or {}
                self.TG[team].append(dict(t=g["t"], poss=(mine.get("poss", 0) + theirs.get("poss", 0)) / 2,
                                          allowed={s: theirs.get(s, 0) for s in STATS}, played=played))
        self.LG = sorted((x for v in self.TG.values() for x in v), key=lambda x: x["t"])
        self.LAST = {}
        for pid, e in self.LASTD.items():
            if e.get("last"):
                self.LAST[pid] = e["last"]

    # ---- the research's estimate (sp_data.py), unchanged
    def start(self, pid, k):
        L = self.LAST.get(pid)
        if not L:
            return None
        if k == "pra":
            return self.start(pid, "pts") + self.start(pid, "reb") + self.start(pid, "ast")
        a, b, _n = self.M["LINE"][k]
        return a + b * L[k] if L[k] >= FLOOR[k] else L[k]

    @staticmethod
    def zcdf(q, v):
        if v <= q[0]:
            return 0.0
        if v >= q[-1]:
            return 1.0
        lo, hi = 0, len(q) - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if q[mid] <= v:
                lo = mid
            else:
                hi = mid
        return (lo + (v - q[lo]) / max(1e-9, q[hi] - q[lo])) / (len(q) - 1)

    def chance(self, k, L, rung):
        """Chance of `rung`+ in stat k for a player whose level is L."""
        if L is None:
            return None
        M = self.M
        if k == "pts":
            L = max(L, 0.5)
            band = 0 if L < 8 else 1 if L < 16 else 2
            return 1.0 - self.zcdf(M["P2"]["zq"][band], (rung - 0.5 - L) / (M["P2"]["a"] + M["P2"]["b"] * L))
        if k == "pra":
            L = max(L, 1.0)
            return 1.0 - self.zcdf(M["PZ"], (rung - 0.5 - L) / (M["PA"] + M["PB"] * L))
        if L <= 0.02:
            return 0.0
        var = max(M["PHI"][k], 1.0001) * L
        r = L * L / (var - L)
        q = r / (r + L)
        p = q ** r
        c = 0.0
        for i in range(rung):
            c += p
            p *= (r + i) / (i + 1) * (1 - q)
        return max(0.0, 1.0 - c)

    def hist(self, pid):
        sofar = self.P.get(pid, [])
        last40 = [dict(min=x[0], pts=x[1], reb=x[2], ast=x[3], m3=x[4], a3=x[5], fga=x[6], pf=x[7], pra=x[1] + x[2] + x[3])
                  for x in (self.LASTD.get(pid) or {}).get("last40", [])]
        return sofar, last40

    def ctx(self, team, home, opp, tip, spread):
        mine, theirs = self.TG[team], self.TG[opp]
        lp = mean([x["poss"] for x in self.LG]) if self.LG else 0
        pace = ((mean([x["poss"] for x in mine]) + mean([x["poss"] for x in theirs])) / 2 - lp) / lp if lp and len(mine) >= 3 and len(theirs) >= 3 else 0.0
        allow = {}
        for k in STATS:
            la = [x["allowed"][k] for x in self.LG]
            sd = statistics.pstdev(la) / math.sqrt(max(1, len(theirs))) if la else 0
            allow[k] = (mean([x["allowed"][k] for x in theirs]) - mean(la)) / sd if sd and len(theirs) >= 5 else 0.0
        wt, ppg = collections.Counter(), {}
        for pid, rs in self.P.items():
            if rs and rs[-1]["team"] == team:
                wt[pid] = sum(x["min"] for x in rs)
                ppg[pid] = mean([x["pts"] for x in rs]) if len(rs) >= 3 else 0
        fav = None if spread is None else (-spread if home else spread)
        return dict(home=home, opp=opp, b2b=bool(mine and tip - mine[-1]["t"] < 30 * 3600), pace=pace, allow=allow, fav_by=fav, wt=wt,
                    tot=sum(wt.values()), top2=sorted(ppg, key=lambda p: -ppg[p])[:2])

    def predict(self, which, x, off):
        Mx = self.M[which]
        z = {k: (x[k] - Mx["mu"][k]) / Mx["sd"][k] for k in Mx["keys"]}
        c = {k: Mx["b"][i + 1] * z[k] for i, k in enumerate(Mx["keys"])}
        why = max((k for k in c if k in NICE), key=lambda k: c[k])
        return 1 / (1 + math.exp(-(off + Mx["b"][0] + sum(c.values())))), NICE[why][0 if z[why] >= 0 else 1]

    def score(self, pid, k, rungs, team, game, out_pids):
        """[dict(p_hold, p_spike?, why_*)] per rung for one player-stat in one game, or (None, reason). `rungs` = [dict(rung, bid, ask)]."""
        sofar, last40 = self.hist(pid)
        n = len(sofar)
        L0, last = self.start(pid, k), self.LAST.get(pid)
        if (L0 is None and n < 3) or not sofar:
            return None, "no projection"
        if team not in (game["home"], game["away"]):
            return None, "team changed"
        home = team == game["home"]
        opp = game["away"] if home else game["home"]
        tip = game["tip"].timestamp() if hasattr(game["tip"], "timestamp") else float(game["tip"])
        cx = self.ctx(team, home, opp, tip, game.get("spread"))
        Ls = mean([x[k] for x in sofar]) if n >= 3 else None
        Lb = (4 * L0 + sum(x[k] for x in sofar)) / (4 + n) if L0 is not None else Ls
        L5 = mean([x[k] for x in sofar[-5:]]) if n >= 5 else None
        mins = mean([x["min"] for x in sofar]) if n >= 3 else (last["min"] if last else None)
        fga = mean([x["fga"] for x in sofar]) if n >= 3 else (last["fga"] if last else None)
        hist = sofar + last40
        mk = mean([x[k] for x in hist])
        a3s, fgas = sum(x["a3"] for x in hist), sum(x["fga"] for x in hist)
        out_w = sum(w for p, w in cx["wt"].items() if p in out_pids and p != pid)
        tot_o = cx["tot"] - cx["wt"].get(pid, 0)
        outs = [self.P[p][-1]["name"] for p in cx["top2"] if p != pid and p in out_pids]
        F_ = dict(min_up=((mins - last["min"]) / 10 if last and n >= 3 else 0.0), fga_up=((fga - last["fga"]) / 5 if last and n >= 3 else 0.0),
                  out_share=(out_w / tot_o if tot_o > 0 else 0.0), top2_out=1.0 if outs else 0.0, allow=cx["allow"][k], pace=cx["pace"] * 10,
                  b2b=1.0 if cx["b2b"] else 0.0, home=1.0 if cx["home"] else 0.0, fav=(cx["fav_by"] or 0.0) / 10,
                  blowout=1.0 if cx["fav_by"] is not None and abs(cx["fav_by"]) >= 10 else 0.0, started_last=1.0 if sofar[-1]["starter"] else 0.0,
                  no_last=0.0 if last else 1.0, cv=(statistics.pstdev([x[k] for x in hist]) / mk if len(hist) >= 5 and mk > 0 else 0.7),
                  three_share=(a3s / fgas if fgas else 0.35), pf36=(36 * sum(x["pf"] for x in hist) / max(1, sum(x["min"] for x in hist))),
                  mins=(mins or 24) / 36)
        out = []
        for r in rungs:
            cb = self.chance(k, Lb, r["rung"])
            cs = self.chance(k, Ls, r["rung"]) if Ls is not None else cb
            c5 = self.chance(k, L5, r["rung"]) if L5 is not None else None
            mid = (r["bid"] + r["ask"]) / 2
            x = dict(F_, d_blend=cb - mid, d_season=cs - mid, cold=(cs - c5) if c5 is not None else 0.0, price=mid,
                     **{"is_" + s: 1.0 if k == s else 0.0 for s in ("m3", "reb", "ast", "pra")})
            ph, why = self.predict("hold", x, logit(mid))
            row = dict(r, p_hold=ph, edge=ph - r["ask"], why_hold=why, outs=outs, games=n, level=Lb)
            if r["ask"] <= SPIKE_MAX_ASK + EPS:
                ps, w2 = self.predict("spike", x, 0.0)
                row.update(p_spike=ps, spike_edge=ps - r["ask"] / round(2 * r["ask"], 2), why_spike=w2)
            out.append(row)
        return out, None


# ---------------------------------------------------------------- state
def empty():
    return {"version": VERSION, "registered": REGISTERED, "rules": {k: {"picks": []} for k in (*BOARDS, *BLIND.values())},
            "looks": {}, "runs": [], "schedule": [], "box_through": None}


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


def night_of(tip):
    return tip.astimezone(ET).date().isoformat()


# ---------------------------------------------------------------- the pulls (ESPN, Kalshi)
def espn_get(url, opener=urllib.request.urlopen):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with opener(req, timeout=40) as r:
        return json.load(r)


def _pair(x):
    try:
        a, b = (int(v) for v in (x or "0-0").split("-"))
        return a, b
    except ValueError:
        return 0, 0


def _int(x):
    return int(x) if str(x).lstrip("-").isdigit() else None


def parse_box(j):
    """ESPN summary -> player rows (the research's box shape)."""
    out = []
    for p in ((j or {}).get("boxscore") or {}).get("players", []):
        team = p["team"]["abbreviation"]
        s = p["statistics"][0]
        labels = s["labels"]
        for a in s["athletes"]:
            if a.get("didNotPlay") or not a.get("stats"):
                continue
            out.append({"team": team, "pid": str(a["athlete"].get("id") or a["athlete"].get("displayName")), "name": a["athlete"].get("displayName"),
                        "starter": a.get("starter"), **dict(zip(labels, a["stats"]))})
    return out


def game_record(gid, date, home, away, box):
    tm = {home: collections.Counter(), away: collections.Counter()}
    pl = []
    for p in box:
        mn = _int(p.get("MIN"))
        if not mn or p["team"] not in tm:
            continue
        _fgm, fga = _pair(p.get("FG"))
        m3, a3 = _pair(p.get("3PT"))
        _ftm, fta = _pair(p.get("FT"))
        pts, reb, ast = _int(p.get("PTS")) or 0, _int(p.get("REB")) or 0, _int(p.get("AST")) or 0
        pl.append([p["pid"], p["name"], p["team"], 1 if p.get("starter") else 0, mn, pts, reb, ast, m3, a3, fga, _int(p.get("PF")) or 0])
        c = tm[p["team"]]
        c["pts"] += pts
        c["reb"] += reb
        c["ast"] += ast
        c["m3"] += m3
        c["pra"] += pts + reb + ast
        c["poss"] += fga + 0.44 * fta + (_int(p.get("TO")) or 0) - (_int(p.get("OREB")) or 0)
    t = dt.datetime.fromisoformat(date.replace("Z", "+00:00")).timestamp()
    return dict(id=str(gid), t=t, day=date[:10], home=home, away=away, teams={k: dict(v) for k, v in tm.items()}, players=pl)


def refresh_box(games_doc, now, get=espn_get, limit=MAX_BOX_PER_RUN):
    """Add every finished regular-season game from the last stored day to yesterday. Returns (new games, errors)."""
    have = {g["id"] for g in games_doc["games"]}
    last_day = max((g["day"] for g in games_doc["games"]), default=SEASON_START)
    first = dt.date.fromisoformat(last_day) - dt.timedelta(days=1)
    today = now.astimezone(ET).date()
    new, errs = 0, []
    d = first
    while d <= today and new < limit:
        try:
            ev = get(ESPN_SB % d.strftime("%Y%m%d")).get("events", [])
        except Exception as e:                                       # noqa: BLE001
            errs.append(f"scoreboard {d}: {str(e)[:60]}")
            d += dt.timedelta(days=1)
            continue
        for e in ev:
            c = e["competitions"][0]
            if e.get("season", {}).get("type") != 2 or c["status"]["type"]["name"] != "STATUS_FINAL" or str(e["id"]) in have:
                continue
            if new >= limit:
                break
            try:
                h = next(t["team"]["abbreviation"] for t in c["competitors"] if t["homeAway"] == "home")
                a = next(t["team"]["abbreviation"] for t in c["competitors"] if t["homeAway"] == "away")
                games_doc["games"].append(game_record(e["id"], e["date"], h, a, parse_box(get(ESPN_SUM % e["id"]))))
                have.add(str(e["id"]))
                new += 1
            except Exception as ex:                                  # noqa: BLE001
                errs.append(f"box {e.get('id')}: {str(ex)[:60]}")
        d += dt.timedelta(days=1)
    games_doc["games"].sort(key=lambda g: g["t"])
    return new, errs


def slate(now, get=espn_get):
    """Games not yet final with tip inside the next day: [dict(id, tip, home, away, spread)]."""
    out = {}
    for d in {now.astimezone(ET).date(), (now + dt.timedelta(hours=20)).astimezone(ET).date(), now.date()}:
        for e in get(ESPN_SB % d.strftime("%Y%m%d")).get("events", []):
            c = e["competitions"][0]
            if e.get("season", {}).get("type") != 2 or c["status"]["type"]["name"] != "STATUS_SCHEDULED":
                continue
            od = (c.get("odds") or [{}])[0]
            tip = dt.datetime.fromisoformat(e["date"].replace("Z", "+00:00"))
            out[str(e["id"])] = dict(id=str(e["id"]), tip=tip, home=next(t["team"]["abbreviation"] for t in c["competitors"] if t["homeAway"] == "home"),
                                     away=next(t["team"]["abbreviation"] for t in c["competitors"] if t["homeAway"] == "away"), spread=od.get("spread"))
    return sorted(out.values(), key=lambda g: (g["tip"], g["id"]))


def injuries(get=espn_get):
    inj = []
    for t in get(ESPN_INJ).get("injuries", []):
        for x in t.get("injuries", []):
            a = x.get("athlete") or {}
            inj.append(dict(name=a.get("displayName"), status=x.get("status")))
    return inj


def kalshi_markets(day_tags, fetch=D.get):
    """{series: [market]} for the five prop series, open, for events dated in day_tags (e.g. '26NOV18')."""
    out = {}
    for s in SERIES:
        v, cur = [], None
        for _ in range(4):
            r = fetch(f"markets?series_ticker={s}&status=open&limit=1000" + (f"&cursor={urllib.parse.quote(cur, safe='')}" if cur else ""))
            v += r.get("markets") or []
            cur = r.get("cursor")
            if not cur or not r.get("markets"):
                break
        out[s] = [m for m in v if m["event_ticker"].split("-")[1][:7] in day_tags]
    return out


def day_tag(d):
    mon = "JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split()[d.month - 1]
    return f"{d.year % 100}{mon}{d.day:02d}"


# ---------------------------------------------------------------- one game's read
def due(games, now, looks):
    if settle_only.on():
        return []
    lo, hi = WINDOW_MIN
    return [g for g in games if g["id"] not in looks and lo <= (g["tip"] - now).total_seconds() / 60 <= hi]


def read_game(W, g, markets, out_pids):
    """Every usable priced rung of one game, scored. Returns (rows, skip counter)."""
    skip = collections.Counter()
    byp = collections.defaultdict(list)
    for ser, ms in markets.items():
        k = SERIES[ser]
        for m in ms:
            suf = m["event_ticker"].split("-")[1][7:]
            away, home = K2E.get(suf[:3], suf[:3]), K2E.get(suf[3:], suf[3:])
            if (away, home) != (g["away"], g["home"]):
                continue
            bid, ask = D.number(m.get("yes_bid_dollars")), D.number(m.get("yes_ask_dollars"))
            if bid is None or ask is None or not 0 < bid <= ask < 1:
                skip["no quote"] += 1
                continue
            if ask - bid > MAX_SPREAD + EPS:
                skip["wide"] += 1
                continue
            if not (PRICE[0] - EPS <= ask <= PRICE[1] + EPS):
                skip["outside 5-60c"] += 1
                continue
            c = W.NAME.get(norm((m.get("title") or "").split(":")[0]), set())
            if len(c) != 1:
                skip["no player match"] += 1
                continue
            try:
                rung = int(m["ticker"].rsplit("-", 1)[1])
            except ValueError:
                skip["odd ticker"] += 1
                continue
            byp[(next(iter(c)), k)].append(dict(rung=rung, bid=bid, ask=ask, tk=m["ticker"], name=(m.get("title") or "").split(":")[0]))
    rows = []
    for (pid, k), rs in byp.items():
        if pid in out_pids:
            skip["listed out"] += len(rs)
            continue
        sofar = W.P.get(pid, [])
        team = sofar[-1]["team"] if sofar else None
        scored, why = W.score(pid, k, rs, team, g, out_pids)
        if scored is None:
            skip[why] += len(rs)
            continue
        for r in scored:
            rows.append(dict(r, pid=pid, stat=k, team=team))
    return rows, skip


def _rank(rows, key, flt, taken, cap):
    """Largest `key` first, one a player-stat across the night, at most `cap` here."""
    out = []
    for r in sorted((r for r in rows if flt(r)), key=lambda r: (-r[key], r["tk"])):
        if len(out) >= cap:
            break
        pk = (r["pid"], r["stat"])
        if pk in taken:
            continue
        taken.add(pk)
        out.append(r)
    return out


def _pick(board, g, night, r, now, p, why, extra=None):
    pid = f"{board}:{r['tk']}"
    row = dict(id=pid, rule=board, night=night, game=f"{g['away']} @ {g['home']}", game_id=g["id"], start=g["tip"].isoformat(), ticker=r["tk"],
               player=r["name"], pid=r["pid"], stat=r["stat"], unit=UNIT[r["stat"]], rung=r["rung"], team=r["team"], bid=r["bid"], price=r["ask"],
               p=None if p is None else round(p, 4), why=why, entered=now.isoformat(), lead_min=round((g["tip"] - now).total_seconds() / 60, 1),
               status="open")
    if board in ("spotter_spike", "spotter_spike_blind"):
        row["target"] = round(2 * r["ask"], 2)
    if r.get("outs"):
        row["outs"] = r["outs"]
    row.update(extra or {})
    return row


def draw_blind(board, rows, pick, excluded):
    """One rung from the same game's priced rungs at about the pick's price, drawn by a seed fixed by the pick, never one of the board's own players."""
    spike = board == "spotter_spike"
    pool = [r for r in rows if (r["pid"], r["stat"]) not in excluded and (not spike or r["ask"] <= SPIKE_MAX_ASK + EPS)]
    if not pool:
        return None
    near = [r for r in pool if abs(r["ask"] - pick["ask"]) <= BLIND_BAND + EPS]
    if not near:
        best = min(abs(r["ask"] - pick["ask"]) for r in pool)
        near = [r for r in pool if abs(r["ask"] - pick["ask"]) <= best + EPS]
    seed = int(hashlib.sha256(f"{board}:{pick['tk']}".encode()).hexdigest()[:12], 16)
    return random.Random(seed).choice(sorted(near, key=lambda r: r["tk"]))


def look(state, W, g, markets, out_pids, now):
    """Enter one game's picks (look_many for a single game)."""
    return look_many(state, W, [g], markets, out_pids, now)


def look_many(state, W, games, markets, out_pids, now):
    """Enter the picks of every game read in this run. The games read TOGETHER are ranked together (largest edge first, one a player-stat a
    night, 4 a game, 8 a night per board), so a catch-up run is not decided by tip order. Returns the new pick ids."""
    read = {}
    for g in games:
        rows, skip = read_game(W, g, markets, out_pids)
        read[g["id"]] = (g, rows, skip)
    spec = {"spotter_hold": ("edge", lambda r: r["edge"] >= EDGE_MIN - EPS, "p_hold", "why_hold"),
            "spotter_spike": ("spike_edge", lambda r: "p_spike" in r, "p_spike", "why_spike")}
    new, entered = [], {gid: {b: 0 for b in BOARDS} for gid in read}
    nights = sorted({night_of(g["tip"]) for g, _r, _s in read.values()})
    for night in nights:
        nt = state.setdefault("nights", {}).setdefault(night, {b: {"n": 0, "players": []} for b in BOARDS})
        here = [v for v in read.values() if night_of(v[0]["tip"]) == night]
        for board in BOARDS:
            key, flt, pk, wk = spec[board]
            used = {tuple(x) for x in nt[board]["players"]}
            cands = sorted(((r, g, rows) for g, rows, _s in here for r in rows if flt(r)), key=lambda c: (-c[0][key], c[0]["tk"]))
            per = collections.Counter()
            taken, chosen = set(used), []
            for r, g, rows in cands:
                if nt[board]["n"] >= NIGHT_CAP:
                    break
                if per[g["id"]] >= GAME_CAP or (r["pid"], r["stat"]) in taken:
                    continue
                per[g["id"]] += 1
                taken.add((r["pid"], r["stat"]))
                nt[board]["players"].append([r["pid"], r["stat"]])
                nt[board]["n"] += 1
                entered[g["id"]][board] += 1
                p = _pick(board, g, night, r, now, r[pk], r[wk], dict(edge=round(r[key], 4)))
                state["rules"][board]["picks"].append(p)
                new.append(p["id"])
                chosen.append((p, g, rows, r))
            for p, g, rows, r in chosen:                      # blind rungs after the board is set: never one of the board's players
                b = draw_blind(board, rows, r, taken)
                if b:
                    bp = _pick(BLIND[board], g, night, b, now, None, "drawn at random from this game's rungs at about the pick's price", dict(matches=p["id"]))
                    state["rules"][BLIND[board]]["picks"].append(bp)
                    new.append(bp["id"])
    for gid, (g, rows, skip) in read.items():
        state["looks"][gid] = dict(at=now.isoformat(), game=f"{g['away']} @ {g['home']}", night=night_of(g["tip"]), usable=len(rows), skipped=dict(skip),
                                   out=len(out_pids), spread=g.get("spread"), entered=entered[gid], batch=len(read))
    return new


# ---------------------------------------------------------------- settle
def prints_of(ticker, fetch=D.get):
    import fillsim_tape as TP
    return F.prints_from_trades([{k: t.get(k) for k in TP.KEEP} for t in TP.fetch_trades(ticker, fetch)])


def sale(prints, entered_ts, target):
    """The first print strictly above the target at least LATENCY_S after the entry, else None: (ts, price)."""
    for p in prints:
        if p[0] >= entered_ts + LATENCY_S and p[1] >= target + 0.01 - EPS:
            return p[0], p[1]
    return None


def settle_row(row, payout, prints=None):
    """Fill in the outcome of one pick. payout is 1 or 0 for YES. profit is dollars a contract after fees; ret is a fraction of the cost."""
    px = row["price"]
    c = cost(px)
    row["fee_in"] = round(fee(px), 4)
    sold = None
    if row["rule"].startswith("spotter_spike") and prints is not None:
        sold = sale(prints, dt.datetime.fromisoformat(row["entered"]).timestamp(), row["target"])
    if sold:
        pay = row["target"] - fee(row["target"])
        row.update(sold=True, sold_at=dt.datetime.fromtimestamp(sold[0], dt.timezone.utc).isoformat(timespec="seconds"), sold_price=row["target"])
        row["profit"] = round(pay - c, 4)
        row["status"] = "won" if row["profit"] > 0 else "lost"
    else:
        row["sold"] = False
        row["profit"] = round(payout - c, 4)
        row["status"] = "won" if payout == 1 else "lost"
    row["payout"] = payout
    row["ret"] = round(row["profit"] / c, 4)
    return row


def settle(state, now, fetch=D.get):
    errs = []
    for lane in state["rules"].values():
        for row in lane["picks"]:
            if row["status"] != "open":
                continue
            if now < dt.datetime.fromisoformat(row["start"]) + dt.timedelta(hours=2):
                continue
            try:
                mk = fetch("markets/" + urllib.parse.quote(row["ticker"], safe="")).get("market", {})
                px = D.payout(mk)
                if px is None:
                    continue
                prints = prints_of(row["ticker"], fetch) if row["rule"].startswith("spotter_spike") else None
                settle_row(row, float(px), prints)
                row["settled"] = now.isoformat()
            except Exception as e:                                   # noqa: BLE001
                errs.append(row["id"] + ": " + str(e)[:80])
    return errs


# ---------------------------------------------------------------- the record
def stats(picks):
    """n, wins, hit rate, mean price, mean profit a contract (dollars), return on cost, t by night (mean of night means v their spread)."""
    done = [p for p in picks if p.get("profit") is not None]
    out = dict(n=len(done), won=sum(1 for p in done if p["profit"] > 0), open=sum(1 for p in picks if p["status"] == "open"), nights=0,
               sold=sum(1 for p in done if p.get("sold")), price=None, profit=None, ret=None, t=None)
    if not done:
        return out
    out["price"] = mean([p["price"] for p in done])
    out["profit"] = mean([p["profit"] for p in done])
    out["ret"] = sum(p["profit"] for p in done) / sum(cost(p["price"]) for p in done)
    by = collections.defaultdict(list)
    for p in done:
        by[p["night"]].append(p["profit"])
    out["nights"] = len(by)
    nm = [mean(v) for v in by.values()]
    out["t"] = (mean(nm) / (statistics.stdev(nm) / math.sqrt(len(nm)))) if len(nm) >= 3 and statistics.stdev(nm) > 0 else None
    out["win_nights"] = sum(1 for v in nm if v > 0)
    return out


def versus_blind(state, board):
    """Mean profit a contract of the board minus its blind control, on the nights both have settled rows: (excess, t by night, nights)."""
    a, b = collections.defaultdict(list), collections.defaultdict(list)
    for p in state["rules"][board]["picks"]:
        if p.get("profit") is not None:
            a[p["night"]].append(p["profit"])
    for p in state["rules"][BLIND[board]]["picks"]:
        if p.get("profit") is not None:
            b[p["night"]].append(p["profit"])
    nights = sorted(set(a) & set(b))
    d = [mean(a[n]) - mean(b[n]) for n in nights]
    if not d:
        return None, None, 0
    t = mean(d) / (statistics.stdev(d) / math.sqrt(len(d))) if len(d) >= 3 and statistics.stdev(d) > 0 else None
    return mean(d), t, len(d)


def read_text(state, board):
    s = stats(state["rules"][board]["picks"])
    n = s["n"]
    if n < READ_AT:
        return f"too early ({n} of {READ_AT} graded picks; read once at {READ_AT})"
    ex, tx, _k = versus_blind(state, board)
    ok = s["profit"] > 0 and (s["t"] or 0) >= 2 and ex is not None and ex >= 0.02
    return "read now: keep (above zero after fees, t 2+ by night, 2+ points over blind)" if ok else "read now: not kept"


# ---------------------------------------------------------------- run
def run(state, W, games_doc, now=None, get=espn_get, fetch=D.get):
    """One pass: finals into the box scores, entries for games 80-35 minutes from tip, then settle. Returns (new pick ids, errors)."""
    now = now or dt.datetime.now(dt.timezone.utc)
    for k in (*BOARDS, *BLIND.values()):
        state["rules"].setdefault(k, {"picks": []})
    errs, new = [], []
    nbox = 0
    try:
        nbox, e = refresh_box(games_doc, now, get)
        errs += e
        if nbox:
            W.games = games_doc["games"]
            W.index()
    except Exception as e:                                           # noqa: BLE001
        errs.append(f"box refresh: {str(e)[:80]}")
    try:
        games = slate(now, get)
    except Exception as e:                                           # noqa: BLE001
        games = []
        errs.append(f"slate: {str(e)[:80]}")
    state["schedule"] = [g["tip"].isoformat() for g in games]
    todo = due(games, now, state["looks"])
    if todo:
        try:
            inj = injuries(get)
            out_pids = set()
            for x in inj:
                c = W.NAME.get(norm(x["name"] or ""), set())
                if x["status"] == "Out" and len(c) == 1:
                    out_pids.add(next(iter(c)))
            tags = {day_tag(g["tip"].astimezone(ET).date()) for g in todo}
            markets = kalshi_markets(tags, fetch)
            new += look_many(state, W, todo, markets, out_pids, now)
        except Exception as e:                                       # noqa: BLE001
            errs.append(f"entries: {str(e)[:100]}")
    errs += settle(state, now, fetch)
    state["last_run"] = now.isoformat()
    state["box_through"] = max((g["day"] for g in games_doc["games"]), default=None)
    state["error"] = "; ".join(errs)[:1000] or None
    state["runs"] = (state.get("runs") or [])[-50:] + [dict(at=now.isoformat(), new=len(new), due=len(todo), box=nbox)]
    return new, errs


def main(argv=None):
    now = dt.datetime.now(dt.timezone.utc)
    games_doc = _json("games.json", {"games": []})
    W = World(games=games_doc["games"])
    state = load()
    new, errs = run(state, W, games_doc, now)
    save(state)
    with open(os.path.join(DATA, "games.json.tmp"), "w") as f:
        json.dump(games_doc, f, separators=(",", ":"))
    os.replace(os.path.join(DATA, "games.json.tmp"), os.path.join(DATA, "games.json"))
    print("spotter", state["runs"][-1], "new", new, "errors", errs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
