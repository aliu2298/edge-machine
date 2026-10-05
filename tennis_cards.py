#!/usr/bin/env python3
"""Tennis rule cards. Presentation only, and only the Tennis page asks for them.

Each Sandbox lane row becomes a card. The front is that row's verdict and its
ROI after fees, the same strings the table cell already uses. The back is the
open bets on that rule, soonest first, four of them. A rule is active when it
has an open bet, or when the tracker has already stored a fixture for it whose
kickoff is after the page clock and at most 48 hours ahead, even with no stake
on that game yet. A kickoff inside the next 24 hours counts; one past 48 hours
does not. Inactive rules sit below. Nothing here grades, settles, or chooses a bet.
"""
import datetime
from datetime import timedelta, timezone

import fmt
import sandbox_build as B
import sandbox_sources as S
import sandbox_track as T

# Upcoming fixture cutoff: after the page clock and at most 48 hours ahead.
# That is the outer edge of the brief's "24–48 hours". A kickoff inside the
# next 24 hours counts. A kickoff past 48 hours does not. An open bet is
# active either way.
HORIZON = timedelta(hours=48)
# The back lists this many open games. The rest of the open count stays a number.
OPEN_LIMIT = 4
_FAR = datetime.datetime.max.replace(tzinfo=timezone.utc)
FAMILY = "Tennis"


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


def upcoming_quotes(d, name, sport, now):
    """Fixtures this rule has already been shown, with no open bet on them.

    The tracker stores a quote when it sees the game. `bet` false and status
    open is that row with no stake yet. The kickoff is the quote's own start.
    Kept when it is still ahead of `now` and at most `HORIZON` (48 hours) out.
    Open bets are not repeated here; `open_quotes` already lists those.
    """
    if now is None:
        return []
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    end = now + HORIZON
    live = []
    for q in d.get("quotes") or []:
        if q.get("source") != name or q.get("sport") != sport:
            continue
        if q.get("bet") or q.get("status") != "open":
            continue
        if T.climate_excluded(q) or S.tennis_refused_row(q):
            continue
        ko = _kickoff(q)
        if ko is not None and now < ko <= end:
            live.append(q)
    live.sort(key=lambda q: (q.get("start") or "", q.get("sport") or "", str(q.get("id") or "")))
    return live


def _market_name(base, fam=FAMILY):
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


def _card(row, quotes, active):
    meta = row["meta"]
    name = meta["label"].split(" (")[0]
    sfx = B._scope(row["sport"])
    tag = f' <span class="sig w">{B.esc(S.SCOPE_LABEL[sfx].upper())}</span>' if sfx else ""
    prod = '<span class="sig y">PRODUCTION</span>' if row.get("prod") else ""
    stage = f'<p class="rule-stage">{prod}</p>' if prod else ""
    active = "1" if active else "0"
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


def _bands(d, rows, now):
    """(active markets, inactive markets). Each market is (base, [(row, open quotes, kickoff)]).

    Active: at least one open bet, or a fixture already stored for the rule
    whose kickoff is inside the next 48 hours. The sort key is the soonest of
    those kickoffs.
    """
    groups = {}
    for row in rows:
        groups.setdefault(B._base_sport(row["sport"]), []).append(row)
    active, inactive = [], []
    for base, rs in groups.items():
        ranked = [row for _rank, _prov, row in B.rank_rows(rs)]
        act, ina = [], []
        for row in ranked:
            quotes = open_quotes(d, row["name"], row["sport"])
            upcoming = upcoming_quotes(d, row["name"], row["sport"], now)
            kick = _soonest(quotes) or _soonest(upcoming)
            (act if quotes or upcoming else ina).append((row, quotes, kick))
        if act:
            act.sort(key=lambda item: (item[2] or _FAR, item[0]["name"], item[0]["sport"]))
            active.append((base, act))
        if ina:
            inactive.append((base, ina))
    active.sort(key=lambda item: (
        min((kick for _row, _qs, kick in item[1] if kick is not None), default=_FAR),
        -sum(row["a"]["n"] for row, _qs, _kick in item[1]),
        S.SPORTS.get(item[0], item[0]),
    ))
    inactive.sort(key=lambda item: (
        -sum(row["a"]["n"] for row, _qs, _kick in item[1]),
        S.SPORTS.get(item[0], item[0]),
    ))
    return active, inactive


def _band(title, key, markets):
    if not markets:
        return ""
    blocks = []
    for base, items in markets:
        cards = "".join(_card(row, quotes, key == "active")
                        for row, quotes, _kick in items)
        blocks.append(
            f'<div class="rule-market" data-market="{B.esc(base)}">'
            f'<h3>{B.esc(_market_name(base))}</h3>'
            f'<div class="rule-grid">{cards}</div>'
            f'</div>')
    return (f'<div class="rule-band" data-band="{key}">'
            f'<h3 class="rule-band-title">{B.esc(title)}</h3>'
            f'{"".join(blocks)}</div>')


def render(d, rows, now=None):
    """Card grid for the Tennis lanes section. `now` is the page clock.

    A rule is active with an open bet, or with a stored fixture kicking off
    within 48 hours and no stake yet. Inside that band, the sooner kickoff
    comes first.
    """
    now = now or datetime.datetime.now(timezone.utc)
    if not rows:
        return '<div class="note">No tennis lane has a record yet.</div>'
    active, inactive = _bands(d, rows, now)
    note = ('<div class="note">Flip a card for the games that rule has open. '
            'The front is the verdict and the ROI after fees. A rule with a pick in, '
            'or a fixture kicking off within 48 hours, sits above the rest.</div>')
    cards = _band("Active", "active", active) + _band("Inactive", "inactive", inactive)
    # Definitions stay folded under the cards. The soccer by-competition panel
    # does not: it ignores the lane reset clock and the refused-tour filter,
    # so its totals are not the records on the cards.
    extra = B.definitions(rows)
    return note + cards + extra
