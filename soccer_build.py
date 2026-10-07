#!/usr/bin/env python3
"""The Soccer page. Rendering lives in sport_tab; this wrapper keeps the Soccer call.

The page stays the Soccer page: same ledger, same pre-flight column, same words.
"""
import os

import sport_tab

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "public_site", "soccer.html")

FAMILY = "Soccer"
KEY = "soccer"
TITLE = "Edge Machine · Soccer"
DESCRIPTION = "Every soccer rule and tipster under test, and the lanes still waiting for a market."
LEDE = (
    "Every soccer rule and tipster under test — over 1.5, both teams to score,\n"
    "team totals, corners, each again for cups and internationals — plus the lanes that have\n"
    "been registered and have never had a market to bet."
)


def build(d=None, st=None, now=None):
    return sport_tab.build(
        FAMILY, KEY, TITLE, LEDE, d, st, now,
        description=DESCRIPTION, preflight=True, cards=True)


def main():
    return sport_tab.write(OUT, build())


if __name__ == "__main__":
    raise SystemExit(main())
