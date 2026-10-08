#!/usr/bin/env python3
"""The Commodities page: four tiles, a one-row rules table, one picks list grouped
by trading day, and the method folded away. Presentation only: the record, ROI and
verdict are the Sandbox row's own strings, and nothing here grades a bet.
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
    m = re.search(rf'<section id="{name}"[^>]*>(.*?)</section>', markup, re.S)
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
ok("<h1>Commodities</h1>" in html, "the title is Commodities")
ok("Daily favourite-band picks on Kalshi commodity closes · times CT" in html, "the one-line lede")
ok(fmt.display_updated(NOW) in html.split("<main", 1)[-1], "the freshness stamp is under the title")
for anchor in ("rule", "picks", "method"):
    ok(f'id="{anchor}"' in html and f'href="#{anchor}"' in html, f"section and sub-nav pill for #{anchor}")
ok(html.find('id="rule"') < html.find('id="picks"') < html.find('id="method"'),
   "the rule first, then the picks, then the folded method")
ok('href="./commodities.html" aria-current="page"' in html and 'href="./crypto.html"' in html,
   "the shared nav carries Commodities after Crypto and marks it current")
ok(html.find('href="./crypto.html"') < html.find('href="./commodities.html"') < html.find('href="./sandbox.html#method"'),
   "the Commodities pill sits after Crypto and before Method")
ok("<thead>" in html and 'data-l="Record"' in html, "the table is labelled for the phone cards")
eq(B.label_cells(html), html, "the tracker's labelling pass leaves the page unchanged")
for gone in ("progressbar", "crypto-hero", "<h3", "<meter", "<progress"):
    ok(gone not in html, f"the page does not print {gone!r}")

print("\ntiles")
tiles = re.search(r'<div class="tiles tn-tiles">(.*?)</div>\s*<section', html, re.S).group(1)
cells = re.findall(r'<div class="tile">(.*?)</div>', tiles)
eq(len(cells), 4, "four stat tiles")
rows = C.commod_rows(ledger, stages)
fav = C._fav_row(rows)
a = fav["a"]
ok(">1</b><span>open picks" in cells[0], "open picks counts the open bet")
ok(f'>{a["won"]}–{a["n"] - a["won"]}</b><span>record · W–L' in cells[1], "record is W–L from the Sandbox row")
ok(f'>{B.pct(a["roi_fee"], sign=True)}</b><span>ROI after fees' in cells[2], "ROI is the Sandbox row's figure")
ok(f'>{a["n"]} of 30</b><span>market-days logged · 30 planned' in cells[3],
   "market-days logged reads 'n of 30' in the tile text")
eq(a.get("unit"), "market-day", "the Sandbox counts this lane in market-days")

print("\nrule: one row, first")
rule = _section(html, "rule")
ok('<table class="tn-rules cr-rules">' in rule, "the rule is the tennis table pattern")
eq(re.findall(r"<th(?:\s[^>]*)?>(.*?)</th>", rule), ["Rule", "Venue", "Record", "ROI", "Verdict", "Open"],
   "Rule · Venue · Record · ROI · Verdict · Open")
eq(rule.count("<tr"), 2, "one header row and one rule row")
ok('<details class="tn-rule"><summary><b>Favourite band · 3h to the close</b></summary>' in rule,
   "the chevron is the details summary in the Rule cell")
ok(f'{B.pct(a["roi_fee"], sign=True)}</span><div class="sm mut">on {a["n"]} market-days</div>' in rule,
   "ROI sits next to its sample")
dl = re.search(r'<dl class="cr-params">(.*?)</dl>', rule).group(1)
eq(re.findall(r"<dt>(.*?)</dt>", dl), ["Entry", "Selection", "Liquidity", "Close"], "four entry parameters")
eq(re.findall(r"<dd>(.*?)</dd>", dl),
   ["Yes ask 70–80¢, 2–3.5h before the close", "lowest qualifying rung, one per commodity, trading days only",
    "≤3¢ spread, 25+ ask", "WTI 14:30 ET · the rest 17:00 ET"], "the parameters are the registered constants")
note = S.SOURCES["commod_fav_band"]["note"].strip()
ok(f'<p class="tn-def sm mut">{B.esc(note)}</p>' in rule, "the registered definition paragraph is in the row")
ok('data-l="Venue">Kalshi</td>' in rule and 'data-l="Open">1</td>' in rule, "venue and open count")

print("\npicks: one list grouped by trading day")
picks = _section(html, "picks")
days = re.findall(r'<div class="tn-day">(.*?)</div>', picks)
eq(days, ["Today · Oct 8", "Oct 7", "Oct 6"], "today first, then settled days newest first")
today_block = picks.split('<div class="tn-day">Oct 7</div>', 1)[0]
today_rows = re.findall(r'<div class="tn-pick cr-pick([^"]*)" data-series="([^"]+)">', today_block)
eq([s for _c, s in today_rows], list(S.COMMOD_FAV_SERIES), "today lists the six commodities once each, in order")
ok(" is-live" in today_rows[0][0] and "is-next" in today_rows[2][0], "an open bet is live, a watch-only quote is watching")
ok(all("is-muted is-none" in cls for cls, s in today_rows if s in ("KXBRENTD", "KXSILVERD", "KXCOPPERD", "KXNATGASD")),
   "a commodity with no rung today is one muted no-entry line")
wti = re.search(r'<div class="tn-pick cr-pick is-live" data-series="KXWTI">(.*?)</div></div>', today_block, re.S).group(1)
ok('<span class="tn-time">1:30 PM CT</span>' in wti, "WTI's time is its own 14:30 ET close, in the Chicago clock")
ok("WTI · KXWTI" in wti and "<b>WTI above $81.99</b>" in wti, "the pick is the rung named by its commodity")
ok('<span class="tn-price">74¢</span>' in wti and '<span class="tn-state is-live">open</span>' in wti, "price and state")
brent = re.search(r'<div class="tn-pick cr-pick is-muted is-none" data-series="KXBRENTD">(.*?)</div></div>', today_block, re.S).group(1)
ok("4:00 PM CT" in brent and '<span class="tn-state is-none">no entry</span>' in brent
   and '<span class="tn-pos"></span>' in brent, "a no-entry row carries the 17:00 ET close and the state only")
ok("W</span>" in picks and "L</span>" in picks, "settled market-days are rows with W and L states")
eq(picks.count('<div class="tn-pick cr-pick'), 9, "six today, two yesterday, one earlier")
scan = re.search(r'<p class="sm mut cr-scan">(.*?)</p>', picks).group(1)
eq(scan, "Last scan Oct 8, 6:00 AM CT · 180 quotes · next window Oct 8, 10:00–11:30 AM CT (WTI)",
   "one muted scanner line naming the next window and its commodities")
inside = C._scan_status(ledger, datetime.datetime(2026, 10, 8, 15, 30, tzinfo=datetime.timezone.utc))
ok("current window Oct 8, 10:00–11:30 AM CT (WTI)" in inside, "inside the WTI window the line says current")
later = C._scan_status(ledger, datetime.datetime(2026, 10, 8, 17, 0, tzinfo=datetime.timezone.utc))
ok("next window Oct 8, 12:30–2:00 PM CT (Brent + Gold + Silver + Copper + Nat gas)" in later,
   "after WTI's window the next is the 17:00 group's")
friday_night = C._scan_status(ledger, datetime.datetime(2026, 10, 9, 23, 0, tzinfo=datetime.timezone.utc))
ok("next window Oct 12, 10:00–11:30 AM CT (WTI)" in friday_night, "on Friday night the next window is Monday's")
eq(picks.count("<p"), 2, "one sentence of copy and the scanner line, nothing else")

print("\nweekends and holidays")
sat = C.build(ledger, stages, datetime.datetime(2026, 10, 10, 15, tzinfo=datetime.timezone.utc))
sat_days = re.findall(r'<div class="tn-day">(.*?)</div>', _section(sat, "picks"))
ok(sat_days and not sat_days[0].startswith("Today"), "a Saturday is not a market-day, so there is no Today block")
ok("no entry" not in _section(sat, "picks"), "and no six no-entry lines")
thanks = C.build({"quotes": []}, stages, datetime.datetime(2026, 11, 26, 15, tzinfo=datetime.timezone.utc))
ok("No market-day today" in thanks, "a holiday with nothing settled says so once")

print("\nmethod: folded")
method = _section(html, "method")
ok(method.lstrip().startswith("<details>") and "<details open" not in method, "method is one closed fold")
ok("A day is one bet" in method and "+0.89" in method and "+0.84" in method,
   "it states the measured pairs")
ok("trading day" in method and "seven weeks" in method, "it says a market-day is a trading day")
ok("<b>Scheduling.</b>" in method and "10:00–11:30 Central" in method and "12:30–2:00 Central" in method,
   "the two windows are in the scheduling sub-line")
eq(method.count("<p"), 2, "two paragraphs")

print("\nedge cases")
empty = C.build({"quotes": []}, {"pairs": {}}, NOW)
empty_rule = _section(empty, "rule")
ok('<table class="tn-rules cr-rules">' in empty_rule and "Waiting for results" in empty_rule
   and 'data-l="Record" data-empty="1">—</td>' in empty_rule and "Yes ask 70–80¢" in empty_rule,
   "before the first bet the row is the registration itself: no record, the Sandbox's waiting verdict")
ok("No commodities favourite-band record yet." not in empty, "the page never says it has no rule")
ok(empty.count('<div class="tn-pick cr-pick') == len(S.COMMOD_FAV_SERIES) and "no entry" in empty,
   "an empty ledger on a trading day still lists the six commodities as no entry")
ok(">0</b><span>open picks" in empty and ">—</b><span>record" in empty and ">0 of 30</b>" in empty, "empty tiles")
ok("Last scan not recorded · no scanner coverage stored" in empty, "no scan is said once")
with patch.object(S, "COMMOD_FAV_BAND", (0.6, 0.9)), patch.object(S, "COMMOD_FAV_MAX_SPREAD", 0.04):
    const = C.build(ledger, stages, NOW)
    ok("Yes ask 60–90¢" in const and "≤4¢ spread" in const and "70–80¢" not in const,
       "the parameters follow the registered constants")
ok("<script" not in html.split("<main", 1)[-1].split("</main>", 1)[0].replace('<script src="./', ""),
   "no inline script")
published = os.path.join(ROOT, "public_site", "commodities.html")
ok(os.path.exists(published) and 'class="tn-pick cr-pick' in open(published, encoding="utf-8").read(),
   "public_site/commodities.html is built")
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
            eq(page.locator(".tn-pick.cr-pick").count(), 9, f"{width}px nine list rows")
            eq(page.locator("#method > details[open]").count(), 0, f"{width}px method starts closed")
            page.locator("details.tn-rule > summary").click()
            ok(page.locator("details.tn-rule .cr-params").is_visible(), f"{width}px the chevron reveals the parameters")
            page.locator("#method > details > summary").click()
            ok(page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), f"{width}px still fits with both open")
            eq(page.locator("nav.toc a").evaluate_all("a => a.map(x => x.getAttribute('href'))"),
               ["#rule", "#picks", "#method"], f"{width}px sub-nav is Rule / Picks / Method")
            eq(page.locator("nav.main a[aria-current='page']").text_content(), "Commodities", f"{width}px the nav marks the page")
            page.close()
        browser.close()

if FAILS:
    print(f"\nFAILED {len(FAILS)}")
    sys.exit(1)
print("PASS commodities page: tiles, one-row rule table, one picks list, folded method")
