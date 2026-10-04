#!/usr/bin/env python3
"""The Cricket page. A thin wrapper around sport_tab.

Family Cricket, including the lane in Production, shown the way the Soccer page
shows a Production lane. The Kalshi pre-flight is a soccer file, so this page
does not show that column.
"""
import os

import sport_tab

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "public_site", "cricket.html")

FAMILY = "Cricket"
KEY = "cricket"
TITLE = "Edge Machine · Cricket"
DESCRIPTION = "Every cricket rule and tipster under test, including the lane in Production."
LEDE = (
    "Every cricket rule and tipster under test, including the one in Production, "
    "with the same records and verdicts as the Sandbox."
)


def build(d=None, st=None, now=None):
    return sport_tab.build(FAMILY, KEY, TITLE, LEDE, d, st, now, description=DESCRIPTION)


def main():
    return sport_tab.write(OUT, build())


if __name__ == "__main__":
    raise SystemExit(main())
