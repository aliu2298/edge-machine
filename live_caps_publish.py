#!/usr/bin/env python3
"""The follower's own price guards per Production pair, written to data/live_caps.json for the Soccer page (2026-11-06).

Why. A pair's paper record counts every leg its rule logged, but the follower refuses a leg whose effective price (ask + Kalshi's fee)
is above the pair's price cap, or whose ask is outside the pair's registered band. The page's headline record has to be the legs the
follower can trade, and the cap is the follower's own number, so it is read from the follower itself, never hand-copied here: this script
runs on the host that holds the follower's config, imports its own price_cap / price_band / fee functions, and writes the result.
Public fields only: a pair name, a price cap, the highest ask under it, a band. No stake, balance, account or key.

Run from the follower's python (its venv) with the follower's folder as FOLLOWER_DIR (default: the one folder named polymarket-* in the home directory):
    <follower>/.venv/bin/python live_caps_publish.py [--config PATH]      # --config: read another config.json (a copy of the host's)
A pair the follower does not know keeps the default cap. If the follower cannot be imported the file is left as it was.
"""
import datetime as dt
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "data", "live_caps.json")
import glob
import importlib
SRC_DIR = os.environ.get("FOLLOWER_DIR") or (sorted(glob.glob(os.path.expanduser("~/polymarket-*")))[:1] or [""])[0]


def compute(pairs, cfg, price_cap, price_band, fee, pair_stake=None, previous=None, now=None):
    """{pair: {cap, max_ask, band, raised_at}}: the effective-price cap, the highest ask on the cent grid whose ask + fee is within it, the
    band (lo, hi) on the ask when the pair has one, else None, and, for a pair whose stake the follower has raised above its default
    (pair_stake(cfg, pair) is a number), `raised_at`: the instant this export first saw it raised, kept from the previous file once set. A
    pair that is no longer raised loses it. No amount is exported: only that the stake is raised, and since when."""
    out = {}
    now = now or dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    for pair in sorted(pairs):
        cap = float(price_cap(cfg, pair))
        asks = [round(c / 100, 2) for c in range(1, 100)]
        ok = [a for a in asks if a + fee(a) <= cap + 1e-9]
        band = price_band(cfg, {"feed": "production", "pair": pair})
        out[pair] = dict(cap=round(cap, 4), max_ask=max(ok) if ok else None, band=[round(band[0], 4), round(band[1], 4)] if band else None)
        if pair_stake is not None and pair_stake(cfg, pair) is not None:
            out[pair]["raised_at"] = ((previous or {}).get(pair) or {}).get("raised_at") or now
    return out


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    sys.path.insert(0, SRC_DIR)
    try:
        # The follower's package is the folder in SRC_DIR that holds its engine and exchange modules (found, not named here).
        pkg = next(n for n in sorted(os.listdir(SRC_DIR)) if os.path.isfile(os.path.join(SRC_DIR, n, "engine.py"))
                   and os.path.isfile(os.path.join(SRC_DIR, n, "kalshi.py")) and os.path.isfile(os.path.join(SRC_DIR, n, "config.py")))
        BC, BE, BK = (importlib.import_module(f"{pkg}.{m}") for m in ("config", "engine", "kalshi"))
    except Exception as exc:                                # noqa: BLE001
        print(f"live_caps: the follower could not be imported ({type(exc).__name__}: {exc}); the file is left as it was")
        return 0
    if "--config" in argv:
        with open(argv[argv.index("--config") + 1]) as f:
            cfg = BC._merge(BC.DEFAULTS, json.load(f))
    else:
        cfg = BC.load()
    import live_record_publish as LP
    _leads, entered = LP.feed_index()
    try:
        with open(OUT) as fh:
            previous = json.load(fh).get("caps") or {}
    except (OSError, ValueError):
        previous = {}
    caps = compute(entered, cfg, BE.price_cap, BE.price_band, BK.fee_per_contract, BE.pair_stake, previous)
    blob = dict(generated=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), caps=caps)
    tmp = OUT + ".tmp"
    with open(tmp, "w") as f:
        json.dump(blob, f, indent=1, sort_keys=True)
        f.write("\n")
    os.replace(tmp, OUT)
    print(f"live_caps: {len(caps)} pairs written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
