#!/usr/bin/env python3
"""The Soccer page, on the shared sport template (sport_page), laid out like Econ Daily (2026-11-05, Olu).

Tiles, the scope and stage filters, the Production rules, the Sandbox rules, Events, the Retired fold and the
method. Every soccer lane is ONE row: the tracker's rules (sport_tab.family_rows) and the own-ledger lanes
(soccer_lanes: label rules, team scoring, the over 3.5 cheap NO, the goalless dips; the retired contenders and
Argentina & Brasileirao over 1.5 in the Retired fold). A lane's words, other exits, splits, versions and research
sit in its row's closed fold. The events and the tracker rules' words are soccer_cards; the method fold carries the
Kalshi pre-flight note, the own-ledger lanes' shared words and the registered lanes that have never fired. It
starts open only when the pre-flight needs attention.
"""
import datetime
import os

import sandbox_build as B
import sandbox_track as T
import soccer_cards
import sport_page as SP
import raised_stakes
import soccer_lanes
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
            f'{_own_ledger_note()}'
            f'<details class="section-disclosure"><summary><b>Registered lanes</b><span>{len(idle)}</span></summary>'
            f'{idle_html}</details>')
        label = "Method · check needed" if attention else "Method"
        return label, f"{len(idle)} waiting for a market", inner, attention
    return _method


def rule_name(row):
    own = row.get("own")
    return own["label"] if own else soccer_cards._rule_name(row)


def market(d, row):
    own = row.get("own")
    return own["market"] if own else soccer_cards.market(d, row)


def definition(d, row):
    own = row.get("own")
    if not own:
        return SP.default_definition(d, row)
    note = (row.get("meta") or {}).get("note")
    return own["details"] + (SP.definition_html(note) if note else "")


def recent(d, row, now=None):
    """The tracker's recent picks (an own-ledger lane's quotes are in the page's ledger too), then an own-ledger
    rule's every entry, in a closed fold."""
    own = row.get("own")
    return soccer_cards.recent_html(d, row, now) + (own.get("entries") or "" if own else "")


def _raised(row):
    """The follower trades this Production pair at a raised stake (raised_stakes.py): a small badge, no amount."""
    if not row.get("prod"):
        return row
    return dict(row, raised=raised_stakes.raised(row.get("pair") or f'{row["name"]}|{row["sport"]}'))


def _tradeable(row, d, st):
    """A Production rule's headline is the legs the follower can take (2026-11-06, Olu): the paper legs inside the pair's price cap and band
    (live_caps.py, read from the follower itself). The record of every leg stays in the row's fold; the ledger is not touched. A row
    with no leg outside the guard is returned as it came."""
    import live_caps as LC
    import soccer_lanes as L
    if not row.get("prod") or row.get("own"):
        return row
    pair = row.get("pair") or f'{row["name"]}|{row["sport"]}'
    if LC.guard(pair) is None:
        return row
    mine = lambda q: q.get("source") == row["name"] and q.get("sport") == row["sport"]
    bad = lambda q: mine(q) and not LC.tradeable(pair, q.get("price"))
    if not any(bad(q) for q in T.bet_rows(d)):
        return row
    d2 = dict(d, quotes=[q for q in d["quotes"] if not bad(q)], _archive=[q for q in (d.get("_archive") or []) if not bad(q)])
    since = T.record_since((st.get("pairs") or {}).get(pair) or {})
    a_t = dict(T.assess(d2, row["name"], row["sport"], since=since, venues=T.TRADEABLE_VENUES))
    a_all = row["a"]
    fresh_v = B.verdict(a_all) == row.get("v")
    out = dict(row, a=dict(a_all, **{k: a_t[k] for k in a_t}), a_all=a_all,
               legs_html=L.legs_table(a_t, a_all))
    if fresh_v:
        out["v"] = B.verdict(out["a"])
    return out


def _own_ledger_note():
    """The own-ledger lanes' shared words and last reads, once, in the method fold (they were each section's footer)."""
    import fmt
    import soccer_lanes as L
    bits = []
    for title, mod in (("Label rules", "soccer_rules"), ("Team scoring rules", "soccer_team_rules"),
                       ("Title contenders' overs", "contender_overs"), ("Argentina & Brasileirão over 1.5", "sa_o15")):
        try:
            m = __import__(mod)
            st = m.load() if os.path.exists(m.PATH) else {}
            last = st.get("last_run")
            bits.append(f'{title} {fmt.when(last) if last else "not yet"}' + (f' ({st["error"]})' if st.get("error") else ""))
        except Exception:                                       # noqa: BLE001
            bits.append(f"{title} could not be read")
    return (
        '<details class="section-disclosure"><summary><b>Own-ledger lanes</b><span>labels · last reads</span></summary>'
        '<p class="sm">The label rules, team scoring, the over 3.5 cheap NO, the goalless dips, the contenders and '
        'Argentina &amp; Brasileirão over 1.5 keep their own ledgers. Each is one row in the tables above, counted as '
        'its ledger counts it: a pick lane on every settled entry at the Kalshi price after the 7% fee; an in-play lane '
        'on its headline exit (the cheap NO\'s 10c bid sold at 4x; a dip\'s headline buy). Their other exits, splits, '
        'versions and research are inside each row.</p>'
        '<p class="sm">Labels: each team\'s last 10 competitive matches against its league\'s mean goals per team (O+/O− '
        'scores more/less, D+/D− concedes more/less). A total-goals pair reads either way round; a team-scoring rule '
        'reads the contract\'s team v its opponent. 2+ is the over 1.5 rung, 3+ the over 2.5 rung. Contenders: the top 3 '
        'of the open Kalshi champion market by mid at entry. Argentina and the Brasileirão are judged apart, never pooled.</p>'
        f'<p class="sm mut">Last scan · {L.esc(" · ".join(bits))}.</p></details>')


def build(d=None, st=None, now=None, own_lanes=True):
    """One page in the Econ Daily layout (2026-11-05, Olu): tiles, filters, the Production rules, the Sandbox
    rules, Events, the Retired fold, Method. Every soccer lane is one row: the tracker's rules (sport_tab), and the
    own-ledger lanes (soccer_lanes: the label rules, team scoring, the over 3.5 cheap NO, the goalless dips, and the
    retired contenders and Argentina & Brasileirao over 1.5). Layout only: each record is counted as before."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    d = d if d is not None else T.load()
    st = st if st is not None else T.load_stages()
    rows = sport_tab.family_rows(d, st, FAMILY)
    idle = sport_tab.idle_lanes(KEY, d, skip=tuple(r["name"] for r in rows))
    # Retired by hand (2026-10-24 and before): their own fold, final record and reason.
    retired = sport_tab.retired_rows(d, st, FAMILY)
    # own_lanes=False: the tracker's rows alone (a test that hands in its own ledger reads that ledger only).
    own_live, own_gone, d, st = (soccer_lanes.rows_and_inputs(d, st, now) if own_lanes else ([], [], d, st))
    rows = [_raised(_tradeable(r, d, st)) for r in rows + own_live]
    sp = SP.spec(
        family=FAMILY, key=KEY, title=TITLE, description=DESCRIPTION, scope=SCOPE,
        venue="Kalshi", rows=rows, events=soccer_cards.events,
        rule_name=rule_name, market=market, definition=definition,
        recent=recent, method=method(idle), retired=list(retired) + own_gone)
    return SP.page(sp, d, st, now, rows=rows, idle=idle)


def main():
    return sport_tab.write(OUT, build())


if __name__ == "__main__":
    raise SystemExit(main())
