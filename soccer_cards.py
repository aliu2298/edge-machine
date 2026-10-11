#!/usr/bin/env python3
"""What the Soccer page hands the shared sport template (sport_page).

The events: every open pick and every fixture a rule has already been shown,
one event per fixture, one pick line per rule on it, plus the picks settled in
the template's window. The pick is written as the position a reader would take
("Under 3.5", "Lyon +0.5", "BTTS yes"), derived from the market title and the
side backed; the stored label and side are untouched.

The rules: the registered definition, the market a rule trades, and its recent
picks for the expanders. Nothing here grades, settles, or chooses a bet.
"""
import datetime
import re
from datetime import timedelta, timezone

import fmt
import sandbox_build as B
import sandbox_sources as S
import sandbox_track as T
import sport_page as SP

# A fixture a rule has been shown, with no stake on it yet, is listed while its
# kickoff is after the page clock and at most this far ahead.
HORIZON = timedelta(hours=48)
# A rule's expander lists this many picks, open ones first.
PICK_LIMIT = 5
_FAR = datetime.datetime.max.replace(tzinfo=timezone.utc)


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


def settled_quotes(d, name, sport, since=None):
    """Settled bets for one rule, newest first, on the row's reset clock."""
    done = [q for q in T.bet_rows(d)
            if q.get("source") == name and q.get("sport") == sport and q.get("bet")
            and q.get("status") in ("won", "lost", "void", "settled") and _keep(q)
            and (not since or str(q.get("logged") or "") >= since)]
    done.sort(key=_by_start, reverse=True)
    return done


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


def market(d, row):
    """The market column: 'Over 1.5', 'BTTS', 'Corners'."""
    return _market_name(B._base_sport(row["sport"]))


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
    market_text = label.split(": ", 1)[1].strip() if ": " in label else ""
    sides = {str(q.get("side_a") or "").strip().lower(),
             str(q.get("side_b") or "").strip().lower()}
    if sides == {"yes", "no"}:
        yes = side.lower() == "yes"
        m = _GOALS.match(market_text)
        if m:
            word = m.group(1).lower()
            if not yes:
                word = "under" if word == "over" else "over"
            return f"{word.capitalize()} {m.group(2)}"
        if market_text.lower() == "both teams to score":
            return "BTTS yes" if yes else "BTTS no"
        m = _WIN.match(market_text)
        if m:
            return f"{m.group(1)} to win" if yes else f"{m.group(2)} +0.5"
        m = _SCORE.match(market_text)
        if m:
            team, n = m.group(1), m.group(2)
            return f"{team} {n}+ goals" if yes else f"{team} under {n} goal{'' if n == '1' else 's'}"
        m = _CORNERS.match(market_text)
        if m:
            head, n = m.group(1).strip(), m.group(2)
            if yes:
                return f"{head} {n}+ corners" if head else f"{n}+ corners"
            return f"{head} under {n} corners" if head else f"Under {n} corners"
        return f"{'Yes' if yes else 'No'}: {market_text}" if market_text else side
    if not side:
        return "—"
    if side.lower() == "draw":
        return "Draw"
    return f"{side} to win"


# ------------------------------------------------------------------ the events
def _state(q):
    if not q.get("bet"):
        return "watch"
    status = str(q.get("status") or "open")
    if status == "settled":
        return "price"
    return status if status in ("won", "lost", "void") else "open"


def _settled_at(q):
    try:
        return SP.instant(q.get("settled"))
    except (TypeError, ValueError):
        return None


def events(d, rows, now):
    """One event per fixture: the open picks, the fixtures being watched, and the
    picks settled inside the template's window, grouped so one match is one row."""
    now = SP.as_utc(now)
    floor = now - timedelta(days=SP.DONE_DAYS)
    by_key = {}
    for row in rows:
        live = open_quotes(d, row["name"], row["sport"])
        watching = upcoming_quotes(d, row["name"], row["sport"], now)
        done = [q for q in settled_quotes(d, row["name"], row["sport"], row.get("since"))
                if (_kickoff(q) or _settled_at(q) or now) >= floor]
        for q in live + watching + done:
            key = _fixture_key(q)
            rec = by_key.setdefault(key, dict(q=q, picks=[]))
            rec["picks"].append(SP.pick(
                row, q, pick_text(q) if q.get("bet") else "watching", _state(q),
                price=q.get("price") if q.get("bet") else None,
                settled=_settled_at(q)))
    out = []
    for rec in by_key.values():
        q = rec["q"]
        league = S.display_league(q) or ""
        out.append(SP.event(_kickoff(q), fmt.contest(_fixture_label(q)), rec["picks"],
                            href=None, sub=str(league)))
    out.sort(key=lambda e: (e["when"] or _FAR, e["label"]))
    return out


# ------------------------------------------------------------------ the rules
def recent_picks(d, name, sport, since=None):
    """Up to PICK_LIMIT picks for one rule: open ones soonest first, then the newest settled.

    `since` is the row's reset clock. A pick logged before it was made under the old rule
    and counts toward nothing, so it is not listed beside the new record.
    """
    mine = [q for q in T.bet_rows(d)
            if q.get("source") == name and q.get("sport") == sport and q.get("bet") and _keep(q)
            and (not since or str(q.get("logged") or "") >= since)]
    live = sorted((q for q in mine if q.get("status") == "open"), key=_by_start)
    done = sorted((q for q in mine if q.get("status") != "open"), key=_by_start, reverse=True)
    return (live + done)[:PICK_LIMIT]


def _pick_item(q):
    status = str(q.get("status") or "")
    word = {"won": "won", "lost": "lost", "void": "void", "open": "open"}.get(status, status or "—")
    cls = {"won": "pos", "lost": "neg"}.get(status, "mut")
    return (f'<li class="rule-pick"><span class="mut">{B.esc(_kick_label(q))}</span>'
            f'<span>{B.safe_href(S.market_url(q), fmt.contest(_fixture_label(q)))}</span>'
            f'<b>{B.esc(pick_text(q))}</b><span class="num">{B.esc(fmt.cents(q.get("price")))}</span>'
            f'<span class="{cls}">{B.esc(word)}</span></li>')


def recent_html(d, row, now=None):
    """The rule's recent picks, for a card's fold or a table row's expander."""
    picks = recent_picks(d, row["name"], row["sport"], row.get("since"))
    if not picks:
        return '<p class="sm mut">No pick yet.</p>'
    return f'<ul class="rule-picks">{"".join(_pick_item(q) for q in picks)}</ul>'
