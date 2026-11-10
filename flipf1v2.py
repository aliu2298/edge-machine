#!/usr/bin/env python3
"""Rule 3 v2 · Every Positive Setting (flip-f1v2, registered 2026-11-10): Sandbox paper, no orders. Replaces The Flip
Side v3 F1.

The base trade is F1 exactly (flipside_v2.flip(..., "flipside_v2_f1")): when v1's S1 25c trigger fires (the cheap side
prints at 25c in the window's first 5 minutes), buy the OTHER side at its ask at the end of the trigger minute; held to
settlement; taker fee. A window is bet ONLY when all four of its settings are in its market's frozen allow-list
(allowgate.py):

  price           the flip's entry price: <73 (< 73c), 73-76 (73c to < 76.5c), 77+ (76.5c and up)
  trigger_minute  the trigger's minute row: 0-1, 2-3, 4
  lead_changes    YES-mid crossings of 50c over the minute rows 0 .. the trigger minute: 0 / 1 / 2+
  time_ct         the window's open hour in Central: 07-11, 12-16, 17-22; any other hour is never bet

An empty list means that market never bets (XRP: no positive time of day; WTI: no positive lead-change setting). The
allow-list was chosen from each market's positive cells on Nov 9 from 7:15 AM CT (in-sample: 122/133, +20.0%, never
counted). It is the pre-registration: frozen, fingerprinted (ALLOW_SHA256), stored in the ledger. A filter over the v1
hour shards; a fresh record from FROM; written to data/flipf1v2_ledger.json by swing15.yml.
"""
import datetime as dt
import os
import sys

import allowgate as G
import flipside_v2 as F
import swing15 as W

VERSION = "flip-f1v2"
REGISTERED = "2026-11-10"
FROM = "2026-11-10T05:15:00+00:00"           # fresh record: the first window after the merge (= F1's cut)
PATH = os.path.join(W.ROOT, "data", "flipf1v2_ledger.json")
LABEL = "Rule 3 v2 · Every Positive Setting"
REVIEW_AT, DECIDE_AT = 30, 100
STRAT = "flipside_v2_f1"
# The frozen pre-registration (flip-f1v2, 2026-11-10). Do not edit: a change is a new version.
ALLOW = {
    "KXGOLD15M": {"price": ["<73", "73-76", "77+"], "trigger_minute": ["0-1", "2-3"], "lead_changes": ["0", "1", "2+"],
                  "time_ct": ["07-11", "12-16", "17-22"]},
    "KXETH15M": {"price": ["<73", "73-76", "77+"], "trigger_minute": ["0-1", "2-3", "4"], "lead_changes": ["0", "1", "2+"],
                 "time_ct": ["07-11", "12-16", "17-22"]},
    "KXPLATINUM15M": {"price": ["<73", "73-76", "77+"], "trigger_minute": ["0-1", "2-3", "4"],
                      "lead_changes": ["0", "1", "2+"], "time_ct": ["12-16", "17-22"]},
    "KXBTC15M": {"price": ["73-76", "77+"], "trigger_minute": ["0-1", "2-3", "4"], "lead_changes": ["0", "1"],
                 "time_ct": ["07-11", "17-22"]},
    "KXNEAR15M": {"price": ["<73"], "trigger_minute": ["0-1", "2-3"], "lead_changes": ["0", "2+"], "time_ct": ["07-11", "17-22"]},
    "KXHYPE15M": {"price": ["<73", "73-76"], "trigger_minute": ["0-1", "4"], "lead_changes": ["0"], "time_ct": ["07-11"]},
    "KXXRP15M": {"price": ["<73", "73-76"], "trigger_minute": ["0-1"], "lead_changes": ["0"], "time_ct": []},
    "KXWTI15M": {"price": ["73-76"], "trigger_minute": ["4"], "lead_changes": [], "time_ct": ["07-11"]},
}
ALLOW_SHA256 = "01203a5be27a049b1f4ce322d0422bdf3c7748621dbf65caef10e4e690e4f90d"   # sha256 of G.fingerprint(ALLOW), set at registration
MARKETS = tuple(ALLOW)
IN_SAMPLE = "Nov 9 in-sample, these settings would have gone 122/133, +20% — not counted"
PRICE_BANDS = ("<73", "73-76", "77+")
MINUTE_BUCKETS = ("0-1", "2-3", "4")


def fingerprint(allow=None):
    return G.fingerprint(allow or ALLOW)


def price_band(p):
    return "<73" if p < 0.73 else "73-76" if p < 0.765 else "77+"


def minute_bucket(m):
    return "0-1" if m <= 1 else "2-3" if m <= 3 else "4" if m == 4 else None


def flip_entry(w):
    """F1's entry for the window, or None (no trigger, or a skip)."""
    f = F.flip(w, STRAT)
    return None if not f or "skip" in f else f


def settings(w):
    """{"price", "trigger_minute", "lead_changes", "time_ct"} of a window where F1 entered, or None."""
    f = flip_entry(w)
    if not f:
        return None
    m = ((w.get("s1") or {}).get("0.25") or {}).get("trigger", {}).get("minute")
    if m is None:
        return None
    return dict(price=price_band(f["price"]), trigger_minute=minute_bucket(m), lead_changes=G.lead_changes(w, m),
                time_ct=G.time_bucket(w["open"]))


def allowed(w):
    return G.allowed(ALLOW, w.get("series"), settings(w))


def in_record(w, start=None):
    return W._ts(w["open"]) >= W._ts(start or FROM) and w.get("series") in MARKETS


def records(state, start=None):
    """{"lane": {"all", "series"}, "every": {"all", "series"}}: the filtered lane and old F1 on the same 8 markets."""
    out = {}
    for key, gate in (("lane", allowed), ("every", lambda w: True)):
        by = {m: [] for m in MARKETS}
        for w in (state.get("windows") or {}).values():
            if not in_record(w, start):
                continue
            f = flip_entry(w)
            if f and gate(w):
                by[w["series"]].append((w["day"], w["open"], f["won"], f["price"], f["roi"]))
        out[key] = dict(all=F._cell([r for rs in by.values() for r in rs]), series={m: F._cell(rs) for m, rs in by.items()})
    return out


def entries(state, start=None):
    rows = []
    for w in (state.get("windows") or {}).values():
        if in_record(w, start) and allowed(w):
            f = flip_entry(w)
            rows.append(dict(at=w["open"], market=w["series"], settings=settings(w), side=f["side"], price=f["price"],
                             won=f["won"], roi=f["roi"]))
    return sorted(rows, key=lambda r: r["at"], reverse=True)


def ledger(state, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    slim = lambda c: None if not c else {k: c[k] for k in ("n", "hits", "hit_rate", "fair", "mean_roi", "z", "days")}
    rec = records(state)
    return dict(version=VERSION, registered=REGISTERED, **{"from": FROM}, allow=ALLOW, allow_sha256=fingerprint(),
                never=G.never(ALLOW), in_sample=IN_SAMPLE, updated=now.isoformat(timespec="seconds"),
                records={k: dict(all=slim(v["all"]), series={m: slim(c) for m, c in v["series"].items()}) for k, v in rec.items()},
                entries=entries(state)[:100])


def main():
    if fingerprint() != ALLOW_SHA256:
        sys.exit("the flip-f1v2 allow-list changed after registration: add a NEW version, never edit this one")
    now = dt.datetime.now(dt.timezone.utc)
    start = dt.datetime.fromisoformat(FROM).astimezone(W.ET).date()
    days = {(start + dt.timedelta(days=i)).isoformat() for i in range(max(0, (now.astimezone(W.ET).date() - start).days) + 1)}
    blob = ledger(W.load(days=days), now)
    W._write(PATH, blob)
    print(VERSION, {k: (v["all"] or {}).get("n", 0) for k, v in blob["records"].items()})
    return 0


if __name__ == "__main__":
    sys.exit(main())
