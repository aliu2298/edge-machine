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
                 'the owner on 2026-10-16; its record counts from its 2026-09-21 reset. It was retired on '
                 '2026-11-02 (Retired rules, below).</p>' + idle_html)
        return "Method", "venue note", inner, False
    return _method


def build(d=None, st=None, now=None, own_lanes=True):
    """The tracker's NFL rows plus the team-total lanes as template rows (2026-11-05): before, the team totals were
    spliced into the Sandbox list after the page was drawn, so the tiles read "0 active rules" and a "—" record and
    Events had nothing to list. own_lanes=False draws the tracker's rows alone (a test with its own ledger)."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    d = d if d is not None else T.load()
    st = st if st is not None else T.load_stages()
    rows = sport_tab.family_rows(d, st, FAMILY)
    idle = sport_tab.idle_lanes(KEY, d, skip=tuple(r["name"] for r in rows))
    idle_html = sport_tab._idle_html(idle, {}, status=False, prefix=KEY) if idle else ""
    retired = list(sport_tab.retired_rows(d, st, FAMILY))
    tt_state = None
    if own_lanes:
        try:
            import nfl_tt as N
            import nfl_tt_build as TB
            tt_state = TB._state(None)
            for lane in N.LANES:
                r = TB.template_row(lane, tt_state)
                (retired if r.get("gone") else rows).append(r)
        except Exception as exc:                                # noqa: BLE001
            print(f"nfl_build: the team-total lanes failed: {type(exc).__name__}: {exc}")
    tracker = lambda rs: [r for r in rs if not r.get("own")]    # noqa: E731
    own = lambda rs: [r for r in rs if r.get("own")]            # noqa: E731

    def events(d_, rs, now_):
        out = CC.events(d_, tracker(rs), now_)
        if own(rs):
            import nfl_tt_build as TB
            out += TB.events(own(rs), tt_state, now_)
        return out

    def empty_reason(d_, rs, idle_, now_):
        if own(rs) and not any(r["a"].get("n") or r.get("open") for r in tracker(rs)):
            import nfl_tt_build as TB
            return TB.empty_reason(tt_state)
        return SP.coverage_reason(sp, d_, tracker(rs), idle_, now_)

    sp = SP.spec(
        family=FAMILY, key=KEY, title=TITLE, description=DESCRIPTION, scope=SCOPE,
        venue="Polymarket US", rows=rows, events=events,
        rule_name=lambda r: r["own"]["label"] if r.get("own") else CC.rule_name(r),
        market=lambda d_, r: r["own"]["market"] if r.get("own") else CC.market(d_, r),
        definition=lambda d_, r: r["own"]["details"] if r.get("own") else SP.default_definition(d_, r),
        recent=lambda d_, r, n_: "" if r.get("own") else CC.recent_html(d_, r, n_),
        method=method(idle_html), retired=retired, empty_reason=empty_reason)
    # cfb_dog_tp50's home (2026-10-27): the cheap-side section near the top, before the rules.
    import chaos_build
    return chaos_build.place(SP.page(sp, d, st, now, rows=rows, idle=idle), "nfl", before='<section id="rules"')


def main():
    return sport_tab.write(OUT, build())


if __name__ == "__main__":
    raise SystemExit(main())
