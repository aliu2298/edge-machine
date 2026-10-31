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


def read_of(n, delta):
    if n < O.REVIEW_N:
        return f"too early ({n} of {O.REVIEW_N})"
    if n < O.DECIDE_N:
        return f"review ({n} of {O.DECIDE_N} to decide)"
    return "decide" + (" · beats hold" if delta is not None and delta > 0 else "")


def variant_table(rows):
    body = []
    for lim in O.LIMITS:
        hold = [r for r in rows if r["variant"] == O.vkey(lim, None)]
        hs = CR.stats(hold)
        for m in (None,) + O.MULTS:
            key = O.vkey(lim, m)
            rs = [r for r in rows if r["variant"] == key]
            s = CR.stats(rs)
            old, new = halves(rs)
            delta = None if m is None or s["roi"] is None or hs["roi"] is None else s["roi"] - hs["roi"]
            bold = " class=\"hl\"" if key == HEAD else ""
            body.append(f'<tr data-variant="{key}"{bold}><td><b>{esc(O.vlabel(key))}{" (headline)" if key == HEAD else ""}</b></td>'
                        f'<td class="num">{s["n"]}</td><td class="num">{s["won"]}</td><td class="num">{pct(s["roi"])}</td>'
                        f'<td class="num">{pct(hs["roi"]) if m is not None else "—"}</td>'
                        f'<td class="num">{zfmt(s["z"])}</td><td class="num">{s["nights"]}</td>'
                        f'<td class="num">{pct(old)}</td><td class="num">{pct(new)}</td>'
                        f'<td class="num">{sum(1 for r in rs if r["dead"])}</td><td class="num">{sum(1 for r in rs if r["thin"])}</td>'
                        f'<td>{esc(read_of(s["n"], delta))}</td></tr>')
    return ('<div class="tbl"><table><tr><th>Bid · exit</th><th class="num">Filled</th><th class="num">Won</th>'
            '<th class="num">ROI after fees</th><th class="num">Hold, same bid</th><th class="num">z (by night)</th>'
            '<th class="num">Nights</th><th class="num">Older half</th><th class="num">Newer half</th>'
            '<th class="num">Dead fills</th><th class="num">Thin sells</th><th>Read</th></tr>' + "".join(body) + "</table></div>")


def league_table(entries, rows):
    head_rows = [r for r in rows if r["variant"] == HEAD]
    hold_rows = [r for r in rows if r["variant"] == O.vkey(O.HEADLINE, None)]
    leagues = sorted({e["league"] for e in entries})
    body = []
    for lg in leagues:
        games = [e for e in entries if e["league"] == lg]
        a = CR.stats([r for r in head_rows if r["league"] == lg])
        h = CR.stats([r for r in hold_rows if r["league"] == lg])
        body.append(f'<tr><td><b>{esc(lg)}</b></td><td class="num">{len(games)}</td><td class="num">{a["n"]}</td>'
                    f'<td class="num">{pct(a["roi"]) if a["n"] else "—"}</td><td class="num">{pct(h["roi"]) if h["n"] else "—"}</td></tr>')
    forms = [e for e in entries if e["form_rule"]]
    for name, sel in (("Over 1.5 form-rule matches", lambda r: r["form_rule"]), ("All other matches", lambda r: not r["form_rule"])):
        a = CR.stats([r for r in head_rows if sel(r)])
        h = CR.stats([r for r in hold_rows if sel(r)])
        n_games = len(forms) if sel is not None and name.startswith("Over") else len(entries) - len(forms)
        body.append(f'<tr><td><i>{esc(name)}</i></td><td class="num">{n_games}</td><td class="num">{a["n"]}</td>'
                    f'<td class="num">{pct(a["roi"]) if a["n"] else "—"}</td><td class="num">{pct(h["roi"]) if h["n"] else "—"}</td></tr>')
    return ('<div class="tbl"><table><tr><th>League</th><th class="num">Games</th><th class="num">Filled at 10c</th>'
            '<th class="num">Sell at 2x</th><th class="num">Hold</th></tr>' + "".join(body) + "</table></div>")


def trade_list(entries, limit=30):
    filled = [(e, e["bids"].get("10")) for e in entries if (e.get("bids") or {}).get("10")]
    filled.sort(key=lambda x: x[0]["kickoff"], reverse=True)
    body = []
    for e, b in filled[:limit]:
        cells = []
        for m in O.MULTS:
            s = b["sells"][str(m)]
            tag = "sold" if s["filled"] else ("thin" if s["thin"] else "held")
            proceeds = s["target"] - O.fee(s["target"]) if s["filled"] else b["payout"]
            cost = b["limit"] + O.fee(b["limit"])
            cells.append(f'<td class="num">{(proceeds - cost) / cost * 100:+.0f}% {tag} · {s["volume"]:.0f}</td>')
        hold = (b["payout"] - (b["limit"] + O.fee(b["limit"]))) / (b["limit"] + O.fee(b["limit"]))
        body.append(f'<tr><td>{esc(clock(e["kickoff"]))}</td><td>{esc(e["event"].split("-", 1)[-1])}</td><td>{esc(e["league"])}</td>'
                    f'<td class="num">{b["fill_print"] * 100:.0f}c{" · dead fill" if b["dead"] else ""}</td>'
                    + "".join(cells) + f'<td class="num">{hold * 100:+.0f}%</td></tr>')
    body = "".join(body) or '<tr><td colspan="8" class="mut">No bid has filled yet.</td></tr>'
    return ('<div class="tbl"><table><tr><th>Kickoff (ET)</th><th>Match</th><th>League</th><th class="num">Filled at</th>'
            '<th class="num">Sell at 2x · contracts</th><th class="num">Sell at 3x · contracts</th>'
            '<th class="num">Sell at 4x · contracts</th><th class="num">Hold</th></tr>' + body + "</table></div>")


def section(state=None):
    if state is None:
        state = O.load() if os.path.exists(O.PATH) else O.load("/nonexistent")
    entries = sorted(state.get("entries") or [], key=lambda e: e["kickoff"])
    rows = O.trade_rows(entries)
    head = [r for r in rows if r["variant"] == HEAD]
    filled10 = [e for e in entries if (e["bids"] or {}).get("10")]
    dead = sum(1 for e in filled10 if e["bids"]["10"]["dead"])
    thin = sum(1 for e in filled10 if e["bids"]["10"]["sells"][str(O.HEAD_MULT)]["thin"])
    last = state.get("last_run")
    summ = (f'{len(entries)} games · {len(filled10)} bids filled at 10c · {dead} dead · {thin} thin' if entries
            else "no game has settled since the record began")
    body = (variant_table(rows) + '<p class="sm"><b>By league, and the over 1.5 form-rule matches</b> · headline bid (10c)</p>'
            + league_table(entries, rows) if entries else '<p class="sm mut">No game has settled since the record began on '
            f'{esc(state.get("since"))}. The first rows appear after the first matches finish.</p>')
    return f"""<section id="cheap-side">
<h2>Cheap side · resting bid</h2>
<p class="shell-kicker">Paper only · no orders · fresh record since {esc(state.get("since"))} · review at {O.REVIEW_N} filled, decide at {O.DECIDE_N}</p>
<p class="sm mut roi-basis">ROI basis changed {ROI_BASIS["on"]} from cost-weighted to equal-stake (the mean of each fill's ROI, the same quantity its z tests); old figure: 10c bid sold at 2x {pct(ROI_BASIS["head"])}, hold {pct(ROI_BASIS["hold"])} on {ROI_BASIS["n"]} fills.</p>
<details class="section-disclosure" data-lane="{O.LANE}" open><summary><b>{esc(O.LABEL)}</b><span>{esc(summ)}</span></summary>
<p class="sm">On the over 3.5 goals market of every game in the twelve leagues on this page, a NO bid rests at 10c before kickoff (15c and 20c are tracked too). It can fill only in play, after goals push the over to 80c or more. The headline sells at 2x the bid; 3x, 4x and holding to settlement are recorded on the same fills.</p>
<p class="sm">A bid fills when the first trade after it prints NO at or under the bid. Fills after the 4th goal are kept and marked dead fill. A sell counts only if a later trade prints at or above its target and at least {O.MIN_VOL} contracts traded at or above the target after the fill; fewer is marked thin and the trade is held. Fees: 1.75% of p(1-p) on both legs. Kickoff is the Kalshi time minus 4 hours.</p>
{body}
<details class="section-disclosure"><summary><b>Fills</b><span>latest 30 at 10c</span></summary>{trade_list(entries)}</details>
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
