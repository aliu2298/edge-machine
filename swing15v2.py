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

VERSION = "sw15-v3"                 # sw15-v2 until 2026-11-09 18:00Z (the registered cells: CELLS_V2)
REGISTERED = "2026-11-09"
FROM = "2026-11-09T13:00:00+00:00"           # fresh record: windows opening at or after this (after the merge)
PICKED_ON = "windows opening 06:00-12:00Z on 2026-11-09"
PATH = os.path.join(W.ROOT, "data", "swing15v2_ledger.json")
S1_CELL = ("0.35", "3.0", "hold")            # band, multiplier, exit: the only S1 cell in v2


def _kx(*names):
    return tuple(f"KX{n}15M" for n in names)


# 2026-11-09 (Olu, from the 17:02Z ledgers): the negative markets are removed. Surviving cells keep their running record
# from FROM; a removed cell stops counting at REMOVED_AT and its final record is kept (records(..., removed=True)).
REMOVED_AT = "2026-11-09T18:00:00+00:00"
# The frozen pre-registration (sw15-v2, 2026-11-09). Do not edit.
CELLS_V2 = {
    "swing15v2_s1": _kx("ZEC", "GOLD", "COPPER", "PALLADIUM", "NATGAS", "USDJPY", "GBPUSD", "USDCAD", "10YRRATE",
                        "30YRRATE"),
    "swing15v2_s2": _kx("BTC", "SOL", "BNB", "GOLD", "SILVER", "COPPER", "WTI", "GBPUSD", "2YRRATE"),
    "swing15v2_s3": _kx("BTC", "ETH", "SOL", "BNB", "GOLD", "SILVER", "COPPER", "PALLADIUM", "WTI", "USDJPY", "GBPUSD",
                        "AUDUSD", "10YRRATE", "2YRRATE"),
}
# sw15-v3: the frozen keep list (2026-11-09). Do not edit.
CELLS_V3 = {
    "swing15v2_s1": _kx("NATGAS", "GBPUSD", "ZEC", "GOLD"),
    "swing15v2_s2": _kx("WTI", "BTC", "SOL"),
    "swing15v2_s3": _kx("USDJPY", "2YRRATE", "GOLD", "ETH", "BNB", "BTC"),
}
# 2026-11-09 (Olu): S1 (the Swing) retired at RETIRED_AT, replaced by Steady Favourites (steadyfav.py); its final record
# is records(..., retired=True). S2 and S3 run on unchanged. v1 keeps grading S1 entries: The Flip Side, Hold to End and
# the Lead Swap Board read them.
RETIRED_AT = "2026-11-09T22:00:00+00:00"
RETIRED = {"swing15v2_s1": CELLS_V3["swing15v2_s1"]}
CELLS = dict(CELLS_V3, swing15v2_s1=())
REMOVED = {k: tuple(s for s in v if s not in CELLS_V3[k]) for k, v in CELLS_V2.items()}
LABELS = {"swing15v2_s1": "S1 Swing · 35c · 3x · else hold", "swing15v2_s2": "S2 Favourite at start",
          "swing15v2_s3": "S3 Favourite at 5 minutes left"}


def v1_key(strat):
    """The sw15-v1 cell key in swing15.cells() that a v2 strategy reads."""
    return ("swing15_s1",) + S1_CELL if strat == "swing15v2_s1" else ("swing15_" + strat.rsplit("_", 1)[1],)


def in_v2(w, strat=None, cells=None, until=None, start=None):
    cells = CELLS if cells is None else cells
    if W._ts(w["open"]) < W._ts(start or FROM) or (until and W._ts(w["open"]) >= W._ts(until)):
        return False
    return w["series"] in (cells[strat] if strat else {s for c in cells.values() for s in c})


def records(state, removed=False, retired=False, start=None):
    """{strat: {"all": cell, "series": {series: cell or None}}}, where a cell is swing15.cells()' record. With
    removed=True: the removed cells' final records (windows opening before REMOVED_AT). retired=True: S1's final record
    (windows opening before RETIRED_AT); start narrows it (e.g. since the 18:00Z cut)."""
    cells, until = (REMOVED, REMOVED_AT) if removed else (RETIRED, RETIRED_AT) if retired else (CELLS, None)
    out = {}
    for strat, series in cells.items():
        key = v1_key(strat)
        out[strat] = dict(all=W.cells(state, lambda w, s=strat: in_v2(w, s, cells, until, start)).get(key),
                          series={s: W.cells(state, lambda w, s=s, t=strat: in_v2(w, t, cells, until, start)
                                             and w["series"] == s).get(key) for s in series})
    return out


def ledger(state, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    slim = lambda c: None if not c else {k: c[k] for k in ("n", "hits", "hit_rate", "fair", "mean_roi", "z", "days")}
    rec = records(state)
    return dict(version=VERSION, registered=REGISTERED, **{"from": FROM}, picked_on=PICKED_ON,
                cells={k: list(v) for k, v in CELLS.items()}, cells_v2={k: list(v) for k, v in CELLS_V2.items()},
                cells_v3={k: list(v) for k, v in CELLS_V3.items()}, retired_at=RETIRED_AT,
                retired_records={k: dict(all=slim(v["all"]), series={s: slim(c) for s, c in v["series"].items()})
                                 for k, v in records(state, retired=True).items()},
                removed_at=REMOVED_AT, removed={k: list(v) for k, v in REMOVED.items()}, s1_cell=list(S1_CELL),
                updated=now.isoformat(timespec="seconds"),
                records={k: dict(all=slim(v["all"]), series={s: slim(c) for s, c in v["series"].items()})
                         for k, v in rec.items()},
                removed_records={k: dict(all=slim(v["all"]), series={s: slim(c) for s, c in v["series"].items()})
                                 for k, v in records(state, removed=True).items()})


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
