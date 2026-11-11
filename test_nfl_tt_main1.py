#!/usr/bin/env python3
"""Offline checks for nfl_tt_main1 (nfl_tt_main1.py) and its NFL page row."""
import datetime as dt
import os
import sys

import nfl_tt as N
import nfl_tt_main1 as M
import nfl_tt_main1_build as MB
import sandbox_audit

FAILS = []
UTC = dt.timezone.utc
# Retired 2026-11-11 (Olu, END NFL): the retirement is lifted for the entry and row logic, and restored for the page.
_retired = dict(M.RETIRED)
M.RETIRED.clear()
KO = dt.datetime(2026, 11, 15, 18, 0, tzinfo=UTC)
NOW = KO - dt.timedelta(minutes=60)


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


def game(away="WSH", home="SF", start=KO, gid="1", state="pre", week="2026-2-W11"):
    return dict(id=gid, start=start.strftime("%Y-%m-%dT%H:%MZ"), valid=True, state=state, away=away, home=home, week=week)


def rung(tag, team, line, bid, ask, status="active", size="250.00"):
    return dict(ticker=f"{tag}-{team}{int(line + 0.5)}", floor_strike=line, strike_type="greater", status=status,
                yes_sub_title=f"{team} over {line} points", yes_bid_dollars=None if bid is None else f"{bid:.4f}",
                yes_ask_dollars=None if ask is None else f"{ask:.4f}", yes_ask_size_fp=size)


def event(ladders, codes="WASSF", day="26NOV15"):
    tag = f"KXNFLTEAMTOTAL-{day}{codes}"
    return dict(event_ticker=tag, markets=[rung(tag, t, ln, *q) for t, lad in ladders.items() for ln, q in lad.items()])


def lad(pairs):
    return [(s, dict(ticker=f"X-T{int(s + 0.5)}"), b, a) for s, (b, a) in sorted(pairs.items())]


print("main line: the quoted rung with mid nearest 0.50 (analyze.main_line)")
m, r = M.pick_main1(lad({17.5: (0.66, 0.68), 20.5: (0.52, 0.54), 24.5: (0.38, 0.40), 27.5: (0.30, 0.32)}))
check("mid 0.53 is the main line", m[0], 20.5)
check("main+1 is the next higher strike (24.5)", r[0], 24.5)
m, r = M.pick_main1(lad({20.5: (0.51, 0.53), 23.5: (0.47, 0.49), 26.5: (0.35, 0.37)}))
check("mids 0.52 and 0.48 tie: the lower strike is the main line", m[0], 20.5)
check("so main+1 is 23.5, not 26.5", r[0], 23.5)
m, r = M.pick_main1(lad({20.5: (0.47, 0.48), 23.5: (0.52, 0.53)}))
check("a float tie (0.475 v 0.525) is a tie: lower strike", m[0], 20.5)
check("matches nfl_tt's main-line pick on the same ladder",
      M.main_line(lad({17.5: (0.66, 0.68), 20.5: (0.52, 0.54), 24.5: (0.38, 0.40)}))[0],
      N.pick_main(lad({17.5: (0.66, 0.68), 20.5: (0.52, 0.54), 24.5: (0.38, 0.40)}))[0])
m, r = M.pick_main1(list(reversed(lad({20.5: (0.49, 0.51), 23.5: (0.38, 0.40)}))))
check("ladder order does not matter", (m[0], r[0]), (20.5, 23.5))
check("no price band: a 0.22 main+1 (outside 35-45c) is still the pick",
      M.pick_main1(lad({20.5: (0.49, 0.51), 23.5: (0.20, 0.22), 26.5: (0.10, 0.12)}))[1][0], 23.5)
check("an empty ladder: nothing", M.pick_main1([]), (None, None))

print("\nmain+1 is the next QUOTED strike (a rung whose quote fails is not in the ladder)")
e = event({"SF": {21.5: (0.61, 0.63), 24.5: (0.49, 0.51), 27.5: (0.36, 0.44), 30.5: (0.30, 0.32)}})
rows, skips = M.picks_for(e, game(), NOW)
check("the wide 27.5 is skipped over: 30.5", [x["line"] for x in rows], [30.5])

print("\nno rung above the main line: no entry, logged as a skip")
e = event({"SF": {21.5: (0.61, 0.63), 24.5: (0.49, 0.51)}, "WAS": {20.5: (0.52, 0.54), 24.5: (0.38, 0.40)}})
rows, skips = M.picks_for(e, game(), NOW)
check("WSH enters 24.5, SF has nothing above 24.5", [(x["team"], x["line"]) for x in rows], [("WSH", 24.5)])
check("SF's skip is logged with its reason and main line", [(s["team"], s["main_line"], s["reason"]) for s in skips],
      [("SF", 24.5, M.SKIP_NO_ABOVE)])

print("\na run: one frozen entry per team per game, skips logged once")
state = M.empty()
evs = [e]
fetch = lambda path: {"events": evs} if path.startswith("events") else {"market": {"status": "active"}}
log1 = M.run(state, [game()], NOW, fetch=fetch)
log2 = M.run(state, [game()], NOW + dt.timedelta(minutes=10), fetch=fetch)
check("entered once", (len(log1), len(log2)), (1, 0))
check("the skip logged once", len(state["skips"]), 1)
p = state["rules"][M.LANE]["picks"][0]
check("id lane:event:team", p["id"], f"{M.LANE}:{e['event_ticker']}:WSH")
check("price is the ask; main line recorded", (p["price"], p["main_line"], p["main_mid"]), (0.40, 20.5, 0.53))
check("week and lead recorded", (p["week"], p["lead_min"]), ("2026-2-W11", 60.0))
check("outside the window nothing enters",
      M.run(M.empty(), [game()], KO - dt.timedelta(minutes=90), fetch=fetch), [])
check("the window is nfl_tt's", M.WINDOW_MIN, N.WINDOW_MIN)

print("\nsettlement on Kalshi's result, after the 7% taker fee")
check("the fee is 0.07 p (1 - p)", round(M.fee(0.41), 8), round(0.07 * 0.41 * 0.59, 8))
for result, status, profit in (("yes", "won", round(100 * (1 / (0.40 + 0.07 * 0.40 * 0.60) - 1), 2)),
                               ("no", "lost", -100.0)):
    s = M.empty()
    s["rules"][M.LANE]["picks"].append(dict(p, status="open"))
    M.run(s, [], NOW + dt.timedelta(hours=5),
          fetch=lambda path, r=result: {"events": []} if path.startswith("events") else {"market": {"status": "settled", "result": r}})
    q = s["rules"][M.LANE]["picks"][0]
    check(f"{result}: {status} at {profit}", (q["status"], q["profit"]), (status, profit))
a = M.stats([dict(price=0.4, status="won", week="W1", profit=140.0), dict(price=0.4, status="lost", week="W2", profit=-100.0)])
check("stats are nfl_tt's, week-clustered", (a["n"], a["won"], a["weeks"]), (2, 1, 2))

print("\nbaseline: nfl_tt's, over this lane's dates only")
base = N.empty()
base["rules"][N.BASE]["picks"] = [dict(price=0.4, status="won", logged="2026-11-01T17:00:00+00:00", week="W9"),
                                  dict(price=0.4, status="lost", logged="2026-11-08T17:00:00+00:00", week="W10")]
check("only rows logged from the registration day", len(M.baseline_picks(base)), 1)

print("\nthe NFL page row")
s = M.empty()
s["rules"][M.LANE]["picks"] = [dict(p, status="won", profit=135.0)]
html = MB.row_html(M.LANE, s, base)
check("named, a Sandbox rule row", (M.NAMES[M.LANE] in html, 'data-stage="sandbox"' in html,
                                    f'data-source="{M.LANE}"' in html), (True, True, True))
check("evidence reads to 30", 'data-l="Evidence">1/30' in html, True)
check("pre-registration in the fold", ("+6.9%" in html, "z +1.54" in html, "about +6%" in html, "2026-11-08" in html),
      (True, True, True, True))
check("in-sample block labelled, not counted", "NOT counted" in html, True)
check("review at 10, decide at 30", "Review at 10 settled entries, decide at 30" in html, True)
check("no dollar amount, no lane id in the visible copy", ("$" in html, M.LANE in html.replace(f'data-source="{M.LANE}"', "")),
      (False, False))
check("no guarded phrase", sandbox_audit.COPY_RE.search(html + open("nfl_tt_main1.py").read()
                                                       + open("nfl_tt_main1_build.py").read()), None)
M.RETIRED.update(_retired)
check("retired: no entry from 2026-11-11 on", (M.retired(M.LANE, NOW), M.run(M.empty(), [game()], NOW, fetch=fetch)), (True, []))
import nfl_build
built = nfl_build.build()
gone = built[built.find('<section id="retired"'):]
check("the built NFL page has the row in its Retired fold, with its reason",
      (f'data-source="{M.LANE}"' in gone, "Losing: -26% at 26 bets" in gone), (True, True))

print("\nSandbox only")
import sandbox_sources as S
check("not a Sandbox-ledger source", M.LANE in S.SOURCES, False)
check("not in the Production overrides", M.LANE in open("production.py").read(), False)
check("retired 2026-11-11 (Olu, END NFL): the workflow is removed, the ledger kept, its final record in the reason",
      (os.path.exists(".github/workflows/nfl-tt.yml"), os.path.exists(M.PATH), M.RETIRED[M.LANE]["on"], "-26%" in M.RETIRED[M.LANE]["reason"]),
      (False, True, "2026-11-11", True))

print()
if FAILS:
    print(f"{len(FAILS)} FAILED: {FAILS}")
    sys.exit(1)
print("all ok")
