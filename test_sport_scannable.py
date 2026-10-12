#!/usr/bin/env python3
"""The sport pages are scannable: numbers on load, words on request.

- No registration or definition text is visible on load. Every registered note,
  every parameter list, dated change log and recent-picks list sits inside a
  closed <details> (the rule's "Rule details" fold, or the closed Sandbox fold
  around it). Checked on the markup of all five template pages, built from a
  fixture and from the committed ledger.
- Outside a closed fold, nothing in the Rules section is a sentence: no text run
  there is longer than a short line (MAX_WORDS words).
- In Chromium at 1366x768, the Events heading is on the first screen on Soccer and
  Tennis, as published and with every soccer rule promoted at once (the "Show N
  more" fold holds the rest); no definition is visible until a row is opened, and
  opening one shows it.
"""
import datetime
import os
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

import sandbox_build as B
import sandbox_sources as S
import sandbox_track as T
import sport_page as SP
import sport_tab

FAILS = []
ROOT = os.path.dirname(os.path.abspath(__file__))
NOW = datetime.datetime(2026, 10, 12, 16, 0, tzinfo=datetime.timezone.utc)
# A visible line in the Rules section may be at most this many words.
MAX_WORDS = 12
# What only a rule's words are drawn with.
WORD_CLASSES = {"sp-def", "sp-params", "sp-changes", "sp-details-body", "rule-picks", "sp-before-reset"}
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


def ok(cond, msg):
    print(f"  {'ok  ' if cond else 'FAIL'} {msg}")
    if not cond:
        FAILS.append(msg)


class Runs(HTMLParser):
    """Every text run in <main>, with whether it sits inside a closed <details>,
    inside an element drawn only for a rule's words, and inside #rules."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []          # (tag, closed_details, words, rules, summary)
        self.runs = []

    def handle_starttag(self, tag, attrs):
        if tag in VOID:
            return
        a = dict(attrs)
        top = self.stack[-1] if self.stack else ("", False, False, False, False)
        classes = set((a.get("class") or "").split())
        closed = top[1] or (tag == "details" and "open" not in a)
        words = top[2] or bool(classes & WORD_CLASSES)
        rules = top[3] or a.get("id") == "rules"
        summary = top[4] or tag == "summary"
        # A <summary> is drawn even when its <details> is closed.
        if tag == "summary" and top[1] is False and self.stack and self.stack[-1][0] == "details":
            closed = False
        self.stack.append((tag, closed, words, rules, summary))

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        text = " ".join(data.split())
        if not text or not self.stack:
            return
        tag, closed, words, rules, _summary = self.stack[-1]
        if tag in ("script", "style"):
            return
        self.runs.append(dict(text=text, closed=closed, words=words, rules=rules))


def runs_of(html):
    main = html.split("<main", 1)[-1].split("</main>", 1)[0]
    parser = Runs()
    parser.feed("<main" + main)
    return parser.runs


def check(html, label, notes):
    """No rule's words on load; no sentence in the Rules section outside a closed fold."""
    runs = runs_of(html)
    shown_words = [r["text"][:70] for r in runs if r["words"] and not r["closed"]]
    ok(not shown_words, f"{label}: every definition, parameter list, change log and pick list is inside a closed fold"
       + (f" (shown: {shown_words[:2]})" if shown_words else ""))
    shown_notes = []
    for note in notes:
        probe = " ".join(note.split())[:60]
        if len(probe) < 30:
            continue
        for r in runs:
            if probe[:40] in r["text"] and not r["closed"]:
                shown_notes.append(probe[:40])
                break
    ok(not shown_notes, f"{label}: no registered note is visible on load"
       + (f" ({shown_notes[:2]})" if shown_notes else ""))
    ok(not any("REGISTERED" in r["text"] and not r["closed"] for r in runs),
       f"{label}: no 'PRE-REGISTERED' paragraph is visible on load")
    long_runs = [r["text"] for r in runs if r["rules"] and not r["closed"] and len(r["text"].split()) > MAX_WORDS]
    ok(not long_runs, f"{label}: nothing in the Rules section is longer than {MAX_WORDS} words outside a closed fold"
       + (f" ({long_runs[:1]})" if long_runs else ""))
    folds = re.findall(r'<details class="sp-rule[^"]*"[^>]*>', html)
    ok(folds and not any(" open" in f for f in folds), f"{label}: every rule's Rule details fold starts closed ({len(folds)})")
    ok("<details open" not in html.split('id="rules"', 1)[-1].split('id="events"', 1)[0],
       f"{label}: no fold in the Rules section starts open")


def notes_for(rows):
    return [str(r["meta"].get("note") or "") for r in rows] + [str(c) for r in rows for c in (r["meta"].get("changes") or [])]


print("the markup, from the committed ledger")
import soccer_build
import tennis_build
import cricket_build
import crypto_build
import commodities_build
from unittest.mock import patch
_fresh = patch("sport_tab.preflight_report",
               return_value=({}, '<div class="note sm">Kalshi checked 1.0h ago.</div>'))
_fresh.start()
d, st = T.load(), T.load_stages()
pages = {
    "soccer": (soccer_build.build(d, st, NOW), sport_tab.family_rows(d, st, "Soccer")),
    "tennis": (tennis_build.build(d, st, NOW), sport_tab.family_rows(d, st, "Tennis")),
    "cricket": (cricket_build.build(d, st, NOW), sport_tab.family_rows(d, st, "Cricket")),
    "crypto": (crypto_build.build(d, st, NOW), crypto_build.page_rows(d, st)),
    "commodities": (commodities_build.build(d, st, NOW), commodities_build.page_rows(d, st)),
}
for key, (html, rows) in pages.items():
    check(html, key, notes_for(rows))

print("\nevery soccer rule promoted at once")
promoted = {"pairs": dict((st.get("pairs") or {}),
                          **{f'{r["name"]}|{r["sport"]}': {"stage": "production", "by_hand": "2026-10-08",
                                                          "promoted_at": "2026-10-08T00:00:00+00:00"}
                             for r in pages["soccer"][1]})}
crowded = soccer_build.build(d, promoted, NOW)
crowded_rows = sport_tab.family_rows(d, promoted, "Soccer")
check(crowded, "soccer, all promoted", notes_for(crowded_rows))
prod = [r for r in crowded_rows if r.get("prod")]
shown = crowded.split('class="sp-rules-list sp-prod"', 1)[1].split('<details class="fold sp-more-rules">', 1)[0]
ok(shown.count('<details class="sp-rule') == SP.PROD_VISIBLE,
   f"the Production list shows {SP.PROD_VISIBLE} rows before the fold")
ok(f"Show {len(prod) - SP.PROD_VISIBLE} more Production rules" in crowded, "and folds the rest behind Show N more")

print("\nthe words are still on the page, in their folds")
html, rows = pages["tennis"]
for r in rows:
    note = " ".join(str(r["meta"].get("note") or "").split())
    if note:
        ok(B.esc(note) in html, f"tennis {r['name']}|{r['sport']}: the full registration is in its fold, verbatim")
    if r["meta"].get("frozen"):
        ok(f'<span class="badge stage" title="Frozen {r["meta"]["frozen"]}">Frozen</span>' in html,
           f"tennis {r['name']}|{r['sport']}: Frozen is a small badge, the date in its tooltip")

print("\nin the browser at 1366x768")
from require_browser import require_browser
playwright = require_browser("test_sport_scannable.py")
if playwright is not None:
    with playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)

        def serve(markup):
            def route_it(route):
                name = Path(urlparse(route.request.url).path).name
                if name.endswith(".html"):
                    route.fulfill(body=markup, content_type="text/html")
                else:
                    route.fulfill(path=str(Path(ROOT) / "public_site" / name))
            return route_it

        cases = [("soccer", pages["soccer"][0]), ("tennis", pages["tennis"][0]),
                 ("soccer, all promoted", crowded)]
        for path in ("soccer.html", "tennis.html"):
            published = Path(ROOT) / "public_site" / path
            if published.exists():
                cases.append((f"published {path}", published.read_text(encoding="utf-8")))
        for label, markup in cases:
            for scheme in ("light", "dark"):
                page = browser.new_page(viewport={"width": 1366, "height": 768}, color_scheme=scheme)
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.route("http://fixture.local/**", serve(markup))
                page.goto("http://fixture.local/sport.html", wait_until="load")
                got = page.evaluate("""() => {
                    const h = document.querySelector('#events h2').getBoundingClientRect();
                    const words = [...document.querySelectorAll('.sp-def, .sp-params, .sp-changes, .sp-details-body, .rule-picks')]
                        .filter(e => e.checkVisibility()).length;
                    return { top: Math.round(h.top), bottom: Math.round(h.bottom), inner: innerHeight, words,
                             overflow: document.documentElement.scrollWidth > innerWidth };
                }""")
                ok(not errors, f"{label} ({scheme}): no page error")
                ok(got["bottom"] <= got["inner"],
                   f"{label} ({scheme}): the Events heading is on the first screen (bottom {got['bottom']}px of {got['inner']})")
                ok(got["words"] == 0, f"{label} ({scheme}): no definition is visible on load ({got['words']})")
                ok(not got["overflow"], f"{label} ({scheme}): nothing scrolls sideways")
                if scheme == "light" and not label.startswith("published"):
                    page.locator("details.sp-rule > summary").first.click()
                    shown = page.evaluate("""() => [...document.querySelectorAll('details.sp-rule[open] .sp-def')]
                        .filter(e => e.checkVisibility()).length""")
                    ok(shown >= 1, f"{label}: opening a row's Rule details shows its definition")
                    ok(page.evaluate("document.documentElement.scrollWidth <= innerWidth"),
                       f"{label}: and still nothing scrolls sideways")
                page.close()
        browser.close()
_fresh.stop()

if FAILS:
    print(f"\nFAILED {len(FAILS)}")
    sys.exit(1)
print("\nPASSED")
