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

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

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


def available():
    """Is a headless browser usable in this process?"""
    try:
        import playwright.sync_api  # noqa: F401
        return True
    except ImportError:
        return False


def fetch_rows(urls, settle_ms=2500, challenge_ms=7000, timeout_ms=45000, log=print):
    """Load each URL in one browser session and return {url: [{href, lines}]}.

    One session for every page, not one per page: the Cloudflare clearance is a cookie,
    so re-launching per URL pays the challenge again each time and is what turns a
    tolerable scrape into a rate-limited one.

    Never raises. A browser that will not start, a page that times out, and a challenge
    that will not clear all resolve to "no rows for that URL", because the caller's
    contract is that a dead source shows up as an empty column rather than a failed run.
    """
    out = {u: [] for u in urls}
    if not available():
        log("  ! scores24: playwright not installed — skipping the browser step")
        return out

    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(headless=True,
                                            args=["--no-sandbox", "--disable-dev-shm-usage"])
            except Exception as e:
                log(f"  ! scores24: chromium would not launch ({type(e).__name__}: "
                    f"{str(e)[:90]}) — run `playwright install chromium`")
                return out

            ctx = browser.new_context(user_agent=UA, locale="en-US",
                                      viewport={"width": 1280, "height": 900})
            page = ctx.new_page()
            for u in urls:
                try:
                    page.goto(u, wait_until="domcontentloaded", timeout=timeout_ms)
                    page.wait_for_timeout(settle_ms)
                    # Give the interstitial one chance to clear before giving up on it.
                    if any(c in (page.title() or "").lower() for c in CHALLENGE):
                        page.wait_for_timeout(challenge_ms)
                    if any(c in (page.title() or "").lower() for c in CHALLENGE):
                        log(f"  ! scores24: challenge did not clear for {u}")
                        continue
                    out[u] = page.evaluate(ROW_JS) or []
                except Exception as e:
                    log(f"  ! scores24: {u} failed ({type(e).__name__}: {str(e)[:70]})")
            browser.close()
    except Exception as e:
        log(f"  ! scores24: browser session failed ({type(e).__name__}: {str(e)[:90]})")
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
