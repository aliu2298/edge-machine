#!/usr/bin/env python3
"""The Tennis page body. Presentation only, and only the Tennis page asks for it.

Four stat tiles, one rules table, one flat list of picks grouped by day, and
the venue note folded away. The record, verdict and ROI on every row are the
Sandbox row's own figures, the same strings the Sandbox table prints, so this
page cannot disagree with the Sandbox about the same pair. Nothing here grades,
settles, or chooses a bet.
"""
import datetime
import os
import re
from datetime import timedelta, timezone

import fmt
import sport_ui as UI
import sandbox_build as B
import sandbox_sources as S
import sandbox_track as T

FAMILY = "Tennis"
ROOT = os.path.dirname(os.path.abspath(__file__))
# The tracker's own schedule. The empty state reads the next firing from it.
TRACKER_WORKFLOW = os.path.join(ROOT, ".github", "workflows", "sandbox-tracker.yml")
# Settled picks listed under an expanded rule, newest first.
RECENT_LIMIT = 5
_FAR = datetime.datetime.max.replace(tzinfo=timezone.utc)

COMBO_SPORTS = ("tennis_combo", "tennis_pmcombo")
# Where a rule's contracts trade. A basket lane is one venue by construction;
# the single-match rule is read from the venues of its own bets.
SPORT_VENUE = {"tennis_combo": "Kalshi", "tennis_pmcombo": "Polymarket US"}
VENUE_NAMES = {"kalshi": "Kalshi", "kalshi_binary": "Kalshi", "polymarket_us": "Polymarket US"}
# The one registered label too long for a table cell. Every other rule name is
# its registered label with the family word and the parenthesis dropped.
SHORT_NAMES = {"tennis_fav_band_3h": "Favourite band · within 3h of the start"}

_CRON = re.compile(r'cron:\s*"(\d{1,2})\s+(\S+)\s+\*\s+\*\s+\*"')


# ------------------------------------------------------------------ Sandbox strings
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


def record_text(a):
    """'23–8', or '12–8, 6 no result' where bets were paid out at a price; an em
    dash with nothing settled. The ledger's own words (sandbox_track.record_text)."""
    return T.record_text(a)


# ------------------------------------------------------------------ the rows a rule owns
def _on_clock(q, row):
    """False for a bet logged before this lane's reset clock. Those stay on file only.

    The clock is the stage row's, read the way the Sandbox's If-faded cell reads
    it, so the picks listed here are the bets the row's record counts.
    """
    clock = S.tour_clock_since(since=row.get("since"))
    if clock is None:
        return True
    return str(q.get("logged") or "") >= clock


def _kept(q, row):
    return (q.get("source") == row["name"] and q.get("sport") == row["sport"]
            and q.get("bet") and not T.climate_excluded(q)
            and not S.tennis_refused_row(q) and _on_clock(q, row))


def open_quotes(d, name, sport, row=None):
    """Open bets for one rule, soonest first. The same rows the open count uses."""
    row = row or dict(name=name, sport=sport)
    live = [q for q in T.bet_rows(d) if q.get("status") == "open" and _kept(q, row)]
    live.sort(key=lambda q: (q.get("start") or "", str(q.get("id") or "")))
    return live


def settled_quotes(d, row):
    """Settled bets for one rule, newest first. The rows its record counts."""
    done = [q for q in T.bet_rows(d) if q.get("status") in ("won", "lost") and _kept(q, row)]
    done.sort(key=lambda q: (q.get("start") or "", str(q.get("id") or "")), reverse=True)
    return done


def _kickoff(q):
    raw = q.get("start")
    if not raw:
        return None
    try:
        return fmt.chicago(raw).astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _as_utc(now):
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc)


# ------------------------------------------------------------------ words
def rule_name(row):
    """A rule's short name: 'Favourite band · within 3h of the start', '2-leg combo'."""
    short = SHORT_NAMES.get(row["name"])
    if short:
        return short
    label = row["meta"]["label"].split(" (")[0].strip()
    if label.startswith(FAMILY + " "):
        label = label[len(FAMILY) + 1:]
    return label


def is_combo(row):
    return B._base_sport(row["sport"]) in COMBO_SPORTS


def venue_name(d, row):
    """Kalshi, Polymarket US, or both, for the rule's own contracts."""
    fixed = SPORT_VENUE.get(B._base_sport(row["sport"]))
    if fixed:
        return fixed
    seen = {VENUE_NAMES.get(q.get("venue")) for q in T.bet_rows(d) if _kept(q, row)}
    names = sorted(n for n in seen if n)
    return " · ".join(names) if names else "—"


def _fixture_label(q):
    return S.position_label(q).split(":", 1)[0].strip()


def pick_label(q):
    """(pick, legs line). The human position: a player, or 'N-leg combo: A + B'.

    A two-leg basket names both legs in the pick. A bigger basket keeps the
    pick short and lists its legs on the muted line under it.
    """
    legs = q.get("legs") or []
    if legs:
        names = [str(leg.get("name") or "").strip() for leg in legs if leg.get("name")]
        head = f"{len(legs)}-leg combo"
        if len(legs) <= 2:
            return f"{head}: {' + '.join(names)}", ""
        return head, " · ".join(names)
    return str(B._side(q) or ""), ""


def match_label(q, row):
    """The contest, or the basket's venue when the row is a combo contract."""
    if q.get("legs") or is_combo(row):
        venue = SPORT_VENUE.get(B._base_sport(row["sport"]), "")
        return f"Combo · {venue}" if venue else "Combo"
    return _fixture_label(q)


def state_of(q, now):
    """(word, class). W / L once settled; in play from the start; upcoming before it."""
    status = q.get("status")
    if status == "won":
        return "W", "is-won"
    if status == "lost":
        return "L", "is-lost"
    ko = _kickoff(q)
    if ko is not None and ko <= now:
        return "in play", "is-live"
    return "upcoming", "is-next"


def _day_label(day, today):
    """'Today · Oct 7', 'Tomorrow · Oct 8', or 'Oct 9'."""
    text = f"{fmt._MONTHS[day.month - 1]} {day.day}"
    delta = (day - today).days
    if delta == 0:
        return f"Today · {text}"
    if delta == 1:
        return f"Tomorrow · {text}"
    return text


def _cron_hours(field):
    out = set()
    for part in field.split(","):
        step = 1
        if "/" in part:
            part, step = part.split("/", 1)
            step = int(step)
        if part == "*":
            lo, hi = 0, 23
        elif "-" in part:
            lo, hi = (int(x) for x in part.split("-", 1))
        else:
            lo = hi = int(part)
        out.update(range(lo, hi + 1, step))
    return out


def next_check(now, path=TRACKER_WORKFLOW):
    """The tracker's next scheduled firing after `now`, from its workflow crons.

    None when the workflow cannot be read or carries no cron the page understands,
    so a missing file is a shorter sentence, not a crash.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return None
    slots = []
    for m in _CRON.finditer(text):
        try:
            minute = int(m.group(1))
            hours = _cron_hours(m.group(2))
        except ValueError:
            continue
        slots.extend((h, minute) for h in hours if 0 <= h <= 23 and 0 <= minute <= 59)
    if not slots:
        return None
    now = _as_utc(now)
    base = now.replace(second=0, microsecond=0)
    best = None
    for hour, minute in slots:
        cand = base.replace(hour=hour, minute=minute)
        if cand <= now:
            cand += timedelta(days=1)
        if best is None or cand < best:
            best = cand
    return best


# ------------------------------------------------------------------ the picks list
def active_rows(rows, d):
    """(active, inactive). A rule is active once it has a settled or an open bet."""
    act, ina = [], []
    for row in rows:
        fired = bool(row["a"].get("n")) or bool(open_quotes(d, row["name"], row["sport"], row))
        (act if fired else ina).append(row)
    return act, ina


def pick_rows(d, rows, now):
    """Every open pick, plus today's settled ones, soonest first, as (row, quote)."""
    now = _as_utc(now)
    today = fmt.chicago(now).date()
    out = []
    for row in rows:
        out.extend((row, q) for q in open_quotes(d, row["name"], row["sport"], row))
        for q in settled_quotes(d, row):
            ko = _kickoff(q)
            if ko is not None and fmt.chicago(ko).date() == today:
                out.append((row, q))
    out.sort(key=lambda rq: (_kickoff(rq[1]) or _FAR, str(rq[1].get("id") or "")))
    return out


def _pick_html(row, q, now):
    ko = _kickoff(q)
    when = fmt.clock(ko) if ko is not None else "time TBC"
    pick, legs = pick_label(q)
    legs_html = f'<span class="tn-legs">{B.esc(legs)}</span>' if legs else ""
    word, cls = state_of(q, now)
    prod = ' <span class="tn-prod">Production</span>' if row.get("prod") else ""
    price = fmt.cents(q.get("price")) if q.get("price") is not None else "—"
    return (
        f'<div class="tn-pick {cls}" data-source="{B.esc(row["name"])}" data-sport="{B.esc(row["sport"])}">'
        f'<span class="tn-time">{B.esc(when)}</span>'
        f'<span class="tn-match">{B.safe_href(S.market_url(q), match_label(q, row))}</span>'
        f'<span class="tn-pos"><b>{B.esc(pick)}</b>{legs_html}</span>'
        f'<span class="tn-price">{B.esc(price)}</span>'
        f'<span class="tn-rule">{B.esc(rule_name(row))}{prod}</span>'
        f'<span class="tn-state {cls}">{B.esc(word)}</span>'
        f'</div>')


def picks_html(d, rows, now):
    """The Matches section body: day headers and one line per pick."""
    now = _as_utc(now)
    today = fmt.chicago(now).date()
    picks = pick_rows(d, rows, now)
    # One block per day, so a day header sticks only while its own picks are
    # under it and the next day's header takes its place.
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
    html = f'<div class="tn-picks">{"".join(parts)}</div>' if parts else ""
    if not any(q.get("status") == "open" for _row, q in picks):
        nxt = next_check(now)
        tail = f" · next check {fmt.when(nxt)}" if nxt is not None else ""
        html += f'<p class="tn-empty">No open pick{B.esc(tail)}</p>'
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
        pick, legs = pick_label(q)
        word, cls = state_of(q, now)
        bits = [B.esc(when), B.safe_href(S.market_url(q), match_label(q, row)), B.esc(pick)]
        if legs:
            bits.append(f'<span class="mut">{B.esc(legs)}</span>')
        if q.get("price") is not None:
            bits.append(B.esc(fmt.cents(q.get("price"))))
        bits.append(f'<span class="tn-state {cls}">{B.esc(word)}</span>')
        items.append(f'<li>{" · ".join(bits)}</li>')
    return f'<ul class="tn-recent">{"".join(items)}</ul>'


def _rule_row(d, row, now):
    name = rule_name(row)
    badges = ""
    if is_combo(row):
        badges += ' <span class="sig n">Combo</span>'
    if row.get("prod"):
        badges += ' <span class="sig y">PRODUCTION</span>'
    note = (row["meta"].get("note") or "").strip()
    note_html = f'<p class="tn-def sm mut">{B.esc(note)}</p>' if note else ""
    open_n = len(open_quotes(d, row["name"], row["sport"], row))
    return (
        f'<tr data-source="{B.esc(row["name"])}" data-sport="{B.esc(row["sport"])}">'
        f'<td><details class="tn-rule"><summary><b>{B.esc(name)}</b>{badges}</summary>'
        f'{note_html}{_recent_html(d, row, now)}</details></td>'
        f'<td>{B.esc(venue_name(d, row))}</td>'
        f'<td class="num">{B.esc(record_text(row["a"]))}</td>'
        f'<td class="num">{roi_html(row)}</td>'
        f'<td>{verdict_html(row)}</td>'
        f'<td class="num">{open_n or "—"}</td></tr>')


def _sort_key(row):
    a = row["a"]
    roi = a["roi_fee"] if a.get("n") and a.get("roi_fee") is not None else float("-inf")
    return (not row.get("prod"), -roi, -(a.get("n") or 0), row["name"])


_HEAD = ('<tr><th>Rule</th><th>Venue</th><th class="num">Record</th>'
         '<th class="num">ROI</th><th>Verdict</th><th class="num">Open</th></tr>')


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
        return '<div class="note">No tennis rule has a record yet.</div>'
    html = _table(d, act, now) if act else '<div class="note">No tennis rule has fired yet.</div>'
    if ina:
        n = len(ina)
        html += UI.disclosure(f"Show {n} inactive rule{'s' if n != 1 else ''}",
                              _table(d, ina, now), css="historical tn-inactive")
    return html


# ------------------------------------------------------------------ tiles and the venue fold
def tiles_html(d, rows):
    """Open picks · active rules · record · ROI after fees, across the active rules."""
    act, _ina = active_rows(rows, d)
    open_n = sum(len(open_quotes(d, r["name"], r["sport"], r)) for r in rows)
    n = sum(r["a"].get("n") or 0 for r in act)
    won = sum(r["a"].get("won") or 0 for r in act)
    if n:
        # Flat stakes, so the n-weighted mean of each rule's ROI is the pooled ROI.
        roi = sum((r["a"].get("roi_fee") or 0) * (r["a"].get("n") or 0) for r in act) / n
        klass = "mut" if n < B.MIN_N else fmt.tone(roi, ".1f", 100)
        roi_cell = f'<b class="{klass}">{B.pct(roi, sign=True)}</b>'
        rec = f"{won}–{n - won}"
    else:
        roi_cell = '<b class="mut">—</b>'
        rec = "—"
    return (
        '<div class="tiles tn-tiles">'
        f'<div class="tile"><b>{open_n}</b><span>open picks</span></div>'
        f'<div class="tile"><b>{len(act)}</b><span>active rules</span></div>'
        f'<div class="tile"><b>{rec}</b><span>record · active rules</span></div>'
        f'<div class="tile">{roi_cell}<span>ROI after fees</span></div>'
        '</div>')


def _listing(d):
    """The Polymarket US counts for this family, from the ledger's stored coverage."""
    import sport_tab
    meta = S.SOURCES.get("polymarket_us") or {}
    sports = [sp for sp in (meta.get("sports") or [])
              if B.family(sp) == FAMILY
              and not S.lane_removed("polymarket_us", sp)
              and sp not in S.REMOVED_VENUE_SPORTS]
    if not sports:
        return ""
    cov = d.get("coverage") or {}
    rows = []
    for sp in sports:
        cell = cov.get(sp) or {}
        rows.append(
            f'<tr><td>{B.esc(S.SPORTS.get(sp, sp))}</td>'
            f'{sport_tab._count_cell(cell.get("polymarket_us"))}'
            f'{sport_tab._count_cell(cell.get("polymarket_us_listed"))}'
            f'{sport_tab._count_cell(cell.get("polymarket_us_priced"))}</tr>')
    head = ('<tr><th>Market</th><th class="num">Taken</th>'
            '<th class="num">Listed</th><th class="num">Priced</th></tr>')
    return f'<div class="tbl" id="listing"><table>{head}{"".join(rows)}</table></div>'


def system_html(d, idle_html=""):
    """The venue and grading note, closed by default."""
    listing = _listing(d) or '<div class="note">No venue coverage stored yet.</div>'
    return f'''<section id="system" class="tn-system">
<details><summary><b>Polymarket US &amp; how picks are graded</b><small>venue listing</small></summary>
<div>
<p class="sm">Polymarket US lists the match-winner markets; it logs prices and holds no record of its own, so it has no row in the rules table, and the counts are what the last run stored.</p>
<p class="sm">Every pick is logged before the start at the price available then, settled on the real result at a flat ${int(T.STAKE)} stake, and judged after fees against the price it paid.</p>
{listing}{idle_html}
</div>
</details>
</section>'''


def render(d, rows, now=None, idle_html=""):
    """The whole page body under the shared header. `now` is the page clock."""
    now = _as_utc(now or datetime.datetime.now(timezone.utc))
    return f'''<h1>Tennis</h1>
<p class="lede">Match-winner picks and combo baskets · times CT</p>
{tiles_html(d, rows)}
<section id="rules" class="tn-section">
<h2>Rules</h2>
<p class="sm mut">Production first, then by ROI after fees; open a row for the registered definition and its recent picks.</p>
{rules_html(d, rows, now)}
</section>
<section id="matches" class="tn-section">
<h2>Matches</h2>
<p class="sm mut">Every open pick, soonest first, plus today's settled ones.</p>
{picks_html(d, rows, now)}
</section>
{system_html(d, idle_html)}'''
