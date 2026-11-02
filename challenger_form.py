"""Challenger "won here, favourite cold" picker (2026-11-02, Olu: every lane needs a player or matchup filter).

PRE-REGISTERED 2026-11-02, before any price or result was looked at. The pick is the Kalshi KXATPCHALLENGERMATCH
player whose YES ask is in the band (0.15-0.30, spread 5c or less, at the real ask before the start, the same entry as
the retired challenger_cheap_split) AND who has already WON a match at this tournament (qualifying counts), while the
favourite has NOT played one there yet. Rationale: a Challenger price leans on ranking and season form; it does not
know that the cheap player has already had match play on site (courts, balls, conditions, time zone) and the
favourite has not. Read point-in-time: "this tournament" is the event's product_metadata.competition (for example
"ATP Challenger Taipei"), and a match counts only once its market settled BEFORE this entry's time, from the same
series within LOOKBACK_DAYS. Players are matched by their full yes_sub_title, accent-insensitively. A match Kalshi
did not list cannot count; an event whose tournament cannot be read is skipped with a note, never guessed.
"""
import datetime as dt
import re
import unicodedata

import chaos_replay as C
import daily_track as D

SERIES = "KXATPCHALLENGERMATCH"
LOOKBACK_DAYS = 10          # qualifying to the final of one Challenger week, with room either side
_EVENTS = {}                # event ticker -> the event (its competition)
_WINDOWS = {}               # (series, first day) -> settled events of the window, nested markets


def norm(name):
    plain = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z]", "", plain.lower())


def _ts(raw):
    try:
        return dt.datetime.fromisoformat(str(raw).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


def competition(event, fetch=D.get):
    """The event's tournament name (product_metadata.competition), None when Kalshi does not give one."""
    if event not in _EVENTS:
        ev = (fetch(f"events/{event}") or {}).get("event") or {}
        _EVENTS[event] = ev
    return ((_EVENTS[event].get("product_metadata") or {}).get("competition") or "").strip() or None


def window(series, first_day, fetch=D.get):
    """Settled events of `series` closing from `first_day` on, with their markets (cached per run)."""
    key = (series, first_day.isoformat())
    if key not in _WINDOWS:
        since = int(dt.datetime.combine(first_day, dt.time(), dt.timezone.utc).timestamp())
        _WINDOWS[key] = D.pages(f"events?series_ticker={series}&status=settled&with_nested_markets=true"
                                f"&min_close_ts={since}&limit=200", "events", fetch)
    return _WINDOWS[key]


def history(event, series, comp, cut_ts, fetch=D.get):
    """{player: (played, won)} at tournament `comp` from matches settled before `cut_ts`, this event excluded."""
    first = dt.datetime.fromtimestamp(cut_ts, dt.timezone.utc).date() - dt.timedelta(days=LOOKBACK_DAYS)
    out = {}
    for ev in window(series, first, fetch):
        if ev.get("event_ticker") == event or ((ev.get("product_metadata") or {}).get("competition") or "").strip() != comp:
            continue
        ms = ev.get("markets") or []
        settled = [m for m in ms if (_ts(m.get("settlement_ts")) or 9e12) < cut_ts and m.get("result") in ("yes", "no")]
        if len(settled) != len(ms) or len(ms) != 2:
            continue                                        # not over by the entry, or not a two-player match
        for m in ms:
            p, w = out.get(norm(m.get("yes_sub_title")), (0, 0))
            out[norm(m.get("yes_sub_title"))] = (p + 1, w + (m.get("result") == "yes"))
    return out


def won_here_picker(lo=0.15, hi=0.30, spread=0.05, fetch=None):
    """The band picker kept only where the cheap player already won here and the favourite has not played here."""
    inner = C.band_picker(lo, hi, ("yes",), spread=spread)

    def pick(ctx):
        cands = inner(ctx)
        if not cands:
            return []
        get = fetch or D.get
        names = {t: (m.get("yes_sub_title") or "") for t, m in ctx["markets"].items()}
        if len(names) != 2 or not all(names.values()):
            raise C.SkipEvent("the event does not name two players")
        comp = competition(ctx["event"], get)
        if not comp:
            raise C.SkipEvent("Kalshi gives no tournament for the event")
        cut = ctx["start_ts"] - int(ctx["hours"] * 3600)
        seen = history(ctx["event"], ctx["series"], comp, cut, get)
        keep = []
        for t, s in cands:
            me = norm(names[t])
            opp = norm(next(n for k, n in names.items() if k != t))
            if seen.get(me, (0, 0))[1] >= 1 and seen.get(opp, (0, 0))[0] == 0:
                keep.append((t, s))
        return keep
    return pick
