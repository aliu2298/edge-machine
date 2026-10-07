#!/usr/bin/env python3
"""The Soccer page: a flat fixture list grouped by day, and a rules table.

Presentation only. The record and the ROI are the Sandbox row's own figures,
compared as strings. Nothing here grades a bet or writes a ledger. A game
label is printed through S.position_label: "A v B" in the ledger reads
"A vs B" on the page. The pick on a fixture row is the position a reader
would take, derived from the market title and the side backed; the stored
label and side are untouched.
"""
import datetime
import os
import re
import subprocess
import sys
from datetime import timedelta, timezone

import fmt
import sandbox_build as B
import sandbox_sources as S

FAILS = []
ROOT = os.path.dirname(os.path.abspath(__file__))
NOW = datetime.datetime(2026, 10, 5, 16, 0, tzinfo=timezone.utc)


def _head_sha():
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return out or "unknown"


SHA = _head_sha()


def ok(cond, msg):
    print(f"  {'ok  ' if cond else 'FAIL'} {msg}")
    if not cond:
        FAILS.append(msg)


def eq(got, want, msg):
    ok(got == want, msg if got == want else f"{msg} — got {got!r}, want {want!r}")


def _quote(i, source, sport, status, start, label, price=0.55,
          url="https://kalshi.com/markets/example", venue="kalshi", bet=True):
    when = start if isinstance(start, datetime.datetime) else NOW + timedelta(hours=start)
    won = status == "won"
    return dict(
        id=f"{source}:{sport}:{i}:{status}:{label}",
        source=source, sport=sport, bet=bet, status=status,
        pick="b", price=price,
        result=("a" if won else "b") if status in ("won", "lost") else None,
        venue=venue,
        pnl=(round(100 * (1 / price - 1), 2) if won else -100.0) if status in ("won", "lost") else None,
        start=when.isoformat(),
        logged=(when - timedelta(hours=2)).isoformat(),
        date=when.date().isoformat(),
        price_a=price, price_b=round(1 - price, 2),
        side_a="Yes", side_b="No",
        label=label,
        market_id=f"KXTEST-{source}-{i}",
        url=url,
    )


def _settled(source, sport, n=4, won=3, price=0.60):
    rows = []
    for i in range(n):
        status = "won" if i < won else "lost"
        rows.append(_quote(
            i, source, sport, status,
            NOW - timedelta(days=3, hours=i),
            f"Settled {source} {i}",
            price=price,
        ))
    return rows


def _fixture():
    """Several markets, open picks across three days, and one stored fixture with no stake."""
    quotes = []
    quotes += _settled("o15_form_l10", "soccer_o15", n=6, won=4)
    quotes += _settled("o15_ranked", "soccer_o15", n=4, won=1, price=0.70)
    quotes += _settled("o15_form_l10", "soccer_o15_cup", n=3, won=2)
    quotes += _settled("btts_form_l10", "soccer_btts", n=5, won=2, price=0.48)
    quotes += _settled("corners_under", "soccer_corners", n=4, won=3, price=0.52)
    soon = [
        (1, "Alpha v Beta soonest"),
        (2, "Gamma v Delta second"),
        (3, "Epsilon v Zeta third"),
        (4, "Eta v Theta fourth"),
        (30, "Iota v Kappa fifth and later"),
    ]
    for i, (hours, label) in enumerate(soon):
        quotes.append(_quote(100 + i, "o15_form_l10", "soccer_o15", "open", hours, label))
    quotes.append(_quote(
        200, "o15_ranked", "soccer_o15", "open", 20, "Lambda v Mu ranked"))
    quotes.append(_quote(
        300, "btts_form_l10", "soccer_btts", "open", 40, "Nu v Xi btts"))
    # Open, past 48 hours: listed on its own day like any other open pick.
    quotes.append(_quote(
        400, "corners_under", "soccer_corners", "open", 80, "Omicron v Pi later"))
    # A label and a url the page must not turn into markup or a script link.
    quotes.append(_quote(
        401, "corners_under", "soccer_corners", "open", 90,
        'Rho <script>alert(1)</script> v "Sigma"',
        url="javascript:alert(1)",
        venue="polymarket_us",
    ))
    # A record, no open bet, and a fixture the tracker already logged without a stake.
    quotes += _settled("team1_form_l5", "soccer_team1", n=4, won=3, price=0.62)
    quotes.append(_quote(
        500, "team1_form_l5", "soccer_team1", "open", 36,
        "Window Side v Keeper", bet=False))
    quotes += _settled("team2_ranked", "soccer_team2", n=4, won=2, price=0.58)
    quotes.append(_quote(
        501, "team2_ranked", "soccer_team2", "open", 12,
        "Soon Side v Tonight", bet=False))
    # Same shape, kickoff past 48 hours: not shown, there is nothing to watch yet.
    quotes += _settled("team1_form_l5", "soccer_team1_cup", n=3, won=1, price=0.61)
    quotes.append(_quote(
        502, "team1_form_l5", "soccer_team1_cup", "open", 72,
        "Far Side v Later", bet=False))
    return {"quotes": quotes}, {"pairs": {}}


def _rows(d, st):
    import sport_tab
    return sport_tab.family_rows(d, st, "Soccer")


def _roi_html(row):
    """The ROI cell the Sandbox row already prints. Not a new formula."""
    a = row["a"]
    if not a["n"]:
        return "—"
    thin = a["n"] < B.MIN_N
    klass = "mut" if thin else fmt.tone(a["roi_fee"], ".1f", 100)
    return f'<span class="{klass}">{B.pct(a["roi_fee"], sign=True)}</span>'


def _verdict_html(row):
    label, chip, _order = B.VERDICTS[row["v"]]
    return f'<span class="sig {chip}">{B.esc(label)}</span>'


def _section(markup, name):
    """A top-level page section: from its opening tag to the next top-level section or the footer."""
    match = re.search(rf'<section id="{name}"[^>]*>(.*?)(?=<section id="|<footer)', markup, re.S)
    return match.group(1) if match else ""


def _rule_rows(html):
    return re.findall(r'<tr class="rule-row"(.*?)</tr>', html, re.S)


def _attr(frag, name):
    m = re.search(rf'\b{name}="([^"]*)"', frag)
    return m.group(1) if m else None


def _shown(label):
    """How a ledger label is printed on the page: 'A v B' becomes 'A vs B'."""
    return fmt.contest(label)


def _absent(label, html):
    """Neither the stored spelling nor the printed one is on the page."""
    return label not in html and _shown(label) not in html


print(f"SHA {SHA}")

import soccer_build
import soccer_cards as C
import tennis_build
import cricket_build
from unittest.mock import patch

# The Kalshi pre-flight file on disk is whatever the last job left. The page
# under test gets a fresh one, so the System fold starts closed.
_fresh = patch("sport_tab.preflight_report",
               return_value=({}, '<div class="note sm">Kalshi checked 1.0h ago.</div>'))
_fresh.start()

print("\nsoccer page shape")
d, st = _fixture()
html = soccer_build.build(d, st, NOW)
rows = _rows(d, st)
ok(rows, "the fixture has soccer lanes")
ok('id="fixtures"' in html and 'id="rules"' in html and 'id="health"' in html,
   "the page has Fixtures, Rules and System sections")
ok('href="#fixtures"' in html and 'href="#rules"' in html and 'href="#health"' in html,
   "the sub-nav jumps to Fixtures, Rules and System")
ok(html.find('id="fixtures"') < html.find('id="rules"') < html.find('id="health"'),
   "fixtures come first, then rules, then the folded system note")
ok("Open picks and the rules that fire them · kickoff times CT" in html,
   "the one-line lede names open picks, rules and the CT clock")
ok(fmt.display_updated(NOW) in html.split("<main", 1)[-1],
   "the freshness stamp is printed under the title")
ok('class="soccer-prod-strip"' in html and html.find('class="soccer-prod-strip"') < html.find('id="fixtures"'),
   "Production rules sit as a chip strip under the header")
for gone in ('class="rule-card"', 'class="rule-grid"', "soccer-fixture-state", "Pick in",
             "Later / time unconfirmed", "soccer-local-nav", "No tracked fixture today",
             "Next 48 hours", "Open picks past kickoff", "<h3>Goals</h3>", "By competition",
             "How each rule is defined", 'class="tiles"'):
    ok(gone not in html, f"the page no longer prints {gone!r}")
ok("<script" not in html.split("<main", 1)[-1].split("</main>", 1)[0].lower()
   or 'src="./' in html, "the page body does not grow an inline script")
ok("javascript:" not in html, "a javascript: game url is not written")
ok("&lt;script&gt;" in html, "a game label is escaped")
ok('class="rule-card"' not in html, "no flip cards")

print("\nfixtures: one list grouped by day")
fixtures = _section(html, "fixtures")
ok(fixtures, "the fixtures section renders")
days = re.findall(r'<h3 class="soccer-day-head">(.*?)</h3>', fixtures)
ok(len(days) >= 3, f"fixtures are grouped under day headers ({days})")
ok(all(re.match(r"^(Mon|Tue|Wed|Thu|Fri|Sat|Sun) [A-Z][a-z]{2} \d{1,2}", re.sub("<[^>]+>", "", day)) for day in days),
   "a day header reads 'Thu Oct 9'")
ok(days[0].startswith("Mon Oct 5") and "<small>Today</small>" in days[0],
   "today's header is first and marked Today")
ok("Alpha vs Beta soonest" in fixtures and "Nu vs Xi btts" in fixtures
   and "Omicron vs Pi later" in fixtures,
   "every open pick is on the one list, including one past 48 hours")
ok("Alpha v Beta soonest" not in html and "Nu v Xi btts" not in html,
   "the page does not print the ledger's 'A v B' spelling")
order = [m for m in ("Alpha vs Beta soonest", "Lambda vs Mu ranked", "Iota vs Kappa fifth and later",
                     "Nu vs Xi btts", "Omicron vs Pi later") ]
pos = [fixtures.find(m) for m in order]
ok(all(p >= 0 for p in pos) and pos == sorted(pos), "fixtures run in kickoff order across days")
ok("Window Side vs Keeper" in fixtures and "Soon Side vs Tonight" in fixtures,
   "a fixture a rule has been shown, with no stake yet, is listed")
ok('class="soccer-pick-side is-watch">watching<' in fixtures,
   "an unstaked fixture reads 'watching' in the pick column, with no price")
ok(_absent("Far Side v Later", html), "an unstaked fixture past 48 hours is not listed")
rows_html = re.findall(r'<div class="soccer-row(?: is-past)?"', fixtures)
eq(len(rows_html), len(C._fixture_rows(d, rows, NOW)), "one flat row per fixture")
ok('class="soccer-pick-rule">Over 1.5 form rule</span>' in fixtures,
   "the rule name is printed, muted, after the price")
ok('class="soccer-pick-price">55¢</span>' in fixtures, "the price is the stored ask in cents")
ok(fixtures.count("<article") == 0 and "soccer-fixture-list" not in fixtures,
   "no boxes per fixture")
ok('class="soccer-day-head"' in fixtures, "day headers carry the sticky class")

print("\nfixtures: the pick in words")
over = _quote(900, "o15_form_l10", "soccer_o15", "open", 30, "City v United: over 1.5 goals")
over.update(pick="a", url="https://kalshi.com/markets/over")
eq(C.pick_text(over), "Over 1.5", "a Yes on an over market is 'Over 1.5'")
eq(C.pick_text(dict(over, pick="b")), "Under 1.5", "a No on an over market is 'Under 1.5'")
under35 = _quote(901, "u35_low_scoring", "soccer_u35", "open", 30, "Genoa v Fiorentina: over 3.5 goals")
eq(C.pick_text(under35), "Under 3.5", "the under-3.5 rule's No reads 'Under 3.5'")
btts = _quote(902, "btts_form_l10", "soccer_btts", "open", 30, "City v United: both teams to score")
btts.update(pick="a", url="https://kalshi.com/markets/btts")
eq(C.pick_text(btts), "BTTS yes", "a Yes on both teams to score is 'BTTS yes'")
eq(C.pick_text(dict(btts, pick="b")), "BTTS no", "a No on both teams to score is 'BTTS no'")
p05 = _quote(903, "p05_unbeaten", "soccer_p05", "open", 30, "Lens v Lyon: Lens to win (No = Lyon +0.5)")
eq(C.pick_text(p05), "Lyon +0.5", "a No on 'Lens to win (No = Lyon +0.5)' is 'Lyon +0.5'")
eq(C.pick_text(dict(p05, pick="a")), "Lens to win", "the Yes side of the same market is 'Lens to win'")
team1 = _quote(904, "team1_form_l5", "soccer_team1", "open", 30, "Ajax v PSV: Ajax to score 1+")
team1.update(pick="a")
eq(C.pick_text(team1), "Ajax 1+ goals", "a side to score 1+ reads 'Ajax 1+ goals'")
corners = _quote(905, "corners_under", "soccer_corners", "open", 30, "Ajax v PSV: 10+ corners")
eq(C.pick_text(corners), "Under 10 corners", "a No on '10+ corners' is 'Under 10 corners'")
winner = _quote(906, "mls_away_band", "soccer", "open", 30, "Saint Louis vs Los Angeles G")
winner.update(side_a="Saint Louis", side_b="Los Angeles G", pick="b")
eq(C.pick_text(winner), "Los Angeles G to win", "a match-winner pick names the side")
eq(C.pick_text(dict(winner, pick="draw")), "Draw", "a draw pick is 'Draw'")
odd = _quote(907, "o15_form_l10", "soccer_o15", "open", 30, "Ajax v PSV: something new")
eq(C.pick_text(odd), "No: something new", "an unrecognised title keeps the venue's words with the side")
ok("Under 3.5 · No" not in html and " · Yes" not in fixtures, "no rule · market · side triple on a row")

print("\nfixtures: one match, several picks; unknown and past kickoffs")
repeat = dict(over, id="repeat", start=(NOW + timedelta(hours=72)).isoformat())
other_league = dict(over, id="other-league", league="Other League")
btts.update(start=over["start"].replace("+00:00", "Z"))
center_data = {"quotes": [over, btts, repeat, other_league]}
center_rows = _rows(center_data, {"pairs": {}})
recs = C._fixture_rows(center_data, center_rows, NOW)
eq(len(recs), 3, "different markets on one match merge; other kickoffs and leagues stay distinct")
merged = next(r for r in recs if len(r["rules"]) == 2)
merged_html = C._fixture_row(merged, NOW)
eq(merged_html.count("City vs United"), 1, "the matchup is printed once")
eq(merged_html.count('class="soccer-pick"'), 2, "one pick line per pick under the same matchup")
ok(">Over 1.5<" in merged_html and ">BTTS yes<" in merged_html,
   "each pick line carries its own position")
ok(f'href="{S.market_url(over)}"' in merged_html and f'href="{S.market_url(btts)}"' in merged_html,
   "each pick links to its own market")

past = _quote(910, "o15_form_l10", "soccer_o15", "open", -30, "Past match")
today_pick = _quote(911, "o15_form_l10", "soccer_o15", "open", 1, "Today match")
later_pick = _quote(913, "o15_form_l10", "soccer_o15", "open", 72, "Later match")
unknown = dict(over, id="unknown", label="Unknown match", start="unreadable")
bucket_data = {"quotes": [past, today_pick, later_pick, unknown]}
bucket_html = C.fixtures(bucket_data, _rows(bucket_data, {"pairs": {}}), NOW)
past_row = re.search(r'<div class="soccer-row[^"]*"[^>]*>(?:(?!soccer-row[ "]).)*?Past match', bucket_html, re.S)
ok(past_row and "in play" in past_row.group(0) and 'class="soccer-row is-past"' in past_row.group(0),
   "an open pick past kickoff is marked 'in play' on its own row")
ok("Open picks past kickoff" not in bucket_html and 'id="in-play"' not in bucket_html,
   "there is no separate past-kickoff section")
unknown_row = re.search(r'<div class="soccer-row[^"]*"[^>]*>(?:(?!soccer-row[ "]).)*?Unknown match', bucket_html, re.S)
ok(unknown_row and "time TBC" in unknown_row.group(0),
   "an unreadable kickoff reads 'time TBC' in the time column")
days_b = re.findall(r'<h3 class="soccer-day-head">(.*?)</h3>', bucket_html)
ok("Date TBC" not in days_b and len(days_b) == 4 and "Tue Oct 6" in days_b[2]
   and bucket_html.find("Tue Oct 6") < bucket_html.find("Unknown match") < bucket_html.find("Thu Oct 8"),
   "a fixture with a date but no readable time sits under its day, not a separate bucket")
ok(bucket_html.find("Past match") < bucket_html.find("Today match") < bucket_html.find("Later match"),
   "past, today and later run in order on the one list")
empty_fix = C.fixtures({"quotes": []}, [], NOW)
ok("No open pick" in empty_fix and 'id="fixtures"' in empty_fix, "an empty list says so once")

print("\nrules table")
rules = _section(html, "rules")
ok('<table class="soccer-rules">' in rules, "rules are one table")
ok("<thead>" in rules and "<tbody>" in rules, "the table is labelled for the phone cards")
head = re.search(r"<thead>(.*?)</thead>", rules, re.S).group(1)
eq(re.findall(r"<th[^>]*>(.*?)</th>", head), ["Rule", "Market", "Scope", "Record", "ROI", "Status"],
   "the columns are Rule · Market · Scope · Record · ROI · Status")
rule_rows = _rule_rows(rules)
eq(len(rule_rows), len(rows), f"one row per soccer lane with a record ({len(rule_rows)} rows, {len(rows)} lanes)")
ok("<h3>" not in rules, "no per-market H3 groups")
ok('data-band=' not in rules and "Inactive rules" not in rules, "no active/inactive bands")
for row in rows:
    frag = next(r for r in rule_rows if _attr(r, "data-source") == row["name"]
                and _attr(r, "data-sport") == row["sport"])
    ok(_roi_html(row) in frag, f"{row['name']}|{row['sport']} ROI is the Sandbox row's own text")
    a = row["a"]
    rec = f'{a["won"]}–{a["n"] - a["won"]}' if a["n"] else "—"
    ok(f'>{rec}<' in frag, f"{row['name']}|{row['sport']} record is W–L")
    chev = re.search(r'<button type="button" class="rule-chev" aria-expanded="false" aria-controls="([^"]+)"', frag)
    ok(chev is not None, f"{row['name']}|{row['sport']} has a chevron")
    if chev:
        detail = re.search(rf'<tr class="rule-detail" id="{chev.group(1)}" hidden>(.*?)</tr>', rules, re.S)
        ok(detail is not None, f"{row['name']}|{row['sport']} chevron controls a detail row")
        if detail:
            note = (row["meta"].get("note") or "").strip()
            ok(_verdict_html(row) in detail.group(1), f"{row['name']}|{row['sport']} detail carries the Sandbox verdict")
            ok(B.esc(note[:60]) in detail.group(1), f"{row['name']}|{row['sport']} detail carries the registered description")
            ok('class="rule-picks"' in detail.group(1) or "No pick yet." in detail.group(1),
               f"{row['name']}|{row['sport']} detail lists recent picks")
stages = [_attr(r, "data-stage") for r in rule_rows]
ok(all(s in ("production", "sandbox", "retired") for s in stages), "status is Production, Sandbox or Retired")

prod_st = {"pairs": {"o15_ranked|soccer_o15": {"stage": "production"},
                     "team1_form_l5|soccer_team1_cup": {"stage": "production"}}}
prod_html = soccer_build.build(d, prod_st, NOW)
prod_rows = _rule_rows(_section(prod_html, "rules"))
prod_stages = [_attr(r, "data-stage") for r in prod_rows]
eq(prod_stages[:2], ["production", "production"], "Production rules are first")
ok(">Production<" in prod_rows[0] and '<span class="sig y">Production</span>' in prod_rows[0],
   "a Production row says so in the Status column")
by = {(_attr(r, "data-source"), _attr(r, "data-sport")): i for i, r in enumerate(prod_rows)}
prod_list = [r for r in _rows(d, prod_st) if r.get("prod")]
_hi, _lo = sorted(prod_list, key=lambda r: -r["a"]["roi_fee"])
ok(by[(_hi["name"], _hi["sport"])] < by[(_lo["name"], _lo["sport"])],
   "within Production, the higher ROI comes first")
rest = [r for r in _rows(d, prod_st) if not r.get("prod")]
def _roi_key(r):
    return (r["a"]["roi_fee"] is None or not r["a"]["n"], -(r["a"]["roi_fee"] or 0))
want = sorted(rest, key=_roi_key)
got_order = [(_attr(r, "data-source"), _attr(r, "data-sport")) for r in prod_rows[2:]]
ok([(r["name"], r["sport"]) for r in want[:3]] == got_order[:3],
   "after Production, rows run by ROI after fees, highest first")
ok(all(_attr(r, "data-stage") != "sandbox" or 'class="num" data-l="ROI"' in r for r in prod_rows[2:3]),
   "ROI cells are named for the phone layout")
strip = re.search(r'<div class="soccer-prod-strip">(.*?)</div>', prod_html, re.S)
chips = re.findall(r'<span class="soccer-prod-rule"><b>(.*?)</b><small>(.*?)</small>', strip.group(1) if strip else "")
eq(chips, [(B.esc(C._scoped_name(r)), B.esc(C._market_name(B._base_sport(r["sport"])))) for r in prod_list],
   "each strip chip is name · market, in row order")
ok(("Team scores 1+ form rule · Cups", "Team 1+") in chips, "a scoped twin carries its scope in the chip")
empty_strip = C.production_strip([])
ok("None in Production." in empty_strip, "an empty strip says so")

print("\nsystem fold")
health = _section(html, "health")
ok(health.startswith("\n<details>") or "<details>" in health.split("summary", 1)[0],
   "the system section is a closed fold by default")
ok("Prices are the Kalshi ask" in health and "settlement" in health,
   "the fold says where prices and results come from")
ok('class="section-disclosure"' in health and "Registered lanes" in health,
   "registered lanes are a nested fold inside System")

with patch("sport_tab.family_rows", return_value=[]):
    empty_html = soccer_build.build({"quotes": []}, {"pairs": {}}, NOW)
ok(all(f'id="{anchor}"' in empty_html for anchor in ("fixtures", "rules", "health")),
   "empty soccer pages preserve every navigation target")
ok("No soccer lane has a record yet." in empty_html and "None in Production." in empty_html,
   "empty pages still explain the missing record")

print("\nother pages keep their own layout")
ten = tennis_build.build(d, st, NOW)
cri = cricket_build.build(d, st, NOW)
ok(_absent("Alpha v Beta soonest", cri) and "o15_form_l10" not in cri,
   "cricket does not pick up soccer lanes")
ok('class="rule-card"' in cri, "a cricket lane the Sandbox still lists is a card on the cricket page")
ok("soccer-rules" not in cri and "soccer-rules" not in ten, "the rules table is the Soccer page's alone")
ok("rule-card" not in ten and "rule-grid" not in ten,
   "a ledger with no tennis lanes does not paint tennis cards")

css = open(os.path.join(ROOT, "public_site", "site.css"), encoding="utf-8").read()
js = open(os.path.join(ROOT, "public_site", "tables.js"), encoding="utf-8").read()
day_css = css.split(".soccer-day-head {", 1)[-1].split("}", 1)[0]
ok("position: sticky" in day_css and "top: var(--hdr-h)" in day_css,
   "site.css sticks the day header under the site header")
ok("function wireRuleRows" in js and 'button.rule-chev[aria-controls]' in js,
   "tables.js opens a rule's detail row without an inline handler")
ok("wireRuleRows: wireRuleRows" in js, "the row wiring is exported like the card flip")
for bar in (".soccer-fixture-state", ".soccer-local-nav", ".soccer-rule-chip", "soccer-fixture-list"):
    ok(bar not in css, f"site.css no longer styles {bar}")

published = open(os.path.join(ROOT, "public_site", "soccer.html"), encoding="utf-8").read()
ok('class="soccer-rules"' in published and 'id="fixtures"' in published,
   "public_site/soccer.html is the fixture-list page")
ok('class="rule-card"' not in published, "public_site/soccer.html has no cards")
pub_again = B.label_cells(published)
ok(pub_again == published, "the tracker's labelling pass leaves the built page unchanged")

print("\nbrowser layout")
from require_browser import require_browser
sync_playwright = require_browser("test_soccer_cards.py")
if sync_playwright is not None:
    import tempfile
    import shutil
    import threading
    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

    browser_st = {"pairs": {f'{r["name"]}|{r["sport"]}': {"stage": "production"}
                            for r in rows}}
    browser_html = soccer_build.build(d, browser_st, NOW)
    with tempfile.TemporaryDirectory(prefix="soccer-center-") as site:
        with open(os.path.join(site, "soccer.html"), "w", encoding="utf-8") as fh:
            fh.write(browser_html)
        for asset in ("site.css", "site.js", "tables.js", "sports.js"):
            shutil.copy2(os.path.join(ROOT, "public_site", asset), site)
        class Handler(SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=site, **kwargs)
            def log_message(self, *args):
                pass
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(channel="chrome", headless=True)
                for width in (1280, 390, 320):
                    page = browser.new_page(viewport={"width": width, "height": 844})
                    errors = []
                    page.on("pageerror", lambda e: errors.append(str(e)))
                    page.goto(f"http://127.0.0.1:{httpd.server_port}/soccer.html",
                              wait_until="networkidle")
                    ok(not errors, f"{width}px page runs without JavaScript errors")
                    ok(page.evaluate("document.documentElement.scrollWidth <= innerWidth"),
                       f"{width}px page has no sideways scroll")
                    ok(page.locator(".soccer-pick-side a").evaluate_all(
                        "links => links.every(a => !a.checkVisibility() || a.getBoundingClientRect().height >= 44)"),
                       f"{width}px pick links have comfortable tap targets")
                    anchors = page.locator("nav.toc a").evaluate_all(
                        "links => links.map(a => a.getAttribute('href'))")
                    eq(anchors, ["#fixtures", "#rules", "#health"], f"{width}px sub-nav is Fixtures / Rules / System")
                    ok(all(page.locator(a).count() == 1 for a in anchors),
                       f"{width}px sub-nav reaches unique sections")
                    eq(page.locator(".soccer-day-head").first.evaluate("e => getComputedStyle(e).position"),
                       "sticky", f"{width}px day header is sticky")
                    eq(page.locator("tr.rule-detail:visible").count(), 0, f"{width}px rule details start closed")
                    page.locator("button.rule-chev").first.click()
                    eq(page.locator("tr.rule-detail:visible").count(), 1, f"{width}px a chevron opens one detail row")
                    eq(page.locator("button.rule-chev").first.get_attribute("aria-expanded"), "true",
                       f"{width}px the chevron reports expanded")
                    ok(page.evaluate("document.documentElement.scrollWidth <= innerWidth"),
                       f"{width}px no sideways scroll with a detail row open")
                    page.locator("button.rule-chev").first.click()
                    eq(page.locator("tr.rule-detail:visible").count(), 0, f"{width}px the chevron closes it again")
                    cards = page.locator(".soccer-rules thead").first.evaluate("e => getComputedStyle(e).display")
                    eq(cards, "none" if width < 760 else "table-header-group",
                       f"{width}px the rules table uses the phone cards under 760px")
                    ok(page.locator("#health > details").get_attribute("open") is None,
                       f"{width}px System starts folded")
                    page.close()
                browser.close()
        finally:
            httpd.shutdown()
            httpd.server_close()

if FAILS:
    print(f"\nSHA {SHA} FAILED {len(FAILS)}")
    sys.exit(1)
print(f"\nSHA {SHA} PASSED")
