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
    match = re.search(r'<nav class="sports"[^>]*>.*?</nav>', page, re.S)
    return match.group(0) if match else ""


print("pill markup")
sports = _sports_nav(PAGE)
ok(sports, "the shell has sport pills")
eq(re.findall(r">([^<]+)</button>", sports),
   ["All", "NBA", "Soccer", "Tennis", "Cricket", "Crypto"],
   "the pills are All, NBA, Soccer, Tennis, Cricket, and Crypto")
ok("<a " not in sports, "sport pills do not navigate")
ok('data-sport="crypto"' in sports and "trading.html" not in sports,
   "Crypto is a sport pill, not the Trading page")
ok('aria-disabled' not in sports and 'tabindex="-1"' not in sports,
   "sport pills are enabled and in the tab order")
eq(sports.count('aria-pressed="true"'), 1, "exactly one sport pill starts pressed")
ok('data-sport="all" aria-pressed="true"' in sports, "All starts pressed")
eq(sports.count('aria-pressed="false"'), 5, "the other five pills start unpressed")
ok('id="sports-soon"' not in PAGE and ">Coming soon</p>" not in PAGE
   and 'aria-describedby="sports-soon"' not in PAGE,
   "the Coming soon note is gone")
eq(_attr(BY_NAME["Alpha v Beta"], "data-sport"), "Soccer", "a soccer row keeps its sport")
eq(_attr(BY_NAME["Crease v Wicket"], "data-sport"), "Cricket", "a cricket row keeps its sport")
eq(_attr(BY_NAME["Lakers v Celtics"], "data-sport"), "NBA", "an NBA row keeps its sport")
eq(_attr(BY_NAME["Coin v Token"], "data-sport"), "Crypto", "a crypto row keeps its sport")
eq(_attr(BY_NAME["Curl v Stone"], "data-sport"), "curling",
   "an unknown sport stays the row's own sport")
eq(_attr(BY_NAME["Market v Quote"], "data-sport"), "Markets",
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
            counts[row["filter"]] += 1
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
        want = {"live": "No live paper bets", "settled": "No settled paper bets",
                "upcoming": "No upcoming paper bets"}[snap["tab"]]
        ok(not snap["emptyHidden"] and snap["emptyText"] == want,
           f"{why}: an empty tab uses the existing empty line ({snap['emptyText']!r})")
    ok(not snap["disabled"] and not snap["soon"],
       f"{why}: pills stay enabled, with no Coming soon note")


SNAP = """() => {
  const buttons = [...document.querySelectorAll("nav.sports button")];
  const pressed = buttons.filter((b) => b.getAttribute("aria-pressed") === "true");
  const tabBtn = document.querySelector(".running-filters button[aria-pressed='true']");
  const rows = [...document.querySelectorAll(".running-row")].map((row) => ({
    name: row.getAttribute("data-name"),
    sport: row.getAttribute("data-sport"),
    filter: row.getAttribute("data-filter"),
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
    hash: location.hash,
  };
}"""


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
                ok(any(row["name"] == "Curl v Stone" and not row["hidden"]
                       for row in initial["rows"]),
                   "an unknown sport is visible under All")
                ok(any(row["name"] == "Market v Quote" and not row["hidden"]
                       for row in initial["rows"]),
                   "a Markets row is visible under All")
                eq(initial["selected"], [], "nothing is selected on load")
                ok(not initial["detailHidden"]
                   and initial["detailText"] == "Select a contest in Running.",
                   "the detail pane starts empty")

                page.click('nav.sports button[data-sport="soccer"]')
                soccer = page.evaluate(SNAP)
                _check_filter(soccer, "Soccer on Live")
                eq(soccer["pressed"], ["soccer"], "Soccer is the only pressed pill")
                eq(soccer["selected"], [],
                   "choosing a sport does not select a row when nothing was selected")
                ok(not soccer["detailHidden"]
                   and soccer["detailText"] == "Select a contest in Running."
                   and soccer["cards"] == 0,
                   "the detail pane stays empty until a row is chosen")
                ok(all(row["name"] != "Curl v Stone" or row["hidden"] for row in soccer["rows"]),
                   "an unknown sport is hidden under Soccer")
                ok(all(row["name"] != "Market v Quote" or row["hidden"] for row in soccer["rows"]),
                   "a Markets row is hidden under Soccer")
                page.click('nav.sports button[data-sport="soccer"]')
                again = page.evaluate(SNAP)
                eq(again["pressed"], ["soccer"], "pressing Soccer again leaves it pressed")
                _check_filter(again, "Soccer pressed again")

                page.click('.running-filters button[data-filter="settled"]')
                settled = page.evaluate(SNAP)
                _check_filter(settled, "Soccer on Settled")
                eq(settled["pressed"], ["soccer"], "the sport pill stays put across tabs")
                eq(settled["ui"], soccer["ui"], "changing tabs does not change the filtered counts")
                eq([row["name"] for row in settled["rows"] if not row["hidden"]],
                   ["Past v Score"], "Settled under Soccer is the soccer result")
                page.click('.running-filters button[data-filter="upcoming"]')
                upcoming = page.evaluate(SNAP)
                _check_filter(upcoming, "Soccer on Upcoming")
                eq(upcoming["pressed"], ["soccer"], "Upcoming keeps the Soccer pill")
                eq([row["name"] for row in upcoming["rows"] if not row["hidden"]],
                   ["Later v Side"], "Upcoming under Soccer is the soccer fixture")
                page.click('.running-filters button[data-filter="live"]')
                live = page.evaluate(SNAP)
                _check_filter(live, "Soccer back on Live")
                eq([row["name"] for row in live["rows"] if not row["hidden"]],
                   ["Alpha v Beta", "Gamma v Delta"], "Live under Soccer is the two soccer rows")

                page.click('nav.sports button[data-sport="all"]')
                restored = page.evaluate(SNAP)
                _check_filter(restored, "All restores Live")
                eq(restored["pressed"], ["all"], "All is pressed again")
                eq(restored["ui"], initial["ui"], "All restores every tab count")
                eq([row["name"] for row in restored["rows"] if not row["hidden"]],
                   [row["name"] for row in initial["rows"] if not row["hidden"]],
                   "All shows the same Live rows as the first load")

                page.click('nav.sports button[data-sport="tennis"]')
                empty = page.evaluate(SNAP)
                _check_filter(empty, "Tennis has no live rows")
                eq(empty["pressed"], ["tennis"], "Tennis is the only pressed pill")
                eq(empty["ui"], {"live": 0, "settled": 0, "upcoming": 0},
                   "a sport with no rows zeros every tab")
                eq(empty["emptyText"], "No live paper bets",
                   "a sport with no live rows uses the live empty line")
                page.click('.running-filters button[data-filter="settled"]')
                empty_settled = page.evaluate(SNAP)
                _check_filter(empty_settled, "Tennis has no settled rows")
                eq(empty_settled["emptyText"], "No settled paper bets",
                   "the empty line follows the tab")
                page.click('.running-filters button[data-filter="live"]')

                page.click('nav.sports button[data-sport="all"]')
                page.locator('.running-row[data-name="Bowl v Bat"]').click()
                page.click('nav.sports button[data-sport="soccer"]')
                moved = page.evaluate(SNAP)
                _check_filter(moved, "Soccer after a cricket selection")
                eq(moved["selected"], ["Alpha v Beta"],
                   "a filtered-out contest moves selection to the first visible row")
                ok("Alpha v Beta" in moved["line"] and not moved["headHidden"]
                   and moved["detailHidden"] and moved["cards"] >= 1,
                   f"the detail pane follows that first visible row ({moved['line']!r})")
                page.click('nav.sports button[data-sport="cricket"]')
                moved_back = page.evaluate(SNAP)
                _check_filter(moved_back, "Cricket after a soccer selection")
                eq(moved_back["selected"], ["Crease v Wicket"],
                   "leaving Soccer selects the first visible cricket row")
                ok("Crease v Wicket" in moved_back["line"],
                   "the detail pane names the cricket row")

                page.click('nav.sports button[data-sport="tennis"]')
                cleared = page.evaluate(SNAP)
                _check_filter(cleared, "Tennis clears a hidden selection")
                eq(cleared["selected"], [], "no visible row clears the selection")
                eq(cleared["cards"], 0, "clearing the selection removes the cards")
                eq(cleared["line"], "", "clearing the selection clears the detail header")
                ok(cleared["headHidden"] and not cleared["detailHidden"]
                   and cleared["detailText"] == "Select a contest in Running.",
                   "the detail pane returns to its empty state")

                page.click('nav.sports button[data-sport="crypto"]')
                crypto = page.evaluate(SNAP)
                _check_filter(crypto, "Crypto on Live")
                eq(crypto["pressed"], ["crypto"], "Crypto is the only pressed pill")
                eq(page.url, base, "the Crypto pill does not navigate")
                ok(all(row["hidden"] or row["sport"] == "Crypto" for row in crypto["rows"]),
                   "Crypto shows only rows whose sport is Crypto")
                ok(all(row["name"] != "Market v Quote" or row["hidden"] for row in crypto["rows"]),
                   "a Markets row stays hidden under the Crypto pill")
                page.click('.running-filters button[data-filter="upcoming"]')
                crypto_up = page.evaluate(SNAP)
                _check_filter(crypto_up, "Crypto on Upcoming")
                eq([row["name"] for row in crypto_up["rows"] if not row["hidden"]],
                   ["Coin v Token"], "Upcoming under Crypto is the crypto contest")
                ok(all(row["name"] != "Market v Quote" or row["hidden"]
                       for row in crypto_up["rows"]),
                   "Markets is still not a Crypto row on Upcoming")

                page.click('.running-filters button[data-filter="live"]')
                page.click('nav.sports button[data-sport="soccer"]')
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
                own = by_chip["Alpha v Beta"]
                other = by_chip["Crease v Wicket"]
                unknown = by_chip["Curl v Stone"]
                market = by_chip["Market v Quote"]
                coin = by_chip["Coin v Token"]
                ok(own["dimmed"] is None and own["opacity"] == 1 and own["note"] == "",
                   f"a chip for the selected sport stays bright ({own})")
                ok(other["dimmed"] == "true" and 0.5 < other["opacity"] < 0.9
                   and other["note"] == "other sport" and other["events"] != "none"
                   and "Crease v Wicket" in other["name"],
                   f"another sport's chip is dimmed, readable, and labeled ({other})")
                ok(unknown["dimmed"] == "true" and unknown["note"] == "other sport",
                   f"an unknown sport's chip is dimmed too ({unknown})")
                ok(market["dimmed"] == "true" and coin["dimmed"] == "true",
                   "Markets and Crypto chips dim while Soccer is pressed")
                page.locator(".bet-chip").filter(has_text="Crease v Wicket").click()
                from_chip = page.evaluate(SNAP)
                _check_filter(from_chip, "a dimmed cricket chip")
                eq(from_chip["pressed"], ["cricket"],
                   "a dimmed chip presses that contest's sport pill")
                eq(from_chip["tab"], "live", "a live chip stays on Live")
                eq(from_chip["selected"], ["Crease v Wicket"],
                   "the dimmed chip selects its contest")
                ok(all(not row["hidden"] for row in from_chip["rows"]
                       if row["name"] == "Crease v Wicket"),
                   "the chip's row is visible")

                page.click('nav.sports button[data-sport="soccer"]')
                page.locator(".bet-chip").filter(has_text="Curl v Stone").focus()
                page.keyboard.press("Enter")
                from_unknown = page.evaluate(SNAP)
                _check_filter(from_unknown, "a dimmed unknown chip")
                eq(from_unknown["pressed"], ["all"],
                   "a chip whose sport has no pill presses All")
                eq(from_unknown["selected"], ["Curl v Stone"],
                   "that chip selects the unknown-sport contest")
                ok(any(not row["hidden"] and row["name"] == "Curl v Stone"
                       for row in from_unknown["rows"]),
                   "the unknown-sport row is visible under All")

                page.click('nav.sports button[data-sport="soccer"]')
                page.locator(".bet-chip").filter(has_text="Coin v Token").click()
                from_coin = page.evaluate(SNAP)
                _check_filter(from_coin, "a dimmed crypto chip")
                eq(from_coin["pressed"], ["crypto"],
                   "a dimmed crypto chip presses Crypto, not Trading")
                eq(from_coin["tab"], "upcoming",
                   "the chip switches to the bucket that holds its contest")
                eq(from_coin["selected"], ["Coin v Token"],
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
                page.click('nav.sports button[data-sport="cricket"]')
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
                page.click('nav.sports button[data-sport="nba"]')
                hashed_click = page.evaluate(SNAP)
                eq(hashed_click["pressed"], ["nba"], "NBA can still be pressed while a hash is present")
                eq(hashed_click["hash"], "#soccer", "pressing NBA does not write the hash")
                _check_filter(hashed_click, "NBA while a hash is present")
                ok(all(row["name"] != "Curl v Stone" or row["hidden"]
                       for row in hashed_click["rows"]),
                   "the unknown sport stays hidden under NBA")

                page.goto(base, wait_until="load")
                page.locator("a.brand").focus()
                for _ in range(4):
                    page.keyboard.press("Tab")
                page_ring = page.evaluate("""() => {
                  const el = document.activeElement;
                  const style = getComputedStyle(el);
                  return { outline: style.outlineStyle, width: style.outlineWidth, tag: el.tagName };
                }""")
                page.keyboard.press("Tab")
                sport_ring = page.evaluate("""() => {
                  const el = document.activeElement;
                  const style = getComputedStyle(el);
                  return {
                    sport: el.getAttribute("data-sport"),
                    tag: el.tagName,
                    outline: style.outlineStyle,
                    width: style.outlineWidth,
                  };
                }""")
                ok(sport_ring["sport"] == "all" and sport_ring["tag"] == "BUTTON"
                   and sport_ring["outline"] == "solid" and sport_ring["width"] == "3px"
                   and sport_ring["outline"] == page_ring["outline"]
                   and sport_ring["width"] == page_ring["width"],
                   f"a sport pill takes Tab focus and the same ring as a page pill "
                   f"({sport_ring}, page {page_ring})")
                page.keyboard.press("Tab")
                page.keyboard.press("Enter")
                entered = page.evaluate(SNAP)
                _check_filter(entered, "Enter on NBA")
                eq(entered["pressed"], ["nba"], "Enter presses the focused pill")
                eq(entered["emptyText"], "No live paper bets",
                   "Enter on a sport with no live rows shows the empty line")
                page.keyboard.press("Tab")
                page.keyboard.press("Space")
                spaced = page.evaluate(SNAP)
                _check_filter(spaced, "Space on Soccer")
                eq(spaced["pressed"], ["soccer"], "Space presses the focused pill")
                eq([row["name"] for row in spaced["rows"] if not row["hidden"]],
                   ["Alpha v Beta", "Gamma v Delta"],
                   "Space filters the list to that sport")

                crypto_url = page.url
                page.click('nav.sports button[data-sport="crypto"]')
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
                    sports: document.querySelectorAll("nav.sports button").length,
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
