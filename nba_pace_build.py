#!/usr/bin/env python3
"""The NBA page: a matchup board in the dark shell, from data/nba_pace.json.

Presentation only. Expectations, labels, actuals, and errors are the values
already stored on each game. Nothing here refetches, relabels, or regrades.
"""
import datetime
import json
import os

import fmt
import shell_build
import site_chrome as C

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "data", "nba_pace.json")
OUT = os.path.join(ROOT, "public_site", "nba.html")

# What each label means, spelled out once rather than left as jargon.
TAGS = {
    "O+D+": "scores more, allows more",
    "O+D-": "scores more, allows less",
    "O-D+": "scores less, allows more",
    "O-D-": "scores less, allows less",
}
PERIODS = (
    ("q1", "1Q", "First quarter"),
    ("h1", "1H", "First half"),
    ("ft", "FT", "Full game"),
)
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

    A period with one value, or with every value equal, fills the bar.
    Anything outside the expectation range clamps to the end of the track.
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


def _games(blob):
    games = blob.get("games") if isinstance(blob, dict) else None
    if not isinstance(games, list):
        return []
    return [game for game in games if isinstance(game, dict)]


def _recent(blob, team):
    """True when this team has a completed NBA game in the file.

    The April seed is not a recent game: those rows have no event, and a team
    that has not played yet must not be given a guessed last box score.
    """
    if not team:
        return False
    for game in _games(blob):
        if game.get("skipped") or not game.get("completed"):
            continue
        if game.get("home") == team or game.get("away") == team:
            return True
    return False


def _present(value):
    if value is None or value is False:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        return bool(value)
    return True


def _pra_field(blob, game, team, side):
    """A stored top-PRA record, if a later feed put one on the game or the team.

    This does not score a player. The first field that is actually present wins.
    """
    if isinstance(game, dict):
        direct = game.get("top_pra_" + side)
        if _present(direct):
            return direct
        block = game.get("top_pra")
        if isinstance(block, dict):
            if _present(block.get(side)):
                return block.get(side)
            if _present(block.get(team)):
                return block.get(team)
    block = blob.get("top_pra") if isinstance(blob, dict) else None
    if isinstance(block, dict) and _present(block.get(team)):
        return block.get(team)
    teams = (blob.get("seed") or {}).get("teams") if isinstance(blob, dict) else None
    rec = teams.get(team) if isinstance(teams, dict) else None
    if isinstance(rec, dict) and _present(rec.get("top_pra")):
        return rec.get("top_pra")
    return None


def _pra_text(blob, game, team, side):
    if not _recent(blob, team):
        return PRA_NONE
    found = _pra_field(blob, game, team, side)
    if found is None:
        return PRA_SOON
    if isinstance(found, str):
        return found.strip()
    if isinstance(found, dict):
        name = found.get("name") or found.get("player") or ""
        name = name.strip() if isinstance(name, str) else ""
        bits = []
        for key, label in (("pts", "pts"), ("reb", "reb"), ("ast", "ast")):
            if key in found and found.get(key) is not None:
                bits.append(f"{found.get(key)} {label}")
        body = ", ".join(bits)
        if name and body:
            return f"{name} · {body}"
        if name or body:
            return name or body
    return PRA_SOON


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
    pra = _pra_text(blob, game, team, side) if team else PRA_NONE
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
        f'<span class="period-value">{esc(PERIOD_SOON)}</span></p>'
        f'</section>'
    )


def _tempo_row(game, period, short, full, lo, hi, uid):
    exp = _finite(game.get("roll_exp_" + period))
    act = _finite(game.get("act_" + period)) if game.get("completed") else None
    err = _finite(game.get("err_" + period)) if act is not None else None
    exp_txt = _points(exp)
    read = f"{full} ({short}) expected {exp_txt} combined"
    fill = _pct(exp, lo, hi) if exp is not None else None
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


def _matchup(blob, game, scale, uid, window):
    if game.get("skipped"):
        return _skipped_card(blob, game)
    away = game.get("away") or "—"
    home = game.get("home") or "—"
    return (
        f'<article class="matchup" data-window="{esc(window)}" '
        f'data-away="{esc(away)}" data-home="{esc(home)}">'
        f'<div class="matchup-grid">'
        f'{_team_card(blob, game, game.get("away"), "away")}'
        f'{_expect_card(game, scale, uid)}'
        f'{_team_card(blob, game, game.get("home"), "home")}'
        f'</div></article>'
    )


def _matchups(blob, games, scale, window):
    if window == "upcoming" and not games:
        return f'<p class="matchup-empty">{esc(EMPTY_UPCOMING)}</p>'
    return "".join(
        _matchup(blob, game, scale, f"m{window[0]}{index}", window)
        for index, game in enumerate(games))


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
            '<h2>Graded, last 24 hours</h2>'
            '<p class="note sm">The tick is the actual combined total. The error is the '
            'file\'s own actual minus expected.</p>'
            f'{_matchups(blob, graded, scale, "graded")}'
            '</section>'
        )
    window = blob.get("window")
    window_txt = esc(window) if window is not None else "—"
    body = f"""<h1>NBA</h1>
<p class="lede">Matchups for the next 24 hours, then the team list. A team card is the
full-game label and the scoring and allowing averages already stored. The middle card is
both teams together. No prices, no bets.</p>
<div class="note"><b>This is a test of the mechanism, not a forecast.</b> Labels and
combined expectations were recorded before tip-off. Preseason basketball predicts nothing.</div>
<section id="matchups">
<h2>Next 24 hours</h2>
<p class="note sm">A game tipping off within 24 hours of this page's clock. The window is the
last {window_txt} games. Per-team first-quarter and first-half totals, and the top PRA from
the last game, are not in the file yet.</p>
{_matchups(blob, upcoming, scale, "upcoming")}
</section>
{graded_html}
<section id="teams">
<h2>Teams</h2>
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
