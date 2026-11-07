"""The pre-registered big-move grid (PREREGISTRATION.md). Reads bars/*.npz, writes events.npz and grid.json.

Run: .venv/bin/python grid.py
"""
import datetime as dt
import glob
import json
import math
import os
from zoneinfo import ZoneInfo

import numpy as np

ET = ZoneInfo("America/New_York")
SIZES = (0.03, 0.05, 0.08)
WINDOWS = ("1h", "day", "gap")
TPS = (0.02, 0.04, 0.08)
SLS = (0.02, 0.04)
HOLDS = (("1h", 60), ("1d", 390), ("5d", 1950))
COST = 0.0030                     # 0.12% taker + 0.03% half-spread, each side
N_BASE = 5
SEED = 20261106
PERIODS = (("h1", "2023-01-01", "2024-06-30"), ("h2", "2024-07-01", "2025-12-31"), ("ho", "2026-01-01", "2026-12-31"))
EXITS = [(tp, sl, hn, hb) for tp in TPS for sl in SLS for hn, hb in HOLDS]   # 18


def sessions(t):
    """session id per bar, the session's ET date, and each bar's ET minute of day."""
    brk = np.r_[0, np.nonzero(np.diff(t) > 600)[0] + 1]
    sid = np.zeros(len(t), dtype=np.int64)
    sid[brk[1:]] = 1
    sid = np.cumsum(sid)
    dates, mod = [], np.empty(len(t), dtype=np.int64)
    ends = np.r_[brk[1:], len(t)]
    for s, (a, b) in enumerate(zip(brk, ends)):
        d0 = dt.datetime.fromtimestamp(int(t[a]) * 60, ET)
        open_ = dt.datetime(d0.year, d0.month, d0.day, 9, 30, tzinfo=ET)
        o_min = int(open_.timestamp() // 60)
        mod[a:b] = 570 + (t[a:b] - o_min)
        dates.append(d0.date().isoformat())
    return sid, brk, ends, dates, mod


def simulate(o, h, l, c, e, side):
    """Net return of every exit in EXITS for an entry at bar e (open), side +1 Up / -1 Down."""
    P = o[e]
    end = min(len(o), e + 1950)
    oo, hh, ll, cc = o[e:end] / P - 1, h[e:end] / P - 1, l[e:end] / P - 1, c[e:end] / P - 1
    if side < 0:                                   # a Down position's return on each path point
        oo, hh, ll, cc = -oo, -ll, -hh, -cc        # favourable = price falls
    n = len(oo)
    out = np.empty(len(EXITS))
    big = 10 ** 9
    first_sl = {}
    for sl in SLS:
        hit = np.nonzero(ll <= -sl)[0]
        first_sl[sl] = hit[0] if len(hit) else big
    first_tp = {}
    for tp in TPS:
        hit = np.nonzero(hh >= tp)[0]
        first_tp[tp] = hit[0] if len(hit) else big
    for i, (tp, sl, _hn, hb) in enumerate(EXITS):
        ks, kt, last = first_sl[sl], first_tp[tp], min(hb, n) - 1
        if ks <= kt and ks <= last:                # stop first, also when both touch the same bar
            r = min(oo[ks], -sl)
        elif kt < ks and kt <= last:
            r = max(oo[kt], tp)
        else:
            r = cc[last]
        out[i] = r - COST
    return out


def events_for(sym, rng):
    z = np.load(f"bars/{sym}.npz")
    t, o, h, l, c = z["t"], z["o"], z["h"], z["l"], z["c"]
    sid, starts, ends, dates, mod = sessions(t)
    rows = []                                     # (window, size, dir, date, sym, move, entry_idx, base_idx[5])

    def base_idx(s, lo_mod, hi_mod, e=None):
        """Amendment 2026-11-06 (A1): the event's own minute of day on 5 random OTHER sessions of the same stock
        within +/-30 sessions. The same-session draw of v1 entered before the move it was testing."""
        want = mod[e]
        pool = [x for x in range(max(1, s - 30), min(len(starts), s + 31)) if x != s]
        picks = []
        for x in rng.permutation(pool):
            a, b = starts[x], ends[x]
            k = np.nonzero(mod[a:b] >= want)[0]
            if len(k) and mod[a + k[0]] - want <= 2 and a + k[0] < b:
                picks.append(a + k[0])
            if len(picks) == N_BASE:
                break
        return np.array(picks) if len(picks) == N_BASE else None

    for s in range(1, len(starts)):
        a, b = starts[s], ends[s]
        prev = c[starts[s] - 1]
        # gap: first bar must be the 9:30 bar
        if mod[a] == 570 and b - a > 2 and mod[a + 1] <= 575:
            r = o[a] / prev - 1
            bi = base_idx(s, 571, 956, a + 1)
            for X in SIZES:
                for d, hit in (("drop", r <= -X), ("jump", r >= X)):
                    if hit and bi is not None:
                        rows.append(("gap", X, d, dates[s], sym, r, a + 1, bi))
        # day: the 15:55 bar v the previous close, entry 15:56
        k = np.nonzero(mod[a:b] == 955)[0]
        if len(k) and a + k[0] + 1 < b:
            i = a + k[0]
            r = c[i] / prev - 1
            bi = base_idx(s, 571, 956, i + 1)
            for X in SIZES:
                for d, hit in (("drop", r <= -X), ("jump", r >= X)):
                    if hit and bi is not None:
                        rows.append(("day", X, d, dates[s], sym, r, i + 1, bi))
        # 1h: close v the close 60 minutes earlier, same session; first crossing of the day
        tt = t[a:b]
        j = np.searchsorted(tt, tt - 60)
        valid = (tt[np.minimum(j, len(tt) - 1)] == tt - 60) & (mod[a:b] >= 630) & (mod[a:b] <= 958)
        valid &= np.arange(b - a) + 1 < (b - a)
        if valid.any():
            r = np.where(valid, c[a:b] / c[a + np.minimum(j, len(tt) - 1)] - 1, 0.0)
            for X in SIZES:
                for d, hit in (("drop", r <= -X), ("jump", r >= X)):
                    w = np.nonzero(hit & valid)[0]
                    bi = base_idx(s, 631, 958, a + w[0] + 1) if len(w) else None
                    if len(w) and bi is not None:
                        rows.append(("1h", X, d, dates[s], sym, float(r[w[0]]), a + w[0] + 1, bi))
    out = []
    for (win, X, d, date, sym_, r, e, bi) in rows:
        up = simulate(o, h, l, c, e, +1)
        dn = simulate(o, h, l, c, e, -1)
        bup = np.mean([simulate(o, h, l, c, x, +1) for x in bi], axis=0)
        bdn = np.mean([simulate(o, h, l, c, x, -1) for x in bi], axis=0)
        # fade: drop->Up, jump->Down ; follow: the other side
        fade, fade_b = (up, bup) if d == "drop" else (dn, bdn)
        follow, follow_b = (dn, bdn) if d == "drop" else (up, bup)
        out.append(dict(win=win, size=X, dir=d, date=date, sym=sym_, move=r,
                        fade=fade, fade_b=fade_b, follow=follow, follow_b=follow_b))
    return out


def tstat_by_date(vals, dates):
    by = {}
    for v, d in zip(vals, dates):
        by.setdefault(d, []).append(v)
    m = np.array([np.mean(x) for x in by.values()])
    if len(m) < 3 or m.std(ddof=1) == 0:
        return None, len(m)
    return float(m.mean() / (m.std(ddof=1) / math.sqrt(len(m)))), len(m)


def main():
    rng = np.random.default_rng(SEED)
    ev = []
    for f in sorted(glob.glob("bars/*.npz")):
        sym = os.path.basename(f)[:-4]
        got = events_for(sym, rng)
        ev += got
        print(sym, len(got), flush=True)
    print("events", len(ev))
    cells = []
    for win in WINDOWS:
        for X in SIZES:
            for d in ("drop", "jump"):
                E = [e for e in ev if e["win"] == win and e["size"] == X and e["dir"] == d]
                for act in ("fade", "follow"):
                    for i, (tp, sl, hn, _hb) in enumerate(EXITS):
                        cell = dict(win=win, size=X, dir=d, act=act, tp=tp, sl=sl, hold=hn)
                        for pname, p0, p1 in PERIODS + (("res", "2023-01-01", "2025-12-31"),):
                            sub = [e for e in E if p0 <= e["date"] <= p1]
                            net = [e[act][i] for e in sub]
                            mar = [e[act][i] - e[act + "_b"][i] for e in sub]
                            dates = [e["date"] for e in sub]
                            tm, nd = tstat_by_date(mar, dates) if sub else (None, 0)
                            cell[pname] = dict(n=len(sub), days=nd,
                                               win=(float(np.mean(np.array(net) > 0)) if sub else None),
                                               net=(float(np.mean(net)) if sub else None),
                                               base=(float(np.mean([e[act + "_b"][i] for e in sub])) if sub else None),
                                               margin=(float(np.mean(mar)) if sub else None), t_margin=tm)
                        cells.append(cell)
    json.dump(dict(n_cells=len(cells), n_events=len(ev), cells=cells), open("grid.json", "w"))
    # per-event file for later reads (no per-trade dollar amounts)
    json.dump([dict(win=e["win"], size=e["size"], dir=e["dir"], date=e["date"], sym=e["sym"], move=e["move"])
               for e in ev], open("events.json", "w"))
    print("cells", len(cells))


if __name__ == "__main__":
    main()
