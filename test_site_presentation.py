#!/usr/bin/env python3
"""Presentation checks for the public pages: phone labels and safe links.

These pin two display bugs. They fail on the builders before the fix and pass
after, and they do not grade, settle, or rewrite a ledger.
"""
import os
import re
import sys
from datetime import datetime, timezone

import fmt
import production as PROD
import sandbox_build as SB
import sandbox_track as T

FAILS = []
ROOT = os.path.dirname(os.path.abspath(__file__))


def ok(cond, msg):
    if cond:
        print(f"  ok   {msg}")
    else:
        print(f"  FAIL {msg}")
        FAILS.append(msg)


def eq(a, b, msg):
    ok(a == b, f"{msg} (got {a!r}, want {b!r})")


def same_cells(a, b, msg):
    """Cell inner HTML, compared without dumping every cell into the log."""
    if a == b:
        ok(True, msg)
        return
    n = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), None)
    ok(False, f"{msg} (first difference at cell {n}; {len(a)} cells vs {len(b)})")


def _labels(row):
    """data-l of each <td> in one row, in order."""
    out = []
    for m in re.finditer(r"<td\b([^>]*)>", row):
        lab = re.search(r'data-l="([^"]*)"', m.group(1))
        out.append(lab.group(1) if lab else None)
    return out


def _data_rows(table):
    return [r for r in re.findall(r"<tr\b[^>]*>.*?</tr>", table, re.S) if "<td" in r]


def _cell_inners(html):
    return re.findall(r"<td\b[^>]*>(.*?)</td>", html, re.S)


def _row_with(html, needle):
    for row in re.findall(r"<tr\b[^>]*>.*?</tr>", html, re.S):
        if needle in row:
            return row
    return ""


# The pairs table production.py actually writes: two header rows, rowspan on the
# corners, colspan on the two group titles. Copied from that builder so a change
# to the header shape is what this test runs, not a hand-simplified stand-in.
_PROD_SRC = open(os.path.join(ROOT, "production.py"), encoding="utf-8").read()
_PROD_HEAD = re.search(
    r'<tr><th rowspan="2">Pair</th>.*?</tr>\s*'
    r'<tr><th class="num">Bets</th>.*?</tr>',
    _PROD_SRC, re.S)

# Numbers are fixed here on purpose. Labeling may rename a cell; it must not
# rewrite what the cell says.
_PROD_ROW = (
    "<tr>"
    "<td><b>OLBG community tips</b><div class=\"sm mut\">Boxing</div></td>"
    "<td class=\"num\">8<div class=\"sm mut\">settled</div></td>"
    "<td class=\"num\"><span class=\"pos\">+16.3%</span><div class=\"sm mut\">after fees</div></td>"
    "<td class=\"num\">-8.0\u00a2<div class=\"sm mut\">v the close</div></td>"
    "<td class=\"num\">4\u20130<div class=\"sm mut\">4 settled</div></td>"
    "<td class=\"num\"><span class=\"mut\">+11.1%</span><div class=\"sm mut\">too early</div></td>"
    "<td class=\"num\"><b>0</b></td>"
    "</tr>"
)
_WANT = ["Pair", "Bets", "ROI", "CLV", "Record", "ROI", "Leads to come"]


print("\nproduction phone labels")

ok(_PROD_HEAD is not None, "production.py still builds the two-row pairs header")
_raw = f"<div class=\"tbl\"><table>\n{_PROD_HEAD.group(0) if _PROD_HEAD else ''}\n{_PROD_ROW}</table></div>"
_lab = SB.label_cells(_raw)
_rows = _data_rows(_lab)
eq(len(_rows), 1, "the fixture has one data row")
_got = _labels(_rows[0]) if _rows else []
eq(_got, _WANT, "each cell is named for its own column, rowspan and colspan included")
_clv = [lab for lab, inner in zip(_got, _cell_inners(_lab)) if "-8.0\u00a2" in inner]
eq(_clv, ["CLV"], "the CLV cell's data-l is CLV")
_thead = re.search(r"<thead>(.*)</thead>", _lab, re.S)
_tbody = re.search(r"<tbody>(.*)</tbody>", _lab, re.S)
ok(_thead is not None and _thead.group(1).count("<tr") == 2 and "CLV" in _thead.group(1),
   "both header rows are in thead, including the CLV sub-header")
ok(_tbody is not None and "<th" not in _tbody.group(1),
   "the second header row is not left in the body")
same_cells(_cell_inners(_raw), _cell_inners(_lab),
           "labeling a production-shaped table does not change any cell's rendered text")
ok("-8.0\u00a2" in "".join(_cell_inners(_lab)) and "+16.3%" in "".join(_cell_inners(_lab))
   and "<b>0</b>" in "".join(_cell_inners(_lab)),
   "the fixture's CLV, ROI and leads figures are still the same text")

# A different two-row shape, so the mapping is not special-cased to Production.
_other = SB.label_cells(
    "<table><tr><th rowspan=\"2\">Name</th><th colspan=\"2\">Group</th></tr>"
    "<tr><th>Left</th><th>Right</th></tr>"
    "<tr><td>n</td><td>1</td><td>2</td></tr></table>")
_other_rows = _data_rows(_other)
eq(_labels(_other_rows[0]) if _other_rows else [], ["Name", "Left", "Right"],
   "a group header does not steal the label of the cells under it")
ok('data-l="Group"' not in _other, "the group title is not a cell label")

# A colspan in the body occupies that many columns, so the next cell keeps its own.
_span = SB.label_cells(
    "<table><tr><th>A</th><th>B</th><th>C</th></tr>"
    "<tr><td colspan=\"2\">ab</td><td>c</td></tr></table>")
_span_rows = _data_rows(_span)
eq(_labels(_span_rows[0]) if _span_rows else [], ["A", "C"],
   "a body colspan does not shift the following cell onto the wrong header")

# The real Production page, from the ledger, labeled the same way the build does.
print("\nproduction.html from the ledger")

_now = datetime(2026, 9, 27, 13, 59, tzinfo=timezone.utc)
_page = PROD.page(T.load(), T.load_stages(), PROD.load_feed(), "<style></style>", now=_now)
_built = SB.label_cells(_page)
_pairs = ""
for _m in re.finditer(r"<table>(.*?)</table>", _built, re.S):
    if 'rowspan="2"' in _m.group(1):
        _pairs = _m.group(0)
        break
ok(_pairs, "the built production page has the two-row pairs table")
_pair_rows = _data_rows(_pairs)
ok(len(_pair_rows) >= 1, "at least one Production pair is on the page")
for _i, _row in enumerate(_pair_rows):
    eq(_labels(_row), _WANT, f"production pair {_i} cells carry their own column names")
same_cells(_cell_inners(_page), _cell_inners(_built),
           "labeling the rendered production page does not change any cell's text")


print("\nsafe hrefs")


def _quote(url, label, price, start, **extra):
    q = dict(status="open", bet=True, sport="boxing", start=start, date="2026-09-27",
             pick="a", side_a="Alpha", side_b="Beta", source="olbg", venue="other",
             market_id="plain", url=url, label=label, price=price, edge=None)
    q.update(extra)
    return q


_quotes = [
    _quote("javascript:alert(1)", "JS contest", 0.41, "2026-09-27T18:00:00Z"),
    _quote(" JaVaScRiPt:alert(1)", "Case contest", 0.42, "2026-09-27T19:00:00Z"),
    _quote("data:text/html,hi", "Data contest", 0.43, "2026-09-27T20:00:00Z"),
    _quote("https://polymarket.us/event/ok", "HTTPS contest", 0.55, "2026-09-27T21:00:00Z"),
    _quote("https://example.com/?q=1&b=2", "A & B <x>", 0.56, "2026-09-27T22:00:00Z"),
    _quote("  HtTpS://example.com/x  ", "Trim contest", 0.57, "2026-09-27T23:00:00Z"),
    _quote("javascript:alert(1)", "Kalshi contest", 0.58, "2026-09-28T00:00:00Z",
           venue="kalshi", market_id="KXMLBGAME-26SEP27ABCD"),
    _quote("java\tscript:alert(1)", "Tab contest", 0.61, "2026-09-28T01:00:00Z"),
    _quote("java\nscript:", "Newline contest", 0.62, "2026-09-28T02:00:00Z"),
    _quote("&#106;avascript:alert(1)", "Entity contest", 0.63, "2026-09-28T03:00:00Z"),
    _quote("javascript&colon;", "Ampersand contest", 0.64, "2026-09-28T04:00:00Z"),
    _quote("//evil.example", "Relative contest", 0.65, "2026-09-28T05:00:00Z"),
    _quote('https://x.example/" onmouseover="alert(1)', "Breakout contest", 0.66,
           "2026-09-28T06:00:00Z"),
    _quote("http\u017f://evil.example", "Long s contest", 0.67, "2026-09-28T07:00:00Z"),
]
_links = SB.open_rows({"quotes": _quotes})[0]
ok("javascript:" not in _links.lower(),
   "a javascript url is not written into the page")
for _name, _price in (("JS contest", "0.41"), ("Case contest", "0.42"), ("Data contest", "0.43")):
    _row = _row_with(_links, _name)
    _shown = fmt.cents(float(_price))
    ok(_row and "href=" not in _row, f"{_name} is text, with no href")
    ok(_shown in _row, f"{_name} still shows its price {_price}")
ok("data:" not in _row_with(_links, "Data contest"), "a data: url is not an href")
_https = _row_with(_links, "HTTPS contest")
ok('href="https://polymarket.us/event/ok"' in _https
   and 'rel="noopener noreferrer"' in _https and 'target="_blank"' in _https,
   "an https url is an external link")
ok(fmt.cents(0.55) in _https, "the https row's price is unchanged")
_esc = _row_with(_links, "A &amp; B &lt;x&gt;")
ok('href="https://example.com/?q=1&amp;b=2"' in _esc,
   "the link text and the url are still escaped")
_trim = _row_with(_links, "Trim contest")
ok('href="HtTpS://example.com/x"' in _trim and 'rel="noopener noreferrer"' in _trim,
   "scheme check is case-insensitive and ignores surrounding whitespace")
_kalshi = _row_with(_links, "Kalshi contest")
ok('href="https://kalshi.com/markets/kxmlbgame#kxmlbgame-26sep27abcd"' in _kalshi
   and "javascript:" not in _kalshi.lower() and 'rel="noopener noreferrer"' in _kalshi,
   "a Kalshi row still links the derived https page, not a stored javascript url")
# The prices above are the fixture. None of them moved when the link was dropped.
for _price in ("0.41", "0.42", "0.43", "0.55", "0.56", "0.57", "0.58"):
    _shown = fmt.cents(float(_price))
    ok(f">{_shown}<" in _links or f">{_shown}</td>" in _links,
       f"rendered price {_price} is unchanged")

# open_rows prints the price in cents inside the cell. Pin the exact cell.
ok(fmt.cents(0.41) in _row_with(_links, "JS contest") and fmt.cents(0.58) in _kalshi,
   "dropping an unsafe href does not change the numeric cells")

for _name, _price in (("Tab contest", "0.61"), ("Newline contest", "0.62"),
                      ("Entity contest", "0.63"), ("Ampersand contest", "0.64"),
                      ("Relative contest", "0.65"), ("Long s contest", "0.67")):
    _row = _row_with(_links, _name)
    ok(_row and "href=" not in _row, f"{_name} is text, with no href")
    ok(fmt.cents(float(_price)) in _row, f"{_name} still shows its price {_price}")
ok("evil.example" not in _row_with(_links, "Relative contest"),
   "a scheme-relative url is not written out")
ok("&#" not in _row_with(_links, "Entity contest") and "javascript" not in _row_with(_links, "Entity contest").lower(),
   "an entity-encoded javascript scheme is not a link and is not decoded into one")
ok("&colon" not in _row_with(_links, "Ampersand contest"),
   "javascript&colon; is not a link")
ok("\t" not in _row_with(_links, "Tab contest") and "alert" not in _row_with(_links, "Tab contest"),
   "a tab inside javascript: is not an href")
ok("script" not in _row_with(_links, "Newline contest"),
   "a newline inside javascript: is not an href")
ok("\u017f" not in _row_with(_links, "Long s contest"),
   "a long s does not make httpſ:// an http link")
_break = _row_with(_links, "Breakout contest")
ok('href="https://x.example/&quot; onmouseover=&quot;alert(1)"' in _break
   and 'rel="noopener noreferrer"' in _break,
   "a quote in an https url stays escaped inside the href")
ok(' onmouseover="' not in _break and _break.count("href=") == 1,
   "that quote does not open a new attribute")
ok(fmt.cents(0.66) in _break, "the breakout row's price is unchanged")

print(f"\n{'FAILED: ' + str(len(FAILS)) if FAILS else 'all presentation tests passed'}")
for _f in FAILS:
    print("   -", _f)
sys.exit(1 if FAILS else 0)
