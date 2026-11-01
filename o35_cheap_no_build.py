"""The Soccer page's "Cheap side + resting bid" section for o35_cheap_no_wave (o35_cheap_no.py), near the top.

Read from the lane's own ledger (data/o35_cheap_no_ledger.json). Header-row tables, so the page's own
label_cells names each cell for the phone layout. Never breaks the page: soccer_build wraps the call.
"""
import datetime as dt
import html as _h
import os

import chaos_replay as CR
import o35_cheap_no as O

HEAD = O.vkey(O.HEADLINE, O.HEAD_MULT)
V1_HEAD = O.vkey(O.HEADLINE, O.V1_HEAD_MULT)
# The ROI basis change (2026-10-31, Olu): chaos_replay.stats(), which this section reads, moved from sum profit / sum
# cost to the equal-stake mean. Said once, with the headline and hold as they read on the old basis that day.
ROI_BASIS = dict(on="2026-10-31", head=0.0786, hold=-0.1796, n=36)


def esc(x):
    return _h.escape(str(x))


def pct(v, sign=True):
    return "—" if v is None else (f"{v * 100:+.0f}%" if sign else f"{v * 100:.0f}%")


def zfmt(v):
    return "—" if v is None else f"{v:+.2f}"


def clock(ts):
    t = dt.datetime.fromtimestamp(ts, O.UTC).astimezone(O.ET)
    return f"{t:%b %-d, %-I:%M %p}"


def halves(rows):
    """ROI of the older and the newer half of a variant's rows (by kickoff), or (None, None) under 4 rows."""
    rows = sorted(rows, key=lambda r: r["kickoff"])
    if len(rows) < 4:
        return None, None
    k = len(rows) // 2
    return CR.stats(rows[:k])["roi"], CR.stats(rows[k:])["roi"]


def read_of(n, delta=None):
    if n < O.REVIEW_N:
        return f"too early ({n} of {O.REVIEW_N})"
    if n < O.DECIDE_N:
        return f"review ({n} of {O.DECIDE_N} to decide)"
    return "decide"


def variant_table(rows, limits, head, mults, hold):
    """One row per exit. v2 shows 4x (headline) and 3x only; the v1 fold shows everything it ever recorded."""
    body = []
    for lim in limits:
        hs = CR.stats([r for r in rows if r["variant"] == O.vkey(lim, None)])
        for m in mults:
            key = O.vkey(lim, m)
            rs = [r for r in rows if r["variant"] == key]
            s = CR.stats(rs)
            old, new = halves(rs)
            delta = None if m is None or s["roi"] is None or hs["roi"] is None else s["roi"] - hs["roi"]
            bold = " class=\"hl\"" if key == head else ""
            hcell = f'<td class="num">{pct(hs["roi"]) if m is not None else "—"}</td>' if hold else ""
            body.append(f'<tr data-variant="{key}"{bold}><td><b>{esc(O.vlabel(key))}{" (headline)" if key == head else ""}</b></td>'
                        f'<td class="num">{s["n"]}</td><td class="num">{s["won"]}</td><td class="num">{pct(s["roi"])}</td>'
                        f'{hcell}'
                        f'<td class="num">{zfmt(s["z"])}</td><td class="num">{s["nights"]}</td>'
                        f'<td class="num">{pct(old)}</td><td class="num">{pct(new)}</td>'
                        f'<td class="num">{sum(1 for r in rs if r["dead"])}</td><td class="num">{sum(1 for r in rs if r["thin"])}</td>'
                        f'<td>{esc(read_of(s["n"], delta if hold else None))}</td></tr>')
    hh = '<th class="num">Hold, same bid</th>' if hold else ""
    return ('<div class="tbl"><table><tr><th>Bid · exit</th><th class="num">Filled</th><th class="num">Won</th>'
            f'<th class="num">ROI after fees</th>{hh}<th class="num">z (by night)</th>'
            '<th class="num">Nights</th><th class="num">Older half</th><th class="num">Newer half</th>'
            '<th class="num">Dead fills</th><th class="num">Thin sells</th><th>Read</th></tr>' + "".join(body) + "</table></div>")


def league_table(entries, rows, head, hold_on=True):
    head_rows = [r for r in rows if r["variant"] == head]
    hold_rows = [r for r in rows if r["variant"] == O.vkey(O.HEADLINE, None)]
    sell = head.split("_")[1]
    hh = '<th class="num">Hold</th>' if hold_on else ""
    body = []

    def row(name, games, sel, bold=True):
        a = CR.stats([r for r in head_rows if sel(r)])
        h = CR.stats([r for r in hold_rows if sel(r)])
        hc = f'<td class="num">{pct(h["roi"]) if h["n"] else "—"}</td>' if hold_on else ""
        nm = f"<b>{esc(name)}</b>" if bold else f"<i>{esc(name)}</i>"
        body.append(f'<tr><td>{nm}</td><td class="num">{games}</td><td class="num">{a["n"]}</td>'
                    f'<td class="num">{pct(a["roi"]) if a["n"] else "—"}</td>{hc}</tr>')

    for lg in sorted({e["league"] for e in entries}):
        row(lg, sum(1 for e in entries if e["league"] == lg), lambda r, lg=lg: r["league"] == lg)
    forms = sum(1 for e in entries if e["form_rule"])
    row("Over 1.5 form-rule matches", forms, lambda r: r["form_rule"], False)
    row("All other matches", len(entries) - forms, lambda r: not r["form_rule"], False)
    return ('<div class="tbl"><table><tr><th>League</th><th class="num">Games</th><th class="num">Filled at 10c</th>'
            f'<th class="num">Sell at {sell}</th>{hh}</tr>' + "".join(body) + "</table></div>")


def trade_list(entries, mults, hold, limit=30):
    filled = [(e, e["bids"].get("10")) for e in entries if (e.get("bids") or {}).get("10")]
    filled.sort(key=lambda x: x[0]["kickoff"], reverse=True)
    body = []
    for e, b in filled[:limit]:
        cells = []
        cost = b["limit"] + O.fee(b["limit"])
        for m in mults:
            s = b["sells"][str(m)]
            tag = "sold" if s["filled"] else ("thin" if s["thin"] else "held")
            proceeds = s["target"] - O.fee(s["target"]) if s["filled"] else b["payout"]
            cells.append(f'<td class="num">{(proceeds - cost) / cost * 100:+.0f}% {tag} · {s["volume"]:.0f}</td>')
        hc = f'<td class="num">{(b["payout"] - cost) / cost * 100:+.0f}%</td>' if hold else ""
        body.append(f'<tr><td>{esc(clock(e["kickoff"]))}</td><td>{esc(e["event"].split("-", 1)[-1])}</td><td>{esc(e["league"])}</td>'
                    f'<td class="num">{b["fill_print"] * 100:.0f}c{" · dead fill" if b["dead"] else ""}</td>'
                    + "".join(cells) + hc + '</tr>')
    cols = 4 + len(mults) + (1 if hold else 0)
    body = "".join(body) or f'<tr><td colspan="{cols}" class="mut">No bid has filled yet.</td></tr>'
    heads = "".join(f'<th class="num">Sell at {m}x · contracts</th>' for m in mults) + ('<th class="num">Hold</th>' if hold else "")
    return ('<div class="tbl"><table><tr><th>Kickoff (ET)</th><th>Match</th><th>League</th><th class="num">Filled at</th>'
            + heads + '</tr>' + body + "</table></div>")


def v1_fold(entries):
    """The v1 record as it stands, collapsed: every bid, every exit, the old 2x headline, hold included."""
    if not entries:
        return ""
    rows = O.trade_rows(entries)
    f10 = [e for e in entries if (e["bids"] or {}).get("10")]
    dead = sum(1 for e in f10 if e["bids"]["10"]["dead"])
    summ = f'{len(entries)} games · {len(f10)} bids filled at 10c · {dead} dead · closed 2026-10-31'
    allm = (None,) + O.MULTS
    return (f'<details class="section-disclosure" data-lane="{O.LANE}_v1"><summary><b>{esc(O.V1_LABEL)}</b><span>{esc(summ)}</span></summary>'
            f'<p class="sm">The first record: 10c, 15c and 20c bids in twelve leagues, headline sold at 2x, ended 2026-10-31 and shown as it stood. '
            f'{esc(O.TRIM_NOTE)}</p>'
            f'<p class="sm mut roi-basis">ROI basis changed {ROI_BASIS["on"]} from cost-weighted to equal-stake (the mean of each fill\'s ROI, the same quantity its z tests); '
            f'old figure: 10c bid sold at 2x {pct(ROI_BASIS["head"])}, hold {pct(ROI_BASIS["hold"])} on {ROI_BASIS["n"]} fills.</p>'
            + variant_table(rows, O.V1_LIMITS, V1_HEAD, allm, True)
            + '<p class="sm"><b>By league, and the over 1.5 form-rule matches</b> · 10c bid, sell at 2x</p>'
            + league_table(entries, rows, V1_HEAD) + '</details>')


def section(state=None):
    if state is None:
        state = O.load() if os.path.exists(O.PATH) else O.load("/nonexistent")
    all_entries = sorted(state.get("entries") or [], key=lambda e: e["kickoff"])
    old, entries = O.split(all_entries)
    rows = O.trade_rows(entries)
    filled10 = [e for e in entries if (e["bids"] or {}).get("10")]
    dead = sum(1 for e in filled10 if e["bids"]["10"]["dead"])
    thin = sum(1 for e in filled10 if e["bids"]["10"]["sells"][str(O.HEAD_MULT)]["thin"])
    last = state.get("last_run")
    summ = (f'{len(entries)} games · {len(filled10)} bids filled at 10c · {dead} dead · {thin} thin' if entries
            else "0 entries since the v2 record began")
    shown = (O.COMPARE_MULT, O.HEAD_MULT)
    body = (variant_table(rows, O.LIMITS, HEAD, (O.HEAD_MULT, O.COMPARE_MULT), False)
            + '<p class="sm"><b>By league, and the over 1.5 form-rule matches</b> · 10c bid, sell at 4x</p>'
            + league_table(entries, rows, HEAD, False) if entries else '<p class="sm mut">0 entries: no game has settled since the v2 record began on '
            f'{esc(state.get("since"))}. The first rows appear after the first matches finish.</p>')
    return f"""<section id="cheap-side">
<h2>Cheap side · resting bid</h2>
<p class="shell-kicker">Paper only · no orders · fresh v2 record since {esc(state.get("since"))} · review at {O.REVIEW_N} filled, decide at {O.DECIDE_N}</p>
<details class="section-disclosure" data-lane="{O.LANE}" open><summary><b>{esc(O.LABEL)}</b><span>{esc(summ)}</span></summary>
<p class="sm mut">{esc(O.TRIM_NOTE)}</p>
<p class="sm">On the over 3.5 goals market of every game in the eleven leagues on this page, a NO bid rests at 10c before kickoff. It can fill only in play, after goals push the over to 80c or more. The headline sells at 4x the bid (40c); selling at 3x is shown beside it.</p>
<p class="sm">A bid fills when the first trade after it prints NO at or under the bid. Fills after the 4th goal are kept and marked dead fill. A sell counts only if a later trade prints at or above its target and at least {O.MIN_VOL} contracts traded at or above the target after the fill; fewer is marked thin and the trade is held. Fees: 1.75% of p(1-p) on both legs. Kickoff is the Kalshi time minus 4 hours.</p>
{body}
<details class="section-disclosure"><summary><b>Fills</b><span>latest 30 at 10c</span></summary>{trade_list(entries, shown, False)}</details>
{v1_fold(old)}
</details>
<p class="sm mut">Last read {esc(last or 'not yet')}{(' · ' + esc(state['error'])) if state.get('error') else ''}.</p>
</section>"""


def place(html, state=None):
    """Put the section near the top: before the page's first <section id=...> in <main>. Never breaks the page."""
    try:
        import sandbox_build
        sec = sandbox_build.label_cells(section(state))
        at = html.find("<section id=", html.find("<main"))
        return html[:at] + sec + html[at:] if at >= 0 else html
    except Exception:                                           # noqa: BLE001
        return html
