"""Corners total · favourite-side NO (v2), the maker entry (2026-11-06, Olu). Sandbox paper.

The Sandbox rule corners_fav_no (sandbox_sources) chooses the match and the rung and logs the same rung at the TAKER
No ask: that row is the comparison. This module is the lane's own entry: a No bid resting at the No ask less 2c from
the moment the rule selected the rung until kickoff. It fills only on a trade print STRICTLY below the bid (a print at
the bid only touches it, and a resting order behind the queue does not fill on it: the o35 rule). Maker fee
0.0175 p (1 - p). Held to settlement, so a filled bid settles with the Sandbox row's own Kalshi result.

Read after kickoff from Kalshi's public trade prints (markets/trades), once per entry: the prints before kickoff do not
change. Its ledger, data/corners_fav_no_maker.json, holds one row per Sandbox entry. Nothing here places an order.
"""
import datetime as dt
import json
import os
import sys

import daily_track as D
import o35_cheap_no as O

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "data", "corners_fav_no_maker.json")
SOURCE = "corners_fav_no"
BID_UNDER = 0.02
MAKER = 0.0175
TAKER = 0.07
EPS = 1e-9
REVIEW_N, DECIDE_N = 10, 30
REGISTERED = "2026-11-06"
UTC = dt.timezone.utc


def maker_fee(p):
    return MAKER * p * (1 - p)


def taker_fee(p):
    return TAKER * p * (1 - p)


def bid_of(price):
    """The resting No bid for a rung whose No ask was `price`."""
    return round(float(price) - BID_UNDER, 2)


def load(path=PATH):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {"version": "corners-fav-no-v2", "bids": {}, "last_run": None, "error": None}


def entries(d):
    """The rule's logged bets, oldest first: one a match."""
    rows = [q for q in d.get("quotes") or [] if q.get("source") == SOURCE and q.get("bet")]
    return sorted(rows, key=lambda q: q.get("logged") or "")


def fill_of(prints, bid, start_ts, end_ts):
    """The first print strictly below `bid` in [start_ts, end_ts): (ts, no price), or None."""
    for ts, no, _n in prints:
        if start_ts <= ts < end_ts and no < bid - EPS:
            return ts, no
    return None


def fetch_trades(ticker, min_ts, max_ts, fetch, max_pages=20):
    """Kalshi's public trade prints on `ticker` between min_ts and max_ts (selection to kickoff)."""
    rows, cur = [], None
    for _ in range(max_pages):
        path = f"markets/trades?ticker={ticker}&min_ts={min_ts}&max_ts={max_ts}&limit=1000" + (f"&cursor={cur}" if cur else "")
        got = fetch(path)
        rows += got.get("trades") or []
        cur = got.get("cursor")
        if not cur or not got.get("trades"):
            break
    return rows


def check(q, now, fetch):
    """The maker bid on one entry, read once kickoff has passed: dict(bid, filled, fill_at, fill_px, prints)."""
    start, logged = D.instant(q.get("start")), D.instant(q.get("logged"))
    if not start or not logged or now < start:
        return None
    bid = bid_of(q["price"])
    prints = O.prints_of(fetch_trades(q["market_id"], int(logged.timestamp()), int(start.timestamp()), fetch))
    hit = fill_of(prints, bid, int(logged.timestamp()), int(start.timestamp()))
    return dict(bid=bid, filled=bool(hit), fill_at=(dt.datetime.fromtimestamp(hit[0], UTC).isoformat() if hit else None),
                fill_px=hit[1] if hit else None, prints=sum(1 for p in prints if p[0] < int(start.timestamp())),
                checked=now.isoformat())


def run(state, d, now=None, fetch=D.get):
    now = now or dt.datetime.now(UTC)
    errs = []
    for q in entries(d):
        if q["id"] in state["bids"]:
            continue
        try:
            got = check(q, now, fetch)
        except Exception as e:                                  # noqa: BLE001
            errs.append(f'{q["id"]}: {str(e)[:80]}')
            continue
        if got:
            state["bids"][q["id"]] = got
    state["last_run"] = now.isoformat()
    state["error"] = "; ".join(errs)[:500] or None
    return state


# ---------- the records (maker and taker, the same entries) ----------

def _roi(rows):
    return sum(r[1] for r in rows) / len(rows) if rows else None


def records(d, state):
    """dict(maker, taker, taker_filled, taker_unfilled): settled n, won, priced (sum of prices), ROI after fees per $1,
    z, open; the maker's also bids placed, filled, unfilled. The taker record is EVERY selected match; taker_filled and
    taker_unfilled split it by whether the maker bid filled. A match is one outcome: one entry a match."""
    import math
    maker, taker, priced_m, priced_t = [], [], [], []
    # The taker record split by what the maker bid did (2026-11-06): a bid filled only on a print below it, so a fill
    # can be the price moving against the entry (adverse selection, seen on the Eredivisie draw maker replay).
    by_fill = {True: ([], []), False: ([], [])}
    placed = filled = waiting = 0
    open_t = open_m = 0
    for q in entries(d):
        won = q.get("status") == "won"
        done = q.get("status") in ("won", "lost")
        if done:
            cost = q["price"] + taker_fee(q["price"])
            taker.append((won, (1 if won else 0) / cost - 1))
            priced_t.append(q["price"])
        elif q.get("status") == "open":
            open_t += 1
        b = state.get("bids", {}).get(q["id"])
        if b is not None and done:
            by_fill[bool(b["filled"])][0].append(taker[-1])
            by_fill[bool(b["filled"])][1].append(q["price"])
        if b is None:
            waiting += 1
            continue
        placed += 1
        if not b["filled"]:
            continue
        filled += 1
        if done:
            cost = b["bid"] + maker_fee(b["bid"])
            maker.append((won, (1 if won else 0) / cost - 1))
            priced_m.append(b["bid"])
        else:
            open_m += 1

    def rec(rows, priced, open_n):
        n, w = len(rows), sum(1 for r in rows if r[0])
        var = sum(p * (1 - p) for p in priced)
        return dict(n=n, won=w, priced=sum(priced), roi=_roi(rows), open=open_n,
                    z=(w - sum(priced)) / math.sqrt(var) if var > 0 else None)
    m = rec(maker, priced_m, open_m)
    m.update(placed=placed, filled=filled, unfilled=placed - filled, waiting=waiting)
    return dict(maker=m, taker=rec(taker, priced_t, open_t), taker_filled=rec(*by_fill[True], 0),
                taker_unfilled=rec(*by_fill[False], 0))


def main(argv=None):
    import sandbox_track as T
    argv = sys.argv[1:] if argv is None else argv
    out = argv[argv.index("--out") + 1] if "--out" in argv else PATH
    state = load(out)
    run(state, T.load())
    os.makedirs(os.path.dirname(out), exist_ok=True)
    tmp = out + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=1, sort_keys=True)
        f.write("\n")
    os.replace(tmp, out)
    print("corners_fav_no maker:", len(state["bids"]), "bids read", "error", state["error"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
