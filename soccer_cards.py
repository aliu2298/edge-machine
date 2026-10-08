#!/usr/bin/env python3
"""The Soccer page's two lists. Presentation only; only the Soccer page asks for them.

Fixtures: every open pick and every fixture a rule has already been shown,
grouped by Chicago day, one flat row per fixture, one line per pick. The pick
is written as the position a reader would take ("Under 3.5", "Lyon +0.5",
"BTTS yes"), derived from the market title and the side backed; the stored
label and side are untouched. A kickoff the ledger could not read is marked
"time TBC" inside its day. A kickoff already behind the page clock is "in play".

Rules: one table row per Sandbox lane, Production first and then by ROI after
fees. The record and the ROI are the Sandbox row's own figures. A chevron opens
the registered description and the rule's recent picks.

Nothing here grades, settles, or chooses a bet.
"""
import datetime
import re
from datetime import timedelta, timezone

import fmt
import sandbox_build as B
import sandbox_sources as S
import sandbox_track as T

# A fixture a rule has been shown, with no stake on it yet, is listed while its
# kickoff is after the page clock and at most this far ahead.
HORIZON = timedelta(hours=48)
# A rule's open panel lists this many picks, open ones first.
PICK_LIMIT = 5
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


def _keep(q):
    return not T.climate_excluded(q) and not S.tennis_refused_row(q)


def _by_start(q):
    return (q.get("start") or "", q.get("sport") or "", str(q.get("id") or ""))


def open_quotes(d, name, sport):
    """Open bets for one rule, soonest first. The same rows the open count uses."""
    live = [q for q in T.bet_rows(d)
            if q.get("source") == name and q.get("sport") == sport
            and q.get("status") == "open" and q.get("bet") and _keep(q)]
    live.sort(key=_by_start)
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


def upcoming_quotes(d, name, sport, now):
    """Fixtures this rule has already been shown, with no open bet on them.

    The tracker stores a quote when it sees the game. `bet` false and status
    open is that row with no stake yet. Kept while the kickoff is still ahead
    of `now` and at most `HORIZON` out. Open bets are not repeated here.
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
        if q.get("bet") or q.get("status") != "open" or not _keep(q):
            continue
        ko = _kickoff(q)
        if ko is not None and now < ko <= end:
            live.append(q)
    live.sort(key=_by_start)
    return live


def _market_name(base, fam="Soccer"):
    """The market a lane trades, as a short word: 'Under 3.5', 'BTTS', 'Match winner'."""
    full = S.SPORTS.get(base, base)
    return "Match winner" if full == fam else full.split(" · ")[-1]


def _fixture_label(q):
    # Soccer market labels append the outcome after the match's team names.
    return S.position_label(q).split(":", 1)[0].strip()


def _fixture_key(q):
    label, kickoff = _fixture_label(q), _kickoff(q)
    if label and kickoff is not None:
        return ("fixture", " ".join(label.casefold().split()),
                str(S.display_league(q) or "").casefold(), kickoff)
    # Without a match name and verified instant, keep distinct markets separate.
    return ("market", str(q.get("market_id") or q.get("id") or ""),
            str(q.get("start") or ""))


def _fixture_rows(d, rows, now):
    """Open and upcoming fixtures, grouped across rules so one match is one row."""
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


def _rule_name(row):
    """The rule's display name, with its scope where the name is shared across scopes."""
    return B.rule_name(row)


def _scoped_name(row):
    """Kept for callers that asked for the scoped form; the name always carries it now."""
    return _rule_name(row)


# ------------------------------------------------------------------ the pick, in words
_GOALS = re.compile(r"^(over|under)\s+(\d+(?:\.\d+)?)\s+goals?$", re.IGNORECASE)
_WIN = re.compile(r"^(.+?) to win \(No = (.+?) \+0\.5\)$")
_SCORE = re.compile(r"^(.+?) to score (\d+)\+$")
_CORNERS = re.compile(r"^(.*?)(\d+)\+ corners$")


def pick_text(q):
    """The position a reader would take, from the market title and the side backed.

    "A v B: over 3.5 goals" backed No is "Under 3.5". "A v B: A to win (No = B
    +0.5)" backed No is "B +0.5". "both teams to score" backed Yes is "BTTS yes".
    A match-winner market names the side: "Sparta to win", or "Draw". A title
    this does not recognise keeps the venue's wording with the side in front,
    so nothing is ever guessed.
    """
    side = str(B._side(q) or "").strip()
    label = str(q.get("label") or "")
    market = label.split(": ", 1)[1].strip() if ": " in label else ""
    sides = {str(q.get("side_a") or "").strip().lower(),
             str(q.get("side_b") or "").strip().lower()}
    if sides == {"yes", "no"}:
        yes = side.lower() == "yes"
        m = _GOALS.match(market)
        if m:
            word = m.group(1).lower()
            if not yes:
                word = "under" if word == "over" else "over"
            return f"{word.capitalize()} {m.group(2)}"
        if market.lower() == "both teams to score":
            return "BTTS yes" if yes else "BTTS no"
        m = _WIN.match(market)
        if m:
            return f"{m.group(1)} to win" if yes else f"{m.group(2)} +0.5"
        m = _SCORE.match(market)
        if m:
            team, n = m.group(1), m.group(2)
            return f"{team} {n}+ goals" if yes else f"{team} under {n} goal{'' if n == '1' else 's'}"
        m = _CORNERS.match(market)
        if m:
            head, n = m.group(1).strip(), m.group(2)
            if yes:
                return f"{head} {n}+ corners" if head else f"{n}+ corners"
            return f"{head} under {n} corners" if head else f"Under {n} corners"
        return f"{'Yes' if yes else 'No'}: {market}" if market else side
    if not side:
        return "—"
    if side.lower() == "draw":
        return "Draw"
    return f"{side} to win"


# ------------------------------------------------------------------ fixtures
def _day_key(q, kickoff):
    """The Chicago calendar day a fixture is listed under. None when the ledger has no day."""
    if kickoff is not None:
        return fmt.chicago(kickoff).date()
    raw = q.get("date")
    if isinstance(raw, str):
        try:
            return datetime.date.fromisoformat(raw.strip()[:10])
        except ValueError:
            return None
    return None


def _day_title(day, today):
    text = f"{day.strftime('%a')} {fmt._MONTHS[day.month - 1]} {day.day}"
    if day == today:
        return f"{B.esc(text)}<small>Today</small>"
    return B.esc(text)


def _pick_line(row, q, now):
    if q.get("bet"):
        side = B.safe_href(S.market_url(q), pick_text(q))
        cls = "soccer-pick-side"
        price = fmt.cents(q.get("price"))
    else:
        side, cls, price = "watching", "soccer-pick-side is-watch", "—"
    return (f'<div class="soccer-pick" data-source="{B.esc(row["name"])}">'
            f'<span class="{cls}">{side}</span>'
            f'<span class="soccer-pick-price">{B.esc(price)}</span>'
            f'<span class="soccer-pick-rule">{B.esc(_scoped_name(row))}</span></div>')


def _fixture_row(rec, now):
    q = rec["q"]
    ko = _kickoff(q)
    live = ko is not None and ko <= now and any(quote.get("bet") for _r, quote in rec["rules"])
    if ko is None:
        when = '<span class="soccer-tbc">time TBC</span>'
    else:
        when = B.esc(fmt.clock(ko))
    badge = '<span class="soccer-live">in play</span>' if live else ""
    picks = "".join(_pick_line(row, quote, now) for row, quote in rec["rules"])
    return (f'<div class="soccer-row{" is-past" if live else ""}">'
            f'<div class="soccer-row-time">{when}{badge}</div>'
            f'<div class="soccer-row-match">{B.esc(_fixture_label(q))}</div>'
            f'<div class="soccer-row-picks">{picks}</div></div>')


def fixtures(d, rows, now):
    """The Fixtures section: one list, grouped by Chicago day, chronological."""
    now = fmt.chicago(now).astimezone(timezone.utc)
    today = fmt.chicago(now).date()
    recs = _fixture_rows(d, rows, now)
    days = {}
    dated = []
    for rec in recs:
        day = _day_key(rec["q"], _kickoff(rec["q"]))
        if day is None:
            dated.append(rec)
        else:
            days.setdefault(day, []).append(rec)
    blocks = []
    for day in sorted(days):
        rows_html = "".join(_fixture_row(rec, now) for rec in days[day])
        blocks.append(f'<section class="soccer-day"><h3 class="soccer-day-head">{_day_title(day, today)}</h3>'
                      f'{rows_html}</section>')
    if dated:
        rows_html = "".join(_fixture_row(rec, now) for rec in dated)
        blocks.append(f'<section class="soccer-day"><h3 class="soccer-day-head">Date TBC</h3>{rows_html}</section>')
    picks = sum(1 for rec in recs for _r, q in rec["rules"] if q.get("bet"))
    count = (f'{picks} open pick{"" if picks == 1 else "s"} on {len(recs)} fixture{"" if len(recs) == 1 else "s"}'
             if recs else "no open pick")
    body = "".join(blocks) or '<p class="sm mut">No open pick and no tracked fixture.</p>'
    return (f'<section id="fixtures" class="soccer-fixtures">'
            f'<div class="soccer-section-head"><h2>Fixtures</h2><span>{B.esc(count)}</span></div>'
            f'{body}</section>')


# ------------------------------------------------------------------ rules
def _status(row):
    if row.get("gone") or row["v"] == "retired":
        return "retired", '<span class="sig x">Retired</span>'
    if row.get("prod"):
        return "production", '<span class="sig y">Production</span>'
    return "sandbox", '<span class="mut">Sandbox</span>'


def _rule_order(row):
    """Production first, then ROI after fees, highest first; no record last; retired after all."""
    stage, _chip = _status(row)
    roi = row["a"]["roi_fee"] if row["a"]["n"] else None
    return (stage == "retired", stage != "production", roi is None, -(roi or 0), -row["a"]["n"], row["name"])


def recent_picks(d, name, sport):
    """Up to PICK_LIMIT picks for one rule: open ones soonest first, then the newest settled."""
    mine = [q for q in T.bet_rows(d)
            if q.get("source") == name and q.get("sport") == sport and q.get("bet") and _keep(q)]
    live = sorted((q for q in mine if q.get("status") == "open"), key=_by_start)
    done = sorted((q for q in mine if q.get("status") != "open"), key=_by_start, reverse=True)
    return (live + done)[:PICK_LIMIT]


def _pick_item(q):
    status = str(q.get("status") or "")
    word = {"won": "won", "lost": "lost", "void": "void", "open": "open"}.get(status, status or "—")
    cls = {"won": "pos", "lost": "neg"}.get(status, "mut")
    return (f'<li class="rule-pick"><span class="mut">{B.esc(_kick_label(q))}</span>'
            f'<span>{B.safe_href(S.market_url(q), _fixture_label(q))}</span>'
            f'<b>{B.esc(pick_text(q))}</b><span class="num">{B.esc(fmt.cents(q.get("price")))}</span>'
            f'<span class="{cls}">{B.esc(word)}</span></li>')


def _rule_rows(d, row, i):
    a = row["a"]
    stage, chip = _status(row)
    sfx = B._scope(row["sport"])
    scope = S.SCOPE_LABEL[sfx] if sfx else S.CLUB_SCOPE_LABEL
    record = T.record_html(a)
    detail_id = f"rule-d-{i}"
    note = (row["meta"].get("note") or "").strip()
    picks = recent_picks(d, row["name"], row["sport"])
    picks_html = (f'<ul class="rule-picks">{"".join(_pick_item(q) for q in picks)}</ul>'
                  if picks else '<p class="sm mut">No pick yet.</p>')
    main = (f'<tr class="rule-row" data-source="{B.esc(row["name"])}" data-sport="{B.esc(row["sport"])}" '
            f'data-stage="{stage}">'
            f'<td><span class="rule-name-cell"><button type="button" class="rule-chev" aria-expanded="false" '
            f'aria-controls="{detail_id}" aria-label="Details for {B.esc(_rule_name(row))}">›</button>'
            f'<b>{B.esc(_rule_name(row))}</b></span></td>'
            f'<td>{B.esc(_market_name(B._base_sport(row["sport"])))}</td>'
            f'<td>{B.esc(scope)}</td>'
            f'<td class="num">{record}</td>'
            f'<td class="num">{roi_html(row)}</td>'
            f'<td>{chip}</td></tr>')
    detail = (f'<tr class="rule-detail" id="{detail_id}" hidden><td colspan="6" class="rule-detail-cell">'
              f'<p class="rule-about">{verdict_html(row)} <span>{B.esc(note) or "No registered description."}</span></p>'
              f'{picks_html}</td></tr>')
    return main + detail


RULES_HEAD = ('<tr><th>Rule</th><th>Market</th><th>Scope</th><th class="num">Record</th>'
              '<th class="num">ROI</th><th>Status</th></tr>')


def rules_table(d, rows):
    """The Rules section: one row per lane, Production first, then by ROI."""
    ordered = sorted(rows, key=_rule_order)
    body = "".join(_rule_rows(d, row, i) for i, row in enumerate(ordered))
    prod = sum(1 for r in rows if _status(r)[0] == "production")
    count = f'{len(rows)} rules · {prod} in Production' if rows else "no rule has a record yet"
    table = (f'<div class="tbl"><table class="soccer-rules">{RULES_HEAD}{body}</table></div>'
             if rows else '<div class="note">No soccer lane has a record yet.</div>')
    return (f'<section id="rules" class="soccer-rule-desk">'
            f'<div class="soccer-section-head"><h2>Rules</h2><span>{B.esc(count)}</span></div>'
            f'{table}</section>')


def production_strip(rows):
    """Production rules as small chips: name · market."""
    prod = [r for r in rows if r.get("prod")]
    chips = "".join(
        f'<span class="soccer-prod-rule"><b>{B.esc(_scoped_name(r))}</b>'
        f'<small>{B.esc(_market_name(B._base_sport(r["sport"])))}</small></span>'
        for r in prod)
    return f'<div class="soccer-prod-strip">{chips or "<span class=\"mut\">None in Production.</span>"}</div>'


def render(d, rows, now=None):
    """Rules, then Fixtures. `now` is the page clock."""
    now = now or datetime.datetime.now(timezone.utc)
    return rules_table(d, rows) + fixtures(d, rows, now)
