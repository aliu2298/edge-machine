"""Trade prints for fillsim, with a disk cache (2026-11-12). Research tooling: read-only, public Kalshi endpoints, no key.

tape(ticker) -> fillsim prints [(ts, yes price, contracts, taker side)] for the market's whole life. A market whose last print is
over 12 hours old, or that the caller says is settled, is cached (FILLSIM_CACHE, default ~/edge-research/fillsim_cache); any other
is re-read each time.
"""
import gzip
import json
import os
import time

import daily_track as D
import fillsim as F

CACHE = os.path.expanduser(os.environ.get("FILLSIM_CACHE") or "~/edge-research/fillsim_cache")
KEEP = ("created_time", "yes_price_dollars", "no_price_dollars", "count_fp", "taker_side", "is_block_trade")
SETTLED_AFTER_S = 12 * 3600


def fetch_trades(ticker, fetch=D.get, max_pages=400):
    """Every trade of a market, from the live endpoint or, once archived, the historical one."""
    for base in ("markets/trades", "historical/trades"):
        rows, cur = [], None
        for _ in range(max_pages):
            d = fetch(f"{base}?ticker={ticker}&limit=1000" + (f"&cursor={cur}" if cur else ""))
            got = d.get("trades") or []
            rows += got
            cur = d.get("cursor")
            if not cur or not got:
                break
        if rows:
            return rows
    return []


def settled_tape(ticker):
    return tape(ticker, settled=True)


def result(ticker, fetch=D.get, cache=CACHE):
    """"yes" / "no" once Kalshi has settled the market, else None. Settled results are cached."""
    path = os.path.join(cache, "_results.json")
    try:
        with open(path) as f:
            known = json.load(f)
    except (OSError, ValueError):
        known = {}
    if ticker in known:
        return known[ticker]
    m = (fetch(f"markets/{ticker}") or {}).get("market") or {}
    res = m.get("result") if m.get("status") in ("finalized", "settled") and m.get("result") in ("yes", "no") else None
    if res:
        known[ticker] = res
        os.makedirs(cache, exist_ok=True)
        with open(path + ".tmp", "w") as f:
            json.dump(known, f)
        os.replace(path + ".tmp", path)
    return res


def tape(ticker, fetch=D.get, cache=CACHE, now=None, settled=False):
    """`settled`: the caller knows the market is over, so its tape is final and is cached even when it is empty or fresh."""
    path = os.path.join(cache, ticker + ".json.gz")
    if os.path.exists(path):
        with gzip.open(path, "rt") as f:
            return [tuple(p) for p in json.load(f)]
    prints = F.prints_from_trades([{k: t.get(k) for k in KEEP} for t in fetch_trades(ticker, fetch)])
    now = now or time.time()
    if settled or (prints and now - prints[-1][0] > SETTLED_AFTER_S):
        os.makedirs(cache, exist_ok=True)
        tmp = path + ".tmp"
        with gzip.open(tmp, "wt") as f:
            json.dump(prints, f)
        os.replace(tmp, path)
    return prints
