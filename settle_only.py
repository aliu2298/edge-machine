"""settle_only.py — one switch for a SETTLE-ONLY pass (2026-11-16).

Rule ledgers that enter inside a window (soccer rules, team rules, NBA rules, NBA value, weather) used to settle only when an
entry read happened to run: over the international break nothing was asked, so a pick sat "unsettled" for 186 hours.
The VPS now also asks once an hour while a started pick is still open (lane_windows.settle_windows), and the workflow
sets EDGE_SETTLE_ONLY=1 when that stamp, and no entry stamp, started the run. Every entry gate calls on() and adds nothing.
"""
import os


def on():
    return os.environ.get("EDGE_SETTLE_ONLY") == "1"
