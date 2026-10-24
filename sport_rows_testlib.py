#!/usr/bin/env python3
"""Read the sport pages' rule rows back out of their markup, for the tests.

A rule is a <details class="sp-rule"> whose <summary> is the row (name, badges,
market, scope, record, ROI after fees, won v priced, evidence, verdict) and whose
body is the closed "Rule details" fold. Not a test itself: the page tests import it.
"""
import contextlib
import re

import sandbox_sources as S


@contextlib.contextmanager
def running_again(*pairs):
    """Put retired "source|sport" scopes back on the run, in this process only, then restore.

    For a test whose fixture replays a lane from before its retirement (2026-10-24 and
    later) and asks about the machinery, not the lane list. The retirement itself is held
    by test_retired_2026_10_24.py.
    """
    saved = {}
    for key in pairs:
        src, sp = key.split("|", 1)
        meta = S.SOURCES[src]
        saved.setdefault(src, (meta["sports"], meta.get("retired_sports")))
        if sp not in meta["sports"]:
            meta["sports"] = list(meta["sports"]) + [sp]
        meta["retired_sports"] = {k: v for k, v in (meta.get("retired_sports") or {}).items() if k != sp}
    try:
        yield
    finally:
        for src, (sports, gone) in saved.items():
            S.SOURCES[src]["sports"] = sports
            if gone is None:
                S.SOURCES[src].pop("retired_sports", None)
            else:
                S.SOURCES[src]["retired_sports"] = gone


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
