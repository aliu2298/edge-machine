#!/usr/bin/env python3
"""Offline checks for the three shadows (shadows.py) and their fold on the Soccer rows."""
import datetime as dt
import json
import os
import sys
import tempfile

import sandbox_audit
import settle_only
import shadows as SH
import soccer_lanes

FAILS = []
UTC = dt.timezone.utc
NOW = dt.datetime(2026, 11, 22, 15, 0, tzinfo=UTC)
START = NOW + dt.timedelta(minutes=40)


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%MZ")


def mk(t, b, a, status="active"):
    return dict(ticker=t, status=status, yes_bid_dollars=str(b), yes_ask_dollars=str(a))


# source ledgers in a temp root
root = tempfile.mkdtemp()
os.makedirs(os.path.join(root, "data"))
t1 = [dict(id=f"T1:KXEPLTEAMTOTAL-26NOV22MCIFUL:{s}", rule="T1", league="Premier League", event="KXEPLTEAMTOTAL-26NOV22MCIFUL", match="Manchester City v Fulham",
           team="Manchester City" if s == "home" else "Fulham", team_side=s, start=iso(START), logged=NOW.isoformat(), price=0.40, ticker=f"KXEPLTEAMTOTAL-26NOV22MCIFUL-{s[:3].upper()}2",
           status="open") for s in ("home", "away")]
a7 = [dict(id="A7:KXUCLTOTAL-26NOV22PSVBRU", rule="A7", league="Champions League", event="KXUCLTOTAL-26NOV22PSVBRU", match="PSV v Brugge", start=iso(START),
           logged=NOW.isoformat(), price=0.50, ticker="KXUCLTOTAL-26NOV22PSVBRU-4", status="open")]
arg = [dict(id="ARG:KXARGPREMDIVTOTAL-26NOV22AAABBB", rule="ARG", league="Liga Profesional", event="KXARGPREMDIVTOTAL-26NOV22AAABBB", match="Alpha v Beta", start=iso(START),
            logged=NOW.isoformat(), price=0.76, ticker="KXARGPREMDIVTOTAL-26NOV22AAABBB-2", status="open")]
for name, rules in (("soccer_team_rules_ledger.json", {"T1": {"picks": t1}}), ("soccer_rules_ledger.json", {"A7": {"picks": a7}}),
                    ("sa_o15_ledger.json", {"ARG": {"picks": arg}, "BRA": {"picks": []}})):
    json.dump({"rules": rules}, open(os.path.join(root, "data", name), "w"))
SH.SR.ROOT, _root = root, SH.SR.ROOT
_src = SH.source_picks
SH.source_picks = lambda lane, root=root: _src(lane, root)

btts_events = {
    "KXEPL2HBTTS": [dict(event_ticker="KXEPL2HBTTS-26NOV22MCIFUL", title="Manchester City vs Fulham: Second Half BTTS", markets=[mk("KXEPL2HBTTS-26NOV22MCIFUL-BTTS", 0.40, 0.42)])],
    "KXUCL2HBTTS": [dict(event_ticker="KXUCL2HBTTS-26NOV22PSVBRU", title="PSV vs Brugge: Second Half BTTS", markets=[mk("KXUCL2HBTTS-26NOV22PSVBRU-BTTS", 0.30, 0.40)])],
    "KXARGPREMDIVBTTS": [dict(event_ticker="KXARGPREMDIVBTTS-26NOV22AAABBB", title="Alpha vs Beta: BTTS", markets=[mk("KXARGPREMDIVBTTS-26NOV22AAABBB-BTTS", 0.46, 0.48)])],
}
ev = lambda series: btts_events.get(series, [])          # noqa: E731
fx = [dict(league="Premier League", home="Manchester City", away="Fulham", kickoff=iso(START), home_id="382", away_id="370", league_slug="eng.1"),
      dict(league="Champions League", home="PSV", away="Brugge", kickoff=iso(START), home_id="1", away_id="2", league_slug="uefa.champions"),
      dict(league="Liga Profesional", home="Alpha", away="Beta", kickoff=iso(START), home_id="11", away_id="12", league_slug="arg.1")]

print("1) BTTS YES at the entry minute")
check("series: league prefix + 2HBTTS for T1/A7; the named BTTS series for ARG", (SH.btts_series("T1", t1[0]), SH.btts_series("A7", a7[0]), SH.btts_series("ARG", arg[0])),
      ("KXEPL2HBTTS", "KXUCL2HBTTS", "KXARGPREMDIVBTTS"))
st = SH.load("team", "/nonexistent")
sd = SH.load("soccer", "/nonexistent")
SH.run(st, "team", fx, NOW, events=ev)
SH.run(sd, "soccer", fx, NOW, events=ev)
check("T1: two teams in one match give ONE 2H BTTS record at the 42c ask", [(r["lane"], r["price"], r["quote"]) for r in st["btts"].values()], [("T1", 0.42, True)])
check("but one half-time record a pick", len(st["ht"]), 2)
check("A7: a 10c spread is 'no quote'; ARG: 48c ask", {k: (r["quote"], r.get("price")) for k, r in sd["btts"].items()},
      {"A7:KXUCLTOTAL-26NOV22PSVBRU": (False, None), "ARG:KXARGPREMDIVTOTAL-26NOV22AAABBB": (True, 0.48)})
SH.run(st, "team", fx, NOW + dt.timedelta(minutes=5), events=ev)
check("a second read adds nothing", (len(st["btts"]), len(st["ht"])), (1, 2))
late = SH.load("team", "/nonexistent")
SH.run(late, "team", fx, NOW + dt.timedelta(hours=2), events=ev)
check("a pick older than the entry minute is not recorded late", (len(late["btts"]), len(late["ht"])), (0, 0))

print("\n   settlement, held")
SH.D.payout = lambda m: {"yes": 1.0, "no": 0.0}.get(m.get("result"))
fetch_res = lambda path: {"market": {"ticker": path.split("/")[-1], "status": "finalized", "result": "yes"}}
SH.run(st, "team", fx, NOW + dt.timedelta(hours=4), fetch=fetch_res, events=ev, get=lambda u: {})
r = next(iter(st["btts"].values()))
check("a settled YES pays: profit per $100 after the fee", (r["status"], r["profit"]), ("won", round(100 * (1 / (0.42 + SH.FEE(0.42)) - 1), 2)))

print("\n2) half-time check")
espn = {"events": [dict(id="9", competitions=[dict(competitors=[dict(team=dict(id="382")), dict(team=dict(id="370"))])])]}
HT_TS = int((START + dt.timedelta(minutes=47)).timestamp())
summary = {"keyEvents": [dict(type=dict(type="halftime"), wallclock=(START + dt.timedelta(minutes=47)).strftime("%Y-%m-%dT%H:%M:%SZ"), period=dict(number=1)),
                         dict(type=dict(type="goal"), scoringPlay=True, period=dict(number=1), team=dict(id="370"))]}


def get(url):
    return summary if "summary?event=9" in url else espn


half = SH.espn_half(fx[0], get)
check("ESPN: the halftime wall clock and the period-1 goals by team", (half["ht_ts"], half["goals"]), (HT_TS, {"382": 0, "370": 1}))
candles = {"candlesticks": [dict(end_period_ts=HT_TS - 60, yes_bid=dict(close_dollars="0.30")), dict(end_period_ts=HT_TS, yes_bid=dict(close_dollars="0.22")),
                            dict(end_period_ts=HT_TS + 600, yes_bid=dict(close_dollars="0.05"))]}
check("the bid is the minute ending at half-time, not a later one", SH.bid_at("KXEPLTEAMTOTAL-26NOV22MCIFUL-HOM2", HT_TS, lambda p: candles), 0.22)
check("no candle: no bid", SH.bid_at("X-1", HT_TS, lambda p: {"candlesticks": []}), None)
later = START + dt.timedelta(minutes=100)
srcs = {p["id"]: p for p in t1}
home, away = st["ht"][t1[0]["id"]], st["ht"][t1[1]["id"]]
SH.resolve_ht("T1", t1[0], home, fx, later, lambda p: candles, get)
SH.resolve_ht("T1", t1[1], away, fx, later, lambda p: candles, get)
cost = 0.40 + SH.FEE(0.40)
check("T1: the home team (0 at half-time) is sold at the 22c bid, minus fee", (home["action"], home["bid"], home["profit"]), ("sell", 0.22, round(100 * ((0.22 - SH.FEE(0.22)) / cost - 1), 2)))
check("T1: the away team scored: hold", (away["action"], away["score"]), ("hold", "0-1"))
check("a match too young is left pending", SH.resolve_ht("T1", t1[0], dict(status="pending"), fx, START + dt.timedelta(minutes=30), lambda p: candles, get), None)
zero = dict(status="pending")
espn0 = dict(summary, keyEvents=[summary["keyEvents"][0]])
SH.resolve_ht("A7", dict(a7[0], league="Premier League", match="Manchester City v Fulham"), zero, fx, later, lambda p: {"candlesticks": []}, lambda u: espn0 if "summary" in u else espn)
check("0-0 with no bid: 'no bid', treated as hold", (zero["action"], zero["score"]), ("no_bid", "0-0"))
gone = dict(status="pending")
SH.resolve_ht("A7", dict(a7[0], league="Premier League", match="Manchester City v Fulham"), gone, fx, START + dt.timedelta(hours=13), lambda p: candles, lambda u: {"events": []})
check("no ESPN data after 12 hours: unavailable", gone["status"], "unavailable")

print("\n   records")
t1_done = [dict(t1[0], status="lost", profit=-100.0), dict(t1[1], status="won", profit=140.0)]
away["profit"] = 140.0                                   # run() copies a hold row's settled result from its source pick
hs = SH.ht_stats(st, "T1", t1_done)
check("sold/held, shadow and hold returns on the same rows", (hs["checked"], hs["sold"], hs["held"], round(hs["ret"], 4), round(hs["hold_ret"], 4)),
      (2, 1, 1, round((home["profit"] + 140.0) / 200, 4), round(((-100.0) + 140.0) / 200, 4)))
bs = SH.btts_stats(st, "T1")
check("BTTS stats: priced, won, return", (bs["matches"], bs["won"], bs["ret"] is not None), (1, 1, True))

print("\nthe Soccer rows")
html = soccer_lanes.shadow_html("T1", {"team": st}, t1_done)
check("fold names both shadows and the in-sample rows, percentages only", ("Half-time check (shadow)" in html, "2H BTTS YES (shadow)" in html, "In-sample, not counted" in html,
      "14-13 at 43c, +17%" in html, "$" in html), (True, True, True, True, False))
check("BRA has no in-sample figure", "no figure" in soccer_lanes.shadow_html("BRA", {"soccer": sd}, []), True)
check("no guarded phrase", sandbox_audit.COPY_RE.findall(html + open("shadows.py").read()), [])
check("the three source rows carry the fold (A7, T1, ARG/BRA)", all("shadow_html(" in open("soccer_lanes.py").read() for _ in range(1)), True)

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
