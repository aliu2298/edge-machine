#!/usr/bin/env python3
"""Rule 4 v2 · Every Positive Setting (flip-f2v2, registered 2026-11-10): Sandbox paper, no orders. Replaces The Flip
Side v3 F2.

The base trade is F2 exactly (flipside_v2.flip(w, "flipside_v2_f2")): when v1's S1 35c trigger fires, buy the OTHER side
at its ask at the end of the trigger minute; held to settlement; taker fee. Bet ONLY when all four settings are in the
market's frozen allow-list (allowgate.py, flipeps.py):

  price           the flip's entry price: <63 (< 62.5c), 63-67 (62.5c to < 67.5c), 68+
  trigger_minute  0-1, 2-3, 4
  lead_changes    YES-mid crossings of 50c over the minute rows 0 .. the trigger minute (the entry's row): 0 / 1 / 2+
  time_ct         the open hour in Central: 07-11, 12-16, 17-22; any other hour is never bet

Brent's lists are empty: it never bets ("no positive setting"). Chosen from Nov 9 from 7:15 AM CT (in-sample 88/109,
+14.6%, never counted); frozen and fingerprinted.
"""
import sys

import allowgate as G
import flipeps

# The frozen pre-registration (flip-f2v2, 2026-11-10). Do not edit: a change is a new version.
ALLOW = {
    "KXXRP15M": {"price": ["<63", "68+"], "trigger_minute": ["0-1", "2-3"], "lead_changes": ["0", "1", "2+"],
                 "time_ct": ["12-16", "17-22"]},
    "KXHYPE15M": {"price": ["<63", "63-67", "68+"], "trigger_minute": ["0-1"], "lead_changes": ["0", "1"],
                  "time_ct": ["07-11", "17-22"]},
    "KXBTC15M": {"price": ["63-67", "68+"], "trigger_minute": ["0-1"], "lead_changes": ["0", "1"], "time_ct": ["07-11", "17-22"]},
    "KXPLATINUM15M": {"price": ["63-67", "68+"], "trigger_minute": ["0-1", "2-3"], "lead_changes": ["0", "1"],
                      "time_ct": ["07-11", "12-16"]},
    "KXWTI15M": {"price": ["68+"], "trigger_minute": ["2-3"], "lead_changes": ["1"], "time_ct": ["07-11"]},
    "KXBRENT15M": {"price": [], "trigger_minute": [], "lead_changes": [], "time_ct": []},
}
ALLOW_SHA256 = "1751db5e2783845d046c8a42b1b747e92561e03f8ac94db5db9a1fdbcc0f8ef5"   # sha256 of G.fingerprint(ALLOW), set at registration
PRICE_BANDS = ("<63", "63-67", "68+")


def price_band(p):
    return "<63" if p < 0.625 else "63-67" if p < 0.675 else "68+"


def minute_bucket(m):
    return "0-1" if m <= 1 else "2-3" if m <= 3 else "4" if m == 4 else None


def _settings(w, f):
    m = ((w.get("s1") or {}).get("0.35") or {}).get("trigger", {}).get("minute")
    if m is None:
        return None
    return dict(price=price_band(f["price"]), trigger_minute=minute_bucket(m), lead_changes=G.lead_changes(w, m),
                time_ct=G.time_bucket(w["open"]))


LANE = flipeps.FlipEPS(
    "flipf2v2", "flip-f2v2", "Rule 4 v2 · Every Positive Setting", "flipside_v2_f2", ALLOW, ALLOW_SHA256,
    "2026-11-10T05:15:00+00:00",                 # fresh record: the first window after the merge (= F2's cut)
    "Nov 9 in-sample, these settings would have gone 88/109, +15% — not counted", _settings,
    "Every bet (old F2 on the same 6 markets)")
flipeps.expose(LANE, globals())
REGISTERED = "2026-11-10"

if __name__ == "__main__":
    sys.exit(main())
