"""Apply the pre-registered bar to grid.json -> research.json (for the page) and table.md."""
import json
import sys

T_CLEAR = 3.8
MIN_N = 30
g = json.load(open("grid.json"))
cells = g["cells"]


def ok(p):
    return bool(p and p["n"] and p["net"] is not None and p["net"] > 0 and p["margin"] > 0)


for c in cells:
    c["both_halves"] = ok(c["h1"]) and ok(c["h2"])
    c["hold_ok"] = ok(c["ho"]) if c["ho"]["n"] else None
    t = c["res"]["t_margin"]
    if c["res"]["n"] < MIN_N:
        c["verdict"] = "too few"
    elif c["both_halves"] and c["hold_ok"] and t is not None and t >= T_CLEAR:
        c["verdict"] = "CLEARS"
    elif c["both_halves"] and c["hold_ok"] and t is not None and t >= 2:
        c["verdict"] = "watch"
    else:
        c["verdict"] = "fails"

ranked = sorted([c for c in cells if c["res"]["n"] >= MIN_N], key=lambda c: -c["res"]["margin"])
rules = {}
for act in ("fade", "follow"):
    for d in ("drop", "jump"):
        mine = [c for c in ranked if c["act"] == act and c["dir"] == d]
        if mine:
            rules[f"{act}_{d}"] = mine[0]
n_clear = sum(c["verdict"] == "CLEARS" for c in cells)
n_watch = sum(c["verdict"] == "watch" for c in cells)
n_eval = len(ranked)
pos_margin = sum(c["res"]["margin"] > 0 for c in ranked)
out = dict(n_cells=len(cells), n_events=g["n_events"], n_evaluable=n_eval, cleared=n_clear, watch=n_watch,
           cleared_line=(f"{n_clear} clear" + (f", {n_watch} watch" if n_watch else "")),
           note=(f"Pre-registered 2026-11-06: {len(cells)} cells (3 sizes x 3 windows x drop/jump x fade/follow x 3 "
                 f"take-profits x 2 stops x 3 holds) on the 58 Invest stocks' 1-minute history, Jan 2023 to Nov 2026, "
                 f"after a 0.30% round trip. A cell clears with 30+ events, a positive net AND a positive margin over "
                 f"random entry (same stock, same day, same exit) in both research halves and the 2026 holdout, and a "
                 f"margin t of 3.8+ (Bonferroni over {len(cells)}). {n_eval} cells had 30+ events; {pos_margin} of them "
                 f"beat random entry over the research years. Ranked on margin; the top 25 shown."),
           top=ranked[:25], rules=rules)
json.dump(out, open("research.json", "w"), indent=1)


def pc(x):
    return "—" if x is None else f"{x * 100:+.2f}%"


lines = ["| event | direction | exit | n | win% | avg net | v baseline (t) | both halves? | holdout (n, net, margin) | verdict |",
         "|---|---|---|---|---|---|---|---|---|---|"]
for c in ranked[:int(sys.argv[1]) if len(sys.argv) > 1 else 30]:
    r, h = c["res"], c["ho"]
    lines.append(f'| {c["win"]} {c["size"]*100:g}% {c["dir"]} | {c["act"]} | TP {c["tp"]*100:g}% / SL {c["sl"]*100:g}% / {c["hold"]} '
                 f'| {r["n"]} | {r["win"]*100:.0f}% | {pc(r["net"])} | {pc(r["margin"])} ({r["t_margin"] if r["t_margin"] is None else round(r["t_margin"], 2)}) '
                 f'| {"yes" if c["both_halves"] else "no"} | {h["n"]}, {pc(h["net"])}, {pc(h["margin"])} | {c["verdict"]} |')
open("table.md", "w").write("\n".join(lines) + "\n")
print("\n".join(lines))
print(f"\ncells {len(cells)}  evaluable(n>={MIN_N}) {n_eval}  positive margin {pos_margin}  CLEARS {n_clear}  watch {n_watch}")
for k, c in rules.items():
    print(k, c["win"], c["size"], c["tp"], c["sl"], c["hold"], c["verdict"], pc(c["res"]["margin"]))
