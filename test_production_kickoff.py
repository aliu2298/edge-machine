#!/usr/bin/env python3
"""Since Production counts the contest, not when the bet was written down.

A bet logged before a pair entered Production and played after it is that
pair's record: the feed, the strip and the Running list already keep it.
The page's Since-Production cell and the feed's sandbox_* numbers used to
ask for logged >= entered_at, so the same bet was missing there.

The fixture is built here. Nothing in this file opens data/.
"""
import datetime
import re
import sys

import production

FAILS = []
NOW = datetime.datetime(2026, 10, 6, 12, 0, tzinfo=datetime.timezone.utc)
ENTERED = "2026-10-01T12:00:00+00:00"
KEY = "fixture_kick|soccer"
PAIR = {
    "stage": "production",
    "ready_at": ENTERED,
    "promoted_at": ENTERED,
    "by_hand": "2026-10-01",
}
# One second either side of the inclusive kickoff boundary.
BEFORE = "2026-10-01T11:59:59+00:00"
AFTER_KO = "2026-10-02T15:00:00+00:00"
LATER_KO = "2026-10-03T15:00:00+00:00"
LOG_BEFORE = "2026-09-28T08:00:00+00:00"
LOG_AFTER = "2026-10-02T08:00:00+00:00"


def ok(cond, why):
    print(f"  {'ok  ' if cond else 'FAIL'} {why}")
    if not cond:
        FAILS.append(why)


def eq(got, want, why):
    ok(got == want, why if got == want else f"{why} — got {got!r}, want {want!r}")


def bet(i, logged, start, status="won", placed=True, **extra):
    won = status == "won"
    row = dict(
        id=f"fixture_kick:{i}", source="fixture_kick", sport="soccer",
        bet=placed, venue="kalshi", pick="a", price=0.80,
        price_a=0.80, price_b=0.20,
        result=("a" if won else "b") if status in ("won", "lost") else None,
        status=status,
        pnl=(25.0 if won else -100.0) if placed and status in ("won", "lost") else None,
        logged=logged, start=start, market_id=f"m{i}",
        side_a="Home", side_b="Away",
    )
    row.update(extra)
    return row


def _cells(html):
    section = html.split('id="pairs"', 1)[1].split('id="coming-up"', 1)[0]
    rows = [row for row in re.findall(r"<tr>(.*?)</tr>", section, re.S)
            if "fixture_kick" in row]
    if len(rows) != 1:
        return None
    cells = re.findall(r"<td\b[^>]*>(.*?)</td>", rows[0], re.S)

    def text(cell):
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", cell)).strip()

    return [text(cell) for cell in cells]


def show(quotes, archive=None):
    """Render the page and read the feed record for this one pair."""
    d = {"quotes": list(quotes), "_archive": list(archive or [])}
    st = {"pairs": {KEY: dict(PAIR)}}
    html = production.page(d, st, {"leads": {}, "pairs": {KEY: {}}}, "", now=NOW)
    cells = _cells(html)
    # The third argument is entered_at(pair), the same value build_feed passes.
    rec = production._sandbox_record(d, KEY, ENTERED)
    feed = production.build_feed(d, st, now=NOW)
    return cells, rec, feed["pairs"][KEY]


print("\ntwo bets kick off after entry: both count, including one logged before it")
# The pre-promotion bet sits in the archive, where a settled row actually goes.
# A filter that only walks the live quotes still shows 1.
early = bet(1, LOG_BEFORE, AFTER_KO)
later = bet(2, LOG_AFTER, LATER_KO)
cells, rec, pair_feed = show([later], archive=[early])
eq(cells[4] if cells else None, "2\u20130 2 settled",
   "the Since-Production record is 2–0, not the one bet logged after entry")
eq(rec["sandbox_n"], 2, "the feed record counts both contests")
eq(pair_feed["sandbox_n"], 2, "build_feed publishes that same n")
eq(rec, {k: pair_feed[k] for k in ("sandbox_n", "sandbox_roi", "sandbox_roi_fee", "sandbox_clv")},
   "the page's helper and the feed record are one assessment")

print("\na bet logged after entry whose kickoff is before it does not count")
late_log_early_ko = bet(3, LOG_AFTER, BEFORE)
cells, rec, _pair = show([late_log_early_ko])
eq(rec["sandbox_n"], 0, "kickoff before entry is outside the record (n=0)")
ok(bool(cells) and cells[4].startswith("\u2014") and "settled" not in cells[4],
   "the page does not show that bet as a Since-Production result")

print("\nthe kickoff boundary is inclusive")
on_the_instant = bet(4, LOG_BEFORE, ENTERED)
cells, rec, _pair = show([on_the_instant])
eq(rec["sandbox_n"], 1, "kickoff == entered_at counts")
eq(cells[4] if cells else None, "1\u20130 1 settled",
   "the page counts the contest that kicks off at the instant of entry")
one_second_early = bet(5, LOG_AFTER, BEFORE)
_cells_b, rec_b, _pair_b = show([one_second_early])
eq(rec_b["sandbox_n"], 0, "kickoff one second before entered_at does not count")

print("\nrunning and priced-out use the same kickoff test")
running = bet(6, LOG_BEFORE, AFTER_KO, status="open")
cells, rec, _pair = show([running])
eq(rec["sandbox_n"], 0, "an open bet is not part of the settled record")
eq(cells[4] if cells else None, "\u2014 1 running",
   "an open bet logged before entry still counts as running when it kicks off after")
running_early = bet(7, LOG_AFTER, BEFORE, status="open")
cells, _rec, _pair = show([running_early])
ok(bool(cells) and "running" not in cells[4],
   "an open bet that already kicked off before entry is not 'running'")
running_exact = bet(8, LOG_BEFORE, ENTERED, status="open")
cells, _rec, _pair = show([running_exact])
eq(cells[4] if cells else None, "\u2014 1 running",
   "an open bet that kicks off at entered_at is inside the window")
priced = bet(9, LOG_BEFORE, AFTER_KO, status="open", placed=False)
cells, _rec, _pair = show([priced])
eq(cells[4] if cells else None, "\u2014 1 priced out",
   "a pick logged before entry and refused on price still counts when the contest is after")
priced_early = bet(10, LOG_AFTER, BEFORE, status="open", placed=False)
cells, _rec, _pair = show([priced_early])
ok(bool(cells) and "priced out" not in cells[4],
   "a priced-out pick whose contest was before entry does not count")

print("\nkickoff is the earlier of start and venue_start")
# start is after entry, the venue's own time is before it. _kickoff takes the
# earlier one, so this contest was not played in Production.
split = bet(11, LOG_AFTER, LATER_KO, venue_start=BEFORE)
_cells_s, rec_s, _pair_s = show([split])
eq(rec_s["sandbox_n"], 0, "an earlier venue_start before entry keeps the bet out")

print("\nthe filter copies; the ledger it was handed is unchanged")
kept = bet(12, LOG_AFTER, LATER_KO)
archived = bet(13, LOG_BEFORE, AFTER_KO)
quotes = [kept]
archive = [archived]
d = {"quotes": quotes, "_archive": archive}
production._sandbox_record(d, KEY, ENTERED)
eq(d["quotes"], [kept], "quotes is the same list of the same rows")
eq(d["_archive"], [archived], "the archive list is untouched")
ok(d["quotes"] is quotes and d["_archive"] is archive,
   "the call does not replace the lists it was given")

print(f"\n{len(FAILS)} FAILED" if FAILS else "\nall passed")
sys.exit(1 if FAILS else 0)
