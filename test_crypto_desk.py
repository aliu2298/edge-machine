#!/usr/bin/env python3
"""The Crypto page: four tiles, one picks list grouped by day, a one-row rules
table, and the method folded away. Presentation only: the record, ROI and
verdict are the Sandbox row's own strings, and nothing here grades a bet.
"""
import copy
import datetime
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse
from unittest.mock import patch

import crypto_build as C
import fmt
import sandbox_build as B
import sandbox_sources as S
import sandbox_track as T

FAILS = []
NOW = datetime.datetime(2026, 10, 7, 12, tzinfo=datetime.timezone.utc)   # 7:00 AM CT, Oct 7
ROOT = os.path.dirname(os.path.abspath(__file__))


def ok(cond, why):
    print(f"  {'ok  ' if cond else 'FAIL'} {why}")
    if not cond:
        FAILS.append(why)


def eq(got, want, why):
    ok(got == want, why if got == want else f"{why} — got {got!r}, want {want!r}")


def _section(markup, name):
    m = re.search(rf'<section id="{name}"[^>]*>(.*?)</section>', markup, re.S)
    return m.group(1) if m else ""


def _rows(block):
    return re.findall(r'<div class="tn-pick cr-pick[^"]*"[^>]*>.*?</div>(?=<div class="tn-pick|</div>)', block, re.S)


def quote(series, strike, price, day, status="open", bet=True, logged=None):
    close = datetime.datetime.combine(day, datetime.time(21, 5), datetime.timezone.utc)
    return dict(
        id=f"crypto_fav_band:{series}-T{strike}-{day}", source="crypto_fav_band", sport="crypto_fav",
        market_id=f"{series}-26OCT0717-T{strike}.99", label=f"Coin price on {day}?",
        side_a=f"${strike:,} or above", side_b="No", pick="a", price=price,
        bet=bet, status=status, result=("a" if status == "won" else "b" if status == "lost" else None),
        pnl=(round(100 * (1 / price - 1), 2) if status == "won" else -100.0 if status == "lost" else None),
        start=close.isoformat(), date=day.isoformat(),
        logged=logged or (close - datetime.timedelta(hours=3)).isoformat(),
        venue="kalshi_binary", url="https://kalshi.com/markets/kxbtcd",
        price_a=price, price_b=round(1 - price, 2))


TODAY = datetime.date(2026, 10, 7)
YESTERDAY = datetime.date(2026, 10, 6)
EARLIER = datetime.date(2026, 10, 5)
ledger = {
    "meta": {"updated": "2026-10-07T11:00:00Z"},
    "coverage": {"crypto_fav": {"crypto_fav_band": {"offered": 525, "picked": 1}}},
    "quotes": [
        quote("KXBTCD", 84500, 0.78, TODAY, status="open"),
        quote("KXETHD", 4500, 0.74, TODAY, status="open", bet=False),
        quote("KXBTCD", 85250, 0.80, YESTERDAY, status="won"),
        quote("KXSOLD", 118, 0.73, YESTERDAY, status="lost"),
        quote("KXBTCD", 82750, 0.78, EARLIER, status="won"),
    ],
}
stages = {"pairs": {}}

print("page shape")
html = C.build(ledger, stages, NOW)
ok('<h1>Crypto</h1>' in html, "the title is Crypto")
ok("Daily favourite-band picks on Kalshi coin closes · times CT" in html, "the one-line lede")
ok(fmt.display_updated(NOW) in html.split("<main", 1)[-1], "the freshness stamp is under the title")
for anchor in ("picks", "rule", "method"):
    ok(f'id="{anchor}"' in html and f'href="#{anchor}"' in html, f"section and sub-nav pill for #{anchor}")
ok(html.find('id="rule"') < html.find('id="picks"') < html.find('id="method"'),
   "the rule first, then the picks, then the folded method")
for gone in ("crypto-hero", "crypto-progress", "progressbar", "crypto-coin", "crypto-tabs", "crypto-health",
             "crypto-rule-strip", "Favourite-band record", "Five live coins", "crypto-metrics",
             'id="today"', 'id="performance"', 'id="lanes"', "Full record table", "<h3"):
    ok(gone not in html, f"the page no longer prints {gone!r}")
ok("<thead>" in html and 'data-l="Record"' in html, "the table is labelled for the phone cards")
eq(B.label_cells(html), html, "the tracker's labelling pass leaves the page unchanged")

print("\ntiles")
tiles = re.search(r'<div class="tiles tn-tiles">(.*?)</div>\s*<section', html, re.S).group(1)
cells = re.findall(r'<div class="tile">(.*?)</div>', tiles)
eq(len(cells), 4, "four stat tiles")
rows = C.crypto_rows(ledger, stages)
fav = C._fav_row(rows)
a = fav["a"]
ok(">1</b><span>open picks" in cells[0], "open picks counts the open bet")
ok(f'>{a["won"]}–{a["n"] - a["won"]}</b><span>record · W–L' in cells[1], "record is W–L from the Sandbox row")
ok(f'>{B.pct(a["roi_fee"], sign=True)}</b><span>ROI after fees' in cells[2], "ROI is the Sandbox row's figure")
ok(f'>{a["n"]} of {T.READ_FLOOR}</b><span>market-days logged · {T.READ_FLOOR} planned' in cells[3],
   "market-days logged reads 'n of 30' in the tile text")
ok('class="mut"' in cells[2], "ROI under the read floor is grey")

print("\npicks: one list grouped by day")
picks = _section(html, "picks")
days = re.findall(r'<div class="tn-day">(.*?)</div>', picks)
eq(days, ["Today · Oct 7", "Oct 6", "Oct 5"], "today first, then settled days newest first")
today_block = picks.split('<div class="tn-day">Oct 6</div>', 1)[0]
today_rows = re.findall(r'<div class="tn-pick cr-pick([^"]*)" data-series="([^"]+)">', today_block)
eq([s for _c, s in today_rows], list(S.COINS), "today lists the five live coins once each, in order")
ok(' is-live' in today_rows[0][0] and 'is-next' in today_rows[1][0], "an open bet is live, a watch-only quote is watching")
ok(all("is-muted is-none" in cls for cls, _s in today_rows[2:]), "a coin with no rung today is one muted no-entry line")
btc = re.search(r'<div class="tn-pick cr-pick is-live" data-series="KXBTCD">(.*?)</div></div>', today_block, re.S).group(1)
ok('<span class="tn-time">4:05 PM CT</span>' in btc, "time is the close, Chicago clock")
ok("BTC · KXBTCD" in btc and f'href="{S.market_url(ledger["quotes"][0])}"' in btc, "coin · series links to the market")
ok("<b>$84,500 or above</b>" in btc, "the pick is the rung as the venue names it")
ok('<span class="tn-price">78¢</span>' in btc, "the price in cents")
ok('<span class="tn-state is-live">open</span>' in btc, "state open")
sol = re.search(r'<div class="tn-pick cr-pick is-muted is-none" data-series="KXSOLD">(.*?)</div></div>', today_block, re.S).group(1)
ok('<span class="tn-state is-none">no entry</span>' in sol and '<span class="tn-pos"></span>' in sol
   and '<span class="tn-price"></span>' in sol and "4:00 PM CT" in sol,
   "a no-entry row carries only the coin, the close and the state")
ok("W</span>" in picks and "L</span>" in picks, "settled market-days are rows with W and L states")
y_block = picks.split('<div class="tn-day">Oct 6</div>', 1)[1].split('<div class="tn-day">Oct 5</div>', 1)[0]
ok("$85,250 or above" in y_block and "$118 or above" in y_block and "is-won" in y_block and "is-lost" in y_block,
   "yesterday lists both coins with their results")
ok(picks.count('<div class="tn-pick cr-pick') == 8, "five today, two yesterday, one earlier")
ok("card" not in picks and "<article" not in picks, "no cards")
scan = re.search(r'<p class="sm mut cr-scan">(.*?)</p>', picks).group(1)
eq(scan, "Last scan Oct 7, 6:00 AM CT · 525 quotes · next window Oct 7, 12:30–2:00 PM CT",
   "one muted scanner line: last scan · quotes · window")
inside = C._scan_status(ledger, datetime.datetime(2026, 10, 7, 18, tzinfo=datetime.timezone.utc))
ok("current window Oct 7, 12:30–2:00 PM CT" in inside, "inside the window the line says current")
eq(picks.count("<p"), 2, "one sentence of copy and the scanner line, nothing else")
later = C._scan_status(ledger, NOW.replace(hour=23))
ok("next window Oct 8, 12:30–2:00 PM CT" in later, "after the window closes the line names the next one")
with patch.object(S, "CRYPTO_FAV_CLOSE_ET", 16):
    ok("11:30 AM–1:00 PM CT" in C._scan_status(ledger, NOW), "a window across noon keeps both periods")

print("\nrule: one row")
rule = _section(html, "rule")
ok('<table class="tn-rules cr-rules">' in rule, "the rule is the tennis table pattern")
eq(re.findall(r"<th(?:\s[^>]*)?>(.*?)</th>", rule), ["Rule", "Venue", "Record", "ROI", "Verdict", "Open"],
   "Rule · Venue · Record · ROI · Verdict · Open")
eq(rule.count("<tr"), 2, "one header row and one rule row")
ok('<details class="tn-rule"><summary><b>Favourite band · 3h to the close</b></summary>' in rule,
   "the chevron is the details summary in the Rule cell")
ok(f'{B.pct(a["roi_fee"], sign=True)}</span><div class="sm mut">on {a["n"]} market-days</div>' in rule,
   "ROI sits next to its sample")
ok(f'data-l="Record">{a["won"]}–{a["n"] - a["won"]}</td>' in rule, "record W–L")
label, chip, _o = B.VERDICTS[fav["v"]]
ok(f'<span class="sig {chip}">{label}</span>' in rule, "the verdict is the Sandbox chip")
ok('data-l="Venue">Kalshi</td>' in rule and 'data-l="Open">1</td>' in rule, "venue and open count")
dl = re.search(r'<dl class="cr-params">(.*?)</dl>', rule).group(1)
eq(re.findall(r"<dt>(.*?)</dt>", dl), ["Entry", "Selection", "Liquidity", "Close"], "four entry parameters")
eq(re.findall(r"<dd>(.*?)</dd>", dl),
   ["Yes ask 70–80¢, 2–3.5h before the close", "lowest qualifying rung, one per coin",
    "≤3¢ spread, 25+ ask", "17:00 ET"], "the parameters are the registered constants")
note = S.SOURCES["crypto_fav_band"]["note"].strip()
ok(f'<p class="tn-def sm mut">{B.esc(note)}</p>' in rule, "the registered definition paragraph is in the row")
ok(rule.find("<dl") < rule.find("tn-def"), "parameters first, then the definition")
with patch.object(S, "CRYPTO_FAV_BAND", (0.6, 0.9)), patch.object(S, "CRYPTO_FAV_MAX_SPREAD", 0.04), \
        patch.object(S, "CRYPTO_FAV_CLOSE_ET", 16):
    const = C.build(ledger, stages, NOW)
    ok("Yes ask 60–90¢" in const and "≤4¢ spread" in const and "16:00 ET" in const and "70–80¢" not in const,
       "the parameters follow the registered constants")

print("\nmethod: folded")
method = _section(html, "method")
ok(method.startswith("\n<details>") or method.lstrip().startswith("<details>"), "method is one closed fold")
ok("<details open" not in method, "it starts closed")
ok("A day is one bet" in method and "graded as a single outcome" in method, "it says why a day is one bet and how a day is graded")
ok("<b>Scheduling.</b>" in method and "13:15 Central" in method, "the scheduling note is a sub-line inside the fold")
ok("launchd" not in html.split('id="method"')[0], "no operational notes on the open page")
ok(method.count("<p") == 2, "a few sentences, two paragraphs")
ok(method.find("Scheduling") > method.find("A day is one bet"), "the method sentences come before scheduling")

print("\nedge cases")
empty = C.build({"quotes": []}, {"pairs": {}}, NOW)
ok("No crypto favourite-band record yet." in empty, "no row says so")
ok(empty.count('<div class="tn-pick cr-pick') == len(S.COINS) and "no entry" in empty,
   "an empty ledger still lists today's coins as no entry")
ok(">0</b><span>open picks" in empty and ">—</b><span>record" in empty and f">0 of {T.READ_FLOOR}</b>" in empty,
   "empty tiles")
for anchor in ("picks", "rule", "method"):
    ok(f'id="{anchor}"' in empty, f"an empty page keeps #{anchor}")
ok("Last scan not recorded · no scanner coverage stored" in empty, "no scan is said once")
unknown = {"quotes": [dict(quote("KXBTCD", 1, 0.75, TODAY, status="open"), start="unreadable")]}
odd = C.build(unknown, stages, NOW)
ok("$1 or above" in odd and "None" not in odd, "an unreadable close still lists the pick by its stored date")
row = {"sport": "crypto_fav", "name": "crypto_fav_band", "prod": False, "open": 0, "v": "early",
       "meta": S.SOURCES["crypto_fav_band"],
       "a": {"n": 2, "won": 1, "expected": 1.5, "roi_fee": None, "clv": None, "clv_n": 0, "n_bets": 5}}
with patch.object(C, "crypto_rows", return_value=[row]):
    nul = C.build({"quotes": []}, {}, NOW)
    ok("None" not in nul and ">—</b><span>ROI after fees" in nul, "a missing ROI is a dash, not None")
prod_row = dict(row, prod=True, a=dict(row["a"], roi_fee=0.1))
with patch.object(C, "crypto_rows", return_value=[prod_row]):
    prod = C.build({"quotes": []}, {}, NOW)
    ok('<span class="sig y">PRODUCTION</span>' in prod, "a Production lane is marked on the row")
ok('<script' not in html.split("<main", 1)[-1].split("</main>", 1)[0].replace('<script src="./', ""),
   "no inline script")

css = open(os.path.join(ROOT, "public_site", "site.css"), encoding="utf-8").read()
ok(".tn-pick.cr-pick {" in css and ".cr-params {" in css, "the crypto rules are additive overrides on the tennis patterns")
ok(".tn-day {" in css and ".tn-rules td:first-child" in css, "the tennis patterns are reused, not copied")
published = open(os.path.join(ROOT, "public_site", "crypto.html"), encoding="utf-8").read()
ok('class="tn-pick cr-pick' in published and "crypto-hero" not in published, "public_site/crypto.html is the list page")

print("\nbrowser")
from require_browser import require_browser
playwright = require_browser("test_crypto_desk.py")
if playwright is not None:
    with playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        for width in (1280, 390, 320):
            page = browser.new_page(viewport={"width": width, "height": 800})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            def serve(route):
                name = Path(urlparse(route.request.url).path).name
                if name == "crypto.html":
                    route.fulfill(body=html, content_type="text/html")
                else:
                    route.fulfill(path=str(Path(C.__file__).parent / "public_site" / name))
            page.route("http://fixture.local/**", serve)
            page.goto("http://fixture.local/crypto.html", wait_until="load")
            ok(not errors, f"{width}px no JavaScript errors")
            ok(page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), f"{width}px no sideways scroll")
            eq(page.locator(".tn-pick.cr-pick").count(), 8, f"{width}px eight list rows")
            eq(page.locator(".tn-day").first.evaluate("e => getComputedStyle(e).position"), "sticky",
               f"{width}px the day header is sticky")
            eq(page.locator("#method > details[open]").count(), 0, f"{width}px method starts closed")
            ok(not page.locator("details.tn-rule .cr-params").is_visible(), f"{width}px the parameters start hidden")
            page.locator("details.tn-rule > summary").click()
            ok(page.locator("details.tn-rule .cr-params").is_visible(), f"{width}px the chevron reveals the parameters")
            page.locator("#method > details > summary").click()
            ok(page.locator("#method > details > div").is_visible(), f"{width}px the method fold opens")
            ok(page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), f"{width}px still fits with both open")
            cards = page.locator(".cr-rules thead").first.evaluate("e => getComputedStyle(e).display")
            eq(cards, "none" if width < 760 else "table-header-group", f"{width}px cards fallback under 760px")
            eq(page.locator("nav.toc a").evaluate_all("a => a.map(x => x.getAttribute('href'))"),
               ["#rule", "#picks", "#method"], f"{width}px sub-nav is Rule / Picks / Method")
            page.close()
        browser.close()

if FAILS:
    print(f"\nFAILED {len(FAILS)}")
    sys.exit(1)
print("PASS crypto page: tiles, one picks list, one-row rule table, folded method")
