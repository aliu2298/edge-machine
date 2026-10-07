#!/usr/bin/env python3
"""The NBA page: a matchup board in the site shell, from data/nba_pace.json.

Presentation only. Expectations, labels, actuals, and errors are the values
already stored on each game. Nothing here refetches, relabels, or regrades.

The board is three tables. Upcoming is one row per game in the next 24
hours with the expected combined points for 1Q, 1H and FT; the highest
value in each column carries a mark, and a chevron opens a detail row with
each side's pace profile. Results is the graded games of the last 24 hours
with expected, actual and the file's own error. Teams is a sortable
reference of every team's current window. No bars: the three numbers are
the numbers.
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
EMPTY_GRADED = "No graded game in the last 24 hours."
# An error inside this many points is on target; inside twice it is near.
ERR_OK = 5.0
ERR_NEAR = 10.0


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
    return (_finite(game.get(scored_key)), _finite(game.get(allowed_key)))


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
    return (_finite(block.get("O")), _finite(block.get("D")))


def _period_text(blob, game, team, side):
    """'1Q 33.8/28.2 · 1H 63.6/59.2': scored/allowed. Per-game pre-tip
    values win, then teams[T].roll, else Coming soon."""
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
        parts.append(f"{short} {_points(found[0])}/{_points(found[1])}")
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
    """Upcoming games, graded games, and the 24–48h 'Next up' index.

    A tip exactly 24h out is not upcoming. A tip exactly 48h out is not Next
    up. Graded games are completed games that tipped off in the last 24h.
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


def _tag_html(tag, phrase_visible=False):
    """The O+D+ code with its meaning. The meaning is spoken always and
    shown when `phrase_visible`."""
    if not isinstance(tag, str) or not tag:
        return '<span class="mut">—</span>'
    phrase = TAGS.get(tag)
    title = f' title="{esc(phrase)}"' if phrase else ""
    if phrase and phrase_visible:
        return (f'<span class="tag"{title}>{esc(tag)}</span>'
                f'<span class="tag-phrase"> {esc(phrase)}</span>')
    spoken = f'<span class="sr-only">, {esc(phrase)}</span>' if phrase else ""
    return f'<span class="tag"{title}>{esc(tag)}{spoken}</span>'


def _leads(games):
    """{period: highest expectation} over the games that have one. Skipped games are out."""
    out = {}
    for key, _short, _full in PERIODS:
        values = [_finite(game.get("roll_exp_" + key)) for game in games if not game.get("skipped")]
        values = [value for value in values if value is not None]
        out[key] = max(values) if values else None
    return out


def _exp_cell(game, period, leads):
    """One expectation. The column's highest value carries a mark and says so."""
    value = _finite(game.get("roll_exp_" + period))
    if value is None or game.get("skipped"):
        return '<td class="num mut">—</td>'
    lead = leads.get(period)
    if lead is not None and value == lead:
        return (f'<td class="num is-lead" data-v="{value:.1f}"><span class="nba-val">{_points(value)}'
                f'<span class="sr-only"> (highest on the board)</span></span></td>')
    return f'<td class="num" data-v="{value:.1f}"><span class="nba-val">{_points(value)}</span></td>'


def _tip_cell(game):
    start = _instant(game.get("start"))
    if start is None:
        return '<td class="mut">—</td>'
    return (f'<td data-v="{esc(start.strftime("%Y%m%d%H%M"))}">'
            f'<time datetime="{esc(fmt.iso_z(start))}">{esc(fmt.when(start))}</time></td>')


def _matchup_cell(game, uid, expandable=True):
    away = game.get("away") or "—"
    home = game.get("home") or "—"
    name = (f'<span class="nba-matchup"><b>{esc(away)}</b><span aria-hidden="true"> @ </span>'
            f'<span class="sr-only"> at </span><b>{esc(home)}</b></span>')
    if not expandable:
        return f"<td>{name}</td>"
    return (f'<td><span class="nba-matchup-cell">{name} <button type="button" class="nba-more" aria-expanded="false"'
            f' aria-controls="{esc(uid)}" aria-label="Details, {esc(away)} at {esc(home)}">'
            f'<span aria-hidden="true">›</span></button></span></td>')


def _side_html(blob, game, team, side):
    side_word = "Away" if side == "away" else "Home"
    shown = team if team else "—"
    name = _full_name(blob, team) if team else None
    name_html = f'<span class="mut"> {esc(name)}</span>' if name else ""
    scored = _points(game.get("roll_" + side + "_O"))
    allowed = _points(game.get("roll_" + side + "_D"))
    tag = game.get("roll_lab_" + side + "_ft")
    pra = _pra_text(blob, team) if team else PRA_SOON
    periods = _period_text(blob, game, team, side)
    return (
        f'<div class="nba-side nba-side-{side}">'
        f'<p class="nba-side-k">{side_word}</p>'
        f'<p class="nba-side-team"><b class="team-abbr">{esc(shown)}</b>{name_html} {_tag_html(tag, phrase_visible=True)}</p>'
        f'<p class="nba-side-rates team-rates">Scored {esc(scored)} · allowed {esc(allowed)}</p>'
        f'<p class="nba-side-periods period-value">{esc(periods)}</p>'
        f'<p class="nba-side-pra pra-value">Last game: {esc(pra)}</p>'
        f'</div>'
    )


def _detail_row(blob, game, uid, columns):
    away = game.get("away") or "—"
    home = game.get("home") or "—"
    if game.get("skipped"):
        inner = (f'<p class="nba-skip"><b>Skipped.</b> {esc(game.get("skipped"))}</p>')
    else:
        inner = (f'<div class="nba-detail-grid">'
                 f'{_side_html(blob, game, game.get("away"), "away")}'
                 f'{_side_html(blob, game, game.get("home"), "home")}'
                 f'</div>')
    return (f'<tr class="nba-detail" id="{esc(uid)}" hidden>'
            f'<td colspan="{int(columns)}" data-l="">'
            f'<div class="nba-detail-box" aria-label="{esc(f"Details, {away} at {home}")}">{inner}</div>'
            f'</td></tr>')


def _status_cell(game):
    if game.get("skipped"):
        return f'<td><span class="nba-status is-skipped">Skipped</span></td>'
    return '<td><span class="nba-status">Upcoming</span></td>'


UP_HEAD = ('<tr><th>Tip (CT)</th><th>Matchup</th><th class="num">1Q</th>'
           '<th class="num">1H</th><th class="num">FT</th><th>Status</th></tr>')


def upcoming_table(blob, games):
    """One row per game, chronological, with a detail row under each."""
    if not games:
        return f'<p class="matchup-empty">{esc(EMPTY_UPCOMING)}</p>'
    leads = _leads(games)
    rows = []
    for index, game in enumerate(games):
        uid = f"game-u{index}"
        skipped = " is-skipped" if game.get("skipped") else ""
        rows.append(
            f'<tr class="nba-row{skipped}" data-away="{esc(game.get("away") or "—")}"'
            f' data-home="{esc(game.get("home") or "—")}" data-window="upcoming">'
            f'{_tip_cell(game)}{_matchup_cell(game, uid)}'
            f'{_exp_cell(game, "q1", leads)}{_exp_cell(game, "h1", leads)}{_exp_cell(game, "ft", leads)}'
            f'{_status_cell(game)}</tr>'
            f'{_detail_row(blob, game, uid, 6)}')
    return f'<div class="tbl"><table class="nba-games">{UP_HEAD}{"".join(rows)}</table></div>'


def _err_class(err):
    number = _finite(err)
    if number is None:
        return ""
    if abs(number) <= ERR_OK:
        return "err-ok"
    if abs(number) <= ERR_NEAR:
        return "err-near"
    return "err-far"


def _result_cell(game, period):
    exp = _finite(game.get("roll_exp_" + period))
    act = _finite(game.get("act_" + period))
    err = _finite(game.get("err_" + period))
    exp_txt = _points(exp)
    act_txt = _points(act) if act is None else _count(act)
    if exp is None and act is None:
        return '<td class="num mut">—</td>'
    cls = _err_class(err)
    err_html = ""
    if err is not None:
        err_html = (f' <span class="nba-err {cls}" title="error, actual minus expected">'
                    f'{esc(_signed_points(err))}</span>')
    data = f' data-v="{err:.1f}"' if err is not None else ""
    return (f'<td class="num"{data}><span class="nba-pair">{esc(exp_txt)} / {esc(act_txt)}</span>'
            f'{err_html}</td>')


RES_HEAD = ('<tr><th>Tip (CT)</th><th>Matchup</th><th class="num">1Q exp / act</th>'
            '<th class="num">1H exp / act</th><th class="num">FT exp / act</th></tr>')


def results_table(graded):
    if not graded:
        return f'<p class="matchup-empty">{esc(EMPTY_GRADED)}</p>'
    rows = []
    for index, game in enumerate(graded):
        rows.append(
            f'<tr class="nba-row" data-away="{esc(game.get("away") or "—")}"'
            f' data-home="{esc(game.get("home") or "—")}" data-window="graded">'
            f'{_tip_cell(game)}{_matchup_cell(game, f"game-g{index}", expandable=False)}'
            f'{_result_cell(game, "q1")}{_result_cell(game, "h1")}{_result_cell(game, "ft")}</tr>')
    return f'<div class="tbl"><table class="nba-results-table">{RES_HEAD}{"".join(rows)}</table></div>'


def accuracy_line(graded):
    """'Last 24h: 4 games graded · mean abs error FT 6.1, 1H 4.8, 1Q 5.2 · 2 of 4 FT within ±5.'

    Every figure is the file's own err_* values. A period with no error on
    any game is left out of the sentence.
    """
    n = len(graded)
    if not n:
        return "Last 24h: no graded game yet."
    parts = []
    for key, short, _full in reversed(PERIODS):
        errs = [abs(e) for e in (_finite(g.get("err_" + key)) for g in graded) if e is not None]
        if errs:
            parts.append(f"{short} {sum(errs) / len(errs):.1f}")
    ft = [abs(e) for e in (_finite(g.get("err_ft")) for g in graded) if e is not None]
    within = sum(1 for e in ft if e <= ERR_OK)
    sentence = f"Last 24h: {n} game{'s' if n != 1 else ''} graded"
    if parts:
        sentence += f" · mean abs error {', '.join(parts)}"
    if ft:
        sentence += f" · {within} of {len(ft)} FT within ±{ERR_OK:g}"
    return sentence + "."


def _seed_means(blob):
    """{team: {period: (scored, allowed)}} from the seed window's stored games."""
    seed = blob.get("seed") if isinstance(blob, dict) else None
    teams = seed.get("teams") if isinstance(seed, dict) else None
    out = {}
    if not isinstance(teams, dict):
        return out
    for team, window in teams.items():
        if not isinstance(window, dict):
            continue
        rec = {}
        for key, _short, _full in PERIODS:
            pairs = [pair for pair in (window.get(key) or [])
                     if isinstance(pair, (list, tuple)) and len(pair) >= 2
                     and _finite(pair[0]) is not None and _finite(pair[1]) is not None]
            if pairs:
                rec[key] = (sum(float(p[0]) for p in pairs) / len(pairs),
                            sum(float(p[1]) for p in pairs) / len(pairs))
        if rec:
            out[team] = rec
    return out


def _team_rows(blob):
    """Every team: current window from teams[T].roll, else the seed window."""
    seeds = _seed_means(blob)
    names = set(seeds)
    teams = blob.get("teams") if isinstance(blob, dict) else None
    if isinstance(teams, dict):
        names.update(str(t) for t in teams)
    out = {}
    for team in names:
        rec = {}
        for key, _short, _full in PERIODS:
            found = _roll_period(blob, team, key)
            if found is None or found[0] is None or found[1] is None:
                found = seeds.get(team, {}).get(key)
            if found is not None:
                rec[key] = found
        if rec:
            out[team] = rec
    return out


TEAM_HEAD = ('<tr><th>Team</th><th>Pace profile</th><th class="num">Scored</th>'
             '<th class="num">Allowed</th><th class="num">1Q scored/allowed</th>'
             '<th class="num">1H scored/allowed</th><th>Last-game PRA</th></tr>')


def team_table(blob):
    """The reference table: one row per team, sortable, highest combined first.

    The label is each team's full-game rates against the league means of the
    same rows, the comparison the old list made against the seed league.
    """
    rows_data = _team_rows(blob)
    if not rows_data:
        return ""
    fulls = [rec["ft"] for rec in rows_data.values() if "ft" in rec]
    lo = sum(pair[0] for pair in fulls) / len(fulls) if fulls else None
    ld = sum(pair[1] for pair in fulls) / len(fulls) if fulls else None

    def _order(item):
        pair = item[1].get("ft")
        return (pair is None, -(pair[0] + pair[1]) if pair else 0.0, str(item[0]))
    rows = []
    for team, rec in sorted(rows_data.items(), key=_order):
        scored, allowed = rec.get("ft") or (None, None)
        tag = None
        if scored is not None and lo is not None:
            tag = ("O+" if scored >= lo else "O-") + ("D+" if allowed >= ld else "D-")
        cells = []
        for key in ("q1", "h1"):
            pair = rec.get(key)
            if pair is None:
                cells.append('<td class="num mut">—</td>')
            else:
                cells.append(f'<td class="num" data-v="{pair[0]:.1f}">{_points(pair[0])}/{_points(pair[1])}</td>')
        full = [
            f'<td class="num" data-v="{scored:.1f}">{_points(scored)}</td>' if scored is not None
            else '<td class="num mut">—</td>',
            f'<td class="num" data-v="{allowed:.1f}">{_points(allowed)}</td>' if allowed is not None
            else '<td class="num mut">—</td>',
        ]
        rows.append(
            f'<tr><td><b>{esc(team)}</b></td><td>{_tag_html(tag, phrase_visible=True)}</td>'
            f'{full[0]}{full[1]}'
            f'{cells[0]}{cells[1]}'
            f'<td class="sm">{esc(_pra_text(blob, team))}</td></tr>')
    return f'<div class="tbl"><table class="team-table sortable">{TEAM_HEAD}{"".join(rows)}</table></div>'


def team_list(blob, soon=None, featured=None):
    """Kept for callers of the old name. The reference table lists every team."""
    del soon, featured
    return team_table(blob)


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
    upcoming, graded, _soon = _classify(blob, clock)
    window = blob.get("window")
    window_txt = esc(window) if window is not None else "—"
    built = _instant(blob.get("built")) if isinstance(blob, dict) else None
    fresh = ""
    if built is not None:
        fresh = f"Pace data as of {fmt.when(built)}"
        if abs((clock - built).total_seconds()) > 60:
            fresh += f" · board cut at {fmt.when(clock)}"
    fresh_html = f'<p class="nba-fresh">{esc(fresh)}</p>' if fresh else ""
    n_up = len(upcoming)
    body = f"""<div class="nba-head">
<div>
<h1>NBA</h1>
<p class="lede">Expected combined points · tip times CT</p>
{fresh_html}</div>
<nav class="nba-local-nav" aria-label="NBA sections">
<a href="#matchups">Upcoming</a>
<a href="#graded">Results</a>
<a href="#teams">Teams</a>
</nav>
</div>
<section id="matchups">
<div class="nba-section-head">
<div><h2>Upcoming</h2><p class="shell-kicker">Next 24 hours · chronological · the mark is the board's highest expectation in that column</p></div>
<span class="nba-count">{n_up} game{"s" if n_up != 1 else ""}</span>
</div>
{upcoming_table(blob, upcoming)}
<p class="nba-accuracy" id="accuracy">{esc(accuracy_line(graded))}</p>
</section>
<section id="graded">
<details class="section-disclosure nba-results"><summary><b>Results · last 24 hours</b><span>{len(graded)} graded</span></summary>
<p class="sm mut">Expected / actual combined points; the small signed number is the file's own error.</p>
{results_table(graded)}
</details>
</section>
<section id="teams">
<details class="section-disclosure nba-teams"><summary><b>Team reference</b><span>Last-{window_txt} window</span></summary>
<p class="sm mut">Each team's scoring and allowing rates over its last {window_txt} games, labelled against the league means of this table.</p>
{team_table(blob)}</details>
</section>
<details class="section-disclosure nba-about"><summary><b>About this desk</b><span>Preseason research</span></summary>
<p class="sm mut">1Q, 1H and FT are expected combined points for both teams, from each team's last-{window_txt} scoring and allowing rates. A finished game is graded against its actual combined total, and the error shown is actual minus expected as stored in the pace file. These are research expectations, not betting lines or recommendations.</p></details>
<footer>Read-only static export · rebuilt by GitHub Actions · research, not betting advice.</footer>

"""
    page = shell_build.sport_board(
        "nba",
        "Edge Machine · NBA",
        "NBA matchups, pace labels, and combined expectations. Preseason. No bets.",
        C.stamp(clock),
        body,
    )
    # Every cell named for its column and the header rows in <thead>, so the
    # phone cards work on this page however it is written out.
    import sandbox_build
    return sandbox_build.label_cells(page)


def main():
    if not os.path.exists(SRC):
        print(f"no {SRC} — run nba_pace.py --run first")
        return 1
    with open(SRC, encoding="utf-8") as fh:
        blob = json.load(fh)
    # The real clock, not the file's own build stamp: Upcoming is the next 24
    # hours from now, so a game already played is never listed as upcoming.
    html = build(blob, now=datetime.datetime.now(datetime.timezone.utc))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(html)
    os.replace(tmp, OUT)
    print(f"wrote {OUT} ({len(html):,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
