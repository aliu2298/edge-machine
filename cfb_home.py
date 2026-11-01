"""College football home underdog picker (2026-11-01, Olu: every lane needs a team or matchup filter).

The pick is the Kalshi KXNCAAFGAME side whose YES ask is in the band AND whose team is the HOME team of an ESPN
game that is not at a neutral site. ESPN's scoreboard (homeAway, competitions[0].neutralSite) is matched to the
market by its yes_sub_title: names are normalised (St. -> State, & -> and, letters only) and compared as a
prefix against the school's short name, location, nickname and abbreviation, and BOTH sides of the event must
match the two different teams of one game. No match: the event is skipped with a note, never guessed.
"""
import datetime as dt
import re

import chaos_replay as C


def norm(name):
    return re.sub(r"[^a-z]", "", (name or "").lower().replace("st.", "state").replace("&", "and"))


def _same(n, cand):
    """A Kalshi name against one ESPN form of a school's name: equal, or (over 4 letters) one starts the other."""
    return bool(n) and bool(cand) and (n == cand or (len(n) > 4 and (cand.startswith(n) or n.startswith(cand))))


def team_forms(team):
    return [norm(team.get(k)) for k in ("shortDisplayName", "location", "name", "abbreviation", "displayName")]


def match_game(names, events):
    """The ESPN game whose two competitors are the event's two named teams -> (home name, neutral flag, {kalshi
    name: 'home' | 'away'}), or None. `names` are the event's yes_sub_titles."""
    wanted = [norm(n) for n in names]
    for ev in events:
        comps = ((ev.get("competitions") or [{}])[0]).get("competitors") or []
        if len(comps) != 2 or len(wanted) != 2:
            continue
        forms = [team_forms(c.get("team") or {}) for c in comps]
        best = None
        for order in ((0, 1), (1, 0)):
            if all(any(_same(wanted[i], f) for f in forms[order[i]]) for i in (0, 1)):
                exact = sum(wanted[i] in forms[order[i]] for i in (0, 1))      # Miami v Miami (OH): exact names win
                if best is None or exact > best[0]:
                    best = (exact, order)
        if best:
            order = best[1]
            neutral = bool(((ev.get("competitions") or [{}])[0]).get("neutralSite"))
            return neutral, {names[i]: comps[order[i]].get("homeAway") for i in (0, 1)}
    return None


def home_dog_picker(board, lo=0.10, hi=0.25, spread=C.MAX_SPREAD):
    """The home-underdog picker: YES ask lo-hi (spread at most `spread`), the team at home, not a neutral site.
    `board(day)` is the ESPN scoreboard events of one day (it raises when ESPN is unreachable)."""
    inner = C.band_picker(lo, hi, ("yes",), spread=spread)

    def pick(ctx):
        cands = inner(ctx)
        if not cands:
            return []
        day = C.event_date(ctx["event"])
        names = [m.get("yes_sub_title") or "" for m in ctx["markets"].values()]
        if not day or len(names) != 2 or not all(names):
            raise C.SkipEvent("no ESPN match: the event does not name two teams")
        found = None
        for d in (day - dt.timedelta(days=1), day, day + dt.timedelta(days=1)):
            found = match_game(names, board(d))
            if found:
                break
        if not found:
            raise C.SkipEvent(f"no ESPN match for {' v '.join(names)}")
        neutral, sides = found
        if neutral:
            return []
        return [(t, s) for t, s in cands if sides.get((ctx["markets"].get(t) or {}).get("yes_sub_title")) == "home"]
    return pick
