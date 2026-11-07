"""Export the exchange's own buy fills per order, for the live record (2026-11-07). Runs on edge-vps with the follower's python, read-only.

GET /portfolio/fills is the exchange's book of what was really filled and what it really charged (fee_cost). This reads it and writes
~/live_record_fills.json: {order id: {qty, px, fee}} for BUY fills only, summed per order. The file stays on the VPS (it is private, it carries
order ids); live_record_publish.py reads it to price each order from its own fills and publishes only the whitelisted public fields.
A failure leaves the file as it was and the publisher falls back to the follower's recorded fill and fee.
"""
import glob
import importlib
import json
import os
import sys

OUT = os.path.expanduser(os.environ.get("LIVE_RECORD_FILLS") or "~/live_record_fills.json")
PAGES = 40


SRC_DIR = os.environ.get("FOLLOWER_DIR") or (sorted(glob.glob(os.path.expanduser("~/polymarket-*")))[:1] or [""])[0]


def follower():
    """(exchange module, credentials module) of the follower's package: the folder in SRC_DIR that holds its engine and exchange modules."""
    sys.path.insert(0, SRC_DIR)
    pkg = next(n for n in sorted(os.listdir(SRC_DIR)) if os.path.isfile(os.path.join(SRC_DIR, n, "engine.py"))
               and os.path.isfile(os.path.join(SRC_DIR, n, "kalshi.py")) and os.path.isfile(os.path.join(SRC_DIR, n, "secrets.py")))
    return importlib.import_module(f"{pkg}.kalshi"), importlib.import_module(f"{pkg}.secrets")


def per_order(fills):
    """{order id: {qty, px, fee}} from raw exchange fills: buys only, quantity-weighted price, fees summed."""
    out = {}
    for f in fills:
        if (f.get("action") or "buy") == "sell" or not f.get("order_id"):
            continue
        yes = (f.get("side") or "yes") == "yes"
        px = float((f.get("yes_price_dollars") if yes else f.get("no_price_dollars")) or 0)
        q = float(f.get("count_fp") or 0)
        o = out.setdefault(f["order_id"], dict(qty=0.0, cost=0.0, fee=0.0))
        o["qty"] += q
        o["cost"] += q * px
        o["fee"] += float(f.get("fee_cost") or 0)
    return {k: dict(qty=round(v["qty"], 4), px=round(v["cost"] / v["qty"], 6), fee=round(v["fee"], 6)) for k, v in out.items() if v["qty"] > 0}


def main():
    kalshi, secrets = follower()
    kid, pem = secrets.load_kalshi()
    if not kid or not pem:
        print("no credentials: fills not exported")
        return 1
    fills = kalshi._pages("/portfolio/fills", kid, pem, "fills", PAGES)
    blob = per_order(fills)
    tmp = OUT + ".tmp"
    with open(tmp, "w") as f:
        json.dump(blob, f)
    os.replace(tmp, OUT)
    print(f"fills exported: {len(blob)} orders from {len(fills)} fills")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
