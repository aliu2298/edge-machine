#!/usr/bin/env python3
"""Phone header: one short stuck bar, a sideways nav, toggle out of the header.

Fails on the wrapping header (main at the base of this change): the stuck bar
is several rows tall, the view toggle sits inside it, a one-link section nav
is rendered, and archive pages have no breadcrumb. Playwright is optional
locally. Without it the static checks still run. CI sets REQUIRE_BROWSER=1,
and then a missing Playwright fails this test.
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

_phone_css = _read("public_site/site.css").split("@media (max-width: 640px)", 1)[-1]
ok("nav.main a:focus-visible" in _phone_css and "outline-offset: -3px" in _phone_css,
   "phone nav pills inset the focus ring so the nav clip does not cut it")

try:
    trail = site_chrome.header(
        "sandbox", (), "stamp", prefix="../",
        crumb=(("Sandbox", "../sandbox.html"), ("Archive", None), ("W39", None)))
except TypeError as exc:
    trail = f"header() raised {exc}"
ok('class="crumbs"' in trail and "Sandbox" in trail and "Archive" in trail and "W39" in trail,
   "header() can render a Sandbox › Archive › W39 breadcrumb")
_trail_nav = re.search(r'<nav class="main"[^>]*>.*?</nav>', trail, re.S)
ok(_trail_nav is not None and _trail_nav.group(0).count('aria-current="page"') == 1,
   "nav.main has exactly one aria-current=page")
ok('class="here" aria-current="page"' in trail,
   "the breadcrumb current item is aria-current=page")

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

# The site root's visible time is Central Time, the same form site_root.py writes.
# A raw ISO instant or a +00:00 offset in that stamp is the broken regeneration.
_STAMP_TEXT = re.compile(
    r"Updated (?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) "
    r"\d{1,2}, \d{1,2}:\d{2} (?:AM|PM) CT")
_RAW_ISO = re.compile(
    r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?")


def _visible_html(fragment):
    return re.sub(r"<[^>]+>", "", fragment or "").strip()


print("\nindex stamp")
_index = _read("public_site/index.html")
_stamp_el = re.search(r'<p class="stamp">(.*?)</p>', _index, re.S)
_lede_el = re.search(r'<p class="lede">(.*?)</p>', _index, re.S)
_stamp_text = _visible_html(_stamp_el.group(1) if _stamp_el else "")
_lede_text = _visible_html(_lede_el.group(1) if _lede_el else "")
ok(_STAMP_TEXT.fullmatch(_stamp_text) is not None,
   f"index.html stamp is 'Updated Mon D, H:MM AM/PM CT' (got {_stamp_text!r})")
ok("Continue to the Sandbox" not in _index and 'url=./sandbox.html' not in _index,
   "index.html is the Production shell, not a redirect to the Sandbox")
ok('href="./production.html" aria-current="page"' in _index,
   "index.html marks Production as the current page")
ok(_lede_text == "" or _STAMP_TEXT.fullmatch(_lede_text) is not None,
   f"index.html has no stale lede (got {_lede_text!r})")
_raw_hits = _RAW_ISO.findall(_index)
_attr_ok = re.findall(r'datetime="(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)"', _index)
ok("+00:00" not in _index and set(_raw_hits) <= set(_attr_ok),
   "index.html stamp contains no +00:00 or raw ISO datetime "
   f"(+00:00={'yes' if '+00:00' in _index else 'no'}, raw={_raw_hits})")

print("\npublished pages")
for path in _published():
    html = _read(os.path.join("public_site", path))
    header = _header(html)
    ok(header != "", f"{path} has a site header")
    ok('id="vw"' not in header and "Phone view" not in header and "view-toggle" not in header,
       f"{path} header does not contain the view toggle")
    _main = re.search(r'<nav class="main"[^>]*>.*?</nav>', html, re.S)
    ok(_main is not None and _main.group(0).count('aria-current="page"') == 1,
       f"{path} nav.main has exactly one aria-current=page")
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
        ok('class="here" aria-current="page"' in html,
           f"{path} breadcrumb current item is aria-current=page")
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
    currents: document.querySelectorAll('nav.main [aria-current="page"]').length,
    crumbCurrent: document.querySelectorAll('nav.crumbs [aria-current="page"]').length,
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


FOCUS_SNAP = r"""
() => {
  const pad = 0.5;
  function ring(el, clip) {
    const rect = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    const width = parseFloat(cs.outlineWidth) || 0;
    const offset = parseFloat(cs.outlineOffset) || 0;
    const shown = cs.outlineStyle !== "none" && width > 0;
    const extra = shown ? width + offset : 0;
    const box = {
      top: rect.top - extra,
      bottom: rect.bottom + extra,
      left: rect.left - extra,
      right: rect.right + extra,
    };
    return { rect, box, shown, offset };
  }
  function outlineClears(r, clip, visLeft, visRight) {
    const box = r.box;
    return r.shown
      && box.top >= clip.top - pad && box.bottom <= clip.bottom + pad
      && box.left >= visLeft - pad && box.right <= visRight + pad;
  }
  function insets(scroller) {
    const fade = parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--nav-fade")) || 22;
    const overflow = scroller.scrollWidth > scroller.clientWidth + 1;
    return {
      left: overflow && scroller.scrollLeft > 2 ? fade : 0,
      right: overflow && scroller.scrollLeft + scroller.clientWidth < scroller.scrollWidth - 2 ? fade : 0,
    };
  }
  const a = document.activeElement;
  if (!a) return { kind: "none" };
  const main = document.querySelector("nav.main");
  const toc = document.querySelector("nav.toc");
  const crumbs = document.querySelector("nav.crumbs");
  const toggle = document.querySelector(".view-toggle");
  if (main && a.tagName === "A" && main.contains(a)) {
    const links = [...main.querySelectorAll("a")];
    const clip = main.getBoundingClientRect();
    const r = ring(a, clip);
    const side = insets(main);
    const visLeft = clip.left + side.left;
    const visRight = clip.right - side.right;
    const clear = r.rect.width > 1 && r.rect.height > 1
      && r.rect.left >= visLeft - pad && r.rect.right <= visRight + pad
      && r.rect.top >= clip.top - pad && r.rect.bottom <= clip.bottom + pad;
    return {
      kind: "pill", text: a.textContent.trim(), index: links.indexOf(a), count: links.length,
      clear: clear, outlineInside: outlineClears(r, clip, visLeft, visRight), offset: r.offset,
      left: r.rect.left, right: r.rect.right, visLeft: visLeft, visRight: visRight,
      boxTop: r.box.top, boxBottom: r.box.bottom, boxLeft: r.box.left, boxRight: r.box.right,
      clipTop: clip.top, clipBottom: clip.bottom,
    };
  }
  const chipNav = toc && a.tagName === "A" && toc.contains(a) ? toc
    : crumbs && a.tagName === "A" && crumbs.contains(a) ? crumbs : null;
  if (chipNav) {
    const clip = chipNav.getBoundingClientRect();
    const r = ring(a, clip);
    const side = insets(chipNav);
    const visLeft = clip.left + side.left;
    const visRight = clip.right - side.right;
    const clear = r.rect.width > 1
      && r.rect.left >= visLeft - pad && r.rect.right <= visRight + pad
      && r.rect.top >= clip.top - pad && r.rect.bottom <= clip.bottom + pad;
    return {
      kind: "chip", text: a.textContent.trim(),
      clear: clear, outlineInside: outlineClears(r, clip, visLeft, visRight), offset: r.offset,
      left: r.rect.left, right: r.rect.right, visLeft: visLeft, visRight: visRight,
      boxTop: r.box.top, boxBottom: r.box.bottom, boxLeft: r.box.left, boxRight: r.box.right,
      clipTop: clip.top, clipBottom: clip.bottom,
    };
  }
  if (toggle && a.tagName === "BUTTON" && toggle.contains(a)) {
    const clip = toggle.getBoundingClientRect();
    const r = ring(a, clip);
    return {
      kind: "toggle", text: a.textContent.trim(),
      outlineInside: outlineClears(r, clip, clip.left, clip.right), shown: r.shown, offset: r.offset,
      boxTop: r.box.top, boxBottom: r.box.bottom, boxLeft: r.box.left, boxRight: r.box.right,
      clipTop: clip.top, clipBottom: clip.bottom, clipLeft: clip.left, clipRight: clip.right,
    };
  }
  return { kind: "other" };
}
"""

ANCHOR = r"""
() => {
  const bar = document.querySelector(".topbar");
  const sections = [...document.querySelectorAll("main section[id]")];
  if (!bar || !sections.length) return { skip: true };
  const doc = document.documentElement;
  const pad = parseFloat(getComputedStyle(doc).scrollPaddingTop) || 0;
  const maxScroll = doc.scrollHeight - window.innerHeight;
  window.scrollTo(0, 0);
  for (const sec of sections) {
    const margin = parseFloat(getComputedStyle(sec).scrollMarginTop) || 0;
    const absTop = sec.getBoundingClientRect().top + window.scrollY;
    const desired = absTop - pad - margin;
    if (desired > maxScroll + 1 || desired < 8) continue;
    sec.scrollIntoView({ block: "start" });
    const gap = sec.getBoundingClientRect().top - bar.getBoundingClientRect().bottom;
    return { skip: false, id: sec.id, gap: gap, margin: margin, pad: pad };
  }
  return { skip: true };
}
"""


def _nav_count(path):
    """The shell's page pills are Sandbox, Production, Trading, and Method."""
    if path == "index.html":
        return 4
    return len(site_chrome.PAGES)


def _keyboard_focus(page, expect_toggle, pill_target=8):
    """Tab from the skip link through every main-nav pill, chip, and toggle segment."""
    page.evaluate("""() => {
      window.scrollTo(0, 0);
      const skip = document.querySelector("a.skip");
      if (skip) skip.focus();
    }""")
    pills, chips, toggles = [], [], []
    seen = set()
    for _ in range(64):
        page.keyboard.press("Tab")
        info = page.evaluate(FOCUS_SNAP)
        kind = info.get("kind")
        if kind == "pill" and info.get("index") not in seen:
            seen.add(info.get("index"))
            pills.append(info)
        elif kind == "chip":
            chips.append(info)
        elif kind == "toggle":
            toggles.append(info)
        elif len(pills) >= pill_target and not expect_toggle:
            break
        if len(pills) >= pill_target and expect_toggle and len(toggles) >= 2:
            break
    return pills, chips, toggles


def _arm_press_probe(page):
    page.evaluate("""() => {
      if (window.__pressArmed) return;
      window.__pressArmed = true;
      document.addEventListener("click", (ev) => {
        const nav = document.querySelector("nav.main");
        const node = ev.target && ev.target.nodeType === 1 ? ev.target : ev.target && ev.target.parentElement;
        const a = node && node.closest ? node.closest("a") : null;
        const pill = a && nav && nav.contains(a) ? a : null;
        window.__press = {
          text: pill ? (pill.textContent || "").trim() : "",
          href: pill ? pill.getAttribute("href") : "",
        };
        ev.preventDefault();
      }, true);
    }""")


def _pointer_sweep(page, label):
    """Tap and click the visible centre of every pill, at the start and partway along."""
    _arm_press_probe(page)
    spots = page.evaluate("""() => {
      const nav = document.querySelector("nav.main");
      const max = Math.max(0, nav.scrollWidth - nav.clientWidth);
      const part = Math.round(max * 0.45);
      const spots = [{ name: "start", left: 0 }];
      if (part > 8) spots.push({ name: "partway", left: part });
      return spots;
    }""")
    for spot in spots:
        indexes = page.evaluate("""(left) => {
          const nav = document.querySelector("nav.main");
          nav.scrollLeft = left;
          const clip = nav.getBoundingClientRect();
          const out = [];
          nav.querySelectorAll("a").forEach((a, index) => {
            const r = a.getBoundingClientRect();
            const L = Math.max(r.left, clip.left);
            const R = Math.min(r.right, clip.right);
            const T = Math.max(r.top, clip.top);
            const B = Math.min(r.bottom, clip.bottom);
            if (R - L >= 2 && B - T >= 2) out.push(index);
          });
          return out;
        }""", spot["left"])
        for kind in ("tap", "click"):
            for index in indexes:
                point = page.evaluate("""(spec) => {
                  const nav = document.querySelector("nav.main");
                  const active = document.activeElement;
                  if (active && active !== document.body && active.blur) active.blur();
                  nav.scrollLeft = spec.left;
                  window.__press = null;
                  const a = nav.querySelectorAll("a")[spec.index];
                  if (!a) return { skip: true };
                  const clip = nav.getBoundingClientRect();
                  const r = a.getBoundingClientRect();
                  const L = Math.max(r.left, clip.left);
                  const R = Math.min(r.right, clip.right);
                  const T = Math.max(r.top, clip.top);
                  const B = Math.min(r.bottom, clip.bottom);
                  if (R - L < 2 || B - T < 2) return { skip: true };
                  return {
                    skip: false,
                    text: (a.textContent || "").trim(),
                    href: a.getAttribute("href") || "",
                    x: (L + R) / 2,
                    y: (T + B) / 2,
                  };
                }""", {"left": spot["left"], "index": index})
                if not point or point.get("skip"):
                    continue
                if kind == "tap":
                    page.touchscreen.tap(point["x"], point["y"])
                else:
                    page.mouse.click(point["x"], point["y"])
                hit = page.evaluate("() => window.__press") or {}
                same = hit.get("text") == point["text"] and hit.get("href") == point["href"]
                detail = "" if same else f" (hit {hit.get('text')!r} {hit.get('href')!r})"
                ok(same,
                   f"{label}: {kind} {spot['name']} on {point['text']!r} lands on that pill{detail}")


def _height_keeps_scroll(page, label, width, height):
    """A height-only resize, like the mobile URL bar, must not jump the nav."""
    before = page.evaluate("""() => {
      const nav = document.querySelector("nav.main");
      const active = document.activeElement;
      if (active && active !== document.body && active.blur) active.blur();
      const max = Math.max(0, nav.scrollWidth - nav.clientWidth);
      nav.scrollLeft = Math.round(max * 0.45);
      return nav.scrollLeft;
    }""")
    try:
        page.set_viewport_size({"width": width, "height": height + 90})
        page.wait_for_timeout(40)
        after = page.evaluate("() => document.querySelector('nav.main').scrollLeft")
    finally:
        page.set_viewport_size({"width": width, "height": height})
    ok(abs(after - before) <= 1,
       f"{label}: a height-only resize keeps a manual nav scroll ({before:.0f}px -> {after:.0f}px)")


def browser_checks():
    print("\nbrowser")
    from require_browser import require_browser
    sync_playwright = require_browser("test_phone_header.py")
    if sync_playwright is None:
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
                    label = f"{path} @{width}"
                    saved_nav = page.evaluate(
                        "() => { const n = document.querySelector('nav.main'); return n ? n.scrollLeft : 0; }")
                    nav_n = _nav_count(path)
                    pills, chips, toggles = _keyboard_focus(page, _has_toggle(path), nav_n)
                    page.evaluate("""(x) => {
                      const nav = document.querySelector('nav.main');
                      if (document.activeElement && document.activeElement.blur) document.activeElement.blur();
                      if (nav) nav.scrollLeft = x;
                      window.scrollTo(0, 0);
                    }""", saved_nav)
                    ok(len(pills) == nav_n,
                       f"{label}: tabbed through all {nav_n} main-nav pills (got {len(pills)}: "
                       + ", ".join(p.get("text", "") for p in pills) + ")")
                    for pill in pills:
                        ok(pill["clear"] and pill["outlineInside"],
                           f"{label}: pill {pill['text']!r} is clear of the fades and its outline "
                           f"is inside the nav (left {pill['left']:.0f}..{pill['right']:.0f} vs "
                           f"{pill['visLeft']:.0f}..{pill['visRight']:.0f}, outline "
                           f"{pill['boxTop']:.1f}..{pill['boxBottom']:.1f} vs "
                           f"{pill['clipTop']:.1f}..{pill['clipBottom']:.1f}, offset {pill['offset']}px)")
                    for chip in chips:
                        ok(chip["clear"] and chip["outlineInside"],
                           f"{label}: chip {chip['text']!r} is clear of the fades and its outline "
                           f"is inside the row (left {chip['left']:.0f}..{chip['right']:.0f} vs "
                           f"{chip['visLeft']:.0f}..{chip['visRight']:.0f}, outline "
                           f"{chip.get('boxLeft', 0):.1f}..{chip.get('boxRight', 0):.1f} vs fade "
                           f"{chip['visLeft']:.1f}..{chip['visRight']:.1f}, offset {chip['offset']}px)")
                    _pointer_sweep(page, label)
                    _height_keeps_scroll(page, label, width, height)
                    page.evaluate("""(x) => {
                      const nav = document.querySelector('nav.main');
                      if (document.activeElement && document.activeElement.blur) document.activeElement.blur();
                      if (nav) nav.scrollLeft = x;
                      window.scrollTo(0, 0);
                    }""", saved_nav)
                    if _has_toggle(path):
                        names = [t.get("text") for t in toggles]
                        ok(names[:2] == ["Cards", "Table"],
                           f"{label}: tabbed to both toggle segments ({names})")
                        for seg in toggles[:2]:
                            ok(seg.get("shown") and seg.get("outlineInside"),
                               f"{label}: toggle {seg.get('text')!r} outline sits inside .view-toggle "
                               f"(offset {seg.get('offset')}px box {seg.get('boxTop', 0):.1f}.."
                               f"{seg.get('boxBottom', 0):.1f} vs {seg.get('clipTop', 0):.1f}.."
                               f"{seg.get('clipBottom', 0):.1f})")
                    got = page.evaluate(MEASURE)
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
                    ok(got["rowSpread"] <= 1 and got["linkCount"] == nav_n,
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
                       f"{label}: nav.main has exactly one aria-current=page ({got['currents']})")
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
                        ok(got["crumbCurrent"] == 1,
                           f"{label}: breadcrumb current item is aria-current=page "
                           f"({got['crumbCurrent']})")
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
                    landed = page.evaluate(ANCHOR)
                    if not landed.get("skip"):
                        gap = landed["gap"]
                        ok(8 <= gap <= 12,
                           f"{label}: #{landed['id']} lands {gap:.1f}px under the bar "
                           f"(scroll-padding {landed['pad']}px, scroll-margin {landed['margin']}px)")
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
