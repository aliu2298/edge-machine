#!/usr/bin/env python3
"""Read the sport pages' rule rows back out of their markup, for the tests.

A rule is a <details class="sp-rule"> whose <summary> is the row (name, badges,
market, scope, record, ROI after fees, won v priced, evidence, verdict) and whose
body is the closed "Rule details" fold. Not a test itself: the page tests import it.
"""
import re

_ROW = re.compile(r'<details class="sp-rule( is-early)?" data-source="([^"]*)" data-sport="([^"]*)" '
                  r'data-scope="([^"]*)" data-stage="([^"]*)"( data-early="1")?>')
_CELL = re.compile(r'<span class="sp-cell[^"]*" data-l="([^"]+)">(.*?)</span>(?=<span class="sp-cell|$)', re.S)


def rule_rows(markup):
    """[dict(source, sport, scope, stage, early, name, badges, cells, summary, body, open)] in page order."""
    out = []
    for m in _ROW.finditer(markup):
        start = m.end()
        nxt = markup.find('<details class="sp-rule', start)
        chunk = markup[start:nxt if nxt != -1 else len(markup)]
        sm = re.search(r"<summary[^>]*>(.*?)</summary>", chunk, re.S)
        summary = sm.group(1) if sm else ""
        body = chunk[sm.end():] if sm else ""
        name = re.search(r'<b class="sp-name" title="([^"]*)">(.*?)</b>', summary)
        badges = re.search(r'<span class="sp-badges">(.*?)</span><span class="sr-only">', summary, re.S)
        out.append(dict(
            source=m.group(2), sport=m.group(3), scope=m.group(4), stage=m.group(5),
            early=bool(m.group(1)), full_name=name.group(1) if name else "", name=name.group(2) if name else "",
            badges=badges.group(1) if badges else "", cells=dict(_CELL.findall(summary)),
            summary=summary, body=body, open=" open" in m.group(0)))
    return out


def text(html):
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())
