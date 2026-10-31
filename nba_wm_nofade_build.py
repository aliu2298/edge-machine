"""The NBA page's "Win margin · NO fade" card (nba_wm_nofade.py), inside the Cheap side + resting take-profit card,
directly under the YES split lane so the two read side by side. Header-row tables, so the page's label_cells names each
cell for the phone layout. Never breaks the page: chaos_build wraps the call.
"""
import html as _h

import chaos_replay as CR
import nba_wm_nofade as N


def esc(x):
    return _h.escape(str(x))


def pct(v, sign=True):
    return "—" if v is None else (f"{v * 100:+.1f}%" if sign else f"{v * 100:.0f}%")


def zfmt(v):
    return "—" if v is None else f"{v:+.2f}"


def status(settled_games):
    if settled_games >= N.DECIDE_N:
        return f"{settled_games} games · decide now (30 reached)"
    if settled_games >= N.REVIEW_N:
        return f"{settled_games} games · review due (10 reached) · decide at 30"
    return f"{settled_games} games · review at 10, decide at 30"


def variant_rows(state, insample, label=None):
    rows = []
    for d in N.DIPS:
        key = N.vkey(d)
        g = N.game_rows(state["entries"], key, insample)
        s = CR.stats(g)
        fills = sum(r["fills"] for r in g)
        sold = sum(r["sold"] for r in g)
        name = f"<b>{esc(N.vlabel(key))}</b>" + (" · headline" if d == N.HEAD and not insample else "")
        rows.append(f'<tr data-variant="{esc(key)}"><td>{name}</td><td class="num">{s["n"]}</td><td class="num">{fills}</td>'
                    f'<td class="num">{sold}</td><td class="num">{s["won"]}</td><td class="num">{pct(s["roi"])}</td>'
                    f'<td class="num">{zfmt(s["z"])}</td><td class="num">{s["nights"]}</td>'
                    + ("" if insample else f'<td>{esc(status(s["n"]))}</td>') + '</tr>')
    return ('<div class="tbl"><table class="nofade-variants"><tr><th>Row</th><th class="num">Games with a fill</th><th class="num">Fills</th>'
            '<th class="num">Sold back</th><th class="num">Games won</th><th class="num">ROI after fees</th>'
            '<th class="num">z (by night)</th><th class="num">Nights</th>' + ("" if insample else "<th>Status</th>")
            + "</tr>" + "".join(rows) + "</table></div>")


def yes_trades(chaos, lane_id):
    L = ((chaos or {}).get("lanes") or {}).get(lane_id)
    if not L:
        return L, []
    return L, [t for t in CR.counted(L.get("trades") or [], L) if t["exit_key"] == CR.SPLIT]


def side_by_side(state, chaos):
    """The YES split row and the NO fade row on the fresh record, and how often both traded the same game."""
    L, yt = yes_trades(chaos, "nba_winmargin_split")
    ys = CR.stats(yt)
    yh = CR.stats([t for t in CR.counted(L.get("trades") or [], L) if t["exit_key"] == "hold"]) if L else CR.stats([])
    ng = N.game_rows(state["entries"], N.vkey(N.HEAD), False)
    ns = CR.stats(ng)
    yes_events = {t["event"] for t in yt}
    no_events = {r["event"] for r in ng}
    both = yes_events & no_events
    same = 0
    for e in state["entries"]:
        if e["event"] not in both or e.get("insample"):
            continue
        yb = {t["ticker"] for t in yt if t["event"] == e["event"]}
        same += sum(1 for r in e["buckets"] if r["ask"]["status"] == "verified" and r["fills"].get(N.vkey(N.HEAD)) and r["id"] in yb)
    games_read = sum(1 for e in state["entries"] if not e.get("insample"))
    rows = (f'<tr><td><b>YES split · win margin 1-5 / 6-10</b> (buy YES 10-20c, sell half at 2x, half at 3x)</td>'
            f'<td class="num">{len(yes_events)}</td><td class="num">{pct(ys["roi"])}</td><td class="num">{pct(yh["roi"])}</td>'
            f'<td class="num">{zfmt(ys["z"])}</td></tr>'
            f'<tr><td><b>NO fade · all buckets</b> (buy NO at 75% of pregame, sell back at pregame)</td>'
            f'<td class="num">{len(no_events)}</td><td class="num">{pct(ns["roi"])}</td><td class="num">—</td>'
            f'<td class="num">{zfmt(ns["z"])}</td></tr>')
    table = ('<div class="tbl"><table class="nofade-compare"><tr><th>Lane</th><th class="num">Games traded</th><th class="num">ROI after fees</th>'
             '<th class="num">Same entries held</th><th class="num">z (by night)</th></tr>' + rows + "</table></div>")
    overlap = (f'<p class="sm"><b>Overlap</b> · fresh record: {games_read} games read, {len(yes_events)} with a YES split entry, {len(no_events)} with a NO fade fill, '
               f'<b>{len(both)} with both</b>, {same} where both traded the same bucket. They are opposite sides of a bucket, so a game with both can hedge itself.</p>')
    return table + overlap


def card(state=None, chaos=None):
    if state is None:
        state = N.load()
    c = N.counts(state["entries"], False)
    i = N.counts(state["entries"], True)
    head = N.game_rows(state["entries"], N.vkey(N.HEAD), False)
    last = state.get("last_run")
    return f"""<details class="section-disclosure" data-lane="{N.LANE}" open><summary><b>{esc(N.LABEL)}</b><span>{c['games']} games read · {len(head)} with a fill · fresh record since {esc(N.SINCE)}</span></summary>
<p class="sm">When a bucket's YES spikes its NO crashes, and the spike reverts. After the tip, a resting NO buy at 75% of the NO price an hour before (85% and 65% are tracked too) fills on a traded print, with at least {N.MIN_FILL} contracts traded at or under the limit within an hour. It is sold back at the pregame price on a later print, else held to settlement. Every bucket whose pregame NO price was 10-95c with a YES spread of 5c or less, both teams. Maker fees in and out. The outcome is the game: a game's filled buckets are one row, z is clustered by night. Review at {N.REVIEW_N} games, decide at {N.DECIDE_N}. Paper only.</p>
<p class="sm"><b>Ask check</b> · a bucket counts only when the pregame price was real: {N.CHECK_MIN}+ contracts traded at or through it in the hour after, and it was not under half the last trade. Skipped as unverified ask: {c['unverified']} of {c['unverified'] + c['verified']} buckets.</p>
{variant_rows(state, False)}
<p class="sm"><b>Next to the YES split</b></p>
{side_by_side(state, chaos)}
<details class="section-disclosure" id="nofade-insample"><summary><b>In-sample result</b><span>{esc(N.SINCE_IN)} to {esc(N.SINCE)}, the days the rule was chosen on · not evidence</span></summary>
<p class="sm mut">The same rule on Oct 20-30, shown once and apart. The rule was found on this data, so it is NOT evidence and is never the headline. {i['games']} games read, {i['unverified']} of {i['unverified'] + i['verified']} buckets skipped as unverified ask.</p>
{variant_rows(state, True)}</details>
<p class="sm mut">Last read {esc(last or 'not yet')}{(' · ' + esc(state['error'])) if state.get('error') else ''}. Replayed after the game from Kalshi's trade prints and 1-minute candles; no live book is read.</p>
</details>"""


def index_row(state=None):
    """The Sandbox Chaos index row (same columns as chaos_build.index)."""
    if state is None:
        state = N.load()
    g = N.game_rows(state["entries"], N.vkey(N.HEAD), False)
    s = CR.stats(g)
    return (f'<tr data-lane="{N.LANE}"><td><b>{esc(N.LABEL)}</b></td><td><a href="./nba.html#cheap-side">NBA</a></td>'
            f'<td class="num">{sum(r["fills"] for r in g)}</td><td class="num">{s["won"]}</td><td class="num">{pct(s["roi"])}</td>'
            f'<td class="num">—</td><td>{esc(status(s["n"]))}</td></tr>')
