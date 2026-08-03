#!/usr/bin/env python3
"""sg_settle.py — grade scraped sportsgambler picks from ESPN final scores.

WHY ESPN AND NOT THE MATCH PAGE: sportsgambler match pages do NOT update in place
with the final score, and their fixtures-results pages list only upcoming fixtures.
Scraping the match page for a scoreline picks up *historical H2H* sentences instead
("A 3-2 home success at Soldier Field...") and silently grades against the wrong
result — verified 2026-08-03. ESPN's scoreboard API is keyless, covers all 10
leagues, and is what app.py already settles from.

Grades three items independently:
  projected score — hit only on an exact scoreline
  btts            — did both teams score at least one
  tip             — by market type (moneyline / Asian handicap incl. quarter lines / totals)

Anything not gradeable with confidence is marked "ungraded" with a null P/L. A
settled WIN is NEVER scored as a loss for want of odds.

Usage:  python3 sg_settle.py [--force]
"""
import json, os, re, sys, time, datetime, urllib.request, unicodedata

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data", "sg_picks.json")
STAKE = 1.0                       # flat 1 unit, paper-tracked

ESPN = "https://site.api.espn.com/apis/site/v2/sports/soccer/{lg}/scoreboard?dates={d}"
ESPN_LEAGUE = {
    "Premier League": "eng.1", "La Liga": "esp.1", "Bundesliga": "ger.1",
    "Serie A": "ita.1", "Ligue 1": "fra.1", "MLS": "usa.1",
    "Eredivisie": "ned.1", "Primeira Liga": "por.1",
    "Champions League": "uefa.champions", "Europa League": "uefa.europa",
}
_cache = {}


# sportsgambler token -> equivalent ESPN token(s). Some clubs share NO token between the
# two sources: ESPN returns literally "LAFC" in displayName/location/abbreviation, while
# sportsgambler says "Los Angeles FC", so nothing overlaps and the fixture never settles.
# Add an entry whenever sg_health.py reports an unmatched fixture.
ALIASES = {
    "angeles": {"lafc"},
    "athletico": {"paranaense"},
}


def _norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    drop = {"fc", "cf", "sc", "afc", "club", "the", "united", "city"}
    toks = {w for w in re.split(r"[^a-z0-9]+", s) if len(w) > 2 and w not in drop}
    for t in list(toks):
        toks |= ALIASES.get(t, set())
    return toks


def espn_scores(league, date):
    """[(home, away, hs, as_)] of FINISHED matches for a league/date."""
    lg = ESPN_LEAGUE.get(league)
    if not lg or not date:
        return []
    key = (lg, date)
    if key in _cache:
        return _cache[key]
    url = ESPN.format(lg=lg, d=date.replace("-", ""))
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "edge-machine/1.0"})
        with urllib.request.urlopen(req, timeout=25) as r:
            data = json.load(r)
    except Exception as e:
        print(f"  ! espn fetch failed {lg} {date}: {e}", file=sys.stderr)
        _cache[key] = []
        return []
    out = []
    for e in data.get("events", []):
        c = (e.get("competitions") or [{}])[0]
        if (c.get("status") or {}).get("type", {}).get("name") != "STATUS_FULL_TIME":
            continue
        cs = c.get("competitors", [])
        if len(cs) < 2:
            continue
        h = next((x for x in cs if x.get("homeAway") == "home"), cs[0])
        a = next((x for x in cs if x.get("homeAway") == "away"), cs[1])
        try:
            out.append((h["team"]["displayName"], a["team"]["displayName"],
                        int(h.get("score")), int(a.get("score"))))
        except (TypeError, ValueError, KeyError):
            continue
    _cache[key] = out
    return out


def find_score(pick):
    """Match a scraped pick to an ESPN result by team-name tokens (+/- 1 day)."""
    ph, pa = _norm(pick.get("home", "")), _norm(pick.get("away", ""))
    if not ph or not pa:
        return None
    try:
        base = datetime.date.fromisoformat(pick.get("date", ""))
    except ValueError:
        return None
    for delta in (0, -1, 1):        # kickoff can land either side of the UTC date
        d = (base + datetime.timedelta(days=delta)).isoformat()
        for eh, ea, hs, as_ in espn_scores(pick.get("league", ""), d):
            if (_norm(eh) & ph) and (_norm(ea) & pa):
                return hs, as_
    return None


def side_of(named, home, away):
    """Is the team named in a tip the home or away side? Returns 'home'/'away'/None."""
    n = _norm(named)
    if not n:
        return None
    h, a = bool(n & _norm(home)), bool(n & _norm(away))
    if h == a:                      # matched both or neither -> ambiguous
        return None
    return "home" if h else "away"


def grade_tip(tip, home, away, hs, as_):
    """(result, stake_multiplier). ('ungraded', None) when not confidently gradeable."""
    if not tip:
        return "ungraded", None
    t = tip.lower()
    margin = hs - as_               # >0 means home won by that much

    # --- Asian handicap, incl. quarter lines (half win / half loss) ---
    m = re.search(r"asian hcp\s*([+-]?\d+(?:\.\d+)?)", t)
    if m:
        line = float(m.group(1))
        named = tip[:m.start()] if m.start() else tip
        side = side_of(named, home, away)
        if side is None:
            return "ungraded", None
        adj = (margin if side == "home" else -margin) + line
        if abs(adj) == 0.25:        # quarter-line split
            return ("half_win", 0.5) if adj > 0 else ("half_loss", -0.5)
        if adj > 0:
            return "win", 1.0
        if adj < 0:
            return "loss", -1.0
        return "push", 0.0

    # --- totals ---
    m = re.search(r"(over|under)\s*(\d+(?:\.\d+)?)\s*goals?", t)
    if m:
        total, line = hs + as_, float(m.group(2))
        if total == line:
            return "push", 0.0
        return (("win", 1.0) if ((total > line) == (m.group(1) == "over"))
                else ("loss", -1.0))

    # --- moneyline "<Team> To Win" ---
    if "to win" in t:
        side = side_of(tip[:t.index("to win")], home, away)
        if side is None:
            return "ungraded", None
        if margin == 0:
            return "loss", -1.0     # straight win market: draw loses
        won = (margin > 0) if side == "home" else (margin < 0)
        return ("win", 1.0) if won else ("loss", -1.0)

    return "ungraded", None


def main():
    force = "--force" in sys.argv
    if not os.path.exists(DATA):
        print("no data/sg_picks.json — run sg_scrape.py first")
        return
    blob = json.load(open(DATA))
    picks = blob.get("picks", [])
    now = datetime.datetime.now(datetime.timezone.utc)
    graded = 0

    for p in picks:
        if p.get("status") != "pending":
            continue
        if not force:
            try:                    # only attempt once the match day has passed
                if (now.date() - datetime.date.fromisoformat(p.get("date", ""))).days < 1:
                    continue
            except ValueError:
                pass

        sc = find_score(p)
        if not sc:
            continue
        hs, as_ = sc
        home, away = p.get("home", ""), p.get("away", "")
        p["final_home"], p["final_away"] = hs, as_
        p["final_score"] = f"{hs}-{as_}"

        if p.get("proj_score"):
            p["proj_result"] = "hit" if p["proj_score"] == p["final_score"] else "miss"

        if p.get("btts_implied"):
            actual = "Yes" if (hs > 0 and as_ > 0) else "No"
            p["btts_actual"] = actual
            p["btts_result"] = "hit" if actual == p["btts_implied"] else "miss"

        res, mult = grade_tip(p.get("tip_text", ""), home, away, hs, as_)
        p["tip_result"] = res
        dec = p.get("tip_odds_decimal")
        if res == "ungraded" or mult is None or dec is None:
            p["tip_pl"] = None      # never guess, never default a win to a loss
        elif mult > 0:
            p["tip_pl"] = round(STAKE * (dec - 1) * mult, 4)
        else:
            p["tip_pl"] = round(STAKE * mult, 4)

        p["status"] = "settled"
        p["settled_at"] = now.isoformat(timespec="seconds")
        graded += 1
        print(f"  {p['match'][:34]:<34} {p['final_score']}  tip={res:<10} pl={p['tip_pl']}"
              f"  proj={p.get('proj_result','-')}  btts={p.get('btts_result','-')}")

    blob["picks"] = picks
    blob["updated_at"] = now.isoformat(timespec="seconds")
    with open(DATA, "w") as f:
        json.dump(blob, f, indent=1)
    pend = sum(1 for p in picks if p.get("status") == "pending")
    print(f"\nsettled {graded} pick(s); {pend} still pending")


if __name__ == "__main__":
    main()
