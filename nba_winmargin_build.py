"""The NBA page's Win margin tracker section (nba_winmargin.py), observation only.

Summary tables by bucket, by the bucket team's pregame standing and by entry price, each against
what a fair price implies; older v newer halves for the two close buckets; last night's games, each
bucket's entry, peak and minutes at 2x+ (no inline SVG: the NBA page's tests forbid <svg> tags).
Never breaks the board: nba_pace_build wraps the call. Tables are written without <thead> so
sandbox_build.label_cells names every cell for the phone cards.
"""
import html as _h
import os

import fmt
import nba_winmargin as W

FAIR = {"r2": 0.50, "r3": 1 / 3, "r5": 0.20}
SIDES = (("favourite", "Bucket team favourite (55%+)"), ("toss-up", "Toss-up (45-55%)"),
         ("underdog", "Bucket team underdog (under 45%)"))
BANDS = ("5-10c", "10-20c", "20-35c")


def esc(x):
    return _h.escape(str(x))


def _p(v):
    return "—" if v is None else f"{v * 100:.0f}%"


def _min(v):
    return "—" if v is None else f"{v:.0f} min"


def _n(v):
    return "—" if v is None else f"{v:,.0f}"


def _vs_fair(s, k):
    v = s.get(k)
    if v is None:
        return "—"
    tone = "pos" if v > FAIR[k] else "neg" if v < FAIR[k] else ""
    return f'<span class="{tone}">{v * 100:.0f}%</span>' if tone else f"{v * 100:.0f}%"


HEAD = ('<tr><th>{first}</th><th class="num">n</th><th class="num">Avg ask</th>'
        '<th class="num">Reached 2x (fair 50%)</th><th class="num">Reached 3x (fair 33%)</th>'
        '<th class="num">Reached 5x (fair 20%)</th><th class="num">Held 2x+ for 10+ min</th>'
        '<th class="num">Median min to 2x</th><th class="num">Median min at 2x+</th>'
        '<th class="num">Median contracts at 2x+</th><th class="num">Won − ask</th></tr>')


def _row(label, s):
    return (f'<tr><td><b>{esc(label)}</b></td><td class="num">{s["n"]}</td><td class="num">{s["ask"] * 100:.1f}c</td>'
            f'<td class="num">{_vs_fair(s, "r2")}</td><td class="num">{_vs_fair(s, "r3")}</td>'
            f'<td class="num">{_vs_fair(s, "r5")}</td><td class="num">{_p(s["held10"])}</td>'
            f'<td class="num">{_min(s["first2"])}</td><td class="num">{_min(s["above2"])}</td>'
            f'<td class="num">{_n(s["vol2"])}</td><td class="num">{s["won_minus_ask"] * 100:+.1f}c</td></tr>')


def table(first, groups):
    if not groups:
        return '<p class="sm mut">No settled game in the tracker yet.</p>'
    rows = "".join(_row(label, s) for label, s in groups)
    return f'<div class="tbl"><table class="wm-table">{HEAD.format(first=esc(first))}{rows}</table></div>'


def night_label(d):
    """2026-10-20 -> Oct 20 (Kalshi's game date, kept as a calendar day: no time-zone shift)."""
    try:
        y, m, dd = (int(x) for x in str(d).split("-"))
        return f"{('Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec')[m - 1]} {dd}"
    except (ValueError, IndexError):
        return str(d)


def _span(rows):
    nights = [r["night"] for r in rows if r.get("night")]
    if not nights:
        return ""
    a, b = min(nights), max(nights)
    return f" ({night_label(a)} – {night_label(b)})" if a != b else f" ({night_label(a)})"


def halves_groups(pop):
    out = []
    for b in ("1-5", "6-10"):
        rows = [r for r in pop if r["bucket"] == b]
        if len(rows) < 2:
            continue
        old, new = W.halves(rows)
        out.append((f"{b} · older half{_span(old)}", W.stats(old)))
        out.append((f"{b} · newer half{_span(new)}", W.stats(new)))
    return out


def _first(v):
    """Minutes from the tip to the first print at 2x: "+34 min", "12 min before the tip", or "—"."""
    if v is None:
        return "—"
    return f"{v:+.0f} min" if v >= 0 else f"{-v:.0f} min before the tip"


def last_night_html(state):
    night, games = W.last_night(state)
    if not games:
        return '<p class="sm mut">No settled game yet.</p>'
    rows = []
    for g in games:
        pop = [r for r in g.get("rows") or [] if r.get("pop") and r.get("m")]
        game = f"{g.get('away')} @ {g.get('home')}"
        if not pop:
            rows.append(f'<tr><td><b>{esc(game)}</b></td><td colspan="5" class="mut">No bucket at 5-35c with a tight '
                        f'spread an hour before the tip.</td></tr>')
            continue
        for r in pop:
            m = r["m"]
            peak = r["ask"] * m["peak"]
            res = {"yes": "won", "no": "lost"}.get(r.get("result"), "—")
            rows.append(f'<tr><td><b>{esc(game)}</b></td><td>{esc(r["team"])} by {esc(r["bucket"])}</td>'
                        f'<td class="num">{r["ask"] * 100:.0f}c → {peak * 100:.0f}c ({m["peak"]:.1f}x)</td>'
                        f'<td class="num">{m["above2"]:.0f} min</td><td class="num">{esc(res)}</td>'
                        f'<td class="num">{_first(m["first2"])}</td></tr>')
    head = ('<tr><th>Game</th><th>Bucket</th><th class="num">Entry → peak</th><th class="num">Minutes at 2x+</th>'
            '<th class="num">Settled</th><th class="num">First 2x</th></tr>')
    return (f'<p class="sm">{esc(night_label(night))} · {len(games)} game{"s" if len(games) != 1 else ""} · only buckets in the '
            f'summary population are listed.</p><div class="tbl"><table class="wm-night">{head}{"".join(rows)}</table></div>')


def section(state=None):
    if state is None:
        state = W.load() if os.path.exists(W.PATH) else W.empty()
    pop = W.population(state)
    s = W.summary(state)
    by_bucket = W.group(pop, lambda r: r["bucket"], W.BUCKETS)
    by_side = [(label, st) for (k, st) in W.group(pop, lambda r: r["side"], [k for k, _ in SIDES])
               for kk, label in SIDES if kk == k]
    by_band = W.group(pop, lambda r: r["band"], BANDS)
    last = state.get("last_run")
    err = state.get("error")
    return f"""<section id="winmargin">
<h2>Win margin tracker</h2>
<p><b>Observation only — no buying or selling rule yet.</b> Nothing here is a bet or a signal.</p>
<ul class="sm"><li>Every Kalshi NBA win-margin bucket ("Boston wins by 1-5 points"), both teams, every game since opening night (Oct 20).</li>
<li>Entry is the ask one hour before the tip. After that, only real trade prints count.</li>
<li>A fair contract bought at its ask reaches 2x about half the time, 3x a third and 5x a fifth. Green beats that, red falls short.</li></ul>
<p class="sm mut">Shown: entry ask 5-35c with a bid-ask spread of 5c or less · {s["population"]} contracts from {s["games"]} settled games. "Held 2x+ for 10+ min" and the minutes count the time from each print at 2x or more to the next print. Medians of minutes and contracts are over the contracts that reached 2x. Won − ask is the average settled value minus the ask, per contract.</p>
<h3>By bucket</h3>
{table("Bucket (points)", by_bucket)}
<h3>By the bucket team's pregame standing</h3>
<p class="sm mut">The team's win share is its four bucket mids summed an hour before the tip, against both teams' sums.</p>
{table("Standing", by_side)}
<h3>By entry price</h3>
{table("Entry ask", by_band)}
<details class="section-disclosure wm-halves"><summary><b>Older v newer games</b><span>1-5 and 6-10 buckets</span></summary>
<p class="sm mut">Each bucket's contracts in tip order, split in two halves. A pattern that is real should hold in both.</p>
{table("Bucket · half", halves_groups(pop))}
</details>
<details class="section-disclosure wm-last"><summary><b>Last night's games</b><span>entry → peak, minutes at 2x+</span></summary>
{last_night_html(state)}
</details>
<p class="sm mut">Collected from Kalshi's public data (1-minute candles for the entry, trade prints after) by nba_winmargin.py · last run {esc(fmt.when(last) if last else "not yet")}{(" · " + esc(err)) if err else ""}.</p>
</section>"""
