#!/usr/bin/env python3
"""Rule 6 v2 · Zcash underdog at 20c+ (flip-f4v2, registered 2026-11-10): Sandbox paper, no orders. Replaces The Flip
Side v3 F4.

The base trade is F4 exactly (flipside_v2.flip(w, "flipside_v2_f4")): the underdog (the side opposite v1's S3
favourite) at its ask from the minute-10 entry quote; held to settlement; taker fee. Zcash only (KXZEC15M). One
setting: the underdog's price must be 20c or more. Every hour is bet (Olu did not restrict the time of day). The
one-key allow-list goes through the shared gate (allowgate.py, flipeps.py), frozen and fingerprinted.
"""
import sys

import flipeps

# The frozen pre-registration (flip-f4v2, 2026-11-10). Do not edit: a change is a new version.
ALLOW = {"KXZEC15M": {"price": ["20+"]}}
ALLOW_SHA256 = "d382c012aa9b890e0e26ef1f808eb282cd7cf78badbd0c7ffb323a3ad488f242"   # sha256 of G.fingerprint(ALLOW), set at registration
MIN_PRICE = 0.20


def price_band(p):
    return "20+" if p >= MIN_PRICE - 1e-9 else "<20"


def _settings(w, f):
    return dict(price=price_band(f["price"]))


LANE = flipeps.FlipEPS(
    "flipf4v2", "flip-f4v2", "Rule 6 v2 · Zcash underdog at 20c+", "flipside_v2_f4", ALLOW, ALLOW_SHA256,
    "2026-11-10T05:30:00+00:00",                 # fresh record: the first window after the merge (= F4's cut)
    "Nov 9 in-sample: 9/22, +38% — not counted (+41.7% as this page measures it: the mean return after fees a bet)",
    _settings, "Every bet (old F4)")
flipeps.expose(LANE, globals())
REGISTERED = "2026-11-10"

if __name__ == "__main__":
    sys.exit(main())
