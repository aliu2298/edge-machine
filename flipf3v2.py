#!/usr/bin/env python3
"""Rule 5 v2 · Every Positive Setting (flip-f3v2, registered 2026-11-10): Sandbox paper, no orders. Replaces The Flip
Side v3 F3.

The base trade is F3 exactly (flipside_v2.flip(w, "flipside_v2_f3")): the underdog (the side opposite v1's S2 favourite)
at its ask from the minute-2 quote; held to settlement; taker fee. Bet ONLY when all three settings are in the market's
frozen allow-list (allowgate.py, flipeps.py):

  price       the underdog's entry price: <30 (< 30c), 30-40 (30c to < 40c), 40+
  early_move  the underdog side's mid from the minute-1 quote (row 0, the first close in the window) to the minute-2
              quote (row 1, the entry quote): fell (<= -5c), flat (between), rose (>= +5c). Only quotes up to the
              entry are read. (As relayed, "minute 0 to minute 2" reproduced its in-sample only with row 2, the
              minute-3 close, which is AFTER the entry; that would be look-ahead, so the pre-entry rows are used.)
  time_ct     the open hour in Central: 07-11, 12-16, 17-22; any other hour is never bet

Chosen from Nov 9 from 7:15 AM CT; frozen and fingerprinted. Direction (YES/NO) is deliberately not a setting.
"""
import sys

import allowgate as G
import flipeps

# The frozen pre-registration (flip-f3v2, 2026-11-10). Do not edit: a change is a new version.
ALLOW = {
    "KXEURUSD15M": {"price": ["30-40", "40+"], "early_move": ["fell", "rose"], "time_ct": ["07-11"]},
    "KXUSDCAD15M": {"price": ["30-40", "40+"], "early_move": ["flat", "rose"], "time_ct": ["07-11"]},
    "KXNATGAS15M": {"price": ["30-40"], "early_move": ["fell"], "time_ct": ["07-11", "12-16"]},
}
ALLOW_SHA256 = "5cfac223c9353064de5d6fcabce71a9892ef9858119ee35a9fcdd0da99e2bf5a"   # sha256 of G.fingerprint(ALLOW), set at registration
PRICE_BANDS = ("<30", "30-40", "40+")
MOVE_BUCKETS = ("fell", "flat", "rose")
FIRST_ROW, ENTRY_ROW = 0, 1                     # the minute-1 and minute-2 closes (v1's S2 reads row 1)


def price_band(p):
    return "<30" if p < 0.30 else "30-40" if p < 0.40 else "40+"


def _mid(w, row):
    cols = w.get("minute_cols") or []
    r = next((r for r in (w.get("minutes") or []) if r[0] == row), None)
    if r is None or "yes_bid" not in cols:
        return None
    b, a = r[cols.index("yes_bid")], r[cols.index("yes_ask")]
    return None if b is None or a is None else (b + a) / 2


def early_move(w, side):
    m0, m1 = _mid(w, FIRST_ROW), _mid(w, ENTRY_ROW)
    if m0 is None or m1 is None:
        return None
    d = (m1 - m0) if side == "yes" else (m0 - m1)
    return "fell" if d <= -0.05 + 1e-9 else "rose" if d >= 0.05 - 1e-9 else "flat"


def _settings(w, f):
    return dict(price=price_band(f["price"]), early_move=early_move(w, f["side"]), time_ct=G.time_bucket(w["open"]))


LANE = flipeps.FlipEPS(
    "flipf3v2", "flip-f3v2", "Rule 5 v2 · Every Positive Setting", "flipside_v2_f3", ALLOW, ALLOW_SHA256,
    "2026-11-10T05:15:00+00:00",                 # fresh record: the first window after the merge (= F3's cut)
    "Nov 9 in-sample, these settings would have gone 15/27, +39% with the early move read before the entry — not "
    "counted (17/25, +65% as relayed read the minute-3 quote, after the entry)", _settings,
    "Every bet (old F3 on the same 3 markets)")
flipeps.expose(LANE, globals())
REGISTERED = "2026-11-10"

if __name__ == "__main__":
    sys.exit(main())
