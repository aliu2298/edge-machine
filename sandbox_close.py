#!/usr/bin/env python3
"""sandbox_close.py — closing prices for the Sandbox, taken close to each deadline.

The tracker runs every six hours, so the last price it saw before a contest started could
be hours old, and closing-line value measured against it is noise. This job runs every 30
minutes, finds the open bets whose deadline (sandbox_track.close_deadline) falls in the
next CLOSE_WINDOW_MIN, and reads just those markets' current price on the bet's own venue.

It writes ONLY data/sandbox_closes.json. The ledger belongs to the tracker, which merges
this file on its next run (apply_closes) — so the two workflows never write the same file
and a rebase between their commits can never conflict. No Odds API credits are spent here.

Usage:  python3 sandbox_close.py
"""
import json, os, sys
from datetime import datetime, timedelta, timezone

import sandbox_sources as S
import sandbox_track as T

CLOSE_WINDOW_MIN = 35       # a 30-minute schedule, with slack for a late start
KEEP_DAYS = 10


def due(d, now, window_min=CLOSE_WINDOW_MIN):
    """Open bets whose deadline is still ahead but inside the window."""
    out = []
    for q in d["quotes"]:
        if q.get("status") != "open" or not q.get("bet") or not q.get("pick"):
            continue
        dl = T.close_deadline(q)
        if dl is not None and now < dl <= now + timedelta(minutes=window_min):
            out.append(q)
    return out


def run(d, closes, now=None, price=S.venue_price):
    """Snapshot every due bet into `closes`; prune old entries. Returns (taken, due)."""
    now = now or datetime.now(timezone.utc)
    stamp = now.replace(microsecond=0).isoformat()
    book = closes.setdefault("closes", {})
    todo = due(d, now)
    taken = 0
    for q in todo:
        p = price(q)
        if p is None:
            continue
        book[q["id"]] = {"price": p, "at": stamp,
                         "lead_min": round((T.close_deadline(q) - now).total_seconds() / 60, 1)}
        taken += 1
    cutoff = (now - timedelta(days=KEEP_DAYS)).isoformat()
    for qid in [k for k, v in book.items() if str(v.get("at")) < cutoff]:
        del book[qid]
    closes["updated"] = stamp
    return taken, len(todo)


def main():
    d = T.load()
    closes = T.load_closes()
    taken, n = run(d, closes)
    print(f"closing prices: {taken} of {n} due bets snapshotted, {len(closes['closes'])} on file")
    if taken:
        os.makedirs(os.path.dirname(T.CLOSES), exist_ok=True)
        with open(T.CLOSES, "w") as f:
            json.dump(closes, f, indent=1, sort_keys=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
