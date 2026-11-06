"""The Soccer page's row for ere_draw_maker (ere_draw_maker.py): ONE row in the Sandbox rules table, right under ere_draw, with
its words and tables inside the row's closed "Rule details" fold (soccer_lanes.row): entry line, exit line, the record
table, the comparison beside ere_draw, every match, and the in-sample replay collapsed and labelled. Presentation only."""
import html as _h

import ere_draw_maker as M
import fmt


def esc(x):
    return _h.escape(str(x))


def pct(v, sign=True):
    return "—" if v is None else (f"{v * 100:+.1f}%" if sign else f"{v * 100:.0f}%").replace("-", "−")


def zfmt(v):
    return "—" if v is None else f"{v:+.2f}".replace("-", "−")


def read_of(n):
    if n < M.REVIEW_N:
        return f"too early ({n} of {M.REVIEW_N} settled fills)"
    if n < M.DECIDE_N:
        return f"review ({n} of {M.DECIDE_N} to decide)"
    return "decide"


def params():
    return [
        ("Entry", "ere_draw's own matches (de-vigged draw 0.20-0.25, ask 0.26 or less), nothing added. A YES bid rests on the Tie at 1c under the ask "
                  "at selection, from 24 hours before kickoff or from when the match first qualified if later, until kickoff."),
        ("Fill", "Only when a trade prints strictly below the bid before kickoff (a print at the bid sits behind the queue). The fill is at the bid; "
                 "no fill costs nothing."),
        ("Exit", "Held to settlement. Maker fee on the entry, none at settlement."),
        ("Record", f"Fresh from {M.SINCE}, paper only, one outcome per match. Review at {M.REVIEW_N} settled fills, decide at {M.DECIDE_N}."),
    ]


def comparison(s):
    """The record table and ere_draw beside it, one header-row table."""
    rows = [
        ("Matches read", f'{s["matches"]}'),
        ("Bids filled", f'{s["filled"]} ({pct(s["fill_rate"], sign=False)})'),
        ("Settled fills · won v priced", f'{s["n"]} · {s["won"]} v {s["expected"]:.1f}'),
        ("Maker ROI on the fills", pct(s["maker"])),
        ("ere_draw taker ROI on the same fills", pct(s["taker_same"])),
        ("ere_draw taker ROI on every match", f'{pct(s["taker_all"])} ({s["taker_all_n"]} settled)'),
        ("z (fills v the bid price)", zfmt(s["z"])),
        ("Read", read_of(s["n"])),
    ]
    body = "".join(f'<tr><td>{esc(k)}</td><td class="num">{esc(v)}</td></tr>' for k, v in rows)
    return f'<div class="tbl"><table><thead><tr><th>Maker v taker</th><th class="num">Figure</th></tr></thead><tbody>{body}</tbody></table></div>'


def match_table(entries):
    if not entries:
        return '<p class="sm mut">No match read yet.</p>'
    body = []
    for e in sorted(entries, key=lambda e: e["start"], reverse=True):
        if e.get("filled"):
            fill = f'filled at {e["bid"] * 100:.0f}c (print {e["fill_print"] * 100:.0f}c)'
        else:
            fill = "not filled"
        mk = pct(e.get("maker_roi")) if e.get("maker_roi") is not None else ("open" if e.get("filled") else "—")
        tk = pct(e.get("taker_roi")) if e.get("taker_roi") is not None else "open"
        body.append(f'<tr><td>{esc(fmt.when(e["start"]))}</td><td>{esc(e.get("match") or "")}</td>'
                    f'<td class="num">{e["ask"] * 100:.0f}c → {e["bid"] * 100:.0f}c</td><td>{esc(fill)}</td>'
                    f'<td class="num">{esc(mk)}</td><td class="num">{esc(tk)}</td></tr>')
    return ('<div class="tbl"><table><thead><tr><th>Kickoff</th><th>Match</th><th class="num">Ask → bid</th><th>Maker</th>'
            '<th class="num">Maker ROI</th><th class="num">ere_draw taker ROI</th></tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table></div>')


def panel(state):
    """The row's fold: definition list, the record beside ere_draw, every match, the in-sample replay."""
    import soccer_lanes as L
    entries, ins = state.get("entries") or [], state.get("insample") or []
    s = M.summary(entries)
    out = [L.params_html(params()), comparison(s)]
    n = len(entries)
    out.append(f'<details class="section-disclosure"><summary><b>Matches</b><span>{n} match{"es" if n != 1 else ""} since {esc(M.SINCE)}</span></summary>'
               f'{match_table(entries)}</details>')
    if ins:
        i = M.summary(ins)
        out.append('<details class="section-disclosure"><summary><b>Earlier matches, replayed once</b>'
                   f'<span>{i["matches"]} matches · in-sample · not in the record</span></summary>'
                   '<p class="sm">ere_draw\'s settled matches before the lane existed, replayed from their trade prints under the same rules. '
                   'Shown once and never counted in the record.</p>'
                   f'{comparison(i)}{match_table(ins)}</details>')
    return "".join(out)
