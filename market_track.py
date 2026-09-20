#!/usr/bin/env python3
"""market_track.py — the Sandbox's TRADING lane: stock rules, logged and graded like bets.

The sports lane taught the method and it carries over unchanged:

  * every rule is PRE-REGISTERED — thresholds fixed in RULES below, with the reasoning, before
    it logs a trade. Nothing here is tuned after the fact;
  * a trade is logged only from bars that CLOSED BEFORE its entry, and it enters at the NEXT
    bar's open. A rule that needs the signal bar's close to enter is a backtest, not a record;
  * costs are charged on both sides (market_sources.COST_BPS_PER_SIDE). A rule that only works
    at zero cost is not a rule — the BTC day-trading tests of 2026-09-19 made that concrete;
  * a rule is judged PER ENTRY DAY, not per trade. Ten names bought the same morning rise and
    fall with the market, so they are one result, the same correction the commodities and
    corners lanes use;
  * and against two baselines: SPY over the identical holding period, and the same stocks'
    own average move over that window. Beating a rising market is not an edge.

Usage:  python3 market_track.py            scan for new trades, grade the open ones
"""
import datetime
import json
import math
import os
import statistics

import market_sources as M

ROOT = os.path.dirname(os.path.abspath(__file__))
LEDGER = os.path.join(ROOT, "data", "market_ledger.json")

STAKE = 1000.0          # notional per trade, so P/L reads in dollars as well as percent
READ_FLOOR = 30         # entry days before a record is read at all
EARLY_N = 10            # below this, not even a lean is shown
BENCH = "SPY"


# --------------------------------------------------------------------------- indicators
def sma(xs, n):
    return sum(xs[-n:]) / n if len(xs) >= n else None


def rsi(closes, n=2):
    """Wilder's RSI over `n` periods; None until there are enough closes."""
    if len(closes) < n + 1:
        return None
    gains = losses = 0.0
    for a, b in zip(closes[-n - 1:-1], closes[-n:]):
        d = b - a
        gains += max(d, 0.0)
        losses += max(-d, 0.0)
    if losses == 0:
        return 100.0
    rs = (gains / n) / (losses / n)
    return 100 - 100 / (1 + rs)


def atr(bars, n=14):
    if len(bars) < n + 1:
        return None
    trs = []
    for prev, b in zip(bars[-n - 1:-1], bars[-n:]):
        trs.append(max(b["h"] - b["l"], abs(b["h"] - prev["c"]), abs(b["l"] - prev["c"])))
    return sum(trs) / len(trs)


# --------------------------------------------------------------------------- the rules
# Each rule: signal(history) -> True when the SIGNAL fires on history[-1]; the trade then
# enters at the next bar's open. exit(bars_since_entry, entry) -> index of the bar whose OPEN
# the trade leaves at, or None to keep holding. Thresholds are fixed here, once.
def _sw_rsi2(h):
    c = [b["c"] for b in h]
    ma200, ma5, r = sma(c, 200), sma(c, 5), rsi(c, 2)
    return bool(ma200 and r is not None and c[-1] > ma200 and r < 5 and c[-1] < (ma5 or 0))


def _sw_rsi2_exit(after, entry):
    for i, b in enumerate(after):
        c = [x["c"] for x in entry["hist"] + after[:i + 1]]
        if b["c"] > (sma(c, 5) or 1e9) or i >= 9:
            return i
    return None


def _sw_breakout(h):
    c = [b["c"] for b in h]
    if len(c) < 252:
        return False
    vol50 = sum(b["v"] for b in h[-50:]) / 50
    return c[-1] >= max(c[-252:]) and h[-1]["v"] >= 1.5 * vol50


def _sw_breakout_exit(after, entry):
    for i, b in enumerate(after):
        c = [x["c"] for x in entry["hist"] + after[:i + 1]]
        if b["c"] < (sma(c, 20) or 0) or i >= 39:
            return i
    return None


def _sw_gap_reversal(h):
    if len(h) < 201:
        return False
    prev, b = h[-2], h[-1]
    gap = (b["o"] - prev["c"]) / prev["c"]
    return bool(gap <= -0.03 and b["c"] > b["o"] and prev["c"] > (sma([x["c"] for x in h], 200) or 1e9))


def _sw_gap_exit(after, entry):
    return 4 if len(after) > 4 else None


def _sw_ma_cross(h):
    """The swing-trader project's own rule (June 2026 config.yaml), unchanged: a 10/100 MA
    cross up within the last 3 sessions, RSI(14) between 50 and 75."""
    c = [b["c"] for b in h]
    if len(c) < 120:
        return False
    fast_now, slow_now = sma(c, 10), sma(c, 100)
    if not (fast_now and slow_now and fast_now > slow_now):
        return False
    crossed = any(sma(c[:-k], 10) is not None and sma(c[:-k], 100) is not None
                  and sma(c[:-k], 10) <= sma(c[:-k], 100) for k in range(1, 4))
    r = rsi(c, 14)
    return bool(crossed and r is not None and 50 <= r <= 75)


def _sw_ma_cross_exit(after, entry):
    """Leave when the fast average falls back under the slow one, or after 60 sessions."""
    for i, b in enumerate(after):
        c = [x["c"] for x in entry["hist"] + after[:i + 1]]
        f, sl = sma(c, 10), sma(c, 100)
        if (f and sl and f < sl) or i >= 59:
            return i
    return None


RULES = {
    "sw_rsi2_pullback": dict(
        lane="swing", label="RSI(2) pullback in an uptrend", signal=_sw_rsi2, exit=_sw_rsi2_exit,
        note="Pre-registered 2026-09-19 (Connors' published RSI-2 rule, thresholds unchanged). "
             "Buy the next open when a stock closes above its 200-day average, below its 5-day "
             "average, with a 2-period RSI under 5. Leave at the open after the first close back "
             "above the 5-day average, or after 10 sessions, whichever comes first. The oldest "
             "published mean-reversion rule there is, which is the point: if a rule this well "
             "known still pays after costs, the Sandbox will show it; if it does not, that is "
             "the answer for every variant of it."),
    "sw_52w_breakout": dict(
        lane="swing", label="52-week breakout on volume", signal=_sw_breakout, exit=_sw_breakout_exit,
        note="Pre-registered 2026-09-19. Buy the next open when a stock closes at its highest "
             "close of the last 252 sessions on volume at least 1.5x its 50-day average. Leave at "
             "the open after the first close below the 20-day average, or after 40 sessions. "
             "Momentum is the one anomaly with decades of out-of-sample evidence; the open "
             "question is whether it survives 10bp of round-trip cost at this holding period."),
    "sw_gap_down_reversal": dict(
        lane="swing", label="Gap-down reversal above the 200-day", signal=_sw_gap_reversal,
        exit=_sw_gap_exit,
        note="Pre-registered 2026-09-19. Buy the next open when a stock in an uptrend (prior "
             "close above its 200-day average) gaps down 3% or more and still closes above its "
             "own open that day. Hold 5 sessions, then leave at the open. Tests whether the "
             "crowd overreacts to a single bad headline in a name the market otherwise likes."),
    "sw_ma_cross_rsi": dict(
        lane="swing", label="10/100 MA cross with an RSI filter", signal=_sw_ma_cross,
        exit=_sw_ma_cross_exit,
        note="The swing-trader project's own strategy (~/Swing trader, June 2026), registered "
             "here unchanged so the Sandbox judges it on the same terms as everything else: buy "
             "the next open within 3 sessions of a 10-day average crossing above the 100-day, "
             "with RSI(14) between 50 and 75; leave when the 10-day falls back under the 100-day "
             "or after 60 sessions. Its own README reports it beating buy-and-hold on "
             "risk-adjusted terms over a cycle while lagging in strong bull markets — this lane "
             "measures it against SPY over the identical days, which is the test that settles it."),
    "dt_orb30": dict(
        lane="day", label="Opening-range breakout (30 min)", signal=None, exit=None,
        note="Pre-registered 2026-09-19. On the 20 most liquid names only: take the first "
             "5-minute close beyond the first 30 minutes' range, enter at the next bar's open, "
             "stop at the other side of that range, and leave at the close — one trade a day a "
             "name, long or short. The textbook day-trading rule. On a year of BTC 5-minute bars "
             "the same rule made +1.6bp a trade before costs (t 0.20) and lost 18bp a trade "
             "after them; this lane asks whether US equities, with an actual opening auction, "
             "behave differently."),
    "dt_vwap_reclaim": dict(
        lane="day", label="VWAP reclaim", signal=None, exit=None,
        note="Pre-registered 2026-09-19. Long only, same 20 names: after a stock has traded "
             "below the session VWAP, take the first 5-minute close back above it from 14:00 UTC, "
             "enter at the next bar's open, stop at the session low to that point, and leave at "
             "the close. VWAP is the most-watched intraday level there is, which is exactly why "
             "it is worth measuring rather than assuming."),
}


# --------------------------------------------------------------------------- the day lane
# A fixed, pre-registered universe: the most liquid ETFs and mega caps, where a 5bp round trip
# is realistic. Day rules are priced on 5-minute bars, and intraday spread is the whole game —
# scanning 500 names would mean logging trades in places this cost model does not describe.
DAY_UNIVERSE = ["SPY", "QQQ", "IWM", "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA",
                "AMD", "AVGO", "NFLX", "JPM", "XOM", "COIN", "MU", "CRM", "BAC", "DIS"]
OPEN_BARS = 6          # the first 30 minutes, in 5-minute bars
SESSION_END = 19 * 60 + 55


def _mins(bar):
    t = str(bar["t"])
    return int(t[11:13]) * 60 + int(t[14:16])


def _vwap_series(bars):
    pv = vv = 0.0
    out = []
    for b in bars:
        tp = (b["h"] + b["l"] + b["c"]) / 3
        pv += tp * max(b["v"], 1); vv += max(b["v"], 1)
        out.append(pv / vv)
    return out


def day_trades(bars, rule):
    """One session's 5-minute bars -> at most one trade for `rule`. Entry is always the NEXT
    bar's open after the signal bar closes; the exit is the stop's price or the last bar's
    close. Returns (side, entry_bar_index, entry, exit_bar_index, exit) or None."""
    ses = [b for b in bars if 13 * 60 + 30 <= _mins(b) <= SESSION_END]
    if len(ses) < OPEN_BARS + 4:
        return None
    if rule == "dt_orb30":
        hi = max(b["h"] for b in ses[:OPEN_BARS]); lo = min(b["l"] for b in ses[:OPEN_BARS])
        for i in range(OPEN_BARS, len(ses) - 1):
            side = 1 if ses[i]["c"] > hi else -1 if ses[i]["c"] < lo else 0
            if not side:
                continue
            entry = ses[i + 1]["o"]; stop = lo if side > 0 else hi
            for j in range(i + 1, len(ses)):
                if (side > 0 and ses[j]["l"] <= stop) or (side < 0 and ses[j]["h"] >= stop):
                    return (side, i + 1, entry, j, stop)
            return (side, i + 1, entry, len(ses) - 1, ses[-1]["c"])
        return None
    if rule == "dt_vwap_reclaim":
        vw = _vwap_series(ses)
        below = False
        for i in range(2, len(ses) - 1):
            if ses[i]["c"] < vw[i]:
                below = True
                continue
            if below and ses[i]["c"] > vw[i] and _mins(ses[i]) >= 14 * 60:
                entry = ses[i + 1]["o"]; stop = min(b["l"] for b in ses[:i + 1])
                for j in range(i + 1, len(ses)):
                    if ses[j]["l"] <= stop:
                        return (1, i + 1, entry, j, stop)
                return (1, i + 1, entry, len(ses) - 1, ses[-1]["c"])
        return None
    return None


def scan_day(bars_by_symbol, d, research_before=None, rules=None):
    """Log the day lane's completed trades. Intraday trades open and close inside one session,
    so they are logged after it, from bars that all existed before each decision."""
    rules = rules or RULES
    seen = {t["id"] for t in d["trades"]}
    bench_day = {}
    for b in bars_by_symbol.get(BENCH, []):
        bench_day.setdefault(_day(b), []).append(b)
    added = 0
    for name, rule in rules.items():
        if rule["lane"] != "day":
            continue
        for sym, bars in bars_by_symbol.items():
            if sym == BENCH:
                continue
            byday = {}
            for b in bars:
                byday.setdefault(_day(b), []).append(b)
            for day, ses in byday.items():
                tid = trade_id(name, sym, day)
                if tid in seen or (research_before and day < research_before):
                    continue
                got = day_trades(ses, name)
                if not got:
                    continue
                side, _i, entry, _j, exit_px = got
                gross = side * (exit_px - entry) / entry
                bs = sorted(bench_day.get(day, []), key=lambda b: _mins(b))
                bench = ((bs[-1]["c"] - bs[0]["o"]) / bs[0]["o"]) if len(bs) > 1 else None
                d["trades"].append(dict(
                    id=tid, rule=name, lane="day", symbol=sym, signal_day=day, entry_day=day,
                    entry=round(float(entry), 4), status="closed", exit=round(float(exit_px), 4),
                    exit_day=day, side=side, ret_gross=round(gross, 6),
                    ret_net=round(gross - 2 * M.COST_BPS_PER_SIDE / 10000.0, 6),
                    bench_ret=(round(bench * side, 6) if bench is not None else None), bars_held=None))
                seen.add(tid); added += 1
    return added


# --------------------------------------------------------------------------- ledger
def load():
    try:
        with open(LEDGER) as f:
            d = json.load(f)
    except (OSError, ValueError):
        d = {}
    d.setdefault("trades", [])
    d.setdefault("meta", {})
    return d


def save(d):
    d["meta"]["updated"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    os.makedirs(os.path.dirname(LEDGER), exist_ok=True)
    tmp = LEDGER + ".tmp"
    with open(tmp, "w") as f:
        json.dump(d, f, indent=1, sort_keys=True)
    os.replace(tmp, LEDGER)


def trade_id(rule, symbol, day):
    return f"{rule}|{symbol}|{day}"


def _day(bar):
    return str(bar["t"])[:10]


def scan(bars_by_symbol, d, now=None, rules=None, research_before=None):
    """Log every NEW signal as an open trade entered at the next bar's open. Returns the count.

    A signal on the last bar available has no next open yet, so it is not logged — it will be
    picked up on the next run, at the open that actually existed.
    """
    now = now or datetime.datetime.now(datetime.timezone.utc)
    seen = {t["id"] for t in d["trades"]}
    added = 0
    for name, rule in (rules or RULES).items():
        if rule["lane"] != "swing":
            continue
        for sym, bars in bars_by_symbol.items():
            if sym == BENCH or len(bars) < 210:
                continue
            for i in range(200, len(bars) - 1):
                h = bars[:i + 1]
                if M.dollar_volume(h[-1]) < M.MIN_DOLLAR_VOLUME:
                    continue
                tid = trade_id(name, sym, _day(h[-1]))
                if tid in seen or not rule["signal"](h):
                    continue
                entry_bar = bars[i + 1]
                # A signal from before the lane went live is a BACKTEST, not a record. The
                # backfill was run once and kept as d["research"] (a summary per rule); it is
                # never re-logged, and never counted in a verdict.
                if research_before and _day(entry_bar) < research_before:
                    continue
                d["trades"].append(dict(
                    id=tid, rule=name, lane=rule["lane"], symbol=sym,
                    signal_day=_day(h[-1]), entry_day=_day(entry_bar),
                    entry=float(entry_bar["o"]), status="open", exit=None, exit_day=None,
                    ret_gross=None, ret_net=None, bench_ret=None, bars_held=None))
                seen.add(tid)
                added += 1
    return added


def grade(bars_by_symbol, d, rules=None):
    """Close every open trade whose exit has happened. Returns the count closed."""
    rules = rules or RULES
    bench = {_day(b): b for b in bars_by_symbol.get(BENCH, [])}
    closed = 0
    for t in d["trades"]:
        if t["status"] != "open":
            continue
        bars = bars_by_symbol.get(t["symbol"]) or []
        idx = next((i for i, b in enumerate(bars) if _day(b) == t["entry_day"]), None)
        if idx is None:
            continue
        rule = rules.get(t["rule"])
        if not rule:
            continue
        after = bars[idx + 1:]
        k = rule["exit"](after, dict(hist=bars[:idx + 1]))
        if k is None or k + 1 >= len(after):
            continue                                  # still open, or no open to leave at yet
        exit_bar = after[k + 1]
        gross = (exit_bar["o"] - t["entry"]) / t["entry"]
        net = gross - 2 * M.COST_BPS_PER_SIDE / 10000.0
        bd = [b for day, b in sorted(bench.items()) if t["entry_day"] <= day <= _day(exit_bar)]
        t.update(status="closed", exit=float(exit_bar["o"]), exit_day=_day(exit_bar),
                 ret_gross=round(gross, 6), ret_net=round(net, 6), bars_held=k + 1,
                 bench_ret=(round((bd[-1]["o"] - bd[0]["o"]) / bd[0]["o"], 6) if len(bd) > 1 else None))
        closed += 1
    return closed


# --------------------------------------------------------------------------- the verdict
VERDICTS = {                       # key -> (label, chip class, order)
    "proven":    ("Proven edge", "y", 0),
    "working":   ("Working", "y", 1),
    "promising": ("Promising", "w", 2),
    "behind":    ("Behind so far", "n", 3),
    "early":     ("Too early", "n", 4),
    "noedge":    ("No edge", "x", 5),
    "waiting":   ("Waiting for trades", "n", 6),
}


def assess(d, rule):
    """One rule's record, counted PER ENTRY DAY and measured against SPY over the same days."""
    live = [t for t in d["trades"] if t["rule"] == rule and not t.get("research")]
    ts = [t for t in live if t["status"] == "closed"]
    op = [t for t in live if t["status"] == "open"]
    days = {}
    for t in ts:
        days.setdefault(t["entry_day"], []).append(t)
    units, edges = [], []
    for day, group in days.items():
        units.append(sum(t["ret_net"] for t in group) / len(group))
        b = [t for t in group if t["bench_ret"] is not None]
        if b:
            edges.append(sum(t["ret_net"] - t["bench_ret"] for t in b) / len(b))
    n = len(units)
    mean = statistics.mean(units) if units else None
    t_stat = (mean / (statistics.pstdev(units) / math.sqrt(n))
              if n > 1 and statistics.pstdev(units) else 0.0)
    edge = statistics.mean(edges) if edges else None
    edge_t = (edge / (statistics.pstdev(edges) / math.sqrt(len(edges)))
              if len(edges) > 1 and statistics.pstdev(edges) else 0.0)
    if not n:
        v = "waiting"
    elif n < EARLY_N:
        v = "early"
    elif n >= READ_FLOOR:
        ahead = (edge or 0) > 0 and (mean or 0) > 0
        v = ("proven" if ahead and edge_t >= 2 else "working") if ahead else "noedge"
    else:
        v = "promising" if (edge or 0) > 0 and (mean or 0) > 0 else "behind"
    r = (d.get("research") or {}).get(rule) or {}
    return dict(rule=rule, days=n, trades=len(ts), open=len(op), verdict=v,
                research_days=r.get("days", 0), research_trades=r.get("trades", 0),
                research_edge=r.get("edge"), research_t=r.get("t", 0.0),
                research_window=r.get("window"),
                mean=mean, t=t_stat, edge=edge, edge_t=edge_t,
                wins=sum(1 for t in ts if t["ret_net"] > 0),
                total=(sum(t["ret_net"] for t in ts) * STAKE) if ts else 0.0,
                last=max((t["entry_day"] for t in ts + op), default=""))


def report(d, rules=None):
    return [assess(d, name) for name in (rules or RULES)]


def main():
    d = load()
    syms = M.universe()
    if not M.configured():
        print("no Alpaca credentials (~/.alpaca-credentials) — nothing fetched")
        save(d)
        return 0
    start = (datetime.date.today() - datetime.timedelta(days=500)).isoformat()
    bars = M.bars(syms + [BENCH], "1Day", start=start)
    print(f"bars for {len(bars)} symbols")
    live_from = d["meta"].setdefault("live_from", datetime.date.today().isoformat())
    added = scan(bars, d, research_before=live_from)
    closed = grade(bars, d)
    intraday = M.bars(DAY_UNIVERSE + [BENCH], "5Min",
                      start=(datetime.date.today() - datetime.timedelta(days=30)).isoformat())
    added += scan_day(intraday, d, research_before=live_from)
    save(d)
    print(f"logged {added} new trade(s), closed {closed}")
    for r in report(d):
        mean = "—" if r["mean"] is None else f"{r['mean']*100:+.2f}%"
        edge = "—" if r["edge"] is None else f"{r['edge']*100:+.2f}%"
        print(f"  {r['rule']:22} {VERDICTS[r['verdict']][0]:12} days {r['days']:3} "
              f"trades {r['trades']:4} open {r['open']:3} mean/day {mean:>7} v SPY {edge:>7}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
