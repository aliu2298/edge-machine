#!/usr/bin/env python3
"""A crash duplicate is counted once in the Production reach cell.

A row can sit in the live ledger and in the archive at once, when a run dies
between those two writes. The reach cell must count that id once, and the
live copy wins. The feed still walks all_bets(), so its skipped-bet count
is not part of this fix.

The fixture is in memory. Nothing here reads data/, the live ledger, or the
network.
"""
import copy
import datetime
import sys
from datetime import timezone

import production
import sandbox_track as T

FAILS = []
NOW = datetime.datetime(2026, 10, 4, 12, 0, tzinfo=timezone.utc)
# Not a removed lane. mma_fav_band is off the board, and a removed pair
# never reaches this cell or the feed.
SOURCE = "fixture_mma"
SPORT = "mma"
KEY = f"{SOURCE}|{SPORT}"
# 13 the feed can publish and 19 it cannot is 32 bets. Two of those ids
# are also in the archive, which is what turned the cell into "13 of 34".
N_PLACEABLE = 13
N_UNPLACEABLE = 19
N_UNIQUE = N_PLACEABLE + N_UNPLACEABLE


def _refuse(*_a, **_k):
    raise AssertionError("this test must not read the live ledger or the archive files")


T.load = _refuse
T.load_stages = _refuse
T.load_archive = _refuse


def ok(cond, why):
    print(f"  {'ok  ' if cond else 'FAIL'} {why}")
    if not cond:
        FAILS.append(why)


def eq(got, want, why):
    ok(got == want, f"{why} — got {got!r}, want {want!r}" if got != want else why)


def _row(i, reachable):
    q = dict(
        id=f"b{i:02d}", bet=True, source=SOURCE, sport=SPORT, pick="a",
        market_id=f"m-{i:02d}", side_a=f"A{i:02d}", side_b=f"B{i:02d}",
        venue="polymarket_us" if reachable else "kalshi",
        status="open", logged="2026-10-01T12:00:00+00:00",
        start="2026-10-05T18:00:00+00:00", price=0.55,
        price_a=0.55, price_b=0.45,
    )
    if not reachable:
        q["start_source"] = None
    return q


def _book():
    """32 live bets, plus two archive copies of ids that are still live.

    b00 can be published from the ledger. Its archive copy cannot, so
    counting the archive copy would drop the reachable total from 13 to 12.
    b13 cannot be published from either copy. all_bets() therefore sees 34
    rows and 13 reachable; bet_rows() sees 32 and 13.
    """
    live = [_row(i, True) for i in range(N_PLACEABLE)]
    live += [_row(i, False) for i in range(N_PLACEABLE, N_UNIQUE)]
    archived_placeable = copy.deepcopy(live[0])
    archived_placeable["venue"] = "kalshi"
    archived_placeable["start_source"] = None
    archived_unplaceable = copy.deepcopy(live[N_PLACEABLE])
    return {
        "quotes": live,
        "_archive": [archived_placeable, archived_unplaceable],
        "meta": {}, "coverage": {}, "retired": {},
    }


def _cell(html):
    needle = '<div class="sm mut">reachable</div>'
    at = html.find(needle)
    if at < 0:
        return None
    start = html.rfind("<span", 0, at)
    return html[start:at + len(needle)]


def main():
    print("the fixture is the reported 13 of 32, inflated to 13 of 34")
    d = _book()
    raw = [q for q in T.all_bets(d)
           if q.get("source") == SOURCE and q.get("sport") == SPORT and q.get("bet")]
    once = [q for q in T.bet_rows(d)
            if q.get("source") == SOURCE and q.get("sport") == SPORT and q.get("bet")]
    eq(len(raw), 34, "all_bets counts both copies")
    eq(sum(1 for q in raw if T.placeable(q)), N_PLACEABLE,
       "the archive copies cannot be published, so the numerator stays 13")
    eq(len(once), N_UNIQUE, "bet_rows counts each id once")
    eq(sum(1 for q in once if T.placeable(q)), N_PLACEABLE,
       "the live copy of b00 is the one the feed can publish")
    kept = next(q for q in once if q["id"] == "b00")
    eq(kept["venue"], "polymarket_us", "the live row wins over the archive copy")

    st = {"pairs": {KEY: {"stage": "production", "ready_at": "2026-09-01T00:00:00+00:00",
                          "by_hand": "2026-09-01"}},
          "events": []}
    blob = {"leads": {}, "pairs": {KEY: {}}, "unlisted_skipped": 0,
            "unverified_kickoff_skipped": 0}
    html = production.page(d, st, blob, "", now=NOW)
    cell = _cell(html)
    eq(cell, '<span class="neg">13 of 32</span><div class="sm mut">reachable</div>',
       "the reach cell counts the crash duplicate once")
    ok("13 of 34" not in html, "the inflated 13 of 34 is not on the page")

    print("\nthe feed's own skipped-bet count still sees both copies")
    feed = production.build_feed(d, st, now=NOW)
    eq(feed["unlisted_skipped"], 21,
       "build_feed still walks all_bets, so the two extra copies are still skipped")
    eq(len(feed["leads"]), N_PLACEABLE,
       "the 13 reachable bets are the leads, and the archive copy of b00 is not a second one")

    print()
    if FAILS:
        print(f"FAIL {len(FAILS)}")
        return 1
    print("PASS production reach dedupe")
    return 0


if __name__ == "__main__":
    sys.exit(main())
