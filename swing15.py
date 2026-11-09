#!/usr/bin/env python3
"""15-Minute Swing (sw15-v1): a forward PAPER tracker on every Kalshi 15-minute window in Crypto, Commodities and
Financials. Public market data only; it places nothing and holds no key.

PRE-REGISTERED 2026-11-08 (Olu, via the coordinator), before any window was graded. Frozen: the terms below do not
change; a change is a new version with a fresh record.

Scope: every Kalshi series with frequency "fifteen_min" in the Crypto, Commodities or Financials category
(GET /series), except KXKPOWMID15M (Elections) and KXGBPUSD15MTEST (a test series). Each series has one binary
market per 15-minute window ("... up in the next 15 mins?"). Windows that OPEN at or after FROM are graded, once each,
after Kalshi settles them, from Kalshi's own 1-minute candlesticks and trade prints. Nothing watches live.

  S1 Swing (swing15_s1). Entry: a resting buy at the band (15c, 25c, 35c: three bands) on whichever side prints there
     first: the entry is the first trade print in the window's first 5 minutes at or under the band on EITHER side
     (a YES print at or under the band, or a NO print at or under it, i.e. YES at or over 1 - band), filled at the
     band. Exit: a resting sell at 1.5x, 2x or 3x the entry (capped at 99c), filled only when 50+ contracts print at
     or above the target on that side at least 60 seconds after the entry. A sell never filled is recorded BOTH
     ways: held to settlement, and sold at the bid with 1 minute left (the bid at minute 14).
  S2 Favourite at start (swing15_s2): at minute 2, buy the side above 50c (by the mid) at its ask; held to settlement.
  S3 Favourite at 5 minutes left (swing15_s3): the same at minute 10.

Honest fills: an S2/S3 entry counts only when a print traded at or through its ask in the next minute; an S1 entry
only on a print at or through the band; a sell only on 50+ contracts printed at or above the target 60s+ after entry.
Fees (every series is fee_type "quadratic", multiplier 1): taker 0.07 * m * p * (1-p) a contract on an entry and on
a sell at the bid; maker 0.0175 * m * p * (1-p) on a resting sell that fills (the chaos engine's convention).

Baselines: S1 against the fair touch rate (entry / target: a fair price reaches T from p with probability p/T); S2
and S3 against the price paid (the win rate a fair price implies). z is clustered by day (America/New_York date).
Review at 10 and decide at 30 settled windows per strategy x series.
"""
import argparse
import datetime as dt
import json
import math
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "data", "swing15_ledger.json")       # the index: version, series, runs
SHARDS = os.path.join(ROOT, "data", "swing15")                  # the graded windows, one file per ET day (YYYY-MM-DD.json)
API = "https://api.elections.kalshi.com/trade-api/v2"
VERSION = "sw15-v1"
REGISTERED = "2026-11-08"
FROM = "2026-11-09T06:00:00+00:00"           # windows opening at or after this are graded (forward from the merge)
GROUPS = ("Crypto", "Commodities", "Financials")
EXCLUDE = ("KXKPOWMID15M", "KXGBPUSD15MTEST")
BANDS = (0.15, 0.25, 0.35)
MULTS = (1.5, 2.0, 3.0)
ENTRY_MIN = 5
SELL_CONTRACTS = 50
SELL_DELAY_S = 60
S2_MIN, S3_MIN = 2, 10
BID_EXIT_MIN = 14
TAKER, MAKER = 0.07, 0.0175
REVIEW_AT, DECIDE_AT = 10, 30
LOOKBACK_H = 36
RUN_BUDGET_S = 15 * 60
PACE_S = 0.12
ET = ZoneInfo("America/New_York")
STRATS = {"swing15_s1": "S1 Swing", "swing15_s2": "S2 Favourite at start", "swing15_s3": "S3 Favourite at 5 minutes left"}

_last = [0.0]


def _get(path, tries=6):
    for i in range(tries):
        wait = _last[0] + PACE_S - time.time()
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()
        try:
            req = urllib.request.Request(API + path, headers={"User-Agent": "edge-machine/1.0", "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as f:
                return json.load(f)
        except urllib.error.HTTPError as e:
            if e.code == 429 or e.code >= 500:
                time.sleep(1.5 * (i + 1))
                continue
            raise
        except (urllib.error.URLError, TimeoutError):
            time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"kalshi {path.split('?')[0]}: no answer after {tries} tries")


def _num(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v


def _ts(iso):
    return dt.datetime.fromisoformat(str(iso).replace("Z", "+00:00")).timestamp()


def fee(p, rate, mult=1.0):
    return rate * mult * p * (1 - p)


# ------------------------------------------------------------------ discovery

def discover(get=_get):
    """[(ticker, group, fee_multiplier)] for every fifteen_min series in scope."""
    s = get("/series?limit=2000").get("series") or []
    out = []
    for x in s:
        if x.get("frequency") != "fifteen_min" or x.get("category") not in GROUPS or x.get("ticker") in EXCLUDE:
            continue
        out.append((x["ticker"], x["category"], _num(x.get("fee_multiplier")) or 1.0))
    return sorted(out)


def settled_markets(series, since_ts, until_ts, get=_get):
    out, cursor = [], None
    for _ in range(20):
        q = {"series_ticker": series, "status": "settled", "min_close_ts": int(since_ts), "max_close_ts": int(until_ts),
             "limit": 1000}
        if cursor:
            q["cursor"] = cursor
        d = get("/markets?" + urllib.parse.urlencode(q))
        out += d.get("markets") or []
        cursor = d.get("cursor")
        if not cursor or not d.get("markets"):
            break
    return out


# ------------------------------------------------------------------ one window's data

class Window:
    """A window's candles (by minute 1..15) and trade prints fetched minute by minute, on demand."""

    def __init__(self, series, m, get=_get):
        self.series, self.m, self.get = series, m, get
        self.ticker = m["ticker"]
        self.open = int(_ts(m["open_time"]))
        self.close = int(_ts(m["close_time"]))
        self._prints = {}
        q = {"start_ts": self.open, "end_ts": self.close, "period_interval": 1}
        cs = get(f"/series/{series}/markets/{urllib.parse.quote(self.ticker)}/candlesticks?" + urllib.parse.urlencode(q))
        self.candles = {}
        for c in cs.get("candlesticks") or []:
            k = round((int(c["end_period_ts"]) - self.open) / 60)
            if 1 <= k <= 15:
                self.candles[k] = c

    def c(self, k, field, what):
        return _num(((self.candles.get(k) or {}).get(field) or {}).get(what))

    def prints(self, k):
        """Prints in minute k (open+60(k-1) .. open+60k), oldest first: [(ts, yes_price, count)]."""
        if k not in self._prints:
            out, cursor = [], None
            a, b = self.open + 60 * (k - 1), self.open + 60 * k
            for _ in range(60):
                q = {"ticker": self.ticker, "min_ts": a, "max_ts": b, "limit": 1000}
                if cursor:
                    q["cursor"] = cursor
                d = self.get("/markets/trades?" + urllib.parse.urlencode(q))
                for t in d.get("trades") or []:
                    ts = _ts(t["created_time"])
                    if a <= ts < b:
                        out.append((ts, _num(t.get("yes_price_dollars")), _num(t.get("count_fp")) or 0.0))
                cursor = d.get("cursor")
                if not cursor or not d.get("trades"):
                    break
            self._prints[k] = sorted(out)
        return self._prints[k]


def _side_price(side, yes):
    return yes if side == "yes" else 1 - yes


def s1(w, band, payout_yes, mult_fee):
    """One band: the entry (or None) and, per multiplier, the exit both ways."""
    entry = None
    for k in range(1, ENTRY_MIN + 1):
        lo, hi = w.c(k, "price", "low_dollars"), w.c(k, "price", "high_dollars")
        if lo is None or hi is None or not (lo <= band + 1e-9 or hi >= 1 - band - 1e-9):
            continue
        for ts, yes, _n in w.prints(k):
            if yes is None:
                continue
            if yes <= band + 1e-9:
                entry = ("yes", ts)
            elif yes >= 1 - band - 1e-9:
                entry = ("no", ts)
            if entry:
                break
        if entry:
            break
    if not entry:
        return None
    side, ets = entry
    cost = band + fee(band, TAKER, mult_fee)
    won = payout_yes if side == "yes" else (None if payout_yes is None else 1 - payout_yes)
    bid14 = w.c(BID_EXIT_MIN, "yes_bid", "close_dollars") if side == "yes" else (
        None if w.c(BID_EXIT_MIN, "yes_ask", "close_dollars") is None else round(1 - w.c(BID_EXIT_MIN, "yes_ask", "close_dollars"), 4))
    out = dict(side=side, won=won, bid14=bid14, exits={})
    first_k = max(1, math.floor((ets + SELL_DELAY_S - w.open) / 60) + 1)
    for mult in MULTS:
        target = min(0.99, round(band * mult, 4))
        filled = None
        cum = 0.0
        for k in range(first_k, 16):
            lo, hi = w.c(k, "price", "low_dollars"), w.c(k, "price", "high_dollars")
            reach = hi if side == "yes" else (None if lo is None else 1 - lo)
            if reach is None or reach < target - 1e-9:
                continue
            for ts, yes, n in w.prints(k):
                if yes is None or ts < ets + SELL_DELAY_S:
                    continue
                if _side_price(side, yes) >= target - 1e-9:
                    cum += n
                    if cum >= SELL_CONTRACTS:
                        filled = ts
                        break
            if filled:
                break
        if filled:
            proceeds = target - fee(target, MAKER, mult_fee)
            r_hold = r_bid = proceeds / cost - 1
        else:
            r_hold = None if won is None else won / cost - 1
            # No bid with a minute left: nothing to sell into, so the position is held to settlement.
            r_bid = (r_hold if bid14 is None or bid14 <= 0 else (bid14 - fee(bid14, TAKER, mult_fee)) / cost - 1)
        out["exits"][str(mult)] = dict(filled=bool(filled),
                                       roi_hold=None if r_hold is None else round(r_hold, 4),
                                       roi_bid=None if r_bid is None else round(r_bid, 4))
    return out


def fav(w, k0, payout_yes, mult_fee):
    """S2/S3: the side above 50c at minute k0, bought at its ask, filled only on a print at or through it next minute."""
    bid, ask = w.c(k0, "yes_bid", "close_dollars"), w.c(k0, "yes_ask", "close_dollars")
    if bid is None or ask is None or not 0 < bid <= ask < 1:
        return dict(status="no_quote")
    mid = (bid + ask) / 2
    if abs(mid - 0.5) < 1e-9:
        return dict(status="no_favourite")
    side = "yes" if mid > 0.5 else "no"
    price = ask if side == "yes" else round(1 - bid, 4)
    lo, hi = w.c(k0 + 1, "price", "low_dollars"), w.c(k0 + 1, "price", "high_dollars")
    through = (lo is not None and lo <= ask + 1e-9) if side == "yes" else (hi is not None and hi >= bid - 1e-9)
    if not through:
        return dict(status="no_fill", side=side, price=price)
    won = payout_yes if side == "yes" else (None if payout_yes is None else 1 - payout_yes)
    roi = None if won is None else won / (price + fee(price, TAKER, mult_fee)) - 1
    return dict(status="filled", side=side, price=price, won=won, roi=None if roi is None else round(roi, 4))


def grade(series, group, mult_fee, m, get=_get):
    res = str(m.get("result") or "").lower()
    payout_yes = 1.0 if res == "yes" else 0.0 if res == "no" else None
    w = Window(series, m, get=get)
    t_open = dt.datetime.fromtimestamp(w.open, ET)
    m_of_day = t_open.hour * 60 + t_open.minute
    return dict(ticker=w.ticker, series=series, group=group, open=m["open_time"], result=res or None,
                day=t_open.date().isoformat(), us_hours=t_open.weekday() < 5 and 570 <= m_of_day < 960,
                s1={str(b): s1(w, b, payout_yes, mult_fee) for b in BANDS},
                s2=fav(w, S2_MIN, payout_yes, mult_fee), s3=fav(w, S3_MIN, payout_yes, mult_fee))


# ------------------------------------------------------------------ the ledger

def empty():
    return {"version": VERSION, "registered": REGISTERED, "from": FROM, "windows": {}, "series": [], "runs": []}


def _read(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def load(path=PATH, shards=SHARDS, days=None):
    """The index plus every graded window (or only the shards for `days`), keyed by market ticker."""
    state = dict(empty(), **_read(path, {}))
    state["windows"] = {}
    if os.path.isdir(shards):
        for name in sorted(os.listdir(shards)):
            if name.endswith(".json") and (days is None or name[:-5] in days):
                state["windows"].update(_read(os.path.join(shards, name), {}))
    return state


def _write(path, blob):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(blob, f, separators=(",", ":"), sort_keys=True)
    os.replace(tmp, path)


def save(state, path=PATH, shards=SHARDS, touched=None):
    """The index, and each day shard holding a window graded this run (all of them when `touched` is None)."""
    by_day = {}
    for t, w in (state.get("windows") or {}).items():
        by_day.setdefault(w["day"], {})[t] = w
    for day, ws in by_day.items():
        if touched is None or day in touched:
            old = _read(os.path.join(shards, day + ".json"), {})
            _write(os.path.join(shards, day + ".json"), dict(old, **ws))
    _write(path, {k: v for k, v in state.items() if k != "windows"})
    return sorted(by_day if touched is None else touched)


def run(state, now=None, get=_get, budget_s=RUN_BUDGET_S, log=print):
    t0 = time.time()
    now = now or dt.datetime.now(dt.timezone.utc)
    since = max(_ts(FROM), now.timestamp() - LOOKBACK_H * 3600)
    series = discover(get)
    state["series"] = [dict(ticker=t, group=g, fee_multiplier=f) for t, g, f in series]
    added, errors, skipped_old = 0, [], 0
    todo = []
    for ticker, group, mult_fee in series:
        try:
            for m in settled_markets(ticker, since, now.timestamp(), get=get):
                if m["ticker"] in state["windows"]:
                    continue
                if _ts(m["open_time"]) < _ts(FROM):
                    skipped_old += 1
                    continue
                todo.append((ticker, group, mult_fee, m))
        except Exception as e:                                   # noqa: BLE001
            errors.append(f"{ticker}: {type(e).__name__}")
    todo.sort(key=lambda x: x[3]["open_time"])
    state.setdefault("touched", [])
    for ticker, group, mult_fee, m in todo:
        if time.time() - t0 > budget_s:
            break
        try:
            g = grade(ticker, group, mult_fee, m, get=get)
            state["windows"][m["ticker"]] = g
            if g["day"] not in state["touched"]:
                state["touched"].append(g["day"])
            added += 1
        except Exception as e:                                   # noqa: BLE001
            errors.append(f"{m['ticker']}: {type(e).__name__}")
    state["runs"] = (state.get("runs") or [])[-200:] + [dict(
        at=now.isoformat(timespec="seconds"), series=len(series), graded=added, waiting=len(todo) - added,
        errors=errors[:20])]
    state["last_run"] = now.isoformat(timespec="seconds")
    log(f"series {len(series)} graded {added} waiting {len(todo) - added} errors {len(errors)}")
    return state


# ------------------------------------------------------------------ the record

def cluster_z(rows):
    """rows: [(day, outcome, expected)]. z = sum of per-day (outcome - expected) over the root of their squares."""
    by = {}
    for d, o, e in rows:
        by[d] = by.get(d, 0.0) + (o - e)
    den = math.sqrt(sum(v * v for v in by.values()))
    return None if den == 0 else sum(by.values()) / den


def cells(state, flt=lambda w: True):
    """Every strategy cell's record. S1 cells are (band, multiplier, exit) with exit 'hold' or 'bid'."""
    out = {}
    ws = sorted((w for w in (state.get("windows") or {}).values() if flt(w)), key=lambda w: w["open"])
    half = ws[len(ws) // 2]["open"] if ws else None

    def add(key, w, roi, hit, exp):
        c = out.setdefault(key, dict(n=0, hits=0, roi=[], exp=[], rows=[], halves=[[], []]))
        c["n"] += 1
        c["hits"] += hit
        c["roi"].append(roi)
        c["exp"].append(exp)
        c["rows"].append((w["day"], hit, exp))
        c["halves"][0 if w["open"] < half else 1].append(roi)

    for w in ws:
        for b, e in (w.get("s1") or {}).items():
            if not e:
                continue
            for mult, x in e["exits"].items():
                exp = float(b) / min(0.99, round(float(b) * float(mult), 4))
                for how in ("hold", "bid"):
                    r = x[f"roi_{how}"]
                    if r is None:
                        continue
                    add(("swing15_s1", b, mult, how), w, r, 1 if x["filled"] else 0, exp)
        for k in ("s2", "s3"):
            x = w.get(k) or {}
            if x.get("status") == "filled" and x.get("roi") is not None:
                add((f"swing15_{k}",), w, x["roi"], int(x["won"] == 1), x["price"])
    for c in out.values():
        c["hit_rate"] = c["hits"] / c["n"]
        c["fair"] = sum(c["exp"]) / c["n"]
        c["mean_roi"] = sum(c["roi"]) / c["n"]
        c["z"] = cluster_z(c["rows"])
        c["half_roi"] = [sum(h) / len(h) if h else None for h in c["halves"]]
        c["days"] = len({r[0] for r in c["rows"]})
        del c["rows"], c["halves"], c["exp"], c["roi"]
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="15-Minute Swing paper tracker (public data only)")
    ap.add_argument("--path", default=PATH)
    ap.add_argument("--budget", type=int, default=RUN_BUDGET_S)
    a = ap.parse_args(argv)
    now = dt.datetime.now(dt.timezone.utc)
    recent = {(now - dt.timedelta(days=i)).astimezone(ET).date().isoformat() for i in range(3)}
    state = load(a.path, days=recent)          # the windows a run can meet again: the lookback is 36 hours
    state["touched"] = []
    run(state, now=now, budget_s=a.budget)
    touched = state.pop("touched")
    for day in save(state, a.path, touched=touched):
        print("wrote", os.path.join(SHARDS, day + ".json"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
