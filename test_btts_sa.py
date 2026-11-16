#!/usr/bin/env python3
"""Offline checks for Brazil and Argentina BTTS YES (btts_sa.py, 2026-11-16): scope, entry window, spread, the NO control,
settlement, the VPS kickoff schedule and the page rows (percentages only)."""
import datetime as dt
import re
import sys

import btts_sa as BS
import lane_windows as W
import sandbox_audit
import soccer_lanes as SL

FAILS = []
UTC = dt.timezone.utc
NOW = dt.datetime(2026, 11, 18, 21, 0, tzinfo=UTC)
KO = NOW + dt.timedelta(minutes=60)


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


def fixture(home, away, league="Brasileirão", ko=KO, played=False):
    return dict(kickoff=ko.strftime("%Y-%m-%dT%H:%MZ"), league=league, home=home, away=away,
                home_goals=None, away_goals=None, played=played, competitive=True)


def ev(series, home, away, yb=0.60, ya=0.61, nb=0.39, na=0.40, day="26NOV18", tag=None):
    tag = tag or f"{series}-{day}{home[:3].upper()}{away[:3].upper()}"
    m = dict(ticker=f"{tag}-BTTS", title="Both Teams To Score", yes_sub_title="Both Teams To Score", status="active",
             yes_bid_dollars=str(yb), yes_ask_dollars=str(ya), no_bid_dollars=str(nb), no_ask_dollars=str(na))
    return dict(event_ticker=tag, title=f"{home} vs {away}: BTTS", markets=[m])


print("scope: Brazil and Argentina BTTS, nothing else")
check("two leagues, two BTTS series", {k: v[1] for k, v in BS.LEAGUES.items()},
      {"Liga Profesional": "KXARGPREMDIVBTTS", "Brasileirão": "KXBRASILEIROBTTS"})
check("lane_windows carries the same map", W.SOCCER_BTTS_SA_SERIES, {k: v[1] for k, v in BS.LEAGUES.items()})
check("a Premier League match is never due", BS.due([fixture("A", "B", league="Premier League")], NOW), [])
check("the pre-registration text is verbatim", BS.PREREG.startswith("Brazil and Argentina BTTS YES. Paper. Every Serie A and Primera match")
      and BS.PREREG.endswith("Retired if it is negative at 100."), True)
doc = open("docs/prereg_btts_bra_arg_2026-11-16.md", encoding="utf-8").read()
check("the prereg doc carries the same text", BS.PREREG in doc.replace("\n", " "), True)

print("\nentry window: 20 to 90 minutes before kickoff")
for mins, want in ((95, 0), (90, 1), (60, 1), (20, 1), (15, 0)):
    check(f"{mins} minutes before: {'due' if want else 'not due'}",
          len(BS.due([fixture("Coritiba", "Santos", ko=NOW + dt.timedelta(minutes=mins))], NOW)), want)
check("a played match is never due", BS.due([fixture("A", "B", played=True)], NOW), [])

print("\nthe quote: YES at the ask, the NO control at its ask, spread 5c or less")
fx = [fixture("Coritiba", "Santos")]
state = BS.load("/nonexistent")
e1 = ev("KXBRASILEIROBTTS", "Coritiba", "Santos")
log = BS.run(state, fx, NOW, fetch=lambda path: {"events": [e1], "cursor": ""})
yes = state["rules"]["YES"]["picks"]
no = state["rules"]["NO"]["picks"]
check("one YES entry at the 0.61 ask", [(p["side"], p["price"], p["ticker"]) for p in yes], [("yes", 0.61, "KXBRASILEIROBTTS-26NOV18CORSAN-BTTS")])
check("one NO control entry at the 0.40 ask", [(p["side"], p["price"]) for p in no], [("no", 0.40)])
check("league key on every entry", {p["league_key"] for p in yes + no}, {"BRA"})
check("the same read again adds nothing", BS.run(state, fx, NOW, fetch=lambda path: {"events": [e1], "cursor": ""}), [])
wide = BS.load("/nonexistent")
BS.run(wide, fx, NOW, fetch=lambda path: {"events": [ev("KXBRASILEIROBTTS", "Coritiba", "Santos", yb=0.55, ya=0.61, nb=0.39, na=0.40)], "cursor": ""})
check("a 6c YES book is no entry, the 1c NO book still is", (len(wide["rules"]["YES"]["picks"]), len(wide["rules"]["NO"]["picks"])), (0, 1))
check("the schedule lists the kickoff for the VPS", state["schedule"], [KO.isoformat()])

print("\nsettlement on Kalshi's own result, profit after the 7% fee")
t = dt.datetime(2026, 11, 19, 5, 0, tzinfo=UTC)
res = lambda r: {"market": {"status": "finalized", "result": r}}  # noqa: E731
BS.SR.settle(state, t, lambda path: res("yes"))
check("YES won, NO lost", ([p["status"] for p in yes], [p["status"] for p in no]), (["won"], ["lost"]))
check("YES profit is 100 * (1 / (0.61 + fee) - 1)", yes[0]["profit"], round(100 * (1 / (0.61 + BS.fee(0.61)) - 1), 2))

print("\nthe VPS window: the same stamp, 90 to 20 minutes before each BTTS kickoff")
k = W.btts_kickoffs(NOW, [fixture("Coritiba", "Santos")])
check("btts_kickoffs finds the Brazil kickoff within a day", k, [KO])
check("soccer_windows opens one window for it", [(w["lane"], w["close"]) for w in W.soccer_windows(NOW, [fixture("Coritiba", "Santos")], {})],
      [("soccer_rules", KO)])
check("the settle stamp reads this ledger", "btts_sa_ledger.json" in W.SETTLE_LANES["soccer_rules_settle"][0], True)

print("\nthe page rows")
live, gone = SL.btts_sa_rows(state)
check("four rows: both leagues, Brazil, Argentina, the NO control", [r["name"] for r in live],
      ["btts_sa_all", "btts_sa_bra", "btts_sa_arg", "btts_sa_no"])
check("none retired", gone, [])
check("Brazil row holds the Brazil bet, Argentina none", [r["a"]["n"] for r in live], [1, 1, 0, 1])
check("the combined row's record is the YES entry", (live[0]["a"]["won"], live[0]["a"]["n"]), (1, 1))
html = " ".join(r["own"]["details"] + r["own"]["entries"] for r in live)
check("public copy has no dollar amount", "$" not in html, True)
check("no guarded public phrase", sandbox_audit.COPY_RE.findall(html), [])
check("the pre-registration text is on the page", BS.PREREG in html.replace("&amp;", "&"), True)
check("the entries show percentages", bool(re.search(r"\+\d+%|−\d+%|-\d+%", html)), True)

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
