#!/usr/bin/env python3
"""Soccer rule cards. Presentation only, and only the Soccer page asks for them.

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
import sport_ui as UI
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


def _market_name(base, fam="Soccer"):
    """The market-fold heading. Same words `market_folds` prints."""
    full = S.SPORTS.get(base, base)
    return "Match winner" if full == fam else full.split(" · ")[-1]


def _fixture_label(q):
    # Soccer market labels append the outcome after the match's team names.
    return S.display_label(q).split(":", 1)[0].strip()


def _fixture_key(q):
    label, kickoff = _fixture_label(q), _kickoff(q)
    if label and kickoff is not None:
        return ("fixture", " ".join(label.casefold().split()),
                str(S.display_league(q) or "").casefold(), kickoff)
    # Without a match name and verified instant, keep distinct markets separate.
    return ("market", str(q.get("market_id") or q.get("id") or ""),
            str(q.get("start") or ""))


def _fixture_rows(d, rows, now):
    """Upcoming/open fixtures, grouped across rules so one match is one row."""
    by_key = {}
    for row in rows:
        open_live = open_quotes(d, row["name"], row["sport"])
        upcoming = upcoming_quotes(d, row["name"], row["sport"], now)
        for q in open_live + upcoming:
            key = _fixture_key(q)
            rec = by_key.setdefault(key, {"q": q, "rules": []})
            rec["rules"].append((row, q))
    out = list(by_key.values())
    out.sort(key=lambda rec: (
        _kickoff(rec["q"]) or _FAR,
        str(rec["q"].get("label") or rec["q"].get("market_id") or "")))
    return out


def _fixture_rule_chip(row, q):
    meta = row["meta"]
    label = meta["label"].split(" (")[0]
    sfx = B._scope(row["sport"])
    scope = S.SCOPE_LABEL[sfx] if sfx else ""
    side = B._side(q) if q.get("bet") else ""
    bits = [label, _market_name(B._base_sport(row["sport"]))]
    if scope:
        bits.append(scope)
    if side:
        bits.append(str(side))
    text = " · ".join(bits)
    stage = '<span class="soccer-prod">Production</span>' if row.get("prod") else ""
    link = B.safe_href(S.market_url(q), text)
    return f'<span class="soccer-rule-chip">{link}{stage}</span>'


def _fixture_card(rec):
    q = rec["q"]
    label = _fixture_label(q)
    when = _kick_label(q)
    link = B.safe_href(S.market_url(q), label)
    chips = "".join(_fixture_rule_chip(row, quote) for row, quote in rec["rules"])
    open_count = sum(1 for _row, quote in rec["rules"] if quote.get("bet"))
    state = "Pick in" if open_count else "Watching"
    state_cls = "is-live" if open_count else "is-watch"
    return (
        f'<article class="soccer-fixture">'
        f'<div class="soccer-fixture-time">{B.esc(when)}</div>'
        f'<div class="soccer-fixture-main"><div class="soccer-fixture-title">{link}</div>'
        f'<div class="soccer-fixture-rules">{chips}</div></div>'
        f'<span class="soccer-fixture-state {state_cls}">{state}</span>'
        f'</article>'
    )


def match_center(d, rows, now):
    fixtures = _fixture_rows(d, rows, now)
    today = []
    upcoming = []
    past = []
    other = []
    now_ct = fmt.chicago(now)
    now = now_ct.astimezone(timezone.utc)
    today_key = now_ct.date()
    for rec in fixtures:
        ko = _kickoff(rec["q"])
        if ko is None or ko > now + HORIZON:
            other.append(rec)
        elif ko <= now:
            past.append(rec)
        elif fmt.chicago(ko).date() == today_key:
            today.append(rec)
        else:
            upcoming.append(rec)
    prod = [r for r in rows if r.get("prod")]
    prod_chips = "".join(
        f'<span class="soccer-prod-rule"><b>{B.esc(r["meta"]["label"].split(" (")[0])}</b>'
        f'<small>{B.esc(S.SPORTS.get(r["sport"], r["sport"]))}</small></span>'
        for r in prod)
    today_html = "".join(_fixture_card(x) for x in today) or '<div class="note">No tracked fixture today.</div>'
    upcoming_html = "".join(_fixture_card(x) for x in upcoming[:12]) or '<div class="note">No tracked fixture in the next 48 hours.</div>'
    more = (f'<p class="sm mut">{len(upcoming) - 12} more upcoming fixtures not shown.</p>'
            if len(upcoming) > 12 else "")
    past_html = '<div class="soccer-fixture-list">' + "".join(_fixture_card(x) for x in past[:3]) + '</div>'
    if len(past) > 3:
        past_html += UI.disclosure("More open picks", '<div class="soccer-fixture-list">' +
                                   "".join(_fixture_card(x) for x in past[3:]) + '</div>', len(past) - 3)
    return f'''<div class="soccer-desk">
<div class="soccer-desk-head">
<div><span class="soccer-kicker">Match center</span><h2>Today & upcoming</h2></div>
<nav class="soccer-local-nav" aria-label="Soccer sections">
<a href="#today">Today</a><a href="#upcoming">Upcoming</a><a href="#in-play">Past kickoff</a><a href="#rules">Rules</a><a href="#health">System</a>
</nav>
</div>
<section id="today" class="soccer-fixture-block">
<div class="soccer-block-head"><h3>Today</h3><span>{len(today)} fixtures</span></div>
<div class="soccer-fixture-list">{today_html}</div>
</section>
<section id="upcoming" class="soccer-fixture-block">
<div class="soccer-block-head"><h3>Next 48 hours</h3><span>{len(upcoming)} fixtures</span></div>
<div class="soccer-fixture-list">{upcoming_html}</div>{more}
</section>
<section class="soccer-production">
<div class="soccer-block-head"><h3>Production rules</h3><span>{len(prod)} live</span></div>
<div class="soccer-prod-strip">{prod_chips or '<span class="mut">None in Production.</span>'}</div>
</section>
<section id="in-play" class="soccer-fixture-block">
<div class="soccer-block-head"><h3>Open picks past kickoff</h3><span>{len(past)} fixtures</span></div>
{past_html if past else '<p class="sm mut">No open pick past kickoff.</p>'}
</section>
<section id="other-open" class="soccer-fixture-block">
{UI.disclosure("Later / time unconfirmed", '<div class="soccer-fixture-list">' + "".join(_fixture_card(x) for x in other) + '</div>', str(len(other)) + " fixtures") if other else '<p class="sm mut">No other open pick.</p>'}
</section>

</div>'''


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


def _category(base):
    if base in ("soccer_team1", "soccer_team2"):
        return "Team totals"
    if base == "soccer_btts":
        return "BTTS"
    if base == "soccer_p05":
        return "Double chance / +0.5"
    if base in ("soccer_o15", "soccer_o25", "soccer_u35"):
        return "Goals"
    return "Match winner" if base == "soccer" else _market_name(base)


def _band(title, key, markets):
    if not markets:
        return ""
    groups = {}
    for base, items in markets:
        groups.setdefault(_category(base), []).extend(items)
    blocks = []
    order = ("Goals", "BTTS", "Team totals", "Double chance / +0.5", "Match winner")
    for category in sorted(groups, key=lambda x: (order.index(x) if x in order else len(order), x)):
        items = groups[category]
        production = [(r, qs) for r, qs, _ in items if key == "active" and r.get("prod")]
        sandbox = [(r, qs) for r, qs, _ in items if not (key == "active" and r.get("prod"))]
        live = "".join(_card(r, qs, True) for r, qs in production)
        research = "".join(_card(r, qs, key == "active") for r, qs in sandbox)
        body = (f'<div class="rule-grid">{live}</div>' if live else "")
        if research:
            body += UI.disclosure("Sandbox rules" if key == "active" else "Inactive rules",
                                  f'<div class="rule-grid">{research}</div>', len(sandbox))
        blocks.append(f'<div class="rule-market"><h3>{B.esc(category)}</h3>{body}</div>')
    content = "".join(blocks)
    if key == "inactive":
        content = UI.disclosure("Inactive rules", content,
                               sum(len(items) for _, items in markets), css="historical")
    return f'<div class="rule-band" data-band="{key}">{content}</div>'


def render(d, rows, now=None):
    """Card grid for the Soccer lanes section. `now` is the page clock.

    A rule is active with an open bet, or with a stored fixture kicking off
    within 48 hours and no stake yet. Inside that band, the sooner kickoff
    comes first.
    """
    now = now or datetime.datetime.now(timezone.utc)
    active, inactive = _bands(d, rows, now)
    note = ''
    if not rows:
        note = '<div class="note">No soccer lane has a record yet.</div>'
    cards = _band("Active", "active", active) + _band("Inactive", "inactive", inactive)
    extra = B.league_panel(d, rows) + B.definitions(rows)
    return (match_center(d, rows, now)
            + '<section id="rules" class="soccer-rule-desk"><div class="soccer-block-head"><h3>Rules</h3>'
              '<span>active first</span></div>'
            + note + cards + extra + '</section>')
