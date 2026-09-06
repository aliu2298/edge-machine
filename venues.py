#!/usr/bin/env python3
"""venues.py — match a fixture to its Bovada market page.

Extracted from export_public.py so the boards, the health check and the slate can all
share ONE matcher. A second copy would drift from the hard-won parts below — the name
aliases and the side-matching rules — each of which was a silent bug that made links
quietly disappear rather than fail loudly.

Public, unauthenticated feeds only. No keys, no auth, fail-soft: a missing link is normal,
since plenty of fixtures simply have no market.
"""
import json, re, difflib, datetime, unicodedata, urllib.request, urllib.error

# ---------------------------------------------------------------- venue links
# Public, unauthenticated feeds only. Extend the lists as leagues open.
BOVADA_API = "https://www.bovada.lv/services/sports/event/coupon/events/A/description/soccer"
# Bovada is queried at the TOP LEVEL, not per league. Two reasons, both learned by
# probing rather than guessing:
#   * the per-league coupon 404s unpredictably — Bundesliga is "1-bundesliga", not
#     "bundesliga", and several paths that appear in the top-level listing return 404
#     when requested directly
#   * one call returns ~1500 events across every competition Bovada lists, which covers
#     all nine tracked domestic leagues in a single request instead of eleven
# Lesson worth keeping: enumerate what the API actually has, never hand-write the
# key space from guesses.
BOVADA_ALL = (BOVADA_API + "?marketFilterId=def&preMatchOnly=true&lang=en")
# our team-name token → alternate token some venues use (tried alongside the raw token)
ALIASES = {"athletico": "paranaense", "angeles": "lafc",
           "hearts": "midlothian"}   # some feeds spell it "Heart of Midlothian"

# Corporate/legal noise that carries no identity. "Real" and "Atletico" are deliberately
# NOT here: they are the only thing separating Real Madrid from Real Sociedad.
NOISE = {"fc", "afc", "cf", "sc", "ac", "as", "ss", "us", "cd", "ud", "sv", "vfl", "vfb",
         "tsg", "bsc", "fsv", "sk", "bk", "if", "nk", "hk", "club", "clube", "calcio",
         "futbol", "football", "the", "de", "do", "da", "of", "и"}
SIDE_MATCH = 0.76          # per-side similarity needed to call it the same team
AMBIGUITY_GAP = 0.06       # best must beat runner-up by this, or we refuse to guess
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

_BOVADA_MEM = None


def fetch_bovada_events():
    """[(url, title, date)] for upcoming Bovada soccer events. Empty on failure.

    One request for every competition (see BOVADA_ALL). Memoised for the process so the
    board builders share a single fetch rather than repeating a 1500-event download.
    """
    global _BOVADA_MEM
    if _BOVADA_MEM is not None:
        return _BOVADA_MEM
    try:
        groups = _get_json(BOVADA_ALL)
    except Exception as e:
        print(f"  (bovada lookup failed: {e})")
        _BOVADA_MEM = []
        return _BOVADA_MEM
    out = []
    for grp in groups or []:
        for ev in grp.get("events") or []:
            d = None
            if ev.get("startTime"):
                d = datetime.datetime.fromtimestamp(
                    ev["startTime"]/1000, datetime.timezone.utc).date()
            # The API's `link` is relative to the /sports app root — without the prefix
            # Bovada renders "page not found".
            out.append((f"https://www.bovada.lv/sports{ev.get('link','')}",
                        ev.get("description") or "", d))
    if not out:
        print("  (bovada: returned NO events — endpoint or filter changed?)")
    print(f"  (bovada events: {len(out)})")
    _BOVADA_MEM = out
    return out

def _sides(text):
    """Split "A vs B" into two normalised team names, or None."""
    parts = re.split(r"\s+vs?\.?\s+", text or "", flags=re.I)
    if len(parts) != 2:
        return None
    return [" ".join(t for t in _norm(p).split() if t not in NOISE) for p in parts]


def side_score(a, b):
    """0..1 that two spellings name the same club.

    Scored on the most distinctive token rather than the whole string, because venues
    disagree about DESCRIPTORS, not about identity: ESPN's "Stade Rennais" is Bovada's
    "Rennes", "Internazionale" is "Inter Milan", "Al Taawoun" is "Al Taawon". Averaging
    over tokens lets a stray "Stade" veto a correct match.

    Scoring on the single best token alone is NOT safe: "Real Madrid" vs "Real Sociedad"
    then scores 1.0 on the shared "Real". So the side with FEWER distinctive tokens must
    have EVERY one of them matched — that side is the abbreviation, and an abbreviation
    drops descriptors, never identity:

        stade rennais / rennes        -> "rennes" is the short side, matches "rennais"
        real madrid   / real sociedad -> tied, so both directions checked: madrid vs
                                         sociedad fails and the shared "Real" cannot
                                         carry it
        inter milan   / internazionale-> "internazionale" is the short side, prefix hit

    A token must be >= 4 chars to count. Names built entirely of short words ("Rio Ave")
    have none, so they fall back to whole-string similarity — the old matcher simply
    dropped such teams, which is why Santa Clara vs Rio Ave had no link despite Bovada
    listing it under exactly that name.
    """
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    long_a = [t for t in a.split() if len(t) >= 4]
    long_b = [t for t in b.split() if len(t) >= 4]
    if not long_a or not long_b:
        return difflib.SequenceMatcher(None, a, b).ratio()

    def tok(x, y):
        """Symmetric: ALIASES is expanded on BOTH tokens, not just one.

        Applying it one-way made LAFC/"Los Angeles" score 1.0 in one direction and 0.18
        in the other, so the two-way cover check below threw the match away.
        """
        xs = {x, ALIASES.get(x, x)}
        ys = {y, ALIASES.get(y, y)}
        if xs & ys:
            return 1.0
        best = 0.0
        for p in xs:
            for q in ys:
                if p.startswith(q) or q.startswith(p):
                    best = max(best, 0.92)
                else:
                    best = max(best, difflib.SequenceMatcher(None, p, q).ratio())
        return best

    def cover(xs, ys):
        """Weakest link: every token of `xs` must find a partner in `ys`."""
        return min(max(tok(x, y) for y in ys) for x in xs)

    if len(long_a) < len(long_b):
        return cover(long_a, long_b)
    if len(long_b) < len(long_a):
        return cover(long_b, long_a)
    return min(cover(long_a, long_b), cover(long_b, long_a))


def venue_link(match, kickoff, events):
    """URL of the venue's game page for `match`, or None if no confident match.

    Sides are matched IN ORDER (home to home), never swapped: accepting a swapped match
    would happily return the reverse fixture, which is a different game. And when two
    events both look like the fixture, this returns None rather than picking one — a
    wrong link is worse than no link, since the card still reads as if it were checked.
    """
    try:
        ko = datetime.date.fromisoformat((kickoff or "")[:10])
    except ValueError:
        return None
    ours = _sides(match)
    if not ours:
        return None
    scored = {}
    for url, title, d in events:
        if d is None or abs((d - ko).days) > 1: continue  # listing dates are ET/UTC-fuzzy
        theirs = _sides(title)
        if not theirs:
            continue
        s = min(side_score(ours[0], theirs[0]), side_score(ours[1], theirs[1]))
        if s < SIDE_MATCH:
            continue
        # Keyed by the TEAM PAIR, not the listing. Bovada publishes the same fixture
        # more than once (different market groupings, same teams and date), and treating
        # a duplicate as a rival candidate made the ambiguity guard veto every ordinary
        # match — coverage fell from 46 to 36 before this was keyed properly.
        key = tuple(theirs)
        if s > scored.get(key, (0.0, None))[0]:
            scored[key] = (s, url)
    if not scored:
        return None
    ranked = sorted(scored.values(), key=lambda x: -x[0])
    if len(ranked) > 1 and ranked[0][0] - ranked[1][0] < AMBIGUITY_GAP:
        return None                      # two DIFFERENT fixtures both fit: refuse to guess
    return ranked[0][1]
