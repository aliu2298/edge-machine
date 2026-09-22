#!/usr/bin/env python3
"""market_track.py — the Sandbox's TRADING lane: stock rules, logged and graded like bets.

The sports lane taught the method and it carries over unchanged:

  * every rule is PRE-REGISTERED — thresholds fixed in RULES below, with the reasoning, before
    it logs a trade. Nothing here is tuned after the fact;
  * a trade is logged only from bars that CLOSED BEFORE its entry, and it enters at the NEXT
    bar's open. A rule that needs the signal bar's close to enter is a backtest, not a record.
    The one exception is a rule whose decision does not depend on that bar at all — the
    overnight rule buys every close, unconditionally — which may enter at that close;
  * costs are charged on both sides (market_sources.COST_BPS_PER_SIDE). A rule that only works
    at zero cost is not a rule — the BTC day-trading tests of 2026-09-19 made that concrete;
  * a rule is judged PER ENTRY DAY, not per trade. Ten names bought the same morning rise and
    fall with the market, so they are one result, the same correction the commodities and
    corners lanes use;
  * and against a baseline: a stock pick against SPY over the identical holding period, since
    beating a rising market is not an edge. A TIMING rule — one that trades SPY, an index ETF or
    a coin itself — is judged against cash instead: set against its own asset over the same
    days it would show zero edge minus costs by construction, and in a cash account the money
    sits in cash whenever the rule is out.

Usage:  python3 market_track.py            scan for new trades, grade the open ones
"""
import datetime
import json
import math
import os
import statistics
from zoneinfo import ZoneInfo

import market_sources as M

NY = ZoneInfo("America/New_York")

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


# ---- index-ETF and crypto rules, registered 2026-09-22 ---------------------------------------
def _ibs(b):
    """Internal bar strength: where the close sits in the day's range, 0 = the low, 1 = the high."""
    rng = b["h"] - b["l"]
    return (b["c"] - b["l"]) / rng if rng > 0 else 0.5


def _etf_ibs_band(h):
    """Close below the 10-day high by 2.5x the 25-day average range, with IBS under 0.3."""
    if len(h) < 26:
        return False
    rng25 = sum(b["h"] - b["l"] for b in h[-25:]) / 25
    hi10 = max(b["h"] for b in h[-10:])
    return h[-1]["c"] < hi10 - 2.5 * rng25 and _ibs(h[-1]) < 0.3


def _etf_ibs_exit(after, entry):
    """Leave at the open after the first close above the prior day's high, or after 10 sessions."""
    prev = entry["hist"][-1]
    for i, b in enumerate(after):
        if b["c"] > prev["h"] or i >= 9:
            return i
        prev = b
    return None


def _etf_double7(h):
    """Above the 200-day average and closing at the lowest close of the last 7 sessions."""
    c = [b["c"] for b in h]
    ma200 = sma(c, 200)
    return bool(ma200 and c[-1] > ma200 and c[-1] <= min(c[-7:]))


def _etf_double7_exit(after, entry):
    """Leave at the open after the first close at the highest close of the last 7, or after 20."""
    for i, b in enumerate(after):
        c = [x["c"] for x in entry["hist"] + after[:i + 1]]
        if c[-1] >= max(c[-7:]) or i >= 19:
            return i
    return None


# NYSE full-day closures. Turn-of-the-month needs to know tomorrow's trading day tonight, before
# the bar exists, so it cannot read the calendar off the bars. Extend before 2028.
NYSE_HOLIDAYS = {
    "2025-01-01", "2025-01-20", "2025-02-17", "2025-04-18", "2025-05-26", "2025-06-19",
    "2025-07-04", "2025-09-01", "2025-11-27", "2025-12-25",
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25", "2026-06-19",
    "2026-07-03", "2026-09-07", "2026-11-26", "2026-12-25",
    "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31", "2027-06-18",
    "2027-07-05", "2027-09-06", "2027-11-25", "2027-12-24",
}


def next_trading_day(day):
    """The next NYSE trading day after `day` (a date)."""
    d = day + datetime.timedelta(days=1)
    while d.weekday() >= 5 or d.isoformat() in NYSE_HOLIDAYS:
        d += datetime.timedelta(days=1)
    return d


def _etf_tom(h):
    """Tonight is the eve of the month's last trading day: tomorrow opens the window."""
    today = datetime.date.fromisoformat(_day(h[-1]))
    n1 = next_trading_day(today)
    return n1.month != next_trading_day(n1).month


def _etf_tom_exit(after, entry):
    """Hold the last trading day and the first three of the new month; leave at the fourth's open."""
    return 2 if len(after) > 3 else None


def _etf_overnight(h):
    """Every close. The rule is the holding window, not a signal."""
    return True


def _etf_overnight_exit(after, entry):
    """Leave at the very next open: -1 points grade() at after[0]."""
    return -1 if after else None


def _cr_trend(h):
    """The close crosses above its 20-day average today, having been at or below it yesterday."""
    c = [b["c"] for b in h]
    if len(c) < 22:
        return False
    now, prev = sma(c, 20), sma(c[:-1], 20)
    return bool(now and prev and c[-1] > now and c[-2] <= prev)


def _cr_trend_exit(after, entry):
    """Leave at the open after the first close back under the 20-day average."""
    for i, b in enumerate(after):
        c = [x["c"] for x in entry["hist"] + after[:i + 1]]
        if c[-1] < (sma(c, 20) or 0):
            return i
    return None


LIVE_2026_09_23 = "2026-09-23"      # rules registered 2026-09-22 count from the next session


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
    "etf_ibs_band": dict(
        lane="swing", label="IBS mean reversion below the 10-day band", signal=_etf_ibs_band,
        exit=_etf_ibs_exit, universe="etf", bench="cash", live_from=LIVE_2026_09_23,
        note="Pre-registered 2026-09-22. On SPY, QQQ, IWM and DIA: buy the next open when the "
             "close is more than 2.5x the 25-day average daily range below the 10-day high AND "
             "closes in the bottom 30% of its own day's range (internal bar strength under 0.3). "
             "Leave at the open after the first close above the prior day's high, or after 10 "
             "sessions. IBS was formally documented by Pagonidis (2013): below 0.2, SPY's next "
             "day averaged +0.35%; this band version is the one published as still working in "
             "2025-26. Judged against cash — it trades the index itself — after 5bp a side."),
    "etf_double7": dict(
        lane="swing", label="Double 7s (Connors)", signal=_etf_double7, exit=_etf_double7_exit,
        universe="etf", bench="cash", live_from=LIVE_2026_09_23,
        note="Pre-registered 2026-09-22, Larry Connors' published rule unchanged: on SPY, QQQ, "
             "IWM and DIA, when the index is above its 200-day average and closes at its lowest "
             "close of the last 7 sessions, buy the next open; leave at the open after it closes "
             "at its highest close of the last 7 (or after 20 sessions). Tests still show it "
             "working on the main indices; it lags buy-and-hold only because it sits out most "
             "days, which is why it is judged against cash, not against SPY over its own days."),
    "etf_tom": dict(
        lane="swing", label="Turn of the month", signal=_etf_tom, exit=_etf_tom_exit,
        universe=["SPY"], bench="cash", live_from=LIVE_2026_09_23,
        note="Pre-registered 2026-09-22. Buy SPY at the open of the month's last trading day, "
             "hold it and the first three trading days of the new month, and leave at the fourth's "
             "open. The oldest calendar anomaly there is, and a contested one: recent work finds "
             "it has largely faded in US stocks over the past decade while persisting in index "
             "futures. That disagreement is exactly what a forward record settles."),
    "etf_overnight": dict(
        lane="swing", label="Overnight hold (buy the close, sell the open)", signal=_etf_overnight,
        exit=_etf_overnight_exit, universe=["SPY", "QQQ"], bench="cash", entry="close",
        live_from=LIVE_2026_09_23,
        note="Pre-registered 2026-09-22. Buy SPY and QQQ at every close and sell at the next "
             "open. Most of the US market's long-run return has come overnight, not during the "
             "session, and 2025 research finds the tilt persists even on nights with no news. It "
             "enters at the close because the decision does not depend on that bar: the rule is "
             "the window itself. The question is only whether the overnight premium beats 10bp "
             "of round-trip cost a night — a hard bar at this frequency."),
    "dt_orb30": dict(
        lane="day", label="Opening-range breakout (30 min)", signal=None, exit=None,
        note="Pre-registered 2026-09-19. On the 20 most liquid names only: take the first "
             "5-minute close beyond the first 30 minutes' range, enter at the next bar's open, "
             "stop at the other side of that range, and leave at the close — one trade a day a "
             "name, long or short. The textbook day-trading rule. On a year of BTC 5-minute bars "
             "the same rule made +1.6bp a trade before costs (t 0.20) and lost 18bp a trade "
             "after them; this lane asks whether US equities, with an actual opening auction, "
             "behave differently."),
    "dt_orb30_long": dict(
        lane="day", label="Opening-range breakout, long only", signal=None, exit=None,
        live_from=LIVE_2026_09_23,
        note="Pre-registered 2026-09-22: the opening-range breakout a cash account can actually "
             "place, since a cash account cannot sell short. Same 20 names, same 30-minute range, "
             "but only the first 5-minute close ABOVE the range counts; enter at the next bar's "
             "open, stop at the range low, leave at the close. On its first live day the two-way "
             "rule's trades were 13 long and 5 short, so this measures the part that is tradable."),
    "dt_intraday_mom": dict(
        lane="day", label="Market intraday momentum (last half-hour)", signal=None, exit=None,
        universe="etf", bench="cash", live_from=LIVE_2026_09_23,
        note="Pre-registered 2026-09-22 from Gao, Han, Li and Zhou (Journal of Financial "
             "Economics, 2018): the market's return from the prior close to 10:00 ET predicts its "
             "last half-hour. Long only, on SPY, QQQ, IWM and DIA: when that first return is "
             "positive, buy at 15:30 ET and sell at the close. Documented on SPY 1993-2013 and in "
             "ten other ETFs; the 2024 'Beat the Market' paper builds a full intraday momentum "
             "system on the same effect. Judged against cash, after 5bp a side."),
    "dt_vwap_reclaim": dict(
        lane="day", label="VWAP reclaim", signal=None, exit=None,
        note="Pre-registered 2026-09-19. Long only, same 20 names: after a stock has traded "
             "below the session VWAP, take the first 5-minute close back above it from 14:00 UTC, "
             "enter at the next bar's open, stop at the session low to that point, and leave at "
             "the close. VWAP is the most-watched intraday level there is, which is exactly why "
             "it is worth measuring rather than assuming."),
    "cr_trend20": dict(
        lane="crypto", label="Crypto trend: close crosses above its 20-day average",
        signal=_cr_trend, exit=_cr_trend_exit, universe="crypto", bench="cash",
        cost_bps=M.CRYPTO_COST_BPS_PER_SIDE, live_from=LIVE_2026_09_23,
        note="Pre-registered 2026-09-22. On BTC and ETH daily (UTC) bars: buy the next open when "
             "the close crosses above its 20-day average, leave at the open after the first close "
             "back under it. Trend-following is the most-documented crypto effect — it catches "
             "long directional runs and gives back in chop. Judged against cash after Alpaca's "
             "0.25% a side; the stricter comparison, simply holding the coin, is noted beside it "
             "because any long-biased rule looks good in a rising market."),
    "cr_btc_2200": dict(
        lane="crypto", label="BTC 22:00-00:00 UTC seasonality", signal=None, exit=None,
        universe=["BTC/USD"], bench="cash", cost_bps=M.CRYPTO_COST_BPS_PER_SIDE,
        live_from=LIVE_2026_09_23,
        note="Pre-registered 2026-09-22 from Quantpedia's published rule: buy BTC at 22:00 UTC "
             "and sell at 00:00, every day — the two hours its research found to carry "
             "Bitcoin's most significant returns (33% a year, Sharpe 1.58, 2015-21). Tested "
             "forward, after its publication, and at Alpaca's 0.25% a side: 50bp a round trip "
             "against an edge that was a few basis points a night. If it survives that, it is "
             "real; the expectation is that it does not."),
}


# --------------------------------------------------------------------------- the day lane
# A fixed, pre-registered universe: the most liquid ETFs and mega caps, where a 5bp round trip
# is realistic. Day rules are priced on 5-minute bars, and intraday spread is the whole game —
# scanning 500 names would mean logging trades in places this cost model does not describe.
DAY_UNIVERSE = ["SPY", "QQQ", "IWM", "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA",
                "AMD", "AVGO", "NFLX", "JPM", "XOM", "COIN", "MU", "CRM", "BAC", "DIS"]
OPEN_BARS = 6          # the first 30 minutes, in 5-minute bars
SESSION_OPEN = 9 * 60 + 30      # New York time. Until 2026-09-22 these were UTC minutes (13:30,
SESSION_END = 15 * 60 + 55      # 19:55), right only in summer: from November's clock change the
                                # session starts at 14:30 UTC and every day rule would have read
                                # the wrong bars. Bars are converted to New York time instead.


def _mins(bar):
    """Minutes past midnight, New York time, of a bar's start."""
    t = datetime.datetime.fromisoformat(str(bar["t"]).replace("Z", "+00:00")).astimezone(NY)
    return t.hour * 60 + t.minute


def _vwap_series(bars):
    pv = vv = 0.0
    out = []
    for b in bars:
        tp = (b["h"] + b["l"] + b["c"]) / 3
        pv += tp * max(b["v"], 1); vv += max(b["v"], 1)
        out.append(pv / vv)
    return out


def day_trades(bars, rule, prev_close=None):
    """One session's 5-minute bars -> at most one trade for `rule`. Entry is always the NEXT
    bar's open after the signal bar closes; the exit is the stop's price or the last bar's
    close. Returns (side, entry_bar_index, entry, exit_bar_index, exit) or None.
    `prev_close` is the prior session's last close, which the intraday-momentum rule needs."""
    ses = [b for b in bars if SESSION_OPEN <= _mins(b) <= SESSION_END]
    if len(ses) < OPEN_BARS + 4:
        return None
    if rule == "dt_orb30_long":
        hi = max(b["h"] for b in ses[:OPEN_BARS]); lo = min(b["l"] for b in ses[:OPEN_BARS])
        for i in range(OPEN_BARS, len(ses) - 1):
            if ses[i]["c"] <= hi:
                continue                              # a break down is not a trade: no shorting
            entry = ses[i + 1]["o"]
            for j in range(i + 1, len(ses)):
                if ses[j]["l"] <= lo:
                    return (1, i + 1, entry, j, lo)
            return (1, i + 1, entry, len(ses) - 1, ses[-1]["c"])
        return None
    if rule == "dt_intraday_mom":
        if not prev_close:
            return None
        first = next((b for b in ses if _mins(b) == 9 * 60 + 55), None)    # closes at 10:00 ET
        late = next((i for i, b in enumerate(ses) if _mins(b) == 15 * 60 + 30), None)
        if first is None or late is None or first["c"] <= prev_close:
            return None
        return (1, late, ses[late]["o"], len(ses) - 1, ses[-1]["c"])
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
            if below and ses[i]["c"] > vw[i] and _mins(ses[i]) >= 10 * 60:     # 10:00 ET
                entry = ses[i + 1]["o"]; stop = min(b["l"] for b in ses[:i + 1])
                for j in range(i + 1, len(ses)):
                    if ses[j]["l"] <= stop:
                        return (1, i + 1, entry, j, stop)
                return (1, i + 1, entry, len(ses) - 1, ses[-1]["c"])
        return None
    return None


def universe_for(rule, symbols):
    """The symbols a rule trades, from what was fetched. Stock picks never trade the ETFs or
    coins fetched beside them, and SPY — their benchmark — only for the ETF timing rules."""
    u = rule.get("universe", "stocks")
    if u == "stocks":
        return [s for s in symbols if s != BENCH and s not in M.ETFS and "/" not in s]
    if u == "etf":
        return [s for s in M.ETFS if s in symbols]
    if u == "crypto":
        return [s for s in M.CRYPTO if s in symbols]
    return [s for s in u if s in symbols]


def cost_of(rule):
    """Round-trip cost as a fraction: the rule's own cost a side, charged on both sides."""
    return 2 * rule.get("cost_bps", M.COST_BPS_PER_SIDE) / 10000.0


def starts(rule, research_before):
    """First entry day a trade counts from. None (the research backfill) means all of history."""
    if not research_before:
        return None
    return max(research_before, rule.get("live_from") or research_before)


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
        start = starts(rule, research_before)
        for sym in universe_for(rule, list(bars_by_symbol)):
            byday = {}
            for b in bars_by_symbol[sym]:
                byday.setdefault(_day(b), []).append(b)
            last_close = {}
            for day in sorted(byday):
                ses = [b for b in byday[day] if SESSION_OPEN <= _mins(b) <= SESSION_END]
                if ses:
                    last_close[day] = ses[-1]["c"]
            days = sorted(byday)
            for k, day in enumerate(days):
                ses = byday[day]
                tid = trade_id(name, sym, day)
                if tid in seen or (start and day < start):
                    continue
                prev = last_close.get(days[k - 1]) if k else None
                got = day_trades(ses, name, prev_close=prev)
                if not got:
                    continue
                side, _i, entry, _j, exit_px = got
                gross = side * (exit_px - entry) / entry
                if rule.get("bench") == "cash":
                    bench = 0.0
                else:
                    bs = sorted(bench_day.get(day, []), key=lambda b: _mins(b))
                    bs = [b for b in bs if SESSION_OPEN <= _mins(b) <= SESSION_END]
                    bench = (side * (bs[-1]["c"] - bs[0]["o"]) / bs[0]["o"]) if len(bs) > 1 else None
                d["trades"].append(dict(
                    id=tid, rule=name, lane="day", symbol=sym, signal_day=day, entry_day=day,
                    entry=round(float(entry), 4), status="closed", exit=round(float(exit_px), 4),
                    exit_day=day, side=side, ret_gross=round(gross, 6),
                    ret_net=round(gross - cost_of(rule), 6),
                    bench_ret=(round(bench, 6) if bench is not None else None), bars_held=None))
                seen.add(tid); added += 1
    return added


def scan_hours(bars_by_symbol, d, research_before=None, rules=None):
    """The hourly crypto seasonality rule: each UTC day, in at the 22:00 bar's open, out at the
    next day's 00:00 bar's open. Logged once that exit bar exists, from bars that all did."""
    rules = rules or RULES
    seen = {t["id"] for t in d["trades"]}
    added = 0
    for name, rule in rules.items():
        if name != "cr_btc_2200":
            continue
        start = starts(rule, research_before)
        for sym in universe_for(rule, list(bars_by_symbol)):
            at = {str(b["t"])[:13]: b for b in bars_by_symbol[sym]}      # "2026-09-22T22"
            for key, b in sorted(at.items()):
                if not key.endswith("T22"):
                    continue
                day = key[:10]
                nxt = (datetime.date.fromisoformat(day) + datetime.timedelta(days=1)).isoformat()
                out = at.get(f"{nxt}T00")
                tid = trade_id(name, sym, day)
                if out is None or tid in seen or (start and day < start):
                    continue
                gross = (out["o"] - b["o"]) / b["o"]
                d["trades"].append(dict(
                    id=tid, rule=name, lane=rule["lane"], symbol=sym, signal_day=day, entry_day=day,
                    entry=round(float(b["o"]), 4), status="closed", exit=round(float(out["o"]), 4),
                    exit_day=nxt, side=1, ret_gross=round(gross, 6), ret_net=round(gross - cost_of(rule), 6),
                    bench_ret=0.0, bars_held=2))
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
        if rule["lane"] not in ("swing", "crypto") or rule.get("signal") is None:
            continue
        start = starts(rule, research_before)
        # Stock picks must clear the liquidity floor. The ETFs always do; the crypto feed's own
        # volume is thin and says nothing about the coins' real liquidity, so it is not gated.
        gated = rule.get("universe", "stocks") == "stocks"
        for sym in universe_for(rule, list(bars_by_symbol)):
            bars = bars_by_symbol[sym]
            if len(bars) < 210:
                continue
            for i in range(200, len(bars) - 1):
                h = bars[:i + 1]
                if gated and M.dollar_volume(h[-1]) < M.MIN_DOLLAR_VOLUME:
                    continue
                tid = trade_id(name, sym, _day(h[-1]))
                if tid in seen or not rule["signal"](h):
                    continue
                # Entry at the signal bar's close only for a rule whose decision does not read
                # that bar (see the principles above); every other rule enters at the next open.
                at_close = rule.get("entry") == "close"
                entry_bar = h[-1] if at_close else bars[i + 1]
                # A signal from before the rule went live is a BACKTEST, not a record. The
                # backfill was run once and kept as d["research"] (a summary per rule); it is
                # never re-logged, and never counted in a verdict.
                if start and _day(entry_bar) < start:
                    continue
                d["trades"].append(dict(
                    id=tid, rule=name, lane=rule["lane"], symbol=sym,
                    signal_day=_day(h[-1]), entry_day=_day(entry_bar),
                    entry=float(entry_bar["c"] if at_close else entry_bar["o"]), status="open",
                    exit=None, exit_day=None, ret_gross=None, ret_net=None, bench_ret=None,
                    bars_held=None))
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
        net = gross - cost_of(rule)
        if rule.get("bench") == "cash":
            bench_ret = 0.0
        else:
            bd = [b for day, b in sorted(bench.items()) if t["entry_day"] <= day <= _day(exit_bar)]
            bench_ret = round((bd[-1]["o"] - bd[0]["o"]) / bd[0]["o"], 6) if len(bd) > 1 else None
        t.update(status="closed", exit=float(exit_bar["o"]), exit_day=_day(exit_bar),
                 ret_gross=round(gross, 6), ret_net=round(net, 6), bars_held=k + 1,
                 bench_ret=bench_ret)
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
    bars = M.bars(sorted(set(syms + [BENCH] + M.ETFS)), "1Day", start=start)
    bars.update(M.crypto_bars(M.CRYPTO, "1Day", start=start))
    print(f"bars for {len(bars)} symbols")
    live_from = d["meta"].setdefault("live_from", datetime.date.today().isoformat())
    added = scan(bars, d, research_before=live_from)
    closed = grade(bars, d)
    recent = (datetime.date.today() - datetime.timedelta(days=30)).isoformat()
    intraday = M.bars(sorted(set(DAY_UNIVERSE + [BENCH] + M.ETFS)), "5Min", start=recent)
    added += scan_day(intraday, d, research_before=live_from)
    added += scan_hours(M.crypto_bars(["BTC/USD"], "1Hour", start=recent), d, research_before=live_from)
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
