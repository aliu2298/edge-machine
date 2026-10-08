#!/usr/bin/env python3
"""The Tennis page.

Family Tennis: the 3-hour band and the combo lanes, on Kalshi and Polymarket US.
Table tennis is a different family and is not on this page. The rows are the
Sandbox's own (sport_tab.family_rows), so the records are unchanged; the body
is tennis_cards: four tiles, one list of picks, one rules table, one fold.
"""
import datetime
import os

import sandbox_track as T
import site_chrome as C
import sport_tab
import tennis_cards

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "public_site", "tennis.html")

FAMILY = "Tennis"
KEY = "tennis"
TITLE = "Edge Machine · Tennis"
DESCRIPTION = ("Every tennis rule under test — the 3-hour favourite band and the combo "
               "baskets, on Kalshi and Polymarket US.")
LEDE = "Match-winner picks and combo baskets · times CT"
TOC = (("rules", "Rules"), ("matches", "Matches"), ("system", "System"))


def build(d=None, st=None, now=None):
    now = now or datetime.datetime.now(datetime.timezone.utc)
    d = d if d is not None else T.load()
    st = st if st is not None else T.load_stages()
    rows = sport_tab.family_rows(d, st, FAMILY)
    idle = sport_tab.idle_lanes(KEY, d, skip=tuple(r["name"] for r in rows))
    idle_html = sport_tab._idle_html(idle, {}, status=False, prefix=KEY) if idle else ""
    body = tennis_cards.render(d, rows, now, idle_html=idle_html)
    body += f"<footer>{sport_tab._FOOT}</footer>\n"
    return C.document(
        TITLE, DESCRIPTION, KEY, TOC, C.stamp(now), body,
        script_src="./site.js", scripts=("./tables.js",), sports=True)


def main():
    return sport_tab.write(OUT, build())


if __name__ == "__main__":
    raise SystemExit(main())
