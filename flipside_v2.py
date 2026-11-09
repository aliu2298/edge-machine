#!/usr/bin/env python3
"""The Flip Side v2 (flip-v2, registered 2026-11-09): Sandbox paper, no orders.

The OTHER side of each sw15-v1 strategy (swing15.py), held to settlement, on the market cells that were positive
when flipped in the first forward read (windows opening 06:00-12:00Z on 2026-11-09). The frozen list is the
pre-registration: no cell is added or dropped later.

  F1 (flipside_v2_f1) flip 25c: when v1's S1 25c trigger fires, buy the opposite side at its ask at the end of the
     trigger minute (from that minute's row: NO at 1 - yes_bid when the cheap side was YES, YES at yes_ask when NO).
  F2 (flipside_v2_f2) flip 35c: the same on the 35c trigger.
  F3 (flipside_v2_f3) underdog at minute 2: the side opposite v1's S2 favourite, at its ask at minute 2.
  F4 (flipside_v2_f4) underdog at minute 10: the same, opposite S3.

Fees: the taker fee on entry, 0.07 * m * p * (1-p) a contract (swing15.fee, as v1); nothing at settlement. A price
outside 1-99c, or a missing quote, is a skip, recorded with its reason. Like sw15-v2 this is a filter over the v1 hour
shards (data/swing15/<ET day>/<HH>.json), not a second poller; only windows opening at or after FROM count, so the
selection windows never do. The record is written to data/flipside_v2_ledger.json by the same hourly run (swing15.yml).
"""
import datetime as dt
import os
import sys

import swing15 as W

VERSION = "flip-v2"
REGISTERED = "2026-11-09"
FROM = "2026-11-09T13:15:00+00:00"           # fresh record: windows opening at or after this (after the merge)
PICKED_ON = "windows opening 06:00-12:00Z on 2026-11-09"
PATH = os.path.join(W.ROOT, "data", "flipside_v2_ledger.json")
LO, HI = 0.01, 0.99


def _kx(names):
    return tuple(f"KX{n}15M" for n in names.split())


# The frozen pre-registration (2026-11-09). Do not edit.
CELLS = {
    "flipside_v2_f1": _kx("10YRRATE BRENT BTC COPPER ETH GOLD HYPE NATGAS NEAR PALLADIUM PLATINUM SILVER WTI XRP ZEC"),
    "flipside_v2_f2": _kx("2YRRATE AUDUSD BRENT BTC ETH EURUSD HYPE NEAR PLATINUM SILVER WTI XRP"),
    "flipside_v2_f3": _kx("10YRRATE 30YRRATE 5YRRATE AUDUSD DOGE EURUSD HYPE NATGAS PALLADIUM USDCAD USDJPY XRP ZEC"),
    "flipside_v2_f4": _kx("30YRRATE 5YRRATE DOGE HYPE NEAR USDCAD XRP ZEC"),
}
LABELS = {"flipside_v2_f1": "F1 Flip 25c", "flipside_v2_f2": "F2 Flip 35c",
          "flipside_v2_f3": "F3 Underdog at minute 2", "flipside_v2_f4": "F4 Underdog at minute 10"}
SOURCE = {"flipside_v2_f1": ("s1", "0.25"), "flipside_v2_f2": ("s1", "0.35"),
          "flipside_v2_f3": ("s2", None), "flipside_v2_f4": ("s3", None)}


def _won(w, side):
    res = w.get("result")
    if res not in ("yes", "no"):
        return None
    return 1.0 if res == side else 0.0


def _entry(side, yes_bid, yes_ask):
    """The ask of `side` from a YES quote: YES at yes_ask, NO at 1 - yes_bid."""
    p = yes_ask if side == "yes" else (None if yes_bid is None else round(1 - yes_bid, 4))
    return p


def flip(w, strat):
    """One window, one strategy: {"skip": reason} or {"side", "price", "won", "roi"}; None when v1 did not trigger."""
    src, band = SOURCE[strat]
    if src == "s1":
        e = (w.get("s1") or {}).get(band)
        if not e or not e.get("trigger"):
            return None
        side = "no" if e["side"] == "yes" else "yes"
        m = e["trigger"]["minute"]
        cols = w.get("minute_cols") or list(W.MINUTE_COLS)
        rowm = next((r for r in (w.get("minutes") or []) if r[0] == m), None)
        if rowm is None:
            return dict(skip="no_minute_row")
        q = dict(zip(cols, rowm))
        p = _entry(side, q.get("yes_bid"), q.get("yes_ask"))
    else:
        x = w.get(src) or {}
        if x.get("side") not in ("yes", "no"):
            return None                                          # v1 had no favourite (no quote, no candle, a 50c tie)
        side = "no" if x["side"] == "yes" else "yes"
        p = _entry(side, x.get("yes_bid"), x.get("yes_ask"))
    if p is None:
        return dict(skip="no_quote", side=side)
    if not LO - 1e-9 <= p <= HI + 1e-9:
        return dict(skip="out_of_range", side=side, price=p)
    won = _won(w, side)
    if won is None:
        return dict(skip="no_result", side=side, price=p)
    cost = p + W.fee(p, W.TAKER, w.get("fee_multiplier") or 1.0)
    return dict(side=side, price=p, won=won, roi=round(won / cost - 1, 4))


def in_flip(w, strat):
    return W._ts(w["open"]) >= W._ts(FROM) and w["series"] in CELLS[strat]


def _cell(rows):
    """rows: [(day, open, won, price, roi)] -> n, wins, fair, mean ROI, z by day, halves."""
    if not rows:
        return None
    rows = sorted(rows, key=lambda r: r[1])
    n = len(rows)
    half = rows[n // 2][1]
    h = [[r[4] for r in rows if r[1] < half], [r[4] for r in rows if r[1] >= half]]
    return dict(n=n, hits=int(sum(r[2] for r in rows)), hit_rate=sum(r[2] for r in rows) / n,
                fair=sum(r[3] for r in rows) / n, mean_roi=sum(r[4] for r in rows) / n,
                z=W.cluster_z([(r[0], r[2], r[3]) for r in rows]), days=len({r[0] for r in rows}),
                half_roi=[sum(x) / len(x) if x else None for x in h])


def records(state):
    """{strat: {"all": cell, "series": {series: cell or None}, "skips": {reason: n}}}."""
    out = {}
    for strat, series in CELLS.items():
        by, skips = {s: [] for s in series}, {}
        for w in (state.get("windows") or {}).values():
            if not in_flip(w, strat):
                continue
            f = flip(w, strat)
            if f is None:
                continue
            if "skip" in f:
                skips[f["skip"]] = skips.get(f["skip"], 0) + 1
                continue
            by[w["series"]].append((w["day"], w["open"], f["won"], f["price"], f["roi"]))
        out[strat] = dict(all=_cell([r for rs in by.values() for r in rs]),
                          series={s: _cell(rs) for s, rs in by.items()}, skips=skips)
    return out


def ledger(state, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    slim = lambda c: None if not c else {k: c[k] for k in ("n", "hits", "hit_rate", "fair", "mean_roi", "z", "days")}
    return dict(version=VERSION, registered=REGISTERED, **{"from": FROM}, picked_on=PICKED_ON,
                cells={k: list(v) for k, v in CELLS.items()}, updated=now.isoformat(timespec="seconds"),
                records={k: dict(all=slim(v["all"]), series={s: slim(c) for s, c in v["series"].items()}, skips=v["skips"])
                         for k, v in records(state).items()})


def main():
    now = dt.datetime.now(dt.timezone.utc)
    start = dt.datetime.fromisoformat(FROM).astimezone(W.ET).date()
    days = {(start + dt.timedelta(days=i)).isoformat() for i in range((now.astimezone(W.ET).date() - start).days + 1)}
    blob = ledger(W.load(days=days), now)
    W._write(PATH, blob)
    print("flip-v2", {k: (v["all"] or {}).get("n", 0) for k, v in blob["records"].items()})
    return 0


if __name__ == "__main__":
    sys.exit(main())
