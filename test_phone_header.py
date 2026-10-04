#!/usr/bin/env python3
"""Phone header: one short stuck bar, a sideways nav, toggle out of the header.

Fails on the wrapping header (main at the base of this change): the stuck bar
is several rows tall, the view toggle sits inside it, a one-link section nav
is rendered, and archive pages have no breadcrumb. Playwright is optional.
Without it the static checks still run, and CI prints a ::warning::.
"""
import datetime
import os
import re
import subprocess
import sys
import threading
import urllib.parse
from datetime import timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

FAILS = []
ROOT = os.path.dirname(os.path.abspath(__file__))


def _head_sha():
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return out or "unknown"


SHA = _head_sha()


def ok(cond, msg):
    print(f"  {'ok  ' if cond else 'FAIL'} {msg}")
    if not cond:
        FAILS.append(msg)


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


def _published():
    pages = [
        "index.html", "sandbox.html", "production.html", "trading.html",
        "nba.html", "soccer.html", "tennis.html", "cricket.html",
        "archive/index.html",
    ]
    archive = os.path.join(ROOT, "public_site", "archive")
    weeks = sorted(
        name for name in os.listdir(archive)
        if re.fullmatch(r"20\d\d-W\d\d\.html", name))
    pages.extend(f"archive/{name}" for name in weeks)
    return pages


def _header(html):
    match = re.search(r'<header class="site">.*?</header>', html, re.S)
    return match.group(0) if match else ""


def _toc(html):
    return re.search(r'<nav class="toc"[^>]*>.*?</nav>', html, re.S)


def _has_toggle(path):
    return path == "sandbox.html" or bool(re.fullmatch(r"archive/20\d\d-W\d\d\.html", path))


# One link, or a breadcrumb in that slot. The section nav must not be rendered.
_NO_TOC = {"index.html", "trading.html", "archive/index.html"}


def _expects_toc(path):
    if path in _NO_TOC or path.startswith("archive/"):
        return False
    return True


print(f"SHA {SHA}")
print("\nstatic")

import site_chrome
import sandbox_build as SB
import site_root

NOW = datetime.datetime(2026, 10, 4, 15, 51, tzinfo=timezone.utc)

try:
    forced = site_chrome.header(
        "sandbox",
        (("running", "Running"), ("archive", "Archive")),
        "stamp",
        tools=getattr(site_chrome, "VIEW_TOGGLE", getattr(site_chrome, "VIEW_BUTTON", "vw")),
    )
except TypeError as exc:
    forced = f"header() raised {exc}"
ok('id="vw"' not in forced and "Phone view" not in forced and "view-toggle" not in forced,
   "site_chrome.header() does not render the view toggle")

try:
    one = site_chrome.toc((("rules", "Rules"),))
    empty = site_chrome.toc(())
    two = site_chrome.toc((("running", "Running"), ("archive", "Archive")))
except Exception as exc:
    one = empty = two = f"toc raised {exc}"
ok(one == "" and empty == "", "toc() renders nothing when it has fewer than 2 links")
ok(isinstance(two, str) and two.count("<a ") == 2 and 'class="toc"' in two,
   "toc() still renders two or more links")

try:
    trail = site_chrome.header(
        "sandbox", (), "stamp", prefix="../",
        crumb=(("Sandbox", "../sandbox.html"), ("Archive", None), ("W39", None)))
except TypeError as exc:
    trail = f"header() raised {exc}"
ok('class="crumbs"' in trail and "Sandbox" in trail and "Archive" in trail and "W39" in trail,
   "header() can render a Sandbox › Archive › W39 breadcrumb")
ok(trail.count('aria-current="page"') == 1,
   "a breadcrumb does not add a second aria-current=page")

src = _read("sandbox_build.py")
section = re.search(
    r'sections = \((.*?)\n    \)\n    return site_chrome\.document\(\n        "Sandbox Tracker"',
    src, re.S)
ok(section is not None and "method" not in section.group(1).lower(),
   "the Sandbox section list does not repeat Method")

try:
    with_toggle = SB._tools("Search contests…", "Search running bets", view=True)
    plain = SB._tools("Search contests…", "Search recently settled bets")
except TypeError as exc:
    with_toggle = plain = f"_tools raised {exc}"
ok('id="vw"' in with_toggle and ">Cards<" in with_toggle and ">Table<" in with_toggle
   and "Phone view" not in with_toggle,
   "the table tools can carry a Cards | Table control")
ok(isinstance(plain, str) and plain.startswith("<div") and 'id="vw"' not in plain,
   "table tools without the flag do not carry the control")

index_html = SB.archive_index_html({}, NOW)
week_html = SB.archive_week_html("2026-W39", [], NOW)
trade_html = SB.trading_page(NOW)
root_html = site_root.root_stub(NOW)
ok('class="crumbs"' in index_html and ">Archive<" in index_html and ">Sandbox<" in index_html,
   "the archive index generator writes a Sandbox › Archive breadcrumb")
ok('id="vw"' not in index_html and 'class="toc"' not in index_html,
   "the archive index has no view toggle and no one-link section nav")
ok('class="crumbs"' in week_html and ">W39<" in week_html and ">Archive<" in week_html,
   "a week page generator writes a Sandbox › Archive › W39 breadcrumb")
ok('class="toc"' not in trade_html, "Trading does not render a one-link Rules nav")
ok('class="toc"' not in root_html, "the index stub does not render a one-link Sandbox nav")

print("\npublished pages")
for path in _published():
    html = _read(os.path.join("public_site", path))
    header = _header(html)
    ok(header != "", f"{path} has a site header")
    ok('id="vw"' not in header and "Phone view" not in header and "view-toggle" not in header,
       f"{path} header does not contain the view toggle")
    ok(len(re.findall(r'aria-current="page"', html)) == 1,
       f"{path} has exactly one aria-current=page")
    toc = _toc(html)
    if not _expects_toc(path):
        ok(toc is None, f"{path} does not render nav.toc")
    elif toc is None:
        ok(False, f"{path} renders nav.toc")
    else:
        labels = re.findall(r">([^<]+)</a>", toc.group(0))
        ok(len(labels) >= 2, f"{path} section nav has {len(labels)} links")
        ok("Method" not in labels, f"{path} section nav does not repeat Method")
    if path.startswith("archive/"):
        ok('class="crumbs"' in html and ">Sandbox<" in html and ">Archive<" in html,
           f"{path} shows the archive breadcrumb")
        if re.fullmatch(r"archive/20\d\d-W\d\d\.html", path):
            week = path.rsplit("-", 1)[-1].replace(".html", "")
            ok(f">{week}<" in html, f"{path} breadcrumb names {week}")
    if _has_toggle(path):
        ok('id="vw"' in html and ">Cards<" in html and ">Table<" in html,
           f"{path} has the Cards | Table control")
        tools = re.search(r'<div class="table-tools">.*?</div>', html, re.S)
        ok(tools is not None and 'id="vw"' in tools.group(0),
           f"{path} puts the control in the table tools")
    else:
        ok('id="vw"' not in html, f"{path} has no view toggle")


def _serve():
    site = os.path.join(ROOT, "public_site")

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=site, **kwargs)

        def log_message(self, fmt, *args):
            return

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def _hold_root(route):
    """Keep the index stub on screen. Visitors are redirected; the audit is not."""
    path = urllib.parse.urlparse(route.request.url).path
    if not path.endswith("/index.html") or path.endswith("/archive/index.html"):
        route.continue_()
        return
    resp = route.fetch()
    body = resp.text()
    body = body.replace(
        '<meta http-equiv="refresh" content="0; url=./sandbox.html">',
        '<meta name="em-hold" content="1">')
    body = body.replace('\n<script src="./root.js"></script>', "")
    headers = {k: v for k, v in resp.headers.items() if k.lower() != "content-length"}
    route.fulfill(status=resp.status, headers=headers, body=body)


MEASURE = r"""
async () => {
  await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  const doc = document.documentElement;
  const header = document.querySelector("header.site");
  const topbar = document.querySelector(".topbar");
  const nav = document.querySelector("nav.main");
  const links = [...nav.querySelectorAll("a")];
  const tops = links.map((a) => a.offsetTop);
  const current = nav.querySelector('[aria-current="page"]');

  function fits(el, box) {
    const a = el.getBoundingClientRect();
    const c = box.getBoundingClientRect();
    return a.width > 1 && a.height > 1
      && a.left >= c.left - 1 && a.right <= c.right + 1
      && a.top >= c.top - 1 && a.bottom <= c.bottom + 1;
  }
  const activeVisible = !!(current && fits(current, nav)
    && current.getBoundingClientRect().left >= -1
    && current.getBoundingClientRect().right <= window.innerWidth + 1);

  const saved = nav.scrollLeft;
  const reach = [];
  for (const a of links) {
    let shown = false;
    for (let i = 0; i < 8 && !shown; i++) {
      if (fits(a, nav)) { shown = true; break; }
      const ar = a.getBoundingClientRect();
      const nr = nav.getBoundingClientRect();
      if (ar.right > nr.right + 1) nav.scrollLeft += (ar.right - nr.right) + 16;
      else if (ar.left < nr.left - 1) nav.scrollLeft -= (nr.left - ar.left) + 16;
      else break;
    }
    reach.push({ text: a.textContent.trim(), ok: shown || fits(a, nav) });
  }
  nav.scrollLeft = saved;

  const overflow = doc.scrollWidth > doc.clientWidth + 1;
  const heights = (sel) => [...document.querySelectorAll(sel)].map((el) => ({
    text: (el.textContent || "").replace(/\s+/g, " ").trim().slice(0, 48),
    height: el.getBoundingClientRect().height,
  }));

  const y = Math.min(1200, Math.max(0, doc.scrollHeight - window.innerHeight));
  window.scrollTo(0, y);
  await new Promise((resolve) => requestAnimationFrame(resolve));
  function stuckEl() {
    const list = [topbar, header].filter(Boolean);
    for (const el of list) {
      const pos = getComputedStyle(el).position;
      if (pos === "sticky" || pos === "fixed") return el;
    }
    return header;
  }
  const stuck = stuckEl();
  const stuckBox = stuck.getBoundingClientRect();
  const scrolledY = window.scrollY;
  const toc = document.querySelector("nav.toc");
  const crumbs = document.querySelector("nav.crumbs");
  const sub = toc || crumbs;
  const subBox = sub ? sub.getBoundingClientRect() : null;
  const subTop = subBox ? subBox.top : null;
  const subBottom = subBox ? subBox.bottom : null;
  const hdr = getComputedStyle(doc).getPropertyValue("--hdr-h").trim();

  function resolved() {
    const v = doc.getAttribute("data-view");
    if (v === "cards" || v === "table") return v;
    const wide = window.matchMedia("(max-width:760px)").matches;
    const phone = window.matchMedia("(max-width:640px)").matches;
    return wide && !phone ? "cards" : "table";
  }
  const vw = document.getElementById("vw");
  let toggle = null;
  if (vw) {
    const buttons = [...vw.querySelectorAll("button")];
    const read = () => buttons.map((b) => ({
      label: b.textContent.trim(),
      pressed: b.getAttribute("aria-pressed"),
      view: b.getAttribute("data-view"),
      height: b.getBoundingClientRect().height,
    }));
    const before = {
      width: vw.getBoundingClientRect().width,
      insideHeader: header.contains(vw),
      radius: parseFloat(getComputedStyle(vw).borderTopLeftRadius) || 0,
      view: resolved(),
      buttons: read(),
    };
    const target = buttons.find((b) => b.getAttribute("aria-pressed") !== "true") || buttons[0];
    const next = target ? target.getAttribute("data-view") : "";
    if (target) target.click();
    await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    toggle = {
      before: before,
      after: {
        width: vw.getBoundingClientRect().width,
        view: resolved(),
        expected: next,
        buttons: read(),
      },
    };
  }

  return {
    rowSpread: tops.length ? Math.max(...tops) - Math.min(...tops) : 99,
    linkCount: links.length,
    active: current ? current.textContent.trim() : "",
    activeVisible: activeVisible,
    reach: reach,
    overflow: overflow,
    scrollX: window.scrollX,
    stuckHeight: stuckBox.height,
    stuckTop: stuckBox.top,
    stuckClass: stuck.className,
    scrolledY: scrolledY,
    subTop: subTop,
    subBottom: subBottom,
    hdr: hdr,
    tocCount: toc ? toc.querySelectorAll("a").length : 0,
    tocMethod: toc ? [...toc.querySelectorAll("a")].some((a) => a.textContent.trim() === "Method") : false,
    crumb: crumbs ? crumbs.textContent.replace(/\s+/g, " ").trim() : "",
    currents: document.querySelectorAll('[aria-current="page"]').length,
    navHeights: heights("nav.main a"),
    tocHeights: heights("nav.toc a"),
    crumbHeights: heights("nav.crumbs a"),
    toggle: toggle,
    h1: (document.querySelector("h1") || {}).textContent || "",
  };
}
"""


def _near(got, want, tol=1.0):
    try:
        return abs(float(str(got).removesuffix("px")) - want) <= tol
    except (TypeError, ValueError):
        return False


def browser_checks():
    print("\nbrowser")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("::warning::Playwright is not installed; browser checks in test_phone_header.py were not run")
        print("  skipped: playwright is not installed; browser check not run")
        return
    httpd = _serve()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    pages = _published()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            for width, height in ((390, 844), (360, 780)):
                print(f"\n  viewport {width}x{height}")
                context = browser.new_context(
                    viewport={"width": width, "height": height},
                    device_scale_factor=1,
                    is_mobile=True,
                    has_touch=True,
                )
                context.add_init_script(
                    "try{localStorage.removeItem('sandbox-view')}catch(e){}")
                context.route("**/index.html", _hold_root)
                page = context.new_page()
                for path in pages:
                    page.goto(f"{base}/{path}", wait_until="load")
                    page.wait_for_timeout(40)
                    if path == "index.html" and "sandbox.html" in page.url:
                        ok(False, f"{path} @{width}: index stub stayed on the stub (went to {page.url})")
                        continue
                    got = page.evaluate(MEASURE)
                    label = f"{path} @{width}"
                    h = got["stuckHeight"]
                    print(f"    {label}: stuck {h:.1f}px top {got['stuckTop']:.1f} "
                          f"--hdr-h {got['hdr']} row {got['rowSpread']} "
                          f"active {got['active']!r} visible {got['activeVisible']}")
                    ok(48 <= h <= 64 and abs(got["stuckTop"]) <= 1,
                       f"{label}: stuck header is {h:.1f}px, between 48 and 64, "
                       f"and stays at the top (top {got['stuckTop']:.1f})")
                    hdr = float(str(got["hdr"]).removesuffix("px") or "0")
                    ok(abs(hdr - h) <= 1,
                       f"{label}: --hdr-h matches the stuck height "
                       f"({got['hdr']} vs {h:.1f}px)")
                    ok(got["rowSpread"] <= 1 and got["linkCount"] == 8,
                       f"{label}: all {got['linkCount']} main-nav links share one row "
                       f"(offsetTop spread {got['rowSpread']}px)")
                    missed = [a["text"] for a in got["reach"] if not a["ok"]]
                    ok(not missed,
                       f"{label}: every main-nav link can be scrolled into view"
                       + ("" if not missed else " (missed " + ", ".join(missed) + ")"))
                    ok(got["activeVisible"],
                       f"{label}: the active pill ({got['active']!r}) is visible on load")
                    ok(not got["overflow"] and got["scrollX"] == 0,
                       f"{label}: the page does not scroll sideways "
                       f"(scrollX {got['scrollX']})")
                    ok(got["currents"] == 1,
                       f"{label}: exactly one aria-current=page ({got['currents']})")
                    short = [a for a in got["navHeights"] if a["height"] < 44]
                    ok(not short, f"{label}: main-nav pills are at least 44px tall"
                       + ("" if not short else f" ({short[0]})"))
                    if not _expects_toc(path):
                        ok(got["tocCount"] == 0 and not got["tocMethod"],
                           f"{label}: nav.toc is not rendered")
                    else:
                        ok(got["tocCount"] >= 2 and not got["tocMethod"],
                           f"{label}: section nav has {got['tocCount']} links and no Method")
                        short = [a for a in got["tocHeights"] if a["height"] < 44]
                        ok(not short, f"{label}: section chips are at least 44px tall"
                           + ("" if not short else f" ({short[0]})"))
                    if path.startswith("archive/"):
                        ok("Sandbox" in got["crumb"] and "Archive" in got["crumb"],
                           f"{label}: breadcrumb is {got['crumb']!r}")
                        short = [a for a in got["crumbHeights"] if a["height"] < 44]
                        ok(got["crumbHeights"] and not short,
                           f"{label}: breadcrumb links are at least 44px tall"
                           + ("" if not short else f" ({short[0]})"))
                        if got["scrolledY"] > 80 and got["subBottom"] is not None:
                            ok(got["subBottom"] <= 1,
                               f"{label}: the breadcrumb scrolls away "
                               f"(bottom {got['subBottom']:.1f}, stuck {h:.1f})")
                    elif got["scrolledY"] > 80 and got["subBottom"] is not None and got["tocCount"]:
                        ok(got["subBottom"] <= 1,
                           f"{label}: the section nav scrolls away "
                           f"(bottom {got['subBottom']:.1f}, stuck {h:.1f})")
                    toggle = got["toggle"]
                    if _has_toggle(path):
                        ok(toggle is not None and not toggle["before"]["insideHeader"],
                           f"{label}: the view toggle is on the page and not in header.site")
                        if toggle:
                            before = toggle["before"]
                            after = toggle["after"]
                            labels = [b["label"] for b in before["buttons"]]
                            ok(labels == ["Cards", "Table"],
                               f"{label}: toggle labels are {labels}")
                            ok(before["radius"] < 20,
                               f"{label}: the toggle is not a nav pill "
                               f"(radius {before['radius']}px)")
                            def pressed(buttons, view):
                                return all(
                                    (b["pressed"] == "true") == (b["view"] == view)
                                    for b in buttons)
                            ok(pressed(before["buttons"], before["view"]),
                               f"{label}: aria-pressed matches {before['view']} before the tap "
                               f"({before['buttons']})")
                            ok(after["view"] == after["expected"]
                               and pressed(after["buttons"], after["view"]),
                               f"{label}: aria-pressed matches {after['view']} after the tap "
                               f"({after['buttons']})")
                            ok(abs(before["width"] - after["width"]) < 1,
                               f"{label}: toggle width stays {before['width']:.1f}px "
                               f"(after {after['width']:.1f})")
                            short = [b for b in before["buttons"] if b["height"] < 44]
                            ok(not short, f"{label}: toggle segments are at least 44px tall"
                               + ("" if not short else f" ({short[0]})"))
                    else:
                        ok(toggle is None,
                           f"{label}: no view toggle"
                           + ("" if toggle is None else " (one was rendered)"))
                page.close()
                context.close()
            browser.close()
    finally:
        httpd.shutdown()


browser_checks()

print()
if FAILS:
    print(f"SHA {SHA} FAILED {len(FAILS)}")
    sys.exit(1)
print(f"SHA {SHA} PASSED")
