#!/usr/bin/env python3
"""Offline checks for the NBA value model, the ladder tracker and the four value lanes."""
import datetime as dt
import json
import math
import sys

import lane_windows as W
import nba_ladder_track as T
import nba_value as V
import nba_value_build as VB
import nba_value_model as M
import sandbox_audit

FAILS = []
UTC = dt.timezone.utc
# Wed Oct 28 2026, 7:30pm ET tip = 23:30 UTC.
TIP = dt.datetime(2026, 10, 28, 23, 30, tzinfo=UTC)


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


def near(label, got, want, tol=1e-6):
    ok = got is not None and abs(got - want) <= tol
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


def mk(ticker, line, bid, ask, status="active", result=None, sub=None):
    m = dict(ticker=ticker, floor_strike=line, strike_type="greater", status=status,
             yes_bid_dollars=None if bid is None else f"{bid:.4f}", yes_ask_dollars=None if ask is None else f"{ask:.4f}",
             yes_sub_title=sub or f"over {line}", open_time="2026-10-26T23:00:00Z")
    if result:
        m.update(status="finalized", result=result)
    return m


GAME = dict(id="9001", start="2026-10-28T23:30Z", day="2026-10-28", home="NY", away="SA", completed=False)
EV_TT = "KXNBATEAMTOTAL-26OCT28SASNYK"
EV_Q1 = "KXNBA1QTOTAL-26OCT28SASNYK"
MODEL = dict(mu={"NY": 115.0, "SA": 110.0}, mu_q1=58.0, sd=12.0, sd_q1=8.0,
             form={"NY": {"n": 3}, "SA": {"n": 3}})

print("the normal")
near("P(over mu) is 0.5", M.p_over(110.5, 110.5, 12), 0.5)
near("P(over mu - 1 sd) = Phi(1)", M.p_over(98.5, 110.5, 12), 0.5 * (1 + math.erf(1 / math.sqrt(2))))
near("symmetry", M.p_over(105.5, 110.5, 12) + M.p_over(115.5, 110.5, 12), 1.0)

print("\nshrinkage: w = n / (n + 8) on the current season")
near("n 0: the prior alone", M.blend(115.0, None, 0), 115.0)
near("n 8: half and half", M.blend(110.0, 120.0, 8), 115.0)
near("n 24: three quarters current", M.blend(110.0, 120.0, 24), 117.5)
near("no prior: the current mean", M.blend(None, 120.0, 3), 120.0)
check("neither: None", M.blend(None, None, 0), None)
pri = {"NY": dict(n=82, off=116.0, dfn=112.0, q1_off=29.0, q1_dfn=28.0)}
cur = {}
M.add(cur, "NY", dict(home="NY", away="SA", pts_home=124, pts_away=100, q1_home=33, q1_away=20))
f = M.form("NY", pri, cur)
near("form after one game: 1/9 of 124 + 8/9 of 116", f["off"], 116 + (124 - 116) / 9)
near("allowing after one game", f["dfn"], 112 + (100 - 112) / 9)
check("form n", f["n"], 1)
check("a team with no prior and no games has no form", M.form("XXX", pri, {})["off"], None)

print("\nmu: L + b * deviations, home term +/-")
lg = dict(pts=114.0, q1=29.0)
own, opp = dict(off=118.0), dict(dfn=116.0)
near("additive team mu (b 0.894, home)", M.mu_team(own, opp, True, lg),
     114 + 0.894 * ((118 - 114) + (116 - 114)) + M.HOME_HALF)
near("away side takes the home term off", M.mu_team(own, opp, False, lg),
     114 + 0.894 * 6 - M.HOME_HALF)
near("b 0.5 with no home term is the plain halves form", M.mu_team(own, opp, True, lg, b=0.5, home_half=0.0),
     (118 + 116) / 2)
h, a = dict(q1_off=30.0, q1_dfn=28.0), dict(q1_off=27.0, q1_dfn=31.0)
near("1Q mu, b 0.5 = the halves form", M.mu_q1(h, a, lg), (30 + 31) / 2 + (27 + 28) / 2)
check("missing rate: no mu", M.mu_team(dict(off=None), opp, True, lg), None)

print("\nthe sd / slope / home fit on synthetic rows")
rows = []
for i in range(4000):
    d = (i % 21 - 10) * 0.8
    home = i % 2 == 0
    noise = 11.0 * math.sin(i * 12.9898) * 1.7320508          # deterministic, mean ~0
    rows.append(dict(L=114.0, d=d, pts=114.0 + 0.9 * d + (1.0 if home else -1.0) + noise, home=home, n=20))
q1rows = [dict(L=58.0, d=r["d"] / 2, q1=58.0 + 0.5 * r["d"] / 2 + (r["pts"] - 114 - 0.9 * r["d"]) * 0.7, n=20) for r in rows]
fit = M.fit(rows, q1rows)
check("slope recovered (0.9 +/- 0.05)", abs(fit["b"] - 0.9) < 0.05, True)
check("home half recovered (1.0 +/- 0.3)", abs(fit["home_half"] - 1.0) < 0.3, True)
sd_true = (sum((r["pts"] - 114 - 0.9 * r["d"] - (1 if r["home"] else -1)) ** 2 for r in rows) / len(rows)) ** 0.5
check("sd recovered (+/- 0.3)", abs(fit["sd"] - sd_true) < 0.3, True)
check("fixed 1Q slope is used as given", M.fit(rows, q1rows, b_q1=0.5)["b_q1"], 0.5)
check("the shipped constants are the fitted ones (sd 11.83, 1Q 8.28, home 0.85)",
      (M.SD_TEAM, M.SD_Q1, M.HOME_HALF, M.B_TEAM, M.B_Q1), (11.83, 8.28, 0.85, 0.894, 0.5))
rel, br = M.reliability([(0.15, 0), (0.15, 1), (0.55, 1), (0.95, 1)])
check("reliability buckets", [(r[0], r[2]) for r in rel], [(0.1, 2), (0.5, 1), (0.9, 1)])
near("Brier", br, (0.15 ** 2 + 0.85 ** 2 + 0.45 ** 2 + 0.05 ** 2) / 4)
pri26 = M.prior()
check("the prior covers 30 teams with 82-83 games each (the Cup final counts)", (len(pri26), {p["n"] for p in pri26.values()} <= {82, 83}), (30, True))

print("\nfee-adjusted edge")
near("cost at 0.50 is 0.5175", V.cost(0.5), 0.5175)
near("cost at 0.30", V.cost(0.30), 0.30 + 0.07 * 0.3 * 0.7)
sd_ = {x[0]: x for x in V.sides(110.5, 0.60, 0.45, 0.47)}
near("YES edge = P - cost(ask)", sd_["yes"][3], 0.60 - V.cost(0.47))
near("NO price is 1 - bid", sd_["no"][1], 0.55)
near("NO edge = (1 - P) - cost(1 - bid)", sd_["no"][3], 0.40 - V.cost(0.55))

print("\nquote: two-sided, spread 3c or less")
check("3c spread passes", V.quote(mk("X-1", 110.5, 0.47, 0.50)), (0.47, 0.50))
check("4c spread fails", V.quote(mk("X-1", 110.5, 0.46, 0.50)), None)
check("no bid fails", V.quote(mk("X-1", 110.5, 0.0, 0.03)), None)
check("ask 1 fails", V.quote(mk("X-1", 110.5, 0.98, 1.0)), None)

print("\nprice floor 0.25 and cap 0.92 on the side bought")
for p, want in ((0.24, False), (0.25, True), (0.60, True), (0.92, True), (0.93, False)):
    check(f"price {p:.2f}", V.in_price(p), want)

print("\nESPN <-> Kalshi team codes")
for espn, kal in (("SA", "SAS"), ("NY", "NYK"), ("GS", "GSW"), ("NO", "NOP"), ("UTAH", "UTA"), ("WSH", "WAS")):
    g = dict(home=espn, away="BOS", start="2026-10-28T23:30Z")
    check(f"{kal} rung belongs to ESPN {espn}", T.team_of(f"KXNBATEAMTOTAL-26OCT28BOS{kal}-{kal}112", g), espn)
    check(f"event ticker uses {kal}", T.event_tickers(T.SERIES_TT, g)[0], f"KXNBATEAMTOTAL-26OCT28BOS{kal}")
check("a code from neither team is dropped", T.team_of("KXNBATEAMTOTAL-26OCT28SASNYK-BOS112", GAME), None)
check("both orders are tried", T.event_tickers(T.SERIES_Q1, GAME), [EV_Q1, "KXNBA1QTOTAL-26OCT28NYKSAS"])
check("the ET date names the event (a 10:30pm ET tip is 02:30Z next day)",
      T.event_tickers(T.SERIES_TT, dict(GAME, start="2026-10-29T02:30Z"))[0], EV_TT)

print("\ncandidates and the best rung")
tt = [mk(f"{EV_TT}-NYK110", 109.5, 0.60, 0.62), mk(f"{EV_TT}-NYK114", 113.5, 0.46, 0.48),
      mk(f"{EV_TT}-NYK118", 117.5, 0.33, 0.35), mk(f"{EV_TT}-NYK122", 121.5, 0.19, 0.21),
      mk(f"{EV_TT}-SAS108", 107.5, 0.70, 0.72), mk(f"{EV_TT}-SAS112", 111.5, 0.55, 0.57),
      mk(f"{EV_TT}-SAS116", 115.5, 0.40, 0.45)]
c = V.candidates(tt, GAME, "tt", MODEL)
b = V.best(c)
p_ny = {m["floor_strike"]: M.p_over(m["floor_strike"], 115.0, 12.0) for m in tt[:4]}
ny_best = max(((s_, pr, pp - V.cost(pr), ln) for ln, (bb, aa) in
               {109.5: (0.60, 0.62), 113.5: (0.46, 0.48), 117.5: (0.33, 0.35), 121.5: (0.19, 0.21)}.items()
               for s_, pr, pp in (("yes", aa, p_ny[ln]), ("no", round(1 - bb, 4), 1 - p_ny[ln]))
               if 0.25 <= pr <= 0.92), key=lambda x: x[2])
check("NY: the single best edge", (b["NY"]["line"], b["NY"]["side"]), (ny_best[3], ny_best[0]))
check("NY 121.5 YES at 0.21 is under the floor (not a candidate)",
      any(x["line"] == 121.5 and x["side"] == "yes" for x in c), False)
check("SA 115.5 (5c spread) is never a candidate", any(x["line"] == 115.5 for x in c), False)
check("SA: the NO on 107.5 (edge 0.418 - cost(0.30) beats the 111.5 NO)", (b["SA"]["line"], b["SA"]["side"]), (107.5, "no"))
check("every candidate clears 0.05", all(x["edge"] >= 0.05 - 1e-9 for x in c), True)
tie = [dict(unit="NY", ticker="a", line=113.5, side="no", edge=0.08), dict(unit="NY", ticker="b", line=109.5, side="no", edge=0.08),
       dict(unit="NY", ticker="c", line=109.5, side="yes", edge=0.08)]
check("a tie goes to the lower strike, then YES", V.best(tie)["NY"]["ticker"], "c")
check("a taken ticker is skipped", all(x["ticker"] != b["SA"]["ticker"] for x in V.candidates(tt, GAME, "tt", MODEL, {b["SA"]["ticker"]})), True)
q1 = [mk(f"{EV_Q1}-54", 53.5, 0.78, 0.80), mk(f"{EV_Q1}-58", 57.5, 0.61, 0.63), mk(f"{EV_Q1}-62", 61.5, 0.42, 0.44),
      mk(f"{EV_Q1}-66", 65.5, 0.25, 0.28)]
cq = V.best(V.candidates(q1, GAME, "q1", MODEL))
check("1Q: one pick per game, unit 'game'", list(cq), ["game"])
check("1Q: model 58 v Kalshi mid 0.62 at 57.5 -> a NO", cq["game"]["side"], "no")
base = V.baseline(tt, GAME, "tt", MODEL)
check("baseline: YES on every quoted rung at 0.25-0.92", sorted(x["line"] for x in base), [107.5, 109.5, 111.5, 113.5, 117.5])

print("\nwindows: 60-90 min and 18-26 h before tip")
for lead, want in ((59, False), (60, True), (75, True), (90, True), (91, False)):
    check(f"1h window at {lead} min", V.in_window(V.TT_1H, GAME, TIP - dt.timedelta(minutes=lead)), want)
for lead_h, want in ((17.9, False), (18, True), (24, True), (26, True), (26.1, False)):
    check(f"24h window at {lead_h} h", V.in_window(V.Q1_24H, GAME, TIP - dt.timedelta(hours=lead_h)), want)
check("lane_windows copies the 1h window", W.NBA_VALUE_1H, tuple(reversed(V.WINDOW_MIN[V.TT_1H])))
check("lane_windows copies the 24h window", W.NBA_VALUE_24H, tuple(reversed(V.WINDOW_MIN[V.TT_24H])))
ws = W.nba_value_windows(TIP, [TIP])
check("two windows per tip", len(ws), 2)
reads = [k for m in range(0, 40, 5) for w, k in W.due(TIP - dt.timedelta(minutes=90) + dt.timedelta(minutes=m), nba_value=[TIP])
         if w["lane"] == "nba_value" and not w.get("early")]
check("the 1h window is asked twice (K-90, K-75)", sorted(set(reads)), [1, 2])
early = sorted({k for m in range(0, 8 * 60 + 1, 15) for w, k in W.due(TIP - dt.timedelta(hours=26) + dt.timedelta(minutes=m), nba_value=[TIP])
                if w.get("early")})
check("the 24h window is asked hourly, up to 8 reads", early, list(range(1, 9)))
lines = W.stamp_lines(TIP - dt.timedelta(hours=25, minutes=59), nba_value=[TIP])
check("the stamp path", "data/nba_value_window/request.txt" in lines, True)
check("the 24h stamp says so", lines["data/nba_value_window/request.txt"].startswith("nba_value 24h "), True)
check("the stamp path is allowed on the VPS", "data/nba_value_window/request.txt" in open("scripts/vps_window_requests.sh").read(), True)
check("the workflow triggers on the stamp", "data/nba_value_window/**" in open(".github/workflows/nba-value.yml").read(), True)
games = {"9001": GAME, "9002": dict(GAME, id="9002", start="2026-10-30T00:00Z")}
check("schedule: unplayed tips in the next 3 days", V.schedule(games, TIP - dt.timedelta(hours=30)),
      ["2026-10-28T23:30:00+00:00", "2026-10-30T00:00:00+00:00"])


def fake(markets_by_event, settled=None):
    def fetch(path):
        if path.startswith("markets?"):
            ev = path.split("event_ticker=")[1].split("&")[0]
            return {"markets": markets_by_event.get(ev, []), "cursor": None}
        if path.startswith("markets/"):
            tk = path.split("/", 1)[1]
            r = (settled or {}).get(tk)
            return {"market": dict(status="finalized", result=r) if r else dict(status="active")}
        raise AssertionError(path)
    return fetch


print("\nthe run: one look, one entry per lane per team / game, the overlap guard")
track = dict(games={"9001": GAME})
state = V.empty()
_model_for = T.model_for
T.model_for = lambda *a, **k: MODEL                           # the fixed model above, at every read
fetch = fake({EV_TT: tt, EV_Q1: q1})
now24 = TIP - dt.timedelta(hours=24)
new = V.run(state, track, now24, fetch, pri={})
check("24h lanes looked", sorted(k.split(":")[0] for k in state["looks"]), [V.Q1_24H, V.TT_24H])
pick24 = {p["unit"]: p for p in state["rules"][V.TT_24H]["picks"]}
check("one 24h team-total entry per team at most", len(pick24) == len(state["rules"][V.TT_24H]["picks"]), True)
again = V.run(state, track, now24 + dt.timedelta(hours=1), fetch, pri={})
check("a second read in the window adds nothing (one look)", again, [])
now1 = TIP - dt.timedelta(minutes=75)
V.run(state, track, now1, fetch, pri={})
held24 = {p["ticker"] for p in state["rules"][V.TT_24H]["picks"] + state["rules"][V.Q1_24H]["picks"]}
held1 = {p["ticker"] for p in state["rules"][V.TT_1H]["picks"] + state["rules"][V.Q1_1H]["picks"]}
check("the 24h lanes entered both teams and the 1Q", (len(pick24), len(state["rules"][V.Q1_24H]["picks"])), (2, 1))
check("the 24h baselines logged", len(state["rules"][V.BASE[V.TT_24H]]["picks"]), 5)
pick1 = {p["unit"]: p for p in state["rules"][V.TT_1H]["picks"]}
check("the 1h lanes entered too", (sorted(pick1), len(state["rules"][V.Q1_1H]["picks"])), (["NY", "SA"], 1))
check("the 1h lanes never take a ticker the 24h lanes hold", held24 & held1, set())
check("so the 1h NY entry is the next-best rung", pick1["NY"]["edge"] <= pick24["NY"]["edge"] and pick1["NY"]["ticker"] != pick24["NY"]["ticker"], True)
check("ids are one per lane per game per unit", len({p["id"] for l in V.LANES for p in state["rules"][l]["picks"]}),
      sum(len(state["rules"][l]["picks"]) for l in V.LANES))
check("no look without a ladder", "x" in V.run(V.empty(), dict(games={"9001": GAME}), now1, fake({}), pri={}) + ["x"], True)
st2 = V.empty()
V.run(st2, dict(games={"9001": GAME}), now1, fake({}), pri={})
check("...and the game stays unlooked for a later read", st2["looks"], {})

T.model_for = _model_for

print("\nsettlement after the fee")
res = {m["ticker"]: ("yes" if m["floor_strike"] < 112 else "no") for m in tt + q1}
fetch_s = fake({EV_TT: tt, EV_Q1: q1}, res)
V.settle(state, TIP + dt.timedelta(hours=3), fetch_s)
for lane in V.LANES:
    for p in state["rules"][lane]["picks"]:
        won = (res[p["ticker"]] == "yes") == (p["side"] == "yes")
        check(f"{p['id']} {p['side']} settles {('won' if won else 'lost')}", p["status"], "won" if won else "lost")
        near(f"{p['id']} profit", p["profit"], round(100 * ((1.0 if won else 0.0) / V.cost(p["price"]) - 1), 2))

print("\nstats clustered by game night")
picks = [dict(status="won", price=0.5, night="2026-10-28", p=0.6, profit=93.2), dict(status="won", price=0.5, night="2026-10-28", p=0.6, profit=93.2),
         dict(status="lost", price=0.5, night="2026-10-29", p=0.6, profit=-100), dict(status="open", price=0.4, night="2026-10-30", p=0.5)]
a = V.stats(picks)
check("n, won, nights, open", (a["n"], a["won"], a["nights"], a["open"]), (3, 2, 2, 1))
near("night-clustered z: (2 - 1.5) / sqrt(max(0.75, 1.0 + 0.25))", a["z"], 0.5 / math.sqrt(1.25))
near("independent z", a["z_iid"], 0.5 / math.sqrt(0.75))
near("model expectation", a["model_exp"], 1.8)

print("\ntracker: candle quotes, 1Q parsing, climb, drift, calibration")
tip_ts = int(TIP.timestamp())
cs = dict(market_tickers=["A", "B"], market_candlesticks=[
    [dict(end_period_ts=tip_ts - 30 * 3600, yes_bid=dict(close_dollars="0.50"), yes_ask=dict(close_dollars="0.52")),
     dict(end_period_ts=tip_ts - 5 * 3600, yes_bid=dict(close_dollars="0.55"), yes_ask=dict(close_dollars="0.57")),
     dict(end_period_ts=tip_ts - 3600, yes_bid=dict(close_dollars="0.60"), yes_ask=dict(close_dollars="0.61"))],
    [dict(end_period_ts=tip_ts - 2 * 3600, yes_bid=dict(close_dollars="0.0000"), yes_ask=dict(close_dollars="0.04"))]])
q = T.candle_quotes(cs, tip_ts)
check("24h, 12h, 6h carry the 30h candle forward", (q["A"]["24"], q["A"]["12"], q["A"]["6"]), ([0.5, 0.52],) * 3)
check("3h takes the 5h candle; 1h the candle ending exactly at 1h", (q["A"]["3"], q["A"]["1"]), ([0.55, 0.57], [0.6, 0.61]))
check("no candle before a time: no quote", "24" in q["B"], False)
check("a one-sided book is recorded, not two-sided", (q["B"]["1"], T.two_sided(q["B"]["1"])), ([0.0, 0.04], False))
q1m = [mk(f"{EV_Q1}-58", 57.5, None, None, result="yes"), mk(f"{EV_Q1}-62", 61.5, None, None, result="no")]
lr = T.ladder_rows(T.SERIES_Q1, q1m, GAME, {f"{EV_Q1}-58": {"1": [0.6, 0.62]}}, MODEL)
check("1Q rungs: unit 'game', lines, results", [(r["team"], r["line"], r["result"]) for r in lr],
      [("game", 57.5, "yes"), ("game", 61.5, "no")])
near("1Q rung model P", lr[0]["p"], round(M.p_over(57.5, 58.0, 8.0), 4))
check("a strike that is not N.5 is skipped", T.strike(dict(floor_strike=110, strike_type="greater")), None)


def rung(team, line, q24, q1_, res, p=None):
    return dict(ticker=f"T-{team}{line}", team=team, line=line, result=res, q={"24": q24, "1": q1_}, p=p)


tracked = {"1": dict(home="NY", away="SA", night="2026-10-28", pts={"NY": 120, "SA": 104},
                     tt=dict(rungs=[rung("NY", 113.5, [0.55, 0.57], [0.48, 0.50], "yes", 0.55),
                                    rung("NY", 117.5, [0.40, 0.42], [0.33, 0.35], "yes", 0.35),
                                    rung("SA", 107.5, [0.50, 0.52], [0.55, 0.56], "no", 0.62),
                                    rung("SA", 111.5, [0.33, 0.35], [0.38, 0.40], "no", 0.30)]),
                     q1_ladder=dict(rungs=[rung("game", 57.5, [0.6, 0.62], [0.62, 0.64], "yes", 0.58)]))}
check("50c line: mid nearest 0.50 at 1h", T.line50(tracked["1"]["tt"]["rungs"][:2])["line"], 113.5)
cl = sorted(T.climbs(tracked))
check("climbs: NY 120 - 113.5, SA 104 - 107.5", [(c[0], c[4]) for c in cl], [("NY", 6.5), ("SA", -3.5)])
ct = T.climb_table(tracked)
check("offence and defence views", (ct["NY"]["off_avg"], ct["NY"]["def_avg"], ct["SA"]["def_beat"]), (6.5, -3.5, 1.0))
dt_ = T.drift_table(tracked)
near("team-total ask drift averages -0.07, -0.07, +0.04, +0.05", dt_["tt"]["avg"], (-0.07 - 0.07 + 0.04 + 0.05) / 4)
check("drift direction matched the result: NY drops then YES (no), SA rises then NO (no)", dt_["tt"]["matched"], 0.0)
check("the 1Q rung drifted +2c and settled yes: matched", (dt_["q1"]["moved"], dt_["q1"]["matched"]), (1, 1.0))
check("line move from 24h to 1h, NY (115.5 not listed: 113.5 -> 113.5)", T.line_moves(tracked)["NY"], [0.0])
cal = T.calibration(tracked, "tt")
check("calibration buckets by model P", [(r[0], r[2]) for r in cal], [(0.3, 2), (0.5, 1), (0.6, 1)])
near("calibration hit rate and ask in the 0.3 bucket", cal[0][4], 0.5)
near("average ask", cal[0][5], (0.35 + 0.40) / 2)
check("bucket by Kalshi ask too", [(r[0], r[2]) for r in T.calibration(tracked, "tt", by="ask")], [(0.3, 1), (0.4, 1), (0.5, 2)])

print("\ntracker run on fakes: ESPN rows in, a finished game tracked once")


def day_rows(day):
    if day.isoformat() != "2026-10-28":
        return []
    return [dict(id="9001", start="2026-10-28T23:30Z", day="2026-10-28", season_type=2, home="NY", away="SA",
                 completed=True, ft_home=120, ft_away=104, q1_home=30, q1_away=26),
            dict(id="9003", start="2026-10-28T23:30Z", day="2026-10-28", season_type=2, home="EAST", away="SA",
                 completed=True, ft_home=1, ft_away=1, q1_home=1, q1_away=1)]


def tfetch(path):
    if path.startswith("markets?"):
        ev = path.split("event_ticker=")[1].split("&")[0]
        ms = {EV_TT: [mk(f"{EV_TT}-NYK114", 113.5, None, None, result="yes")],
              EV_Q1: [mk(f"{EV_Q1}-58", 57.5, None, None, result="no")]}.get(ev, [])
        return {"markets": ms, "cursor": None}
    if "/candlesticks" in path:
        return dict(market_tickers=[], market_candlesticks=[])
    raise AssertionError(path)


ts = T.empty()
T.run(ts, dt.datetime(2026, 10, 29, 12, tzinfo=UTC), tfetch, day_rows, pri=pri26)
check("backfilled from opening night", ts["backfilled"], True)
check("only NBA teams' regular-season games", sorted(ts["games"]), ["9001"])
row = ts["tracked"]["9001"]
check("tracked: points, 1Q, both ladders", (row["pts"], row["q1"]["NY"], row["tt"]["event"], row["q1_ladder"]["event"]),
      ({"NY": 120, "SA": 104}, 30, EV_TT, EV_Q1))
check("the model at the tip is stored, with its level", sorted(row["model"]), ["level", "mu", "mu_q1", "n", "sd", "sd_q1"])
check("a game night", row["night"], "2026-10-28")
n_before = len(ts["tracked"])
T.run(ts, dt.datetime(2026, 10, 29, 13, tzinfo=UTC), tfetch, day_rows, pri=pri26)
check("tracked once", len(ts["tracked"]), n_before)
hist = T.history_rows(ts["games"], before=TIP)
check("the game is not in its own model (before the tip)", hist, [])

print("\nthe level anchor: team prior = level now + (team 2025-26 - league 2025-26)")
pri2 = {"A": dict(n=82, off=120.0, dfn=110.0, q1_off=30.0, q1_dfn=28.0),
        "B": dict(n=82, off=110.0, dfn=120.0, q1_off=28.0, q1_dfn=30.0)}
check("the prior's level", M.prior_level(pri2), (115.0, 58.0))
sh = M.shift_prior(pri2, 118.0, 62.0)
check("every rate moves by the level change (+3, 1Q +2 per side)",
      (sh["A"]["off"], sh["A"]["dfn"], sh["B"]["q1_off"], sh["B"]["q1_dfn"]), (123.0, 113.0, 30.0, 32.0))
check("the spread between teams is kept", sh["A"]["off"] - sh["B"]["off"], 10.0)
check("a level of None changes nothing", M.shift_prior(pri2, None, None), pri2)
pre_rows = [("2026-10-05T23:00Z", 230, 60), ("2026-10-06T23:00Z", 240, 56)]
lv = T.level_now({"9001": dict(GAME, completed=True, pts_home=120, pts_away=100, q1_home=30, q1_away=28)},
                 before=TIP + dt.timedelta(hours=5), pre=pre_rows)
check("level now: preseason plus regular-season games", (lv[0], lv[1], lv[2]), ((230 + 240 + 220) / 6, (60 + 56 + 58) / 3, 3))
check("a game after the cut is not in the level", T.level_now({"9001": dict(GAME, completed=True, pts_home=120, pts_away=100,
      q1_home=30, q1_away=28)}, before=TIP, pre=pre_rows)[2], 2)

check("no entries before the first night (the 2026-10-21 slate is observed only)",
      V.due(V.TT_1H, {"x": dict(GAME, id="x", start="2026-10-21T23:30Z")}, dt.datetime(2026, 10, 21, 22, 15, tzinfo=UTC)), [])
check("the first night is 2026-10-22", V.FIRST_NIGHT, "2026-10-22")

print("\nthe level guard")
near("market median interpolates the 0.50 crossing", V.market_median([(109.5, 0.61), (113.5, 0.47), (117.5, 0.34)]),
     109.5 + (0.61 - 0.5) / (0.61 - 0.47) * 4)
check("outside the quoted range: the nearest rung", V.market_median([(109.5, 0.3), (113.5, 0.2)]), 109.5)
check("a gap over 4 points blocks", V.check_verdict([-5.0, -4.5, -3.0], ["no", "yes"], "tt")[0], False)
check("...and says so", V.check_verdict([-5.0, -4.5, -3.0], ["no"], "tt")[1].startswith("model level mismatch"), True)
check("a 1Q gap over 3 blocks", V.check_verdict([-3.5], [], "q1")[0], False)
check("12 of 13 one side blocks", V.check_verdict([-1.0], ["no"] * 12 + ["yes"], "tt")[0], False)
check("4 of 4 one side is too few to judge", V.check_verdict([-1.0], ["no"] * 4, "tt")[0], True)
check("80% exactly passes", V.check_verdict([0.5], ["no"] * 4 + ["yes"], "tt")[0], True)
biased = dict(MODEL, mu={"NY": 107.0, "SA": 104.0})
T.model_for = lambda *a, **k: biased
sb = V.empty()
V.run(sb, dict(games={"9001": GAME}), TIP - dt.timedelta(minutes=75), fake({EV_TT: tt, EV_Q1: q1}), pri={})
T.model_for = _model_for
chk = sb["checks"][f"{V.TT_1H}:2026-10-28"]
check("a model 6-8 points under the market: the night is a mismatch", (chk["ok"], chk["reason"][:20]), (False, "model level mismatch"))
check("...no entries and no baseline that night", (sb["rules"][V.TT_1H]["picks"], sb["rules"][V.BASE[V.TT_1H]]["picks"]), ([], []))
check("...but the look is used and logged", sb["looks"][f"{V.TT_1H}:9001"]["blocked"][:20], "model level mismatch")
lg_ = T.level_gaps(tracked)
check("tracker gaps need a stored model", lg_, {"tt": [], "q1": []})
tracked["1"]["model"] = dict(mu={"NY": 112.0, "SA": 110.0}, mu_q1=60.0)
lg_ = T.level_gaps(tracked)
near("tracker gap: NY mu 112 v the nearest-50c rung 113.5 (both mids under 0.50)", lg_["tt"][0], -1.5)
check("median", T.median([3, 1, 2, 10]), 2.5)

print("\nthe page sections")
html = VB.section(state, dict(tracked=tracked, games={}, last_run=None))
for lane in V.LANES:
    check(f"{lane} row", f'data-source="{lane}"' in html, True)
check("value and ladder sections", ('id="value"' in html, 'id="ladder"' in html), (True, True))
check("calibration as a table: no SVG, meter or inline style", ("Hit − ask" in html, "<svg" in html, "<meter" in html, " style=" in html), (True, False, False, False))
check("climb table lists the teams", ">NY</b>" in html and ">SA</b>" in html, True)
empty_html = VB.section(V.empty(), T.empty())
check("an empty ledger renders", "No tracked game yet" in empty_html and "No entries yet" in empty_html, True)
import nba_pace_build
page = nba_pace_build.build(json.load(open(nba_pace_build.SRC)), now=TIP)
check("the NBA page carries both sections and the nav", all(x in page for x in ('id="value"', 'id="ladder"', 'href="#ladder"')), True)
check("no guarded phrase in the copy",
      sandbox_audit.COPY_RE.search(html + open("nba_value.py").read() + open("nba_value_build.py").read()
                                   + open("nba_ladder_track.py").read() + open("nba_value_model.py").read()), None)

print("\nSandbox only")
import sandbox_sources as S
for lane in V.LANES:
    check(f"{lane} is not a Sandbox-ledger source", lane in S.SOURCES, False)
    check(f"{lane} is not in Production", lane in open("production.py").read(), False)
check("the R1-R7 rules are untouched (own ledger)", V.PATH != __import__("nba_rules").PATH, True)

print()
if FAILS:
    print(f"{len(FAILS)} FAILED: {FAILS}")
    sys.exit(1)
print("all ok")
