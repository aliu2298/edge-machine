#!/usr/bin/env python3
"""The Tennis page. A thin wrapper around sport_tab.

Family Tennis: the 3-hour band, the combo lanes, and the Polymarket US listing.
Table tennis is a different family and is not on this page. The Kalshi pre-flight
is a soccer file, so this page does not show that column.
"""
import os

import sport_tab

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "public_site", "tennis.html")

FAMILY = "Tennis"
KEY = "tennis"
TITLE = "Edge Machine · Tennis"
DESCRIPTION = ("Every tennis rule under test — the 3-hour favourite band, the combo "
               "baskets, and the Polymarket US listing.")
LEDE = (
    "Every tennis rule under test — the 3-hour favourite band, the combo baskets, "
    "and the Polymarket US listing — with the same records and verdicts as the Sandbox. "
    "Table tennis is a separate sport and is not on this page."
)


def build(d=None, st=None, now=None):
    return sport_tab.build(FAMILY, KEY, TITLE, LEDE, d, st, now, description=DESCRIPTION)


def main():
    return sport_tab.write(OUT, build())


if __name__ == "__main__":
    raise SystemExit(main())
