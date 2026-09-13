#!/usr/bin/env python3
"""sandbox_close.py — closing prices for the Sandbox, taken close to each deadline.

The tracker runs every six hours, so the last price it saw before a contest started could
be hours old, and closing-line value measured against it is noise. This job runs every 30
minutes, finds the open bets whose deadline (sandbox_track.close_deadline) falls in the
next CLOSE_WINDOW_MIN, and reads just those markets' current price on the bet's own venue.

It writes ONLY data/sandbox_closes/<writer>.json — one file per workflow that runs it (the
close job, the hourly watchdog, the board refresh), because GitHub honours none of their
schedules reliably and more chances to snapshot means more real closes. The ledger belongs
to the tracker, which merges every writer's file on its next run (apply_closes), so no two
workflows ever commit the same file. No Odds API credits are spent here.

Usage:  python3 sandbox_close.py [--writer close|watchdog|boards]
"""
import json, os, sys
from datetime import datetime, timedelta, timezone

import sandbox_sources as S
import sandbox_track as T

CLOSE_WINDOW_MIN = 60       # = CLOSE_MAX_LEAD_MIN: every snapshot taken still counts toward CLV
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


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    writer = argv[argv.index("--writer") + 1] if "--writer" in argv else "close"
    if not writer.isidentifier():
        raise SystemExit(f"bad writer name: {writer!r}")
    path = os.path.join(T.CLOSES_DIR, f"{writer}.json")
    d = T.load()
    closes = T.load_closes(path)
    before = len(closes["closes"])
    taken, n = run(d, closes)
    print(f"closing prices [{writer}]: {taken} of {n} due bets snapshotted, "
          f"{len(closes['closes'])} on file")
    # Written only when something changed, so an hourly run with nothing due makes no commit.
    if taken or len(closes["closes"]) != before or not os.path.exists(path):
        os.makedirs(T.CLOSES_DIR, exist_ok=True)
        with open(path, "w") as f:
            json.dump(closes, f, indent=1, sort_keys=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
