#!/usr/bin/env python3
"""Offline checks for the Sandbox's index of the paper watches (watch_index.py, 2026-11-14): a row for every watch, the empty and no-fill-yet wording, percentages
only, a link to the card on its own sport page, the Sandbox carrying the section, and no guarded phrase."""
import datetime as dt
import sys

import bs_bid as B
import sandbox_audit
import sandbox_build
import watch_index as W

FAILS = []


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


rs = {r["lane"]: r for r in W.rows()}
check("a row for each of the four before-start groups, the kickoff groups, NL dump and mentions",
      sorted(rs), sorted(["bs_bid_ufc", "bs_bid_boxing", "bs_bid_nfl", "bs_bid_cricket", "ko_bid_national", "ko_bid_club", "nl_dump_d20", "mentions_dump_m20", "attendance_dump_m20"]))
check("NFL links to its own page's card", rs["bs_bid_nfl"]["href"], "./nfl.html#bs-bid-nfl")
check("cricket links to its own page's card", rs["bs_bid_cricket"]["href"], "./cricket.html#bs-bid-cricket")
check("wording: no event settled", W._status(0, 0, "x"), "Waiting for the first event to settle")
check("wording: events seen, no fill", W._status(12, 0, "x"), "12 events seen, 0 fills yet")
check("wording: one event", W._status(1, 0, "x"), "1 event seen, 0 fills yet")
check("wording: fills show the read", W._status(30, 5, "too early (5 of 50)"), "Too early (5 of 50)")
check("a watch with no fill shows no return", W._row("a", "A", "./a.html", "A", 3, 0, 0.5, "r")["roi"], None)

html = W.index_html()
check("the section is the Paper watches index", 'id="paper-watches"' in html and "Paper watches" in html, True)
check("percentages only: no dollar sign", "$" in html, False)
check("every row is labelled a paper watch", html.count("paper watch</b>"), 9)

# a ledger with events but no fill reads "N events seen, 0 fills yet" on the NFL row
st = B.empty()
for i in range(3):
    st["markets"][f"KXNFLGAME-26NOV15X{i}-A"] = dict(event=f"KXNFLGAME-26NOV15X{i}", day="2026-11-15", series="KXNFLGAME", group="nfl", match="A v B", leg="A", result="yes",
                                                  start=1, cutoff=1, prints=10, bets={"B15_25s": [], "B15_2s": []})
real = B.load
B.load = lambda *a, **k: st
nfl = {r["lane"]: r for r in W.rows()}["bs_bid_nfl"]
B.load = real
check("the NFL row reads 3 events seen, 0 fills yet", nfl["status"], "3 events seen, 0 fills yet")

sb, _idx, _wk = sandbox_build.render_pages(dt.datetime.now(dt.timezone.utc))
check("the Sandbox page carries the index", 'id="paper-watches"' in sb, True)
for f in ("watch_index.py", "test_watch_index.py"):
    check(f"no guarded phrase in {f}", sandbox_audit.COPY_RE.search(open(f).read()), None)

print("ALL PASS" if not FAILS else f"FAILED: {FAILS}")
sys.exit(1 if FAILS else 0)
