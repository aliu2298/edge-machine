#!/usr/bin/env python3
"""The Cricket page.

Family Cricket, including the lane in Production. The rows are the Sandbox's
own (sport_tab.family_rows), so the records are unchanged; the body is
cricket_cards: four tiles, one list of picks, one rules table, one fold, the
same shape as the Tennis page.
"""
import datetime
import os

import cricket_cards
import sandbox_track as T
import site_chrome as C
import sport_tab

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "public_site", "cricket.html")

FAMILY = "Cricket"
KEY = "cricket"
TITLE = "Edge Machine · Cricket"
DESCRIPTION = "Every cricket rule and tipster under test, including the lane in Production."
LEDE = "Match-winner picks and the rules that fire them · times CT"
TOC = (("rules", "Rules"), ("matches", "Matches"))


def build(d=None, st=None, now=None):
    now = now or datetime.datetime.now(datetime.timezone.utc)
    d = d if d is not None else T.load()
    st = st if st is not None else T.load_stages()
    rows = sport_tab.family_rows(d, st, FAMILY)
    idle = sport_tab.idle_lanes(KEY, d, skip=tuple(r["name"] for r in rows))
    idle_html = sport_tab._idle_html(idle, {}, status=False, prefix=KEY) if idle else ""
    body = cricket_cards.render(d, rows, now, idle_html=idle_html)
    body += f"<footer>{sport_tab._FOOT}</footer>\n"
    return C.document(
        TITLE, DESCRIPTION, KEY, TOC, C.stamp(now), body,
        script_src="./site.js", scripts=("./tables.js",), sports=True)


def main():
    return sport_tab.write(OUT, build())


if __name__ == "__main__":
    raise SystemExit(main())
