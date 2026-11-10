#!/usr/bin/env python3
"""Rule 3 v2 · Every Positive Setting (flip-f1v2, registered 2026-11-10): Sandbox paper, no orders. Replaces The Flip
Side v3 F1.

The base trade is F1 exactly (flipside_v2.flip(..., "flipside_v2_f1")): when v1's S1 25c trigger fires (the cheap side
prints at 25c in the window's first 5 minutes), buy the OTHER side at its ask at the end of the trigger minute; held to
settlement; taker fee. A window is bet ONLY when all four of its settings are in its market's frozen allow-list
(allowgate.py):

  price           the flip's entry price: <73 (< 73c), 73-76 (73c to < 76.5c), 77+ (76.5c and up)
  trigger_minute  the trigger's minute row: 0-1, 2-3, 4
  lead_changes    YES-mid crossings of 50c over the minute rows 0 .. the trigger minute: 0 / 1 / 2+
  time_ct         the window's open hour in Central: 07-11, 12-16, 17-22; any other hour is never bet

An empty list means that market never bets (XRP: no positive time of day; WTI: no positive lead-change setting). The
allow-list was chosen from each market's positive cells on Nov 9 from 7:15 AM CT (in-sample: 122/133, +20.0%, never
counted). It is the pre-registration: frozen, fingerprinted (ALLOW_SHA256), stored in the ledger. A filter over the v1
hour shards; a fresh record from FROM; written to data/flipf1v2_ledger.json by swing15.yml.
"""
import sys

import allowgate as G
import flipeps

# The frozen pre-registration (flip-f1v2, 2026-11-10). Do not edit: a change is a new version.
ALLOW = {
    "KXGOLD15M": {"price": ["<73", "73-76", "77+"], "trigger_minute": ["0-1", "2-3"], "lead_changes": ["0", "1", "2+"],
                  "time_ct": ["07-11", "12-16", "17-22"]},
    "KXETH15M": {"price": ["<73", "73-76", "77+"], "trigger_minute": ["0-1", "2-3", "4"], "lead_changes": ["0", "1", "2+"],
                 "time_ct": ["07-11", "12-16", "17-22"]},
    "KXPLATINUM15M": {"price": ["<73", "73-76", "77+"], "trigger_minute": ["0-1", "2-3", "4"],
                      "lead_changes": ["0", "1", "2+"], "time_ct": ["12-16", "17-22"]},
    "KXBTC15M": {"price": ["73-76", "77+"], "trigger_minute": ["0-1", "2-3", "4"], "lead_changes": ["0", "1"],
                 "time_ct": ["07-11", "17-22"]},
    "KXNEAR15M": {"price": ["<73"], "trigger_minute": ["0-1", "2-3"], "lead_changes": ["0", "2+"], "time_ct": ["07-11", "17-22"]},
    "KXHYPE15M": {"price": ["<73", "73-76"], "trigger_minute": ["0-1", "4"], "lead_changes": ["0"], "time_ct": ["07-11"]},
    "KXXRP15M": {"price": ["<73", "73-76"], "trigger_minute": ["0-1"], "lead_changes": ["0"], "time_ct": []},
    "KXWTI15M": {"price": ["73-76"], "trigger_minute": ["4"], "lead_changes": [], "time_ct": ["07-11"]},
}
ALLOW_SHA256 = "01203a5be27a049b1f4ce322d0422bdf3c7748621dbf65caef10e4e690e4f90d"   # sha256 of G.fingerprint(ALLOW), set at registration
PRICE_BANDS = ("<73", "73-76", "77+")
MINUTE_BUCKETS = ("0-1", "2-3", "4")


def price_band(p):
    return "<73" if p < 0.73 else "73-76" if p < 0.765 else "77+"


def minute_bucket(m):
    return "0-1" if m <= 1 else "2-3" if m <= 3 else "4" if m == 4 else None


def _settings(w, f):
    """The four settings of a window where F1 entered; lead changes over the minute rows 0 .. the trigger minute (the
    row whose quote is the entry), so nothing after the entry is read."""
    m = ((w.get("s1") or {}).get("0.25") or {}).get("trigger", {}).get("minute")
    if m is None:
        return None
    return dict(price=price_band(f["price"]), trigger_minute=minute_bucket(m), lead_changes=G.lead_changes(w, m),
                time_ct=G.time_bucket(w["open"]))


LANE = flipeps.FlipEPS(
    "flipf1v2", "flip-f1v2", "Rule 3 v2 · Every Positive Setting", "flipside_v2_f1", ALLOW, ALLOW_SHA256,
    "2026-11-10T05:15:00+00:00",                 # fresh record: the first window after the merge (= F1's cut)
    "Nov 9 in-sample, these settings would have gone 122/133, +20% — not counted", _settings,
    "Every bet (old F1 on the same 8 markets)")
flipeps.expose(LANE, globals())
REGISTERED = "2026-11-10"

if __name__ == "__main__":
    sys.exit(main())
