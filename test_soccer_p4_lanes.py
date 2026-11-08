#!/usr/bin/env python3
"""Offline checks for soccer_p4_lanes (2026-11-08): the point-in-time labels (no fixture at or after kickoff counts), the
T-1h mid NO, half-time from the 1st-half market's close, goals timed by the spread market's own price, the minute-75
moment only with the score unchanged since half-time, the label filters and their label-blind baselines, the taker depth
rule and maker variant, the fresh record (no match before registration), one read per match, and the Soccer page rows."""
import datetime as dt
import sys

import sandbox_audit
import soccer_p4_build as PB
import soccer_p4_lanes as P

FAILS = []
UTC = dt.timezone.utc


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


def iso(t):
    return dt.datetime.fromtimestamp(t, UTC).isoformat().replace("+00:00", "Z")


print("pure pieces")
check("the study's fee: 7% of p(1-p) on a $1 stake, rounded up to the cent", (P.fee(0.55, 0.07), P.fee(0.88, 0.07)), (0.02, 0.01))
check("half-time: the 1st-half correct-score close when it reads as the whistle, else the 1st-half spread's",
      (P.half_time(0, (47 * 60, 46 * 60)), P.half_time(0, (90 * 60, 46 * 60)), P.half_time(0, (None, 30 * 60))), (2820, 2760, None))
est = P.goal_estimates([(1, 1200, "home"), (2, 3000, "away"), (3, 10, "home"), (1, None, "home")], 0, 2820)
check("goal clock estimates: 1st half from kickoff, 2nd from half-time + 15 min; extra periods and clockless goals out",
      est, [(1200, "home", 1), (2820 + 900 + 300, "away", 2)])
check("minute 75 = half-time + 45 min, only with the score unchanged since half-time",
      (P.m75_moment(0, 2820, [(1200, "home", 1)]), P.m75_moment(0, 2820, [(1200, "home", 1), (5000, "away", 2)]),
       P.m75_moment(0, None, [])), (2820 + 2700, None, None))
ss = lambda side, t: 0.21 if t >= 1260 else 0.11     # noqa: E731
check("a goal is timed at the first minute its scorer's spread mids jump 4c+", P.time_goals([(1200, "home", 1)], ss), [1260])
check("no 4c jump: untimed", P.time_goals([(1200, "home", 1)], lambda s, t: 0.11 + (0.02 if t >= 1260 else 0)), [None])
check("v2: an untimed goal near the entry fails the state check",
      (P.valid_v2([(1200, "home", 1)], [1260], 5000, True), P.valid_v2([(1200, "home", 1)], [None], 5000, True),
       P.valid_v2([(1200, "home", 1)], [1260], 5000, False)), (True, False, False))
rows = [[60, 0.40, 0.42, 0, 0, 0, 0, 0], [180, 0.50, 0.52, 0, 0, 0, 0, 0]]
check("in play, a quote older than 3 minutes is not used; before kickoff it is",
      (P.quote(rows, 180 + 181, None, True), P.quote(rows, 180 + 181, None, False)), (None, (0.50, 0.52)))
check("a wide quote, or one within a minute of the close, is not used",
      (P.quote([[60, 0.40, 0.46, 0, 0, 0, 0, 0]], 60, None, False), P.quote(rows, 150, 200, False)), (None, None))
check("Kalshi names to ESPN sides", (P.team_of("Arsenal wins by more than 1.5 goals", "Arsenal", "Chelsea"),
                                     P.team_of("Chelsea", "Arsenal", "Chelsea")), ("home", "away"))
L = {"p4_mid_no": P.BY_LANE["p4_mid_no"], "over": P.BY_LANE["p4_late_over"], "under": P.BY_LANE["p4_late_under"]}
check("Mid NO Mismatch: the market's team O+D+, its opponent O−D+ (ordered)",
      (P.wants(L["p4_mid_no"], dict(home="O+D+", away="O-D+"), "home"), P.wants(L["p4_mid_no"], dict(home="O+D+", away="O-D+"), "away"),
       P.wants(L["p4_mid_no"], dict(home="O-D+", away="O+D+"), "away")), (True, False, True))
check("Late Over Calm: both labelled, neither D+",
      (P.wants(L["over"], dict(home="O+D-", away="O-D-")), P.wants(L["over"], dict(home="O+D-", away="O-D+")),
       P.wants(L["over"], dict(home="O+D-", away=None))), (True, False, False))
check("Late Under Leaky: both D+",
      (P.wants(L["under"], dict(home="O+D+", away="O-D+")), P.wants(L["under"], dict(home="O+D+", away="O-D-"))), (True, False))
check("baselines take every row", all(P.wants(P.BY_LANE[b], {}, None) for b in P.BASELINE.values()), True)
t, m = P.fills(dict(ts=0, ask=0.55, bid=0.53, side="no"), [(10, 0.46, 30.0), (200, 0.45, 20.0), (400, 0.40, 99.0), (500, 0.48, 1.0)], False)
check("taker: 50 contracts at or through the NO ask within 5 minutes (a NO print = 1 - YES)", (t["filled"], t["depth"]), (True, 50.0))
check("taker ROI held to settlement after the rounded fee", (t["cost"], t["roi"]), (0.57, -1.0))
check("maker: a print through the NO bid within 15 minutes fills at the bid", m["filled"], True)
t, _ = P.fills(dict(ts=0, ask=0.52, bid=0.50, side="yes"), [(10, 0.52, 49.0), (20, 0.53, 500.0)], True)
check("49 contracts at the ask (a print above it is not through it) is no fill", t["filled"], False)

print("\nthe run on one synthetic match")
KO = int(dt.datetime(2026, 11, 14, 15, 0, tzinfo=UTC).timestamp())
EV, EARLY = "KXEPLGAME-26NOV14ARSCHE", "KXEPLGAME-26NOV08LIVMCI"
SUF = EV.split("-", 1)[1]
HT = KO + 47 * 60
CLOSE = KO + 2 * 3600
GOAL = KO + 1260                                       # Arsenal score at 20' (clock 1200 s), the spread jumps a minute later
YQ = {
    f"{EV}-ARS": (0.45, 0.47), f"{EV}-CHE": (0.28, 0.30), f"{EV}-TIE": (0.24, 0.26),
    f"KXEPLTOTAL-{SUF}-1": (0.97, 0.98), f"KXEPLTOTAL-{SUF}-2": (0.50, 0.52), f"KXEPLTOTAL-{SUF}-3": (0.12, 0.14),
    f"KXEPLSPREAD-{SUF}-CHE2": (0.03, 0.05),
}


def yq(tk, t):
    if tk == f"KXEPLSPREAD-{SUF}-ARS2":
        return (0.20, 0.22) if t >= GOAL else (0.10, 0.12)
    return YQ[tk]


M = lambda tk, name, res, close=CLOSE, strike=None: dict(ticker=tk, yes_sub_title=name, result=res, status="finalized",   # noqa: E731
                                                         close_time=iso(close), floor_strike=strike)
MARKETS = {
    EV: [M(f"{EV}-ARS", "Arsenal", "yes"), M(f"{EV}-CHE", "Chelsea", "no"), M(f"{EV}-TIE", "Tie", "no")],
    f"KXEPLTOTAL-{SUF}": [M(f"KXEPLTOTAL-{SUF}-1", "Over 0.5 goals scored", "yes", strike=0.5),
                          M(f"KXEPLTOTAL-{SUF}-2", "Over 1.5 goals scored", "no", strike=1.5),
                          M(f"KXEPLTOTAL-{SUF}-3", "Over 2.5 goals scored", "no", strike=2.5)],
    f"KXEPLSPREAD-{SUF}": [M(f"KXEPLSPREAD-{SUF}-ARS2", "Arsenal wins by more than 1.5 goals", "no", strike=1.5),
                           M(f"KXEPLSPREAD-{SUF}-CHE2", "Chelsea wins by more than 1.5 goals", "no", strike=1.5)],
    f"KXEPL1HSCORE-{SUF}": [M(f"KXEPL1HSCORE-{SUF}-1", "Arsenal wins 1H 1-0", "yes", close=HT)],
    EARLY: [M(f"{EARLY}-LIV", "Liverpool", "yes"), M(f"{EARLY}-MCI", "Manchester City", "no"), M(f"{EARLY}-TIE", "Tie", "no")],
}
TRADES = {f"{EV}-ARS": [(100, "0.46", "60")], f"KXEPLTOTAL-{SUF}-2": [(100, "0.52", "40")],
          f"KXEPLTOTAL-{SUF}-3": [(100, "0.12", "80")]}
calls = []


def fetch(path, *a, **k):
    calls.append(path)
    if path.startswith("events?"):
        if "KXEPLGAME" in path:
            return {"events": [{"event_ticker": EV}, {"event_ticker": EARLY}], "cursor": ""}
        return {"events": [], "cursor": ""}
    if "markets?limit=200&event_ticker=" in path:
        ev = path.split("event_ticker=")[1].split("&")[0]
        return {"markets": [] if "historical" in path else MARKETS.get(ev, []), "cursor": ""}
    if "candlesticks" in path:
        ev = path.split("/events/")[1].split("/")[0]
        lo = int(path.split("start_ts=")[1].split("&")[0])
        hi = int(path.split("end_ts=")[1].split("&")[0])
        tick = [m["ticker"] for m in MARKETS[ev]]
        cs = [[dict(end_period_ts=t, yes_bid=dict(close_dollars=str(yq(x, t)[0])), yes_ask=dict(close_dollars=str(yq(x, t)[1])),
                    volume_fp="10") for t in range(lo - lo % 60 + 60, hi, 60)] for x in tick]
        return {"market_tickers": tick, "market_candlesticks": cs}
    if "trades?" in path:
        tk = path.split("ticker=")[1].split("&")[0]
        lo = int(path.split("min_ts=")[1].split("&")[0])
        return {"trades": [dict(created_time=iso(lo + dtt), yes_price_dollars=px, count_fp=n) for dtt, px, n in TRADES.get(tk, [])],
                "cursor": ""}
    return {}


def team(name, tid, ha):
    return dict(homeAway=ha, team=dict(displayName=name, shortDisplayName=name, id=tid))


def board(day):
    g = lambda gid, t, h, a: dict(id=gid, date=iso(t), competitions=[dict(status=dict(type=dict(completed=True)),   # noqa: E731
                                                                         competitors=[h, a])])
    return [g("e1", KO, team("Arsenal", "359", "home"), team("Chelsea", "363", "away")),
            g("e0", int(dt.datetime(2026, 11, 8, 16, 30, tzinfo=UTC).timestamp()), team("Liverpool", "364", "home"),
              team("Manchester City", "382", "away"))]


def summary(gid):
    return {"keyEvents": [dict(scoringPlay=True, period=dict(number=1), clock=dict(value=1200.0), team=dict(id="359"))]}


def fx(t, h, a, hg, ag, hid=None, aid=None):
    return dict(kickoff=iso(t), league="Premier League", home=h, away=a, home_id=hid or h, away_id=aid or a, home_goals=hg,
                away_goals=ag, played=True, competitive=True)


DAY = 86400
FIX = [fx(KO - (40 + i) * DAY, f"T{i}", f"U{i}", 1, 1) for i in range(30)]                 # league mean 1.0 goal per team
FIX += [fx(KO - (i + 1) * 7 * DAY, "Arsenal", f"V{i}", 2, 2, hid="359") for i in range(10)]      # Arsenal O+D+
FIX += [fx(KO - (i + 1) * 7 * DAY - DAY, f"W{i}", "Chelsea", 2, 0, aid="363") for i in range(10)]  # Chelsea O-D+
FUTURE = [fx(KO, "Arsenal", "Chelsea", 1, 0, "359", "363"),                                     # the match itself
          fx(KO + 3 * DAY, "Arsenal", "X", 0, 6, hid="359"), fx(KO + 4 * DAY, "Y", "Chelsea", 0, 9, aid="363")]
fx_calls = []


def fixtures():
    fx_calls.append(1)
    return FIX + FUTURE


g = dict(date=iso(KO), teams=dict(home=dict(id="359", name="Arsenal"), away=dict(id="363", name="Chelsea")))
check("labels from fixtures before kickoff: Arsenal O+D+, Chelsea O−D+",
      P.labels_for(FIX, "Premier League", g), ("O+D+", "O-D+"))
check("look-ahead: the match itself and later games change nothing",
      P.labels_for(FIX + FUTURE, "Premier League", g), P.labels_for(FIX, "Premier League", g))
check("fewer than 6 prior matches: no label", P.labels_for(FIX[:30] + FIX[30:35], "Premier League", g)[0], None)

now = dt.datetime(2026, 11, 16, tzinfo=UTC)
st = P.run(P.empty(), now=now, fetch=fetch, fixtures_fn=fixtures, board_fn=board, summary_fn=summary)
check("the match is read; the one that kicked off before registration is skipped as in-sample",
      ([x["event"] for x in st["matches"]], list(st["skips"].values()), st["error"]),
      ([EV], ["kicked off before the lanes were registered (in-sample, not replayed)"], None))
rec = st["matches"][0]
check("labels frozen on the match, fixtures read once", (rec["labels"], len(fx_calls)), (dict(home="O+D+", away="O-D+"), 1))
check("half-time from the 1st-half market's close; the goal price-timed", (rec["ht"], rec["goals"], rec["timed"]), (HT, 1, 1))
pre = [e for e in rec["entries"] if e["mom"] == "pre"]
check("T-1h: only Arsenal's NO is inside 36-64c (Chelsea's is 72c, the tie is never taken)",
      [(e["ticker"].rsplit("-", 1)[1], e["ts"], e["ask"], e["team"]) for e in pre], [("ARS", KO - 3600, 0.55, "home")])
late = [e for e in rec["entries"] if e["mom"] == "m75"]
check("minute 75 (1-0 since half-time): over 1.5 YES 52c and over 2.5 NO 88c; over 0.5 is already won and skipped",
      sorted((e["ticker"].rsplit("-", 1)[1], e["side"], e["ask"], e["ts"], e["score"]) for e in late),
      [("2", "yes", 0.52, HT + 2700, "1-0"), ("3", "no", 0.88, HT + 2700, "1-0")])
check("fills: Arsenal NO and the over 2.5 NO filled on depth, the over 1.5 YES (40 contracts) did not",
      sorted((e["ticker"].rsplit("-", 1)[1], e["taker"]["filled"], e["won"]) for e in rec["entries"]),
      [("2", False, False), ("3", True, True), ("ARS", True, False)])
n = len(calls)
P.run(st, now=now, fetch=fetch, fixtures_fn=fixtures, board_fn=board, summary_fn=summary)
check("a second run reads no match again", [p for p in calls[n:] if not p.startswith("events?")], [])
pend = P.run(P.empty(), now=dt.datetime(2026, 11, 15, tzinfo=UTC), fetch=fetch, fixtures_fn=fixtures, board_fn=lambda d: [],
             summary_fn=summary)
check("no ESPN match yet: retried within 3 days of the date code, skipped for good after",
      (pend["matches"], sorted(pend["skips"])), ([], [EARLY]))

print("\nthe record")
S = lambda lane: P.summary(P.rows_for(st, lane))   # noqa: E731
check("Mid NO Mismatch: one settled entry, lost; its baseline the same row",
      ((S("p4_mid_no")["n"], S("p4_mid_no")["won"]), S("p4_mid_no_all")["n"]), ((1, 0), 1))
check("Late Under Leaky: both teams D+, one settled entry, won; its baseline the same row",
      ((S("p4_late_under")["n"], S("p4_late_under")["won"]), S("p4_late_under_all")["n"]), ((1, 1), 1))
check("Late Over Calm: a D+ team in the match, so no row; the baseline logs the no-fill row",
      (S("p4_late_over")["logged"], S("p4_late_over_all")["logged"], S("p4_late_over_all")["n"]), (0, 1, 0))
st2 = dict(st, matches=[dict(rec, labels=dict(home="O+D-", away="O-D-"))])
check("relabelled O+D− v O−D−: in Late Over Calm and out of the other two lanes, baselines unchanged",
      tuple(P.summary(P.rows_for(st2, x))["logged"] for x in ("p4_late_over", "p4_late_under", "p4_mid_no", "p4_mid_no_all")),
      (1, 0, 0, 1))
check("reads: early, review, decide", (P.read_of(3)[:9], P.read_of(12)[:6], P.read_of(30)), ("too early", "review", "decide"))

print("\nthe Soccer page rows")
rows = PB.rows(st)
check("three rows with the frozen ids and names, Sandbox not Production",
      [(r["name"], r["own"]["label"], r["prod"]) for r in rows],
      [("p4_mid_no", "Mid NO Mismatch", False), ("p4_late_over", "Late Over Calm", False),
       ("p4_late_under", "Late Under Leaky", False)])
details = "".join(r["own"]["details"] for r in rows)
check("each fold carries the research (live, halves, holdout), the shuffled-null note, the record and the baseline",
      all(x in details for x in ("Discovery", "Halves", "August holdout", "Shuffled-label null", "WATCH forward tests",
                                 "Maker variant", "Entries", "Baseline · match winner NO", "Baseline · over YES",
                                 "Baseline · under NO")), True)
words = details + "".join(r["own"]["label"] + r["meta"]["note"] for r in rows)
check("public copy: the rows' words pass the copy guard", bool(sandbox_audit.COPY_RE.search(words)), False)
check("no dollar amounts on the page words", "$" in words, False)
check("pinned: the three rows lead the Sandbox list, above a row with more evidence",
      sorted(r["name"] for r in sorted(rows + [dict(rows[0], name="other", pin=False, a=dict(rows[0]["a"], n=40, roi_fee=0.1))],
                                 key=__import__("sport_page").sandbox_order)[:3]), ["p4_late_over", "p4_late_under", "p4_mid_no"])
import soccer_lanes
check("the Soccer page's own-ledger rows include the three lanes",
      "soccer_p4_build.rows()" in open(soccer_lanes.__file__).read(), True)

if FAILS:
    print(f"\nFAILED {len(FAILS)}")
    sys.exit(1)
print("\nall ok")
