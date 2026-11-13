#!/usr/bin/env python3
"""15-Minute rule C, version 2: "S&P 500 opening sweep" (Olu 2026-11-13, "build C v2"). Sandbox PAPER, no orders.

Spec and pre-registration, unchanged: docs/prereg_sw15_c2_2026-11-13.md (Fable's rule C review, docs/sw15_rule_c_study_2026-11-13.md).
Replaces rule C version 1 (the 15c underdog flip and its 25c companion), retired at sw15cuts round 5 with its whole record kept.

THE RULE, on every S&P 500 15-minute window (KXINX15M only): two resting bids, one on YES and one on NO, at the level, placed DELAY seconds after
the window opens and cancelled 5 minutes after the open if unfilled. The first to fill is the bet; the other is cancelled. Then a resting sell at
the multiple, from 60 seconds after the fill (fillsim honest-v1); if unsold with 1 minute left, sell at the bid (taker fee). Rows, each its own record:
    10c sell 3x (read at 40 settled bets), 15c sell 2x (read at 80), 25c sell 2x (read at 150).
The headline delay is 5 seconds; 2 and 30 seconds are comparison rows of every level.
FILLS: fillsim honest-v1 on Kalshi's trade prints: a buy only on a print strictly through the level, a sell only strictly through the target. No fee
on a resting fill; the taker fee on a sale at the bid. One window is one bet; the score clusters by clock hour.
ALSO LOGGED: seconds from the open to the fill, contracts printed through the level, the day's count of windows with a print through 10c/90c.
EARLY CLOSE: a level with fewer than one bet per trading day over any ten trading days is closed as "the opening has gone", whatever its return.
FRESH RECORD from FROM (the first S&P window after the build). Own ledger data/sw15c2_ledger.json; read hourly in swing15.yml.
"""
import datetime as dt
import json
import os
import sys

import fdr_check as FD
import fillsim as F
import fillsim_tape as TP
import swing15 as W

VERSION = "sw15-c2"
REGISTERED = "2026-11-13"
MARKET = "KXINX15M"
FROM = "2026-11-14T00:00:00+00:00"            # the first window after the build is the Monday cash open (= sw15cuts.CUT5_AT, when rule C v1 retires)
PATH = os.path.join(W.ROOT, "data", "sw15c2_ledger.json")
LEVELS = {"10": dict(level=0.10, mult=3.0, read_at=40), "15": dict(level=0.15, mult=2.0, read_at=80), "25": dict(level=0.25, mult=2.0, read_at=150)}
HEADLINE, COMPARE = 5, (2, 30)
DELAYS = (HEADLINE,) + COMPARE
CANCEL_S, SELL_UNTIL_S = 300, 840          # bids cancelled 5 minutes after the open; the sell stands to minute 14 (1 minute left)
EARLY_DAYS = 10
KEEP_SCORE = 1.5
MAX_PER_RUN = 60
LABELS = {"10": "C v2 · S&P 500 opening sweep, 10c sell 3x", "15": "C v2 · S&P 500 opening sweep, 15c sell 2x", "25": "C v2 · S&P 500 opening sweep, 25c sell 2x"}


def cell_key(lv, delay):
    return f"{lv}c_{delay}s"


def last_bid(w, side):
    """The bid on `side` at minute 14 (1 minute left) from the window's minute rows, or None."""
    m = w.get("minutes") or []
    if len(m) <= 14 or m[14] is None:
        return None
    yb, ya = m[14][1], m[14][2]
    if side == "yes":
        return yb
    return None if ya is None else round(1 - ya, 4)


def play(w, prints, level, mult, delay):
    """One window under one (level, multiple, delay): None for no bet, else dict(side, fill_s, roi, sold, qty). The research's run(), unchanged."""
    o = W._ts(w["open"])
    best = None
    for side in ("yes", "no"):
        e = F.resting_buy(prints, o + delay, level, side, F.stake_qty(level), F.HONEST, cancel_ts=o + CANCEL_S, check_cross=True)
        if e["qty"] > 1e-9:
            ft = e["fill_ts"] or e["first_ts"]
            if best is None or ft < best[0]:
                best = (ft, side)
    if not best:
        return None
    ft, side = best
    target = min(0.99, round(level * mult, 4))
    res = F.trade(prints, side, dict(kind="rest", ts=o + delay, price=level, cancel_ts=o + CANCEL_S),
                  [dict(target=target, share=1.0, until_ts=o + SELL_UNTIL_S)], payout=1.0 if w["result"] == side else 0.0, rules=F.HONEST)
    if res["status"] == "no_entry":
        return None
    sold = res["sold"] if isinstance(res.get("sold"), (int, float)) else sum(x["sold"] for x in res["legs"])
    q = res["qty"]
    frac = sold / q if q else 0.0
    if frac >= 1 - 1e-6:
        roi = res["roi"]
    else:
        bid = last_bid(w, side)
        rest_val = (bid - F.fee(bid)) if bid and bid > 0 else (1.0 if w["result"] == side else 0.0)
        roi = (frac * target + (1 - frac) * rest_val) / level - 1
    through = round(sum(p[2] for p in prints if o + delay <= p[0] < o + CANCEL_S and (p[1] < level - 1e-9 if side == "yes" else 1 - p[1] < level - 1e-9)), 2)
    return dict(side=side, fill_s=round(ft - o, 1), roi=round(roi, 4), sold=frac >= 1 - 1e-6, qty=q, through=through)


def sweep(prints, o):
    """True when a print went through 10c or 90c from 5 seconds to 5 minutes after the open."""
    return any(o + 5 <= p[0] < o + CANCEL_S and (p[1] <= 0.10 + 1e-9 or p[1] >= 0.90 - 1e-9) for p in prints)


def empty():
    return dict(version=VERSION, registered=REGISTERED, since=FROM, windows={}, updated=None)


def load(path=PATH):
    try:
        with open(path) as f:
            return dict(empty(), **json.load(f))
    except (OSError, ValueError):
        return empty()


def save(state, path=PATH):
    W._write(path, state)


def process(state, win, tape=TP.settled_tape):
    """Read one graded window into the ledger once."""
    o = W._ts(win["open"])
    prints = tape(win["ticker"])
    cells = {}
    for lv, c in LEVELS.items():
        for delay in DELAYS:
            cells[cell_key(lv, delay)] = play(win, prints, c["level"], c["mult"], delay)
    state["windows"][win["ticker"]] = dict(open=win["open"], day=win["day"], hour=win["open"][:13], result=win["result"], prints=len(prints),
                                           sweep=sweep(prints, o), cells=cells)


def run(state, windows, now=None, tape=TP.settled_tape):
    """Every graded S&P window opening at or after FROM that the ledger has not read, oldest first."""
    now = now or dt.datetime.now(dt.timezone.utc)
    start = W._ts(FROM)
    todo = sorted((w for w in windows if w.get("series") == MARKET and w.get("result") in ("yes", "no") and W._ts(w["open"]) >= start
                   and w["ticker"] not in state["windows"]), key=lambda w: w["open"])
    done, errs = 0, []
    for w in todo[:MAX_PER_RUN]:
        try:
            process(state, w, tape)
            done += 1
        except Exception as exc:                                # noqa: BLE001  (one window never stops the rest; it is read next hour)
            errs.append(f'{w["ticker"]}: {str(exc)[:60]}')
    state["updated"] = now.isoformat(timespec="seconds")
    state["errors"] = errs[:10]
    return done


# ---------------------------------------------------------------- the record
def trading_days(state):
    return sorted({v["day"] for v in state["windows"].values()})


def closed_on(state, lv):
    """The trading day a level closed as "the opening has gone" (fewer than one headline bet per trading day over any ten trading days), or None."""
    days = trading_days(state)
    n = {d: 0 for d in days}
    for v in state["windows"].values():
        if v["cells"].get(cell_key(lv, HEADLINE)):
            n[v["day"]] += 1
    for i in range(len(days) - EARLY_DAYS + 1):
        span = days[i:i + EARLY_DAYS]
        if sum(n[d] for d in span) < EARLY_DAYS:
            return span[-1]
    return None


def cell_rows(state, lv, delay):
    """[(roi, hour, window)] for one cell, windows up to the level's close (a closed level takes no later bets)."""
    stop = closed_on(state, lv)
    out = []
    for tk, v in sorted(state["windows"].items(), key=lambda kv: kv[1]["open"]):
        if stop and v["day"] > stop:
            continue
        x = v["cells"].get(cell_key(lv, delay))
        if x:
            out.append((x["roi"], v["hour"], dict(v, ticker=tk, **x)))
    return out


def stat(rows):
    s = FD.lane_stats([(r[0], r[1]) for r in rows])
    n = len(rows)
    s["sold"] = sum(1 for r in rows if r[2]["sold"])
    s["fill_s"] = sorted(r[2]["fill_s"] for r in rows)[n // 2] if n else None
    return s


def records(state):
    """{level: dict(headline, compare={delay: stat}, closed_on, read)} for the three rows."""
    out = {}
    for lv, c in LEVELS.items():
        head = stat(cell_rows(state, lv, HEADLINE))
        cmp = {d: stat(cell_rows(state, lv, d)) for d in COMPARE}
        out[lv] = dict(headline=head, compare=cmp, closed_on=closed_on(state, lv), read_at=c["read_at"], read=read_text(lv, head, cmp[30], closed_on(state, lv)))
    sw = [v for v in state["windows"].values()]
    out["days"] = len(trading_days(state))
    out["windows"] = len(sw)
    out["sweep_days"] = {d: sum(1 for v in sw if v["day"] == d and v["sweep"]) for d in trading_days(state)}
    return out


def read_text(lv, head, c30, closed):
    """The pre-registered read: once at the row's bet count; keep needs return above zero, score 1.5+, and the 30-second row above zero."""
    n, need = head["n"], LEVELS[lv]["read_at"]
    if closed:
        return f"closed {closed}: the opening has gone"
    if n < need:
        return f"too early ({n} of {need} settled bets; read once at {need})"
    ok = (head["roi"] or 0) > 0 and (head["t"] or 0) >= KEEP_SCORE and (c30["roi"] or 0) > 0
    if (head["roi"] or 0) <= 0:
        return "read now: retire (return zero or below)"
    return "read now: keep (return above zero, score 1.5+, the 30-second row above zero)" if ok else "read now: not kept (return above zero but the score or the 30-second row falls short)"


def main():
    now = dt.datetime.now(dt.timezone.utc)
    start = dt.datetime.fromisoformat(FROM).astimezone(W.ET).date()
    days = {(start + dt.timedelta(days=i)).isoformat() for i in range(max(0, (now.astimezone(W.ET).date() - start).days) + 2)}
    state = load()
    n = run(state, _windows(days), now)
    save(state)
    r = records(state)
    print(VERSION, "new", n, {lv: r[lv]["headline"]["n"] for lv in LEVELS}, state.get("errors"))
    return 0


def _windows(days):
    st = W.load(days=days)
    return [dict(w, ticker=k) for k, w in (st.get("windows") or {}).items()]


if __name__ == "__main__":
    sys.exit(main())
