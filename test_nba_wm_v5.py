#!/usr/bin/env python3
"""NBA win margin version 5 paper candidates (nba_wm_v5.py, 2026-11-11): the registered buckets, the favourite skip, the NO bucket filter,
the v4 comparison on the same games, the Sandbox rows and the pre-registration file."""
import datetime as dt
import os
import sys

import nba_page as NP
import nba_wm_nofade as N
import nba_wm_v4 as V4
import nba_wm_v5 as V5
import sandbox_audit

FAILS = []
NOW = dt.datetime(2026, 11, 12, 12, tzinfo=dt.timezone.utc)


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


print("YES v5: buckets 6-10 and 11-20, favourite skip on, 2x / 2.5x")
tr = lambda i, ev, b, share, night="2026-11-11": dict(id=i, event=ev, night=night, tip=1, team="BOS", bucket=b, ask=0.15, spread=0.02, eligible=True, team_share=share,
                                                      ask_ok=True, path=[[60, 31, 5]], won=False)
rows = [tr("a", "E1", "1-5", 0.55), tr("b", "E1", "6-10", 0.55), tr("c", "E1", "11-20", 0.45), tr("d", "E1", "21+", 0.5), tr("e", "E2", "6-10", 0.80),
        tr("f", "E3", "6-10", 0.55, "2026-11-10")]
ok, skips = V4.candidates(rows, V5.SINCE, V5.RULE_V5)
check("6-10 and 11-20 enter; 1-5 and 21+ do not; a 0.80 game is skipped; the night before the start is out", (sorted(r["id"] for r in ok), list(skips)), (["b", "c"], ["e"]))
ok4, _s = V4.candidates(rows, V5.SINCE, V4.RULE_V4)
check("the v4 rule on the same rows also enters 1-5", sorted(r["id"] for r in ok4), ["a", "b", "c"])
s = V5.run(V5.load("/nonexistent"), dict(rows=rows), NOW)
r = s["rows"]["b"]
check("its own lane, version and fresh start", (r["lane"], r["version"], s["since"], V5.RULE_V5["path"].endswith("nba_wm_v5.json")), ("nba_wm_yes_v5", "wm-yes-v5-paper", "2026-11-11", True))
check("the 2x leg fills on a 0.31 print, the 2.5x leg does not", (r["filled_2x"], r["filled_25x"]), (True, False))
check("the v4 rows from the start: the same games or all", ([x["key"] for x in V5.yes_v4_rows(s, events={"E1"})], len(V5.yes_v4_rows(s))), (["b", "c"], 2))

print("\nNO v5: the 65% bid on 1-5, 6-10 and the alternate ladder")
fill = lambda p: dict(cost=0.5, profit=p, sold_at=None)
key = N.vkey(V5.NO_DIP)
bk = lambda b, p: dict(bucket=b, ask=dict(status="verified"), fills={key: fill(p)})
entries = [dict(event="G1", night="2026-11-11", buckets=[bk("1-5", 0.1), bk("6-10", 0.1), bk("11-20", -0.5), bk("21+", -0.5), bk("26+", 0.1), bk("11+", 0.1)]),
           dict(event="G2", night="2026-11-11", buckets=[bk("21+", 0.3)]),
           dict(event="G3", night="2026-11-10", buckets=[bk("1-5", 0.2)])]
nofade = dict(entries=entries)
orig_phase = N.phase_of
N.phase_of = lambda night: "v2"
g = V5.no_games(nofade)
check("only G1 trades (11-20 and 21+ are cut, G2 has only 21+); four buckets, +0.4", ([x["event"] for x in g], g[0]["fills"], round(g[0]["profit"], 2)), (["G1"], 4, 0.4))
v4g = V5.no_v4_games(nofade)
check("the v4 rule on the same nights keeps every bucket and G2", (sorted(x["event"] for x in v4g), round(sum(x["profit"] for x in v4g), 2)), (["G1", "G2"], -0.3))
check("the v4 comparison can be cut to the v5 games", [x["event"] for x in V5.no_v4_games(nofade, events={"G1"})], ["G1"])

print("\nthe Sandbox rows and panels")
rows_ = NP.sandbox_rows(nofade, V4.load("/nonexistent", V4.RULE_V3), s)
check("the two v5 rows are paper, not Production, with the plain label", [(r["name"], r["prod"], r["label"]) for r in rows_[2:]],
      [("nba_wm_yes_v5", False, "Win margin · YES split v5 (paper)"), ("nba_wm_nofade_v5", False, "Win margin · NO fade v5 (paper)")])
yp, np_ = NP.yes5_panel(s, V4.load("/nonexistent")), NP.no5_panel(nofade, NOW.isoformat())
check("the panels carry the plain words, the pre-registration path and the comparison", all(("Paper test · candidate next version · Production still runs v4" in x and V5.PREREG in x and "Against version 4" in x) for x in (yp, np_)), True)
check("no guarded phrase, no inline style", (sandbox_audit.COPY_RE.search(yp + np_), "style=" in yp + np_), (None, False))
N.phase_of = orig_phase

print("\nthe pre-registration file")
txt = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), V5.PREREG)).read()
check("it exists and names both lanes, the start night and the review / decide counts", all(x in txt for x in ("nba_wm_yes_v5", "nba_wm_nofade_v5", "2026-11-11", "10 nights", "30")), True)

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
