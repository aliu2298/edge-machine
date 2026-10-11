#!/usr/bin/env python3
"""The Cricket page, on the shared sport template (sport_page).

Family Cricket, including the lane in Production. The rows are the Sandbox's
own (sport_tab.family_rows), so the records are unchanged; the events and the
rule words are cricket_cards, built on the Tennis page's helpers.
"""
import datetime
import os

import cricket_cards
import sandbox_track as T
import sport_page as SP
import sport_tab

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "public_site", "cricket.html")

FAMILY = "Cricket"
KEY = "cricket"
TITLE = "Edge Machine · Cricket"
DESCRIPTION = "Every cricket rule and tipster under test, including the lane in Production."
LEDE = "Match-winner picks and the rules that fire them · times CT"
SCOPE = "Match-winner picks and the rules that fire them"
TOC = SP.TOC


def build(d=None, st=None, now=None):
    now = now or datetime.datetime.now(datetime.timezone.utc)
    d = d if d is not None else T.load()
    st = st if st is not None else T.load_stages()
    rows = sport_tab.family_rows(d, st, FAMILY)
    idle = sport_tab.idle_lanes(KEY, d, skip=tuple(r["name"] for r in rows))
    idle_html = sport_tab._idle_html(idle, {}, status=False, prefix=KEY) if idle else ""
    sp = SP.spec(
        family=FAMILY, key=KEY, title=TITLE, description=DESCRIPTION, scope=SCOPE,
        venue="Polymarket US", rows=rows, events=cricket_cards.events,
        rule_name=cricket_cards.rule_name, market=cricket_cards.market,
        definition=cricket_cards.definition,
        recent=cricket_cards.recent_html, method=cricket_cards.method(idle_html))
    return SP.page(sp, d, st, now, rows=rows, idle=idle)


def main():
    return sport_tab.write(OUT, build())


if __name__ == "__main__":
    raise SystemExit(main())
