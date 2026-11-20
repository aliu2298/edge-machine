#!/usr/bin/env python3
"""Offline checks for the NBA Spotter (nba_spotter.py): the frozen model reproduces Fable's board, entry, caps, blind controls, the sale rule, settlement, the page."""
import collections
import copy
import datetime as dt
import json
import os
import sys

import nba_spotter as S
import nba_spotter_build as B
import sandbox_audit

FAILS = []
UTC = dt.timezone.utc


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


FX = json.load(open(os.path.join(S.DATA, "regression.json")))
# the games as seeded on Nov 18: the live games.json grows with every run, and the regression board is that day's
REG_GAMES = json.load(open(os.path.join(S.DATA, "games_regression.json")))["games"]
W = S.World(games=copy.deepcopy(REG_GAMES))
OUT = set()
for nm in FX["out_names"]:
    c = W.NAME.get(S.norm(nm), set())
    if len(c) == 1:
        OUT.add(next(iter(c)))
MK = FX["markets"]
TIP = {s["id"]: dt.datetime.fromisoformat(s["date"].replace("Z", "+00:00")) for s in FX["slate"]}


def game_of(s):
    return dict(id=s["id"], tip=TIP[s["id"]].timestamp(), home=s["home"], away=s["away"], spread=s.get("spread"))


print("the frozen model")
import hashlib
check("the model file is the research's, unrefitted", hashlib.sha256(json.dumps({k: W.M[k] for k in ("hold", "spike")}, sort_keys=True).encode()).hexdigest(), W.M["sha256_models"])
rows = []
for s in FX["slate"]:
    r, _sk = S.read_game(W, game_of(s), MK, OUT)
    rows += r
by = {r["tk"]: r for r in rows}
check("every fixture contract is usable", sorted(by), sorted(FX["expect"]))
bad = [tk for tk, e in FX["expect"].items() if abs(by[tk]["p_hold"] - e["p_hold"]) > 1e-5 or by[tk]["why_hold"] != e["why_hold"]
       or (e["p_spike"] is not None and (abs(by[tk]["p_spike"] - e["p_spike"]) > 1e-5 or by[tk]["why_spike"] != e["why_spike"]))]
check("model chances and reasons match Fable's Nov 18 board", bad, [])
check("a day's priced contracts: spread 5c or less, ask 5-60c", all(r["ask"] - r["bid"] <= 0.05 + 1e-9 and 0.05 <= r["ask"] <= 0.60 for r in rows), True)

print("\nentries, caps and blind controls")
now = dt.datetime(2026, 11, 18, 22, 0, tzinfo=UTC)
games = [dict(game_of(s), tip=TIP[s["id"]]) for s in FX["slate"]]
check("a game 80 to 35 minutes from tip is due; earlier and later are not",
      [bool(S.due([dict(id="x", tip=now + dt.timedelta(minutes=m))], now, {})) for m in (90, 81, 80, 60, 35, 34, -5)], [False, False, True, True, True, False, False])
check("a game already read is not read again", S.due([dict(id="x", tip=now + dt.timedelta(minutes=60))], now, {"x": {}}), [])
os.environ["EDGE_SETTLE_ONLY"] = "1"
check("settle-only passes enter nothing", S.due([dict(id="x", tip=now + dt.timedelta(minutes=60))], now, {}), [])
os.environ.pop("EDGE_SETTLE_ONLY", None)

st = S.empty()
g_by_tk = {}
for r in rows:
    g_by_tk[r["tk"]] = next(g for g in games if r["team"] in (g["home"], g["away"]))
gid = next(iter(g_by_tk.values()))["id"]
g = next(x for x in games if x["id"] == gid)
t0 = g["tip"] - dt.timedelta(minutes=60)
new = S.look(st, W, g, MK, OUT, t0)
h, sp = st["rules"]["spotter_hold"]["picks"], st["rules"]["spotter_spike"]["picks"]
check("hold needs 5 points of edge: none of tonight's rungs reach it (Fable's board)", h, [])
check("spike takes the top rungs of the game at 49c or less, one a player-stat, 4 a game at most", (0 < len(sp) <= S.GAME_CAP, len({(p["pid"], p["stat"]) for p in sp}) == len(sp)), (True, True))
check("each spike pick carries its price, target at 2x, model chance and reason", all(p["target"] == round(2 * p["price"], 2) and p["p"] and p["why"] for p in sp), True)
bl = st["rules"]["spotter_spike_blind"]["picks"]
st2 = S.empty()
S.look(st2, W, g, MK, OUT, t0)
check("the blind draw is fixed by the pick: a rerun draws the same rungs", [b["ticker"] for b in st2["rules"]["spotter_spike_blind"]["picks"]], [b["ticker"] for b in bl])
check("the read is logged once per game with what was left out", (sorted(st["looks"]), "usable" in st["looks"][gid]), ([gid], True))
check("night counters track the cap", st["nights"][S.night_of(g["tip"])]["spotter_spike"]["n"], len(sp))

# the night cap: every rung gets an edge; lots of games
st3 = S.empty()
fake = [dict(rung=i, bid=0.40, ask=0.42, tk=f"K-{i}", name=f"P{i}", pid=f"p{i}", stat="pts", team="AAA", p_hold=0.60, edge=0.18 - i / 1000, why_hold="w", outs=[],
             p_spike=0.6, spike_edge=0.1 - i / 1000, why_spike="w") for i in range(30)]
orig = S.read_game
S.read_game = lambda W_, g_, m_, o_: (fake, {})
try:
    for k in range(4):
        gg = dict(id=f"g{k}", tip=t0 + dt.timedelta(hours=1) + dt.timedelta(minutes=k), home="H", away="A")
        S.look(st3, W, gg, {}, set(), t0)
finally:
    S.read_game = orig
hp = st3["rules"]["spotter_hold"]["picks"]
check("8 a night on each board, 4 from the first game", (len(hp), len(st3["rules"]["spotter_spike"]["picks"]), sum(1 for p in hp if p["game_id"] == "g0")), (8, 8, 4))
bh, bs = st3["rules"]["spotter_hold_blind"]["picks"], st3["rules"]["spotter_spike_blind"]["picks"]
check("a blind row for every pick, never the pick's own player-stat, within 3c of its price, same game",
      (len(bh), len(bs), not ({(b["pid"], b["stat"]) for b in bh} & {(p["pid"], p["stat"]) for p in hp}),
       all(abs(b["price"] - 0.42) <= S.BLIND_BAND + 1e-9 for b in bh), all(b["game_id"] == b["game_id"] for b in bh)), (8, 8, True, True, True))
check("the highest edges are taken first", [p["rung"] for p in hp if p["game_id"] == "g0"], [0, 1, 2, 3])
check("the same player is not entered twice in a night", len({(p["pid"], p["stat"]) for p in hp}), len(hp))

# games read in the same run are ranked together, not in tip order
st5 = S.empty()
def fake_rows(prefix, top):
    return [dict(rung=i, bid=0.40, ask=0.42, tk=f"{prefix}-{i}", name=f"{prefix}{i}", pid=f"{prefix}{i}", stat="pts", team="AAA", p_hold=0.6, edge=top - i / 1000, why_hold="w",
                 outs=[], p_spike=0.6, spike_edge=top - i / 1000, why_spike="w") for i in range(12)]
S.read_game = lambda W_, g_, m_, o_: (fake_rows(g_["id"], 0.30 if g_["id"] == "late" else 0.10), {})
try:
    ga = dict(id="early", tip=t0 + dt.timedelta(hours=1), home="H", away="A")
    gb = dict(id="late", tip=t0 + dt.timedelta(hours=2), home="H2", away="A2")
    S.look_many(st5, W, [ga, gb], {}, set(), t0)
finally:
    S.read_game = orig
hp5 = st5["rules"]["spotter_hold"]["picks"]
check("two games in one run: the later game's better edges are not shut out by tip order (4 + 4)",
      (sorted(collections.Counter(p["game_id"] for p in hp5).items()), len(hp5)), ([("early", 4), ("late", 4)], 8))
check("the batch size is logged", st5["looks"]["early"]["batch"], 2)

# the fade board: buy NO where the model is 5+ points below the YES ask, real NO ask <= 90c, from the first board night
print("\nthe fade board")
tkf = 1_800_000_000.0
def fade_rows(prefix, top, n=12, no_ask=0.60):
    return [dict(rung=i, bid=0.40, ask=0.42, no_ask=no_ask, tk=f"{prefix}-{i}", name=f"{prefix}{i}", pid=f"{prefix}{i}", stat="pts", team="AAA", p_hold=0.42 - top + i / 1000,
                 edge=-top, why_hold="w", outs=[], gap=top - i / 1000, p_fade=0.58 + top - i / 1000, why_fade="a cold run") for i in range(n)]
st6 = S.empty()
S.read_game = lambda W_, g_, m_, o_: (fade_rows(g_["id"], 0.20 if g_["id"] == "late" else 0.10) + [dict(fade_rows("x", 0.30, 1)[0], no_ask=0.93, tk="x-hi", pid="xhi"), dict(fade_rows("y", 0.30, 1)[0], no_ask=None, tk="y-none", pid="ynone"),
                                                                                                    dict(fade_rows("z", 0.04, 1)[0], tk="z-small", pid="zsmall", gap=0.04)], {})
try:
    tip = dt.datetime(2026, 11, 20, 0, 30, tzinfo=UTC)
    ga, gb = dict(id="early", tip=tip, home="H", away="A"), dict(id="late", tip=tip + dt.timedelta(hours=1), home="H2", away="A2")
    S.look_many(st6, W, [ga, gb], {}, set(), tip - dt.timedelta(minutes=60))
    old = dict(id="old", tip=dt.datetime(2026, 11, 18, 23, 30, tzinfo=UTC), home="H3", away="A3")
    S.look_many(st6, W, [old], {}, set(), old["tip"] - dt.timedelta(minutes=60))
finally:
    S.read_game = orig
fp = st6["rules"]["spotter_fade"]["picks"]
check("fade: 4 + 4 across two games read together, best gaps first", (sorted(collections.Counter(p["game_id"] for p in fp).items()), len(fp)), ([("early", 4), ("late", 4)], 8))
check("fade: priced at the NO ask, side no, never a NO ask above 90c, a missing NO ask or a gap under 5 points",
      (all(p["price"] == 0.60 and p["side"] == "no" and p["yes_ask"] == 0.42 for p in fp), any(p["ticker"] in ("x-hi", "y-none", "z-small") for p in fp)), (True, False))
check("fade: nothing entered for a night before the start night (no backfill)", [p for p in fp if p["game_id"] == "old"], [])
fb = st6["rules"]["spotter_fade_blind"]["picks"]
check("fade blind: one per pick, NO side, never the board's own player-stat", (len(fb), all(b["price"] <= 0.90 and b["side"] == "no" for b in fb), not ({b["pid"] for b in fb} & {p["pid"] for p in fp})), (8, True, True))
r = dict(rule="spotter_fade", price=0.60, side="no", entered=dt.datetime.fromtimestamp(tkf, UTC).isoformat(), status="open")
S.settle_row(r, 1.0)
check("fade: NO wins when the rung misses (NO payout 1), fees on entry", (r["status"], round(r["profit"], 4)), ("won", round(1 - 0.60 - S.fee(0.60), 4)))
r = dict(rule="spotter_fade", price=0.60, side="no", entered=dt.datetime.fromtimestamp(tkf, UTC).isoformat(), status="open")
S.settle_row(r, 0.0)
check("fade: loses the cost when the rung hits", (r["status"], round(r["profit"], 4)), ("lost", round(-(0.60 + S.fee(0.60)), 4)))
sv = S.empty()
sv["rules"]["spotter_fade"]["picks"].append(dict(id="v", rule="spotter_fade", side="no", price=0.6, ticker="T", start="2026-11-20T00:00:00+00:00", status="open", night="2026-11-19"))
S.settle(sv, dt.datetime(2026, 11, 21, tzinfo=UTC), lambda path, **_: {"market": {"status": "settled", "result": "scalar", "settlement_value_dollars": "0.5"}})
check("a scalar settlement is void and leaves the record", (sv["rules"]["spotter_fade"]["picks"][0]["status"], S.stats(sv["rules"]["spotter_fade"]["picks"])["n"]), ("void", 0))


print("\nthe sale and the settlement")
tkt = 1_800_000_000.0
pr = [(tkt + 10, 0.95, 5.0, "yes"), (tkt + 30, 0.84, 5.0, "yes"), (tkt + 40, 0.85, 3.0, "yes"), (tkt + 60, 0.86, 3.0, "no")]
check("the sell is a later print strictly above the target, 25 seconds on at the earliest",
      (S.sale(pr, tkt, 0.84), S.sale(pr, tkt, 0.85), S.sale(pr, tkt, 0.94), S.sale(pr, tkt + 20, 0.84)), ((tkt + 40, 0.85), (tkt + 60, 0.86), None, (tkt + 60, 0.86)))
check("a print AT the target does not sell", S.sale([(tkt + 40, 0.84, 9.0, "yes")], tkt, 0.84), None)
row = dict(rule="spotter_spike", price=0.40, target=0.80, entered=dt.datetime.fromtimestamp(tkt, UTC).isoformat(), status="open")
S.settle_row(row, 0.0, [(tkt + 90, 0.81, 4.0, "yes")])
check("sold at 2x: target less both fees, more than the cost", (row["sold"], row["status"], round(row["profit"], 4)), (True, "won", round(0.80 - S.fee(0.80) - 0.40 - S.fee(0.40), 4)))
row = dict(rule="spotter_spike", price=0.40, target=0.80, entered=dt.datetime.fromtimestamp(tkt, UTC).isoformat(), status="open")
S.settle_row(row, 1.0, [])
check("never sold, settles yes: held", (row["sold"], row["status"], round(row["profit"], 4)), (False, "won", round(1 - 0.40 - S.fee(0.40), 4)))
row = dict(rule="spotter_hold", price=0.40, entered=dt.datetime.fromtimestamp(tkt, UTC).isoformat(), status="open")
S.settle_row(row, 0.0)
check("a hold that loses pays the cost", (row["status"], round(row["profit"], 4), round(row["ret"], 4)), ("lost", round(-(0.40 + S.fee(0.40)), 4), -1.0))

print("\nthe record")
def pk(rule, night, price, profit, status="won"):
    return dict(rule=rule, night=night, price=price, profit=profit, status=status, sold=False)
stt = S.empty()
for i, n in enumerate(("2026-11-18", "2026-11-19", "2026-11-20", "2026-11-21")):
    stt["rules"]["spotter_hold"]["picks"] += [pk("spotter_hold", n, 0.4, 0.10 + i * 0.01), pk("spotter_hold", n, 0.4, -0.05, "lost")]
    stt["rules"]["spotter_hold_blind"]["picks"] += [pk("spotter_hold_blind", n, 0.4, -0.02)]
s = S.stats(stt["rules"]["spotter_hold"]["picks"])
check("n, nights, mean profit", (s["n"], s["nights"], round(s["profit"], 4)), (8, 4, round((0.10 + 0.11 + 0.12 + 0.13 - 0.20) / 8, 4)))
ex, tx, k = S.versus_blind(stt, "spotter_hold")
check("over blind on the nights both have", (round(ex, 4), k, tx is not None), (round(((0.10 + 0.11 + 0.12 + 0.13) / 4 - 0.05) / 2 * 0 + (sum((0.10 + i * 0.01 - 0.05) / 2 + 0.02 for i in range(4)) / 4), 4), 4, True))
check("the read waits for 200 graded picks", S.read_text(stt, "spotter_hold").startswith("too early (8 of 200"), True)

print("\nrun(): finals, the injury list, entries, settle")
def ev(i, date, status, home, away, spread=None, typ=2):
    return dict(id=i, date=date, season=dict(type=typ), competitions=[dict(status=dict(type=dict(name=status)),
                competitors=[dict(homeAway="home", team=dict(abbreviation=home)), dict(homeAway="away", team=dict(abbreviation=away))],
                odds=[dict(spread=spread)] if spread is not None else [])])
s0 = FX["slate"][0]
final_box = dict(boxscore=dict(players=[dict(team=dict(abbreviation="BOS"), statistics=[dict(labels=["MIN", "FG", "3PT", "FT", "OREB", "REB", "AST", "TO", "PF", "PTS"],
                 athletes=[dict(athlete=dict(id="999", displayName="Test Guy"), starter=True, stats=["30", "5-10", "2-4", "3-4", "1", "6", "3", "2", "1", "15"])])]),
                 dict(team=dict(abbreviation="NY"), statistics=[dict(labels=["MIN", "FG", "3PT", "FT", "OREB", "REB", "AST", "TO", "PF", "PTS"],
                 athletes=[dict(athlete=dict(id="998", displayName="Other Guy"), starter=False, stats=["20", "2-6", "0-1", "0-0", "0", "3", "1", "1", "2", "4"]),
                           dict(athlete=dict(id="997", displayName="DNP"), didNotPlay=True, stats=[])])])]))
now2 = TIP[s0["id"]] - dt.timedelta(minutes=62)
last_day = max(x["day"] for x in W.games)
import calendar
def fake_get(url, **_):
    if "injuries" in url:
        return dict(injuries=[dict(injuries=[dict(athlete=dict(displayName=n), status="Out") for n in FX["out_names"]])])
    if "summary" in url:
        return final_box
    d = url.split("dates=")[1]
    tip = TIP[s0["id"]]
    evs = [ev(str(e["id"]), e["date"], "STATUS_SCHEDULED", e["home"], e["away"], e.get("spread")) for e in FX["slate"]]
    if d == (now2.astimezone(S.ET) - dt.timedelta(days=1)).strftime("%Y%m%d"):
        evs = [ev("777", "2026-11-17T23:00Z", "STATUS_FINAL", "NY", "BOS"), ev("778", "2026-11-17T23:00Z", "STATUS_FINAL", "NY", "BOS", typ=1)]
    elif d != now2.astimezone(S.ET).strftime("%Y%m%d"):
        evs = []
    return dict(events=evs)
def fake_fetch(path):
    if path.startswith("markets?series_ticker="):
        ser = path.split("series_ticker=")[1].split("&")[0]
        return dict(markets=[dict(m, ticker=m["ticker"]) for m in MK.get(ser, [])], cursor=None)
    if path.startswith("markets/trades") or path.startswith("historical/trades"):
        return dict(trades=[], cursor=None)
    return dict(market=dict(status="active"))
gd = dict(games=copy.deepcopy(W.games))
W2 = S.World(games=gd["games"])
st4 = S.empty()
new4, errs = S.run(st4, W2, gd, now2, fake_get, fake_fetch)
check("a finished regular-season game is added to the box scores (a preseason one is not)", ("777" in {x["id"] for x in gd["games"]}, "778" in {x["id"] for x in gd["games"]}), (True, False))
check("the new box score is in the model's world", (len(W2.P["999"]), W2.P["999"][0]["pts"], W2.P["999"][0]["m3"]), (1, 15, 2))
check("no error", errs, [])
check("the game inside the window was read once, with its spike picks", (s0["id"] in st4["looks"], len(st4["rules"]["spotter_spike"]["picks"]) > 0), (True, True))
n_before = len(new4)
new5, _e = S.run(st4, W2, gd, now2 + dt.timedelta(minutes=5), fake_get, fake_fetch)
check("a second read of the same game adds nothing", new5, [])
check("the run is stamped", (st4["last_run"], st4["runs"][-2]["new"] == n_before), ((now2 + dt.timedelta(minutes=5)).isoformat(), True))
done = S.settle(st4, TIP[s0["id"]] + dt.timedelta(hours=1), lambda p: (_ for _ in ()).throw(AssertionError("settled too early")))
check("nothing settles before 2 hours after the tip", done, [])

print("\nthe page")
html = B.section(st4, now2)
check("the section is on the page with its heading and both boards", ("id=\"spotter\"" in html, "NBA Spotter (Sandbox)" in html, "spotter_hold" in html, "spotter_spike" in html), (True,) * 4)
check("no guarded public phrase", sandbox_audit.COPY_RE.findall(html), [])
check("no dollar sign, inline style or SVG", ("$" in html, "style=" in html, "<svg" in html), (False, False, False))
check("a pick shows its price, model chance and reason", all(x in html for x in ("c →", "%")), True)
check("an empty ledger still renders", "No open picks" in B.section(S.empty(), now2), True)

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
