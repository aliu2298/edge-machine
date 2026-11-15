#!/usr/bin/env python3
"""Attendance and performers dump bid: a Sandbox PAPER watch (Olu, Nov 15 2026, "Yes, paper lane"). No orders, no VPS, no live loop.

The lead is the attendance and performers screen and confirm test (docs/attendance_confirm_2026-11-15.md): on 50 events read once, a bid 20c under the last
trade, sold 15c above the bid, returned +28.3% (who attends) and +25.5% (performers) after fees at 20c under, and passed its written test in all four cells.
Here it is run forward on events that open after the merge.

THE RULE is the mentions dump bid (mentions_dump.py; nl_dump.replay is the engine) with ONE change, the clock:
  * Every item of every event in the 54 fixed series (POOL: who attends and guests, performers, setlists, features and ads; one-winner markets stay out).
    Every whole minute a bid rests DEPTH under R, the last trade on the bid's side, on both sides. No bid if nothing traded in the last 10 minutes, R is over 95c,
    or the bid would sit under 5c. Live from T + 25 s (headline; 2 s is the comparison).
  * THE CLOCK: each item is bid from its open until THAT item is confirmed: its first trade at 97c or more after last trading under 90c. Not the event's first
    confirmation (guests and performers are announced one at a time), and not the listed start.
  * FILL: honest-v1, only a trade strictly through the bid. SELL: resting at R - 5c (15c above a 20c bid), up 60 s after the fill; what is not sold rides to
    the result. One open position a side of an item.
  * FEES: a resting fill pays nothing unless the series lists a maker fee; a taker sale pays 0.07 x p x (1 - p). Every series here is fee_type quadratic.

ROWS, all on the same trades: M20 (20c under, headline, shown for each group), M15 (15c under), M20L (20c under, bids of 50c or less), M20E (the headline row on
events that already have 20 fills: a lead seen after the test), H20 (control: the first fill of each side of an item held to the result).

Only events whose first item opened after START_TS count. Each event is replayed once, after every item has settled, from public trade prints. Own ledger
data/attendance_dump_ledger.json, read in attendance-dump.yml. Pre-registration text: PREREG below, verbatim.
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
PATH = os.path.join(ROOT, "data", "attendance_dump_ledger.json")
VERSION = "attendance-dump-v1"
REGISTERED = "2026-11-15"
START_TS = int(dt.datetime(2026, 11, 15, 12, 0, tzinfo=dt.timezone.utc).timestamp())   # only events that open after this (the merge) count
START_DAY = "2026-11-15"
PREREG = ("Attendance and performers dump bid. Paper. Kalshi events on who attends, who performs, setlists and features; each minute a bid 20c under the last "
          "trade on both sides of every item, until that item is confirmed; honest fills, order 25 seconds late; sold 15c above the bid, otherwise held. Read at "
          "100 and 300 fills, scored by event. Held if the main row is positive with t of 2 or more at 300 fills. Retired if it is negative at 300. Expect few "
          "fills before February.")
GROUPS = ("who attends, guests", "performers, setlists, features, ads")
A = (
    "KXACTORAWARDSATTEND",
    "KXATTENDGRAMMYS",
    "KXATTENDSOTU",
    "KXATTENDUFC250",
    "KXCHENEYFUNERAL",
    "KXFINALSATTEND",
    "KXFRIDMAN",
    "KXHULKHOGANATTEND",
    "KXINAUG",
    "KXMAMDANISWEARING",
    "KXMETGALA",
    "KXNBAATTEND",
    "KXOSCARGUESTS",
    "KXPERSONPUBLIC",
    "KXROGANGUEST",
    "KXSBGUESTS",
    "KXSUBPOENAATTEND",
    "KXTAYLORSWIFTWEDDINGATTEND",
    "KXTRUMPATTEND",
    "KXTRUMPCRYPTOCONF",
    "KXTRUMPFOOTBALL",
    "KXTRUMPPUTIN",
    "KXTRUMPSCOTUS",
    "KXTRUMPUFC",
    "KXTRUMPUFC322",
    "KXWCATTEND",
    "KXWCATTENDSWIFT",
    "KXWHCDATTEND",
    "KXWHITEPARTY",
    "KXWHPRESSBRIEFING",
)
P = (
    "KXFEATURE",
    "KXFEATUREDRAKE",
    "KXFEATUREJCOLE",
    "KXFEATURETRIPPIERED",
    "KXFEATUREYE",
    "KXINAUGSPEAK",
    "KXPERFORMGRAMMYS",
    "KXPERFORMSONGJB",
    "KXPERFORMSUPERBOWLB",
    "KXPERFORMVMA",
    "KXPERFORMVS",
    "KXRNCMIDTERMSPEAK",
    "KXSBADAPPEARANCES",
    "KXSBADS",
    "KXSBPERFORM",
    "KXSBSETLISTS",
    "KXSNLHOST",
    "KXVENUEPERFORM",
    "KXVENUEPERFORMANCESPHERE",
    "KXVSFANTASYBRA",
    "KXWCFINALSONGS",
    "KXWCOCMEX",
    "KXWCOCUSA",
    "KXWORLDCUPHALFTIME",
)
POOL = {**{t: GROUPS[0] for t in A}, **{t: GROUPS[1] for t in P}}
ROW = {
    "M20": dict(depth=0.20, ex="A"),
    "M15": dict(depth=0.15, ex="A"),
    "M20L": dict(depth=0.20, ex="A", max_l=0.50),
    "H20": dict(depth=0.20, ex="C"),
}
LABEL = {
    "M20": "20c under, all prices, sold back",
    "M15": "15c under, sold back",
    "M20L": "20c under, bids of 50c or less, sold back",
    "M20E": "20c under, events that already have 20 fills",
    "H20": "20c under, first fill of each side held to the result",
}
HEAD_ROW = "M20"
HEADLINE, COMPARE = N.HEADLINE, N.COMPARE
READ_AT = (100, 300)
KEEP_T = 2.0
EVENT_FILLS = 20
STRIKE_HI, STRIKE_LO = 0.97, 0.90
RULES = {False: F.HONEST, True: dataclasses.replace(F.HONEST, maker_rate=0.0175)}
MAX_EVENTS_PER_RUN = 20
SWEEP_BACK_S = 6 * 3600
PENDING_DAYS = 120             # an attendance event can stay open for months: an event not all settled is retried this long


def now_ts():
    return int(dt.datetime.now(dt.timezone.utc).timestamp())


def strike(prints):
    """Unix seconds of this item's first trade at 97c or more after it last traded under 90c, or None. prints = [(ts, yes price, contracts, ...)]."""
    prev = None
    for p in prints:
        if prev is not None and prev < STRIKE_LO - 1e-9 and p[1] >= STRIKE_HI - 1e-9:
            return int(p[0])
        prev = p[1]
    return None


def replay(prints, result, maker, confirm):
    """One item's bets. The clock is the item's own confirmation."""
    return N.replay(prints, result, rows=ROW, rules=RULES[bool(maker)], since=START_TS, until=confirm)


def empty():
    return dict(version=VERSION, registered=REGISTERED, since=START_DAY, markets={}, events={}, pending={}, swept=None, updated=None, errors=[])


def load(path=PATH):
    try:
        with open(path) as f:
            return dict(empty(), **json.load(f))
    except (OSError, ValueError):
        return empty()


def save(state, path=PATH):
    N.save(state, path)


def sweep(series, since, get=D.get):
    """{event ticker: series} of every event with a market that settled since `since` (unix seconds)."""
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


def opened(markets):
    ts = [D.instant(m.get("open_time")) for m in markets if m.get("open_time")]
    ts = [t for t in ts if t]
    return min(ts) if ts else None


def event_day(markets):
    ts = [D.instant(m.get("close_time")) for m in markets if m.get("close_time")]
    ts = [t for t in ts if t]
    return max(ts).strftime("%Y-%m-%d") if ts else None


def match_of(ev):
    return re.sub(r"\s+", " ", str(ev.get("title") or ev.get("event_ticker") or "")).strip()


def process(state, et, series, tape=TP.settled_tape, get=D.get):
    """Read one event once: None if an item is not settled yet (retried), else True. Raises on a failed pull (retried next run)."""
    d = get(f"events/{et}?with_nested_markets=true") or {}
    ev = d.get("event") or {}
    mk = d.get("markets") or ev.get("markets") or []
    if not mk or any(m.get("result") not in ("yes", "no") for m in mk):
        return None
    day, op = event_day(mk), opened(mk)
    if not op or op.timestamp() < START_TS:
        state["events"][et] = dict(day=day, skipped="opened before the start of the record")
        return True
    name = match_of(ev)
    maker = False
    confirms = 0
    for m in mk:
        prints = tape(m["ticker"])
        c = strike(prints)
        confirms += 1 if c else 0
        state["markets"][m["ticker"]] = dict(
            event=et, day=day, series=series, group=POOL.get(series), match=name, leg=m.get("yes_sub_title") or m.get("subtitle") or "", result=m["result"],
            prints=len(prints), confirm=c,
            bets=replay(prints, m["result"], maker, c) if prints else {N.cell_key(k, x): [] for k in ROW for x in N.DELAYS})
    state["events"][et] = dict(day=day, series=series, group=POOL.get(series), items=len(mk), confirmed=confirms)
    return True


def run(state, now=None, get=D.get, tape=TP.settled_tape, series=None):
    now = now or now_ts()
    series = list(series if series is not None else POOL)
    since = max(START_TS, (state.get("swept") or START_TS) - SWEEP_BACK_S)
    for et, s in sweep(series, since, get).items():
        if et not in state["events"]:
            state["pending"].setdefault(et, dict(series=s, first=now))
    todo = sorted(state["pending"].items(), key=lambda kv: (kv[1]["first"], kv[0]))
    done, errs = 0, []
    for et, v in todo[:MAX_EVENTS_PER_RUN]:
        if et in state["events"]:
            state["pending"].pop(et, None)
            continue
        try:
            r = process(state, et, v["series"], tape, get)
        except Exception as exc:                                    # noqa: BLE001  (one event never stops the rest; it is read next run)
            errs.append(f"{et}: {str(exc)[:60]}")
            continue
        if r:
            state["pending"].pop(et, None)
            done += 1
    for et in [e for e, v in state["pending"].items() if now - v["first"] > PENDING_DAYS * 86400]:
        state["pending"].pop(et, None)
    state["swept"] = now
    state["updated"] = dt.datetime.fromtimestamp(now, dt.timezone.utc).isoformat(timespec="seconds")
    state["errors"] = errs[:10]
    return done


# ---------------------------------------------------------------- the record
def bets(state, row, delay, group=None):
    """[(roi, event, bet)] for one cell, oldest first. M20E is the headline row restricted to events with EVENT_FILLS or more fills (all fills of those events)."""
    src = HEAD_ROW if row == "M20E" else row
    keep = None
    if row == "M20E":
        count = {}
        for tk, v in state["markets"].items():
            count[v["event"]] = count.get(v["event"], 0) + len(v["bets"].get(N.cell_key(src, delay)) or [])
        keep = {e for e, n in count.items() if n >= EVENT_FILLS}
    out = []
    for tk, v in sorted(state["markets"].items(), key=lambda kv: (kv[1]["day"], kv[0])):
        if group and v.get("group") != group or (keep is not None and v["event"] not in keep):
            continue
        for b in v["bets"].get(N.cell_key(src, delay)) or []:
            out.append((b["roi"], v["event"], dict(b, ticker=tk, day=v["day"], match=v["match"], leg=v.get("leg"), series=v["series"])))
    return out


def read_text(st):
    """Pre-registered: read at 100 and 300 fills, scored by event. Held if the main row is positive with t of 2 or more at 300; retired if negative at 300."""
    n = st["n"]
    if n < READ_AT[0]:
        return f"too early ({n} of {READ_AT[0]} fills; read at 100 and 300)"
    roi, t = st["roi"] or 0, st["t"] or 0
    if n < READ_AT[1]:
        return f"read at 100: {'positive' if roi > 0 else 'not positive'}, no decision before 300 fills"
    if roi > 0 and t >= KEEP_T:
        verdict = "held (positive, score 2 or more)"
    elif roi < 0:
        verdict = "retired (negative)"
    else:
        verdict = "not decided (positive, score under 2)"
    return f"read at 300: {verdict}"


def records(state):
    out = {}
    for k in list(ROW) + ["M20E"]:
        head, cmp = N.stat(bets(state, k, HEADLINE)), N.stat(bets(state, k, COMPARE))
        out[k] = dict(headline=head, compare=cmp, read=read_text(head) if k == HEAD_ROW else None)
    out["groups"] = {g: N.stat(bets(state, HEAD_ROW, HEADLINE, g)) for g in GROUPS}
    live = {et: v for et, v in state["events"].items() if not v.get("skipped")}
    out["events"] = len(live)
    out["markets"] = len(state["markets"])
    out["days"] = sorted({v["day"] for v in live.values()})
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
