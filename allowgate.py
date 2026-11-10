"""The "Every Positive Setting" allow-list gate, shared by the 15-Minute v2 rules (s3v2.py, flipf1v2.py, and the next).

A rule's frozen allow-list maps each market to {setting: [allowed buckets]}. A window is bet only when its market is
listed and EVERY setting's bucket is in that market's list; an empty list means the market never bets on that setting,
and a window whose bucket is None (unknown, or an hour outside 07-22 CT) is never bet. The list is fingerprinted so
any edit after registration is caught (a change is a new version, never an edit).
"""
import datetime as dt
import hashlib
import json
from zoneinfo import ZoneInfo

CT = ZoneInfo("America/Chicago")
TIME_BUCKETS = ("07-11", "12-16", "17-22")
LEAD_BUCKETS = ("0", "1", "2+")


def fingerprint(allow):
    """sha256 of the allow-list's canonical JSON (sorted keys, no spaces)."""
    return hashlib.sha256(json.dumps(allow, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def time_bucket(open_iso):
    """The window's open hour in Central: 07-11, 12-16, 17-22, or None for any other hour (never bet)."""
    h = dt.datetime.fromisoformat(open_iso.replace("Z", "+00:00")).astimezone(CT).hour
    return "07-11" if 7 <= h <= 11 else "12-16" if 12 <= h <= 16 else "17-22" if 17 <= h <= 22 else None


def lead_changes(w, upto):
    """How often the YES mid crossed 50c over the v1 minute rows m = 0..upto, bucketed 0 / 1 / 2+ (a mid of exactly 50c
    is no side and is skipped); None when the window carries no quotes."""
    cols = w.get("minute_cols") or []
    if "yes_bid" not in cols or "yes_ask" not in cols:
        return None
    ib, ia = cols.index("yes_bid"), cols.index("yes_ask")
    side, n = None, 0
    for r in w.get("minutes") or []:
        if r[0] > upto:
            break
        b, a = r[ib], r[ia]
        if b is None or a is None:
            continue
        mid = (b + a) / 2
        if mid == 0.5:
            continue
        up = mid > 0.5
        if side is not None and up != side:
            n += 1
        side = up
    return "0" if n == 0 else "1" if n == 1 else "2+"


def allowed(allow, market, settings):
    """True only when `market` is listed and every one of its settings' buckets is in its list."""
    a = allow.get(market)
    if not a or not settings:
        return False
    return all(settings.get(k) is not None and settings[k] in (a.get(k) or []) for k in a)


def never(allow):
    """{market: [settings with an empty list]}: markets that can never bet, and why."""
    return {m: [k for k, v in a.items() if not v] for m, a in allow.items() if any(not v for v in a.values())}
