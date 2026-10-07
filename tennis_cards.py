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


def _fixture_label(q):
    return S.display_label(q).split(":", 1)[0].strip()


def _fixture_key(q):
    label, kickoff = _fixture_label(q), _kickoff(q)
    if label and kickoff is not None:
        return ("fixture", " ".join(label.casefold().split()),
                _tour_label(q).casefold(), kickoff)
    return ("market", str(q.get("market_id") or q.get("id") or ""),
            str(q.get("start") or ""))


def _tour_label(q):
    tier = str(q.get("tier") or "").strip()
    league = str(q.get("league") or "").strip()
    raw = tier or league
    if not raw:
        return ""
    low = raw.lower()
    if "wta" in low and "double" in low:
        return "WTA Doubles"
    if "atp" in low:
        return "ATP"
    if "utr" in low:
        return "UTR"
    if "wta" in low:
        return "WTA"
    return raw


def _match_rows(d, rows, now):
    """Single-match tennis only; combo products are rendered separately."""
    singles = [r for r in rows if B._base_sport(r["sport"]) == "tennis"]
    by_key = {}
    for row in singles:
        for q in open_quotes(d, row["name"], row["sport"]) + upcoming_quotes(d, row["name"], row["sport"], now):
            key = _fixture_key(q)
            rec = by_key.setdefault(key, {"q": q, "rules": []})
            rec["rules"].append((row, q))
    found = list(by_key.values())
    found.sort(key=lambda rec: (_kickoff(rec["q"]) or _FAR,
                                str(rec["q"].get("label") or rec["q"].get("market_id") or "")))
    return found


def _match_rule(row, q):
    label = row["meta"]["label"].split(" (")[0]
    side = B._side(q) if q.get("bet") else ""
    scope = B._scope(row["sport"])
    bits = [label, _market_name(B._base_sport(row["sport"]))]
    if scope:
        bits.append(S.SCOPE_LABEL[scope])
    if side:
        bits.append(str(side))
    text = " · ".join(bits)
    stage = '<span class="tennis-prod">Production</span>' if row.get("prod") else ""
    return f'<span class="tennis-rule-chip">{B.safe_href(S.market_url(q), text)}{stage}</span>'


def _match_card(rec):
    q = rec["q"]
    label = _fixture_label(q)
    when = _kick_label(q)
    tour = _tour_label(q)
    link = B.safe_href(S.market_url(q), label)
    chips = "".join(_match_rule(row, quote) for row, quote in rec["rules"])
    has_bet = any(quote.get("bet") for _row, quote in rec["rules"])
    state = "Pick in" if has_bet else "Watching"
    state_cls = "is-live" if has_bet else "is-watch"
    tour_html = f'<span class="tennis-tour">{B.esc(tour)}</span>' if tour else ""
    return (
        f'<article class="tennis-match">'
        f'<div class="tennis-match-time">{B.esc(when)}{tour_html}</div>'
        f'<div class="tennis-match-main"><div class="tennis-match-title">{link}</div>'
        f'<div class="tennis-match-rules">{chips}</div></div>'
        f'<span class="tennis-match-state {state_cls}">{state}</span>'
        f'</article>'
    )


def _combo_summary(row, quotes):
    a = row["a"]
    name = row["meta"]["label"].split(" (")[0]
    rec = f'{a["won"]}–{max(0, a["n"] - a["won"])}' if a.get("n") else "—"
    open_n = len(quotes)
    return (
        f'<article class="tennis-combo-card">'
        f'<div><span class="tennis-combo-kicker">{B.esc(_market_name(B._base_sport(row["sport"])))}</span>'
        f'<h4>{B.esc(name)}</h4></div>'
        f'<div class="tennis-combo-stat"><b>{B.esc(rec)}</b><span>record</span></div>'
        f'<div class="tennis-combo-stat"><b>{roi_html(row)}</b><span>ROI</span></div>'
        f'<div class="tennis-combo-stat"><b>{open_n}</b><span>open</span></div>'
        f'</article>'
    )


def match_center(d, rows, now):
    matches = _match_rows(d, rows, now)
    now_ct = fmt.chicago(now)
    today_key = now_ct.date()
    now = now_ct.astimezone(timezone.utc)
    today, upcoming, past, other = [], [], [], []
    for rec in matches:
        ko = _kickoff(rec["q"])
        if ko is None or ko > now + HORIZON:
            other.append(rec)
        elif ko <= now:
            past.append(rec)
        elif fmt.chicago(ko).date() == today_key:
            today.append(rec)
        else:
            upcoming.append(rec)

    combo_rows = [r for r in rows if B._base_sport(r["sport"]) in ("tennis_combo", "tennis_pmcombo")]
    combo_rows = [r for _rank, _prov, r in B.rank_rows(combo_rows)]
    combo_html = "".join(_combo_summary(r, open_quotes(d, r["name"], r["sport"])) for r in combo_rows)

    today_html = "".join(_match_card(x) for x in today) or '<div class="note">No tracked tennis match today.</div>'
    upcoming_html = "".join(_match_card(x) for x in upcoming[:12]) or '<div class="note">No tracked tennis match in the next 48 hours.</div>'
    more = (f'<p class="sm mut">{len(upcoming) - 12} more upcoming matches not shown.</p>'
            if len(upcoming) > 12 else "")
    return f'''<div class="tennis-desk">
<div class="tennis-desk-head">
<div><span class="tennis-kicker">Match center</span><h2>Today & upcoming</h2></div>
<nav class="tennis-local-nav" aria-label="Tennis sections">
<a href="#today">Today</a><a href="#upcoming">Upcoming</a><a href="#in-play">Past kickoff</a><a href="#combos">Combos</a><a href="#rules">Rules</a><a href="#system">System</a>
</nav>
</div>
<section id="today" class="tennis-match-block">
<div class="tennis-block-head"><h3>Today</h3><span>{len(today)} matches</span></div>
<div class="tennis-match-list">{today_html}</div>
</section>
<section id="upcoming" class="tennis-match-block">
<div class="tennis-block-head"><h3>Next 48 hours</h3><span>{len(upcoming)} matches</span></div>
<div class="tennis-match-list">{upcoming_html}</div>{more}
</section>
<section id="in-play" class="tennis-match-block">
<div class="tennis-block-head"><h3>In play / past kickoff</h3><span>{len(past)} matches</span></div>
<div class="tennis-match-list">{"".join(_match_card(x) for x in past) or '<div class="note">No open pick past kickoff.</div>'}</div>
</section>
<section id="other-open" class="tennis-match-block">
<div class="tennis-block-head"><h3>Later / time unconfirmed</h3><span>{len(other)} matches</span></div>
<div class="tennis-match-list">{"".join(_match_card(x) for x in other) or '<div class="note">No other open pick.</div>'}</div>
</section>
<section id="combos" class="tennis-combos">
<div class="tennis-block-head"><h3>Combo baskets</h3><span>{len(combo_rows)} rules</span></div>
<div class="tennis-combo-grid">{combo_html or '<div class="note">No combo lane has a record yet.</div>'}</div>
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
    active, inactive = _bands(d, rows, now)
    note = ('<div class="note">Match center first. Single-match tennis is separated '
            'from combo products; the full rule record stays below.</div>')
    cards = _band("Active", "active", active) + _band("Inactive", "inactive", inactive)
    extra = B.definitions(rows)
    if not rows:
        note += '<div class="note">No tennis lane has a record yet.</div>'
    return (match_center(d, rows, now)
            + '<section id="rules" class="tennis-rule-desk"><div class="tennis-block-head"><h3>Rules</h3>'
              '<span>active first</span></div>'
            + note + cards + extra + '</section>')
