#!/usr/bin/env python3
"""Phase 1 of the redesign: one token set, two themes, and the layout fixes.

- site.css defines the palette once as custom properties on :root (dark), and
  again for the light theme under prefers-color-scheme and html[data-theme];
  no rule outside the token blocks carries a colour of its own.
- Every page carries one theme toggle; tables.js applies a remembered choice
  (localStorage, wrapped) and the toggle flips it.
- The page pills never clip: they wrap from 641px up and scroll under 641px.
- A record stat tile's big number is the W–L; a no-result count sits in the label.
- A Production pair row is a few lines tall, with the light's word beside its dot.
- One container width on every page.
- Every sport page's sub-nav is Rules · Events · Method.
Builds in memory; nothing reads data/ except the committed site.css and the
scripts. The browser checks need Chromium.
"""
import datetime
import os
import re
import sys
from datetime import timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import sandbox_build as B
import sandbox_sources as S
import site_chrome
import tennis_cards as TN

FAILS = []
ROOT = os.path.dirname(os.path.abspath(__file__))
NOW = datetime.datetime(2026, 10, 11, 18, 0, tzinfo=timezone.utc)


def ok(cond, why):
    print(f"  {'ok  ' if cond else 'FAIL'} {why}")
    if not cond:
        FAILS.append(why)


def eq(got, want, why):
    ok(got == want, why if got == want else f"{why} — got {got!r}, want {want!r}")


css = open(os.path.join(ROOT, "public_site", "site.css"), encoding="utf-8").read()
js = open(os.path.join(ROOT, "public_site", "tables.js"), encoding="utf-8").read()

print("tokens")
root = re.search(r":root \{(.*?)\n\}", css, re.S).group(1)
tokens = dict(re.findall(r"--([a-z0-9-]+):\s*([^;]+);", root))
for name in ("bg", "card", "raised", "line", "fg", "mut", "acc", "pos", "neg", "warn", "att",
             "pos-bg", "neg-bg", "warn-bg", "att-bg", "bar-bg", "font", "r", "page-w"):
    ok(name in tokens, f"--{name} is a token on :root")
eq(tokens.get("page-w"), "1120px", "one page width token")
ok("color-scheme: dark" in root, "dark is the default scheme")
light_media = re.search(r"@media \(prefers-color-scheme: light\) \{\s*:root:not\(\[data-theme=\"dark\"\]\) \{(.*?)\n  \}", css, re.S)
light_set = re.search(r":root\[data-theme=\"light\"\] \{(.*?)\n\}", css, re.S)
ok(light_media is not None, "a light device preference gets the light theme unless dark was chosen")
ok(light_set is not None, "a chosen light theme applies whatever the device says")
if light_media and light_set:
    a = dict(re.findall(r"--([a-z0-9-]+):\s*([^;]+);", light_media.group(1)))
    b = dict(re.findall(r"--([a-z0-9-]+):\s*([^;]+);", light_set.group(1)))
    eq(a, b, "the two light blocks set the same tokens to the same values")
    ok(a.get("bg") != tokens.get("bg") and a.get("fg") != tokens.get("fg"), "light and dark differ")
    ok(all(k in tokens for k in a), "the light theme overrides only tokens the dark theme defines")
    ok("color-scheme: light" in light_set.group(1), "the light theme tells the browser its scheme")
body = css.split("\n}", 1)[1]
body = body.split(":root[data-theme=\"light\"] {", 1)[1].split("\n}", 1)[1]
stray = [ln for ln in body.splitlines()
         if re.search(r"#[0-9a-fA-F]{3,8}\b|rgba?\(", ln) and "var(--" not in ln
         and not ln.strip().startswith(("/*", "*", "--"))]
eq(stray, [], "no rule outside the token blocks carries a colour of its own")
for name in (".theme-toggle", ".eyebrow", ".scope", ".card", ".badge.stage", ".badge.status.waiting",
             ".badge.status.stale", ".badge.status.attention", ".badge.status.healthy", ".fig", "td.light"):
    ok(name in css, f"shared component {name} is styled")

print("\nthe toggle and the scripts")
page = site_chrome.document("Edge Machine · Fixture", "fixture", "sandbox",
                            (("a", "A"), ("b", "B")), site_chrome.stamp(NOW), "<p>hi</p>")
eq(page.count('class="theme-toggle"'), 1, "every page carries one theme toggle")
ok('data-theme-toggle' in page and 'aria-label="Switch theme"' in page, "the toggle is a labelled button")
ok('<meta name="color-scheme" content="dark light">' in page, "the page declares both schemes")
ok(page.find('class="subbar"') > page.find('class="topbar"') and page.find("theme-toggle") > page.find('class="toc"'),
   "the toggle sits in the second header row, after the section nav")
stored = js.split("function storedTheme", 1)[1].split("function rememberTheme", 1)[0]
ok("function wireTheme" in js and 'THEME_KEY = "edge-theme"' in js and "localStorage.getItem(THEME_KEY)" in stored
   and "try {" in stored and "catch (e)" in stored,
   "tables.js reads the remembered theme inside a try")
ok("rememberTheme" in js and "setItem" in js and "prefers-color-scheme: light" in js,
   "tables.js remembers a choice and reads the device preference")
ok("wireTheme: wireTheme" in js and "api.wireTheme(document)" in js, "the theme is wired on every page that loads tables.js")

print("\nthe record tile")
eq(TN.record_tile(dict(n=21, won=13, n_price=6), "record · Oddspedia community tips"),
   '<div class="tile"><b>13–8</b><span>record · Oddspedia community tips · 6 no result</span></div>',
   "the W–L is the big number and the no-result count goes in the label")
eq(TN.record_tile(dict(n=5, won=3), "record · W–L"),
   '<div class="tile"><b>3–2</b><span>record · W–L</span></div>', "with no no-result bet the label is plain")
eq(TN.record_tile({}, "record · W–L"), '<div class="tile"><b>—</b><span>record · W–L</span></div>',
   "nothing settled is an em dash")
for src in ("cricket_cards.py", "tennis_cards.py", "crypto_build.py", "commodities_build.py"):
    text = open(os.path.join(ROOT, src), encoding="utf-8").read()
    ok("record_tile(" in text and "<b>{B.esc(rec)}</b>" not in text and "<b>{esc(TN.record_text(a))}</b>" not in text,
       f"{src} builds its record tile through the helper")

print("\nthe sub-nav vocabulary")
import soccer_build, tennis_build, cricket_build, crypto_build, commodities_build
built = {
    "soccer": soccer_build.build({"quotes": []}, {"pairs": {}}, NOW),
    "tennis": tennis_build.build({"quotes": []}, {"pairs": {}}, NOW),
    "cricket": cricket_build.build({"quotes": []}, {"pairs": {}}, NOW),
    "crypto": crypto_build.build({"quotes": []}, {"pairs": {}}, NOW),
    "commodities": commodities_build.build({"quotes": []}, {"pairs": {}}, NOW),
}
for name, html in built.items():
    toc = re.search(r'<nav class="toc"[^>]*>(.*?)</nav>', html, re.S)
    labels = re.findall(r'<a href="#([a-z]+)">([^<]+)</a>', toc.group(1)) if toc else []
    eq(labels, [("rules", "Rules"), ("events", "Events"), ("method", "Method")], f"{name} sub-nav is Rules · Events · Method")
    ok(all(f'id="{i}"' in html for i in ("rules", "events", "method")), f"{name} has the three sections")
    for old in ('id="fixtures"', 'id="matches"', 'id="system"', 'id="health"', 'id="picks"', 'id="rule"'):
        ok(old not in html, f"{name} no longer has {old}")

print("\nthe Production row")
import production as P
import sandbox_track as T
pairs = {"o15_form_l10|soccer_o15": {"stage": "production", "by_hand": "2026-09-20", "ready_at": "2026-09-20T00:00:00+00:00"}}
quotes = []
for i in range(6):
    start = NOW - timedelta(days=i + 1)
    quotes.append(dict(id=f"q{i}", source="o15_form_l10", sport="soccer_o15", bet=True, status="won" if i < 4 else "lost",
                       pick="a", price=0.6, result="a" if i < 4 else "b", venue="kalshi", stake=100.0,
                       pnl=66.67 if i < 4 else -100.0, start=start.isoformat(),
                       logged=(start - timedelta(hours=2)).isoformat(), date=start.date().isoformat(),
                       settled=(start + timedelta(hours=3)).isoformat(), price_a=0.6, price_b=0.4,
                       side_a="Home", side_b="Away", label=f"Home v Away {i}", market_id=f"m{i}", url="https://kalshi.com/x"))
# The pair's light is red with the longest reason the column carries ("6 of 6 recent
# bets cannot be published — the feed drops them silently"), so the row the browser
# measures below is the tallest a pair row gets.
prod = P.page({"quotes": quotes}, {"pairs": pairs}, {"leads": {}, "pairs": {}}, "", now=NOW)
row = re.search(r'<tr>\s*<td><b>Over 1\.5 form rule.*?</tr>', prod, re.S).group(0)
light = re.search(r'<td class="num light">(.*?)</td>', row, re.S)
ok(light is not None and re.fullmatch(r'<b class="(pos|neg)">●</b> <span class="sm mut">[^<]+</span>', light.group(1).strip()),
   "the light cell is the dot and its word on one line, not a stacked note")
ok('class="sm mut wrap"' not in prod and ".num .sub {" in css and ".num .wrap" not in css,
   "no cell borrows the page container's .wrap class any more")

from require_browser import require_browser
playwright = require_browser("test_design_system.py")
if playwright is not None:
    print("\nin the browser")
    pages = {
        "production.html": B.label_cells(prod),
        "soccer.html": built["soccer"],
        "cricket.html": cricket_build.build({"quotes": [dict(q, source="oddspedia", sport="cricket", venue="polymarket_us",
                                                             id=f"c{q['id']}", market_id=f"c{q['market_id']}",
                                                             status="settled" if q["id"] in ("q4", "q5") else q["status"],
                                                             result="price" if q["id"] in ("q4", "q5") else q["result"],
                                                             settle_px=0.5 if q["id"] in ("q4", "q5") else None,
                                                             pnl=-16.67 if q["id"] in ("q4", "q5") else q["pnl"])
                                                        for q in quotes]},
                                            {"pairs": {"oddspedia|cricket": {"stage": "production", "by_hand": "2026-09-20",
                                                                            "ready_at": "2026-09-20T00:00:00+00:00"}}}, NOW),
    }
    with playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)

        def serve(html):
            def route_it(route):
                name = Path(urlparse(route.request.url).path).name
                if name.endswith(".html"):
                    route.fulfill(body=html, content_type="text/html")
                else:
                    route.fulfill(path=str(Path(ROOT) / "public_site" / name))
            return route_it

        # Both themes render, follow the device, and the toggle flips and remembers.
        seen = {}
        for scheme in ("dark", "light"):
            page = browser.new_page(viewport={"width": 1280, "height": 900}, color_scheme=scheme)
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.route("http://fixture.local/**", serve(pages["soccer.html"]))
            page.goto("http://fixture.local/soccer.html", wait_until="load")
            seen[scheme] = page.evaluate("getComputedStyle(document.body).backgroundColor")
            ok(not errors, f"{scheme}: no page error ({errors})")
            eq(page.evaluate("document.documentElement.getAttribute('data-theme')"), None,
               f"{scheme}: with nothing remembered the page follows the device")
            eq(page.locator(".theme-toggle").text_content(), "Light" if scheme == "dark" else "Dark",
               f"{scheme}: the toggle offers the other theme")
            page.locator(".theme-toggle").click()
            flipped = page.evaluate("getComputedStyle(document.body).backgroundColor")
            ok(flipped != seen[scheme], f"{scheme}: the toggle changes the page")
            eq(page.evaluate("document.documentElement.getAttribute('data-theme')"),
               "light" if scheme == "dark" else "dark", f"{scheme}: the choice is on the html element")
            eq(page.evaluate("(() => { try { return localStorage.getItem('edge-theme'); } catch (e) { return 'no storage'; } })()"),
               "light" if scheme == "dark" else "dark", f"{scheme}: the choice is remembered")
            page.reload(wait_until="load")
            ok(page.evaluate("getComputedStyle(document.body).backgroundColor") == flipped,
               f"{scheme}: the remembered choice survives a reload")
            page.close()
        ok(seen["dark"] != seen["light"], f"the two themes draw different pages ({seen})")
        ok(seen["dark"] == "rgb(11, 12, 15)" and seen["light"] == "rgb(245, 248, 244)",
           "dark is the dark page and light is the off-white page")

        # The nav never clips: it wraps when squeezed from 641px up (at 900 and
        # 768 it must), scrolls in one row at 390, and every pill can be shown.
        for width in (1070, 900, 768, 390):
            page = browser.new_page(viewport={"width": width, "height": 800})
            page.route("http://fixture.local/**", serve(pages["soccer.html"]))
            page.goto("http://fixture.local/soccer.html", wait_until="load")
            got = page.evaluate("""() => {
                const nav = document.querySelector('nav.main');
                const pills = [...nav.querySelectorAll('a')];
                const inside = pills.every(a => { a.scrollIntoView({inline: 'nearest', block: 'nearest'});
                    const r = a.getBoundingClientRect(); const n = nav.getBoundingClientRect();
                    return r.left >= n.left - 1 && r.right <= n.right + 1 && r.right <= innerWidth + 1; });
                return { inside, overflow: document.documentElement.scrollWidth > innerWidth,
                         rows: new Set(pills.map(a => Math.round(a.getBoundingClientRect().top))).size,
                         scrolls: nav.scrollWidth > nav.clientWidth + 1,
                         method: pills[pills.length - 1].textContent };
            }""")
            ok(got["inside"] and not got["overflow"], f"{width}px: every page pill can be shown whole, nothing clipped ({got})")
            eq(got["method"], "Method", f"{width}px: Method is still the last pill")
            if width > 640:
                ok(not got["scrolls"], f"{width}px: the pills do not scroll ({got})")
                if width <= 900:
                    ok(got["rows"] >= 2, f"{width}px: the pills wrap onto more rows ({got})")
            else:
                ok(got["rows"] == 1 and got["scrolls"], f"{width}px: the pills scroll in one row ({got})")
            page.close()

        # One container width on every page.
        widths = {}
        for name, html in pages.items():
            page = browser.new_page(viewport={"width": 1280, "height": 800})
            page.route("http://fixture.local/**", serve(html))
            page.goto(f"http://fixture.local/{name}", wait_until="load")
            widths[name] = page.evaluate("Math.round(document.querySelector('main').getBoundingClientRect().width)")
            page.close()
        eq(len(set(widths.values())), 1, f"every page's container is the same width ({widths})")
        eq(set(widths.values()), {1120}, "the container is the 1120px token")

        # The Production row and the record tile.
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.route("http://fixture.local/**", serve(pages["production.html"]))
        page.goto("http://fixture.local/production.html", wait_until="load")
        got = page.evaluate("""() => {
            const t = document.querySelector('#pairs table'); const tr = t.tBodies[0].rows[0];
            const cell = tr.querySelector('td.light'); const dot = cell.querySelector('b'); const word = cell.querySelector('span');
            const first = word.getClientRects()[0];   // the word's first line box, if it wraps
            const tables = [...document.querySelectorAll('#pairs table')];
            return { rowH: Math.round(tr.getBoundingClientRect().height),
                     sameLine: Math.abs(dot.getBoundingClientRect().top - first.top) < 6
                               && first.left >= dot.getBoundingClientRect().right - 1,
                     gap: Math.round(t.tBodies[0].rows[0].getBoundingClientRect().top - t.tHead.getBoundingClientRect().bottom),
                     cols: [...tr.cells].map(c => Math.round(c.getBoundingClientRect().width)),
                     lines: [...tr.cells].map(c => { const r = document.createRange(); r.selectNodeContents(c);
                                                     return new Set([...r.getClientRects()].map(b => Math.round(b.top))).size; }),
                     pair: tr.cells[0].textContent.trim().replace(/\s+/g, ' '),
                     // every sport's pairs table fits its card: no in-card scrolling, where the header cannot stick
                     fits: tables.every(x => x.getBoundingClientRect().width <= x.parentElement.getBoundingClientRect().width + 1
                                             && !x.parentElement.classList.contains('scroll-x')) };
        }""")
        # The runner's fonts differ from a desktop's; the font the row was drawn with goes in the report.
        try:
            cdp = page.context.new_cdp_session(page)
            cdp.send("DOM.enable"); cdp.send("CSS.enable")
            root = cdp.send("DOM.getDocument", {"depth": -1})["root"]["nodeId"]
            node = cdp.send("DOM.querySelector", {"nodeId": root, "selector": "body"})["nodeId"]
            got["font"] = [f["familyName"] for f in cdp.send("CSS.getPlatformFontsForNode", {"nodeId": node})["fonts"]]
        except Exception as e:  # the report is richer with the font, the checks do not need it
            got["font"] = f"unknown ({type(e).__name__})"
        ok(got["rowH"] <= 140, f"a Production pair row with the longest light reason is under 140px tall ({got['rowH']}px, was 205px; font {got['font']}, columns {got['cols']}, lines {got['lines']}, pair {got['pair']!r})")
        ok(got["sameLine"], f"the light's word sits beside its dot ({got})")
        ok(abs(got["gap"]) <= 1, f"no empty band between the header rows and the first pair ({got['gap']}px)")
        ok(got["fits"], f"every pairs table fits its card, whatever the font (columns {got['cols']})")
        ok(got["cols"][0] >= 220, f"the pair's name keeps its column ({got['cols'][0]}px, floor 220)")
        page.close()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.route("http://fixture.local/**", serve(pages["cricket.html"]))
        page.goto("http://fixture.local/cricket.html", wait_until="load")
        got = page.evaluate("""() => { const t = [...document.querySelectorAll('.tile')].find(t => t.textContent.includes('no result'));
            if (!t) return null; const b = t.querySelector('b'); const line = parseFloat(getComputedStyle(b).lineHeight) || 36;
            return { big: b.textContent, lines: Math.round(b.getBoundingClientRect().height / line), label: t.querySelector('span').textContent }; }""")
        ok(got is not None and got["lines"] == 1 and "no result" not in got["big"] and "no result" in got["label"],
           f"the cricket record tile keeps its big number on one line, the no-result count in the label ({got})")
        browser.close()

if FAILS:
    print(f"\nFAILED {len(FAILS)}")
    sys.exit(1)
print("\nPASSED")
