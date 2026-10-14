#!/usr/bin/env python3
"""The Commodities page on the shared sport template: one rule, its market-days
as the events, the method folded. Presentation only: the record, ROI and verdict
are the Sandbox row's own strings, and nothing here grades a bet.
"""
import datetime
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse
from unittest.mock import patch

import commodities_build as C
import fmt
import sandbox_build as B
import sandbox_sources as S
import sandbox_track as T
import sport_page as SP

FAILS = []
ROOT = os.path.dirname(os.path.abspath(__file__))
# Thursday 2026-10-08, 7:00 AM CT: before both windows.
NOW = datetime.datetime(2026, 10, 8, 12, tzinfo=datetime.timezone.utc)


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
    hour, minute = S.commod_fav_close_et(series)
    close = datetime.datetime.combine(day, datetime.time(hour, minute), S.COMMOD_FAV_TZ).astimezone(datetime.timezone.utc)
    return dict(
        id=f"commod_fav_band:{series}-T{strike}-{day}", source="commod_fav_band", sport="commodities_fav",
        market_id=f"{series}-26OCT0817-T{strike}", label=f"{series} above {strike}",
        side_a=f"${strike} or above", side_b="No", pick="a", price=price,
        bet=bet, status=status, result=("a" if status == "won" else "b" if status == "lost" else None),
        pnl=(round(100 * (1 / price - 1), 2) if status == "won" else -100.0 if status == "lost" else None),
        start=close.isoformat(), date=close.strftime("%Y-%m-%d"),
        logged=logged or (close - datetime.timedelta(hours=3)).isoformat(),
        venue="kalshi_binary", url="https://kalshi.com/markets/x",
        price_a=price, price_b=round(1 - price, 2), bid=round(price - 0.01, 2), ask=price, ask_size=200)


TODAY = datetime.date(2026, 10, 8)
YESTERDAY = datetime.date(2026, 10, 7)
EARLIER = datetime.date(2026, 10, 6)
ledger = {
    "meta": {"updated": "2026-10-08T11:00:00Z"},
    "coverage": {"commodities_fav": {"commod_fav_band": {"offered": 180, "picked": 1}}},
    "quotes": [
        quote("KXWTI", "81.99", 0.74, TODAY, status="open"),
        quote("KXGOLDD", "4006", 0.73, TODAY, status="open", bet=False),
        quote("KXGOLDD", "3996", 0.78, YESTERDAY, status="won"),
        quote("KXSILVERD", "47.5", 0.72, YESTERDAY, status="lost"),
        quote("KXWTI", "80.49", 0.77, EARLIER, status="won"),
    ],
}
stages = {"pairs": {}}

print("page shape")
html = C.build(ledger, stages, NOW)
main = html.split("<main", 1)[-1].split("</main>", 1)[0]
ok("<h1>Commodities</h1>" in html, "the title is Commodities")
ok("Daily favourite-band picks on Kalshi commodity closes · All times Central" in html, "the one scope line")
for anchor in ("rules", "events", "method"):
    ok(f'id="{anchor}"' in html and f'href="#{anchor}"' in html, f"section and sub-nav pill for #{anchor}")
ok(html.find('id="rules"') < html.find('id="events"') < html.find('id="method"'),
   "the rule first, then the events, then the folded method")
ok('href="./commodities.html" aria-current="page"' in html and 'href="./crypto.html"' in html,
   "the shared nav carries Commodities after Crypto and marks it current")
ok(html.find('href="./crypto.html"') < html.find('href="./commodities.html"') < html.find('href="./sandbox.html#method"'),
   "the Commodities pill sits after Crypto and before Method")
eq(B.label_cells(html), html, "the tracker's labelling pass leaves the page unchanged")
for gone in ("progressbar", "crypto-hero", "<meter", "<progress", "tn-pick", "cr-pick", "cr-rules", "tn-tiles"):
    ok(gone not in html, f"the page does not print {gone!r}")

print("\ntiles")
cells = re.findall(r'<div class="tile">(.*?)</div>', main)
eq(len(cells), 4, "four stat tiles")
rows = C.commod_rows(ledger, stages)
fav = C._fav_row(rows)
a = fav["a"]
ok(">1</b><span>open picks" in cells[0], "open picks counts the open bet")
ok(">1</b><span>active rules" in cells[1], "the one rule is active")
ok("<b>—</b><span>Production record · no rule in Production</span>" in cells[2], "not in Production, so the record tile says so")
eq(a.get("unit"), "market-day", "the Sandbox counts this lane in market-days")

print("\nrules: one row")
rule = _section(main, "rules")
from sport_rows_testlib import rule_rows, text as row_text
ok("No commodities rule is in Production." in rule and 'data-list="sandbox"' in rule, "the Sandbox rule is a row in the Sandbox fold")
r = rule_rows(rule)[0]
eq(r["name"], "Favourite band · 3h to the close", "named")
ok(r["cells"]["ROI after fees"] == SP.roi_html(fav) and r["cells"]["Evidence"] == f'{a["n"]}/{T.READ_FLOOR}', "ROI and evidence are the row's own")
detail = r["body"]
ok(not r["open"], "its Rule details fold starts closed")
dl = re.search(r'<dl class="sp-params">(.*?)</dl>', detail).group(1)
eq(re.findall(r"<dt>(.*?)</dt>", dl), ["Entry", "Selection", "Liquidity", "Close"], "four entry parameters")
eq(re.findall(r"<dd>(.*?)</dd>", dl),
   ["Yes ask 70–80¢, 2–3.5h before the close", "lowest qualifying rung, one per commodity, trading days only",
    "≤3¢ spread, 25+ ask", "WTI 14:30 ET · the rest 17:00 ET"], "the parameters are the registered constants")
note = " ".join(S.SOURCES["commod_fav_band"]["note"].split())
ok(f'<p class="sp-def">{B.esc(note)}</p>' in detail, "the registered definition paragraph is in the fold")
eq(r["cells"]["Market"], "Kalshi", "the market column is the venue")

print("\nevents: market-days in the tabs")
events = _section(main, "events")
tabs = [re.sub(r"<[^>]+>", "", t).strip() for t in re.findall(r'role="tab"[^>]*>(.*?)</button>', events)]
eq(tabs, ["Next 24h 2", "In progress 0", "Completed · 14 days 3"], "the open bet and the watch-only quote are next; three market-days completed")
nxt = events.split('id="events-live"', 1)[0]
wti = re.search(r'<div class="sp-event"[^>]*>(?:(?!sp-event").)*?WTI · KXWTI.*?</div></div>', nxt, re.S).group(0)
ok('<div class="sp-when">1:30 PM CT</div>' in wti, "WTI's time is its own 14:30 ET close, in the Chicago clock")
ok(">WTI above $81.99<" in wti, "the pick is the rung named by its commodity")
ok('<span class="sp-price">74¢</span>' in wti and 'class="sp-state is-next">upcoming<' in wti, "price and state")
gold = re.search(r'<div class="sp-event"[^>]*>(?:(?!sp-event").)*?Gold · KXGOLDD.*?</div></div>', nxt, re.S).group(0)
ok('class="sp-pick is-watch"' in gold and ">watching<" in gold and "4:00 PM CT" in gold,
   "a watch-only quote is watching, at the 17:00 ET close")
done = events.split('id="events-done"', 1)[1]
days = re.findall(r'<h4 class="sp-day-head">([^<]+)', done)
eq(days, ["Wed Oct 7", "Tue Oct 6"], "completed market-days newest first")
ok('is-won">W<' in done and 'is-lost">L<' in done, "settled market-days are rows with W and L states")
ok("no entry" not in html, "a commodity with no rung is not a line")

print("\nscan status")
scan = C._scan_status(ledger, NOW)
eq(scan, '<p class="sm mut cr-scan">Last scan Oct 8, 6:00 AM CT · 180 quotes · next window Oct 8, 10:00–11:30 AM CT (WTI)</p>',
   "one muted scanner line naming the next window and its commodities")
ok("Last scan Oct 8, 6:00 AM CT · 180 quotes" in detail, "the scanner line sits under the definition")
inside = C._scan_status(ledger, datetime.datetime(2026, 10, 8, 15, 30, tzinfo=datetime.timezone.utc))
ok("current window Oct 8, 10:00–11:30 AM CT (WTI)" in inside, "inside the WTI window the line says current")
later = C._scan_status(ledger, datetime.datetime(2026, 10, 8, 17, 0, tzinfo=datetime.timezone.utc))
ok("next window Oct 8, 12:30–2:00 PM CT (Brent + Gold + Silver + Copper + Nat gas)" in later,
   "after WTI's window the next is the 17:00 group's")
friday_night = C._scan_status(ledger, datetime.datetime(2026, 10, 9, 23, 0, tzinfo=datetime.timezone.utc))
ok("next window Oct 12, 10:00–11:30 AM CT (WTI)" in friday_night, "on Friday night the next window is Monday's")

print("\nweekends and holidays")
sat = C.build(ledger, stages, datetime.datetime(2026, 10, 10, 15, tzinfo=datetime.timezone.utc))
sat_ev = _section(sat.split("<main", 1)[-1], "events")
ok('data-empty="next"' in sat_ev and "Next 24h 0" in re.sub(r"<[^>]+>", "", sat_ev), "a Saturday has nothing in the next 24 hours")
thanks = C.build({"quotes": []}, stages, datetime.datetime(2026, 11, 26, 15, tzinfo=datetime.timezone.utc))
ok('data-empty="next"' in thanks and 'data-empty="done"' in thanks, "a holiday with nothing settled says so on both tabs")

print("\nmethod: folded")
method = _section(main, "method")
ok(method.lstrip().startswith("<details><summary><b>Method</b>") and "<details open" not in method, "method is one closed fold")
ok("A day is one bet" in method and "+0.89" in method and "+0.84" in method, "it states the measured pairs")
ok("trading day" in method and "seven weeks" in method, "it says a market-day is a trading day")
ok("<b>Scheduling.</b>" in method and "10:00–11:30 Central" in method and "12:30–2:00 Central" in method,
   "the two windows are in the scheduling sub-line")

print("\nedge cases")
empty = C.build({"quotes": []}, {"pairs": {}}, NOW)
empty_rule = _section(empty.split("<main", 1)[-1], "rules")
ok('data-list="sandbox"' in empty_rule and 'data-verdict="waiting">Too early<' in empty_rule
   and '<span class="sp-cell num" data-l="Record"><span class="mut">—</span></span>' in empty_rule and "Yes ask 70–80¢" in empty_rule,
   "before the first bet the row is the registration itself: no record, the Sandbox's waiting verdict")
ok("No commodities favourite-band record yet." not in empty, "the page never says it has no rule")
ok(">0</b><span>open picks" in empty and "<b>—</b><span>Production record" in empty, "empty tiles")
ok("Last scan not recorded · no scanner coverage stored" in empty, "no scan is said once")
with patch.object(S, "COMMOD_FAV_BAND", (0.6, 0.9)), patch.object(S, "COMMOD_FAV_MAX_SPREAD", 0.04):
    const = C.build(ledger, stages, NOW)
    ok("Yes ask 60–90¢" in const and "≤4¢ spread" in const and "70–80¢" not in const,
       "the parameters follow the registered constants")
ok("<script" not in main.replace('<script src="./', ""), "no inline script")
published = os.path.join(ROOT, "public_site", "commodities.html")
ok(os.path.exists(published) and 'class="sp-head"' in open(published, encoding="utf-8").read(),
   "public_site/commodities.html is built on the template")
sitemap = open(os.path.join(ROOT, "public_site", "sitemap.txt"), encoding="utf-8").read()
ok("edge-machine/commodities.html" in sitemap, "the sitemap lists the page")

print("\nbrowser")
from require_browser import require_browser
playwright = require_browser("test_commodities_desk.py")
if playwright is not None:
    with playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        for width in (1280, 390, 320):
            page = browser.new_page(viewport={"width": width, "height": 800})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            def serve(route):
                name = Path(urlparse(route.request.url).path).name
                if name == "commodities.html":
                    route.fulfill(body=html, content_type="text/html")
                else:
                    route.fulfill(path=str(Path(C.__file__).parent / "public_site" / name))
            page.route("http://fixture.local/**", serve)
            page.goto("http://fixture.local/commodities.html", wait_until="load")
            ok(not errors, f"{width}px no JavaScript errors")
            ok(page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), f"{width}px no sideways scroll")
            eq(page.locator(".sp-pick:visible").count(), 2, f"{width}px the Next 24h tab shows two lines")
            eq(page.locator("#method > details[open]").count(), 0, f"{width}px method starts closed")
            page.locator("details.sp-sandbox > summary").click()
            page.locator("details.sp-rule > summary").first.click()
            ok(page.locator("details.sp-rule .sp-params").is_visible(), f"{width}px opening the row reveals the parameters")
            page.locator("#method > details > summary").click()
            ok(page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), f"{width}px still fits with both open")
            eq(page.locator("nav.toc a").evaluate_all("a => a.map(x => x.getAttribute('href'))"),
               ["#rules", "#events", "#method"], f"{width}px sub-nav is Rules / Events / Method")
            eq(page.locator("nav.main a[aria-current='page']").text_content(), "Commodities", f"{width}px the nav marks the page")
            page.close()
        browser.close()

if FAILS:
    print(f"\nFAILED {len(FAILS)}")
    sys.exit(1)
print("PASS commodities page: tiles, one rule row, market-day events, folded method")
