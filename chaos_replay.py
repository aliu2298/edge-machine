#!/usr/bin/env python3
"""Chaos replay (2026-10-25): the shared paper-replay engine for pre-start take-profit lanes.

Phase 1 of the "chaos trading" Sandbox. A lane BUYS BEFORE THE EVENT STARTS, at a set time before
the start (1 hour before, and a 24-hour variant), and at the same moment places a RESTING LIMIT
SELL at a target. The in-play swings either fill that sell or the position settles. Nothing is
bought during the event: no dip, wave or momentum triggers (the in-play entries E0-E3 of the first
draft are withdrawn). Nothing here trades and nothing polls live: every lane is SIMULATED nightly
from Kalshi's 1-minute candles of events that have already settled, using only the minutes up to
each decision. PAPER ONLY: no Production listing, no PAIR_OVERRIDES, no live orders. Its own ledger,
data/chaos_ledger.json.

THE ENGINE. A lane is a config (chaos_lanes.py is where lanes plug in; Phase 1 ships none):

    id             the lane's name; its record starts FRESH from its first replayed night and never
                   inherits an old lane's rows (old lanes and ledgers are left exactly as they are)
    series         Kalshi series tickers to replay (settled events only)
    picker         which market and side to buy: picker(ctx) -> [(ticker, "yes"|"no"), ...]
                   (named_picker, band_picker, any_side_picker); ctx["entry_view"](ticker, side) is
                   the side's quote at the entry time being replayed
    entry_hours    the entry times before the start, default (1, 24)
    start          optional: start(ctx) -> the event's start as epoch seconds, from the lane's own
                   kickoff / tip source (the ESPN times other lanes use); without it the start is
                   detected from the price path (below)
    duration_min   minutes from start to close, the fallback start when the path shows no onset
    since          first night to replay (ISO date); default the day before the lane's first run

ENTRY: at start - h hours (h in entry_hours) buy the picked side at the ask at the first tight quote
(spread 3c or less) in the 15 minutes from then, only while still before the start. One trade per
market, side and entry time. A market with no quote that early has no trade at that time.
EXITS, all from the same entry, in parallel (variants): a resting limit sell at +20%, +30%, +50% or +100% ROI
after fees, or none (hold to settlement); each with no stop or a -50% stop. The limit rests from the
entry on, pre-game and in play. A sell fills only when the side's bid trades 1c through the limit
inside a minute (the limit price is then the fill); a stop fills at the stop price, or the minute's
best bid if the whole minute is below it; a minute touching both takes the stop. Anything not exited
is held to Kalshi's settlement.
FEES: taker 0.07 p (1 - p) on entry and on a stop; maker 0.0175 p (1 - p) on a limit exit.
CONTROL: the same entry HELD TO SETTLEMENT. Every lane shows hold v each target; the stop variants
are compared with the held-with-the-same-stop row. A variant is flagged for review at 10 trades;
promotion needs 30 AND a better ROI than its hold control. z is day-clustered (by the ET date of the
start), never below the independent-trades z.

START TIME. Where a lane has its own source, `start` wins. Otherwise the onset of play is read from
the price path: the first minute whose rolling 10-minute sum of |change in the first market's mid|
reaches 0.10 and stays active, corrected by ONSET_LAG_MIN (18 minutes, measured on 14 NBA games
against ESPN's tip times: detected 13-27 minutes late, median 18) and falling back to the close
minus duration_min. Only candles up to the entry minute are used for the entry quote; the start only
places the entry minute on the clock, as the clock does for a live entry.

DATA: series/{s}/events/{e}/candlesticks?period_interval=1 (yes_bid / yes_ask close, high, low in
*_dollars); archived events (settled before Kalshi's historical cutoff) come from
historical/markets/{t}/candlesticks (the same fields without the suffix). A minute with no candle
carries the last quote forward. Requests go through daily_track.get, about 8 a second.
"""
import datetime as dt
import json
import os
import re
import sys
from zoneinfo import ZoneInfo

import daily_track as D

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "data", "chaos_ledger.json")
ET = ZoneInfo("America/New_York")
UTC = dt.timezone.utc
TAKER, MAKER = 0.07, 0.0175
MAX_SPREAD = 0.03
ASK_RANGE = (0.02, 0.98)
FILL_MARGIN = 0.01             # a limit sell fills when the bid trades this far through it
TARGETS = (0.20, 0.30, 0.50, 1.00)
STOP = -0.50
ENTRY_HOURS = (1, 24)
ENTRY_GRACE_MIN = 15           # the first tight quote within this many minutes of the entry time
FETCH_BEFORE_H = 24 + 9        # candles from this many hours before the close (an entry 24h before the start)
ONSET_LAG_MIN = 18
ONSET_ROLL, ONSET_SUM, ONSET_KEEP = 10, 0.10, 0.08
MIN_NIGHTS_Z = 3               # z is night-clustered: fewer clusters than this has no meaningful variance
REVIEW_N, PROMOTE_N = 10, 30
MAX_EVENTS_PER_RUN = 40        # per lane, per run: a backlog finishes over the next runs
VERSION = "chaos-v2"
EPS = 1e-9


def _exits():
    out = {}
    for tp in (None,) + TARGETS:
        for stop in (None, STOP):
            key = ("hold" if tp is None else f"tp{round(tp * 100)}") + ("" if stop is None else f"_stop{round(-stop * 100)}")
            out[key] = dict(tp=tp, stop=stop)
    return out


EXITS = _exits()                # hold, hold_stop50, tp20, tp20_stop50, tp30, ... tp50_stop50
# The cheap-side SPLIT exit (2026-10-27, Olu: "the cheap-side split is the standard"): half the stake
# rests at 2x the entry ask, half at 3x, each capped at 0.98; a leg fills only when a TRADE prints at or
# above it (the candle's price.high, never the bid); a leg not filled is held to settlement. Maker fee
# on a filled leg. Every lane carries it beside its own targets (LANE_EXITS); a lane that recorded
# entries before it gains the split variant by the additive backfill below, its rows unedited.
SPLIT = "split"
SPLIT_LEGS = ((2.0, 0.5), (3.0, 0.5))
SPLIT_CAP = 0.98
LANE_EXITS = tuple(EXITS) + (SPLIT,)


def lane_exits(lane):
    """The exit keys a lane is replayed with: its own `exits`, else every target and the split."""
    return tuple(lane.get("exits") or LANE_EXITS)


def vkey(hours, exit_key):
    return f"t{hours}h_{exit_key}"


def split_key(key):
    h, _, rest = key.partition("_")
    return int(h[1:-1]), rest


def exit_label(key):
    if key == SPLIT:
        return "split: half at 2x, half at 3x"
    v = EXITS[key]
    base = "hold to settlement" if v["tp"] is None else f"sell at +{round(v['tp'] * 100)}%"
    return base + ("" if v["stop"] is None else f", stop {round(v['stop'] * 100)}%")


def variant_label(key):
    h, ex = split_key(key)
    return f"{h}h before · {exit_label(ex)}"


def control_of(key):
    """The variant a key is judged against: the same entry time and stop, held to settlement."""
    h, ex = split_key(key)
    if ex == SPLIT:
        return vkey(h, "hold")
    return vkey(h, "hold" + ("" if EXITS[ex]["stop"] is None else f"_stop{round(-EXITS[ex]['stop'] * 100)}"))


# ---------- fees, targets, stops ----------

def taker_fee(p):
    return TAKER * p * (1 - p)


def maker_fee(p):
    return MAKER * p * (1 - p)


def cost(p):
    """What one contract costs at ask p: the price and the taker fee."""
    return p + taker_fee(p)


def _bisect(f, lo, hi):
    for _ in range(60):
        mid = (lo + hi) / 2
        if f(mid) < 0:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def target_price(entry, roi):
    """The limit-sell price that returns `roi` after the entry fee and the maker fee, or None when
    even a 0.99 sell cannot."""
    need = cost(entry) * (1 + roi)
    f = lambda L: L - maker_fee(L) - need
    if f(0.99) < 0:
        return None
    return round(_bisect(f, entry, 0.99), 4)


def stop_price(entry, roi=STOP):
    """The bid at which a taker sell loses `roi` after both fees."""
    need = cost(entry) * (1 + roi)
    f = lambda S: S - taker_fee(S) - need
    if f(entry) < 0:
        return None
    return round(_bisect(f, 0.0001, entry), 4)


# ---------- candles ----------

def _f(d, k):
    d = d or {}
    v = d.get(k + "_dollars", d.get(k))
    return D.number(v)


def normalise(c):
    """One candle -> dict(ts, bid, ask, bid_lo, bid_hi, ask_lo, ask_hi) in YES terms, or None."""
    ts = c.get("end_period_ts")
    yb, ya = c.get("yes_bid") or {}, c.get("yes_ask") or {}
    px = c.get("price") or {}
    row = dict(ts=ts, bid=_f(yb, "close"), ask=_f(ya, "close"), bid_lo=_f(yb, "low"), bid_hi=_f(yb, "high"),
               ask_lo=_f(ya, "low"), ask_hi=_f(ya, "high"), px_hi=_f(px, "high"), px_lo=_f(px, "low"))
    if not isinstance(ts, (int, float)) or row["bid"] is None or row["ask"] is None:
        return None
    for k in ("bid_lo", "bid_hi"):
        row[k] = row["bid"] if row[k] is None else row[k]
    for k in ("ask_lo", "ask_hi"):
        row[k] = row["ask"] if row[k] is None else row[k]
    return row


def dense(candles, start_ts, end_ts):
    """One row per minute from start_ts to end_ts (the minute's END timestamp, both on a minute), the
    last quote carried forward through a minute with no candle (its high and low then equal that quote).
    Minutes before the first candle have no row."""
    rows = sorted((r for r in (normalise(c) for c in candles or []) if r), key=lambda r: r["ts"])
    out, k, last, t = [], 0, None, start_ts
    while t <= end_ts:
        while k < len(rows) and rows[k]["ts"] <= t:
            last = rows[k]
            k += 1
        if last is not None:
            if last["ts"] == t:
                out.append(dict(last))
            else:
                out.append(dict(ts=t, bid=last["bid"], ask=last["ask"], bid_lo=last["bid"], bid_hi=last["bid"],
                                ask_lo=last["ask"], ask_hi=last["ask"], px_hi=None, px_lo=None))
        t += 60
    return out


def view(m, side):
    """A minute row seen from one side: ask / bid at the close, the minute's bid high/low, and the
    minute's TRADED high (traded_hi: YES price.high, or 1 - price.low for the NO; None without a trade)."""
    if side == "yes":
        return dict(ts=m["ts"], ask=m["ask"], bid=m["bid"], bid_hi=m["bid_hi"], bid_lo=m["bid_lo"], ask_lo=m["ask_lo"],
                    traded_hi=m.get("px_hi"))
    lo = m.get("px_lo")
    return dict(ts=m["ts"], ask=round(1 - m["bid"], 4), bid=round(1 - m["ask"], 4), bid_hi=round(1 - m["ask_lo"], 4),
                bid_lo=round(1 - m["ask_hi"], 4), ask_lo=round(1 - m["bid_hi"], 4),
                traded_hi=None if lo is None else round(1 - lo, 4))


def tight(v, spread=MAX_SPREAD):
    return v["bid"] > 0 and v["ask"] - v["bid"] <= spread + EPS and ASK_RANGE[0] - EPS <= v["ask"] <= ASK_RANGE[1] + EPS


# ---------- the start of the event ----------

def detect_onset(minutes, lag_min=ONSET_LAG_MIN):
    """The event's start (epoch seconds) read from one market's dense price path, or None.

    The first minute whose rolling ONSET_ROLL-minute sum of |change in the mid| reaches ONSET_SUM and
    stays active (14 of the next 20 minutes at ONSET_KEEP or more), less the detection lag."""
    if len(minutes) < ONSET_ROLL + 25:
        return None
    mids = [(m["bid"] + m["ask"]) / 2 for m in minutes]
    ch = [0.0] + [abs(mids[i] - mids[i - 1]) for i in range(1, len(mids))]
    roll = [sum(ch[max(0, i - ONSET_ROLL + 1):i + 1]) for i in range(len(ch))]
    for i in range(len(roll) - 20):
        if roll[i] >= ONSET_SUM and sum(1 for x in roll[i:i + 20] if x >= ONSET_KEEP) >= 14:
            return minutes[i]["ts"] - lag_min * 60
    return None


# ---------- one trade ----------

def entry_index(vs, target_ts, start_ts, spread=MAX_SPREAD):
    """The minute to buy at: the first tight quote from target_ts within the grace window, before the start."""
    for i, v in enumerate(vs):
        if v["ts"] < target_ts:
            continue
        if v["ts"] > target_ts + ENTRY_GRACE_MIN * 60 or v["ts"] >= start_ts:
            return None
        if tight(v, spread):
            return i
    return None


def _trade(vs, i, won_side, var):
    """One trade bought at the close of minute i of the side views `vs`, exited per variant `var`."""
    n = len(vs)
    entry = vs[i]["ask"]
    c = cost(entry)
    tp = None if var["tp"] is None else target_price(entry, var["tp"])
    stop = None if var["stop"] is None else stop_price(entry, var["stop"])
    exit_i = exit_p = reason = None
    for j in range(i + 1, n):
        w = vs[j]
        if stop is not None and w["bid_lo"] <= stop + EPS:        # a minute touching both takes the stop
            exit_i, exit_p, reason = j, min(stop, w["bid_hi"]), "stop"
            break
        if tp is not None and w["bid_hi"] >= tp + FILL_MARGIN - EPS:
            exit_i, exit_p, reason = j, tp, "target"
            break
    if exit_i is None:
        exit_i, reason, exit_p = n - 1, "settled", (1.0 if won_side else 0.0)
        proceeds = exit_p
    elif reason == "stop":
        proceeds = exit_p - taker_fee(exit_p)
    else:
        proceeds = exit_p - maker_fee(exit_p)
    return dict(entry_i=i, entry_ts=vs[i]["ts"], entry=round(entry, 4), spread=round(entry - vs[i]["bid"], 4),
                exit_i=exit_i, exit_ts=vs[exit_i]["ts"],
                exit=round(exit_p, 4), reason=reason, cost=round(c, 5), profit=round(proceeds - c, 5),
                roi=round((proceeds - c) / c, 4), won=proceeds > c, target=tp, stop=stop,
                unreachable=(var["tp"] is not None and tp is None))


def split_targets(entry):
    return [(m, w, round(min(entry * m, SPLIT_CAP), 2)) for m, w in SPLIT_LEGS]


def _split_trade(vs, i, won_side):
    """The cheap-side split from minute i: two resting legs, filled only on a traded print at or above
    each target; a leg not filled is held to settlement."""
    entry = vs[i]["ask"]
    c = cost(entry)
    pay = 1.0 if won_side else 0.0
    legs, proceeds = [], 0.0
    for mult, share, target in split_targets(entry):
        fill = next((j for j in range(i + 1, len(vs)) if vs[j].get("traded_hi") is not None
                     and vs[j]["traded_hi"] >= target - EPS), None)
        legs.append(dict(multiple=mult, target=target, filled_ts=vs[fill]["ts"] if fill is not None else None))
        proceeds += share * ((target - maker_fee(target)) if fill is not None else pay)
    last = max([l["filled_ts"] for l in legs if l["filled_ts"]] or [vs[-1]["ts"]])
    if any(l["filled_ts"] is None for l in legs):
        last = vs[-1]["ts"]
    return dict(entry_i=i, entry_ts=vs[i]["ts"], entry=round(entry, 4), spread=round(entry - vs[i]["bid"], 4),
                exit_i=None, exit_ts=last,
                exit=None, reason="split", cost=round(c, 5), profit=round(proceeds - c, 5),
                roi=round((proceeds - c) / c, 4), won=proceeds > c, target=None, stop=None, unreachable=False,
                legs=legs, filled_2x=legs[0]["filled_ts"] is not None, filled_3x=legs[1]["filled_ts"] is not None,
                side_won=won_side)


def simulate(minutes, side, result, start_ts, hours, exit_key, spread=MAX_SPREAD):
    """One variant's trade in one market and side: bought `hours` before start_ts, exited per exit_key.
    Returns [trade] or [] when there is no tight quote at that time."""
    vs = [view(m, side) for m in minutes]
    i = entry_index(vs, start_ts - int(hours * 3600), start_ts, spread)
    if i is None or i >= len(vs) - 1:
        return []
    if exit_key == SPLIT:
        return [_split_trade(vs, i, result == side)]
    return [_trade(vs, i, result == side, EXITS[exit_key])]


# ---------- pickers: which market and side a lane buys ----------

def band_picker(lo, hi, sides=("yes", "no"), spread=MAX_SPREAD):
    """Any side whose ask at the entry time is in [lo, hi] (and tight: spread at most `spread`)."""
    def pick(ctx):
        return [(t, s) for t in ctx["tickers"] for s in sides
                if (v := ctx["entry_view"](t, s)) and tight(v, spread) and lo - EPS <= v["ask"] <= hi + EPS]
    return pick


def any_side_picker(sides=("yes", "no")):
    """Every side of every market of the event."""
    return lambda ctx: [(t, s) for t in ctx["tickers"] for s in sides]


def one_per_event(picker):
    """Keep only the cheapest-ask pick of an event (a coin-flip lane must not buy both players)."""
    def pick(ctx):
        got = picker(ctx)
        if not got:
            return []
        ask = lambda ts: ((ctx["entry_view"](*ts) or {}).get("ask") or 9, ts[0])
        return [min(got, key=ask)]
    return pick


def named_picker(table, default_side="yes"):
    """A named side from another lane's pick: table maps an event ticker to [(ticker, side)] or to
    a ticker (taken on `default_side`); a callable is called with the event ticker."""
    def pick(ctx):
        got = table(ctx["event"]) if callable(table) else table.get(ctx["event"])
        out = []
        for x in got or []:
            t, s = (x, default_side) if isinstance(x, str) else x
            if t in ctx["tickers"]:
                out.append((t, s))
        return out
    return pick


# ---------- events and markets ----------

_DATE = re.compile(r"-(\d{2})([A-Z]{3})(\d{2})")
MON = "JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split()


def event_date(ticker):
    """The date code of an event ticker (KXNBAGAME-26OCT24HOUATL -> 2026-10-24), or None."""
    m = _DATE.search(str(ticker or ""))
    if not m or m.group(2) not in MON:
        return None
    try:
        return dt.date(2000 + int(m.group(1)), MON.index(m.group(2)) + 1, int(m.group(3)))
    except ValueError:
        return None


def _ts(v):
    t = D.instant(v)
    return None if t is None else int(t.timestamp())


def list_events(series, since, fetch, until=None, cap=400):
    """Settled event tickers of a series dated since-1 day to until+1 day, newest first."""
    out, path, pages = [], f"events?series_ticker={series}&status=settled&limit=200", 0
    floor = since - dt.timedelta(days=1)
    top = (until or dt.date.today()) + dt.timedelta(days=1)
    while path and pages < 40:
        d = fetch(path)
        evs = d.get("events") or []
        dates = [event_date(e.get("event_ticker")) for e in evs]
        out += [e["event_ticker"] for e, day in zip(evs, dates) if day and floor <= day <= top]
        pages += 1
        if not evs or (dates and all(x and x < floor for x in dates)) or len(out) >= cap:
            break
        cur = d.get("cursor")
        path = f"events?series_ticker={series}&status=settled&limit=200&cursor={cur}" if cur else None
    return sorted(set(out), reverse=True)


def event_markets(event, fetch):
    """(markets, archived): the event's markets, from the live listing or, once Kalshi has archived
    it, the historical one."""
    ms = D.pages(f"markets?limit=200&event_ticker={event}", "markets", fetch)
    if ms:
        return ms, False
    return D.pages(f"historical/markets?limit=200&event_ticker={event}", "markets", fetch), True


def settled_result(m):
    if m.get("status") not in ("finalized", "settled"):
        return None
    return m.get("result") if m.get("result") in ("yes", "no") else None


def fetch_candles(series, event, markets, start_ts, end_ts, fetch, archived):
    """{ticker: [candle, ...]} for the event's markets over [start_ts, end_ts]."""
    if not archived:
        try:
            d = fetch(f"series/{series}/events/{event}/candlesticks?start_ts={start_ts}&end_ts={end_ts}&period_interval=1")
        except Exception:                       # some series (team totals) have no event-level candles: go per market
            d = {}
        got = dict(zip(d.get("market_tickers") or [], d.get("market_candlesticks") or []))
        if any(got.values()):
            return got
        out = {}
        for m in markets:
            try:
                x = fetch(f"series/{series}/markets/{m['ticker']}/candlesticks?start_ts={start_ts}&end_ts={end_ts}&period_interval=1")
            except Exception:
                x = {}
            out[m["ticker"]] = x.get("candlesticks") or x.get("market_candlesticks") or []
        if any(out.values()):
            return out
    out = {}
    for m in markets:
        d = fetch(f"historical/markets/{m['ticker']}/candlesticks?start_ts={start_ts}&end_ts={end_ts}&period_interval=1")
        out[m["ticker"]] = d.get("candlesticks") or d.get("market_candlesticks") or []
    return out


def night_of(ts):
    return dt.datetime.fromtimestamp(ts, UTC).astimezone(ET).date().isoformat()


def replay_event(lane, series, event, fetch, now=None):
    """Replay one settled event for one lane -> (trades, note). Every trade carries its variant key
    (entry hours and exit), the start it was timed from and how that start was found."""
    markets, archived = event_markets(event, fetch)
    results = {m["ticker"]: settled_result(m) for m in markets}
    if not markets or any(r is None for r in results.values()):
        return None, "not settled with a clean result"
    closes = [x for x in (_ts(m.get("close_time")) for m in markets) if x]
    if not closes:
        return None, "no close time"
    end_ts = max(closes) - max(closes) % 60
    lo = end_ts - FETCH_BEFORE_H * 3600
    candles = fetch_candles(series, event, markets, lo, end_ts, fetch, archived)
    mins = {t: dense(c, lo, end_ts) for t, c in candles.items() if c}
    if not mins:
        return None, "no candles"
    ctx0 = dict(event=event, series=series, tickers=sorted(mins), markets={m["ticker"]: m for m in markets},
                close_ts=end_ts, minutes=mins)
    start_ts, how = None, None
    if callable(lane.get("start")):
        start_ts, how = lane["start"](ctx0), "lane source"
    if not start_ts:
        onset = detect_onset(mins[sorted(mins)[0]])
        if onset:
            start_ts, how = onset - onset % 60, "price path"
    if not start_ts and lane.get("duration_min"):
        start_ts, how = end_ts - int(lane["duration_min"]) * 60, "close minus duration"
    if not start_ts:
        return None, "no start time"
    start_ts -= start_ts % 60
    night = night_of(start_ts)
    spread = lane.get("max_spread", MAX_SPREAD)
    trades = []
    for hours in lane.get("entry_hours") or ENTRY_HOURS:
        target = start_ts - int(hours * 3600)

        def entry_view(t, s, target=target):
            ms = mins.get(t) or []
            i = entry_index([view(m, "yes") for m in ms], target, start_ts, spread)
            return view(ms[i], s) if i is not None else None
        ctx = dict(ctx0, entry_view=entry_view, start_ts=start_ts, hours=hours)
        for ticker, side in dict.fromkeys(lane["picker"](ctx) or []):
            ms = mins.get(ticker)
            if not ms:
                continue
            for ex in lane_exits(lane):
                for t in simulate(ms, side, results[ticker], start_ts, hours, ex, spread):
                    trades.append(dict(t, variant=vkey(hours, ex), hours=hours, exit_key=ex, event=event, ticker=ticker,
                                       side=side, night=night, start_ts=start_ts, start_how=how))
    return trades, None


# ---------- the ledger ----------

def empty():
    return {"version": VERSION, "lanes": {}, "runs": []}


def load(path=PATH):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return empty()


def lane_state(state, lane, now):
    """The lane's own record, created fresh on its first run: never seeded from any other lane."""
    L = state.setdefault("lanes", {}).get(lane["id"])
    if L is None:
        since = lane.get("since") or (now.astimezone(ET).date() - dt.timedelta(days=1)).isoformat()
        L = state["lanes"][lane["id"]] = dict(
            id=lane["id"], label=lane.get("label") or lane["id"], registered=now.isoformat(), since=since,
            series=list(lane["series"]), entry_hours=list(lane.get("entry_hours") or ENTRY_HOURS),
            duration_min=lane.get("duration_min"), note=lane.get("note") or "", headline=lane.get("headline"),
            caution=lane.get("caution") or "", watch=bool(lane.get("watch")), replayed={}, trades=[], skipped={})
    # The lane's exits as configured now (the split joined every lane on 2026-10-27; additive only).
    L["exits"] = list(lane_exits(lane))
    for k in ("label", "note", "headline", "first"):
        if lane.get(k) is not None:
            L[k] = lane[k]
    return L


def _backfill(L, lane, now, fetch, errs):
    """Re-replay events whose entries lack an exit variant added since (e.g. +100%) and append ONLY the missing
    variants of the entries already recorded; nothing existing is edited. Skips an event that has no recorded entry."""
    by_event = {}
    for t in L["trades"]:
        by_event.setdefault(t["event"], set()).add(t["exit_key"])
    todo = [e for e, ks in by_event.items() if set(lane_exits(lane)) - ks][:MAX_EVENTS_PER_RUN]
    for event in todo:
        have = {(t["ticker"], t["side"], t["hours"], t["exit_key"]) for t in L["trades"] if t["event"] == event}
        entries = {(a, b, c) for a, b, c, _ in have}
        series = next((x for x in lane["series"] if event.startswith(x + "-")), None)
        if not series:
            continue
        try:
            trades, note = replay_event(lane, series, event, fetch, now)
        except Exception as e:                                  # noqa: BLE001
            errs.append(f"{lane['id']} backfill {event}: {str(e)[:80]}")
            continue
        if note:
            continue
        L["trades"] += [t for t in trades if (t["ticker"], t["side"], t["hours"]) in entries
                        and (t["ticker"], t["side"], t["hours"], t["exit_key"]) not in have]


def run(state, lanes, now=None, fetch=D.get):
    """Replay every settled, not yet replayed event of every lane. Returns {lane id: new trades}."""
    now = now or dt.datetime.now(UTC)
    new, errs = {}, []
    for lane in lanes:
        L = lane_state(state, lane, now)
        since = dt.date.fromisoformat(L["since"])
        done = 0
        for series in lane["series"]:
            try:
                events = list_events(series, since, fetch, until=now.astimezone(ET).date())
            except Exception as e:                              # noqa: BLE001
                errs.append(f"{lane['id']} {series}: listing {str(e)[:80]}")
                continue
            for event in events:
                day = event_date(event)
                if event in L["replayed"] or event in L["skipped"] or day is None or day < since - dt.timedelta(days=1):
                    continue
                if done >= MAX_EVENTS_PER_RUN:
                    break
                try:
                    trades, note = replay_event(lane, series, event, fetch, now)
                except Exception as e:                          # noqa: BLE001
                    errs.append(f"{lane['id']} {event}: {str(e)[:80]}")
                    continue
                if note:
                    if note != "not settled with a clean result":
                        L["skipped"][event] = note
                    continue
                if trades and min(t["night"] for t in trades) < L["since"]:
                    L["replayed"][event] = "before the lane's first night"
                    continue
                L["trades"] += trades
                L["replayed"][event] = len({(t["ticker"], t["side"]) for t in trades})
                new.setdefault(lane["id"], []).extend(trades)
                done += 1
    for lane in lanes:                                          # new exit variants reach entries already on the ledger
        L = state["lanes"].get(lane["id"])
        if L:
            _backfill(L, lane, now, fetch, errs)
    state["last_run"] = now.isoformat()
    state["error"] = "; ".join(errs)[:1000] or None
    state["runs"] = (state.get("runs") or [])[-50:] + [dict(at=now.isoformat(), new={k: len(v) for k, v in new.items()})]
    return new


# ---------- stats ----------

def _rows(trades, variant):
    return [t for t in trades if t["variant"] == variant]


def stats(rows):
    """n, hit rate, ROI after fees (sum profit / sum cost), z by night (None under 3 nights or a degenerate variance), nights, per-reason counts."""
    n = len(rows)
    if not n:
        return dict(n=0, won=0, hit=None, roi=None, z=None, nights=0, reasons={})
    cost_sum = sum(t["cost"] for t in rows)
    roi = sum(t["profit"] for t in rows) / cost_sum
    r = [t["roi"] for t in rows]
    mean = sum(r) / n
    nights = {}
    for t in rows:
        nights.setdefault(t["night"], []).append(t["roi"] - mean)
    iid_se = (sum((x - mean) ** 2 for x in r) / max(n - 1, 1)) ** 0.5 / n ** 0.5
    clu_se = (sum(sum(g) ** 2 for g in nights.values())) ** 0.5 / n
    se = max(iid_se, clu_se)
    reasons = {}
    for t in rows:
        reasons[t["reason"]] = reasons.get(t["reason"], 0) + 1
    return dict(n=n, won=sum(1 for t in rows if t["won"]), hit=sum(1 for t in rows if t["won"]) / n, roi=roi,
                z=(mean / se if len(nights) >= MIN_NIGHTS_Z and se > 1e-6 else None), nights=len(nights), reasons=reasons)


def variants_of(L):
    return [vkey(h, ex) for h in (L.get("entry_hours") or ENTRY_HOURS) for ex in (L.get("exits") or EXITS)]


def lane_table(L):
    """{variant: dict(lane stats, control stats, delta, flag)}: each variant against the same entry held
    to settlement (the control), the hold rows against nothing."""
    out = {}
    trades = L.get("trades") or []
    for key in variants_of(L):
        a = stats(_rows(trades, key))
        ctl = control_of(key)
        c = stats(_rows(trades, ctl)) if ctl != key else None
        delta = None if c is None or a["roi"] is None or c["roi"] is None else a["roi"] - c["roi"]
        flag = ("too early" if a["n"] < REVIEW_N else
                "control" if c is None else
                "promotable" if a["n"] >= PROMOTE_N and delta is not None and delta > 0 else
                "review")
        out[key] = dict(lane=a, control=c, delta=delta, flag=flag)
    return out


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    import chaos_lanes
    out = argv[argv.index("--out") + 1] if "--out" in argv else PATH
    lanes = list(chaos_lanes.LANES)
    if "--demo" in argv:
        lanes = [chaos_lanes.DEMO]
    if "--lane" in argv:
        lanes = [x for x in lanes if x["id"] == argv[argv.index("--lane") + 1]]
    if "--since" in argv:
        lanes = [dict(x, since=argv[argv.index("--since") + 1]) for x in lanes]
    if not lanes:                                   # Phase 1: no lane registered, nothing to replay or write
        print("no chaos lane registered; nothing to do")
        return 0
    state = load(out)
    new = run(state, lanes)
    tmp = out + ".tmp"
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(tmp, "w") as f:
        json.dump(state, f, indent=1, sort_keys=True)
        f.write("\n")
    os.replace(tmp, out)
    print("lanes", [x["id"] for x in lanes], "new trades", {k: len(v) for k, v in new.items()}, "error", state["error"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
