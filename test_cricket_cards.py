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


def _settled(source, sport, n=4, won=3, price=0.60, logged=None, league=None, tag="Settled"):
    rows = []
    for i in range(n):
        status = "won" if i < won else "lost"
        rows.append(_quote(
            i, source, sport, status,
            NOW - timedelta(days=3, hours=i),
            f"{tag} {source} {i}",
            price=price,
            logged=logged,
            league=league,
        ))
    return rows


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
    quotes += _settled("polymarket", "cricket", n=4, won=3, price=0.50, logged=AFTER)
    quotes.append(_quote(
        500, "polymarket", "cricket", "open", 12,
        "Soon Side v Tonight", bet=False, logged=AFTER))
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


_HORIZON = timedelta(hours=48)


def _kickoff(q):
    raw = q.get("start")
    if not raw:
        return None
    try:
        return fmt.chicago(raw).astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _upcoming(d, name, sport, now):
    """A ledger quote for this rule, not an open bet, kicking off inside 48 hours.

    A repeat city-day quote is not a fixture the lane still counts.
    """
    end = now + _HORIZON
    for q in d.get("quotes") or []:
        if q.get("source") != name or q.get("sport") != sport:
            continue
        if q.get("bet") or q.get("status") != "open":
            continue
        if T.climate_excluded(q):
            continue
        ko = _kickoff(q)
        if ko is not None and now < ko <= end:
            return True
    return False


def _expect_active(row, d, now):
    return "1" if row["open"] or _upcoming(d, row["name"], row["sport"], now) else "0"


def _cards(html):
    return re.findall(r'<article class="rule-card"(.*?)</article>', html, re.S)


def _attr(card, name):
    m = re.search(rf'\b{name}="([^"]*)"', card)
    return m.group(1) if m else None


def _shown(label):
    """How a ledger label is printed on a card: 'A v B' becomes 'A vs B'."""
    return fmt.contest(label)


def _absent(label, html):
    """Neither the stored spelling nor the printed one is on the page."""
    return label not in html and _shown(label) not in html


print(f"SHA {SHA}")

try:
    import cricket_cards
except ImportError:
    cricket_cards = None

import cricket_build
import soccer_build
import tennis_build

print("\ncricket cards")
d, st = _fixture()
html = cricket_build.build(d, st, NOW)
rows = _rows(d, st)
ok(rows, "the fixture has cricket lanes")
ok('class="rule-grid"' in html, "cricket lanes use a card grid")
ok('class="rule-card"' in html, "cricket lanes are flippable cards")
ok('class="rule-flip"' in html, "each card has a flip control")
main = html.split("<main", 1)[-1].split("</main>", 1)[0]
ok("<script" not in main.lower(), "the page body does not grow an inline script")
ok('src="./tables.js"' in html and 'src="./site.js"' in html and 'href="./site.css"' in html,
   "the page loads the shared script and stylesheet by a relative path")
ok("javascript:" not in html, "a javascript: game url is not written")
ok("&lt;script&gt;" in html, "a game label is escaped")
css = open(os.path.join(ROOT, "public_site", "site.css"), encoding="utf-8").read()
ok("repeat(4, minmax(0, 1fr))" in css, "the grid is four columns")
ok("repeat(2, minmax(0, 1fr))" in css, "the grid is two columns under 980px")
ok("grid-template-columns: minmax(0, 1fr)" in css, "the grid is one column under 640px")
ok(">Match winner</h3>" in html, "the cricket market is its own row")
ok(html.count('class="rule-grid"') == html.count('class="rule-market"') >= 1,
   "each market row holds one card grid")

cards = _cards(html)
ok(len(cards) == len(rows), f"one card per cricket lane with a record ({len(cards)} cards, {len(rows)} lanes)")

actives = [_attr(c, "data-active") for c in cards]
if "0" in actives and "1" in actives:
    split = actives.index("0")
    ok(set(actives[:split]) == {"1"} and set(actives[split:]) == {"0"},
       "active cards are a single block above inactive cards")
else:
    ok(False, "the fixture has both an active card and an inactive card")

by_key = {}
for c in cards:
    by_key.setdefault((_attr(c, "data-source"), _attr(c, "data-sport")), []).append(c)

form = by_key.get(("oddspedia", "cricket"), [""])[0]
ok("Alpha vs Beta soonest" in form and "TourLookingOpen" in form,
   "the back lists the soonest open games, with the contest printed as A vs B")
ok("Alpha v Beta soonest" not in form, "the card does not print the ledger's 'A v B' spelling")
eq(S.position_label(next(q for q in d["quotes"] if q["label"] == "Alpha v Beta soonest")),
   "Alpha vs Beta soonest", "the card label is S.position_label of the quote")
ok("FourthOpenLabel" not in form and "FifthLaterLabel" not in form,
   "the back stops at four open games")
ok("4 of 6 open, soonest first." in form,
   "a longer slate says four of the open count, and the city-day row is not in that count")
ok("&lt;script&gt;" in form, "a game label on the card is escaped")

hostile = form.find("&lt;script&gt;")
alpha = form.find("Alpha vs Beta soonest")
pre = form.find("PreResetOpenLabel")
tour = form.find("TourLookingOpen")
ok(0 <= hostile < alpha < pre < tour, "the four open games are soonest first")
ok("GhostClimateOpen" not in form and "GhostClimateOpen" not in html,
   "a repeat city-day open bet is not on the card")
ok("PreResetOpenLabel" in form,
   "an open bet logged before the lane clock stays on the card")
ok("TourLookingOpen" in form,
   "a cricket open bet is not dropped for looking like a refused tennis tour")

if cricket_cards is None:
    ok(False, "cricket_cards renders the Cricket lanes")
for row in rows:
    found = [c for c in cards if _attr(c, "data-source") == row["name"]
             and _attr(c, "data-sport") == row["sport"]]
    card = found[0] if found else ""
    roi = _roi_html(row)
    verdict = _verdict_html(row)
    ok(roi in card, f"{row['name']}|{row['sport']} front ROI matches the lane row")
    ok(verdict in card, f"{row['name']}|{row['sport']} front verdict matches the lane row")
    if cricket_cards is not None:
        eq(cricket_cards.roi_html(row), roi,
           f"{row['name']}|{row['sport']} ROI helper is the lane-row string")
        eq(cricket_cards.verdict_html(row), verdict,
           f"{row['name']}|{row['sport']} verdict helper is the lane-row string")
        eq(_attr(card, "data-active"), _expect_active(row, d, NOW),
           f"{row['name']}|{row['sport']} active flag matches the lane open count")
        listed = cricket_cards.open_quotes(d, row["name"], row["sport"])
        eq(len(listed), row["open"],
           f"{row['name']}|{row['sport']} open list is the lane's open count")

odds = next((r for r in rows if r["name"] == "oddspedia"), None)
ok(odds is not None and odds["a"]["n"] == 2,
   "the Oddspedia record counts only bets logged after the reset")
ok(odds is not None and "PRODUCTION" in form,
   "the Production lane keeps its Production mark")
if odds is not None and cricket_cards is not None:
    ok(cricket_cards.roi_html(odds) in form and "—" != cricket_cards.roi_html(odds),
       "the card ROI is the post-reset lane row, not the unfiltered slate")

tour_row = next(q for q in d["quotes"] if q.get("label") == "TourLookingOpen")
ok(not S.tennis_refused_row(tour_row),
   "the cricket source is not on the tennis tour clock")

ok('data-band="active"' in html and 'data-band="inactive"' in html,
   "active and inactive are separate bands")


def _one(source, sport):
    found = by_key.get((source, sport)) or [""]
    return found[0]


window = _one("polymarket_us", "cricket")
soon = _one("polymarket", "cricket")
far = _one("cricket_consensus", "cricket")
eq(_attr(window, "data-active"), "1",
   "a fixture 36h away and no open bet is active (cutoff is 48 hours)")
eq(_attr(soon, "data-active"), "1",
   "a fixture 12h away and no open bet is active (inside 48 hours, not only the 24–48h band)")
eq(_attr(far, "data-active"), "0",
   "a fixture 72h away, and a city-day fixture inside 48 hours, stays inactive")
ok("No open game." in window and _absent("Window Side v Keeper", window),
   "the back stays the open bets; an unstaked fixture is not listed there")
ok("No open game." in soon and _absent("Soon Side v Tonight", soon),
   "a nearer unstaked fixture is not copied onto the back")
ok("GhostClimateFixture" not in html,
   "a city-day fixture is not listed and does not activate the lane")
active_end = html.find('data-band="inactive"')
window_pos = html.find('data-source="polymarket_us"')
soon_pos = html.find('data-source="polymarket"')
far_pos = html.find('data-source="cricket_consensus"')
odds_pos = html.find('data-source="oddspedia"')
ok(0 < odds_pos < soon_pos < window_pos < active_end,
   "inside the active band, the sooner kickoff comes first")
ok(far_pos > active_end > 0, "a fixture past 48 hours sits in the inactive band")

print("\nno competition panel, definitions stay")
ok("By competition" not in html, "cricket does not add the soccer by-competition panel")
ok("Bundesliga scored 3.49" not in html,
   "cricket does not add the soccer competition note")
ok("GhostCricketLeague" not in html,
   "a pre-reset competition name is not printed as a total")
ok("GhostPrereset" not in html, "a pre-reset settled label is not on the page")
ok("How each rule is defined" in html, "the rule definitions stay under the cards")
ok("Oddspedia community tips" in html and "niche cricket" in html,
   "the Oddspedia definition stays on the page")
empty = cricket_cards.render({"quotes": []}, [], NOW) if cricket_cards else ""
ok("No cricket lane has a record yet." in empty and "rule-card" not in empty,
   "an empty lane list is a note, not a card grid")

print("\nsoccer and tennis stay on their own pages")
cri = html
soc = soccer_build.build(d, st, NOW)
ten = tennis_build.build(d, st, NOW)
ok(_absent("Soccer Only v Stay", cri) and _absent("Tennis Only v Stay", cri),
   "cricket cards do not pick up soccer or tennis lanes")
ok("o15_form_l10" not in cri and "tennis_fav_band_3h" not in cri,
   "cricket cards do not name soccer or tennis rules")
ok('class="rule-card"' in soc and _shown("Soccer Only v Stay") in soc,
   "soccer still renders its own rule cards")
ok("PreResetOpenLabel" not in soc and "TourLookingOpen" not in soc,
   "soccer cards do not pick up cricket lanes")
ok('class="rule-card"' in ten and _shown("Tennis Only v Stay") in ten,
   "tennis still renders its own rule cards")
ok("PreResetOpenLabel" not in ten and "oddspedia" not in ten.lower(),
   "tennis cards do not pick up cricket lanes")

js = open(os.path.join(ROOT, "public_site", "tables.js"), encoding="utf-8").read()
wire = js.split("function wireRuleCards", 1)[-1].split("function enhance", 1)[0]
ok("function wireRuleCards" in js and "is-flipped" in js and ".rule-flip" in wire,
   "tables.js flips a card without an inline handler")
ok("btn.focus()" in wire, "tables.js restores keyboard focus on the flipped face")
ok(js.count("function wireRuleCards") == 1, "cricket reuses the one card flip")

published = open(os.path.join(ROOT, "public_site", "cricket.html"), encoding="utf-8").read()
ok('class="rule-card"' in published and 'class="rule-grid"' in published,
   "public_site/cricket.html is the card page")
ok('src="./tables.js"' in published, "the published cricket page loads tables.js")
ok("By competition" not in published,
   "published cricket page has no by-competition panel")
ok("How each rule is defined" in published,
   "published cricket page still has the rule definitions")
soc_file = open(os.path.join(ROOT, "public_site", "soccer.html"), encoding="utf-8").read()
ten_file = open(os.path.join(ROOT, "public_site", "tennis.html"), encoding="utf-8").read()
ok('class="rule-card"' in soc_file, "published soccer page still has its cards")
ok('class="rule-card"' in ten_file, "published tennis page still has its cards")
ok("By competition" in soc_file, "published soccer page still has its by-competition panel")

if FAILS:
    print(f"\nSHA {SHA} FAILED {len(FAILS)}")
    sys.exit(1)
print(f"\nSHA {SHA} PASSED")
