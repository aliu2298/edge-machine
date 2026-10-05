#!/usr/bin/env python3
"""Tennis rule rows render as flippable cards. Cricket has its own cards.

Presentation only. The verdict word and the ROI text are the Sandbox row's own
figures, compared as strings. Nothing here grades a bet or writes a ledger.
Soccer keeps its own cards; this file does not change how those are built.
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

FAILS = []
ROOT = os.path.dirname(os.path.abspath(__file__))
NOW = datetime.datetime(2026, 10, 5, 16, 0, tzinfo=timezone.utc)


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
          url="https://kalshi.com/markets/example", venue="kalshi", bet=True):
    when = start if isinstance(start, datetime.datetime) else NOW + timedelta(hours=start)
    won = status == "won"
    return dict(
        id=f"{source}:{sport}:{i}:{status}:{label}",
        source=source, sport=sport, bet=bet, status=status,
        pick="b", price=price,
        result=("a" if won else "b") if status in ("won", "lost") else None,
        venue=venue,
        pnl=(round(100 * (1 / price - 1), 2) if won else -100.0) if status in ("won", "lost") else None,
        start=when.isoformat(),
        logged=(when - timedelta(hours=2)).isoformat(),
        date=when.date().isoformat(),
        price_a=price, price_b=round(1 - price, 2),
        side_a="Yes", side_b="No",
        label=label,
        market_id=f"m-{source}-{i}",
        url=url,
    )


def _settled(source, sport, n=4, won=3, price=0.60):
    rows = []
    for i in range(n):
        status = "won" if i < won else "lost"
        rows.append(_quote(
            i, source, sport, status,
            NOW - timedelta(days=3, hours=i),
            f"Settled {source} {i}",
            price=price,
        ))
    return rows


def _fixture():
    """Tennis markets, plus one soccer lane and one cricket lane that must stay put.

    Active tennis rules have an open bet, or a stored fixture inside 48 hours.
    A fixture at 72 hours with no stake stays inactive.
    """
    quotes = []
    quotes += _settled("tennis_fav_band_3h", "tennis", n=6, won=4)
    quotes += _settled("tennis_combo2", "tennis_combo", n=4, won=3, price=0.62)
    quotes += _settled("tennis_combo3", "tennis_combo", n=4, won=2, price=0.58)
    quotes += _settled("tennis_combo4", "tennis_combo", n=3, won=1, price=0.61)
    quotes += _settled("pm_combo2", "tennis_pmcombo", n=5, won=2, price=0.48)
    quotes += _settled("pm_combo3", "tennis_pmcombo", n=4, won=3, price=0.52)
    quotes += _settled("pm_combo4", "tennis_pmcombo", n=4, won=1, price=0.70)
    # Soonest four of five open games on the favourite-band rule. The fifth is later.
    soon = [
        (1, "Alpha v Beta soonest"),
        (2, "Gamma v Delta second"),
        (3, "Epsilon v Zeta third"),
        (4, "Eta v Theta fourth"),
        (30, "Iota v Kappa fifth and later"),
    ]
    for i, (hours, label) in enumerate(soon):
        quotes.append(_quote(100 + i, "tennis_fav_band_3h", "tennis", "open", hours, label))
    # No open bet. The tracker already stored the fixture (bet false, status open).
    # 12h is inside the next day. 36h is past 24h and inside 48h. 72h is outside.
    quotes.append(_quote(
        500, "tennis_combo2", "tennis_combo", "open", 12,
        "Soon Side v Tonight", bet=False))
    quotes.append(_quote(
        501, "tennis_combo3", "tennis_combo", "open", 36,
        "Window Side v Keeper", bet=False))
    quotes.append(_quote(
        502, "tennis_combo4", "tennis_combo", "open", 72,
        "Far Side v Later", bet=False))
    # Open, but the kickoff is past 48 hours: still receiving a pick, so active,
    # and the market sorts after rules whose game is inside the window.
    quotes.append(_quote(
        400, "pm_combo2", "tennis_pmcombo", "open", 80, "Omicron v Pi later"))
    quotes.append(_quote(
        401, "pm_combo2", "tennis_pmcombo", "open", 90,
        'Rho <script>alert(1)</script> v "Sigma"',
        url="javascript:alert(1)",
        venue="polymarket_us",
    ))
    # Other families. They must not land on the Tennis cards, and Tennis cards
    # must not land on their pages.
    quotes += _settled("o15_form_l10", "soccer_o15", n=4, won=3)
    quotes.append(_quote(
        900, "o15_form_l10", "soccer_o15", "open", 5, "Soccer Only v Stay"))
    quotes += _settled("oddspedia", "cricket", n=6, won=4, price=0.40)
    return {"quotes": quotes}, {"pairs": {}}


def _rows(d, st):
    import sport_tab
    return sport_tab.family_rows(d, st, "Tennis")


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


# Cutoff for "upcoming". A kickoff after the page clock and at most 48 hours
# ahead counts, including one inside the next 24 hours. Past 48 hours does not.
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
    """A ledger quote for this rule, not an open bet, kicking off inside 48 hours."""
    end = now + _HORIZON
    for q in d.get("quotes") or []:
        if q.get("source") != name or q.get("sport") != sport:
            continue
        if q.get("bet") or q.get("status") != "open":
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


print(f"SHA {SHA}")

try:
    import tennis_cards
except ImportError:
    tennis_cards = None

import tennis_build
import cricket_build
import soccer_build

print("\ntennis cards")
d, st = _fixture()
html = tennis_build.build(d, st, NOW)
rows = _rows(d, st)
ok(rows, "the fixture has tennis lanes")
ok('class="rule-grid"' in html, "tennis lanes use a card grid")
ok('class="rule-card"' in html, "tennis lanes are flippable cards")
ok('class="rule-flip"' in html, "each card has a flip control")
main = html.split("<main", 1)[-1].split("</main>", 1)[0]
ok("<script" not in main.lower(), "the page body does not grow an inline script")
ok("javascript:" not in html, "a javascript: game url is not written")
ok("&lt;script&gt;" in html, "a game label is escaped")
css = open(os.path.join(ROOT, "public_site", "site.css"), encoding="utf-8").read()
ok("repeat(4, minmax(0, 1fr))" in css, "the grid is four columns")
ok("repeat(2, minmax(0, 1fr))" in css, "the grid is two columns under 980px")
ok("grid-template-columns: minmax(0, 1fr)" in css, "the grid is one column under 640px")
ok(">Match winner</h3>" in html and ">Combos</h3>" in html and ">PM Combos</h3>" in html,
   "each tennis market is its own row")
ok(html.count('class="rule-grid"') == html.count('class="rule-market"') > 1,
   "each market row holds one card grid")

cards = _cards(html)
ok(len(cards) == len(rows), f"one card per tennis lane with a record ({len(cards)} cards, {len(rows)} lanes)")

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

form = by_key.get(("tennis_fav_band_3h", "tennis"), [""])[0]
ok("Alpha v Beta soonest" in form and "Eta v Theta fourth" in form,
   "the back lists the soonest open games")
ok("Iota v Kappa fifth and later" not in form,
   "the back stops at four open games")
ok("4 of 5 open, soonest first." in form, "a longer slate says four of the open count")
alpha = form.find("Alpha v Beta soonest")
gamma = form.find("Gamma v Delta second")
epsilon = form.find("Epsilon v Zeta third")
eta = form.find("Eta v Theta fourth")
ok(0 <= alpha < gamma < epsilon < eta, "the four open games are soonest first")

if tennis_cards is None:
    ok(False, "tennis_cards renders the Tennis lanes")
for row in rows:
    found = [c for c in cards if _attr(c, "data-source") == row["name"]
             and _attr(c, "data-sport") == row["sport"]]
    card = found[0] if found else ""
    roi = _roi_html(row)
    verdict = _verdict_html(row)
    ok(roi in card, f"{row['name']}|{row['sport']} front ROI matches the lane row")
    ok(verdict in card, f"{row['name']}|{row['sport']} front verdict matches the lane row")
    if tennis_cards is not None:
        eq(tennis_cards.roi_html(row), roi,
           f"{row['name']}|{row['sport']} ROI helper is the lane-row string")
        eq(tennis_cards.verdict_html(row), verdict,
           f"{row['name']}|{row['sport']} verdict helper is the lane-row string")
    want_active = _expect_active(row, d, NOW)
    eq(_attr(card, "data-active"), want_active,
       f"{row['name']}|{row['sport']} active flag is an open bet or a fixture inside 48 hours")

active_html = html.split('data-band="inactive"', 1)[0]
combo_names = [_attr(c, "data-source") for c in _cards(active_html)
               if _attr(c, "data-market") == "tennis_combo"]
eq(combo_names, ["tennis_combo2", "tennis_combo3"],
   "the active combo row puts the sooner kickoff first")
markets = [m.group(1) for m in re.finditer(r'class="rule-market" data-market="([^"]+)"', active_html)]
eq(markets, ["tennis", "tennis_combo", "tennis_pmcombo"],
   "active markets are soonest kickoff first, each on its own row")

ok('data-band="active"' in html and 'data-band="inactive"' in html,
   "active and inactive are separate bands")


def _one(source, sport):
    found = by_key.get((source, sport)) or [""]
    return found[0]


window = _one("tennis_combo3", "tennis_combo")
soon = _one("tennis_combo2", "tennis_combo")
far = _one("tennis_combo4", "tennis_combo")
eq(_attr(window, "data-active"), "1",
   "a fixture 36h away and no open bet is active (cutoff is 48 hours)")
eq(_attr(soon, "data-active"), "1",
   "a fixture 12h away and no open bet is active (inside 48 hours, not only the 24–48h band)")
eq(_attr(far, "data-active"), "0",
   "a fixture 72h away and no open bet stays inactive")
ok("No open game." in window and "Window Side v Keeper" not in window,
   "the back stays the open bets; an unstaked fixture is not listed there")
ok("No open game." in soon and "Soon Side v Tonight" not in soon,
   "a nearer unstaked fixture is not copied onto the back")
active_end = html.find('data-band="inactive"')
window_pos = html.find('data-source="tennis_combo3"')
soon_pos = html.find('data-source="tennis_combo2"')
far_pos = html.find('data-source="tennis_combo4"')
ok(0 < soon_pos < active_end and 0 < window_pos < active_end,
   "fixtures inside 48 hours sit in the active band")
ok(far_pos > active_end > 0, "a fixture past 48 hours sits in the inactive band")

late_pos = html.find('data-source="pm_combo2"')
ok(0 < window_pos < late_pos < active_end,
   "a pick in, but outside 48 hours, is active and below the nearer games")

print("\ncricket and soccer stay on their own pages")
ten = html
soc = soccer_build.build(d, st, NOW)
cri = cricket_build.build(d, st, NOW)
ok("Soccer Only v Stay" not in ten and "oddspedia" not in ten.lower(),
   "tennis cards do not pick up soccer or cricket lanes")
ok('class="rule-card"' in soc and "Soccer Only v Stay" in soc,
   "soccer still renders its own rule cards")
ok("tennis_fav_band_3h" not in soc and "Alpha v Beta soonest" not in soc,
   "soccer cards do not pick up tennis lanes")
ok('class="rule-card"' in cri and "Oddspedia" in cri,
   "cricket renders its own cards for the cricket lane in this ledger")
ok("By competition" not in cri,
   "cricket does not add the soccer by-competition panel")
ok("tennis_fav_band_3h" not in cri and "Alpha v Beta soonest" not in cri,
   "cricket does not pick up tennis lanes")

js = open(os.path.join(ROOT, "public_site", "tables.js"), encoding="utf-8").read()
ok("function wireRuleCards" in js and "is-flipped" in js and ".rule-flip" in js,
   "tables.js flips a card, including the focus restore, without an inline handler")
ok(js.count("function wireRuleCards") == 1, "tennis reuses the one card flip")

published = open(os.path.join(ROOT, "public_site", "tennis.html"), encoding="utf-8").read()
ok('class="rule-card"' in published and 'class="rule-grid"' in published,
   "public_site/tennis.html is the card page")
soc_file = open(os.path.join(ROOT, "public_site", "soccer.html"), encoding="utf-8").read()
cri_file = open(os.path.join(ROOT, "public_site", "cricket.html"), encoding="utf-8").read()
ok('class="rule-card"' in soc_file, "published soccer page still has its cards")
ok('class="rule-card"' in cri_file, "published cricket page has its own rule cards")


def _filtered_quote(i, source, sport, status, logged, label, league, tier, market_id,
                    bet=True, start=None):
    """One tennis quote. `logged` is the reset clock's own comparison string."""
    when = start or logged
    won = status == "won"
    price = 0.55
    return dict(
        id=f"filter:{source}:{market_id}",
        source=source, sport=sport, bet=bet, status=status,
        pick="b", price=price,
        result="b" if status in ("won", "lost") and won else ("a" if status in ("won", "lost") else None),
        venue="kalshi",
        pnl=(round(100 * (1 / price - 1), 2) if won else -100.0) if status in ("won", "lost") else None,
        start=when, logged=logged, date=logged[:10],
        price_a=price, price_b=round(1 - price, 2),
        side_a="Yes", side_b="No",
        label=label, league=league, tier=tier,
        market_id=market_id,
        url="https://kalshi.com/markets/example",
    )


print("\nrefused tours and pre-reset rows stay off the tennis page")
# The lane clocks are the stage rows the page already reads. An empty stages
# file would count the pre-reset bets, which is a different page.
fav_clock = S.TENNIS_FAV_KEEP_SINCE
combo_clock = S.TENNIS_COMBO_BAND_SINCE
fav_after = "2026-10-03T12:00:00+00:00"
fav_before = "2026-10-01T12:00:00+00:00"
combo_after = "2026-10-04T12:00:00+00:00"
combo_before = "2026-10-03T18:00:00+00:00"
KEPT_N = 2
GHOST_N = 4
filter_quotes = []
for i in range(KEPT_N):
    filter_quotes.append(_filtered_quote(
        i, "tennis_fav_band_3h", "tennis", "won", fav_after,
        f"Kept Atp Settled {i}", "ATP Kept League", "atp",
        f"aec-atp-kept-settled-{i}"))
    filter_quotes.append(_filtered_quote(
        i, "tennis_combo2", "tennis_combo", "won", combo_after,
        f"Kept Combo Settled {i}", "ATP Kept Combo", "atp",
        f"aec-atp-kept-combo-{i}"))
for i in range(GHOST_N):
    filter_quotes.append(_filtered_quote(
        i, "tennis_fav_band_3h", "tennis", "won", fav_after,
        f"GhostRefusedRow {i}", "GhostRefusedLeague", "wta",
        f"aec-wta-ghostrefused-{i}"))
    filter_quotes.append(_filtered_quote(
        i, "tennis_fav_band_3h", "tennis", "won", fav_before,
        f"GhostPreresetRow {i}", "GhostPreresetLeague", "atp",
        f"aec-atp-ghostprereset-{i}"))
    filter_quotes.append(_filtered_quote(
        i, "tennis_combo2", "tennis_combo", "won", combo_after,
        f"GhostComboRefused {i}", "GhostComboRefused", "wta",
        f"aec-wta-ghostcomborefused-{i}"))
    filter_quotes.append(_filtered_quote(
        i, "tennis_combo2", "tennis_combo", "lost", combo_before,
        f"GhostComboPrereset {i}", "GhostComboPrereset", "atp",
        f"aec-atp-ghostcomboprereset-{i}"))
filter_quotes.append(_filtered_quote(
    0, "tennis_fav_band_3h", "tennis", "open", fav_after,
    "GhostRefusedOpenLabel", "GhostRefusedLeague", "wta",
    "aec-wta-ghostrefused-open",
    start=(NOW + timedelta(hours=2)).isoformat()))
filter_quotes.append(_filtered_quote(
    1, "tennis_fav_band_3h", "tennis", "open", fav_after,
    "KeptOpenAtpLabel", "ATP Kept League", "atp",
    "aec-atp-kept-open",
    start=(NOW + timedelta(hours=3)).isoformat()))
filter_d = {"quotes": filter_quotes}
filter_st = {"pairs": {
    "tennis_fav_band_3h|tennis": {"stage": "sandbox", "since": fav_clock},
    "tennis_combo2|tennis_combo": {"stage": "sandbox", "since": combo_clock},
}}
filter_html = tennis_build.build(filter_d, filter_st, NOW)
filter_rows = _rows(filter_d, filter_st)
by_lane = {(r["name"], r["sport"]): r for r in filter_rows}
fav_row = by_lane.get(("tennis_fav_band_3h", "tennis"))
combo_row = by_lane.get(("tennis_combo2", "tennis_combo"))
ok(fav_row is not None and combo_row is not None,
   "the filtered fixture still lists the favourite band and the 2-leg combo")
if fav_row and combo_row:
    eq(fav_row["a"]["n"], KEPT_N,
       "the favourite-band record counts only kept tours logged after the reset")
    eq(combo_row["a"]["n"], KEPT_N,
       "the combo record counts only kept tours logged after its reset")
    fav_card = next((c for c in _cards(filter_html)
                     if _attr(c, "data-source") == "tennis_fav_band_3h"), "")
    combo_card = next((c for c in _cards(filter_html)
                       if _attr(c, "data-source") == "tennis_combo2"), "")
    ok(tennis_cards is not None and tennis_cards.roi_html(fav_row) in fav_card,
       "the favourite-band card ROI is the filtered lane row")
    ok(tennis_cards is not None and tennis_cards.verdict_html(fav_row) in fav_card,
       "the favourite-band card verdict is the filtered lane row")
    ok(tennis_cards is not None and tennis_cards.roi_html(combo_row) in combo_card,
       "the combo card ROI is the filtered lane row")
    ok("KeptOpenAtpLabel" in fav_card, "a kept open bet is still on the card back")
    ok("GhostRefusedOpenLabel" not in fav_card,
       "a refused-tour open bet is not on the card back")
# These names are the competition panel's own rows. Cards do not print a league.
for ghost in ("GhostRefusedLeague", "GhostPreresetLeague",
              "GhostComboRefused", "GhostComboPrereset",
              "GhostRefusedRow", "GhostPreresetRow",
              "GhostRefusedOpenLabel",
              "aec-wta-ghostrefused", "aec-atp-ghostprereset",
              "aec-wta-ghostcomborefused", "aec-atp-ghostcomboprereset"):
    ok(ghost not in filter_html, f"{ghost} never reaches the tennis page")
ok("By competition" not in filter_html,
   "tennis does not add the soccer by-competition panel")
ok("Bundesliga scored 3.49" not in filter_html,
   "tennis does not add the soccer competition note")
ok("How each rule is defined" in filter_html,
   "the rule definitions stay under the cards")
ok("within 3 hours of the scheduled start" in filter_html,
   "the 3-hour definition stays on the page")
# Unfiltered, the panel would print each ghost league's settled count.
ok(f"{GHOST_N} settled" not in filter_html and f"{KEPT_N + GHOST_N * 2} settled" not in filter_html,
   "a competition total that includes refused or pre-reset bets is not on the page")
ok("By competition" not in published,
   "published tennis page has no by-competition panel")
ok("Bundesliga scored 3.49" not in published,
   "published tennis page has no soccer competition note")
ok("How each rule is defined" in published,
   "published tennis page still has the rule definitions")
ok("By competition" in soc_file,
   "published soccer page still has its by-competition panel")

if FAILS:
    print(f"\nSHA {SHA} FAILED {len(FAILS)}")
    sys.exit(1)
print(f"\nSHA {SHA} PASSED")
