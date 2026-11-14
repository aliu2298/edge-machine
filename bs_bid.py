#!/usr/bin/env python3
"""Before-start bid in fights and NFL: two Sandbox PAPER watches (Olu 2026-11-14, "yes, send both to production moves"). No orders, no VPS, no live loop.

The lead is the before-start study (docs/before_start_study_2026-11-14.md, docs PR 455): PR 450's before-start bid, unchanged, in six sports. Fights
(UFC, boxing) passed: +16.8% on 36 bets on the found dates and +17.4% on 160 bets (t 4.3) on the later dates, a world where no news arrives before the
start and a wide, thin book lets a bid inside the gap get hit and a sell get lifted. Pro football is NOT a pass: +14.7% on 47 bets over both halves,
a near miss, so it is a watch on its own reads. Here both are run forward on events not yet played.

THE RULE (the study's build spec; nl_dump.replay is the engine, checked bet for bet against Fable's replay):
  * Kalshi winner markets, both sides of every market. From the first trade until the cutoff, every whole minute T a bid rests 15c under R, the last trade
    on the bid's side. No bid if nothing traded in the 10 minutes before T, if R is over 95c, or if the bid would sit under 5c. Live from T + 25 s.
  * THE START is Kalshi's own schedule: the milestone listing's start_date for the event, NOT expected_expiration_time (in tennis that field sits anywhere
    from 50 hours before the close to an hour after). Fights cutoff = 12 hours before that start (the one change from the tested rule's 3 hours, chosen
    after looking; the listed start of a bout can be hours late and the 12 hour cut gave up nothing). NFL cutoff = 3 hours before it, the tested rule
    (that schedule is accurate to about ten minutes).
  * FILL: honest-v1, only a trade strictly through the bid. Size: what $1 buys, or what printed through when that is less.
  * SELL: resting at R - 5c, up 60 s after the fill, filled only by a trade strictly through it (a taker sale with the taker fee if the price is already
    there). What is not sold rides to the result. One position a side of a market at a time.
  * FEES: Kalshi lists no maker fee on the UFC and boxing series (fee_type quadratic): a resting fill pays nothing. KXNFLGAME is quadratic_with_maker_fees:
    every resting fill, buy and sell, pays 0.0175 x p x (1 - p). A taker sale pays 0.07 x p x (1 - p).
  * The headline column is the 25 s order delay; the 2 s column is the comparison. The FIRST-FILL column keeps only the first fill of each fight or game
    (the study found many fills are repeats in one market; the keep rule uses this column).

THREE ROWS, judged apart: UFC, boxing, NFL (NFL = a watch, not a pass).

HOW IT RUNS: each market is replayed once, after it settles, from Kalshi's public trade prints, in bs-bid.yml. A late run backfills: the ledger holds
every market already read and a run reads whatever settled markets are not in it. Only bids from FROM_TS count. Own ledger data/bs_bid_ledger.json.
Read at 50 and at 100 fills a row (docs/prereg_bs_bid_2026-11-14.md).
"""
import dataclasses
import datetime as dt
import json
import os
import sys

import daily_track as D
import fillsim as F
import fillsim_tape as TP
import nl_dump as N

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "data", "bs_bid_ledger.json")
VERSION = "bs-bid-v1"
REGISTERED = "2026-11-14"
FROM_TS = int(dt.datetime(2026, 11, 14, 12, 0, tzinfo=dt.timezone.utc).timestamp())   # only bids from here on count
FROM_DAY = "2026-11-14"
DEPTH = 0.15
ROW = {"B15": dict(depth=DEPTH, ex="A")}
HEADLINE, COMPARE = N.HEADLINE, N.COMPARE
READ_AT = (50, 100)
KEEP_T = 2.0
GROUPS = {
    "ufc": dict(label="UFC", series="KXUFCFIGHT", hours=12, maker=False, unit="fight", market="Fight winner", watch="a pass in the study (fights)"),
    "boxing": dict(label="Boxing", series="KXBOXING", hours=12, maker=False, unit="fight", market="Fight winner", watch="a pass in the study (fights)"),
    "nfl": dict(label="NFL", series="KXNFLGAME", hours=3, maker=True, unit="game", market="Game winner", watch="a watch, not a pass: a near miss in the study"),
}
GROUP_OF = {c["series"]: g for g, c in GROUPS.items()}
RULES = {False: F.HONEST, True: dataclasses.replace(F.HONEST, maker_rate=0.0175)}
MAX_PER_RUN = 150


def start_of(event_ticker, get=D.get):
    """Unix seconds of the start in Kalshi's own schedule (the milestone listing), or None when it lists none."""
    d = get(f"milestones?limit=5&related_event_ticker={event_ticker}") or {}
    ms = d.get("milestones") or []
    ms = [m for m in ms if event_ticker in (m.get("related_event_tickers") or [])] or ms
    x = D.instant(ms[0].get("start_date")) if ms else None
    return int(x.timestamp()) if x else None


def cutoff_of(start, group):
    """The last moment a bid may be set: the group's hours before the scheduled start, or None with no start."""
    return None if start is None else start - GROUPS[group]["hours"] * 3600


def replay(prints, result, group, cutoff):
    return N.replay(prints, result, rows=ROW, rules=RULES[GROUPS[group]["maker"]], since=FROM_TS, until=cutoff)


# ---------------------------------------------------------------- the ledger
def empty():
    return dict(version=VERSION, registered=REGISTERED, since=FROM_DAY, markets={}, updated=None, errors=[])


def load(path=PATH):
    try:
        with open(path) as f:
            return dict(empty(), **json.load(f))
    except (OSError, ValueError):
        return empty()


def save(state, path=PATH):
    N.save(state, path)


def settled_events(series, get=D.get):
    return N.settled_events(get=get, series=series)


def todo(events, state, series):
    """[(day, event, market, series)] of the event days from FROM_DAY whose market has a result and is not in the ledger yet."""
    out = []
    for ev in events:
        day = N.event_day(ev.get("event_ticker"))
        if not day or day < FROM_DAY:
            continue
        for m in ev.get("markets") or []:
            if m.get("result") in ("yes", "no") and m["ticker"] not in state["markets"]:
                out.append((day, ev, m, series))
    return out


def process(state, ev, m, series, tape=TP.settled_tape, starts=None, get=D.get):
    group = GROUP_OF[series]
    et = ev["event_ticker"]
    starts = starts if starts is not None else {}
    if et not in starts:
        starts[et] = start_of(et, get)
    cut = cutoff_of(starts[et], group)
    if cut is None:
        raise ValueError("no scheduled start")
    prints = tape(m["ticker"])
    state["markets"][m["ticker"]] = dict(
        event=et, day=N.event_day(et), series=series, group=group, match=N.match_of(ev.get("title")), leg=m.get("yes_sub_title") or "",
        result=m["result"], start=starts[et], cutoff=cut, prints=len(prints),
        bets=replay(prints, m["result"], group, cut) if prints else {N.cell_key(k, d): [] for k in ROW for d in N.DELAYS})


def run(state, events_by_series, now=None, tape=TP.settled_tape, get=D.get):
    """Read every settled market that is not in the ledger, oldest event first (a late run backfills what an earlier one missed)."""
    now = now or dt.datetime.now(dt.timezone.utc)
    items = []
    for series, events in events_by_series.items():
        items += todo(events, state, series)
    items.sort(key=lambda x: (x[0], x[2]["ticker"]))
    done, errs, starts = 0, [], {}
    for _day, ev, m, series in items[:MAX_PER_RUN]:
        try:
            process(state, ev, m, series, tape, starts, get)
            done += 1
        except Exception as exc:                                    # noqa: BLE001  (one market never stops the rest; it is read next run)
            errs.append(f'{m["ticker"]}: {str(exc)[:60]}')
    state["updated"] = now.isoformat(timespec="seconds")
    state["errors"] = errs[:10]
    return done


# ---------------------------------------------------------------- the record
def bets(state, group, delay):
    out = []
    for tk, v in sorted(state["markets"].items(), key=lambda kv: (kv[1]["day"], kv[0])):
        if v["group"] != group:
            continue
        for b in v["bets"].get(N.cell_key("B15", delay)) or []:
            out.append((b["roi"], v["event"], dict(b, ticker=tk, day=v["day"], match=v["match"], leg=v.get("leg"), series=v["series"])))
    return out


def first_fills(rows):
    """Only the first fill of each fight or game (earliest fill time over every market and side of the event)."""
    best = {}
    for r in rows:
        k = r[1]
        if k not in best or (r[2]["fill"], r[2]["ticker"]) < (best[k][2]["fill"], best[k][2]["ticker"]):
            best[k] = r
    return sorted(best.values(), key=lambda r: (r[2]["day"], r[2]["ticker"]))


def read_text(head, first):
    """Read at 50 and at 100 fills. Keep = positive after fees, score 2 or more clustered by card day (game day), and the first-fill-only row still positive.
    Retire = under that at 100."""
    n = head["n"]
    if n < READ_AT[0]:
        return f"too early ({n} of {READ_AT[0]} fills; read at {READ_AT[0]} and at {READ_AT[1]})"
    ok = (head["roi"] or 0) > 0 and (head["t"] or 0) >= KEEP_T and (first["roi"] or 0) > 0 and first["n"] > 0
    if n < READ_AT[1]:
        return f"read at {READ_AT[0]}: " + ("on track (positive, score 2 or more, first fills positive); read again at 100" if ok else "not there yet; read again at 100")
    return f"read at {READ_AT[1]}: " + ("keep (positive, score 2 or more, first fills positive)" if ok else "retire (under the bar at 100 fills)")


def records(state):
    out = {}
    for g in GROUPS:
        rows = bets(state, g, HEADLINE)
        head, cmp, first = N.stat(rows), N.stat(bets(state, g, COMPARE)), N.stat(first_fills(rows))
        out[g] = dict(headline=head, compare=cmp, first=first, read=read_text(head, first),
                      games=len({v["event"] for v in state["markets"].values() if v["group"] == g}))
    return out


def main():
    state = load()
    events = {s: settled_events(s) for s in GROUP_OF}
    n = run(state, events)
    save(state)
    r = records(state)
    print(VERSION, "new", n, {g: (r[g]["headline"]["n"], r[g]["games"]) for g in GROUPS}, state.get("errors"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
