"""The table, as pre-registered: per variant, per period, v B1 (the same slides, no support cue) and B2 (random entry);
date-clustered means; Welch t (research, variant v B1); CLEAR / WATCH. Research first; the holdout column is read
once, at the end, in the same printout. -> results.json, table.md"""
import json
import math
from collections import defaultdict

T_CLEAR, T_WATCH, N_MIN = 3.1, 2.0, 30
d = json.load(open("trades.json"))


def by_date(rows):
    g = defaultdict(list)
    for r in rows:
        g[r["date"]].append(r["net"])
    return [sum(v) / len(v) for v in g.values()]


def stats(rows):
    if not rows:
        return dict(n=0, net=None, win=None, dates=0)
    dm = by_date(rows)
    return dict(n=len(rows), net=sum(r["net"] for r in rows) / len(rows), win=sum(r["net"] > 0 for r in rows) / len(rows),
                dates=len(dm), date_mean=sum(dm) / len(dm))


def welch(a, b):
    if len(a) < 2 or len(b) < 2:
        return None
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    va = sum((x - ma) ** 2 for x in a) / (len(a) - 1)
    vb = sum((x - mb) ** 2 for x in b) / (len(b) - 1)
    se = math.sqrt(va / len(a) + vb / len(b))
    return None if se == 0 else (ma - mb) / se


res = []
for key, rows in d.items():
    if key.endswith("|B1") or key.endswith("|B2"):
        continue
    slide = key.split("|")[0]
    b1, b2 = d[f"{slide}|B1"], d.get(key + "|B2", [])
    per = {}
    ok_periods = True
    for p in ("H1", "H2", "HO"):
        v = stats([r for r in rows if r["period"] == p])
        b = stats([r for r in b1 if r["period"] == p])
        r2 = stats([r for r in b2 if r["period"] == p])
        per[p] = dict(v=v, b1=b, b2=r2)
        if not (v["n"] and b["n"] and v["net"] > 0 and v["net"] > b["net"]):
            ok_periods = False
    rv = [r for r in rows if r["period"] in ("H1", "H2")]
    rb = [r for r in b1 if r["period"] in ("H1", "H2")]
    t = welch(by_date(rv), by_date(rb))
    rs, bs = stats(rv), stats(rb)
    margin = None if not rs["n"] or not bs["n"] else rs["net"] - bs["net"]
    n_ok = len(rv) >= N_MIN
    verdict = ("CLEARS" if n_ok and ok_periods and t is not None and t >= T_CLEAR else
               "WATCH" if n_ok and ok_periods and t is not None and t >= T_WATCH else "no")
    res.append(dict(key=key, research=rs, b1_research=bs, margin=margin, t=t, per=per, verdict=verdict,
                    b2_research=stats([r for r in d.get(key + "|B2", []) if r["period"] in ("H1", "H2")]),
                    all_periods_beat_b1=ok_periods))
res.sort(key=lambda r: -(r["margin"] if r["margin"] is not None else -9))
base = {s: {p: stats([r for r in d[f"{s}|B1"] if r["period"] == p]) for p in ("H1", "H2", "HO")} for s in ("S24", "S5D")}
json.dump(dict(variants=res, b1=base, n_variants=len(res)), open("results.json", "w"), indent=1)

f = lambda x: "—" if x is None else f"{x * 100:+.2f}%"
lines = ["| variant | n (res) | net res | B1 res | margin | t | H1 net / B1 | H2 net / B1 | holdout net / B1 | B2 res | verdict |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
for r in res:
    pp = r["per"]
    lines.append(f'| {r["key"]} | {r["research"]["n"]} | {f(r["research"]["net"])} | {f(r["b1_research"]["net"])} | '
                 f'{f(r["margin"])} | {"—" if r["t"] is None else f"{r[chr(116)]:+.2f}"} | '
                 + " | ".join(f'{pp[p]["v"]["n"]}: {f(pp[p]["v"]["net"])} / {f(pp[p]["b1"]["net"])}' for p in ("H1", "H2", "HO"))
                 + f' | {f(r["b2_research"]["net"])} | {r["verdict"]} |')
open("table.md", "w").write("\n".join(lines) + "\n")
print("B1 (same slides, no support cue):")
for s, v in base.items():
    print(" ", s, {p: (x["n"], f(x["net"])) for p, x in v.items()})
print("verdicts:", {v: sum(1 for r in res if r["verdict"] == v) for v in ("CLEARS", "WATCH", "no")})
print("\n".join(lines[:14]))
