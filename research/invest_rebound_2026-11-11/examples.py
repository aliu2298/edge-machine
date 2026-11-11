"""Worked examples: SPCX and NVDA, Nov 9-11 2026 — the slide, the support levels near it, every touch, what confirmed
(or failed), and what the variants would have done. -> examples.json and a printout."""
import datetime as dt
import json
import sys

import numpy as np

import research as R

DAYS = (dt.date(2026, 11, 9), dt.date(2026, 11, 10), dt.date(2026, 11, 11))
out = {}
trades = json.load(open("trades.json"))
for sym in ("SPCX", "NVDA"):
    S = R.Sym(sym)
    rows = []
    for s in range(S.ns):
        d = dt.date.fromordinal(int(S.ddate[s]))
        if d not in DAYS:
            continue
        a, b = S.s_start[s], S.s_end[s]
        lv, tested = S.levels(s)
        info = dict(day=str(d), open=float(S.dO[s]), high=float(S.dH[s]), low=float(S.dL[s]), close=float(S.dC[s]),
                    worst_24h=float(min(S.c[a:b] / S.H24[a:b]) - 1), worst_5d=float(min(S.c[a:b] / S.H5[a:b]) - 1),
                    s24_minutes=int(S.slide["S24"][a:b].sum()), s5d_minutes=int(S.slide["S5D"][a:b].sum()),
                    levels=sorted({(round(float(x), 2), m) for x, m in lv if 0.75 * S.dL[s] < x < 1.1 * S.dH[s]}))
        for slide in ("S24", "S5D"):
            for strong in (False, True):
                tl = [x for x in S.touches(slide, strong) if a <= x[0] < b]
                seen, out_t = set(), []
                for i, L, H in tl:
                    if (round(L, 2)) in seen:
                        continue
                    seen.add(round(L, 2))
                    conf, wend = S.confirm(i, L)
                    out_t.append(dict(at=R.et_dt(S.t[i]).strftime("%H:%M ET"), level=round(L, 2), slide_high=round(H, 2),
                                      strength=S.strength(L, lv, [p[1] for p in S.ph if p[0] < i and s - 20 <= p[2] <= s], tested),
                                      confirmations={k: R.et_dt(S.t[v]).strftime("%H:%M") for k, v in conf.items()},
                                      window_end=R.et_dt(S.t[wend]).strftime("%H:%M")))
                info[f"touches_{slide}_{'strong' if strong else 'all'}"] = out_t
        info["trades"] = {k: [dict(entry=R.et_dt(r["entry_t"]).strftime("%b %d %H:%M"), px=round(r["entry"], 2),
                                   exit=R.et_dt(r["exit_t"]).strftime("%b %d %H:%M"), out=round(r["exit"], 2),
                                   why=r["why"], net=r["net"], L=round(r.get("L", 0), 2))
                              for r in v if r["sym"] == sym and dt.date.fromordinal(r["date"]) == d]
                          for k, v in trades.items() if not k.endswith("B2")}
        info["trades"] = {k: v for k, v in info["trades"].items() if v}
        rows.append(info)
    out[sym] = rows
json.dump(out, open("examples.json", "w"), indent=1, default=str)
for sym, rows in out.items():
    for r in rows:
        print(sym, r["day"], f'O {r["open"]:.2f} H {r["high"]:.2f} L {r["low"]:.2f} C {r["close"]:.2f}',
              f'worst v 24h high {r["worst_24h"] * 100:+.1f}%  v 5-day high {r["worst_5d"] * 100:+.1f}%',
              f'slide minutes S24 {r["s24_minutes"]} S5D {r["s5d_minutes"]}')
        for k in ("touches_S24_all", "touches_S5D_all"):
            for t in r[k]:
                print("   ", k, t)
        for k, v in r["trades"].items():
            print("    trade", k, v)
