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
    'href="./sandbox.html#method"',
)
_CURRENT = {
    "sandbox": 'href="./sandbox.html" aria-current="page"',
    "production": 'href="./production.html" aria-current="page"',
    "trading": 'href="./trading.html" aria-current="page"',
    "index": 'href="./sandbox.html" aria-current="page"',
}


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
    for href in _NAV_HREFS:
        ok(href in html, f"{name} nav includes {href}")
    currents = re.findall(r'aria-current="page"', html)
    eq(len(currents), 1, f"{name} has exactly one aria-current")
    ok(_CURRENT[current] in html, f"{name} marks {current} as the current page")
    # The four links are the same set, in the same order, on every page.
    nav = re.search(r'<nav class="main"[^>]*>.*?</nav>', html, re.S)
    ok(nav is not None, f"{name} has the shared main nav")
    if nav:
        labels = re.findall(r">([^<]+)</a>", nav.group(0))
        eq(labels, ["Sandbox", "Production", "Trading", "Method"],
           f"{name} nav labels")


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
    source = next(k for k, m in S.SOURCES.items() if "mlb" in m.get("sports", []))
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


if FAILS:
    print(f"\n{len(FAILS)} FAILED")
    sys.exit(1)
print("\nall passed")
