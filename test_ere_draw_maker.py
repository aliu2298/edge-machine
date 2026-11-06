#!/usr/bin/env python3
"""Offline checks for ere_draw_maker (2026-11-06): the queue-honest fill, the maker fee, the settlement, the comparison beside
ere_draw, the fresh record, the in-sample replay, and the Soccer page row right under ere_draw."""
import copy
import datetime as dt
import sys

import ere_draw_maker as M
import ere_draw_maker_build as MB
import sandbox_audit
import soccer_lanes as L

FAILS = []
UTC = dt.timezone.utc


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


KICK = dt.datetime(2026, 11, 8, 14, 0, tzinfo=UTC)
K = int(KICK.timestamp())


def q(mid="KXEREDIVISIEGAME-26NOV08AAABBB", price=0.25, status="open", logged=None, start=KICK):
    return dict(market_id=mid, label="Alpha vs Beta", price=price, status=status, venue="kalshi", sport="soccer", source="ere_draw", pick="draw",
                start=start.isoformat(), logged=(logged or (start - dt.timedelta(days=3))).isoformat(), pnl=0.0)


print("the bid and the queue-honest fill")
e = M.evaluate(q(), [(K - 7200, 0.24, 30.0)], K + 3600)
check("the bid rests 1c under the ask", (e["ask"], e["bid"]), (0.25, 0.24))
check("a print AT the bid does not fill it (the queue)", e["filled"], False)
e = M.evaluate(q(), [(K - 7200, 0.23, 5.0)], K + 3600)
check("a print strictly below the bid fills it, at the bid", (e["filled"], e["fill_price"], e["fill_print"]), (True, 0.24, 0.23))
e = M.evaluate(q(), [(K + 60, 0.10, 99.0)], K + 3600)
check("a print after kickoff does not fill it", e["filled"], False)
e = M.evaluate(q(logged=KICK - dt.timedelta(hours=2)), [(K - 4 * 3600, 0.20, 10.0), (K - 3600, 0.22, 1.0)], K + 3600)
check("the bid is placed when the match first qualified: an earlier print is before it, a later one fills",
      (e["placed_ts"], e["filled"], e["fill_print"]), (K - 7200, True, 0.22))
e = M.evaluate(q(logged=KICK - dt.timedelta(days=5)), [(K - 25 * 3600, 0.20, 10.0)], K + 3600)
check("at most 24 hours before kickoff: a print 25 hours out is before the bid", (e["placed_ts"], e["filled"]), (K - 24 * 3600, False))

print("\nsettlement and the comparison beside ere_draw")
won = M.settle(M.evaluate(q(price=0.25, status="won"), [(K - 3600, 0.20, 5.0)], K + 3600), q(price=0.25, status="won"))
cost = 0.24 + 0.0175 * 0.24 * 0.76
check("a filled winner returns 1 over the bid plus the maker fee", round(won["maker_roi"], 6), round((1 - cost) / cost, 6))
check("ere_draw's taker result is on the same match", won["taker_roi"] is not None and won["taker_roi"] > 2.0, True)
lost = M.settle(M.evaluate(q(status="lost"), [(K - 3600, 0.20, 5.0)], K + 3600), q(status="lost"))
check("a filled loser loses the stake", (lost["maker_roi"], lost["taker_roi"]), (-1.0, -1.0))
nofill = M.settle(M.evaluate(q(status="won"), [], K + 3600), q(status="won"))
check("an unfilled match has no maker result and still shows the taker one", (nofill["maker_roi"], nofill["taker_roi"] is not None), (None, True))
open_fill = M.settle(M.evaluate(q(), [(K - 3600, 0.20, 5.0)], K + 3600), q())
check("an open fill has no result yet", (open_fill["filled"], open_fill["maker_roi"], open_fill["taker_roi"]), (True, None, None))

print("\nthe summary")
s = M.summary([won, lost, nofill, open_fill])
check("matches, fills, settled fills", (s["matches"], s["filled"], s["n"], s["won"], s["open_fills"]), (4, 3, 2, 1, 1))
check("the fill rate", round(s["fill_rate"], 3), 0.75)
check("taker ROI on the same fills is the two fills; on every match is the three settled",
      (round(s["taker_same"], 4), s["taker_all_n"]), (round((won["taker_roi"] + -1.0) / 2, 4), 3))
check("the record is the settled fills", (M.record(dict(entries=[won, lost, nofill]))["n"], M.record(dict(entries=[]))["n"]), (2, 0))

print("\nthe run: fresh record, in-sample replay, no double read")
import sandbox_track as T
calls = []
parent = [q("KXEREDIVISIEGAME-26NOV08AAABBB"), q("KXEREDIVISIEGAME-26OCT10CCCDDD", status="won", start=dt.datetime(2026, 10, 10, 14, tzinfo=UTC))]
T.bet_rows = lambda d: parent
now = KICK + dt.timedelta(hours=3)


def fetch(path, *a, **k):
    calls.append(path)
    return {"trades": [], "cursor": ""}


st = M.run(M.empty(), {}, now=now, fetch=fetch)
check("the Nov 8 match is read once; the October one waits for --backfill", ([e["id"] for e in st["entries"]], st["insample"]), (["KXEREDIVISIEGAME-26NOV08AAABBB"], []))
n = len(calls)
M.run(st, {}, now=now, fetch=fetch)
check("a second run reads nothing again", len(calls), n)
st = M.run(st, {}, now=now, fetch=fetch, backfill=True)
check("--backfill replays the earlier match into the in-sample block, never the record", ([e["id"] for e in st["insample"]], len(st["entries"])), (["KXEREDIVISIEGAME-26OCT10CCCDDD"], 1))
early = M.run(M.empty(), {}, now=KICK + dt.timedelta(minutes=2), fetch=fetch)
check("a match is not read before every print that could fill the bid is on file", early["entries"], [])
check("the trades come from the Tie market", all("-TIE" in p for p in calls), True)

print("\nthe Soccer page row")
row = L.ere_draw_maker_row(st)
check("one Sandbox row, placed right under ere_draw", (row["name"], row["prod"], row["after"]), ("ere_draw_maker", False, "ere_draw"))
text = row["own"]["details"]
check("the fold carries the entry, fill, exit, the comparison and the matches", all(x in text for x in ("Entry", "Fill", "Exit", "Maker v taker", "ere_draw taker ROI", "Matches")), True)
check("the in-sample replay is collapsed and labelled", ("Earlier matches, replayed once" in text, "not in the record" in text), (True, True))
check("public copy: the row's words pass the copy guard", bool(sandbox_audit.COPY_RE.search(text + row["own"]["label"])), False)
check("no loose dollar amounts on the page words", "$" in text, False)

if FAILS:
    print(f"\nFAILED {len(FAILS)}")
    sys.exit(1)
print("ALL PASS")
