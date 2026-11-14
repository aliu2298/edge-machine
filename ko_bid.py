#!/usr/bin/env python3
"""Before-kickoff dump bid: a Sandbox PAPER watch (Olu 2026-11-13, "send it to production moves"). No orders, no VPS, no live loop.

The lead is the last one standing in the flash dump study (docs/flash_dump_condition_study_2026-11-14.md, docs PR 450): in national-team soccer
game markets the stage-2 trailing bid, placed BEFORE kickoff, made money on both sets of dates (3 hours or more before the listed kickoff:
+17.4% on 83 bets in 43 games, t 3.1 at a 25 s order delay), because with no game on a drop is nearly always a sweep, not news. Found after
the tables were read, so it is a lead, never a pass. This is the forward check, on games not yet played.

THE RULE, fixed in advance (the report's build spec; nl_dump.replay is the engine, checked bet for bet against Fable's replay):
  * Kalshi soccer game-winner markets (home, tie, away). From the first trade until 3 hours before the listed kickoff (Kalshi's expected
    expiration minus 6 hours), every whole minute T a bid rests 15c under R, the last trade on the bid's side, on both sides of every leg.
    No bid if nothing traded in the 10 minutes before T, if R is over 95c, or if the bid would sit under 5c. Live from T + 25 s to T + 85 s.
  * FILL: honest-v1, only a trade strictly through the bid. Size: what $1 buys, or what printed through when that is less.
  * SELL: resting at R - 5c, up 60 s after the fill, filled only by a trade strictly through it (a taker sale with the taker fee if the price is
    already there). What is not sold rides to the result. One position a side of a market at a time.
  * FEES: Kalshi lists no maker fee on the national-team series (fee_type quadratic): a resting fill pays nothing. The club series carry maker
    fees (quadratic_with_maker_fees): every resting fill, buy and sell, pays 0.0175 x p x (1 - p). A taker sale pays 0.07 x p x (1 - p).
  * The headline column is the 25 s order delay (the order path as measured); the 2 s column is the comparison.

TWO ROWS, judged apart:
    NATIONAL  CONCACAF Nations League, AFCON, international friendlies, UEFA Nations League game, in their windows
    CLUB      Premier League, La Liga, Serie A, Bundesliga, Champions League. Never tested: forward only

HOW IT RUNS: each market is replayed once, after it settles, from Kalshi's public trade prints, in ko-bid.yml. A late run backfills: the ledger
holds every market already read and a run reads whatever settled markets are not in it. Only bids from FROM_TS count (the rule was fixed
before then). Own ledger data/ko_bid_ledger.json. Read at 50 and at 100 fills a row (docs/prereg_ko_bid_2026-11-14.md).
"""
import datetime as dt
import json
import os
import sys
import dataclasses

import daily_track as D
import fdr_check as FD
import fillsim as F
import fillsim_tape as TP
import nl_dump as N

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "data", "ko_bid_ledger.json")
VERSION = "ko-bid-v1"
REGISTERED = "2026-11-14"
FROM_TS = int(dt.datetime(2026, 11, 14, 12, 0, tzinfo=dt.timezone.utc).timestamp())   # only bids from here on count
FROM_DAY = "2026-11-14"
CUT_BEFORE_EXPIRY_S = 6 * 3600       # expected expiration minus 6 hours = 3 hours before the listed kickoff
DEPTH = 0.15
ROW = {"B15": dict(depth=DEPTH, ex="A")}
HEADLINE, COMPARE = N.HEADLINE, N.COMPARE
READ_AT = (50, 100)
KEEP_T = 2.0
GROUPS = {
    "national": dict(label="National teams", series=("KXCONCACAFNLGAME", "KXAFCONGAME", "KXINTLFRIENDLYGAME", "KXUEFANLGAME"), maker=False,
                     names="CONCACAF Nations League, AFCON, international friendlies, UEFA Nations League"),
    "club": dict(label="Club leagues", series=("KXEPLGAME", "KXLALIGAGAME", "KXSERIEAGAME", "KXBUNDESLIGAGAME", "KXUCLGAME"), maker=True,
                 names="Premier League, La Liga, Serie A, Bundesliga, Champions League"),
}
GROUP_OF = {s: g for g, c in GROUPS.items() for s in c["series"]}
RULES = {False: F.HONEST, True: dataclasses.replace(F.HONEST, maker_rate=0.0175)}
MAX_PER_RUN = 150


def cutoff_of(market):
    """Unix seconds of the last moment a bid may be set: 3 hours before the listed kickoff, or None when Kalshi lists no expiry."""
    x = D.instant(market.get("expected_expiration_time"))
    return int(x.timestamp()) - CUT_BEFORE_EXPIRY_S if x else None


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
    """[(event, market, series)] of the game days from FROM_DAY whose market has a result and an expiry and is not in the ledger yet."""
    out = []
    for ev in events:
        day = N.event_day(ev.get("event_ticker"))
        if not day or day < FROM_DAY:
            continue
        for m in ev.get("markets") or []:
            if m.get("result") in ("yes", "no") and m["ticker"] not in state["markets"]:
                out.append((day, ev, m, series))
    return out


def process(state, ev, m, series, tape=TP.settled_tape):
    group = GROUP_OF[series]
    cut = cutoff_of(m)
    if cut is None:
        raise ValueError("no listed expiry")
    prints = tape(m["ticker"])
    state["markets"][m["ticker"]] = dict(
        event=ev["event_ticker"], day=N.event_day(ev["event_ticker"]), series=series, group=group, match=N.match_of(ev.get("title")),
        leg=m.get("yes_sub_title") or "", result=m["result"], cutoff=cut, prints=len(prints),
        bets=replay(prints, m["result"], group, cut) if prints else {N.cell_key(k, d): [] for k in ROW for d in N.DELAYS})


def run(state, events_by_series, now=None, tape=TP.settled_tape):
    """Read every settled market that is not in the ledger, oldest game first (a late run backfills what an earlier one missed)."""
    now = now or dt.datetime.now(dt.timezone.utc)
    items = []
    for series, events in events_by_series.items():
        items += todo(events, state, series)
    items.sort(key=lambda x: (x[0], x[2]["ticker"]))
    done, errs = 0, []
    for _day, ev, m, series in items[:MAX_PER_RUN]:
        try:
            process(state, ev, m, series, tape)
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


def read_text(head):
    """Read at 50 and at 100 fills. Keep = positive after fees, score 2 or more clustered by game, both halves of the record positive. Retire = under that at 100."""
    n = head["n"]
    if n < READ_AT[0]:
        return f"too early ({n} of {READ_AT[0]} fills; read at {READ_AT[0]} and at {READ_AT[1]})"
    halves = head.get("halves")
    ok = (head["roi"] or 0) > 0 and (head["t"] or 0) >= KEEP_T and bool(halves) and all((h or 0) > 0 for h in halves)
    if n < READ_AT[1]:
        return f"read at {READ_AT[0]}: " + ("on track (positive, score 2 or more, both halves positive); read again at 100" if ok else "not there yet; read again at 100")
    return f"read at {READ_AT[1]}: " + ("keep (positive, score 2 or more, both halves positive)" if ok else "retire (under the bar at 100 fills)")


def records(state):
    out = {}
    for g in GROUPS:
        head, cmp = N.stat(bets(state, g, HEADLINE)), N.stat(bets(state, g, COMPARE))
        out[g] = dict(headline=head, compare=cmp, read=read_text(head),
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
