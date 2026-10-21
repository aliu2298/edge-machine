#!/usr/bin/env python3
"""The Tennis page, on the shared sport template (sport_page).

Family Tennis: the 3-hour band and the combo lanes, on Kalshi and Polymarket US.
Table tennis is a different family and is not on this page. The rows are the
Sandbox's own (sport_tab.family_rows), so the records are unchanged; the events
and the rule words are tennis_cards.
"""
import datetime
import os

import sandbox_track as T
import sport_page as SP
import sport_tab
import tennis_cards

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "public_site", "tennis.html")

FAMILY = "Tennis"
KEY = "tennis"
TITLE = "Edge Machine · Tennis"
DESCRIPTION = ("Every tennis rule under test — the 3-hour favourite band and the combo "
               "baskets, on Kalshi and Polymarket US.")
LEDE = "UTR daily shortlist · up to 3 singles · previous rules paused · times CT"
SCOPE = "Match-winner picks and combo baskets"
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
        venue="Kalshi or Polymarket US", rows=rows, events=tennis_cards.events,
        rule_name=tennis_cards.rule_name, market=tennis_cards.market,
        definition=tennis_cards.definition, recent=tennis_cards.recent_html,
        method=tennis_cards.method(idle_html))
    return _atp_totals(SP.page(sp, d, st, now, rows=rows, idle=idle))


def _atp_totals(html):
    """tennis_atp_low_over (tennis_totals_build.py, 2026-10-21) in the Sandbox rules list,
    from its own ledger. Never breaks the page."""
    try:
        import tennis_totals_build
        return tennis_totals_build.place(html)
    except Exception:                                           # noqa: BLE001
        return html


def main():
    return sport_tab.write(OUT, build())


if __name__ == "__main__":
    raise SystemExit(main())
