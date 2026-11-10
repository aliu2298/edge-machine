#!/usr/bin/env python3
"""Backtest of Rule 1 v2 · Loss Reader (lossreader.py, sw15-lr1), REPORT ONLY: never a gate, never tuned against.

Replays the frozen rule day by day on Kalshi's public 1-minute candles for KXBTC15M / KXSOL15M / KXWTI15M, Oct 25 to
Nov 9 (Central days). S2 here is the research engine's candle quote (the ask at the end of minute 2, or 1 - bid for NO;
the side by the mid), with no print check: the live lane's honest fill (a print at or through the ask) is stricter.
Taker fee as v1: return = won / (price + fee) - 1.

  python3 scripts/lossreader_backtest.py DIR [DIR ...] [--shuffles 200] [--out data/lossreader_backtest.json]

Each DIR holds markets_<series>.json and candles_<series>.json (the research files, ~/edge-research/swing15_2026-11-09/
data, plus a refetch for the later days). A later DIR wins on the same ticker.
Shuffle test: each day's outcome order is permuted within each market (200 times by default) and the whole rule is
replayed; the real total profit's percentile among the shuffles is reported.
"""
import datetime as dt
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import lossreader as LR                                           # noqa: E402
import swing15 as W                                               # noqa: E402

FIRST, LAST = dt.date(2026, 10, 25), dt.date(2026, 11, 9)


def f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def ts(s):
    return int(dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp())


def s2_from_candles(cs, open_ts, won_yes):
    """The research engine's S2: the quote of the candle ending at minute 2 (or the latest before it)."""
    cm = {}
    for c in cs:
        cm[(c["end_period_ts"] - open_ts) // 60] = (f((c.get("yes_bid") or {}).get("close_dollars")),
                                                     f((c.get("yes_ask") or {}).get("close_dollars")))
    q = next((cm[k] for k in (2, 1) if k in cm), None)
    if not q or q[0] is None or q[1] is None or not (q[0] > 0 and q[1] < 1):
        return None
    yb, ya = q
    mid = (yb + ya) / 2
    if mid == 0.5:
        return None
    yes = mid > 0.5
    price = ya if yes else 1 - yb
    if price >= 0.995 or price <= 0.5:
        return None
    won = 1.0 if (won_yes if yes else not won_yes) else 0.0
    return dict(price=price, won=won, roi=round(won / (price + W.fee(price, W.TAKER)) - 1, 4))


def load(dirs):
    rows = {}
    for d in dirs:
        for m in LR.MARKETS:
            mp, cp = os.path.join(d, f"markets_{m}.json"), os.path.join(d, f"candles_{m}.json")
            if not (os.path.exists(mp) and os.path.exists(cp)):
                continue
            cands = json.load(open(cp))
            for x in json.load(open(mp)):
                if x.get("result") not in ("yes", "no"):
                    continue
                t = ts(x["open_time"])
                if not FIRST <= LR.ct_day(t) <= LAST:
                    continue
                s2 = s2_from_candles(cands.get(x["ticker"]) or [], t, x["result"] == "yes")
                rows[x["ticker"]] = dict(m=m, t=t, quoted=s2 is not None, won=s2 and s2["won"],
                                         price=s2 and s2["price"], roi=s2 and s2["roi"])
    out = [r for r in rows.values()]
    for r in out:
        if not r["quoted"]:
            r.update(won=None, price=None, roi=None)
    return sorted(out, key=lambda r: (r["t"], r["m"]))


def by_day(rows):
    d = {}
    for r in rows:
        if r.get("won") is not None and r.get("roi") is not None:
            d.setdefault(LR.ct_day(r["t"]).isoformat(), []).append(r["roi"])
    return d


def run(windows):
    bets, _ = LR.replay(windows)
    every, fixed = LR.compare(windows, 0)
    return bets, every, fixed


def shuffled(windows, rng):
    """Each (market, CT day)'s outcomes in a random order over the same window times."""
    groups = {}
    for w in windows:
        groups.setdefault((w["m"], LR.ct_day(w["t"])), []).append(w)
    out = []
    for g in groups.values():
        outcomes = [{k: w[k] for k in ("quoted", "won", "price", "roi")} for w in g]
        rng.shuffle(outcomes)
        out += [dict(w, **o) for w, o in zip(g, outcomes)]
    return out


def main(argv):
    n_shuf = int(argv[argv.index("--shuffles") + 1]) if "--shuffles" in argv else 200
    out = argv[argv.index("--out") + 1] if "--out" in argv else None
    dirs = [a for a in argv if os.path.isdir(a)]
    windows = load(dirs)
    bets, every, fixed = run(windows)
    L, E, F = by_day(bets), by_day(every), by_day(fixed)
    days = sorted(set(E))
    table = []
    for d in days:
        l, e, x = L.get(d, []), E.get(d, []), F.get(d, [])
        table.append(dict(day=d, bets=len(l), roi=(sum(l) / len(l)) if l else None, profit=sum(l),
                          every_n=len(e), every_roi=sum(e) / len(e) if e else None,
                          fixed2_n=len(x), fixed2_roi=sum(x) / len(x) if x else None))
    real = sum(sum(v) for v in L.values())
    rng = random.Random(20261110)
    sh = sorted(sum(sum(v) for v in by_day(LR.replay(shuffled(windows, rng))[0]).values()) for _ in range(n_shuf))
    pct = sum(1 for v in sh if v < real) / len(sh) * 100 if sh else None
    tot = lambda rows: LR.stats(rows)
    summary = dict(
        version=LR.VERSION, engine="candle quote at minute 2 (no print check), taker fee", days=f"{days[0]}..{days[-1]} CT",
        windows=len(windows), observed=sum(1 for w in windows if w["won"] is not None),
        lane=tot([b for b in bets if b["status"] == "filled"]), every=tot(every), fixed2=tot(fixed),
        days_with_bets=sum(1 for r in table if r["bets"]),
        days_beating_every=sum(1 for r in table if r["bets"] and r["every_roi"] is not None and r["roi"] > r["every_roi"]),
        days_profitable=sum(1 for r in table if r["bets"] and r["profit"] > 0), n_days=len(table),
        shuffles=n_shuf, real_profit=round(real, 3), shuffle_percentile=None if pct is None else round(pct, 1),
        shuffle_median=round(sh[len(sh) // 2], 3) if sh else None, per_day=table)
    p = lambda x: "    —  " if x is None else f"{x * 100:+6.1f}%"
    for r in table:
        print(f'{r["day"]}  bets {r["bets"]:3d} lane {p(r["roi"])}  every {r["every_n"]:3d} {p(r["every_roi"])}'
              f'  fixed2 {r["fixed2_n"]:3d} {p(r["fixed2_roi"])}')
    print({k: v for k, v in summary.items() if k != "per_day"})
    if out:
        with open(out, "w") as fh:
            json.dump(summary, fh, indent=1, sort_keys=True)
            fh.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
