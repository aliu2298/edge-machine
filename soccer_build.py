#!/usr/bin/env python3
"""The Soccer page, on the shared sport template (sport_page).

The rows are the Sandbox's own (sport_tab.family_rows); the events and the
rule words are soccer_cards; the method fold carries the Kalshi pre-flight
note and the registered lanes that have never fired. The fold starts open
only when the pre-flight needs attention.
"""
import datetime
import os

import sandbox_track as T
import soccer_cards
import sport_page as SP
import sport_tab

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "public_site", "soccer.html")

FAMILY = "Soccer"
KEY = "soccer"
TITLE = "Edge Machine · Soccer"
DESCRIPTION = "Open soccer picks by kickoff, and the record of every rule that fires them."
LEDE = "Open picks and the rules that fire them · kickoff times CT"
SCOPE = "Match picks and the rules that fire them"


def method(idle):
    def _method(d, rows, now):
        by_lane, pf_note = sport_tab.preflight_report(now=now)
        attention = 'class="neg"' in pf_note or "could not be read" in pf_note
        idle_html = sport_tab._idle_html(idle, by_lane, status=True, prefix=KEY)
        inner = (
            '<p class="sm">Prices are the Kalshi ask the tracker logged when a rule fired. '
            'Results are read back from the venue\'s own settlement, and this page is rebuilt '
            'from that ledger by GitHub Actions.</p>'
            f'{pf_note}'
            f'<details class="section-disclosure"><summary><b>Registered lanes</b><span>{len(idle)}</span></summary>'
            f'{idle_html}</details>')
        label = "Method · check needed" if attention else "Method"
        return label, f"{len(idle)} waiting for a market", inner, attention
    return _method


def build(d=None, st=None, now=None):
    now = now or datetime.datetime.now(datetime.timezone.utc)
    d = d if d is not None else T.load()
    st = st if st is not None else T.load_stages()
    rows = sport_tab.family_rows(d, st, FAMILY)
    idle = sport_tab.idle_lanes(KEY, d, skip=tuple(r["name"] for r in rows))
    sp = SP.spec(
        family=FAMILY, key=KEY, title=TITLE, description=DESCRIPTION, scope=SCOPE,
        venue="Kalshi", rows=rows, events=soccer_cards.events,
        rule_name=soccer_cards._rule_name, market=soccer_cards.market,
        recent=soccer_cards.recent_html, method=method(idle))
    html = SP.page(sp, d, st, now, rows=rows, idle=idle)
    return html.replace("<footer>", _rules_section() + "\n<footer>", 1)


def _rules_section():
    """The 21 Sandbox total-goals label rules (soccer_rules_build.py, 2026-10-17). Never breaks the page."""
    try:
        import soccer_rules_build
        return soccer_rules_build.section()
    except Exception as exc:                                    # noqa: BLE001
        return f'<section id="label-rules"><p class="sm mut">Rules section unavailable ({type(exc).__name__}).</p></section>'


def main():
    return sport_tab.write(OUT, build())


if __name__ == "__main__":
    raise SystemExit(main())
