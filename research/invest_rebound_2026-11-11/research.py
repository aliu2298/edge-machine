"""Rebound after a slide — the research run, exactly as PREREGISTRATION.md (fixed before any result).

python research.py            -> trades.json (every variant's and baseline's trades) and prints progress
"""
import json
import math
import os
import random
import sys
import datetime as dt
from zoneinfo import ZoneInfo

import numpy as np

ET = ZoneInfo("America/New_York")
SY = [s.strip() for s in open("symbols.txt") if s.strip()]
TOL = 0.0075
FAIL = 0.995
WINDOW = 120
COST = 0.0030
HOLD = {"S24": 390, "S5D": 1950}
CONFS = ("C1a", "C1b", "C2", "C3", "C4", "ANY1", "ANY2")
METHODS = ("PD", "PH", "PDL", "PWL", "MA50", "MA200", "GAP")


def load(sym):
    parts = []
    for d in ("bars_cached", "bars_new"):
        p = f"{d}/{sym}.npz"
        if os.path.exists(p):
            z = np.load(p)
            parts.append(np.column_stack([z["t"], z["o"], z["h"], z["l"], z["c"], z["v"]]))
    a = np.concatenate(parts)
    a = a[np.argsort(a[:, 0], kind="stable")]
    _, keep = np.unique(a[:, 0], return_index=True)
    a = a[keep]
    a = a[a[:, 0] >= int(dt.datetime(2023, 1, 3, tzinfo=dt.timezone.utc).timestamp() // 60)]
    return a


def et_dt(m):
    return dt.datetime.fromtimestamp(int(m) * 60, ET)


def rnd_step(p):
    return 1 if p < 50 else 5 if p < 200 else 10 if p < 1000 else 50


def rsi(closes, n=14):
    out = np.full(len(closes), np.nan)
    if len(closes) <= n:
        return out
    d = np.diff(closes)
    up, dn = np.clip(d, 0, None), np.clip(-d, 0, None)
    au, ad = up[:n].mean(), dn[:n].mean()
    for i in range(n, len(d) + 1):
        if i > n:
            au = (au * (n - 1) + up[i - 1]) / n
            ad = (ad * (n - 1) + dn[i - 1]) / n
        out[i] = 100.0 if ad == 0 else 100 - 100 / (1 + au / ad)
    return out


class Sym:
    def __init__(self, sym):
        a = load(sym)
        self.sym = sym
        self.t, self.o, self.h, self.l, self.c, self.v = (a[:, i] for i in range(6))
        self.t = self.t.astype(np.int64)
        days = [et_dt(m).date() for m in self.t]
        self.date = np.array([d.toordinal() for d in days])
        self.mod = np.array([et_dt(m).hour * 60 + et_dt(m).minute for m in self.t])
        _, s_start = np.unique(self.date, return_index=True)
        self.s_start = s_start
        self.s_end = np.append(s_start[1:], len(self.t))
        self.sid = np.repeat(np.arange(len(s_start)), self.s_end - s_start)
        self.ns = len(s_start)
        self.dO = self.o[s_start]
        self.dC = self.c[self.s_end - 1]
        self.dH = np.maximum.reduceat(self.h, s_start)
        self.dL = np.minimum.reduceat(self.l, s_start)
        self.ddate = self.date[s_start]
        self.iso_week = np.array([dt.date.fromordinal(int(x)).isocalendar()[:2] for x in self.ddate])
        self._bars()
        self._slides()

    # -------- 5-, 15-minute and hourly bars (bucketed within the session)
    def _bars(self):
        self.b5 = (self.sid * 100 + (self.mod - 570) // 5)
        self.b15 = (self.sid * 100 + (self.mod - 570) // 15)
        self.b60 = (self.sid * 100 + (self.mod - 570) // 60)
        # 15-minute closes and RSI(14), continuous across sessions
        k15, i15 = np.unique(self.b15, return_index=True)
        last15 = np.append(i15[1:], len(self.t)) - 1
        self.k15, self.c15_end = k15, last15
        self.rsi15 = rsi(self.c[last15])
        # 5-minute bars
        k5, i5 = np.unique(self.b5, return_index=True)
        e5 = np.append(i5[1:], len(self.t))
        self.k5, self.i5, self.e5 = k5, i5, e5
        self.l5 = np.minimum.reduceat(self.l, i5)
        self.h5 = np.maximum.reduceat(self.h, i5)
        self.o5 = self.o[i5]
        self.c5 = self.c[e5 - 1]
        self.v5 = np.add.reduceat(self.v, i5)
        # hourly bars and their 5-bar pivot lows, each with the minute it is confirmed (end of the bar 2 later)
        k60, i60 = np.unique(self.b60, return_index=True)
        e60 = np.append(i60[1:], len(self.t))
        l60 = np.minimum.reduceat(self.l, i60)
        self.ph = []                                      # (confirm_minute_index, level, session)
        for j in range(2, len(k60) - 2):
            if l60[j] < l60[j - 1] and l60[j] < l60[j - 2] and l60[j] < l60[j + 1] and l60[j] < l60[j + 2]:
                self.ph.append((e60[j + 2] - 1, l60[j], self.sid[i60[j]]))
        self.ph = np.array(self.ph) if self.ph else np.zeros((0, 3))

    # -------- the slide flags
    def _slides(self):
        n = len(self.t)
        cum = np.empty(n)
        for s in range(self.ns):
            a, b = self.s_start[s], self.s_end[s]
            cum[a:b] = np.maximum.accumulate(self.h[a:b])
        # S24: today's high so far v the previous session's highs after (t - 24h)
        prev = np.full(n, -np.inf)
        for s in range(1, self.ns):
            a, b = self.s_start[s], self.s_end[s]
            pa, pb = self.s_start[s - 1], self.s_end[s - 1]
            suf = np.maximum.accumulate(self.h[pa:pb][::-1])[::-1]
            # the first index of the previous session with t > t_now - 1440
            j = np.searchsorted(self.t[pa:pb], self.t[a:b] - 1440, side="right")
            ok = j < (pb - pa)
            prev[a:b][ok] = suf[j[ok]]
        self.H24 = np.maximum(cum, prev)
        # S5D: the previous 4 sessions' highs and today's so far
        prev4 = np.full(n, -np.inf)
        for s in range(self.ns):
            lo = max(0, s - 4)
            if s > 0:
                prev4[self.s_start[s]:self.s_end[s]] = self.dH[lo:s].max() if s > lo else -np.inf
        self.H5 = np.maximum(cum, prev4)
        self.slide = {"S24": self.c <= 0.95 * self.H24, "S5D": self.c <= 0.90 * self.H5}
        self.H = {"S24": self.H24, "S5D": self.H5}

    # -------- support levels for a session (from data before it), with method tags
    def levels(self, s):
        if hasattr(self, "_lv") and s in self._lv:
            return self._lv[s]
        self._lv = getattr(self, "_lv", {})
        out = []                                               # (level, method)
        for k in range(max(2, s - 120), s - 2):
            if (self.dL[k] < self.dL[k - 1] and self.dL[k] < self.dL[k - 2] and self.dL[k] < self.dL[k + 1]
                    and self.dL[k] < self.dL[k + 2]):
                out.append((self.dL[k], "PD"))
        if s >= 1:
            out.append((self.dL[s - 1], "PDL"))
            wk = tuple(self.iso_week[s])
            prev_week = [k for k in range(max(0, s - 10), s) if tuple(self.iso_week[k]) != wk]
            if prev_week:
                w = tuple(self.iso_week[prev_week[-1]])
                out.append((min(self.dL[k] for k in prev_week if tuple(self.iso_week[k]) == w), "PWL"))
        if s >= 50:
            out.append((self.dC[s - 50:s].mean(), "MA50"))
        if s >= 200:
            out.append((self.dC[s - 200:s].mean(), "MA200"))
        for k in range(max(1, s - 60), s):
            if self.dO[k] >= 1.01 * self.dC[k - 1]:
                out.append((self.dC[k - 1], "GAP"))
        tested = self.dL[max(0, s - 60):s]
        self._lv[s] = (out, tested)
        return self._lv[s]

    def strength(self, L, levels, ph_now, tested):
        m = {meth for x, meth in levels if abs(x - L) <= TOL * L}
        if any(abs(x - L) <= TOL * L for x in ph_now):
            m.add("PH")
        return len(m) + int(bool(np.any(np.abs(tested - L) <= TOL * L)))

    def touches(self, slide, strong):
        """Every minute in a slide whose low is within TOL of a support level: (i, L, H)."""
        idx = np.nonzero(self.slide[slide])[0]
        out = []
        H = self.H[slide]
        ph = self.ph
        for i in idx:
            s = self.sid[i]
            lv, tested = self.levels(s)
            hi, lo = H[i], 0.8 * H[i]
            low = self.l[i]
            ph_now = [p[1] for p in ph if p[0] < i and s - 20 <= p[2] <= s] if len(ph) else []
            cand = [(x, m) for x, m in lv] + [(x, "PH") for x in ph_now]
            st = rnd_step(low)
            for k in (math.floor(low / st), math.ceil(low / st)):
                cand.append((k * st, "RND"))
            hit = [x for x, _m in cand if lo < x < hi and abs(low - x) <= TOL * x]
            if not hit:
                continue
            L = max(hit)
            if strong and self.strength(L, lv, ph_now, tested) < 2:
                continue
            out.append((int(i), float(L), float(H[i])))
        return out

    # -------- confirmations for one touch
    def confirm(self, i, L):
        s = self.sid[i]
        end = min(i + WINDOW, self.s_end[s] - 1)
        cl = self.c[i + 1:end + 1]
        bad = np.nonzero(cl < FAIL * L)[0]
        fail = i + 1 + int(bad[0]) if len(bad) else None
        lim = (fail - 1) if fail is not None else end
        conf = {}
        if i + 15 <= lim:
            conf["C1a"] = i + 15
        if i + 30 <= lim:
            conf["C1b"] = i + 30
        # C3: a close above the highest high of the 30 minutes before the touch
        a = max(self.s_start[s], i - 30)
        if a < i:
            hh = self.h[a:i].max()
            up = np.nonzero(self.c[i + 1:lim + 1] > hh)[0]
            if len(up):
                conf["C3"] = i + 1 + int(up[0])
        # C2: two completed 5-minute bars with higher lows after the lowest one since the touch
        j0 = np.searchsorted(self.k5, self.b5[i])
        mn, cnt = None, 0
        for j in range(j0, len(self.k5)):
            if self.e5[j] - 1 > lim:
                break
            if mn is None or self.l5[j] <= mn:
                mn, cnt = self.l5[j], 0
                continue
            cnt += 1
            if cnt >= 2:
                conf["C2"] = int(self.e5[j] - 1)
                break
        # C4: 15-minute RSI(14) below 30 then higher, or a 5-minute volume spike with a long lower wick
        c4 = []
        q0 = np.searchsorted(self.k15, self.b15[i])
        for q in range(max(1, q0), len(self.k15)):
            e = int(self.c15_end[q])
            if e > lim:
                break
            if e > i and self.rsi15[q - 1] < 30 and self.rsi15[q] > self.rsi15[q - 1]:
                c4.append(e)
                break
        for j in range(j0 + 1, len(self.k5)):
            e = int(self.e5[j] - 1)
            if e > lim:
                break
            if j >= 20:
                rng = self.h5[j] - self.l5[j]
                avg = self.v5[j - 20:j].mean()
                if (rng > 0 and self.v5[j] >= 2 * avg and (min(self.o5[j], self.c5[j]) - self.l5[j]) >= 0.5 * rng
                        and self.c5[j] >= self.l5[j] + 0.5 * rng):
                    c4.append(e)
                    break
        if c4:
            conf["C4"] = min(c4)
        base = sorted(conf[k] for k in ("C1a", "C2", "C3", "C4") if k in conf)
        if base:
            conf["ANY1"] = base[0]
        if len(base) >= 2:
            conf["ANY2"] = base[1]
        return conf, (fail if fail is not None else end)

    # -------- one trade's exit
    def exit(self, e, stop, target, hold):
        """Enter at the open of bar e; exits as registered. -> (exit_index, exit_price, why)."""
        last = min(e + hold, len(self.t)) - 1
        o, h, l = self.o[e:last + 1], self.h[e:last + 1], self.l[e:last + 1]
        for k in range(len(o)):
            if o[k] <= stop:
                return e + k, o[k], "stop"
            if l[k] <= stop:
                return e + k, stop, "stop"
            if o[k] >= target:
                return e + k, o[k], "target"
            if h[k] >= target:
                return e + k, target, "target"
        return last, self.c[last], "time"

    def targets(self, i, L, H, entry):
        half = L + 0.5 * (H - L)
        s = self.sid[i]
        lv, _ = self.levels(s)
        above = sorted(x for x, _m in lv if entry * 1.01 < x < H)
        st = rnd_step(entry)
        k = math.floor(entry * 1.01 / st) + 1
        while k * st < H:
            above.append(k * st)
            k += 1
        above = sorted(above)
        return {"T_half": half, "T_break": above[0] if above else half}


def period(dord):
    d = dt.date.fromordinal(int(dord))
    if d <= dt.date(2024, 6, 30):
        return "H1"
    if d <= dt.date(2026, 8, 7):
        return "H2"
    return "HO"


def trade_row(S, e, x, px_in, px_out, why, extra):
    gross = px_out / px_in - 1
    return dict(sym=S.sym, entry_t=int(S.t[e]), exit_t=int(S.t[x]), date=int(S.date[e]), period=period(S.date[e]),
                entry=float(px_in), exit=float(px_out), why=why, gross=round(float(gross), 6),
                net=round(float(gross - COST), 6), **extra)


def run_symbol(sym, rng):
    S = Sym(sym)
    out = {}
    for slide in ("S24", "S5D"):
        block = 1 if slide == "S24" else 5
        hold = HOLD[slide]
        # B1: the first slide minute per session / per 5 sessions, no support cue
        b1, nxt = [], -1
        for i in np.nonzero(S.slide[slide])[0]:
            s = S.sid[i]
            if s < nxt or i + 1 >= len(S.t):
                continue
            e = i + 1
            px = S.o[e]
            H = S.H[slide][i]
            x, pout, why = S.exit(e, px * 0.97, px + 0.5 * (H - px), hold)
            b1.append(trade_row(S, e, x, px, pout, why, dict(H=float(H))))
            nxt = s + block
        out[f"{slide}|B1"] = b1
        for strong in (False, True):
            touches = S.touches(slide, strong)
            cache = {}
            for conf_name in CONFS:
                for tgt in ("T_half", "T_break"):
                    key = f"{slide}|{conf_name}|{'strong' if strong else 'all'}|{tgt}"
                    rows, busy, nxt = [], -1, -1
                    for n_, (i, L, H) in enumerate(touches):
                        s = S.sid[i]
                        if i <= busy or s < nxt:
                            continue
                        if n_ not in cache:
                            cache[n_] = S.confirm(i, L)
                        conf, wend = cache[n_]
                        c = conf.get(conf_name)
                        if c is None or c + 1 >= len(S.t) or S.sid[c + 1] != s and False:
                            busy = wend
                            continue
                        e = c + 1
                        px = S.o[e]
                        stop = 0.99 * L
                        T = S.targets(i, L, H, px)[tgt]
                        x, pout, why = S.exit(e, stop, T, hold)
                        rows.append(trade_row(S, e, x, px, pout, why, dict(L=L, H=H, touch_t=int(S.t[i]),
                                                                          stop_pct=float(stop / px - 1),
                                                                          tgt_pct=float(T / px - 1))))
                        nxt = s + block
                        busy = x
                    out[key] = rows
    # B2: random entry for every rule trade (same minute of day, a random other session within +-30)
    for key, rows in list(out.items()):
        if key.endswith("|B1"):
            continue
        hold = HOLD[key.split("|")[0]]
        b2 = []
        for r in rows:
            e0 = int(np.searchsorted(S.t, r["entry_t"]))
            s0 = S.sid[e0]
            choices = [s for s in range(max(0, s0 - 30), min(S.ns, s0 + 31)) if s != s0]
            if not choices:
                continue
            s = rng.choice(choices)
            a, b = S.s_start[s], S.s_end[s]
            e = a + int(np.searchsorted(S.mod[a:b], S.mod[e0]))
            if e >= b or e >= len(S.t):
                continue
            px = S.o[e]
            x, pout, why = S.exit(e, px * (1 + r["stop_pct"]), px * (1 + r["tgt_pct"]), hold)
            b2.append(trade_row(S, e, x, px, pout, why, dict(of=r["entry_t"])))
        out[key + "|B2"] = b2
    return out


if __name__ == "__main__":
    only = sys.argv[1:] or SY
    rng = random.Random(20261111)
    allout = {}
    for sym in only:
        res = run_symbol(sym, rng)
        for k, v in res.items():
            allout.setdefault(k, []).extend(v)
        print(sym, sum(len(v) for k, v in res.items() if not k.endswith("B2")), flush=True)
    json.dump(allout, open("trades.json" if not sys.argv[1:] else f"trades_{'_'.join(only)}.json", "w"))
    print("DONE")
