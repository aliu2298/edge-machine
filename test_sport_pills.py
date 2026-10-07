#!/usr/bin/env python3
"""Sport pills filter the Running list in place.

Fails while the pills are aria-disabled chrome with a Coming soon note, or
while a pill does not hide the other sports. Passes once All shows every
group, one sport hides the rest across Live / Settled / Upcoming, the counts
match the rows still on screen, and the choice is forgotten on reload.
No network. The clock is pinned. Browser checks need REQUIRE_BROWSER=1.
"""
import datetime
import html as html_lib
import os
import re
import shutil
import sys
import tempfile
import threading
from datetime import timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import shell_build

FAILS = []
ROOT = os.path.dirname(os.path.abspath(__file__))
NOW = datetime.datetime(2026, 10, 5, 18, 0, tzinfo=timezone.utc)
PILL_LABEL = {
    "all": None,
    "nba": "nba",
    "soccer": "soccer",
    "tennis": "tennis",
    "cricket": "cricket",
    "crypto": "crypto",
}


def ok(cond, why):
    print(f"  {'ok  ' if cond else 'FAIL'} {why}")
    if not cond:
        FAILS.append(why)


def eq(got, want, why):
    ok(got == want, why if got == want else f"{why} — got {got!r}, want {want!r}")


def _lead(lid, home, away, kickoff, status, sport, price=0.54):
    return {
        "id": lid,
        "home": home,
        "away": away,
        "match": f"{home} v {away}",
        "headline": f"{home} to win",
        "kickoff": kickoff,
        "status": status,
        "pair": f"note|{sport}",
        "sport": sport,
        "lane": "production",
        "price_at_log": price,
        "league": "League",
        "source": "note",
        "sandbox_quote": lid,
    }


def _blob(leads):
    return {"leads": {lead["id"]: lead for lead in leads}, "pairs": {}}


def _rows(page):
    return re.findall(r'<button\b[^>]*class="running-row"[^>]*>.*?</button>', page, re.S)


def _attr(tag, name):
    match = re.search(rf'\b{name}="([^"]*)"', tag)
    return html_lib.unescape(match.group(1)) if match else None


LEADS = [
    _lead("s-live-a", "Alpha", "Beta", "2026-10-05T16:00:00Z", "pending", "soccer"),
    _lead("s-live-b", "Gamma", "Delta", "2026-10-05T17:00:00Z", "pending", "soccer"),
    _lead("s-soon", "Later", "Side", "2026-10-06T15:00:00Z", "pending", "soccer"),
    _lead("s-done", "Past", "Score", "2026-10-04T15:00:00Z", "hit", "soccer"),
    _lead("c-live-a", "Crease", "Wicket", "2026-10-05T12:00:00Z", "pending", "cricket"),
    _lead("c-live-b", "Bowl", "Bat", "2026-10-05T13:00:00Z", "pending", "cricket"),
    _lead("c-done", "Echo", "Foxtrot", "2026-10-03T15:00:00Z", "miss", "cricket"),
    _lead("n-soon", "Lakers", "Celtics", "2026-10-07T15:00:00Z", "pending", "NBA"),
    _lead("k-soon", "Coin", "Token", "2026-10-08T15:00:00Z", "pending", "crypto_fav"),
    _lead("u-live", "Curl", "Stone", "2026-10-05T11:00:00Z", "pending", "curling"),
    _lead("m-live", "Market", "Quote", "2026-10-05T15:00:00Z", "pending", "crypto"),
]
PAGE = shell_build.page(NOW, d={"quotes": []}, st={"pairs": {}}, blob=_blob(LEADS))
ROWS = _rows(PAGE)
BY_NAME = {_attr(row, "data-name"): row for row in ROWS}


def _sports_nav(page):
    match = re.search(r'<nav class="sports sport-filter"[^>]*>.*?</nav>', page, re.S)
    return match.group(0) if match else ""


EMPTY = shell_build._EMPTY

print("pill markup")
sports = _sports_nav(PAGE)
ok(sports, "the shell has sport pills")
eq(re.findall(r">([^<]+)</button>", sports),
   ["All", "NBA", "Soccer", "Cricket", "Crypto"],
   "the pills are All plus the sports with a lane: NBA, Soccer, Cricket, and Crypto")
ok('data-sport="tennis"' not in sports, "a sport with no lane on the list has no pill")
eq(re.findall(r">([^<]+)</button>", shell_build._sport_pills(None)),
   ["All", "NBA", "Soccer", "Tennis", "Cricket", "Crypto"],
   "with no present set, every pill is drawn")
eq(re.findall(r">([^<]+)</button>", shell_build._sport_pills(set())), ["All"],
   "with nothing present, only All is drawn")
_running_pane = PAGE.split('id="running"', 1)[1].split("</section>", 1)[0]
ok(sports in _running_pane
   and _running_pane.find('class="running-filters"') < _running_pane.find(sports)
   < _running_pane.find('id="settled-caption"'),
   "the pills sit inside the Running pane, between the filters and the settled caption")
ok('aside class="desk-nav"' not in PAGE and "desk-nav-block" not in PAGE,
   "there is no sidebar nav")
ok("<a " not in sports, "sport pills do not navigate")
ok('data-sport="crypto"' in sports and "trading.html" not in sports,
   "Crypto is a sport pill, not the Trading page")
ok('aria-disabled' not in sports and 'tabindex="-1"' not in sports,
   "sport pills are enabled and in the tab order")
eq(sports.count('aria-pressed="true"'), 1, "exactly one sport pill starts pressed")
ok('data-sport="all" aria-pressed="true"' in sports, "All starts pressed")
eq(sports.count('aria-pressed="false"'), 4, "the other four pills start unpressed")
ok('id="sports-soon"' not in PAGE and ">Coming soon</p>" not in PAGE
   and 'aria-describedby="sports-soon"' not in PAGE,
   "the Coming soon note is gone")
eq(_attr(BY_NAME["Alpha vs Beta"], "data-sport"), "Soccer", "a soccer row keeps its sport")
eq(_attr(BY_NAME["Crease vs Wicket"], "data-sport"), "Cricket", "a cricket row keeps its sport")
eq(_attr(BY_NAME["Lakers vs Celtics"], "data-sport"), "NBA", "an NBA row keeps its sport")
eq(_attr(BY_NAME["Coin vs Token"], "data-sport"), "Crypto", "a crypto row keeps its sport")
eq(_attr(BY_NAME["Curl vs Stone"], "data-sport"), "curling",
   "an unknown sport stays the row's own sport")
eq(_attr(BY_NAME["Market vs Quote"], "data-sport"), "Markets",
   "a crypto market row keeps the Markets label it already has")
ok("localStorage" not in PAGE and "sessionStorage" not in PAGE,
   "the page does not embed a stored sport")

js = open(os.path.join(ROOT, "public_site", "shell.js"), encoding="utf-8").read()
for needle in ("localStorage", "sessionStorage", "document.cookie", "location.hash",
               "location.", "innerHTML", "fetch("):
    ok(needle not in js, f"shell.js does not use {needle}")
ok("pressSport" in js and "refreshCounts" in js and "data-dimmed" in js,
   "shell.js arms the pills, recounts the tabs, and dims other chips")

trading = open(os.path.join(ROOT, "public_site", "trading.html"), encoding="utf-8").read()
ok('href="./trading.html" aria-current="page"' in trading,
   "the Trading page still marks its own pill")
ok('href="./crypto.html"' in trading and "shell.js" not in trading,
   "the Trading page keeps its crypto link and does not load the shell")
ok('class="running-row"' not in trading and 'id="sports-soon"' not in trading,
   "the Trading page has no Running list and no Coming soon note")


def _expect(rows, pill, tab):
    label = PILL_LABEL[pill]
    visible = []
    counts = {"live": 0, "settled": 0, "upcoming": 0}
    for row in rows:
        sport = (row["sport"] or "").strip().lower()
        allowed = pill == "all" or sport == label
        if allowed and row["filter"] in counts:
            counts[row["filter"]] += row["lanes"]
        if allowed and row["filter"] == tab:
            visible.append(row["name"])
    return counts, visible


def _check_filter(snap, why):
    eq(len(snap["pressed"]), 1, f"{why}: exactly one sport pill is pressed")
    if len(snap["pressed"]) != 1:
        return
    pill = snap["pressed"][0]
    counts, visible = _expect(snap["rows"], pill, snap["tab"])
    eq(snap["ui"], counts, f"{why}: each tab count is the filtered set")
    shown = [row["name"] for row in snap["rows"] if not row["hidden"]]
    eq(shown, visible, f"{why}: the current tab shows only that sport's rows")
    painted = [row["name"] for row in snap["rows"] if row["display"] != "none"]
    eq(painted, visible, f"{why}: hidden rows are not painted")
    ok(all(row["display"] == "none" for row in snap["rows"] if row["hidden"]),
       f"{why}: a filtered-out row stays display:none")
    if visible:
        ok(snap["emptyHidden"] and snap["emptyText"],
           f"{why}: a tab with rows hides the empty state")
    else:
        want = EMPTY[snap["tab"]]
        ok(not snap["emptyHidden"] and snap["emptyText"] == want,
           f"{why}: an empty tab uses the existing empty line ({snap['emptyText']!r})")
    ok(not snap["disabled"] and not snap["soon"],
       f"{why}: pills stay enabled, with no Coming soon note")


SNAP = """() => {
  const buttons = [...document.querySelectorAll("nav.sport-filter button")];
  const pressed = buttons.filter((b) => b.getAttribute("aria-pressed") === "true");
  const tabBtn = document.querySelector(".running-filters button[aria-pressed='true']");
  const rows = [...document.querySelectorAll(".running-row")].map((row) => ({
    name: row.getAttribute("data-name"),
    sport: row.getAttribute("data-sport"),
    filter: row.getAttribute("data-filter"),
    lanes: parseInt(row.getAttribute("data-lanes") || "1", 10),
    hidden: row.hidden,
    display: getComputedStyle(row).display,
  }));
  const ui = {};
  document.querySelectorAll(".running-filters button").forEach((btn) => {
    ui[btn.getAttribute("data-filter")] = Number(btn.querySelector(".count").textContent);
  });
  const empty = document.getElementById("running-empty");
  const detail = document.getElementById("rules-empty");
  const line = document.getElementById("rules-line");
  const head = document.getElementById("rules-head");
  const selected = [...document.querySelectorAll('.running-row[aria-pressed="true"]')]
    .map((row) => row.getAttribute("data-name"));
  return {
    pressed: pressed.map((b) => b.getAttribute("data-sport")),
    disabled: buttons.some((b) => b.getAttribute("aria-disabled") !== null || b.tabIndex < 0),
    soon: !!document.getElementById("sports-soon") || document.body.textContent.includes("Coming soon"),
    tab: tabBtn ? tabBtn.getAttribute("data-filter") : "",
    ui: ui,
    rows: rows,
    emptyHidden: empty ? empty.hidden : null,
    emptyText: empty ? empty.textContent : "",
    detailHidden: detail ? detail.hidden : null,
    detailText: detail ? detail.textContent : "",
    line: line ? line.textContent : "",
    headHidden: head ? head.hidden : null,
    selected: selected,
    cards: document.querySelectorAll(".rule-mini").length,
    live: (document.getElementById("rules-live") || {}).textContent || "",
    pills: buttons.map((b) => b.getAttribute("data-sport")),
    hash: location.hash,
  };
}"""


def _cleared_text(name, sport):
    return f"Selection cleared: {name} is not in {sport}. Select a contest in Running."


def _browser():
    from require_browser import require_browser
    sync_playwright = require_browser("test_sport_pills.py")
    if sync_playwright is None:
        return
    site = tempfile.mkdtemp(prefix="sport-pills-")
    try:
        open(os.path.join(site, "index.html"), "w", encoding="utf-8").write(PAGE)
        shutil.copy(os.path.join(ROOT, "public_site", "trading.html"),
                    os.path.join(site, "trading.html"))
        for name in ("site.css", "shell.js", "tables.js"):
            shutil.copy(os.path.join(ROOT, "public_site", name), os.path.join(site, name))

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
                page.mouse.move(0, 0)
                initial = page.evaluate(SNAP)
                _check_filter(initial, "All on Live")
                eq(initial["pressed"], ["all"], "All is pressed on load")
                eq(initial["tab"], "live", "Live is the tab on load")
                ok(any(row["name"] == "Curl vs Stone" and not row["hidden"]
                       for row in initial["rows"]),
                   "an unknown sport is visible under All")
                ok(any(row["name"] == "Market vs Quote" and not row["hidden"]
                       for row in initial["rows"]),
                   "a Markets row is visible under All")
                eq(initial["pills"], ["all", "nba", "soccer", "cricket", "crypto"],
                   "the pills are All and the sports with a lane; Tennis has none")
                eq(initial["selected"], ["Alpha vs Beta"],
                   "the first visible row starts pressed on load")
                ok(initial["detailHidden"] and "Alpha vs Beta" in initial["line"]
                   and initial["cards"] >= 1,
                   f"the detail pane opens on that first row ({initial['line']!r})")

                page.click('nav.sport-filter button[data-sport="soccer"]')
                soccer = page.evaluate(SNAP)
                _check_filter(soccer, "Soccer on Live")
                eq(soccer["pressed"], ["soccer"], "Soccer is the only pressed pill")
                eq(soccer["selected"], ["Alpha vs Beta"],
                   "choosing a sport keeps a pressed row that is still visible")
                ok(soccer["detailHidden"] and "Alpha vs Beta" in soccer["line"]
                   and soccer["cards"] == initial["cards"],
                   "the detail pane keeps that row's cards")
                ok(all(row["name"] != "Curl vs Stone" or row["hidden"] for row in soccer["rows"]),
                   "an unknown sport is hidden under Soccer")
                ok(all(row["name"] != "Market vs Quote" or row["hidden"] for row in soccer["rows"]),
                   "a Markets row is hidden under Soccer")
                page.click('nav.sport-filter button[data-sport="soccer"]')
                again = page.evaluate(SNAP)
                eq(again["pressed"], ["soccer"], "pressing Soccer again leaves it pressed")
                eq(again["selected"], ["Alpha vs Beta"], "pressing Soccer again keeps the selection")
                _check_filter(again, "Soccer pressed again")

                page.click('.running-filters button[data-filter="settled"]')
                settled = page.evaluate(SNAP)
                _check_filter(settled, "Soccer on Settled")
                eq(settled["pressed"], ["soccer"], "the sport pill stays put across tabs")
                eq(settled["selected"], [], "a tab that hides the pressed row clears the selection")
                ok(not settled["detailHidden"] and settled["cards"] == 0
                   and settled["detailText"].startswith("Selection cleared: Alpha vs Beta is not in ")
                   and settled["detailText"].endswith(" Select a contest in Running."),
                   f"the detail pane says why it emptied ({settled['detailText']!r})")
                eq(settled["ui"], soccer["ui"], "changing tabs does not change the filtered counts")
                eq([row["name"] for row in settled["rows"] if not row["hidden"]],
                   ["Past vs Score"], "Settled under Soccer is the soccer result")
                page.click('.running-filters button[data-filter="upcoming"]')
                upcoming = page.evaluate(SNAP)
                _check_filter(upcoming, "Soccer on Upcoming")
                eq(upcoming["pressed"], ["soccer"], "Upcoming keeps the Soccer pill")
                eq([row["name"] for row in upcoming["rows"] if not row["hidden"]],
                   ["Later vs Side"], "Upcoming under Soccer is the soccer fixture")
                page.click('.running-filters button[data-filter="live"]')
                live = page.evaluate(SNAP)
                _check_filter(live, "Soccer back on Live")
                eq([row["name"] for row in live["rows"] if not row["hidden"]],
                   ["Alpha vs Beta", "Gamma vs Delta"], "Live under Soccer is the two soccer rows")

                page.click('nav.sport-filter button[data-sport="all"]')
                restored = page.evaluate(SNAP)
                _check_filter(restored, "All restores Live")
                eq(restored["pressed"], ["all"], "All is pressed again")
                eq(restored["ui"], initial["ui"], "All restores every tab count")
                eq([row["name"] for row in restored["rows"] if not row["hidden"]],
                   [row["name"] for row in initial["rows"] if not row["hidden"]],
                   "All shows the same Live rows as the first load")

                eq(page.locator('nav.sport-filter button[data-sport="tennis"]').count(), 0,
                   "Tennis, with no lane on the list, has no pill to press")
                page.click('nav.sport-filter button[data-sport="nba"]')
                empty = page.evaluate(SNAP)
                _check_filter(empty, "NBA has no live rows")
                eq(empty["pressed"], ["nba"], "NBA is the only pressed pill")
                eq(empty["ui"], {"live": 0, "settled": 0, "upcoming": 1},
                   "a sport with one upcoming bet zeros the other tabs")
                eq(empty["emptyText"], EMPTY["live"],
                   "a sport with no live rows uses the live empty line")
                page.click('.running-filters button[data-filter="settled"]')
                empty_settled = page.evaluate(SNAP)
                _check_filter(empty_settled, "NBA has no settled rows")
                eq(empty_settled["emptyText"], EMPTY["settled"],
                   "the empty line follows the tab")
                page.click('.running-filters button[data-filter="live"]')

                page.click('nav.sport-filter button[data-sport="all"]')
                page.locator('.running-row[data-name="Bowl vs Bat"]').click()
                page.click('nav.sport-filter button[data-sport="soccer"]')
                moved = page.evaluate(SNAP)
                _check_filter(moved, "Soccer after a cricket selection")
                eq(moved["selected"], [],
                   "a filtered-out contest clears the selection, with no switch to another contest")
                eq(moved["detailText"], _cleared_text("Bowl vs Bat", "Soccer"),
                   "the detail pane says which contest was cleared and why")
                eq(moved["live"], moved["detailText"], "the live region reads the same reason")
                ok(moved["headHidden"] and not moved["detailHidden"]
                   and moved["cards"] == 0 and moved["line"] == "",
                   f"the detail header and cards are gone ({moved['line']!r})")
                page.click('nav.sport-filter button[data-sport="cricket"]')
                moved_back = page.evaluate(SNAP)
                _check_filter(moved_back, "Cricket after a soccer selection")
                eq(moved_back["selected"], [],
                   "returning to Cricket does not pick a contest on its own")
                ok(moved_back["cards"] == 0 and not moved_back["detailHidden"]
                   and moved_back["detailText"].endswith("Select a contest in Running."),
                   "the detail pane still asks for a contest")

                page.locator('.running-row[data-name="Crease vs Wicket"]').click()
                chosen = page.evaluate(SNAP)
                eq(chosen["selected"], ["Crease vs Wicket"], "a visible cricket row can be pressed")
                page.click('nav.sport-filter button[data-sport="crypto"]')
                cleared = page.evaluate(SNAP)
                _check_filter(cleared, "Crypto clears a hidden selection")
                eq(cleared["selected"], [], "no visible row clears the selection")
                eq(cleared["cards"], 0, "clearing the selection removes the cards")
                eq(cleared["line"], "", "clearing the selection clears the detail header")
                ok(cleared["headHidden"] and not cleared["detailHidden"]
                   and cleared["detailText"] == _cleared_text("Crease vs Wicket", "Crypto"),
                   f"the detail pane says the contest is not in Crypto ({cleared['detailText']!r})")
                page.click('nav.sport-filter button[data-sport="all"]')

                page.click('nav.sport-filter button[data-sport="crypto"]')
                crypto = page.evaluate(SNAP)
                _check_filter(crypto, "Crypto on Live")
                eq(crypto["pressed"], ["crypto"], "Crypto is the only pressed pill")
                eq(page.url, base, "the Crypto pill does not navigate")
                ok(all(row["hidden"] or row["sport"] == "Crypto" for row in crypto["rows"]),
                   "Crypto shows only rows whose sport is Crypto")
                ok(all(row["name"] != "Market vs Quote" or row["hidden"] for row in crypto["rows"]),
                   "a Markets row stays hidden under the Crypto pill")
                page.click('.running-filters button[data-filter="upcoming"]')
                crypto_up = page.evaluate(SNAP)
                _check_filter(crypto_up, "Crypto on Upcoming")
                eq([row["name"] for row in crypto_up["rows"] if not row["hidden"]],
                   ["Coin vs Token"], "Upcoming under Crypto is the crypto contest")
                ok(all(row["name"] != "Market vs Quote" or row["hidden"]
                       for row in crypto_up["rows"]),
                   "Markets is still not a Crypto row on Upcoming")

                page.click('.running-filters button[data-filter="live"]')
                page.click('nav.sport-filter button[data-sport="soccer"]')
                chips = page.evaluate("""() => [...document.querySelectorAll(".bet-chip")].map((chip) => {
                  const note = chip.querySelector(".chip-filter-note");
                  const style = getComputedStyle(chip);
                  return {
                    name: (chip.querySelector(".bet-chip-contest") || {}).textContent || "",
                    dimmed: chip.getAttribute("data-dimmed"),
                    opacity: Number(style.opacity),
                    note: note ? note.textContent : "",
                    events: style.pointerEvents,
                  };
                })""")
                by_chip = {chip["name"]: chip for chip in chips}
                own = by_chip["Alpha vs Beta"]
                other = by_chip["Crease vs Wicket"]
                unknown = by_chip["Curl vs Stone"]
                market = by_chip["Market vs Quote"]
                coin = by_chip["Coin vs Token"]
                ok(own["dimmed"] is None and own["opacity"] == 1 and own["note"] == "",
                   f"a chip for the selected sport stays bright ({own})")
                ok(other["dimmed"] == "true" and 0.5 < other["opacity"] < 0.9
                   and other["note"] == "other sport" and other["events"] != "none"
                   and "Crease vs Wicket" in other["name"],
                   f"another sport's chip is dimmed, readable, and labeled ({other})")
                ok(unknown["dimmed"] == "true" and unknown["note"] == "other sport",
                   f"an unknown sport's chip is dimmed too ({unknown})")
                ok(market["dimmed"] == "true" and coin["dimmed"] == "true",
                   "Markets and Crypto chips dim while Soccer is pressed")
                page.locator(".bet-chip").filter(has_text="Crease vs Wicket").click()
                from_chip = page.evaluate(SNAP)
                _check_filter(from_chip, "a dimmed cricket chip")
                eq(from_chip["pressed"], ["cricket"],
                   "a dimmed chip presses that contest's sport pill")
                eq(from_chip["tab"], "live", "a live chip stays on Live")
                eq(from_chip["selected"], ["Crease vs Wicket"],
                   "the dimmed chip selects its contest")
                ok(all(not row["hidden"] for row in from_chip["rows"]
                       if row["name"] == "Crease vs Wicket"),
                   "the chip's row is visible")

                page.click('nav.sport-filter button[data-sport="soccer"]')
                page.locator(".bet-chip").filter(has_text="Curl vs Stone").focus()
                page.keyboard.press("Enter")
                from_unknown = page.evaluate(SNAP)
                _check_filter(from_unknown, "a dimmed unknown chip")
                eq(from_unknown["pressed"], ["all"],
                   "a chip whose sport has no pill presses All")
                eq(from_unknown["selected"], ["Curl vs Stone"],
                   "that chip selects the unknown-sport contest")
                ok(any(not row["hidden"] and row["name"] == "Curl vs Stone"
                       for row in from_unknown["rows"]),
                   "the unknown-sport row is visible under All")

                page.click('nav.sport-filter button[data-sport="soccer"]')
                page.locator(".bet-chip").filter(has_text="Coin vs Token").click()
                from_coin = page.evaluate(SNAP)
                _check_filter(from_coin, "a dimmed crypto chip")
                eq(from_coin["pressed"], ["crypto"],
                   "a dimmed crypto chip presses Crypto, not Trading")
                eq(from_coin["tab"], "upcoming",
                   "the chip switches to the bucket that holds its contest")
                eq(from_coin["selected"], ["Coin vs Token"],
                   "the crypto chip selects its contest")
                eq(page.url, base, "the crypto chip stays on the shell")

                page.goto(base, wait_until="load")
                page.evaluate("""() => {
                  localStorage.clear();
                  sessionStorage.clear();
                  localStorage.setItem("sentinel", "keep");
                  sessionStorage.setItem("sentinel", "keep");
                }""")
                cookie_before = page.evaluate("() => document.cookie")
                page.click('nav.sport-filter button[data-sport="cricket"]')
                stored = page.evaluate("""() => ({
                  local: Object.keys(localStorage).sort(),
                  session: Object.keys(sessionStorage).sort(),
                  cookie: document.cookie,
                  hash: location.hash,
                })""")
                eq(stored["local"], ["sentinel"], "a pill writes nothing to localStorage")
                eq(stored["session"], ["sentinel"], "a pill writes nothing to sessionStorage")
                eq(stored["cookie"], cookie_before, "a pill writes no cookie")
                eq(stored["hash"], "", "a pill writes no URL hash")
                page.reload(wait_until="load")
                reloaded = page.evaluate(SNAP)
                _check_filter(reloaded, "reload")
                eq(reloaded["pressed"], ["all"], "reload returns to All")
                eq(reloaded["ui"], initial["ui"], "reload restores the unfiltered counts")
                eq(reloaded["hash"], "", "reload does not grow a hash")
                remembered = page.evaluate("""() => ({
                  local: Object.keys(localStorage).sort(),
                  session: Object.keys(sessionStorage).sort(),
                })""")
                eq(remembered["local"], ["sentinel"], "reload did not store a sport")
                eq(remembered["session"], ["sentinel"], "reload did not store a sport in the session")

                page.goto(base + "#soccer", wait_until="load")
                hashed = page.evaluate(SNAP)
                _check_filter(hashed, "a hash does not choose a sport")
                eq(hashed["pressed"], ["all"], "a sport hash still lands on All")
                eq(hashed["hash"], "#soccer", "the hash is ignored, not rewritten")
                page.click('nav.sport-filter button[data-sport="nba"]')
                hashed_click = page.evaluate(SNAP)
                eq(hashed_click["pressed"], ["nba"], "NBA can still be pressed while a hash is present")
                eq(hashed_click["hash"], "#soccer", "pressing NBA does not write the hash")
                _check_filter(hashed_click, "NBA while a hash is present")
                ok(all(row["name"] != "Curl vs Stone" or row["hidden"]
                       for row in hashed_click["rows"]),
                   "the unknown sport stays hidden under NBA")

                page.goto(base, wait_until="load")
                page.locator("a.brand").focus()
                page.keyboard.press("Tab")
                page_ring = page.evaluate("""() => {
                  const el = document.activeElement;
                  const style = getComputedStyle(el);
                  return {
                    outline: style.outlineStyle,
                    width: style.outlineWidth,
                    tag: el.tagName,
                    inMain: !!el.closest("nav.main"),
                    before: document.activeElement.compareDocumentPosition(
                      document.querySelector("nav.sport-filter")) & Node.DOCUMENT_POSITION_FOLLOWING ? true : false,
                  };
                }""")
                ok(page_ring["tag"] == "A" and page_ring["inMain"] and page_ring["before"],
                   f"Tab from the brand reaches a page pill, ahead of the sport pills ({page_ring})")
                sport_ring = None
                steps = 0
                for _ in range(30):
                    page.keyboard.press("Tab")
                    steps += 1
                    sport_ring = page.evaluate("""() => {
                      const el = document.activeElement;
                      const style = getComputedStyle(el);
                      return {
                        sport: el.getAttribute("data-sport"),
                        tag: el.tagName,
                        filter: el.getAttribute("data-filter"),
                        outline: style.outlineStyle,
                        width: style.outlineWidth,
                      };
                    }""")
                    if sport_ring["sport"] == "all":
                        break
                ok(sport_ring["sport"] == "all" and sport_ring["tag"] == "BUTTON"
                   and sport_ring["outline"] == "solid" and sport_ring["width"] == "3px"
                   and sport_ring["outline"] == page_ring["outline"]
                   and sport_ring["width"] == page_ring["width"],
                   f"a sport pill takes Tab focus after the page pills and Running filters, "
                   f"with the same ring as a page pill ({sport_ring}, page {page_ring}, {steps} tabs)")
                page.keyboard.press("Tab")
                page.keyboard.press("Enter")
                entered = page.evaluate(SNAP)
                _check_filter(entered, "Enter on NBA")
                eq(entered["pressed"], ["nba"], "Enter presses the focused pill")
                eq(entered["emptyText"], EMPTY["live"],
                   "Enter on a sport with no live rows shows the empty line")
                page.keyboard.press("Tab")
                page.keyboard.press("Space")
                spaced = page.evaluate(SNAP)
                _check_filter(spaced, "Space on Soccer")
                eq(spaced["pressed"], ["soccer"], "Space presses the focused pill")
                eq([row["name"] for row in spaced["rows"] if not row["hidden"]],
                   ["Alpha vs Beta", "Gamma vs Delta"],
                   "Space filters the list to that sport")

                crypto_url = page.url
                page.click('nav.sport-filter button[data-sport="crypto"]')
                eq(page.url, crypto_url, "Crypto still does not leave the shell")
                page.click('nav.main a[href="./trading.html"]')
                page.wait_for_url("**/trading.html")
                traded = page.evaluate("""() => {
                  const current = document.querySelector('nav.main [aria-current="page"]');
                  const crypto = document.querySelector('nav.main a[href="./crypto.html"]');
                  return {
                    href: location.pathname,
                    current: current ? current.textContent.trim() : "",
                    crypto: crypto ? crypto.getAttribute("href") : "",
                    rows: document.querySelectorAll(".running-row").length,
                    shell: !!document.querySelector("script[src='./shell.js']"),
                    sports: document.querySelectorAll("nav.sports button, nav.sport-filter button").length,
                  };
                }""")
                eq(traded["current"], "Trading", "the Trading page pill still opens Trading")
                eq(traded["crypto"], "./crypto.html",
                   "Trading keeps its own crypto link")
                eq(traded["rows"], 0, "Trading has no Running rows to filter")
                ok(traded["shell"] is False and traded["sports"] == 0,
                   f"Trading loads neither the shell script nor sport pills ({traded})")
                browser.close()
        finally:
            httpd.shutdown()
    finally:
        shutil.rmtree(site, ignore_errors=True)


_browser()

print()
if FAILS:
    print(f"{len(FAILS)} FAILED")
    sys.exit(1)
print("all passed")
