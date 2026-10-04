#!/usr/bin/env python3
"""Page overflow, phone-card filters, nav wrap, date lines, market subtitles.

Presentation only. The browser half needs Playwright and Chrome. Without them
the static checks still run (and those fail on the pages this branch started from).

Ledger rows are not part of the contract. Card filters, the wide-table
container, date lines, and the Markets subtitle are checked on a fixture this
file writes. Published pages are still checked for page overflow, nav clipping,
and archive date lines, with archive weeks discovered by filename.
"""
import os
import re
import subprocess
import sys
import tempfile
import threading
import urllib.parse
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

# Fixed rows. Boston + MLB is one card; the tennis combo is a different sport.
CARD_ROWS = (
    ("Boston Red Sox vs New York Yankees", "MLB", "Boston Red Sox"),
    ("2-leg tennis combo: Denis Shapovalov + Kimberly Birrell", "Tennis · Combos", "All 2 win"),
    ("Chicago Cubs vs St Louis Cardinals", "MLB", "Chicago Cubs"),
    ("Los Angeles Dodgers vs San Diego Padres", "MLB", "Los Angeles Dodgers"),
    ("Aryna Sabalenka vs Iga Swiatek", "Tennis", "Aryna Sabalenka"),
)


def ok(cond, msg):
    print(f"  {'ok  ' if cond else 'FAIL'} {msg}")
    if not cond:
        FAILS.append(msg)


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


def _published_pages():
    """Sandbox, production, trading, and whatever archive weeks are on disk."""
    pages = ["sandbox.html", "production.html", "trading.html", "soccer.html",
             "tennis.html", "cricket.html", "nba.html", "archive/index.html"]
    archive = os.path.join(ROOT, "public_site", "archive")
    if os.path.isdir(archive):
        weeks = sorted(
            name for name in os.listdir(archive)
            if re.fullmatch(r"20\d\d-W\d\d\.html", name))
        pages.extend(f"archive/{name}" for name in weeks)
    return pages


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


gas = _pair("gas_nochange", "commodities")
tail = _pair("cmd_tail", "commodities")
mlb = _subtitle(_pair("mlb_fade_streak", "mlb"))
ok(_subtitle(gas) == "Rule" and _subtitle(tail) == "Rule",
   f"a commodities row prints its kind (gas {_subtitle(gas)!r}, far-tail {_subtitle(tail)!r})")
ok(mlb == "MLB", f"a sport row still prints the sport ({mlb!r})")


def _fixture_html():
    """A page with known rows. It does not read the published ledger."""
    cards = "".join(
        "<tr>"
        f'<td data-l="Contest">{contest}</td>'
        f'<td data-l="Sport">{sport}</td>'
        f'<td data-l="Backing">{backing}</td>'
        "</tr>"
        for contest, sport, backing in CARD_ROWS)
    sticky = "".join(
        f"<tr><td>Fixture row {i}</td><td>note</td></tr>" for i in range(40))
    heads = "".join(
        f"<th>Wide column {i:02d} stays on one line</th>" for i in range(24))
    cells = "".join(f"<td>cell {i:02d}</td>" for i in range(24))
    markets = SB._row(gas) + SB._row(tail)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Layout fixture</title>
<link rel="stylesheet" href="/site.css">
</head>
<body>
<header class="site">
<div class="topbar">
<a class="brand" href="/sandbox.html">Edge Machine</a>
<nav class="main" aria-label="Pages"><a href="/sandbox.html" aria-current="page">Sandbox</a><a href="/production.html">Production</a><a href="/trading.html">Trading</a><a href="/sandbox.html#method">Method</a></nav>
<button type="button" id="vw" class="vw">Phone view</button>
<p class="stamp">Updated Sep 30, 9:09 PM CT</p>
</div>
<nav class="toc" aria-label="On this page"><a href="#flush">Running</a><a href="#recently-settled">Recently settled</a><a href="#archive">Archive</a><a href="#summary">What it says</a><a href="#by-sport">By sport</a><a href="#reference">Reference</a><a href="#method">Method</a></nav>
</header>
<main id="content" class="wrap">
<section id="flush">
<div class="tbl"><table>
<thead><tr><th>Contest</th><th>Note</th></tr></thead>
<tbody>{sticky}</tbody>
</table></div>
</section>
<section id="dates">
<div class="tbl"><table style="width:64px;table-layout:fixed">
<tbody><tr>
<td data-l="Date">2026-09-23</td>
<td data-l="Settled">2026-09-20</td>
<td data-l="Last">2026-09-30</td>
</tr></tbody>
</table></div>
</section>
<section id="running">
<div class="table-tools"><input class="flt" type="search" aria-label="Search running bets" placeholder="Search contests…"></div>
<div class="tbl"><table class="sortable">
<thead><tr><th>Contest</th><th>Sport</th><th>Backing</th></tr></thead>
<tbody>{cards}</tbody>
</table></div>
</section>
<details class="sport" open><summary><b>Markets</b> <span class="mut">· fixture</span></summary>
<div class="tbl"><table>
<thead><tr><th class="num">#</th><th>Rule or tipster</th></tr></thead>
<tbody>{markets}</tbody>
</table></div>
</details>
<section id="wide">
<div class="tbl"><table>
<thead><tr>{heads}</tr></thead>
<tbody><tr>{cells}</tr></tbody>
</table></div>
</section>
</main>
<script src="/tables.js"></script>
</body>
</html>
"""


def _serve(fx_dir):
    site = os.path.join(ROOT, "public_site")
    root_fx = os.path.realpath(fx_dir)

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=site, **kwargs)

        def translate_path(self, path):
            raw = urllib.parse.unquote(urllib.parse.urlparse(path).path)
            if raw.startswith("/fixture/"):
                rel = os.path.normpath(raw[len("/fixture/"):].lstrip("/"))
                full = os.path.realpath(os.path.join(root_fx, rel))
                if full != root_fx and not full.startswith(root_fx + os.sep):
                    return os.path.join(root_fx, "missing")
                return full
            return super().translate_path(path)

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
    const want = [...select.options].some((o) => o.value === sport);
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
  const links = [...document.querySelectorAll("nav.main a, nav.toc a, nav.crumbs a, #vw")];
  function scroller(el) {
    let n = el.parentElement;
    while (n && n !== document.documentElement) {
      const ox = getComputedStyle(n).overflowX;
      if ((ox === "auto" || ox === "scroll" || ox === "hidden")
          && n.scrollWidth > n.clientWidth + 1) {
        const r = n.getBoundingClientRect();
        return { left: r.left, right: r.right };
      }
      n = n.parentElement;
    }
    return null;
  }
  return {
    vw: vw,
    scrollWidth: document.documentElement.scrollWidth,
    links: links.map((a) => {
      const r = a.getBoundingClientRect();
      return {
        text: a.textContent.trim(),
        left: r.left,
        right: r.right,
        scroller: scroller(a),
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
    setTimeout(() => requestAnimationFrame(() => {
      const header = document.querySelector("header.site");
      const table = document.querySelector("#flush table");
      const thead = table.tHead;
      const rows = [...table.tBodies[0].rows].filter((row) => row.querySelector("td") && !row.hidden);
      rows[Math.floor(rows.length / 2)].scrollIntoView({ block: "center" });
      const hb = header.getBoundingClientRect().bottom;
      let top = thead.getBoundingClientRect().top;
      if (top > hb + 0.5) window.scrollBy(0, top - hb + 24);
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
    }), 60);
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
      if (!rects.length) return true;
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
  const table = market.querySelector("table");
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


def _clipped(got):
    """A link past the viewport is fine when it lives in a scroller that does not."""
    bad = []
    for a in got["links"]:
        if a["left"] >= -1 and a["right"] <= got["vw"] + 1:
            continue
        box = a.get("scroller")
        if box and box["left"] >= -1 and box["right"] <= got["vw"] + 1:
            continue
        bad.append(a)
    return bad


def browser_checks():
    print("\nbrowser")
    from require_browser import require_browser
    sync_playwright = require_browser("test_site_layout.py")
    if sync_playwright is None:
        return
    fx_dir = tempfile.mkdtemp(prefix="layout-fx-")
    with open(os.path.join(fx_dir, "layout.html"), "w", encoding="utf-8") as fh:
        fh.write(_fixture_html())
    httpd = _serve(fx_dir)
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    pages = _published_pages()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 800}, device_scale_factor=1)
            for width in (1280, 390):
                page.set_viewport_size({"width": width, "height": 800})
                for path in pages:
                    page.goto(f"{base}/{path}", wait_until="load")
                    page.wait_for_timeout(40)
                    got = page.evaluate(OVERFLOW)
                    ok(got["scrollWidth"] <= got["clientWidth"] + 1,
                       f"{path} at {width}px: page scrollWidth {got['scrollWidth']} "
                       f"<= viewport {got['clientWidth']}")
                page.goto(f"{base}/fixture/layout.html", wait_until="load")
                page.wait_for_timeout(40)
                got = page.evaluate(OVERFLOW)
                ok(got["scrollWidth"] <= got["clientWidth"] + 1,
                   f"fixture/layout.html at {width}px: page scrollWidth {got['scrollWidth']} "
                   f"<= viewport {got['clientWidth']}")

            page.set_viewport_size({"width": 1280, "height": 800})
            page.goto(f"{base}/fixture/layout.html", wait_until="load")
            page.wait_for_timeout(40)
            combos = (
                ("Boston", "MLB", 1, "boston"),
                ("Shapovalov", "", 1, "shapovalov"),
                ("Boston", "Tennis · Combos", 0, None),
                ("", "MLB", 3, None),
                ("", "", len(CARD_ROWS), None),
            )
            for query, sport, expect, needle in combos:
                got = page.evaluate(CARDS, {"query": query, "sport": sport})
                label = f"search {query!r} sport {sport or 'all'}"
                ok(got["same"] and got["cardOn"] == got["rowOn"] == expect,
                   f"cards match rows for {label} "
                   f"({got['cardOn']} cards, {got['rowOn']} rows, of {got['rows']}; expected {expect})")
                ok(got["count"] == f"{got['cardOn']} of {got['rows']} rows",
                   f"count matches the visible cards for {label} ({got['count']!r})")
                if needle:
                    ok(got["cardOn"] == expect and needle in got["first"].lower()
                       and (sport == "" or all(s == sport for s in got["sports"])),
                       f"{label} shows the matching card ({got['first']!r}, {got['sports']})")
                if sport:
                    ok(got["hasSport"], f"sport option {sport!r} is on the fixture")

            page.set_viewport_size({"width": 400, "height": 800})
            nav_pages = list(pages) + ["fixture/layout.html"]
            for path in nav_pages:
                page.goto(f"{base}/{path}", wait_until="load")
                page.wait_for_timeout(30)
                got = page.evaluate(NAV)
                clipped = _clipped(got)
                ok(not clipped and got["scrollWidth"] <= got["vw"] + 1,
                   f"{path} at 400px: every nav item is inside the viewport"
                   + ("" if not clipped else
                      " (clipped: " + ", ".join(a["text"] for a in clipped) + ")"))

            page.set_viewport_size({"width": 1280, "height": 800})
            page.goto(f"{base}/fixture/layout.html", wait_until="load")
            page.wait_for_timeout(40)
            got = page.evaluate(STICKY_WRAP)
            hdr = float(str(got["hdr"]).removesuffix("px") or "0")
            ok(got["wrapped"] and not got["scrollX"] and abs(got["gap"]) <= 1
               and abs(got["headerHeight"] - hdr) <= 1,
               f"wrapped nav keeps the fixture header flush "
               f"(gap {got['gap']:.2f}px, header {got['headerHeight']:.1f}px, "
               f"--hdr-h {got['hdr']}, wrapped {got['wrapped']}, scroll-x {got['scrollX']})")

            page.goto(f"{base}/fixture/layout.html", wait_until="load")
            page.wait_for_timeout(30)
            for label in ("Date", "Settled", "Last"):
                got = page.evaluate(DATES, label)
                ok(not got.get("missing") and got["bad"] == 0,
                   f"fixture {label}: {got.get('n', 0)} dates on one line "
                   f"(sample {got.get('sample', '')!r}, {got.get('whiteSpace', '')}, "
                   f"{got.get('bad', 'missing')} wrapped)")

            weeks = [path for path in pages if re.search(r"archive/20\d\d-W\d\d\.html$", path)]
            ok(len(weeks) >= 1, f"archive weeks discovered by filename ({len(weeks)})")
            for path in weeks:
                page.goto(f"{base}/{path}", wait_until="load")
                page.wait_for_timeout(30)
                got = page.evaluate(DATES, "Settled")
                if got.get("missing"):
                    print(f"  ok   {path} Settled: no ISO dates on this week")
                    continue
                ok(got["bad"] == 0,
                   f"{path} Settled: {got.get('n', 0)} dates on one line "
                   f"(sample {got.get('sample', '')!r}, {got.get('whiteSpace', '')}, "
                   f"{got.get('bad', 'missing')} wrapped)")

            page.goto(f"{base}/fixture/layout.html", wait_until="load")
            labels = page.evaluate(LABELS)
            wanted = [row for row in labels if row["name"] in (
                "AAA gasoline no-change rule", "Commodity far-tail rule")]
            ok(len(wanted) == 2 and all(row["sub"] == "Rule" for row in wanted),
               f"fixture Markets subtitles are Rule ({wanted})")
            browser.close()
    finally:
        httpd.shutdown()


browser_checks()

print()
if FAILS:
    print(f"SHA {SHA} FAILED {len(FAILS)}")
    sys.exit(1)
print(f"SHA {SHA} PASSED")
