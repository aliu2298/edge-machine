#!/usr/bin/env python3
"""production.html by sport: one fold per sport in the pairs table with the sport's
combined since-Production line, a sport pill row over Coming up and Recently
settled, the next 24h open with later days folded, the last 7 days open with
older leads folded. The fixture is built here; nothing reads data/ or the network.
"""
import datetime
import os
import re
import sys
from datetime import timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import production as P
import sandbox_build as B
import sandbox_sources as S
import sandbox_track as T
import site_chrome

FAILS = []
ROOT = os.path.dirname(os.path.abspath(__file__))
NOW = datetime.datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc)   # 7 AM CT


def ok(cond, why):
    print(f"  {'ok  ' if cond else 'FAIL'} {why}")
    if not cond:
        FAILS.append(why)


def eq(got, want, why):
    ok(got == want, why if got == want else f"{why} — got {got!r}, want {want!r}")


def _bet(i, source, sport, hours, status="won", price=0.6, venue="kalshi"):
    start = NOW + timedelta(hours=hours)
    won = status == "won"
    return dict(
        id=f"{source}:{sport}:{i}", source=source, sport=sport, bet=True, status=status,
        pick="a", price=price, result=("a" if won else "b") if status in ("won", "lost") else None,
        venue=venue, stake=100.0,
        pnl=(round(100 * (1 / price - 1), 2) if won else -100.0) if status in ("won", "lost") else None,
        start=start.isoformat(), logged=(start - timedelta(hours=2)).isoformat(),
        date=start.date().isoformat(), settled=(start + timedelta(hours=3)).isoformat() if status != "open" else None,
        price_a=price, price_b=round(1 - price, 2), side_a="Home", side_b="Away",
        label=f"Home v Away {i}", market_id=f"m-{source}-{i}", url="https://kalshi.com/x",
    )


def _lead(i, pair, hours, status="pending"):
    return dict(
        id=f"lead-{i}", pair=pair, status=status,
        kickoff=(NOW + timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%MZ"),
        league="Fixture League", match=f"Team A{i} v Team B{i}", headline=f"Lead {i}",
        price_at_log=0.55,
    )


# Pairs across four sports, one of them a lane the registry does not know: it
# still lands in a section of its own under its key.
PAIRS = {
    "o15_form_l10|soccer_o15": {"stage": "production", "by_hand": "2026-09-20", "ready_at": "2026-09-20T00:00:00+00:00"},
    "team1_form_l5|soccer_team1_intl": {"stage": "production", "by_hand": "2026-10-08", "ready_at": "2026-10-08T00:00:00+00:00"},
    "oddspedia|cricket": {"stage": "production", "by_hand": "2026-09-25", "ready_at": "2026-09-25T00:00:00+00:00"},
    "tennis_combo2|tennis_combo": {"stage": "production", "by_hand": "2026-10-08", "ready_at": "2026-10-08T00:00:00+00:00"},
    "commodities_fav_band|commodities_fav": {"stage": "production", "by_hand": "2026-10-08", "ready_at": "2026-10-08T00:00:00+00:00"},
}
quotes = []
# Soccer: a settled record since Production, and leads to come.
quotes += [_bet(i, "o15_form_l10", "soccer_o15", -24 * (i + 1), "won" if i < 7 else "lost") for i in range(12)]
quotes += [_bet(i, "team1_form_l5", "soccer_team1_intl", -24 * (i + 1), "won" if i < 2 else "lost") for i in range(3)]
# Cricket: four settled, nothing to come.
quotes += [_bet(i, "oddspedia", "cricket", -24 * (i + 1), "won" if i < 1 else "lost", venue="polymarket_us") for i in range(4)]
# Tennis and Commodities: nothing settled since Production yet.
quotes += [_bet(0, "tennis_combo2", "tennis_combo", 5, "open", venue="combo")]
d = {"quotes": quotes}
st = {"pairs": PAIRS}
LEADS = [
    _lead(1, "o15_form_l10|soccer_o15", 3),                 # today, inside 24h
    _lead(2, "o15_form_l10|soccer_o15", 20),                # inside 24h, tomorrow CT
    _lead(3, "team1_form_l5|soccer_team1_intl", 30),        # later
    _lead(4, "o15_form_l10|soccer_o15", 70),                # later still
    _lead(5, "tennis_combo2|tennis_combo", 6),              # today, tennis
    _lead(6, "oddspedia|cricket", -30, "hit"),              # settled, recent
    _lead(7, "oddspedia|cricket", -24 * 9, "miss"),         # settled, older than 7 days
    _lead(8, "o15_form_l10|soccer_o15", -24 * 2, "miss"),   # settled, recent
    _lead(9, "o15_form_l10|soccer_o15", -24 * 20, "hit"),   # settled, older
]
blob = {"leads": {l["id"]: l for l in LEADS}, "pairs": {}}
html = P.page(d, st, blob, "", now=NOW)
main = html.split("<main", 1)[-1].split("</main>", 1)[0]


def _section(start_id, end_id):
    return main.split(f'id="{start_id}"', 1)[1].split(f'id="{end_id}"', 1)[0]


def _text(fragment):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", fragment)).strip()


print("grouping")
eq(P.sport_group("soccer_o15_intl"), "Soccer", "a soccer twin groups under Soccer")
eq(P.sport_group("commodities_fav"), "Commodities", "the commodities lane groups under Commodities, from its label")
eq(P.sport_group("crypto_fav"), "Crypto", "the crypto lane groups under Crypto")
eq(P.sport_group("tennis_combo"), "Tennis", "a basket lane groups under Tennis")
eq(P.sport_group("made_up_lane"), "made_up_lane", "an unregistered lane is its own group, never dropped")
eq(P.ordered_groups({"Crypto", "Zebra", "Soccer", "Commodities", "Cricket", "Tennis", "Alpha"}),
   ["Soccer", "Cricket", "Tennis", "Crypto", "Commodities", "Alpha", "Zebra"],
   "sections run Soccer, Cricket, Tennis, Crypto, Commodities, then any new sport by name")
eq(P.sport_key("Polymarket US"), "polymarket-us", "a chip token is a slug")

pairs = _section("pairs", "coming-up")
folds = re.findall(r'<details class="fold sport-fold" data-sport="([^"]+)"( open)?>\s*<summary>(.*?)</summary>(.*?)</details>', pairs, re.S)
eq([f[0] for f in folds], ["soccer", "cricket", "tennis", "commodities"],
   "one fold per sport present, in order; Crypto has no pair and is not drawn")
eq([bool(f[1]) for f in folds], [True, False, True, False],
   "a sport with leads to come starts open, the rest folded")
heads = [re.search(r"<h3>(.*?)</h3>", f[2]).group(1) for f in folds]
eq(heads, ["Soccer", "Cricket", "Tennis", "Commodities"], "each fold is headed by its sport")
by_sport = {f[0]: f for f in folds}
for key, want_pairs in (("soccer", 2), ("cricket", 1), ("tennis", 1), ("commodities", 1)):
    body = by_sport[key][3]
    rows = [r for r in re.findall(r"<tr\b[^>]*>(.*?)</tr>", body, re.S) if "<td" in r]
    eq(len(rows), want_pairs, f"{key} holds its own pairs")
    ok('<th rowspan="2">Pair</th>' in body and '<th class="num">CLV</th>' in body,
       f"{key} table keeps the same columns as before")
ok("Commodities · Favourite band" in _text(by_sport["commodities"][3]),
   "the commodities pair sits under its own Commodities section")

print("\nsection totals")
soccer_line = _text(by_sport["soccer"][2])
ok(soccer_line.startswith("Soccer · 2 pairs (1 early)"), f"the soccer line counts pairs and early pairs ({soccer_line})")
soccer_lives = [P._assess_since_kickoff(d, k, PAIRS[k]) for k in PAIRS if k.endswith("soccer_o15") or k.endswith("soccer_team1_intl")]
rec = P._group_record(soccer_lives)
eq((rec["n"], rec["won"]), (sum(l["n"] for l in soccer_lives), sum(l["won"] for l in soccer_lives)),
   "the combined record adds the pairs' since-Production records")
ok(rec["n"] == 13 and rec["won"] == 8,
   "the window is each pair's own: the two bets before the second pair entered are not counted")
ok(f"since Production {T.record_text(rec)}" in soccer_line, "the line prints the combined W–L in the ledger's words")
ok(B.pct(rec["roi_fee"], sign=True) in by_sport["soccer"][2], "the line prints the combined ROI after fees")
ok(f'<span class="{P._tone(rec["roi_fee"], True)}">' in by_sport["soccer"][2]
   and "too early" not in soccer_line, "15 settled: the ROI is coloured, not greyed")
ok(soccer_line.endswith("4 leads to come"), f"the line ends with the sport's leads to come ({soccer_line})")
cricket_line = _text(by_sport["cricket"][2])
ok("1 pair · since Production 1–3" in cricket_line and "too early" in cricket_line
   and '<span class="mut">' in by_sport["cricket"][2] and "0 leads to come" in cricket_line,
   f"under 10 settled the sport ROI is grey and marked too early ({cricket_line})")
tennis_line = _text(by_sport["tennis"][2])
ok("nothing settled since Production" in tennis_line and "1 lead to come" in tennis_line,
   f"a sport with nothing settled says so ({tennis_line})")
ok("· 5 · 3 early · 4 sports" in _text(main.split('id="pairs"', 1)[1][:600]),
   "the Pairs heading counts pairs, early pairs and sports")
tiles = re.search(r'<div class="tiles">(.*?)</div>\s*</div>', main, re.S).group(0)
ok("<b>5</b><span>pairs in Production</span>" in tiles and "<b>5</b><span>leads still to come</span>" in tiles,
   "the stat strip at the top is unchanged")

print("\nchips")
nav = re.search(r'<nav class="sports sport-filter prod-filter"[^>]*data-controls="coming-up recent">(.*?)</nav>', main, re.S)
ok(nav is not None, "one sport pill row controls Coming up and Recently settled")
chips = re.findall(r'<button type="button" data-sport="([^"]+)" aria-pressed="([^"]+)">([^<]+)</button>', nav.group(1) if nav else "")
eq([(c[0], c[2]) for c in chips], [("all", "All"), ("soccer", "Soccer"), ("cricket", "Cricket"), ("tennis", "Tennis")],
   "All then the sports with a lead on either list; Commodities has no lead and no chip")
eq([c[1] for c in chips], ["true", "false", "false", "false"], "All starts pressed")
ok(main.find("prod-filter") < main.find('id="coming-up"') < main.find('id="recent"'),
   "the pills sit above Coming up and Recently settled")
coming = _section("coming-up", "recent")
recent = _section("recent", "held-back")
ok(all(re.search(r'<tr data-sport="(soccer|cricket|tennis)">', r) for r in re.findall(r"<tr[^>]*>", coming) if "data-sport" in r)
   and coming.count('<tr data-sport="') == 5 and recent.count('<tr data-sport="') == 4,
   "every lead row carries its sport token")

print("\ncollapsibles")
day_folds = re.findall(r'<details class="fold"( open)?>\s*<summary>(.*?)<span', coming, re.S)
eq([(_text(f[1]), bool(f[0])) for f in day_folds][:2], [("Today · Oct 9", True), ("Tomorrow · Oct 10", True)],
   "the next 24h is open, by day")
later = re.search(r'<details class="fold later" id="coming-later">\s*<summary>Later<span class="mut sm">([^<]*)</span></summary>(.*?)</details>\s*</details>', coming, re.S)
ok(later is not None and "· 2 leads over 2 days" in later.group(1), "later days fold under one line with their count")
ok(later is not None and "Lead 3" in later.group(2) and "Lead 4" in later.group(2)
   and "Lead 1" not in later.group(2) and "Lead 5" not in later.group(2),
   "the later fold holds exactly the leads past 24h")
ok(later is not None and " open" not in later.group(0).split("<summary>", 1)[0]
   and all(" open" not in m for m in re.findall(r'<details class="fold"[^>]*>', later.group(2))),
   "the later fold and its days start closed")
ok("· 3 in the next 24h" in _text(coming.split("</summary>", 1)[0]), "the Coming up heading says how many are in the next 24h")
main_rows = recent.split('id="recent-older"', 1)[0]
ok("Lead 6" in main_rows and "Lead 8" in main_rows and "Lead 7" not in main_rows and "Lead 9" not in main_rows,
   "Recently settled shows the last 7 days by default")
older = re.search(r'<details class="fold later" id="recent-older">\s*<summary>Older<span class="mut sm">([^<]*)</span></summary>(.*?)</details>', recent, re.S)
ok(older is not None and "· 2 leads before the last 7 days" in older.group(1)
   and "Lead 7" in older.group(2) and "Lead 9" in older.group(2), "older settled leads fold under one line")

print("\nnothing older, nothing later")
quiet = P.page(d, st, {"leads": {l["id"]: l for l in LEADS[:2] + LEADS[5:6]}, "pairs": {}}, "", now=NOW)
ok('id="coming-later"' not in quiet and 'id="recent-older"' not in quiet,
   "without later or older leads neither fold is drawn")
ok("in the next 24h" not in quiet.split('id="coming-up"', 1)[1].split("</summary>", 1)[0],
   "and the heading does not mention the 24h window")

print("\nthe row regexes other tests use")
tags = re.findall(r"<tr[^>]*>", coming)
ok(tags and all(t == "<tr>" or re.fullmatch(r'<tr data-sport="[a-z0-9-]+">', t) for t in tags),
   "lead rows carry their sport token; header rows are bare")

from require_browser import require_browser
playwright = require_browser("test_production_groups.py")
if playwright is not None:
    print("\nin the browser")
    page_html = B.label_cells(html)
    with playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        for width in (1280, 390):
            page = browser.new_page(viewport={"width": width, "height": 900})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))

            def serve(route):
                name = Path(urlparse(route.request.url).path).name
                if name.endswith(".html"):
                    route.fulfill(body=page_html, content_type="text/html")
                else:
                    route.fulfill(path=str(Path(ROOT) / "public_site" / name))
            page.route("http://fixture.local/**", serve)
            page.goto("http://fixture.local/production.html", wait_until="load")
            ok(not errors, f"{width}px: no page error ({errors})")
            ok(page.evaluate("document.documentElement.scrollWidth <= innerWidth"), f"{width}px: no sideways scroll")
            # The sport folds: open where leads are to come, and every pair row inside.
            ok(page.locator('details.sport-fold[data-sport="soccer"][open]').count() == 1
               and page.locator('details.sport-fold[data-sport="cricket"]:not([open])').count() == 1,
               f"{width}px: Soccer is open and Cricket folded")
            # Chips wrap in their row; none is clipped.
            inside = page.evaluate("""() => [...document.querySelectorAll('nav.prod-filter button')].every(b => {
                const r = b.getBoundingClientRect(); return r.left >= 0 && r.right <= innerWidth && r.height >= 36; })""")
            ok(inside, f"{width}px: every chip is inside the viewport and tappable")

            def visible(selector):
                # checkVisibility is false inside a closed <details> and for a hidden row.
                return page.evaluate("""(sel) => [...document.querySelectorAll(sel)].filter(r => !r.hidden && r.checkVisibility()).length""", selector)
            eq(visible('#coming-up tr[data-sport]'), 3, f"{width}px: with All pressed the next 24h shows its 3 leads")
            page.locator('nav.prod-filter button[data-sport="cricket"]').click()
            eq(page.locator('nav.prod-filter button[aria-pressed="true"]').get_attribute("data-sport"), "cricket",
               f"{width}px: the pressed chip moves")
            eq(visible('#coming-up tr[data-sport]'), 0, f"{width}px: Cricket has nothing coming up")
            ok(page.locator('#coming-up .sport-filter-empty:not([hidden])').count() == 1
               and "No Cricket lead here." in page.locator('#coming-up .sport-filter-empty').text_content(),
               f"{width}px: an emptied list says so")
            ok(page.locator('#coming-up details.fold:not(.sec)[hidden]').count()
               == page.locator('#coming-up details.fold:not(.sec)').count() == 5,
               f"{width}px: the emptied day folds, the Later fold and its days are all hidden")
            eq(visible('#recent tr[data-sport="cricket"]'), 1, f"{width}px: Recently settled keeps the cricket row")
            eq(visible('#recent tr[data-sport="soccer"]'), 0, f"{width}px: and hides the soccer rows")
            page.locator('nav.prod-filter button[data-sport="soccer"]').click()
            eq(visible('#coming-up tr[data-sport="soccer"]'), 2, f"{width}px: Soccer shows its two leads in the next 24h")
            page.evaluate("() => document.querySelectorAll('#coming-later, #coming-later details').forEach(d => { d.open = true; })")
            eq(visible('#coming-later tr[data-sport="soccer"]'), 2, f"{width}px: and both later soccer leads once Later is opened")
            page.locator('nav.prod-filter button[data-sport="all"]').click()
            eq(visible('#coming-up tr[data-sport]'), 5, f"{width}px: All brings every row back")
            ok(page.locator('.sport-filter-empty:not([hidden])').count() == 0, f"{width}px: and the empty notes go")
            page.close()
        browser.close()

if FAILS:
    print(f"\nFAILED {len(FAILS)}")
    sys.exit(1)
print("\nPASSED")
