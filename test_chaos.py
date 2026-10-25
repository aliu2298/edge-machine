#!/usr/bin/env python3
"""Offline checks for the chaos replay engine (chaos_replay.py): pre-start entries with a resting limit sell."""
import datetime as dt
import sys

import chaos_build as CB
import chaos_lanes
import chaos_replay as C
import lane_windows as W
import sandbox_audit

FAILS = []
UTC = dt.timezone.utc


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


def near(label, got, want, tol=1e-3):
    ok = got is not None and abs(got - want) <= tol
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


T0 = 1_800_000_000 - 1_800_000_000 % 60          # a minute boundary


def row(i, bid, ask, bid_lo=None, bid_hi=None, ask_lo=None, ask_hi=None):
    """A dense YES-term minute row (the engine's own shape), minute i from T0."""
    return dict(ts=T0 + 60 * i, bid=bid, ask=ask, bid_lo=bid if bid_lo is None else bid_lo,
                bid_hi=bid if bid_hi is None else bid_hi, ask_lo=ask if ask_lo is None else ask_lo,
                ask_hi=ask if ask_hi is None else ask_hi)


def line(prices, spread=0.02):
    return [row(i, round(a - spread, 4), a) for i, a in enumerate(prices)]


print("fees, targets and stops")
near("taker fee 0.07 p (1-p)", C.taker_fee(0.5), 0.0175)
near("maker fee 0.0175 p (1-p)", C.maker_fee(0.5), 0.004375)
near("cost = price + taker fee", C.cost(0.5), 0.5175)
L = C.target_price(0.50, 0.20)
near("the +20% limit returns 20% after both fees", (L - C.maker_fee(L)) / C.cost(0.50) - 1, 0.20, 1e-3)
near("...at 0.6251", L, 0.6251, 1e-3)
check("a +50% target from 0.90 cannot be reached", C.target_price(0.90, 0.50), None)
S = C.stop_price(0.50)
near("the -50% stop loses half after both fees", (S - C.taker_fee(S)) / C.cost(0.50) - 1, -0.50, 1e-3)
check("eight exits: hold and +20/30/50, each with and without the -50% stop",
      sorted(C.EXITS), ["hold", "hold_stop50", "tp20", "tp20_stop50", "tp30", "tp30_stop50", "tp50", "tp50_stop50"])
check("entry times default to 1 and 24 hours before the start", C.ENTRY_HOURS, (1, 24))
check("variant keys carry the entry time; the control is the same entry held with the same stop",
      (C.vkey(1, "tp20"), C.split_key("t24h_tp30_stop50"), C.control_of("t1h_tp20"), C.control_of("t24h_tp50_stop50"), C.control_of("t1h_hold")),
      ("t1h_tp20", (24, "tp30_stop50"), "t1h_hold", "t24h_hold_stop50", "t1h_hold"))

print("\ncandles: dense minutes, forward fill, the NO side")
cs = [dict(end_period_ts=T0 + 60, yes_bid=dict(close_dollars="0.40", high_dollars="0.41", low_dollars="0.39"),
           yes_ask=dict(close_dollars="0.43", high_dollars="0.44", low_dollars="0.42")),
      dict(end_period_ts=T0 + 240, yes_bid=dict(close="0.50"), yes_ask=dict(close="0.52"))]       # archived: no suffix
d = C.dense(cs, T0, T0 + 300)
check("one row per minute from the first candle on", [r["ts"] for r in d], [T0 + 60 * k for k in range(1, 6)])
check("a minute with no candle carries the last quote, flat", (d[1]["bid"], d[1]["ask"], d[1]["bid_hi"], d[1]["bid_lo"]), (0.40, 0.43, 0.40, 0.40))
check("a real candle keeps its own high and low", (d[0]["bid_hi"], d[0]["bid_lo"], d[0]["ask_lo"]), (0.41, 0.39, 0.42))
check("the unsuffixed (archived) fields parse", (d[3]["bid"], d[3]["ask"]), (0.50, 0.52))
no = C.view(row(0, 0.40, 0.43, bid_lo=0.39, bid_hi=0.41, ask_lo=0.42, ask_hi=0.44), "no")
check("the NO side: ask 1 - yes bid, bid 1 - yes ask, bid high 1 - yes ask low",
      (no["ask"], no["bid"], no["bid_hi"], no["bid_lo"]), (0.60, 0.57, 0.58, 0.56))
check("tight: 3c spread passes, 4c does not, an empty bid does not, ask outside 0.02-0.98 does not",
      (C.tight(dict(bid=.50, ask=.53)), C.tight(dict(bid=.50, ask=.54)), C.tight(dict(bid=0, ask=.02)), C.tight(dict(bid=.97, ask=.99))),
      (True, False, False, False))

print("\nthe entry: a set time before the start, never in play")
START = T0 + 120 * 60                                   # the event starts 120 minutes in
pre = [0.55] * 130 + [0.56] * 10
vs = [C.view(m, "yes") for m in line(pre)]
check("1h before the start is minute 60: the first tight quote at that time", C.entry_index(vs, START - 3600, START), 60)
wide = [row(i, 0.50, 0.56) if i < 63 else row(i, 0.54, 0.56) for i in range(130)]
check("a wide spread at the entry time waits for the next tight minute (within 15 minutes)",
      C.entry_index([C.view(m, "yes") for m in wide], START - 3600, START), 63)
allwide = [row(i, 0.50, 0.56) for i in range(130)]
check("no tight quote within 15 minutes: no entry", C.entry_index([C.view(m, "yes") for m in allwide], START - 3600, START), None)
check("an entry time at or after the start is refused (nothing is bought in play)", C.entry_index(vs, START, START), None)
check("so is a grace window that would run past the start", C.entry_index([C.view(m, "yes") for m in allwide], START - 300, START), None)
check("a market with no quote that early has no trade", C.entry_index(vs[100:], START - 24 * 3600, START), None)

print("\nexits: the resting limit, fills, stops, fees, settlement")
base = line([0.55] * 130 + [0.55] * 40)
t = C.simulate(base, "yes", "yes", START, 1, "hold")[0]
check("bought at the ask 1h before the start", (t["entry_i"], t["entry"]), (60, 0.55))
near("held to a settlement win pays 1, no exit fee", t["profit"], 1 - C.cost(0.55), 1e-4)
t = C.simulate(base, "yes", "no", START, 1, "hold")[0]
near("held to a settlement loss loses the whole cost", t["roi"], -1.0, 1e-4)
tp20 = C.target_price(0.55, 0.20)
at = lambda i, hi: base[:i] + [row(i, 0.53, 0.55, bid_hi=hi)] + base[i + 1:]
t = C.simulate(at(100, tp20 + 0.009), "yes", "yes", START, 1, "tp20")[0]
check("a bid trading 0.9c through the limit does not fill it", t["reason"], "settled")
t = C.simulate(at(100, tp20 + 0.010), "yes", "yes", START, 1, "tp20")[0]
check("a bid trading 1c through the limit fills it, at the limit price", (t["reason"], t["exit"], t["exit_i"]), ("target", tp20, 100))
near("...the profit is the limit less the maker fee, less the cost", t["profit"], tp20 - C.maker_fee(tp20) - C.cost(0.55), 1e-4)
near("...which is the 20% ROI after fees", t["roi"], 0.20, 2e-3)
t = C.simulate(at(80, tp20 + 0.02), "yes", "yes", START, 1, "tp20")[0]
check("the limit rests from the entry, so a PRE-GAME fill counts (minute 80 is before the start at 120)",
      (t["reason"], t["exit_i"] < 120), ("target", True))
t = C.simulate(at(61, tp20 + 0.02), "yes", "yes", START, 1, "tp20")[0]
check("the first minute a sell can fill is the one after the entry", t["exit_i"], 61)
stop50 = C.stop_price(0.55)
dn = lambda lo, hi: base[:100] + [row(100, 0.30, 0.55, bid_lo=lo, bid_hi=hi)] + base[101:]
t = C.simulate(dn(stop50 - 0.01, 0.40), "yes", "yes", START, 1, "hold_stop50")[0]
check("a bid touching the stop price sells at the stop (taker)", (t["reason"], t["exit"]), ("stop", stop50))
near("...and loses 50% after both fees", t["roi"], -0.50, 2e-3)
t = C.simulate(dn(stop50 - 0.20, stop50 - 0.10), "yes", "yes", START, 1, "hold_stop50")[0]
check("a whole minute below the stop sells at its best bid, not the stop price", t["exit"], round(stop50 - 0.10, 4))
both = base[:100] + [row(100, 0.40, 0.55, bid_lo=stop50 - 0.05, bid_hi=tp20 + 0.05)] + base[101:]
check("a minute touching both the stop and the limit takes the stop", C.simulate(both, "yes", "yes", START, 1, "tp20_stop50")[0]["reason"], "stop")
check("a target that no 0.99 sell can reach is flagged and the trade is held",
      [(x["unreachable"], x["reason"]) for x in C.simulate(line([0.95] * 170), "yes", "yes", START, 1, "tp50")], [(True, "settled")])
t = C.simulate(line([0.45] * 170), "no", "no", START, 1, "hold")[0]
check("the NO side buys at 1 - the yes bid and wins on a no result", (t["entry"], t["won"]), (0.57, True))
check("the 24h entry is bought 24 hours before the start (when the market has a quote that early)",
      C.simulate(line([0.50] * 1800), "yes", "yes", T0 + 25 * 3600, 24, "hold")[0]["entry_i"], 60)

print("\npoint-in-time: an entry never reads the minutes after it")
a = line([0.55] * 130 + [0.90] * 40)
b = line([0.55] * 130 + [0.10] * 40)
ta, tb = C.simulate(a, "yes", "yes", START, 1, "hold")[0], C.simulate(b, "yes", "yes", START, 1, "hold")[0]
check("changing every minute after the entry changes nothing about the entry (same minute, same price)",
      (ta["entry_i"], ta["entry"]), (tb["entry_i"], tb["entry"]))
c1 = line([0.55] * 61 + [0.50] * 109)
c2 = line([0.55] * 61 + [0.90] * 109)
check("the entry is the quote at the entry time, not a later one", C.simulate(c1, "yes", "yes", START, 1, "hold")[0]["entry"],
      C.simulate(c2, "yes", "yes", START, 1, "hold")[0]["entry"])

print("\nthe start of the event: a lane's own source, else the price path")
calm = line([0.55] * 100)
wild = line([0.55] * 100 + [0.55 + (0.03 if k % 2 else 0) for k in range(80)])
check("a calm path shows no onset", C.detect_onset(calm), None)
check("too short a path shows none", C.detect_onset(line([0.5] * 20)), None)
on = C.detect_onset(wild)
check("play starting at minute 100 is detected a few minutes in, less the 18-minute lag", on, T0 + 60 * 104 - 18 * 60)
check("the lag is the measured 18 minutes", C.ONSET_LAG_MIN, 18)

print("\nreplaying events: fresh records, nothing replayed twice")
EV = "KXNBAGAME-26OCT24AAABBB"
END = T0 + 40 * 3600
START_E = END - 150 * 60


def mkt(tk, result, status="finalized"):
    return dict(ticker=tk, status=status, result=result, open_time="2026-10-20T00:00:00Z",
                close_time=dt.datetime.fromtimestamp(END, UTC).strftime("%Y-%m-%dT%H:%M:%SZ"))


def candles_for(prices_from, spread=0.02):
    """Candles from END - 33h, one a minute: calm pre-game, then the in-play path."""
    out = []
    start = END - C.FETCH_BEFORE_H * 3600
    for i, a in enumerate(prices_from):
        out.append(dict(end_period_ts=start + 60 * (i + 1), yes_bid=dict(close_dollars=f"{a - spread:.4f}", high_dollars=f"{a - spread:.4f}", low_dollars=f"{a - spread:.4f}"),
                        yes_ask=dict(close_dollars=f"{a:.4f}", high_dollars=f"{a:.4f}", low_dollars=f"{a:.4f}")))
    return out


n_pre = (C.FETCH_BEFORE_H * 60) - 150
path_aaa = [0.55] * n_pre + [0.55, 0.60, 0.70, 0.80, 0.78, 0.75] + [0.90] * 144
path_bbb = [round(1 - x, 4) for x in path_aaa]
MARKETS = {EV: [mkt(EV + "-AAA", "yes"), mkt(EV + "-BBB", "no")]}
CANDLES = {EV + "-AAA": candles_for(path_aaa), EV + "-BBB": candles_for(path_bbb)}
CALLS = []


def fetch(path):
    CALLS.append(path)
    if path.startswith("events?"):
        return {"events": [dict(event_ticker=EV), dict(event_ticker="KXNBAGAME-26OCT24CCCDDD")], "cursor": None}
    if path.startswith("markets?"):
        ev = path.split("event_ticker=")[1].split("&")[0]
        return {"markets": MARKETS.get(ev, []), "cursor": None}
    if path.startswith("series/"):
        return {"market_tickers": list(CANDLES), "market_candlesticks": list(CANDLES.values())}
    raise AssertionError(path)


lane = dict(id="t_lane", label="Test lane", series=["KXNBAGAME"], picker=C.any_side_picker(), duration_min=150, since="2026-10-24",
            start=lambda ctx: START_E, note="a test lane")
NOW = dt.datetime(2026, 10, 25, 9, 0, tzinfo=UTC)
st = C.empty()
new = C.run(st, [lane], NOW, fetch)
Ls = st["lanes"]["t_lane"]
check("the lane's record starts fresh, with its own first night and no inherited rows",
      (Ls["since"], list(st["lanes"]), Ls["registered"][:10]), ("2026-10-24", ["t_lane"], "2026-10-25"))
check("an event that has not settled is left for a later night, not marked", "KXNBAGAME-26OCT24CCCDDD" in Ls["replayed"], False)
check("the settled event was replayed", (EV in Ls["replayed"], len(Ls["trades"]) > 0), (True, True))
check("every trade is bought 1h or 24h before the start, never in play",
      all(t["entry_ts"] <= t["start_ts"] - t["hours"] * 3600 + C.ENTRY_GRACE_MIN * 60 for t in Ls["trades"]), True)
check("every trade carries its variant, the start it was timed from and how that was found",
      all(t["variant"] == C.vkey(t["hours"], t["exit_key"]) and t["start_how"] == "lane source" for t in Ls["trades"]), True)
sets = {(t["hours"], t["exit_key"]) for t in Ls["trades"]}
check("both entry times and all eight exits are recorded from the same entries", len(sets), 16)
aaa_hold = [t for t in Ls["trades"] if t["ticker"].endswith("AAA") and t["side"] == "yes" and t["variant"] == "t1h_hold"][0]
aaa_tp = [t for t in Ls["trades"] if t["ticker"].endswith("AAA") and t["side"] == "yes" and t["variant"] == "t1h_tp30"][0]
check("the same entry: held it wins to 1; the +30% sell fills in play when the bid runs to 0.78+",
      ((aaa_hold["entry"], aaa_hold["reason"]), (aaa_tp["entry"], aaa_tp["reason"])), ((0.55, "settled"), (0.55, "target")))
check("the night is the ET date of the start", Ls["trades"][0]["night"], C.night_of(START_E))
n_before = len(Ls["trades"])
calls_before = len(CALLS)
C.run(st, [lane], NOW + dt.timedelta(hours=1), fetch)
check("a second run does not replay the event again", (len(Ls["trades"]), any("candlesticks" in c for c in CALLS[calls_before:])), (n_before, False))
other = dict(lane, id="t_lane_2")
C.run(st, [lane, other], NOW + dt.timedelta(hours=2), fetch)
check("a second lane starts empty and fresh: never seeded from the first", (st["lanes"]["t_lane_2"]["registered"][:13], len(st["lanes"]["t_lane"]["trades"])),
      ("2026-10-25T11", n_before))
old = C.empty()
old["lanes"]["old_lane"] = dict(id="old_lane", trades=[dict(variant="t1h_hold", roi=-1, profit=-1, cost=1, night="x", reason="settled", won=False)], replayed={})
C.run(old, [lane], NOW, fetch)
check("an older lane's rows in the same ledger are never edited or deleted", len(old["lanes"]["old_lane"]["trades"]), 1)
check("a lane before its first night is not replayed", C.run(C.empty(), [dict(lane, since="2026-10-26")], NOW, fetch), {})
check("the five approved lanes are registered, each with fresh record from 2026-10-25",
      ([l["id"] for l in chaos_lanes.LANES], {l["since"] for l in chaos_lanes.LANES}),
      (["challenger_dog_tp30", "cfb_dog_tp50", "atp_coinflip_tp30", "nba_tt_cheap_tp30", "nba_ml_dog_tp50"], {"2026-10-25"}))
LD = {l["id"]: l for l in chaos_lanes.LANES}
check("entry times and headlines as approved",
      [(l["entry_hours"], l["headline"]) for l in chaos_lanes.LANES],
      [((1,), "tp30"), ((1, 24), "tp50"), ((1,), "tp30"), ((1, 24), "tp30"), ((1,), "tp50")])
check("the coin-flip lane is a watch lane; the NBA moneyline lane carries the hold-beat-the-sell caution",
      (LD["atp_coinflip_tp30"]["watch"], "HOLD beat the sell" in LD["nba_ml_dog_tp50"]["caution"]), (True, True))
ctx2 = dict(event=EV, tickers=[EV + "-AAA", EV + "-BBB"],
            entry_view=lambda t, s: dict(ask=0.45 if t.endswith("AAA") else 0.52, bid=0.43))
bp = C.one_per_event(C.band_picker(0.40, 0.60, ("yes",)))
check("a coin-flip lane buys one player only (the cheaper ask)", bp(ctx2), [(EV + "-AAA", "yes")])
dog = chaos_lanes.DOG
check("the underdog band is 10-40c YES",
      dog(dict(ctx2, entry_view=lambda t, s: dict(ask=0.30 if t.endswith("AAA") else 0.52, bid=0.28))), [(EV + "-AAA", "yes")])
chaos_lanes._BOARDS[("basketball/nba", dt.date(2026, 10, 24))] = [dict(date="2026-10-24T23:30Z", competitions=[dict(competitors=[
    dict(team=dict(abbreviation="HOU")), dict(team=dict(abbreviation="ATL"))])])]
st_ = chaos_lanes.espn_start("basketball/nba")
check("ESPN start matched by the two team codes in the ticker", st_(dict(event="KXNBAGAME-26OCT24HOUATL")), 1792884600)
check("no match gives None (the engine then uses the price path)", st_(dict(event="KXNBAGAME-26OCT24LALDEN")), None)
check("its own ledger file, not the Sandbox's", (C.PATH.endswith("data/chaos_ledger.json"), "sandbox_ledger" in C.PATH), (True, False))
only1 = dict(lane, id="t_one", entry_hours=(1,))
C.run(st, [only1], NOW, fetch)
check("a lane may buy at one entry time only", {t["hours"] for t in st["lanes"]["t_one"]["trades"]}, {1})

print("\nthe start when the lane has no source of its own")
nosrc = dict(lane, id="t_path")
del nosrc["start"]
CANDLES_SAVE = dict(CANDLES)
wild_path = [0.55] * n_pre + [0.55 + (0.03 if k % 2 else 0) for k in range(150)]
CANDLES[EV + "-AAA"] = candles_for(wild_path)
CANDLES[EV + "-BBB"] = candles_for([round(1 - x, 4) for x in wild_path])
tr, note = C.replay_event(nosrc, "KXNBAGAME", EV, fetch)
check("the price path gives the start (price path) and the trades follow it", (note, {t["start_how"] for t in tr}), (None, {"price path"}))
CANDLES[EV + "-AAA"] = candles_for([0.55] * (C.FETCH_BEFORE_H * 60))
CANDLES[EV + "-BBB"] = candles_for([0.45] * (C.FETCH_BEFORE_H * 60))
tr, note = C.replay_event(dict(nosrc, duration_min=150), "KXNBAGAME", EV, fetch)
check("no onset in the path: close minus duration_min", (note, {t["start_how"] for t in tr}), (None, {"close minus duration"}))
tr, note = C.replay_event(dict(nosrc, duration_min=None), "KXNBAGAME", EV, fetch)
check("no source, no onset and no duration: no start, the event is skipped", (tr, note), (None, "no start time"))
CANDLES.update(CANDLES_SAVE)

print("\npickers: a named side, a price band at the entry time")
ctx = dict(event=EV, tickers=[EV + "-AAA", EV + "-BBB"],
           entry_view=lambda t, s: dict(ask=0.70, bid=0.68) if (t.endswith("AAA") and s == "yes") else dict(ask=0.30, bid=0.28))
check("a named side from another lane's pick", C.named_picker({EV: [(EV + "-BBB", "no")]})(ctx), [(EV + "-BBB", "no")])
check("a named ticker takes the default side", C.named_picker({EV: [EV + "-AAA"]}, "no")(ctx), [(EV + "-AAA", "no")])
check("a named pick for another event is ignored", C.named_picker({"X": [EV + "-AAA"]})(ctx), [])
check("any side matching a price band: asks of 0.65-0.85 here", C.band_picker(0.65, 0.85)(ctx), [(EV + "-AAA", "yes")])
check("any side of every market", sorted(C.any_side_picker()(ctx)), sorted([(EV + "-AAA", "yes"), (EV + "-AAA", "no"), (EV + "-BBB", "yes"), (EV + "-BBB", "no")]))
band = dict(lane, id="t_band", picker=C.band_picker(0.75, 0.85))
tr, note = C.replay_event(band, "KXNBAGAME", EV, fetch)
check("a band picker prices each entry time on its own quote: 0.57 / 0.43 are outside 0.75-0.85, so nothing is bought", tr, [])

print("\narchived events: the historical endpoints and unsuffixed fields")
ARCH = "KXNBAGAME-26APR12ZZZYYY"
A_END = T0 + 40 * 3600
ARCH_C = {ARCH + "-ZZZ": [dict(end_period_ts=A_END - C.FETCH_BEFORE_H * 3600 + 60 * (i + 1), yes_bid=dict(close=f"{a - 0.02:.4f}"), yes_ask=dict(close=f"{a:.4f}"))
                          for i, a in enumerate(path_aaa)]}


def fetch_arch(path):
    if path.startswith("markets?"):
        return {"markets": [], "cursor": None}
    if path.startswith("historical/markets?"):
        return {"markets": [dict(mkt(ARCH + "-ZZZ", "yes"), close_time=dt.datetime.fromtimestamp(A_END, UTC).strftime("%Y-%m-%dT%H:%M:%SZ"))], "cursor": None}
    if path.startswith("historical/markets/"):
        return {"candlesticks": ARCH_C[path.split("/")[2]]}
    raise AssertionError(path)


mk, arch = C.event_markets(ARCH, fetch_arch)
check("an archived event is read from the historical listing", (arch, len(mk)), (True, 1))
tr, note = C.replay_event(dict(lane, since="2026-04-01", start=lambda ctx: A_END - 150 * 60), "KXNBAGAME", ARCH, fetch_arch)
check("and replayed from the historical candles", (note, len(tr) > 0), (None, True))

print("\nstats: day-clustered z, the hold control, the flags")
def tr_(night, roi, v="t1h_hold", cost=0.5, ex="hold"):
    return dict(variant=v, night=night, roi=roi, cost=cost, profit=roi * cost, reason="target", won=roi > 0, hours=1, exit_key=ex)


rows = [tr_("n1", 0.2)] * 4 + [tr_("n2", -0.1)] * 2
s_ = C.stats(rows)
near("ROI after fees = sum profit / sum cost", s_["roi"], (4 * 0.2 - 2 * 0.1) / 6, 1e-6)
check("trades, hit rate, nights", (s_["n"], round(s_["hit"], 3), s_["nights"]), (6, 0.667, 2))
one_night = C.stats([tr_("n1", 0.1), tr_("n1", 0.12), tr_("n1", 0.09), tr_("n1", 0.11)])
iid_z = (0.105) / ((sum((x - 0.105) ** 2 for x in [0.1, 0.12, 0.09, 0.11]) / 3) ** .5 / 2)
check("one night is not many independent trades: z stays at the independent-trades level or below", one_night["z"] <= iid_z + 1e-6, True)
check("an empty variant has no stats", C.stats([])["roi"], None)
mk_lane = lambda n, tp_roi, hold_roi, nights=9: dict(entry_hours=[1], trades=[
    tr_("n%d" % (i % nights), tp_roi, v="t1h_tp20", ex="tp20") for i in range(n)] + [
    tr_("n%d" % (i % nights), hold_roi, v="t1h_hold") for i in range(n)])
tab = C.lane_table(mk_lane(12, 0.2, -0.1))
check("12 trades: flagged for review; the hold row is the control itself", (tab["t1h_tp20"]["flag"], tab["t1h_hold"]["flag"]), ("review", "control"))
near("v hold = the target variant's ROI minus the held ROI on the same entry", tab["t1h_tp20"]["delta"], 0.3, 1e-6)
tab = C.lane_table(mk_lane(30, 0.2, -0.1))
check("30 trades beating the hold control: promotable", tab["t1h_tp20"]["flag"], "promotable")
check("30 trades that do not beat the hold control are not promotable", C.lane_table(mk_lane(30, -0.2, -0.1))["t1h_tp20"]["flag"], "review")
check("under 10 trades: too early", C.lane_table(mk_lane(5, 0.2, -0.1))["t1h_tp20"]["flag"], "too early")
check("the stop variants are judged against hold with the same stop", C.control_of("t1h_tp30_stop50"), "t1h_hold_stop50")

print("\nthe Sandbox section")
empty_html = CB.section(C.empty())
check("no lane registered says so", ('id="chaos"' in empty_html, "No chaos lane is registered yet" in empty_html), (True, True))
html = CB.section(st)
check("a lane's section: its name, the fresh-record note, every entry time and exit",
      ("Test lane" in html, "fresh record since 2026-10-24" in html, all(C.variant_label(k) in html for k in C.variants_of(Ls))), (True, True, True))
check("lane v hold control: the control column and the v hold column", ("Hold control" in html, "v hold" in html), (True, True))
check("the trade list names the entry time, price and the exit reason letters", ("h before" in html and "T target, S stop, H held" in html), True)
check("the flags and the 10 / 30 rule are stated", ("too early" in html, "promotion needs 30 AND a better ROI than its hold control" in html), (True, True))
check("it says nothing is bought during the event, and no in-play entry rules remain",
      ("Nothing is bought during the event" in html, "dip" in html.lower(), "momentum" in html.lower()), (True, False, False))
check("tables are header-row tables (the Sandbox labels them for a phone)", ("<thead>" not in html, "<tr><th>Entry · exit</th>" in html), (True, True))
check("public copy passes the guard", sandbox_audit.COPY_RE.search(html), None)
import sandbox_build as SB
check("the Sandbox page carries the section and its nav link", ("chaos" in SB.chaos_html(), '("chaos", "Chaos")' in open("sandbox_build.py").read()), (True, True))

print("\nlane windows: a nightly replay read")
at = lambda h, m: dt.datetime(2026, 10, 25, h, m, tzinfo=UTC)
got = lambda t: sorted(k for w, k in W.due(t, {"quotes": []}, [], []) if w["lane"] == "chaos")
check("04:00 ET (08:00Z in daylight time): read 1; 08:35Z read 2; 10:30Z none", (got(at(8, 5)), got(at(8, 35)), got(at(10, 30))), ([1], [2], []))
check("its stamp file", W.STAMP["chaos"], "data/chaos_window/request.txt")

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
