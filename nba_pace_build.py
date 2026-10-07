#!/usr/bin/env python3
"""The NBA page: a matchup board in the dark shell, from data/nba_pace.json.

Presentation only. Expectations, labels, actuals, and errors are the values
already stored on each game. Nothing here refetches, relabels, or regrades.
"""
import datetime
import json
import os
import re

import fmt
import shell_build
import site_chrome as C

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "data", "nba_pace.json")
OUT = os.path.join(ROOT, "public_site", "nba.html")

# What each label means, spelled out once rather than left as jargon.
TAGS = {
    "O+D+": "Fast offense · porous defense",
    "O+D-": "Fast offense · strong defense",
    "O-D+": "Slow offense · porous defense",
    "O-D-": "Slow offense · strong defense",
}
PERIODS = (
    ("q1", "1Q", "First quarter"),
    ("h1", "1H", "First half"),
    ("ft", "FT", "Full game"),
)
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
_DAY = datetime.timedelta(hours=24)
PRA_SOON = "Coming soon"
PRA_NONE = "No recent game"
PERIOD_SOON = "Coming soon"
EMPTY_UPCOMING = "No games in the next 24 hours."


def esc(x):
    return C.esc("" if x is None else x)


def _instant(value):
    """A datetime or ISO instant, as UTC. Naive datetimes are UTC. None stays None."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime.datetime):
        dt = value
    else:
        text = str(value).strip().replace("Z", "+00:00")
        try:
            dt = datetime.datetime.fromisoformat(text)
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt.astimezone(datetime.timezone.utc)


def _finite(value):
    """A real number stored in the file. Strings, bools, and NaN are missing."""
    if isinstance(value, bool) or isinstance(value, str) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def _points(value):
    number = _finite(value)
    if number is None:
        return "—"
    return f"{number:.1f}"


def _signed_points(value):
    """The file's own error, with a sign. A displayed zero has none."""
    number = _finite(value)
    if number is None:
        return "—"
    body = f"{abs(number):.1f}"
    if float(body) == 0.0:
        return "0.0"
    if number < 0:
        return f"{fmt.MINUS}{body}"
    return f"+{body}"


def _pct(value, lo, hi):
    """0 at the lowest expectation on the page, 100 at the highest.

    A period with one value, or with every value equal, is 100.
    Anything outside the expectation range clamps to an end of the track.
    """
    if value is None or lo is None or hi is None:
        return None
    if hi <= lo:
        return 100
    raw = (float(value) - float(lo)) / (float(hi) - float(lo)) * 100.0
    number = int(round(raw))
    if number < 0:
        return 0
    if number > 100:
        return 100
    return number


# A stored expectation at the bottom of the scale would otherwise paint an
# empty track. The text is the number; this only keeps the bar visible.
_FILL_FLOOR = 8


def _fill_pct(value, lo, hi):
    """The painted width. Same scale as `_pct`, never empty when a value exists."""
    number = _pct(value, lo, hi)
    if number is None or number >= 100:
        return number
    if number < _FILL_FLOOR:
        return _FILL_FLOOR
    return number


def _games(blob):
    games = blob.get("games") if isinstance(blob, dict) else None
    if not isinstance(games, list):
        return []
    return [game for game in games if isinstance(game, dict)]


def _team_entry(blob, team):
    """Top-level teams[T], the ESPN-abbreviation record. Absent is not null.

    Missing `teams`, or a missing team, means that feed has not landed.
    `last_game: null` is a different fact and is read by the caller.
    """
    if not team or not isinstance(blob, dict):
        return None
    teams = blob.get("teams")
    if not isinstance(teams, dict) or team not in teams:
        return None
    rec = teams.get(team)
    return rec if isinstance(rec, dict) else None


def _count(value):
    """A stored counting stat. Whole numbers stay whole. Anything else is 1 dp."""
    number = _finite(value)
    if number is None:
        return "—"
    text = f"{number:.1f}"
    if text.endswith(".0"):
        return str(int(round(number)))
    return text


def _day_label(value):
    """A stored YYYY-MM-DD, as 'Oct 4'. The day is already a calendar date."""
    if not isinstance(value, str):
        return None
    match = re.match(r"^(\d{4})-(\d{2})-(\d{2})", value.strip())
    if match is None:
        return None
    month = int(match.group(2))
    day = int(match.group(3))
    if not 1 <= month <= 12 or not 1 <= day <= 31:
        return None
    return f"{_MONTHS[month - 1]} {day}"


def _pra_text(blob, team):
    """Last-game top PRA from teams[T].last_game. Nothing here is summed.

    No `teams` record: Coming soon. last_game null: No recent game.
    A present top_pra is the stored name, pra, and the pts/reb/ast split.
    """
    rec = _team_entry(blob, team)
    if rec is None or "last_game" not in rec:
        return PRA_SOON
    last = rec.get("last_game")
    if last is None:
        return PRA_NONE
    if not isinstance(last, dict):
        return PRA_SOON
    top = last.get("top_pra")
    if not isinstance(top, dict):
        return PRA_SOON
    name = top.get("name")
    name = name.strip() if isinstance(name, str) and name.strip() else "—"
    where = ""
    opp = last.get("opp")
    opp = opp.strip() if isinstance(opp, str) else ""
    side = last.get("home_away")
    if opp and side == "away":
        where = f"at {opp}"
    elif opp and side == "home":
        where = f"vs {opp}"
    elif opp:
        where = opp
    day = _day_label(last.get("date"))
    tail = " ".join(part for part in (where, day) if part)
    body = (f"{name} {_count(top.get('pra'))} PRA "
            f"({_count(top.get('pts'))} pts · {_count(top.get('reb'))} reb · "
            f"{_count(top.get('ast'))} ast)")
    if tail:
        body += f", {tail}"
    return body


def _game_period(game, side, period):
    """Pre-tip quarter rates on the game, when those keys were stored."""
    if not isinstance(game, dict):
        return None
    scored_key = f"roll_{side}_O_{period}"
    allowed_key = f"roll_{side}_D_{period}"
    if scored_key not in game and allowed_key not in game:
        return None
    return (_finite(game.get(scored_key)), _finite(game.get(allowed_key)), None)


def _roll_period(blob, team, period):
    """teams[T].roll[period], the window as of the build. None when absent."""
    rec = _team_entry(blob, team)
    if rec is None:
        return None
    roll = rec.get("roll")
    if not isinstance(roll, dict):
        return None
    block = roll.get(period)
    if not isinstance(block, dict):
        return None
    if "O" not in block and "D" not in block:
        return None
    return (_finite(block.get("O")), _finite(block.get("D")), _finite(block.get("n")))


def _period_phrase(short, found):
    scored, allowed, count = found
    text = f"{short} scored {_points(scored)} · allowed {_points(allowed)}"
    if count is not None:
        text += f" · n {_count(count)}"
    return text


def _period_text(blob, game, team, side):
    """1Q and 1H. Per-game pre-tip values win, then teams[T].roll, else soon."""
    parts = []
    found_any = False
    for key, short in (("q1", "1Q"), ("h1", "1H")):
        found = _game_period(game, side, key)
        if found is None and team:
            found = _roll_period(blob, team, key)
        if found is None:
            parts.append(f"{short} —")
            continue
        found_any = True
        parts.append(_period_phrase(short, found))
    if not found_any:
        return PERIOD_SOON
    return " · ".join(parts)


def _full_name(blob, team):
    """A full name only when the file already stored one. No invented names."""
    teams = (blob.get("seed") or {}).get("teams") if isinstance(blob, dict) else None
    rec = teams.get(team) if isinstance(teams, dict) else None
    if isinstance(rec, dict):
        for key in ("name", "full_name"):
            value = rec.get(key)
            if isinstance(value, str) and value.strip() and value.strip() != str(team):
                return value.strip()
    return None


def _classify(blob, now):
    """Upcoming cards, graded cards, and the 24–48h 'Next up' index.

    A tip exactly 24h out is not a card. A tip exactly 48h out is not Next up.
    Graded cards are completed games that tipped off in the last 24h. They
    keep their teams in the list.
    """
    upcoming, graded = [], []
    soon = {}
    for game in _games(blob):
        start = _instant(game.get("start"))
        if start is None:
            continue
        delta = start - now
        if datetime.timedelta(0) <= delta < _DAY:
            upcoming.append(game)
        elif _DAY <= delta < _DAY * 2:
            for team in (game.get("away"), game.get("home")):
                if not team:
                    continue
                prev = soon.get(team)
                if prev is None or start < prev[0]:
                    soon[team] = (start, game)
        elif -_DAY <= delta < datetime.timedelta(0) and game.get("completed") and not game.get("skipped"):
            graded.append(game)
    def _key(game):
        return (_instant(game.get("start")), str(game.get("id") or ""))
    upcoming.sort(key=_key)
    graded.sort(key=_key)
    return upcoming, graded, soon


def _tempo_games(upcoming, graded):
    return [game for game in upcoming if not game.get("skipped")] + list(graded)


def _scale(games):
    found = {key: [] for key, _short, _full in PERIODS}
    for game in games:
        for key, _short, _full in PERIODS:
            number = _finite(game.get("roll_exp_" + key))
            if number is not None:
                found[key].append(number)
    out = {}
    for key, values in found.items():
        out[key] = (min(values), max(values)) if values else (None, None)
    return out


def _tag_html(tag):
    if not isinstance(tag, str) or not tag:
        return "<span class=\"mut\">—</span>"
    phrase = TAGS.get(tag)
    title = f' title="{esc(phrase)}"' if phrase else ""
    spoken = f'<span class="sr-only">, {esc(phrase)}</span>' if phrase else ""
    return f'<span class="tag"{title}>{esc(tag)}{spoken}</span>'


def _team_card(blob, game, team, side):
    side_word = "Away" if side == "away" else "Home"
    shown = team if team else "—"
    name = _full_name(blob, team) if team else None
    name_html = f'<p class="team-name">{esc(name)}</p>' if name else ""
    scored = _points(game.get("roll_" + side + "_O"))
    allowed = _points(game.get("roll_" + side + "_D"))
    tag = game.get("roll_lab_" + side + "_ft")
    pra = _pra_text(blob, team) if team else PRA_SOON
    periods = _period_text(blob, game, team, side)
    label = f"{side_word}, {shown}"
    if name:
        label += f", {name}"
    return (
        f'<section class="team-card team-{side}" aria-label="{esc(label)}">'
        f'<p class="team-side">{side_word}</p>'
        f'<p class="team-abbr">{esc(shown)}</p>'
        f'{name_html}'
        f'<p class="team-tag">{_tag_html(tag)}</p>'
        f'<p class="team-rates">Full game scored {esc(scored)} · allowed {esc(allowed)}</p>'
        f'<p class="pra-slot"><span class="slot-k">Top PRA (points + rebounds + assists), last game</span> '
        f'<span class="pra-value">{esc(pra)}</span></p>'
        f'<p class="period-slot"><span class="slot-k">1Q / 1H</span> '
        f'<span class="period-value">{esc(periods)}</span></p>'
        f'</section>'
    )


def _tempo_row(game, period, short, full, lo, hi, uid):
    exp = _finite(game.get("roll_exp_" + period))
    act = _finite(game.get("act_" + period)) if game.get("completed") else None
    err = _finite(game.get("err_" + period)) if act is not None else None
    exp_txt = _points(exp)
    read = f"{full} ({short}) expected {exp_txt} combined"
    fill = _fill_pct(exp, lo, hi) if exp is not None else None
    mark = None
    if act is not None:
        err_txt = _signed_points(err)
        read += f", actual {_points(act)}, error {err_txt}"
        if lo is not None and hi is not None and (act < lo or act > hi):
            read += ", outside the range of expectations on this page"
        mark = _pct(act, lo, hi)
    fill_html = ""
    if fill is not None:
        fill_html = f'<span class="tempo-fill" data-pct="{int(fill)}" aria-hidden="true"></span>'
    mark_html = ""
    if mark is not None:
        mark_html = f'<span class="tempo-mark" data-pct="{int(mark)}" aria-hidden="true"></span>'
    return (
        f'<div class="tempo-row" data-period="{esc(period)}">'
        f'<p class="tempo-read">{esc(read)}</p>'
        f'<div class="tempo-scale" role="img" aria-label="{esc(read)}">'
        f'{fill_html}{mark_html}'
        f'</div></div>'
    )


def _expect_card(game, scale, uid):
    away = game.get("away") or "—"
    home = game.get("home") or "—"
    start = _instant(game.get("start"))
    if start is None:
        when = "—"
        stamp = ""
    else:
        when = fmt.when(start)
        stamp = f' datetime="{esc(fmt.iso_z(start))}"'
    rows = []
    for index, (key, short, full) in enumerate(PERIODS):
        lo, hi = scale.get(key, (None, None))
        rows.append(_tempo_row(game, key, short, full, lo, hi, f"{uid}-{index}"))
    return (
        f'<section class="expect-card" aria-label="{esc(f"Combined expectation, {away} at {home}")}">'
        f'<p class="expect-title">{esc(away)} at {esc(home)}</p>'
        f'<p class="expect-when"><time{stamp}>{esc(when)}</time></p>'
        f'<p class="expect-kicker">Expected combined points, both teams</p>'
        f'<p class="tempo-note">Each bar runs from the lowest to the highest '
        f'combined expectation of that period on this page.</p>'
        f'<div class="tempo" role="group" aria-label="Tempo track, combined points">'
        f'{"".join(rows)}</div></section>'
    )


def _skipped_card(blob, game):
    away = game.get("away") or "—"
    home = game.get("home") or "—"
    reason = game.get("skipped") or "Skipped"
    start = _instant(game.get("start"))
    if start is None:
        when = "—"
        stamp = ""
    else:
        when = fmt.when(start)
        stamp = f' datetime="{esc(fmt.iso_z(start))}"'
    return (
        f'<article class="matchup is-skipped" data-window="upcoming" '
        f'data-away="{esc(away)}" data-home="{esc(home)}">'
        f'<div class="matchup-grid">'
        f'{_team_card(blob, game, game.get("away"), "away")}'
        f'<section class="expect-card" aria-label="{esc(f"Skipped, {away} at {home}")}">'
        f'<p class="expect-title">{esc(away)} at {esc(home)}</p>'
        f'<p class="expect-when"><time{stamp}>{esc(when)}</time></p>'
        f'<p class="expect-kicker">Skipped</p>'
        f'<p class="skip-reason">{esc(reason)}</p>'
        f'</section>'
        f'{_team_card(blob, game, game.get("home"), "home")}'
        f'</div></article>'
    )


def _summary_value(game, period):
    value = _finite(game.get("roll_exp_" + period))
    return _points(value) if value is not None else "—"


def _matchup_summary(game, window):
    away = game.get("away") or "—"
    home = game.get("home") or "—"
    start = _instant(game.get("start"))
    when = fmt.when(start) if start is not None else "—"
    status = "Final" if window == "graded" else ("Skipped" if game.get("skipped") else "Upcoming")
    return (
        f'<summary class="nba-game-summary">'
        f'<span class="nba-summary-time">{esc(when)}</span>'
        f'<span class="nba-summary-match"><b>{esc(away)}</b><span aria-hidden="true"> @ </span><b>{esc(home)}</b></span>'
        f'<span class="nba-summary-metric"><small>1Q</small>{esc(_summary_value(game, "q1"))}</span>'
        f'<span class="nba-summary-metric"><small>1H</small>{esc(_summary_value(game, "h1"))}</span>'
        f'<span class="nba-summary-metric"><small>FT</small>{esc(_summary_value(game, "ft"))}</span>'
        f'<span class="nba-summary-status">{esc(status)}</span>'
        f'</summary>'
    )


def _matchup(blob, game, scale, uid, window):
    away = game.get("away") or "—"
    home = game.get("home") or "—"
    skipped = bool(game.get("skipped"))
    return (
        f'<article class="matchup{" is-skipped" if skipped else ""}" data-window="{esc(window)}" '
        f'data-away="{esc(away)}" data-home="{esc(home)}">'
        f'<details class="nba-game">'
        f'{_matchup_summary(game, window)}'
        f'<div class="matchup-grid">'
        f'{_team_card(blob, game, game.get("away"), "away")}'
        f'{_skipped_expect(game) if skipped else _expect_card(game, scale, uid)}'
        f'{_team_card(blob, game, game.get("home"), "home")}'
        f'</div></details></article>'
    )


def _skipped_expect(game):
    away = game.get("away") or "—"
    home = game.get("home") or "—"
    reason = game.get("skipped") or "Skipped"
    start = _instant(game.get("start"))
    if start is None:
        when = "—"
        stamp = ""
    else:
        when = fmt.when(start)
        stamp = f' datetime="{esc(fmt.iso_z(start))}"'
    return (
        f'<section class="expect-card" aria-label="{esc(f"Skipped, {away} at {home}")}">'
        f'<p class="expect-title">{esc(away)} at {esc(home)}</p>'
        f'<p class="expect-when"><time{stamp}>{esc(when)}</time></p>'
        f'<p class="expect-kicker">Skipped</p>'
        f'<p class="skip-reason">{esc(reason)}</p>'
        f'</section>'
    )


def _matchups(blob, games, scale, window):
    if window == "upcoming" and not games:
        return f'<p class="matchup-empty">{esc(EMPTY_UPCOMING)}</p>'
    return "".join(
        _matchup(blob, game, scale, f"m{window[0]}{index}", window)
        for index, game in enumerate(games))


def _pace_leaders(games):
    rows = []
    for period, short, full in PERIODS:
        ranked = []
        for game in games:
            if game.get("skipped"):
                continue
            value = _finite(game.get("roll_exp_" + period))
            if value is None:
                continue
            ranked.append((value, game))
        ranked.sort(key=lambda item: (-item[0], str(item[1].get("id") or "")))
        if not ranked:
            continue
        value, game = ranked[0]
        away = game.get("away") or "—"
        home = game.get("home") or "—"
        rows.append(
            f'<a class="pace-leader" href="#matchups">'
            f'<span class="pace-leader-k">{esc(short)} leader</span>'
            f'<strong>{esc(away)} @ {esc(home)}</strong>'
            f'<span>{esc(_points(value))} combined</span>'
            f'</a>'
        )
    return "".join(rows)


def _seed_rows(blob):
    seed = blob.get("seed") if isinstance(blob, dict) else None
    teams = seed.get("teams") if isinstance(seed, dict) else None
    if not isinstance(teams, dict):
        return {}, {}
    calc = {}
    for team, window in teams.items():
        if not isinstance(window, dict):
            continue
        ft = window.get("ft") or []
        pairs = [pair for pair in ft if isinstance(pair, (list, tuple)) and len(pair) >= 2
                 and _finite(pair[0]) is not None and _finite(pair[1]) is not None]
        if not pairs:
            continue
        calc[team] = (sum(pair[0] for pair in pairs) / len(pairs),
                      sum(pair[1] for pair in pairs) / len(pairs))
    return calc, seed


def team_list(blob, soon, featured):
    """The 30-team list. Same columns as before, plus a Next up flag.

    Teams on a card in the next 24h are left out: they moved up. A game in
    the following day stays here. Labels are the seed window's own means
    against the seed league, the same comparison the list already printed.
    """
    calc, seed = _seed_rows(blob)
    if not calc:
        return ""
    shown = [(team, pair) for team, pair in calc.items() if team not in featured]
    lo = sum(pair[0] for pair in calc.values()) / len(calc)
    ld = sum(pair[1] for pair in calc.values()) / len(calc)
    span = seed.get("span", ["", ""]) if isinstance(seed, dict) else ["", ""]
    window = blob.get("window")
    window_txt = esc(window) if window is not None else "—"
    note = (f'<div class="note sm">Each team\'s last {window_txt} regular-season games '
            f'of 2025-26, {esc(span[0] if span else "")} to {esc(span[1] if len(span) > 1 else "")} '
            f'({esc(seed.get("games", 0) if isinstance(seed, dict) else 0)} games). '
            f'This is the starting window. A team with a game in the next 24 hours '
            f'is on a matchup card above. Next up is a game in the 24 hours after that.</div>')
    if not shown:
        return note + '<p class="matchup-empty">Every listed team has a game in the next 24 hours.</p>'
    rows = []
    for team, (scored, allowed) in sorted(shown, key=lambda item: (-(item[1][0] + item[1][1]), str(item[0]))):
        tag = ("O+" if scored >= lo else "O-") + ("D+" if allowed >= ld else "D-")
        hit = soon.get(team)
        if hit:
            start = hit[0]
            nxt = (f'<td class="next-up">Next up <time datetime="{esc(fmt.iso_z(start))}">'
                   f'{esc(fmt.when(start))}</time></td>')
        else:
            nxt = '<td class="mut">—</td>'
        rows.append(
            f'<tr><td>{esc(team)}</td><td class="num">{_points(scored)}</td>'
            f'<td class="num">{_points(allowed)}</td><td class="num">{_points(scored + allowed)}</td>'
            f'<td>{_tag_html(tag)}</td>{nxt}</tr>')
    head = ("<tr><th>Team</th><th>Scored</th><th>Allowed</th><th>Combined</th>"
            "<th>Label</th><th>Next</th></tr>")
    return f'{note}<div class="tbl"><table class="team-table">{head}{"".join(rows)}</table></div>'


def _clock(blob, now):
    if now is not None:
        return _instant(now)
    built = blob.get("built") if isinstance(blob, dict) else None
    stamped = _instant(built) if built else None
    if stamped is not None:
        return stamped
    return datetime.datetime.now(datetime.timezone.utc)


def build(blob=None, now=None):
    if blob is None:
        with open(SRC, encoding="utf-8") as fh:
            blob = json.load(fh)
    if not isinstance(blob, dict):
        blob = {}
    clock = _clock(blob, now)
    upcoming, graded, soon = _classify(blob, clock)
    featured = set()
    for game in upcoming:
        if game.get("away"):
            featured.add(game["away"])
        if game.get("home"):
            featured.add(game["home"])
    scale = _scale(_tempo_games(upcoming, graded))
    graded_html = ""
    if graded:
        graded_html = (
            '<section id="graded">'
            '<div class="nba-section-head"><div><h2>Results</h2><p class="shell-kicker">Graded, last 24 hours</p></div></div>'
            '<p class="note sm">The tick is the actual combined total. The error is the '
            'file\'s own actual minus expected.</p>'
            f'{_matchups(blob, graded, scale, "graded")}'
            '</section>'
        )
    window = blob.get("window")
    window_txt = esc(window) if window is not None else "—"
    body = f"""<div class="nba-head">
<div>
<h1>NBA Analyst Desk</h1>
<p class="lede">Scan the next games first. Open a matchup for the full last-{window_txt} detail.</p>
</div>
<nav class="nba-local-nav" aria-label="NBA sections">
<a href="#matchups">Upcoming</a>
<a href="#graded">Results</a>
<a href="#teams">Teams</a>
</nav>
</div>
<div class="note"><b>Research view.</b> These are stored preseason expectations, not betting lines or recommendations.</div>
<section class="pace-leaders" aria-label="Highest combined expectations">
{_pace_leaders(upcoming)}
</section>
<section id="matchups">
<div class="nba-section-head">
<div><h2>Upcoming</h2><p class="shell-kicker">Next 24 hours · chronological</p></div>
<span class="nba-count">{len(upcoming)} games</span>
</div>
<p class="note sm">Each row shows tip time and stored 1Q, 1H and full-game combined expectations.
Open a matchup for offense/defense rates, PRA and the expectation tracks.</p>
{_matchups(blob, upcoming, scale, "upcoming")}
</section>
{graded_html}
<section id="teams">
<div class="nba-section-head"><div><h2>Teams</h2><p class="shell-kicker">Reference list</p></div></div>
{team_list(blob, soon, featured)}
</section>
<footer>Read-only static export · rebuilt by GitHub Actions · research, not betting advice.</footer>
"""
    return shell_build.sport_board(
        "nba",
        "Edge Machine · NBA",
        "NBA matchups, pace labels, and combined expectations. Preseason. No bets.",
        C.stamp(clock),
        body,
    )


def main():
    if not os.path.exists(SRC):
        print(f"no {SRC} — run nba_pace.py --run first")
        return 1
    with open(SRC, encoding="utf-8") as fh:
        blob = json.load(fh)
    html = build(blob)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(html)
    os.replace(tmp, OUT)
    print(f"wrote {OUT} ({len(html):,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
