"""The "15-Minute Swing" section of the Daily Markets tab and its Sandbox index row (swing15.py). Paper · no orders.

One headline row per strategy (S1, S2, S3) in the Econ Daily Rules-list design; every number beyond the headline sits
in that row's fold. S1's headline is its middle cell, fixed when it was registered: the 25c band, a 2x take-profit,
held to settlement when the sell does not fill. The full S1 grid is in the fold.
"""
import html as _h

import swing15 as W

HEADLINE_S1 = ("swing15_s1", "0.25", "2.0", "hold")
EXIT_WORDS = {"hold": "else hold", "bid": "else sell at the bid, 1 min left"}


def esc(x):
    return _h.escape(str(x))


def pct(x, d=1):
    return "—" if x is None else f"{x * 100:+.{d}f}%".replace("-", "−")


def _z(x):
    return "—" if x is None else f"{x:+.2f}".replace("-", "−")


def _tone(c):
    if not c or c["n"] < W.REVIEW_AT:
        return "mut"
    return "pos" if c["mean_roi"] > 0 else "neg"


def _per_series(state, key):
    """{series: n} for one strategy cell: the review clock (10) and decision (30) run per strategy x series."""
    out = {}
    for s in sorted({w["series"] for w in state["windows"].values()}):
        c = W.cells(state, lambda w, s=s: w["series"] == s).get(key)
        out[s] = c["n"] if c else 0
    return out


def _verdict(per):
    due = sum(n >= W.DECIDE_AT for n in per.values())
    rev = sum(W.REVIEW_AT <= n < W.DECIDE_AT for n in per.values())
    if due:
        return f'<span class="sig w">Decide · {due} series at {W.DECIDE_AT}+</span>'
    if rev:
        return f'<span class="sig w">Review · {rev} series at {W.REVIEW_AT}+</span>'
    return '<span class="sig n">Too early</span>'


def _row(key, label, c, per, body):
    record = '<span class="mut">—</span>' if not c else f'{c["hits"]}–{c["n"] - c["hits"]}'
    roi = '<span class="mut">—</span>' if not c else f'<span class="{_tone(c)}">{pct(c["mean_roi"])}</span>'
    wvp = "—" if not c else f'{c["hits"]} v {c["fair"] * c["n"]:.1f}'
    best = max(per.values(), default=0)
    return (f'<details class="sp-rule{"" if c and c["n"] >= W.REVIEW_AT else " is-early"}" data-source="{esc(key)}" '
            f'data-sport="swing15" data-scope="clubs" data-stage="sandbox">'
            f'<summary class="sp-line"><span class="sp-cell sp-c-name"><span class="sp-chev" aria-hidden="true">›</span>'
            f'<b class="sp-name" title="{esc(label)}">{esc(label)}</b><span class="sr-only"> · Rule details</span></span>'
            f'<span class="sp-cell sp-c-market" data-l="Market">Kalshi</span>'
            f'<span class="sp-cell num" data-l="Record">{record}</span>'
            f'<span class="sp-cell num" data-l="ROI after fees">{roi}</span>'
            f'<span class="sp-cell num" data-l="Won v priced">{esc(wvp)}</span>'
            f'<span class="sp-cell num" data-l="Evidence">{min(best, W.DECIDE_AT)}/{W.DECIDE_AT}</span>'
            f'<span class="sp-cell sp-c-verdict" data-l="Verdict">{_verdict(per)}</span></summary>'
            f'<div class="sp-details-body">{body}</div></details>')


def _table(head, rows):
    return ('<div class="tbl"><table><thead><tr>' + "".join(f"<th{' class=\"num\"' if i else ''}>{esc(h)}</th>" for i, h in enumerate(head))
            + "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>")


def _cell_tr(name, c):
    if not c:
        return f'<tr><td>{esc(name)}</td>' + '<td class="num">—</td>' * 6 + '</tr>'
    h0, h1 = c["half_roi"]
    return (f'<tr><td>{esc(name)}</td><td class="num">{c["n"]}</td><td class="num">{c["hit_rate"] * 100:.0f}%</td>'
            f'<td class="num">{c["fair"] * 100:.0f}%</td><td class="num">{pct(c["mean_roi"])}</td>'
            f'<td class="num">{_z(c["z"])}</td><td class="num">{pct(h0)} / {pct(h1)}</td></tr>')


HEAD = ("Cell", "n", "Hit", "Fair", "ROI after fees", "z (by day)", "Halves")


def _splits(state, key):
    rows = []
    for name, flt in (
            *[(g, (lambda w, g=g: w["group"] == g)) for g in W.GROUPS],
            ("US hours (9:30–16:00 ET weekdays)", lambda w: w["us_hours"]),
            ("Overnight and weekends", lambda w: not w["us_hours"])):
        rows.append(_cell_tr(name, W.cells(state, flt).get(key)))
    for s in sorted({w["series"] for w in state["windows"].values()}):
        c = W.cells(state, lambda w, s=s: w["series"] == s).get(key)
        if c:
            rows.append(_cell_tr(s, c))
    return _table(HEAD, rows)


def section(state=None):
    state = W.load() if state is None else state
    allc = W.cells(state)
    n_w = len(state.get("windows") or {})
    s1_grid = [_cell_tr(f'{float(b) * 100:g}c · {float(m):g}x · {EXIT_WORDS[how]}', allc.get(("swing15_s1", b, m, how)))
               for b in map(str, W.BANDS) for m in map(str, W.MULTS) for how in ("hold", "bid")]
    defs = {
        "swing15_s1": ("S1 Swing · 25c · 2x · else hold",
                       "A resting buy at the band on whichever side prints there first in the window's first 5 minutes "
                       "(15c, 25c or 35c), filled at the band only on a print at or through it; a resting sell at 1.5x, 2x "
                       "or 3x (capped at 99c), filled only on 50+ contracts printed at or above it 60s+ after the entry. "
                       "Unfilled: recorded both held to settlement and sold at the bid with 1 minute left. Judged against "
                       "the fair touch rate, entry / target. The row is the 25c · 2x · hold cell, fixed at registration; "
                       "the whole grid is below."),
        "swing15_s2": ("S2 Favourite at start",
                       "At minute 2, buy the side above 50c (by the mid) at its ask, filled only on a print at or through "
                       "it in the next minute; held to settlement. Judged against the price paid."),
        "swing15_s3": ("S3 Favourite at 5 minutes left",
                       "The same at minute 10. Judged against the price paid."),
    }
    rows = []
    for key, (label, text) in defs.items():
        ck = HEADLINE_S1 if key == "swing15_s1" else (key,)
        per = _per_series(state, ck)
        body = (f'<p class="sp-details-name"><b>{esc(label)}</b> · Kalshi 15-minute windows · paper · {esc(W.VERSION)}</p>'
                f'<p class="sp-def">{esc(text)}</p>'
                '<dl class="sp-params"><dt>Scope</dt><dd>Every Kalshi 15-minute series in Crypto, Commodities and '
                f'Financials ({len(state.get("series") or [])} series)</dd>'
                '<dt>Fees</dt><dd>Taker 0.07·p(1−p) on an entry and a sell at the bid; maker 0.0175·p(1−p) on a resting '
                'sell</dd><dt>Read</dt><dd>Review at 10 and decide at 30 settled windows per strategy and series; z '
                'clustered by day</dd></dl>')
        if key == "swing15_s1":
            body += '<details class="fold"><summary>The whole S1 grid</summary>' + _table(HEAD, s1_grid) + "</details>"
        body += f'<details class="fold"><summary>Splits: group, hours, series</summary>{_splits(state, ck)}</details>'
        rows.append(_row(key, label, allc.get(ck), per, body))
    head = ('<div class="sp-line sp-head-line" aria-hidden="true"><span class="sp-cell sp-c-name">Rule</span>'
            '<span class="sp-cell sp-c-market">Market</span><span class="sp-cell num">Record</span>'
            '<span class="sp-cell num">ROI after fees</span><span class="sp-cell num">Won v priced</span>'
            '<span class="sp-cell num">Evidence</span><span class="sp-cell sp-c-verdict">Verdict</span></div>')
    last = state.get("last_run") or "not yet"
    method = (f'<section class="sp-method"><details><summary><b>Method</b><small>registration · fills · fees</small></summary><div>'
              f'<p class="sm">Pre-registered {esc(W.REGISTERED)} as {esc(W.VERSION)}, frozen before any window was graded: '
              f'windows opening from {esc(W.FROM[:16].replace("T", " "))} UTC are graded once each, after Kalshi settles '
              'them, from its own 1-minute candles and trade prints. A minute is read print by print only where its candle '
              'shows the price could have touched an entry or a target. Paper only; nothing is placed.</p>'
              f'<p class="sm mut">{n_w} windows graded. Last run {esc(last)}.</p></div></details></section>')
    return (f'<h2 class="dm-title">15-Minute Swing</h2><p class="scope">Every Kalshi 15-minute window in Crypto, '
            f'Commodities and Financials · three pre-registered strategies · paper</p>'
            f'<div class="sp-rules-list" data-list="sandbox">{head}{"".join(rows)}</div>{method}')


def index_rows(state=None):
    state = W.load() if state is None else state
    allc = W.cells(state)
    out = []
    for key, label in W.STRATS.items():
        ck = HEADLINE_S1 if key == "swing15_s1" else (key,)
        c = allc.get(ck)
        per = _per_series(state, ck)
        out.append(dict(lane=key, label=label + (" · 25c · 2x · hold" if key == "swing15_s1" else ""),
                        n=c["n"] if c else 0, roi=c["mean_roi"] if c else None,
                        hit=c["hit_rate"] if c else None, fair=c["fair"] if c else None,
                        status=(f"{max(per.values(), default=0)}/{W.DECIDE_AT} in its best series")))
    return out


def index_html(state=None):
    """The Sandbox's index rows, linking to the section on the Daily Markets tab."""
    try:
        rs = index_rows(state)
    except Exception:                                           # noqa: BLE001
        return ""
    def hv(r):
        return "—" if r["hit"] is None else f'{r["hit"] * 100:.0f}% v {r["fair"] * 100:.0f}%'
    rows = "".join(
        f'<tr data-lane="{esc(r["lane"])}"><td><b>{esc(r["label"])}</b></td>'
        f'<td><a href="./daily_markets.html#swing15">Daily Markets</a></td><td class="num">{r["n"]}</td>'
        f'<td class="num">{hv(r)}</td><td class="num">{pct(r["roi"])}</td><td>{esc(r["status"])}</td></tr>' for r in rs)
    return ('<section id="swing15-index"><h2>15-Minute Swing</h2><p class="shell-kicker">Every Kalshi 15-minute window in '
            'Crypto, Commodities and Financials · three pre-registered strategies · paper · not in Production</p>'
            '<div class="tbl"><table><tr><th>Strategy</th><th>Page</th><th class="num">Windows</th>'
            '<th class="num">Hit v fair</th><th class="num">ROI after fees</th><th>Evidence</th></tr>'
            + rows + '</table></div></section>')
