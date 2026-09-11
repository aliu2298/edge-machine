"""Adapters for the Sandbox Tracker: every prediction source, behind one interface.

The question this file exists to answer is "which prediction source is actually worth
following?", and that question is only answerable if three things are true of every
source: it must state a PROBABILITY (not a pick), on an event that RESOLVES, at a price
that was really available. A tipster page that says "Yankees look good" cannot be scored
against anything, so it is not a source here no matter how well known the site is.

That constraint is what picked the source list. Polymarket is the spine — it is the only
feed that covers all six sports, it carries a tradeable price, and it resolves itself, so
it doubles as the settlement oracle. Everything else is a challenger measured against
that price.

Sources deliberately left UNCONNECTED are still declared in SOURCES with connected=False.
A source that is silently missing looks identical to a source with no edge, and the whole
point of the board is to tell those two apart.
"""

import json
import concurrent.futures
import functools
import html
import http.client
import re
import unicodedata
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

# The six sports the board tracks. Key is internal; label is what the page prints.
SPORTS = {
    "soccer":       "Soccer",
    "tennis":       "Tennis",
    "table_tennis": "Table Tennis",
    "boxing":       "Boxing",
    "nfl":          "NFL",
    "cricket":      "Cricket",
    "mlb":          "MLB",
}

# Polymarket tag slugs, verified live against gamma-api on 2026-09-09: every one of the
# six returns open, tradeable markets. table-tennis is the surprise — Polymarket carries
# a deep book of Ukrainian/WTT singles matches.
PM_TAGS = {
    "soccer": "soccer", "tennis": "tennis", "table_tennis": "table-tennis", "boxing": "boxing",
    "nfl": "nfl", "cricket": "cricket", "mlb": "mlb",
}

# ESPN paths, site API (scoreboard) and core API (predictor/odds).
ESPN_PATHS = {
    "nfl": ("football/nfl", "football/leagues/nfl"),
    "mlb": ("baseball/mlb", "baseball/leagues/mlb"),
}

# Kalshi series tickers, verified returning open markets on 2026-09-09.
KALSHI_SERIES = {"nfl": "KXNFLGAME", "mlb": "KXMLBGAME", "tennis": "KXATPMATCH"}

# The registry. `connected` is the honest bit: it says whether this run can actually
# reach the source, not whether the site exists.
SOURCES = {
    "polymarket": dict(
        label="Polymarket", kind="Prediction market", connected=True,
        site="polymarket.com",
        # Not soccer: that spine is ESPN + DraftKings, so Polymarket neither prices nor
        # quotes it, and claiming coverage would show an empty cell as a failure.
        sports=[s for s in SPORTS if s != "soccer"],
        note="The benchmark. Its own price is what every other source is priced against, "
             "so it cannot beat itself — a flat ~0% ROI here is the expected result and "
             "is the control that proves the ledger is wired up correctly."),
    "kalshi": dict(
        label="Kalshi", kind="Prediction market", connected=True,
        site="kalshi.com", sports=["nfl", "mlb", "tennis"],
        note="A second regulated exchange. Where the two exchanges disagree, one of them "
             "is mispriced, and this is the lane that finds out which."),
    "espn_fpi": dict(
        label="ESPN FPI / Matchup Predictor", kind="Statistical model", connected=True,
        site="espn.com", sports=["nfl", "mlb"],
        note="ESPN's own win probability (gameProjection). A pure model with no money "
             "behind it, which makes it the most likely of the four to be beatable."),
    "draftkings": dict(
        label="DraftKings (via ESPN)", kind="Sportsbook", connected=True,
        site="draftkings.com", sports=["nfl", "mlb"],
        note="Closing-ish moneyline, de-vigged to a fair probability. A sportsbook line "
             "is the hardest public number to beat, so this is the ceiling."),
    "covers": dict(
        label="Covers / OddsShark computer picks", kind="Tipster site", connected=True,
        site="covers.com", sports=["nfl", "mlb"],
        note="A published computer pick per game, free and dated. It states a projected "
             "SCORE rather than a probability, so it is backed at the market price with "
             "no edge filter and gets no Brier column — a pick cannot be calibrated."),
    "oddspedia": dict(
        label="Oddspedia community tips", kind="Tipster site", connected=True,
        site="oddspedia.com", sports=["cricket"],
        note="A public tipster community — named accounts with a visible record — "
             "reduced to a majority consensus per match, because its tipsters routinely "
             "take opposite sides of the same game. The only source found that tips the "
             "niche cricket Polymarket lists. Cloudflare-protected, so it comes through "
             "the headless browser. Tips carry no date, so each is resolved to the "
             "soonest fixture between those two sides."),
    "sportsgambler": dict(
        label="SportsGambler", kind="Tipster site", connected=True,
        site="sportsgambler.com", sports=["soccer"],
        note="A named analyst's Main Match Prediction per fixture across 14 leagues. Only "
             "its To Win and Draw calls are scored — about one tip in six; the rest are "
             "over/unders, Asian handicaps and BTTS, which settle a different question. "
             "Its tennis, table-tennis, cricket and boxing pages are not scored: they "
             "restate the bookmaker line as prose, so following them only measures the "
             "favourite."),
    "soccerpredictions": dict(
        label="SoccerPredictions.ai", kind="Tipster site", connected=True,
        site="soccerpredictions.ai", sports=["soccer"],
        note="One published tip per fixture. Only plain Home / Away / Draw calls are "
             "scored; combined tips such as 'Home & Over 2.5' are a different bet and are "
             "dropped rather than read as a result pick."),
    "tennisexplorer": dict(
        label="Tennis Explorer", kind="Tipster site", connected=False,
        site="tennisexplorer.com", sports=["tennis"],
        note="Parser written and kept, but the match page carries a price on only a "
             "handful of rows — most cells are empty. Connecting it would have produced "
             "an almost-always-zero column indistinguishable from a broken feed."),
    "pickwatch": dict(
        label="NFL Pickwatch (expert consensus)", kind="Tipster site", connected=False,
        site="nflpickwatch.com", sports=["nfl"],
        note="Expert consensus is rendered client-side and the useful views sit behind a "
             "paid trial, so there is nothing a plain fetch can read."),
    "forebet": dict(
        label="Forebet", kind="Tipster site", connected=False,
        site="forebet.com", sports=["nfl", "cricket", "tennis"],
        note="Cloudflare returns 403 to any non-browser request, including from GitHub's "
             "runners. Reachable only through a headless browser, which this pipeline "
             "deliberately does not run."),
    "scores24": dict(
        label="Scores24 (editorial tips)", kind="Tipster site", connected=True,
        site="scores24.live", sports=["soccer", "tennis", "nfl", "mlb"],
        note="Named human tipsters publishing a written call per match. Cloudflare 403s "
             "every plain request, so this is the one source fetched through a real "
             "headless browser. Only its MATCH-WINNER tips are scored — its totals and "
             "handicap tips settle on a different question than the market they would "
             "be booked against."),
    "oddsapi": dict(
        label="The Odds API (bookmaker consensus)", kind="Sportsbook consensus",
        connected=False, site="the-odds-api.com",
        sports=["tennis", "boxing", "nfl", "mlb", "cricket"],
        note="Needs ODDS_API_KEY in repo secrets. Adds real bookmaker prices for the four "
             "sports where DraftKings-via-ESPN does not reach. Wired but dormant."),
}


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def _get(url, tries=3, timeout=20):
    """GET JSON, with a curl fallback.

    urllib is the repo convention and is what works inside GitHub Actions. It is NOT
    what works from this machine: the local sandbox's egress makes ESPN answer urllib
    with 403 while answering curl normally. Falling back rather than switching wholesale
    keeps CI on the path the rest of the repo already uses, and still lets the exact same
    script be run and debugged locally.
    """
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as f:
                return json.load(f)
        # OSError covers URLError, timeouts and a dropped connection; HTTPException covers
        # a truncated body; ValueError covers bad JSON. The narrower list this replaced
        # let http.client.RemoteDisconnected through, and one Polymarket hiccup crashed
        # an entire run — no grading, nothing saved.
        except (OSError, http.client.HTTPException, ValueError) as e:
            last = e
            time.sleep(1.2 * (i + 1))
    try:
        out = subprocess.run(
            ["curl", "-s", "--max-time", str(timeout), "-A", UA, url],
            capture_output=True, text=True, timeout=timeout + 10)
        if out.stdout:
            return json.loads(out.stdout)
    except Exception:
        pass
    raise RuntimeError(f"fetch failed [{type(last).__name__}: {last}] {url}")


# ---------------------------------------------------------------------------
# Name matching
# ---------------------------------------------------------------------------

# Words that carry no identity. "red"/"white" stay IN on purpose: dropping them collapses
# Red Sox and White Sox onto the same key, which is exactly the kind of silent mismatch
# that would book a pick against the wrong game.
STOP = {"the", "fc", "at", "vs", "v", "and", "de", "of", "wins", "win"}

# ---------------------------------------------------------------------------
# Team aliases
# ---------------------------------------------------------------------------

# The three feeds name the same team three different ways: Polymarket says "Giants",
# ESPN says "New York Giants", and Kalshi says "New York G". Token overlap alone scores
# that pair at ZERO, which is why the first live run matched 0 of 31 NFL games and looked
# exactly like a source with nothing to say. City alone is not enough either — Kalshi's
# truncated "Los Angeles R" / "Los Angeles C" are only told apart by the trailing letter,
# so the alias has to carry it.
NICKNAMES = {
    "nfl": {
        "cardinals": ["arizona"], "falcons": ["atlanta"], "ravens": ["baltimore"],
        "bills": ["buffalo"], "panthers": ["carolina"], "bears": ["chicago"],
        "bengals": ["cincinnati"], "browns": ["cleveland"], "cowboys": ["dallas"],
        "broncos": ["denver"], "lions": ["detroit"], "packers": ["green bay"],
        "texans": ["houston"], "colts": ["indianapolis"], "jaguars": ["jacksonville"],
        "chiefs": ["kansas city"], "raiders": ["las vegas"],
        "chargers": ["los angeles c"], "rams": ["los angeles r"],
        "dolphins": ["miami"], "vikings": ["minnesota"], "patriots": ["new england"],
        "saints": ["new orleans"], "giants": ["new york g"], "jets": ["new york j"],
        "eagles": ["philadelphia"], "steelers": ["pittsburgh"],
        "49ers": ["san francisco", "niners"], "seahawks": ["seattle"],
        "buccaneers": ["tampa bay", "bucs"], "titans": ["tennessee"],
        "commanders": ["washington"],
    },
    "mlb": {
        "diamondbacks": ["arizona", "dbacks"], "braves": ["atlanta"],
        "orioles": ["baltimore"], "red sox": ["boston"], "cubs": ["chicago c"],
        "white sox": ["chicago w"], "reds": ["cincinnati"], "guardians": ["cleveland"],
        "rockies": ["colorado"], "tigers": ["detroit"], "astros": ["houston"],
        "royals": ["kansas city"], "angels": ["los angeles a"],
        "dodgers": ["los angeles d"], "marlins": ["miami"], "brewers": ["milwaukee"],
        "twins": ["minnesota"], "mets": ["new york m"], "yankees": ["new york y"],
        "athletics": ["oakland", "sacramento"], "phillies": ["philadelphia"],
        "pirates": ["pittsburgh"], "padres": ["san diego"], "giants": ["san francisco"],
        "mariners": ["seattle"], "cardinals": ["st louis", "saint louis"],
        "rays": ["tampa bay"], "rangers": ["texas"], "blue jays": ["toronto"],
        "nationals": ["washington"],
    },
}


def canon(name, sport):
    """Team name -> canonical nickname, or '' when the sport has no alias table.

    Individual sports (tennis, boxing, table tennis) get '' on purpose: player names
    already agree across feeds, and inventing aliases for them would only create
    false matches between players who share a surname.
    """
    table = NICKNAMES.get(sport)
    if not table:
        return ""
    n = re.sub(r"[^a-z0-9 ]", " ", _fold(name))
    n = " ".join(n.split())
    for nick, alts in table.items():
        if nick in n:
            return nick
        for a in alts:
            if n == a or n.startswith(a + " ") or n == a.replace(" ", ""):
                return nick
    return ""




def _fold(name):
    """Lowercase, accents stripped: "São Paulo" -> "sao paulo", "Köln" -> "koln".

    Without this the non-ASCII letter became a separator — "São" tokenized to a lone
    "s", which the length filter then threw away — so São Paulo could never match
    Sao Paulo, and every Brazilian, German and French club with an accent was at risk.
    """
    s = unicodedata.normalize("NFKD", str(name))
    return s.encode("ascii", "ignore").decode("ascii").lower()


@functools.lru_cache(maxsize=50000)
def tokens(name):
    """Lowercase alphanumeric tokens of a team or player name, minus filler.

    Cached, and frozen so a cached result can never be mutated by a caller. Matching is
    every quote against every fixture, and with soccer on Kalshi that is several
    hundred fixtures a run — recomputing each name thousands of times was the slow part.
    """
    t = re.sub(r"[^a-z0-9 ]", " ", _fold(name))
    return frozenset(w for w in t.split() if w and w not in STOP and len(w) > 1)


def sim(a, b):
    """Overlap of two names, normalised by the SHORTER one.

    Normalising by the shorter side is what lets "Yankees" match "New York Yankees"
    (1.0) while keeping "Boston Red Sox" and "Chicago White Sox" apart (0.33).
    """
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / min(len(ta), len(tb))


# ---------------------------------------------------------------------------
# Soccer names
# ---------------------------------------------------------------------------
#
# Soccer is where name matching is most dangerous, because the failure is not a missed
# match but a WRONG one. Clubs share cities (Manchester United / City, Inter / AC Milan,
# PSG / Paris FC, Hertha / Union Berlin), and the NFL/MLB approach — a substring check on
# a nickname — would book an AC Milan tip against Inter ("milan" is inside "inter
# milan"). Three rules replace it:
#
#   1. aliases are matched on WORD boundaries, longest first, so "Inter Milan" resolves
#      before "Milan" can and "internacional" never matches "inter";
#   2. two known clubs are decisive: same key 1.0, different keys 0;
#   3. unknown names only match when one is a SUBSET of the other ("Newcastle" in
#      "Newcastle United"). If each has a word the other lacks, they are two different
#      clubs — which is exactly the Manchester United / Manchester City case.
SOCCER_ALIASES = {
    # England
    "manchester united": ["manchester united", "man united", "man utd", "manchester utd", "man u"],
    "manchester city": ["manchester city", "man city"],
    "tottenham": ["tottenham hotspur", "tottenham", "spurs"],
    "wolverhampton": ["wolverhampton wanderers", "wolverhampton", "wolves"],
    "brighton": ["brighton and hove albion", "brighton hove albion", "brighton"],
    "west ham": ["west ham united", "west ham"],
    "newcastle": ["newcastle united", "newcastle"],
    "nottingham forest": ["nottingham forest", "nottm forest", "nott m forest"],
    "sheffield united": ["sheffield united", "sheffield utd", "sheff utd"],
    "sheffield wednesday": ["sheffield wednesday", "sheff wed"],
    "leeds": ["leeds united", "leeds"],
    "leicester": ["leicester city", "leicester"],
    "ipswich": ["ipswich town", "ipswich"],
    # Spain
    "athletic bilbao": ["athletic club", "athletic bilbao"],
    "atletico madrid": ["atletico madrid", "atl madrid", "atleti", "atletico"],
    "rayo vallecano": ["rayo vallecano", "vallecano", "rayo"],
    "racing santander": ["racing santander", "racing de santander", "santander"],
    "real sociedad": ["real sociedad", "sociedad"],
    "real betis": ["real betis", "betis"],
    "alaves": ["deportivo alaves", "alaves"],
    "celta vigo": ["celta vigo", "celta"],
    # Germany
    "bayern munich": ["bayern munich", "bayern munchen", "fc bayern", "bayern"],
    "rb leipzig": ["rb leipzig", "rasenballsport leipzig", "leipzig"],
    "eintracht frankfurt": ["eintracht frankfurt", "frankfurt"],
    "werder bremen": ["werder bremen", "bremen", "werder"],
    "monchengladbach": ["borussia monchengladbach", "monchengladbach", "mgladbach",
                        "m gladbach", "gladbach"],
    "koln": ["1 fc koln", "fc koln", "koln", "cologne"],
    "dortmund": ["borussia dortmund", "dortmund", "bvb"],
    "leverkusen": ["bayer leverkusen", "leverkusen"],
    "mainz": ["mainz 05", "fsv mainz", "mainz"],
    "hertha": ["hertha berlin", "hertha bsc", "hertha"],
    "union berlin": ["1 fc union berlin", "union berlin"],
    "hamburg": ["hamburger sv", "hamburg", "hsv"],
    "st pauli": ["fc st pauli", "st pauli", "sankt pauli"],
    "schalke": ["schalke 04", "schalke"],
    # Italy
    "inter": ["inter milan", "internazionale", "inter"],
    "milan": ["ac milan", "milan"],
    "roma": ["as roma", "roma"],
    "lazio": ["ss lazio", "lazio"],
    "napoli": ["ssc napoli", "napoli"],
    "parma": ["parma calcio", "parma"],
    "verona": ["hellas verona", "verona"],
    # France
    "psg": ["paris saint germain", "paris sg", "psg"],
    "paris fc": ["paris fc"],
    "rennes": ["stade rennais", "rennes"],
    "brest": ["stade brest 29", "stade brestois", "stade brest", "brest"],
    "strasbourg": ["strasbourg alsace", "rc strasbourg", "strasbourg"],
    "marseille": ["olympique de marseille", "olympique marseille", "marseille"],
    "lyon": ["olympique lyonnais", "olympique lyon", "lyon"],
    "saint etienne": ["saint etienne", "st etienne"],
    # Netherlands
    "psv": ["psv eindhoven", "psv", "eindhoven"],
    "twente": ["fc twente", "twente", "enschede"],
    "az": ["az alkmaar", "az"],
    "go ahead eagles": ["go ahead eagles", "ga eagles"],
    "nec": ["nec nijmegen", "nijmegen", "nec"],
    "fortuna sittard": ["fortuna sittard", "sittard"],
    "pec zwolle": ["pec zwolle", "zwolle"],
    "sparta rotterdam": ["sparta rotterdam", "sparta"],
    "ado den haag": ["ado den haag", "den haag"],
    # USA / MLS
    "la galaxy": ["los angeles galaxy", "la galaxy", "los angeles g", "galaxy"],
    "lafc": ["los angeles fc", "lafc", "los angeles f"],
    "inter miami": ["inter miami cf", "inter miami"],
    "new york city": ["new york city fc", "nycfc", "new york city"],
    "new york red bulls": ["new york red bulls", "ny red bulls", "red bulls"],
    "st louis city": ["st louis city", "saint louis city", "st louis", "saint louis"],
    "real salt lake": ["real salt lake", "salt lake"],
    "cf montreal": ["cf montreal", "montreal"],
    "new england": ["new england revolution", "new england"],
    "chicago fire": ["chicago fire", "chicago"],
    "sporting kc": ["sporting kansas city", "sporting kc"],
    # Mexico
    "club america": ["club america", "america"],
    "pumas": ["pumas unam", "unam", "pumas"],
    "tijuana": ["tijuana de caliente", "club tijuana", "tijuana", "xolos"],
    "atletico san luis": ["atletico san luis", "san luis"],
    "guadalajara": ["chivas guadalajara", "guadalajara", "chivas"],
    "santos laguna": ["santos laguna"],
    # Brazil / South America
    "athletico paranaense": ["athletico paranaense", "atletico paranaense", "paranaense"],
    "atletico mineiro": ["atletico mineiro", "atletico mg"],
    "america mineiro": ["america mineiro", "america mg"],
    "vasco": ["vasco da gama", "vasco"],
    "santos": ["santos fc", "santos"],
    "independiente santa fe": ["independiente santa fe", "independ santa fe"],
}

# Words that name no club on their own. A bare "United" or "City" matching any club
# with that word would be the subset rule's one blind spot.
SOCCER_FILLER = {"fc", "cf", "afc", "sc", "ac", "club", "cd", "ud", "sd", "calcio", "sv",
                 "as", "ss", "ssc", "rc", "ogc", "de", "la", "le", "el", "the"}
SOCCER_GENERIC = {"united", "city", "town", "real", "athletic", "sporting", "rovers",
                  "wanderers", "county", "albion"}


def _phrase(name):
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", _fold(name)).split())


_SOCCER_INDEX = sorted(((_phrase(v), key) for key, vs in SOCCER_ALIASES.items() for v in vs),
                       key=lambda kv: -len(kv[0]))


@functools.lru_cache(maxsize=50000)
def soccer_canon(name):
    """Known club -> canonical key, matched on word boundaries, longest alias first."""
    n = f" {_phrase(name)} "
    for variant, key in _SOCCER_INDEX:
        if f" {variant} " in n:
            return key
    return ""


def soccer_sim(a, b):
    """Two unknown club names: a match only when one is a subset of the other."""
    ta, tb = tokens(a) - SOCCER_FILLER, tokens(b) - SOCCER_FILLER
    if not ta or not tb:
        return 0.0
    if (ta - tb) and (tb - ta):
        return 0.0
    if min((ta, tb), key=len) <= SOCCER_GENERIC:
        return 0.0
    return 1.0


def _score(a, b, sport):
    """How strongly do these two names refer to the same competitor?

    A canonical-nickname hit is decisive (1.0); anything else falls back to token
    overlap. Two DIFFERENT known teams score 0 outright — without that, "Los Angeles
    Rams" and "Los Angeles Chargers" share a city and would otherwise score 0.67.
    """
    if sport == "soccer":
        ca, cb = soccer_canon(a), soccer_canon(b)
        if ca and cb:
            return 1.0 if ca == cb else 0.0
        return soccer_sim(a, b)
    ca, cb = canon(a, sport), canon(b, sport)
    if ca and cb:
        return 1.0 if ca == cb else 0.0
    return sim(a, b)


def pair_match(a1, a2, b1, b2, sport=None, floor=0.5):
    """Match fixture (a1,a2) against fixture (b1,b2), either way round.

    Returns (score, flipped) or (0, False). Both sides must clear `floor` independently,
    so one strong match cannot drag a wrong opponent along with it. Orientation is not a
    detail: a flipped probability is the exact opposite prediction.
    """
    sa = min(_score(a1, b1, sport), _score(a2, b2, sport))
    sf = min(_score(a1, b2, sport), _score(a2, b1, sport))
    if sa >= floor and sa >= sf:
        return (_score(a1, b1, sport) + _score(a2, b2, sport)) / 2, False
    if sf >= floor:
        return (_score(a1, b2, sport) + _score(a2, b1, sport)) / 2, True
    return 0.0, False


def day(ts):
    """ISO-ish timestamp -> YYYY-MM-DD, or '' if unparseable."""
    if not ts:
        return ""
    s = str(ts).replace("Z", "+00:00").replace(" ", "T", 1)
    try:
        return datetime.fromisoformat(s[:25]).astimezone(timezone.utc).strftime("%Y-%m-%d")
    except ValueError:
        return str(ts)[:10]


def american_to_prob(ml):
    """American moneyline -> implied probability (still carrying vig)."""
    try:
        ml = float(ml)
    except (TypeError, ValueError):
        return None
    if ml == 0:
        return None
    return (-ml) / ((-ml) + 100) if ml < 0 else 100 / (ml + 100)


def devig(p_a, p_b):
    """Strip the bookmaker's margin by normalising the two implied probabilities.

    Without this a book's pair sums to ~1.05 and every one of its quotes looks like an
    edge over a prediction-market price that sums to 1.00 — the book would top the
    leaderboard purely on its own vig.
    """
    if p_a is None or p_b is None:
        return None, None
    tot = p_a + p_b
    if tot <= 0:
        return None, None
    return p_a / tot, p_b / tot


# ---------------------------------------------------------------------------
# Polymarket — universe, prices, and settlement oracle
# ---------------------------------------------------------------------------

GAMMA = "https://gamma-api.polymarket.com"


def _pm_json(v, default):
    """gamma returns outcomes/prices as JSON-encoded STRINGS, not arrays."""
    if isinstance(v, list):
        return v
    try:
        return json.loads(v) if v else default
    except (json.JSONDecodeError, TypeError):
        return default


# Words that mark a market as a PROP rather than the head-to-head result. Props are the
# main way a universe like this quietly rots: "Reds vs. Dodgers" is the moneyline, but so
# is the label on "first inning run scored", and a source's win probability booked against
# an inning prop is scored on a question it never answered.
PROP_WORDS = ("o/u", "over", "under", "handicap", "spread", "total", "margin",
              "inning", "quarter", "half", "set", "first to", "correct score",
              "points", "runs", "goals", "aces", "winner", "series")


def _is_head_to_head(question, side_a, side_b):
    """True only for the market that pays out on the RESULT of the contest."""
    q = str(question).lower()
    # Word-boundary, not substring: a plain `"over" in q` also rejects Vancouver, Dover
    # and Hanover, silently deleting real matchups from the universe.
    if any(re.search(r"\b" + re.escape(w.strip()) + r"\b", q) for w in PROP_WORDS):
        return False
    if {str(side_a).strip().lower(), str(side_b).strip().lower()} & {"over", "under", "yes", "no"}:
        return False
    # Both competitors must actually be named in the question. This is what rejects
    # "Set Handicap: Samsonova (-1.5) vs Siegemund (+1.5)"-style relabelling.
    qt = tokens(q)
    return tokens(side_a) <= qt and tokens(side_b) <= qt


# Per sport, per run. The ledger is committed to git four times a day, so unbounded
# intake is a real cost: uncapped, tennis alone logs ~200 contests a day and the file
# reaches double-digit megabytes within months. Capping by VOLUME rather than by an
# arbitrary slice also improves the sample — a market with $12 of volume is a quoted
# price nobody has tested, and it is the deep books that make a source's error visible.
MAX_PER_SPORT = 40


def fetch_polymarket(sport, horizon_days=4, page=100, max_pages=8, cap=MAX_PER_SPORT,
                     stats=None):
    """Every PRE-MATCH head-to-head market for one sport, one row per contest.

    Three filters carry the integrity of the whole board:

    * paginated. gamma silently caps a page at 100 regardless of the limit asked for, so
      a single call made tennis, cricket and table tennis look EMPTY when each in fact
      has hundreds to thousands of live markets. That near-miss is why the page prints
      per-sport market counts: an empty sport must be visibly empty, not absent.
    * strictly future start. A market that is already in play prices the score, not the
      matchup, so a quote logged against it is not a prediction.
    * one row per contest, highest volume wins. A single game carries dozens of markets
      and only one of them is the moneyline.
    """
    tag = PM_TAGS[sport]
    events = []
    for off in range(0, page * max_pages, page):
        try:
            batch = _get(f"{GAMMA}/events?closed=false&limit={page}&offset={off}&tag_slug={tag}")
        except RuntimeError:
            break
        if not isinstance(batch, list) or not batch:
            break
        events += batch
        if len(batch) < page:
            break

    now = datetime.now(timezone.utc)
    horizon = now + timedelta(days=horizon_days)
    best = {}
    for ev in events:
        for m in ev.get("markets") or []:
            if m.get("closed") or not m.get("acceptingOrders"):
                continue
            outs = _pm_json(m.get("outcomes"), [])
            pxs = _pm_json(m.get("outcomePrices"), [])
            if len(outs) != 2 or len(pxs) != 2:
                continue
            if not _is_head_to_head(m.get("question") or ev.get("title"), outs[0], outs[1]):
                continue
            try:
                pa, pb = float(pxs[0]), float(pxs[1])
            except (TypeError, ValueError):
                continue
            if pa <= 0 or pb <= 0 or abs(pa + pb - 1) > 0.08:
                continue
            # A book pinned at exactly 0.50/0.50 has never traded. Its "probability" is a
            # placeholder, not a crowd view, and table tennis is full of them.
            untraded = (pa == 0.5 and pb == 0.5)

            when = m.get("gameStartTime") or ev.get("startDate")
            try:
                wdt = datetime.fromisoformat(
                    str(when).replace("Z", "+00:00").replace(" ", "T", 1)[:25])
                if wdt.tzinfo is None:
                    wdt = wdt.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                continue
            if not (now - timedelta(minutes=5) <= wdt <= horizon):
                continue

            vol = float(m.get("volumeNum") or 0)
            key = (frozenset({frozenset(tokens(outs[0])), frozenset(tokens(outs[1]))}),
                   wdt.strftime("%Y-%m-%d"))
            row = dict(
                sport=sport,
                market_id=str(m.get("id")),
                label=f"{outs[0]} vs {outs[1]}",
                side_a=str(outs[0]), side_b=str(outs[1]),
                price_a=pa, price_b=pb,
                start=wdt.isoformat(), date=wdt.strftime("%Y-%m-%d"),
                volume=vol, untraded=untraded,
                url=f"https://polymarket.com/event/{ev.get('slug')}",
            )
            if key not in best or vol > best[key]["volume"]:
                best[key] = row

    # Deepest books first, then cut. Placeholder 50/50 books sort to the bottom on
    # volume, so the cap drops those before it drops anything real.
    rows = sorted(best.values(), key=lambda r: (-r["volume"], r["start"]))

    # Pre-cap totals, reported separately. The coverage panel exists to answer whether
    # Polymarket really carries these six sports, and answering that with a number the
    # intake cap had already truncated to 40 would be answering a different question.
    if stats is not None:
        stats["listed"] = len(rows)
        stats["priced"] = sum(1 for r in rows if not r["untraded"])

    return rows[:cap] if cap else rows


def resolve_polymarket(market_id):
    """Settlement oracle: has this market resolved, and to which side?

    Returns 'a', 'b', 'void', or None if still open. Polymarket writes the resolution
    back into outcomePrices as a hard 1/0, which is why one feed can settle all six
    sports — ESPN has no boxing or table tennis at all.
    """
    try:
        m = _get(f"{GAMMA}/markets/{market_id}", tries=2)
    except RuntimeError:
        return None
    if not isinstance(m, dict) or not m.get("closed"):
        return None
    pxs = _pm_json(m.get("outcomePrices"), [])
    if len(pxs) != 2:
        return None
    try:
        pa, pb = float(pxs[0]), float(pxs[1])
    except (TypeError, ValueError):
        return None
    if pa >= 0.99 and pb <= 0.01:
        return "a"
    if pb >= 0.99 and pa <= 0.01:
        return "b"
    # Closed without a clean 1/0 — cancelled, or UMA still disputing it. Refund, never
    # guess: booking a coin-flip here would quietly invent P/L.
    return "void"


# ---------------------------------------------------------------------------
# Challenger sources
# ---------------------------------------------------------------------------

MONTHS = {m: i + 1 for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"])}


def kalshi_date(ticker, fallback=None):
    """Game date out of a Kalshi ticker: KXNFLGAME-26SEP21NYGLAR -> 2026-09-21.

    The ticker is the only trustworthy date on the record. `close_time` sits roughly two
    days AFTER kickoff (settlement window, not start), and using it shifted every NFL
    game a week forward — which killed all 31 matches against Polymarket while looking
    like Kalshi simply had no NFL book.
    """
    m = re.search(r"-(\d{2})([A-Z]{3})(\d{2})", str(ticker))
    if m:
        yy, mon, dd = m.groups()
        if mon in MONTHS:
            return f"20{yy}-{MONTHS[mon]:02d}-{int(dd):02d}"
    return day(fallback)


def fetch_kalshi(sport):
    """Kalshi's open markets for one sport, re-paired into two-sided contests.

    Kalshi lists one market PER SIDE ("New York G wins"), so the two legs of a game have
    to be rejoined through the event ticker before they mean anything. The book is also
    cursor-paginated: without following the cursor only the first page arrives, which is
    mostly NEXT week's games and misses the ones actually about to be played.
    """
    series = KALSHI_SERIES.get(sport)
    if not series:
        return []

    markets, cursor = [], ""
    for _ in range(10):
        url = ("https://api.elections.kalshi.com/trade-api/v2/markets"
               f"?limit=200&status=open&series_ticker={series}")
        if cursor:
            url += f"&cursor={cursor}"
        try:
            d = _get(url, tries=2)
        except RuntimeError:
            break
        batch = d.get("markets") or []
        markets += batch
        cursor = d.get("cursor") or ""
        if not cursor or not batch:
            break

    by_event = {}
    for m in markets:
        by_event.setdefault(m.get("event_ticker"), []).append(m)

    out = []
    for ticker, legs in by_event.items():
        if len(legs) != 2:
            continue
        a, b = legs

        def mid(m):
            """Mid of the book, in probability. Falls back to the last trade."""
            for lo, hi in (("yes_bid_dollars", "yes_ask_dollars"), ("yes_bid", "yes_ask")):
                try:
                    x, y = float(m.get(lo)), float(m.get(hi))
                    if x > 0 and y > 0:
                        v = (x + y) / 2
                        return v if v <= 1 else v / 100
                except (TypeError, ValueError):
                    continue
            for k in ("last_price_dollars", "last_price"):
                try:
                    v = float(m.get(k))
                    if v > 0:
                        return v if v <= 1 else v / 100
                except (TypeError, ValueError):
                    continue
            return None

        pa, pb = mid(a), mid(b)
        if pa is None and pb is None:
            continue
        if pa is None:
            pa = 1 - pb
        elif pb is None:
            pb = 1 - pa
        pa, pb = devig(pa, pb)
        if pa is None:
            continue
        out.append(dict(a=str(a.get("yes_sub_title") or a.get("title") or ""),
                        b=str(b.get("yes_sub_title") or b.get("title") or ""),
                        prob_a=pa, date=kalshi_date(ticker, a.get("close_time"))))
    return out


# site.api.espn.com has 403-ed every request since 2026-08-08 — this machine AND the
# GitHub runner, any user-agent. It is a server-side block, not a header problem, and
# streaks_fetch.py hit the same wall and moved to this host. site.web.api serves the
# identical payload. sports.core.api (predictor/odds) is unaffected.
ESPN_SITE = "https://site.web.api.espn.com"


def _espn_events(sport, days=4):
    """ESPN scoreboard events across a small date window."""
    site, _ = ESPN_PATHS[sport]
    seen, evs = set(), []
    base = datetime.now(timezone.utc)
    for i in range(days):
        d = (base + timedelta(days=i)).strftime("%Y%m%d")
        try:
            sb = _get(f"{ESPN_SITE}/apis/site/v2/sports/{site}/scoreboard?dates={d}",
                      tries=2)
        except RuntimeError as e:
            if not evs:
                print(f"  ! espn scoreboard {sport} {d}: {str(e)[:90]}")
            continue
        for ev in sb.get("events") or []:
            if ev.get("id") in seen:
                continue
            seen.add(ev.get("id"))
            evs.append(ev)
    return evs


def _espn_sides(ev):
    """(home_name, away_name, competition_id) for an ESPN event, or None."""
    comps = ev.get("competitions") or []
    if not comps:
        return None
    c = comps[0]
    home = away = None
    for t in c.get("competitors") or []:
        nm = (t.get("team") or {}).get("displayName")
        if t.get("homeAway") == "home":
            home = nm
        elif t.get("homeAway") == "away":
            away = nm
    if not home or not away:
        return None
    return home, away, c.get("id")


def fetch_espn_fpi(sport):
    """ESPN's own win probability (gameProjection) per upcoming game."""
    if sport not in ESPN_PATHS:
        return []
    _, core = ESPN_PATHS[sport]
    out, evs, failed = [], _espn_events(sport), 0
    for ev in evs:
        sides = _espn_sides(ev)
        if not sides:
            continue
        home, away, cid = sides
        try:
            p = _get(f"https://sports.core.api.espn.com/v2/sports/{core}"
                     f"/events/{ev['id']}/competitions/{cid}/predictor", tries=2, timeout=20)
        except RuntimeError as e:
            failed += 1
            if failed == 1:
                print(f"  ! espn_fpi/{sport} predictor unreachable: {str(e)[:90]}")
            continue
        stats = {s.get("name"): s.get("displayValue")
                 for s in (p.get("homeTeam") or {}).get("statistics") or []}
        try:
            proj = float(str(stats.get("gameProjection")).strip()) / 100.0
        except (TypeError, ValueError):
            continue
        if not 0 < proj < 1:
            continue
        out.append(dict(a=home, b=away, prob_a=proj, date=day(ev.get("date"))))
        time.sleep(0.12)
    if evs and not out:
        print(f"  ! espn_fpi/{sport}: {len(evs)} games seen, 0 predictions "
              f"({failed} predictor calls failed)")
    return out


def fetch_draftkings(sport):
    """DraftKings moneyline via ESPN's odds feed, de-vigged."""
    if sport not in ESPN_PATHS:
        return []
    _, core = ESPN_PATHS[sport]
    out, evs, failed = [], _espn_events(sport), 0
    for ev in evs:
        sides = _espn_sides(ev)
        if not sides:
            continue
        home, away, cid = sides
        try:
            o = _get(f"https://sports.core.api.espn.com/v2/sports/{core}"
                     f"/events/{ev['id']}/competitions/{cid}/odds", tries=2, timeout=20)
        except RuntimeError as e:
            failed += 1
            if failed == 1:
                print(f"  ! draftkings/{sport} odds unreachable: {str(e)[:90]}")
            continue
        items = o.get("items") or []
        if not items:
            continue
        it = items[0]
        ph = american_to_prob((it.get("homeTeamOdds") or {}).get("moneyLine"))
        pa = american_to_prob((it.get("awayTeamOdds") or {}).get("moneyLine"))
        ph, _pa = devig(ph, pa)
        if ph is None:
            continue
        out.append(dict(a=home, b=away, prob_a=ph, date=day(ev.get("date"))))
        time.sleep(0.12)
    if evs and not out:
        print(f"  ! draftkings/{sport}: {len(evs)} games seen, 0 lines "
              f"({failed} odds calls failed)")
    return out



# ---------------------------------------------------------------------------
# Tipster sites
# ---------------------------------------------------------------------------
#
# A tipster states a PICK, not a probability. That is scoreable — back the named side at
# the market price, flat stake, and the ROI is as real as anyone else's — but it costs
# two things, and the board says so rather than hiding it: a bare pick gets no Brier
# score (there is no number to be calibrated), and no edge filter (a pick carries no
# claim about how big the disagreement is), so every pick inside the price band is
# backed. That makes a tipster's turnover much higher than a model's, which is exactly
# how tipsters are actually followed.

def _get_html(url, tries=2, timeout=30):
    """GET a page as text. Same urllib-then-curl fallback as the JSON fetcher."""
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.9",
            })
            with urllib.request.urlopen(req, timeout=timeout) as f:
                return f.read().decode("utf-8", "replace")
        except Exception as e:
            last = e
            time.sleep(1.0 * (i + 1))
    try:
        out = subprocess.run(["curl", "-sL", "--max-time", str(timeout), "-A", UA, url],
                             capture_output=True, text=True, timeout=timeout + 10)
        if out.stdout:
            return out.stdout
    except Exception:
        pass
    raise RuntimeError(f"html fetch failed [{type(last).__name__}: {last}] {url}")


def _text(h):
    """HTML -> collapsed visible text."""
    h = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", h)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", h)))


COVERS_URL = {"nfl": "https://www.covers.com/picks/nfl", "mlb": "https://www.covers.com/picks/mlb"}

# "Predicted Score  SF SF 21.62 @ 28.09 LA ... 49ers vs Rams ·"
# The projected scores come first with team ABBREVIATIONS, then the same matchup is
# repeated with full nicknames. Both are captured and the nicknames are what get matched:
# the abbreviations are ambiguous in exactly the place it matters (LA is both the Rams
# and the Chargers), and a mis-resolved abbreviation books a pick against another team's
# game rather than failing visibly.
COVERS_RE = re.compile(
    r"Predicted Score\s+\S+\s+\S+\s+(\d+\.\d+)\s*@?\s*\S*\s*(\d+\.\d+)\s+\S+"
    r".{0,140}?([A-Za-z0-9 .&'-]{3,28}?)\s+vs\s+([A-Za-z0-9 .&'-]{3,28}?)\s*[\u00b7]")


def fetch_covers(sport):
    """Covers / OddsShark computer picks — a projected score per game, turned into a pick."""
    url = COVERS_URL.get(sport)
    if not url:
        return []
    try:
        txt = _text(_get_html(url))
    except RuntimeError as e:
        print(f"  ! covers/{sport}: {str(e)[:80]}")
        return []

    out = []
    for sa, sb, na, nb in COVERS_RE.findall(txt):
        try:
            sa, sb = float(sa), float(sb)
        except ValueError:
            continue
        if sa == sb:
            continue                      # a dead-level projection is not a pick
        a, b = na.strip(), nb.strip()
        # The nickname capture can pick up the trailing abbreviation of the block before
        # it ("LA 49ers"). canon() resolves that correctly, but trim it anyway so the
        # label the board prints is the team's actual name.
        a = re.sub(r"^[A-Z]{2,3}\s+(?=[A-Z0-9])", "", a)
        if len(a) < 2 or len(b) < 2:
            continue
        out.append(dict(a=a, b=b, pick="a" if sa > sb else "b", date=None,
                        detail=f"projected {sa:.1f}-{sb:.1f}"))
    return out


TENNIS_EXPLORER = "https://www.tennisexplorer.com/matches/"


def fetch_tennisexplorer(sport):
    """Tennis Explorer's per-match win probabilities.

    Its match table prints each player's forecast as a percentage pair. Anything that
    does not parse into a clean complementary pair is dropped rather than guessed.
    """
    if sport != "tennis":
        return []
    try:
        h = _get_html(TENNIS_EXPLORER)
    except RuntimeError as e:
        print(f"  ! tennisexplorer: {str(e)[:80]}")
        return []

    out = []
    # Rows pair up: the first row is player one, the row after it is the opponent.
    rows = re.findall(r"(?is)<tr[^>]*>(.*?)</tr>", h)
    pending = None
    for r in rows:
        name = re.search(r'(?is)<td class="t-name"[^>]*>\s*(?:<a[^>]*>)?([^<]{3,40})', r)
        prob = re.search(r'(?is)<td class="[^"]*course[^"]*"[^>]*>\s*([\d.]+)\s*</td>', r)
        if not name:
            continue
        nm = name.group(1).strip()
        pr = None
        if prob:
            try:
                pr = float(prob.group(1))
            except ValueError:
                pr = None
        if pending is None:
            pending = (nm, pr)
            continue
        a, pa = pending
        pending = None
        if pa and pr and pa > 1 and pr > 1:
            # Two decimal odds -> de-vigged probabilities.
            ia, ib = 1.0 / pa, 1.0 / pr
            ia, ib = devig(ia, ib)
            if ia:
                out.append(dict(a=a, b=nm, prob_a=ia, date=None))
    return out




# ---------------------------------------------------------------------------
# Kalshi as a VENUE — soccer, and whatever Polymarket does not list
# ---------------------------------------------------------------------------
#
# Polymarket prices and settles six of the seven sports. Where it cannot, Kalshi does the
# same job: all of soccer (Polymarket lists one or two soccer MATCHES a day, in leagues no
# tipster covers, against hundreds of futures) and any individual fight, match or game
# Polymarket is missing. Kalshi lists one yes/no market per outcome — each team, plus a
# Tie in soccer — and finalizes exactly one of them "yes".
KALSHI_API = "https://api.elections.kalshi.com/trade-api/v2/markets"

KALSHI_VENUE_SERIES = {
    "soccer": [
        # top flights tipsters cover most
        "KXEPLGAME", "KXLALIGAGAME", "KXBUNDESLIGAGAME", "KXSERIEAGAME", "KXLIGUE1GAME",
        "KXEREDIVISIEGAME", "KXLIGAPORTUGALGAME", "KXSCOTTISHPREMGAME", "KXBELGIANPLGAME",
        "KXSUPERLIGGAME", "KXSWISSLEAGUEGAME", "KXSLGREECEGAME", "KXDENSUPERLIGAGAME",
        "KXALLSVENSKANGAME", "KXELITESERIENGAME", "KXCZEFLGAME", "KXSRBSLGAME",
        "KXSVNPLGAME", "KXISRPLGAME", "KXSAUDIPLGAME", "KXUAEPLGAME", "KXEGYPLGAME",
        # second tiers
        "KXEFLCHAMPIONSHIPGAME", "KXEFLL1GAME", "KXBUNDESLIGA2GAME", "KXLIGUE2GAME",
        "KXLALIGA2GAME", "KXCZEFNLGAME", "KXSVK2LGAME", "KXISRNLGAME",
        # Americas
        "KXMLSGAME", "KXUSLGAME", "KXCANPLGAME", "KXLIGAMXGAME", "KXLIGAEXPGAME",
        "KXBRASILEIROGAME", "KXBRASILEIROBGAME", "KXBRASILEIROCGAME", "KXCHLLDPGAME",
        "KXPERLIGA1GAME", "KXURYPDGAME", "KXECULPGAME", "KXAPFDDHGAME",
        # Asia
        "KXJLEAGUEGAME", "KXKLEAGUEGAME", "KXK2LEAGUEGAME", "KXCHNSLGAME", "KXCHNL1GAME",
        "KXTHAIL1GAME", "KXMYSLGAME", "KXIDNSLGAME", "KXVLEAGUE1GAME", "KXSGPPLGAME",
        # smaller leagues
        "KXLVAVIRGAME", "KXFROPLGAME",
        # continental and domestic cups
        "KXUCLGAME", "KXUELGAME", "KXCONMEBOLSUDGAME", "KXCONMEBOLLIBGAME",
        "KXCONCACAFCCUPGAME", "KXAFCCLGAME", "KXEFLCUPGAME", "KXFACUPGAME",
        "KXCOPADELREYGAME", "KXCOPADOBRASILGAME", "KXSCOCUPGAME", "KXSVKCUPGAME",
        "KXUSOPENCUPGAME",
    ],
    "tennis": ["KXATPMATCH", "KXATPCHALLENGERMATCH", "KXWTAMATCH"],
    "table_tennis": ["KXTABLETENNIS", "KXTTMATCH", "KXTTELITEGAME", "KXWTTMATCH"],
    "boxing": ["KXBOXING"],
    "cricket": ["KXCPLMATCH", "KXT20MATCH", "KXCRICKETT20IMATCH", "KXCRICKETODIMATCH"],
    "nfl": ["KXNFLGAME"],
    "mlb": ["KXMLBGAME"],
}

# A tip is priced at the YES ASK — what backing it would actually cost — and only where
# the book is tight. Kalshi carries untouched books quoted 0.02 bid / 0.81 ask; a mid of
# 0.415 on one of those is a number nobody could trade at, and T20 cricket is full of
# them.
# De-duplicated on purpose. A series listed twice would load every event's markets twice,
# the event would then appear to have four teams, and it would be skipped without a word.
KALSHI_VENUE_SERIES = {k: list(dict.fromkeys(v)) for k, v in KALSHI_VENUE_SERIES.items()}

KALSHI_MAX_SPREAD = 0.10
KALSHI_FINAL = {"finalized", "settled", "determined"}

_kalshi_open_cache = {}


def _kalshi_open(series):
    """Every open market in one Kalshi series, cursor-paginated, cached per run."""
    if series in _kalshi_open_cache:
        return _kalshi_open_cache[series]
    out, cursor = [], ""
    for _ in range(10):
        url = f"{KALSHI_API}?limit=200&status=open&series_ticker={series}"
        if cursor:
            url += f"&cursor={cursor}"
        try:
            d = _get(url, tries=2, timeout=30)
        except RuntimeError:
            break
        batch = d.get("markets") or []
        out += batch
        cursor = d.get("cursor") or ""
        if not cursor or not batch:
            break
    _kalshi_open_cache[series] = out
    return out


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _kalshi_code(m):
    return str(m.get("ticker", "")).rsplit("-", 1)[-1]


def _kalshi_is_tie(m):
    return (_kalshi_code(m).upper() == "TIE"
            or str(m.get("yes_sub_title", "")).strip().lower().endswith("tie"))


def _kalshi_name(m):
    # Some cup series prefix every outcome "Reg Time: " — the market settles on 90
    # minutes. The prefix is not part of the club's name.
    return str(m.get("yes_sub_title") or "").replace("Reg Time:", "").strip()


def kalshi_sides(event_ticker, markets):
    """{market code: 'a' | 'b' | 'draw'} for one Kalshi event.

    Side A is the home team: the team code the event suffix STARTS with once the date —
    and, for MLB and cricket, a four-digit start time — is stripped, so
    KXEPLGAME-26SEP06ARSCFC is Arsenal at home. Codes run two to six characters, so the
    suffix can never be split by length. Fetch and settlement both call this one
    function, which is what guarantees a bet placed on side A is settled against the
    same team it was placed on.
    """
    suffix = str(event_ticker).rsplit("-", 1)[-1]
    body = re.sub(r"^\d{2}[A-Z]{3}\d{2}(\d{4})?", "", suffix)
    out = {_kalshi_code(m): "draw" for m in markets if _kalshi_is_tie(m)}
    teams = [_kalshi_code(m) for m in markets if not _kalshi_is_tie(m)]
    if len(teams) != 2:
        return out
    home = [c for c in teams if body.startswith(c)]
    a = home[0] if len(home) == 1 else sorted(teams)[0]
    b = teams[1] if teams[0] == a else teams[0]
    out[a], out[b] = "a", "b"
    return out


def fetch_kalshi_venue(sport, horizon_days=4, cap=800, stats=None):
    """Kalshi contests for one sport, as universe rows with Kalshi as the venue.

    The cap is generous on purpose. A Kalshi-venue row adds nothing to the ledger by
    itself — no self-quote is logged against it — so a wide universe costs nothing but
    matching time, while a narrow one silently discards every tip on a fixture it cut.
    """
    now = datetime.now(timezone.utc)
    first = now.strftime("%Y-%m-%d")
    last = (now + timedelta(days=horizon_days)).strftime("%Y-%m-%d")
    # Fetched concurrently. Soccer alone is 69 series, and one after another they took
    # nearly five minutes of a run whose CPU time was under two seconds. Six workers stays
    # well inside Kalshi's public read limits.
    series_list = KALSHI_VENUE_SERIES.get(sport) or []
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        fetched = dict(zip(series_list, pool.map(_kalshi_open, series_list)))
    events = {}
    for series in series_list:
        for m in fetched[series]:
            events.setdefault((series, m.get("event_ticker")), []).append(m)

    rows, listed = [], 0
    for (series, et), ms in events.items():
        date = kalshi_date(et)
        if not (first <= date <= last):
            continue
        sides = kalshi_sides(et, ms)
        by_side = {sides[_kalshi_code(m)]: m for m in ms if _kalshi_code(m) in sides}
        if "a" not in by_side or "b" not in by_side:
            continue
        three_way = sport == "soccer"
        if three_way and "draw" not in by_side:
            continue
        listed += 1

        # Kalshi publishes no kickoff time. Expected expiration sits two to three hours
        # after the start, so three hours before it is a deliberately EARLY estimate:
        # logging stops before the real kickoff, never after it.
        try:
            end = datetime.fromisoformat(
                str(ms[0].get("expected_expiration_time")).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            continue
        start = end - timedelta(hours=3)
        if start < now - timedelta(minutes=5):
            continue

        prices, tradeable = {}, {}
        for side, m in by_side.items():
            bid, ask = _num(m.get("yes_bid_dollars")), _num(m.get("yes_ask_dollars"))
            prices[side] = ask
            tradeable[side] = bool(bid is not None and ask is not None and bid > 0
                                   and ask < 1 and ask - bid <= KALSHI_MAX_SPREAD)
        if not prices.get("a") or not prices.get("b"):
            continue

        rows.append(dict(
            sport=sport, venue="kalshi", market_id=et,
            label=f"{_kalshi_name(by_side['a'])} vs {_kalshi_name(by_side['b'])}",
            side_a=_kalshi_name(by_side["a"]), side_b=_kalshi_name(by_side["b"]),
            price_a=prices["a"], price_b=prices["b"],
            price_draw=prices.get("draw") if three_way else None,
            tradeable=tradeable, untraded=not any(tradeable.values()),
            start=start.isoformat(), date=date, volume=0.0,
            url=f"https://kalshi.com/markets/{series.lower()}",
        ))

    rows.sort(key=lambda r: r["start"])
    if stats is not None:
        stats["listed"] = listed
        stats["priced"] = sum(1 for r in rows if not r["untraded"])
    return rows[:cap] if cap else rows


def resolve_kalshi(event_ticker):
    """Settlement oracle for a Kalshi event: 'a', 'b', 'draw', 'void', or None if open.

    The winning side is read through kalshi_sides — the same mapping used when the bet
    was placed — so side A can never quietly change meaning between placing and settling.
    """
    try:
        ms = _get(f"{KALSHI_API}?event_ticker={event_ticker}&limit=20",
                  tries=2, timeout=30).get("markets") or []
    except RuntimeError:
        return None
    if not ms:
        return None
    sides = kalshi_sides(event_ticker, ms)
    yes = [m for m in ms if str(m.get("result")).lower() == "yes"]
    if yes:
        if any(str(m.get("status")).lower() not in KALSHI_FINAL for m in yes):
            return None
        if len(yes) != 1:
            return "void"
        return sides.get(_kalshi_code(yes[0])) or "void"
    if all(str(m.get("status")).lower() in KALSHI_FINAL for m in ms):
        # Everything final and nothing resolved yes: cancelled or voided. Refund it.
        return "void"
    return None


# ---------------------------------------------------------------------------
# Scores24 (behind Cloudflare — needs the headless browser)
# ---------------------------------------------------------------------------

# Every sport this board tracks gets a listing page requested, including the ones that
# turned out to be empty. Scores24 publishes editorial tips per sport, but which sports
# it bothers with moves with the calendar — boxing has nothing on an ordinary Tuesday and
# may well have tips on a fight week. Asking for all six costs one page load each and
# lets the coverage table report an honest zero instead of an omission.
# Verified live: Scores24's cricket, boxing and table-tennis listing pages contain only
# a generic cross-sport rail, no tips of their own. Requesting them cost a page load and
# a Cloudflare challenge each to learn nothing, so they are not requested. Their absence
# is recorded in this source's `sports` list rather than as a nightly empty fetch.
SCORES24_SLUG = {"soccer": "soccer", "tennis": "tennis",
                 "nfl": "american-football", "mlb": "baseball"}
SCORES24_URL = "https://scores24.live/en/predictions/{slug}"


_browser_cache = None


def _browser_pages():
    """Every browser-fetched page, in ONE session, once per process.

    Both Cloudflare-protected sources are scraped together. Two sessions meant two
    browser launches and two sets of challenges for the same wall clock budget, and this
    step is already the slowest thing in the run.
    """
    global _browser_cache
    if _browser_cache is not None:
        return _browser_cache
    import sandbox_browser as B
    # Oddspedia first, and paced. It tolerates roughly one page before it starts serving
    # the interstitial, so whichever of its pages goes last tends to be lost — and its
    # soccer tips are the ones worth protecting, since soccer is where tipsters actually
    # publish. Scores24 is far more tolerant and goes at the back of the queue.
    jobs = ([(ODDSPEDIA_URL.format(slug=s), B.TIPS_JS) for s in ODDSPEDIA_SLUG.values()]
            + [(SCORES24_URL.format(slug=s), B.ROW_JS) for s in SCORES24_SLUG.values()])
    _browser_cache = B.fetch_rows(jobs, pace_ms=6000)
    return _browser_cache


_scores24_cache = None


def _scores24_all():
    """Scrape every sport's listing ONCE per process and cache the result.

    fetch_scores24 is called per sport, but launching a browser six times would pay the
    Cloudflare challenge six times over. One session, one pass, cached.
    """
    global _scores24_cache
    if _scores24_cache is not None:
        return _scores24_cache

    import sandbox_browser as B
    pages = _browser_pages()
    urls = {sport: SCORES24_URL.format(slug=slug) for sport, slug in SCORES24_SLUG.items()}
    _scores24_cache = {}
    for sport, url in urls.items():
        picks = []
        for row in pages.get(url) or []:
            got = B.parse_row(row, SCORES24_SLUG[sport])
            if got:
                picks.append(got)
        _scores24_cache[sport] = picks
    return _scores24_cache


def fetch_scores24(sport):
    """Scores24's published match-winner tips for one sport."""
    if sport not in SCORES24_SLUG:
        return []
    return _scores24_all().get(sport, [])



# ---------------------------------------------------------------------------
# Oddspedia community tips (behind Cloudflare — needs the headless browser)
# ---------------------------------------------------------------------------

# Oddspedia runs a public tipster community: named accounts with a visible tip count and
# running ROI, posting a selection per match. It is the one source found that covers the
# NICHE cricket Polymarket actually lists — European Cricket League sides like Dublin
# Guardians and Belfast Wolves, not just Test nations.
# Cricket only. Oddspedia's community covers the niche cricket nothing else touches, but
# its other sports were empty or duplicated a source already connected — and every extra
# page in one session makes the whole batch more likely to be challenged. Its table
# tennis page was checked repeatedly and carries no tips at all.
# Cricket only, and that is a hard limit rather than a preference: Oddspedia serves
# roughly ONE page per browser session before it starts returning the interstitial —
# reordering and pacing to 6s did not move it. Cricket is the page worth spending that
# single request on, because it is the only source found anywhere that tips the niche
# cricket Polymarket lists. Soccer tips come from Scores24 instead.
ODDSPEDIA_SLUG = {"cricket": "cricket"}
ODDSPEDIA_URL = "https://oddspedia.com/{slug}/tips"

_oddspedia_cache = None


def _oddspedia_all():
    """Scrape every sport's community tips ONCE per process, reduced to a consensus."""
    global _oddspedia_cache
    if _oddspedia_cache is not None:
        return _oddspedia_cache

    import sandbox_browser as B
    pages = _browser_pages()
    urls = {sp: ODDSPEDIA_URL.format(slug=slug) for sp, slug in ODDSPEDIA_SLUG.items()}
    _oddspedia_cache = {}
    for sport, url in urls.items():
        tips = [t for t in (B.parse_tip(r) for r in (pages.get(url) or [])) if t]
        _oddspedia_cache[sport] = consensus(tips)
    return _oddspedia_cache


def consensus(tips):
    """Reduce many individual tips to one call per contest.

    Community tipsters contradict each other constantly — on the live cricket page two
    of them had opposite sides of Belfast Wolves vs Amsterdam Flames. Logging both would
    let "Oddspedia" be simultaneously right and wrong about the same match and guarantee
    a ~0% ROI that measured nothing. So the community votes: the majority side is the
    call, and an even split is no call at all rather than a coin flip.
    """
    groups = {}
    for t in tips:
        key = frozenset({frozenset(tokens(t["a"])), frozenset(tokens(t["b"]))})
        g = groups.setdefault(key, dict(a=t["a"], b=t["b"], a_votes=0, b_votes=0,
                                        tipsters=[]))
        # Orient every tip to the FIRST spelling of the fixture seen, since a later
        # tipster may list the same match the other way round.
        flip = sim(t["a"], g["a"]) < sim(t["a"], g["b"])
        side = t["pick"]
        if flip:
            side = "b" if side == "a" else "a"
        g[f"{side}_votes"] += 1
        if t.get("tipster"):
            g["tipsters"].append(t["tipster"])

    out = []
    for g in groups.values():
        if g["a_votes"] == g["b_votes"]:
            continue
        pick = "a" if g["a_votes"] > g["b_votes"] else "b"
        n = g["a_votes"] + g["b_votes"]
        out.append(dict(a=g["a"], b=g["b"], pick=pick, date=None,
                        detail=f"{max(g['a_votes'], g['b_votes'])}/{n} tipsters"
                               + (f" ({', '.join(g['tipsters'][:3])})" if g["tipsters"] else "")))
    return out


def fetch_oddspedia(sport):
    """Oddspedia's community consensus for one sport."""
    if sport not in ODDSPEDIA_SLUG:
        return []
    return _oddspedia_all().get(sport, [])


# ---------------------------------------------------------------------------
# SportsGambler — football match predictions (plain HTTP)
# ---------------------------------------------------------------------------
#
# Every match page carries one "Main Match Prediction" from a named analyst. Only its
# To Win and Draw calls are scored. That is roughly one tip in six: the rest are
# over/unders, Asian handicaps and both-teams-to-score, which settle a different question
# than the result market they would be priced against.
#
# Football only. Its tennis, table-tennis, cricket and boxing pages were checked and are
# not tips at all — they restate the bookmaker line as prose ("odds of -192 that Jorgic
# lands victory"). Scoring those would only ever measure the favourite.
SPORTSGAMBLER = "https://www.sportsgambler.com"
# Only leagues Kalshi prices: a tip on a fixture with no price cannot be scored.
SPORTSGAMBLER_LEAGUES = [
    "premier-league", "la-liga", "bundesliga", "serie-a", "ligue-1", "eredivisie",
    "primeira-liga", "scottish-premiership", "belgium-first-division-a", "super-lig",
    "swiss-super-league", "greece-super-league-1", "denmark-superliga", "allsvenskan",
    "eliteserien", "championship", "league-one", "2-bundesliga", "la-liga-2", "mls",
    "liga-mx", "brazil-serie-a", "brazil-serie-b", "peru-liga-1", "j1-league",
    "k-league-1", "chinese-super-league", "uefa-champions-league", "europa-league",
    "copa-sudamericana", "copa-libertadores", "afc-champions-league", "efl-cup",
    "fa-cup", "copa-del-rey", "copa-do-brasil",
]
SPORTSGAMBLER_MAX_PAGES = 50        # ~1 request a second; this is the slowest source
SG_MATCH_RE = re.compile(
    r'href="(?:https://www\.sportsgambler\.com)?'
    r'(/betting-tips/football/[a-z0-9\-]+-vs-[a-z0-9\-]+-(\d{4}-\d{2}-\d{2})/)"')

_sportsgambler_cache = None

# Set by the tracker before publishing: {sport: universe rows}. None when run standalone.
UNIVERSE = None
SG_SLUG_RE = re.compile(r"/football/(.+?)-vs-(.+?)-prediction")


def sportsgambler_priced(links, rows):
    """Keep only match pages whose fixture a venue actually prices.

    Every SportsGambler tip costs a page load and a polite second, and most of its 36
    league pages list fixtures Kalshi does not carry. A tip on one of those can never be
    scored, so fetching it is pure waiting. The home and away teams are in the URL slug,
    which is enough to check against the universe before spending the request.

    rows=None means no universe is known (a standalone run) and nothing is filtered.
    """
    if rows is None:
        return links
    out = []
    for path, d in links:
        m = SG_SLUG_RE.search(path)
        if not m:
            continue
        home, away = m.group(1).replace("-", " "), m.group(2).replace("-", " ")
        for r in rows:
            try:
                gap = abs((datetime.strptime(r["date"], "%Y-%m-%d")
                           - datetime.strptime(d, "%Y-%m-%d")).days)
            except (ValueError, TypeError):
                continue
            if gap <= 1 and pair_match(r["side_a"], r["side_b"], home, away,
                                       sport="soccer")[0] > 0:
                out.append((path, d))
                break
    return out


def parse_sportsgambler(page):
    """A match page -> {a, b, pick, detail} from its MAIN prediction, or None."""
    head = re.search(r"<h2>\s*([^<]+?)\s+vs\s+([^<]+?)\s+Predictions\s*</h2>", page)
    tip = re.search(r'Main Match Prediction</span>.*?<h3 class="tip--card__title">(.*?)</h3>',
                    page, re.S)
    if not head or not tip:
        return None
    a = html.unescape(head.group(1)).strip()
    b = html.unescape(head.group(2)).strip()
    text = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", tip.group(1))).split())

    if re.match(r"^Draw\s*@", text, re.I):
        return dict(a=a, b=b, pick="draw", detail=text)
    # "@" straight after "To Win" — so "Arsenal To Win & Over 2.5 @" is rejected too.
    m = re.match(r"^(.+?)\s+To Win\s*@", text, re.I)
    if not m:
        return None
    team = m.group(1).strip()
    sa, sb = _score(team, a, "soccer"), _score(team, b, "soccer")
    if max(sa, sb) < 0.5 or sa == sb:
        return None
    return dict(a=a, b=b, pick="a" if sa > sb else "b", detail=text)


def _sportsgambler_all():
    global _sportsgambler_cache
    if _sportsgambler_cache is not None:
        return _sportsgambler_cache
    now = datetime.now(timezone.utc)
    days = {(now + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(5)}

    links, seen = [], set()
    for league in SPORTSGAMBLER_LEAGUES:
        try:
            index = _get_html(f"{SPORTSGAMBLER}/betting-tips/football/{league}-predictions/")
        except RuntimeError as e:
            print(f"  ! sportsgambler/{league}: {str(e)[:80]}")
            continue
        for path, d in SG_MATCH_RE.findall(index):
            if d in days and path not in seen:
                seen.add(path)
                links.append((path, d))
        time.sleep(0.6)

    rows = (UNIVERSE or {}).get("soccer") if UNIVERSE is not None else None
    priced = sportsgambler_priced(links, rows)
    todo = sorted(priced, key=lambda x: x[1])[:SPORTSGAMBLER_MAX_PAGES]
    print(f"  sportsgambler: {len(links)} fixtures in horizon, {len(priced)} priced, "
          f"fetching {len(todo)}")
    out = []
    for path, d in todo:
        try:
            page = _get_html(SPORTSGAMBLER + path)
        except RuntimeError:
            continue
        got = parse_sportsgambler(page)
        if got:
            got["date"] = d
            out.append(got)
        time.sleep(0.6)
    _sportsgambler_cache = out
    return out


def fetch_sportsgambler(sport):
    return _sportsgambler_all() if sport == "soccer" else []


# ---------------------------------------------------------------------------
# SoccerPredictions.ai (plain HTTP)
# ---------------------------------------------------------------------------
SOCCERPREDICTIONS_URLS = ["https://soccerpredictions.ai/soccer-predictions/",
                          "https://soccerpredictions.ai/"]
SP_LINK_RE = re.compile(
    r'<a href="(https://soccerpredictions\.ai/[^"]+-prediction-date-(\d{4}-\d{2}-\d{2}))"'
    r'[^>]*>(.*?)</a>', re.S)
# Only the plain result calls. "Home & Over 2.5" is a different, combined bet.
SP_PICK = {"home": "a", "away": "b", "draw": "draw"}

_soccerpredictions_cache = None


def parse_soccerpredictions(page):
    """Listing page -> [{a, b, pick, date, detail}] for plain Home / Away / Draw tips.

    Each row is parsed inside its own <a>…</a>, so a malformed row can never borrow the
    team names of the row after it.
    """
    out, seen = [], set()
    for url, d, inner in SP_LINK_RE.findall(page):
        names = re.findall(r'tipscell__text__name">([^<]+)<', inner)
        tip = re.search(r'tipscell--score"><div class="tipscell__text fw-500"><span>([^<]+)</span>',
                        inner)
        if len(names) != 2 or not tip or url in seen:
            continue
        pick = SP_PICK.get(" ".join(tip.group(1).split()).lower())
        if not pick:
            continue
        seen.add(url)
        out.append(dict(a=html.unescape(names[0]).strip(), b=html.unescape(names[1]).strip(),
                        pick=pick, date=d, detail=tip.group(1).strip()))
    return out


def fetch_soccerpredictions(sport):
    global _soccerpredictions_cache
    if sport != "soccer":
        return []
    if _soccerpredictions_cache is None:
        rows, seen = [], set()
        for url in SOCCERPREDICTIONS_URLS:
            try:
                page = _get_html(url, timeout=25)
            except RuntimeError as e:
                print(f"  ! soccerpredictions: {str(e)[:80]}")
                continue
            for r in parse_soccerpredictions(page):
                key = (r["a"], r["b"], r["date"])
                if key not in seen:
                    seen.add(key)
                    rows.append(r)
        _soccerpredictions_cache = rows
    return _soccerpredictions_cache


CHALLENGERS = {
    "kalshi": fetch_kalshi,
    "espn_fpi": fetch_espn_fpi,
    "draftkings": fetch_draftkings,
    "covers": fetch_covers,
    "scores24": fetch_scores24,
    "oddspedia": fetch_oddspedia,
    "sportsgambler": fetch_sportsgambler,
    "soccerpredictions": fetch_soccerpredictions,
}
