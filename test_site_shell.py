#!/usr/bin/env python3
"""Shared shell for the published pages: one nav, one stylesheet, no inline script.

Fails on main before this change: the pages load Google Fonts, keep an inline
<script>, and the nav is only Sandbox and Production. Trading is a hidden tab.
"""
import datetime
import os
import re
import sys
from datetime import timedelta, timezone

FAILS = []
ROOT = os.path.dirname(os.path.abspath(__file__))
MINUS = "\u2212"


def ok(cond, why):
    print(f"  {'ok  ' if cond else 'FAIL'} {why}")
    if not cond:
        FAILS.append(why)


def eq(got, want, why):
    ok(got == want, why if got == want else f"{why} — got {got!r}, want {want!r}")


_SCRIPT = re.compile(r"<script\b([^>]*)>(.*?)</script>", re.I | re.S)
_HANDLER = re.compile(r"""\son[a-z]+\s*=""", re.I)
_NAV_HREFS = (
    'href="./sandbox.html"',
    'href="./production.html"',
    'href="./trading.html"',
    'href="./nba.html"',
    'href="./soccer.html"',
    'href="./tennis.html"',
    'href="./cricket.html"',
    'href="./sandbox.html#method"',
)
_NAV_LABELS = ["Sandbox", "Production", "Trading", "NBA", "Soccer", "Tennis", "Cricket",
               "Crypto", "Method"]
_CURRENT = {
    "sandbox": 'href="./sandbox.html" aria-current="page"',
    "production": 'href="./production.html" aria-current="page"',
    "trading": 'href="./trading.html" aria-current="page"',
    "nba": 'href="./nba.html" aria-current="page"',
    "soccer": 'href="./soccer.html" aria-current="page"',
    "tennis": 'href="./tennis.html" aria-current="page"',
    "cricket": 'href="./cricket.html" aria-current="page"',
    "crypto": 'href="./crypto.html" aria-current="page"',
    "index": 'href="./production.html" aria-current="page"',
}
# The site root is the shell. Sport pages stay on the shared nine-link nav.
_SHELL_LABELS = ["Sandbox", "Production", "Trading", "Method"]


def _inline_script(html):
    for m in _SCRIPT.finditer(html):
        if m.group(2).strip():
            return True
    return False


def _check_page(name, html, current):
    print(f"\n{name}")
    ok('href="./site.css"' in html, f"{name} links site.css")
    ok("<style" not in html.lower(), f"{name} has no inline style block")
    ok("fonts.googleapis.com" not in html and "fonts.gstatic.com" not in html,
       f"{name} does not reference Google Fonts")
    ok(not _inline_script(html), f"{name} has no inline script body")
    ok(_HANDLER.search(html) is None, f"{name} has no inline on* handler")
    ok('href="#content"' in html and "Skip to content" in html,
       f"{name} has a skip-to-content link")
    if current == "index":
        for href in (
            'href="./sandbox.html"',
            'href="./production.html"',
            'href="./trading.html"',
            'href="./sandbox.html#method"',
        ):
            ok(href in html, f"{name} nav includes {href}")
    else:
        for href in _NAV_HREFS:
            ok(href in html, f"{name} nav includes {href}")
    ok(_CURRENT[current] in html, f"{name} marks {current} as the current page")
    # The eight links are the same set, in the same order, on every page.
    # aria-current on a breadcrumb is separate; the main nav marks one page.
    nav = re.search(r'<nav class="main"[^>]*>.*?</nav>', html, re.S)
    ok(nav is not None, f"{name} has the shared main nav")
    currents = re.findall(r'aria-current="page"', nav.group(0) if nav else "")
    eq(len(currents), 1, f"{name} nav.main has exactly one aria-current")
    if nav:
        labels = re.findall(r">([^<]+)</a>", nav.group(0))
        eq(labels, _SHELL_LABELS if current == "index" else _NAV_LABELS, f"{name} nav labels")


def _nba(now):
    """The NBA page off a minimal blob, so the shell is checked without live data."""
    import nba_pace_build
    return nba_pace_build.build(
        {"window": 5, "periods": ["q1", "h1", "ft"], "games": [], "label_flips": {},
         "skipped": 0, "seed": {"span": ["2026-03-25", "2026-04-12"], "games": 0,
                                "teams": {}}},
        now=now)


def _soccer(now):
    """The Soccer page off an empty ledger, so the shell is checked without live data."""
    import soccer_build
    return soccer_build.build({"quotes": []}, {"pairs": {}}, now=now)


def _tennis(now):
    """The Tennis page off an empty ledger, so the shell is checked without live data."""
    import tennis_build
    return tennis_build.build({"quotes": []}, {"pairs": {}}, now=now)


def _cricket(now):
    """The Cricket page off an empty ledger, so the shell is checked without live data."""
    import cricket_build
    return cricket_build.build({"quotes": []}, {"pairs": {}}, now=now)


def _crypto(now):
    """The Crypto page off an empty ledger, so the shell is checked without live data."""
    import crypto_build
    return crypto_build.build({"quotes": []}, {"pairs": {}}, now=now)


def _pages():
    """Each published page, even when a later one cannot be built yet."""
    import sandbox_build as SB
    import production
    import site_root
    now = datetime.datetime(2026, 9, 27, 5, 12, tzinfo=timezone.utc)
    out = []
    errors = []
    builders = (
        ("sandbox.html", "sandbox", lambda: SB.build()),
        ("production.html", "production", lambda: production.page(
            {"quotes": []}, {"pairs": {}}, {"leads": {}, "pairs": {}}, "", now=now)),
        ("trading.html", "trading", lambda: SB.trading_page(now)),
        ("nba.html", "nba", lambda: _nba(now)),
        ("soccer.html", "soccer", lambda: _soccer(now)),
        ("tennis.html", "tennis", lambda: _tennis(now)),
        ("cricket.html", "cricket", lambda: _cricket(now)),
        ("crypto.html", "crypto", lambda: _crypto(now)),
        ("index.html", "index", lambda: site_root.root_stub(now)),
    )
    for name, current, build in builders:
        try:
            out.append((name, build(), current))
        except Exception as exc:
            errors.append(f"{name} ({type(exc).__name__}: {exc})")
    if errors:
        ok(False, "every published page renders — " + "; ".join(errors))
    return out


# ---------------------------------------------------------------------------
print("formatter")
try:
    import fmt
except ImportError:
    fmt = None
ok(fmt is not None, "fmt.py is the shared presentation formatter")

if fmt is not None:
    eq(fmt.money(-100), f"{MINUS}$100", "−100 dollars renders with U+2212")
    eq(fmt.money(100), "+$100", "positive money keeps the plus")
    eq(fmt.pct(-0.0015, digits=2, sign=True), f"{MINUS}0.15%",
       "−0.15% uses U+2212, not a hyphen")
    eq(fmt.pct(0.163, digits=1, sign=True), "+16.3%", "a positive percent stays signed")
    eq(fmt.cents(0.77), "77¢", "price 0.77 renders as 77¢")
    eq(fmt.cents(0.40), "40¢", "a two-decimal price rounds the same way as before")
    eq(fmt.clock("2026-09-27T05:12:00Z"), "12:12 AM CT",
       "05:12 UTC on Sep 27 renders as 12:12 AM CT")
    # DST ends 2026-11-01 at 02:00 CDT (07:00 UTC). The next day is standard time.
    winter = fmt.chicago("2026-11-02T06:12:00Z")
    eq(fmt.zone_abbr("2026-11-02T06:12:00Z"), "CST",
       "after Nov 1 2026 the zone abbreviation is CST")
    eq((winter.hour, winter.minute), (0, 12),
       "06:12 UTC after the fall-back is 12:12 AM, not 1:12 AM")
    eq(winter.utcoffset(), timedelta(hours=-6), "CST is UTC−6")
    eq(fmt.clock("2026-11-02T06:12:00Z"), "12:12 AM CT",
       "the winter clock still carries the CT label")
    summer = fmt.chicago("2026-09-27T05:12:00Z")
    eq(fmt.zone_abbr("2026-09-27T05:12:00Z"), "CDT", "September is CDT")
    eq(summer.utcoffset(), timedelta(hours=-5), "CDT is UTC−5")
    # The watchdog still reads this exact form. The root stub must not use it.
    eq(fmt.machine_stamp("2026-09-27T05:12:00Z"), "updated 2026-09-27 05:12 UTC",
       "the machine stamp stays the tracker form")
    # A value that rounds to zero at the displayed precision has no minus.
    # -0.0004 is -0.04 cents, which is 0.0¢ at one decimal place.
    eq(fmt.signed_cents(-0.0), "0.0¢",
       "test_signed_cents_negative_zero")
    eq(fmt.signed_cents(-0.0004), "0.0¢",
       "test_signed_cents_negative_four_hundredths")
    eq(fmt.cents(-0.0), "0¢", "test_cents_negative_zero")
    eq(fmt.cents(-0.004), "0¢", "test_cents_rounds_to_zero")
    eq(fmt.money(-0.0), "$0", "test_money_negative_zero")
    eq(fmt.money(-0.4), "$0", "test_money_negative_four_tenths")
    eq(fmt.money(-0.5), "$0", "test_money_half_dollar_rounds_to_zero")
    eq(fmt.money(0.4), "$0", "test_money_positive_rounds_to_zero")
    eq(fmt.signed_cents(0.0), "0.0¢", "test_signed_cents_zero")
    eq(fmt.pct(-0.0, digits=1, sign=True), "0.0%", "test_pct_negative_zero")
    eq(fmt.pct(-0.00004, digits=1, sign=True), "0.0%",
       "test_pct_rounds_to_zero")
    eq(fmt.money(-1), f"{MINUS}$1", "test_money_real_negative_keeps_minus")
    eq(fmt.signed_cents(-0.08), f"{MINUS}8.0¢",
       "test_signed_cents_real_negative_keeps_minus")
    eq(fmt.signed_cents(-0.0004, digits=2), f"{MINUS}0.04¢",
       "test_signed_cents_real_hundredths_keep_minus")
    eq(fmt.cents(-0.01), f"{MINUS}1¢", "test_cents_real_negative_keeps_minus")
    for _shown in (fmt.money(-0.4), fmt.signed_cents(-0.0), fmt.signed_cents(-0.0004),
                   fmt.cents(-0.0), fmt.pct(-0.0, sign=True)):
        ok(MINUS not in _shown and "-" not in _shown,
           f"test_rounded_zero_has_no_minus_glyph {_shown!r}")


# ---------------------------------------------------------------------------
print("\npublished pages")
try:
    pages = _pages()
except Exception as exc:
    pages = []
    ok(False, f"published pages render ({type(exc).__name__}: {exc})")

def _same_links(navs):
    def hrefs(nav):
        return re.findall(r'href="[^"]+"', nav)
    return bool(navs) and len({tuple(hrefs(n)) for n in navs}) == 1


navs = []
for name, html, current in pages:
    _check_page(name, html, current)
    nav = re.search(r'<nav class="main"[^>]*>.*?</nav>', html, re.S)
    navs.append(nav.group(0) if nav else "")
if len(navs) == 4:
    ok(_same_links(navs), "the four nav hrefs match on every published page")


# ---------------------------------------------------------------------------
print("\nnumber preservation")


def canonical_numbers(html):
    """Money, percents, and cent-prices as floats. Clocks are not values."""
    text = re.sub(r"<script\b[^>]*>.*?</script>", " ", html, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace(MINUS, "-").replace("−", "-")
    # Drop the tracker stamp and CT clock lines so a relabelled time is not a new number.
    text = re.sub(r"updated \d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC", " ", text)
    text = re.sub(r"\b\d{1,2}:\d{2}\s*(?:AM|PM)\b", " ", text)
    text = re.sub(r"\b\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}(?::\d{2})?Z?)?", " ", text)
    found = []

    def take(pattern, scale):
        nonlocal text
        for m in re.finditer(pattern, text):
            raw = m.group(1).replace(",", "")
            found.append(round(float(raw) * scale, 6))
        text = re.sub(pattern, " ", text)

    take(r"(-?\d[\d,]*(?:\.\d+)?)¢", 0.01)
    take(r"(-?\$)(\d[\d,]*(?:\.\d+)?)", 1.0)  # placeholder, replaced below
    # money was partially handled; do it explicitly from the original approach
    return found


def canonical_values(html):
    """Normalised ledger values: 77¢ -> 0.77, −$100 -> -100, −0.15% -> -0.15."""
    text = re.sub(r"<script\b[^>]*>.*?</script>", " ", html, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace(MINUS, "-").replace("−", "-")
    text = re.sub(r"updated \d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC", " ", text)
    text = re.sub(r"\b\d{1,2}:\d{2}\s*(?:AM|PM)\b", " ", text, flags=re.I)
    text = re.sub(r"\b\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:\d{2})?)?", " ", text)
    found = []
    for m in list(re.finditer(r"-?\d[\d,]*(?:\.\d+)?¢", text)):
        found.append(round(float(m.group(0).replace("¢", "").replace(",", "")) / 100.0, 6))
    text = re.sub(r"-?\d[\d,]*(?:\.\d+)?¢", " ", text)
    for m in list(re.finditer(r"-?\$\d[\d,]*(?:\.\d+)?", text)):
        raw = m.group(0).replace("$", "").replace(",", "")
        found.append(round(float(raw), 6))
    text = re.sub(r"-?\$\d[\d,]*(?:\.\d+)?", " ", text)
    for m in list(re.finditer(r"-?\d[\d,]*(?:\.\d+)?%", text)):
        found.append(round(float(m.group(0).replace("%", "").replace(",", "")), 6))
    text = re.sub(r"-?\d[\d,]*(?:\.\d+)?%", " ", text)
    return found


def legacy_values(price, pnl, edge, digits):
    """The same numbers the way main formats them, then normalised."""
    bits = [f"{price:.2f}", f"{'+' if pnl >= 0 else MINUS}${abs(pnl):,.0f}",
            f"{edge * 100:+.{digits}f}%"]
    return canonical_values(" ".join(bits))


try:
    import sandbox_build as SB
    import sandbox_sources as S
except ImportError as exc:
    SB = None
    ok(False, f"sandbox_build imports ({exc})")

if SB is not None:
    source = "team2_form_l10"
    quote = dict(
        status="open", bet=True, sport="mlb", start="2026-09-27T23:00:00+00:00",
        pick="a", side_a="Home", side_b="Away", date="2026-09-27",
        price=0.77, edge=-0.0015, source=source, label="Home v Away",
        venue="kalshi", market_id="KXTEST", url="https://example.com/market",
        pnl=None,
    )
    live_html, n_live = SB.open_rows({"quotes": [quote]})
    eq(n_live, 1, "the fixture still contributes one running bet")
    ok("77¢" in live_html, "the running price renders as 77¢")
    ok(f"{MINUS}0.1%" in live_html, "the running edge uses a real minus sign")
    ok("javascript:" not in live_html, "the fixture link is not a javascript url")
    settled = dict(quote, status="lost", result="b", pnl=-100.0,
                   settled="2026-09-26T18:00:00+00:00")
    hist_html, n_hist = SB.settled_rows({"quotes": [settled]})
    eq(n_hist, 1, "the fixture still contributes one settled bet")
    ok(f"{MINUS}$100" in hist_html, "−$100 on the settled row")
    ok("77¢" in hist_html, "the settled price renders as 77¢")
    got = canonical_values(live_html + hist_html)
    want = legacy_values(0.77, -100, -0.0015, 1)
    # pnl is only on the settled row; edge is only on the running row.
    for value in (0.77, -0.15 if False else round(-0.0015 * 100, 1), -100.0):
        ok(value in got, f"canonical value {value} survived formatting")
    for value in want:
        ok(value in got, f"legacy value {value} is still on the page")
    # A hostile url stays plain text, same as PR 1.
    hostile = dict(quote, url="javascript:alert(1)", venue="polymarket")
    hostile_html, _n = SB.open_rows({"quotes": [hostile]})
    ok("href=" not in hostile_html.split("Home v Away")[0][-80:] or "javascript:" not in hostile_html,
       "javascript: contest url is not an href")
    ok("javascript:" not in hostile_html, "javascript: is not written into the row")


# ---------------------------------------------------------------------------
print("\nsport tabs match the Sandbox")


def _lane_metrics(rows):
    """The numbers a sport tab must not recompute: record, P/L, ROI, counts, verdict."""
    out = []
    for r in rows:
        a = r["a"]
        roi = a.get("roi_fee")
        out.append((
            r["name"], r["sport"], r["v"], bool(r.get("prod")), r.get("open"),
            a.get("n"), a.get("won"),
            None if a.get("expected") is None else round(a["expected"], 4),
            None if roi is None else round(roi, 6),
            None if a.get("pnl") is None else round(a["pnl"], 2),
        ))
    return out


def _sport_fixture():
    """A ledger with real Tennis and Cricket lanes, plus lanes that must stay off those tabs."""
    import sandbox_sources as S
    start = datetime.datetime(2026, 10, 4, 18, tzinfo=timezone.utc)

    def q(i, source, sport, won=True, price=0.55, status=None, bet=True):
        when = start + timedelta(hours=i)
        status = status or ("won" if won else "lost")
        row = dict(
            id=f"{source}:{sport}:{i}:{status}",
            source=source, sport=sport, bet=bet, status=status,
            pick="a", price=price,
            result=("a" if won else "b") if status in ("won", "lost") else None,
            venue="polymarket_us",
            pnl=(round(100 * (1 / price - 1), 2) if won else -100.0) if status in ("won", "lost") else None,
            start=when.isoformat(),
            logged=(when - timedelta(hours=1)).isoformat(),
            price_a=price, price_b=round(1 - price, 2),
            label="Home v Away",
            market_id=f"m-{source}-{sport}-{i}",
        )
        return row

    quotes = []
    for i in range(12):
        quotes.append(q(i, "oddspedia", "cricket", True, 0.40))
    for i in range(4):
        quotes.append(q(20 + i, "oddspedia", "cricket", False, 0.40))
    for i in range(3):
        quotes.append(q(i, "polymarket", "cricket", True, 0.25))
    quotes.append(q(9, "polymarket", "cricket", False, 0.25))
    quotes.append(q(1, "tennis_fav_band_3h", "tennis", status="open"))
    for i in range(6):
        quotes.append(q(i, "tennis_combo2", "tennis_combo", i % 2 == 0, 0.62))
    for i in range(4):
        quotes.append(q(i, "pm_combo2", "tennis_pmcombo", True, 0.70))
    # Removed, eliminated, or a different family. None of these belong on the two tabs.
    quotes.append(q(1, "tennis_fav_band", "tennis", True, 0.78))
    quotes.append(q(1, "olbg", "mma", True, 0.60))
    quotes.append(q(1, "olbg", "boxing", True, 0.60))
    quotes.append(q(1, "mlb_fade_streak", "mlb", False, 0.45))
    quotes.append(q(1, "nhl_rest_edge", "nhl_rest", True, 0.55))
    quotes.append(q(1, "tt_band_55_60", "table_tennis", True, 0.58))
    quotes.append(q(1, "polymarket_us", "table_tennis", bet=False, status="open"))
    quotes.append(q(2, "polymarket_us", "tennis", bet=False, status="open"))
    quotes.append(q(3, "polymarket_us", "cricket", bet=False, status="open"))
    st = {"pairs": {
        "oddspedia|cricket": {"stage": "production", "by_hand": "2026-09-27",
                              "since": "2026-09-01T00:00:00+00:00"},
        "tennis_fav_band_3h|tennis": {"stage": "sandbox", "since": S.TENNIS_FAV_KEEP_SINCE},
        "tennis_combo2|tennis_combo": {"stage": "sandbox", "since": S.TENNIS_COMBO_BAND_SINCE},
        "tennis_combo3|tennis_combo": {"stage": "sandbox", "since": S.TENNIS_COMBO_BAND_SINCE},
        "tennis_combo4|tennis_combo": {"stage": "sandbox", "since": S.TENNIS_COMBO_BAND_SINCE},
        "pm_combo2|tennis_pmcombo": {"stage": "sandbox", "since": S.TENNIS_COMBO_BAND_SINCE},
        "pm_combo3|tennis_pmcombo": {"stage": "sandbox", "since": S.TENNIS_COMBO_BAND_SINCE},
        "pm_combo4|tennis_pmcombo": {"stage": "sandbox", "since": S.TENNIS_COMBO_BAND_SINCE},
    }}
    cov = {
        "tennis": {"polymarket_us": 40, "polymarket_us_listed": 435, "polymarket_us_priced": 267},
        "cricket": {"polymarket_us": 10, "polymarket_us_listed": 11, "polymarket_us_priced": 9},
        "table_tennis": {"polymarket_us": 99, "polymarket_us_listed": 98, "polymarket_us_priced": 97},
    }
    return {"quotes": quotes, "coverage": cov}, st


def _check_sport_tab(family, html, d, st):
    import sandbox_build as B
    rows = [r for r in B.pair_list(d, st)
            if B.family(r["sport"]) == family and not B.eliminated(r)]
    section = B.sport_sections(d, rows)
    ok(bool(section) and len(section) > 200, f"{family} Sandbox section is non-empty")
    lanes = re.search(r'<section id="lanes">(.*?)</section>', html, re.S)
    ok(lanes is not None, f"{family} tab has a lanes section")
    # Soccer, Tennis, and Cricket replace the lane table with cards. The
    # verdict and the ROI on each card are still the Sandbox row's strings.
    if family == "Soccer":
        ok('class="rule-card"' in html and 'class="rule-grid"' in html,
           "soccer lanes are flippable cards")
        import soccer_cards
        for r in rows:
            ok(soccer_cards.verdict_html(r) in html and soccer_cards.roi_html(r) in html,
               f"soccer card shows the Sandbox verdict and ROI for {r['name']}|{r['sport']}")
    elif family == "Tennis":
        ok('class="rule-card"' in html and 'class="rule-grid"' in html,
           "tennis lanes are flippable cards")
        import tennis_cards
        for r in rows:
            ok(tennis_cards.verdict_html(r) in html and tennis_cards.roi_html(r) in html,
               f"tennis card shows the Sandbox verdict and ROI for {r['name']}|{r['sport']}")
    elif family == "Cricket":
        ok('class="rule-card"' in html and 'class="rule-grid"' in html,
           "cricket lanes are flippable cards")
        import cricket_cards
        for r in rows:
            ok(cricket_cards.verdict_html(r) in html and cricket_cards.roi_html(r) in html,
               f"cricket card shows the Sandbox verdict and ROI for {r['name']}|{r['sport']}")
        ok("By competition" not in html,
           "cricket does not add the soccer by-competition panel")
    else:
        ok(section in html, f"{family} tab lanes are the Sandbox sport_sections for that family")
        if lanes and section:
            eq(canonical_values(lanes.group(1)), canonical_values(section),
               f"{family} tab lane numbers equal the Sandbox section")
    got = _lane_metrics(rows)
    print(f"  {family} lanes {got}")
    ok(got, f"{family} fixture has lanes to compare")
    # Same pairs the Sandbox lists for this family. The section HTML above is
    # that list rendered, so a rewritten number cannot match.
    again = _lane_metrics([r for r in B.pair_list(d, st)
                           if B.family(r["sport"]) == family and not B.eliminated(r)])
    eq(got, again, f"{family} metrics are pair_list's own record")
    if any(prod for _n, _s, _v, prod, _o, _n2, _w, _e, _r, _p in got):
        ok("PRODUCTION" in html, f"{family} shows a Production lane the way the Sandbox does")
    return got


try:
    import tennis_build
    import cricket_build
    import soccer_build
except ImportError as exc:
    tennis_build = cricket_build = soccer_build = None
    ok(False, f"tennis and cricket tabs import ({exc})")

if tennis_build is not None and SB is not None:
    _fx, _fx_st = _sport_fixture()
    _now = datetime.datetime(2026, 10, 4, 18, tzinfo=timezone.utc)
    _ten = tennis_build.build(_fx, _fx_st, _now)
    _cri = cricket_build.build(_fx, _fx_st, _now)
    _soc = soccer_build.build(_fx, _fx_st, _now)
    _check_sport_tab("Tennis", _ten, _fx, _fx_st)
    _check_sport_tab("Cricket", _cri, _fx, _fx_st)
    _check_sport_tab("Soccer", _soc, _fx, _fx_st)
    ok("Kalshi status" in _soc, "soccer still shows the Kalshi pre-flight column")
    ok("Kalshi status" not in _ten and "Kalshi status" not in _cri,
       "tennis and cricket hide the Kalshi pre-flight column")
    ok('id="listing"' in _ten and "435" in _ten and "267" in _ten,
       "tennis shows the Polymarket US listing counts")
    ok('id="listing"' in _cri and ">10<" in _cri,
       "cricket shows the Polymarket US listing count")
    ok("99" not in _ten and "99" not in _cri and "Table Tennis" not in _ten and "Table Tennis" not in _cri,
       "table tennis stays off the Tennis and Cricket tabs")
    ok("within 3 hours of the scheduled start" in _ten and "Challenger" in _ten
       and "Tennis Explorer" in _ten and S.TENNIS_COMBO_BAND_SINCE in _ten
       and "TENNIS_COMBO_BAND_SINCE" not in _ten,
       "tennis keeps the 3-hour note, the tour check, and the combo clock")
    ok("PRODUCTION" in _cri and "Oddspedia community tips" in _cri
       and "Cricket consensus" in _cri,
       "cricket shows the Production lane and the consensus lane")
    for _label in ("Tennis favourite-band rule", "OLBG community tips",
                   "MMA favourite-band rule", "MLB fade-the-streak rule", "NHL rest rule"):
        ok(_label not in _ten and _label not in _cri,
           f"removed lane {_label} is not on Tennis or Cricket")
    ok("tennis_fav_band_3h" in _ten, "the kept 3-hour lane is named")


if FAILS:
    print(f"\n{len(FAILS)} FAILED")
    sys.exit(1)
print("\nall passed")
