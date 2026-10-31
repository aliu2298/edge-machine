"""The Sandbox page's "Daily health" card (2026-10-30): the newest reports/daily report's verdict, its time,
and its red and amber lines. Built at page build from the files the twice-daily cloud health check writes
(format: reports/daily/README.md). With no report yet the card says so. Never breaks the page.

The card is public copy, the reports are not: a detail that carries a $ amount, a key-like string or a
phrase the public pages are kept free of is not shown on the card, only its status and component (the full
line stays in the report).
"""
import html as _h
import os
import re

import bot_health
import sandbox_audit

ROOT = os.path.dirname(os.path.abspath(__file__))
DIR = os.path.join(ROOT, "reports", "daily")
NAME = re.compile(r"^(\d{4}-\d{2}-\d{2})-(am|pm)\.md$")
VERDICT = re.compile(r"^(All green|\d+ red, \d+ amber)$")
CHECKED = re.compile(r"^Checked (\d{4}-\d{2}-\d{2} \d{2}:\d{2}) CT$")
LINE = re.compile(r"^- (green|amber|red) · ([^·]+?) · (.+)$")
REPO = "https://github.com/aliu2298/edge-machine/blob/main/reports/daily/"


def reports(d=DIR):
    """Report file names, newest first (the date, then pm after am)."""
    try:
        names = [f for f in os.listdir(d) if NAME.match(f)]
    except OSError:
        return []
    return sorted(names, key=lambda f: (NAME.match(f).group(1), NAME.match(f).group(2)), reverse=True)


def parse(text):
    """dict(verdict, checked, lines=[(status, component, detail)]) or None when line 1 is not a verdict."""
    rows = [r.rstrip() for r in (text or "").splitlines() if r.strip()]
    if not rows or not VERDICT.match(rows[0]):
        return None
    m = CHECKED.match(rows[1]) if len(rows) > 1 else None
    lines = [LINE.match(r).groups() for r in rows[1:] if LINE.match(r)]
    return dict(verdict=rows[0], checked=m.group(1) if m else None, lines=[tuple(x.strip() for x in g) for g in lines])


def _public(text):
    """The text if it is fit for a public page, else None."""
    if bot_health.guard(text) or sandbox_audit.COPY_RE.search(text):
        return None
    return text


def card(d=DIR):
    names = reports(d)
    if not names:
        return ('<div class="health-card" id="daily-health"><b>Daily health</b> · <span class="mut">no report yet: '
                'the first check runs at 7:30 AM or 7:30 PM Central.</span></div>')
    name = names[0]
    try:
        rep = parse(open(os.path.join(d, name), encoding="utf-8").read())
    except OSError:
        rep = None
    if rep is None:
        return (f'<div class="health-card" id="daily-health"><b>Daily health</b> · <span class="mut">the newest report '
                f'({_h.escape(name)}) is not in the expected format.</span></div>')
    bad = [x for x in rep["lines"] if x[0] in ("red", "amber")]
    bad.sort(key=lambda x: x[0] != "red")
    items = []
    for status, comp, detail in bad:
        comp_ok, det_ok = _public(comp), _public(detail)
        items.append(f'<li class="{status}"><b>{status}</b> · {_h.escape(comp_ok or "a component")}'
                     + (f' · {_h.escape(det_ok)}' if det_ok else ' · detail in the report') + '</li>')
    tone = "pos" if rep["verdict"] == "All green" else ("neg" if not rep["verdict"].startswith("0 red") else "")
    when = rep["checked"] + " CT" if rep["checked"] else name[:-3]
    return (f'<div class="health-card" id="daily-health"><b>Daily health</b> · <b class="{tone}">{_h.escape(rep["verdict"])}</b>'
            f' · <span class="mut">checked {_h.escape(when)} · <a href="{REPO}{_h.escape(name)}">full report</a></span>'
            + (f'<ul class="sm">{"".join(items)}</ul>' if items else "") + '</div>')


def safe_card(d=DIR):
    try:
        return card(d)
    except Exception:                                           # noqa: BLE001
        return ""
