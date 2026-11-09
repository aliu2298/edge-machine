#!/usr/bin/env python3
"""15-Minute Swing v2 (sw15-v2, registered 2026-11-09): Sandbox paper, no orders.

The same three strategies as sw15-v1 (swing15.py), with the same rules, fills, fees and grading, restricted to the
market x strategy cells that were positive in the first forward read (windows opening 06:00-12:00Z on 2026-11-09).
That frozen list is the pre-registration: no cell is added or dropped later.

  S1 (swing15v2_s1): the 35c band, a 3x take-profit, held to settlement when the sell does not fill.
  S2 (swing15v2_s2): the favourite at minute 2, held.
  S3 (swing15v2_s3): the favourite at minute 10, held.

v2 is NOT a second poller. sw15-v1 keeps grading every window of all 15-minute series into its hour shards
(data/swing15/<ET day>/<HH>.json); v2 is a filter over those rows: its cells, and windows opening at or after FROM.
FROM is after the merge, so the 06:00-12:00Z windows the cells were picked on never count (that would be in-sample).
Its record is written to data/swing15v2_ledger.json by the same hourly run (swing15.yml).
"""
import datetime as dt
import json
import os
import sys

import swing15 as W

VERSION = "sw15-v2"
REGISTERED = "2026-11-09"
FROM = "2026-11-09T13:00:00+00:00"           # fresh record: windows opening at or after this (after the merge)
PICKED_ON = "windows opening 06:00-12:00Z on 2026-11-09"
PATH = os.path.join(W.ROOT, "data", "swing15v2_ledger.json")
S1_CELL = ("0.35", "3.0", "hold")            # band, multiplier, exit: the only S1 cell in v2


def _kx(*names):
    return tuple(f"KX{n}15M" for n in names)


# The frozen pre-registration (2026-11-09). Do not edit.
CELLS = {
    "swing15v2_s1": _kx("ZEC", "GOLD", "COPPER", "PALLADIUM", "NATGAS", "USDJPY", "GBPUSD", "USDCAD", "10YRRATE",
                        "30YRRATE"),
    "swing15v2_s2": _kx("BTC", "SOL", "BNB", "GOLD", "SILVER", "COPPER", "WTI", "GBPUSD", "2YRRATE"),
    "swing15v2_s3": _kx("BTC", "ETH", "SOL", "BNB", "GOLD", "SILVER", "COPPER", "PALLADIUM", "WTI", "USDJPY", "GBPUSD",
                        "AUDUSD", "10YRRATE", "2YRRATE"),
}
LABELS = {"swing15v2_s1": "S1 Swing · 35c · 3x · else hold", "swing15v2_s2": "S2 Favourite at start",
          "swing15v2_s3": "S3 Favourite at 5 minutes left"}


def v1_key(strat):
    """The sw15-v1 cell key in swing15.cells() that a v2 strategy reads."""
    return ("swing15_s1",) + S1_CELL if strat == "swing15v2_s1" else ("swing15_" + strat.rsplit("_", 1)[1],)


def in_v2(w, strat=None):
    if W._ts(w["open"]) < W._ts(FROM):
        return False
    return w["series"] in (CELLS[strat] if strat else {s for c in CELLS.values() for s in c})


def records(state):
    """{strat: {"all": cell, "series": {series: cell or None}}}, where a cell is swing15.cells()' record."""
    out = {}
    for strat, series in CELLS.items():
        key = v1_key(strat)
        out[strat] = dict(all=W.cells(state, lambda w, s=strat: in_v2(w, s)).get(key),
                          series={s: W.cells(state, lambda w, s=s, t=strat: in_v2(w, t) and w["series"] == s).get(key)
                                  for s in series})
    return out


def ledger(state, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    slim = lambda c: None if not c else {k: c[k] for k in ("n", "hits", "hit_rate", "fair", "mean_roi", "z", "days")}
    rec = records(state)
    return dict(version=VERSION, registered=REGISTERED, **{"from": FROM}, picked_on=PICKED_ON,
                cells={k: list(v) for k, v in CELLS.items()}, s1_cell=list(S1_CELL),
                updated=now.isoformat(timespec="seconds"),
                records={k: dict(all=slim(v["all"]), series={s: slim(c) for s, c in v["series"].items()})
                         for k, v in rec.items()})


def main():
    now = dt.datetime.now(dt.timezone.utc)
    start = dt.datetime.fromisoformat(FROM).astimezone(W.ET).date()
    days = {(start + dt.timedelta(days=i)).isoformat() for i in range((now.astimezone(W.ET).date() - start).days + 1)}
    blob = ledger(W.load(days=days), now)
    W._write(PATH, blob)
    print("v2", {k: (v["all"] or {}).get("n", 0) for k, v in blob["records"].items()})
    return 0


if __name__ == "__main__":
    sys.exit(main())
