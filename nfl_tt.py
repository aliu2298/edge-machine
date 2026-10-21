#!/usr/bin/env python3
"""NFL team totals · OVER (2026-10-21): two Sandbox PAPER lanes, `nfl_tt_over_3545` and `nfl_tt_over_main`.

Paper only: not in Production, not in the Production feed, no PAIR_OVERRIDES entry, on their own
fresh record (data/nfl_tt_ledger.json). Nothing is placed.

PRE-REGISTERED 2026-10-21. Research on Kalshi KXNFLTEAMTOTAL quotes 1 hour before kickoff, spread
5c or less, after fee, z clustered by NFL week.
  2026 weeks 1-6 (93 games): OVER 35-45c 72/144, 50% @39c, +23.1%, z +2.72 (weeks 1-4 +28%,
  weeks 5-6 +14%). Main-line OVER 100/185, 54% @51c, +3.2% (+3% / +3%).
  2025 holdout (archived markets; Kalshi team totals exist from Dec 2025, 45 games): OVER 35-45c
  16/22, 73% @39c, +79.1%, z +3.25. Main-line OVER 27/42, 64% @51c, +22.7%, z +1.85. Main-line
  UNDER 15/42, -33%.
  Reading: Kalshi sets NFL team-total lines too low.
  Caveats: the holdout is small (22 and 42 picks), from one late-season/playoff stretch, and the
  2026 window is the one the angle was found on. Read at 30 settled entries each; Olu reviews at 10+.

THE RULES
1. Scope: Kalshi's NFL team-total ladders, series KXNFLTEAMTOTAL, nothing else. Each game event
   (KXNFLTEAMTOTAL-26OCT19WASSF) holds one ladder per team; a rung is "<team> over N.5 points"
   (strike_type greater, floor_strike N.5) and its team is the ticker suffix without the strike
   (...-SF15 is San Francisco). Kickoffs come from ESPN's NFL scoreboard; a game is matched to its
   event by the ET date of kickoff and the two team codes, in either order, with Kalshi's WAS / LA /
   JAC read as ESPN's WSH / LAR / JAX.
2. Quote: only a rung with a two-sided YES quote (bid above 0, ask below 1) and spread at most 5c,
   the research filter, can be picked. No depth floor, as the other paper ladder lanes; the size at
   the ask is recorded on each entry.
3. nfl_tt_over_3545: per team per game, the YES on the CHEAPEST rung (lowest YES ask) of that
   team's ladder whose ask is at least 0.35 and below 0.45. A tie on the ask goes to the lower
   ticker (the lower strike).
4. nfl_tt_over_main: per team per game, the YES on the rung whose mid ((bid + ask) / 2) is nearest
   0.50. A tie goes to the lower strike. One market, one lane: if that rung is the one
   nfl_tt_over_3545 took, nfl_tt_over_3545 keeps it and this lane takes the next-nearest-to-50c rung.
5. Entry: 45 to 75 minutes before the ESPN kickoff (inclusive), while ESPN still has the game as
   not started. One frozen entry per lane per team per game: up to two per game per lane.
6. Settled on Kalshi's official result, profit per $100 after the 7% taker fee 0.07 p (1 - p).
   Stats are clustered by NFL week (games in one week share conditions): the z uses the
   week-clustered variance, never below the independent-bets variance.
7. Blind baseline: the YES on EVERY in-window team-total rung with the same two-sided 5c quote,
   one entry per rung.

How it runs: nfl-tt.yml, asked for by the VPS from inside each kickoff's window
(scripts/vps_window_requests.sh, lane_windows.nfl_windows), plus an hourly schedule that settles.
Each run writes the next 8 days' valid kickoffs into the ledger ("schedule"), which the VPS reads.
"""
import datetime as dt
import json
import os
import re
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

import daily_track as D

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "data", "nfl_tt_ledger.json")
LANE_BAND = "nfl_tt_over_3545"
LANE_MAIN = "nfl_tt_over_main"
LANES = (LANE_BAND, LANE_MAIN)
BASE = "baseline"
REGISTERED = "2026-10-21"
SERIES = "KXNFLTEAMTOTAL"
BAND = (0.35, 0.45)              # YES ask, low end inclusive, high end exclusive
WINDOW_MIN = (45, 75)            # minutes before the ESPN kickoff, both ends inclusive
MAX_SPREAD = 0.05
FEE = 0.07
SCHEDULE_DAYS = 8
EPS = 1e-9
ET = ZoneInfo("America/New_York")
ESPN = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
MON = "JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split()
# ESPN code -> the other code Kalshi has used for the same team.
ALIAS = {"WSH": "WAS", "LAR": "LA", "JAX": "JAC"}
NAMES = {LANE_BAND: "NFL team total · OVER 35-45c", LANE_MAIN: "NFL team total · OVER · main line"}
PREREG = {
    LANE_BAND: (
        "PRE-REGISTERED 2026-10-21: research on Kalshi KXNFLTEAMTOTAL quotes 1h before kickoff, spread "
        "≤5c, after fee, week-clustered z. 2026 weeks 1-6 (93 games): OVER 35-45c 72/144, 50% @39c, "
        "+23.1%, z +2.72 (weeks 1-4 +28% / weeks 5-6 +14%). 2025 holdout (archived markets, Kalshi team "
        "totals exist from Dec 2025, 45 games): 16/22, 73% @39c, +79.1%, z +3.25. Reading: Kalshi sets "
        "NFL team-total lines too low. Caveats: the holdout is small (22 picks), from one "
        "late-season/playoff stretch, and the 2026 window is the one the angle was found on. Read at 30 "
        "settled entries; Olu reviews at 10+."),
    LANE_MAIN: (
        "PRE-REGISTERED 2026-10-21: research on Kalshi KXNFLTEAMTOTAL quotes 1h before kickoff, spread "
        "≤5c, after fee, week-clustered z. 2026 weeks 1-6 (93 games): main-line OVER 100/185, 54% @51c, "
        "+3.2% (weeks 1-4 +3% / weeks 5-6 +3%). 2025 holdout (archived markets, Kalshi team totals exist "
        "from Dec 2025, 45 games): 27/42, 64% @51c, +22.7%, z +1.85; main-line UNDER 15/42, −33%. "
        "Reading: Kalshi sets NFL team-total lines too low. Caveats: the holdout is small (42 picks), "
        "from one late-season/playoff stretch, and the 2026 window is the one the angle was found on. "
        "Read at 30 settled entries; Olu reviews at 10+."),
}
_COMMON = ("Entry 45-75 minutes before the ESPN kickoff, one frozen entry per team per game. Only a "
           "two-sided YES quote with spread ≤5c counts, no depth floor. Settled on Kalshi's official "
           "result after the 7% taker fee; stats clustered by NFL week. Blind baseline: the YES on "
           "every in-window team-total rung with the same quote. Paper, Sandbox only.")
DEFINITION = {
    LANE_BAND: ("Kalshi NFL team totals (KXNFLTEAMTOTAL). Per team per game, back YES (over) on the "
                "CHEAPEST rung of that team's ladder whose YES ask is ≥0.35 and <0.45; a tie goes to "
                "the lower ticker. " + _COMMON),
    LANE_MAIN: ("Kalshi NFL team totals (KXNFLTEAMTOTAL). Per team per game, back YES (over) on the "
                "rung whose mid ((bid+ask)/2) is nearest 0.50; a tie goes to the lower strike. If "
                "that rung is the OVER 35-45c lane's pick, that lane keeps it and this one takes the "
                "next-nearest-to-50c rung. " + _COMMON),
}


def fee(p):
    return FEE * p * (1 - p)


def empty():
    return {"version": "nfl-tt-v1", "registered": REGISTERED,
            "rules": {LANE_BAND: {"picks": []}, LANE_MAIN: {"picks": []}, BASE: {"picks": []}},
            "runs": [], "schedule": []}


def load(path=PATH):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return empty()


# ---------- ESPN kickoffs ----------

def http_json(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "edge-machine-paper-nfl"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def espn_games(now=None, fetch=http_json, days=SCHEDULE_DAYS):
    """NFL games on ESPN's scoreboard from yesterday (ET) through `days` ahead, deduped by id.

    Each is {id, start, valid, state, away, home, week}: ESPN's team codes and a week key
    "<season year>-<season type>-W<week>" for the clustering."""
    now = now or dt.datetime.now(dt.timezone.utc)
    today = now.astimezone(ET).date()
    out = {}
    for i in range(-1, days + 1):
        day = today + dt.timedelta(days=i)
        d = fetch(f"{ESPN}?dates={day:%Y%m%d}")
        for e in d.get("events") or []:
            for c in (e.get("competitions") or [])[:1]:
                side = {x.get("homeAway"): ((x.get("team") or {}).get("abbreviation") or "").upper()
                        for x in c.get("competitors") or []}
                start = c.get("date") or e.get("date")
                season = e.get("season") or {}
                wk = (e.get("week") or {}).get("number")
                t = start_of(dict(start=start))
                year = season.get("year") or (t.year if t else None)
                week = f"{year}-{season.get('type', 2)}-W{int(wk):02d}" if wk else None
                out[str(e.get("id"))] = dict(
                    id=str(e.get("id")), start=start, valid=bool(c.get("timeValid", True)),
                    state=((c.get("status") or e.get("status") or {}).get("type") or {}).get("state"),
                    away=side.get("away"), home=side.get("home"), week=week, name=e.get("shortName"))
    return list(out.values())


def start_of(g):
    return D.instant(str(g.get("start") or "").replace("Z", "+00:00"))


def real_game(g):
    return bool(g.get("away") and g.get("home") and g.get("valid") and start_of(g) is not None)


def week_of(g):
    """ESPN's week key, else the Tuesday-to-Monday ET week the kickoff falls in."""
    if g.get("week"):
        return g["week"]
    t = start_of(g)
    if t is None:
        return None
    d = t.astimezone(ET).date()
    return "wk-" + (d - dt.timedelta(days=(d.weekday() - 1) % 7)).isoformat()


def schedule(games, now):
    """Valid kickoffs of unstarted games over the next SCHEDULE_DAYS days, ISO UTC, sorted."""
    out = set()
    for g in games:
        t = start_of(g)
        if real_game(g) and g.get("state") == "pre" and now - dt.timedelta(hours=1) <= t <= now + dt.timedelta(days=SCHEDULE_DAYS):
            out.add(t.astimezone(dt.timezone.utc).isoformat())
    return sorted(out)


# ---------- matching ----------

def codes(espn_code):
    """Every code Kalshi may use for an ESPN team code."""
    c = str(espn_code or "").upper()
    return {c, ALIAS[c]} if c in ALIAS else {c}


def event_tag(ticker):
    """KXNFLTEAMTOTAL-26OCT19WASSF -> (2026-10-19, "WASSF"), else None."""
    m = re.match(r"^[A-Z0-9]+-(\d{2})([A-Z]{3})(\d{2})([A-Z]+)$", str(ticker or ""))
    if not m or m.group(2) not in MON:
        return None
    try:
        return dt.date(2000 + int(m.group(1)), MON.index(m.group(2)) + 1, int(m.group(3))), m.group(4)
    except ValueError:
        return None


def fits(ev, g):
    tag, t = event_tag(ev.get("event_ticker")), start_of(g)
    if not tag or t is None or not real_game(g):
        return False
    day, teams = tag
    if day != t.astimezone(ET).date():
        return False
    pairs = {a + h for a in codes(g["away"]) for h in codes(g["home"])}
    pairs |= {h + a for a in codes(g["away"]) for h in codes(g["home"])}
    return teams in pairs


def find_event(g, events):
    hits = [ev for ev in events if fits(ev, g)]
    return hits[0] if len(hits) == 1 else None


def team_of(ticker, g):
    """The ESPN code of the team a rung belongs to, from the ticker suffix (...-SF15 -> SF)."""
    m = re.match(r"^([A-Z]+)\d+$", str(ticker or "").rsplit("-", 1)[-1])
    if not m:
        return None
    for t in (g.get("away"), g.get("home")):
        if m.group(1) in codes(t):
            return t
    return None


# ---------- rungs and quotes ----------

def strike(mk):
    v = D.number(mk.get("floor_strike"))
    if v is None or abs((v % 1) - 0.5) > EPS:
        return None
    if mk.get("strike_type") not in (None, "", "greater"):
        return None
    return v


def quote(mk):
    """(bid, ask) for a two-sided YES quote with spread at most 5c, else None."""
    b, a = D.number(mk.get("yes_bid_dollars")), D.number(mk.get("yes_ask_dollars"))
    if b is None or a is None or not 0 < b < a < 1 or a - b > MAX_SPREAD + EPS:
        return None
    return b, a


def ladders(ev, g):
    """{ESPN team code: [(strike, market, bid, ask)]} of active rungs with a passing quote, lowest strike first."""
    out = {}
    for mk in ev.get("markets") or []:
        if str(mk.get("status") or "").lower() not in ("active", "open"):
            continue
        s, team, q = strike(mk), team_of(mk.get("ticker"), g), quote(mk)
        if s is None or team is None or q is None:
            continue
        out.setdefault(team, []).append((s, mk, q[0], q[1]))
    for v in out.values():
        v.sort(key=lambda x: (x[0], str(x[1].get("ticker"))))
    return out


def in_band(a):
    return BAND[0] - EPS <= a < BAND[1] - EPS


def pick_band(ladder):
    """The cheapest in-band rung (lowest ask, a tie to the lower strike), or None."""
    inb = [r for r in ladder if in_band(r[3])]
    return min(inb, key=lambda r: (r[3], r[0])) if inb else None


def pick_main(ladder, taken=None):
    """The rung whose mid is nearest 0.50 (a tie to the lower strike), skipping `taken`'s market."""
    skip = taken[1].get("ticker") if taken else None
    rest = [r for r in ladder if r[1].get("ticker") != skip]
    return min(rest, key=lambda r: (round(abs((r[2] + r[3]) / 2 - 0.5), 6), r[0])) if rest else None


def in_window(g, now):
    t = start_of(g)
    if t is None:
        return False
    lead = (t - now).total_seconds()
    return WINDOW_MIN[0] * 60 <= lead <= WINDOW_MIN[1] * 60


def due(games, now):
    return [g for g in games if real_game(g) and g.get("state") == "pre" and in_window(g, now)]


def entry(rule, ev, g, team, r, now):
    s, mk, b, a = r
    t = start_of(g)
    eid = f"{rule}:{ev['event_ticker']}:{team}" if rule in LANES else f"{BASE}:{mk['ticker']}"
    return dict(id=eid, rule=rule, event=ev["event_ticker"], ticker=mk["ticker"], team=team, line=s, side="yes",
                game=f"{g['away']} @ {g['home']}", espn_id=g.get("id"), week=week_of(g),
                start=t.astimezone(dt.timezone.utc).isoformat(), lead_min=round((t - now).total_seconds() / 60, 1),
                price=round(a, 4), bid=b, ask=a, mid=round((b + a) / 2, 4), ask_size=D.number(mk.get("yes_ask_size_fp")),
                title=mk.get("yes_sub_title") or mk.get("title"), logged=now.isoformat(), status="open",
                why=f"{team} over {s} YES {a:.2f}")


def picks_for(ev, g, now):
    """{lane: [entries]} plus the baseline for one matched, in-window game."""
    out = {LANE_BAND: [], LANE_MAIN: [], BASE: []}
    for team, ladder in sorted(ladders(ev, g).items()):
        band = pick_band(ladder)
        if band:
            out[LANE_BAND].append(entry(LANE_BAND, ev, g, team, band, now))
        main = pick_main(ladder, band)
        if main:
            out[LANE_MAIN].append(entry(LANE_MAIN, ev, g, team, main, now))
        out[BASE] += [entry(BASE, ev, g, team, r, now) for r in ladder]
    return out


# ---------- settlement and stats ----------

def settle(state, now, fetch):
    errs = []
    for lane in state["rules"].values():
        for row in lane["picks"]:
            if row["status"] != "open":
                continue
            try:
                mk = fetch("markets/" + urllib.parse.quote(row["ticker"], safe="")).get("market", {})
                pay = D.payout(mk)
                if pay is None:
                    continue
                row.update(payout=pay, profit=round(100 * (pay / (row["price"] + fee(row["price"])) - 1), 2),
                           status="won" if pay == 1 else "lost" if pay == 0 else "no_result", settled=now.isoformat())
            except Exception as e:                              # noqa: BLE001
                errs.append(row["id"] + ": " + str(e)[:80])
    return errs


def stats(picks):
    """n (won+lost), n_price (no result), won, expected, z (week-clustered), weeks, roi_fee, open.

    The clustered variance is the sum over NFL weeks of the squared week residual (wins minus
    prices), floored at the independent-bets variance sum p(1-p) so a week whose residuals
    happen to cancel never makes the z look stronger than treating every bet as its own."""
    wl = [p for p in picks if p["status"] in ("won", "lost")]
    done = wl + [p for p in picks if p["status"] == "no_result"]
    won = sum(p["status"] == "won" for p in wl)
    exp = sum(p["price"] for p in wl)
    iid = sum(p["price"] * (1 - p["price"]) for p in wl)
    weeks = {}
    for p in wl:
        weeks.setdefault(p.get("week") or p.get("start", "")[:10], []).append(p)
    clus = sum(sum((p["status"] == "won") - p["price"] for p in ps) ** 2 for ps in weeks.values())
    var = max(iid, clus)
    return dict(n=len(wl), n_price=len(done) - len(wl), won=won, expected=exp,
                z=(won - exp) / var ** 0.5 if var > 0 else 0.0,
                z_iid=(won - exp) / iid ** 0.5 if iid > 0 else 0.0, weeks=len(weeks),
                roi_fee=sum(p.get("profit") or 0 for p in done) / (100 * len(done)) if done else None,
                open=sum(p["status"] == "open" for p in picks))


# ---------- the run ----------

def fetch_events(fetch=D.get):
    return [ev for ev in D.pages(f"events?series_ticker={SERIES}&status=open&limit=200&with_nested_markets=true",
                                 "events", fetch) if str(ev.get("event_ticker") or "").startswith(SERIES + "-")]


def run(state, games, now=None, fetch=D.get):
    now = now or dt.datetime.now(dt.timezone.utc)
    for k in (*LANES, BASE):
        state["rules"].setdefault(k, {"picks": []})
    seen = {p["id"] for lane in state["rules"].values() for p in lane["picks"]}
    log, errs = [], []
    st = dict(due=0, matched=0, entered=0, baseline=0)
    todo = due(games, now)
    events = None
    if todo:
        try:
            events = fetch_events(fetch)
        except Exception as e:                                  # noqa: BLE001
            errs.append(f"{SERIES}: {str(e)[:80]}")
    for g in todo if events is not None else ():
        st["due"] += 1
        ev = find_event(g, events)
        if not ev:
            continue
        st["matched"] += 1
        for rule, rows in picks_for(ev, g, now).items():
            for p in rows:
                if p["id"] in seen:
                    continue
                state["rules"][rule]["picks"].append(p)
                seen.add(p["id"])
                if rule == BASE:
                    st["baseline"] += 1
                else:
                    log.append(p["id"])
                    st["entered"] += 1
    errs += settle(state, now, fetch)
    state["schedule"] = schedule(games, now)
    state["last_run"] = now.isoformat()
    state["error"] = "; ".join(errs)[:1000] or None
    state["runs"] = (state.get("runs") or [])[-50:] + [dict(at=now.isoformat(), new=len(log), **st)]
    return log


def board(games, now=None, fetch=D.get):
    """What the scanner sees now, per upcoming matched game (a probe, no writes)."""
    now = now or dt.datetime.now(dt.timezone.utc)
    events = fetch_events(fetch)
    out = []
    for g in games:
        if not real_game(g) or g.get("state") != "pre":
            continue
        ev = find_event(g, events)
        if not ev:
            out.append(dict(game=f"{g['away']} @ {g['home']}", start=g["start"], matched=False, band=0, main=0, teams=0))
            continue
        p = picks_for(ev, g, now)
        out.append(dict(game=f"{g['away']} @ {g['home']}", start=g["start"], matched=True,
                        teams=len(ladders(ev, g)), band=len(p[LANE_BAND]), main=len(p[LANE_MAIN]),
                        band_picks=[x["why"] for x in p[LANE_BAND]], main_picks=[x["why"] for x in p[LANE_MAIN]]))
    return sorted(out, key=lambda r: r["start"]), len(events)


def main(argv=None):
    import sys
    argv = sys.argv[1:] if argv is None else argv
    out = argv[argv.index("--out") + 1] if "--out" in argv else PATH
    now = dt.datetime.now(dt.timezone.utc)
    games = espn_games(now)
    if "--board" in argv:
        rows, n_ev = board(games, now)
        print(f"{n_ev} open {SERIES} events; {len(rows)} upcoming ESPN games")
        for r in rows:
            t = start_of(r).astimezone(ZoneInfo("America/Chicago"))
            print(f"  {t:%a %b %d %H:%M} CT  {r['game']:10} matched {r['matched']!s:5} ladders {r['teams']} "
                  f"3545 {r['band']} main {r['main']}  {r.get('band_picks', '')} {r.get('main_picks', '')}")
        return 0
    state = load(out)
    new = run(state, games, now)
    tmp = out + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=1, sort_keys=True)
        f.write("\n")
    os.replace(tmp, out)
    print("run", state["runs"][-1], "new", new, "schedule", len(state["schedule"]), "error", state["error"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
