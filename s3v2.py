#!/usr/bin/env python3
"""Rule 2 v2 · Every Positive Setting (sw15-s3v2, registered 2026-11-10): Sandbox paper, no orders. Replaces Swing v3 S3.

The base trade is S3 exactly (sw15-v1's S3): at minute 10 of a 15-minute window, buy the side above 50c (by the mid) at
its ask, filled only on a print at or through it in the next minute; held to settlement; taker fee on entry. A window is
bet ONLY when all three of its settings are in its market's frozen allow-list:

  price         the entry price of the side bought: 50-80 (< 80c), 80-90, 90-95, 95+ (95c and up)
  lead_changes  how often the YES mid crossed 50c in the minute quotes before the entry (the closes of minutes 1-10),
                0 / 1 / 2+ (a mid of exactly 50c is no side and is skipped)
  time_ct       the window's open hour in Central: 07-11, 12-16, 17-22; any other hour is never bet

The allow-list was chosen from each market's positive cells on Nov 9 (in-sample: 125/131, +14.1%, never counted). It is
the pre-registration: frozen, fingerprinted (ALLOW_SHA256) and stored in the ledger. A filter over the v1 hour shards
(data/swing15/<ET day>/<HH>.json); a fresh record from FROM; written to data/s3v2_ledger.json by swing15.yml.
"""
import datetime as dt
import os
import sys

import allowgate as G
import swing15 as W

VERSION = "sw15-s3v2"
REGISTERED = "2026-11-10"
FROM = "2026-11-10T05:00:00+00:00"           # fresh record: the first window after the merge (= Swing v3 S3's cut)
PATH = os.path.join(W.ROOT, "data", "s3v2_ledger.json")
LABEL = "Rule 2 v2 · Every Positive Setting"
REVIEW_AT, DECIDE_AT = 30, 100
# The frozen pre-registration (sw15-s3v2, 2026-11-10). Do not edit: a change is a new version.
ALLOW = {
    "KX2YRRATE15M": {"price": ["50-80", "80-90", "90-95", "95+"], "lead_changes": ["0", "1", "2+"], "time_ct": ["07-11", "12-16"]},
    "KXBTC15M": {"price": ["50-80", "95+"], "lead_changes": ["0", "1", "2+"], "time_ct": ["07-11", "12-16", "17-22"]},
    "KXGOLD15M": {"price": ["50-80", "80-90", "90-95"], "lead_changes": ["0", "1", "2+"], "time_ct": ["07-11", "17-22"]},
    "KXETH15M": {"price": ["50-80", "95+"], "lead_changes": ["0", "1"], "time_ct": ["07-11", "17-22"]},
    "KXBNB15M": {"price": ["80-90", "95+"], "lead_changes": ["0"], "time_ct": ["07-11", "17-22"]},
    "KXUSDJPY15M": {"price": ["95+"], "lead_changes": ["0"], "time_ct": ["07-11"]},
}
ALLOW_SHA256 = "483f343525cdac937e9d9d1de6e5301baeea052c1c87561936b67850c4780d15"   # sha256 of fingerprint(ALLOW)
MARKETS = tuple(ALLOW)
IN_SAMPLE = "Nov 9 in-sample, these settings would have gone 125/131, +14.1% — not counted"
PRICE_BANDS = ("50-80", "80-90", "90-95", "95+")
LEAD_BUCKETS, TIME_BUCKETS = G.LEAD_BUCKETS, G.TIME_BUCKETS


def fingerprint(allow=None):
    return G.fingerprint(allow or ALLOW)


def price_band(p):
    return "50-80" if p < 0.80 else "80-90" if p < 0.90 else "90-95" if p < 0.95 else "95+"


time_bucket = G.time_bucket


def lead_changes(w, upto=9):
    """Crossings of 50c by the YES mid over the minute rows m = 0..upto (closes of minutes 1-10), bucketed."""
    return G.lead_changes(w, upto)


def settings(w):
    """{"price", "lead_changes", "time_ct"} of a window with an S3 quote, or None."""
    s3 = w.get("s3") or {}
    if s3.get("price") is None:
        return None
    return dict(price=price_band(s3["price"]), lead_changes=lead_changes(w), time_ct=time_bucket(w["open"]))


def allowed(w):
    """True when the window's market is listed and all three settings are in its allow-list; an hour outside 07-22 CT
    (time_ct None) is never allowed."""
    return G.allowed(ALLOW, w.get("series"), settings(w))


def in_record(w, start=None):
    return W._ts(w["open"]) >= W._ts(start or FROM) and w.get("series") in MARKETS


def records(state, start=None):
    """{"lane": {"all", "series"}, "every": {"all", "series"}}: the filtered lane and old S3 on the same 6 markets."""
    out = {}
    for key, flt in (("lane", lambda w: in_record(w, start) and allowed(w)), ("every", lambda w: in_record(w, start))):
        out[key] = dict(all=W.cells(state, flt).get(("swing15_s3",)),
                        series={m: W.cells(state, lambda w, m=m, f=flt: f(w) and w["series"] == m).get(("swing15_s3",))
                                for m in MARKETS})
    return out


def entries(state, start=None):
    """The lane's graded entries, newest first: [{"at", "market", "settings", "price", "won", "roi"}]."""
    rows = []
    for w in (state.get("windows") or {}).values():
        if not (in_record(w, start) and allowed(w)):
            continue
        s3 = w.get("s3") or {}
        if s3.get("status") != "filled":
            continue
        rows.append(dict(at=w["open"], market=w["series"], settings=settings(w), price=s3["price"], won=s3["won"],
                         roi=s3.get("roi")))
    return sorted(rows, key=lambda r: r["at"], reverse=True)


def ledger(state, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    slim = lambda c: None if not c else {k: c[k] for k in ("n", "hits", "hit_rate", "fair", "mean_roi", "z", "days")}
    rec = records(state)
    return dict(version=VERSION, registered=REGISTERED, **{"from": FROM}, allow=ALLOW, allow_sha256=fingerprint(),
                in_sample=IN_SAMPLE, updated=now.isoformat(timespec="seconds"),
                records={k: dict(all=slim(v["all"]), series={m: slim(c) for m, c in v["series"].items()}) for k, v in rec.items()},
                entries=entries(state)[:100])


def main():
    if fingerprint() != ALLOW_SHA256:
        sys.exit("the sw15-s3v2 allow-list changed after registration: add a NEW version, never edit this one")
    now = dt.datetime.now(dt.timezone.utc)
    start = dt.datetime.fromisoformat(FROM).astimezone(W.ET).date()
    days = {(start + dt.timedelta(days=i)).isoformat() for i in range(max(0, (now.astimezone(W.ET).date() - start).days) + 1)}
    blob = ledger(W.load(days=days), now)
    W._write(PATH, blob)
    print(VERSION, {k: (v["all"] or {}).get("n", 0) for k, v in blob["records"].items()})
    return 0


if __name__ == "__main__":
    sys.exit(main())
