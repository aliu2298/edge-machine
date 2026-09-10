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
import html
import re
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

def _get(url, tries=3, timeout=30):
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
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError,
                json.JSONDecodeError) as e:
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
    n = re.sub(r"[^a-z0-9 ]", " ", str(name).lower())
    n = " ".join(n.split())
    for nick, alts in table.items():
        if nick in n:
            return nick
        for a in alts:
            if n == a or n.startswith(a + " ") or n == a.replace(" ", ""):
                return nick
    return ""




def tokens(name):
    """Lowercase alphanumeric tokens of a team or player name, minus filler."""
    t = re.sub(r"[^a-z0-9 ]", " ", str(name).lower())
    return {w for w in t.split() if w and w not in STOP and len(w) > 1}


def sim(a, b):
    """Overlap of two names, normalised by the SHORTER one.

    Normalising by the shorter side is what lets "Yankees" match "New York Yankees"
    (1.0) while keeping "Boston Red Sox" and "Chicago White Sox" apart (0.33).
    """
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / min(len(ta), len(tb))


def _score(a, b, sport):
    """How strongly do these two names refer to the same competitor?

    A canonical-nickname hit is decisive (1.0); anything else falls back to token
    overlap. Two DIFFERENT known teams score 0 outright — without that, "Los Angeles
    Rams" and "Los Angeles Chargers" share a city and would otherwise score 0.67.
    """
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
# Soccer — a second spine, because Polymarket does not price it
# ---------------------------------------------------------------------------
#
# Every other sport here hangs off Polymarket: it supplies the price and it settles
# itself. Soccer cannot, and the numbers are not close. Polymarket lists one or two
# soccer MATCHES a day — Chinese Super League and the Colombian top flight — against
# hundreds of futures markets. There is no Premier League match to bet into. Meanwhile
# soccer is the sport tipsters overwhelmingly publish on: Scores24 alone had 187 soccer
# tips against 30 for tennis. Hanging soccer off Polymarket would have produced a column
# that never matched anything.
#
# So soccer runs on ESPN instead: ESPN lists the fixture, DraftKings prices it through
# ESPN's odds feed, and ESPN's own final score settles it. The rest of this repo already
# depends on that same feed for the streaks board, so it is well-proven ground.
#
# The important structural difference is that soccer is a THREE-way market. A backed side
# loses to the draw as well as to defeat, which is why the draw price is carried and why
# a soccer pick is never treated as the complement of the other side.
# Chosen to overlap with what tipsters actually publish on, not just the marquee
# leagues. The first soccer tips that arrived were for a USL side and a Copa
# Sudamericana tie — outside the original ten, so they matched nothing. A tip against a
# fixture the board never listed is a tip silently thrown away.
SOCCER_LEAGUES = {
    "eng.1": "Premier League", "eng.2": "Championship", "esp.1": "La Liga",
    "ger.1": "Bundesliga", "ita.1": "Serie A", "fra.1": "Ligue 1",
    "ned.1": "Eredivisie", "por.1": "Primeira Liga", "tur.1": "Super Lig",
    "usa.1": "MLS", "usa.usl.1": "USL Championship", "mex.1": "Liga MX",
    "bra.1": "Brasileirao", "arg.1": "Liga Profesional",
    "uefa.champions": "Champions League", "uefa.europa": "Europa League",
    "conmebol.sudamericana": "Copa Sudamericana",
}


def _decimal(ml):
    """American moneyline -> decimal odds (the multiple returned on a winning stake)."""
    try:
        ml = float(ml)
    except (TypeError, ValueError):
        return None
    if ml == 0:
        return None
    return 1 + (ml / 100.0) if ml > 0 else 1 + (100.0 / abs(ml))


def fetch_soccer(horizon_days=4, cap=MAX_PER_SPORT):
    """Upcoming fixtures across the tracked leagues, priced by DraftKings via ESPN.

    Prices are the RAW implied probabilities, vig included, because the payout has to be
    the price a bettor could actually have taken. De-vigging here would quietly inflate
    every settled return.
    """
    now = datetime.now(timezone.utc)
    horizon = now + timedelta(days=horizon_days)
    rows = []
    for slug, league in SOCCER_LEAGUES.items():
        for i in range(horizon_days + 1):
            d = (now + timedelta(days=i)).strftime("%Y%m%d")
            try:
                sb = _get(f"{ESPN_SITE}/apis/site/v2/sports/soccer/{slug}/scoreboard?dates={d}",
                          tries=2, timeout=25)
            except RuntimeError:
                continue
            for ev in sb.get("events") or []:
                sides = _espn_sides(ev)
                if not sides:
                    continue
                home, away, cid = sides
                comp = (ev.get("competitions") or [{}])[0]
                if (comp.get("status") or {}).get("type", {}).get("state") != "pre":
                    continue
                try:
                    start = datetime.fromisoformat(
                        str(ev.get("date")).replace("Z", "+00:00")[:25])
                    if start.tzinfo is None:
                        start = start.replace(tzinfo=timezone.utc)
                except (ValueError, TypeError):
                    continue
                if not (now - timedelta(minutes=5) <= start <= horizon):
                    continue
                try:
                    o = _get(f"https://sports.core.api.espn.com/v2/sports/soccer/leagues/"
                             f"{slug}/events/{ev['id']}/competitions/{cid}/odds",
                             tries=2, timeout=20)
                except RuntimeError:
                    continue

                dh = da = dd = None
                for it in o.get("items") or []:
                    dh = dh or _decimal((it.get("homeTeamOdds") or {}).get("moneyLine"))
                    da = da or _decimal((it.get("awayTeamOdds") or {}).get("moneyLine"))
                    draw = it.get("drawOdds")
                    dd = dd or _decimal(draw.get("moneyLine") if isinstance(draw, dict) else draw)
                if not dh or not da:
                    continue

                rows.append(dict(
                    sport="soccer", venue="espn",
                    market_id=f"espn:{slug}:{ev['id']}",
                    label=f"{home} vs {away}", side_a=home, side_b=away,
                    price_a=1.0 / dh, price_b=1.0 / da,
                    price_draw=(1.0 / dd) if dd else None,
                    start=start.isoformat(), date=start.strftime("%Y-%m-%d"),
                    volume=0.0, untraded=False, league=league,
                    url=f"https://www.espn.com/soccer/match/_/gameId/{ev['id']}",
                ))
                time.sleep(0.1)

    rows.sort(key=lambda r: r["start"])
    return rows[:cap] if cap else rows


def resolve_soccer(market_id):
    """Settle a soccer fixture from ESPN's final score.

    Returns 'a' (home win), 'b' (away win), 'draw', or None while unfinished. A backed
    side loses to the draw, so the draw is a real third outcome and never a void.
    """
    try:
        _, slug, eid = market_id.split(":", 2)
    except ValueError:
        return None
    try:
        sb = _get(f"{ESPN_SITE}/apis/site/v2/sports/soccer/{slug}/scoreboard?event={eid}",
                  tries=2, timeout=25)
    except RuntimeError:
        return None
    for ev in sb.get("events") or []:
        if str(ev.get("id")) != str(eid):
            continue
        comp = (ev.get("competitions") or [{}])[0]
        if not (comp.get("status") or {}).get("type", {}).get("completed"):
            return None
        hs = as_ = None
        for t in comp.get("competitors") or []:
            try:
                sc = int(t.get("score"))
            except (TypeError, ValueError):
                return None
            if t.get("homeAway") == "home":
                hs = sc
            else:
                as_ = sc
        if hs is None or as_ is None:
            return None
        return "a" if hs > as_ else ("b" if as_ > hs else "draw")
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


CHALLENGERS = {
    "kalshi": fetch_kalshi,
    "espn_fpi": fetch_espn_fpi,
    "draftkings": fetch_draftkings,
    "covers": fetch_covers,
    "scores24": fetch_scores24,
    "oddspedia": fetch_oddspedia,
}
