#!/usr/bin/env python3
"""The NFL page (2026-10-17), on the shared sport template (sport_page).

Family NFL: ESPN FPI and any other NFL rule, including the one in Production. The rows are
the Sandbox's own (sport_tab.family_rows), so the records are unchanged. NFL picks are match
winners like cricket's, so the events, rule words and recent folds reuse cricket_cards.
"""
import datetime
import os

import cricket_cards as CC
import sandbox_track as T
import sport_page as SP
import sport_tab

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "public_site", "nfl.html")

FAMILY = "NFL"
KEY = "nfl"
TITLE = "Edge Machine · NFL"
DESCRIPTION = "Every NFL rule under test, including the lane in Production."
SCOPE = "Match-winner picks and the rules that fire them"


def method(idle_html=""):
    def _method(d, rows, now):
        inner = ('<p class="sm">NFL picks are match winners, priced on Polymarket US or Kalshi. Every pick '
                 'is logged before kickoff at the price available then, settled on the real result at a '
                 f'flat ${int(T.STAKE)} stake, and judged after fees against the price it paid.</p>'
                 '<p class="sm">ESPN FPI was paused on 2026-09-25 with every NFL lane and resumed by '
                 'the owner on 2026-10-16; its record counts from its 2026-09-21 reset.</p>' + idle_html)
        return "Method", "venue note", inner, False
    return _method


def build(d=None, st=None, now=None):
    now = now or datetime.datetime.now(datetime.timezone.utc)
    d = d if d is not None else T.load()
    st = st if st is not None else T.load_stages()
    rows = sport_tab.family_rows(d, st, FAMILY)
    idle = sport_tab.idle_lanes(KEY, d, skip=tuple(r["name"] for r in rows))
    idle_html = sport_tab._idle_html(idle, {}, status=False, prefix=KEY) if idle else ""
    sp = SP.spec(
        family=FAMILY, key=KEY, title=TITLE, description=DESCRIPTION, scope=SCOPE,
        venue="Polymarket US", rows=rows, events=CC.events, rule_name=CC.rule_name,
        market=CC.market, definition=SP.default_definition, recent=CC.recent_html,
        method=method(idle_html))
    return _team_totals(SP.page(sp, d, st, now, rows=rows, idle=idle))


def _team_totals(html):
    """nfl_tt_over_3545 and nfl_tt_over_main (nfl_tt_build.py, 2026-10-21) in the Sandbox rules
    list, from their own ledger. Never breaks the page."""
    try:
        import nfl_tt_build
        return nfl_tt_build.place(html)
    except Exception:                                           # noqa: BLE001
        return html


def main():
    return sport_tab.write(OUT, build())


if __name__ == "__main__":
    raise SystemExit(main())
