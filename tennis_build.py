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
    real = d is None                                           # the real ledger's page counts the real cheap-side lanes; a test's own ledger does not
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
        method=tennis_cards.method(idle_html),
        # Retired by hand (2026-10-24): their own fold, final record and reason.
        retired=sport_tab.retired_rows(d, st, FAMILY), lane_tiles=(lambda: _lane_tiles()) if real else None)
    live = [r for r in rows if not r.get("gone") and r.get("v") != "retired"]
    if real and not live:
        lean = _lean(sp, d, st, now, rows)
        if lean:
            return lean
    return _cheap_side(_atp_totals(SP.page(sp, d, st, now, rows=rows, idle=idle)))


def _lean(sp, d, st, now, rows):
    """The page when no rule is under test in the Sandbox or Production (2026-11-11, Olu: very few words, everything
    collapsible): the live cheap-side lanes as one row each, then ONE closed Retired block holding the retired lanes
    and the retired rules, then the method. No empty Rules or Events sections, so the page never says "no rule"
    while a lane runs. Returns "" when there is no live lane (the full page then stands)."""
    import re
    import chaos_build
    import sandbox_build as B
    import site_chrome as C
    sec, ul, n_lanes = chaos_build.compact_section(KEY)
    if not sec:
        return ""
    now = SP.as_utc(now)
    ret = SP.retired_html(sp, d, now)
    m = re.match(r'<section[^>]*><details[^>]*><summary>.*?</summary>(.*)</details></section>\s*$', ret, re.S)
    inner_rules = m.group(1) if m else ret
    n_rules = len(sp.get("retired") or ())
    n = n_lanes + n_rules
    retired = (f'<section id="retired" class="sp-section"><details class="fold sp-retired"><summary><h3>Retired</h3>'
               f'<span class="sm mut">· {n_lanes} lane{"s" if n_lanes != 1 else ""} + {n_rules} rules · final records</span>'
               f'</summary>{ul}{inner_rules}</details></section>') if n else ""
    label, hint, inner, opened = sp["method"](d, rows, now)
    ev_list = sp["events"](d, rows, now)
    open_n = sum(1 for e in ev_list for p in e["picks"] if p["state"] == "open")
    t = chaos_build.page_tiles(KEY)
    rec = t["record"] or {}
    roi = (f'<b>{rec["roi_fee"] * 100:+.1f}%</b>' if rec.get("roi_fee") is not None else '<b class="mut">—</b>')
    tiles = ('<div class="tiles sp-tiles">'
             f'<div class="tile"><b>{open_n}</b><span>open picks</span></div>'
             f'<div class="tile"><b>{t["active"]}</b><span>active lane{"" if t["active"] == 1 else "s"}</span></div>'
             f'<div class="tile"><b>{rec.get("won", 0)} of {rec.get("n", 0)}</b><span>won · held, paper</span></div>'
             f'<div class="tile">{roi}<span>held ROI after fees · paper</span></div></div>')
    body = (f'<div class="sp-head"><p class="eyebrow">Rules under test</p><h1>Tennis</h1>'
            f'<p class="scope">Challenger cheap side · paper · All times Central</p></div>\n'
            f'{tiles}\n{B.label_cells(sec)}\n{retired}\n{SP.method_html(label, hint, inner, opened)}\n<footer>{SP.FOOT}</footer>\n')
    toc = (("cheap-side", "Lanes"),) + ((("retired", "Retired"),) if n else ()) + (("method", "Method"),)
    html = C.document(sp["title"], sp["description"], sp["key"], toc, C.stamp(now), body,
                      script_src="./site.js", scripts=("./tables.js",), sports=True)
    return B.label_cells(html)


def _lane_tiles():
    try:
        import chaos_build
        return chaos_build.page_tiles("tennis")
    except Exception:                                           # noqa: BLE001
        return None


def _cheap_side(html):
    """The tennis chaos lanes as the page's "Cheap side + resting take-profit" section, at the top of the
    page before the rules (2026-10-27: the tennis strategy now). From data/chaos_ledger.json, the same
    records as the Sandbox's Chaos section. Never breaks the page."""
    import chaos_build
    return chaos_build.place(html, "tennis", before='<section id="rules"')


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
