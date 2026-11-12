#!/usr/bin/env python3
"""Lead Swap favourite, version 2 (lsb-v2, registered 2026-11-12): Sandbox paper, no orders. Pre-registration: docs/prereg_leadswap_v2_2026-11-12.md.

THE RULE IS lsb-v1's, ON THREE MARKETS. Every hour the Lead Swap Board ranks every 15-minute series by lead swaps over the past two hours and
freezes the picks at about :04 (data to :00); that is unchanged (leadswap.py, the same frozen picks). A series in the BOTTOM 3 (the most stable)
gets v1's S3 favourite: at minute 10 buy the side over 50c at its ask, filled only on a print at or through it in the next minute, held to
settlement, taker fee. The change: only three markets are traded when picked, Bitcoin, WTI Crude Oil and NEAR; a pick on any other market is
skipped, no backfill from the next rank.

CONTROL: the same three markets when they are in the TOP 3 by swaps (v1's favourite control, on these markets only), so calm v swingy stays measured.

FROZEN: the three markets are fingerprinted (MARKETS_SHA256). A change is a NEW VERSION, never an edit: no further cuts, no exclusion rounds.

FRESH RECORD: windows opening at or after FROM; review at 30 bets, decide at 100. Nothing before FROM is counted, and nothing is backfilled.

WHY THESE THREE (said honestly): they were chosen IN-SAMPLE on lsb-v1's Nov 9-11 windows, after the fact: each had 20+ bets and beat its own
every-window S3 bet by 11-18 points, and did far worse when swingy. So the v1 numbers below are NOT evidence for v2 (the selection made them
look good); only the forward record from FROM is. v1's full record, with the 16 markets cut after the fact, was 414 bets, -0.7% after fees.
  Bitcoin  64 bets  +7.1% v every-window S3 -1.4% v swingy -10.5%
  WTI      32 bets  +10.1% v -4.2% v -14.6%
  NEAR     23 bets  +14.5% v -3.8% v -9.4%
"""
import datetime as dt
import json
import os
import sys

import leadswap as L
import swing15 as W

VERSION = "lsb-v2"
REGISTERED = "2026-11-12"
FROM = "2026-11-12T11:00:00+00:00"            # fresh record: windows opening at or after this (= sw15cuts.CUT3_AT, when lsb-v1 closes)
PATH = os.path.join(W.ROOT, "data", "leadswap_v2_ledger.json")
MARKETS = ("KXBTC15M", "KXNEAR15M", "KXWTI15M")
MARKETS_SHA256 = "66c474f362a4f908deced4de88cde689dbc8e6b50a46cad82eed97ca6aaeeb4e"                     # sha256 of fingerprint(), set at registration
REVIEW_AT, DECIDE_AT = 30, 100
TRADES = (("leadswap_v2", "bottom"), ("leadswap_v2_ctrl", "top"))
LABELS = {"leadswap_v2": "Lead Swap favourite v2 · Bitcoin, WTI, NEAR", "leadswap_v2_ctrl": "Control · the same markets when swappy"}
# The in-sample numbers the three markets were chosen on (lsb-v1, Nov 9-11): market -> (bets, rule, every-window S3, swingy). Said on the page.
IN_SAMPLE = {"KXBTC15M": (64, 7.1, -1.4, -10.5), "KXWTI15M": (32, 10.1, -4.2, -14.6), "KXNEAR15M": (23, 14.5, -3.8, -9.4)}


def fingerprint():
    import allowgate
    return allowgate.fingerprint(dict(markets=list(MARKETS), from_=FROM, version=VERSION))


def routing(rows, picks):
    """{trade: cell}: each frozen hour's picks applied to the windows opening in that hour at or after FROM, on the three markets only.
    The cell is leadswap.routing()'s (n, hits, hit_rate, fair, mean_roi, z, clusters, before_freeze, series)."""
    found = {k: [] for k, _side in TRADES}
    for s, _g, o, _c, _m, w in rows:
        if o < W._ts(FROM) or s not in MARKETS:
            continue
        hk = dt.datetime.fromtimestamp(o - o % 3600, dt.timezone.utc).isoformat()
        p = picks.get(hk)
        if not p:
            continue
        for trade, side in TRADES:
            if s in p[side]:
                t = L._trade(w, "leadswap_fav")
                if t:
                    found[trade].append((f"{o}|{L.block(w)}", o, t[0], t[1], t[2], s, L._before_freeze(w, "leadswap_fav", p)))
    out = {}
    for trade, rs in found.items():
        if not rs:
            out[trade] = None
            continue
        n = len(rs)
        out[trade] = dict(n=n, hits=int(sum(r[2] for r in rs)), hit_rate=sum(r[2] for r in rs) / n, fair=sum(r[3] for r in rs) / n,
                          mean_roi=sum(r[4] for r in rs) / n, z=W.cluster_z([(r[0], r[2], r[3]) for r in rs]),
                          clusters=len({r[0] for r in rs}), before_freeze=sum(bool(r[6]) for r in rs), series={})
        for r in rs:
            c = out[trade]["series"].setdefault(r[5], [0, 0, 0.0])
            c[0] += 1
            c[1] += int(r[2])
            c[2] += r[4]
    return out


def empty():
    return dict(version=VERSION, registered=REGISTERED, **{"from": FROM}, markets=list(MARKETS), routing=None, updated=None)


def update(state, led_v1, now=None):
    """Recompute the record from the v1 ledger's frozen picks (the same picks lsb-v1 uses) and the graded windows."""
    now = now or dt.datetime.now(dt.timezone.utc)
    led = empty()
    led["routing"] = routing(L.table(state), (led_v1 or {}).get("picks") or {})
    led.update(markets=list(MARKETS), fingerprint=fingerprint(), review_at=REVIEW_AT, decide_at=DECIDE_AT,
               updated=now.isoformat(timespec="seconds"))
    return led


def load(path=PATH):
    try:
        with open(path) as f:
            return dict(empty(), **json.load(f))
    except (OSError, ValueError):
        return empty()


def main():
    if fingerprint() != MARKETS_SHA256:
        sys.exit("the lsb-v2 market list changed after registration: a change is a new version, never an edit")
    now = dt.datetime.now(dt.timezone.utc)
    start = dt.datetime.fromisoformat(FROM).astimezone(W.ET).date()
    days = {(start + dt.timedelta(days=i)).isoformat() for i in range(max(0, (now.astimezone(W.ET).date() - start).days) + 2)}
    led = update(W.load(days=days), L.load(), now)
    W._write(PATH, led)
    print(VERSION, {k: (v or {}).get("n", 0) for k, v in (led["routing"] or {}).items()})
    return 0


if __name__ == "__main__":
    sys.exit(main())
