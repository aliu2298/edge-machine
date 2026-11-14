#!/usr/bin/env python3
"""Mentions dump bid: a Sandbox PAPER watch (Olu 2026-11-14, "send the paper lane to production"). No orders, no VPS, no live loop.

The lead is the mentions bounce study (docs/mentions_bounce_study_2026-11-14.md, docs PR 464): across 63 series and 623 settled events a bid 20c under
the last trade, sold back when the price is back within 5c, returned +16.6% then +12.6% after fees (it passed its written test); 15c under was the weakest
pass (+7.8% then +3.9%). It works on NO as well as YES and in every type of event. Here it is run forward on events not yet played.

THE RULE (the study's build spec; nl_dump.replay is the engine, the same one every dump / before-start watch uses; nothing here is tuned):
  * Every Kalshi mention event (every series Kalshi lists in its Mentions category), both sides of every word. Every whole minute T a bid rests DEPTH under R,
    the last trade on the bid's side. No bid if nothing traded in the 10 minutes before T, if R is over 95c, or if the bid would sit under 5c. Live from T + 25 s
    (the headline column; 2 s is the comparison).
  * BIDS STOP when the first word of the event is confirmed: the first trade at 97c or more in any word that last traded under 90c. The listed start is not
    used: about one event in three had a word confirmed before it (taped interviews, a start listed late), so a rule tied to it would bid into a finished
    market. A bid whose minute T is before that trade stands; none after.
  * FILL: honest-v1, only a trade strictly through the bid; size what $1 buys, or what printed through when that is less.
  * SELL: resting at R - 5c (5c under the price before the drop: +15c over the bid on the 20c rows, +10c on the 15c row), up 60 s after the fill, filled only
    by a trade strictly through it (a taker sale with the taker fee if the price is already there). What is not sold rides to the result. One position a
    side of a word at a time.
  * FEES: a resting fill pays nothing unless the series lists a maker fee (fee_type quadratic_with_maker_fees: then every resting fill, buy and sell, pays
    0.0175 x p x (1 - p)); a taker sale pays 0.07 x p x (1 - p).

FOUR ROWS, judged apart, all on the same trades:
    M20   20c under, all prices, sold back            (the tested rule: the headline)
    M20L  20c under, bids of 50c or less, sold back   (a lead seen AFTER the test: a second row, never the headline)
    M15   15c under, sold back                        (the weakest pass)
    H20   20c under, the first fill of each side of a word held to the result (control)

HOW IT RUNS: each event is replayed once, after every one of its words has settled, from Kalshi's public trade prints (a sweep of the Mentions series for
markets settled since the last sweep, one pull a market). The rule is fixed, so this is a forward test: only bids from FROM_TS count. A late run backfills
(the ledger holds every event read; a sweep re-reads from a safe margin). Own ledger data/mentions_dump_ledger.json, read in mentions-dump.yml.
Read at 100, 300 and 600 fills in the headline column, scored by event (docs/prereg_mentions_dump_2026-11-14.md).
"""
import dataclasses
import datetime as dt
import json
import os
import re
import sys

import daily_track as D
import fillsim as F
import fillsim_tape as TP
import nl_dump as N

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "data", "mentions_dump_ledger.json")
VERSION = "mentions-dump-v1"
REGISTERED = "2026-11-14"
FROM_TS = int(dt.datetime(2026, 11, 14, 19, 0, tzinfo=dt.timezone.utc).timestamp())   # only bids from here on count
FROM_DAY = "2026-11-14"
ROW = {
    "M20": dict(depth=0.20, ex="A"),
    "M20L": dict(depth=0.20, ex="A", max_l=0.50),
    "M15": dict(depth=0.15, ex="A"),
    "H20": dict(depth=0.20, ex="C"),
}
LABEL = {
    "M20": "20c under, all prices, sold back",
    "M20L": "20c under, bids of 50c or less, sold back",
    "M15": "15c under, sold back",
    "H20": "20c under, first fill of each side held to the result",
}
HEAD_ROW = "M20"
HEADLINE, COMPARE = N.HEADLINE, N.COMPARE
READ_AT = (100, 300, 600)
KEEP_T = 2.0
STRIKE_HI, STRIKE_LO = 0.97, 0.90
RULES = {False: F.HONEST, True: dataclasses.replace(F.HONEST, maker_rate=0.0175)}
MAX_EVENTS_PER_RUN = 14
SWEEP_BACK_S = 6 * 3600        # a sweep re-reads markets settled this long before the last one (a late market is never missed)
PENDING_DAYS = 4               # an event whose words are not all settled is retried this long


def now_ts():
    return int(dt.datetime.now(dt.timezone.utc).timestamp())


# ---------------------------------------------------------------- the clock: the first word confirmed
def first_strike(tapes):
    """Unix seconds of the first trade at 97c or more in a word that last traded under 90c, over every word of the event, or None.
    tapes = {market ticker: [(ts, yes price, contracts, ...)]}. The listed start is not used."""
    best = None
    for prints in tapes.values():
        prev = None
        for p in prints:
            if prev is not None and prev < STRIKE_LO - 1e-9 and p[1] >= STRIKE_HI - 1e-9:
                best = p[0] if best is None else min(best, p[0])
                break
            prev = p[1]
    return None if best is None else int(best)


def replay(prints, result, maker, confirm):
    return N.replay(prints, result, rows=ROW, rules=RULES[bool(maker)], since=FROM_TS, until=confirm)


# ---------------------------------------------------------------- the ledger
def empty():
    return dict(version=VERSION, registered=REGISTERED, since=FROM_DAY, markets={}, events={}, pending={}, swept=None, updated=None, errors=[])


def load(path=PATH):
    try:
        with open(path) as f:
            return dict(empty(), **json.load(f))
    except (OSError, ValueError):
        return empty()


def save(state, path=PATH):
    N.save(state, path)


def mention_series(get=D.get):
    """{series ticker: maker?} for Kalshi's Mentions category."""
    d = get("series?category=Mentions") or {}
    return {s["ticker"]: "maker" in (s.get("fee_type") or "") for s in d.get("series") or [] if s.get("ticker")}


def sweep(state, series, since, get=D.get):
    """{event ticker: series} of every event with a market that settled since `since` (unix seconds). One listing a series, paged."""
    out = {}
    for s in series:
        cur = None
        for _ in range(6):
            d = get(f"markets?series_ticker={s}&status=settled&min_close_ts={int(since)}&limit=1000" + (f"&cursor={cur}" if cur else "")) or {}
            for m in d.get("markets") or []:
                if m.get("event_ticker"):
                    out[m["event_ticker"]] = s
            cur = d.get("cursor")
            if not cur:
                break
    return out


def event_day(markets):
    """The UTC day the event closed: the latest close time of its words."""
    ts = [D.instant(m.get("close_time")) for m in markets if m.get("close_time")]
    ts = [t for t in ts if t]
    return max(ts).strftime("%Y-%m-%d") if ts else None


def match_of(ev):
    return re.sub(r"\s+", " ", str(ev.get("title") or ev.get("event_ticker") or "")).strip()


def process(state, et, series, maker, tape=TP.settled_tape, get=D.get):
    """Read one event once: None if a word is not settled yet (retried), else True. Raises on a failed pull (retried next run)."""
    d = get(f"events/{et}?with_nested_markets=true") or {}
    ev = d.get("event") or {}
    mk = d.get("markets") or ev.get("markets") or []
    if not mk or any(m.get("result") not in ("yes", "no") for m in mk):
        return None
    day = event_day(mk)
    if not day or day < FROM_DAY:
        state["events"][et] = dict(day=day, skipped="before the start of the record")
        return True
    tapes = {m["ticker"]: tape(m["ticker"]) for m in mk}
    confirm = first_strike(tapes)
    name = match_of(ev)
    for m in mk:
        prints = tapes[m["ticker"]]
        state["markets"][m["ticker"]] = dict(
            event=et, day=day, series=series, match=name, leg=m.get("yes_sub_title") or m.get("subtitle") or "", result=m["result"], prints=len(prints),
            bets=replay(prints, m["result"], maker, confirm) if prints else {N.cell_key(k, x): [] for k in ROW for x in N.DELAYS})
    state["events"][et] = dict(day=day, series=series, words=len(mk), confirm=confirm, maker=bool(maker))
    return True


def run(state, now=None, get=D.get, tape=TP.settled_tape, series=None):
    """Sweep for markets settled since the last sweep, then read every event not in the ledger whose words have all settled, oldest first."""
    now = now or now_ts()
    series = series if series is not None else mention_series(get)
    since = max(FROM_TS, (state.get("swept") or FROM_TS) - SWEEP_BACK_S)
    found = sweep(state, series, since, get)
    for et, s in found.items():
        if et not in state["events"]:
            state["pending"].setdefault(et, dict(series=s, first=now))
    todo = sorted(state["pending"].items(), key=lambda kv: (kv[1]["first"], kv[0]))
    done, errs = 0, []
    for et, v in todo[:MAX_EVENTS_PER_RUN]:
        if et in state["events"]:
            state["pending"].pop(et, None)
            continue
        try:
            r = process(state, et, v["series"], series.get(v["series"], False), tape, get)
        except Exception as exc:                                    # noqa: BLE001  (one event never stops the rest; it is read next run)
            errs.append(f"{et}: {str(exc)[:60]}")
            continue
        if r:
            state["pending"].pop(et, None)
            done += 1
    for et in [e for e, v in state["pending"].items() if now - v["first"] > PENDING_DAYS * 86400]:
        state["pending"].pop(et, None)                              # never all settled: dropped, not graded
    state["swept"] = now
    state["updated"] = dt.datetime.fromtimestamp(now, dt.timezone.utc).isoformat(timespec="seconds")
    state["errors"] = errs[:10]
    return done


# ---------------------------------------------------------------- the record
def bets(state, row, delay):
    """[(roi, event, bet)] for one cell, every event read, oldest first."""
    out = []
    for tk, v in sorted(state["markets"].items(), key=lambda kv: (kv[1]["day"], kv[0])):
        for b in v["bets"].get(N.cell_key(row, delay)) or []:
            out.append((b["roi"], v["event"], dict(b, ticker=tk, day=v["day"], match=v["match"], leg=v.get("leg"), series=v["series"])))
    return out


def read_text(row, st, n_events=0):
    """Pre-registered: read at 100, 300 and 600 fills, scored by event. Main row: held if positive with a score of 2 or more at 300; retired if negative at 300.
    M20L is judged the same way and replaces the main row only if it is ahead at 600; M15 and H20 are comparisons."""
    n = st["n"]
    if n < READ_AT[0]:
        return f"too early ({n} of {READ_AT[0]} fills; read at 100, 300 and 600)"
    roi, t = st["roi"] or 0, st["t"] or 0
    if n < READ_AT[1]:
        return f"read at 100: {'positive' if roi > 0 else 'not positive'}, no decision before 300 fills"
    at = READ_AT[2] if n >= READ_AT[2] else READ_AT[1]
    if roi > 0 and t >= KEEP_T:
        verdict = "held (positive, score 2 or more)"
    elif roi < 0:
        verdict = "retired (negative)"
    else:
        verdict = "not decided (positive, score under 2): read again at 600"
    return f"read at {at}: {verdict}"


def records(state):
    out = {}
    for k in ROW:
        head, cmp = N.stat(bets(state, k, HEADLINE)), N.stat(bets(state, k, COMPARE))
        out[k] = dict(headline=head, compare=cmp, read=read_text(k, head))
    live = {et: v for et, v in state["events"].items() if not v.get("skipped")}
    out["events"] = len(live)
    out["markets"] = len(state["markets"])
    out["days"] = sorted({v["day"] for v in live.values()})
    out["confirmed"] = sum(1 for v in live.values() if v.get("confirm"))
    out["pending"] = len(state["pending"])
    return out


def main():
    state = load()
    n = run(state)
    save(state)
    r = records(state)
    print(VERSION, "new events", n, "events", r["events"], "pending", r["pending"], {k: r[k]["headline"]["n"] for k in ROW}, state.get("errors"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
