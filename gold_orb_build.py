"""The Trading page's Gold Asia-open breakout section (gold_orb.py): paper · never places an order."""
import datetime as dt
import html as _h
import os

import gold_orb as G

WORDS = {"no_range": "no range (too few minutes traded)", "no_break": "no close beyond the range by 9:00 pm",
         "pending": "waiting", "ranged": "watching", "open": "in the trade", "error": "run error"}
ANCHORS = (("ct_2000", "8:00 pm CT"), ("utc_0100", "01:00 UTC shadow"))


def esc(x):
    return _h.escape(str(x))


def _num(x, fmt="{:+.1f}"):
    return "—" if x is None else fmt.format(x)


def _usd(x):
    return "—" if x is None else f"${x:+.2f}"


def _anchor(r):
    return dict(ANCHORS).get(r.get("anchor"), r.get("anchor", ""))


def _row(r):
    night = dt.date.fromisoformat(r["night"])
    head = (f'<td>{esc(f"{night:%a %b} {night.day}")}</td><td>{esc(r.get("variant", ""))}</td>'
            f'<td>{esc(_anchor(r))}</td>')
    if r["status"] not in ("settled", "open"):
        return f'<tr class="mut">{head}<td colspan="6">{esc(WORDS.get(r["status"], r["status"]))}</td></tr>'
    entry = "—" if r.get("entry_px") is None else f'{r["entry_px"]:.1f}' + (" †" if r.get("entry_late") else "")
    exit_ = "—" if r.get("exit_px") is None else f'{r["exit_px"]:.1f}' + (" *" if r.get("exit_carried") else "")
    spreads = f'{_num(r.get("entry_spread_bp"), "{:.1f}")} / {_num(r.get("exit_spread_bp"), "{:.1f}")}'
    return (f'<tr>{head}<td>{esc(r["side"])}</td><td class="num">{entry}</td><td class="num">{exit_}</td>'
            f'<td class="num">{_num(r.get("gross_bp"))}</td><td class="num">{spreads}</td>'
            f'<td class="num">{_num(r.get("net_bp"))} · {_usd(r.get("net_usd"))}</td></tr>')


def _summary_row(variant, key, label, rows):
    s = G.summary([r for r in rows if r.get("variant") == variant and r.get("anchor") == key])
    name = G.VARIANTS[variant][2]
    if not s["n"]:
        cells = '<td class="num">0</td>' + '<td class="num">—</td>' * 5
    else:
        cells = (f'<td class="num">{s["n"]}</td><td class="num">{s["win"] * 100:.0f}%</td>'
                 f'<td class="num">{_num(s["gross"])}</td><td class="num">{_num(s["net"])} · {_usd(s["net_usd"])}</td>'
                 f'<td class="num">{_num(s["spread"], "{:.1f}")}</td><td class="num">{_num(s["t"], "{:+.2f}")}</td>')
    return f'<tr><td>{esc(name)}</td><td>{esc(label)}</td>{cells}</tr>'


def section(state=None):
    if state is None:
        state = G.load() if os.path.exists(G.PATH) else {"nights": []}
    rows = sorted(state.get("nights") or [],
                  key=lambda r: (r["night"], r.get("variant", ""), r.get("shadow", False)), reverse=True)
    summ = "".join(_summary_row(v, k, label, rows) for v in G.VARIANTS for k, label in ANCHORS)
    body = "".join(_row(r) for r in rows[:80]) or (
        '<tr><td colspan="9" class="mut">No nights yet: the first is the next Sunday-to-Thursday '
        'evening, from 7:30 pm CT.</td></tr>')
    last = state.get("last_run")
    return f"""<section id="gold-orb">
<h2>Gold Asia-open breakout (paper)</h2>
<p class="sm"><b>Definition:</b> the first minute after 8:00 pm CT that closes beyond the 7:30–8:00 pm range (A) or the
7:55–8:00 pm range (B) on Coinbase's GOL gold future; enter at the next minute's open, exit 15 minutes later.
Paper · never places an order · not in Production.</p>
<details class="fold trade-method"><summary>How the gold breakout is defined</summary>
<div class="note sm">One contract is 1 oz. A's range is the 30-minute candle as a chart draws it; B's needs all five
minutes to have traded. The side is the first minute within 60 minutes of 8:00 pm that closes beyond the range,
and it is decided only once that minute has finished; no stop. Each variant is also kept from a fixed 01:00 UTC
anchor (the China open): the same time as 8:00 pm CT until Nov 1, then 7:00 pm CST. Sunday–Thursday nights.</div>
</details>
<div class="tbl"><table><thead><tr><th>Variant</th><th>Anchor</th><th class="num">Settled nights</th>
<th class="num">Won</th><th class="num">Avg gross bp</th><th class="num">Avg net bp · $</th>
<th class="num">Avg spread bp</th><th class="num">t (net)</th></tr></thead>
<tbody>{summ}</tbody></table></div>
<p class="sm mut">Olu reviews at {G.READ_AT}+ settled nights per variant. Net buys at the ask and sells at the bid
(the book at the entry poll and the exit poll), {esc(G.FEE_NOTE)}. Won = net above zero.</p>
<div class="tbl"><table><thead><tr><th>Night</th><th>Variant</th><th>Anchor</th><th>Side</th>
<th class="num">Entry</th><th class="num">Exit</th><th class="num">Gross bp</th>
<th class="num">Spread bp entry / exit</th><th class="num">Net bp · $</th></tr></thead>
<tbody>{body}</tbody></table></div>
<p class="sm mut">† nothing traded in the entry minute: the first open after it. * nothing traded in the exit
minute: the last price before it. Research, look-ahead-free: the 5-minute range made +0.9bp a trade (t +0.91)
on 500 nights and −1.2bp on the 250-night holdout, before costs; this lane measures what the venue really pays.
Last run {esc(last or "not yet")}.</p>
</section>"""
