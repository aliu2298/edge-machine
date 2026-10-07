#!/usr/bin/env python3
"""Regression checks for the approved Analyst Desk production shell."""
import datetime
import os
import re
import sys

import shell_build

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
ok('<aside class="desk-nav"' in html, "desktop quick-access rail exists")
ok('<div class="desk-center">' in html, "center Running column exists")
ok('<div class="desk-side">' in html, "right Rules/status column exists")
ok('id="running-title">Running markets<' in html, "center column is the Running markets feed")
ok('id="rules-title">Rule cards<' in html, "right column carries Rule cards")
ok('id="status-title">System status<' in html, "right column carries System status")
ok('class="shell-summary"' in html and 'data-board="production"' in html,
   "Production totals remain the system-status source")
ok('class="bet-roll shell-pane"' in html and 'id="bets-roll-title">Bets roll<' in html,
   "Bets roll is in the center workspace")
ok(html.index('class="running-pane"') < html.index('class="bet-roll shell-pane"'),
   "Running appears before Bets roll")
ok(html.index('class="rules-pane"') < html.index('class="desk-status"'),
   "Rule cards appear before System status")
ok('class="top-production">Production</span>' in html,
   "header exposes Production state immediately")
ok(re.search(r'>\s*History\s*<', html, re.I) is None,
   "deferred History remains absent")

print("\nAnalyst Desk navigation")
nav = re.search(r'<nav class="main"[^>]*>(.*?)</nav>', html, re.S)
sports = re.search(r'<nav class="sports"[^>]*>(.*?)</nav>', html, re.S)
ok(nav is not None, "workspace nav exists")
ok(sports is not None, "sport filter rail exists")
if nav:
    labels = re.findall(r'>([^<]+)</a>', nav.group(1))
    ok(labels == ["Sandbox", "Production", "Trading", "Method"],
       "workspace nav keeps the existing destinations")
if sports:
    labels = re.findall(r'>([^<]+)</button>', sports.group(1))
    ok(labels == ["All", "NBA", "Soccer", "Tennis", "Cricket", "Crypto"],
       "sport rail keeps every filter")
ok(html.index('<nav class="main"') < html.index('<nav class="sports"'),
   "workspace shortcuts lead into sport shortcuts")

print("\nResponsive CSS")
root = os.path.dirname(os.path.abspath(__file__))
css = open(os.path.join(root, "public_site", "site.css"), encoding="utf-8").read()
ok(".desk-layout" in css and "grid-template-columns: 184px minmax(0, 1fr)" in css,
   "desktop uses a dedicated left rail")
ok("minmax(286px, 340px)" in css,
   "desktop keeps a persistent right analysis rail")
ok("body.analyst-desk .desk-nav nav.main" in css and "position: fixed" in css,
   "mobile workspace navigation becomes a bottom bar")
ok("bottom: max(8px, env(safe-area-inset-bottom))" in css,
   "mobile bottom bar respects the safe area")
ok("body.analyst-desk .desk-nav nav.sports" in css and "overflow-x: auto" in css,
   "mobile sport filters stay horizontally reachable")
ok("@media (max-width: 800px)" in css,
   "single-column mobile breakpoint is present")

print()
if FAILS:
    print(f"{len(FAILS)} FAILED")
    sys.exit(1)
print("all passed")
