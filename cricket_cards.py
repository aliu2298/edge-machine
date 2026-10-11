#!/usr/bin/env python3
"""What the Cricket page hands the shared sport template (sport_page), built with
the Tennis page's own helpers so the two cannot drift apart. The record, verdict
and ROI on every row are the Sandbox row's own figures, the same strings the
Sandbox table prints. Nothing here grades, settles, or chooses a bet.

Cricket lane records do not use the tennis tour keep-set, so a refused-tour
check is not applied. A repeat city-day quote is left out, the same exclusion
the lane's open count already uses. A lane reset clock is already inside the
row's verdict and ROI, and the picks listed under a rule are the bets its
record counts.
"""
import datetime
from datetime import timedelta, timezone

import fmt
import sandbox_build as B
import sandbox_sources as S
import sandbox_track as T
import tennis_cards as TN

FAMILY = "Cricket"
# Settled picks stay on the Matches list this long after their start.
SETTLED_DAYS = 14
# Settled picks listed under an expanded rule, newest first.
RECENT_LIMIT = TN.RECENT_LIMIT
_FAR = datetime.datetime.max.replace(tzinfo=timezone.utc)
# Where a bet traded. polymarket.com rows from before 2026-09-13 keep their name.
VENUE_NAMES = dict(TN.VENUE_NAMES, polymarket="Polymarket")
# Every status a settled cricket bet can carry, with the word and the class the
# list shows. won and lost are the Tennis page's own.
_SETTLED_STATES = {
    "won": ("W", "is-won"),
    "lost": ("L", "is-lost"),
    "void": ("Void", "is-void"),
    "settled": (T.NO_RESULT_LABEL, "is-price"),
}
SETTLED_STATUSES = tuple(_SETTLED_STATES)

roi_html = TN.roi_html
verdict_html = TN.verdict_html
record_text = TN.record_text
_kickoff = TN._kickoff
_as_utc = TN._as_utc
_day_label = TN._day_label
next_check = TN.next_check


# ------------------------------------------------------------------ the rows a rule owns
def _on_clock(q, row):
    """False for a bet logged before this lane's reset clock. Those stay on file only.

    The clock is the stage row's `since`, the same instant `assess` counts
    the record from (`logged >= since`), so the picks listed here are the bets
    the row's record counts. A tennis tour clock, were a cricket lane ever on
    one, is read the same way the Sandbox reads it.
    """
    clock = S.tour_clock_since(since=row.get("since"), source=row["name"]) or row.get("since")
    if not clock:
        return True
    return str(q.get("logged") or "") >= str(clock)


def _kept(q, row):
    return (q.get("source") == row["name"] and q.get("sport") == row["sport"]
            and q.get("bet") and not T.climate_excluded(q) and _on_clock(q, row))


def open_quotes(d, name, sport, row=None):
    """Open bets for one rule, soonest first. The same rows the open count uses.

    An open bet is not cut by the lane clock: the open column does not cut it either.
    """
    live = [q for q in T.bet_rows(d)
            if q.get("source") == name and q.get("sport") == sport
            and q.get("status") == "open" and q.get("bet") and not T.climate_excluded(q)]
    live.sort(key=lambda q: (q.get("start") or "", str(q.get("id") or "")))
    return live


def settled_quotes(d, row):
    """Settled bets for one rule, newest first: won, lost, void, or paid at a price."""
    done = [q for q in T.bet_rows(d) if q.get("status") in SETTLED_STATUSES and _kept(q, row)]
    done.sort(key=lambda q: (q.get("start") or "", str(q.get("id") or "")), reverse=True)
    return done


# ------------------------------------------------------------------ words
def rule_name(row):
    """A rule's short name: its registered label without the parenthesis."""
    return row["meta"]["label"].split(" (")[0].strip()


def venue_of(q):
    return VENUE_NAMES.get(str(q.get("venue") or ""), "")


def venue_name(d, row):
    """Kalshi, Polymarket US, or both, read from the venues of the rule's own bets."""
    seen = {venue_of(q) for q in T.bet_rows(d) if _kept(q, row)}
    names = sorted(n for n in seen if n)
    return " · ".join(names) if names else "—"


def match_label(q):
    """'Team A vs Team B', the contest without the market part."""
    return S.position_label(q).split(":", 1)[0].strip()


def pick_label(q):
    """The team backed. A Yes/No market names its side as stored."""
    return str(B._side(q) or "")


def state_of(q, now):
    """(word, class). W / L / Void / No result · paid 50¢ once settled; in play
    from the start; upcoming before it."""
    found = _SETTLED_STATES.get(q.get("status"))
    if found:
        if q.get("status") == "settled":
            return T.no_result_label(q), found[1]
        return found
    ko = _kickoff(q)
    if ko is not None and ko <= now:
        return "in play", "is-live"
    return "upcoming", "is-next"


# ------------------------------------------------------------------ the picks list
def _pick_instant(q):
    """When a settled pick happened: its start, or the settlement stamp without one."""
    ko = _kickoff(q)
    if ko is not None:
        return ko
    try:
        return _as_utc(datetime.datetime.fromisoformat(str(q.get("settled")).replace("Z", "+00:00")))
    except (TypeError, ValueError):
        return None


def _recent_html(d, row, now):
    live = open_quotes(d, row["name"], row["sport"], row)
    done = settled_quotes(d, row)[:RECENT_LIMIT]
    if not live and not done:
        return '<p class="sm mut">No pick logged yet.</p>'
    items = []
    for q in live + done:
        ko = _kickoff(q)
        when = fmt.when(ko) if ko is not None else "time TBC"
        word, cls = state_of(q, now)
        bits = [B.esc(when), B.safe_href(S.market_url(q), match_label(q)), B.esc(pick_label(q))]
        if q.get("price") is not None:
            bits.append(B.esc(fmt.cents(q.get("price"))))
        venue = venue_of(q)
        if venue:
            bits.append(f'<span class="badge">{B.esc(venue)}</span>')
        bits.append(f'<span class="sp-state {cls}">{B.esc(word)}</span>')
        items.append(f'<li class="rule-pick">{" · ".join(bits)}</li>')
    return f'<ul class="rule-picks">{"".join(items)}</ul>'


def listing_counts(d):
    """(taken, listed, priced) the last run stored for the Polymarket US cricket
    listing, or None when the venue has no cricket market on its list."""
    meta = S.SOURCES.get("polymarket_us") or {}
    sports = [sp for sp in (meta.get("sports") or [])
              if B.family(sp) == FAMILY
              and not S.lane_removed("polymarket_us", sp)
              and sp not in S.REMOVED_VENUE_SPORTS]
    if not sports:
        return None
    cov = d.get("coverage") or {}
    taken = listed = priced = 0
    for sp in sports:
        cell = cov.get(sp) or {}
        for key, slot in (("polymarket_us", 0), ("polymarket_us_listed", 1), ("polymarket_us_priced", 2)):
            value = cell.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            if slot == 0:
                taken += int(value)
            elif slot == 1:
                listed += int(value)
            else:
                priced += int(value)
    return taken, listed, priced


def listing_line(d):
    counts = listing_counts(d)
    if counts is None:
        return "Polymarket US listing: not on the venue's list"
    taken, listed, priced = counts
    return f"Polymarket US listing: {taken} taken · {listed} listed · {priced} priced · no record"



# ------------------------------------------------------------------ what the template asks for
def market(d, row):
    """The venue column: where the rule's own bets traded."""
    return venue_name(d, row)


def recent_html(d, row, now):
    return _recent_html(d, row, now)


def _state(q):
    status = str(q.get("status") or "open")
    if status == "settled":
        return "price"
    return status if status in ("won", "lost", "void") else "open"


def events(d, rows, now):
    """One event per contest: the open picks and the picks settled inside the
    template's window, each pick on its own rule, with its venue."""
    import sport_page as SP
    now = _as_utc(now)
    floor = now - timedelta(days=SP.DONE_DAYS)
    by_key = {}
    for row in rows:
        live = open_quotes(d, row["name"], row["sport"], row)
        done = [q for q in settled_quotes(d, row) if (_pick_instant(q) or floor) >= floor]
        for q in live + done:
            label = match_label(q)
            ko = _kickoff(q)
            key = (" ".join(label.casefold().split()), ko.isoformat() if ko else str(q.get("id") or ""))
            rec = by_key.setdefault(key, dict(q=q, label=label, picks=[]))
            rec["picks"].append(SP.pick(row, q, pick_label(q), _state(q), price=q.get("price"),
                                        legs=venue_of(q), settled=_pick_instant(q)))
    out = []
    for rec in by_key.values():
        q = rec["q"]
        out.append(SP.event(_kickoff(q), fmt.contest(rec["label"]), rec["picks"], href=None, sub=""))
    out.sort(key=lambda e: (e["when"] or _FAR, e["label"]))
    return out


def method(idle_html=""):
    """The venue line and the grading note for the template's Method fold."""
    def _method(d, rows, now):
        inner = (
            '<p class="sm">Polymarket US lists the match-winner markets; it logs prices and holds no '
            'record of its own, so it has no row in the rules table, and the counts are what the '
            'last run stored.</p>'
            f'<p class="sm">Every pick is logged before the start at the price available then, settled '
            f'on the real result at a flat ${int(T.STAKE)} stake, and judged after fees against the '
            f'price it paid.</p>'
            f'{idle_html}')
        return listing_line(d), "venue note", inner, False
    return _method
