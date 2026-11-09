#!/usr/bin/env python3
"""Hold to End (hte-v1, registered 2026-11-09): Sandbox paper, no orders.

sw15-v1's S1 entry exactly as v1 records it (swing15.py): the first print on either side at or through the band in
minutes 0-4, entered at the band price with v1's honest fill and taker entry fee. No resting sell: held to settlement,
so the outcome is the s1[band]["won"] v1 already stores, and the return is won / (band + fee) - 1.

Frozen cells (hold-to-settlement return over +10% in the windows opening 06:00-12:00Z on 2026-11-09), the
pre-registration; no cell is added or dropped later:
  holdtoend_25: 25c on USDCAD, 30YRRATE, 5YRRATE
  holdtoend_35: 35c on 10YRRATE, GBPUSD, USDCAD, USDJPY, 30YRRATE, GOLD

hte-v2 (18:00Z): 35c on GBPUSD only. Retired at 22:00Z (decide at 30: 11/32, -6.1%) for hte-v3: 35c on USDCAD only,
a fresh record from FROM_V3; USDCAD's hte-v1 result is shown, not counted.

A filter over the v1 hour shards (data/swing15/<ET day>/<HH>.json), not a second poller. Only windows opening at or
after FROM (after the merge) count. The record is written to data/holdtoend_ledger.json by the hourly run (swing15.yml).
"""
import datetime as dt
import os
import sys

import flipside_v2 as F
import swing15 as W

VERSION = "hte-v3"                  # hte-v1 to 18:00Z, hte-v2 to 22:00Z on 2026-11-09 (CELLS_V1, CELLS_V2)
REGISTERED = "2026-11-09"
FROM = "2026-11-09T14:00:00+00:00"           # hte-v1/v2 record: windows opening at or after this
# hte-v3 (Olu, 2026-11-09): hte-v2 (GBPUSD 35c) retired at its decide-at-30 read; one new cell, 35c on USDCAD, with a
# FRESH record from FROM_V3 (the first window after the merge). USDCAD's hte-v1 35c result is not carried over.
FROM_V3 = "2026-11-09T23:15:00+00:00"
RETIRED_AT = "2026-11-09T22:00:00+00:00"     # hte-v2's last counted window opens before this
PICKED_ON = "windows opening 06:00-12:00Z on 2026-11-09"
PATH = os.path.join(W.ROOT, "data", "holdtoend_ledger.json")


def _kx(names):
    return tuple(f"KX{n}15M" for n in names.split())


# 2026-11-09 (Olu, from the 17:02Z ledgers): the negative markets are removed. Surviving cells keep their running record
# from FROM; a removed cell stops counting at REMOVED_AT and its final record is kept (records(..., removed=True)).
REMOVED_AT = "2026-11-09T18:00:00+00:00"
# The frozen pre-registration (hte-v1, 2026-11-09). Do not edit.
CELLS_V1 = {
    "holdtoend_25": _kx("USDCAD 30YRRATE 5YRRATE"),
    "holdtoend_35": _kx("10YRRATE GBPUSD USDCAD USDJPY 30YRRATE GOLD"),
}
# hte-v2: the frozen keep list (2026-11-09). The 25c row is removed entirely (all three markets negative). Do not edit.
CELLS_V2 = {
    "holdtoend_25": (),
    "holdtoend_35": _kx("GBPUSD"),
}
# hte-v3: the one live cell. The 25c USDCAD cell stays removed. Do not edit.
CELLS = {
    "holdtoend_25": (),
    "holdtoend_35": _kx("USDCAD"),
}
REMOVED = {k: tuple(s for s in v if s not in CELLS_V2[k]) for k, v in CELLS_V1.items()}
BAND = {"holdtoend_25": "0.25", "holdtoend_35": "0.35"}
LABELS = {"holdtoend_25": "Hold to End · 25c", "holdtoend_35": "Hold to End · 35c"}


def entry(w, strat):
    """None when v1 did not enter at this band; {"skip"} when unsettled; else {"side", "price", "won", "roi"}."""
    band = BAND[strat]
    e = (w.get("s1") or {}).get(band)
    if not e:
        return None
    if e.get("won") is None:
        return dict(skip="no_result", side=e.get("side"))
    p = float(band)
    cost = p + W.fee(p, W.TAKER, w.get("fee_multiplier") or 1.0)
    return dict(side=e["side"], price=p, won=e["won"], roi=round(e["won"] / cost - 1, 4))


def records(state, removed=False, retired=False):
    """{strat: {"all": cell, "series": {series: cell or None}, "skips": {reason: n}}} (flipside_v2's cell shape): the
    live hte-v3 cells from FROM_V3. removed=True: the cells cut at REMOVED_AT, final (FROM to REMOVED_AT). retired=True:
    hte-v2's cells, final (FROM to RETIRED_AT)."""
    cells, start, until = ((REMOVED, FROM, REMOVED_AT) if removed else (CELLS_V2, FROM, RETIRED_AT) if retired
                           else (CELLS, FROM_V3, None))
    out = {}
    for strat, series in cells.items():
        by, skips = {s: [] for s in series}, {}
        for w in (state.get("windows") or {}).values():
            if W._ts(w["open"]) < W._ts(start) or w["series"] not in series:
                continue
            if until and W._ts(w["open"]) >= W._ts(until):
                continue
            x = entry(w, strat)
            if x is None:
                continue
            if "skip" in x:
                skips[x["skip"]] = skips.get(x["skip"], 0) + 1
                continue
            by[w["series"]].append((w["day"], w["open"], x["won"], x["price"], x["roi"]))
        out[strat] = dict(all=F._cell([r for rs in by.values() for r in rs]),
                          series={s: F._cell(rs) for s, rs in by.items()}, skips=skips)
    return out


def ledger(state, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    slim = lambda c: None if not c else {k: c[k] for k in ("n", "hits", "hit_rate", "fair", "mean_roi", "z", "days")}
    return dict(version=VERSION, registered=REGISTERED, **{"from": FROM_V3}, from_v1=FROM, picked_on=PICKED_ON,
                cells={k: list(v) for k, v in CELLS.items()}, cells_v1={k: list(v) for k, v in CELLS_V1.items()},
                cells_v2={k: list(v) for k, v in CELLS_V2.items()}, updated=now.isoformat(timespec="seconds"),
                records={k: dict(all=slim(v["all"]), series={s: slim(c) for s, c in v["series"].items()}, skips=v["skips"])
                         for k, v in records(state).items()},
                removed_at=REMOVED_AT, removed={k: list(v) for k, v in REMOVED.items()},
                removed_records={k: dict(all=slim(v["all"]), series={s: slim(c) for s, c in v["series"].items()})
                                 for k, v in records(state, removed=True).items()},
                retired_at=RETIRED_AT,
                retired_records={k: dict(all=slim(v["all"]), series={s: slim(c) for s, c in v["series"].items()})
                                 for k, v in records(state, retired=True).items()})


def main():
    now = dt.datetime.now(dt.timezone.utc)
    start = dt.datetime.fromisoformat(FROM).astimezone(W.ET).date()
    days = {(start + dt.timedelta(days=i)).isoformat() for i in range((now.astimezone(W.ET).date() - start).days + 1)}
    blob = ledger(W.load(days=days), now)
    W._write(PATH, blob)
    print(VERSION, {k: (v["all"] or {}).get("n", 0) for k, v in blob["records"].items()})
    return 0


if __name__ == "__main__":
    sys.exit(main())
