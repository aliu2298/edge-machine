"""The Trading page's Gold Asia-open breakout section (gold_orb.py): paper · never places an order."""
import datetime as dt
import html as _h
import os

import gold_orb as G
import trading_layout as L

WORDS = {"no_range": "no range (too few minutes traded)", "no_break": "no close beyond the range within the hour",
         "pending": "waiting", "ranged": "watching", "open": "in the trade", "error": "run error"}
# anchor key -> (label, summary label). The primary anchor is fixed UTC (2026-10-24 amendment).
ANCHORS = (("utc_0130", "7:30 pm CST fixed (01:30 UTC)"),
           ("utc_0100", "01:00 UTC shadow (China open)"),
           ("ct_2000", "8:00 pm CT · retired 2026-10-24"))
AMENDMENT = ("2026-10-24: fixed to 7:30 pm CST (01:30 UTC) per the original spec; the earlier DST-following "
             "7:30 pm CDT anchor was an hour early.")


def esc(x):
    return _h.escape(str(x))


def _num(x, fmt="{:+.1f}"):
    return "—" if x is None else fmt.format(x)


def _usd(x):
    return "—" if x is None else f"${x:+.2f}"


def _ct(r):
    """The row's range start in Chicago time ('8:30 pm CDT'): the same UTC instant is 8:30 pm CDT until
    Nov 1 and 7:30 pm CST after."""
    try:
        t = dt.datetime.fromisoformat(r["anchor_at"]).astimezone(G.CT) - dt.timedelta(minutes=30)
    except (KeyError, ValueError):
        return ""
    return f"{t:%I:%M %p %Z}".lstrip("0").lower().replace(" cdt", " CDT").replace(" cst", " CST")


def _anchor(r):
    key = r.get("anchor", "")
    label = dict(ANCHORS).get(key, key)
    if key == "utc_0130":
        label += f" · {_ct(r)}"
    return label


def _row(r):
    night = dt.date.fromisoformat(r["night"])
    flag = ' <span class="badge stage">Backfilled · candles only</span>' if r.get("backfilled") else ""
    mut = ' class="mut"' if r.get("retired") else ""
    head = (f'<td>{esc(f"{night:%a %b} {night.day}")}</td><td>{esc(r.get("variant", ""))}</td>'
            f'<td>{esc(_anchor(r))}{flag}</td>')
    if r["status"] not in ("settled", "open"):
        return f'<tr class="mut">{head}<td colspan="6">{esc(WORDS.get(r["status"], r["status"]))}</td></tr>'
    entry = "—" if r.get("entry_px") is None else f'{r["entry_px"]:.1f}' + (" †" if r.get("entry_late") else "")
    exit_ = "—" if r.get("exit_px") is None else f'{r["exit_px"]:.1f}' + (" *" if r.get("exit_carried") else "")
    if r.get("backfilled"):
        spreads, net = "no spread", "— · —"
    elif r.get("book_invalid"):
        side = r["book_invalid"]
        spreads, net = f'book invalid ({esc(side)}) · {esc(r.get("entry_book_invalid") or r.get("exit_book_invalid") or "")}', "— · —"
    else:
        spreads = f'{_num(r.get("entry_spread_bp"), "{:.1f}")} / {_num(r.get("exit_spread_bp"), "{:.1f}")}'
        net = f'{_num(r.get("net_bp"))} · {_usd(r.get("net_usd"))}'
    return (f'<tr{mut}>{head}<td>{esc(r["side"])}</td><td class="num">{entry}</td><td class="num">{exit_}</td>'
            f'<td class="num">{_num(r.get("gross_bp"))}</td><td class="num">{spreads}</td>'
            f'<td class="num">{net}</td></tr>')


def _summary_row(variant, key, label, rows):
    mine = [r for r in rows if r.get("variant") == variant and r.get("anchor") == key]
    s = G.summary(mine)
    name = G.VARIANTS[variant][2]
    if not s["n"]:
        cells = '<td class="num">0</td>' + '<td class="num">—</td>' * 5
    else:
        cells = (f'<td class="num">{s["n"]}</td><td class="num">{s["win"] * 100:.0f}%</td>'
                 f'<td class="num">{_num(s["gross"])}</td><td class="num">{_num(s["net"])} · {_usd(s["net_usd"])}</td>'
                 f'<td class="num">{_num(s["spread"], "{:.1f}")}</td><td class="num">{_num(s["t"], "{:+.2f}")}</td>')
    out = f'<tr><td>{esc(name)}</td><td>{esc(label)}</td>{cells}</tr>'
    g = G.gross_summary(mine)
    if g["n"]:
        # The backfilled nights: gross only, never in the net-after-spread figures above.
        out += (f'<tr class="mut"><td>{esc(name)}</td><td>{esc(label)} · backfilled, candles only</td>'
                f'<td class="num">{g["n"]}</td><td class="num">{g["win"] * 100:.0f}% gross</td>'
                f'<td class="num">{_num(g["gross"])}</td><td class="num">—</td><td class="num">—</td>'
                f'<td class="num">—</td></tr>')
    a = G.gross_all(mine)
    if a["n"] and any(r.get("backfilled") or r.get("book_invalid") for r in mine):
        # Every settled night at this anchor on its gross return, net or not: backfilled nights and
        # nights whose book was unusable sit here next to the net line.
        out += (f'<tr class="mut"><td>{esc(name)}</td><td>{esc(label)} · all nights, gross</td>'
                f'<td class="num">{a["n"]}</td><td class="num">{a["win"] * 100:.0f}% gross</td>'
                f'<td class="num">{_num(a["gross"])}</td><td class="num">—</td><td class="num">—</td>'
                f'<td class="num">{_num(a["t"], "{:+.2f}")} gross</td></tr>')
    return out


def _status(s):
    if s["n"] >= G.READ_AT:
        return L.sig("review due", "w")
    return L.sig(f'{s["n"]}/{G.READ_AT} to review')


def _variant_row(v, rows):
    """One lane row per variant, on the primary anchor; every anchor's nights sit in its fold."""
    mine = [r for r in rows if r.get("variant") == v]
    s = G.summary([r for r in mine if r.get("anchor") == "utc_0130"])
    rng, _w, name = G.VARIANTS[v]
    nights = "".join(_row(r) for r in mine[:60]) or (
        '<tr><td colspan="9" class="mut">No nights yet: the first is the next Sunday-to-Thursday evening.</td></tr>')
    body = (f'<p class="sp-def">On the Coinbase GOL gold future: the first minute after 02:00 UTC that closes beyond the '
            f'{"01:30–02:00" if rng == 30 else "01:55–02:00"} UTC range; enter at the next open, exit 15 minutes later. '
            f'Paper, one contract, never places an order.</p>'
            + L.params([("Settled", f'{s["n"]} nights on the 01:30 UTC anchor, net after the spread and fee'),
                        ("Avg gross", f'{_num(s["gross"])}bp'),
                        ("Avg spread", f'{_num(s["spread"], "{:.1f}")}bp')])
            + L.fold("Nightly rows, every anchor",
                     '<div class="tbl"><table><thead><tr><th>Night</th><th>Variant</th><th>Anchor</th><th>Side</th>'
                     '<th class="num">Entry</th><th class="num">Exit</th><th class="num">Gross bp</th>'
                     '<th class="num">Spread bp entry / exit</th><th class="num">Net bp · $</th></tr></thead>'
                     f'<tbody>{nights}</tbody></table></div>'))
    win = "—" if s["win"] is None else f'{s["win"] * 100:.0f}%'
    net = "—" if s["net"] is None else f'{_num(s["net"])}bp'
    t = "—" if s["t"] is None else f'{s["t"]:+.2f}'
    return L.rule(f"gold_orb_{v}", name, "Coinbase GOL", str(s["n"]), win, net, t, _status(s), body)


def section(state=None):
    if state is None:
        state = G.load() if os.path.exists(G.PATH) else {"nights": []}
    rows = sorted(state.get("nights") or [],
                  key=lambda r: (r["night"], r.get("variant", ""), r.get("anchor") == "utc_0130", r.get("anchor", "")),
                  reverse=True)
    present = {r.get("anchor") for r in rows}
    summ = "".join(_summary_row(v, k, label, rows) for v in G.VARIANTS for k, label in ANCHORS
                   if k in present or k != "ct_2000")
    empty = "" if rows else ('<p class="sm mut">No nights yet: the first is the next Sunday-to-Thursday '
                             'evening, from 8:30 pm CDT.</p>')
    last = state.get("last_run")
    lanes = L.rules_list([_variant_row(v, rows) for v in G.VARIANTS], first="Variant", key="gold-orb")
    full = L.fold("Every anchor, the backfill and the gross-only lines", f"""
<div class="tbl"><table><thead><tr><th>Variant</th><th>Anchor</th><th class="num">Settled nights</th>
<th class="num">Won</th><th class="num">Avg gross bp</th><th class="num">Avg net bp · $</th>
<th class="num">Avg spread bp</th><th class="num">t (net)</th></tr></thead>
<tbody>{summ}</tbody></table></div>
<p class="sm mut">Olu reviews at {G.READ_AT}+ settled nights per variant. Net buys at the ask and sells at the bid
(the book at the entry poll and the exit poll), {esc(G.FEE_NOTE)}. Won = net above zero.
† nothing traded in the entry minute: the first open after it. * nothing traded in the exit
minute: the last price before it. Last run {esc(last or "not yet")}.</p>""")
    method = L.fold("How the gold breakout is defined", f"""
<div class="note sm">One contract is 1 oz. The primary anchor is FIXED at 7:30 pm CST = 01:30 UTC all year, which reads
8:30 pm CDT until Nov 1 and 7:30 pm CST after. A's range is the 30-minute candle as a chart draws it; B's needs all
five minutes to have traded. The side is the first minute within 60 minutes (to 03:00 UTC) that closes beyond the
range, decided only once that minute has finished; no stop. The 01:00 UTC China-open shadow (range 00:30–01:00 UTC)
is kept as a second anchor. The DST-following 8:00 pm CT anchor is retired; its rows stay. Sunday–Thursday nights.</div>
<div class="note sm"><b>Amendment {esc(AMENDMENT)}</b> Nights since 2026-10-18 were re-run at the new anchor from
Coinbase's historical 1-minute candles (GOL-25NOV26-CDE). Coinbase publishes no historical book, so those rows are
marked backfilled, show their gross return and no spread, and stay out of every net-after-spread figure.</div>
<div class="note sm"><b>Book guard 2026-11-04.</b> A book with a side missing, bid at or above ask, or older than a few
seconds is re-polled; if none arrives the row is marked <i>book invalid</i> and leaves the net figures, keeping its gross.
Four rows from 2026-10-29 (a crossed book at the entry or the exit poll) were moved out that way.</div>
<div class="note sm">Research, look-ahead-free: the 5-minute range made +0.9bp a trade (t +0.91)
on 500 nights and −1.2bp on the 250-night holdout, before costs; this lane measures what the venue really pays.</div>""",
                    cls="fold trade-method")
    return L.section("gold-orb", "Gold Asia-open breakout (paper)",
                     "2 variants · Paper · never places an order · not in Production",
                     lanes + empty + full + method)
