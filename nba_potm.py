#!/usr/bin/env python3
"""NBA Player of the Month daily snapshot (Kalshi KXNBAPOTM): DATA ONLY, no lane, no rule, no page (Olu 2026-11-14, docs PR 459).

The research (docs/research/nba_potm_2026-11-14.md) found one open window and no history, so no rule can be tested. This builds the history for free:
once a day, both open events of the series (East and West, about 60 markets each) are read with ONE request per event, and the bid, ask, last price and
volume of every player are appended to data/nba_potm.json. When a window settles its winner is recorded. The research reopens once 3 or more windows
have settled (docs/research/nba_potm_prereg_2026-11-14.md: a build needs 6).

File shape (percent-free raw prices as dollars-as-cents integers or None):
  snapshots[YYYY-MM-DD (UTC)] = {ts, events: {EVENT_TICKER: [[market_ticker, player, yes_bid, yes_ask, last, volume, open_interest], ...]}}
  settled[EVENT_TICKER]       = {winner, winner_market, results: {market_ticker: "yes"|"no"}, close, recorded}
Idempotent: one snapshot a UTC day (the first of the day is kept, a rerun changes nothing) and a window is recorded once, so a missed run only leaves a gap
in the path, never a duplicate. Runs in nba-potm.yml (GitHub Actions); no VPS, no orders.
"""
import datetime as dt
import json
import os
import sys

import daily_track as D

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "data", "nba_potm.json")
SERIES = "KXNBAPOTM"
VERSION = "nba-potm-v1"


def cents(v):
    """A Kalshi dollar string as whole cents (None when absent)."""
    try:
        return None if v in (None, "") else round(float(v) * 100)
    except (TypeError, ValueError):
        return None


def num(v):
    try:
        return None if v in (None, "") else float(v)
    except (TypeError, ValueError):
        return None


def empty():
    return dict(version=VERSION, series=SERIES, snapshots={}, settled={}, updated=None)


def load(path=PATH):
    try:
        with open(path) as f:
            return dict(empty(), **json.load(f))
    except (OSError, ValueError):
        return empty()


def save(state, path=PATH):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, separators=(",", ":"), sort_keys=True)
    os.replace(tmp, path)


def rows(event):
    return [[m["ticker"], m.get("yes_sub_title") or "", cents(m.get("yes_bid_dollars")), cents(m.get("yes_ask_dollars")),
             cents(m.get("last_price_dollars")), num(m.get("volume_fp")), num(m.get("open_interest_fp"))] for m in event.get("markets") or []]


def events_of(status, get=D.get):
    d = get(f"events?series_ticker={SERIES}&status={status}&with_nested_markets=true&limit=50") or {}
    return d.get("events") or []


def snapshot(state, now=None, get=D.get):
    """Append today's snapshot of every open event; False when today's is already there or nothing is open."""
    now = now or dt.datetime.now(dt.timezone.utc)
    day = now.strftime("%Y-%m-%d")
    if day in state["snapshots"]:
        return False
    evs = {e["event_ticker"]: rows(e) for e in events_of("open", get) if e.get("markets")}
    if not evs:
        return False
    state["snapshots"][day] = dict(ts=now.isoformat(timespec="seconds"), events=evs)
    return True


def settle(state, now=None, get=D.get):
    """Record the winner of every settled window not recorded yet: the market whose result is yes. Returns the number added."""
    now = now or dt.datetime.now(dt.timezone.utc)
    added = 0
    for e in events_of("settled", get):
        et = e["event_ticker"]
        ms = e.get("markets") or []
        if et in state["settled"] or not ms or any(m.get("result") not in ("yes", "no") for m in ms):
            continue
        win = [m for m in ms if m["result"] == "yes"]
        state["settled"][et] = dict(winner=win[0].get("yes_sub_title") if len(win) == 1 else None, winner_market=win[0]["ticker"] if len(win) == 1 else None,
                                    winners=len(win), results={m["ticker"]: m["result"] for m in ms}, close=ms[0].get("close_time"),
                                    recorded=now.isoformat(timespec="seconds"))
        added += 1
    return added


def main():
    state = load()
    a = snapshot(state)
    b = settle(state)
    if a or b:
        state["updated"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        save(state)
    print(VERSION, "snapshot", a, "settled added", b, "days", len(state["snapshots"]), "windows settled", len(state["settled"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
