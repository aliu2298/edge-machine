#!/usr/bin/env python3
"""Steady Favourites (sw15-sf1, registered 2026-11-09): Sandbox paper, no orders. Replaces the retired S1 Swing.

Four fixed markets where the favourite won above its price in both halves of sw15-v1's first day and repeated in v3,
the Lead Swap Board or The Flip Side: Bitcoin, USD/JPY, Gold, 2-Year Treasury Yield. The frozen list is the
pre-registration: no market is added or dropped later.

  Rule A (steadyfav_a) Favourite at start: sw15-v1's S2 exactly. At minute 2, buy the side above 50c (by the mid) at its
         ask, filled only on a print at or through it in the next minute; held to settlement; taker fee on entry.
  Rule B (steadyfav_b) Favourite at 5 minutes left: sw15-v1's S3, the same at minute 10.

Controls (steadyfav_a_ctrl, steadyfav_b_ctrl): the same two rules on every other 15-minute series, pooled into one row
each, so the record shows whether "steady" beats everything else.

A filter over the v1 hour shards (data/swing15/<ET day>/<HH>.json), not a second poller; a FRESH record from FROM (the
first window after the merge): v1/v3 history is not carried over. Written to data/steadyfav_ledger.json by the hourly
run (swing15.yml).
"""
import datetime as dt
import os
import sys

import swing15 as W

VERSION = "sw15-sf1"
REGISTERED = "2026-11-09"
FROM = "2026-11-10T00:00:00+00:00"           # fresh record: windows opening at or after this (after the merge)
PATH = os.path.join(W.ROOT, "data", "steadyfav_ledger.json")
# The frozen pre-registration (sw15-sf1, 2026-11-09). Do not edit.
MARKETS = ("KXBTC15M", "KXUSDJPY15M", "KXGOLD15M", "KX2YRRATE15M")
EXCLUDE = ("KXCRYPTOLEAD15M",)
# 2026-11-10 (Olu): USD/JPY dropped from A and B at REMOVED_AT; its final records are records(..., removed=True). The
# surviving markets' records continue. The controls keep excluding all four frozen MARKETS (USD/JPY never joins the pool).
REMOVED_AT = "2026-11-10T05:30:00+00:00"
REMOVED = ("KXUSDJPY15M",)
LIVE = tuple(m for m in MARKETS if m not in REMOVED)               # not a price series (as the Lead Swap Board)
RULES = {"steadyfav_a": ("swing15_s2",), "steadyfav_b": ("swing15_s3",)}
CONTROLS = {"steadyfav_a_ctrl": "steadyfav_a", "steadyfav_b_ctrl": "steadyfav_b"}
LABELS = {"steadyfav_a": "A Favourite at start", "steadyfav_b": "B Favourite at 5 minutes left",
          "steadyfav_a_ctrl": "A control · the other markets", "steadyfav_b_ctrl": "B control · the other markets"}


def in_sf(w, until=None):
    t = W._ts(w["open"])
    return t >= W._ts(FROM) and (not until or t < W._ts(until))


def records(state, earlier=False, removed=False):
    """{rule: {"all": cell, "series": {market: cell or None}}, control: {"all": cell, "markets": n}}; cells are
    swing15.cells()' records. earlier=True: the same four markets on v1 BEFORE FROM (shown, never counted)."""
    if earlier:
        flt, mk = (lambda w: W._ts(w["open"]) < W._ts(FROM)), MARKETS
    elif removed:
        flt, mk = (lambda w: in_sf(w, REMOVED_AT)), REMOVED
    else:
        flt, mk = in_sf, LIVE
    out = {}
    for rule, key in RULES.items():
        out[rule] = dict(all=W.cells(state, lambda w: flt(w) and w["series"] in mk).get(key),
                         series={s: W.cells(state, lambda w, s=s: flt(w) and w["series"] == s).get(key) for s in mk})
    if earlier or removed:
        return out
    others = lambda w: flt(w) and w["series"] not in MARKETS and w["series"] not in EXCLUDE
    n_other = len({w["series"] for w in (state.get("windows") or {}).values()
                   if w["series"] not in MARKETS and w["series"] not in EXCLUDE})
    for ctrl, rule in CONTROLS.items():
        out[ctrl] = dict(all=W.cells(state, others).get(RULES[rule]), markets=n_other)
    return out


def ledger(state, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    slim = lambda c: None if not c else {k: c[k] for k in ("n", "hits", "hit_rate", "fair", "mean_roi", "z", "days")}
    rec = records(state)
    gone = records(state, removed=True)
    return dict(version=VERSION, registered=REGISTERED, **{"from": FROM}, markets=list(LIVE), registered_markets=list(MARKETS),
                removed=list(REMOVED), removed_at=REMOVED_AT,
                removed_records={k: dict(all=slim(v["all"]), series={s: slim(c) for s, c in v["series"].items()})
                                 for k, v in gone.items()},
                updated=now.isoformat(timespec="seconds"),
                records={k: dict(all=slim(v["all"]), **({"series": {s: slim(c) for s, c in v["series"].items()}}
                                                        if "series" in v else {"markets": v["markets"]}))
                         for k, v in rec.items()})


def main():
    now = dt.datetime.now(dt.timezone.utc)
    start = dt.datetime.fromisoformat(FROM).astimezone(W.ET).date()
    days = {(start + dt.timedelta(days=i)).isoformat() for i in range(max(0, (now.astimezone(W.ET).date() - start).days) + 1)}
    blob = ledger(W.load(days=days), now)
    W._write(PATH, blob)
    print(VERSION, {k: (v["all"] or {}).get("n", 0) for k, v in blob["records"].items()})
    return 0


if __name__ == "__main__":
    sys.exit(main())
