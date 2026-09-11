"""Headless-browser fetch, isolated behind one function.

Scores24 sits behind Cloudflare, which 403s every plain request — any user-agent, any
header set, from this machine and from GitHub's runners alike. It is not a header
problem and no amount of curl tuning solves it: the check wants a real browser engine.
So this module drives one.

It lives apart from sandbox_sources on purpose. Everything else in this pipeline is
stdlib-only and must keep working when Playwright is absent — a missing browser has to
degrade to "this source reported nothing", visibly, and never take the run down with it.
"""

import re

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")

# Cloudflare fingerprints the automation, not the IP. Plain headless Playwright was
# served the interstitial forever on Oddspedia while a normal browser on the SAME
# connection walked straight in — so this is not rate limiting and waiting longer does
# not help. Three things together clear it: the automation flag off, navigator.webdriver
# masked, and a UA that matches a real recent Chrome.
LAUNCH_ARGS = ["--no-sandbox", "--disable-dev-shm-usage",
               "--disable-blink-features=AutomationControlled"]

STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
window.chrome = {runtime: {}};
Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
"""

# Text Cloudflare shows while it is deciding. Seeing this is not failure — it is the
# interstitial, and it clears on its own within a few seconds.
CHALLENGE = ("just a moment", "verify you are human", "checking your browser",
             "enable javascript and cookies")

# Pulls every prediction link on a listing page together with its own visible text.
# The <a> is the row: the whole line — players, time, tip, confidence, price — is inside
# it. Nothing above it is a reliable container, and the class names are hashed by
# styled-components, so they change on any deploy and cannot be selected on.
ROW_JS = """() => [...document.querySelectorAll('a[href*="-prediction"]')].map(a => ({
  href: a.getAttribute('href'),
  lines: (a.innerText || '').split('\\n').map(s => s.trim()).filter(Boolean)
}))"""


# {url: "ok" | reason} for every page asked for on the last fetch. Whether a page LOADED is
# the only honest feed-health signal: a page that loads and carries no usable tip is a
# quiet day, and must not be reported the same way as a page that never arrived.
STATUS = {}


def available():
    """Is a headless browser usable in this process?"""
    try:
        import playwright.sync_api  # noqa: F401
        return True
    except ImportError:
        return False


# Oddspedia's community tips. Unlike Scores24 these class names are BEM, not hashed by a
# CSS-in-JS build, so selecting on them is stable across deploys.
# Accumulator bets carry no .tip-match and are skipped: they are one stake across several
# matches and cannot be booked against a single contest.
TIPS_JS = r"""() => [...document.querySelectorAll('.tip')]
  .filter(t => t.querySelector('.tip-match'))
  .map(t => ({
    name: (t.querySelector('.tip-match__name')?.innerText || '').trim(),
    market: (t.querySelector('.tip-match__market')?.innerText || '').trim(),
    tipster: ((t.querySelector('.tip-head')?.innerText || '')
                .split(/\r?\n/).map(s => s.trim()).filter(Boolean)
                .filter(s => s.length > 1)[0]) || ''
  }))"""


def fetch_rows(jobs, js=None, settle_ms=2000, challenge_ms=10000, timeout_ms=45000,
               pace_ms=1500, scrolls=4, warmup=None, log=print):
    """Load each URL in one browser session and return {url: [{href, lines}]}.

    One session for every page, not one per page: the Cloudflare clearance is a cookie,
    so re-launching per URL pays the challenge again each time and is what turns a
    tolerable scrape into a rate-limited one.

    Never raises. A browser that will not start, a page that times out, and a challenge
    that will not clear all resolve to "no rows for that URL", because the caller's
    contract is that a dead source shows up as an empty column rather than a failed run.
    """
    # jobs is either a list of URLs (all sharing `js`) or (url, js) pairs, so one
    # browser session can serve sites that need different extractors. Launching a
    # browser per site doubled the wall clock for no benefit.
    jobs = [(j, js) if isinstance(j, str) else j for j in jobs]
    out = {u: [] for u, _ in jobs}
    for u, _ in jobs:
        STATUS[u] = "not fetched"
    if not available():
        log("  ! browser: playwright not installed — skipping the browser step")
        return out

    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(headless=True, args=LAUNCH_ARGS)
            except Exception as e:
                log(f"  ! browser: chromium would not launch ({type(e).__name__}: "
                    f"{str(e)[:90]}) — run `playwright install chromium`")
                return out

            ctx = browser.new_context(user_agent=UA, locale="en-US",
                                      timezone_id="America/Chicago",
                                      viewport={"width": 1440, "height": 900})
            ctx.add_init_script(STEALTH_JS)
            page = ctx.new_page()

            # Take the clearance cookie on a cheap page first. Landing straight on a
            # deep league URL is what gets challenged hardest.
            if warmup:
                try:
                    page.goto(warmup, wait_until="domcontentloaded", timeout=timeout_ms)
                    page.wait_for_timeout(settle_ms)
                except Exception:
                    pass

            for n, (u, page_js) in enumerate(jobs):
                # Pace the navigations. Loading a batch back-to-back is itself a bot
                # tell: the FIRST page clears instantly and the second gets the
                # interstitial. A short gap between pages is worth far more here than a
                # longer wait once the challenge has already been served.
                if n:
                    page.wait_for_timeout(pace_ms)
                try:
                    page.goto(u, wait_until="domcontentloaded", timeout=timeout_ms)
                    page.wait_for_timeout(settle_ms)
                    # Poll rather than sleeping a fixed amount: the interstitial usually
                    # clears in a second or two, and occasionally takes fifteen.
                    waited = 0
                    while (waited < challenge_ms
                           and any(c in (page.title() or "").lower() for c in CHALLENGE)):
                        page.wait_for_timeout(2000)
                        waited += 2000
                    if any(c in (page.title() or "").lower() for c in CHALLENGE):
                        # One retry after a longer pause. A challenge that is a reaction
                        # to pacing clears on a second, unhurried attempt; one that is a
                        # hard block on this path never does, and that distinction is
                        # what the log line has to make visible.
                        page.wait_for_timeout(pace_ms * 2)
                        page.goto(u, wait_until="domcontentloaded", timeout=timeout_ms)
                        page.wait_for_timeout(settle_ms)
                        waited = 0
                        while (waited < challenge_ms
                               and any(c in (page.title() or "").lower() for c in CHALLENGE)):
                            page.wait_for_timeout(2000)
                            waited += 2000
                    if any(c in (page.title() or "").lower() for c in CHALLENGE):
                        STATUS[u] = "challenge not cleared"
                        log(f"  ! browser: challenge did not clear for {u}")
                        continue
                    # These listings lazy-load. Without scrolling, Scores24's soccer
                    # page yields a handful of "editor's choice" rows out of the ~190
                    # tips it actually has, and the sport with the most tipster activity
                    # ends up the thinnest column on the board.
                    for _ in range(scrolls):
                        page.mouse.wheel(0, 6000)
                        page.wait_for_timeout(900)
                    out[u] = page.evaluate(page_js or js or ROW_JS) or []
                    STATUS[u] = "ok"
                except Exception as e:
                    STATUS[u] = f"error: {type(e).__name__}"
                    log(f"  ! browser: {u} failed ({type(e).__name__}: {str(e)[:70]})")
            browser.close()
    except Exception as e:
        log(f"  ! browser: browser session failed ({type(e).__name__}: {str(e)[:90]})")
    return out


# ---------------------------------------------------------------------------
# Row parsing (pure — no browser needed, so it is unit-testable)
# ---------------------------------------------------------------------------

# Everything in a row that is not a name or the tip.
NOISE = re.compile(
    r"^(?:\d{1,2}:\d{2}|\d{1,2}\s+\w{3},?|[+-]?\d+|\d+%|-|–|Today|Tomorrow|Yesterday"
    r"|Ended|Live|Prediction|Postponed|Cancelled)$", re.I)

SLUG_DATE = re.compile(r"m-(\d{2})-(\d{2})-(\d{4})-")


def parse_row(row, sport_slug):
    """One listing row -> {a, b, pick, date, detail}, or None.

    Only MATCH-WINNER tips survive. Scores24 publishes plenty of totals and handicaps
    ("Total Over (36,5)", "Karen Khachanov Total Over (15,5)"), and those settle on a
    different question than the head-to-head market they would be booked against —
    scoring one as if it were a moneyline pick would be recording a bet nobody made.
    """
    href = row.get("href") or ""
    # Listing pages carry a cross-sport "other predictions" rail. On the cricket, boxing
    # and table-tennis pages that rail is the ONLY thing present, so without this the
    # scraper would happily return ice-hockey tips as cricket ones.
    if not href.startswith(f"/en/{sport_slug}/"):
        return None

    lines = [l for l in (row.get("lines") or []) if not NOISE.match(l)]
    tips = [l for l in lines if l.endswith(" Win")]
    if len(tips) != 1:
        return None
    tip = tips[0]
    names = [l for l in lines if l != tip]
    # Exactly two names, or the layout is not what this parser was written against and
    # guessing which line is a competitor would silently mis-assign the pick.
    if len(names) != 2:
        return None

    team = tip[: -len(" Win")].strip()
    a, b = names[0], names[1]
    if team == a:
        pick = "a"
    elif team == b:
        pick = "b"
    else:
        # Fall back to loose matching (trailing spaces, accents, "(W)" suffixes), but
        # only when one side is clearly closer than the other.
        from sandbox_sources import sim
        sa, sb = sim(team, a), sim(team, b)
        if max(sa, sb) < 0.5 or abs(sa - sb) < 0.2:
            return None
        pick = "a" if sa > sb else "b"

    date = None
    m = SLUG_DATE.search(href)
    if m:
        dd, mm, yyyy = m.groups()
        date = f"{yyyy}-{mm}-{dd}"

    return dict(a=a, b=b, pick=pick, date=date, detail=tip)


# ---------------------------------------------------------------------------
# Oddspedia community tips
# ---------------------------------------------------------------------------

# "FT inc. OT Result: Bathinda Royals" / "Result: Bangladesh Women". Anything else the
# community tips — totals, handicaps, method-of-victory — settles a different question
# than the head-to-head market it would be booked against.
RESULT_MARKET = re.compile(r"^(?:FT\s*INC\.?\s*OT\s*)?RESULT:\s*(.+)$", re.I)


def parse_tip(row):
    """One Oddspedia community tip -> {a, b, pick, tipster}, or None.

    Tips carry no date. That is handled in matching rather than invented here: a tip is
    hours old and the universe only holds the next few days, so it is resolved to the
    SOONEST fixture between those two sides.
    """
    name = (row.get("name") or "").strip()
    market = (row.get("market") or "").strip()
    m = RESULT_MARKET.match(market)
    if not m or " - " not in name:
        return None

    a, b = [x.strip() for x in name.split(" - ", 1)]
    team = m.group(1).strip()
    if not a or not b or not team:
        return None

    from sandbox_sources import sim
    sa, sb = sim(team, a), sim(team, b)
    # The named selection has to be clearly one of the two sides. Ambiguity here would
    # book the bet on the wrong team, which is worse than skipping the tip.
    if max(sa, sb) < 0.5 or abs(sa - sb) < 0.2:
        return None
    return dict(a=a, b=b, pick="a" if sa > sb else "b",
                tipster=(row.get("tipster") or "").strip())
