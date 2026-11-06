"""Pairs the live follower trades at a raised stake (2026-11-05, Olu; read from the follower itself since 2026-11-06).

The follower sizes each order from its own config, risk.stake_usd_by_pair. The public pages are built here and cannot read that file, so
live_caps_publish.py (run in the follower's python on its host) exports, per Production pair, whether the stake is raised and the instant it
was first seen raised (data/live_caps.json, field raised_at). This module reads that: a pair listed there gets a small "Raised stake" badge on
its sport page's rule row, and the Production page counts its record from that instant (a NEW raise starts a new window by itself; the record
at the earlier stake stays in a fold). No amount is printed anywhere (public copy: sandbox_audit.COPY_RE), and nothing here changes what the
follower does. There is no hand-kept list.
"""
import live_caps as LC


def raised(pair):
    """True when the follower trades this Production pair ("source|sport") at a raised stake."""
    return LC.raised_at(pair) is not None


def since(pair):
    """The instant (ISO, UTC) the stake was first seen raised, or None."""
    return LC.raised_at(pair)


def pairs():
    """{pair: raised_at} for every pair the follower trades at a raised stake."""
    return {p: g["raised_at"] for p, g in LC.load().items() if g.get("raised_at")}
