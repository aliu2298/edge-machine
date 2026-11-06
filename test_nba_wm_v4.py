#!/usr/bin/env python3
"""NBA win margin, the two Sandbox paper lanes of 2026-11-06 (nba_wm_v4.py) and the tracker's minute marks."""
import datetime as dt
import sys

import chaos_replay as C
import nba_winmargin as W
import nba_wm_nofade as N
import nba_wm_v4 as V

FAILS = []
NOW = dt.datetime(2026, 11, 7, 12, tzinfo=dt.timezone.utc)


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


def row(i, ev, bucket, ask, share, ask_ok=True, night="2026-11-06", path=None, won=False, spread=0.02, elig=True):
    return dict(id=i, event=ev, night=night, tip=1000, team="BOS", bucket=bucket, ask=ask, spread=spread, eligible=elig, team_share=share,
                ask_ok=ask_ok, path=path if path is not None else [[-100, 15, 20]], won=won)


print("the entry rule")
rows = [row("a", "E1", "1-5", 0.15, 0.55), row("b", "E1", "11-20", 0.12, 0.45), row("c", "E1", "21+", 0.12, 0.45),
        row("d", "E2", "6-10", 0.15, 0.72), row("e", "E3", "6-10", 0.25, 0.5), row("f", "E3", "6-10", 0.15, 0.5, ask_ok=False),
        row("g", "E4", "6-10", 0.15, 0.5, night="2026-11-05"), row("h", "E5", "6-10", 0.20, 0.69), row("i", "E5", "1-5", 0.10, 0.31, spread=0.06),
        row("j", "E6", "11-20", 0.15, 0.5, ask_ok=None)]
ok, skips = V.candidates(rows)
check("1-5, 6-10 and 11-20 at 10-20c enter; 21+, a 25c ask, a spread over 5c, earlier nights do not", sorted(r["id"] for r in ok), ["a", "b", "h"])
check("a favourite share of 0.70 or more is skipped, with its reason", skips.get("d"), "favourite share 0.72 (0.70 or more)")
check("an ask that failed or never had its check is skipped as unverified", (skips.get("f"), skips.get("j")), ("unverified ask", "unverified ask"))
check("the favourite is the larger share in the game: 0.69 stays, the 0.31 side does not matter", "h" in [r["id"] for r in ok], True)
check("the 0.70 line is inclusive (skipped at exactly 0.70)", V.candidates([row("k", "E7", "1-5", 0.15, 0.70)])[1].get("k") is not None, True)

print("the 2x / 2.5x split")
t = V.trade([[-60, 15, 20], [60, 30, 5]], 0.15, False)         # 30c is not strictly through 0.30; 2.5x = 0.375
check("a print AT the 2x target does not fill it (strictly through)", (t["filled_2x"], t["filled_25x"]), (False, False))
t = V.trade([[60, 31, 5]], 0.15, False)
check("a print through 2x but under 2.5x fills only the first leg", (t["filled_2x"], t["filled_25x"]), (True, False))
check("that leg's proceeds: half at 0.30 less the maker fee, half lost", round(t["profit"], 4),
      round(0.5 * (0.30 - C.maker_fee(0.30)) - C.cost(0.15), 4))
t = V.trade([[60, 40, 5]], 0.15, True)
check("both legs fill on a print through 2.5x; cost is the ask plus the taker fee", (t["filled_2x"], t["filled_25x"], t["cost"]),
      (True, True, round(C.cost(0.15), 5)))
check("hold control: the same entry to settlement", t["hold_roi"], round((1.0 - C.cost(0.15)) / C.cost(0.15), 4))
t = V.trade([[-30, 99, 5]], 0.15, False)
check("a print before the tip never fills a leg", (t["filled_2x"], t["filled_25x"]), (False, False))
t = V.trade([[60, 98, 5]], 0.45, False)
check("2.5x of 45c is capped at 98c and needs a print strictly above it; 2x (90c) is filled", (t["filled_2x"], t["filled_25x"]), (True, False))

print("the lane run")
tracker = dict(rows=[row("a", "E1", "1-5", 0.15, 0.55, path=[[-100, 15, 20], [120, 40, 3]], won=True),
                     row("n", "E8", "6-10", 0.15, 0.5, path=[])])
st = V.run(V.load("/nonexistent"), tracker, NOW)
check("a candidate becomes one row, keyed by contract", sorted(st["rows"]), ["a"])
check("a row with no prints and no metrics is left out and says why", st["skips"].get("n"), "no price path")
before = dict(st["rows"]["a"])
V.run(st, tracker, NOW)
check("a row is never rewritten", st["rows"]["a"], before)
check("the row carries the lane, version and the cost", (st["rows"]["a"]["lane"], st["rows"]["a"]["version"]), ("nba_wm_yes_v4", "wm-yes-v4"))

print("the NO fade at 65%")
def bucket(i, fills):
    return dict(id=i, bucket="1-5", team="BOS", P=0.5, spread=0.02, ask=dict(status="verified"), no_wins=True, fills=fills)
fill = lambda p: dict(limit=0.33, fill_at=1, fill_print=0.3, printed=12, sold_at=2, cost=0.34, profit=p, won=p > 0, reason="sold")
entries = [dict(event="KXNBAWINMARGIN-26NOV06AAABBB", night="2026-11-06", tip=1, buckets=[bucket("x", {"d65": fill(0.1), "d75": None})]),
           dict(event="KXNBAWINMARGIN-26NOV05CCCDDD", night="2026-11-05", tip=1, buckets=[bucket("y", {"d65": fill(0.2), "d75": fill(0.1)})]),
           dict(event="KXNBAWINMARGIN-26NOV07EEEFFF", night="2026-11-07", tip=1, buckets=[bucket("z", {"d65": fill(-0.1), "d75": fill(0.05)})])]
nf = dict(entries=entries)
check("the lane counts its 65% fills from SINCE_NO on, not the earlier night", sorted(r["night"] for r in V.no_games(nf)), ["2026-11-06", "2026-11-07"])
check("the 75% comparison on the same nights has its own fills", [r["night"] for r in V.no_games(nf, N.HEAD)], ["2026-11-07"])
check("the nights before the lane are the in-sample row", [r["night"] for r in V.before_games(nf, 0.65)], ["2026-11-05"])

print("the tracker's minute marks")
m = W.marks_of([[-600, 15, 5], [300, 20, 5], [1900, 31, 2], [4000, 40, 1]], 0.15)
check("the last print at or before each minute, None before the first", (m["p"]["30"], m["p"]["60"], m["p"]["90"]), (20, 31, 40))
check("first minute at 2x and at 2.5x", (m["first2"], m["first25"]), (31.7, 66.7))
check("a target above 99c is None, never reached", W.marks_of([[60, 50, 1]], 0.45)["first2"], None)
check("no path, no marks", W.marks_of([], 0.15), None)
st = dict(rows=[dict(id="r", event="E", night="2026-11-06", tip=0, ask=0.15, eligible=True, m=dict(), path=[[60, 40, 1]], marks=None)],
          spread_rows=[], seen={}, spread_seen={}, skips={}, since="2026-10-20")
W.run(st, now=NOW, fetch=lambda *a, **k: {})
check("a row read before the marks existed is stamped while its path is kept", st["rows"][0]["marks"] is not None, True)

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
