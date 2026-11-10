#!/usr/bin/env python3
"""Rule 1 v2 · Loss Reader (sw15-lr1, registered 2026-11-10): Sandbox paper, no orders.

The base trade is Rule 1 = sw15-v1's S2: at minute 2 of a 15-minute window, buy the side above 50c (by the mid) at its
ask, filled only on a print at or through it in the next minute; held to settlement; taker fee on entry. Three markets:
Bitcoin, Solana, WTI.

FROZEN RULES (the pre-registration; do not edit, add a new version instead):
  Observed   Every window's S2 result on the three markets, bet or not (sw15-v1 grades S2 on every series): an observed
             window is one where S2 filled, with its outcome (won 0/1) and price.
  Triggers   Per market: 0 = every window; 1 = after 1 observed loss; 2 = after 2 in a row; 3 = after 3 in a row. A
             trigger k fires in a window when the market's last k observed windows before it were all losses (0 always).
  Learning   Before every window, per market, each trigger's score = the sum of (won − price) over TODAY's observed
             windows (day = midnight to midnight Central) where it fired, + 1/3 × the same sum over the previous 3
             days. The best trigger is active only with ≥ 4 such windows today AND a score > 0; else the market is Off.
             Ties go to the lower trigger. Re-learned before every window.
  Stop       Two losing BETS in a row on a market: that market is Off for its next 4 windows, then re-learns.
  One pick   When more than one market fires in a window, only the one with the highest active-trigger score is bet
             (ties: Bitcoin, Solana, WTI). A market is a candidate only when S2 quoted a favourite in that window
             (filled or not); a picked window S2 could not fill is a "no fill", never replaced by another market.
  Record     Bets on windows opening at or after FROM; review at 30 bets, decide at 100 bets or 5 trading days.
  Compared   "Every bet" = S2 on every observed window of the three markets; "fixed after 2" = S2 on every observed
             window after 2 observed losses in a row on that market (no learning, no stop, no one-pick).

A filter over the v1 hour shards (data/swing15/<ET day>/<HH>.json), replayed from the start each hourly run: every
decision reads only windows settled before it, so the replay is the same whatever hour it runs. Written to
data/lossreader_ledger.json by swing15.yml.
"""
import datetime as dt
import os
import sys
from zoneinfo import ZoneInfo

import swing15 as W

VERSION = "sw15-lr1"
REGISTERED = "2026-11-10"
FROM = "2026-11-10T04:45:00+00:00"            # fresh record: the first window after the merge
PATH = os.path.join(W.ROOT, "data", "lossreader_ledger.json")
CT = ZoneInfo("America/Chicago")
# The frozen pre-registration (sw15-lr1, 2026-11-10). Do not edit.
MARKETS = ("KXBTC15M", "KXSOL15M", "KXWTI15M")
TRIGGERS = (0, 1, 2, 3)
MIN_TODAY = 4
PRIOR_DAYS, PRIOR_WEIGHT = 3, 1 / 3
STOP_LOSSES, STOP_WINDOWS = 2, 4
WINDOW_S = 900
REVIEW_AT, DECIDE_BETS, DECIDE_DAYS = 30, 100, 5
LABEL = "Rule 1 v2 · Loss Reader"


def ct_day(t):
    return dt.datetime.fromtimestamp(t, CT).date()


def trigger_word(k):
    return "Off" if k is None else "every window" if k == 0 else f"after {k}"


class Market:
    """One market's observed history: [(open ts, CT day, won − price, losses in a row before it)]."""

    def __init__(self):
        self.obs, self.streak = [], 0

    def fires(self, k):
        return k == 0 or self.streak >= k

    def add(self, t, won, price):
        self.obs.append((t, ct_day(t), won - price, self.streak))
        self.streak = 0 if won else self.streak + 1

    def learn(self, t):
        """-> (active trigger or None, its score, {k: (score, today's windows)}) before the window opening at t."""
        today = ct_day(t)
        first = today - dt.timedelta(days=PRIOR_DAYS)
        s_today, n_today, s_prior = {k: 0.0 for k in TRIGGERS}, {k: 0 for k in TRIGGERS}, {k: 0.0 for k in TRIGGERS}
        for ot, day, edge, streak in reversed(self.obs):
            if day < first:
                break
            if ot >= t:
                continue
            for k in TRIGGERS:
                if k == 0 or streak >= k:
                    if day == today:
                        s_today[k] += edge
                        n_today[k] += 1
                    else:
                        s_prior[k] += edge
        table = {k: (s_today[k] + PRIOR_WEIGHT * s_prior[k], n_today[k]) for k in TRIGGERS}
        best = None
        for k in TRIGGERS:                       # ascending: a tie keeps the lower trigger
            sc, n = table[k]
            if n >= MIN_TODAY and sc > 0 and (best is None or sc > table[best][0]):
                best = k
        return best, (table[best][0] if best is not None else None), table


def replay(windows):
    """windows: [{"m", "t", "quoted", "won" (None unless S2 filled), "price", "roi"}] for the three markets.
    -> (bets, state): bets [{"m", "t", "k", "score", "status" filled/no_fill, "won", "price", "roi"}]; state the
    per-market Market objects and stop times after the last window (for the Now line)."""
    by_t = {}
    for w in windows:
        if w["m"] in MARKETS:
            by_t.setdefault(w["t"], {})[w["m"]] = w
    mk = {m: Market() for m in MARKETS}
    stop_until = {m: 0 for m in MARKETS}
    lost_bets = {m: 0 for m in MARKETS}
    bets = []
    for t in sorted(by_t):
        cands = []
        for i, m in enumerate(MARKETS):
            if t < stop_until[m]:
                continue
            k, score, _ = mk[m].learn(t)
            w = by_t[t].get(m)
            if k is not None and mk[m].fires(k) and w and w.get("quoted"):
                cands.append((score, -i, m, k))
        if cands:
            score, _, m, k = max(cands)
            w = by_t[t][m]
            filled = w.get("won") is not None
            bets.append(dict(m=m, t=t, k=k, score=round(score, 4), status="filled" if filled else "no_fill",
                             won=w.get("won"), price=w.get("price"), roi=w.get("roi")))
            if filled:
                if w["won"]:
                    lost_bets[m] = 0
                else:
                    lost_bets[m] += 1
                    if lost_bets[m] >= STOP_LOSSES:
                        stop_until[m] = t + WINDOW_S * (STOP_WINDOWS + 1)    # off for the next 4 windows
                        lost_bets[m] = 0
        for m, w in by_t[t].items():                 # the window's observed results, after the decision
            if w.get("won") is not None:
                mk[m].add(t, w["won"], w["price"])
    return bets, dict(markets=mk, stop_until=stop_until)


def compare(windows, since_ts):
    """The two comparison books over windows opening at or after since_ts: every bet, fixed after 2."""
    every, fixed = [], []
    streak = {m: 0 for m in MARKETS}
    for w in sorted((w for w in windows if w["m"] in MARKETS), key=lambda w: (w["t"], w["m"])):
        if w.get("won") is None:
            continue
        if w["t"] >= since_ts:
            every.append(w)
            if streak[w["m"]] >= 2:
                fixed.append(w)
        streak[w["m"]] = 0 if w["won"] else streak[w["m"]] + 1
    return every, fixed


def stats(rows):
    """{"n", "hits", "fair" (mean price), "mean_roi", "profit" (sum of roi)} of filled rows, or None."""
    rows = [r for r in rows if r.get("won") is not None and r.get("roi") is not None]
    if not rows:
        return None
    n = len(rows)
    return dict(n=n, hits=int(sum(1 for r in rows if r["won"])), fair=sum(r["price"] for r in rows) / n,
                mean_roi=sum(r["roi"] for r in rows) / n, profit=sum(r["roi"] for r in rows))


def now_line(state, t):
    """"Now: Bitcoin after 2 · Solana Off · WTI after 3" for the window opening at t."""
    import swing15_build as WB
    parts = []
    for m in MARKETS:
        if t < state["stop_until"][m]:
            back = dt.datetime.fromtimestamp(state["stop_until"][m], CT)
            parts.append(f"{WB.name(m)} Off (2 losing bets; back {back.hour % 12 or 12}:{back:%M} "
                         f"{'AM' if back.hour < 12 else 'PM'} CT)")
            continue
        k, _s, _ = state["markets"][m].learn(t)
        parts.append(f"{WB.name(m)} {trigger_word(k)}")
    return "Now: " + " · ".join(parts)


def from_shards(state):
    """The three markets' windows from the v1 state, in replay() form."""
    out = []
    for w in (state.get("windows") or {}).values():
        if w.get("series") not in MARKETS:
            continue
        s2 = w.get("s2") or {}
        st = s2.get("status")
        out.append(dict(m=w["series"], t=int(W._ts(w["open"])), quoted=st in ("filled", "no_fill"),
                        won=(s2.get("won") if st == "filled" else None), price=s2.get("price"), roi=s2.get("roi")))
    return out


def ledger(state, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    windows = from_shards(state)
    bets, st = replay(windows)
    start = int(W._ts(FROM))
    mine = [b for b in bets if b["t"] >= start]
    every, fixed = compare(windows, start)
    nxt = (int(now.timestamp()) // WINDOW_S + 1) * WINDOW_S
    per = {m: stats([b for b in mine if b["m"] == m]) for m in MARKETS}
    days = sorted({ct_day(b["t"]).isoformat() for b in mine})
    return dict(version=VERSION, registered=REGISTERED, **{"from": FROM}, markets=list(MARKETS),
                updated=now.isoformat(timespec="seconds"), now=now_line(st, nxt), now_for=nxt,
                record=stats(mine), per_market=per, every=stats(every), fixed2=stats(fixed),
                no_fills=sum(1 for b in mine if b["status"] == "no_fill"), days=days,
                bets=[dict(b, at=dt.datetime.fromtimestamp(b["t"], dt.timezone.utc).isoformat()) for b in mine][-200:])


def main():
    now = dt.datetime.now(dt.timezone.utc)
    first = (dt.datetime.fromisoformat(FROM) - dt.timedelta(days=PRIOR_DAYS + 1)).astimezone(W.ET).date()
    days = {(first + dt.timedelta(days=i)).isoformat() for i in range((now.astimezone(W.ET).date() - first).days + 1)}
    blob = ledger(W.load(days=days), now)
    W._write(PATH, blob)
    print(VERSION, (blob["record"] or {}).get("n", 0), "bets;", blob["now"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
