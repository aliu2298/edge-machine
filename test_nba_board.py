#!/usr/bin/env python3
"""NBA matchup board. Fixture clock, no live ledger, no wall clock.

The page is presentation: three tables and a detail row per game, no bars.
These checks fail if a row crosses the 24h line, a total is recomputed from
the rates, the mark lands on anything but the board's highest expectation,
the error is act minus expected instead of the file's err_*, a missing
teams record is called 'No recent game', a player name is left unescaped,
or a bar or meter comes back.
"""
import datetime
import os
import re
import sys
import tempfile
import threading
from datetime import timedelta, timezone
from html.parser import HTMLParser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import fmt
import nba_pace_build as N
import sandbox_build
import site_chrome

FAILS = []
ROOT = os.path.dirname(os.path.abspath(__file__))
NOW = datetime.datetime(2026, 10, 6, 18, 0, tzinfo=timezone.utc)
MINUS = "−"
HOSTILE = '"><svg/onload=alert(1)>'
SKIP_REASON = "<script>alert(1)</script>"


def ok(cond, why):
    print(f"  {'ok  ' if cond else 'FAIL'} {why}")
    if not cond:
        FAILS.append(why)


def eq(got, want, why):
    ok(got == want, why if got == want else f"{why} — got {got!r}, want {want!r}")


class _Tags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
        self.handlers = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        for name, _value in attrs:
            if name.lower().startswith("on"):
                self.handlers.append(name)


def _section(html, sid):
    """The inside of one section, including anything nested in it."""
    open_tag = f'<section id="{sid}">'
    start = html.find(open_tag)
    if start < 0:
        return ""
    i = start + len(open_tag)
    depth = 1
    while i < len(html):
        next_open = html.find("<section", i)
        next_close = html.find("</section>", i)
        if next_close < 0:
            return ""
        if next_open != -1 and next_open < next_close:
            depth += 1
            i = next_open + len("<section")
            continue
        depth -= 1
        if depth == 0:
            return html[start + len(open_tag):next_close]
        i = next_close + len("</section>")
    return ""


def _text(block):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", block)).strip()


def _game_rows(fragment):
    return re.findall(r'<tr class="nba-row[^"]*"[^>]*>.*?</tr>', fragment, re.S)


def _game_row(fragment, away):
    for row in _game_rows(fragment):
        if f'data-away="{site_chrome.esc(away)}"' in row:
            return row
    return ""


def _detail(fragment, row):
    """The detail row the chevron on `row` controls."""
    match = re.search(r'aria-controls="([^"]+)"', row)
    if not match:
        return ""
    found = re.search(rf'<tr class="nba-detail" id="{re.escape(match.group(1))}"[^>]*>.*?</tr>', fragment, re.S)
    return found.group(0) if found else ""


def _cells(row):
    return re.findall(r"<td\b[^>]*>.*?</td>", row, re.S)


def _side(detail, which):
    match = re.search(rf'<div class="nba-side nba-side-{which}">.*?</div>', detail, re.S)
    return match.group(0) if match else ""


def _team_rows(fragment):
    table = re.search(r'<table class="team-table sortable">.*?</table>', fragment, re.S)
    if not table:
        return []
    return [row for row in re.findall(r"<tr>.*?</tr>", table.group(0), re.S) if "<td" in row]


def _team_row(fragment, team):
    for row in _team_rows(fragment):
        if re.search(rf"<td[^>]*><b>{re.escape(team)}</b></td>", row):
            return row
    return ""


def _game(gid, start, away, home, **extra):
    row = {"id": gid, "start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
           "away": away, "home": home, "completed": False}
    row.update(extra)
    return row


def _ft(scored, allowed):
    return {"ft": [[scored, allowed]] * 5}


def _blob():
    """One pinned clock. Numbers are chosen so a recomputed total cannot pass."""
    return {
        "window": 5,
        "built": "2026-10-01T18:00:00Z",
        "games": [
            _game("skip", NOW + timedelta(hours=1), HOSTILE, "POR",
                  skipped=SKIP_REASON,
                  roll_exp_q1=999.9, roll_exp_h1=999.9, roll_exp_ft=999.9),
            _game("bkn", NOW + timedelta(hours=5), "BKN", "CHA",
                  roll_exp_q1=56.2, roll_exp_h1=114.0, roll_exp_ft=221.5,
                  roll_away_O=11.1, roll_away_D=12.2, roll_lab_away_ft="O-D-",
                  roll_home_O=13.3, roll_home_D=14.4, roll_lab_home_ft="O+D+",
                  top_pra_away={"name": "Should Not Show", "pts": 9, "reb": 9, "ast": 9}),
            _game("2", NOW + timedelta(hours=6), "AA", "BB",
                  roll_exp_q1=40.0, roll_exp_h1=80.0, roll_exp_ft=160.0),
            _game("1", NOW + timedelta(hours=6), "CC", "DD",
                  roll_exp_q1=40.0, roll_exp_h1=80.0, roll_exp_ft=160.0),
            _game("in", NOW + timedelta(hours=24) - timedelta(seconds=1), "IN", "SIDE",
                  completed=True,
                  roll_exp_q1=50.0, roll_exp_h1="NaN", roll_exp_ft=200.0,
                  act_q1=53, err_q1=9.0,
                  roll_away_O=21.0, roll_away_D=22.0, roll_lab_away_ft="O+D-",
                  roll_home_O=23.0, roll_home_D=24.0, roll_lab_home_ft="O-D+"),
            _game("edge", NOW + timedelta(hours=24), "EDGE", "WALL"),
            _game("soon", NOW + timedelta(hours=36), "SOON", "LATER"),
            _game("out", NOW + timedelta(hours=48), "OUT", "FAR"),
            _game("graded", NOW - timedelta(hours=2), "GS", "LAC",
                  completed=True,
                  roll_exp_q1=57.3, roll_exp_h1=112.3, roll_exp_ft=227.9,
                  act_q1=55, act_h1=140, act_ft=210,
                  err_q1=-1.5, err_h1=5.0, err_ft=4.0,
                  roll_away_O=33.3, roll_away_D=34.4, roll_lab_away_ft="O+D+",
                  roll_home_O=35.5, roll_home_D=36.6, roll_lab_home_ft="O-D-",
                  top_pra_away={"name": "Stephen Curry", "pts": 30, "reb": 5, "ast": 8}),
            _game("old", NOW - timedelta(hours=30), "MIA", "TOR",
                  completed=True, roll_exp_ft=9.9, act_ft=2, err_ft=0.9),
        ],
        "seed": {"span": ["2026-03-25", "2026-04-12"], "games": 16, "teams": {
            "BKN": _ft(70, 70),
            "CHA": _ft(77.7, 77.7),
            "IN": _ft(60, 60),
            "SIDE": _ft(61, 61),
            "POR": _ft(62, 62),
            "EDGE": _ft(90, 90),
            "WALL": _ft(91, 91),
            "SOON": _ft(50, 50),
            "LATER": _ft(51, 51),
            "OUT": _ft(45, 45),
            "FAR": _ft(46, 46),
            "GS": dict(_ft(88.8, 80), name="<b>Warriors</b>"),
            "LAC": _ft(40, 90),
            "AAA": _ft(100, 80),
            "MIA": _ft(30, 30),
            "TOR": _ft(31, 31),
        }},
    }


print("windows, order, and the upcoming table")
BLOB = _blob()
HTML = N.build(BLOB, now=NOW)
UP = _section(HTML, "matchups")
GRADED = _section(HTML, "graded")
TEAMS = _section(HTML, "teams")
ok(UP and GRADED and TEAMS, "the board has upcoming, graded, and team sections")
ok('<table class="nba-games">' in UP and "<th>Tip (CT)</th><th>Matchup</th>" in UP
   and '<th class="num">1Q</th><th class="num">1H</th><th class="num">FT</th><th>Status</th>' in UP,
   "Upcoming is a table: Tip (CT), Matchup, 1Q, 1H, FT, Status")
rows = _game_rows(UP)
eq([re.search(r'data-away="([^"]*)"', row).group(1) for row in rows],
   [site_chrome.esc(HOSTILE), "BKN", "CC", "AA", "IN"],
   "upcoming rows are start order, then id")
eq([re.search(r'data-home="([^"]*)"', row).group(1) for row in rows],
   ["POR", "CHA", "DD", "BB", "SIDE"], "home sits opposite the away team")
ok(all('data-window="upcoming"' in row for row in rows), "every upcoming row says so")

bkn = _game_row(UP, "BKN")
cells = _cells(bkn)
eq(len(cells), 6, "a game row has one cell per column")
ok(fmt.when(NOW + timedelta(hours=5)) in cells[0] and "<time" in cells[0],
   "the tip is the CT clock in the site's date form")
ok("<b>BKN</b>" in cells[1] and "<b>CHA</b>" in cells[1] and " at " in _text(cells[1]) + " at ",
   "the matchup names both sides")
ok("56.2" in cells[2] and "114.0" in cells[3] and "221.5" in cells[4],
   "the row prints the file's roll_exp values for 1Q, 1H, FT")
ok("25.5" not in bkn, "the row does not recompute the total from O and D")
ok("Upcoming" in _text(cells[5]), "the status column reads Upcoming")
ok('class="num is-lead"' in cells[2] and 'class="num is-lead"' in cells[3] and 'class="num is-lead"' in cells[4]
   and "highest on the board" in cells[2],
   "BKN carries the mark in all three columns: it has the board's highest expectation")
for away in ("CC", "AA", "IN"):
    ok("is-lead" not in _game_row(UP, away), f"{away} carries no mark")
ok("999.9" not in HTML and "is-lead" not in _game_row(UP, HOSTILE),
   "a skipped game's expectation is neither printed nor a lead")
ok("pace-leader" not in HTML and "leader" not in _text(UP).lower(),
   "the three leader tiles are gone")

tied = N.build({"window": 5, "games": [
    _game("a", NOW + timedelta(hours=2), "AA", "BB",
          roll_exp_q1=40.0, roll_exp_h1=40.0, roll_exp_ft=40.0),
    _game("b", NOW + timedelta(hours=3), "CC", "DD",
          roll_exp_q1=40.0, roll_exp_h1=40.0, roll_exp_ft=40.0),
], "seed": {"teams": {}}}, now=NOW)
tied_up = _section(tied, "matchups")
ok(_game_row(tied_up, "AA").count("is-lead") == 3 and _game_row(tied_up, "CC").count("is-lead") == 3,
   "two games tied on the highest expectation both carry the mark")

print("\ndetail rows")
detail = _detail(UP, bkn)
ok(detail and ' hidden>' in detail.split(">", 1)[0] + ">", "the BKN detail row exists and starts hidden")
ok('colspan="6"' in detail and 'data-l=""' in detail,
   "the detail cell spans every column and carries no phone-card label")
ok(bkn.index("nba-more") < len(bkn) and 'aria-expanded="false"' in bkn,
   "the chevron is a button that starts collapsed")
away, home = _side(detail, "away"), _side(detail, "home")
ok(">Away<" in away and ">Home<" in home and detail.index(away) < detail.index(home),
   "the detail is two columns, away then home")
ok("11.1" in away and "12.2" in away and "O-D-" in away and "Slow offense · strong defense" in away,
   "the away column shows the stored rates, the code and its meaning")
ok("13.3" in home and "14.4" in home and "O+D+" in home, "the home column shows the stored rates and label")
ok("Scored 11.1 · allowed 12.2" in _text(away), "rates read Scored X · allowed Y")
ok("Nets" not in HTML and "Brooklyn" not in HTML, "a team with no stored full name is not given one")
ok("tempo" not in HTML and "Combined expectations" not in HTML and "<meter" not in HTML
   and "<progress" not in HTML and "data-pct" not in HTML,
   "no bars, meters, or expectation tracks anywhere on the page")
inside = _game_row(UP, "IN")
ok(inside and 'data-window="upcoming"' in inside, "a tip one second inside 24h is an upcoming row")
ok("—" in _cells(inside)[3] and not re.search(r"\bnan\b", HTML, re.I),
   "a missing expectation is an em dash, and NaN is never printed")
ok('data-away="EDGE"' not in UP, "a tip exactly 24h out is not upcoming")
skipped = _game_row(UP, HOSTILE)
ok("Skipped" in _text(skipped) and "is-skipped" in skipped,
   "a skipped game is on the board with a Skipped status")
skip_detail = _detail(UP, skipped)
ok("Skipped." in skip_detail and "&lt;script&gt;alert(1)&lt;/script&gt;" in skip_detail,
   "its detail says why, escaped")

print("\nresults and accuracy")
acc = re.search(r'class="nba-accuracy" id="accuracy">([^<]*)<', HTML)
eq(acc.group(1) if acc else None,
   "Last 24h: 1 game graded · mean abs error FT 4.0, 1H 5.0, 1Q 1.5 · 1 of 1 FT within ±5.",
   "the accuracy line is built from the file's own errors on the graded games")
ok(UP.index("nba-games") < HTML.index('id="accuracy"') < HTML.index('<section id="graded">'),
   "the accuracy line sits under the upcoming table, before Results")
ok('<details class="section-disclosure nba-results"><summary><b>Results · last 24 hours</b>' in GRADED
   and "<details" in GRADED and ' open' not in GRADED.split("<summary>", 1)[0],
   "Results is a collapsed section headed Results · last 24 hours")
ok('<th class="num">1Q exp / act</th><th class="num">1H exp / act</th><th class="num">FT exp / act</th>' in GRADED,
   "the results table has the exp / act columns")
gs = _game_row(GRADED, "GS")
ok(gs and 'data-window="graded"' in gs, "a completed game in the last 24h is a results row")
gcells = _cells(gs)
ok("57.3 / 55" in _text(gcells[2]) and f"{MINUS}1.5" in gcells[2] and "err-ok" in gcells[2],
   "1Q shows expected / actual and the file's negative error in green")
ok(f"{MINUS}2.3" not in HTML and "-2.3" not in HTML, "the error is never actual minus expected")
ok("112.3 / 140" in _text(gcells[3]) and "+5.0" in gcells[3] and "err-ok" in gcells[3] and "27.7" not in HTML,
   "1H shows the file's +5.0 (on the ±5 line, green), not 27.7")
ok("227.9 / 210" in _text(gcells[4]) and "+4.0" in gcells[4] and f"{MINUS}17.9" not in HTML,
   "FT shows the file's +4.0")
ok("nba-more" not in gs, "a results row has no detail chevron")
ok('data-away="MIA"' not in HTML and "9.9" not in HTML, "a completed game older than 24h is not a row")
ok("<b>Warriors</b>" not in HTML, "a stored full name is never injected raw")

coloured = N.build({"window": 5, "games": [
    _game("g", NOW - timedelta(hours=1), "AA", "BB", completed=True,
          roll_exp_q1=50.0, roll_exp_h1=100.0, roll_exp_ft=200.0,
          act_q1=53, act_h1=93, act_ft=212, err_q1=3.0, err_h1=-7.0, err_ft=12.0),
    _game("h", NOW - timedelta(hours=2), "CC", "DD", completed=True,
          roll_exp_ft=200.0, act_ft=204, err_ft=4.0),
], "seed": {"teams": {}}}, now=NOW)
crow = _cells(_game_row(_section(coloured, "graded"), "AA"))
ok("err-ok" in crow[2] and "+3.0" in crow[2], "within ±5 is green")
ok("err-near" in crow[3] and f"{MINUS}7.0" in crow[3], "between 5 and 10 is amber")
ok("err-far" in crow[4] and "+12.0" in crow[4], "beyond 10 is red")
cacc = re.search(r'class="nba-accuracy" id="accuracy">([^<]*)<', coloured).group(1)
eq(cacc, "Last 24h: 2 games graded · mean abs error FT 8.0, 1H 7.0, 1Q 3.0 · 1 of 2 FT within ±5.",
   "the accuracy line averages absolute errors and counts FT within ±5")

print("\nteam reference")
ok('<table class="team-table sortable">' in TEAMS and "<details" in TEAMS
   and "<b>Team reference</b>" in TEAMS and ' open' not in TEAMS.split("<summary>", 1)[0],
   "Teams is one sortable table, collapsed under Team reference")
ok("<th>Team</th><th>Pace profile</th>" in TEAMS and "1Q scored/allowed" in TEAMS
   and "1H scored/allowed" in TEAMS and "<th>Last-game PRA</th>" in TEAMS,
   "the team table has the reference columns")
names = [re.search(r"<td[^>]*><b>([^<]*)</b></td>", row).group(1) for row in _team_rows(TEAMS)]
eq(names[0], "WALL", "the list is highest combined first")
ok("BKN" in names and "IN" in names and "AAA" in names, "every team is on the reference, upcoming or not")
aaa = _team_row(TEAMS, "AAA")
ok('data-v="100.0"' in aaa and ">100.0<" in aaa and ">80.0<" in aaa and "O+D+" in aaa
   and "Fast offense · porous defense" in aaa,
   "a row prints seed scored and allowed with a sortable value and the profile in words")
ok("88.8" in _team_row(TEAMS, "GS"), "a graded team keeps its seed average on the list")
ok("Coming soon" in _text(aaa), "with no teams record the PRA column is Coming soon")
ok("Next up" not in HTML, "the Next up flag is gone with the old list")

print("\nPRA, periods, shell")
def _pra(detail, which):
    block = _side(detail, which)
    pra = re.search(r'class="nba-side-pra pra-value">Last game: (.*?)</p>', block)
    period = re.search(r'class="nba-side-periods period-value">(.*?)</p>', block)
    return (pra.group(1) if pra else "", period.group(1) if period else "")

eq(_pra(detail, "away"), ("Coming soon", "Coming soon"),
   "with no teams record the PRA and period slots are Coming soon, not No recent game")
eq(_pra(detail, "home"), ("Coming soon", "Coming soon"), "the home side is also Coming soon")
ok("No recent game" not in HTML, "absent keys are not described as no recent game")
ok("Should Not Show" not in HTML and "Stephen Curry" not in HTML,
   "a PRA hung on the game row is not read")

HOSTILE_PLAYER = "<img src=x onerror=alert(1)>"
fed = N.build({
    "window": 5,
    "games": [
        _game("box", NOW + timedelta(hours=2), "GS", "LAC",
              roll_exp_q1=50.0, roll_exp_h1=100.0, roll_exp_ft=200.0,
              roll_away_O_q1=20.0, roll_away_D_q1=14.0,
              roll_away_O_h1=48.0, roll_away_D_h1=42.0),
        _game("none", NOW + timedelta(hours=3), "BKN", "CHA",
              roll_exp_q1=40.0, roll_exp_h1=80.0, roll_exp_ft=160.0),
    ],
    "teams": {
        "GS": {
            "roll": {"q1": {"O": 1.1, "D": 1.2, "n": 5},
                     "h1": {"O": 1.3, "D": 1.4, "n": 5}},
            "last_game": {
                "id": "401918010", "date": "2026-10-04", "opp": "LAC",
                "home_away": "away",
                "top_pra": {"name": "Charles Bassey", "pts": 12, "reb": 8, "ast": 1, "pra": 21},
            },
        },
        "LAC": {
            "roll": {"q1": {"O": 13.6, "D": 19.2, "n": 5},
                     "h1": {"O": 42.0, "D": 46.8, "n": 5}},
            "last_game": {
                "id": "g1", "date": "2026-10-03", "opp": "NY", "home_away": "home",
                "top_pra": {"name": HOSTILE_PLAYER, "pts": 30, "reb": 5, "ast": 8, "pra": 4},
            },
        },
        "BKN": {
            "roll": {"q1": {"O": 10.0, "D": 11.0, "n": 5},
                     "h1": {"O": "NaN", "D": 28.0, "n": 5}},
            "last_game": None,
        },
    },
    "seed": {"teams": {}},
}, now=NOW)
fed_up = _section(fed, "matchups")
gs_detail = _detail(fed_up, _game_row(fed_up, "GS"))
eq(_pra(gs_detail, "away"), (
    "Charles Bassey 21 PRA (12 pts · 8 reb · 1 ast), at LAC Oct 4",
    "1Q 20.0/14.0 · 1H 48.0/42.0",
), "a stored top_pra renders, and the matchup prefers the pre-tip quarter rates")
ok("1.1" not in _pra(gs_detail, "away")[1], "the team roll does not replace pre-tip quarter rates")
lac = _pra(gs_detail, "home")
eq(lac[1], "1Q 13.6/19.2 · 1H 42.0/46.8", "with no pre-tip quarter keys the side uses teams[T].roll")
ok("4 PRA" in lac[0] and "vs NY Oct 3" in lac[0] and "43" not in lac[0],
   "the home side shows the stored pra and the home opponent, not the sum")
ok(HOSTILE_PLAYER not in fed and "&lt;img src=x onerror=alert(1)&gt;" in fed, "a hostile player name is escaped")
fed_tags = _Tags()
fed_tags.feed(fed)
ok("img" not in fed_tags.tags and not fed_tags.handlers, "the player name is not a tag")
bkn_detail = _detail(fed_up, _game_row(fed_up, "BKN"))
bkn_fed = _pra(bkn_detail, "away")
eq(bkn_fed[0], "No recent game", "last_game null is No recent game")
eq(bkn_fed[1], "1Q 10.0/11.0 · 1H —/28.0",
   "a null last game still shows the stored quarter rates, and a bad number is an em dash")
eq(_pra(bkn_detail, "home"), ("Coming soon", "Coming soon"), "a missing team entry is Coming soon on both slots")
ok("None" not in fed and not re.search(r"\bnan\b", fed, re.I), "the fed page never prints None or NaN")
ok("Charles Bassey" in _section(fed, "teams"), "the team reference shows the same last-game PRA")

ok(HOSTILE not in HTML and "svg/onload" in HTML and "&lt;svg/onload=alert(1)&gt;" in HTML,
   "a hostile team string is escaped")
parsed = _Tags()
parsed.feed(HTML)
ok("svg" not in parsed.tags and "img" not in parsed.tags, "the hostile string is not a tag")
ok(not parsed.handlers, "no inline event handler")
_SCRIPT = re.compile(r"<script\b([^>]*)>(.*?)</script>", re.I | re.S)
ok(not any(m.group(2).strip() for m in _SCRIPT.finditer(HTML))
   and '<script src="./tables.js"></script>' in HTML,
   "no inline script body")
ok(site_chrome.CSP in HTML, "the page keeps the site Content-Security-Policy")
ok('href="./site.css"' in HTML and "<style" not in HTML.lower() and not re.search(r"\sstyle\s*=", HTML),
   "no inline style")
ok(HTML.count('<header class="site">') == 1 and 'class="topbar"' in HTML
   and '<a class="brand" href="./index.html">Edge Machine</a>' in HTML
   and '<body class="sports-page sport-nba">' in HTML,
   "the one shared shell is up, the brand is the site root, and the body is the NBA sport page")
ok('class="sport-row"' not in HTML and 'class="page-menu"' not in HTML
   and "Pages ⌄" not in HTML and '<nav class="sports"' not in HTML,
   "no third header: no sport row, Pages menu, or sport selector")
main_nav = re.search(r'<nav class="main"[^>]*>.*?</nav>', HTML, re.S)
main_nav = main_nav.group(0) if main_nav else ""
nba_tab = re.search(r'<a\b[^>]*href="./nba.html"[^>]*>', main_nav)
ok(nba_tab is not None and 'aria-current="page"' in nba_tab.group(0)
   and main_nav.count('aria-current="page"') == 1 and HTML.count('<nav class="main"') == 1,
   "only the NBA pill is current")
ok('<script src="./sports.js"></script>' in HTML, "the NBA page still loads sports.js")
ok('<nav class="nba-local-nav" aria-label="NBA sections">' in HTML
   and all(f'href="#{sid}">{label}</a>' in HTML for sid, label in
           (("matchups", "Upcoming"), ("graded", "Results"), ("teams", "Teams"))),
   "the Upcoming / Results / Teams jump pills are in the sub-nav")
head = HTML.split('<section id="matchups">', 1)[0]
ok("<h1>NBA</h1>" in head and "Expected combined points · tip times CT" in head
   and "Pace data as of Oct 1, 1:00 PM CT" in head and "Open a matchup" not in HTML,
   "the header is the title, one line, and the freshness line")
ok(fmt.display_updated(NOW) in HTML and "CT" in fmt.display_updated(NOW),
   "the stamp is Updated … CT for the pinned clock")
about = re.search(r'<details class="section-disclosure nba-about">.*?</details>', HTML, re.S)
ok(about and " open" not in about.group(0).split(">", 1)[0]
   and len(re.findall(r"[.!?](\s|$)", _text(about.group(0)))) <= 4,
   "About this desk is collapsed and a few sentences")
css = open(os.path.join(ROOT, "public_site", "site.css"), encoding="utf-8").read()
ok("color-scheme: dark" in css and "prefers-color-scheme: light" not in css, "the stylesheet is dark only")
ok("tempo" not in css and "pace-leader" not in css, "the bar and leader-tile styles are gone")
ok("tr.nba-detail[hidden] { display: none !important; }" in css,
   "a hidden detail row stays hidden under the phone cards")
ok("td.is-lead" in css and ".nba-err.err-ok" in css and ".nba-err.err-far" in css,
   "the lead mark and error colours are styled")
js = open(os.path.join(ROOT, "public_site", "sports.js"), encoding="utf-8").read()
ok("button.nba-more" in js and "aria-expanded" in js, "sports.js wires the row chevron")

labelled = HTML
ok(HTML.count('data-l=""') >= 1 and 'data-l="" data-l=' not in HTML
   and 'data-l="1Q"' in HTML and HTML.count("<thead>") == 3,
   "the page names each column for the phone cards and leaves the detail cell unlabelled")
ok(sandbox_build.label_cells(HTML) == HTML, "labelling the page again changes nothing")

empty = N.build({"window": 5, "games": [
    _game("late", NOW + timedelta(hours=30), "SOON", "LATER"),
    _game("gone", NOW - timedelta(hours=30), "MIA", "TOR", completed=True,
          roll_exp_ft=1.1, act_ft=2, err_ft=0.9),
], "seed": {"teams": {"SOON": _ft(50, 50), "MIA": _ft(30, 30)}}}, now=NOW)
ok(N.EMPTY_UPCOMING in empty and "nba-row" not in _section(empty, "matchups"),
   "no game in the next 24h is an empty board, not a stale row")
ok(N.EMPTY_GRADED in empty and "Last 24h: no graded game yet." in empty,
   "no graded game is said plainly in both places")
ok("<b>SOON</b>" in _section(empty, "teams"), "the team reference still lists the teams")

bare = N.build(BLOB)
ok("Updated Oct 1, 1:00 PM CT" in bare and 'data-away="BKN"' not in bare,
   "with no clock passed, the page uses the file's own built time")


def _serve(directory):
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=directory, **kwargs)

        def log_message(self, fmt, *args):
            return

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


STATE = r"""
() => {
  const doc = document.documentElement;
  const detail = document.getElementById(document.querySelector("#matchups button.nba-more").getAttribute("aria-controls"));
  const table = document.querySelector("#matchups table");
  const results = document.querySelector("#graded details");
  const teams = document.querySelector("#teams details");
  const row = detail.previousElementSibling;
  const vis = (el) => el && getComputedStyle(el).display !== "none" && el.getBoundingClientRect().height > 0;
  return {
    overflow: doc.scrollWidth > doc.clientWidth + 1,
    detailShown: vis(detail),
    expanded: document.querySelector("#matchups button.nba-more").getAttribute("aria-expanded"),
    tableDisplay: getComputedStyle(table).display,
    resultsOpen: results.open, teamsOpen: teams.open,
    rowTop: row.getBoundingClientRect().top, detailTop: detail.getBoundingClientRect().top,
    bars: document.querySelectorAll("meter, progress, .tempo-scale").length,
  };
}
"""


def browser_checks():
    print("\nbrowser")
    from require_browser import require_browser
    sync_playwright = require_browser("test_nba_board.py")
    if sync_playwright is None:
        return
    folder = tempfile.mkdtemp(prefix="nba-board-")
    for name in ("site.css", "tables.js", "sports.js"):
        os.symlink(os.path.join(ROOT, "public_site", name), os.path.join(folder, name))
    with open(os.path.join(folder, "board.html"), "w", encoding="utf-8") as fh:
        fh.write(labelled)
    httpd = _serve(folder)
    base = f"http://127.0.0.1:{httpd.server_address[1]}/board.html"
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 800})
            page.goto(base, wait_until="load")
            page.wait_for_timeout(40)
            wide = page.evaluate(STATE)
            ok(not wide["detailShown"] and wide["expanded"] == "false",
               "desktop starts with every detail row closed")
            ok(not wide["resultsOpen"] and not wide["teamsOpen"], "Results and Team reference start collapsed")
            ok(wide["tableDisplay"] == "table" and not wide["overflow"] and wide["bars"] == 0,
               f"at 1280px the board is a table with no bars and no sideways scroll (overflow {wide['overflow']})")
            page.locator("#matchups button.nba-more").first.click()
            page.wait_for_timeout(40)
            opened = page.evaluate(STATE)
            ok(opened["detailShown"] and opened["expanded"] == "true"
               and opened["detailTop"] > opened["rowTop"] and not opened["overflow"],
               "the chevron opens the detail row under its game")
            page.locator("#matchups button.nba-more").first.click()
            page.wait_for_timeout(40)
            ok(not page.evaluate(STATE)["detailShown"], "a second press closes it again")
            page.locator("#graded summary").click()
            page.wait_for_timeout(40)
            ok(page.evaluate(STATE)["resultsOpen"] and page.locator("#graded table").is_visible(),
               "Results opens to its table")
            page.locator("#teams summary").click()
            page.wait_for_timeout(40)
            scored = page.locator("#teams th.num").first  # the Scored column
            scored.click()
            page.wait_for_timeout(40)
            sort = scored.get_attribute("aria-sort")
            ok(sort in ("ascending", "descending"), f"the team reference sorts on a column ({sort})")
            page.set_viewport_size({"width": 390, "height": 800})
            page.reload(wait_until="load")
            page.wait_for_timeout(40)
            narrow = page.evaluate(STATE)
            ok(narrow["tableDisplay"] == "block" and not narrow["detailShown"] and not narrow["overflow"],
               f"at 390px the table is the phone cards, the detail stays hidden, and nothing scrolls sideways "
               f"(display {narrow['tableDisplay']}, overflow {narrow['overflow']})")
            page.locator("#matchups button.nba-more").first.click()
            page.wait_for_timeout(40)
            phone_open = page.evaluate(STATE)
            ok(phone_open["detailShown"] and not phone_open["overflow"],
               "on the phone the chevron opens the detail card without widening the page")
            browser.close()
    finally:
        httpd.shutdown()


browser_checks()

print()
if FAILS:
    print(f"{len(FAILS)} FAILED")
    sys.exit(1)
print("all passed")
