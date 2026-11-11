#!/usr/bin/env python3
"""The 15-Minute section narrowed to three rules (Olu, 2026-11-11). Sandbox paper, no orders.

Two of the three are filters over the v1 hour shards (data/swing15/<ET day>/<HH>.json), S&P 500 (KXINX15M) only; the
third is the Lead Swap Board's favourite trade (leadswap.py, exclusion round 3). Each kept rule is a FRESH record from
FROM; review at 30, decide at 100. The same rule on every other market is tracked in the background (shown, never
counted) so a market that comes back can be seen.

  sp500_fav5    A · the favourite with 5 minutes left: at minute 10 buy the side over 50c at its ask (v1's S3, its
                fill rule), held to settlement; taker fee.
  sp500_flip15  C · the S&P 500 underdog at 15c or less: v1's S1 cell 15c · 2x · else sell at the bid with 1 minute
                left — a resting buy at 15c filled on a print at or through it, a resting sell at 2x filled on prints.
  sp500_flip25  the companion observation row: the same at 25c (not a separate rule, never judged on its own).

Why these markets (Olu's split of the forward windows Nov 9-11, checked against the Oct 26 - Nov 8 history):
  A: S&P 500 forward +4.9% (60), history +1.3% (36, research) and +11.8% (35, holdout); 2-Year, USD/JPY and Silver
     looked good forward but failed the history (-7.9% on 312, -2.1% on 843, -3.2% on 789).
  C: S&P 500 forward +66.5% (28), positive in both halves; history +68% candle / +92% trades (12), positive in both
     halves; every other market's underdog flip loses (-14% to -21% pooled). 25c: forward +30.4% (45), history +33% (28).
"""
import datetime as dt
import os
import sys

import sw15cuts as C
import swing15 as W

VERSION = "sw15-keep3"
REGISTERED = "2026-11-11"
FROM = C.CUT2_AT                               # fresh record: the first window after the merge (= the narrowing cut)
MARKET = "KXINX15M"
PATH = os.path.join(W.ROOT, "data", "sw15keep_ledger.json")
REVIEW_AT, DECIDE_AT = 30, 100
RULES = {
    "sp500_fav5": dict(key=("swing15_s3",), label="A · Favourite with 5 minutes left · S&P 500",
                       won="Won", why="Why only the S&P 500: forward +4.9% (60 bets); history +1.3% (36) and +11.8% (35, "
                                      "held out). 2-Year, USD/JPY and Silver looked good forward but lost in the history "
                                      "(−7.9% on 312, −2.1% on 843, −3.2% on 789)."),
    "sp500_flip15": dict(key=("swing15_s1", "0.15", "2.0", "bid"), label="C · S&P 500 underdog at 15c · sell at 2x",
                         won="Sells filled", why="Why only the S&P 500: forward +66.5% (28 bets), up in both halves; "
                                                 "history +68% (candles) / +92% (trade prints, 12), up in both halves. "
                                                 "Every other market's underdog flip loses (−14% to −21% pooled)."),
}
COMPANION = {"sp500_flip25": dict(key=("swing15_s1", "0.25", "2.0", "bid"), of="sp500_flip15",
                                  label="Companion · the same at 25c (observation, not a rule)",
                                  why="Forward +30.4% (45 bets); history +33% (28).")}


def in_record(w, start=None):
    return W._ts(w["open"]) >= W._ts(start or FROM)


def records(state, start=None):
    """{rule: {"all": cell (S&P 500), "background": {market: cell}}} for the two filter rules and the companion."""
    out = {}
    markets = sorted({w["series"] for w in (state.get("windows") or {}).values()} - {MARKET, "KXCRYPTOLEAD15M"})
    for k, r in list(RULES.items()) + list(COMPANION.items()):
        out[k] = dict(all=W.cells(state, lambda w: in_record(w, start) and w["series"] == MARKET).get(r["key"]),
                      background={m: W.cells(state, lambda w, m=m: in_record(w, start) and w["series"] == m).get(r["key"])
                                  for m in markets})
    return out


def ledger(state, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    slim = lambda c: None if not c else {k: c[k] for k in ("n", "hits", "hit_rate", "fair", "mean_roi", "z", "days")}
    rec = records(state)
    return dict(version=VERSION, registered=REGISTERED, **{"from": FROM}, market=MARKET,
                rules={k: list(v["key"]) for k, v in list(RULES.items()) + list(COMPANION.items())},
                updated=now.isoformat(timespec="seconds"),
                records={k: dict(all=slim(v["all"]), background={m: slim(c) for m, c in v["background"].items()})
                         for k, v in rec.items()})


def main():
    now = dt.datetime.now(dt.timezone.utc)
    start = dt.datetime.fromisoformat(FROM).astimezone(W.ET).date()
    days = {(start + dt.timedelta(days=i)).isoformat() for i in range(max(0, (now.astimezone(W.ET).date() - start).days) + 1)}
    blob = ledger(W.load(days=days), now)
    W._write(PATH, blob)
    print(VERSION, {k: (v["all"] or {}).get("n", 0) for k, v in blob["records"].items()})
    return 0


if __name__ == "__main__":
    sys.exit(main())
