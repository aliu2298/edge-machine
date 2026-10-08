#!/usr/bin/env python3
"""Sport navigation, disclosure access, scan honesty, and phone layout regressions."""
import copy
import datetime as dt
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlparse

import crypto_build as crypto
import nba_pace_build as nba
import site_chrome
import soccer_build as soccer
import tennis_build as tennis
from require_browser import require_browser

NOW = dt.datetime(2026, 10, 7, 12, tzinfo=dt.timezone.utc)
ROOT = Path(__file__).parent
ledger = {"quotes": [], "meta": {"updated": "2026-10-07T11:00:00Z"},
          "coverage": {"crypto_fav": {"crypto_fav_band": {"offered": 42, "picked": 0}}}}
original = copy.deepcopy(ledger)
scan = crypto._scan_status(ledger, NOW)
assert "Last scan Oct 7, 6:00 AM CT · 42 quotes · next window Oct 7, 12:30–2:00 PM CT" in scan, scan
assert scan.count("<p") == 1 and 'class="sm mut cr-scan"' in scan
assert "Last scan not recorded" in crypto._scan_status({"quotes": []}, NOW)
assert "quotes" not in crypto._scan_status(
    {"meta": {"updated": "bad"}, "coverage": ledger["coverage"]}, NOW)
for date in (dt.datetime(2026, 11, 1, 12, tzinfo=dt.timezone.utc),
             dt.datetime(2026, 7, 1, 12, tzinfo=dt.timezone.utc)):
    assert "12:30–2:00 PM CT" in crypto._scan_status(ledger, date)
assert "next window Oct 8" in crypto._scan_status(ledger, NOW.replace(hour=23))

game = {"id": "next", "start": "2026-10-07T18:00:00Z", "away": "BKN", "home": "CHA",
        "roll_exp_q1": 56.2, "roll_exp_h1": 114.0, "roll_exp_ft": 221.5}
pages = {"nba": nba.build({"window": 5, "games": [game], "seed": {"teams": {}}}, NOW),
         "crypto": crypto.build(ledger, {"pairs": {}}, NOW),
         "tennis": tennis.build(ledger, {"pairs": {}}, NOW)}
with patch("sport_tab.preflight_report", return_value=({}, '<p class="note">Checked recently.</p>')):
    pages["soccer"] = soccer.build(ledger, {"pairs": {}}, NOW)
with patch("sport_tab.preflight_report", return_value=({}, '<p class="note"><b class="neg">Status is old.</b></p>')):
    warning = soccer.build(ledger, {"pairs": {}}, NOW)
assert ledger == original, "rendering must not mutate stored data"
for sport, html in pages.items():
    assert site_chrome.CSP in html
    assert '<script src="./sports.js"></script>' in html
    assert f'<body class="sports-page sport-{sport}">' in html, sport
    assert html.count('<header class="site">') == 1, sport
    assert '<a class="brand" href="./index.html">Edge Machine</a>' in html, sport
    assert "page-menu" not in html and "sport-row" not in html and '<nav class="sports"' not in html, sport

playwright = require_browser("test_sports_ui.py")
if playwright is not None:
    with playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        for sport, html in pages.items():
            for width in (320, 375, 390, 414, 768, 1280):
                page = browser.new_page(viewport={"width": width, "height": 844})
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                def serve(route):
                    name = Path(urlparse(route.request.url).path).name
                    if name.endswith(".html"):
                        route.fulfill(body=html, content_type="text/html")
                    else:
                        route.fulfill(path=str(ROOT / "public_site" / name))
                page.route("http://fixture.local/**", serve)
                page.goto(f"http://fixture.local/{sport}.html", wait_until="load")
                assert not errors, (sport, width, errors)
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (sport, width)
                # The shared shell hides the stamp on a phone and shows it from 641px.
                assert page.locator(".stamp").count() == 1, (sport, width)
                assert page.locator(".stamp").is_visible() == (width > 640), (sport, width)
                assert page.locator("header.site .brand[href='./index.html']").count() == 1, (sport, width)
                assert page.locator("header.site nav.main [aria-current='page']").count() == 1, (sport, width)
                assert page.locator("[aria-current='page']").count() == 1, (sport, width)
                # Phone pills are 44px touch targets; from 641px the pointer shell is shorter.
                tap = 44 if width <= 640 else 24
                assert page.locator("nav.main [aria-current='page']").evaluate("""(e, tap) => {
                    const r = e.getBoundingClientRect(), n = e.parentElement.getBoundingClientRect();
                    return r.left >= n.left - 1 && r.right <= n.right + 1 && r.height >= tap
                        && r.left >= -1 && r.right <= innerWidth + 1;
                }""", tap), (sport, width)
                assert page.evaluate("""() => [...document.querySelectorAll('body *')].every(e =>
                    !e.checkVisibility() || ![...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())
                    || parseFloat(getComputedStyle(e).fontSize) >= 11)"""), (sport, width)
                assert page.locator(".page-menu").count() == 0 and page.locator("nav.sports").count() == 0
                assert page.locator("nav.main a").count() == len(site_chrome.PAGES)
                assert page.locator("nav.main a").evaluate_all(
                    "(links, tap) => links.every(e => e.getBoundingClientRect().height >= tap)", tap)
                # Every page pill can be brought into view, on a phone by scrolling the row.
                assert page.locator("nav.main a").evaluate_all("""links => links.every(a => {
                    const nav = a.parentElement;
                    a.scrollIntoView({block: "nearest", inline: "nearest"});
                    const r = a.getBoundingClientRect(), n = nav.getBoundingClientRect();
                    return r.left >= n.left - 1 && r.right <= n.right + 1 && r.left >= -1 && r.right <= innerWidth + 1;
                })"""), (sport, width)
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (sport, width, "nav")
                if sport == "nba":
                    # The game row's chevron opens the detail row under it.
                    assert page.locator("tr.nba-detail:not([hidden])").count() == 0
                    page.locator("button.nba-more").first.click()
                    assert page.locator("tr.nba-detail:not([hidden])").count() == 1
                    assert page.locator("tr.nba-detail .nba-side").first.is_visible()
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (sport, width, "analysis")
                    page.locator("a[href='#graded']").click()
                    page.locator(".nba-results[open]").wait_for(state="attached")
                    page.locator("a[href='#teams']").click()
                    page.locator("#teams > details[open]").wait_for(state="attached")
                if sport == "soccer":
                    assert page.locator("#health > details").get_attribute("open") is None
                if sport == "tennis":
                    assert page.locator("#system > details").get_attribute("open") is None
                if sport == "crypto":
                    assert page.locator("#method details[open]").count() == 0
                    assert page.locator(".tn-pick.cr-pick").count() == 5
                    assert page.locator(".crypto-hero, .crypto-progress, .crypto-coin").count() == 0
                page.close()
        page = browser.new_page()
        page.route("http://fixture.local/soccer.html", lambda route: route.fulfill(body=warning, content_type="text/html"))
        page.route("http://fixture.local/*.js", lambda route: route.fulfill(body="", content_type="application/javascript"))
        page.route("http://fixture.local/*.css", lambda route: route.fulfill(body="", content_type="text/css"))
        page.goto("http://fixture.local/soccer.html")
        assert page.locator("#health > details").get_attribute("open") is not None
        assert page.locator("#health details.section-disclosure").get_attribute("open") is None
        browser.close()
print("PASS four sport pages: 320–1280px, readable text, one shell, disclosures, stored scan status")
