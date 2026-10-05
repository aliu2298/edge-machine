#!/usr/bin/env python3
"""SofaScore shell slice 1: chrome and empty panes, Production land.

Fails before the shell exists: the site root still refreshes to the Sandbox,
the page nav is the old sport list, and there is no empty Running pane.
Passes once the root is the dark shell, Production is the current page pill,
the summary strip is the Production board's own headline tiles, and the
Running and Rules-applied panes are empty. No network.
"""
import os
import re
import sys
import threading
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import fmt
import production
import sandbox_track as T

FAILS = []
ROOT = os.path.dirname(os.path.abspath(__file__))
NOW = datetime(2026, 10, 5, 18, 0, tzinfo=timezone.utc)
PAGE_HREFS = (
    'href="./sandbox.html"',
    'href="./production.html"',
    'href="./trading.html"',
    'href="./sandbox.html#method"',
)
SKETCH_FAKES = (
    "Milan",
    "Atalanta",
    "Rybakina",
    "+$1,840",
    "o15_ranked",
    "Paper P&L",
    "PAPER P&L",
)


def ok(cond, why):
    print(f"  {'ok  ' if cond else 'FAIL'} {why}")
    if not cond:
        FAILS.append(why)


def eq(got, want, why):
    ok(got == want, why if got == want else f"{why} — got {got!r}, want {want!r}")


def _tiles(html):
    """The headline strip. Child tiles are one div deep, so count them."""
    start = html.find('<div class="tiles">')
    if start < 0:
        return ""
    depth = 0
    i = start
    while i < len(html):
        if html.startswith("<div", i):
            depth += 1
            i = html.find(">", i) + 1
            continue
        if html.startswith("</div>", i):
            depth -= 1
            i += len("</div>")
            if depth == 0:
                return html[start:i]
            continue
        i += 1
    return ""


def _tile_map(fragment):
    found = re.findall(
        r'<div class="tile"><b(?: class="when")?>(.*?)</b><span>(.*?)</span></div>',
        fragment)
    return {label: value for value, label in found}


def _nav(html):
    match = re.search(r'<nav class="main"[^>]*>.*?</nav>', html, re.S)
    return match.group(0) if match else ""


def _sports(html):
    match = re.search(r'<nav class="sports"[^>]*>.*?</nav>', html, re.S)
    return match.group(0) if match else ""


def _fixture():
    """One Production pair and four leads. Counts are the board's, not the sketch."""
    st = {"pairs": {
        "oddspedia|cricket": {
            "stage": "production",
            "ready_at": "2026-09-27T00:00:00+00:00",
            "since": "2026-09-01T00:00:00+00:00",
            "by_hand": "2026-09-27",
        },
    }}
    blob = {"leads": {
        "soon": {
            "id": "soon", "pair": "oddspedia|cricket", "status": "pending",
            "kickoff": "2026-10-06T15:00:00Z", "match": "Alpha v Beta",
            "headline": "Alpha to win", "price_at_log": 0.61,
        },
        "later": {
            "id": "later", "pair": "oddspedia|cricket", "status": "pending",
            "kickoff": "2026-10-07T15:00:00Z", "match": "Gamma v Delta",
            "headline": "Gamma to win", "price_at_log": 0.55,
        },
        "hit": {
            "id": "hit", "pair": "oddspedia|cricket", "status": "hit",
            "kickoff": "2026-10-04T15:00:00Z", "match": "Echo v Foxtrot",
            "headline": "Echo to win",
        },
        "miss": {
            "id": "miss", "pair": "oddspedia|cricket", "status": "miss",
            "kickoff": "2026-10-03T15:00:00Z", "match": "Golf v Hotel",
            "headline": "Golf to win",
        },
    }, "pairs": {}, "unlisted_skipped": 0, "unverified_kickoff_skipped": 0}
    return {"quotes": []}, st, blob


def _check_chrome(html, why):
    print(f"\n{why}")
    ok('href="./site.css"' in html, f"{why} links site.css")
    ok("<style" not in html.lower(), f"{why} has no inline style")
    ok(not re.search(r"\sstyle\s*=", html), f"{why} has no style attribute")
    ok("fonts.googleapis.com" not in html, f"{why} does not load a web font")
    ok('href="#content"' in html and "Skip to content" in html, f"{why} can skip to content")
    ok('http-equiv="refresh"' not in html, f"{why} does not refresh away")
    ok('src="./root.js"' not in html, f"{why} does not load the Sandbox redirect")
    ok("Continue to the Sandbox" not in html, f"{why} is not the old Sandbox stub")
    ok("theme-toggle" not in html and "data-theme" not in html,
       f"{why} has no theme toggle")
    ok("download" not in html.lower() and ".csv" not in html.lower(),
       f"{why} has no download or CSV affordance")
    for needle in SKETCH_FAKES:
        ok(needle not in html, f"{why} does not ship the sketch placeholder {needle!r}")
    ok("$" not in html, f"{why} does not invent a dollar P&L")
    nav = _nav(html)
    ok(nav, f"{why} has the page nav")
    labels = re.findall(r">([^<]+)</a>", nav)
    eq(labels, ["Sandbox", "Production", "Trading", "Method"], f"{why} page pills")
    eq(nav.count('aria-current="page"'), 1, f"{why} marks one current page")
    ok('href="./production.html" aria-current="page"' in nav,
       f"{why} lands on Production")
    for href in PAGE_HREFS:
        ok(href in nav, f"{why} page pill {href}")
    ok('href="./nba.html"' not in nav and 'href="./crypto.html"' not in nav,
       f"{why} page nav does not link the sport pages")
    sports = _sports(html)
    ok(sports, f"{why} has sport pills")
    sport_labels = re.findall(r">([^<]+)</button>", sports)
    eq(sport_labels, ["All", "NBA", "Soccer", "Tennis", "Cricket", "Crypto"],
       f"{why} sport pills")
    ok("<a " not in sports, f"{why} sport pills do not navigate")
    ok('data-sport="crypto"' in sports and "trading.html" not in sports,
       f"{why} Crypto is a Running filter, not the Trading page")
    ok('aria-pressed="true"' in sports and ">All</button>" in sports,
       f"{why} All starts pressed")
    ok(">Live</button>" in html and ">Settled</button>" in html
       and ">Upcoming</button>" in html,
       f"{why} has Live / Settled / Upcoming chrome")
    ok("No open or recent paper bets yet." in html,
       f"{why} bet roll is an empty state, not fake chips")
    ok('class="bet-chip"' not in html and 'class="event-chip"' not in html,
       f"{why} bet roll has no result chips")
    ok("No live, settled, or upcoming paper bets." in html,
       f"{why} Running pane is empty")
    ok("Select a contest in Running." in html, f"{why} Rules-applied pane is empty")
    ok('class="running-row"' not in html and "data-contest" not in html,
       f"{why} has no Running contest rows")
    ok('class="rule-mini"' not in html, f"{why} has no Rules-applied mini cards")
    ok(re.search(r">\s*History\s*<", html, re.I) is None,
       f"{why} has no History tab")
    ok('role="tab"' not in html, f"{why} has no tab stub")
    ok('href="./production.html"' in html and "Full page" in html,
       f"{why} links Full page to the existing Production board")
    ok('data-board="production"' in html, f"{why} summary strip is the Production board")
    css = open(os.path.join(ROOT, "public_site", "site.css"), encoding="utf-8").read()
    ok("color-scheme: dark" in css, "site.css is dark")
    ok("prefers-color-scheme: light" not in css, "site.css has no light theme")
    ok(".shell-columns" in css and "grid-template-columns: minmax(0, 1fr)" in css,
       "narrow viewports stack the two panes")


print("shell module")
try:
    import shell_build
except ImportError as exc:
    shell_build = None
    ok(False, f"shell_build imports ({exc})")

if shell_build is not None:
    d, st, blob = _fixture()
    html = shell_build.page(NOW, d=d, st=st, blob=blob)
    _check_chrome(html, "fixture shell")
    prod = production.page(d, st, blob, "", now=NOW)
    shell_tiles = _tiles(html)
    prod_tiles = _tiles(prod)
    eq(shell_tiles, prod_tiles, "summary strip is the Production page's own tiles")
    want_next = fmt.when("2026-10-06T15:00:00Z")
    eq(_tile_map(shell_tiles), {
        "pairs in Production": "1",
        "leads still to come": "2",
        "recent leads landed": "1/2",
        "next lead (CT)": want_next,
    }, "fixture totals are the Production headlines")
    empty = shell_build.page(
        NOW, d={"quotes": []}, st={"pairs": {}}, blob={"leads": {}, "pairs": {}})
    eq(_tile_map(_tiles(empty)), {
        "pairs in Production": "0",
        "leads still to come": "0",
        "recent leads landed": "0/0",
        "next lead (CT)": production.PLACEHOLDER_DATE,
    }, "an empty board prints the Production zeros, not the sketch")
    live = shell_build.page(NOW)
    live_prod = production.page(T.load(), T.load_stages(), production.load_feed(), "", now=NOW)
    eq(_tiles(live), _tiles(live_prod),
       "the live shell strip matches the live Production headlines")
    _check_chrome(live, "live shell")

    print("\npublished root")
    root_html = open(os.path.join(ROOT, "public_site", "index.html"), encoding="utf-8").read()
    ok('href="./production.html" aria-current="page"' in root_html,
       "public_site/index.html lands on Production")
    ok('http-equiv="refresh"' not in root_html,
       "public_site/index.html does not refresh to the Sandbox")
    ok("Select a contest in Running." in root_html,
       "public_site/index.html has the empty Rules-applied pane")
    ok(re.search(r">\s*History\s*<", root_html, re.I) is None,
       "public_site/index.html has no History tab")
    for rel in ("sandbox.html", "production.html", "trading.html"):
        ok(os.path.isfile(os.path.join(ROOT, "public_site", rel)),
           f"{rel} still exists for the page pill")
    sandbox = open(os.path.join(ROOT, "public_site", "sandbox.html"), encoding="utf-8").read()
    ok('id="method"' in sandbox, "Method still points at the Sandbox method section")

    js = open(os.path.join(ROOT, "public_site", "shell.js"), encoding="utf-8").read()
    ok("fetch(" not in js and "location." not in js and "XMLHttpRequest" not in js,
       "shell.js does not load bets or navigate")
    ok("aria-pressed" in js, "shell.js only records which filter is pressed")


def _browser():
    from require_browser import require_browser
    sync_playwright = require_browser("test_sofascore_shell.py")
    if sync_playwright is None:
        return
    site = os.path.join(ROOT, "public_site")

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=site, **kwargs)

        def log_message(self, fmt, *args):
            return

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}/index.html"
    print("\nbrowser")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 800})
            page.goto(base, wait_until="load")
            wide = page.evaluate("""() => {
              const cols = document.querySelector(".shell-columns");
              const panes = [...cols.children];
              const a = panes[0].getBoundingClientRect();
              const b = panes[1].getBoundingClientRect();
              const bg = getComputedStyle(document.body).backgroundColor;
              return {
                side: b.left >= a.right - 2,
                overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
                bg: bg,
                history: [...document.querySelectorAll("button, [role=tab], a")]
                  .some((el) => el.textContent.trim() === "History"),
                empty: document.body.textContent.includes("Select a contest in Running."),
                current: (document.querySelector('nav.main [aria-current="page"]') || {}).textContent || "",
              };
            }""")
            ok(wide["side"] and not wide["overflow"],
               f"desktop panes sit side by side without sideways scroll ({wide})")
            ok(wide["current"].strip() == "Production",
               f"desktop land highlights Production ({wide['current']!r})")
            ok(wide["empty"] and not wide["history"],
               "desktop shows the empty detail pane and no History tab")
            ok(wide["bg"] in ("rgb(11, 12, 15)", "rgb(11, 13, 16)"),
               f"desktop background stays dark ({wide['bg']})")
            page.click('nav.sports button[data-sport="crypto"]')
            crypto = page.evaluate("""() => ({
              pressed: document.querySelector('[data-sport="crypto"]').getAttribute("aria-pressed"),
              all: document.querySelector('[data-sport="all"]').getAttribute("aria-pressed"),
              url: location.pathname,
              rows: document.querySelectorAll(".running-row").length,
              empty: document.body.textContent.includes("No live, settled, or upcoming paper bets."),
            })""")
            ok(crypto["pressed"] == "true" and crypto["all"] == "false"
               and crypto["url"].endswith("index.html") and crypto["rows"] == 0
               and crypto["empty"],
               f"Crypto only changes the filter state ({crypto})")
            page.set_viewport_size({"width": 390, "height": 844})
            page.wait_for_timeout(40)
            narrow = page.evaluate("""() => {
              const cols = document.querySelector(".shell-columns");
              const panes = [...cols.children];
              const a = panes[0].getBoundingClientRect();
              const b = panes[1].getBoundingClientRect();
              return {
                stacked: b.top >= a.bottom - 2 && a.width > 200,
                overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
              };
            }""")
            ok(narrow["stacked"] and not narrow["overflow"],
               f"phone stacks the panes and does not scroll sideways ({narrow})")
            browser.close()
    finally:
        httpd.shutdown()


if shell_build is not None:
    _browser()

print()
if FAILS:
    print(f"{len(FAILS)} FAILED")
    sys.exit(1)
print("all passed")
