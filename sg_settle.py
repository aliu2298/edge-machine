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

# ESPN hosts, tried in order. site.api began returning 403 for EVERY league on 2026-08-08
# — from this machine AND from the GitHub runner, with any user-agent — so it is a
# server-side block, not a rate limit we caused. site.web.api serves the identical payload
# on the identical path. Keeping a list means one host going dark degrades instead of
# killing settlement outright.
ESPN_HOSTS = ["https://site.web.api.espn.com", "https://site.api.espn.com"]
ESPN_PATH = "/apis/site/v2/sports/soccer/{lg}/scoreboard?dates={d}"
ESPN_SUMMARY = "/apis/site/v2/sports/soccer/{lg}/summary?event={eid}"

# Statuses that mean "played to a result". Accepting only STATUS_FULL_TIME left every
# extra-time tie permanently unsettleable (two Aug 11 UCL qualifiers sat stuck).
DONE_STATUSES = {"STATUS_FULL_TIME", "STATUS_FINAL", "STATUS_FINAL_AET",
                 "STATUS_FINAL_PEN", "STATUS_FINAL_AWD"}
# ...but the scoreboard score for those INCLUDES extra time and shootouts, while BTTS /
# totals / handicap bets settle on 90 MINUTES. Grading NEC Nijmegen v Olympiacos on the
# scoreboard's 2-1 instead of the true 1-1 flips an Over 2.5 from loss to win. So for any
# non-90-minute finish we rebuild the regulation score from timed goal events, and if that
# cannot be done we return nothing rather than grade on the wrong basis.
REG_ONLY = {"STATUS_FINAL_AET", "STATUS_FINAL_PEN"}
# Each competition maps to a LIST of ESPN slugs, all of which are searched.
# QUALIFYING rounds live under a separate "_qual" slug: on 2026-08-04 `uefa.champions`
# returned 0 events while `uefa.champions_qual` returned 8 (Red Star at Hapoel Be'er
# Sheva etc.). Querying only the main slug left every August qualifier permanently
# unsettleable — the same failure shape as pointing at the wrong Kalshi series ticker.
ESPN_LEAGUE = {
    "Premier League": ["eng.1"], "La Liga": ["esp.1"], "Bundesliga": ["ger.1"],
    "Serie A": ["ita.1"], "Ligue 1": ["fra.1"], "MLS": ["usa.1"],
    "Eredivisie": ["ned.1"], "Primeira Liga": ["por.1"],
    "Champions League": ["uefa.champions", "uefa.champions_qual"],
    "Europa League": ["uefa.europa", "uefa.europa_qual", "uefa.europa.conf"],
}
_cache = {}


# sportsgambler token -> equivalent ESPN token(s). Some clubs share NO token between the
# two sources: ESPN returns literally "LAFC" in displayName/location/abbreviation, while
# sportsgambler says "Los Angeles FC", so nothing overlaps and the fixture never settles.
# Add an entry whenever sg_health.py reports an unmatched fixture.
ALIASES = {
    "angeles": {"lafc"},
    "athletico": {"paranaense"},
    # ESPN renders these clubs with a completely different name from sportsgambler,
    # so no token overlaps and the fixture never settles. Each was surfaced by a
    # sg_health STUCK warning — that is the loop working as intended.
    "zvezda": {"belgrade", "star"},        # Crvena Zvezda -> "Red Star Belgrade"
    "hearts": {"midlothian"},              # Hearts        -> "Heart of Midlothian"
}


def _norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    drop = {"fc", "cf", "sc", "afc", "club", "the", "united", "city"}
    toks = {w for w in re.split(r"[^a-z0-9]+", s) if len(w) > 2 and w not in drop}
    for t in list(toks):
        toks |= ALIASES.get(t, set())
    return toks


def espn_scores(league, date):
    """[(home, away, hs, as_)] of FINISHED matches for a league/date, across every
    slug that competition uses (main + qualifying)."""
    slugs = ESPN_LEAGUE.get(league)
    if not slugs or not date:
        return []
    key = (league, date)
    if key in _cache:
        return _cache[key]
    out = []
    for lg in slugs:
        out += _espn_one(lg, date)
    _cache[key] = out
    return out


def _espn_one(lg, date):
    """One league slug, trying each host."""
    path = ESPN_PATH.format(lg=lg, d=date.replace("-", ""))
    data, last_err = None, None
    for host in ESPN_HOSTS:
        try:
            req = urllib.request.Request(host + path,
                                         headers={"User-Agent": "edge-machine/1.0"})
            with urllib.request.urlopen(req, timeout=25) as r:
                data = json.load(r)
            break
        except Exception as e:
            last_err = e
    if data is None:
        print(f"  ! espn fetch failed {lg} {date} on all hosts: {last_err}", file=sys.stderr)
        return []
    out = []
    for e in data.get("events", []):
        c = (e.get("competitions") or [{}])[0]
        st = (c.get("status") or {}).get("type", {}).get("name")
        if st not in DONE_STATUSES:
            continue
        cs = c.get("competitors", [])
        if len(cs) < 2:
            continue
        h = next((x for x in cs if x.get("homeAway") == "home"), cs[0])
        a = next((x for x in cs if x.get("homeAway") == "away"), cs[1])
        try:
            hn, an = h["team"]["displayName"], a["team"]["displayName"]
            hs, as_ = int(h.get("score")), int(a.get("score"))
        except (TypeError, ValueError, KeyError):
            continue
        if st in REG_ONLY:
            reg = _regulation_score(lg, e.get("id"), hn, an)
            if reg is None:
                print(f"  ! {hn} v {an}: {st}, could not rebuild the 90-minute score "
                      f"— left unsettled rather than graded on the extra-time result",
                      file=sys.stderr)
                continue
            hs, as_ = reg
        out.append((hn, an, hs, as_))
    return out


def _regulation_score(lg, eid, home_name, away_name):
    """90-minute score rebuilt from timed goal events, or None if not reconstructable."""
    if not eid:
        return None
    try:
        data = None
        for host in ESPN_HOSTS:
            try:
                req = urllib.request.Request(host + ESPN_SUMMARY.format(lg=lg, eid=eid),
                                             headers={"User-Agent": "edge-machine/1.0"})
                with urllib.request.urlopen(req, timeout=25) as r:
                    data = json.load(r)
                break
            except Exception:
                continue
        if not data:
            return None
        events = data.get("keyEvents") or []
        if not events:
            return None
        hs = as_ = 0
        saw_goal = False
        for p in events:
            ty = ((p.get("type") or {}).get("text") or "").lower()
            if "goal" not in ty:                       # includes "own goal", "penalty - scored"
                continue
            clock = ((p.get("clock") or {}).get("displayValue") or "")
            m = re.match(r"(\d+)", clock)
            if not m:
                return None                            # untimed goal -> cannot trust the split
            saw_goal = True
            if int(m.group(1)) > 90:                   # extra time; excluded from a 90' market
                continue
            team = ((p.get("team") or {}).get("displayName") or "")
            if team == home_name:
                hs += 1
            elif team == away_name:
                as_ += 1
            else:
                return None                            # unattributable goal
        return (hs, as_) if saw_goal else None
    except Exception:
        return None


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

    # --- both teams to score ("Both Teams To Score - Yes @ -154") ---
    # sportsgambler publishes these often and they were the ONLY unhandled shape, so
    # every BTTS tip settled as "ungraded" with a null P/L — invisible in the record
    # rather than wrong, but still a hole in a lane that is explicitly BTTS-focused.
    if "both teams to score" in t:
        m = re.search(r"both teams to score\s*[-–:]?\s*(yes|no)\b", t)
        if not m:
            return "ungraded", None
        both = hs > 0 and as_ > 0
        backed_yes = m.group(1) == "yes"
        return ("win", 1.0) if (both == backed_yes) else ("loss", -1.0)

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
        # Re-grade rows that settled as "ungraded": the score is already stored, only the
        # grader was missing. Without this a parser improvement never reaches past rows and
        # the gap stays in the record forever.
        if p.get("status") == "settled" and p.get("tip_result") == "ungraded":
            hs, as_ = p.get("final_home"), p.get("final_away")
            if hs is not None and as_ is not None:
                res, mult = grade_tip(p.get("tip_text", ""), p.get("home", ""),
                                      p.get("away", ""), hs, as_)
                if res != "ungraded":
                    dec = p.get("tip_odds_decimal")
                    p["tip_result"] = res
                    p["tip_pl"] = (None if (mult is None or dec is None) else
                                   round(STAKE * (dec - 1) * mult, 4) if mult > 0 else
                                   round(STAKE * mult, 4))
                    graded += 1
                    print(f"  REGRADED {p['match'][:30]:<30} {p['final_score']}  "
                          f"tip={res}  pl={p['tip_pl']}")
            continue
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
