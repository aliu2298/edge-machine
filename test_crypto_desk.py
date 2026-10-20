#!/usr/bin/env python3
"""The Crypto page on the shared sport template: one rule, its market-days as
the events, the method folded. Presentation only: the record, ROI and verdict
are the Sandbox row's own strings, and nothing here grades a bet.
"""
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
import sport_page as SP

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
    m = re.search(rf'<section id="{name}"[^>]*>(.*?)(?=<section id="|<footer)', markup, re.S)
    return m.group(1) if m else ""


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
main = html.split("<main", 1)[-1].split("</main>", 1)[0]
ok("<h1>Crypto</h1>" in html, "the title is Crypto")
ok("Daily favourite-band picks on Kalshi coin closes · All times Central" in html, "the one scope line")
for anchor in ("events", "rules", "method"):
    ok(f'id="{anchor}"' in html and f'href="#{anchor}"' in html, f"section and sub-nav pill for #{anchor}")
ok(html.find('id="rules"') < html.find('id="events"') < html.find('id="method"'),
   "the rule first, then the events, then the folded method")
for gone in ("crypto-hero", "crypto-progress", "progressbar", "crypto-coin", "crypto-tabs", "crypto-health",
             "crypto-rule-strip", "Favourite-band record", "Five live coins", "crypto-metrics", "tn-pick", "cr-pick",
             "cr-rules", 'id="today"', 'id="performance"', 'id="lanes"', "Full record table"):
    ok(gone not in html, f"the page no longer prints {gone!r}")
eq(B.label_cells(html), html, "the tracker's labelling pass leaves the page unchanged")
ok('data-filter="scope"' not in html and 'data-filter="stage"' in html, "one scope, so only the stage chips")

print("\ntiles")
cells = re.findall(r'<div class="tile">(.*?)</div>', main)
eq(len(cells), 4, "four stat tiles")
rows = C.crypto_rows(ledger, stages)
fav = C._fav_row(rows)
a = fav["a"]
ok(">1</b><span>open picks" in cells[0], "open picks counts the open bet")
ok(">1</b><span>active rules" in cells[1], "the one rule is active")
_won, _n = int(a.get("won") or 0), int(a.get("n") or 0)
ok(f"<b>{_won}–{_n - _won}</b><span>Sandbox record · paper" in cells[2] if _n else "<b>—</b><span>Sandbox record · paper" in cells[2],
   "not in Production, so the record tile is the Sandbox rule's own record, labelled paper (2026-10-20)")
ok("ROI after fees · Sandbox, paper" in cells[3] and "Production" not in cells[2] + cells[3],
   "and the ROI tile is the Sandbox's, never implying Production")
prod = {"pairs": {"crypto_fav_band|crypto_fav": {"stage": "production", "by_hand": "2026-10-08",
                                                 "promoted_at": "2026-10-04T00:00:00+00:00"}}}
prod_html = C.build(ledger, prod, NOW)
ok("since Production · Favourite band · 3h to the close" in prod_html
   and f'<b>{a["won"]}–{a["n"] - a["won"]}</b><span>since Production · Favourite band · 3h to the close</span>' in prod_html,
   "in Production the record tile is the since-Production market-day record, named")

print("\nevents: market-days in the tabs")
events = _section(main, "events")
tabs = [re.sub(r"<[^>]+>", "", t).strip() for t in re.findall(r'role="tab"[^>]*>(.*?)</button>', events)]
eq(tabs, ["Next 24h 2", "In progress 0", "Completed · 14 days 3"], "the open bet and the watch-only quote are next; three market-days completed")
nxt = events.split('id="events-live"', 1)[0]
btc = re.search(r'<div class="sp-event"[^>]*>(?:(?!sp-event").)*?BTC · KXBTCD.*?</div></div>', nxt, re.S).group(0)
ok('<div class="sp-when">4:05 PM CT</div>' in btc, "time is the close, Chicago clock")
ok(f'href="{S.market_url(ledger["quotes"][0])}"' in btc and "BTC · KXBTCD" in btc, "coin · series links to the market")
ok(">$84,500 or above<" in btc, "the pick is the rung as the venue names it")
ok('<span class="sp-price">78¢</span>' in btc and 'class="sp-state is-next">upcoming<' in btc, "the price in cents and the state")
eth = re.search(r'<div class="sp-event"[^>]*>(?:(?!sp-event").)*?ETH · KXETHD.*?</div></div>', nxt, re.S).group(0)
ok('class="sp-pick is-watch"' in eth and ">watching<" in eth, "a watch-only quote is watching")
done = events.split('id="events-done"', 1)[1]
days = re.findall(r'<h4 class="sp-day-head">([^<]+)', done)
eq(days, ["Tue Oct 6", "Mon Oct 5"], "completed market-days newest first")
ok("$85,250 or above" in done and "$118 or above" in done and 'is-won">W<' in done and 'is-lost">L<' in done,
   "yesterday lists both coins with their results")
ok("no entry" not in html, "a coin with no rung is not a line; the empty state carries the reason instead")

print("\nrules: one card")
rule = _section(main, "rules")
from sport_rows_testlib import rule_rows, text as row_text
ok("No crypto rule is in Production." in rule and 'data-list="sandbox"' in rule, "the Sandbox rule is a row in the Sandbox fold")
r = rule_rows(rule)[0]
ok((r["source"], r["sport"]) == ("crypto_fav_band", "crypto_fav"), "the row is the favourite-band lane")
eq(r["name"], "Favourite band · 3h to the close", "named")
eq(row_text(r["cells"]["Record"]), f'{a["won"]}–{a["n"] - a["won"]}', "record W–L")
eq(r["cells"]["ROI after fees"], SP.roi_html(fav), "ROI is the Sandbox row's figure")
eq(r["cells"]["Evidence"], f'{a["n"]}/{T.READ_FLOOR}', "evidence is market-days of 30")
eq(r["cells"]["Verdict"], SP.verdict_badge(fav), "the verdict is the Sandbox chip, read through sport_page.verdict_badge")
eq(r["cells"]["Market"], "Kalshi", "the market column is the venue")
detail = r["body"]
ok(not r["open"], "its Rule details fold starts closed")
dl = re.search(r'<dl class="sp-params">(.*?)</dl>', detail).group(1)
eq(re.findall(r"<dt>(.*?)</dt>", dl), ["Entry", "Selection", "Liquidity", "Close"], "four entry parameters")
eq(re.findall(r"<dd>(.*?)</dd>", dl),
   ["Yes ask 70–80¢, 2–3.5h before the close", "lowest qualifying rung, one per coin",
    "≤3¢ spread, 25+ ask", "17:00 ET"], "the parameters are the registered constants")
note = " ".join(S.SOURCES["crypto_fav_band"]["note"].split())
ok(f'<p class="sp-def">{B.esc(note)}</p>' in detail, "the registered definition, verbatim, in the fold")
ok(detail.find("<dl") < detail.find("sp-def"), "parameters first, then the definition")
ok("Last scan Oct 7, 6:00 AM CT · 525 quotes · next window Oct 7, 12:30–2:00 PM CT" in detail,
   "the scanner line sits under the definition")
with patch.object(S, "CRYPTO_FAV_BAND", (0.6, 0.9)), patch.object(S, "CRYPTO_FAV_MAX_SPREAD", 0.04), \
        patch.object(S, "CRYPTO_FAV_CLOSE_ET", 16):
    const = C.build(ledger, stages, NOW)
    ok("Yes ask 60–90¢" in const and "≤4¢ spread" in const and "16:00 ET" in const and "70–80¢" not in const,
       "the parameters follow the registered constants")
prod_rules = _section(prod_html.split("<main", 1)[-1], "rules")
prow = rule_rows(prod_rules.split('id="sandbox"', 1)[0])
ok(prow and prow[0]["stage"] == "production" and prow[0]["name"] == "Favourite band · 3h to the close"
   and '<dl class="sp-params">' in prow[0]["body"],
   "in Production the rule is a row in the Production list, its parameters in the fold")

print("\nscan status")
scan = C._scan_status(ledger, NOW)
eq(scan, '<p class="sm mut cr-scan">Last scan Oct 7, 6:00 AM CT · 525 quotes · next window Oct 7, 12:30–2:00 PM CT</p>',
   "one muted scanner line: last scan · quotes · window")
inside = C._scan_status(ledger, datetime.datetime(2026, 10, 7, 18, tzinfo=datetime.timezone.utc))
ok("current window Oct 7, 12:30–2:00 PM CT" in inside, "inside the window the line says current")
later = C._scan_status(ledger, NOW.replace(hour=23))
ok("next window Oct 8, 12:30–2:00 PM CT" in later, "after the window closes the line names the next one")
with patch.object(S, "CRYPTO_FAV_CLOSE_ET", 16):
    ok("11:30 AM–1:00 PM CT" in C._scan_status(ledger, NOW), "a window across noon keeps both periods")

print("\nmethod: folded")
method = _section(main, "method")
ok(method.lstrip().startswith("<details><summary><b>Method</b>"), "method is one closed fold")
ok("<details open" not in method, "it starts closed")
ok("A day is one bet" in method and "graded as a single outcome" in method, "it says why a day is one bet and how a day is graded")
ok("<b>Scheduling.</b>" in method and "13:15 Central" in method, "the scheduling note is a sub-line inside the fold")
ok("launchd" not in html.split('id="method"')[0], "no operational notes on the open page")
ok(method.find("Scheduling") > method.find("A day is one bet"), "the method sentences come before scheduling")

print("\nedge cases")
empty = C.build({"quotes": []}, {"pairs": {}}, NOW)
ok("No crypto favourite-band record yet." not in empty and 'data-verdict="waiting">Too early<' in empty
   and '<span class="sp-cell num" data-l="Record"><span class="mut">—</span></span>' in empty,
   "before the first bet the row is the registration itself: no record, the Sandbox's waiting verdict")
ok(">0</b><span>open picks" in empty and "<b>—</b><span>Sandbox record · paper" in empty, "empty tiles: nothing settled is a dash")
for anchor in ("events", "rules", "method"):
    ok(f'id="{anchor}"' in empty, f"an empty page keeps #{anchor}")
ok("Last scan not recorded · no scanner coverage stored" in empty, "no scan is said once")
ok('data-empty="next"' in empty and "no read is stored for this sport yet" in empty, "the Next 24h empty state says no read is stored")
unknown = {"quotes": [dict(quote("KXBTCD", 1, 0.75, TODAY, status="open"), start="unreadable")]}
odd = C.build(unknown, stages, NOW)
ok("$1 or above" in odd and "None" not in odd and "time TBC" in odd, "an unreadable close still lists the pick, time TBC")
row = {"sport": "crypto_fav", "name": "crypto_fav_band", "prod": False, "open": 0, "v": "early", "since": None,
       "meta": S.SOURCES["crypto_fav_band"],
       "a": {"n": 2, "won": 1, "expected": 1.5, "roi_fee": None, "clv": None, "clv_n": 0, "n_bets": 5}}
with patch.object(C, "crypto_rows", return_value=[row]):
    nul = C.build({"quotes": []}, {}, NOW)
    ok("None" not in nul, "a missing ROI is a dash, not None")
ok('<script' not in main.replace('<script src="./', ""), "no inline script")

css = open(os.path.join(ROOT, "public_site", "site.css"), encoding="utf-8").read()
ok(".sp-params {" in css and ".cr-params" not in css and ".tn-pick.cr-pick" not in css,
   "the crypto rules are the template's; the page-specific ones are retired")
published = open(os.path.join(ROOT, "public_site", "crypto.html"), encoding="utf-8").read()
ok('class="sp-head"' in published and "crypto-hero" not in published, "public_site/crypto.html is the template page")

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
            eq(page.locator(".sp-pick:visible").count(), 2, f"{width}px the Next 24h tab shows two lines")
            page.locator('.sp-tabs button[data-tab="done"]').click()
            eq(page.locator(".sp-pick:visible").count(), 3, f"{width}px the Completed tab shows three")
            eq(page.locator(".sp-day-head:visible").first.evaluate("e => getComputedStyle(e).position"), "sticky",
               f"{width}px the day head is sticky")
            eq(page.locator("#method > details[open]").count(), 0, f"{width}px method starts closed")
            page.locator("details.sp-sandbox > summary").click()
            ok(page.locator("details.sp-rule .sp-params:visible").count() == 0, f"{width}px the parameters start hidden")
            page.locator("details.sp-rule > summary").first.click()
            ok(page.locator("details.sp-rule").first.locator(".sp-params").is_visible(), f"{width}px opening the row reveals the parameters")
            page.locator("#method > details > summary").click()
            ok(page.locator("#method > details > div").is_visible(), f"{width}px the method fold opens")
            ok(page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), f"{width}px still fits with both open")
            eq(page.locator(".sp-head-line").first.evaluate("e => getComputedStyle(e).display"),
               "none" if width <= 980 else "grid", f"{width}px the figures carry their own labels under 981px")
            eq(page.locator("nav.toc a").evaluate_all("a => a.map(x => x.getAttribute('href'))"),
               ["#rules", "#events", "#method"], f"{width}px sub-nav is Rules / Events / Method")
            page.close()
        browser.close()

if FAILS:
    print(f"\nFAILED {len(FAILS)}")
    sys.exit(1)
print("PASS crypto page: tiles, market-day events, one rule row, folded method")
