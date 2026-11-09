#!/usr/bin/env python3
"""Lead Swap Board (lsb-v1, registered 2026-11-09): Sandbox paper, no orders.

How and how often the lead swaps on Kalshi's 15-minute markets, and a test of Olu's clue: send the swing trade to the
series swapping the lead most, and the favourite trade to the stablest. A 14-day backtest on 5 assets found swaps
did NOT persist (past-2h swaps v next window, corr -0.006); this measures all the 15-minute series live.

Everything is read from the sw15-v1 hour shards (data/swing15/<ET day>/<HH>.json); there is no second poller.

1. MEASURE, per window (metrics()): a lead swap is the YES mid, (bid + ask) / 2 of a minute row, crossing 50c between
   consecutive minute rows that both have a quote (an empty book, 0/100c, is skipped) (a mid of exactly 50c holds the previous side). Kept: the
   swap count, each swap's minute, the minute 0-9 mid range, each swing's size (cents from the low to the high of the
   two minutes' traded range around the swap), and whether the minute-14 favourite (mid above or below 50c) won.
   KXCRYPTOLEAD15M is left out: it is a which-coin-leads market, not an up/down one.
2. BOARD, every hour: series ranked by swaps per window over the windows that closed in the last 2 hours (8 windows)
   and in the last 24 hours; ties broken by the larger minute 0-9 mid range, then the ticker. A series needs 4 of its 8
   windows (2h) or 24 of 96 (24h) to be ranked.
3. PERSISTENCE: each hour's top 3 and bottom 3 by the past 2 hours against the top 3 and bottom 3 of that hour's own
   windows (hit rate v chance, 3/N), and per group the correlation of a window's swaps with its series' past-2h rate.
4. PAPER ROUTING (fresh from FROM): for windows opening in hour H, the top 3 by past-2h swaps get v1's S1 35c entry
   held to settlement (leadswap_swing), the bottom 3 get v1's S3 favourite at minute 10, held (leadswap_fav). Controls:
   the same trades on the opposite end (leadswap_swing_ctrl on the bottom 3, leadswap_fav_ctrl on the top 3). v1's fills
   and fees. The picks for hour H are frozen in the ledger the first time a run at or after H computes them, from the
   windows graded by then, so later data never moves them. z is cluster-aware: the markets of one block (crypto,
   metals, energy, yields, FX, indices) in the same window are one cluster.
"""
import bisect
import datetime as dt
import math
import os
import sys

import swing15 as W

VERSION = "lsb-v1"
REGISTERED = "2026-11-09"
FROM = "2026-11-09T15:00:00+00:00"           # routing record: windows opening at or after this (after the merge)
PATH = os.path.join(W.ROOT, "data", "leadswap_ledger.json")
EXCLUDE = ("KXCRYPTOLEAD15M",)
PAST_H, DAY_H = 2, 24
MIN_PAST, MIN_DAY = 4, 24
TOP = 3
STRATS = {"leadswap_swing": "Swing to the most swaps", "leadswap_fav": "Favourite to the most stable",
          "leadswap_swing_ctrl": "Control · swing to the most stable", "leadswap_fav_ctrl": "Control · favourite to the most swaps"}
METALS = ("GOLD", "SILVER", "COPPER", "PLATINUM", "PALLADIUM")
ENERGY = ("WTI", "BRENT", "NATGAS", "GAS", "OIL")
FX = ("USD", "EUR", "GBP", "JPY", "CAD", "AUD", "CHF", "NZD", "MXN", "CNY")


def block(w_or_series, group=None):
    """crypto, metals, energy, yields, fx or indices (the cluster block)."""
    s = w_or_series if isinstance(w_or_series, str) else w_or_series["series"]
    group = group or ({} if isinstance(w_or_series, str) else w_or_series).get("group")
    name = s[2:-3] if s.startswith("KX") and s.endswith("15M") else s
    if group == "Crypto":
        return "crypto"
    if group == "Commodities" or any(m in name for m in METALS + ENERGY):
        return "metals" if any(m in name for m in METALS) else "energy"
    if "RATE" in name:
        return "yields"
    if any(c in name for c in FX):
        return "fx"
    return "indices"


def family(b):
    """The persistence groups: crypto, commodities, FX, yields, indices."""
    return {"metals": "commodities", "energy": "commodities"}.get(b, b)


def _row(w, m):
    cols = w.get("minute_cols") or list(W.MINUTE_COLS)
    r = next((x for x in w.get("minutes") or [] if x[0] == m), None)
    return dict(zip(cols, r)) if r else None


def metrics(w):
    """One window's lead-swap measures, or None when it has no two-sided quote at all."""
    mids = []
    for m in range(15):
        r = _row(w, m)
        if r and r.get("yes_bid") is not None and r.get("yes_ask") is not None \
                and 0 <= r["yes_bid"] <= r["yes_ask"] <= 1 and not (r["yes_bid"] == 0 and r["yes_ask"] == 1):
            mids.append((m, (r["yes_bid"] + r["yes_ask"]) / 2, r))
    if not mids:
        return None
    swaps, sizes, side = [], [], None
    prev = None
    for m, mid, r in mids:
        s = 1 if mid > 0.5 + 1e-9 else -1 if mid < 0.5 - 1e-9 else 0
        if s and side and s != side:
            swaps.append(m)
            lows = [x for x in (prev[2].get("low"), r.get("low")) if x is not None]
            highs = [x for x in (prev[2].get("high"), r.get("high")) if x is not None]
            sizes.append(round((max(highs) - min(lows)) * 100, 1) if lows and highs else None)
        if s:
            side = s
        prev = (m, mid, r)
    early = [mid for m, mid, _r in mids if m <= 9]
    fav_won = None
    last = next((mid for m, mid, _r in mids if m == 14), None)
    if last is not None and abs(last - 0.5) > 1e-9 and w.get("result") in ("yes", "no"):
        fav_won = (last > 0.5) == (w["result"] == "yes")
    return dict(swaps=len(swaps), minutes=swaps, sizes=sizes, quoted=len(mids),
                range09=round((max(early) - min(early)) * 100, 1) if early else None, fav14_won=fav_won)


def _close(w):
    return W._ts(w.get("close") or w["open"]) if w.get("close") else W._ts(w["open"]) + 900


def table(state):
    """[(series, group, open_ts, close_ts, metrics, window)] for every measurable window, oldest first."""
    out = []
    for w in (state.get("windows") or {}).values():
        if w["series"] in EXCLUDE or w.get("schema", 1) < 2:
            continue
        m = metrics(w)
        if m:
            out.append((w["series"], w.get("group"), W._ts(w["open"]), _close(w), m, w))
    return sorted(out, key=lambda r: (r[2], r[0]))


def rank(rows, at, hours, need):
    """[(series, swaps/window, n, mean range)] by swaps per window over windows closing in (at - hours, at], most first."""
    lo = at - hours * 3600
    by = {}
    for s, _g, _o, c, m, _w in rows:
        if lo < c <= at:
            by.setdefault(s, []).append(m)
    out = []
    for s, ms in by.items():
        if len(ms) < need:
            continue
        rng = [m["range09"] for m in ms if m["range09"] is not None]
        out.append((s, sum(m["swaps"] for m in ms) / len(ms), len(ms), sum(rng) / len(rng) if rng else 0.0))
    return sorted(out, key=lambda r: (-r[1], -r[3], r[0]))


def ends(ranked, k=TOP):
    """(top k, bottom k); a series is never in both."""
    top = [r[0] for r in ranked[:k]]
    bottom = [r[0] for r in ranked[::-1] if r[0] not in top][:k]
    return top, bottom


def pick(rows, hour_ts, graded_by=None):
    """The routing picks for windows opening in the hour starting hour_ts, from the windows graded by `graded_by`."""
    have = [r for r in rows if graded_by is None or r[3] <= graded_by]
    ranked = rank(have, hour_ts, PAST_H, MIN_PAST)
    top, bottom = ends(ranked)
    return dict(top=top, bottom=bottom, ranked=len(ranked))


def _corr(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    return None if sx == 0 or sy == 0 else sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy)


def persistence(rows):
    """Top/bottom 3 keep rate v chance, and per family the corr of past-2h swaps/window with the next window's swaps."""
    if not rows:
        return dict(hours=0, top=None, bottom=None, chance=None, corr={})
    first = min(r[2] for r in rows)
    last = max(r[2] for r in rows)
    h = int(first // 3600) * 3600 + PAST_H * 3600
    keep_t = keep_b = slots = 0
    chance = []
    hours = 0
    while h + 3600 <= last + 900:
        past = rank(rows, h, PAST_H, MIN_PAST)
        nxt = {}
        for s, _g, o, _c, m, _w in rows:
            if h <= o < h + 3600:
                nxt.setdefault(s, []).append(m)
        now_r = sorted(((s, sum(m["swaps"] for m in ms) / len(ms), len(ms),
                         sum(m["range09"] or 0 for m in ms) / len(ms)) for s, ms in nxt.items() if len(ms) >= 2),
                       key=lambda r: (-r[1], -r[3], r[0]))
        common = {r[0] for r in past} & {r[0] for r in now_r}
        if len(common) >= 2 * TOP:
            t0, b0 = ends([r for r in past if r[0] in common])
            t1, b1 = ends([r for r in now_r if r[0] in common])
            keep_t += len(set(t0) & set(t1))
            keep_b += len(set(b0) & set(b1))
            slots += TOP
            chance.append(TOP / len(common))
            hours += 1
        h += 3600
    corr = {}
    pairs = {}
    by = {}
    for r in rows:
        by.setdefault(r[0], []).append(r)
    for s, rs in by.items():
        closes = [r[3] for r in rs]
        for s_, g, o, _c, m, w in rs:
            lo, hi = bisect.bisect_right(closes, o - PAST_H * 3600), bisect.bisect_right(closes, o)
            past = [x[4]["swaps"] for x in rs[lo:hi]]
            if len(past) >= MIN_PAST:
                pairs.setdefault(family(block(w)), []).append((sum(past) / len(past), m["swaps"]))
    for fam, ps in sorted(pairs.items()):
        c = _corr([p[0] for p in ps], [p[1] for p in ps])
        corr[fam] = dict(n=len(ps), corr=None if c is None else round(c, 3))
    return dict(hours=hours, top=None if not slots else round(keep_t / slots, 3),
                bottom=None if not slots else round(keep_b / slots, 3),
                chance=None if not chance else round(sum(chance) / len(chance), 3), corr=corr)


def _trade(w, strat):
    """v1's S1 35c held to settlement, or v1's S3 favourite held: (won, price, roi) or None."""
    if strat in ("leadswap_swing", "leadswap_swing_ctrl"):
        e = (w.get("s1") or {}).get("0.35")
        if not e or e.get("won") is None:
            return None
        cost = 0.35 + W.fee(0.35, W.TAKER, w.get("fee_multiplier") or 1.0)
        return e["won"], 0.35, round(e["won"] / cost - 1, 4)
    x = w.get("s3") or {}
    if x.get("status") != "filled" or x.get("roi") is None:
        return None
    return int(x["won"] == 1), x["price"], x["roi"]


def routing(rows, picks):
    """{strat: cell}: each frozen hour's picks applied to the windows opening in that hour."""
    found = {k: [] for k in STRATS}
    for s, _g, o, _c, _m, w in rows:
        if o < W._ts(FROM):
            continue
        hk = dt.datetime.fromtimestamp(o - o % 3600, dt.timezone.utc).isoformat()
        p = picks.get(hk)
        if not p:
            continue
        for strat, side in (("leadswap_swing", "top"), ("leadswap_fav", "bottom"),
                            ("leadswap_swing_ctrl", "bottom"), ("leadswap_fav_ctrl", "top")):
            if s in p[side]:
                t = _trade(w, strat)
                if t:
                    found[strat].append((f"{o}|{block(w)}", o, t[0], t[1], t[2], s))
    out = {}
    for strat, rs in found.items():
        if not rs:
            out[strat] = None
            continue
        n = len(rs)
        out[strat] = dict(n=n, hits=int(sum(r[2] for r in rs)), hit_rate=sum(r[2] for r in rs) / n,
                          fair=sum(r[3] for r in rs) / n, mean_roi=sum(r[4] for r in rs) / n,
                          z=W.cluster_z([(r[0], r[2], r[3]) for r in rs]), clusters=len({r[0] for r in rs}),
                          series={})
        for r in rs:
            c = out[strat]["series"].setdefault(r[5], [0, 0, 0.0])
            c[0] += 1
            c[1] += int(r[2])
            c[2] += r[4]
    return out


def board(rows, now_ts):
    """The hourly board: the 2h and 24h ends, the minute histogram and the ET hour-of-day heatmap (last 24h / all)."""
    r2, r24 = rank(rows, now_ts, PAST_H, MIN_PAST), rank(rows, now_ts, DAY_H, MIN_DAY)
    hist = [0] * 15
    day = [r for r in rows if now_ts - DAY_H * 3600 < r[3] <= now_ts]
    for r in day:
        for m in r[4]["minutes"]:
            hist[m] += 1
    heat = {}
    for s, _g, o, _c, m, _w in rows:
        hh = dt.datetime.fromtimestamp(o, W.ET).hour
        c = heat.setdefault(s, {}).setdefault(hh, [0, 0])
        c[0] += m["swaps"]
        c[1] += 1
    sizes = [x for r in day for x in r[4]["sizes"] if x is not None]
    fav = [r[4]["fav14_won"] for r in day if r[4]["fav14_won"] is not None]
    return dict(past2h=[list(x) for x in r2], past24h=[list(x) for x in r24], minutes=hist, windows_24h=len(day),
                swaps_24h=sum(r[4]["swaps"] for r in day), median_swing=sorted(sizes)[len(sizes) // 2] if sizes else None,
                fav14_won=None if not fav else round(sum(fav) / len(fav), 3),
                heat={s: {str(h): [c[0], c[1]] for h, c in hs.items()} for s, hs in sorted(heat.items())},
                blocks={s: block(s) for s in heat})


def empty():
    return dict(version=VERSION, registered=REGISTERED, **{"from": FROM}, picks={}, board=None, persistence=None,
                routing=None, updated=None)


def update(state, led, now=None):
    """Freeze the picks for every hour from FROM up to now that has none yet; refresh the board and the readouts."""
    now = now or dt.datetime.now(dt.timezone.utc)
    rows = table(state)
    h = max(W._ts(FROM), now.timestamp() - 6 * 3600)
    h = h - h % 3600
    while h <= now.timestamp():
        key = dt.datetime.fromtimestamp(h, dt.timezone.utc).isoformat()
        if key not in led["picks"]:
            led["picks"][key] = dict(pick(rows, h, graded_by=now.timestamp()), at=now.isoformat(timespec="seconds"))
        h += 3600
    led["board"] = board(rows, now.timestamp())
    led["persistence"] = persistence(rows)
    led["routing"] = routing(rows, led["picks"])
    led["updated"] = now.isoformat(timespec="seconds")
    return led


def load(path=PATH):
    try:
        import json
        with open(path) as f:
            return dict(empty(), **json.load(f))
    except (OSError, ValueError):
        return empty()


def main():
    now = dt.datetime.now(dt.timezone.utc)
    days = {(now - dt.timedelta(days=i)).astimezone(W.ET).date().isoformat() for i in range(8)}
    led = update(W.load(days=days), load(), now)
    W._write(PATH, led)
    print("lsb-v1", {k: (v or {}).get("n", 0) for k, v in led["routing"].items()},
          "picks", len(led["picks"]), "persistence hours", led["persistence"]["hours"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
