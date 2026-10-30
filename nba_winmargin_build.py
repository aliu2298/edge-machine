"""The NBA page's "Win margin tracker" section (nba_winmargin.py): observation only, no buying or selling rule.

Read from data/nba_winmargin_tracker.json. Header-row tables (no <thead>), so sandbox_build.label_cells names each
cell for the phone cards. Never breaks the page: nba_pace_build wraps the call.
"""
import datetime as dt
import html as _h
import os

import nba_winmargin as W

COLS = ("Contracts", "Avg ask", "Reached 2x", "3x", "5x", "Held 10+ min", "Min to 2x", "Min above 2x",
        "Contracts at 2x+", "Won minus ask")


def esc(x):
    return _h.escape(str(x))


def pct(v):
    return "—" if v is None else f"{v * 100:.0f}%"


def num(v, d=0):
    return "—" if v is None else f"{v:.{d}f}"


def cells(s):
    if not s.get("n"):
        return '<td class="num">0</td>' + '<td class="num">—</td>' * (len(COLS) - 1)
    return (f'<td class="num">{s["n"]}</td><td class="num">{s["ask"] * 100:.0f}c</td><td class="num">{pct(s["r2"])}</td>'
            f'<td class="num">{pct(s["r3"])}</td><td class="num">{pct(s["r5"])}</td><td class="num">{pct(s["held"])}</td>'
            f'<td class="num">{num(s["first"])}</td><td class="num">{num(s["above"])}</td><td class="num">{num(s["vol"])}</td>'
            f'<td class="num">{s["edge"] * 100:+.1f}pp</td>')


def table(first_col, groups, rows, key):
    body = ""
    for g in groups:
        sel = [r for r in rows if key(r) == g]
        body += f'<tr><td><b>{esc(g)}</b></td>{cells(W.summarize(sel))}</tr>'
    body += f'<tr><td><i>All eligible</i></td>{cells(W.summarize(rows))}</tr>'
    return (f'<div class="tbl"><table><tr><th>{esc(first_col)}</th>' + "".join(f'<th class="num">{esc(c)}</th>' for c in COLS)
            + f"</tr>{body}</table></div>")


def halves_table(rows):
    body = ""
    for b in ("1-5", "6-10"):
        old, new = W.halves([r for r in rows if r["bucket"] == b])
        for name, s in (("Older half", old), ("Newer half", new)):
            cs = cells(s) if s else f'<td colspan="{len(COLS)}" class="mut">needs 4 contracts</td>'
            body += f'<tr><td><b>{esc(b)}</b></td><td>{name}</td>{cs}</tr>'
    return ('<div class="tbl"><table><tr><th>Bucket</th><th>Half</th>' + "".join(f'<th class="num">{esc(c)}</th>' for c in COLS)
            + f"</tr>{body}</table></div>")


def spark(r, w=120, h=34):
    """A tiny price-path chart as multiples of the entry ask, from the entry hour to 3 hours after the tip, with 2x
    and 3x lines. Inline SVG that takes its colours from the page."""
    pts = [(t, c / 100 / r["ask"]) for t, c, _n in r.get("path") or [] if -3600 <= t <= 3 * 3600]
    if not pts:
        return '<span class="mut">—</span>'
    top = max(3.4, max(m for _t, m in pts) * 1.05)
    x = lambda t: (t + 3600) / (4 * 3600) * w
    y = lambda m: h - 2 - (min(m, top) / top) * (h - 4)
    line = " ".join(f"{x(t):.1f},{y(m):.1f}" for t, m in pts)
    marks = "".join(f'<line x1="0" x2="{w}" y1="{y(k):.1f}" y2="{y(k):.1f}" stroke="currentColor" stroke-opacity=".35" stroke-dasharray="3 3"/>' for k in (1, 2, 3))
    tip_x = x(0)
    return (f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-label="price path as multiples of the entry, 1x 2x 3x lines" '
            f'style="max-width:100%;color:inherit">{marks}<line x1="{tip_x:.1f}" x2="{tip_x:.1f}" y1="0" y2="{h}" stroke="currentColor" stroke-opacity=".25"/>'
            f'<polyline fill="none" stroke="currentColor" stroke-width="1.5" points="{line}"/></svg>')


def last_night(rows):
    nights = sorted({r["night"] for r in rows})
    if not nights:
        return "", None
    night = nights[-1]
    sel = sorted([r for r in rows if r["night"] == night], key=lambda r: (r["tip"], r["event"], -(r["m"]["peak"])))
    body = ""
    for r in sel:
        m = r["m"]
        body += (f'<tr><td>{esc(r["event"].split("-", 1)[1][7:])}</td><td><b>{esc(r["team"])} {esc(r["bucket"])}</b> · {esc(r["side"])}</td>'
                 f'<td class="num">{r["ask"] * 100:.0f}c</td><td class="num">{m["peak"]:.1f}x</td>'
                 f'<td class="num">{num(m["first2"])}</td><td class="num">{num(m["above2"])}</td>'
                 f'<td>{"won" if r["won"] else "lost"}</td><td>{spark(r)}</td></tr>')
    return ('<div class="tbl"><table><tr><th>Game (away home)</th><th>Contract</th><th class="num">Entry ask</th><th class="num">Peak</th>'
            '<th class="num">Min to 2x</th><th class="num">Min above 2x</th><th>Result</th><th>Price path (x entry, 2x / 3x dashed)</th></tr>'
            + body + "</table></div>"), night


def spread_block(state):
    """The comeback-underdog spread line: Comeback teams as the underdog v every other underdog, same entry rule."""
    rows = W.eligible(state.get("spread_rows") or [])
    teams = ", ".join(sorted(W.COMEBACK))
    if not rows:
        inner = '<p class="sm mut">No underdog spread rung has been recorded yet.</p>'
    else:
        key = lambda r: "Comeback team as underdog" if r["comeback"] else "Other underdogs"
        gl = ""
        for g in ("Comeback team as underdog", "Other underdogs"):
            n, hit = W.by_game([r for r in rows if key(r) == g])
            gl += f'<tr><td><b>{esc(g)}</b></td><td class="num">{n}</td><td class="num">{hit}</td><td class="num">{pct(hit / n) if n else "—"}</td></tr>'
        inner = (f'{table("Underdog", ("Comeback team as underdog", "Other underdogs"), rows, key)}'
                 '<p class="sm"><b>By game</b> · a game counts once: did any of the underdog\'s eligible rungs reach 2x</p>'
                 '<div class="tbl"><table><tr><th>Underdog</th><th class="num">Games</th><th class="num">Any rung reached 2x</th><th class="num">Share</th></tr>'
                 f'{gl}</table></div>')
    return (f'<details class="section-disclosure"><summary><b>Comeback underdog spread line</b><span>observation only · '
            f'{len(rows)} rungs</span></summary>'
            '<p class="sm">The underdog\'s Kalshi spread rungs ("wins by over N"), read the same way as the buckets: the ask an hour '
            'before the tip, 5-35c with a spread of 5c or less, then every trade print. Comeback teams won 40% or more of the '
            f'2025-26 games they trailed at half-time: {esc(teams)}. In the Oct 20-28 data their underdog rungs reached 2x in 7 of 9 '
            'games, against about half the games for other underdogs. Nine games prove nothing; this line grows the sample.</p>'
            f'{inner}</details>')


def section(state=None):
    if state is None:
        state = W.load() if os.path.exists(W.PATH) else W.load("/nonexistent")
    rows = W.eligible(state.get("rows") or [])
    games = len(state.get("seen") or {})
    last = state.get("last_run")
    if not rows:
        body = (f'<p class="sm mut">No game has been recorded yet since {esc(state.get("since"))}. The first rows appear after the '
                'first games finish.</p>')
        summ = "no games yet"
    else:
        lt, night = last_night(rows)
        summ = f'{len(rows)} contracts · {games} games since {state.get("since")}'
        body = (f'<p class="sm"><b>By bucket</b> · the margin bucket of the team named</p>{table("Bucket", W.BUCKETS, rows, lambda r: r["bucket"])}'
                f'<p class="sm"><b>By favourite or underdog</b> · the bucket team\'s pregame win share (55% or more, under 45%)</p>'
                f'{table("Team", ("favourite", "toss-up", "underdog"), rows, lambda r: r["role"])}'
                f'<p class="sm"><b>By entry price</b></p>{table("Entry ask", ("5-10c", "10-20c", "20-35c"), rows, lambda r: r["band"])}'
                f'<details class="section-disclosure"><summary><b>Older and newer halves</b><span>buckets 1-5 and 6-10, split by tip time</span></summary>{halves_table(rows)}</details>'
                f'<details class="section-disclosure"><summary><b>Last night\'s games</b><span>{esc(night)} · each contract entry to peak, time above 2x</span></summary>{lt}</details>')
    return f"""<section id="win-margin">
<h2>Win margin tracker</h2>
<p class="shell-kicker">Observation only — no buying or selling rule yet · paper · no orders · since {esc(state.get("since"))}</p>
<details class="section-disclosure" open><summary><b>Kalshi NBA win-margin buckets, bought at the ask an hour before the tip</b><span>{esc(summ)}</span></summary>
<p class="sm">For every game, each bucket contract (both teams: 1-5, 6-10, 11-20, 21+) is read at the ask one hour before the tip, then followed through every trade print. Only contracts with an entry ask of 5-35c and a spread of 5c or less are counted. The tip is the Kalshi game market's time minus 3 hours.</p>
<p class="sm">Reached means a trade at or after the tip printed at 2, 3 or 5 times the entry ask (a target above 99c is left out of that rate). At fair prices a contract reaches 2x about {W.FAIR[2] * 100:.0f}% of the time, 3x {W.FAIR[3] * 100:.0f}% and 5x {W.FAIR[5] * 100:.0f}%. Held 10+ min is the share that stayed at 2x or more for ten minutes or longer. Min to 2x, Min above 2x and Contracts at 2x+ are medians over the contracts that reached 2x. Won minus ask is the share that settled yes less the average ask paid.</p>
{body}
</details>
{spread_block(state)}
<p class="sm mut">Last read {esc(last or 'not yet')}{(' · ' + esc(state['error'])) if state.get('error') else ''}.</p>
</section>"""


def place(html, state=None):
    """Put the section directly above the Safe Card (so under the cheap-side card). Never breaks the page."""
    try:
        import sandbox_build
        sec = sandbox_build.label_cells(section(state))
        at = html.find('<section id="safe-card"')
        if at < 0:
            at = html.find("<section id=", html.find("<main"))
        return html[:at] + sec + html[at:] if at >= 0 else html
    except Exception:                                           # noqa: BLE001
        return html
