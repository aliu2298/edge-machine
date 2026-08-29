#!/usr/bin/env python3
"""venues.py — match a fixture to its betting-venue page (Kalshi, Bovada).

Extracted from export_public.py so the boards, the health check and the slate can all
share ONE matcher. A second copy would drift from the hard-won parts below — the empty
KXUEFAGAME series, cursor pagination, 429 backoff, and the name aliases — each of which
was a silent bug that made links quietly disappear rather than fail loudly.

Public, unauthenticated feeds only. No keys, no auth, fail-soft: a missing link is normal,
since plenty of fixtures simply have no market.
"""
import json, os, re, time, datetime, unicodedata, urllib.request, urllib.error

# ---------------------------------------------------------------- venue links
# Public, unauthenticated feeds only. Extend the lists as leagues open.
KALSHI_API = "https://api.elections.kalshi.com/trade-api/v2/events"
# Per-match GAME series for the 10 tracked leagues.
# NB: "KXUEFAGAME" looks right but is an EMPTY series (0 events) — Europa League fixtures
# live under KXUELGAME. Using the wrong one silently produced tips cards with no Kalshi
# button for every Europa tie. Verify a series actually returns events before adding it.
KALSHI_SERIES = ["KXBRASILEIROGAME", "KXMLSGAME",
                 "KXEPLGAME", "KXLALIGAGAME", "KXBUNDESLIGAGAME", "KXSERIEAGAME",
                 "KXLIGUE1GAME", "KXEREDIVISIEGAME", "KXLIGAPORTUGALGAME",
                 "KXUCLGAME", "KXUELGAME", "KXUECLGAME"]
KALSHI_MAX_PAGES = 3      # events endpoint caps at 200/page and returns a cursor
BOVADA_API = "https://www.bovada.lv/services/sports/event/coupon/events/A/description/soccer"
BOVADA_LEAGUES = ["north-america/united-states/mls",
                  "south-america/brazil/brasileirao-serie-a",
                  "international-club/uefa-champions-league",
                  "international-club/uefa-europa-league"]
# our team-name token → alternate token some venues use (tried alongside the raw token)
ALIASES = {"athletico": "paranaense", "angeles": "lafc",
           "hearts": "midlothian"}   # Kalshi spells it "Heart of Midlothian"
MONTHS = {m: i+1 for i, m in enumerate(
    ["JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"])}

def _norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9 ]", " ", s.lower())

def _get_json(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"})
    with urllib.request.urlopen(req, timeout=10) as f:
        return json.load(f)

KALSHI_CACHE = os.path.join(os.path.dirname(__file__), "data", ".kalshi_events.json")
KALSHI_CACHE_TTL = 3600          # seconds
_KALSHI_MEM = None
_KALSHI_COUNTS = {}               # series -> event count, for health.py's series check


def _kalshi_page(url, tries=4):
    """One request, with backoff on 429. Kalshi rate-limits hard once you query ~10
    series back-to-back, and a silent failure just makes links disappear."""
    for i in range(tries):
        try:
            return _get_json(url)
        except urllib.error.HTTPError as e:
            if e.code == 429 and i < tries - 1:
                time.sleep(1.5 * (i + 1))
                continue
            raise
    return {}


def _kalshi_series_events(series):
    """All events for a series, following the cursor.

    The endpoint caps at 200 per page. Taking only the first page silently truncated
    KXUCLGAME (exactly 200 back, cursor non-null), so fixtures past the cut had no link.
    """
    out, cursor = [], None
    for page in range(KALSHI_MAX_PAGES):
        # no status filter: events leave "open" at kickoff, but their pages keep
        # working (and show the result) — the date check scopes matches
        url = f"{KALSHI_API}?series_ticker={series}&limit=200"
        if cursor:
            url += f"&cursor={cursor}"
        try:
            data = _kalshi_page(url)
        except Exception as e:
            print(f"  (kalshi lookup skipped for {series}: {e})")
            break
        evs = data.get("events") or []
        out += evs
        cursor = data.get("cursor")
        if not cursor or not evs:
            break
        time.sleep(0.3)
    if not out:
        print(f"  (kalshi: {series} returned NO events — wrong series ticker?)")
    return out


def fetch_kalshi_events():
    """[(url, title, date)] for Kalshi game events. Cached on disk so the two board
    builders in one CI run share a single fetch instead of doubling the request count."""
    global _KALSHI_MEM
    if _KALSHI_MEM is not None:
        return _KALSHI_MEM
    global _KALSHI_COUNTS
    try:
        st = os.path.getmtime(KALSHI_CACHE)
        if time.time() - st < KALSHI_CACHE_TTL:
            raw = json.load(open(KALSHI_CACHE))
            # cache was a bare list before per-series counts were added; accept both
            rows = raw.get("events", []) if isinstance(raw, dict) else raw
            _KALSHI_COUNTS = raw.get("counts", {}) if isinstance(raw, dict) else {}
            _KALSHI_MEM = [(u, t, datetime.date.fromisoformat(d) if d else None)
                           for u, t, d in rows]
            print(f"  (kalshi events from cache: {len(_KALSHI_MEM)})")
            return _KALSHI_MEM
    except Exception:
        pass

    out = []
    _KALSHI_COUNTS = {}
    for n, series in enumerate(KALSHI_SERIES):
        if n:
            time.sleep(0.4)                      # pace: stay under the rate limit
        events = _kalshi_series_events(series)
        _KALSHI_COUNTS[series] = len(events)
        for ev in events:
            t = ev.get("event_ticker") or ""
            m = re.search(r"-(\d{2})([A-Z]{3})(\d{2})", t)  # -26JUL25...
            d = None
            if m:
                yy, mon, dd = m.groups()
                try: d = datetime.date(2000+int(yy), MONTHS[mon], int(dd))
                except (KeyError, ValueError): pass
            out.append((f"https://kalshi.com/events/{t}", ev.get("title") or "", d))
    try:
        os.makedirs(os.path.dirname(KALSHI_CACHE), exist_ok=True)
        with open(KALSHI_CACHE, "w") as f:
            json.dump({"events": [(u, t, d.isoformat() if d else None) for u, t, d in out],
                       "counts": _KALSHI_COUNTS}, f)
    except Exception:
        pass
    _KALSHI_MEM = out
    return out

def kalshi_series_counts():
    """series -> number of events fetched. Populated by fetch_kalshi_events (or restored
    from its cache); health.py uses it to catch a series ticker that returns nothing."""
    if _KALSHI_MEM is None:
        fetch_kalshi_events()
    return dict(_KALSHI_COUNTS)


def fetch_bovada_events():
    """[(url, title, date)] for upcoming Bovada soccer events. Empty on failure."""
    out = []
    for league in BOVADA_LEAGUES:
        try:
            groups = _get_json(f"{BOVADA_API}/{league}?marketFilterId=def&preMatchOnly=true&lang=en")
        except Exception as e:
            print(f"  (bovada lookup skipped for {league}: {e})")
            continue
        for grp in groups or []:
            for ev in grp.get("events") or []:
                d = None
                if ev.get("startTime"):
                    d = datetime.datetime.fromtimestamp(
                        ev["startTime"]/1000, datetime.timezone.utc).date()
                # The API's `link` is relative to the /sports app root — without
                # the prefix Bovada renders "page not found".
                out.append((f"https://www.bovada.lv/sports{ev.get('link','')}",
                            ev.get("description") or "", d))
    return out

def venue_link(match, kickoff, events):
    """URL of the venue's game page for `match`, or None if no confident match."""
    try:
        ko = datetime.date.fromisoformat((kickoff or "")[:10])
    except ValueError:
        return None
    sides = re.split(r"\s+vs?\.?\s+", match or "", flags=re.I)
    if len(sides) != 2: return None
    def side_hits(side, nt):
        for tok in _norm(side).split():
            cands = [tok, ALIASES.get(tok, tok)]
            if any(len(c) >= 4 and c in nt for c in cands):
                return True
        return False
    for url, title, d in events:
        if d is None or abs((d - ko).days) > 1: continue  # listing dates are ET/UTC-fuzzy
        nt = _norm(title)
        if all(side_hits(s, nt) for s in sides):
            return url
    return None
