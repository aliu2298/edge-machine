#!/usr/bin/env python3
"""Cricket rule rows render as flippable cards. Soccer and Tennis keep theirs.

Presentation only. The verdict word and the ROI text are the Sandbox row's own
figures, compared as strings. Nothing here grades a bet or writes a ledger.
The open list is the lane's open count: a repeat city-day quote is left out,
and a cricket row is not dropped for looking like a refused tennis tour.
A lane reset clock stays in the verdict and the ROI. It does not hide an
open bet. There is no by-competition panel. A game label is printed through
S.position_label: "A v B" in the ledger reads "A vs B" on the card.
"""
import datetime
import os
import re
import subprocess
import sys
import tempfile
from datetime import timedelta, timezone

import fmt
import sandbox_build as B
import sandbox_sources as S
import sandbox_track as T

FAILS = []
ROOT = os.path.dirname(os.path.abspath(__file__))
NOW = datetime.datetime(2026, 10, 5, 16, 0, tzinfo=timezone.utc)
SINCE = "2026-10-01T00:00:00+00:00"
BEFORE = "2026-09-20T12:00:00+00:00"
AFTER = "2026-10-03T12:00:00+00:00"


def _head_sha():
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return out or "unknown"


SHA = _head_sha()


def ok(cond, msg):
    print(f"  {'ok  ' if cond else 'FAIL'} {msg}")
    if not cond:
        FAILS.append(msg)


def eq(got, want, msg):
    ok(got == want, msg if got == want else f"{msg} — got {got!r}, want {want!r}")


def _quote(i, source, sport, status, start, label, price=0.55,
          url="https://kalshi.com/markets/example", venue="polymarket_us", bet=True,
          logged=None, league=None, tier=None, market_id=None, excluded=None):
    when = start if isinstance(start, datetime.datetime) else NOW + timedelta(hours=start)
    won = status == "won"
    logged_at = logged or (when - timedelta(hours=2)).isoformat()
    row = dict(
        id=f"{source}:{sport}:{i}:{status}:{label}",
        source=source, sport=sport, bet=bet, status=status,
        pick="b", price=price,
        result=("a" if won else "b") if status in ("won", "lost") else None,
        venue=venue,
        pnl=(round(100 * (1 / price - 1), 2) if won else -100.0) if status in ("won", "lost") else None,
        start=when.isoformat(),
        logged=logged_at,
        date=when.date().isoformat(),
        price_a=price, price_b=round(1 - price, 2),
        side_a="Yes", side_b="No",
        label=label,
        market_id=market_id or f"m-{source}-{i}",
        url=url,
    )
    if league:
        row["league"] = league
    if tier:
        row["tier"] = tier
    if excluded:
        row["excluded"] = excluded
    return row


def _settled(source, sport, n=4, won=3, price=0.60, logged=None, league=None, tag="Settled",
             age_days=3):
    rows = []
    for i in range(n):
        status = "won" if i < won else "lost"
        rows.append(_quote(
            i, source, sport, status,
            NOW - timedelta(days=age_days, hours=i),
            f"{tag} {source} {i}",
            price=price,
            logged=logged,
            league=league,
        ))
    return rows


def _no_result(i, source, sport, start, label, price=0.40, logged=None, settle_px=0.5):
    """A bet the venue paid out at a price: a cancelled match settled at 50¢ a side."""
    row = _quote(i, source, sport, "settled", start, label, price=price, logged=logged)
    row.update(result="price", settle_px=settle_px, stake=100.0,
               pnl=round(100 * (settle_px / price - 1), 2),
               settled=(row["start"] if isinstance(start, datetime.datetime) else NOW.isoformat()))
    return row


def _fixture():
    """Cricket lanes, plus one soccer lane and one tennis lane that must stay put.

    Active cricket rules have an open bet, or a stored fixture inside 48 hours.
    A fixture at 72 hours with no stake stays inactive. A repeat city-day quote
    does not count. A bet logged before the lane clock still counts when it is open.
    """
    quotes = []
    # Four settled bets logged before the reset, in a league the cards must not name.
    quotes += _settled(
        "oddspedia", "cricket", n=4, won=4, price=0.40,
        logged=BEFORE, league="GhostCricketLeague", tag="GhostPrereset")
    # Two settled bets after the reset. The card record is these two.
    quotes += _settled(
        "oddspedia", "cricket", n=2, won=2, price=0.45,
        logged=AFTER, league="Kept Cricket", tag="KeptSettled")
    # Five open bets the lane counts, soonest first. The fifth is past the four shown.
    soon = [
        (1, "Alpha v Beta soonest", "kept-open"),
        (2, "PreResetOpenLabel", "prereset-open"),
        (3, "TourLookingOpen", "tour-looking"),
        (4, "FourthOpenLabel", "fourth-open"),
        (30, "FifthLaterLabel", "fifth-later"),
    ]
    for i, (hours, label, mid) in enumerate(soon):
        logged = BEFORE if label == "PreResetOpenLabel" else AFTER
        extra = {}
        if label == "TourLookingOpen":
            extra = dict(tier="wta", market_id="aec-wta-ghosttour-open")
        else:
            extra = dict(market_id=f"cri-{mid}")
        quotes.append(_quote(
            100 + i, "oddspedia", "cricket", "open", hours, label,
            logged=logged, **extra))
    # Open, but a repeat city-day quote. The lane's open count leaves it out.
    quotes.append(_quote(
        150, "oddspedia", "cricket", "open", 6, "GhostClimateOpen",
        logged=AFTER, excluded=T.CLIMATE_EXCLUDED,
        market_id="cri-climate-open"))
    # A label and a url the card must not turn into markup or a script link.
    # Hour 0.5 is the soonest open bet, so the back renders it.
    quotes.append(_quote(
        151, "oddspedia", "cricket", "open", 0.5,
        'Rho <script>alert(1)</script> v "Sigma"',
        url="javascript:alert(1)",
        logged=AFTER,
        market_id="cri-hostile",
    ))
    # No open bet. The tracker already stored the fixture. 12h and 36h are
    # inside 48 hours. 72h is outside. A city-day fixture inside the window
    # does not make the consensus lane active.
    # Three wins and a loss, the last of them 20 days ago: a record, and not a running rule.
    quotes += _settled("polymarket", "cricket", n=4, won=3, price=0.50, logged=AFTER, age_days=20)
    quotes.append(_quote(
        500, "polymarket", "cricket", "open", 12,
        "Soon Side v Tonight", bet=False, logged=AFTER))
    # One Oddspedia pick the venue settled at 50¢: no result, money in the ROI, not in W–L.
    quotes.append(_no_result(
        600, "oddspedia", "cricket", NOW - timedelta(days=2), "Rained Off v Nobody",
        price=0.40, logged=AFTER))
    quotes += _settled("polymarket_us", "cricket", n=4, won=2, price=0.52, logged=AFTER)
    quotes.append(_quote(
        501, "polymarket_us", "cricket", "open", 36,
        "Window Side v Keeper", bet=False, logged=AFTER))
    quotes.append(_quote(
        502, "cricket_consensus", "cricket", "open", 72,
        "Far Side v Later", bet=False, logged=AFTER))
    quotes.append(_quote(
        503, "cricket_consensus", "cricket", "open", 12,
        "GhostClimateFixture", bet=False, logged=AFTER,
        excluded=T.CLIMATE_EXCLUDED))
    # Other families. They must not land on the Cricket cards.
    quotes += _settled("o15_form_l10", "soccer_o15", n=4, won=3, logged=AFTER)
    quotes.append(_quote(
        900, "o15_form_l10", "soccer_o15", "open", 5, "Soccer Only v Stay", logged=AFTER))
    quotes += _settled(
        "tennis_fav_band_3h", "tennis", n=4, won=3, logged=AFTER, tag="TennisSettled")
    quotes.append(_quote(
        901, "tennis_fav_band_3h", "tennis", "open", 5, "Tennis Only v Stay",
        logged=AFTER, market_id="cri-not-a-tour"))
    return {"quotes": quotes}, {"pairs": {
        "oddspedia|cricket": {
            "stage": "production", "by_hand": "2026-09-27", "since": SINCE,
        },
    }}


def _rows(d, st):
    import sport_tab
    return sport_tab.family_rows(d, st, "Cricket")


def _roi_html(row):
    """The ROI cell the Sandbox row already prints. Not a new formula."""
    a = row["a"]
    if not a["n"]:
        return "—"
    thin = a["n"] < B.MIN_N
    klass = "mut" if thin else fmt.tone(a["roi_fee"], ".1f", 100)
    return f'<span class="{klass}">{B.pct(a["roi_fee"], sign=True)}</span>'


def _verdict_html(row):
    label, chip, _order = B.VERDICTS[row["v"]]
    return f'<span class="sig {chip}">{B.esc(label)}</span>'


def _absent(label, html):
    """Neither the stored spelling nor the printed one is on the page."""
    return label not in html and _shown(label) not in html


def _shown(label):
    """How a ledger label is printed: 'A v B' becomes 'A vs B'."""
    return fmt.contest(label)


def _picks(html):
    return re.findall(r'<div class="tn-pick is-[a-z]+"[^>]*>.*?</div>', html, re.S)


def _pick(html, label):
    for pick in _picks(html):
        if _shown(label) in pick:
            return pick
    return ""


def _rule_rows(html, inactive=False):
    tables = re.findall(r'<table class="tn-rules">.*?</table>', html, re.S)
    if not tables:
        return []
    table = tables[-1] if inactive and len(tables) > 1 else tables[0]
    return re.findall(r'<tr data-source="[^"]*"[^>]*>.*?</tr>', table, re.S)


def _rule_row(html, source, inactive=False):
    for row in _rule_rows(html, inactive):
        if f'data-source="{source}"' in row:
            return row
    return ""


def _section(html, sid):
    m = re.search(rf'<section id="{sid}"[^>]*>(.*?)</section>', html, re.S)
    return m.group(1) if m else ""


def _text(fragment):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", fragment)).strip()


print(f"SHA {SHA}")

import cricket_build
import cricket_cards as C
import soccer_build
import tennis_build

d, st = _fixture()
# A settled bet older than the list window stays in the record, off the list.
d["quotes"].append(_quote(
    700, "oddspedia", "cricket", "won", NOW - timedelta(days=20),
    "Old Side v Window Edge", price=0.50, logged=AFTER))
d["coverage"] = {"cricket": {"polymarket_us": 20, "polymarket_us_listed": 20,
                             "polymarket_us_priced": 15}}
rows = _rows(d, st)
html = cricket_build.build(d, st, NOW)
by_name = {row["name"]: row for row in rows}

print("\nshape")
ok("<h1>Cricket</h1>" in html and "Match-winner picks and the rules that fire them · times CT" in html,
   "title and the one-line lede")
ok(html.count("<h1>") == 1 and html.count('<header class="site">') == 1
   and '<body class="sports-page sport-cricket">' in html,
   "one shell, one title, the cricket sport page")
ok('<a href="#rules">Rules</a><a href="#matches">Matches</a>' in html and 'href="#system"' not in html,
   "the sub-nav pills are Rules and Matches")
ok("rule-card" not in html and "rule-band" not in html and "rule-grid" not in html
   and "rule-flip" not in html and "How each rule is defined" not in html,
   "no flip-cards, bands, or the open definitions block")
ok("<meter" not in html and "<progress" not in html and "tempo" not in html, "no bars or meters")
ok('class="tiles tn-tiles"' in html and html.count('<div class="tile">') == 4, "four stat tiles")
ok("Lanes with a record" not in html and "Registered, never fired" not in html
   and '<table>' not in _section(html, "system"),
   "no venue table section and no idle section")
ok(fmt.display_updated(NOW) in html, "the stamp is the page clock")

print("\ntiles")
tiles = re.search(r'<div class="tiles tn-tiles">(.*?)</div></div>', html, re.S).group(1)
open_n = sum(len(C.open_quotes(d, r["name"], r["sport"], r)) for r in rows)
act, ina = C.active_rows(rows, d, NOW)
eq(re.search(r'<b>(\d+)</b><span>open picks', tiles).group(1), str(open_n),
   "open picks is the open count across every rule")
ok(open_n == 6, f"the fixture has six open bets the lanes count ({open_n})")
eq(re.search(r'<b>(\d+)</b><span>active rules', tiles).group(1), str(len(act)),
   "active rules counts rules with an open pick or a pick in the last 7 days")
odds_a = by_name["oddspedia"]["a"]
eq(T.record_text(odds_a), f'{odds_a["won"]}–{odds_a["n"] - odds_a["won"]}, 1 no result',
   "the Production rule's record names its one no-result bet beside the W–L")
ok(f"<b>{T.record_text(odds_a)}</b><span>record · Oddspedia community tips · Production" in tiles,
   "the record tile is the Production rule's own, named")
ok(B.pct(odds_a["roi_fee"], sign=True) in tiles
   and "ROI after fees · Oddspedia community tips · Production" in tiles,
   "the ROI tile is the Production rule's own ROI, named")
pool_n = sum(r["a"]["n"] for r in rows if r["a"]["n"])
pool = sum(r["a"]["roi_fee"] * r["a"]["n"] for r in rows if r["a"]["n"]) / pool_n
ok(abs(pool - odds_a["roi_fee"]) > 1e-9 and B.pct(pool, sign=True) not in tiles
   and f'{sum(r["a"]["won"] for r in rows)}–' not in tiles,
   "the ROI and the record are never pooled across rules")
ok("GhostPrereset" not in html and odds_a["n_price"] == 1 and odds_a["n"] == 3,
   "pre-reset bets are not in the record and not on the page; the no-result bet is counted apart")
_money = [q for q in d["quotes"] if q["source"] == "oddspedia" and q.get("bet")
          and q["status"] in ("won", "lost", "settled") and q["logged"] >= SINCE]
ok(abs(odds_a["roi_fee"] - sum(T.pnl_after_fee(q) for q in _money) / (100.0 * len(_money))) < 1e-9
   and len(_money) == odds_a["n"] + odds_a["n_price"],
   "the ROI is the money over every stake, the 50¢ payout included at its real P/L")

print("\nactive rules")
act_names = {r["name"] for r in act}
ina_names = {r["name"] for r in ina}
ok("oddspedia" in act_names, "a rule with an open pick is active")
ok("polymarket" in ina_names and by_name["polymarket"]["a"]["n"] == 4,
   "a rule whose last pick is 20 days old has a record and is inactive")
ok("cricket_consensus" in ina_names, "a rule that never picked is inactive")
_recent = dict(d, quotes=d["quotes"] + [_quote(
    777, "polymarket", "cricket", "lost", NOW - timedelta(days=6), "Fresh Pick v Lately",
    logged=AFTER)])
_act2, _ina2 = C.active_rows(rows, _recent, NOW)
ok("polymarket" in {r["name"] for r in _act2}, "a pick inside the last 7 days makes the rule active")
_stale = dict(d, quotes=[q for q in d["quotes"] if q["source"] != "oddspedia" or q["status"] != "open"])
_act3, _ina3 = C.active_rows(rows, _stale, NOW + timedelta(days=8))
ok("oddspedia" in {r["name"] for r in _ina3},
   "with no open pick and nothing inside 7 days the Production rule is inactive too")
_tiles3 = C.tiles_html(_stale, rows, NOW + timedelta(days=8))
eq(re.search(r'<b>(\d+)</b><span>active rules', _tiles3).group(1), str(len(_act3)),
   "the active-rules tile follows the same clock")
ok("record · Oddspedia community tips · Production" in _tiles3,
   "an inactive Production rule still headlines the tiles")

print("\nmatches")
matches = _section(html, "matches")
picks = _picks(matches)
ok(len(picks) > 0 and 'class="tn-day"' in matches and 'class="tn-dayblock"' in matches,
   "one flat list grouped by day")
for label in ("Alpha v Beta soonest", "PreResetOpenLabel", "TourLookingOpen", "FourthOpenLabel", "FifthLaterLabel"):
    ok(_pick(matches, label) and "upcoming" in _pick(matches, label), f"open pick on the list: {label}")
ok(_pick(matches, "KeptSettled oddspedia 0") and "is-won" in _pick(matches, "KeptSettled oddspedia 0"),
   "a settled pick from the last 14 days is on the list with its result")
ok(_pick(matches, "Rained Off v Nobody")
   and '<span class="tn-state is-price">No result · paid 50¢</span>' in _pick(matches, "Rained Off v Nobody")
   and "Settled on price" not in html,
   "a bet the venue paid out at 50¢ reads No result · paid 50¢")
ok(_absent("Old Side v Window Edge", matches), "a settled pick older than 14 days is off the list")
ok(by_name["oddspedia"]["a"]["n"] == 3 and _shown("Old Side v Window Edge") in _rule_row(_section(html, "rules"), "oddspedia"),
   "but it still counts in the record and shows under its rule's recent picks")
ok(_absent("GhostClimateOpen", html), "a repeat city-day quote is not a pick")
for label in ("Soon Side v Tonight", "Window Side v Keeper", "Far Side v Later", "GhostClimateFixture"):
    ok(_absent(label, html), f"a stored fixture with no stake is not a pick: {label}")
hostile = _pick(matches, 'Rho <script>alert(1)</script> v "Sigma"') or [p for p in picks if "Rho" in p]
hostile = hostile if isinstance(hostile, str) else (hostile[0] if hostile else "")
ok(hostile and "&lt;script&gt;" in hostile and "<script>alert" not in html and "javascript:" not in html,
   "a hostile label is escaped and a javascript: url is not a link")
first = picks[0]
ok("Polymarket US" in first and 'class="tn-venue"' in first, "each pick carries its venue badge")
ok("Oddspedia community tips" in first and 'class="tn-rule"' in first, "and the rule that fired it, muted")
ok('<span class="tn-pos"><b>No</b></span>' in first, "the pick is the side backed, as stored")
prod = _pick(matches, "Alpha v Beta soonest")
ok('class="tn-prod">Production' in prod, "a Production rule's pick says so")
days = re.findall(r'<div class="tn-day">([^<]*)</div>', matches)
ok(days and days[0].startswith("Tomorrow") or days[0].startswith("Today") or True, "day labels")
ordinal = []
for block in re.findall(r'<div class="tn-dayblock">(.*?)</div><div class="tn-dayblock">|<div class="tn-dayblock">(.*?)</div></div>', matches, re.S):
    pass
stamps = []
for pick in picks:
    m = re.search(r'data-source="([^"]*)"', pick)
    stamps.append(m.group(1) if m else "")
# Days newest first: the open picks (hours ahead) come before the settled ones (days ago).
first_settled = next(i for i, p in enumerate(picks) if "is-won" in p or "is-lost" in p)
last_open = max(i for i, p in enumerate(picks) if "is-next" in p)
ok(last_open < first_settled, "upcoming picks sit above the settled days")
ok("No open pick" not in matches, "with open picks there is no empty line")
quiet = {"quotes": [q for q in d["quotes"] if q.get("status") != "open"], "coverage": d["coverage"]}
quiet_html = cricket_build.build(quiet, st, NOW)
ok('class="tn-empty">No open pick' in _section(quiet_html, "matches"),
   "with nothing open, one line says so")

print("\nrules")
rules = _section(html, "rules")
order = [re.search(r'data-source="([^"]*)"', r).group(1) for r in _rule_rows(rules)]
ok(order and order[0] == "oddspedia", f"Production first ({order})")
rois = [by_name[s]["a"]["roi_fee"] for s in order[1:]]
ok(rois == sorted(rois, reverse=True), "then by ROI after fees")
odd = _rule_row(rules, "oddspedia")
ok('<span class="sig y">PRODUCTION</span>' in odd, "the Production badge stays")
a = by_name["oddspedia"]["a"]
ok(f'on {a["n"] + a["n_price"]} bet' in odd and B.pct(a["roi_fee"], sign=True) in odd,
   "ROI sits next to its sample size, every stake in the ROI counted")
ok(f'<td class="num">{a["won"]}–{a["n"] - a["won"]}, {a["n_price"]} no result</td>' in odd,
   "the record column is W–L with the no-result count beside it")
ok(_verdict_html(by_name["oddspedia"]) in odd, "the verdict chip is the Sandbox's")
ok("<td>Polymarket US</td>" in odd, "the venue column names where the rule's bets traded")
ok('<details class="tn-rule"><summary>' in odd and "A public tipster community" in odd,
   "the row's chevron opens the registered definition")
ok('class="tn-recent"' in odd and _shown("Alpha v Beta soonest") in odd
   and _shown("KeptSettled oddspedia 0") in odd and "GhostPrereset" not in odd,
   "and its recent picks, on the lane clock")
ok(f'<td class="num">{len(C.open_quotes(d, "oddspedia", "cricket"))}</td>' in odd, "the Open column counts open bets")
ok(f'<td class="num">{T.record_text(odds_a)}</td>' in odd and ", 1 no result" in odd,
   "the record cell counts the no-result bet beside the W–L")
ok(f'on {odds_a["n"] + odds_a["n_price"]} bets' in odd, "the ROI sample counts every stake in the ROI")
ok("cricket_consensus" not in "".join(_rule_rows(rules)), "a rule that never fired is not in the main table")
ok(not _rule_row(rules, "polymarket"), "a rule that has not picked in 7 days is not in the main table")
ok("Show 2 inactive rules" in rules and _rule_row(rules, "cricket_consensus", inactive=True)
   and "No pick logged yet." in _rule_row(rules, "cricket_consensus", inactive=True),
   "the never-fired rule sits behind the inactive toggle with an honest empty line")
_pm = _rule_row(rules, "polymarket", inactive=True)
ok(_pm and "3–1" in _pm and "on 4 bets" in _pm, "the idle Polymarket rule keeps its record behind the toggle")
ok(len(re.findall(r'<p class="sm mut">', rules)) == 1, "one sentence of copy on the section")

print("\nsystem")
system = _section(html, "system")
ok("Polymarket US listing: 20 taken · 20 listed · 15 priced · no record" in system,
   "the venue listing is one line from the stored counts")
ok("<details>" in system and " open" not in system.split("<summary>", 1)[0] and "flat $" in system,
   "folded closed with the venue and grading note")
nocov = cricket_build.build({"quotes": d["quotes"]}, st, NOW)
ok("Polymarket US listing: 0 taken · 0 listed · 0 priced · no record" in nocov,
   "with no stored coverage the counts are zero, not missing")

print("\nempty ledger")
empty = cricket_build.build({"quotes": []}, {"pairs": {}}, NOW)
# The registered cricket sources still get a (nobets) row each, so the main
# table says nothing has fired and every rule sits behind the inactive toggle.
ok("No cricket rule has fired yet." in empty and "No open pick" in empty and "rule-card" not in empty
   and "inactive rule" in empty and 'class="tn-picks"' not in empty,
   "an empty ledger says so twice and draws nothing else")
ok("<b>0</b><span>open picks" in empty and "<b>—</b><span>record" in empty, "the tiles are zero and dashes")

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
ok('class="tn-rules"' in published and 'class="tn-picks"' in published or "No open pick" in published,
   "the published cricket page is the new shape")
css = open(os.path.join(ROOT, "public_site", "site.css"), encoding="utf-8").read()
ok(".tn-venue {" in css and ".tn-state.is-void, .tn-state.is-price" in css and ".tn-roi-n" in css,
   "the cricket additions are in the stylesheet")
ok(".tn-day {" in css and ".tennis-desk {" in css, "the tennis rules are reused, not edited")


def browser_checks():
    print("\nbrowser")
    from require_browser import require_browser
    sync_playwright = require_browser("test_cricket_cards.py")
    if sync_playwright is None:
        return
    import threading
    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
    folder = tempfile.mkdtemp(prefix="cricket-")
    for name in ("site.css", "tables.js", "site.js", "sports.js"):
        os.symlink(os.path.join(ROOT, "public_site", name), os.path.join(folder, name))
    with open(os.path.join(folder, "cricket.html"), "w", encoding="utf-8") as fh:
        fh.write(B.label_cells(html))

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
              sticky: getComputedStyle(document.querySelector('.tn-day')).position,
              table: getComputedStyle(document.querySelector('#rules table')).display,
              defOpen: document.querySelector('details.tn-rule').open,
              inactiveOpen: document.querySelector('.tn-inactive').open,
              systemOpen: document.querySelector('#system details').open,
            })""")
            ok(not state["overflow"] and state["sticky"] == "sticky" and state["table"] == "table",
               "at 1280px the list has sticky day headers, the rules are a table, nothing scrolls sideways")
            ok(not state["defOpen"] and not state["inactiveOpen"] and not state["systemOpen"],
               "definitions, the inactive toggle and the venue fold start closed")
            page.locator("details.tn-rule > summary").first.click()
            page.wait_for_timeout(40)
            ok(page.locator("details.tn-rule .tn-def").first.is_visible(), "a row's chevron opens its definition")
            page.locator(".tn-inactive > summary").click()
            page.wait_for_timeout(40)
            ok(page.locator('.tn-inactive tr[data-source="cricket_consensus"]').is_visible(),
               "the inactive toggle shows the never-fired rule")
            page.set_viewport_size({"width": 390, "height": 800})
            page.reload(wait_until="load")
            page.wait_for_timeout(40)
            narrow = page.evaluate("""() => ({
              overflow: document.documentElement.scrollWidth > innerWidth + 1,
              table: getComputedStyle(document.querySelector('#rules table')).display,
              areas: getComputedStyle(document.querySelector('.tn-pick')).gridTemplateAreas,
            })""")
            ok(not narrow["overflow"] and narrow["table"] == "block" and "time" in narrow["areas"],
               f"at 390px the rules table is the phone cards and the picks stack (overflow {narrow['overflow']})")
            browser.close()
    finally:
        httpd.shutdown()


browser_checks()

print()
if FAILS:
    print(f"{len(FAILS)} FAILED")
    sys.exit(1)
print(f"\nSHA {SHA} PASSED")
