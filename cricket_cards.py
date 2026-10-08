#!/usr/bin/env python3
"""The Cricket page body. Presentation only, and only the Cricket page asks for it.

Four stat tiles, one flat list of picks grouped by day, one rules table, and
the venue note folded away: the Tennis page's shape, built with the Tennis
page's own helpers so the two cannot drift apart. The record, verdict and ROI
on every row are the Sandbox row's own figures, the same strings the Sandbox
table prints. Nothing here grades, settles, or chooses a bet.

Cricket lane records do not use the tennis tour keep-set, so a refused-tour
check is not applied. A repeat city-day quote is left out, the same exclusion
the lane's open count already uses. A lane reset clock is already inside the
row's verdict and ROI, and the picks listed under a rule are the bets its
record counts.
"""
import datetime
from datetime import timedelta, timezone

import fmt
import sport_ui as UI
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
    "settled": ("Settled on price", "is-price"),
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
    """(word, class). W / L / Void / Settled on price once settled; in play
    from the start; upcoming before it."""
    found = _SETTLED_STATES.get(q.get("status"))
    if found:
        return found
    ko = _kickoff(q)
    if ko is not None and ko <= now:
        return "in play", "is-live"
    return "upcoming", "is-next"


# ------------------------------------------------------------------ the picks list
def active_rows(rows, d):
    """(active, inactive). A rule is active once it has a settled or an open bet."""
    act, ina = [], []
    for row in rows:
        fired = bool(row["a"].get("n")) or bool(open_quotes(d, row["name"], row["sport"], row))
        (act if fired else ina).append(row)
    return act, ina


def pick_rows(d, rows, now):
    """Every open pick, plus the settled ones that started in the last SETTLED_DAYS
    days, as (row, quote). Days run newest first; inside a day, by start time."""
    now = _as_utc(now)
    floor = now - timedelta(days=SETTLED_DAYS)
    out = []
    for row in rows:
        out.extend((row, q) for q in open_quotes(d, row["name"], row["sport"], row))
        for q in settled_quotes(d, row):
            ko = _kickoff(q)
            if ko is not None and ko >= floor:
                out.append((row, q))

    def _key(rq):
        ko = _kickoff(rq[1])
        day = fmt.chicago(ko).date() if ko is not None else None
        return (day is None, -(day.toordinal() if day else 0), ko or _FAR, str(rq[1].get("id") or ""))
    out.sort(key=_key)
    return out


def _pick_html(row, q, now):
    ko = _kickoff(q)
    when = fmt.clock(ko) if ko is not None else "time TBC"
    word, cls = state_of(q, now)
    prod = ' <span class="tn-prod">Production</span>' if row.get("prod") else ""
    venue = venue_of(q)
    venue_html = f' <span class="tn-venue">{B.esc(venue)}</span>' if venue else ""
    price = fmt.cents(q.get("price")) if q.get("price") is not None else "—"
    return (
        f'<div class="tn-pick {cls}" data-source="{B.esc(row["name"])}" data-sport="{B.esc(row["sport"])}">'
        f'<span class="tn-time">{B.esc(when)}</span>'
        f'<span class="tn-match">{B.safe_href(S.market_url(q), match_label(q))}</span>'
        f'<span class="tn-pos"><b>{B.esc(pick_label(q))}</b></span>'
        f'<span class="tn-price">{B.esc(price)}</span>'
        f'<span class="tn-rule">{B.esc(rule_name(row))}{prod}{venue_html}</span>'
        f'<span class="tn-state {cls}">{B.esc(word)}</span>'
        f'</div>')


def picks_html(d, rows, now):
    """The Matches section body: day headers and one line per pick."""
    now = _as_utc(now)
    today = fmt.chicago(now).date()
    picks = pick_rows(d, rows, now)
    blocks, day = [], object()
    for row, q in picks:
        ko = _kickoff(q)
        key = fmt.chicago(ko).date() if ko is not None else None
        if key != day:
            day = key
            label = _day_label(key, today) if key is not None else "Time unconfirmed"
            blocks.append([f'<div class="tn-day">{B.esc(label)}</div>'])
        blocks[-1].append(_pick_html(row, q, now))
    parts = [f'<div class="tn-dayblock">{"".join(block)}</div>' for block in blocks]
    html = ""
    if not any(q.get("status") == "open" for _row, q in picks):
        nxt = next_check(now)
        tail = f" · next check {fmt.when(nxt)}" if nxt is not None else ""
        html += f'<p class="tn-empty">No open pick{B.esc(tail)}</p>'
    if parts:
        html += f'<div class="tn-picks">{"".join(parts)}</div>'
    return html


# ------------------------------------------------------------------ the rules table
def _recent_html(d, row, now):
    live = open_quotes(d, row["name"], row["sport"], row)
    done = settled_quotes(d, row)[:RECENT_LIMIT]
    if not live and not done:
        return '<p class="sm mut tn-none">No pick logged yet.</p>'
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
            bits.append(f'<span class="tn-venue">{B.esc(venue)}</span>')
        bits.append(f'<span class="tn-state {cls}">{B.esc(word)}</span>')
        items.append(f'<li>{" · ".join(bits)}</li>')
    return f'<ul class="tn-recent">{"".join(items)}</ul>'


def roi_cell(row):
    """The ROI beside its sample, so a tiny sample cannot read as a headline:
    '+522.8% on 4 bets'. Nothing settled is a dash."""
    a = row["a"]
    n = a.get("n") or 0
    if not n:
        return "—"
    return f'{roi_html(row)}<span class="tn-roi-n sm mut"> on {n} bet{"s" if n != 1 else ""}</span>'


def _rule_row(d, row, now):
    name = rule_name(row)
    badges = ' <span class="sig y">PRODUCTION</span>' if row.get("prod") else ""
    note = (row["meta"].get("note") or "").strip()
    note_html = f'<p class="tn-def sm mut">{B.esc(note)}</p>' if note else ""
    open_n = len(open_quotes(d, row["name"], row["sport"], row))
    return (
        f'<tr data-source="{B.esc(row["name"])}" data-sport="{B.esc(row["sport"])}">'
        f'<td><details class="tn-rule"><summary><b>{B.esc(name)}</b>{badges}</summary>'
        f'{note_html}{_recent_html(d, row, now)}</details></td>'
        f'<td>{B.esc(venue_name(d, row))}</td>'
        f'<td class="num">{B.esc(record_text(row["a"]))}</td>'
        f'<td class="num">{roi_cell(row)}</td>'
        f'<td>{verdict_html(row)}</td>'
        f'<td class="num">{open_n or "—"}</td></tr>')


_sort_key = TN._sort_key
_HEAD = TN._HEAD


def _table(d, rows, now):
    body = "".join(_rule_row(d, row, now) for row in rows)
    return f'<div class="tbl"><table class="tn-rules">{_HEAD}{body}</table></div>'


def rules_html(d, rows, now):
    """One table, Production first then by ROI; the never-fired rules behind a toggle."""
    now = _as_utc(now)
    act, ina = active_rows(rows, d)
    act = sorted(act, key=_sort_key)
    ina = sorted(ina, key=_sort_key)
    if not rows:
        return '<div class="note">No cricket rule has a record yet.</div>'
    html = _table(d, act, now) if act else '<div class="note">No cricket rule has fired yet.</div>'
    if ina:
        n = len(ina)
        html += UI.disclosure(f"Show {n} inactive rule{'s' if n != 1 else ''}",
                              _table(d, ina, now), css="historical tn-inactive")
    return html


# ------------------------------------------------------------------ tiles and the venue fold
def tiles_html(d, rows):
    """Open picks · active rules · record · ROI after fees, across the rules with a record."""
    act, _ina = active_rows(rows, d)
    open_n = sum(len(open_quotes(d, r["name"], r["sport"], r)) for r in rows)
    n = sum(r["a"].get("n") or 0 for r in act)
    won = sum(r["a"].get("won") or 0 for r in act)
    if n:
        # Flat stakes, so the n-weighted mean of each rule's ROI is the pooled ROI.
        roi = sum((r["a"].get("roi_fee") or 0) * (r["a"].get("n") or 0) for r in act) / n
        klass = "mut" if n < B.MIN_N else fmt.tone(roi, ".1f", 100)
        roi_cell_html = f'<b class="{klass}">{B.pct(roi, sign=True)}</b>'
        rec = f"{won}–{n - won}"
    else:
        roi_cell_html = '<b class="mut">—</b>'
        rec = "—"
    return (
        '<div class="tiles tn-tiles">'
        f'<div class="tile"><b>{open_n}</b><span>open picks</span></div>'
        f'<div class="tile"><b>{len(act)}</b><span>active rules</span></div>'
        f'<div class="tile"><b>{rec}</b><span>record · rules with a record</span></div>'
        f'<div class="tile">{roi_cell_html}<span>ROI after fees</span></div>'
        '</div>')


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


def system_html(d, idle_html=""):
    """The venue line and the grading note, closed by default."""
    return f'''<section id="system" class="tn-system">
<details><summary><b class="mut">{B.esc(listing_line(d))}</b><small>venue note</small></summary>
<div>
<p class="sm">Polymarket US lists the match-winner markets; it logs prices and holds no record of its own, so it has no row in the rules table, and the counts are what the last run stored.</p>
<p class="sm">Every pick is logged before the start at the price available then, settled on the real result at a flat ${int(T.STAKE)} stake, and judged after fees against the price it paid.</p>
{idle_html}
</div>
</details>
</section>'''


def render(d, rows, now=None, idle_html=""):
    """The whole page body under the shared header. `now` is the page clock."""
    now = _as_utc(now or datetime.datetime.now(timezone.utc))
    return f'''<h1>Cricket</h1>
<p class="lede">Match-winner picks and the rules that fire them · times CT</p>
{tiles_html(d, rows)}
<section id="rules" class="tn-section">
<h2>Rules</h2>
<p class="sm mut">Production first, then by ROI after fees; open a row for the registered definition and its recent picks.</p>
{rules_html(d, rows, now)}
</section>
<section id="matches" class="tn-section">
<h2>Matches</h2>
<p class="sm mut">Every open pick, plus the last {SETTLED_DAYS} days of settled ones, newest day first.</p>
{picks_html(d, rows, now)}
</section>
{system_html(d, idle_html)}'''
