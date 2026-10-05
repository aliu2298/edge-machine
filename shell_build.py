"""The SofaScore-style shell. Slice 1 is chrome and empty panes.

The site root lands here with Production selected. Page pills go to the
existing Sandbox, Production, Trading, and Method pages. Sport pills and the
Live / Settled / Upcoming controls only record which one is pressed; they do
not filter a list. The summary strip is the Production page's own headline
tiles — the same counts that page already prints, not a new P&L.
"""
import datetime

import production
import site_chrome

SPORTS = (
    ("all", "All"),
    ("nba", "NBA"),
    ("soccer", "Soccer"),
    ("tennis", "Tennis"),
    ("cricket", "Cricket"),
    ("crypto", "Crypto"),
)
PAGES = (
    ("Sandbox", "./sandbox.html", False),
    ("Production", "./production.html", True),
    ("Trading", "./trading.html", False),
    ("Method", "./sandbox.html#method", False),
)
RUNNING = (("live", "Live", True), ("settled", "Settled", False), ("upcoming", "Upcoming", False))


def _tiles(html):
    """Copy the Production headline strip out of a page that already built it."""
    start = html.find('<div class="tiles">')
    if start < 0:
        raise RuntimeError("Production board has no headline tiles")
    depth = 0
    i = start
    while i < len(html):
        if html.startswith("<div", i):
            depth += 1
            i = html.find(">", i) + 1
            continue
        if html.startswith("</div>", i):
            depth -= 1
            i += len("</div>")
            if depth == 0:
                return html[start:i]
            continue
        i += 1
    raise RuntimeError("Production headline tiles are not closed")


def production_summary(d, st, blob, now):
    """The four Production tiles. page() does the counting; this only displays it."""
    return _tiles(production.page(d, st, blob, "", now=now))


def _load(d, st, blob):
    if d is None or st is None or blob is None:
        import sandbox_track as T
        if d is None:
            d = T.load()
        if st is None:
            st = T.load_stages()
        if blob is None:
            blob = production.load_feed()
    return d, st, blob


def _now(now):
    if isinstance(now, datetime.datetime):
        if now.tzinfo is None:
            return now.replace(tzinfo=datetime.timezone.utc)
        return now.astimezone(datetime.timezone.utc)
    return datetime.datetime.now(datetime.timezone.utc)


def _stamp(now):
    if isinstance(now, datetime.datetime):
        return site_chrome.stamp(_now(now), machine=False)
    return site_chrome.esc(str(now))


def _page_pills():
    parts = []
    for label, href, current in PAGES:
        attr = ' aria-current="page"' if current else ""
        parts.append(f'<a href="{site_chrome.esc(href)}"{attr}>{site_chrome.esc(label)}</a>')
    return "".join(parts)


def _sport_pills():
    parts = []
    for key, label in SPORTS:
        pressed = "true" if key == "all" else "false"
        parts.append(
            f'<button type="button" data-sport="{site_chrome.esc(key)}" '
            f'aria-pressed="{pressed}">{site_chrome.esc(label)}</button>')
    return "".join(parts)


def _running_filters():
    parts = []
    for key, label, pressed in RUNNING:
        parts.append(
            f'<button type="button" data-filter="{site_chrome.esc(key)}" '
            f'aria-pressed="{"true" if pressed else "false"}">{site_chrome.esc(label)}</button>')
    return "".join(parts)


def page(now, d=None, st=None, blob=None):
    """The shell document. `d`, `st`, and `blob` default to the live board."""
    d, st, blob = _load(d, st, blob)
    now_dt = _now(now)
    summary = production_summary(d, st, blob, now_dt)
    body = f"""<h1 class="sr-only">Edge Machine · Production</h1>
<section class="shell-summary" aria-label="Production totals" data-board="production">
{summary}
</section>
<div class="shell-columns">
<section class="shell-pane" aria-labelledby="running-title">
<h2 id="running-title">Running</h2>
<p class="shell-kicker">Open paper bets</p>
<div class="running-filters" role="group" aria-label="Running filters">
{_running_filters()}
</div>
<p class="shell-note">These filters do not change the list yet.</p>
<p class="shell-empty">No live, settled, or upcoming paper bets.</p>
</section>
<section class="shell-pane" aria-labelledby="rules-title">
<div class="pane-head">
<h2 id="rules-title">Rules applied</h2>
<a class="full-page" href="./production.html">Full page →</a>
</div>
<p class="shell-empty">Select a contest in Running.</p>
</section>
</div>
<footer>Read-only static export · rebuilt by GitHub Actions · research, not betting advice.</footer>
"""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Edge Machine</title>
<meta name="description" content="Production headlines, and the paper bets still to be listed.">
<link rel="stylesheet" href="./site.css">
{site_chrome.CSP}
{site_chrome.REFERRER}
</head>
<body>
<a class="skip" href="#content">Skip to content</a>
<header class="site">
<div class="bet-roll">
<p class="bet-roll-label">Open &amp; recent</p>
<div class="bet-roll-track">
<p class="bet-roll-empty">No open or recent paper bets yet.</p>
</div>
</div>
<div class="topbar">
<a class="brand" href="./index.html">Edge Machine</a>
<nav class="main" aria-label="Pages">{_page_pills()}</nav>
<p class="stamp">{_stamp(now)}</p>
</div>
<nav class="sports" aria-label="Sports">{_sport_pills()}</nav>
</header>
<main id="content" class="wrap">
{body}
</main>
<script src="./tables.js"></script>
<script src="./shell.js"></script>
</body>
</html>
"""
