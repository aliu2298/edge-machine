#!/usr/bin/env python3
"""Rebound after a slide (2026-11-11): two OBSERVATION-ONLY paper lanes on Kalshi Invest stock perps. Up only, 1x.

PAPER ONLY. Public Kalshi data (the collector's 1-minute ticks and public prints) and Alpaca bars for the support
levels; no key is printed, nothing is placed, amended or cancelled.

Pre-registered and researched first (~/edge-research/invest_rebound_2026-11-11, PREREGISTRATION.md sha256 17ecd1cd…):
56 variants on 2023-01 .. 2026-11 Alpaca 1-minute bars, against the SAME slides with no support cue (B1) and random
entry (B2). NOTHING cleared: no variant beat B1 in both research halves and the holdout. Olu asked for the top 1-2 to
run anyway so he can watch them, labelled observation-only. These are the top variant of each slide length by research
margin over B1:

  rb_5d   the price 10%+ below its 5-day high; touches a STRONG support level (2+ methods agree, or tested before);
          selling slows (15-minute RSI(14) below 30, then turning up); Up at the ask on the next minute.
  rb_24h  the price 5%+ below its 24-hour high; touches ANY support level; the same confirmation.
  Both: stop 1% under the support (taker at the bid), target halfway back to the slide's high (a resting limit, filled
  only by a print through it), time stop 1 day (24h) / 5 days (5-day) of regular-hours minutes. One trade a stock per
  session (24h) / per 5 sessions (5-day). Fees: 0.12% taker a side, 0.02% maker on the target.

Differences from the research, stated: the live lane reads Kalshi's reference price in every open minute, overnight
included (the research saw regular hours only); the reference has no volume, so the confirmation is the RSI branch only.
Support levels (Alpaca SIP daily and hourly bars, split-adjusted) are scaled to the reference price by the measured
stock/reference ratio (50 on 2026-11-11).

  python3 rebound.py track --work ~/invest --state ~/invest/rebound_state.json      every 15 minutes, after invest.py
"""
import argparse
import datetime as dt
import json
import math
import os
import re
import sys
import time

import invest as I

ROOT = I.ROOT
STATE = os.path.join(ROOT, "data", "rebound_state.json")
VERSION = "rebound-v1"
REGISTERED = "2026-11-11"
FROM = "2026-11-12T00:00:00+00:00"         # the fresh record: signals from here (the backfill before it is in-sample)
PREREG_SHA = "17ecd1cd57183bacd45e8e1e6477c542b4ecaaa88a3e8b8a62fa395bbc45a581"
LANES = {
    "rb_5d": dict(slide="S5D", drop=0.10, strong=True, hold=1950, block=5,
                  label="Rebound after a 5-day slide · strong support",
                  research="5-day slide · strong support · selling slows · halfway target: research +0.12% a trade after "
                           "costs v +0.12% for the same slides with no support cue (t −0.12); holdout −0.42% v −0.62%"),
    "rb_24h": dict(slide="S24", drop=0.05, strong=False, hold=390, block=1,
                   label="Rebound after a 24-hour slide · any support",
                   research="24-hour slide · any support · selling slows · halfway target: research −0.31% a trade v "
                            "−0.23% with no support cue (t −1.69); holdout −0.35% v −0.37%"),
}
TOL, FAIL, WINDOW = 0.0075, 0.995, 120
REVIEW_AT, DECIDE_AT = 10, 30
METHODS = ("PD", "PH", "PDL", "PWL", "MA50", "MA200", "GAP")


# ---------------------------------------------------------------- support levels (stock prices, from Alpaca)

def _rnd_step(p):
    return 1 if p < 50 else 5 if p < 200 else 10 if p < 1000 else 50


def daily_levels(daily, day):
    """[(level, method)] and the tested lows, from the daily bars strictly before ET date `day` (ISO)."""
    d = [b for b in daily if b["t"][:10] < day]
    if len(d) < 3:
        return [], []
    L, H, O, C = [b["l"] for b in d], [b["h"] for b in d], [b["o"] for b in d], [b["c"] for b in d]
    s, out = len(d), []
    for k in range(max(2, s - 120), s - 2):
        if L[k] < L[k - 1] and L[k] < L[k - 2] and L[k] < L[k + 1] and L[k] < L[k + 2]:
            out.append((L[k], "PD"))
    out.append((L[-1], "PDL"))
    wk = lambda b: dt.date.fromisoformat(b["t"][:10]).isocalendar()[:2]
    this = dt.date.fromisoformat(day).isocalendar()[:2]
    prev = [b for b in d[-10:] if wk(b) != this]
    if prev:
        w = wk(prev[-1])
        out.append((min(b["l"] for b in prev if wk(b) == w), "PWL"))
    if s >= 50:
        out.append((sum(C[-50:]) / 50, "MA50"))
    if s >= 200:
        out.append((sum(C[-200:]) / 200, "MA200"))
    for k in range(max(1, s - 60), s):
        if O[k] >= 1.01 * C[k - 1]:
            out.append((C[k - 1], "GAP"))
    return out, L[-60:]


def hourly_pivots(hourly, before_ts):
    """Hourly 5-bar pivot lows confirmed (the bar 2 later has ended) before `before_ts`, from the last 20 sessions."""
    hb = [b for b in hourly if _ts(b["t"]) + 3600 <= before_ts]
    out = []
    for j in range(2, len(hb) - 2):
        if all(hb[j]["l"] < hb[j + k]["l"] for k in (-2, -1, 1, 2)) and _ts(hb[j + 2]["t"]) + 3600 <= before_ts:
            out.append(hb[j]["l"])
    return out[-60:]


def _ts(iso):
    return int(dt.datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp())


def strength(L, levels, ph, tested):
    m = {meth for x, meth in levels if abs(x - L) <= TOL * L}
    if any(abs(x - L) <= TOL * L for x in ph):
        m.add("PH")
    return len(m) + int(any(abs(x - L) <= TOL * L for x in tested))


def touched(px, H, levels, ph):
    """The highest support level within TOL of `px` (stock price), below the slide high and above 0.8 of it."""
    cand = [x for x, _m in levels] + list(ph)
    st = _rnd_step(px)
    cand += [math.floor(px / st) * st, math.ceil(px / st) * st]
    hit = [x for x in cand if 0.8 * H < x < H and abs(px - x) <= TOL * x]
    return max(hit) if hit else None


# ---------------------------------------------------------------- the signal, from the reference-price ticks

def rsi(xs, n=14):
    out = [None] * len(xs)
    if len(xs) <= n:
        return out
    d = [b - a for a, b in zip(xs, xs[1:])]
    up, dn = [max(x, 0) for x in d], [max(-x, 0) for x in d]
    au, ad = sum(up[:n]) / n, sum(dn[:n]) / n
    out[n] = 100.0 if ad == 0 else 100 - 100 / (1 + au / ad)
    for i in range(n + 1, len(xs)):
        au = (au * (n - 1) + up[i - 1]) / n
        ad = (ad * (n - 1) + dn[i - 1]) / n
        out[i] = 100.0 if ad == 0 else 100 - 100 / (1 + au / ad)
    return out


def rsi15(rows):
    """[(bucket end ts, rsi)] on 15-minute closes of the reference price, every open minute."""
    buckets = {}
    for r in rows:
        if r["ref"] is not None and r["open"]:
            buckets[r["ts"] // 900] = (r["ts"] // 900 * 900 + 900, r["ref"])
    keys = sorted(buckets)
    vals = rsi([buckets[k][1] for k in keys])
    return [(buckets[k][0], v) for k, v in zip(keys, vals)]


def _rolling(rows, ratio, daily):
    """Per row: the 24-hour high and the 5-session high (prior 4 daily highs + today's so far), in stock prices."""
    from collections import deque
    q, h24, h5d = deque(), [], []
    daily_highs = {b["t"][:10]: b["h"] for b in daily}
    days = sorted(daily_highs)
    day_max, cur = None, None
    for r in rows:
        v = r["ref"] * ratio
        while q and q[-1][1] <= v:
            q.pop()
        q.append((r["ts"], v))
        while q[0][0] <= r["ts"] - 86400:
            q.popleft()
        h24.append(q[0][1])
        d = I.et(r["ts"]).date().isoformat()
        if d != cur:
            cur, day_max = d, v
        day_max = max(day_max, v)
        prev4 = [daily_highs[x] for x in days if x < d][-4:]
        h5d.append(max(prev4 + [day_max]))
    return h24, h5d


def signals(ticker, rows, daily, hourly, ratio, lane, known, now):
    """New observation events for one ticker and lane. Stock-price levels are scaled to the reference by `ratio`."""
    Ln = LANES[lane]
    rows = [r for r in rows if r["ref"] is not None and r["open"]]
    if not rows or not daily:
        return []
    r15 = rsi15(rows)
    h24, h5d = _rolling(rows, ratio, daily)
    Hs = h24 if Ln["slide"] == "S24" else h5d
    days = sorted({b["t"][:10] for b in daily})
    lv_cache, ph_cache = {}, {}
    out, block_until = [], None
    i = 0
    while i < len(rows):
        r = rows[i]
        px, H = r["ref"] * ratio, Hs[i]
        if px > (1 - Ln["drop"]) * H:
            i += 1
            continue
        day = I.et(r["ts"]).date().isoformat()
        eid = f"{lane}|{ticker}|{day}"
        if eid in known or (block_until and day < block_until):
            i += 1
            continue
        if day not in lv_cache:
            lv_cache[day] = daily_levels(daily, day)
        levels, tested = lv_cache[day]
        hk = r["ts"] // 3600
        if hk not in ph_cache:
            ph_cache[hk] = hourly_pivots(hourly, hk * 3600)
        ph = ph_cache[hk]
        L = touched(px, H, levels, ph)
        if L is None or (Ln["strong"] and strength(L, levels, ph, tested) < 2):
            i += 1
            continue
        # confirmation: within WINDOW open minutes, before a reference below FAIL x L, the 15-minute RSI below 30
        # and turning up on a bucket that ends after the touch
        win = rows[i + 1:i + 1 + WINDOW]
        fail = next((x["ts"] for x in win if x["ref"] * ratio < FAIL * L), None)
        end = fail if fail is not None else (win[-1]["ts"] if win else r["ts"])
        conf = None
        for k in range(1, len(r15)):
            t_end, v = r15[k]
            if t_end <= r["ts"] or t_end > end:
                continue
            if r15[k - 1][1] is not None and v is not None and r15[k - 1][1] < 30 and v > r15[k - 1][1]:
                conf = t_end
                break
        if conf is None:
            if fail is None and len(win) < WINDOW and end > now - 120:
                break                                        # the window is still running: read again next time
            i = next((j for j in range(i + 1, len(rows)) if rows[j]["ts"] > end), len(rows))
            continue
        out.append(dict(id=eid, lane=lane, ticker=ticker, sym=r["sym"], day=day, touch_ts=r["ts"], signal_ts=conf,
                        level=round(L / ratio, 6), level_stock=round(L, 2), slide_high=round(H, 2),
                        stop=round(0.99 * L / ratio, 6), target=round((L + 0.5 * (H - L)) / ratio, 6),
                        strength=strength(L, levels, ph, tested), status="pending",
                        backfill=conf < _ts(FROM)))
        known.add(eid)
        nxt = [d for d in days if d > day]
        block_until = ((I.et(conf).date() + dt.timedelta(days=1)).isoformat() if Ln["block"] == 1 else
                       (nxt[Ln["block"] - 1] if len(nxt) >= Ln["block"] else
                        (dt.date.fromisoformat(day) + dt.timedelta(days=7)).isoformat()))
        i = next((j for j in range(i + 1, len(rows)) if I.et(rows[j]["ts"]).date().isoformat() >= block_until), len(rows))
    return out


# ---------------------------------------------------------------- grading: honest fills on Kalshi prices

def grade(ev, rows, prints, now):
    hold = LANES[ev["lane"]]["hold"]
    if ev["status"] == "pending":
        tries = 0
        for r in (x for x in rows if x["ts"] > ev["signal_ts"]):
            if r["ask"] is None:
                continue
            if r["ts"] + 60 > now:
                return ev
            tries += 1
            if any(p >= r["ask"] for _t, p in prints(r["ts"], r["ts"] + 60)):
                ev.update(status="open", entry_ts=r["ts"], entry=r["ask"], spread_in=I._spread(r))
                break
            if tries >= I.FILL_TRIES:
                ev.update(status="no_fill", note=f"no print at or through the ask in {I.FILL_TRIES} minutes")
                return ev
        else:
            return ev
    if ev["status"] != "open":
        return ev
    used, t_prev = 0, ev["entry_ts"]
    for r in (x for x in rows if x["ts"] > ev["entry_ts"]):
        thru = [t for t, p in prints(t_prev, r["ts"]) if p > ev["target"]]
        if thru:
            return _close(ev, thru[0], ev["target"], "target", I.MAKER)
        t_prev = r["ts"]
        if I.rth_minute(r["ts"]) is not None:
            used += 1
        if r["bid"] is None:
            continue
        if r["bid"] <= ev["stop"]:
            return _close(ev, r["ts"], r["bid"], "stop", I.TAKER)
        if used >= hold:
            return _close(ev, r["ts"], r["bid"], "time", I.TAKER)
    return ev


def _close(ev, ts, px, why, fee):
    gross = px / ev["entry"] - 1
    ev.update(status="settled", exit_ts=int(ts), exit=px, exit_why=why, gross=round(gross, 5),
              net=round(gross - I.TAKER - fee, 5))
    return ev


# ---------------------------------------------------------------- state and the run

def load(path=STATE):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return dict(version=VERSION, registered=REGISTERED, events=[], ratios={}, last_run=None)


def summary(s, include_backfill=False):
    out = {}
    for k in LANES:
        ev = [e for e in s["events"] if e["lane"] == k and (include_backfill or not e.get("backfill"))]
        done = [e["net"] for e in ev if e["status"] == "settled"]
        n = len(done)
        mean = sum(done) / n if n else None
        sd = math.sqrt(sum((x - mean) ** 2 for x in done) / (n - 1)) if n > 1 else 0
        out[k] = dict(n=n, win=(sum(x > 0 for x in done) / n if n else None), net=mean,
                      t=(mean / (sd / math.sqrt(n)) if n > 1 and sd > 0 else None),
                      open=sum(e["status"] == "open" for e in ev), pending=sum(e["status"] == "pending" for e in ev),
                      no_fill=sum(e["status"] == "no_fill" for e in ev))
    return out


def cached_bars(work, syms, now):
    """Alpaca SIP bars, cached in <work>/rebound_bars.json: daily refreshed once an ET day, hourly once an hour."""
    import market_sources as M
    path = os.path.join(work, "rebound_bars.json")
    try:
        with open(path) as f:
            c = json.load(f)
    except (OSError, ValueError):
        c = {}
    today = I.et(now).date().isoformat()
    end = dt.datetime.fromtimestamp(now - 16 * 60, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if c.get("daily_day") != today or set(syms) - set(c.get("daily") or {}):
        c["daily"] = M.bars(syms, "1Day", start=(I.et(now).date() - dt.timedelta(days=420)).isoformat(), end=end, feed="sip")
        c["daily_day"] = today
    if (c.get("hourly_at") or 0) < now - 3600 or set(syms) - set(c.get("hourly") or {}):
        c["hourly"] = M.bars(syms, "1Hour", start=(I.et(now).date() - dt.timedelta(days=35)).isoformat(), end=end, feed="sip")
        c["hourly_at"] = now
    if c.get("daily"):
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(c, f)
        os.replace(tmp, path)
    return c.get("daily") or {}, c.get("hourly") or {}


def track(work, state_path=STATE, now=None, get=I._get, bars=None):
    import market_sources as M
    now = now or time.time()
    s = load(state_path)
    ticks = I.load_ticks(work, now - I.KEEP_DAYS * 86400)
    # stock tickers only: the index perps ("US500", "US Tech 100") are not Alpaca symbols and would fail the whole batch
    syms = sorted({rows[0]["sym"] for rows in ticks.values() if rows and re.fullmatch(r"[A-Z]{1,5}(\.[A-Z])?", rows[0]["sym"])})
    if bars is None:
        daily, hourly = cached_bars(work, syms, now)
    else:
        daily, hourly = bars
    known = {e["id"] for e in s["events"]}
    for ticker, rows in ticks.items():
        sym = rows[0]["sym"] if rows else ""
        d = daily.get(sym) or []
        if not d:
            continue
        # the stock / reference ratio, measured on the last daily close against the reference at that close
        last = d[-1]
        close_ts = _ts(last["t"][:10] + "T21:00:00Z")
        near = [x for x in rows if x["ref"] and abs(x["ts"] - close_ts) <= 3600]
        ratio = (last["c"] / near[-1]["ref"]) if near else s.get("ratios", {}).get(sym, 50.0)
        if not 30 <= ratio <= 70:
            ratio = s.get("ratios", {}).get(sym, 50.0)
        s.setdefault("ratios", {})[sym] = round(ratio, 4)
        for lane in LANES:
            s["events"] += signals(ticker, rows, d, hourly.get(sym) or [], ratio, lane, known, now)
    cache = {}

    def prints_for(ticker):
        def f(t0, t1):
            key = (ticker, int(t0) // 3600)
            if key not in cache:
                h0 = (int(t0) // 3600) * 3600
                cache[key] = I.trades(ticker, h0, h0 + 3600, get=get) if h0 < now else []
            got = cache[key]
            if int(t1) // 3600 != int(t0) // 3600:
                got = got + f((int(t0) // 3600 + 1) * 3600, t1)
            return [(t, p) for t, p in got if t0 <= t < t1]
        return f
    for ev in s["events"]:
        if ev["status"] in ("pending", "open") and ev["ticker"] in ticks:
            try:
                grade(ev, ticks[ev["ticker"]], prints_for(ev["ticker"]), now)
            except RuntimeError as e:
                ev["note"] = str(e)[:120]
    s.update(version=VERSION, registered=REGISTERED, prereg_sha256=PREREG_SHA, **{"from": FROM},
             lanes={k: dict(slide=v["slide"], drop=v["drop"], strong=v["strong"], hold=v["hold"]) for k, v in LANES.items()},
             last_run=dt.datetime.fromtimestamp(now, dt.timezone.utc).isoformat(timespec="seconds"))
    I.save(s, state_path)
    return s


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=("track",))
    ap.add_argument("--work", default=os.path.expanduser("~/invest"))
    ap.add_argument("--state", default=STATE)
    a = ap.parse_args(argv)
    s = track(a.work, a.state)
    for k, v in summary(s, include_backfill=True).items():
        print(k, v)
    return 0


if __name__ == "__main__":
    sys.exit(main())
