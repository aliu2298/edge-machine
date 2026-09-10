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
    "tennis": "tennis", "table_tennis": "table-tennis", "boxing": "boxing",
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
        site="polymarket.com", sports=list(SPORTS),
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
        label="Scores24", kind="Tipster site", connected=False,
        site="scores24.live", sports=["tennis", "table_tennis", "cricket", "boxing"],
        note="The one candidate that covers all four thin sports, and the one that 403s "
             "hardest. Still the best target if this list is ever extended."),
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
    raise RuntimeError(f"fetch failed: {url} ({last})")


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


def _espn_events(sport, days=4):
    """ESPN scoreboard events across a small date window."""
    site, _ = ESPN_PATHS[sport]
    seen, evs = set(), []
    base = datetime.now(timezone.utc)
    for i in range(days):
        d = (base + timedelta(days=i)).strftime("%Y%m%d")
        try:
            sb = _get(f"https://site.api.espn.com/apis/site/v2/sports/{site}/scoreboard?dates={d}",
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
    raise RuntimeError(f"html fetch failed: {url} ({last})")


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


CHALLENGERS = {
    "kalshi": fetch_kalshi,
    "espn_fpi": fetch_espn_fpi,
    "draftkings": fetch_draftkings,
    "covers": fetch_covers,
}
