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


# ROUND 2 (Olu, 2026-11-11): the section is narrowed to three rules (sw15keep.py A and C, the Lead Swap favourite).
# Every other live lane is retired at CUT2_AT, its whole record final in the archive. The Loss Reader runs on as a
# watch row to 30 bets. Frozen like round 1: ROUND2_SHA256 is checked by the tests.
CUT2_AT = "2026-11-11T22:00:00+00:00"
RETIRED2 = ("s3v2", "flipf1v2", "flipf2v2", "flipf3v2", "steadyfav_b", "swing15v2_s2", "leadswap_swing")
ROUND2_SHA256 = "89fe4ce425d0288c0bdfb3712593f0187ed174ede63ab48b38977cb5691ae67e"   # sha256 of fingerprint2(), set at registration


def fingerprint2():
    return allowgate.fingerprint(dict(cut_at=CUT2_AT, retired=list(RETIRED2)))


def retire_at(lane):
    """The cut time a retired lane stops entering at (round 1 or 2), or None for a live lane."""
    return CUT_AT if lane in RETIRED else CUT2_AT if lane in RETIRED2 else None


def fingerprint():
    return allowgate.fingerprint(dict(cut_at=CUT_AT, cuts={k: list(v) for k, v in CUTS.items()}, retired=list(RETIRED)))


def cut(lane):
    return CUTS.get(lane, ())


def is_cut(lane, market, open_ts):
    """True when `market` is cut from `lane` for a window opening at open_ts (at or after CUT_AT)."""
    import swing15 as W
    return market in CUTS.get(lane, ()) and open_ts >= W._ts(CUT_AT)
