#!/usr/bin/env python3
"""Nations League dump bid: a Sandbox PAPER watch (Olu 2026-11-13, "let's watch it in sandbox"). No orders, no VPS, no live loop.

The lead is the one green group of the flash dump map, stage 2 (docs/flash_dump_map_stage2_2026-11-14.md): on UEFA Nations League total
goals markets a bid 20c under the last trade, sold when the price is back within 5c, returned +12% / +10% on the later dates at about
50 bets each, not significant. Here it is watched forward on the games that have not been played yet.

THE RULE, fixed in advance (Fable's replay, s2_replay.py, vendored unchanged apart from the row list; nothing here is tuned):
  * Every whole minute T a bid rests DEPTH under R, the last trade on the bid's side (the YES price for a YES bid, 1 - YES for a NO bid), on
    BOTH sides of every market of the game. No bid if there was no trade in the 10 minutes before T, if R is over 95c, or if the bid would sit
    under 5c. The order is live from T + DELAY to T + 60 s + DELAY (the next minute's order replaces it). DELAY 25 s is the order path as
    measured (the headline column); 2 s is the comparison column. It is not placed if a trade between T and T + DELAY is already at or under it.
  * FILL: fillsim honest-v1, only when a trade prints strictly through the bid while the order is live; filled at the bid; the size is what $1
    buys, or what traded through when that is less (a part fill).
  * SELL (exit A): a resting sell at R - 5c, up 60 s after the fill, filled only by a trade strictly through it. If the price is already
    there when the sell goes up it is sold as a taker with the taker fee. What is not sold rides to the result.
  * One position a side of a market at a time: no new bid on that side until it is fully sold; none after one is left to the result.
  * Fees: Kalshi lists no maker fee on this series (fee_type quadratic), so a resting fill pays nothing; a taker sale pays 0.07 x p x (1 - p).

ROWS (each its own record, each in both delay columns), all on the same trades:
    D20  bid 20c under, sell back within 5c        (the headline)
    D15  bid 15c under, sell back within 5c
    H20  bid 20c under, simply held (no sell)      (the D20 fills, held to the result)
    D40  bid 40c under, sell back within 5c, only in the last 3 hours of each market's trading (Fable's tracker spec in the same report)

HOW IT RUNS: every game is replayed once, after it settles, from Kalshi's public trade prints (one small pull a market). The rule is fixed, so
this is a forward test of games not yet played. FROM is the first game day after the build. Own ledger data/nl_dump_ledger.json; read hourly in
nl-dump.yml. The score clusters by game; read at 100 and at 200 fills in the headline column (docs/prereg_nl_dump_2026-11-13.md).
"""
import bisect
import datetime as dt
import json
import math
import os
import re
import sys

import daily_track as D
import fdr_check as FD
import fillsim as F
import fillsim_tape as TP

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "data", "nl_dump_ledger.json")
VERSION = "nl-dump-v1"
REGISTERED = "2026-11-13"
SERIES = "KXUEFANLTOTAL"
LEAGUE = "UEFA Nations League"
FROM = "2026-11-14"                  # the first game day after the build: the Nov 13 games were in the research sample
EPS = 1e-9
DELAYS = (25, 2)
HEADLINE = 25
COMPARE = 2
LAST_H = 3
READ_AT = (100, 200)
KEEP_T = 2.0
FEE_TYPE = "quadratic"               # Kalshi's fee_type for the series: no maker fee
ROWS = {
    "D20": dict(depth=0.20, ex="A", label="Bid 20c under, sold back within 5c", short="20c under · sold back"),
    "D15": dict(depth=0.15, ex="A", label="Bid 15c under, sold back within 5c", short="15c under · sold back"),
    "H20": dict(depth=0.20, ex="C", label="Bid 20c under, simply held", short="20c under · held"),
    "D40": dict(depth=0.40, ex="A", label="Bid 40c under in the last 3 hours, sold back within 5c", short="40c under · last 3 hours", last_h=LAST_H),
}
MAX_PER_RUN = 120
MONTHS = {m: i for i, m in enumerate(("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"), 1)}
LAT, LOOK = F.HONEST.latency_s, F.HONEST.cross_lookback_s


def cell_key(row, delay):
    return f"{row}_{delay}s"


# ---------------------------------------------------------------- the replay (Fable's s2_replay.replay)
def sell(ts, px, n, fill_ts, target, qty):
    """fillsim.resting_sell on lists (px on the bet's side): (sold, taker?, time the last contract sold or None)."""
    up = fill_ts + LAT
    i = bisect.bisect_left(ts, up)
    crossed = i > 0 and ts[i - 1] >= up - LOOK and px[i - 1] >= target - EPS
    sold = 0.0
    lim = target - EPS if crossed else target + EPS
    for k in range(i, len(ts)):
        if (px[k] >= lim) if crossed else (px[k] > lim):
            sold += n[k]
            if sold >= qty - EPS:
                return qty, crossed, ts[k]
    return sold, crossed, None


def replay(prints, result):
    """Every bet of every row and delay on one market's trades: {cell key: [bet dict]}."""
    out = {cell_key(k, d): [] for k in ROWS for d in DELAYS}
    ts = [p[0] for p in prints]
    yes = [p[1] for p in prints]
    n = [p[2] for p in prints]
    if len(ts) < 2:
        return out
    start, last = ts[0], ts[-1]
    PX = dict(yes=yes, no=[round(1 - y, 4) for y in yes])
    for delay in DELAYS:
        T, first = [], []                                            # the minutes T whose order is live when a trade lands, and each one's first trade
        for i, t in enumerate(ts):
            m = math.floor((t - delay) / 60) * 60
            if not T or m != T[-1]:
                T.append(m)
                first.append(i)
        first.append(len(ts))
        for side in ("yes", "no"):
            px = PX[side]
            payout = 1.0 if result == side else 0.0
            base = []                                                # (T, R, lowest trade while live, b, e) for every minute a bid could be up
            for c, t0 in enumerate(T):
                if t0 < start:
                    continue
                i = bisect.bisect_right(ts, t0) - 1
                if i < 0 or ts[i] < t0 - 600:
                    continue
                r = px[i]
                if r > 0.95 + EPS:
                    continue
                b, e = first[c], first[c + 1]
                base.append((t0, r, min(px[b:e]), b, e))
            for key, cfg in ROWS.items():
                d, ex = cfg["depth"], cfg["ex"]
                lo = last - cfg["last_h"] * 3600 if cfg.get("last_h") else -math.inf
                cand = [(t0, r, round(r - d, 4), b, e) for t0, r, w, b, e in base
                        if t0 >= lo and round(r - d, 4) >= 0.05 - EPS and w < round(r - d, 4) - EPS]
                free = -math.inf
                for t0, r, l, b, e in cand:
                    if t0 < free:
                        continue
                    a = bisect.bisect_right(ts, t0)
                    if b > a and min(px[a:b]) <= l + EPS:
                        continue                                      # the price was already there before the order went up
                    want = F.stake_qty(l)
                    got, thr, fill_ts = 0.0, 0.0, None
                    for k in range(b, e):
                        if px[k] < l - EPS:
                            thr += n[k]
                            if got < want - EPS:
                                got = min(want, got + n[k])
                                fill_ts = ts[k]
                    target = None if ex == "C" else round(r - 0.05, 4)
                    sells, done, taker = [], None, False
                    if target is not None:
                        sold, taker, done = sell(ts, px, n, fill_ts, target, got)
                        if sold > EPS:
                            sells = [(target, sold, taker)]
                    s = F.settle(l, got, sells, payout, entry_taker=False, rules=F.HONEST)
                    j, j2 = bisect.bisect_right(ts, fill_ts), bisect.bisect_right(ts, fill_ts + 120)
                    out[cell_key(key, delay)].append(dict(
                        side=side, T=int(t0), R=r, L=l, fill=int(fill_ts), qty=round(got, 2), part=got < want - EPS, through=round(thr, 1),
                        roi=round(s["roi"], 4), sold=bool(s["sold"]) if not isinstance(s["sold"], (int, float)) else s["sold"] >= got - EPS,
                        taker_sell=bool(sells and sells[0][2]), back=bool(j2 > j and max(px[j:j2]) >= r - 0.05 - EPS), won=payout))
                    if done is None:
                        break                                         # left to the result (or held): no more bids on this side
                    free = done
    return out


# ---------------------------------------------------------------- the ledger
def empty():
    return dict(version=VERSION, registered=REGISTERED, since=FROM, markets={}, updated=None, errors=[])


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


def event_day(event_ticker):
    """The game day from a Kalshi event ticker (KXUEFANLTOTAL-26NOV14KOSISR -> 2026-11-14), or None."""
    m = re.search(r"-(\d{2})(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)(\d{2})", str(event_ticker))
    return f"20{m.group(1)}-{MONTHS[m.group(2)]:02d}-{m.group(3)}" if m else None


def match_of(title):
    return re.sub(r":?\s*Total Goals\s*$", "", str(title or "")).replace(" vs ", " v ").strip()


def settled_events(get=D.get, max_pages=8):
    """Every settled event of the series with its markets: [event dict]."""
    out, cur = [], None
    for _ in range(max_pages):
        d = get(f"events?series_ticker={SERIES}&status=settled&limit=200&with_nested_markets=true" + (f"&cursor={cur}" if cur else "")) or {}
        out += d.get("events") or []
        cur = d.get("cursor")
        if not cur:
            break
    return out


def todo(events, state):
    """[(event, market)] of the game days from FROM whose market has a result and no read yet, oldest game first."""
    out = []
    for ev in events:
        day = event_day(ev.get("event_ticker"))
        if not day or day < FROM:
            continue
        for m in ev.get("markets") or []:
            if m.get("result") in ("yes", "no") and m["ticker"] not in state["markets"]:
                out.append((day, ev, m))
    out.sort(key=lambda x: (x[0], x[2]["ticker"]))
    return [(ev, m) for _d, ev, m in out]


def process(state, ev, m, tape=TP.settled_tape):
    """Read one settled market into the ledger once."""
    prints = tape(m["ticker"])
    state["markets"][m["ticker"]] = dict(
        event=ev["event_ticker"], day=event_day(ev["event_ticker"]), match=match_of(ev.get("title")), line=m.get("yes_sub_title") or m.get("subtitle") or "",
        result=m["result"], prints=len(prints), bets=replay(prints, m["result"]) if prints else {cell_key(k, d): [] for k in ROWS for d in DELAYS})


def run(state, events, now=None, tape=TP.settled_tape):
    now = now or dt.datetime.now(dt.timezone.utc)
    done, errs = 0, []
    for ev, m in todo(events, state)[:MAX_PER_RUN]:
        try:
            process(state, ev, m, tape)
            done += 1
        except Exception as exc:                                    # noqa: BLE001  (one market never stops the rest; it is read next hour)
            errs.append(f'{m["ticker"]}: {str(exc)[:60]}')
    state["updated"] = now.isoformat(timespec="seconds")
    state["errors"] = errs[:10]
    return done


# ---------------------------------------------------------------- the record
def bets(state, row, delay):
    """[(roi, game, bet)] for one cell, every settled market, oldest first."""
    out = []
    for tk, v in sorted(state["markets"].items(), key=lambda kv: (kv[1]["day"], kv[0])):
        for b in v["bets"].get(cell_key(row, delay)) or []:
            out.append((b["roi"], v["event"], dict(b, ticker=tk, day=v["day"], match=v["match"], line=v.get("line"))))
    return out


def stat(rows):
    s = FD.lane_stats([(r[0], r[1]) for r in rows])
    n = len(rows)
    s["won"] = sum(1 for r in rows if r[0] > 0)
    s["back"] = (sum(1 for r in rows if r[2]["back"]) / n) if n else None
    s["sold"] = (sum(1 for r in rows if r[2]["sold"]) / n) if n else None
    return s


def read_text(head):
    """The pre-registered read: once at 100 fills and once at 200 in the headline column. Keep = positive with t of 2 or more, clustered by game."""
    n = head["n"]
    if n < READ_AT[0]:
        return f"too early ({n} of {READ_AT[0]} fills; read at {READ_AT[0]} and at {READ_AT[1]})"
    at = READ_AT[0] if n < READ_AT[1] else READ_AT[1]
    ok = (head["roi"] or 0) > 0 and (head["t"] or 0) >= KEEP_T
    return f"read at {at}: " + ("keep (positive, score 2 or more)" if ok else "retire (not positive with a score of 2 or more)")


def records(state):
    """{row: dict(headline, compare, read)} and the totals."""
    out = {}
    for k in ROWS:
        head, cmp = stat(bets(state, k, HEADLINE)), stat(bets(state, k, COMPARE))
        out[k] = dict(headline=head, compare=cmp, read=read_text(head))
    out["markets"] = len(state["markets"])
    out["games"] = len({v["event"] for v in state["markets"].values()})
    out["days"] = sorted({v["day"] for v in state["markets"].values()})
    return out


def main():
    state = load()
    n = run(state, settled_events())
    save(state)
    r = records(state)
    print(VERSION, "new", n, "markets", r["markets"], "games", r["games"], {k: r[k]["headline"]["n"] for k in ROWS}, state.get("errors"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
