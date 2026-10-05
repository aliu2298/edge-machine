#!/usr/bin/env python3
"""Soccer rule rows render as flippable cards. Tennis and cricket stay tables.

Presentation only. The verdict word and the ROI text are the Sandbox row's own
figures, compared as strings. Nothing here grades a bet or writes a ledger.
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
        market_id=f"KXTEST-{source}-{i}",
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
    """Two markets. Active rules have open games; inactive rules do not."""
    quotes = []
    quotes += _settled("o15_form_l10", "soccer_o15", n=6, won=4)
    quotes += _settled("o15_ranked", "soccer_o15", n=4, won=1, price=0.70)
    quotes += _settled("o15_form_l10", "soccer_o15_cup", n=3, won=2)
    quotes += _settled("btts_form_l10", "soccer_btts", n=5, won=2, price=0.48)
    quotes += _settled("corners_under", "soccer_corners", n=4, won=3, price=0.52)
    # Soonest four of five open games on the over-1.5 form rule. The fifth is later.
    soon = [
        (1, "Alpha v Beta soonest"),
        (2, "Gamma v Delta second"),
        (3, "Epsilon v Zeta third"),
        (4, "Eta v Theta fourth"),
        (30, "Iota v Kappa fifth and later"),
    ]
    for i, (hours, label) in enumerate(soon):
        quotes.append(_quote(100 + i, "o15_form_l10", "soccer_o15", "open", hours, label))
    # A second active rule in the same market, kicking off later the same day.
    quotes.append(_quote(
        200, "o15_ranked", "soccer_o15", "open", 20, "Lambda v Mu ranked"))
    # Active in another market, inside 48 hours, after the over-1.5 games.
    quotes.append(_quote(
        300, "btts_form_l10", "soccer_btts", "open", 40, "Nu v Xi btts"))
    # Open, but the kickoff is past 48 hours: still receiving a pick, so active,
    # and ordered after rules whose game is inside the window.
    quotes.append(_quote(
        400, "corners_under", "soccer_corners", "open", 80, "Omicron v Pi later"))
    # A label and a url the card must not turn into markup or a script link.
    quotes.append(_quote(
        401, "corners_under", "soccer_corners", "open", 90,
        'Rho <script>alert(1)</script> v "Sigma"',
        url="javascript:alert(1)",
        venue="polymarket_us",
    ))
    # A record, no open bet, and a fixture the tracker already logged without a
    # stake. 36h is inside the 48h cutoff and outside a 24h one. 12h is inside
    # both, so a window that skips the next day would miss it.
    quotes += _settled("team1_form_l5", "soccer_team1", n=4, won=3, price=0.62)
    quotes.append(_quote(
        500, "team1_form_l5", "soccer_team1", "open", 36,
        "Window Side v Keeper", bet=False))
    quotes += _settled("team2_ranked", "soccer_team2", n=4, won=2, price=0.58)
    quotes.append(_quote(
        501, "team2_ranked", "soccer_team2", "open", 12,
        "Soon Side v Tonight", bet=False))
    # Same shape, kickoff past 48 hours. Not an open bet, so it stays inactive.
    quotes += _settled("team1_form_l5", "soccer_team1_cup", n=3, won=1, price=0.61)
    quotes.append(_quote(
        502, "team1_form_l5", "soccer_team1_cup", "open", 72,
        "Far Side v Later", bet=False))
    return {"quotes": quotes}, {"pairs": {}}


def _rows(d, st):
    import sport_tab
    return sport_tab.family_rows(d, st, "Soccer")


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

import soccer_build
import tennis_build
import cricket_build

print("\nsoccer cards")
d, st = _fixture()
html = soccer_build.build(d, st, NOW)
rows = _rows(d, st)
ok(rows, "the fixture has soccer lanes")
ok('class="rule-grid"' in html, "soccer lanes use a card grid")
ok('class="rule-card"' in html, "soccer lanes are flippable cards")
ok('class="rule-flip"' in html, "each card has a flip control")
ok("<script" not in html.split("<main", 1)[-1].split("</main>", 1)[0].lower()
   or 'src="./' in html, "the page body does not grow an inline script")
ok("javascript:" not in html, "a javascript: game url is not written")
ok("&lt;script&gt;" in html, "a game label is escaped")
ok('class="rule-grid"' in html and "repeat(4" in open(
    os.path.join(ROOT, "public_site", "site.css"), encoding="utf-8").read(),
   "the grid is four columns")

cards = _cards(html)
ok(len(cards) == len(rows), f"one card per soccer lane with a record ({len(cards)} cards, {len(rows)} lanes)")

actives = [_attr(c, "data-active") for c in cards]
if "0" in actives and "1" in actives:
    split = actives.index("0")
    ok(set(actives[:split]) == {"1"} and set(actives[split:]) == {"0"},
       "active cards are a single block above inactive cards")
else:
    ok(False, "the fixture has both an active card and an inactive card")

by_sport = {}
for c in cards:
    by_sport.setdefault(_attr(c, "data-sport"), []).append(c)

form = by_sport.get("soccer_o15", [""])[0]
ok("Alpha v Beta soonest" in form and "Eta v Theta fourth" in form,
   "the back lists the soonest open games")
ok("Iota v Kappa fifth and later" not in form,
   "the back stops at four open games")
ok("4 of 5 open" in form, "a longer slate says four of the open count")
ok("Gamma v Delta second" in form and "Epsilon v Zeta third" in form,
   "the other two soonest games are on the back")

# Front text is the helper's own verdict and ROI, character for character.
for row in rows:
    card = next(c for c in cards if _attr(c, "data-source") == row["name"]
                and _attr(c, "data-sport") == row["sport"])
    roi = _roi_html(row)
    verdict = _verdict_html(row)
    ok(roi in card, f"{row['name']}|{row['sport']} front ROI matches the Sandbox row")
    ok(verdict in card, f"{row['name']}|{row['sport']} front verdict matches the Sandbox row")
    want_active = _expect_active(row, d, NOW)
    eq(_attr(card, "data-active"), want_active,
       f"{row['name']}|{row['sport']} active flag is an open bet or a fixture inside 48 hours")

# Same market, two active rules: the sooner kickoff is first in that grid.
active_html = html.split('data-band="inactive"', 1)[0]
o15_names = [_attr(c, "data-source") for c in _cards(active_html)
             if _attr(c, "data-market") == "soccer_o15"]
eq(o15_names, ["o15_form_l10", "o15_ranked"],
   "the active over-1.5 row puts the sooner kickoff first")
ok('data-market="soccer_o15"' in html and 'class="rule-grid"' in html,
   "over 1.5 is its own market row")

grids = re.findall(r'<div class="rule-grid">(.*?)</div>', html, re.S)
ok(any(g.count('class="rule-card"') >= 1 for g in grids), "a market row holds its cards in one grid")
ok('data-band="active"' in html and 'data-band="inactive"' in html,
   "active and inactive are separate bands")
# The cup twin has no open game, so it is not in the active over-1.5 row.
ok('data-sport="soccer_o15_cup"' in html, "the cup twin still has a card")
cup_pos = html.find('data-sport="soccer_o15_cup"')
active_end = html.find('data-band="inactive"')
ok(cup_pos > active_end > 0, "the cup twin, with nothing open, sits in the inactive band")

# No open bet. The fixture is one the tracker already stored (bet false, status
# open). 36h is past a 24h cutoff and inside 48h. 12h is inside the next day,
# which the 48h cutoff still counts. 72h is outside it.
def _one(source, sport):
    return next(c for c in cards if _attr(c, "data-source") == source
                and _attr(c, "data-sport") == sport)

window = _one("team1_form_l5", "soccer_team1")
soon = _one("team2_ranked", "soccer_team2")
far = _one("team1_form_l5", "soccer_team1_cup")
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
window_pos = html.find('data-sport="soccer_team1"')
soon_pos = html.find('data-sport="soccer_team2"')
far_pos = html.find('data-sport="soccer_team1_cup"')
ok(0 < soon_pos < active_end and 0 < window_pos < active_end,
   "fixtures inside 48 hours sit in the active band")
ok(far_pos > active_end > 0, "a fixture past 48 hours sits in the inactive band")

# Corners is receiving picks (open games past 48h), so it stays active and after
# the rules whose game is inside 48 hours.
corners_pos = html.find('data-sport="soccer_corners"')
btts_pos = html.find('data-sport="soccer_btts"')
ok(0 < btts_pos < corners_pos < active_end,
   "a pick in, but outside 48 hours, is active and below the nearer games")

print("\nother sports stay tables")
ten = tennis_build.build(d, st, NOW)
cri = cricket_build.build(d, st, NOW)
for name, page in (("tennis", ten), ("cricket", cri)):
    ok("rule-card" not in page and "rule-grid" not in page and "rule-flip" not in page,
       f"{name} does not use the soccer card markup")
    ok('id="lanes"' in page and "<table" in page,
       f"{name} lanes are still a table")

css = open(os.path.join(ROOT, "public_site", "site.css"), encoding="utf-8").read()
js = open(os.path.join(ROOT, "public_site", "tables.js"), encoding="utf-8").read()
ok(".rule-grid" in css and "repeat(4, minmax(0, 1fr))" in css,
   "site.css lays the soccer grid out in four columns")
ok("function wireRuleCards" in js and "is-flipped" in js,
   "tables.js flips a soccer card without an inline handler")

published = open(os.path.join(ROOT, "public_site", "soccer.html"), encoding="utf-8").read()
ok('class="rule-card"' in published and 'class="rule-grid"' in published,
   "public_site/soccer.html is the card page")
ten_file = open(os.path.join(ROOT, "public_site", "tennis.html"), encoding="utf-8").read()
cri_file = open(os.path.join(ROOT, "public_site", "cricket.html"), encoding="utf-8").read()
ok("rule-card" not in ten_file and "rule-card" not in cri_file,
   "published tennis and cricket pages have no soccer card")

if FAILS:
    print(f"\nSHA {SHA} FAILED {len(FAILS)}")
    sys.exit(1)
print(f"\nSHA {SHA} PASSED")
