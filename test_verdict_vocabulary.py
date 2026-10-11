#!/usr/bin/env python3
"""Redesign phase 4: one verdict vocabulary, and the Rule scorecard on the Control Center.

The ladder every page prints, read off sandbox_build.verdict() (the grading is unchanged):
  Too early                     under 10 settled, nothing settled included
  Collecting n/30 · Promising   10 to 29 settled, ahead so far
  Collecting n/30 · Behind      10 to 29 settled, not ahead
  Working | No edge | Proven    30 settled and over
sport_page.verdict_badge is the one renderer: the sport pages, the Sandbox and trading
tables, the tennis cards, the shell's rule cards and the scorecard all go through it.

The scorecard lists every rule on the pages with stage, open, settled (a market-day for
crypto and commodities, a match for the corners ladder, a basket for a combo, a bet
otherwise), record, Won v priced, ROI after fees, Evidence n/30 and the verdict, under the
chips All · Production · With records · 30+. No network.
"""
import datetime
import glob
import os
import re
import sys
import threading
from datetime import timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import control_center as CC
import sandbox_build as B
import sandbox_sources as S
import sport_page as SP

FAILS = []
ROOT = os.path.dirname(os.path.abspath(__file__))
NOW = datetime.datetime(2026, 10, 11, 22, 0, tzinfo=timezone.utc)
OLD_WORDS = ("Proven edge", "Behind so far", "Waiting for results", "No qualifying match yet",
             "Waiting for trades")


def ok(cond, why):
    print(f"  {'ok  ' if cond else 'FAIL'} {why}")
    if not cond:
        FAILS.append(why)


def eq(got, want, why):
    ok(got == want, why if got == want else f"{why} — got {got!r}, want {want!r}")


def _a(n, won=0, expected=0.0, z=0.0, roi=None, unit="bet", n_price=0, n_bets=None):
    return dict(n=n, won=won, expected=expected, z=z, roi_fee=roi, unit=unit,
                n_price=n_price, n_bets=n if n_bets is None else n_bets)


print("the ladder")
eq(SP.verdict_label("waiting", 0), ("Too early", "n"), "nothing settled is Too early")
eq(SP.verdict_label("nobets", 0), ("Too early", "n"), "no qualifying match yet is Too early too")
eq(SP.verdict_label("early", 9), ("Too early", "n"), "nine settled is Too early")
eq(SP.verdict_label("promising", 10), ("Collecting 10/30 · Promising", "w"), "ten settled, ahead: Collecting 10/30 · Promising")
eq(SP.verdict_label("behind", 29), ("Collecting 29/30 · Behind", "n"), "29 settled, not ahead: Collecting 29/30 · Behind")
eq(SP.verdict_label("working", 30), ("Working", "y"), "30 settled and ahead: Working")
eq(SP.verdict_label("noedge", 44), ("No edge", "x"), "30+ and not ahead: No edge")
eq(SP.verdict_label("proven", 61), ("Proven", "y"), "30+ and z 2 or over: Proven")
eq(SP.verdict_label("promising", 12, floor=30), SP.verdict_label("promising", 12), "the floor is 30 by default")
eq(SP.verdict_label("removed", 5)[0], "Removed from Production", "Removed keeps its own words: it is a stage, not a step")
eq(SP.verdict_label("retired", 40)[0], "Retired", "Retired keeps its own word")
eq(SP.verdict_label("build_fail", 500)[0], "Fails BUILD", "Fails BUILD keeps its own words")
eq(SP.TOO_EARLY_N, 10, "Too early is under 10")
eq(SP.EVIDENCE_FLOOR, 30, "the read floor is 30")

print("\nthe ladder is verdict()'s grading, unchanged")
cases = [
    (_a(0), "Too early"),
    (_a(9, won=7, expected=4.0, z=1.5, roi=0.4), "Too early"),
    (_a(10, won=7, expected=5.0, z=1.2, roi=0.2), "Collecting 10/30 · Promising"),
    (_a(20, won=8, expected=10.0, z=-0.8, roi=-0.1), "Collecting 20/30 · Behind"),
    (_a(29, won=15, expected=14.0, z=0.3, roi=-0.02), "Collecting 29/30 · Behind"),
    (_a(30, won=18, expected=16.0, z=0.9, roi=0.05), "Working"),
    (_a(30, won=14, expected=16.0, z=-0.9, roi=-0.05), "No edge"),
    (_a(60, won=40, expected=30.0, z=2.4, roi=0.2), "Proven"),
]
for a, want in cases:
    eq(SP.verdict_text(dict(v=B.verdict(a), a=a)), want, f"n={a['n']} z={a['z']:+.1f} reads {want}")

print("\nthe badge")
row = dict(v="promising", a=_a(14))
eq(SP.verdict_badge(row), '<span class="sig w" data-verdict="promising">Collecting 14/30 · Promising</span>',
   "the badge is the chip, the key and the words")
eq(SP.verdict_badge(dict(v="behind", a={"n": 12}), floor=30), SP.verdict_badge(dict(v="behind", a=_a(12))),
   "a row needs only v and a.n")
ok("Too early" in SP.verdict_badge(dict(v="waiting")), "a row with no record at all is Too early")
for key in ("proven", "working", "promising", "behind", "early", "noedge", "waiting", "nobets"):
    ok(B.VERDICTS[key][0] in {w for w, _c in SP.VERDICT_WORDS.values()},
       f"sandbox_build.VERDICTS[{key!r}] carries a word of the one vocabulary")
import market_track as MT
for key in MT.VERDICTS:
    ok(MT.VERDICTS[key][0] in {w for w, _c in SP.VERDICT_WORDS.values()},
       f"market_track.VERDICTS[{key!r}] carries a word of the one vocabulary")

print("\nverdict_badge is the one renderer")
sources = [p for p in glob.glob(os.path.join(ROOT, "*.py")) if not os.path.basename(p).startswith("test_")]
chip_builders = [os.path.basename(p) for p in sources if 'class="sig {chip}"' in open(p, encoding="utf-8").read()]
eq(chip_builders, ["sport_page.py"], "only sport_page builds a verdict chip")
import tennis_cards
row = dict(v="behind", a=_a(17), sport="tennis")
eq(tennis_cards.verdict_html(row), SP.verdict_badge(row), "the tennis cards print the same badge")
ok(SP.verdict_badge(dict(v="promising", a={"n": 14}), floor=MT.READ_FLOOR).endswith("Collecting 14/30 · Promising</span>"),
   "a trading rule at 14 entry days reads Collecting 14/30 · Promising")

print("\nno page prints the old words")
pages = sorted(glob.glob(os.path.join(ROOT, "public_site", "*.html")))
ok(len(pages) >= 8, f"the built pages are on disk ({len(pages)})")
for path in pages:
    html = open(path, encoding="utf-8").read()
    found = [w for w in OLD_WORDS if w in html]
    eq(found, [], f"{os.path.basename(path)} carries none of the old verdict words")
sandbox_html = open(os.path.join(ROOT, "public_site", "sandbox.html"), encoding="utf-8").read()
ok("Collecting n/30" in sandbox_html, "the Sandbox method names the Collecting step")

# ---------------------------------------------------------------------------
print("\nthe scorecard model")
# ---------------------------------------------------------------------------


def _row(name, sport, a, prod=False, open_n=0, v=None):
    return dict(name=name, sport=sport, a=a, prod=prod, open=open_n, v=v or B.verdict(a),
                meta=dict(S.SOURCES.get(name) or {"label": name}), early=None, gone=None,
                moved="2026-10-11" if prod else "")


rows = [
    _row("o15_ranked", "soccer_o15", _a(34, won=27, expected=24.0, z=1.3, roi=0.08), prod=True, open_n=3),
    _row("u35_low_scoring", "soccer_u35", _a(13, won=11, expected=9.0, z=1.1, roi=0.16), prod=True, open_n=4),
    _row("crypto_fav_band", "crypto_fav", _a(5, won=4, expected=3.6, z=0.4, roi=0.02, unit="market-day", n_bets=11)),
    _row("corners_under", "soccer_corners", _a(14, won=8, expected=7.5, z=0.2, roi=0.04, unit="match", n_bets=35)),
    _row("tennis_combo2", "tennis_combo", _a(4, won=1, expected=1.4, z=-0.4, roi=-0.17), open_n=1),
    _row("cricket_consensus", "cricket", _a(0)),
    _row("oddspedia", "cricket", _a(0, n_price=2)),
]
sc = CC.scorecard_rows(rows)
eq([e["name"] for e in sc][:2], [B.rule_name(rows[0]), B.rule_name(rows[1])],
   "Production first, the most evidence first within it")
eq([e["stage"] for e in sc], ["production", "production"] + ["sandbox"] * 5, "then the Sandbox")
eq([e["n"] for e in sc[2:]], [14, 5, 4, 0, 0], "the Sandbox by evidence, most first")
by = {e["row"]["name"]: e for e in sc}
eq(by["crypto_fav_band"]["unit"], "market-day", "crypto counts market-days")
eq(by["corners_under"]["unit"], "match", "the corners ladder counts matches, the unit assess() counts")
eq(by["tennis_combo2"]["unit"], "basket", "a combo counts baskets")
eq(by["o15_ranked"]["unit"], "bet", "anything else counts bets")
eq(SP.unit_count(1, "basket"), "1 basket", "one basket")
eq(SP.unit_count(3, "match"), "3 matches", "three matches")
eq(SP.unit_count(12, "market-day"), "12 market-days", "twelve market-days")
eq((by["oddspedia"]["records"], by["cricket_consensus"]["records"]), (True, False),
   "a no-result payout is a record; nothing settled is not")
eq((by["o15_ranked"]["read"], by["u35_low_scoring"]["read"]), (True, False), "30+ is the read floor")
eq(CC.scorecard_counts(sc), {"all": 7, "production": 2, "records": 6, "read": 1}, "the chips' counts")
eq(by["u35_low_scoring"]["win_rate"], 11 / 13, "the win rate is won over settled")
eq(by["cricket_consensus"]["win_rate"], None, "and none with nothing settled")

print("\nthe scorecard table")
html = CC._scorecard_html(sc)
head = re.findall(r"<th[^>]*>([^<]+)</th>", html)
eq(head, ["Rule", "Stage", "Open", "Settled", "Record", "Won v priced", "ROI after fees", "Evidence", "Verdict"],
   "columns: rule, stage, open, settled, record, Won v priced, ROI after fees, evidence, verdict")
chips = re.findall(r'<button type="button" data-value="([^"]+)" aria-pressed="(true|false)">([^<]+)<span class="count">(\d+)</span>', html)
eq([(v, label.strip(), int(n)) for v, _p, label, n in chips],
   [("all", "All", 7), ("production", "Production", 2), ("records", "With records", 6), ("read", "30+", 1)],
   "chips All · Production · With records · 30+, each with its count")
eq([p for _v, p, _l, _n in chips], ["true", "false", "false", "false"], "All starts pressed")
trs = re.findall(r'<tr class="cc-rule"[^>]*>.*?</tr>', html, re.S)
eq(len(trs), 7, "one row per rule")
prod_tr = trs[0]
ok('data-stage="production" data-records="1" data-read="1"' in prod_tr, "the row carries what the chips filter on")
cells = re.findall(r"<td[^>]*>(.*?)</td>", prod_tr, re.S)
ok("Production" in cells[1], "stage: the Production badge")
eq(re.sub(r"<[^>]+>", "", cells[2]), "3", "open")
eq(re.sub(r"<[^>]+>", "", cells[3]), "34 bets", "settled, in its unit")
ok(cells[4].startswith("27–7") and 'class="sm mut cc-winrate">79% won<' in cells[4],
   "record, with the win rate only as a grey sub-line")
ok(cells[5].startswith(SP.won_v_priced(rows[0]["a"])) and '<div class="sm">z +1.30</div>' in cells[5],
   "Won v priced with z beside it, not greyed")
eq(cells[6], SP.roi_html(rows[0]), "ROI after fees is the Sandbox row's own")
eq(cells[7], "34/30", "evidence n/30")
eq(cells[8], SP.verdict_badge(rows[0]), "the verdict is verdict_badge")
crypto_tr = next(t for t in trs if "Favourite band" in t or "crypto_fav" in t)
ok(">5 market-days<" in crypto_tr and ">11 bets<" in crypto_tr, "a market-day count names the bets under it")
combo_tr = next(t for t in trs if 'data-sport="tennis_combo"' in t)
ok(">4 baskets<" in combo_tr and ">Combo</span>" in combo_tr, "a combo row counts baskets and wears its Combo badge")
empty_tr = next(t for t in trs if 'data-records="0"' in t)
ok('data-verdict="waiting">Too early<' in empty_tr or 'data-verdict="nobets">Too early<' in empty_tr,
   "a rule with nothing settled reads Too early")
ok("cc-winrate" not in empty_tr and "z " not in re.sub(r"<[^>]+>", " ", empty_tr), "and has no win rate or z")
ok('href="./soccer.html"' in prod_tr and 'href="./crypto.html"' in crypto_tr, "each rule links its sport page")
eq(CC._scorecard_html([]), '<p class="shell-empty">No rule has a record yet.</p>', "no rules, one line")

print("\nthe scorecard on the Control Center")
q = dict(id="o15_ranked:soccer_o15:1", source="o15_ranked", sport="soccer_o15", bet=True, status="won",
         pick="a", price=0.6, venue="kalshi_binary", market_id="KXEPLTOTAL-26OCT05AAABBB-2",
         label="Alpha v Beta: over 1.5 goals", side_a="Yes", side_b="No",
         start="2026-10-05T14:00:00+00:00", logged="2026-10-05T06:00:00+00:00", date="2026-10-05",
         stake=100.0, pnl=66.67, result="a", settled="2026-10-05T17:00:00+00:00",
         league="Premier League", espn_home="Alpha", espn_away="Beta", start_source="espn")
d = {"quotes": [q], "coverage": {}, "meta": {"updated": NOW.isoformat()}}
st = {"pairs": {"o15_ranked|soccer_o15": {"stage": "production", "by_hand": "2026-10-01",
                                          "ready_at": "2026-10-01T00:00:00+00:00",
                                          "promoted_at": "2026-10-01T00:00:00+00:00"}}}
m = CC.model(d, st, {"leads": {}, "pairs": {}}, NOW, nba={}, market={}, closes={})
want = [r for r in B.pair_list(d, st) if not B.eliminated(r)]
eq(len(m["scorecard"]), len(want), "the scorecard covers every rule on the pages")
eq(m["scorecard"][0]["row"]["name"], "o15_ranked", "the Production rule leads")
page = CC.page(NOW, d=d, st=st, blob={"leads": {}, "pairs": {}}, nba={}, market={}, closes={})
ok('<section id="scorecard"' in page and '<h2 id="scorecard-title">Rule scorecard</h2>' in page,
   "the page carries the Rule scorecard section")
ok(page.index('id="live-title"') < page.index('id="scorecard-title"'), "after Live now")
eq(page.count('<tr class="cc-rule"'), len(want), "one row per rule on the page")
ok('<script src="./tables.js"' in page, "tables.js, which wires the chips, is on the page")
ok("Collecting n/30" in page, "the scorecard note names the ladder")
ok('aria-label="Rules" data-controls="scorecard-table"' in page and 'id="scorecard-table"' in page,
   "the chips name the table they filter")


# ---------------------------------------------------------------------------
def _browser():
    from require_browser import require_browser
    sync_playwright = require_browser("test_verdict_vocabulary.py")
    if sync_playwright is None:
        return
    import tempfile
    import shutil
    site = tempfile.mkdtemp(prefix="scorecard-")
    for name in ("tables.js", "site.css", "control.css", "shell.js"):
        shutil.copy(os.path.join(ROOT, "public_site", name), site)
    page_html = CC.page(NOW, d=d, st=st, blob={"leads": {}, "pairs": {}}, nba={}, market={}, closes={})
    # Swap the fixture table for the seven-rule one so every chip has something to drop.
    start = page_html.index('<nav class="sp-filter cc-filter"')
    end = page_html.index("</section>", start)
    page_html = page_html[:start] + CC._scorecard_html(sc) + page_html[end:]
    open(os.path.join(site, "index.html"), "w", encoding="utf-8").write(page_html)

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=site, **kwargs)

        def log_message(self, fmt, *args):
            return

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}/index.html"
    print("\nbrowser")
    shown = """() => [...document.querySelectorAll('#scorecard-table tbody tr')]
      .filter((tr) => !tr.hidden && getComputedStyle(tr).display !== 'none').length"""
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.goto(base, wait_until="load")
            eq(page.evaluate(shown), 7, "every rule shows under All")
            for value, want_n in (("production", 2), ("records", 6), ("read", 1), ("all", 7)):
                page.click(f'nav.cc-filter button[data-value="{value}"]')
                eq(page.evaluate(shown), want_n, f"the {value} chip shows {want_n}")
                eq(page.evaluate(f"""() => document.querySelector('nav.cc-filter button[data-value="{value}"]')
                    .getAttribute('aria-pressed')"""), "true", f"the {value} chip is pressed")
            page.set_viewport_size({"width": 390, "height": 844})
            page.wait_for_timeout(50)
            wide = page.evaluate("() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1")
            ok(not wide, "on a phone the scorecard scrolls inside its box, not the page")
            browser.close()
    finally:
        httpd.shutdown()
        shutil.rmtree(site, ignore_errors=True)


_browser()

print()
if FAILS:
    print(f"{len(FAILS)} FAILED")
    sys.exit(1)
print("all passed")
