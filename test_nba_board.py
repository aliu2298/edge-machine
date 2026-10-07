#!/usr/bin/env python3
"""NBA matchup board. Fixture clock, no live ledger, no wall clock.

The page is presentation. These checks fail if a card crosses the 24h line,
the middle card reprints a recomputed total, the tempo bar uses a fixed
scale or paints a real value as an empty track, the error is act minus
expected instead of the file's err_*, a missing teams record is called
'No recent game', or a player name is left unescaped.
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
import site_chrome

FAILS = []
ROOT = os.path.dirname(os.path.abspath(__file__))
NOW = datetime.datetime(2026, 10, 6, 18, 0, tzinfo=timezone.utc)
MINUS = "\u2212"
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


def _pct(value, lo, hi):
    """The page's scale, copied here so a mutated builder fails this file."""
    if hi <= lo:
        return 100
    number = int(round((value - lo) / (hi - lo) * 100.0))
    return max(0, min(100, number))


def _fill(value, lo, hi):
    """Painted width. The scale stays min-to-max. A real value is at least 8%."""
    raw = _pct(value, lo, hi)
    if raw >= 100:
        return 100
    return max(8, raw)


def _section(html, sid):
    """The inside of one section, including the cards nested in it."""
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


def _articles(fragment):
    return re.findall(r'<article class="matchup\b.*?</article>', fragment, re.S)


def _article(fragment, away):
    for article in _articles(fragment):
        if f'data-away="{site_chrome.esc(away)}"' in article:
            return article
    return ""


def _rows(fragment):
    table = re.search(r'<table class="team-table">.*?</table>', fragment, re.S)
    if not table:
        return []
    return re.findall(r"<tr>.*?</tr>", table.group(0), re.S)


def _row(fragment, team):
    for row in _rows(fragment):
        if f"<td>{team}</td>" in row:
            return row
    return ""


def _tempo(article, period):
    match = re.search(
        rf'<div class="tempo-row" data-period="{period}">(.*?)</div></div>', article, re.S)
    return match.group(1) if match else ""


def _read(block):
    match = re.search(r'class="tempo-read">(.*?)</p>', block, re.S)
    return match.group(1) if match else ""


def _attr(block, kind):
    match = re.search(rf'class="tempo-{kind}" data-pct="(\d+)"', block)
    return None if match is None else int(match.group(1))


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


def _scale(values):
    return min(values), max(values)


print("windows, order, and the middle card")
BLOB = _blob()
HTML = N.build(BLOB, now=NOW)
UP = _section(HTML, "matchups")
GRADED = _section(HTML, "graded")
TEAMS = _section(HTML, "teams")
ok(UP and GRADED and TEAMS, "the board has upcoming, graded, and team sections")

upcoming = _articles(UP)
eq([re.search(r'data-away="([^"]*)"', article).group(1) for article in upcoming],
   [site_chrome.esc(HOSTILE), "BKN", "CC", "AA", "IN"],
   "upcoming cards are start order, then id, away on the card")
eq([re.search(r'data-home="([^"]*)"', article).group(1) for article in upcoming],
   ["POR", "CHA", "DD", "BB", "SIDE"],
   "home sits on the card opposite the away team")

bkn = _article(UP, "BKN")
ok(bkn.index('class="team-card team-away"') < bkn.index('class="expect-card"')
   < bkn.index('class="team-card team-home"'),
   "a matchup is away, then the expectation, then home")
ok(">Away<" in bkn and ">Home<" in bkn, "the two sides are named, not only placed")
ok("56.2" in _read(_tempo(bkn, "q1")) and "114.0" in _read(_tempo(bkn, "h1"))
   and "221.5" in _read(_tempo(bkn, "ft")),
   "the middle card prints the file's roll_exp values")
ok("combined" in _read(_tempo(bkn, "q1")) and "Combined expectations" in bkn,
   "the middle card says the totals are combined")
ok("25.5" not in bkn, "the middle card does not recompute the total from O and D")
ok("11.1" in bkn and "12.2" in bkn and "O-D-" in bkn,
   "the away card shows the stored full-game averages and label")
ok("13.3" in bkn and "14.4" in bkn, "the home card shows the stored full-game averages")
ok("Nets" not in HTML and "Brooklyn" not in HTML and "Celtics" not in HTML and "Boston" not in HTML,
   "a team with no stored full name is not given one")

inside = _article(UP, "IN")
ok("IN" in UP and 'data-window="upcoming"' in inside, "a tip one second inside 24h is a card")
ok(_row(TEAMS, "IN") == "" and _row(TEAMS, "BKN") == "" and _row(TEAMS, "CHA") == "",
   "teams on a card in the next 24h leave the list")
edge = _row(TEAMS, "EDGE")
ok('data-away="EDGE"' not in HTML and "Next up" in edge and fmt.when(NOW + timedelta(hours=24)) in edge,
   "a tip exactly 24h out stays in the list as Next up")
soon = _row(TEAMS, "SOON")
ok("Next up" in soon and fmt.when(NOW + timedelta(hours=36)) in soon,
   "a game in the 24–48h window is flagged Next up with the tip")
out = _row(TEAMS, "OUT")
ok(out and "Next up" not in out, "a tip exactly 48h out is not Next up")
ok(_row(TEAMS, "AAA") and "Next up" not in _row(TEAMS, "AAA"),
   "a team with no game in the window is unflagged")
names = []
for row in _rows(TEAMS):
    cell = re.search(r"<td>([^<]*)</td>", row)
    if cell:
        names.append(cell.group(1))
eq(names[0], "WALL", "the list stays in combined order, with Next up as a flag")
aaa = _row(TEAMS, "AAA")
ok(">100.0<" in aaa and ">80.0<" in aaa and ">180.0<" in aaa and "O+D+" in aaa,
   "the list still prints seed scored, allowed, combined, and the seed label")


print("\ntempo track")
# Expectations on the page, skipped and the 30h-old game excluded.
q1_lo, q1_hi = _scale([50.0, 40.0, 40.0, 56.2, 57.3])
h1_lo, h1_hi = _scale([80.0, 80.0, 114.0, 112.3])
ft_lo, ft_hi = _scale([160.0, 160.0, 200.0, 221.5, 227.9])
eq(_attr(_tempo(bkn, "q1"), "fill"), _pct(56.2, q1_lo, q1_hi), "BKN 1Q bar width")
ok(_pct(56.2, q1_lo, q1_hi) > 8, "BKN 1Q is above the visibility floor, so the floor does not move it")
eq(_attr(_tempo(bkn, "h1"), "fill"), _pct(114.0, h1_lo, h1_hi), "BKN 1H bar width")
eq(_attr(_tempo(bkn, "ft"), "fill"), _pct(221.5, ft_lo, ft_hi), "BKN full-game bar width")
eq(_pct(40.0, q1_lo, q1_hi), 0, "40 is the low end of the 1Q scale")
eq(_attr(_tempo(_article(UP, "CC"), "q1"), "fill"), 8,
   "the low end still paints about 8% so the bar is not an empty track")
ok("40.0" in _read(_tempo(_article(UP, "CC"), "q1")),
   "the floored bar still prints the stored expectation")
eq(_attr(_tempo(_article(UP, "AA"), "q1"), "fill"),
   _attr(_tempo(_article(UP, "CC"), "q1"), "fill"),
   "two games with the same expectation get the same bar width")
inside_q1 = _tempo(inside, "q1")
eq(_attr(inside_q1, "fill"), _fill(50.0, q1_lo, q1_hi), "inside game 1Q bar width")
eq(_attr(inside_q1, "mark"), _pct(53, q1_lo, q1_hi), "actual marker uses the expectation scale")
ok("error +9.0" in _read(inside_q1) and "error +3.0" not in _read(inside_q1),
   "the upcoming card shows the file's positive error, not actual minus expected")
h1 = _tempo(inside, "h1")
ok("expected — combined" in _read(h1) and _attr(h1, "fill") is None,
   "a missing expectation is an em dash and an empty bar")
ok(not re.search(r"\bnan\b", HTML, re.I), "NaN is never printed")

graded = _article(GRADED, "GS")
ok(graded and 'data-window="graded"' in graded, "a completed game in the last 24h is a graded card")
ok('data-away="MIA"' not in HTML and "9.9" not in HTML,
   "a completed game older than 24h is not a card")
gq1 = _tempo(graded, "q1")
eq(_attr(gq1, "mark"), _pct(55, q1_lo, q1_hi), "graded 1Q marker")
ok(f"error {MINUS}1.5" in _read(gq1) and f"{MINUS}2.3" not in _read(gq1) and "-2.3" not in _read(gq1),
   "a negative error uses the file's err and a real minus")
gh1 = _tempo(graded, "h1")
eq(_attr(gh1, "mark"), 100, "an actual above every expectation clamps to the end of the bar")
ok("outside the range of expectations on this page" in _read(gh1),
   "a clamped actual is also said in text")
ok("error +5.0" in _read(gh1) and "27.7" not in _read(gh1),
   "the high actual still shows the file's error")
gft = _tempo(graded, "ft")
eq(_attr(gft, "mark"), _pct(210, ft_lo, ft_hi), "graded full-game marker")
ok("error +4.0" in _read(gft) and f"{MINUS}17.9" not in HTML and "-17.9" not in HTML,
   "the full-game error is the file's +4.0")
for period in ("q1", "h1", "ft"):
    block = _tempo(graded, period)
    label = re.search(r'aria-label="([^"]*)"', block)
    ok(label is not None and label.group(1) == _read(block),
       f"the {period} bar's aria-label matches its text")
ok("33.3" in graded and "88.8" not in graded, "a graded card uses the game's rolling averages")
tied = N.build({"window": 5, "games": [
    _game("a", NOW + timedelta(hours=2), "AA", "BB",
          roll_exp_q1=40.0, roll_exp_h1=40.0, roll_exp_ft=40.0),
    _game("b", NOW + timedelta(hours=3), "CC", "DD",
          roll_exp_q1=40.0, roll_exp_h1=40.0, roll_exp_ft=40.0),
], "seed": {"teams": {}}}, now=NOW)
tied_q1 = _tempo(_article(_section(tied, "matchups"), "AA"), "q1")
eq(_attr(tied_q1, "fill"), 100,
   "when every expectation of a period is equal, the bar fills instead of a fixed scale")
ok("40.0" in _read(tied_q1), "the tied bar still prints the stored expectation")
ok("88.8" in _row(TEAMS, "GS"), "the same team keeps its seed average on the list")
ok("&lt;b&gt;Warriors&lt;/b&gt;" in graded and "<b>Warriors</b>" not in HTML,
   "a stored full name is shown and escaped")


print("\nPRA, skipped, empty, shell")
def _pra(article, team):
    # The away card is first. Split so the two slots are not mixed.
    away, _rest = article.split('class="team-card team-home"', 1)
    home = _rest
    block = away if f'class="team-abbr">{team}<' in away else home
    match = re.search(r'class="pra-value">(.*?)</span>', block)
    period = re.search(r'class="period-value">(.*?)</span>', block)
    return (match.group(1) if match else "", period.group(1) if period else "")

eq(_pra(bkn, "BKN"), ("Coming soon", "Coming soon"),
   "with no teams record the PRA slot is Coming soon, not No recent game")
eq(_pra(bkn, "CHA"), ("Coming soon", "Coming soon"),
   "the home card is also Coming soon when its teams entry is absent")
ok("No recent game" not in HTML, "absent keys are not described as no recent game")
ok("Should Not Show" not in HTML and "Stephen Curry" not in HTML,
   "a PRA hung on the game row is not read")
eq(_pra(graded, "GS"), ("Coming soon", "Coming soon"),
   "a completed game without teams[T] stays Coming soon")
eq(_pra(inside, "IN"), ("Coming soon", "Coming soon"),
   "1Q and 1H stay Coming soon when neither the game nor teams has them")

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
gs = _article(fed_up, "GS")
eq(_pra(gs, "GS"), (
    "Charles Bassey 21 PRA (12 pts · 8 reb · 1 ast), at LAC Oct 4",
    "1Q scored 20.0 · allowed 14.0 · 1H scored 48.0 · allowed 42.0",
), "a stored top_pra renders, and the matchup prefers the pre-tip quarter rates")
ok("1.1" not in _pra(gs, "GS")[1] and "1.2" not in _pra(gs, "GS")[1],
   "the team roll does not replace pre-tip quarter rates")
lac = _pra(gs, "LAC")
eq(lac[1], "1Q scored 13.6 · allowed 19.2 · n 5 · 1H scored 42.0 · allowed 46.8 · n 5",
   "with no pre-tip quarter keys the card uses teams[T].roll, including n")
ok("4 PRA" in lac[0] and "vs NY Oct 3" in lac[0] and "43" not in lac[0],
   "the home card shows the stored pra and the home opponent, not the sum")
ok(HOSTILE_PLAYER not in fed and "&lt;img src=x onerror=alert(1)&gt;" in fed,
   "a hostile player name is escaped")
fed_tags = _Tags()
fed_tags.feed(fed)
ok("img" not in fed_tags.tags and not fed_tags.handlers, "the player name is not a tag")
bkn_fed = _pra(_article(fed_up, "BKN"), "BKN")
eq(bkn_fed[0], "No recent game", "last_game null is No recent game")
eq(bkn_fed[1], "1Q scored 10.0 · allowed 11.0 · n 5 · 1H scored — · allowed 28.0 · n 5",
   "a null last game still shows the stored quarter rates, and a bad number is an em dash")
eq(_pra(_article(fed_up, "BKN"), "CHA"), ("Coming soon", "Coming soon"),
   "a missing team entry is Coming soon on both slots")
ok("None" not in fed and not re.search(r"\bnan\b", fed, re.I),
   "the fed card never prints None or NaN")

skipped = _article(UP, HOSTILE)
ok("Skipped" in skipped and "&lt;script&gt;alert(1)&lt;/script&gt;" in skipped,
   "a skipped game in the window says why, escaped")
ok("999.9" not in HTML and "tempo-scale" not in skipped,
   "a skipped game does not show an expectation")
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
ok('class="sport-row"' in HTML and 'class="topbar"' in HTML
   and 'href="./nba.html" aria-current="page"' in HTML,
   "the dark shell is up and the NBA tab is current")
sports = re.search(r'<nav class="sports"[^>]*>.*?</nav>', HTML, re.S).group(0)
nba_tab = re.search(r'<a\b[^>]*href="./nba.html"[^>]*>', sports)
ok(nba_tab is not None and 'aria-current="page"' in nba_tab.group(0)
   and "aria-describedby" not in nba_tab.group(0)
   and sports.count('aria-current="page"') == 1,
   "only the NBA tab is current, and that tab is not described as coming soon")
ok(all(f'href="./{sport}.html"' in sports for sport in ("soccer", "tennis", "cricket", "crypto"))
   and 'aria-disabled="true"' not in sports,
   "the other sport tabs reach the published pages")
ok("theme-toggle" not in HTML and "data-theme" not in HTML, "no theme toggle")
ok("download" not in HTML.lower() and ".csv" not in HTML.lower(), "no download or CSV")
ok(fmt.display_updated(NOW) in HTML and "CT" in fmt.display_updated(NOW),
   "the stamp is Updated … CT for the pinned clock")
css = open(os.path.join(ROOT, "public_site", "site.css"), encoding="utf-8").read()
ok("color-scheme: dark" in css and "prefers-color-scheme: light" not in css, "the stylesheet is dark only")
narrow = css.split("@media (max-width: 640px)", 1)[-1]
ok(".matchup-grid { grid-template-columns: minmax(0, 1fr); }" in narrow,
   "at 640px the matchup cards stack")

empty = N.build({"window": 5, "games": [
    _game("late", NOW + timedelta(hours=30), "SOON", "LATER"),
    _game("gone", NOW - timedelta(hours=30), "MIA", "TOR", completed=True,
          roll_exp_ft=1.1, act_ft=2, err_ft=0.9),
], "seed": {"teams": {"SOON": _ft(50, 50), "MIA": _ft(30, 30)}}}, now=NOW)
ok(N.EMPTY_UPCOMING in empty and "<article" not in empty,
   "no game in the next 24h is an empty board, not a stale card")
ok("Next up" in _row(_section(empty, "teams"), "SOON"),
   "Next up still flags a 24–48h game when nothing is a card")

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


LAYOUT = r"""
() => {
  const grid = document.querySelector("#matchups .matchup-grid");
  const cards = [...grid.children];
  const box = (el) => {
    const r = el.getBoundingClientRect();
    return { top: r.top, left: r.left, right: r.right, bottom: r.bottom };
  };
  const tracks = getComputedStyle(grid).gridTemplateColumns.split(" ").filter(Boolean);
  const doc = document.documentElement;
  const bars = [...document.querySelectorAll(".tempo-row")].map((row) => {
    const scale = row.querySelector(".tempo-scale");
    const fill = row.querySelector(".tempo-fill");
    const mark = row.querySelector(".tempo-mark");
    const sw = scale.getBoundingClientRect().width;
    const shown = fill && getComputedStyle(fill).display !== "none";
    const fw = shown ? fill.getBoundingClientRect().width : 0;
    let marker = null;
    if (mark && sw) {
      const m = mark.getBoundingClientRect();
      const center = ((m.left + m.right) / 2 - scale.getBoundingClientRect().left) / sw * 100;
      marker = { pct: Number(mark.getAttribute("data-pct")), center };
    }
    return {
      period: row.getAttribute("data-period"),
      pct: fill ? Number(fill.getAttribute("data-pct")) : 0,
      width: sw ? fw / sw * 100 : 0,
      marker,
      label: (row.querySelector(".tempo-scale") || {}).getAttribute
        ? row.querySelector(".tempo-scale").getAttribute("aria-label") : "",
      text: (row.querySelector(".tempo-read") || {}).textContent || "",
    };
  });
  return {
    tracks: tracks.length,
    cards: cards.map(box),
    overflow: doc.scrollWidth > doc.clientWidth + 1,
    bars,
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
    os.symlink(os.path.join(ROOT, "public_site", "site.css"), os.path.join(folder, "site.css"))
    os.symlink(os.path.join(ROOT, "public_site", "tables.js"), os.path.join(folder, "tables.js"))
    with open(os.path.join(folder, "board.html"), "w", encoding="utf-8") as fh:
        fh.write(HTML)
    os.symlink(os.path.join(ROOT, "public_site", "sports.js"), os.path.join(folder, "sports.js"))
    httpd = _serve(folder)
    base = f"http://127.0.0.1:{httpd.server_address[1]}/board.html"
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 800})
            page.goto(base, wait_until="load")
            page.wait_for_timeout(40)
            ok(not page.locator("#matchups .team-card").first.is_visible(),
               "desktop starts with compact summaries")
            page.locator(".nba-results > summary").click()
            for summary in page.locator("details.nba-game > summary").all():
                summary.click()
            wide = page.evaluate(LAYOUT)
            ok(wide["tracks"] == 3 and not wide["overflow"],
               f"at 1280px the matchup is three columns and the page does not scroll sideways "
               f"({wide['tracks']} tracks, overflow {wide['overflow']})")
            away, mid, home = wide["cards"]
            ok(away["left"] < mid["left"] < home["left"]
               and abs(away["top"] - home["top"]) < 4,
               "at 1280px away is left of the expectation and home is right")
            page.set_viewport_size({"width": 640, "height": 800})
            page.reload(wait_until="load")
            page.wait_for_timeout(40)
            first_detail = page.locator("#matchups details.nba-game").first
            ok(first_detail.get_attribute("open") is None,
               "at 640px the first matchup starts as a compact closed row")
            ok(not page.locator("#matchups .team-card").first.is_visible(),
               "mobile detail starts collapsed")
            page.locator("#matchups .nba-game-summary").first.click()
            ok(page.locator("#matchups .team-card").first.is_visible(),
               "mobile summary opens the analysis")
            narrow = page.evaluate(LAYOUT)
            ok(narrow["tracks"] == 1 and not narrow["overflow"],
               f"at 640px the matchup stacks and the page does not scroll sideways "
               f"({narrow['tracks']} tracks, overflow {narrow['overflow']})")
            away, mid, home = narrow["cards"]
            ok(away["bottom"] <= mid["top"] + 16 and mid["bottom"] <= home["top"] + 16
               and abs(away["left"] - home["left"]) < 2,
               "at 640px the cards stack away, expectation, home")
            bars = {bar["period"]: bar for bar in wide["bars"]}
            # The first matchup on the page is the skipped game, which has no bars.
            # wide["bars"] is every tempo row. Check the graded 1Q marker and a fill.
            graded_q1 = [bar for bar in wide["bars"]
                         if bar["period"] == "q1" and bar["marker"] and bar["marker"]["pct"] == _pct(55, q1_lo, q1_hi)]
            ok(len(graded_q1) == 1, "the graded 1Q marker is on the page")
            if graded_q1:
                bar = graded_q1[0]
                ok(abs(bar["width"] - bar["pct"]) <= 2,
                   f"the 1Q fill is as wide as its data-pct ({bar['width']:.1f} vs {bar['pct']})")
                col = bar["marker"]["pct"] or 1
                want = col - 0.5
                ok(abs(bar["marker"]["center"] - want) <= 2.5,
                   f"the actual marker sits on its column ({bar['marker']['center']:.1f} vs {want})")
                ok(bar["label"] == bar["text"] and "combined" in bar["text"],
                   "the bar label and the visible text say the same thing")
            page.set_viewport_size({"width": 1280, "height": 800})
            page.wait_for_timeout(40)
            ok(page.locator("#matchups .team-card").first.is_visible(),
               "returning to desktop preserves the user's expanded analysis")
            browser.close()
    finally:
        httpd.shutdown()


browser_checks()

print()
if FAILS:
    print(f"{len(FAILS)} FAILED")
    sys.exit(1)
print("all passed")
