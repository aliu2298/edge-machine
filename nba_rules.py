"""NBA label rules (2026-10-17): seven Sandbox paper lanes on Kalshi team totals and first-half totals.

Registered by Olu on the 2026-27 PRESEASON tables (54 games): each team's rolling last-five label
from nba_pace.py (O+/O- scores more/less than the league mean, D+/D- allows more/less) against
how often a line hit and what Kalshi (first half) or the sportsbooks (team points, estimated)
charged for it. Paper only, at the Kalshi ask with the 7% fee, settled on Kalshi's own result.
Nothing here is in Production and nothing is placed. One frozen entry per rule per team per game.

  R1  O+ team                 team total 110+   YES   60-80c  (not when both teams are D-: R7)
  R2  O+ team                 team total 115+   YES   <=60c   (not when both teams are D-: R7)
  R3  O- team                 team total 115+   NO    40-65c
  R4  O-D- v O-D-             team total 100-110, the cheapest NO   NO   <=45c
  R5  either team O-D- (1H)   first half 115+   NO    35-60c
  R6  O+ team                 team total 105+   YES   <=85c
  R7  both teams D-           team total 110+ or 115+, the NO nearer 50c   NO   40-60c

"Line L+" is the rung whose strike sits nearest L - 0.5 (Kalshi's rungs are N.5), within 1.5.
The labels are the ones the rules were found on: nba_pace.py's rolling five-game window, full
game for team totals and first half for R5. Entries are taken 20-90 minutes before tip-off.
Evidence, preseason only and small: R1 41/51 at 110+, R2 33/51 at 115+, R3 13/22 broad +
19/26 weak-v-weak, R4 5/10 at 27c, R5 8/12 on real Kalshi prices, R6 21/22, R7 ~31 team-games.
Team-points prices in that evidence were ESTIMATED from sportsbook lines; these lanes are the
first test on real Kalshi team-total prices.
"""
import datetime as dt
import json
import os
import urllib.parse

import daily_track as D

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "data", "nba_rules_ledger.json")
PACE = os.path.join(ROOT, "data", "nba_pace.json")
FEE = 0.07
WINDOW_MIN = (20, 90)            # minutes before tip-off
MAX_SPREAD = 0.05
TEAM, HALF = "KXNBATEAMTOTAL", "KXNBA1HTOTAL"
E2K = {"SA": "SAS", "NY": "NYK", "GS": "GSW", "NO": "NOP", "UTAH": "UTA", "WSH": "WAS"}
K2E = {v: k for k, v in E2K.items()}
MON = "JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split()
ET = D.ET

RULES = {
    "R1": dict(label="O+ team · team total 110+ · YES 60-80c", market=TEAM),
    "R2": dict(label="O+ team · team total 115+ · YES ≤60c", market=TEAM),
    "R3": dict(label="O− team · team total 115+ · NO 40-65c", market=TEAM),
    "R4": dict(label="O−D− v O−D− · team total 100-110 · cheapest NO ≤45c", market=TEAM),
    "R5": dict(label="Either team O−D− (1st half) · 1H total 115+ · NO 35-60c", market=HALF),
    "R6": dict(label="O+ team · team total 105+ · YES ≤85c", market=TEAM),
    "R7": dict(label="Both teams D− · team total 110+/115+ · NO 40-60c", market=TEAM),
}


def fee(p):
    return FEE * p * (1 - p)


def load(path=PATH):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {"version": "nba-rules-v1", "rules": {k: {"picks": []} for k in RULES}, "runs": []}


def event_tag(start, away, home):
    """KX...-26OCT18HOUSAS: the ET date of tip-off, then Kalshi's away and home codes."""
    t = D.instant(start).astimezone(ET)
    return f"{t:%y}{MON[t.month - 1]}{t:%d}{E2K.get(away, away)}{E2K.get(home, home)}"


def quote(m):
    b, a = D.number(m.get("yes_bid_dollars")), D.number(m.get("yes_ask_dollars"))
    if b is None or a is None or not 0 < b < a < 1 or a - b > MAX_SPREAD + 1e-9:
        return None
    return b, a


def rung(ms, line):
    """The open market whose strike is nearest line - 0.5, within 1.5 points, with a quote."""
    best = None
    for m in ms:
        k = m.get("floor_strike")
        if not isinstance(k, (int, float)) or m.get("status") not in ("active", "open") or not quote(m):
            continue
        d = abs(k - (line - 0.5))
        if d <= 1.5 and (best is None or d < best[0]):
            best = (d, m)
    return best[1] if best else None


def team_of(m):
    """The ESPN code a team-total market is about: KX...-MEMCHA-CHA137 -> CHA."""
    code = "".join(ch for ch in str(m.get("ticker", "")).rsplit("-", 1)[-1] if ch.isalpha())
    return K2E.get(code, code)


def entry(rule, g, team, m, side, price, now, why):
    return dict(id=f"{rule}:{m['ticker']}", rule=rule, game=g["id"], team=team,
                match=f"{g['away']} @ {g['home']}", start=g["start"], ticker=m["ticker"],
                strike=m.get("floor_strike"), side=side, price=round(price, 4),
                title=m.get("yes_sub_title") or m.get("title"), logged=now.isoformat(),
                status="open", why=why,
                labels=dict(home=g.get("roll_lab_home_ft"), away=g.get("roll_lab_away_ft"),
                            home_h1=g.get("roll_lab_home_h1"), away_h1=g.get("roll_lab_away_h1")))


def team_picks(g, ms, now):
    """R1-R4, R6, R7 for both teams of one game, from its team-total markets."""
    out = []
    lab = {g["home"]: g.get("roll_lab_home_ft"), g["away"]: g.get("roll_lab_away_ft")}
    if not all(lab.values()):
        return out
    both_dm = all(v[2:] == "D-" for v in lab.values())
    for team, opp in ((g["home"], g["away"]), (g["away"], g["home"])):
        mine = [m for m in ms if team_of(m) == team]
        own, theirs = lab[team], lab[opp]
        why = f"{team} {own} v {opp} {theirs}"

        def take(rule, line, side, lo, hi):
            m = rung(mine, line)
            if not m:
                return
            b, a = quote(m)
            px = a if side == "yes" else round(1 - b, 4)
            if lo - 1e-9 <= px <= hi + 1e-9:
                out.append(entry(rule, g, team, m, side, px, now, f"{why} · {line}+ {side.upper()} {px:.2f}"))

        if own[:2] == "O+":
            # Both teams D-: R7 fades the 110/115 rungs, so the O+ overs on those lines stand
            # aside rather than buying both sides of one contract. R6 (105) is a different line.
            if not both_dm:
                take("R1", 110, "yes", 0.60, 0.80)
                take("R2", 115, "yes", 0.0, 0.60)
            take("R6", 105, "yes", 0.0, 0.85)
        if own[:2] == "O-":
            take("R3", 115, "no", 0.40, 0.65)
        if own == "O-D-" and theirs == "O-D-":
            cands = []
            for m in mine:
                k, q = m.get("floor_strike"), quote(m)
                if isinstance(k, (int, float)) and 98.5 <= k <= 110.5 and q and 1 - q[0] <= 0.45:
                    cands.append((round(1 - q[0], 4), k, m))
            if cands:
                px, k, m = min(cands, key=lambda c: (c[0], -c[1]))
                out.append(entry("R4", g, team, m, "no", px, now, f"{why} · cheapest NO {px:.2f} at {k:g}"))
        if both_dm:
            cands = []
            for line in (110, 115):
                m = rung(mine, line)
                if m:
                    px = round(1 - quote(m)[0], 4)
                    if 0.40 - 1e-9 <= px <= 0.60 + 1e-9:
                        cands.append((abs(px - 0.5), line, px, m))
            if cands:
                _d, line, px, m = min(cands, key=lambda c: (c[0], c[1]))
                out.append(entry("R7", g, team, m, "no", px, now, f"{why} · both D− · {line}+ NO {px:.2f}"))
    return out


def half_picks(g, ms, now):
    """R5: the first-half 115+ NO when either team carries a first-half O-D- label."""
    h, a = g.get("roll_lab_home_h1"), g.get("roll_lab_away_h1")
    if "O-D-" not in (h, a):
        return []
    m = rung(ms, 115)
    if not m:
        return []
    px = round(1 - quote(m)[0], 4)
    if not 0.35 - 1e-9 <= px <= 0.60 + 1e-9:
        return []
    return [entry("R5", g, "game", m, "no", px, now, f"1H {g['away']} {a} @ {g['home']} {h} · 115+ NO {px:.2f}")]


def due(games, now):
    """Scheduled, labelled games tipping off 20-90 minutes from now."""
    out = []
    for g in games:
        if g.get("completed") or g.get("skipped"):
            continue
        t = D.instant(g.get("start"))
        if t and WINDOW_MIN[0] * 60 <= (t - now).total_seconds() <= WINDOW_MIN[1] * 60:
            out.append(g)
    return out


def event_markets(series, g, fetch):
    for tag in (event_tag(g["start"], g["away"], g["home"]), event_tag(g["start"], g["home"], g["away"])):
        ms = D.pages(f"markets?limit=200&event_ticker={series}-{tag}", "markets", fetch)
        if ms:
            return ms
    return []


def settle(state, now, fetch):
    errs = []
    for lane in state["rules"].values():
        for row in lane["picks"]:
            if row["status"] != "open":
                continue
            try:
                m = fetch("markets/" + urllib.parse.quote(row["ticker"], safe="")).get("market", {})
                px = D.payout(m)
                if px is None:
                    continue
                pay = px if row["side"] == "yes" else 1 - px
                row.update(payout=pay, profit=round(100 * (pay / (row["price"] + fee(row["price"])) - 1), 2),
                           status="won" if pay == 1 else "lost" if pay == 0 else "no_result", settled=now.isoformat())
            except Exception as e:                              # noqa: BLE001
                errs.append(row["id"] + ": " + str(e)[:80])
    return errs


def run(state, games, now=None, fetch=D.get):
    now = now or dt.datetime.now(dt.timezone.utc)
    seen = {p["id"] for lane in state["rules"].values() for p in lane["picks"]}
    have = {(p["rule"], p["game"], p["team"]) for lane in state["rules"].values() for p in lane["picks"]}
    log, errs = [], []
    for g in due(games, now):
        try:
            picks = team_picks(g, event_markets(TEAM, g, fetch), now) + half_picks(g, event_markets(HALF, g, fetch), now)
        except Exception as e:                                  # noqa: BLE001
            errs.append(f"{g['away']}@{g['home']}: {str(e)[:80]}")
            continue
        for p in picks:
            if p["id"] in seen or (p["rule"], p["game"], p["team"]) in have:
                continue
            state["rules"][p["rule"]]["picks"].append(p)
            seen.add(p["id"]); have.add((p["rule"], p["game"], p["team"]))
            log.append(p["id"])
    errs += settle(state, now, fetch)
    state["last_run"] = now.isoformat()
    state["error"] = "; ".join(errs)[:1000] or None
    state["runs"] = (state.get("runs") or [])[-50:] + [dict(at=now.isoformat(), due=len(due(games, now)), new=len(log))]
    return log


def main():
    state = load()
    with open(PACE) as f:
        games = json.load(f).get("games") or []
    new = run(state, games)
    tmp = PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=1, sort_keys=True)
        f.write("\n")
    os.replace(tmp, PATH)
    for k, lane in state["rules"].items():
        print(k, "picks", len(lane["picks"]), "open", sum(p["status"] == "open" for p in lane["picks"]))
    print("new", new, "error", state["error"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
