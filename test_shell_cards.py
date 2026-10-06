#!/usr/bin/env python3
"""SofaScore shell slice 3: Rules-applied cards, and the slice-2 follow-ups.

Fails while a selected contest has no card payload, a multi-bet row shows
only the first price, an unknown status reads Void, or an ungraded bet past
the await window still says Open. Passes once each bet is a mini card
(Production before Sandbox), prices list in cents, and the follow-ups hold.
No network. Browser checks need REQUIRE_BROWSER=1.
"""
import datetime
import html as html_lib
import json
import os
import re
import shutil
import sys
import tempfile
import threading
from datetime import timedelta, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import sandbox_build
import shell_build

FAILS = []
ROOT = os.path.dirname(os.path.abspath(__file__))
NOW = datetime.datetime(2026, 10, 5, 18, 0, tzinfo=timezone.utc)


def ok(cond, why):
    print(f"  {'ok  ' if cond else 'FAIL'} {why}")
    if not cond:
        FAILS.append(why)


def eq(got, want, why):
    ok(got == want, why if got == want else f"{why} — got {got!r}, want {want!r}")


def _lead(lid, home, away, kickoff, status, pair, sport, price, **extra):
    row = {
        "id": lid,
        "home": home,
        "away": away,
        "match": f"{home} v {away}",
        "headline": extra.pop("headline", f"{home} to win"),
        "kickoff": kickoff,
        "status": status,
        "pair": pair,
        "sport": sport,
        "lane": extra.pop("lane", "production"),
        "price_at_log": price,
        "league": extra.pop("league", "League"),
        "source": extra.pop("source", pair.split("|", 1)[0]),
        "sandbox_quote": lid,
    }
    row.update(extra)
    return row


def _blob(leads):
    return {"leads": {lead["id"]: lead for lead in leads}, "pairs": {}}


def _rows(page):
    return re.findall(r'<button\b[^>]*class="running-row"[^>]*>.*?</button>', page, re.S)


def _attr(tag, name):
    match = re.search(rf'\b{name}="([^"]*)"', tag)
    return html_lib.unescape(match.group(1)) if match else None


def _contests(leads, now=NOW, d=None, st=None):
    blob = _blob(leads)
    empty = {"quotes": []}
    stages = {"pairs": {}}
    lanes = shell_build.collect_lanes(d or empty, st or stages, blob, now)
    return shell_build.contests_from_lanes(lanes, now, d=d or empty, st=st or stages)


def _cards(row):
    raw = _attr(row, "data-cards")
    if not raw:
        return None
    return json.loads(raw)


print("unknown status is not Void")
eq(shell_build._status_label("void"), "Void", "a real void is still Void")
eq(shell_build._status_label("held"), "held", "an unknown status stays the raw status")
eq(shell_build._status_label(None), "Unknown", "a missing status is Unknown")
ok(shell_build._status_label("held") != "Void", "an unknown status is never Void")
ok(shell_build._status_label("bogus") != "Void", "another unknown status is never Void")
held = _contests([
    _lead("held", "Held", "Match", "2026-10-04T15:00:00Z", "held",
          "oddspedia|cricket", "cricket", 0.30),
])
eq(held[0]["status"], "held", "the row shows the raw status, not Void")
eq(held[0]["cards"][0]["status"], "held", "the card shows the raw status, not Void")
held_page = shell_build.page(NOW, d={"quotes": []}, st={"pairs": {}}, blob=_blob([
    _lead("held", "Held", "Match", "2026-10-04T15:00:00Z", "held",
          "oddspedia|cricket", "cricket", 0.30),
]))
held_row = _rows(held_page)[0]
ok(">held</span>" in held_row and ">Void</span>" not in held_row,
   "rendered unknown status is the escaped raw word")


print("\nungraded bets past six hours")
def _one(kickoff, now=NOW):
    return _contests([
        _lead("x", "Home", "Away", kickoff, "pending", "oddspedia|cricket", "cricket", 0.50),
    ], now=now)[0]


at_kick = _one("2026-10-05T18:00:00Z")
eq(at_kick["bucket"], "live", "kickoff equal to now is Live")
eq(at_kick["status"], "Open", "kickoff equal to now is not awaiting")
ok(not at_kick["awaiting"], "the equal-now contest is not awaiting")
just_before = _one("2026-10-05T18:00:01Z")
eq(just_before["bucket"], "upcoming", "the instant before kickoff is Upcoming")
eq(just_before["status"], "Open", "an upcoming bet stays Open")
just_after = _one("2026-10-05T17:59:59Z")
eq(just_after["bucket"], "live", "one second after kickoff is Live")
eq(just_after["status"], "Open", "one second after kickoff is not yet awaiting")
at_six = _one("2026-10-05T12:00:00Z")
eq(at_six["bucket"], "live", "exactly six hours after kickoff stays Live")
eq(at_six["status"], "Open", "the six-hour boundary is still Open")
ok(not at_six["awaiting"], "exactly six hours is not past the window")
past_six = _one("2026-10-05T11:59:59Z")
eq(past_six["bucket"], "live", "past six hours stays in the Live bucket")
eq(past_six["status"], "Awaiting result", "past six hours and ungraded says Awaiting result")
eq(past_six["spoken"], "awaiting result", "awaiting is spoken as awaiting result")
ok(past_six["awaiting"], "the contest is marked awaiting")
past_page = shell_build.page(NOW, d={"quotes": []}, st={"pairs": {}}, blob=_blob([
    _lead("late", "Late", "Grade", "2026-10-05T11:59:59Z", "pending",
          "oddspedia|cricket", "cricket", 0.50),
    _lead("on", "On", "Time", "2026-10-05T12:00:00Z", "pending",
          "oddspedia|cricket", "cricket", 0.51),
]))
late_row = next(row for row in _rows(past_page) if _attr(row, "data-name") == "Late v Grade")
on_row = next(row for row in _rows(past_page) if _attr(row, "data-name") == "On v Time")
ok('data-awaiting="true"' in late_row and ">Awaiting result</span>" in late_row,
   "the stuck row renders Awaiting result")
eq(_attr(late_row, "data-filter"), "live", "Awaiting result stays in Live")
ok('data-awaiting="true"' not in on_row and ">Open</span>" in on_row,
   "the six-hour boundary row stays Open")
saved_await = shell_build.SHELL_AWAIT_HOURS
try:
    shell_build.SHELL_AWAIT_HOURS = 1
    moved = _one("2026-10-05T16:00:00Z")
    eq(moved["status"], "Awaiting result",
       "SHELL_AWAIT_HOURS is read on each call")
finally:
    shell_build.SHELL_AWAIT_HOURS = saved_await
eq(_one("2026-10-05T16:00:00Z")["status"], "Open",
   "restoring SHELL_AWAIT_HOURS restores the six-hour window")


print("\ncards, prices, and sport pages")
hostile_lane = "<svg/onload=alert(1)>"
hostile_market = '<img src=x onerror=alert(1)>'
mix = [
    _lead("sand", "Mix", "Match", "2026-10-04T15:00:00Z", "hit",
          "aaa|soccer", "soccer", 0.40, lane="sandbox", headline="Draw",
          source="aaa", venue="kalshi"),
    _lead("prod", "Mix", "Match", "2026-10-04T15:00:00Z", "miss",
          "zzz|soccer", "soccer", 0.67, headline=hostile_market,
          source=hostile_lane, edge_at_log=0.042,
          route={"venue": "polymarket_us"}),
]
found = _contests(mix)
eq(len(found), 1, "a production bet and a sandbox bet stay one contest")
eq(len(found[0]["cards"]), len(found[0]["bets"]),
   "one card per bet")
eq([card["pill"] for card in found[0]["cards"]], ["PRODUCTION", "Sandbox"],
   "Production cards come before Sandbox cards")
eq(found[0]["price_text"], "67¢ / 40¢",
   "the row price lists each bet, production price first")
eq(found[0]["page"], "./soccer.html", "a soccer contest links to soccer.html")
prod_card, sand_card = found[0]["cards"]
eq(prod_card["lane"], hostile_lane, "the card keeps the hostile lane name")
eq(prod_card["market"], hostile_market, "the card keeps the hostile market")
eq(prod_card["venue"], "Polymarket US", "the venue badge uses the source label")
eq(prod_card["price"], "67¢", "the card price is cents")
eq(prod_card["edge"], "+4.2%", "a stored edge is shown in the board's percent format")
eq(sand_card["venue"], "Kalshi", "Kalshi uses the board's venue label")
eq(sand_card["market"], "Draw", "the sandbox card keeps its market")
ok("edge" not in sand_card, "a card with no stored edge omits edge")
group, assessed, *_rest = sandbox_build.pair_status(
    {"quotes": []}, {"pairs": {}}, "zzz", "soccer")
want_verdict = sandbox_build.VERDICTS[
    sandbox_build.verdict(assessed) if group is not None else "nobets"][0]
eq(prod_card["verdict"], want_verdict, "the verdict is the sport page's helper")
ok("roi" not in prod_card and "record" not in prod_card,
   "an empty sample omits ROI and record")
plain = _contests([
    _lead("c", "Home", "Away", "2026-10-06T15:00:00Z", "pending",
          "oddspedia|cricket", "cricket", 0.50),
])
eq(plain[0]["page"], "./cricket.html", "a cricket contest links to cricket.html")
ok("edge" not in plain[0]["cards"][0], "a null edge is omitted")
mma = _contests([
    _lead("m", "A", "B", "2026-10-06T15:00:00Z", "pending", "x|mma", "mma", 0.50),
])
eq(mma[0]["page"], "./production.html", "a sport without a page links to production.html")
crypto = _contests([
    _lead("k", "Coin", "Band", "2026-10-06T15:00:00Z", "pending",
          "spot|crypto", "crypto", 0.55),
])
eq(crypto[0]["page"], "./crypto.html", "crypto links to crypto.html")

page = shell_build.page(NOW, d={"quotes": []}, st={"pairs": {}}, blob=_blob(mix))
rows = _rows(page)
eq(len(rows), 1, "the mixed contest is one Running row")
eq(_attr(rows[0], "data-price"), "67¢ / 40¢", "the row attribute lists both prices")
eq(_attr(rows[0], "data-page"), "./soccer.html", "the row carries the sport page")
parsed = _cards(rows[0])
eq([card["pill"] for card in parsed], ["PRODUCTION", "Sandbox"],
   "the embedded payload keeps Production before Sandbox")
eq(parsed[0]["lane"], hostile_lane, "the embedded lane name survives escaping")
eq(parsed[0]["market"], hostile_market, "the embedded market survives escaping")
ok('class="rule-mini"' not in page, "cards are not painted until a row is selected")
ok("Select a contest in Running." in page, "the detail pane starts empty")
ok(hostile_market not in page and "&lt;img src=x onerror=alert(1)&gt;" in page,
   "the hostile market is escaped")
ok(hostile_lane not in page and "&lt;svg/onload=alert(1)&gt;" in page,
   "the hostile lane name is escaped")
ok('href="javascript:' not in page and 'href="data:' not in page,
   "card text does not become a javascript or data link")
ok(re.search(r">\s*History\s*<", page, re.I) is None, "there is no History tab")
ok('href="./production.html"' in page and "Full page" in page,
   "Full page still starts on the Production board")


print("\nlive helpers, not a new formula")
import sandbox_track as T
live_d, live_st = T.load(), T.load_stages()
live_pair = "oddspedia|cricket"
live = _contests([
    _lead("live", "Home", "Away", "2026-10-04T15:00:00Z", "hit",
          live_pair, "cricket", 0.37, headline="Home to win",
          route={"venue": "kalshi"}),
], d=live_d, st=live_st)
live_group, live_a, *_rest = sandbox_build.pair_status(live_d, live_st, "oddspedia", "cricket")
live_key = sandbox_build.verdict(live_a) if live_group is not None else "nobets"
live_card = live[0]["cards"][0]
eq(live_card["verdict"], sandbox_build.VERDICTS[live_key][0],
   "the live card verdict is pair_status plus verdict()")
if live_a.get("n"):
    eq(live_card.get("roi"), sandbox_build.pct(live_a.get("roi_fee"), sign=True),
       "ROI after fees is sandbox_build.pct of the assessed roi_fee")
    eq(live_card.get("record"), f"{live_a['won']}\u2013{live_a['n'] - live_a['won']}",
       "the record is the assessed won-lost line")
else:
    ok("roi" not in live_card and "record" not in live_card,
       "a live pair with no sample omits ROI and record")
eq(live_card["lane"], "Oddspedia community tips",
   "the lane name is the source label the board prints")
eq(live_card["venue"], "Kalshi", "the live card's venue badge is Kalshi")


print("\nshell text is at least 11px")
css = open(os.path.join(ROOT, "public_site", "site.css"), encoding="utf-8").read()
shell_at = css.find("/* SofaScore shell.")
ok(shell_at >= 0, "site.css marks the shell block")
shell_css = css[shell_at:]
declared = re.findall(r"font-size:\s*([0-9.]+)(px|rem|em)\b", shell_css)
ok(declared, "the shell block declares font sizes")
small = []
for number, unit in declared:
    px = float(number) if unit == "px" else float(number) * 15
    if px < 11:
        small.append(f"{number}{unit}")
eq(small, [], "no shell font-size is below 11px")
js = open(os.path.join(ROOT, "public_site", "shell.js"), encoding="utf-8").read()
for needle in ("innerHTML", "insertAdjacentHTML", "outerHTML", "document.write", "eval("):
    ok(needle not in js, f"shell.js does not use {needle}")
ok("textContent" in js, "shell.js writes card text with textContent")


def _browser():
    from require_browser import require_browser
    sync_playwright = require_browser("test_shell_cards.py")
    if sync_playwright is None:
        return
    site = tempfile.mkdtemp(prefix="shell-cards-")
    try:
        browser_html = shell_build.page(NOW, d={"quotes": []}, st={"pairs": {}}, blob=_blob(mix + [
            _lead("late", "Late", "Grade", "2026-10-05T11:59:59Z", "pending",
                  "oddspedia|cricket", "cricket", 0.50),
            _lead("on", "On", "Time", "2026-10-05T12:00:00Z", "pending",
                  "oddspedia|cricket", "cricket", 0.51),
        ]))
        open(os.path.join(site, "index.html"), "w", encoding="utf-8").write(browser_html)
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
                view = browser.new_page(viewport={"width": 1280, "height": 800})
                view.goto(base, wait_until="load")
                colors = view.evaluate("""() => {
                  const awaiting = document.querySelector('.running-row[data-awaiting="true"] .running-status');
                  const open = document.querySelector('.running-row:not([data-awaiting="true"]) .running-status');
                  if (!awaiting || !open) return null;
                  const a = getComputedStyle(awaiting);
                  const b = getComputedStyle(open);
                  return { awaiting: a.color, open: b.color, italic: a.fontStyle };
                }""")
                ok(colors and colors["awaiting"] != colors["open"] and colors["italic"] == "italic",
                   f"Awaiting result is styled apart from an open Live row ({colors})")
                view.click('.running-filters button[data-filter="settled"]')
                view.wait_for_timeout(30)
                row = view.locator(".running-row:not([hidden])")
                row.focus()
                view.keyboard.press("Enter")
                shown = view.evaluate("""() => {
                  const cards = [...document.querySelectorAll(".rule-mini")];
                  const section = document.getElementById("rules-section");
                  const line = document.getElementById("rules-line");
                  const empty = document.getElementById("rules-empty");
                  const link = document.querySelector("a.full-page");
                  const host = document.getElementById("rules-cards");
                  return {
                    n: cards.length,
                    pills: cards.map((card) => {
                      const pill = card.querySelector(".lane-pill");
                      return pill ? pill.textContent : "";
                    }),
                    text: host ? host.textContent : "",
                    imgs: host ? host.querySelectorAll("img, svg, script").length : -1,
                    section: section ? section.textContent : "",
                    line: line ? line.textContent : "",
                    emptyHidden: empty ? empty.hidden : null,
                    href: link ? link.getAttribute("href") : "",
                    html: host ? host.innerHTML : "",
                  };
                }""")
                ok(shown["n"] == 2, f"keyboard selection renders one card per bet ({shown['n']})")
                eq(shown["pills"], ["PRODUCTION", "Sandbox"],
                   "rendered cards keep Production before Sandbox")
                ok(shown["section"] == "Rules applied · 2 lanes fired",
                   f"the section counts the lanes ({shown['section']!r})")
                ok("67¢ / 40¢" in shown["line"],
                   f"the header lists both prices ({shown['line']!r})")
                ok(hostile_lane in shown["text"] and hostile_market in shown["text"],
                   "hostile lane and market names render as text")
                eq(shown["imgs"], 0, "hostile names do not become elements")
                ok("<img" not in shown["html"] and "<svg" not in shown["html"]
                   and "<script" not in shown["html"],
                   "the card host has no injected tags")
                ok(shown["emptyHidden"], "the empty state hides once cards show")
                eq(shown["href"], "./soccer.html", "Full page follows the contest's sport page")
                sizes = view.evaluate("""() => {
                  const nodes = [...document.querySelectorAll("header.site *, main *")];
                  const small = [];
                  for (const el of nodes) {
                    if (el.closest(".sr-only")) continue;
                    const size = parseFloat(getComputedStyle(el).fontSize);
                    if (size < 11) small.push((el.className || el.tagName) + " " + size);
                  }
                  return small;
                }""")
                eq(sizes, [], "computed shell text, including the cards, is at least 11px")
                loaded = view.evaluate("""async () => {
                  const res = await fetch("./shell.js");
                  return await res.text();
                }""")
                ok("innerHTML" not in loaded and "insertAdjacentHTML" not in loaded,
                   "the shell.js the page loaded does not use innerHTML")
                view.click('.running-filters button[data-filter="upcoming"]')
                view.wait_for_timeout(30)
                cleared = view.evaluate("""() => {
                  const empty = document.getElementById("rules-empty");
                  const link = document.querySelector("a.full-page");
                  return {
                    cards: document.querySelectorAll(".rule-mini").length,
                    empty: empty ? empty.textContent : "",
                    emptyHidden: empty ? empty.hidden : null,
                    href: link ? link.getAttribute("href") : "",
                  };
                }""")
                eq(cleared["cards"], 0, "hiding the selected row clears the cards")
                eq(cleared["empty"], "Select a contest in Running.",
                   "hiding the selected row restores the empty state")
                ok(not cleared["emptyHidden"], "the empty state is visible again")
                eq(cleared["href"], "./production.html",
                   "Full page returns to the Production board")
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
