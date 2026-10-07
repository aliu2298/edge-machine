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
assert "42 quotes · 0 picks" in scan and "Last tracker scan" in scan
assert "Oct 7, 12:30 PM–2:00 PM CT" in scan
assert "Coin-specific scan times unavailable" in scan
assert "Not recorded" in crypto._scan_status({"quotes": []}, NOW)
assert "Coverage recorded" not in crypto._scan_status(
    {"meta": {"updated": "bad"}, "coverage": ledger["coverage"]}, NOW)
for date in (dt.datetime(2026, 11, 1, 12, tzinfo=dt.timezone.utc),
             dt.datetime(2026, 7, 1, 12, tzinfo=dt.timezone.utc)):
    assert "12:30 PM–2:00 PM CT" in crypto._scan_status(ledger, date)
assert "Oct 8" in crypto._scan_status(ledger, NOW.replace(hour=23))

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
for html in pages.values():
    assert site_chrome.CSP in html
    assert '<script src="./sports.js"></script>' in html

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
                assert page.locator(".stamp").is_visible(), (sport, width)
                assert page.locator("nav.sports [aria-current='page']").count() == 1
                assert page.locator("nav.sports [aria-current='page']").evaluate("""e => {
                    const r = e.getBoundingClientRect(), n = e.parentElement.getBoundingClientRect();
                    return r.left >= n.left - 1 && r.right <= n.right + 1 && r.height >= 44;
                }"""), (sport, width)
                assert page.evaluate("""() => [...document.querySelectorAll('body *')].every(e =>
                    !e.checkVisibility() || ![...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())
                    || parseFloat(getComputedStyle(e).fontSize) >= 11)"""), (sport, width)
                page.locator(".page-menu > summary").click()
                assert page.locator("nav.main a").count() == 4
                assert page.locator("nav.main a").evaluate_all(
                    "links => links.every(e => e.getBoundingClientRect().height >= 44)")
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (sport, width, "menu")
                page.keyboard.press("Escape")
                assert page.locator(".page-menu").get_attribute("open") is None
                if sport == "nba":
                    assert page.locator("details.nba-game[open]").count() == 0
                    page.locator(".nba-game-summary").click()
                    assert page.locator("details.nba-game[open]").count() == 1
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
                    assert page.locator(".crypto-coin").count() == 5
                page.close()
        page = browser.new_page()
        page.route("http://fixture.local/soccer.html", lambda route: route.fulfill(body=warning, content_type="text/html"))
        page.route("http://fixture.local/*.js", lambda route: route.fulfill(body="", content_type="application/javascript"))
        page.route("http://fixture.local/*.css", lambda route: route.fulfill(body="", content_type="text/css"))
        page.goto("http://fixture.local/soccer.html")
        assert page.locator("#health > details").get_attribute("open") is not None
        assert page.locator("#health details.section-disclosure").get_attribute("open") is None
        browser.close()
print("PASS four sport pages: 320–1280px, readable text, menu, disclosures, stored scan status")
