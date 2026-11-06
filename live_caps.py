"""The follower's price guards per Production pair, as the Soccer page reads them (2026-11-06).

data/live_caps.json is written by live_caps_publish.py on the host that runs the follower, from the follower's own price_cap /
price_band / fee functions, so nothing here is a hand copy of a number. A leg is TRADEABLE when its ask is at or under the pair's
max_ask (ask + the venue's fee within the effective-price cap) and inside the pair's band when it has one. A pair with no entry in
the file (or no file) has no guard here: every leg counts, as before.
"""
import json
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "data", "live_caps.json")
EPS = 1e-9
_CACHE = {}


def load(path=PATH):
    key = (path, os.path.getmtime(path) if os.path.exists(path) else None)
    if key not in _CACHE:
        try:
            with open(path) as f:
                _CACHE[key] = (json.load(f).get("caps") or {})
        except (OSError, ValueError):
            _CACHE[key] = {}
    return _CACHE[key]


def guard(pair, caps=None):
    caps = load() if caps is None else caps
    return caps.get(pair)


def raised_at(pair, caps=None):
    """The instant (ISO, UTC) the follower's stake on this pair was first seen raised above its default, or None. Read from the follower's own
    config by live_caps_publish.py, never kept by hand: a new raise starts a new window by itself."""
    g = guard(pair, caps)
    return (g or {}).get("raised_at")


def tradeable(pair, price, caps=None):
    """True when the follower could take a leg at this ask under the pair's price cap and band (or when nothing is known)."""
    g = guard(pair, caps)
    if g is None or price is None:
        return True
    p = float(price)
    if g.get("max_ask") is not None and p > g["max_ask"] + EPS:
        return False
    band = g.get("band")
    if band and not (band[0] - EPS <= p <= band[1] + EPS):
        return False
    return True


def reason(pair, price, caps=None):
    """Why a leg is not tradeable ('above the price cap', 'outside the band') or None."""
    g = guard(pair, caps)
    if g is None or price is None or tradeable(pair, price, caps):
        return None
    p = float(price)
    if g.get("max_ask") is not None and p > g["max_ask"] + EPS:
        return "above the live price cap"
    return "outside the live band"


def split(pair, rows, price=lambda r: r.get("price"), caps=None):
    """(tradeable rows, all rows) for one pair; the rows are never altered."""
    rows = list(rows)
    return [r for r in rows if tradeable(pair, price(r), caps)], rows
