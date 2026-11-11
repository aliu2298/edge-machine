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


# The page's layout (2026-11-11, Olu): the Production rows and tiles read Live (the follower's own fills) over Paper; every list
# starts closed; rows drop the two evidence cells (in the fold) so names fit; a short empty state. A test of the shared template's
# defaults sets this to {}.
LAYOUT = dict(live=True, fold_prod=True, compact=True, empty_reason=lambda d_, rs, idle_, now_: "no qualifying price yet")


def method(idle):
    """Method, closed: how Live and Paper are counted, the labels in words, and two small folds (rules waiting for a first pick, the
    last data reads). The old Kalshi pre-flight note is gone (2026-11-11): its file is only refreshed by hand, so it read as an alarm."""
    def _method(d, rows, now):
        idle_html = sport_tab._idle_html(idle, {}, status=False, prefix=KEY)
        inner = (
            '<p class="sm">Prices are the Kalshi ask logged when a rule fired; results are Kalshi\'s own settlement.</p>'
            '<p class="sm"><b>Live</b> is the follower\'s own fills, settled by Kalshi, counted from the day each rule moved to '
            'Production (or its stake was raised). <b>Paper</b> is the same rule\'s picks over the same days at the Kalshi price, '
            'after fees. A rule\'s full paper record, the one its 30-bet verdict reads, is inside its row.</p>'
            '<p class="sm"><b>Labels.</b> Each team\'s last 10 competitive matches against its league\'s average goals per team: '
            '<i>attacking</i> scores at least the average, <i>low-scoring</i> less; <i>leaky</i> concedes at least the average, '
            '<i>tight</i> less. The codes (O+/O−, D+/D−) are inside each rule.</p>'
            f'<details class="section-disclosure"><summary><b>Registered lanes · waiting for a first pick</b><span>{len(idle)}</span></summary>'
            f'{idle_html}</details>'
            f'{_own_ledger_note()}')
        return "Method", "how Live and Paper are counted", inner, False
    return _method


# Plain-English names (2026-11-11, Olu: "plain-English rule names"): a team's label read as words. O+ / O- = scores at least / less
# than its league's average, D+ / D- = concedes at least / less. The codes stay inside each rule's fold.
_O = {"O+": "attacking", "O-": "low-scoring"}
_D = {"D+": "leaky", "D-": "tight"}


def label_words(part):
    """'O+D-' -> 'attacking, tight'; 'O+' -> 'attacking'; 'D-' -> 'tight'."""
    part = part.replace("−", "-")
    if len(part) == 4:
        return f"{_O[part[:2]]}, {_D[part[2:]]}"
    return _O.get(part) or _D[part]


def _a(words):
    return ("an " if words[0] in "aeiou" else "a ") + words


def test_words(test):
    """A match test in words: 'two attacking, tight sides meet', 'a tight side meets an attacking one', 'either side is low-scoring'."""
    if test[0] == "either":
        return f"either side is {label_words(test[1])}"
    _, x, y = test
    if x == y:
        return f"two {label_words(x)} sides meet"
    return f"{_a(label_words(x))} side meets {_a(label_words(y))} one"


def plain_name(row):
    """The plain-English name of a label rule (sr_*), a team rule (st_*) or T1-M's readout; None for any other row."""
    import soccer_rules as SR
    import soccer_team_rules as TR
    name = row.get("name") or ""
    t1 = test_words(("pair", "O+D-", "O+D-"))
    if name.startswith("sr_"):
        r = SR.RULES.get(name[3:].upper())
        if not r:
            return None
        where = "Every BTTS league" if r["league"] == SR.ALL else r["league"]
        bet = (f'Both teams to score {"YES" if r["side"] == "yes" else "NO"}' if r.get("market") == "btts"
               else f'{"Over" if r["side"] == "yes" else "Under"} {r["line"]}')
        return f"{where} · {bet} when {test_words(r['test'])}"
    if name == "t1m_sell15":
        return f"Over 3.5 when {t1}, sold at 1.5x (readout)"
    if name == "st_t1h":
        return f"Home side scores 2+ when {t1}"
    if name == "st_t1m":
        return f"Over 3.5 when {t1}"
    if name.startswith("st_"):
        r = TR.RULES.get(name[3:].upper())
        if not r:
            return None
        bet = f"scores {r['goals']}+" if r["side"] == "yes" else f"held under {r['goals']}"
        if r["own"] == r["opp"]:
            return f"Team {bet} when two {label_words(r['own'])} sides meet"
        return f"{_a(label_words(r['own'])).capitalize()} side {bet} v {_a(label_words(r['opp']))} one"
    return None


def rule_name(row):
    own = row.get("own")
    return plain_name(row) or (own["label"] if own else soccer_cards._rule_name(row))


def market(d, row):
    own = row.get("own")
    return own["market"] if own else soccer_cards.market(d, row)


def definition(d, row):
    own = row.get("own")
    if not own:
        return SP.default_definition(d, row)
    note = (row.get("meta") or {}).get("note")
    code = (f'<p class="sm mut">Code: {SP.esc(own["label"])}</p>' if plain_name(row) else "")
    return code + own["details"] + (SP.definition_html(note) if note else "")


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
        '<details class="section-disclosure"><summary><b>Last data reads</b><span>rules with their own records</span></summary>'
        f'<p class="sm mut">{L.esc(" · ".join(bits))}.</p></details>')


def build(d=None, st=None, now=None, own_lanes=True):
    """One page in the Econ Daily layout (2026-11-05, Olu): tiles, filters, the Production rules, the Sandbox
    rules, Events, the Retired fold, Method. Every soccer lane is one row: the tracker's rules (sport_tab), and the
    own-ledger lanes (soccer_lanes: the label rules, team scoring, the over 3.5 cheap NO, the goalless dips, and the
    retired contenders and Argentina & Brasileirao over 1.5). Layout only: each record is counted as before."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    d = d if d is not None else T.load()
    st = st if st is not None else T.load_stages()
    rows = sport_tab.family_rows(d, st, FAMILY)
    if own_lanes:          # 2026-11-06: one row from registration, its headline the maker bid (corners_fav_no_build)
        import corners_fav_no_build
        rows = corners_fav_no_build.place(d, rows)
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
        recent=recent, method=method(idle), retired=list(retired) + own_gone,
        **LAYOUT)
    return SP.page(sp, d, st, now, rows=rows, idle=idle)


def main():
    return sport_tab.write(OUT, build())


if __name__ == "__main__":
    raise SystemExit(main())
