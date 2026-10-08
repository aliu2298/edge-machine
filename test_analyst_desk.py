#!/usr/bin/env python3
"""Regression checks for the approved Analyst Desk production shell."""
import datetime
import os
import re
import sys

import shell_build
import site_chrome

FAILS = []
NOW = datetime.datetime(2026, 10, 6, 23, 0, tzinfo=datetime.timezone.utc)


def ok(cond, why):
    print(f"  {'ok  ' if cond else 'FAIL'} {why}")
    if not cond:
        FAILS.append(why)


html = shell_build.page(
    NOW,
    d={"quotes": []},
    st={"pairs": {}},
    blob={"leads": {}, "pairs": {}},
)

print("Analyst Desk structure")
ok('data-layout="analyst-desk"' in html, "root declares the Analyst Desk layout")
ok('<body class="analyst-desk">' in html, "the body carries the analyst-desk class")
ok("<title>Edge Machine · Home</title>" in html, "the root is titled Edge Machine · Home")
ok(html.count('<header class="site">') == 1, "one site header, the shared shell")
ok('<aside class="desk-nav"' not in html and "desk-nav-block" not in html,
   "the old desktop quick-access rail is gone")
ok('<div class="desk-center">' in html, "center Running column exists")
ok('<div class="desk-side">' in html, "right Rules/status column exists")
ok('id="running-title">Running markets<' in html, "center column is the Running markets feed")
ok('id="rules-title">Rule cards<' in html, "right column carries Rule cards")
ok('id="status-title">System status<' in html, "right column carries System status")
ok('class="shell-summary"' in html and 'data-board="production"' in html,
   "Production totals remain the system-status source")
ok('class="bet-roll shell-pane"' in html and 'id="bets-roll-title">Bets roll<' in html,
   "Bets roll is in the center workspace")
ok(html.index('class="shell-pane running-pane"') < html.index('class="bet-roll shell-pane"'),
   "Running appears before Bets roll")
ok(html.index('class="shell-pane rules-pane"') < html.index('class="shell-pane desk-status"'),
   "Rule cards appear before System status")
ok('class="production-badge">Production</span>' in html
   and html.index('id="running-title"') < html.index('class="production-badge"')
   < html.index('class="running-filters"'),
   "the Running pane head exposes Production state immediately")
ok("top-production" not in html, "the header no longer carries the Production badge")
ok(re.search(r'>\s*History\s*<', html, re.I) is None,
   "deferred History remains absent")

print("\nAnalyst Desk navigation")
header = re.search(r'<header class="site">.*?</header>', html, re.S)
ok(header is not None, "the shared header is on the page")
header = header.group(0) if header else ""
navs = re.findall(r'<nav class="main"[^>]*>(.*?)</nav>', html, re.S)
ok(len(navs) == 1 and '<nav class="main" aria-label="Pages">' in header,
   "the page's only nav.main is the shell's page nav, in the header")
ok(html.index("</header>") < html.index('<main id="content"'),
   "the header comes before the workspace")
if navs:
    labels = re.findall(r'>([^<]+)</a>', navs[0])
    ok(labels == [label for _key, label, _href in site_chrome.PAGES],
       f"the page nav carries every destination ({labels})")
    ok('aria-current="page"' not in navs[0], "no page pill is current on the root")
ok('<a class="brand" href="./index.html" aria-current="page">Edge Machine</a>' in header,
   "the brand is the current page on the root")
sports = re.search(r'<nav class="sports sport-filter" aria-label="Sport filter">(.*?)</nav>', html, re.S)
ok(sports is not None, "sport filter rail exists")
if sports:
    labels = re.findall(r'>([^<]+)</button>', sports.group(1))
    ok(labels == ["All"], f"an empty list keeps only the All pill ({labels})")
    ok('data-sport="all" aria-pressed="true"' in sports.group(0), "All starts pressed")
    running = html[html.index('class="shell-pane running-pane"'):html.index('class="bet-roll shell-pane"')]
    ok(sports.group(0) in running, "the sport filter lives inside the Running pane")
    ok(running.index('class="running-filters"') < running.index('class="sports sport-filter"')
       < running.index('id="settled-caption"'),
       "the sport filter sits after the Live/Settled/Upcoming filters and before the settled caption")
ok(html.index("</header>") < html.index('<nav class="sports sport-filter"'),
   "page destinations in the header lead into the sport filter in the workspace")
every = re.findall(r'>([^<]+)</button>', shell_build._sport_pills(None))
ok(every == ["All", "NBA", "Soccer", "Tennis", "Cricket", "Crypto", "Commodities"],
   f"_sport_pills(None) keeps every filter ({every})")
some = re.findall(r'>([^<]+)</button>', shell_build._sport_pills({"Cricket", "Soccer"}))
ok(some == ["All", "Soccer", "Cricket"],
   f"_sport_pills only offers sports with a lane on the list ({some})")
ok('<details class="page-menu"' not in html and "Pages ⌄" not in html,
   "no Pages ⌄ menu")

print("\nResponsive CSS")
root = os.path.dirname(os.path.abspath(__file__))
css = open(os.path.join(root, "public_site", "site.css"), encoding="utf-8").read()
ok("body.analyst-desk .shell-columns" in css
   and "grid-template-columns: minmax(0, 1fr) minmax(286px, 340px)" in css,
   "desktop is the Running feed beside a persistent right analysis rail")
ok("desk-nav" not in css, "no left rail rule is left in the stylesheet")
filter_css = css.split("nav.sport-filter {", 1)[-1].split("}", 1)[0] if "nav.sport-filter {" in css else ""
ok("flex-wrap: wrap" in filter_css, "the sport filter wraps inside the Running pane")
ok("@media (max-width: 800px)" in css,
   "single-column mobile breakpoint is present")
phone = css.split("@media (max-width: 800px)", 1)[-1]
ok("body.analyst-desk .shell-columns" in phone and "grid-template-columns: minmax(0, 1fr)" in phone,
   "mobile stacks the workspace in one column")
ok("body.analyst-desk .running-filters" in phone and "overflow-x: auto" in phone,
   "mobile running filters stay horizontally reachable")
ok("position: fixed" not in css.split("body.analyst-desk", 1)[-1],
   "no fixed bottom bar: the shell header is the only navigation")

print()
if FAILS:
    print(f"{len(FAILS)} FAILED")
    sys.exit(1)
print("all passed")
