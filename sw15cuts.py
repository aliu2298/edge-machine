"""The 15-Minute market cuts (Olu, 2026-11-10, from the 17:09Z ledgers): frozen, fingerprinted, one cut time.

A market is cut from a lane only where its record there had a return after fees of 0 or less; a market with no bets
stays eligible. From CUT_AT the lane skips a cut market (no backfill); the cut market's final record (windows before
CUT_AT) goes to the Retired & removed archive; the kept markets' records continue, and the lane's totals are over them.
Comparison books (every bet, fixed after 2, the pooled controls) are unchanged and keep the full market set. A lane in
RETIRED stops entering at CUT_AT; its record lives only in the archive.

Frozen: a later cut is a new round, never an edit (CUTS_SHA256 is checked by the tests).
"""
import allowgate

CUT_AT = "2026-11-10T19:00:00+00:00"
DATA = "the 17:09Z ledgers"
CUTS = {
    "lossreader": ("KXBTC15M", "KXWTI15M"),
    "s3v2": ("KXGOLD15M", "KXETH15M", "KXBNB15M", "KX2YRRATE15M"),
    "flipf1v2": ("KXETH15M", "KXGOLD15M", "KXNEAR15M", "KXHYPE15M"),
    "flipf2v2": ("KXBTC15M", "KXHYPE15M", "KXPLATINUM15M"),
    "flipf3v2": ("KXEURUSD15M", "KXNATGAS15M"),
    "steadyfav_b": ("KXGOLD15M",),
    "swing15v2_s2": ("KXSOL15M", "KXWTI15M"),
}
RETIRED = ("flipf4v2", "steadyfav_a")
CUTS_SHA256 = "4d654a40e9f970d123b9883b23861e8f76db47cad8f3d0647585b159df6eb5a9"   # sha256 of fingerprint(), set at registration


def fingerprint():
    return allowgate.fingerprint(dict(cut_at=CUT_AT, cuts={k: list(v) for k, v in CUTS.items()}, retired=list(RETIRED)))


def cut(lane):
    return CUTS.get(lane, ())


def is_cut(lane, market, open_ts):
    """True when `market` is cut from `lane` for a window opening at open_ts (at or after CUT_AT)."""
    import swing15 as W
    return market in CUTS.get(lane, ()) and open_ts >= W._ts(CUT_AT)
