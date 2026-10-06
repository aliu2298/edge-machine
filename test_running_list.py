#!/usr/bin/env python3
"""SofaScore shell slice 2: the Running list, and the #69 follow-ups.

Fails while the root is still an empty pane, record_build stamps index.html
with its own clock, or the freshness notes still call that page a redirect stub.
Passes once one build writes a Production contest row per contest, the filters
count those rows, and the follow-ups hold. No network.
"""
import datetime
import html as html_lib
import os
import re
import shutil
import sys
import tempfile
import threading
from datetime import timedelta, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

FAILS = []
ROOT = os.path.dirname(os.path.abspath(__file__))
NOW = datetime.datetime(2026, 10, 5, 18, 0, tzinfo=timezone.utc)


def ok(cond, why):
    print(f"  {'ok  ' if cond else 'FAIL'} {why}")
    if not cond:
        FAILS.append(why)


def eq(got, want, why):
    ok(got == want, why if got == want else f"{why} — got {got!r}, want {want!r}")


def _lead(lid, home, away, kickoff, status, pair, sport, price, league="League"):
    return {
        "id": lid,
        "home": home,
        "away": away,
        "match": f"{home} v {away}",
        "headline": f"{home} to win",
        "kickoff": kickoff,
        "status": status,
        "pair": pair,
        "sport": sport,
        "lane": "production",
        "price_at_log": price,
        "league": league,
        "source": pair.split("|", 1)[0],
        "sandbox_quote": lid,
    }


def _blob(leads):
    return {"leads": {lead["id"]: lead for lead in leads}, "pairs": {}}


def _rows(page):
    return re.findall(r'<button\b[^>]*class="running-row"[^>]*>.*?</button>', page, re.S)


def _attr(tag, name):
    match = re.search(rf'\b{name}="([^"]*)"', tag)
    return html_lib.unescape(match.group(1)) if match else None


def _filter_count(page, key, label):
    match = re.search(
        rf'data-filter="{key}"[^>]*>{label} <span class="count">(\d+)</span>',
        page)
    return int(match.group(1)) if match else None


def _groups(page):
    return re.findall(
        r'<section class="running-group"[^>]*>\s*<h3>([^<]+)</h3>(.*?)</section>',
        page, re.S)


def _quote(qid, status, start, settled=None, price=0.54, source="oddspedia",
           home="QuoteHome", away="QuoteAway"):
    row = {
        "id": qid,
        "source": source,
        "sport": "cricket",
        "bet": True,
        "status": status,
        "pick": "a",
        "side_a": home,
        "side_b": away,
        "market_id": "m-" + qid,
        "venue": "polymarket_us",
        "start": start,
        "logged": "2026-10-01T00:00:00+00:00",
        "start_source": "espn",
        "price": price,
        "label": f"{home} v {away}",
    }
    if settled:
        row["settled"] = settled
    if status == "won":
        row["result"] = "a"
    if status == "lost":
        row["result"] = "b"
    if status == "settled":
        row["result"] = "price"
    return row


def _prod_st(*keys):
    return {"pairs": {
        key: {"stage": "production", "ready_at": "2026-09-01T00:00:00+00:00"}
        for key in keys
    }}


print("running rows")
import shell_build

LEADS = [
    _lead("alpha-a", "Alpha", "Beta", "2026-10-06T15:00:00Z", "pending",
          "oddspedia|cricket", "cricket", 0.54, "Big Bash"),
    _lead("alpha-b", "Alpha", "Beta", "2026-10-06T15:00:00Z", "pending",
          "team1|cricket", "cricket", 0.40, "Big Bash"),
    _lead("gamma", "Gamma", "Delta", "2026-10-07T15:00:00Z", "pending",
          "o15_ranked|soccer_o15_intl", "soccer_o15_intl", 0.61, "Nations League"),
    _lead("echo", "Echo", "Foxtrot", "2026-10-04T15:00:00Z", "hit",
          "oddspedia|cricket", "cricket", 0.48, "Big Bash"),
    _lead("inside", "Inside", "Edge", "2026-10-01T18:00:00Z", "miss",
          "oddspedia|cricket", "cricket", 0.33, "Big Bash"),
    _lead("old", "Old", "Gone", "2026-09-21T18:00:00Z", "hit",
          "oddspedia|cricket", "cricket", 0.70, "Big Bash"),
    _lead("live", "Live", "Now", "2026-10-05T12:00:00Z", "pending",
          "oddspedia|cricket", "cricket", 0.52, "Big Bash"),
    _lead("voided", "Void", "Match", "2026-10-03T18:00:00Z", "void",
          "oddspedia|cricket", "cricket", 0.50, "Big Bash"),
    _lead("priced", "Price", "Result", "2026-10-02T18:00:00Z", "price",
          "oddspedia|cricket", "cricket", 0.25, "Big Bash"),
    _lead("hostile", "<b>Beta", 'javascript:alert(1)', "2026-10-08T15:00:00Z", "pending",
          "oddspedia|cricket", "cricket", 0.54, 'League "x"'),
]
PAGE = shell_build.page(NOW, d={"quotes": []}, st={"pairs": {}}, blob=_blob(LEADS))
ROWS = _rows(PAGE)

eq(len(ROWS), 8, "one row per contest, with the contest outside the production window left out")
ok("Old v Gone" not in PAGE, "a contest outside the production settled window is left out")
ok(all("o15_ranked" not in row and "team1|cricket" not in row for row in ROWS),
   "rows do not print source ids")

by_name = {_attr(row, "data-name"): row for row in ROWS}


def _got(name):
    return by_name.get(name, "")


ok("Alpha v Beta" in by_name, "the two Alpha lanes collapse to one contest")
eq(sum(1 for row in ROWS if _attr(row, "data-name") == "Alpha v Beta"), 1,
   "the contest title is not repeated per lane")
ok("2 lanes" in _got("Alpha v Beta"), "a contest with two lanes shows the count")
ok("Gamma v Delta" in by_name and "2 lanes" not in _got("Gamma v Delta"),
   "a single lane does not show a count")
eq(_attr(_got("Alpha v Beta"), "data-price"), "54¢", "the row price is cents, 0.54 → 54¢")
ok("$" not in _got("Alpha v Beta") and "0.54" not in _got("Alpha v Beta"),
   "the row does not print a dollar price or the raw fraction")
eq(_attr(_got("Alpha v Beta"), "data-filter"), "upcoming", "a later kickoff is upcoming")
eq(_attr(_got("Live v Now"), "data-filter"), "live", "started and unsettled is live")
ok(">Live</span>" in _got("Live v Now"), "a live row's time says Live")
eq(_attr(_got("Echo v Foxtrot"), "data-filter"), "settled", "a hit inside the window is settled")
ok(">W</span>" in _got("Echo v Foxtrot"), "a hit renders as W")
ok(">L</span>" in _got("Inside v Edge"), "a miss renders as L")
ok(">Void</span>" in _got("Void v Match"), "a void renders as Void")
ok(">price result</span>" in _got("Price v Result"), "a price payout renders as price result")
ok(">Production</span>" in _got("Alpha v Beta"), "the lane pill says Production")
ok(">Sandbox</span>" not in PAGE, "Sandbox contests are not on the Production list")
ok("Tomorrow" in _got("Alpha v Beta"), "tomorrow's kickoff is a relative day")
ok("Yesterday" in _got("Echo v Foxtrot"), "yesterday's kickoff is a relative day")

groups = _groups(PAGE)
eq([name for name, _body in groups], ["Soccer", "Cricket"],
   "rows are grouped under sport labels, Soccer then Cricket")
soccer_body = dict(groups)["Soccer"]
cricket_body = dict(groups)["Cricket"]
ok("Gamma v Delta" in soccer_body and "Alpha v Beta" not in soccer_body,
   "a soccer contest sits under Soccer only")
ok("Alpha v Beta" in cricket_body and "Gamma v Delta" not in cricket_body,
   "a cricket contest sits under Cricket only")

for key, label in (("live", "Live"), ("settled", "Settled"), ("upcoming", "Upcoming")):
    shown = sum(1 for row in ROWS if _attr(row, "data-filter") == key)
    eq(_filter_count(PAGE, key, label), shown,
       f"the {label} count equals the rendered {label} rows")

ok("No live paper bets" in PAGE and "No settled paper bets" in PAGE
   and "No upcoming paper bets" in PAGE,
   "each filter has its empty-state copy")
ok("No live, settled, or upcoming paper bets." not in PAGE,
   "the combined empty line is gone")
ok("These filters do not change the list yet." not in PAGE,
   "the filters are no longer marked display-only")
ok('class="rule-mini"' not in PAGE, "there are still no rule cards")
ok("Select a contest in Running." in PAGE, "the detail pane starts empty")
ok('id="rules-line"' in PAGE, "the detail header is ready for the selected contest")
ok('href="javascript:' not in PAGE and 'href="data:' not in PAGE,
   "rendered text does not become a javascript or data link")
ok("<script>alert" not in PAGE and "&lt;b&gt;Beta" in PAGE,
   "contest text is escaped")
ok("javascript:alert(1)" in html_lib.unescape(PAGE)
   and 'href="javascript:alert(1)"' not in PAGE,
   "a javascript: string stays text")
ok('aria-disabled="true"' in PAGE and 'id="sports-soon"' in PAGE,
   "sport pills stay inert with Coming soon")

print("\nempty filter and quote window")
empty = shell_build.page(
    NOW, d={"quotes": []}, st={"pairs": {}}, blob={"leads": {}, "pairs": {}})
eq(_rows(empty), [], "an empty board has no contest rows")
for key, label in (("live", "Live"), ("settled", "Settled"), ("upcoming", "Upcoming")):
    eq(_filter_count(empty, key, label), 0, f"an empty board counts {label} as 0")
ok('id="running-empty"' in empty and "No live paper bets" in empty,
   "the empty live state keeps the Running chrome")
ok('id="running-title"' in empty and 'class="running-filters"' in empty,
   "the pane chrome stays when a filter is empty")

st = _prod_st("oddspedia|cricket")
_TILES = '<div class="tiles"><div class="tile"><b>1</b><span>pairs in Production</span></div></div>'
live_q = shell_build.page(NOW, d={"quotes": [
    _quote("live-q", "open", "2026-10-05T12:00:00+00:00"),
]}, st=st, blob={"leads": {}, "pairs": {}}, tiles=_TILES)
live_rows = _rows(live_q)
eq(len(live_rows), 1, "a started open Production bet is a live row even though the feed drops it")
eq(_attr(live_rows[0], "data-name"), "QuoteHome v QuoteAway", "the live row names the contest")
eq(_attr(live_rows[0], "data-filter"), "live", "that quote is in Live")
eq(_attr(live_rows[0], "data-price"), "54¢", "the live quote price is cents")

upcoming_q = shell_build.page(NOW, d={"quotes": [
    _quote("up-q", "open", "2026-10-08T15:00:00+00:00"),
]}, st=st, blob={"leads": {}, "pairs": {}}, tiles=_TILES)
eq(_rows(upcoming_q), [], "an upcoming quote stays off the list until the Production feed has it")

kept = shell_build.page(NOW, d={"quotes": [
    _quote("kept-q", "won", "2026-10-02T18:00:00+00:00",
           settled="2026-10-02T20:00:00+00:00", price=0.41),
]}, st=st, blob={"leads": {}, "pairs": {}}, tiles=_TILES)
kept_rows = _rows(kept)
eq(len(kept_rows), 1, "a settled quote inside the production window is a row")
ok(">W</span>" in kept_rows[0], "that settled quote renders as W")
eq(_attr(kept_rows[0], "data-price"), "41¢", "41% of a dollar is 41¢")

dropped = shell_build.page(NOW, d={"quotes": [
    _quote("drop-q", "won", "2026-09-21T18:00:00+00:00",
           settled="2026-09-28T18:00:00+00:00"),
]}, st=st, blob={"leads": {}, "pairs": {}}, tiles=_TILES)
eq(_rows(dropped), [], "a quote kicked off outside the production window is left out")
import production
saved_days = production.KEEP_SETTLED_DAYS
try:
    production.KEEP_SETTLED_DAYS = 1
    ok(not shell_build._in_window(NOW - timedelta(days=2), NOW),
       "shrinking production.KEEP_SETTLED_DAYS shrinks the shell window")
    ok(shell_build._in_window(NOW - timedelta(hours=1), NOW),
       "a kickoff inside the shrunk production window stays")
finally:
    production.KEEP_SETTLED_DAYS = saved_days
ok(shell_build._in_window(NOW - timedelta(days=production.KEEP_SETTLED_DAYS), NOW),
   "a kickoff exactly KEEP_SETTLED_DAYS ago stays, matching the feed")
ok(not shell_build._in_window(
    NOW - timedelta(days=production.KEEP_SETTLED_DAYS, seconds=1), NOW),
   "a kickoff just older than KEEP_SETTLED_DAYS drops, matching the feed")

sandbox_only = shell_build.page(NOW, d={"quotes": [
    _quote("sand-q", "open", "2026-10-05T12:00:00+00:00"),
]}, st={"pairs": {
    "oddspedia|cricket": {"stage": "sandbox", "since": "2026-09-01T00:00:00+00:00"},
}}, blob={"leads": {}, "pairs": {}}, tiles=_TILES)
eq(_rows(sandbox_only), [], "a Sandbox-stage contest is not listed on the Production shell")

print("\nsame clock as the page argument")
late = NOW + timedelta(hours=6)
between = _blob([
    _lead("soon", "Soon", "Later", "2026-10-05T21:00:00Z", "pending",
          "oddspedia|cricket", "cricket", 0.54),
])
early_page = shell_build.page(NOW, d={"quotes": []}, st={"pairs": {}}, blob=between)
late_page = shell_build.page(late, d={"quotes": []}, st={"pairs": {}}, blob=between)
early_rows = _rows(early_page)
late_rows = _rows(late_page)
eq(len(early_rows), 1, "the between-clock contest is still one row")
eq(_attr(early_rows[0], "data-filter"), "upcoming",
   "classification uses the build clock, not a later instant")
ok('<span class="running-time">Live</span>' not in early_rows[0],
   "that contest is not marked Live on the build clock")
eq(_attr(late_rows[0], "data-filter"), "live",
   "the same contest is live when the build clock is after kickoff")

print("\none pass, one clock, copied tiles")
import production
import sandbox_build
fixture_d = {"quotes": []}
fixture_st = {"pairs": {
    "oddspedia|cricket": {
        "stage": "production",
        "ready_at": "2026-09-27T00:00:00+00:00",
        "since": "2026-09-01T00:00:00+00:00",
        "by_hand": "2026-09-27",
    },
}}
fixture_blob = _blob([
    _lead("soon", "Alpha", "Beta", "2026-10-06T15:00:00Z", "pending",
          "oddspedia|cricket", "cricket", 0.61),
])
prod_html, index_html = sandbox_build.production_and_index(
    NOW, fixture_d, fixture_st, fixture_blob)
prod_tiles = shell_build.tiles_html(prod_html)
index_tiles = shell_build.tiles_html(index_html)
eq(index_tiles, prod_tiles, "the shared pass still copies Production tiles onto the shell")
prod_stamp = re.search(r'<time datetime="([^"]+)"', prod_html)
index_stamp = re.search(r'<p class="stamp">.*?<time datetime="([^"]+)"', index_html, re.S)
ok(prod_stamp and index_stamp and prod_stamp.group(1) == index_stamp.group(1),
   "the shared pass stamps index.html with production.html's clock")
ok('data-name="Alpha v Beta"' in index_html, "that same pass writes the Running row")


def _stamp(page):
    match = re.search(r'<p class="stamp">(.*?)</p>', page, re.S)
    return match.group(1) if match else ""


print("\ntracker build writes both pages from the first clock")
calls = {"n": 0}
base = datetime.datetime(2026, 10, 5, 18, 0, tzinfo=timezone.utc)
_RealDate = sandbox_build.datetime


class _Stepped(_RealDate):
    @classmethod
    def now(cls, tz=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return base
        return base + timedelta(hours=2)


saved = {
    "out": sandbox_build.OUT,
    "clock": sandbox_build.datetime,
    "render": sandbox_build.render_pages,
    "trade": sandbox_build.trading_page,
}
sandbox_build.datetime = _Stepped
sandbox_build.render_pages = lambda now=None, d=None, st=None: ("<html>sandbox</html>", "<html>arch</html>", {})
sandbox_build.trading_page = lambda now: "<html>trade</html>"
import cricket_build
import crypto_build
import soccer_build
import tennis_build
saved_builds = {
    "soccer": soccer_build.build,
    "tennis": tennis_build.build,
    "cricket": cricket_build.build,
    "crypto": crypto_build.build,
}
for mod in (soccer_build, tennis_build, cricket_build, crypto_build):
    mod.build = lambda *args, **kwargs: "<html></html>"
tmpdir = tempfile.mkdtemp(prefix="shell-main-")
sandbox_build.OUT = os.path.join(tmpdir, "sandbox.html")
try:
    sandbox_build.main()
    prod_path = os.path.join(tmpdir, "production.html")
    index_path = os.path.join(tmpdir, "index.html")
    ok(os.path.isfile(prod_path) and os.path.isfile(index_path),
       "the tracker build writes production.html and index.html")
    if os.path.isfile(prod_path) and os.path.isfile(index_path):
        prod_body = open(prod_path, encoding="utf-8").read()
        index_body = open(index_path, encoding="utf-8").read()
        prod_when = re.search(r'datetime="([^"]+)"', prod_body)
        index_when = re.search(r'datetime="([^"]+)"', _stamp(index_body))
        eq(None if index_when is None else index_when.group(1),
           None if prod_when is None else prod_when.group(1),
           "index.html does not carry a later clock than production.html")
        eq(None if prod_when is None else prod_when.group(1), "2026-10-05T18:00:00Z",
           "both pages use the tracker's first clock")
finally:
    sandbox_build.OUT = saved["out"]
    sandbox_build.datetime = saved["clock"]
    sandbox_build.render_pages = saved["render"]
    sandbox_build.trading_page = saved["trade"]
    soccer_build.build = saved_builds["soccer"]
    tennis_build.build = saved_builds["tennis"]
    cricket_build.build = saved_builds["cricket"]
    crypto_build.build = saved_builds["crypto"]
    shutil.rmtree(tmpdir, ignore_errors=True)


print("\ntakeover copies tiles and the production clock")
boom = {"n": 0}
real_page = production.page


def _boom(*args, **kwargs):
    boom["n"] += 1
    raise AssertionError("takeover recounted tiles")


take_dir = tempfile.mkdtemp(prefix="shell-take-")
take_prod = os.path.join(take_dir, "production.html")
take_index = os.path.join(take_dir, "index.html")
open(take_prod, "w", encoding="utf-8").write(
    '<time datetime="2026-10-01T12:00:00Z">Updated Oct 1, 7:00 AM CT</time>\n'
    '<div class="tiles"><div class="tile"><b>4</b><span>pairs in Production</span></div></div>\n')
open(take_index, "w", encoding="utf-8").write("old shell\n")
import site_root
saved_out = site_root.OUT
saved_site_dt = site_root.datetime


class _SiteClock:
    timezone = timezone

    class datetime(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return base + timedelta(hours=5)

        @staticmethod
        def strptime(text, pattern):
            return datetime.datetime.strptime(text, pattern)


site_root.OUT = take_index
site_root.datetime = _SiteClock
production.page = _boom
try:
    site_root.main()
finally:
    production.page = real_page
    site_root.OUT = saved_out
    site_root.datetime = saved_site_dt
taken = open(take_index, encoding="utf-8").read()
eq(boom["n"], 0, "takeover does not call production.page")
ok("2026-10-01T12:00:00Z" in _stamp(taken), "takeover stamps the shell with production.html's clock")
ok("2026-10-05" not in _stamp(taken), "takeover does not stamp the shell with its own clock")
ok('<div class="tile"><b>4</b><span>pairs in Production</span></div>' in taken,
   "takeover copies the production tiles")
shutil.rmtree(take_dir, ignore_errors=True)


print("\ntakeover does not rebuild Running from newer data")
drift_dir = tempfile.mkdtemp(prefix="shell-drift-")
drift_prod = os.path.join(drift_dir, "production.html")
drift_index = os.path.join(drift_dir, "index.html")
drift_blob = _blob([
    _lead("soon", "Alpha", "Beta", "2026-10-06T15:00:00Z", "pending",
          "oddspedia|cricket", "cricket", 0.61),
])
drift_prod_html, drift_index_html = sandbox_build.production_and_index(
    NOW, {"quotes": []}, {"pairs": {
        "oddspedia|cricket": {
            "stage": "production",
            "ready_at": "2026-09-27T00:00:00+00:00",
            "since": "2026-09-01T00:00:00+00:00",
            "by_hand": "2026-09-27",
        },
    }}, drift_blob)
open(drift_prod, "w", encoding="utf-8").write(drift_prod_html)
open(drift_index, "w", encoding="utf-8").write(drift_index_html)
newer_blob = _blob([
    _lead("soon", "Newer", "Data", "2026-10-06T15:00:00Z", "pending",
          "oddspedia|cricket", "cricket", 0.22),
])
lane_calls = {"n": 0}
real_collect = shell_build.collect_lanes


def _count_lanes(*args, **kwargs):
    lane_calls["n"] += 1
    return real_collect(*args, **kwargs)


saved_loaders = {
    "collect": shell_build.collect_lanes,
    "feed": production.load_feed,
    "load": shell_build.T.load,
    "stages": shell_build.T.load_stages,
    "out": site_root.OUT,
}
shell_build.collect_lanes = _count_lanes
production.load_feed = lambda *args, **kwargs: newer_blob
shell_build.T.load = lambda *args, **kwargs: {"quotes": []}
shell_build.T.load_stages = lambda *args, **kwargs: {"pairs": {}}
site_root.OUT = drift_index
try:
    site_root.main()
    matched = open(drift_index, encoding="utf-8").read()
    eq(lane_calls["n"], 0, "a matching stamp does not rebuild Running")
    ok("Alpha v Beta" in matched and "Newer v Data" not in matched,
       "Running still names the production build, not the newer ledger")
    tampered = matched.replace("2026-10-05T18:00:00Z", "2026-10-01T00:00:00Z", 1)
    open(drift_index, "w", encoding="utf-8").write(tampered)
    site_root.main()
    copied = open(drift_index, encoding="utf-8").read()
    eq(lane_calls["n"], 0, "a stamp mismatch still does not rebuild Running")
    ok("Alpha v Beta" in copied and "Newer v Data" not in copied,
       "the copied Running block is still the tracker block")
    ok("2026-10-05T18:00:00Z" in _stamp(copied),
       "the copied shell takes production.html's clock")
    ok("2026-10-01T00:00:00Z" not in _stamp(copied),
       "the copied shell does not keep the stale index clock")
finally:
    shell_build.collect_lanes = saved_loaders["collect"]
    production.load_feed = saved_loaders["feed"]
    shell_build.T.load = saved_loaders["load"]
    shell_build.T.load_stages = saved_loaders["stages"]
    site_root.OUT = saved_loaders["out"]
    shutil.rmtree(drift_dir, ignore_errors=True)


print("\nrecord_build does not stamp index.html")
import book_track
import fire_track
import record_build
import streaks_fetch
import streaks_track

saved_record = {
    "out": record_build.OUT_DIR,
    "fetch": streaks_fetch.load_or_fetch,
    "report": streaks_track.report,
    "compare": streaks_track.rule_compare,
    "load": streaks_track.load,
    "fire": fire_track.report,
    "book": book_track.report,
    "book_load": book_track.load,
}
streaks_fetch.load_or_fetch = lambda: {"fixtures": []}
streaks_track.report = lambda fixtures: {"pending": 0, "graded": 0}
streaks_track.rule_compare = lambda *args, **kwargs: {}
streaks_track.load = lambda *args, **kwargs: {}
fire_track.report = lambda fixtures: {"graded": 0}
book_track.report = lambda blob: {"graded": 0}
book_track.load = lambda: {}
record_dir = tempfile.mkdtemp(prefix="shell-record-")
record_index = os.path.join(record_dir, "index.html")
open(record_index, "w", encoding="utf-8").write("KEEP-STAMP\n")
record_build.OUT_DIR = record_dir
try:
    record_build.build()
finally:
    record_build.OUT_DIR = saved_record["out"]
    streaks_fetch.load_or_fetch = saved_record["fetch"]
    streaks_track.report = saved_record["report"]
    streaks_track.rule_compare = saved_record["compare"]
    streaks_track.load = saved_record["load"]
    fire_track.report = saved_record["fire"]
    book_track.report = saved_record["book"]
    book_track.load = saved_record["book_load"]
eq(open(record_index, encoding="utf-8").read(), "KEEP-STAMP\n",
   "record_build leaves index.html on the shell clock")
shutil.rmtree(record_dir, ignore_errors=True)


print("\nfreshness notes")
fresh = open(os.path.join(ROOT, "page_freshness.py"), encoding="utf-8").read()
ok("redirect stub" not in fresh.lower(),
   "page_freshness.py does not call index.html a redirect stub")
record_src = open(os.path.join(ROOT, "record_build.py"), encoding="utf-8").read()
ok("sends visitors to the Sandbox" not in record_src,
   "record_build.py does not describe the root as a Sandbox redirect")
ok("root -> sandbox.html" not in record_src,
   "record_build.py does not log a redirect write")
wf_dir = os.path.join(ROOT, ".github", "workflows")
for name in sorted(os.listdir(wf_dir)):
    if not name.endswith(".yml"):
        continue
    body = open(os.path.join(wf_dir, name), encoding="utf-8").read()
    stale = [
        line.strip() for line in body.splitlines()
        if "redirect stub" in line.lower() and "not a redirect stub" not in line.lower()
    ]
    eq(stale, [], f"{name} does not describe index.html as a redirect stub")


print("\ncommitted shell")
_committed = open(os.path.join(ROOT, "public_site", "index.html"), encoding="utf-8").read()
_committed_rows = _rows(_committed)
ok(_committed_rows, "committed index.html lists Running contests")
for _key, _label in (("live", "Live"), ("settled", "Settled"), ("upcoming", "Upcoming")):
    eq(_filter_count(_committed, _key, _label),
       sum(1 for _row in _committed_rows if _attr(_row, "data-filter") == _key),
       f"committed {_label} count equals the committed rows")
ok('class="rule-mini"' not in _committed, "committed index.html has no rule cards yet")
_prod_committed = open(os.path.join(ROOT, "public_site", "production.html"), encoding="utf-8").read()
eq(shell_build.tiles_html(_committed), shell_build.tiles_html(_prod_committed),
   "committed index.html tiles equal committed production.html tiles")
_RESULT = {"landed": "W", "missed": "L", "paid": "price result"}
_recent = _prod_committed.split('id="recent"', 1)[1].split('id="held-back"', 1)[0]
_prod_settled = [
    (html_lib.unescape(name), _RESULT[status])
    for name, status in re.findall(
        r'data-l="Match">([^<]*)</td>.*?data-l="Result"><span class="[^"]*">([^<]+)</span>',
        _recent, re.S)
]
_shell_settled = [
    (html_lib.unescape(name), html_lib.unescape(status))
    for name, status in re.findall(
        r'data-filter="settled"[^>]*data-name="([^"]*)"[^>]*>.*?'
        r'<span class="running-status"[^>]*>([^<]+)</span>',
        _committed, re.S)
]
eq(sorted(_shell_settled), sorted(_prod_settled),
   "committed Settled rows match production.html's recent settled leads")


def _browser():
    from require_browser import require_browser
    sync_playwright = require_browser("test_running_list.py")
    if sync_playwright is None:
        return
    site = tempfile.mkdtemp(prefix="shell-browser-")
    try:
        open(os.path.join(site, "index.html"), "w", encoding="utf-8").write(PAGE)
        for name in ("site.css", "shell.js", "tables.js"):
            shutil.copy(os.path.join(ROOT, "public_site", name), os.path.join(site, name))

        class Handler(SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=site, **kwargs)

            def log_message(self, fmt, *args):
                return

        httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{httpd.server_address[1]}/index.html"
        print("\nbrowser")
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(channel="chrome", headless=True)
                page = browser.new_page(viewport={"width": 1280, "height": 800})
                page.goto(base, wait_until="load")
                styles = page.evaluate("""() => {
                  const sport = document.querySelector('nav.sports button[data-sport="crypto"]');
                  const filter = document.querySelector('.running-filters button[data-filter="settled"]');
                  const a = getComputedStyle(sport);
                  const b = getComputedStyle(filter);
                  return {
                    sportOpacity: a.opacity,
                    filterOpacity: b.opacity,
                    sportColor: a.color,
                    filterColor: b.color,
                    sportBorder: a.borderTopColor,
                    filterBorder: b.borderTopColor,
                    sportDisabled: sport.getAttribute("aria-disabled"),
                  };
                }""")
                ok(styles["sportDisabled"] == "true"
                   and float(styles["sportOpacity"]) < float(styles["filterOpacity"])
                   and styles["sportColor"] != styles["filterColor"]
                   and styles["sportBorder"] != styles["filterBorder"],
                   f"disabled sport pills are dimmer than an unpressed filter ({styles})")
                page.click('.running-filters button[data-filter="upcoming"]')
                page.wait_for_timeout(30)
                shown = page.evaluate("""() => {
                  const rows = [...document.querySelectorAll(".running-row")];
                  return rows.map((row) => ({
                    filter: row.getAttribute("data-filter"),
                    display: getComputedStyle(row).display,
                    h: row.getBoundingClientRect().height,
                  }));
                }""")
                upcoming_on = [row for row in shown if row["filter"] == "upcoming"]
                upcoming_off = [row for row in shown if row["filter"] != "upcoming"]
                ok(upcoming_on and all(row["display"] != "none" and row["h"] > 0 for row in upcoming_on)
                   and upcoming_off and all(row["display"] == "none" and row["h"] == 0 for row in upcoming_off),
                   "Upcoming hides the other buckets, including settled rows in the same sport group "
                   f"({shown})")
                roles = page.evaluate("""() => ({
                  listbox: document.querySelectorAll('[role="listbox"]').length,
                  option: document.querySelectorAll('[role="option"]').length,
                })""")
                eq(roles, {"listbox": 0, "option": 0}, "Running rows are not a listbox")
                page.click('.running-filters button[data-filter="settled"]')
                page.wait_for_timeout(30)
                page.locator('.running-filters button[data-filter="settled"]').focus()
                page.keyboard.press("Tab")
                page.keyboard.press("Tab")
                tabbed = page.evaluate("""() => {
                  const el = document.activeElement;
                  return el ? el.className : "";
                }""")
                ok("running-row" in tabbed, f"Tab reaches a Running row ({tabbed})")
                first = page.locator(".running-row:not([hidden])").nth(0)
                second = page.locator(".running-row:not([hidden])").nth(1)
                first.focus()
                page.keyboard.press("Enter")
                selected = page.evaluate("""() => {
                  const rows = [...document.querySelectorAll(".running-row")];
                  const on = rows.filter((row) => row.getAttribute("aria-pressed") === "true");
                  const current = on[0];
                  const line = document.getElementById("rules-line");
                  const empty = document.getElementById("rules-empty");
                  return {
                    n: on.length,
                    pressed: current ? current.getAttribute("aria-pressed") : "",
                    name: current ? current.getAttribute("data-name") : "",
                    shadow: current ? getComputedStyle(current).boxShadow : "",
                    line: line ? line.textContent : "",
                    emptyHidden: empty ? empty.hidden : null,
                    cards: document.querySelectorAll(".rule-mini").length,
                    selectedAttr: document.querySelectorAll("[aria-selected]").length,
                  };
                }""")
                ok(selected["n"] == 1 and selected["pressed"] == "true"
                   and selected["name"] and selected["name"] in selected["line"]
                   and "inset" in selected["shadow"]
                   and "¢" in selected["line"] and " · " in selected["line"]
                   and selected["emptyHidden"] and selected["cards"] == 0
                   and selected["selectedAttr"] == 0,
                   f"Enter presses one row and names it in the header ({selected})")
                second.focus()
                page.keyboard.press("Space")
                moved = page.evaluate("""() => {
                  const rows = [...document.querySelectorAll(".running-row:not([hidden])")];
                  return rows.map((row) => row.getAttribute("aria-pressed"));
                }""")
                eq(moved[:2], ["false", "true"], "Space moves aria-pressed to the focused row")
                eq(moved.count("true"), 1, "Space leaves only one row pressed")
                page.locator(".running-row:not([hidden])").nth(0).click()
                clicked = page.evaluate("""() => {
                  const rows = [...document.querySelectorAll(".running-row:not([hidden])")];
                  return rows.map((row) => row.getAttribute("aria-pressed"));
                }""")
                eq(clicked[0], "true", "a click presses that row")
                eq(clicked.count("true"), 1, "a click clears the other rows")
                page.click('.running-filters button[data-filter="upcoming"]')
                page.wait_for_timeout(30)
                cleared = page.evaluate("""() => {
                  const line = document.getElementById("rules-line");
                  const head = document.getElementById("rules-head");
                  const empty = document.getElementById("rules-empty");
                  return {
                    pressed: document.querySelectorAll('.running-row[aria-pressed="true"]').length,
                    line: line ? line.textContent : null,
                    headHidden: head ? head.hidden : null,
                    emptyHidden: empty ? empty.hidden : null,
                    empty: empty ? empty.textContent : "",
                  };
                }""")
                eq(cleared["pressed"], 0, "hiding the selected row clears aria-pressed")
                eq(cleared["line"], "", "hiding the selected row clears the detail header")
                ok(cleared["headHidden"] and not cleared["emptyHidden"]
                   and cleared["empty"] == "Select a contest in Running.",
                   f"the detail pane returns to its empty state ({cleared})")
                browser.close()
        finally:
            httpd.shutdown()
    finally:
        shutil.rmtree(site, ignore_errors=True)


_browser()

print()
if FAILS:
    print(f"{len(FAILS)} FAILED")
    sys.exit(1)
print("all passed")
