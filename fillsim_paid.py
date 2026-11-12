"""The main tracker's lanes: the price the page logged v the price really paid (2026-11-12). Research tooling, read-only.

A tracker lane buys at the ask it logged and holds to settlement, so paper and live can differ only two ways: the PRICE (the order
paid more or less than the logged ask, or a different fee), and WHICH BETS (the follower refused or missed some the page counts).
This reads data/live_record.json (every live order: its return after the exchange's own fees), finds the paper bet behind each one,
and reports per lane:

  slippage   on live winners, the price paid (worked back from the live return) minus the price the page logged. A loser shows no
             price: both sides lose the whole stake.
  same bets  the page's return and the live return over the bets both hold, with the page priced at the exchange's real fee.

Kalshi orders only (the other venue no longer trades). Run: python3 fillsim_paid.py [--json out.json]
"""
import glob
import json
import os
import sys

import fillsim as F
import fillsim_regrade as G

ROOT = os.path.dirname(os.path.abspath(__file__))
LEDGERS = ("sandbox_ledger", "nba_value_ledger", "soccer_rules_ledger", "soccer_team_rules_ledger", "daily_ledger", "nfl_tt_ledger",
           "culture_ledger")


def paid_price(ret):
    """The price a winning taker order paid per contract, from its live return: cost = 1 / (1 + return) = price + fee."""
    cost = 1.0 / (1.0 + ret)
    lo, hi = 0.0, min(cost, 0.9999)
    for _ in range(60):
        mid = (lo + hi) / 2
        if mid + 0.07 * mid * (1 - mid) < cost:
            lo = mid
        else:
            hi = mid
    return round((lo + hi) / 2, 4)


def paper_index():
    """({bet id: entry}, {ticker: [entries]}) over every ledger entry that carries a logged price and a Kalshi ticker."""
    by_id, by_ticker = {}, {}

    def walk(x):
        if isinstance(x, dict):
            price = x.get("price")
            tk = x.get("ticker") or x.get("market_id") or (x.get("id") if str(x.get("id") or "").startswith("KX") else None)
            if isinstance(price, (int, float)) and isinstance(tk, str) and tk.startswith("KX") and x.get("bet", True):
                if isinstance(x.get("id"), str):
                    by_id.setdefault(x["id"], x)
                by_ticker.setdefault(tk, []).append(x)
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    for name in LEDGERS:
        try:
            walk(G.load(name))
        except (OSError, ValueError):
            continue
    for path in sorted(glob.glob(os.path.join(ROOT, "data", "sandbox_archive", "*.json"))):
        with open(path) as f:
            walk(json.load(f))
    return by_id, by_ticker


def paper_for(order, by_id, by_ticker):
    """The paper entry behind a live order: by its bet id, else the one ledger entry on its ticker whose rule matches the lane."""
    if order["id"] in by_id:
        return by_id[order["id"]]
    src, _, tk = order["id"].partition(":")
    got = by_ticker.get(tk) or []
    rule = src.split("_", 1)[-1].upper()                       # sr_a7 -> A7, st_t1h -> T1H
    named = [e for e in got if str(e.get("rule") or "").upper() in (rule, rule[:2])]
    if len(named) == 1:
        return named[0]
    return got[0] if len(got) == 1 else None


def won(entry):
    s = str(entry.get("status") or "")
    if s in ("won", "lost"):
        return s == "won"
    if entry.get("payout") in (0, 0.0, 1, 1.0):
        return entry["payout"] == 1
    return None


def run():
    lr = G.load("live_record")
    pairs = {k: (v["orders"], "production") for k, v in lr["pairs"].items()}
    pairs.update({k: (v, "pulled") for k, v in lr["pulled"].items()})
    by_id, by_ticker = paper_index()
    out = {}
    for pair, (orders, where) in sorted(pairs.items()):
        rows, unmatched = [], 0
        for o in orders:
            tk = o["id"].partition(":")[2]
            if not tk.startswith("KX") or o.get("r") is None or o.get("st") not in ("won", "lost"):
                continue
            e = paper_for(o, by_id, by_ticker)
            if e is None:
                unmatched += 1
                continue
            p = float(e["price"])
            live_won = o["st"] == "won"
            rows.append(dict(id=o["id"], ko=o["ko"], logged=p, live=o["r"], live_won=live_won, paper_won=won(e),
                             paid=paid_price(o["r"]) if live_won and o["r"] > 0 else None,
                             paper=round(1.0 / (p + F.fee(p)) - 1, 4) if live_won else -1.0))
        if not rows:
            continue
        slips = [r["paid"] - r["logged"] for r in rows if r["paid"] is not None]
        out[pair] = dict(where=where, n=len(rows), won=sum(r["live_won"] for r in rows), unmatched=unmatched,
                         slip_n=len(slips), slip=round(sum(slips) / len(slips), 4) if slips else None,
                         slip_worse=sum(1 for s in slips if s > 0.005), slip_better=sum(1 for s in slips if s < -0.005),
                         paper=G.stats([(r["paper"], r["ko"][:10]) for r in rows]), live=G.stats([(r["live"], r["ko"][:10]) for r in rows]),
                         result_mismatch=sum(1 for r in rows if r["paper_won"] is not None and r["paper_won"] != r["live_won"]), rows=rows)
    return out


def report(out):
    lines = [f"{'lane':40} {'bets':>4} {'won':>4}  {'page, same bets':>16} {'live':>9}  {'gap':>7}  slippage on winners"]
    tot_p = tot_l = tot_n = 0
    allslip = []
    for pair, s in sorted(out.items(), key=lambda kv: -kv[1]["n"]):
        p, l = s["paper"]["roi"], s["live"]["roi"]
        slip = "-" if s["slip"] is None else f"{s['slip'] * 100:+.1f}c on {s['slip_n']} ({s['slip_worse']} worse, {s['slip_better']} better)"
        mm = f"  RESULT MISMATCH {s['result_mismatch']}" if s["result_mismatch"] else ""
        lines.append(f"{pair[:40]:40} {s['n']:>4} {s['won']:>4}  {p * 100:>+15.1f}% {l * 100:>+8.1f}%  {(l - p) * 100:>+6.1f}  {slip}{mm}")
        tot_p += p * s["n"]
        tot_l += l * s["n"]
        tot_n += s["n"]
        allslip += [r["paid"] - r["logged"] for r in s["rows"] if r["paid"] is not None]
    if tot_n:
        lines.append(f"{'ALL':40} {tot_n:>4} {'':>4}  {tot_p / tot_n * 100:>+15.1f}% {tot_l / tot_n * 100:>+8.1f}%  {(tot_l - tot_p) / tot_n * 100:>+6.1f}  "
                     f"{sum(allslip) / len(allslip) * 100:+.2f}c on {len(allslip)} winners")
    return "\n".join(lines)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    out = run()
    print(report(out))
    if "--json" in argv:
        with open(argv[argv.index("--json") + 1], "w") as f:
            json.dump(out, f, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
