#!/usr/bin/env python3
"""Sticky table headers sit flush under the site header, and dates stay one line.

The browser check opens the published pages at 1280x800, scrolls each long table,
and compares thead top to the site header's bottom. It needs Playwright and Chrome.
Without them, the static checks still run (and fail on the old hard-coded offset).
"""
import os
import subprocess
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

FAILS = []
ROOT = os.path.dirname(os.path.abspath(__file__))


def _head_sha():
    """HEAD when this tree is a git checkout, otherwise a stable label."""
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return out or "unknown"


SHA = _head_sha()

# The four long tables from the report: two on Sandbox, Pairs, Stock rules.
TABLES = (
    ("sandbox.html", "#running table", "sandbox Running", "Date"),
    ("sandbox.html", "#recently-settled table", "sandbox Recently settled", "Settled"),
    ("production.html", "#pairs table", "production Pairs", None),
    ("trading.html", "#rules table", "trading Stock rules", None),
)


def ok(cond, msg):
    print(f"  {'ok  ' if cond else 'FAIL'} {msg}")
    if not cond:
        FAILS.append(msg)


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


print(f"SHA {SHA}")
print("\nstatic")

css = _read("public_site/site.css")
js = _read("public_site/tables.js")
chrome = _read("site_chrome.py")
ok("--hdr-h:" in css and "top: var(--hdr-h)" in css,
   "thead sticks at top: var(--hdr-h), with a CSS fallback")
ok("ResizeObserver" in js and 'setProperty("--hdr-h"' in js
   and 'querySelector("header.site")' in js,
   "tables.js sets --hdr-h from the measured header.site height")
ok('td[data-l="Date"]' in css and 'td[data-l="Settled"]' in css
   and "nowrap" in css.split('td[data-l="Date"]', 1)[-1][:180],
   "date and settled cells stay on one line")
ok('src="./tables.js"' in _read("public_site/production.html"),
   "production.html loads tables.js")
ok('src="./tables.js"' in _read("public_site/trading.html"),
   "trading.html loads tables.js")
ok('"./tables.js" not in srcs' in chrome,
   "the page template adds tables.js when a page does not already")
ok("thead { position: static; top: auto;" in css and "--sticky-top: 0px" in css,
   "under 640px the header row is not restuck")


def _serve():
    site = os.path.join(ROOT, "public_site")

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=site, **kwargs)

        def log_message(self, fmt, *args):
            return

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd


MEASURE = r"""
(spec) => {
  const header = document.querySelector("header.site");
  const table = document.querySelector(spec.sel);
  const thead = table.tHead;
  const rows = [...table.tBodies[0].rows].filter((row) => row.querySelector("td") && !row.hidden);
  rows[Math.floor(rows.length / 2)].scrollIntoView({block: "center"});
  const hb = header.getBoundingClientRect().bottom;
  let top = thead.getBoundingClientRect().top;
  if (top > hb + 0.5) {
    const room = table.getBoundingClientRect().bottom - (hb + thead.getBoundingClientRect().height);
    window.scrollBy(0, (top - hb) + Math.min(48, Math.max(8, room * 0.12)));
  }
  const headerBottom = header.getBoundingClientRect().bottom;
  const theadTop = thead.getBoundingClientRect().top;
  let date = null;
  if (spec.dateLabel) {
    const cell = table.querySelector('td[data-l="' + spec.dateLabel + '"]');
    const range = document.createRange();
    range.selectNodeContents(cell);
    const rects = [...range.getClientRects()].filter((r) => r.width > 0.5 && r.height > 0.5);
    const textTop = Math.min(...rects.map((r) => r.top));
    const textBottom = Math.max(...rects.map((r) => r.bottom));
    const lines = new Set(rects.map((r) => Math.round(r.top))).size;
    date = {
      text: cell.textContent.trim(),
      lines: lines,
      textHeight: textBottom - textTop,
      lineHeight: parseFloat(getComputedStyle(cell).lineHeight),
    };
  }
  return {
    headerBottom: headerBottom,
    theadTop: theadTop,
    gap: theadTop - headerBottom,
    date: date,
  };
}
"""

PHONE = r"""
() => {
  const table = document.querySelector("#running table");
  const th = table.querySelector("th");
  const thead = table.tHead;
  return {
    theadPosition: getComputedStyle(thead).position,
    theadTop: getComputedStyle(thead).top,
    thTop: getComputedStyle(th).top,
    tableDisplay: getComputedStyle(table).display,
    theadDisplay: getComputedStyle(thead).display,
    overflowX: getComputedStyle(table.closest(".tbl")).overflowX,
  };
}
"""


def browser_checks():
    print("\nbrowser 1280x800")
    from require_browser import require_browser
    sync_playwright = require_browser("test_sticky_header.py")
    if sync_playwright is None:
        return
    httpd = _serve()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 800}, device_scale_factor=1)
            for filename, sel, label, date_label in TABLES:
                page.goto(f"{base}/{filename}", wait_until="networkidle")
                page.wait_for_timeout(150)
                got = page.evaluate(MEASURE, {"sel": sel, "dateLabel": date_label})
                gap = got["gap"]
                ok(abs(gap) <= 1,
                   f"{label}: thead top equals header bottom "
                   f"(gap {gap:.2f}px, thead {got['theadTop']:.2f}, header {got['headerBottom']:.2f})")
                if date_label:
                    date = got["date"]
                    one_line = (
                        date is not None
                        and date["lines"] == 1
                        and date["textHeight"] <= date["lineHeight"] + 1
                    )
                    ok(one_line,
                       f"{label}: {date_label} cell is one line "
                       f"({date['text'] if date else 'missing'}, "
                       f"text {None if not date else round(date['textHeight'], 1)}px, "
                       f"line-height {None if not date else date['lineHeight']}px, "
                       f"{None if not date else date['lines']} line)")
            page.close()
            phone = browser.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=1)
            phone.goto(f"{base}/sandbox.html", wait_until="networkidle")
            phone.wait_for_timeout(100)
            view = phone.evaluate(PHONE)
            ok(view["theadPosition"] == "static" and view["thTop"] == "0px"
               and view["tableDisplay"] == "table" and view["theadDisplay"] == "table-header-group"
               and view["overflowX"] == "auto",
               f"390px phone table is unchanged ({view})")
            browser.close()
    finally:
        httpd.shutdown()


browser_checks()

print()
if FAILS:
    print(f"SHA {SHA} FAILED {len(FAILS)}")
    sys.exit(1)
print(f"SHA {SHA} PASSED")
