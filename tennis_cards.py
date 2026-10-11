#!/usr/bin/env python3
"""What the Tennis page hands the shared sport template (sport_page), and the
helpers the other pages borrow: the record tile, the ROI and verdict strings,
the tracker's next check. The record, verdict and ROI on every row are the
Sandbox row's own figures, the same strings the Sandbox table prints, so this
page cannot disagree with the Sandbox about the same pair. Nothing here grades,
settles, or chooses a bet.
"""
import datetime
import os
import re
from datetime import timedelta, timezone

import fmt
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
    """The verdict chip a Sandbox row prints for this pair: sport_page.verdict_badge."""
    import sport_page
    return sport_page.verdict_badge(row)


def record_text(a):
    """'23–8', or '12–8, 6 no result' where bets were paid out at a price; an em
    dash with nothing settled. The ledger's own words (sandbox_track.record_text)."""
    return T.record_text(a)


def record_tile(a, label):
    """The record stat tile: the W–L as the big number, the no-result count in
    the small label, so '13–8, 6 no result' never wraps into two huge lines.

    `label` is what the record is of ('record · Favourite band'); the no-result
    count is appended to it. Nothing settled is an em dash.
    """
    n = int(a.get("n") or 0)
    n_price = int(a.get("n_price") or 0)
    if not n and not n_price:
        return f'<div class="tile"><b>—</b><span>{B.esc(label)}</span></div>'
    big = f'{int(a.get("won") or 0)}–{max(0, n - int(a.get("won") or 0))}'
    small = label + (f' · {n_price} no result' if n_price else "")
    return f'<div class="tile"><b>{B.esc(big)}</b><span>{B.esc(small)}</span></div>'


# ------------------------------------------------------------------ the rows a rule owns
def _on_clock(q, row):
    """False for a bet logged before this lane's reset clock. Those stay on file only.

    The clock is the stage row's, read the way the Sandbox's If-faded cell reads
    it, so the picks listed here are the bets the row's record counts.
    """
    logged = str(q.get("logged") or "")
    # The row's own reset counts as well: pm_combo4 was demoted 2026-10-03, before the
    # 2026-10-04 widening, and without this its Sep 24-25 narrow-leg baskets were listed.
    clocks = [c for c in (S.tour_clock_since(since=row.get("since")), row.get("since"),
                          S.TENNIS_COMBO_BAND_SINCE if row.get("sport", "").endswith(("combo", "pmcombo")) else None)
              if c]
    return all(logged >= c for c in clocks)


def _kept(q, row):
    return (q.get("source") == row["name"] and q.get("sport") == row["sport"]
            and q.get("bet") and not T.climate_excluded(q)
            and q.get("note") != T.KALSHI_UNPLACEABLE
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
        age = (now - ko).total_seconds() / 3600
        # Past the settler's own flag, "in play" would be a fiction: the venue has
        # not finalised the market, and the row says so with its age.
        if age > T.OVERDUE_H:
            return f"unsettled · {age:.0f}h", "is-late"
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


def _recent_html(d, row, now):
    live = open_quotes(d, row["name"], row["sport"], row)
    done = settled_quotes(d, row)[:RECENT_LIMIT]
    if not live and not done:
        return '<p class="sm mut">No pick logged yet.</p>'
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
        bits.append(f'<span class="sp-state {cls}">{B.esc(word)}</span>')
        items.append(f'<li class="rule-pick">{" · ".join(bits)}</li>')
    return f'<ul class="rule-picks">{"".join(items)}</ul>'


def _legs(row):
    """How many legs a basket rule buys, from its registered source name; 0 for singles."""
    m = re.search(r"(\d)$", row["name"])
    return int(m.group(1)) if m and is_combo(row) else 0


def params(d, row):
    """What the rule backs now, from the registered constants: (name, value) pairs.

    The dated history is in `changes_html`; this is the current contract, so a
    reader sees the band, window, tours and venue before any reset is mentioned.
    Only the frozen tennis rules print one; another family's row prints nothing.
    """
    if row["name"] not in S.TENNIS_FROZEN_RULES:
        return ()
    lo, hi = S.TENNIS_3H_BAND
    band = f"{lo * 100:g}–{hi * 100:g}¢"
    hours = S.TENNIS_FAV_3H.total_seconds() / 3600
    # In the registry's own order, the way the registration names them.
    tours = ", ".join(S.TENNIS_TIERS[t] for t in S.TENNIS_TIERS if t in S.TENNIS_FAV_KEEP)
    k = _legs(row)
    if not k:
        return (
            ("Backs", f"the match winner priced {band}, one contract per match"),
            ("Window", f"entered within {hours:g}h of a verified start"),
            ("Tours", tours),
            ("Venue", venue_name(d, row)),
        )
    pm = B._base_sport(row["sport"]) == "tennis_pmcombo"
    markup = (S.PM_COMBO_MARKUP if pm else S.COMBO_MARKUP).get(k)
    measured = (S.PM_COMBO_MEASURED.get(k) if pm else True)
    price = (f"product of the legs + {markup * 100:.2f}% "
             f"{'measured' if measured else 'extrapolated'} markup" if markup else "product of the legs")
    return (
        ("Backs", f"{k} favourite-band legs as one contract, paid only if all {k} win"),
        ("Legs", f"priced {band}, same {hours:g}h window and tours as the favourite band ({tours})"),
        ("Price", price),
        ("Venue", venue_name(d, row)),
    )


def params_html(d, row):
    pairs = params(d, row)
    if not pairs:
        return ""
    return ('<dl class="sp-params">'
            + "".join(f"<dt>{B.esc(k)}</dt><dd>{B.esc(v)}</dd>" for k, v in pairs)
            + "</dl>")


def changes_html(row):
    """The dated resets, newest first, folded under the current definition."""
    changes = [c for c in (row["meta"].get("changes") or []) if str(c).strip()]
    if not changes:
        return ""
    items = "".join(f'<li>{B.esc(str(c).strip())}</li>' for c in changes)
    return (f'<details class="sp-changes"><summary>Changes · {len(changes)}</summary>'
            f'<ol class="sm mut">{items}</ol></details>')



# ------------------------------------------------------------------ what the template asks for
def market(d, row):
    """The venue column: Kalshi, Polymarket US, or both, for the rule's own contracts."""
    return venue_name(d, row)


def definition(d, row):
    """The current contract first (its parameters), then the registered definition,
    then the dated changes folded: the order a reader needs them in."""
    import sport_page as SP
    return params_html(d, row) + SP.definition_html(row["meta"].get("note")) + changes_html(row)


def recent_html(d, row, now):
    return _recent_html(d, row, now)


def _state(q):
    status = str(q.get("status") or "open")
    if status == "settled":
        return "price"
    return status if status in ("won", "lost", "void") else "open"


def events(d, rows, now):
    """One event per contest: the open picks and the picks settled inside the
    template's window, each pick on its own rule. A basket is its own event."""
    import sport_page as SP
    now = _as_utc(now)
    floor = now - timedelta(days=SP.DONE_DAYS)
    by_key = {}
    for row in rows:
        live = open_quotes(d, row["name"], row["sport"], row)
        done = [q for q in settled_quotes(d, row) if (_kickoff(q) or floor) >= floor]
        for q in live + done:
            label = match_label(q, row)
            ko = _kickoff(q)
            key = ("combo", str(q.get("id") or "")) if (q.get("legs") or is_combo(row)) else (
                " ".join(label.casefold().split()), ko.isoformat() if ko else str(q.get("id") or ""))
            rec = by_key.setdefault(key, dict(q=q, label=label, picks=[]))
            text, legs = pick_label(q)
            rec["picks"].append(SP.pick(row, q, text, _state(q), price=q.get("price"), legs=legs))
    out = []
    for rec in by_key.values():
        q = rec["q"]
        venue = VENUE_NAMES.get(str(q.get("venue") or ""), "")
        out.append(SP.event(_kickoff(q), fmt.contest(rec["label"]), rec["picks"],
                            href=None, sub=venue if not rec["label"].startswith("Combo") else ""))
    out.sort(key=lambda e: (e["when"] or _FAR, e["label"]))
    return out


def listing_html(d):
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


def method(idle_html=""):
    """The venue and grading note for the template's Method fold."""
    def _method(d, rows, now):
        listing = listing_html(d) or '<div class="note">No venue coverage stored yet.</div>'
        inner = (
            '<p class="sm">Polymarket US lists the match-winner markets; it logs prices and holds no '
            'record of its own, so it has no row in the rules table, and the counts are what the '
            'last run stored.</p>'
            f'<p class="sm">Every pick is logged before the start at the price available then, settled '
            f'on the real result at a flat ${int(T.STAKE)} stake, and judged after fees against the '
            f'price it paid.</p>'
            f'{listing}{idle_html}')
        return "Polymarket US & how picks are graded", "venue listing", inner, False
    return _method
