#!/usr/bin/env python3
"""venue_book.py — prices from the exchanges a lead can actually be traded on.

Replaces the Bovada sportsbook feed (retired 2026-09-13: it began answering every request
with a cookie redirect loop, and a sportsbook line was never the price anyone here pays).
Every quote is now the ask on Kalshi or Polymarket US — the two venues the trading bot
routes to — so a lead's price, its break-even and its P/L are all measured at a price that
could really have been bought.

Markets, per fixture, under the ledger's existing keys:

  over15 / over25   Polymarket US full-game totals ladder; Kalshi KX{LEAGUE}TOTAL
  btts              Kalshi KX{LEAGUE}BTTS (Polymarket US lists none)
  home2plus/away2plus  Kalshi KX{LEAGUE}TEAMTOTAL, "<team> over 1.5 goals" (none on PM US)

Where both venues list a market the cheaper EFFECTIVE price wins (ask plus that venue's
taker fee) — the same rule the bot routes on. Each quote carries:

  price   decimal odds at the effective price, 1 / (ask + fee): what a follower pays
  fair    the book's midpoint, (bid + ask) / 2: the market's own probability
  ask, bid, fee, venue, market (Kalshi ticker / Polymarket market slug), event
  (Polymarket event slug). No URL is stored: market_url() builds it at render time, so a
  venue changing its URL scheme never leaves stale links frozen in a ledger.

A market is only quoted when its book is two-sided and tight (spread <= MAX_SPREAD); a
one-sided or wide book is no price at all, the same rule the Sandbox applies.

The fixture matcher and the venue adapters are copied from the polymarket-bot
(bot/venue.py, bot/kalshi.py, bot/mapping.py) — public, read-only endpoints only. Its
thresholds were paid for by silent mismatches there and are kept exactly.
"""
import datetime, difflib, json, re, time, unicodedata, urllib.parse, urllib.request

POLY_GATEWAY = "https://gateway.polymarket.us"
KALSHI_API = "https://api.elections.kalshi.com/trade-api/v2"
UA = "edge-machine/venue-book"

POLY = "polymarket_us"
KALSHI = "kalshi"

MAX_SPREAD = 0.10
PACE_S = 0.25                   # between Kalshi calls; one call per series per build

# Board league name -> Polymarket US league slug (bot/venue.py). None: not listed there.
POLY_LEAGUES = {
    "Premier League": "epl", "La Liga": "lal", "Serie A": "sea", "Bundesliga": "bun",
    "Ligue 1": "lg1", "MLS": "mls", "Primeira Liga": "ligpor", "Brasileirao": "bra",
    "Brasileirão": "bra", "Saudi Pro League": "spl", "Champions League": "ucl",
    "Europa League": "uel", "Scottish Premiership": "scp", "Eredivisie": None,
}
POLY_TOTALS = "soccer_team_full_game_total"

# Board league name -> Kalshi ticker fragment, matched EXACTLY as KX{FRAG}{SUFFIX}
# (bot/kalshi.py): a substring match pulls KXSCOTTISHPREMBTTS into "EPL".
KALSHI_LEAGUES = {
    "Premier League": "EPL", "La Liga": "LALIGA", "Serie A": "SERIEA",
    "Bundesliga": "BUNDESLIGA", "Ligue 1": "LIGUE1", "Champions League": "UCL",
    "Europa League": "UEL", "MLS": "MLS", "Eredivisie": "EREDIVISIE",
    "Primeira Liga": "LIGAPORTUGAL", "Saudi Pro League": "SAUDIPL",
    "Scottish Premiership": "SCOTTISHPREM", "Brasileirao": "BRASILEIRO",
    "Brasileirão": "BRASILEIRO",
}

# ---------------------------------------------------------------- fees (bot/venue, bot/kalshi)
def poly_fee(p):
    return 0.06 * p * (1.0 - p)


def kalshi_fee(p):
    import math
    return min(0.035, math.ceil(0.07 * p * (1.0 - p) / 0.0001) * 0.0001)


# ---------------------------------------------------------------- matching (bot/venue.py)
NOISE = {"fc", "afc", "cf", "sc", "ac", "as", "ss", "us", "cd", "ud", "sv", "vfl", "vfb",
         "tsg", "bsc", "fsv", "sk", "bk", "if", "nk", "hk", "club", "clube", "calcio",
         "futbol", "football", "the", "de", "do", "da", "of"}
SIDE_MATCH = 0.76
AMBIGUITY_GAP = 0.06
ALIASES = {
    "la galaxy": "los angeles galaxy", "lafc": "los angeles fc",
    "los angeles fc": "los angeles fc", "ny red bulls": "new york red bulls",
    "red bull new york": "new york red bulls", "nycfc": "new york city fc",
    "hearts": "heart of midlothian", "man city": "manchester city",
    "man utd": "manchester united", "spurs": "tottenham hotspur",
    "psg": "paris saint germain", "inter": "internazionale",
}


def _norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9 ]", " ", s.lower())


def _alias(name):
    return ALIASES.get(" ".join(_norm(name).split()), name)


def _tokens(name):
    return [t for t in _norm(name).split() if t and t not in NOISE]


def sim(a, b):
    a, b = _alias(a), _alias(b)
    ta, tb = " ".join(_tokens(a)), " ".join(_tokens(b))
    if not ta or not tb:
        return 0.0
    if ta in tb or tb in ta:
        return 1.0
    return difflib.SequenceMatcher(None, ta, tb).ratio()


def _pick_event(cands, home, away):
    """cands: [((home_name, away_name), event)] on the right day -> (event|None, reason).
    Both sides must clear SIDE_MATCH; a near-tie between two events is refused."""
    scored = []
    for (h, a), ev in cands:
        sh, sa = sim(h, home), sim(a, away)
        if sh >= SIDE_MATCH and sa >= SIDE_MATCH:
            scored.append((min(sh, sa), ev))
    if not scored:
        return None, ("no event that day" if not cands else
                      f"{len(cands)} event(s) that day, none matching both sides")
    scored.sort(key=lambda x: -x[0])
    if len(scored) > 1 and scored[0][0] - scored[1][0] < AMBIGUITY_GAP:
        return None, "two events matched equally — refusing to guess"
    return scored[0][1], "matched"


# ---------------------------------------------------------------- http
def _get(url, tries=3, timeout=25):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA,
                                                       "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as f:
                return json.loads(f.read())
        except Exception as e:                    # network, HTTP, bad JSON: retried
            last = e
            if i < tries - 1:
                time.sleep(1.5 * (i + 1))
    raise last


def _f(x):
    if isinstance(x, dict):
        x = x.get("value")
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


# Per-process caches. One build prices dozens of fixtures from the same few feeds.
_POLY_EVENTS = {}
_KALSHI_SERIES = None
_KALSHI_EVENTS = {}
_last_kalshi = 0.0
STATS = {"calls": 0, "errors": 0}


def poly_events(slug):
    if slug not in _POLY_EVENTS:
        try:
            STATS["calls"] += 1
            d = _get(f"{POLY_GATEWAY}/v2/leagues/{slug}/events?limit=100")
            _POLY_EVENTS[slug] = (d or {}).get("events") or []
        except Exception:
            STATS["errors"] += 1
            _POLY_EVENTS[slug] = []
    return _POLY_EVENTS[slug]


def _kalshi_get(url):
    global _last_kalshi
    wait = PACE_S - (time.time() - _last_kalshi)
    if wait > 0:
        time.sleep(wait)
    _last_kalshi = time.time()
    STATS["calls"] += 1
    return _get(url)


def kalshi_series():
    global _KALSHI_SERIES
    if _KALSHI_SERIES is None:
        try:
            rows = (_kalshi_get(f"{KALSHI_API}/series?category=Sports") or {}).get("series") or []
            _KALSHI_SERIES = {s.get("ticker") for s in rows if s.get("ticker")}
        except Exception:
            STATS["errors"] += 1
            _KALSHI_SERIES = set()
    return _KALSHI_SERIES


def kalshi_events(series):
    """Open events of a series WITH their markets, cursor-paginated. One call per series."""
    if series in _KALSHI_EVENTS:
        return _KALSHI_EVENTS[series]
    out, cursor = [], ""
    try:
        for _ in range(5):
            q = {"series_ticker": series, "status": "open", "limit": 200,
                 "with_nested_markets": "true"}
            if cursor:
                q["cursor"] = cursor
            d = _kalshi_get(f"{KALSHI_API}/events?{urllib.parse.urlencode(q)}") or {}
            out += d.get("events") or []
            cursor = d.get("cursor") or ""
            if not cursor:
                break
    except Exception:
        STATS["errors"] += 1
    _KALSHI_EVENTS[series] = out
    return out


def _kalshi_date(ev):
    tail = (ev.get("event_ticker") or "").split("-")[-1]
    for i in range(max(0, len(tail) - 6)):
        try:
            return datetime.datetime.strptime(tail[i:i + 7], "%y%b%d").date()
        except ValueError:
            continue
    return None


def _kalshi_sides(ev):
    title = (ev.get("title") or "").split(":")[0]
    parts = [p.strip() for p in title.replace(" vs. ", " vs ").split(" vs ")]
    return (parts[0], parts[1]) if len(parts) == 2 else None


def _quote(venue, ask, bid, market, event=None):
    """One tradeable quote, or None for a one-sided or wide book."""
    if ask is None or bid is None or not (0 < bid < ask < 1) or ask - bid > MAX_SPREAD + 1e-9:
        return None
    fee = poly_fee(ask) if venue == POLY else kalshi_fee(ask)
    eff = ask + fee
    return {"price": round(1.0 / eff, 3), "fair": round((bid + ask) / 2, 4),
            "ask": round(ask, 4), "bid": round(bid, 4), "fee": round(fee, 4),
            "venue": venue, "market": market, **({"event": event} if event else {})}


def market_url(q):
    """Public page for a stored quote, or None."""
    if not isinstance(q, dict):
        return None
    if q.get("venue") == KALSHI and q.get("market"):
        return f"https://kalshi.com/markets/{str(q['market']).split('-')[0].lower()}"
    if q.get("venue") == POLY and q.get("event"):
        return f"https://polymarket.us/event/{q['event']}"
    return None


# ---------------------------------------------------------------- per venue
def poly_quotes(home, away, day, league):
    """{over15, over25} from Polymarket US, or {} when it lists nothing for this fixture."""
    slug = POLY_LEAGUES.get(league)
    if not slug:
        return {}
    cands = []
    for ev in poly_events(slug):
        if (ev.get("startDate") or "")[:10] != day:
            continue
        parts = re.split(r"\s+vs?\.?\s+", ev.get("title") or "", flags=re.I)
        if len(parts) == 2:
            cands.append(((parts[0].strip(), parts[1].strip()), ev))
    ev, _why = _pick_event(cands, home, away)
    if not ev:
        return {}
    out = {}
    for m in ev.get("markets") or []:
        if m.get("closed") or m.get("sportsMarketType") != POLY_TOTALS:
            continue
        title = (m.get("title") or "").strip()
        for mk, want in (("over15", "Over 1.5 total goals"), ("over25", "Over 2.5 total goals")):
            if title == want:
                q = _quote(POLY, _f(m.get("bestAskQuote")), _f(m.get("bestBidQuote")),
                           m.get("slug"), ev.get("slug"))
                if q:
                    out[mk] = q
    return out


def kalshi_quotes(home, away, day, league):
    """{over15, over25, btts, home2plus, away2plus} from Kalshi, as far as it lists them."""
    frag = KALSHI_LEAGUES.get(league)
    if not frag:
        return {}
    want = datetime.date.fromisoformat(day)
    out = {}
    for suffix in ("TOTAL", "BTTS", "TEAMTOTAL"):
        series = f"KX{frag}{suffix}"
        if series not in kalshi_series():
            continue
        cands = [(s, ev) for ev in kalshi_events(series)
                 if _kalshi_date(ev) == want and (s := _kalshi_sides(ev))]
        ev, _why = _pick_event(cands, home, away)
        if not ev:
            continue
        ms = [m for m in ev.get("markets") or []
              if str(m.get("status", "")).lower() in ("active", "open")]
        sides = _kalshi_sides(ev)

        def q(m):
            return _quote(KALSHI, _f(m.get("yes_ask_dollars")), _f(m.get("yes_bid_dollars")),
                          m.get("ticker"))

        if suffix == "BTTS":
            m = next((x for x in ms if str(x.get("ticker", "")).endswith("-BTTS")), None)
            if m and q(m):
                out["btts"] = q(m)
        elif suffix == "TOTAL":
            for mk, line in (("over15", "1.5"), ("over25", "2.5")):
                m = [x for x in ms if f"over {line}" in (x.get("yes_sub_title") or "").lower()]
                if len(m) == 1 and q(m[0]):
                    out[mk] = q(m[0])
        else:
            for mk, team in (("home2plus", sides[0]), ("away2plus", sides[1])):
                # "Leeds United over 1.5 goals": the team must be THIS side, or this quotes
                # the other team's line.
                m = [x for x in ms if " over 1.5" in (x.get("yes_sub_title") or "").lower()
                     and sim((x.get("yes_sub_title") or "").lower().split(" over ")[0], team)
                     >= SIDE_MATCH
                     and sim((x.get("yes_sub_title") or "").lower().split(" over ")[0],
                             sides[1] if team == sides[0] else sides[0]) < SIDE_MATCH]
                if len(m) == 1 and q(m[0]):
                    out[mk] = q(m[0])
    return out


# ---------------------------------------------------------------- the interface
FIXTURE_MARKETS = ("over15", "over25", "btts", "home2plus", "away2plus")


def fixture_key(f):
    """Pricing key for a fixture — replaces the Bovada game link — or None when neither
    venue lists its league at all."""
    league = f.get("league") or ""
    if not (POLY_LEAGUES.get(league) or KALSHI_LEAGUES.get(league)):
        return None
    ko = f.get("kickoff") or f.get("date") or ""
    return json.dumps({"league": league, "day": str(ko)[:10],
                       "home": f.get("home"), "away": f.get("away")}, sort_keys=True)


def fixture_quotes(key):
    """{market: quote} for a fixture key, the cheaper effective price per market, or None
    when the key is unreadable. {} means nothing is listed (yet)."""
    try:
        k = json.loads(key)
        home, away, day, league = k["home"], k["away"], k["day"], k["league"]
    except (TypeError, ValueError, KeyError):
        return None
    best = {}
    for quotes in (poly_quotes(home, away, day, league), kalshi_quotes(home, away, day, league)):
        for mk, q in quotes.items():
            if mk not in best or 1 / q["price"] < 1 / best[mk]["price"]:
                best[mk] = q
    return best


def fetch_prices(key):
    """The shape streaks_track.price expects (formerly venues.fetch_bovada_prices):
    fixture markets at the top level, team totals under "team" by side."""
    q = fixture_quotes(key)
    if q is None:
        return None
    out = {mk: q[mk] for mk in ("over15", "over25", "btts") if mk in q}
    team = {side: {"over15": q[mk]} for side, mk in (("home", "home2plus"), ("away", "away2plus"))
            if mk in q}
    if team:
        out["team"] = team
    return out
