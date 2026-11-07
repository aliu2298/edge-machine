"""The Soccer page's row for mls_tie_split (mls_tie_split.py): ONE row in the Sandbox rules table, its words and tables inside
the row's closed "Rule details" fold (soccer_lanes.row): entry, exit, record and research lines, the record table, every
match, and the in-sample replay collapsed and labelled. Presentation only."""
import datetime as dt
import html as _h

import mls_tie_split as M


def esc(x):
    return _h.escape(str(x))


def pct(v):
    return "—" if v is None else f"{v * 100:+.1f}%".replace("-", "−")


def zfmt(v):
    return "—" if v is None else f"{v:+.2f}".replace("-", "−")


def read_of(n):
    if n < M.REVIEW_N:
        return f"too early ({n} of {M.REVIEW_N} settled entries)"
    if n < M.DECIDE_N:
        return f"review ({n} of {M.DECIDE_N} to decide)"
    return "decide"


def params():
    return [
        ("Entry", "Every MLS match: the Tie's YES ask an hour before kickoff, if it is 1-35c with the bid within 5c, bought at the ask (taker fee)."),
        ("Exit", "Two resting sells on half the position each, at 2x and 3x the entry (capped at 98c). A sell counts only when 50+ contracts "
                 "trade at or above its price from a minute after the entry. Maker fee on a sold half; an unsold half is held to settlement."),
        ("Control", "The same entry held to settlement."),
        ("Record", f"Fresh from {M.SINCE}, paper only, one outcome per match, z by matchday. Review at {M.REVIEW_N} settled entries, decide at {M.DECIDE_N}. "
                   "The regular season is over, so few matches arrive before the 2027 season."),
        ("Research", "The one cell that passed six pre-registered match filters on Kalshi soccer: positive in both halves of Sep-Nov and on an "
                     "August holdout, but small (z under 1 on Sep-Nov) and MLS draws have been priced fair over 14 seasons. A forward test, not a bet."),
    ]


def record_table(s):
    rows = [
        ("Settled entries · matchdays", f'{s["n"]} · {s["days"]}'),
        ("Draws v priced", f'{s["draws"]} v {s["priced"]:.1f}'),
        ("2x half sold · 3x half sold", f'{s["sold2"]} · {s["sold3"]}'),
        ("Split ROI per entry, after fees", pct(s["roi"])),
        ("Held to settlement (control)", pct(s["hold"])),
        ("z by matchday", zfmt(s["z"])),
        ("Earlier half · later half", f'{pct(s["old"])} · {pct(s["new"])}'),
        ("Read", read_of(s["n"])),
    ]
    body = "".join(f'<tr><td>{esc(k)}</td><td class="num">{esc(v)}</td></tr>' for k, v in rows)
    return f'<div class="tbl"><table><thead><tr><th>Record</th><th class="num">Figure</th></tr></thead><tbody>{body}</tbody></table></div>'


def _when(ts):
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%b %-d %H:%M UTC")


def match_table(entries):
    if not entries:
        return '<p class="sm mut">No match settled yet.</p>'
    body = []
    for e in sorted(entries, key=lambda e: e["kickoff"], reverse=True):
        legs = " · ".join(f'{l["multiple"]:g}x {l["target"] * 100:.0f}c {"sold" if l["sold_ts"] else "held"}' for l in e["legs"])
        body.append(f'<tr><td>{esc(_when(e["kickoff"]))}</td><td>{esc(e["title"])}</td><td class="num">{e["ask"] * 100:.0f}c</td>'
                    f'<td>{esc(legs)}</td><td>{"draw" if e["won"] else "no draw"}</td>'
                    f'<td class="num">{esc(pct(e["roi"]))}</td><td class="num">{esc(pct(e["hold"]))}</td></tr>')
    return ('<div class="tbl"><table><thead><tr><th>Kickoff</th><th>Match</th><th class="num">Ask</th><th>Sells</th><th>Result</th>'
            '<th class="num">Split ROI</th><th class="num">Held</th></tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table></div>')


def panel(state):
    """The row's fold: definition list, the record, every match, the in-sample replay."""
    import soccer_lanes as L
    entries, ins = state.get("entries") or [], (state.get("insample") or {}).get("entries") or []
    out = [L.params_html(params()), record_table(M.summary(entries))]
    n = len(entries)
    out.append(f'<details class="section-disclosure"><summary><b>Matches</b><span>{n} match{"es" if n != 1 else ""} since {esc(M.SINCE)}</span></summary>'
               f'{match_table(entries)}</details>')
    if ins:
        w = (state.get("insample") or {}).get("window") or list(M.INSAMPLE)
        out.append('<details class="section-disclosure"><summary><b>Earlier matches, replayed once</b>'
                   f'<span>{len(ins)} matches · {esc(w[0])} to {esc(w[1])} · in-sample · not in the record</span></summary>'
                   '<p class="sm">The research months, replayed from their candles and trade prints under the same rule. '
                   'Shown once and never counted in the record.</p>'
                   f'{record_table(M.summary(ins))}{match_table(ins)}</details>')
    return "".join(out)
