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
DESCRIPTION = "Open soccer picks by kickoff, and the record of every rule that fires them."
LEDE = "Open picks and the rules that fire them · kickoff times CT"


def build(d=None, st=None, now=None):
    """The page, with its table cells already named for the phone layout.

    The tracker's own pass over the finished page leaves a labelled table
    alone, so the direct build and the tracker build are the same document.
    """
    import sandbox_build
    return sandbox_build.label_cells(sport_tab.build(
        FAMILY, KEY, TITLE, LEDE, d, st, now,
        description=DESCRIPTION, preflight=True, cards=True))


def main():
    return sport_tab.write(OUT, build())


if __name__ == "__main__":
    raise SystemExit(main())
