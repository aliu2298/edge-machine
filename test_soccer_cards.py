#!/usr/bin/env python3
"""The Soccer page on the shared sport template: what soccer_cards hands it.

Presentation only. The record and the ROI are the Sandbox row's own figures,
compared as strings. Nothing here grades a bet or writes a ledger. A game
label is printed through S.position_label: "A v B" in the ledger reads
"A vs B" on the page. The pick on an event row is the position a reader
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
import sport_page as SP

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
    quotes += _settled("btts_form_l10_fade", "soccer_btts", n=5, won=2, price=0.48)
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
        300, "btts_form_l10_fade", "soccer_btts", "open", 40, "Nu v Xi btts"))
    # Open, past 48 hours: in the Later fold like any other open pick.
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


def _section(markup, name):
    """A top-level page section: from its opening tag to the next top-level section or the footer."""
    match = re.search(rf'<section id="{name}"[^>]*>(.*?)(?=<section id="|<footer)', markup, re.S)
    return match.group(1) if match else ""


def _rule_rows(html):
    return re.findall(r'<tr class="rule-row(?: is-early)?"(.*?)</tr>', html, re.S)


def _attr(frag, name):
    m = re.search(rf'\b{name}="([^"]*)"', frag)
    return m.group(1) if m else None


def _shown(label):
    """How a ledger label is printed on the page: 'A v B' becomes 'A vs B'."""
    return fmt.contest(label)


def _absent(label, html):
    """Neither the stored spelling nor the printed one is on the page."""
    return label not in html and _shown(label) not in html


def _event(markup, label):
    m = re.search(r'<div class="sp-event[^"]*"[^>]*>(?:(?!sp-event").)*?' + re.escape(label) + r'.*?</div></div>', markup, re.S)
    return m.group(0) if m else ""


print(f"SHA {SHA}")

import soccer_build
import soccer_cards as C
import tennis_build
import cricket_build
from unittest.mock import patch

# The Kalshi pre-flight file on disk is whatever the last job left. The page
# under test gets a fresh one, so the Method fold starts closed.
_fresh = patch("sport_tab.preflight_report",
               return_value=({}, '<div class="note sm">Kalshi checked 1.0h ago.</div>'))
_fresh.start()

print("\nsoccer page shape")
d, st = _fixture()
html = soccer_build.build(d, st, NOW)
rows = _rows(d, st)
ok(rows, "the fixture has soccer lanes")
ok('id="events"' in html and 'id="rules"' in html and 'id="method"' in html,
   "the page has Rules, Events and Method sections")
ok('href="#events"' in html and 'href="#rules"' in html and 'href="#method"' in html,
   "the sub-nav jumps to Rules, Events and Method")
ok(html.find('id="rules"') < html.find('id="events"') < html.find('id="method"'),
   "rules come first, then events, then the folded method")
ok("<h1>Soccer</h1>" in html and "Match picks and the rules that fire them · All times Central" in html,
   "the head is the title and one scope line")
for gone in ('class="rule-card"', 'class="rule-grid"', "soccer-fixture-state", "soccer-prod-strip",
             "soccer-rules", "soccer-day-head", "Fixtures</h2>", "<h3>Goals</h3>", "By competition",
             "How each rule is defined"):
    ok(gone not in html, f"the page no longer prints {gone!r}")
ok("<script" not in html.split("<main", 1)[-1].split("</main>", 1)[0].lower()
   or 'src="./' in html, "the page body does not grow an inline script")
ok("javascript:" not in html, "a javascript: game url is not written")
ok("&lt;script&gt;" in html, "a game label is escaped")

print("\nevents: one row per fixture, in the template's tabs")
events = C.events(d, rows, NOW)
nxt, later, live, done = SP.bucket(events, NOW)
ok("Alpha vs Beta soonest" in [e["label"] for e in nxt] and "Lambda vs Mu ranked" in [e["label"] for e in nxt],
   "open picks inside 24 hours are Next 24h events")
eq([e["label"] for e in later][:3], ["Iota vs Kappa fifth and later", "Window vs Keeper".replace("Window vs Keeper", "Window Side vs Keeper"), "Nu vs Xi btts"],
   "picks past 24 hours run in kickoff order in the Later fold")
ok("Window Side vs Keeper" in [e["label"] for e in later] and "Soon Side vs Tonight" in [e["label"] for e in nxt],
   "a fixture a rule has been shown, with no stake yet, is listed")
ok(all(p["state"] == "watch" for e in nxt + later if e["label"] == "Window Side vs Keeper" for p in e["picks"]),
   "an unstaked fixture is a watching pick")
ok("Far Side vs Later" not in [e["label"] for e in events], "an unstaked fixture past 48 hours is not listed")
eq(len([e for e in nxt + later]), len([e for e in events if any(p["state"] in ("open", "watch") for p in e["picks"])]),
   "one event per fixture with something pending")
page_events = _section(html, "events")
ok("Alpha vs Beta soonest" in page_events and "Nu vs Xi btts" in page_events
   and "Omicron vs Pi later" in page_events, "every open pick is on the page, the far ones in the Later fold")
ok("Alpha v Beta soonest" not in html and "Nu v Xi btts" not in html,
   "the page does not print the ledger's 'A v B' spelling")
order = ["Alpha vs Beta soonest", "Lambda vs Mu ranked", "Iota vs Kappa fifth and later",
         "Nu vs Xi btts", "Omicron vs Pi later"]
pos = [page_events.find(m) for m in order]
ok(all(p >= 0 for p in pos) and pos == sorted(pos), "events run in kickoff order, Next 24h then Later")
ok('class="sp-pick is-watch"' in page_events and ">watching<" in page_events,
   "an unstaked fixture reads 'watching' in the pick column")
ok(_absent("Far Side v Later", html), "an unstaked fixture past 48 hours is not on the page")
alpha = _event(page_events, "Alpha vs Beta soonest")
ok('<span class="sp-pick-rule">Over 1.5 form rule · Clubs</span>' in alpha, "the rule name is printed, muted, after the price")
ok('<span class="sp-price">55¢</span>' in alpha, "the price is the stored ask in cents")
ok(page_events.count("<article") == 0, "no boxes per fixture")
ok('class="sp-day-head"' in page_events, "day heads carry the sticky class")

print("\nevents: the pick in words")
over = _quote(900, "o15_form_l10", "soccer_o15", "open", 30, "City v United: over 1.5 goals")
over.update(pick="a", url="https://kalshi.com/markets/over")
eq(C.pick_text(over), "Over 1.5", "a Yes on an over market is 'Over 1.5'")
eq(C.pick_text(dict(over, pick="b")), "Under 1.5", "a No on an over market is 'Under 1.5'")
under35 = _quote(901, "u35_low_scoring", "soccer_u35", "open", 30, "Genoa v Fiorentina: over 3.5 goals")
eq(C.pick_text(under35), "Under 3.5", "the under-3.5 rule's No reads 'Under 3.5'")
btts = _quote(902, "btts_form_l10_fade", "soccer_btts", "open", 30, "City v United: both teams to score")
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
ok("Under 3.5 · No" not in html and " · Yes" not in page_events, "no rule · market · side triple on a row")

print("\nevents: one match, several picks; unknown and past kickoffs")
repeat = dict(over, id="repeat", start=(NOW + timedelta(hours=72)).isoformat())
other_league = dict(over, id="other-league", league="Other League")
btts.update(start=over["start"].replace("+00:00", "Z"))
center_data = {"quotes": [over, btts, repeat, other_league]}
center_rows = _rows(center_data, {"pairs": {}})
recs = C.events(center_data, center_rows, NOW)
eq(len(recs), 3, "different markets on one match merge; other kickoffs and leagues stay distinct")
merged = next(r for r in recs if len(r["picks"]) == 2)
eq(merged["label"], "City vs United", "the matchup is printed once, spelt vs")
eq(sorted(p["text"] for p in merged["picks"]), ["BTTS yes", "Over 1.5"], "each pick line carries its own position")
eq(sorted(p["href"] for p in merged["picks"]), sorted([S.market_url(over), S.market_url(btts)]), "each pick links to its own market")
ok(next(r for r in recs if r["label"] == "City vs United" and r is not merged)["sub"] == "Other League",
   "the competition is the row's sub-line")

past = _quote(910, "o15_form_l10", "soccer_o15", "open", -30, "Past match")
today_pick = _quote(911, "o15_form_l10", "soccer_o15", "open", 1, "Today match")
later_pick = _quote(913, "o15_form_l10", "soccer_o15", "open", 72, "Later match")
unknown = dict(over, id="unknown", label="Unknown match", start="unreadable")
bucket_data = {"quotes": [past, today_pick, later_pick, unknown]}
bucket_rows = _rows(bucket_data, {"pairs": {}})
nxt, later, live, done = SP.bucket(C.events(bucket_data, bucket_rows, NOW), NOW)
eq([e["label"] for e in live], ["Past match"], "an open pick past kickoff is In progress")
eq(SP.pick_state(live[0]["picks"][0], NOW), ("unsettled · 30h", "is-late"), "and 30 hours on it says so")
eq([e["label"] for e in nxt], ["Today match", "Unknown match"], "an unreadable kickoff sits in Next 24h as time TBC, after the timed ones")
eq([e["label"] for e in later], ["Later match"], "a pick days out is in the Later fold")
bucket_html = soccer_build.build(bucket_data, {"pairs": {}}, NOW)
unknown_row = _event(_section(bucket_html, "events"), "Unknown match")
ok('<span class="sp-tbc">time TBC</span>' in unknown_row, "an unreadable kickoff reads 'time TBC' in the time column")
ok("Date TBC" not in bucket_html and "Tue Oct 6" in bucket_html, "a fixture with a date but no readable time sits under its day")
empty_html = soccer_build.build({"quotes": []}, {"pairs": {}}, NOW)
ok('data-empty="next"' in empty_html and 'data-empty="done"' in empty_html, "an empty page says why each tab is empty")

print("\nrules: a row per rule, the words folded")
from sport_rows_testlib import rule_rows, text as row_text
rules = _section(html, "rules")
ok('class="sp-rules-list" data-list="sandbox"' in rules, "the Sandbox rules are one list")
head_line = re.search(r'<div class="sp-line sp-head-line[^"]*" aria-hidden="true">(.*?)</div>', rules.split('id="sandbox"', 1)[-1], re.S)
eq(re.findall(r'<span class="sp-cell[^"]*">([^<]*)</span>', head_line.group(1)) if head_line else None,
   ["Rule", "Market", "Scope", "Record", "ROI after fees", "Won v priced", "Evidence", "Verdict"],
   "the columns are Rule · Market · Scope · Record · ROI after fees · Won v priced · Evidence · Verdict")
srows = rule_rows(rules)
eq(len(srows), len(rows), f"with nothing in Production, one row per soccer lane ({len(srows)} rows, {len(rows)} lanes)")
ok("<h3>Goals</h3>" not in rules, "no per-market H3 groups")
for row in rows:
    r = next(x for x in srows if x["source"] == row["name"] and x["sport"] == row["sport"])
    ok(r["cells"]["ROI after fees"] == SP.roi_html(row), f"{row['name']}|{row['sport']} ROI is the Sandbox row's own text")
    a = row["a"]
    rec = f'{a["won"]}–{a["n"] - a["won"]}' if a["n"] else "—"
    ok(row_text(r["cells"]["Record"]).startswith(rec), f"{row['name']}|{row['sport']} record is W–L")
    ok(not r["open"], f"{row['name']}|{row['sport']} Rule details starts closed")
    note = " ".join((row["meta"].get("note") or "").split())
    ok(not note or B.esc(note) in r["body"], f"{row['name']}|{row['sport']} the fold carries the registered description, verbatim")
    ok('class="rule-picks"' in r["body"] or "No pick yet." in r["body"], f"{row['name']}|{row['sport']} the fold lists recent picks")
ok(all(r["stage"] == "sandbox" for r in srows), "every row is a Sandbox row")
by_n = [next(x for x in rows if x["name"] == r["source"] and x["sport"] == r["sport"])["a"]["n"] for r in srows]
early = [r["early"] for r in srows]
ok(early == sorted(early), "the too-early rows (under 10 settled) are sunk under the read ones")
ok(all(by_n[i] >= by_n[i + 1] for i in range(len(by_n) - 1) if early[i] == early[i + 1]),
   "within each band, more evidence comes first")

prod_st = {"pairs": {"o15_ranked|soccer_o15": {"stage": "production", "by_hand": "2026-09-20", "promoted_at": "2026-09-20T00:00:00+00:00"},
                     "team1_form_l5|soccer_team1_cup": {"stage": "production", "by_hand": "2026-09-20", "promoted_at": "2026-09-20T00:00:00+00:00"}}}
prod_html = soccer_build.build(d, prod_st, NOW)
prod_rules = _section(prod_html, "rules")
prod_list = prod_rules.split('class="sp-rules-list sp-prod"', 1)[1].split('id="sandbox"', 1)[0]
prows = rule_rows(prod_list)
eq(len(prows), 2, "a Production rule is a row in the Production list")
eq(len(rule_rows(prod_rules.split('id="sandbox"', 1)[1])), len(rows) - 2, "and leaves the Sandbox list")
ok(all(r["stage"] == "production" for r in prows), "its rows carry the Production stage for the chips")
ok("Team scores 1+ form rule · Cups" in [r["full_name"] for r in prows], "a scoped twin carries its scope in its full name")
ok("Team 1+" in [r["cells"]["Market"] for r in prows], "a row names the market the rule trades")
empty_rules = _section(empty_html, "rules")
ok("No soccer rule is in Production." in empty_rules and 'data-list="sandbox"' in empty_rules,
   "an empty ledger still lists the wired cup and international twins as Sandbox rows, and says nothing is in Production")
with patch("sport_tab.family_rows", return_value=[]):
    no_rows = _section(soccer_build.build({"quotes": []}, {"pairs": {}}, NOW), "rules")
ok("No soccer rule is in Production." in no_rows and "No soccer rule is in the Sandbox." in no_rows,
   "with no rows at all both halves say so")

print("\nmethod fold")
health = _section(html, "method")
ok("<details><summary><b>Method</b>" in health, "the method section is a closed fold by default")
ok("Prices are the Kalshi ask" in health and "settlement" in health,
   "the fold says where prices and results come from")
ok('class="section-disclosure"' in health and "Registered lanes" in health,
   "registered lanes are a nested fold inside Method")

with patch("sport_tab.family_rows", return_value=[]):
    empty_html = soccer_build.build({"quotes": []}, {"pairs": {}}, NOW)
ok(all(f'id="{anchor}"' in empty_html for anchor in ("events", "rules", "method")),
   "empty soccer pages preserve every navigation target")

print("\nother pages keep their own rows")
ten = tennis_build.build(d, st, NOW)
cri = cricket_build.build(d, st, NOW)
ok(_absent("Alpha v Beta soonest", cri) and "o15_form_l10" not in cri,
   "cricket does not pick up soccer lanes")
ok('data-list="sandbox"' in cri or "No cricket rule is in the Sandbox." in cri,
   "the cricket page is on the same template")
ok(_absent("Alpha v Beta soonest", ten) and "o15_form_l10" not in ten, "tennis does not pick up soccer lanes")

css = open(os.path.join(ROOT, "public_site", "site.css"), encoding="utf-8").read()
js = open(os.path.join(ROOT, "public_site", "tables.js"), encoding="utf-8").read()
day_css = css.split(".sp-day-head {", 1)[-1].split("}", 1)[0]
ok("position: sticky" in day_css and "top: var(--hdr-h)" in day_css,
   "site.css sticks the day head under the site header")
ok("function wireRuleRows" in js and 'button.rule-chev[aria-controls]' in js,
   "tables.js opens a rule's detail row without an inline handler")
for bar in (".soccer-fixture-state", ".soccer-local-nav", ".soccer-rule-chip", "soccer-fixture-list", ".soccer-rules", ".soccer-prod-strip"):
    ok(bar not in css, f"site.css no longer styles {bar}")

published = open(os.path.join(ROOT, "public_site", "soccer.html"), encoding="utf-8").read()
ok('class="sp-head"' in published and 'id="events"' in published and 'class="sp-tabs"' in published,
   "public_site/soccer.html is the template page")
ok('class="rule-card"' not in published and 'class="soccer-prod-strip"' not in published, "public_site/soccer.html has no cards or chip strip")
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

    browser_st = {"pairs": {f'{r["name"]}|{r["sport"]}': {"stage": "production", "by_hand": "2026-09-20",
                                                         "promoted_at": "2026-09-20T00:00:00+00:00"}
                            for r in rows[:2]}}
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
                    ok(page.locator(".sp-pos a").evaluate_all(
                        "links => links.every(a => !a.checkVisibility() || a.getBoundingClientRect().height >= 44)"),
                       f"{width}px pick links have comfortable tap targets")
                    anchors = page.locator("nav.toc a").evaluate_all(
                        "links => links.map(a => a.getAttribute('href'))")
                    eq(anchors, ["#rules", "#events", "#method"], f"{width}px sub-nav is Rules / Events / Method")
                    ok(all(page.locator(a).count() == 1 for a in anchors),
                       f"{width}px sub-nav reaches unique sections")
                    eq(page.locator(".sp-day-head").first.evaluate("e => getComputedStyle(e).position"),
                       "sticky", f"{width}px day head is sticky")
                    page.locator("details.sp-sandbox > summary").click()
                    eq(page.locator(".sp-details-body:visible").count(), 0, f"{width}px every Rule details fold starts closed")
                    page.locator('[data-list="sandbox"] details.sp-rule > summary').first.click()
                    eq(page.locator(".sp-details-body:visible").count(), 1, f"{width}px a row opens its one Rule details fold")
                    ok(page.evaluate("document.documentElement.scrollWidth <= innerWidth"),
                       f"{width}px no sideways scroll with a fold open")
                    page.locator('[data-list="sandbox"] details.sp-rule > summary').first.click()
                    eq(page.locator(".sp-details-body:visible").count(), 0, f"{width}px and closes it again")
                    ok(page.locator("#method > details").get_attribute("open") is None,
                       f"{width}px Method starts folded")
                    page.close()
                browser.close()
        finally:
            httpd.shutdown()
            httpd.server_close()

if FAILS:
    print(f"\nSHA {SHA} FAILED {len(FAILS)}")
    sys.exit(1)
print(f"\nSHA {SHA} PASSED")
