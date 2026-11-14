#!/usr/bin/env python3
"""Offline checks for the before-start bid in fights and NFL (bs_bid.py, 2026-11-14): the cutoff from Kalshi's schedule (12h fights, 3h NFL), bids only
before it and after FROM_TS, the maker fee on NFL only, the first-fill-only column, backfill, the pre-registered read, and page sections that make no
venue call and use no guarded phrase."""
import datetime as dt
import sys

import bs_bid as B
import bs_bid_build as BB
import daily_track as D
import fights_build
import nl_dump as N
import sandbox_audit

FAILS = []


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


print("the start and the cutoff")
START = int(dt.datetime(2026, 11, 15, 2, 0, tzinfo=dt.timezone.utc).timestamp())
get = lambda path: {"milestones": [{"related_event_tickers": ["X-1"], "start_date": "2026-11-15T02:00:00Z"}]}
check("the start is the milestone's start_date", B.start_of("X-1", get), START)
check("no milestone, no start", B.start_of("X-1", lambda p: {"milestones": []}), None)
check("a failed call, no start", B.start_of("X-1", lambda p: None), None)
check("fights cut 12 hours before the start, NFL 3", (START - B.cutoff_of(START, "ufc"), START - B.cutoff_of(START, "boxing"), START - B.cutoff_of(START, "nfl")), (12 * 3600, 12 * 3600, 3 * 3600))
check("no start, no cutoff", B.cutoff_of(None, "ufc"), None)
check("three rows by series; maker fee on NFL only", ({g: B.RULES[c["maker"]].maker_rate for g, c in B.GROUPS.items()}, B.GROUP_OF["KXBOXING"]), ({"ufc": 0.0, "boxing": 0.0, "nfl": 0.0175}, "boxing"))

print("\nthe replay on a made-up dump")
T0 = B.FROM_TS + 3600
steady = [(T0 + 30 * i, 0.60, 10.0, None) for i in range(25)]
dump = steady + [(T0 + 760, 0.35, 500.0, "no"), (T0 + 840, 0.56, 500.0, "yes")]
CUT = T0 + 3600
yes = lambda b: [x for x in b["B15_25s"] if x["side"] == "yes"]
fi = yes(B.replay(dump, "yes", "ufc", CUT))
nf = yes(B.replay(dump, "yes", "nfl", CUT))
check("a bid 15c under the 60c print, filled by the dump and sold at 55c: +22.2% with no maker fee", [(x["L"], x["roi"], x["sold"]) for x in fi], [(0.45, 0.2222, True)])
check("NFL pays the maker fee, so it earns less on the same trades", (len(nf) == 1, nf[0]["roi"] < fi[0]["roi"]), (True, True))
check("a dump after the cutoff is not bid for", yes(B.replay(dump, "yes", "ufc", T0 + 600)), [])
check("a bid whose minute is before FROM_TS does not count", yes(B.replay([(t - 7200, p, n, s) for t, p, n, s in dump], "yes", "ufc", CUT)), [])

print("\nwhich markets are read, and a late run backfills")
ev = lambda tk, day, ms: dict(event_ticker=f"{tk}-26NOV{day}AAABBB", title="A vs B", markets=ms)
mk = lambda t, res="yes": dict(ticker=t, result=res, yes_sub_title="A")
starts_get = lambda path: {"milestones": [{"related_event_tickers": [path.split("related_event_ticker=")[1]], "start_date": "2026-11-15T22:00:00Z"}]}
by = {"KXUFCFIGHT": [ev("KXUFCFIGHT", "15", [mk("U-1"), mk("U-2", "")]), ev("KXUFCFIGHT", "13", [mk("U-0")])], "KXNFLGAME": [ev("KXNFLGAME", "15", [mk("F-1", "no")])]}
st = B.empty()
n = B.run(st, by, tape=lambda tk: dump, get=starts_get)
check("a day before FROM_DAY and a market with no result are left out", (n, sorted(st["markets"])), (2, ["F-1", "U-1"]))
check("each market lands in its own row", (st["markets"]["U-1"]["group"], st["markets"]["F-1"]["group"]), ("ufc", "nfl"))
check("the ledger keeps the start and the cutoff", (st["markets"]["U-1"]["start"], st["markets"]["U-1"]["cutoff"] - st["markets"]["F-1"]["cutoff"]), (int(dt.datetime(2026, 11, 15, 22, tzinfo=dt.timezone.utc).timestamp()), -9 * 3600))
check("a second run reads nothing new", B.run(st, by, tape=lambda tk: dump, get=starts_get), 0)
nostart = B.empty()
check("an event with no schedule is an error, read on a later run", (B.run(nostart, by, tape=lambda tk: dump, get=lambda p: {}), len(nostart["errors"]), sorted(nostart["markets"])), (0, 2, []))
late = B.empty()
by2 = {"KXBOXING": [ev("KXBOXING", "15", [mk("B-1")])]}
B.run(late, by2, tape=lambda tk: dump, get=starts_get)
by2["KXBOXING"].append(ev("KXBOXING", "16", [mk("B-2")]))
check("a later run backfills the market an earlier one never saw", (B.run(late, by2, tape=lambda tk: dump, get=starts_get), sorted(late["markets"])), (1, ["B-1", "B-2"]))

print("\nthe first-fill column and the read")
rows = [(0.1, "E1", dict(fill=50, ticker="a", day="2026-11-15")), (0.5, "E1", dict(fill=20, ticker="b", day="2026-11-15")), (-0.2, "E2", dict(fill=5, ticker="c", day="2026-11-16"))]
check("only the earliest fill of each event", [(r[1], r[0]) for r in B.first_fills(rows)], [("E1", 0.5), ("E2", -0.2)])
head = lambda n, roi, t: dict(n=n, roi=roi, t=t)
check("under 50 fills: too early", B.read_text(head(10, 0.2, 3), head(5, 0.1, 1)).startswith("too early"), True)
check("50 fills, positive, t 2+, first fills positive: on track", B.read_text(head(60, 0.1, 2.5), head(20, 0.05, 1)).startswith("read at 50: on track"), True)
check("50 fills but the first-fill row negative: not there yet", B.read_text(head(60, 0.1, 2.5), head(20, -0.05, 1)).startswith("read at 50: not there"), True)
check("100 fills, positive, t 2+, first fills positive: keep", B.read_text(head(120, 0.1, 2.5), head(40, 0.05, 1)), "read at 100: keep (positive, score 2 or more, first fills positive)")
check("100 fills, t under 2: retire", B.read_text(head(120, 0.1, 1.9), head(40, 0.05, 1)), "read at 100: retire (under the bar at 100 fills)")
rec = B.records(st)
check("three rows, kept apart", (sorted(rec), rec["ufc"]["games"], rec["nfl"]["games"], rec["boxing"]["games"]), (["boxing", "nfl", "ufc"], 1, 1, 0))
check("one fill an event in the first-fill column of the dump test", rec["ufc"]["first"]["n"] <= rec["ufc"]["headline"]["n"], True)

print("\nthe page sections")


def _no_call(*a, **k):
    raise AssertionError("the page builder made a venue call")


real = D.get
D.get = _no_call
try:
    fights = BB.section(["ufc", "boxing"], B.empty())
    nfl = BB.section(["nfl"], st, anchor="bs-bid-nfl")
    page = fights_build.build()
finally:
    D.get = real
check("the fights section names both rows as a pass and the NFL one as a watch, not a pass", ("a pass in the study" in fights and "UFC" in fights and "Boxing" in fights, "a watch, not a pass" in nfl), (True, True))
check("the Fights page carries the section", 'id="bs-bid"' in page, True)
text = (fights + nfl).lower()
check("no guarded phrase, no money words, no weather words", [w for w in ("real " + "money", "the b" + "ot", "follow" + "er", "$", "weath" + "er") if w in text], [])
check("the audit's phrase scan finds nothing in the sections or the module text",
      (sandbox_audit.COPY_RE.search(fights + nfl), sandbox_audit.COPY_RE.search(open("bs_bid.py").read() + open("bs_bid_build.py").read() + open("docs/prereg_bs_bid_2026-11-14.md").read())), (None, None))
check("place() lands the section before the marker, or at the end of the body", (BB.place("<main>a<section id=\"rules\">", "S", '<section id="rules"'), BB.place("<main>a</main>", "S", "nope")), ("<main>aS<section id=\"rules\">", "<main>aS</main>"))

print()
if FAILS:
    print(f"{len(FAILS)} FAILED")
    sys.exit(1)
print("all ok")
