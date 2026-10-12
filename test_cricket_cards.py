#!/usr/bin/env python3
"""The Cricket page on the shared sport template: what cricket_cards hands it.

Presentation only. The record, verdict and ROI are the Sandbox row's own
figures, compared as strings. A no-result bet (paid out at a price) is a
count beside the record, never a win or a loss. A pre-reset bet never
reaches the page.
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
import sandbox_track as T
import sport_page as SP

FAILS = []
ROOT = os.path.dirname(os.path.abspath(__file__))
NOW = datetime.datetime(2026, 10, 5, 16, 0, tzinfo=timezone.utc)   # 11:00 AM CT
# The lane's reset clock, and a logged stamp on either side of it.
SINCE = "2026-09-20T00:00:00+00:00"
AFTER = "2026-09-21T00:00:00+00:00"
BEFORE = "2026-09-10T00:00:00+00:00"


def _head_sha():
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
                                       stderr=subprocess.DEVNULL).strip() or "unknown"
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


SHA = _head_sha()


def ok(cond, msg):
    print(f"  {'ok  ' if cond else 'FAIL'} {msg}")
    if not cond:
        FAILS.append(msg)


def eq(got, want, msg):
    ok(got == want, msg if got == want else f"{msg} — got {got!r}, want {want!r}")


def _quote(i, source, sport, status, start, label, price=0.55, bet=True, venue="polymarket_us",
           url="https://polymarket.us/event/x", logged=None, **extra):
    when = start if isinstance(start, datetime.datetime) else NOW + timedelta(hours=start)
    won = status == "won"
    q = dict(
        id=f"{source}:{sport}:{i}:{status}:{label}", source=source, sport=sport, bet=bet, status=status,
        pick="b", price=price, result=("b" if won else "a") if status in ("won", "lost") else None,
        venue=venue, pnl=(round(100 * (1 / price - 1), 2) if won else -100.0) if status in ("won", "lost") else None,
        start=when.isoformat(), logged=logged or (when - timedelta(hours=2)).isoformat(),
        date=when.date().isoformat(), price_a=round(1 - price, 2), price_b=price,
        side_a="Yes", side_b="No", label=label, market_id=f"m-{source}-{i}", url=url)
    q.update(extra)
    return q


def _fixture():
    quotes = []
    # The Production tipster: three settled on the clock, one paid out at 50¢, one before the clock.
    for i in range(3):
        quotes.append(_quote(i, "oddspedia", "cricket", "won" if i < 2 else "lost", NOW - timedelta(days=2, hours=i),
                             f"KeptSettled oddspedia {i}", logged=AFTER))
    quotes.append(_quote(10, "oddspedia", "cricket", "settled", NOW - timedelta(days=1), "Rained Off v Nobody",
                         logged=AFTER, settle_px=0.5, pnl=-16.67, result="price"))
    quotes.append(_quote(11, "oddspedia", "cricket", "won", NOW - timedelta(days=4), "GhostPrereset v Old", logged=BEFORE))
    quotes.append(_quote(20, "oddspedia", "cricket", "open", 3, "Alpha v Beta soonest", logged=AFTER))
    # A stored fixture with no stake is not a pick.
    quotes.append(_quote(40, "oddspedia", "cricket", "open", 12, "Window Side v Keeper", bet=False, logged=AFTER))
    # A hostile label and url.
    quotes.append(_quote(41, "oddspedia", "cricket", "open", 9, 'Rho <script>alert(1)</script> v "Sigma"',
                         url="javascript:alert(1)", logged=AFTER))
    # Other families stay on their own pages.
    quotes.append(_quote(50, "o15_form_l10", "soccer_o15", "open", 3, "Soccer Only v Stay", venue="kalshi"))
    quotes.append(_quote(60, "tennis_fav_band_3h", "tennis", "open", 3, "Tennis Only v Stay", venue="kalshi"))
    d = {"quotes": quotes,
         "coverage": {"cricket": {"polymarket_us": 20, "polymarket_us_listed": 20, "polymarket_us_priced": 15}}}
    st = {"pairs": {"oddspedia|cricket": {"stage": "production", "by_hand": "2026-09-20",
                                          "promoted_at": SINCE, "ready_at": SINCE, "since": SINCE}}}
    return d, st


def _rows(d, st):
    import sport_tab
    return sport_tab.family_rows(d, st, "Cricket")


def _section(markup, name):
    m = re.search(rf'<section id="{name}"[^>]*>(.*?)(?=<section id="|<footer)', markup, re.S)
    return m.group(1) if m else ""


def _picks(markup):
    return re.findall(r'<div class="sp-pick ([^"]*)" data-source="([^"]*)"[^>]*>(.*?)</div>', markup, re.S)


def _shown(label):
    return fmt.contest(label)


def _absent(label, html):
    return label not in html and _shown(label) not in html


def _pick(markup, label):
    """The event row carrying `label`: its time, name and every pick line under it."""
    m = re.search(r'<div class="sp-event[^"]*"[^>]*>(?:(?!sp-event").)*?' + re.escape(_shown(label)) + r'.*?</div></div>', markup, re.S)
    return m.group(0) if m else ""


print(f"SHA {SHA}")

import cricket_build
import cricket_cards as C
import soccer_build
import tennis_build

d, st = _fixture()
# A settled bet older than the list window stays in the record, off the list.
d["quotes"].append(_quote(700, "oddspedia", "cricket", "won", NOW - timedelta(days=20),
                          "Old Side v Window Edge", price=0.50, logged=AFTER))
rows = _rows(d, st)
html = cricket_build.build(d, st, NOW)
main = html.split("<main", 1)[-1].split("</main>", 1)[0]
by_name = {row["name"]: row for row in rows}

print("\nshape")
ok("<h1>Cricket</h1>" in html and "Match-winner picks and the rules that fire them · All times Central" in html,
   "title and the one scope line")
ok(html.count("<h1>") == 1 and html.count('<header class="site">') == 1
   and '<body class="sports-page sport-cricket">' in html,
   "one shell, one title, the cricket sport page")
ok('<a href="#rules">Rules</a><a href="#events">Events</a><a href="#method">Method</a>' in html and 'href="#system"' not in html,
   "the sub-nav pills are Rules · Events · Method")
for gone in ("rule-card", "rule-band", "rule-grid", "rule-flip", "How each rule is defined", "tn-rules", "tn-pick", "tn-tiles",
             "<meter", "<progress", "tempo", "Lanes with a record", "Registered, never fired"):
    ok(gone not in html, f"the page does not print {gone!r}")
ok(html.count('<div class="tile">') == 4, "four stat tiles")
ok(fmt.display_updated(NOW) in html, "the stamp is the page clock")
ok("javascript:" not in html and "&lt;script&gt;" in html, "a hostile label is escaped and a javascript: url is not a link")

print("\ntiles")
tiles = re.findall(r'<div class="tile">(.*?)</div>', main, re.S)
open_n = sum(len(C.open_quotes(d, r["name"], r["sport"], r)) for r in rows)
eq(re.search(r'<b>(\d+)</b><span>open picks', tiles[0]).group(1), str(open_n), "open picks is the open count across every rule")
eq(open_n, 2, "the fixture has two open bets the lanes count")
active = [r for r in rows if r["a"]["n"] or r["a"].get("n_price") or r["open"]]
eq(re.search(r'<b>(\d+)</b><span>active rules', tiles[1]).group(1), str(len(active)),
   "active rules counts rules with a settled or an open bet")
import production
live = production._assess_since_kickoff(d, "oddspedia|cricket", st["pairs"]["oddspedia|cricket"])
ok(f'<b>{live["won"]}–{live["n"] - live["won"]}</b><span>since Production · Oddspedia community tips · {live["n_price"]} no result</span>' in tiles[2],
   "the record tile is the Production rule's since-Production W–L, named, the no-result count in its label")
ok(B.pct(live["roi_fee"], sign=True) in tiles[3] and "ROI after fees · since Production" in tiles[3],
   "the ROI tile is that window's ROI after fees, named")
odds_a = by_name["oddspedia"]["a"]
eq(T.record_text(odds_a), f'{odds_a["won"]}–{odds_a["n"] - odds_a["won"]}, 1 no result',
   "the Production rule's whole record names its one no-result bet beside the W–L")
ok("cricket_consensus" not in "".join(tiles) and "since Production · Oddspedia community tips" in tiles[2],
   "the tiles name the Production rule alone; a Sandbox rule is never pooled in")
ok("GhostPrereset" not in html and odds_a["n_price"] == 1 and odds_a["n"] == 4,
   "pre-reset bets are not in the record and not on the page; the no-result bet is counted apart")

print("\nevents")
events = _section(main, "events")
picks = _picks(events)
ok(len(picks) > 0 and 'class="sp-day-head"' in events and 'class="sp-tabs"' in events, "the events are the template's tabs")
nxt = events.split('id="events-live"', 1)[0]
done = events.split('id="events-done"', 1)[1]
for label in ("Alpha v Beta soonest",):
    ok(_pick(nxt, label) and "upcoming" in _pick(nxt, label), f"open pick on Next 24h: {label}")
ok(_pick(done, "KeptSettled oddspedia 0") and "is-won" in _pick(done, "KeptSettled oddspedia 0"),
   "a settled pick from the last 14 days is on Completed with its result")
ok(_pick(done, "Rained Off v Nobody") and f'<span class="sp-state is-price">{T.NO_RESULT_LABEL}</span>' in _pick(done, "Rained Off v Nobody")
   and "Settled on price" not in html, "a bet the venue paid out at 50¢ reads No result · paid 50¢")
ok(_absent("Old Side v Window Edge", events), "a settled pick older than 14 days is off the list")
rules = _section(main, "rules")
ok(by_name["oddspedia"]["a"]["n"] == 4 and _shown("Old Side v Window Edge") in rules,
   "but it still counts in the record and shows under its rule's recent picks")
ok(_absent("Window Side v Keeper", html), "a stored fixture with no stake is not a pick")
first = _pick(nxt, "Alpha v Beta soonest")
ok('<span class="sp-legs">Polymarket US</span>' in first, "each pick carries its venue")
ok("Oddspedia community tips" in first and 'class="sp-pick-rule"' in first, "and the rule that fired it, muted")
ok('<span class="sp-pos"><a href="https://polymarket.us/event/x"' in first and ">No</a>" in first, "the pick is the side backed, as stored, linked")
ok('<span class="badge stage production">Production</span>' in first, "a Production rule's pick says so")
days = [re.sub("<[^>]+>", "", x) for x in re.findall(r'<h4 class="sp-day-head">(.*?)</h4>', done)]
ok(days == sorted(days, key=lambda s: -datetime.datetime.strptime(s.split("Yesterday")[0].split("Today")[0].strip() + " 2026", "%a %b %d %Y").toordinal()),
   f"completed days run newest first ({days})")
quiet = {"quotes": [q for q in d["quotes"] if q.get("status") != "open"], "coverage": d["coverage"]}
quiet_html = cricket_build.build(quiet, st, NOW)
ok('data-empty="next"' in quiet_html and "No pick starts in the next 24 hours" in quiet_html,
   "with nothing open the Next 24h tab says why")
ok("no read is stored for this sport yet" in quiet_html, "a venue listing alone is not a rule read, so the reason is honest")

print("\nrules")
from sport_rows_testlib import rule_rows, text as row_text
prod_list = rules.split('class="sp-rules-list sp-prod"', 1)[1].split('id="sandbox"', 1)[0]
prows = rule_rows(prod_list)
eq(len(prows), 1, "the Production tipster is one row")
odd = prows[0]
ok(odd["name"] == "Oddspedia community tips" and odd["stage"] == "production", "named, in the Production list")
a = odds_a
c = odd["cells"]
eq(row_text(c["Record"]), f'{a["won"]}–{a["n"] - a["won"]} +1 n/r', "the record is the W–L with the no-result count as a small tail")
ok(c["ROI after fees"] == SP.roi_html(by_name["oddspedia"]), "ROI after fees")
eq(c["Won v priced"], f'{a["won"]} v {a["expected"]:.1f}', "won v priced")
eq(c["Evidence"], f'{a["n"]}/{T.READ_FLOOR}', "evidence n/30")
eq(c["Verdict"], SP.verdict_badge(by_name["oddspedia"]), "the verdict chip is the one vocabulary's")
eq(c["Market"], "Polymarket US", "the market column names where the rule's bets traded")
ok(not odd["open"] and "A public tipster community" in odd["body"], "the registration is in the closed Rule details fold")
ok('<h4 class="sp-details-sub">Recent picks · 2 open</h4>' in odd["body"] and _shown("Alpha v Beta soonest") in odd["body"]
   and _shown("KeptSettled oddspedia 0") in odd["body"] and "GhostPrereset" not in odd["body"],
   "recent picks are in the fold, on the lane clock")
fold = re.search(r'<details class="fold sp-sandbox" id="sandbox"><summary>(.*?)</summary>(.*)', rules, re.S)
ok(fold is not None, "the Sandbox rules are one fold")
srows = rule_rows(fold.group(2)) if fold else []
order = [r["source"] for r in srows]
eq(order, [r["name"] for r in sorted(rows, key=SP.sandbox_order) if not r.get("prod")], "Sandbox rows by evidence, too-early sunk")
con = next((r for r in srows if r["source"] == "cricket_consensus"), None)
ok(con is not None and con["early"] and row_text(con["cells"]["Record"]) == "—" and con["cells"]["Evidence"] == "0/30",
   "a rule that never fired is a too-early row with no record")
ok(con is not None and con["cells"]["Market"] == "—", "and no venue, having no bet to read one from")
head_line = re.search(r'<div class="sp-line sp-head-line" aria-hidden="true">(.*?)</div>', fold.group(2), re.S)
eq(re.findall(r'<span class="sp-cell[^"]*">([^<]*)</span>', head_line.group(1)) if head_line else None,
   ["Rule", "Market", "Record", "ROI after fees", "Won v priced", "Evidence", "Verdict"], "one scope, so no Scope column")

print("\nmethod")
method = _section(main, "method")
ok("Polymarket US listing: 20 taken · 20 listed · 15 priced · no record" in method,
   "the venue listing is one line from the stored counts")
ok("<details><summary>" in method and "<details open" not in method.split("</summary>", 1)[0] and "flat $" in method,
   "folded closed with the venue and grading note")
nocov = cricket_build.build({"quotes": d["quotes"]}, st, NOW)
ok("Polymarket US listing: 0 taken · 0 listed · 0 priced · no record" in nocov,
   "with no stored coverage the counts are zero, not missing")

print("\nempty ledger")
empty = cricket_build.build({"quotes": []}, {"pairs": {}}, NOW)
ok("No cricket rule is in Production." in empty and 'data-empty="next"' in empty and "rule-card" not in empty
   and 'class="sp-pick' not in empty, "an empty ledger says so and draws no pick")
ok("<b>0</b><span>open picks" in empty and "<b>—</b><span>Production record" in empty, "the tiles are zero and dashes")

print("\nsoccer and tennis stay on their own pages")
soc = soccer_build.build(d, st, NOW)
ten = tennis_build.build(d, st, NOW)
ok(_absent("Soccer Only v Stay", html) and _absent("Tennis Only v Stay", html)
   and "tennis_fav_band_3h" not in html and "o15_form_l10" not in html,
   "the cricket page does not pick up soccer or tennis lanes")
ok(_absent("Alpha v Beta soonest", soc) and _absent("Alpha v Beta soonest", ten),
   "the other pages do not pick up cricket picks")

print("\npublished page and stylesheet")
published = open(os.path.join(ROOT, "public_site", "cricket.html"), encoding="utf-8").read()
ok('class="sp-head"' in published and 'class="sp-tabs"' in published, "the published cricket page is the template page")
css = open(os.path.join(ROOT, "public_site", "site.css"), encoding="utf-8").read()
ok(".sp-state.is-price" in css and ".sp-legs" in css, "the no-result state and the venue line are styled")
ok(".tn-venue" not in css and ".tn-day" not in css, "the cricket-only tennis additions are retired with the page")


def browser_checks():
    print("\nbrowser")
    from require_browser import require_browser
    sync_playwright = require_browser("test_cricket_cards.py")
    if sync_playwright is None:
        return
    import tempfile
    import threading
    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
    folder = tempfile.mkdtemp(prefix="cricket-")
    for name in ("site.css", "tables.js", "site.js", "sports.js"):
        os.symlink(os.path.join(ROOT, "public_site", name), os.path.join(folder, name))
    with open(os.path.join(folder, "cricket.html"), "w", encoding="utf-8") as fh:
        fh.write(html)

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=folder, **kwargs)

        def log_message(self, fmt, *args):
            return
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}/cricket.html"
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 800})
            page.goto(base, wait_until="load")
            page.wait_for_timeout(40)
            state = page.evaluate("""() => ({
              overflow: document.documentElement.scrollWidth > innerWidth + 1,
              sticky: getComputedStyle(document.querySelector('.sp-day-head')).position,
              card: getComputedStyle(document.querySelector('details.sp-rule > summary')).display,
              moreOpen: document.querySelector('details.sp-rule').open,
              sandboxOpen: document.querySelector('details.sp-sandbox').open,
              methodOpen: document.querySelector('#method details').open,
            })""")
            ok(not state["overflow"] and state["sticky"] == "sticky" and state["card"] == "grid",
               "at 1280px the list has sticky day heads, the Production rule is one row, nothing scrolls sideways")
            ok(not state["moreOpen"] and not state["sandboxOpen"] and not state["methodOpen"],
               "the Rule details fold, the Sandbox fold and the method start closed")
            page.locator("details.sp-sandbox > summary").click()
            page.wait_for_timeout(40)
            ok(page.locator('details.sp-rule[data-source="cricket_consensus"]').is_visible(), "the Sandbox fold shows the never-fired rule")
            page.locator('[data-list="sandbox"] details.sp-rule > summary').first.click()
            page.wait_for_timeout(40)
            ok(page.locator(".sp-details-body:visible").count() == 1, "a row opens its Rule details")
            page.set_viewport_size({"width": 390, "height": 800})
            page.reload(wait_until="load")
            page.wait_for_timeout(40)
            narrow = page.evaluate("""() => ({
              overflow: document.documentElement.scrollWidth > innerWidth + 1,
              areas: getComputedStyle(document.querySelector('.sp-pick')).gridTemplateAreas,
            })""")
            ok(not narrow["overflow"] and "pos" in narrow["areas"],
               f"at 390px the picks stack and nothing scrolls sideways (overflow {narrow['overflow']})")
            browser.close()
    finally:
        httpd.shutdown()


browser_checks()

print()
if FAILS:
    print(f"{len(FAILS)} FAILED")
    sys.exit(1)
print(f"\nSHA {SHA} PASSED")
