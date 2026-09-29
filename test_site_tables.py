#!/usr/bin/env python3
"""Presentation checks for sortable tables, the settled archive, and page CSP.

These fail on main before this change: numeric cells have no data-v, every
settled bet is inlined on sandbox.html, and the pages have no Content-Security-Policy.
They do not grade, settle, or rewrite a ledger.
"""
import datetime
import html as html_lib
import os
import re
import shutil
import subprocess
import sys
from datetime import timezone

import fmt
import production
import sandbox_build as SB
import sandbox_track as T
import site_root

FAILS = []
ROOT = os.path.dirname(os.path.abspath(__file__))
# Noon CDT on 27 Sep 2026. The last 7 Chicago dates are 21 Sep through 27 Sep.
NOW = datetime.datetime(2026, 9, 27, 17, 0, tzinfo=timezone.utc)
# The labeled sandbox page was about 1.63MB with every settled bet inlined.
# Weekly archive pages take the older rows off it. 1.4MB still fails that page.
SANDBOX_BUDGET = 1_400_000
CSP = (
    '<meta http-equiv="Content-Security-Policy" content="default-src \'self\'; '
    'script-src \'self\'; style-src \'self\'; img-src \'self\' data:; '
    'base-uri \'none\'; form-action \'none\'">'
)
REFERRER = '<meta name="referrer" content="no-referrer">'
HIST = ("won", "lost", "void", "settled")
_ASSET = re.compile(
    r"<(script|link)\b([^>]*)>",
    re.I,
)
_SRC = re.compile(r"""(?:src|href)\s*=\s*["']([^"']+)["']""", re.I)
_REL = re.compile(r"""rel\s*=\s*["']([^"']+)["']""", re.I)


def ok(cond, why):
    print(f"  {'ok  ' if cond else 'FAIL'} {why}")
    if not cond:
        FAILS.append(why)


def eq(got, want, why):
    ok(got == want, why if got == want else f"{why} — got {got!r}, want {want!r}")


def ids_eq(got, want, why):
    if sorted(got) == sorted(want):
        ok(True, why)
        return
    extra = sorted(set(got) - set(want))[:3]
    missing = sorted(set(want) - set(got))[:3]
    ok(False, f"{why} — got {len(got)} rows, want {len(want)}; "
       f"extra {extra}; missing {missing}")


def _section(page, sid):
    m = re.search(rf'<section id="{sid}"[^>]*>(.*?)(?=<section |<footer)', page, re.S)
    return m.group(1) if m else ""


def _ids(fragment):
    return [html_lib.unescape(i) for i in re.findall(r'data-id="([^"]*)"', fragment)]


def _displayed_number(inner):
    """The first number a reader sees, or None when the cell is not a figure."""
    text = re.sub(r"<[^>]+>", " ", inner)
    text = html_lib.unescape(text).replace("\u2212", "-").replace("−", "-")
    text = text.replace(",", "").replace("$", "").strip()
    if not text or text in ("—", "-", "pick"):
        return None
    m = re.search(r"([+-]?\d+(?:\.\d+)?)\s*[¢%]?", text)
    if not m:
        return None
    if not re.search(r"\d", text):
        return None
    return float(m.group(1))


def _sortable_tables(page):
    return re.findall(r"<table\b[^>]*\bclass=\"[^\"]*\bsortable\b[^\"]*\"[^>]*>.*?</table>", page, re.S)


def _num_columns(table):
    head = re.search(r"<thead>(.*?)</thead>", table, re.S)
    header = head.group(1) if head else table
    cols = []
    for i, th in enumerate(re.findall(r"<th\b([^>]*)>", header)):
        cols.append("num" in th.split(">", 1)[0] if False else ("num" in th))
    # The regex above captured only the attribute string.
    return [i for i, attrs in enumerate(re.findall(r"<th\b([^>]*)>", header)) if "num" in attrs]


def _rows(table):
    body = re.search(r"<tbody>(.*)</tbody>", table, re.S)
    chunk = body.group(1) if body else table
    return [r for r in re.findall(r"<tr\b[^>]*>.*?</tr>", chunk, re.S) if "<td" in r]


def _external(url):
    return url.startswith("http://") or url.startswith("https://") or url.startswith("//")


def _asset_urls(page):
    """src/href of scripts, stylesheets, and fonts. Ordinary links are not assets."""
    found = []
    for tag, attrs in _ASSET.findall(page):
        src = _SRC.search(attrs)
        if not src:
            continue
        rel = _REL.search(attrs)
        kind = tag.lower()
        rel_text = rel.group(1).lower() if rel else ""
        if kind == "script" or "stylesheet" in rel_text or "font" in rel_text:
            found.append(src.group(1))
    return found


def _ledger_settled(now):
    d = T.load()
    today = fmt.chicago(now).date()
    recent, older = [], []
    for q in d["quotes"]:
        if not q.get("bet") or q.get("status") not in HIST or T.climate_excluded(q):
            continue
        try:
            day = fmt.chicago(q.get("settled")).date()
        except (TypeError, ValueError, OverflowError, OSError):
            day = None
        if day is not None and 0 <= (today - day).days < 7:
            recent.append(q["id"])
        else:
            older.append(q["id"])
    return recent, older


print("\ntest_sortable_numeric_cells_have_data_v")


def _check_data_v(name, page):
    tables = _sortable_tables(page)
    ok(bool(tables), f"{name} has a sortable table")
    checked = 0
    missing = 0
    bad = []
    for table in tables:
        cols = set(_num_columns(table))
        for row in _rows(table):
            cells = re.findall(r"<td\b([^>]*)>(.*?)</td>", row, re.S)
            for i, (attrs, inner) in enumerate(cells):
                if i not in cols:
                    continue
                shown = _displayed_number(inner)
                if shown is None:
                    continue
                checked += 1
                m = re.search(r'data-v="([^"]*)"', attrs)
                if not m:
                    missing += 1
                    if len(bad) < 3:
                        bad.append(f"missing data-v on {re.sub(r'<[^>]+>', '', inner)[:40]!r}")
                    continue
                raw = html_lib.unescape(m.group(1))
                if re.fullmatch(r"[+-]?(?:\d+\.?\d*|\.\d+)", raw) is None:
                    missing += 1
                    if len(bad) < 3:
                        bad.append(f"data-v {raw!r} is not numeric")
                    continue
                if abs(float(raw) - shown) >= 1e-9:
                    missing += 1
                    if len(bad) < 3:
                        bad.append(f"data-v {raw} != displayed {shown}")
    ok(checked > 0 and missing == 0,
       f"{name}: {checked} sortable numeric cells, each data-v matches the displayed value"
       + (f" ({missing} bad; {bad})" if missing else ""))
    return checked


try:
    _sandbox = SB.label_cells(SB.build(now=NOW))
except TypeError:
    ok(False, "build(now=) is required")
    _sandbox = SB.label_cells(SB.build())
_check_data_v("sandbox.html", _sandbox)

_quote = '5" onmouseover="alert(1)'
_cell = SB._td_num("x", _quote) if hasattr(SB, "_td_num") else ""
ok('data-v="5&quot; onmouseover=&quot;alert(1)"' in _cell,
   "data-v is escaped so a quote cannot open an attribute")
ok(' onmouseover="' not in _cell, "the escaped data-v does not become a handler")


print("\ntest_settled_rows_partitioned_across_archive")

_want_recent, _want_older = _ledger_settled(NOW)
_got_recent = _ids(_section(_sandbox, "recently-settled"))
_archive = {}
if hasattr(SB, "archive_documents"):
    _archive = {name: SB.label_cells(page) for name, page in SB.archive_documents(now=NOW).items()}
else:
    ok(False, "archive_documents builds the weekly pages")
_week_pages = {name: page for name, page in _archive.items() if name != "archive/index.html"}
_got_older = []
for _name, _page in sorted(_week_pages.items()):
    _got_older.extend(_ids(_page))
_index = _archive.get("archive/index.html", "")
ok("archive/index.html" in _archive, "the archive index page is built")
ok(not _ids(_index), "the archive index lists weeks and does not repeat bet rows")
ids_eq(_got_recent, _want_recent,
       "sandbox.html recently settled is only the last 7 Chicago days")
eq(len(_got_recent), len(set(_got_recent)), "the main page has no duplicate settled row")
eq(len(_got_older), len(set(_got_older)), "the archive pages have no duplicate settled row")
eq(len(set(_got_recent) & set(_got_older)), 0, "no settled row is on both the main page and an archive page")
ids_eq(_got_recent + _got_older, _want_recent + _want_older,
       "sandbox.html plus the archive pages equals the ledger settled count")
ok(len(_want_recent) + len(_want_older) == len(_got_recent) + len(_got_older),
   f"settled rows {_got_recent and len(_got_recent)}+{len(_got_older)} "
   f"vs ledger {len(_want_recent)}+{len(_want_older)}")

# A Chicago midnight on the edge of the window. 2026-09-21T04:30Z is still
# 20 Sep in Chicago; 05:30Z is 21 Sep, the first day of a 27 Sep window.
_edge_now = datetime.datetime(2026, 9, 28, 3, 30, tzinfo=timezone.utc)


def _q(qid, settled):
    return {"id": qid, "bet": True, "status": "won", "settled": settled, "pnl": 1, "price": 0.5,
            "sport": "mlb", "source": "x", "pick": "a", "side_a": "A", "side_b": "B", "date": "2026-09-20"}


if hasattr(SB, "partition_settled"):
    _recent, _older = SB.partition_settled(
        {"quotes": [_q("early", "2026-09-21T04:30:00Z"), _q("on-time", "2026-09-21T05:30:00Z")]},
        _edge_now)
    eq(sorted(q["id"] for q in _recent), ["on-time"],
       "a bet that settles at Chicago midnight of day 7 stays on the main page")
    eq(sorted(q["id"] for q in _older), ["early"],
       "a bet one hour earlier, still the previous Chicago date, is archived")
else:
    ok(False, "partition_settled splits on the Chicago date of the build time")


print("\ntest_published_pages_csp_and_no_inline")


def _check_policy(name, page):
    ok(CSP in page, f"{name} has the Content-Security-Policy meta")
    ok(REFERRER in page, f"{name} has the referrer meta")
    ok("<style" not in page.lower(), f"{name} has no style block")
    ok(not re.search(r"\sstyle\s*=", page, re.I), f"{name} has no style attribute")
    inline = False
    for m in re.finditer(r"<script\b([^>]*)>(.*?)</script>", page, re.I | re.S):
        if m.group(2).strip():
            inline = True
    ok(not inline, f"{name} has no inline script")
    bad = [url for url in _asset_urls(page) if _external(url)]
    ok(not bad, f"{name} has no external script, style, or font URL" + (f" ({bad})" if bad else ""))
    ok("fonts.googleapis.com" not in page and "fonts.gstatic.com" not in page,
       f"{name} does not reference Google Fonts")


_pages = [("sandbox.html", _sandbox)]
_pages.append(("production.html", production.page(
    {"quotes": []}, {"pairs": {}}, {"leads": {}, "pairs": {}}, "", now=NOW)))
_pages.append(("trading.html", SB.trading_page(NOW)))
_pages.append(("index.html", site_root.root_stub(NOW)))
for _name, _page in sorted(_archive.items()):
    _pages.append((_name, _page))
ok(any(name.startswith("archive/") and name.endswith(".html") for name, _p in _pages),
   "at least one archive page is published")
for _name, _page in _pages:
    _check_policy(_name, _page)
_weeks = [page for name, page in _pages if re.search(r"archive/20\d\d-W\d\d\.html", name)]
if _weeks:
    _check_data_v("archive week", _weeks[0])
else:
    ok(False, "archive week has a sortable table")


print("\ntest_sandbox_html_size_budget")

_size = len(_sandbox.encode())
ok(_size < SANDBOX_BUDGET,
   f"sandbox.html is {_size} bytes, under the {SANDBOX_BUDGET} byte budget")


print("\ntest_tables_js_sort_and_filter")

_node = shutil.which("node")
if not _node:
    print("  skipped: node is not installed")
else:
    _run = subprocess.run([_node, os.path.join(ROOT, "test_tables.js")],
                          cwd=ROOT, capture_output=True, text=True)
    ok(_run.returncode == 0,
       "node test_tables.js sorts −$100 below +$6 and filters text"
       + ("" if _run.returncode == 0 else "\n" + _run.stdout + _run.stderr))
    if _run.returncode == 0:
        print("  " + _run.stdout.strip())


print("\ntest_tstat_zero_and_minus")

if not hasattr(fmt, "tstat"):
    ok(False, "t-stat formatting goes through fmt.tstat")
    ok(False, "a zero t-stat is 't 0.00'")
    ok(False, "a negative t-stat uses U+2212")
else:
    eq(fmt.tstat(0), "t 0.00", "a zero t-stat is 't 0.00'")
    eq(fmt.tstat(0.001), "t 0.00", "a t-stat that rounds to zero has no plus")
    eq(fmt.tstat(-0.001), "t 0.00", "a negative t-stat that rounds to zero has no minus")
    eq(fmt.tstat(-1.2), "t \u22121.20", "a negative t-stat uses U+2212")
    eq(fmt.tstat(1.2), "t +1.20", "a positive t-stat keeps the plus")
    ok(True, "t-stat formatting goes through fmt.tstat")
_zero = SB.close_cell({"clv": 0.01, "clv_n": 3, "clv_t": 0.0, "clv_read": "level"})
ok("t 0.00" in _zero and "t +0.00" not in _zero and "t -0.00" not in _zero,
   "close_cell prints t 0.00 rather than t +0.00")
_neg = SB.close_cell({"clv": -0.08, "clv_n": 3, "clv_t": -1.25, "clv_read": "behind"})
ok("t \u22121.25" in _neg and "t -1.25" not in _neg,
   "close_cell prints the t-stat minus as U+2212")


print("\ntest_colour_follows_displayed_value")

if not hasattr(fmt, "tone"):
    ok(False, "colour follows the displayed value through fmt.tone")
    ok(False, "-0.04% shown as 0.0% is neutral")
    ok(False, "a percent that still shows a minus stays negative")
else:
    eq(fmt.tone(-0.0004, spec=".1f", scale=100), "mut",
       "-0.04% shown as 0.0% is neutral")
    eq(fmt.tone(-0.0015, spec=".1f", scale=100), "neg",
       "a percent that still shows a minus stays negative")
    eq(fmt.tone(0.163, spec=".1f", scale=100), "pos",
       "a positive percent stays positive")
    eq(fmt.tone(-0.4, spec=",.0f", scale=1), "mut",
       "−$0.40 shown as $0 is neutral")
if not hasattr(SB, "_pct_span"):
    ok(False, "the percent span for -0.0004 is mut 0.0%")
else:
    eq(SB._pct_span(-0.0004, digits=1), '<span class="mut">0.0%</span>',
       "the percent span for -0.0004 is mut 0.0%")
_edge_html, _n = SB.open_rows({"quotes": [{
    "id": "colour", "status": "open", "bet": True, "sport": "mlb",
    "start": "2026-09-27T23:00:00+00:00", "pick": "a", "side_a": "Home", "side_b": "Away",
    "date": "2026-09-27", "price": 0.5, "edge": -0.0004, "source": next(iter(
        __import__("sandbox_sources").SOURCES)), "label": "Home v Away",
    "venue": "kalshi", "market_id": "COLOUR", "url": "https://example.com/c",
}]})
_edge_cell = ""
for _td in re.findall(r"<td\b[^>]*>.*?</td>", _edge_html, re.S):
    if "0.0%" in _td:
        _edge_cell = _td
        break
ok(_edge_cell and "pos" not in _edge_cell and "neg" not in _edge_cell,
   "an edge shown as 0.0% is not painted positive or negative")
if not hasattr(production, "_tone"):
    ok(False, "production colours a 0.0% display as neutral")
else:
    eq(production._tone(-0.0004, 5, digits=1), "mut",
       "production colours a 0.0% display as neutral")
    eq(production._tone(-0.0015, 5, digits=1), "neg",
       "production keeps neg when the percent still shows a minus")
    eq(production._tone(-0.0015, 0, digits=1), "mut",
       "production still greys a percent when there is no sample")


print("\ntest_malformed_kickoff_placeholder")

_bad_now = datetime.datetime(2026, 9, 27, 18, 0, tzinfo=timezone.utc)
_overflow = {
    "status": "hit", "kickoff": "0001-01-01T00:00:00Z", "pair": "demo|soccer",
    "league": "Fixture", "match": "Overflow FC v Range", "headline": "Home to win",
    "price_at_log": 0.5,
}
_malformed = {
    "status": "pending", "kickoff": "not-a-date", "pair": "demo|soccer",
    "league": "Fixture", "match": "Bad Stamp v Placeholder", "headline": "Home to win",
    "price_at_log": 0.4,
}
_raised = None
try:
    _prod = production.page(
        {"quotes": []}, {"pairs": {}},
        {"leads": {"0": _overflow, "1": _malformed}, "pairs": {}},
        "", now=_bad_now)
except (OverflowError, ValueError, OSError) as exc:
    _raised = exc
    _prod = ""
ok(_raised is None, "a malformed kickoff does not crash the production page"
   + (f" ({type(_raised).__name__}: {_raised})" if _raised else ""))
ok("Overflow FC v Range" in _prod, "the out-of-range kickoff row is still on the page")
ok("Bad Stamp v Placeholder" in _prod, "the unparseable kickoff row is still on the page")
_overflow_row = ""
for _row in re.findall(r"<tr\b[^>]*>.*?</tr>", _prod, re.S):
    if "Overflow FC v Range" in _row:
        _overflow_row = _row
        break
_ph = getattr(production, "PLACEHOLDER_DATE", None)
ok(_ph is not None, "production has a placeholder date for a bad kickoff")
ok(_overflow_row and _ph is not None and ">" + _ph + "<" in _overflow_row,
   "the out-of-range kickoff shows a placeholder date")
_bad_row = ""
for _row in re.findall(r"<tr\b[^>]*>.*?</tr>", _prod, re.S):
    if "Bad Stamp v Placeholder" in _row:
        _bad_row = _row
        break
ok(_bad_row and _ph is not None and _ph in _bad_row,
   "the unparseable kickoff shows a placeholder date")
_feed_raised = None
try:
    production.build_feed(
        {"quotes": [{
            "id": "bad-start", "source": "src", "sport": "soccer", "bet": True,
            "status": "open", "start": "0001-01-01T00:00:00Z",
        }]},
        {"pairs": {"src|soccer": {
            "stage": "production", "ready_at": "2020-01-01T00:00:00+00:00",
        }}},
        now=_bad_now)
except (OverflowError, ValueError, OSError) as exc:
    _feed_raised = exc
ok(_feed_raised is None, "build_feed does not crash on an out-of-range kickoff"
   + (f" ({type(_feed_raised).__name__}: {_feed_raised})" if _feed_raised else ""))


print("\ntest_running_rows_match_header_and_keep_sport")

_run = _section(_sandbox, "running")
_run_tables = _sortable_tables(_run)
ok(len(_run_tables) == 1, "sandbox.html has one Running table")
if _run_tables:
    _head_n = len(re.findall(r"<th\b", _run_tables[0]))
    _sports = {q["id"]: (q.get("sport") or "") for q in T.load()["quotes"]
               if q.get("bet") and q.get("status") == "open" and not T.climate_excluded(q)}
    _checked = 0
    for _row in _rows(_run_tables[0]):
        _cells = re.findall(r"<td\b([^>]*)>(.*?)</td>", _row, re.S)
        if len(_cells) != _head_n:
            ok(False, f"a Running row has {len(_cells)} cells, the header has {_head_n}")
            break
        _qid = html_lib.unescape(re.search(r'data-id="([^"]*)"', _row).group(1))
        _sport_cell = next((inner for attrs, inner in _cells if 'data-l="Sport"' in attrs), "")
        _sport_text = re.sub(r"<[^>]+>", "", html_lib.unescape(_sport_cell)).strip()
        if _sports.get(_qid) and not _sport_text:
            ok(False, f"Running row {_qid} has a ledger sport and an empty Sport cell")
            break
        _checked += 1
    else:
        ok(_checked > 0 and _checked == len(_sports),
           f"all {_checked} Running rows match the header, and Sport is filled when the ledger has one")

_css = open(os.path.join(ROOT, "public_site", "site.css"), encoding="utf-8").read()
_narrow = _css.split("@media (max-width: 640px)", 1)[-1]
ok('td[data-l="Source"]' in _narrow and "display: table-cell" in _narrow and "text-align: left" in _narrow,
   "under 640px the card rules do not leave Sport or Source as a right-aligned block")
ok(_narrow.count("vertical-align: top") >= 2,
   "under 640px every cell uses the same vertical alignment")


print("\ntest_climate_excluded_rows_stay_off_the_pages")


def _record_settled(quotes):
    """Settled-on-record count: settled bets that honour the city-day flag, voids aside."""
    n_hist = sum(1 for q in quotes if q.get("bet") and q.get("status") in HIST
                 and not T.climate_excluded(q))
    n_void = sum(1 for q in quotes if q.get("status") == "void" and q.get("bet"))
    return n_hist - n_void


def _shown_settled(page):
    m = re.search(
        r"([\d,]+)(?: · [\d,]+ void)?(?: · [\d,]+ city-day repeats?)? settled on the record",
        page)
    return int(m.group(1).replace(",", "")) if m else None


def _flagged(qid, status, **extra):
    row = {
        "id": qid, "bet": True, "status": status, "excluded": T.CLIMATE_EXCLUDED,
        "sport": "climate", "source": "nws", "pick": "a", "side_a": "City Repeat",
        "side_b": "Other", "price": 0.4, "pnl": 50.0, "label": "City Repeat fixture",
        "date": "2026-09-10", "venue": "kalshi", "market_id": qid,
    }
    row.update(extra)
    return row


_ledger = T.load()
_flag_ids = ("fixture-cityday-open", "fixture-cityday-recent", "fixture-cityday-old")
_fx_quotes = list(_ledger["quotes"]) + [
    _flagged("fixture-cityday-open", "open", start="2026-09-28T18:00:00Z", pnl=None),
    _flagged("fixture-cityday-recent", "won", settled="2026-09-26T18:00:00Z",
             start="2026-09-26T17:00:00Z"),
    _flagged("fixture-cityday-old", "won", settled="2026-09-10T18:00:00Z",
             start="2026-09-10T17:00:00Z"),
]
_fx = dict(_ledger, quotes=_fx_quotes)
_fx_st = T.load_stages()
_fx_page = SB.label_cells(SB.build(now=NOW, d=_fx, st=_fx_st))
_fx_archive = {name: SB.label_cells(page)
               for name, page in SB.archive_documents(now=NOW, d=_fx, st=_fx_st).items()}
_fx_running = _ids(_section(_fx_page, "running"))
_fx_recent = _ids(_section(_fx_page, "recently-settled"))
_fx_older = []
for _name, _page in _fx_archive.items():
    if _name != "archive/index.html":
        _fx_older.extend(_ids(_page))
for _fid in _flag_ids:
    ok(_fid not in _fx_running and _fid not in _fx_recent and _fid not in _fx_older,
       f"{_fid} is on none of Running, Recently settled, or an archive page")
_want_record = _record_settled(_fx_quotes)
_got_record = _shown_settled(_fx_page)
eq(_got_record, _want_record,
   "the settled-on-record count honours the city-day flag")
ok(re.search(r"· \d[\d,]* city-day repeats?", _section(_fx_page, "recently-settled")),
   "the city-day repeat label is shown beside the settled-on-record count")


if FAILS:
    print(f"\n{len(FAILS)} FAILED")
    sys.exit(1)
print("\nall passed")
