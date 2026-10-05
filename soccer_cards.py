#!/usr/bin/env python3
"""Soccer rule cards. Presentation only, and only the Soccer page asks for them.

Each Sandbox lane row becomes a card. The front is that row's verdict and its
ROI after fees, the same strings the table cell already uses. The back is the
open bets on that rule, soonest first, four of them. Active rules — a pick is
in, including one whose game is inside 48 hours — sit above rules with nothing
open. Nothing here grades, settles, or chooses a bet.
"""
import datetime
from datetime import timedelta, timezone

import fmt
import sandbox_build as B
import sandbox_sources as S
import sandbox_track as T

# The brief's window for "upcoming". A pick already in is active either way.
HORIZON = timedelta(hours=48)
# The back lists this many open games. The rest of the open count stays a number.
OPEN_LIMIT = 4
_FAR = datetime.datetime.max.replace(tzinfo=timezone.utc)


def roi_html(row):
    """The ROI text a Sandbox row prints for this pair. Grey under the read floor."""
    a = row["a"]
    if not a["n"]:
        return "—"
    thin = a["n"] < B.MIN_N
    klass = "mut" if thin else fmt.tone(a["roi_fee"], ".1f", 100)
    return f'<span class="{klass}">{B.pct(a["roi_fee"], sign=True)}</span>'


def verdict_html(row):
    """The verdict chip a Sandbox row prints for this pair."""
    label, chip, _order = B.VERDICTS[row["v"]]
    return f'<span class="sig {chip}">{B.esc(label)}</span>'


def open_quotes(d, name, sport):
    """Open bets for one rule, soonest first. The same rows the open count uses.

    `pair_status` counts a bet row that is open, not removed by the climate
    rule, and not a refused tennis tour. This is that list, ordered the way
    the Sandbox's running table orders a slate.
    """
    live = [q for q in T.bet_rows(d)
            if q.get("source") == name and q.get("sport") == sport
            and q.get("status") == "open" and q.get("bet")
            and not T.climate_excluded(q) and not S.tennis_refused_row(q)]
    live.sort(key=lambda q: (q.get("start") or "", q.get("sport") or "", str(q.get("id") or "")))
    return live


def _kickoff(q):
    raw = q.get("start")
    if not raw:
        return None
    try:
        return fmt.chicago(raw).astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _kick_label(q):
    raw = q.get("start")
    if raw:
        try:
            return fmt.when(raw)
        except (TypeError, ValueError, OverflowError, OSError):
            pass
    day = q.get("date")
    return day.strip() if isinstance(day, str) else ""


def _soonest(quotes):
    found = [k for k in (_kickoff(q) for q in quotes) if k is not None]
    return min(found) if found else None


def _market_name(base, fam="Soccer"):
    """The market-fold heading. Same words `market_folds` prints."""
    full = S.SPORTS.get(base, base)
    return "Match winner" if full == fam else full.split(" · ")[-1]


def _games(quotes):
    shown = quotes[:OPEN_LIMIT]
    if not shown:
        return '<p class="mut">No open game.</p>'
    items = []
    for q in shown:
        label = S.display_label(q)
        side = B._side(q) or ""
        when = _kick_label(q)
        extra = " · ".join(part for part in (str(side), when) if part)
        link = B.safe_href(S.market_url(q), label)
        sub = f'<div class="sm mut">{B.esc(extra)}</div>' if extra else ""
        items.append(f'<li class="rule-game">{link}{sub}</li>')
    more = ""
    if len(quotes) > OPEN_LIMIT:
        more = f'<p class="sm mut">{OPEN_LIMIT} of {len(quotes)} open, soonest first.</p>'
    return (f'<p class="rule-kicker">Open games</p>'
            f'<ul class="rule-games">{"".join(items)}</ul>{more}')


def _card(row, quotes):
    meta = row["meta"]
    name = meta["label"].split(" (")[0]
    sfx = B._scope(row["sport"])
    tag = f' <span class="sig w">{B.esc(S.SCOPE_LABEL[sfx].upper())}</span>' if sfx else ""
    prod = '<span class="sig y">PRODUCTION</span>' if row.get("prod") else ""
    stage = f'<p class="rule-stage">{prod}</p>' if prod else ""
    active = "1" if quotes else "0"
    base = B._base_sport(row["sport"])
    return f'''<article class="rule-card" data-active="{active}" data-market="{B.esc(base)}" data-source="{B.esc(row["name"])}" data-sport="{B.esc(row["sport"])}">
<div class="rule-rotator">
<div class="rule-face rule-front" aria-hidden="false">
<p class="rule-name"><b>{B.esc(name)}</b>{tag}</p>
{stage}<p class="rule-status">{verdict_html(row)}</p>
<p class="rule-roi">{roi_html(row)}<span class="sm mut">ROI after fees</span></p>
<button type="button" class="rule-flip" aria-expanded="false">Open games</button>
</div>
<div class="rule-face rule-back" aria-hidden="true">
<button type="button" class="rule-flip" aria-expanded="false" tabindex="-1">Verdict</button>
{_games(quotes)}
</div>
</div>
</article>'''


def _bands(d, rows):
    """(active markets, inactive markets). Each market is (base, [(row, quotes)])."""
    groups = {}
    for row in rows:
        groups.setdefault(B._base_sport(row["sport"]), []).append(row)
    active, inactive = [], []
    for base, rs in groups.items():
        ranked = [row for _rank, _prov, row in B.rank_rows(rs)]
        act, ina = [], []
        for row in ranked:
            quotes = open_quotes(d, row["name"], row["sport"])
            (act if quotes else ina).append((row, quotes))
        if act:
            act.sort(key=lambda item: (_soonest(item[1]) or _FAR, item[0]["name"], item[0]["sport"]))
            active.append((base, act))
        if ina:
            inactive.append((base, ina))
    active.sort(key=lambda item: (
        _soonest([q for _row, qs in item[1] for q in qs]) or _FAR,
        -sum(row["a"]["n"] for row, _qs in item[1]),
        S.SPORTS.get(item[0], item[0]),
    ))
    inactive.sort(key=lambda item: (
        -sum(row["a"]["n"] for row, _qs in item[1]),
        S.SPORTS.get(item[0], item[0]),
    ))
    return active, inactive


def _band(title, key, markets):
    if not markets:
        return ""
    blocks = []
    for base, items in markets:
        cards = "".join(_card(row, quotes) for row, quotes in items)
        blocks.append(
            f'<div class="rule-market" data-market="{B.esc(base)}">'
            f'<h3>{B.esc(_market_name(base))}</h3>'
            f'<div class="rule-grid">{cards}</div>'
            f'</div>')
    return (f'<div class="rule-band" data-band="{key}">'
            f'<h3 class="rule-band-title">{B.esc(title)}</h3>'
            f'{"".join(blocks)}</div>')


def render(d, rows, now=None):
    """Card grid for the Soccer lanes section. `now` is the page clock.

    Rules with an open bet are active. Inside that band, a game inside the
    next 48 hours is ordered ahead of a pick whose kickoff is further out.
    """
    del now  # ordering reads each open bet's own start, not a second clock
    if not rows:
        return '<div class="note">No soccer lane has a record yet.</div>'
    active, inactive = _bands(d, rows)
    note = ('<div class="note">Flip a card for the games that rule has open. '
            'The front is the verdict and the ROI after fees. A rule with a pick in, '
            'or a game inside 48 hours, sits above a rule with nothing open.</div>')
    cards = _band("Active", "active", active) + _band("Inactive", "inactive", inactive)
    # The by-competition tables and the definitions stay, folded, under the cards.
    # They are the same Sandbox blocks the lane section already showed.
    extra = B.league_panel(d, rows) + B.definitions(rows)
    return note + cards + extra
