#!/usr/bin/env python3
"""Page overflow, phone-card filters, nav wrap, date lines, market subtitles.

Presentation only. The browser half needs Playwright and Chrome. Without them
the static checks still run, and those fail on the pages this branch started from.
"""
import os
import re
import subprocess
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

FAILS = []
ROOT = os.path.dirname(os.path.abspath(__file__))
SHA = subprocess.check_output(
    ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()

PAGES = (
    "sandbox.html",
    "production.html",
    "trading.html",
    "archive/index.html",
    "archive/2026-W37.html",
    "archive/2026-W38.html",
    "archive/2026-W39.html",
)


def ok(cond, msg):
    print(f"  {'ok  ' if cond else 'FAIL'} {msg}")
    if not cond:
        FAILS.append(msg)


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


print(f"SHA {SHA}")

print("\n1. wide tables scroll inside the card")
css = _read("public_site/site.css")
js = _read("public_site/tables.js")
ok("function containWideTables" in js and 'classList.add("scroll-x")' in js,
   "tables.js marks a table .scroll-x only when it is wider than the card")
scroll_css = css.split(".tbl.scroll-x {", 1)[-1].split("}", 1)[0] if ".tbl.scroll-x {" in css else ""
ok("overflow-x: auto" in scroll_css and "minmax(0, 1fr)" in scroll_css,
   "a wide card scrolls sideways and cannot stretch the page")

print("\n2. phone cards use the same filter as the rows")
ok("function passesFilters" in js and "function paintRow" in js
   and 'setProperty("display", "none", "important")' in js,
   "tables.js hides a card with the same predicate as its row")
ok("tr[hidden]" in css and "display: none !important" in css,
   "a hidden row stays hidden when the card layout sets display:block")

print("\n3. nav wraps instead of clipping")
nav_css = css.split("nav.main, nav.toc {", 1)[-1].split("}", 1)[0]
ok("flex-wrap: wrap" in nav_css and "overflow-x: visible" in nav_css,
   "the main nav and the sub-nav wrap")

print("\n4. dates stay on one line")
date_css = css.split('td[data-l="Date"]', 1)[-1][:240] if 'td[data-l="Date"]' in css else ""
ok('td[data-l="Settled"]' in date_css and 'td[data-l="Last"]' in date_css
   and "nowrap" in date_css,
   "Date, Settled, and Last cells do not wrap")

print("\n5. Markets subtitles say Rule")
page = _read("public_site/sandbox.html")
markets = page.split("<b>Markets</b>", 1)[-1].split("</details></details>", 1)[0]
for label in ("AAA gasoline no-change rule", "Commodity far-tail rule"):
    bit = markets.split(label, 1)[-1][:180]
    ok(re.search(r'<div class="sm mut">Rule</div>', bit) is not None
       and "Commodities" not in bit.split("</td>", 1)[0],
       f"the {label} subtitle is Rule")
build = _read("sandbox_build.py")
ok('r["sport"] in MARKET_KEYS' in build and "subline" in build,
   "the row template uses the rule kind for a market sport")

import sandbox_build as SB
import sandbox_sources as S


def _pair(name, sport):
    return dict(
        name=name, sport=sport, meta=S.SOURCES[name],
        a=dict(n=2, won=0, expected=0.6, z=-1.0, roi_fee=-1.0),
        open=0, prod=False, moved="", v="early",
    )


def _subtitle(row):
    return re.search(r'class="sm mut">([^<]*)</div>', SB._row(row)).group(1)


gas = _subtitle(_pair("gas_nochange", "commodities"))
tail = _subtitle(_pair("cmd_tail", "commodities"))
mlb = _subtitle(_pair("mlb_fade_streak", "mlb"))
ok(gas == "Rule" and tail == "Rule",
   f"a commodities row prints its kind (gas {gas!r}, far-tail {tail!r})")
ok(mlb == "MLB", f"a sport row still prints the sport ({mlb!r})")


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


OVERFLOW = r"""
() => {
  document.querySelectorAll("details").forEach((d) => { d.open = true; });
  const root = document.documentElement;
  return { scrollWidth: root.scrollWidth, clientWidth: root.clientWidth };
}
"""

CARDS = r"""
({ query, sport }) => {
  document.documentElement.setAttribute("data-view", "cards");
  const table = document.querySelector("#running table");
  const tools = table.closest(".tbl").previousElementSibling;
  const input = tools.querySelector("input.flt");
  const select = [...tools.querySelectorAll("select")].find(
    (s) => (s.getAttribute("aria-label") || "") === "Sport");
  input.value = query;
  input.dispatchEvent(new Event("input", { bubbles: true }));
  if (select) {
    const want = [...select.options].find((o) => o.value === sport);
    select.value = want ? sport : "";
    select.dispatchEvent(new Event("change", { bubbles: true }));
  }
  const rows = [...table.tBodies[0].rows].filter((row) => !row.classList.contains("grp"));
  const rowOn = rows.map((row) => !row.hidden);
  const cardOn = rows.map((row) => getComputedStyle(row).display !== "none");
  const count = tools.querySelector(".count").textContent;
  const visible = rows.filter((row, i) => cardOn[i]);
  return {
    rows: rows.length,
    rowOn: rowOn.filter(Boolean).length,
    cardOn: cardOn.filter(Boolean).length,
    same: rowOn.every((on, i) => on === cardOn[i]),
    count: count,
    first: visible.length ? visible[0].textContent.replace(/\s+/g, " ").trim().slice(0, 90) : "",
    sports: visible.map((row) => {
      const cell = [...row.cells].find((c) => c.getAttribute("data-l") === "Sport");
      return cell ? cell.textContent.replace(/\s+/g, " ").trim() : "";
    }),
    hasSport: !!(select && [...select.options].some((o) => o.value === sport)),
  };
}
"""

NAV = r"""
() => {
  const vw = document.documentElement.clientWidth;
  const links = [...document.querySelectorAll("nav.main a, nav.toc a, #vw")];
  return {
    vw: vw,
    scrollWidth: document.documentElement.scrollWidth,
    links: links.map((a) => {
      const r = a.getBoundingClientRect();
      return {
        text: a.textContent.trim(),
        left: r.left,
        right: r.right,
        top: r.top,
        nav: a.closest("nav") ? a.closest("nav").className : "button",
      };
    }),
  };
}
"""

STICKY_WRAP = r"""
() => {
  const nav = document.querySelector("nav.main");
  nav.style.maxWidth = "220px";
  return new Promise((resolve) => {
    requestAnimationFrame(() => requestAnimationFrame(() => {
      const header = document.querySelector("header.site");
      const table = document.querySelector("#running table");
      const thead = table.tHead;
      const rows = [...table.tBodies[0].rows].filter((row) => row.querySelector("td") && !row.hidden);
      rows[Math.floor(rows.length / 2)].scrollIntoView({ block: "center" });
      const hb = header.getBoundingClientRect().bottom;
      let top = thead.getBoundingClientRect().top;
      if (top > hb + 0.5) {
        window.scrollBy(0, top - hb + 24);
      }
      const tops = [...nav.querySelectorAll("a")].map((a) => Math.round(a.getBoundingClientRect().top));
      const headerBottom = header.getBoundingClientRect().bottom;
      const theadTop = thead.getBoundingClientRect().top;
      const hdr = getComputedStyle(document.documentElement).getPropertyValue("--hdr-h").trim();
      resolve({
        wrapped: new Set(tops).size > 1,
        headerHeight: header.getBoundingClientRect().height,
        hdr: hdr,
        gap: theadTop - headerBottom,
        scrollX: table.closest(".tbl").classList.contains("scroll-x"),
      });
    }));
  });
}
"""

DATES = r"""
(label) => {
  const cells = [...document.querySelectorAll('td[data-l="' + label + '"]')]
    .filter((cell) => /\d{4}-\d{2}-\d{2}/.test(cell.textContent));
  if (!cells.length) return { missing: true, label: label };
  return {
    label: label,
    n: cells.length,
    bad: cells.filter((cell) => {
      const style = getComputedStyle(cell);
      const range = document.createRange();
      range.selectNodeContents(cell);
      const rects = [...range.getClientRects()].filter((r) => r.width > 0.5 && r.height > 0.5);
      const lines = new Set(rects.map((r) => Math.round(r.top))).size;
      const textHeight = Math.max(...rects.map((r) => r.bottom)) - Math.min(...rects.map((r) => r.top));
      const lineHeight = parseFloat(style.lineHeight);
      return style.whiteSpace !== "nowrap" || lines !== 1 || textHeight > lineHeight + 1;
    }).length,
    sample: cells[0].textContent.trim(),
    whiteSpace: getComputedStyle(cells[0]).whiteSpace,
  };
}
"""

LABELS = r"""
() => {
  const market = [...document.querySelectorAll("details.sport")].find((d) => {
    const summary = d.querySelector(":scope > summary");
    return summary && /^Markets\b/.test(summary.textContent.trim());
  });
  if (!market) return [];
  market.open = true;
  const table = market.querySelector(":scope > .tbl table, :scope > div.tbl table");
  return [...table.tBodies[0].rows].map((row) => {
    const name = row.querySelector("b");
    const sub = row.querySelector(".sm");
    return {
      name: name ? name.textContent.trim() : "",
      sub: sub ? sub.textContent.trim() : "",
    };
  });
}
"""


def browser_checks():
    print("\nbrowser")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  skipped: playwright is not installed; browser check not run")
        return
    httpd = _serve()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 800}, device_scale_factor=1)
            for width in (1280, 390):
                page.set_viewport_size({"width": width, "height": 800})
                for path in PAGES:
                    page.goto(f"{base}/{path}", wait_until="load")
                    page.wait_for_timeout(80)
                    got = page.evaluate(OVERFLOW)
                    ok(got["scrollWidth"] <= got["clientWidth"] + 1,
                       f"{path} at {width}px: page scrollWidth {got['scrollWidth']} "
                       f"<= viewport {got['clientWidth']}")

            page.set_viewport_size({"width": 1280, "height": 800})
            page.goto(f"{base}/sandbox.html", wait_until="load")
            page.wait_for_timeout(80)
            combos = (
                ("Boston", "MLB"),
                ("Shapovalov", ""),
                ("Boston", "Tennis · Combos"),
                ("", "MLB"),
                ("", ""),
            )
            for query, sport in combos:
                got = page.evaluate(CARDS, {"query": query, "sport": sport})
                label = f"search {query!r} sport {sport or 'all'}"
                ok(got["same"] and got["cardOn"] == got["rowOn"],
                   f"cards match rows for {label} "
                   f"({got['cardOn']} cards, {got['rowOn']} rows, of {got['rows']})")
                ok(got["count"] == f"{got['cardOn']} of {got['rows']} rows",
                   f"count matches the visible cards for {label} ({got['count']!r})")
                if query == "Boston" and sport == "MLB":
                    ok(got["cardOn"] >= 1 and got["first"].lower().find("boston") >= 0
                       and all(s == "MLB" for s in got["sports"]),
                       f"Boston + MLB shows the Boston card ({got['first']!r}, {got['sports']})")
                if query == "Shapovalov":
                    ok(got["cardOn"] >= 1 and "shapovalov" in got["first"].lower(),
                       f"Shapovalov shows that card ({got['first']!r})")
                if sport and not got["hasSport"] and query != "Boston":
                    ok(False, f"sport option {sport!r} is missing")

            page.set_viewport_size({"width": 400, "height": 800})
            for path in ("sandbox.html", "production.html", "trading.html",
                         "archive/2026-W39.html"):
                page.goto(f"{base}/{path}", wait_until="load")
                page.wait_for_timeout(50)
                got = page.evaluate(NAV)
                clipped = [
                    a for a in got["links"]
                    if a["left"] < -1 or a["right"] > got["vw"] + 1
                ]
                ok(not clipped and got["scrollWidth"] <= got["vw"] + 1,
                   f"{path} at 400px: every nav item is inside the viewport"
                   + ("" if not clipped else
                      " (clipped: " + ", ".join(a["text"] for a in clipped) + ")"))

            page.set_viewport_size({"width": 1280, "height": 800})
            page.goto(f"{base}/sandbox.html", wait_until="load")
            page.wait_for_timeout(80)
            got = page.evaluate(STICKY_WRAP)
            ok(got["wrapped"] and not got["scrollX"] and abs(got["gap"]) <= 1
               and abs(got["headerHeight"] - float(got["hdr"][:-2] or "0")) <= 1,
               f"wrapped nav keeps the running header flush "
               f"(gap {got['gap']:.2f}px, header {got['headerHeight']:.1f}px, "
               f"--hdr-h {got['hdr']}, wrapped {got['wrapped']}, scroll-x {got['scrollX']})")

            for path, label in (
                ("archive/2026-W38.html", "Settled"),
                ("archive/2026-W39.html", "Settled"),
                ("sandbox.html", "Date"),
                ("trading.html", "Last"),
            ):
                page.goto(f"{base}/{path}", wait_until="load")
                page.wait_for_timeout(40)
                got = page.evaluate(DATES, label)
                ok(not got.get("missing") and got["bad"] == 0,
                   f"{path} {label}: {got.get('n', 0)} dates on one line "
                   f"(sample {got.get('sample', '')!r}, {got.get('whiteSpace', '')}, "
                   f"{got.get('bad', 'missing')} wrapped)")

            page.goto(f"{base}/sandbox.html", wait_until="load")
            labels = page.evaluate(LABELS)
            wanted = [row for row in labels if row["name"] in (
                "AAA gasoline no-change rule", "Commodity far-tail rule")]
            ok(len(wanted) == 2 and all(row["sub"] == "Rule" for row in wanted),
               f"rendered Markets subtitles are Rule ({wanted})")
            browser.close()
    finally:
        httpd.shutdown()


browser_checks()

print()
if FAILS:
    print(f"SHA {SHA} FAILED {len(FAILS)}")
    sys.exit(1)
print(f"SHA {SHA} PASSED")
