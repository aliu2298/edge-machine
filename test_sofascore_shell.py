#!/usr/bin/env python3
"""SofaScore shell slice 1: chrome and empty panes, Production land.

Fails before the shell exists: the site root still refreshes to the Sandbox,
the page nav is the old sport list, and there is no empty Running pane.
Passes once the root is the dark shell, Production is the current page pill,
the summary strip is the Production board's own headline tiles, and the
Running and Rules-applied panes are empty. No network.
"""
import html as html_lib
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
    'href="./nba.html"',
    'href="./soccer.html"',
    'href="./tennis.html"',
    'href="./cricket.html"',
    'href="./crypto.html"',
    'href="./commodities.html"',
    'href="./sandbox.html#method"',
)
PAGE_LABELS = ["Sandbox", "Production", "Trading", "NBA", "Soccer", "Tennis", "Cricket", "Crypto",
               "Commodities", "Method"]
LANDED = re.compile(
    r'<div class="tile"><b>[^<]*</b><span>(?:recent leads landed|paper bets landed[^<]*)</span></div>')
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
    match = re.search(r'<nav class="sports sport-filter"[^>]*>.*?</nav>', html, re.S)
    return match.group(0) if match else ""


def _present_sports(html):
    """Sport labels with at least one Running row, in pill order."""
    rows = re.findall(r'<button\b[^>]*class="running-row"[^>]*>', html)
    present = set()
    for row in rows:
        match = re.search(r'data-sport="([^"]*)"', row)
        if match:
            present.add(html_lib.unescape(match.group(1)))
    return [label for key, label in shell_build.SPORTS if key != "all" and label in present]


def _without_landed(tiles):
    """The strip minus the landed tile, which the shell counts its own way."""
    return LANDED.sub("", tiles)


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


def _check_chrome(html, why, placeholders=True):
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
    banned = SKETCH_FAKES if placeholders else (
        "+$1,840", "o15_ranked", "Paper P&L", "PAPER P&L")
    for needle in banned:
        ok(needle not in html, f"{why} does not ship the sketch placeholder {needle!r}")
    # A dollar P&L is a SIGNED amount ("+$1,840"). A Kalshi ladder rung names its strike
    # in dollars ("$80,250 or above at the close", the crypto lane's lead since
    # 2026-10-08), which is the bet, not a profit; a bare "$" no longer proves anything.
    ok(not re.search(r"[+\-\u2212]\$\d", html) and "P&L" not in html and "P&amp;L" not in html,
       f"{why} does not invent a dollar P&L")
    nav = _nav(html)
    ok(nav, f"{why} has the page nav")
    eq(html.count('<nav class="main"'), 1, f"{why} has one page nav, in the header")
    ok('<header class="site"><div class="topbar">' in html.replace("\n", "")
       and nav in html.split("</header>", 1)[0],
       f"{why} page nav sits in the site header")
    labels = re.findall(r">([^<]+)</a>", nav)
    eq(labels, PAGE_LABELS, f"{why} page pills")
    eq(nav.count('aria-current="page"'), 0, f"{why} marks no page pill current on the root")
    ok('<a class="brand" href="./index.html" aria-current="page">Edge Machine</a>' in html,
       f"{why} brand is the current page")
    for href in PAGE_HREFS:
        ok(href in nav, f"{why} page pill {href}")
    ok('aside class="desk-nav"' not in html and 'desk-nav-block' not in html
       and 'top-production' not in html,
       f"{why} has no sidebar nav")
    sports = _sports(html)
    ok(sports, f"{why} has sport pills")
    running = html.split('id="running"', 1)[-1].split("</section>", 1)[0]
    ok(sports in running
       and running.find('class="running-filters"') < running.find(sports) < running.find('id="settled-caption"'),
       f"{why} sport pills sit inside the Running pane, after the filters")
    sport_labels = re.findall(r">([^<]+)</button>", sports)
    eq(sport_labels, ["All"] + _present_sports(html),
       f"{why} sport pills are All plus the sports with a lane on the list")
    ok("<a " not in sports, f"{why} sport pills do not navigate")
    ok("trading.html" not in sports, f"{why} sport pills do not link the Trading page")
    ok('aria-disabled' not in sports and 'tabindex="-1"' not in sports,
       f"{why} sport pills are enabled and in the tab order")
    eq(sports.count('aria-pressed="true"'), 1, f"{why} exactly one sport pill is pressed")
    ok('data-sport="all" aria-pressed="true"' in sports,
       f"{why} All starts pressed")
    eq(sports.count('aria-pressed="false"'), len(sport_labels) - 1,
       f"{why} the other sport pills are not pressed")
    ok('aria-describedby="sports-soon"' not in sports and 'id="sports-soon"' not in html
       and ">Coming soon</p>" not in html,
       f"{why} has no Coming soon note")
    ok('data-filter="live"' in html and 'data-filter="settled"' in html
       and 'data-filter="upcoming"' in html,
       f"{why} has Live / Settled / Upcoming filters")
    ok(">Live <span class=\"count\">" in html and ">Settled <span class=\"count\">" in html
       and ">Upcoming <span class=\"count\">" in html,
       f"{why} counts each Running filter")
    eq(html.count('</span><span class="sr-only"> paper bets</span></button>'), 3,
       f"{why} each filter count is read as paper bets")
    if 'class="running-row"' in html:
        ok('class="bet-chip"' in html, f"{why} wires the Open and recent roll")
        ok("No open or recent paper bets yet." not in html,
           f"{why} hides the roll empty state when a chip is showing")
    else:
        ok("No open or recent paper bets yet." in html,
           f"{why} bet roll stays empty when there is nothing to show")
        ok('class="bet-chip"' not in html, f"{why} an empty roll has no chips")
    ok('class="event-chip"' not in html, f"{why} bet roll has no sketch chips")
    stamp = re.search(r'<div class="topbar">.*?<p class="stamp">(.*?)</p>', html, re.S)
    ok(stamp and fmt.iso_z(NOW) in stamp.group(1) and "CT" in stamp.group(1),
       f"{why} top bar stamp is the build clock, labeled CT")
    ok("No live, settled, or upcoming paper bets." not in html,
       f"{why} does not use the combined empty line")
    ok("These filters do not change the list yet." not in html,
       f"{why} does not mark the filters as display-only")
    ok("Select a contest in Running." in html, f"{why} Rules-applied pane starts empty")
    ok('class="rule-mini"' not in html, f"{why} has no Rules-applied mini cards")
    ok(re.search(r">\s*History\s*<", html, re.I) is None,
       f"{why} has no History tab")
    ok('role="tab"' not in html, f"{why} has no tab stub")
    ok('href="./production.html"' in html and "Full page" in html,
       f"{why} links Full page to the existing Production board")
    ok('data-board="production"' in html, f"{why} summary strip is the Production board")
    ok("paper bets landed · last 14 days" in _tiles(html) and "recent leads landed" not in _tiles(html),
       f"{why} counts landed paper bets over the shell window, not recent leads")
    ok('<title>Edge Machine · Home</title>' in html and '<body class="analyst-desk">' in html,
       f"{why} is titled Home on the analyst-desk body")
    ok('<link rel="icon" href="./favicon.svg" type="image/svg+xml">' in html,
       f"{why} links the favicon")
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
    eq(_without_landed(shell_tiles), _without_landed(prod_tiles),
       "summary strip is the Production page's own tiles, bar the landed tile")
    eq(shell_tiles, shell_build._with_landed(prod_tiles, 1, 2),
       "the landed tile is rewritten in place from the roll's chips")
    ok("recent leads landed" in prod_tiles and "recent leads landed" not in shell_tiles,
       "production.html keeps its own landed tile; the shell does not copy it")
    want_next = fmt.when("2026-10-06T15:00:00Z")
    eq(_tile_map(shell_tiles), {
        "pairs in Production": "1",
        "leads still to come": "2",
        "paper bets landed · last 14 days": "1/2",
        "next lead (CT)": want_next,
    }, "fixture totals are the Production headlines, with landed paper bets")
    empty = shell_build.page(
        NOW, d={"quotes": []}, st={"pairs": {}}, blob={"leads": {}, "pairs": {}})
    eq(_tile_map(_tiles(empty)), {
        "pairs in Production": "0",
        "leads still to come": "0",
        "paper bets landed · last 14 days": "0/0",
        "next lead · none logged yet": "None scheduled",
    }, "an empty board prints the Production zeros and no next lead, not the sketch")
    ok("No open or recent paper bets yet." in empty and 'class="bet-chip"' not in empty,
       "an empty board keeps the roll empty state")
    eq(re.findall(r">([^<]+)</button>", _sports(empty)), ["All"],
       "an empty board has only the All pill")
    live = shell_build.page(NOW)
    live_prod = production.page(T.load(), T.load_stages(), production.load_feed(), "", now=NOW)
    eq(_without_landed(_tiles(live)), _without_landed(_tiles(live_prod)),
       "the live shell strip matches the live Production headlines, bar the landed tile")
    live_chips = re.findall(r'<button\b[^>]*class="bet-chip"[^>]*>', live)
    live_won = sum(1 for chip in live_chips if 'data-status="W"' in chip)
    # A no-result chip (data-status price) is on the settled list and out of
    # the landed count: it is neither a win nor a loss.
    live_settled = sum(1 for chip in live_chips
                       if re.search(r'data-status="(?:W|L|Void)"', chip))
    eq(_tiles(live), shell_build._with_landed(_tiles(live_prod), live_won, live_settled),
       "the live landed tile counts the live roll's settled chips, no-result chips apart")
    _check_chrome(live, "live shell", placeholders=False)

    print("\none build writes production.html and index.html")
    import sandbox_build
    later = datetime(2026, 10, 6, 18, 0, tzinfo=timezone.utc)
    built_prod, built_index = sandbox_build.production_and_index(NOW, d, st, blob)
    eq(_without_landed(_tiles(built_prod)), _without_landed(_tiles(built_index)),
       "one build writes both pages with the same tiles, bar the landed tile")
    eq(_tile_map(_tiles(built_index)), {
        "pairs in Production": "1",
        "leads still to come": "2",
        "paper bets landed · last 14 days": "1/2",
        "next lead (CT)": want_next,
    }, "that shared strip is the Production headlines at this clock")
    later_prod, later_index = sandbox_build.production_and_index(later, d, st, blob)
    eq(_without_landed(_tiles(later_prod)), _without_landed(_tiles(later_index)),
       "a later clock still writes the same tiles on both pages")
    ok(_tiles(later_prod) != _tiles(built_prod),
       "the shared strip follows that clock")
    # Passing tiles must not count again. A boom in production.page proves it.
    sentinel = '<div class="tiles"><div class="tile"><b>7</b><span>pairs in Production</span></div></div>'
    real_page = production.page
    def _boom(*_a, **_k):
        raise AssertionError("shell recounted tiles")
    production.page = _boom
    try:
        copied = shell_build.page(NOW, tiles=sentinel)
    finally:
        production.page = real_page
    ok('<div class="tile"><b>7</b><span>pairs in Production</span></div>' in copied
       and "paper bets landed" in _tiles(copied) and "recent leads landed" not in copied,
       "the shell uses the tiles it was given, adding only its landed tile")

    print("\npublished root")
    root_html = open(os.path.join(ROOT, "public_site", "index.html"), encoding="utf-8").read()
    ok('<a class="brand" href="./index.html" aria-current="page">Edge Machine</a>' in root_html
       and 'aria-current="page"' not in _nav(root_html),
       "public_site/index.html marks the brand current, not a page pill")
    ok('http-equiv="refresh"' not in root_html,
       "public_site/index.html does not refresh to the Sandbox")
    ok("Select a contest in Running." in root_html,
       "public_site/index.html has the empty Rules-applied pane")
    ok(re.search(r">\s*History\s*<", root_html, re.I) is None,
       "public_site/index.html has no History tab")
    for rel in ("sandbox.html", "production.html", "trading.html"):
        ok(os.path.isfile(os.path.join(ROOT, "public_site", rel)),
           f"{rel} still exists for the page pill")
    prod_html = open(os.path.join(ROOT, "public_site", "production.html"), encoding="utf-8").read()
    eq(_tile_map(_without_landed(_tiles(root_html))), _tile_map(_without_landed(_tiles(prod_html))),
       "committed index.html tiles equal committed production.html tiles, bar the landed tile")
    ok("paper bets landed · last 14 days" in _tile_map(_tiles(root_html))
       and "recent leads landed" in _tile_map(_tiles(prod_html)),
       "the committed shell counts landed paper bets; production.html keeps recent leads")
    tracker = open(os.path.join(ROOT, ".github", "workflows", "sandbox-tracker.yml"),
                   encoding="utf-8").read()
    ok("public_site/index.html" in tracker.split('SITE="', 1)[-1].split('"', 1)[0],
       "the tracker commit step stages index.html")
    boards = open(os.path.join(ROOT, ".github", "workflows", "refresh-boards.yml"),
                  encoding="utf-8").read()
    ok("python3 site_root.py" not in boards and "public_site/index.html" not in boards,
       "refresh-boards does not write or stage the shell strip")
    sandbox = open(os.path.join(ROOT, "public_site", "sandbox.html"), encoding="utf-8").read()
    ok('id="method"' in sandbox, "Method still points at the Sandbox method section")

    js = open(os.path.join(ROOT, "public_site", "shell.js"), encoding="utf-8").read()
    ok("fetch(" not in js and "location." not in js and "XMLHttpRequest" not in js,
       "shell.js does not load bets or navigate")
    ok("aria-pressed" in js, "shell.js records which Running filter is pressed")
    ok("data-sport-filter" in js,
       "a chip can switch a sport filter that is hiding its contest")
    ok('"nav.sport-filter"' in js and "button[data-sport=" in js,
       "shell.js reads a sport pill in the Running pane so a chip can reveal its contest")
    ok(not os.path.isfile(os.path.join(ROOT, "public_site", "root.js")),
       "root.js is gone; no page loads the old Sandbox redirect")


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
                empty: document.getElementById("rules-empty").textContent,
                emptyHidden: document.getElementById("rules-empty").hidden,
                pressed: document.querySelectorAll('.running-row[aria-pressed="true"]').length,
                rows: document.querySelectorAll('.running-row:not([hidden])').length,
                cards: document.querySelectorAll(".rule-mini").length,
                current: (document.querySelector('a.brand[aria-current="page"]') || {}).textContent || "",
                pills: document.querySelectorAll('nav.main [aria-current="page"]').length,
              };
            }""")
            ok(wide["side"] and not wide["overflow"],
               f"desktop panes sit side by side without sideways scroll ({wide})")
            ok(wide["current"].strip() == "Edge Machine" and wide["pills"] == 0,
               f"desktop land marks the brand current and no page pill ({wide['current']!r})")
            ok(not wide["history"], "desktop has no History tab")
            if wide["rows"]:
                ok(wide["pressed"] == 1 and wide["cards"] >= 1 and wide["emptyHidden"],
                   f"with Running rows, the first is pressed so the detail pane is not empty ({wide})")
            else:
                ok(wide["pressed"] == 0 and wide["empty"] == "Select a contest in Running.",
                   f"with no Running rows, the detail pane starts empty ({wide})")
            ok(wide["bg"] in ("rgb(11, 12, 15)", "rgb(11, 13, 16)"),
               f"desktop background stays dark ({wide['bg']})")
            page.mouse.move(0, 0)
            sports = page.evaluate("""() => {
              const nav = document.querySelector("nav.sport-filter");
              const buttons = [...nav.querySelectorAll("button")];
              const note = document.getElementById("sports-soon");
              const fg = getComputedStyle(document.body).color;
              const pressed = buttons.filter((b) => b.getAttribute("aria-pressed") === "true");
              const idle = buttons.find((b) => b.getAttribute("aria-pressed") === "false");
              const all = buttons.find((b) => b.getAttribute("data-sport") === "all");
              const allStyle = getComputedStyle(all);
              const idleStyle = idle ? getComputedStyle(idle) : null;
              const present = new Set([...document.querySelectorAll(".running-row")]
                .map((row) => row.getAttribute("data-sport")));
              return {
                n: buttons.length,
                inRunning: !!nav.closest("#running"),
                labels: buttons.map((b) => b.textContent.trim()),
                missing: buttons.filter((b) => b.getAttribute("data-sport") !== "all"
                  && !present.has(b.textContent.trim())).map((b) => b.textContent.trim()),
                idle: idle ? idle.getAttribute("data-sport") : "",
                disabled: buttons.some((b) => b.getAttribute("aria-disabled") === "true"
                  || b.tabIndex < 0),
                pressed: pressed.map((b) => b.getAttribute("data-sport")),
                note: note ? note.textContent.trim() : "",
                described: nav.getAttribute("aria-describedby"),
                cursor: allStyle.cursor,
                allColor: allStyle.color,
                idleColor: idleStyle ? idleStyle.color : "",
                fg: fg,
                allBg: allStyle.backgroundColor,
                idleBg: idleStyle ? idleStyle.backgroundColor : "",
                hrefs: [...document.querySelectorAll("nav.main a")].map((a) => a.getAttribute("href")),
              };
            }""")
            page.locator("a.brand").focus()
            focused = None
            for _ in range(30):
                page.keyboard.press("Tab")
                focused = page.evaluate("""() => {
                  const el = document.activeElement;
                  const style = getComputedStyle(el);
                  return {
                    sport: el && el.getAttribute("data-sport"),
                    tag: el && el.tagName,
                    inMain: !!(el && el.closest("nav.main")),
                    outline: style.outlineStyle,
                    width: style.outlineWidth,
                  };
                }""")
                if focused["sport"] == "all":
                    break
            all_labels = [label for _key, label in shell_build.SPORTS]
            ok(sports["n"] >= 1 and sports["labels"][0] == "All"
               and sports["labels"] == [l for l in all_labels if l in sports["labels"]]
               and sports["missing"] == [] and sports["inRunning"]
               and not sports["disabled"] and sports["pressed"] == ["all"]
               and sports["note"] == "" and not sports["described"]
               and sports["cursor"] == "pointer" and sports["allColor"] == sports["fg"]
               and sports["allBg"] not in ("transparent", "rgba(0, 0, 0, 0)")
               and (not sports["idle"] or (sports["idleColor"] != sports["fg"]
                                           and sports["idleBg"] in ("transparent", "rgba(0, 0, 0, 0)")))
               and sports["hrefs"] == [href[6:-1] for href in PAGE_HREFS]
               and focused["sport"] == "all" and focused["tag"] == "BUTTON"
               and focused["outline"] == "solid" and focused["width"] == "3px",
               f"sport pills filter in place inside Running and page pills stay links ({sports}, focus {focused})")
            page.click('nav.main a[href="./sandbox.html"]')
            page.wait_for_url("**/sandbox.html")
            ok(page.url.endswith("sandbox.html"),
               f"the Sandbox page pill still opens the Sandbox ({page.url})")
            page.goto(base, wait_until="load")
            page.set_viewport_size({"width": 390, "height": 844})
            page.wait_for_timeout(40)
            narrow = page.evaluate("""() => {
              const cols = document.querySelector(".shell-columns");
              // Both columns use display:contents on a phone; measure the panes.
              const panes = [...cols.querySelectorAll(".shell-pane")]
                .map((pane) => ({ id: pane.id, box: pane.getBoundingClientRect() }))
                .sort((a, b) => a.box.top - b.box.top);
              let stacked = panes.length >= 4;
              for (let i = 1; i < panes.length; i += 1) {
                if (panes[i].box.top < panes[i - 1].box.bottom - 2) stacked = false;
              }
              return {
                order: panes.map((pane) => pane.id),
                stacked: stacked && panes.every((pane) => pane.box.width > 200),
                overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
              };
            }""")
            ok(narrow["stacked"] and not narrow["overflow"]
               and narrow["order"] == ["running", "rules", "status", "bets-roll"],
               f"phone stacks the panes, Running, Rule cards, Status, then the roll, "
               f"without sideways scroll ({narrow})")
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
