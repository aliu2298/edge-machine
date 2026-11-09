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


# 2026-11-09 (Olu): readable market names everywhere in the 15-Minute section; display only, tickers stay in the data.
NAMES = {
    "KXBTC15M": "Bitcoin", "KXETH15M": "Ethereum", "KXSOL15M": "Solana", "KXXRP15M": "XRP", "KXBNB15M": "BNB",
    "KXDOGE15M": "Dogecoin", "KXHYPE15M": "Hyperliquid", "KXNEAR15M": "NEAR", "KXZEC15M": "Zcash",
    "KXCRYPTOLEAD15M": "Coin Race (biggest gainer)",
    "KXGOLD15M": "Gold", "KXSILVER15M": "Silver", "KXCOPPER15M": "Copper", "KXPLATINUM15M": "Platinum",
    "KXPALLADIUM15M": "Palladium", "KXWTI15M": "WTI Crude Oil", "KXBRENT15M": "Brent Crude Oil",
    "KXNATGAS15M": "Natural Gas",
    "KXINX15M": "S&P 500", "KXNDQ15M": "Nasdaq 100", "KXDJIA15M": "Dow Jones",
    "KX2YRRATE15M": "2-Year Treasury Yield", "KX5YRRATE15M": "5-Year Treasury Yield",
    "KX10YRRATE15M": "10-Year Treasury Yield", "KX30YRRATE15M": "30-Year Treasury Yield",
    "KXEURUSD15M": "EUR/USD (Euro)", "KXGBPUSD15M": "GBP/USD (British Pound)", "KXUSDJPY15M": "USD/JPY (Japanese Yen)",
    "KXUSDCAD15M": "USD/CAD (Canadian Dollar)", "KXAUDUSD15M": "AUD/USD (Australian Dollar)",
}


def name(ticker):
    """The display name; a series not in NAMES falls back to the ticker without KX and 15M, never a blank."""
    t = str(ticker or "")
    if t in NAMES:
        return NAMES[t]
    core = t[2:] if t.startswith("KX") else t
    core = core[:-3] if core.endswith("15M") else core
    return core or t or "?"


def mkt(ticker):
    """A market cell's text: the readable name, the ticker in a hover title so it is still findable."""
    return f'<span title="{esc(ticker)}">{esc(name(ticker))}</span>'


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


SORT_LINE = "Sorted automatically each hour by return after fees; nothing is removed."
BAD_THEAD = '<thead style="background:rgba(220,38,38,.14)">'


def _zd(c):
    """z clustered by day means nothing on one day: 'needs 2+ days' until there are two."""
    return "needs 2+ days" if (c.get("days") or 0) < 2 else _z(c.get("z"))


def _under10(n):
    return ' <span class="mut sm">under 10</span>' if n < 10 else ""


def split_markets(items):
    """items: [(series, n, roi)] -> (doing, not_doing, no_bets): return after fees > 0 v <= 0, each by bets descending
    (then name); markets with no bets yet listed apart. Recomputed from the live record on every build."""
    key = lambda r: (-r[1], name(r[0]))
    bet = [r for r in items if r[1]]
    return (sorted([r for r in bet if r[2] > 0], key=key), sorted([r for r in bet if r[2] <= 0], key=key),
            sorted([r[0] for r in items if not r[1]], key=name))


def count_line(good, bad):
    return f'<p class="sm ls-count"><b>{len(good)} doing well · {len(bad)} not</b></p>'


def _split_html(head, good, bad, tr, none=()):
    """Doing well, then Not doing well (red header) directly below, then any no-bet markets on one line."""
    return (f'<p class="sm">Doing well · return after fees above 0 ({len(good)})</p>'
            + (_table(head, [tr(r) for r in good]) if good else '<p class="sm mut">None yet.</p>')
            + f'<p class="sm ls-bad">Not doing well · return after fees 0 or below ({len(bad)})</p>'
            + (_table(head, [tr(r) for r in bad]).replace("<thead>", BAD_THEAD, 1) if bad
               else '<p class="sm mut">None yet.</p>')
            + (f'<p class="sm mut">No bets yet: {", ".join(mkt(t) for t in none)}</p>' if none else ""))


def _cell_tr(label, c, ticker=None):
    first = mkt(ticker) if ticker else esc(label)
    if not c:
        return f'<tr><td>{first}</td>' + '<td class="num">—</td>' * 6 + '</tr>'
    h0, h1 = c["half_roi"]
    return (f'<tr><td>{first}</td><td class="num">{c["n"]}</td><td class="num">{c["hit_rate"] * 100:.0f}%</td>'
            f'<td class="num">{c["fair"] * 100:.0f}%</td><td class="num">{pct(c["mean_roi"])}</td>'
            f'<td class="num">{_zd(c)}</td><td class="num">{pct(h0)} / {pct(h1)}</td></tr>')


HEAD = ("Cell", "n", "Hit", "Fair", "ROI after fees", "z (by day)", "Halves")


def _splits(state, key):
    rows = []
    for name, flt in (
            *[(g, (lambda w, g=g: w["group"] == g)) for g in W.GROUPS],
            ("US hours (9:30–16:00 ET weekdays)", lambda w: w["us_hours"]),
            ("Overnight and weekends", lambda w: not w["us_hours"])):
        rows.append(_cell_tr(name, W.cells(state, flt).get(key)))
    return _table(HEAD, rows)


def _v1_markets(state, key):
    """(count line, split tables) for one v1 strategy cell, by series."""
    cs = {s: W.cells(state, lambda w, s=s: w["series"] == s).get(key)
          for s in sorted({w["series"] for w in state["windows"].values()})}
    good, bad, none = split_markets([(s, c["n"] if c else 0, c["mean_roi"] if c else 0) for s, c in cs.items()])
    tr = lambda r: _cell_tr(r[0], cs[r[0]], ticker=r[0]).replace(f"{mkt(r[0])}</td>", f"{mkt(r[0])}{_under10(r[1])}</td>", 1)
    return count_line(good, bad), _split_html(("Market",) + HEAD[1:], good, bad, tr, none)


def _removed_fold(labels, removed, removed_at, won_word, word="Removed", note=""):
    """The cells taken out at a cut: their final n, wins and ROI (windows before the cut), collapsed."""
    trs = []
    for strat, label in labels.items():
        r = (removed or {}).get(strat) or {}
        for s, x in (r.get("series") or {}).items():
            trs.append(f'<tr><td>{esc(label)}</td><td>{mkt(s)}</td><td class="num">{x["n"] if x else 0}</td>'
                       f'<td class="num">{x["hits"] if x else "—"}</td>'
                       f'<td class="num">{pct(x["mean_roi"]) if x else "—"}</td></tr>')
    if not trs:
        return ""
    return (f'<details class="fold sw15-removed"><summary>{esc(word)} {esc(_start(removed_at))} · {len(trs)} markets, '
            f'final records</summary>{note}' + _table(("Rule", "Market", "n", "Wins", "ROI after fees"), trs) + '</details>')


def _frozen_block(anchor, title, line, version, labels, rec, sport, won_word, removed=None, removed_at=None, extra=""):
    """A frozen-cell lane block (sw15, flip, hte): one row per strategy with cells, each market's n, wins and ROI in its
    fold, then the removed cells' final records (collapsed)."""
    rows = []
    for strat, label in labels.items():
        r = rec[strat]
        if not r["series"]:
            continue                                             # a row with every market removed shows only below
        per = {s: (x["n"] if x else 0) for s, x in r["series"].items()}
        ser = r["series"]
        good, bad, none = split_markets([(s, x["n"] if x else 0, x["mean_roi"] if x else 0) for s, x in ser.items()])
        tr = lambda q: (f'<tr><td>{mkt(q[0])}{_under10(q[1])}</td><td class="num">{q[1]}</td>'
                        f'<td class="num">{ser[q[0]]["hits"]}</td><td class="num">{pct(ser[q[0]]["mean_roi"])}</td>'
                        f'<td class="num">{_zd(ser[q[0]])}</td></tr>')
        skips = r.get("skips") or {}
        body = (count_line(good, bad)
                + f'<p class="sp-details-name"><b>{esc(label)}</b> · Kalshi 15-minute windows · paper · {esc(version)}</p>'
                f'<p class="sp-def">Frozen: {len(r["series"])} markets. Held to settlement; taker fee '
                f'on entry.</p>' + _split_html(("Market", "n", won_word(strat), "ROI after fees", "z (by day)"),
                                               good, bad, tr, none)
                + (f'<p class="sm mut">Skipped: {esc(", ".join(f"{k} {v}" for k, v in sorted(skips.items())))}</p>'
                   if skips else ""))
        rows.append(_row(strat, label, r["all"], per, body).replace('data-sport="swing15"', f'data-sport="{sport}"'))
    head = ('<div class="sp-line sp-head-line" aria-hidden="true"><span class="sp-cell sp-c-name">Rule</span>'
            '<span class="sp-cell sp-c-market">Market</span><span class="sp-cell num">Record</span>'
            '<span class="sp-cell num">ROI after fees</span><span class="sp-cell num">Won v priced</span>'
            '<span class="sp-cell num">Evidence</span><span class="sp-cell sp-c-verdict">Verdict</span></div>')
    return (f'<h3 class="dm-title" id="{anchor}">{esc(title)}</h3><p class="scope">{esc(line)}</p>'
            f'<p class="sm mut">{SORT_LINE}</p>'
            f'<div class="sp-rules-list" data-list="sandbox">{head}{"".join(rows)}</div>'
            + extra + (_removed_fold(labels, removed, removed_at, won_word) if removed_at else ""))


def _cut_line(M):
    return f" {M.VERSION} from {_start(M.REMOVED_AT)}: negative markets removed after ~4h of results."


def _start(iso):
    return iso[:16].replace("T", " ") + " UTC"


def v2_block(state):
    """15-Minute Swing v2 (swing15v2.py), then The Flip Side v2 (flipside_v2.py). Above v1."""
    import swing15v2 as V
    out = _frozen_block("swing15v2", "15-Minute Swing v3",
                        f"Cells picked from one overnight session; fresh record from {_start(V.FROM)}; review at "
                        f"{W.REVIEW_AT}, decide at {W.DECIDE_AT}." + _cut_line(V), V.VERSION, V.LABELS, V.records(state),
                        "swing15v2", lambda k: "Sells filled" if k == "swing15v2_s1" else "Won",
                        V.records(state, removed=True), V.REMOVED_AT, extra=_v3_s1_retired(state, V))
    try:
        import flipside_v2 as F
        out += _frozen_block("flipside_v2", "The Flip Side v3",
                             "Opposite side of the 15-Minute Swing; cells picked from one overnight session; 14-day "
                             f"backtest of the flips ran −0.5% to −16%; fresh record from {_start(F.FROM)}; review at "
                             f"{W.REVIEW_AT}, decide at {W.DECIDE_AT}." + _cut_line(F), F.VERSION, F.LABELS,
                             F.records(state), "flipside_v2", lambda k: "Won", F.records(state, removed=True), F.REMOVED_AT)
    except Exception:                                           # noqa: BLE001  (never breaks the section)
        pass
    try:
        import holdtoend as H
        out += holdtoend_block(state, H)
    except Exception:                                           # noqa: BLE001  (never breaks the section)
        pass
    return out


def _v3_s1_retired(state, V):
    """S1 (sw15-v3) retired 2026-11-09 22:00Z for Steady Favourites: its final record, collapsed."""
    ret = V.records(state, retired=True)
    a = (ret.get("swing15v2_s1") or {}).get("all")
    since = (V.records(state, retired=True, start=V.REMOVED_AT).get("swing15v2_s1") or {}).get("all")
    note = ("" if not a else
            f'<p class="sm">S1 final: {a["hits"]}/{a["n"]} sells filled against {a["fair"] * a["n"]:.1f} priced, '
            f'{pct(a["mean_roi"])} after fees'
            + ("" if not since else f'; since the 18:00 UTC cut, {since["hits"]}/{since["n"]}, {pct(since["mean_roi"])}')
            + '. Replaced by Steady Favourites. No new entries.</p>')
    return _removed_fold({"swing15v2_s1": V.LABELS["swing15v2_s1"]}, ret, V.RETIRED_AT,
                         lambda k: "Sells filled", word="Retired", note=note)


def _v1_s1_retired(state, allc_before):
    """S1 (sw15-v1) retired 2026-11-09 22:00Z: the headline cell's final record and the whole grid, collapsed. v1 keeps
    grading S1 entries underneath (The Flip Side, Hold to End and the Lead Swap Board read them)."""
    import swing15v2 as V
    c = allc_before.get(HEADLINE_S1)
    grid = [_cell_tr(f'{float(b) * 100:g}c · {float(m):g}x · {EXIT_WORDS[how]}', allc_before.get(("swing15_s1", b, m, how)))
            for b in map(str, W.BANDS) for m in map(str, W.MULTS) for how in ("hold", "bid")]
    neg = sum(1 for b in map(str, W.BANDS) for m in map(str, W.MULTS) for how in ("hold", "bid")
              if (allc_before.get(("swing15_s1", b, m, how)) or {}).get("mean_roi", 0) < 0)
    note = ("" if not c else
            f'<p class="sm">S1 Swing · 25c · 2x · else hold, final: {c["hits"]}–{c["n"] - c["hits"]} against '
            f'{c["fair"] * c["n"]:.1f} priced, {pct(c["mean_roi"])} after fees; {neg} of {len(grid)} grid cells negative. '
            f'Replaced by Steady Favourites. No new entries.</p>')
    return (f'<details class="fold sw15-removed"><summary>Retired {esc(_start(V.RETIRED_AT))} · S1 Swing, final '
            f'records</summary>{note}' + _table(HEAD, grid) + '</details>')


def steadyfav_block(state):
    """Steady Favourites (steadyfav.py, sw15-sf1): rules A and B on four fixed markets, then the pooled controls."""
    import steadyfav as S
    rec = S.records(state)
    rows = []
    defs = {"steadyfav_a": "At minute 2, buy the side above 50c (by the mid) at its ask, filled only on a print at or "
                           "through it in the next minute; held to settlement; taker fee on entry (v1's S2).",
            "steadyfav_b": "The same at minute 10, with 5 minutes left (v1's S3)."}
    for rule, text in defs.items():
        r = rec[rule]
        ser = r["series"]
        good, bad, none = split_markets([(s, x["n"] if x else 0, x["mean_roi"] if x else 0) for s, x in ser.items()])
        tr = lambda q, ser=ser: (f'<tr><td>{mkt(q[0])}{_under10(q[1])}</td><td class="num">{q[1]}</td>'
                                 f'<td class="num">{ser[q[0]]["hits"]} v {ser[q[0]]["fair"] * q[1]:.1f}</td>'
                                 f'<td class="num">{pct(ser[q[0]]["mean_roi"])}</td><td class="num">{_zd(ser[q[0]])}</td></tr>')
        c = (rec[rule + "_ctrl"] or {}).get("all")
        ctl = ("no control windows yet" if not c else
               f'{c["hits"]}/{c["n"]} won against {c["fair"] * c["n"]:.1f} priced, {pct(c["mean_roi"])} after fees')
        body = (count_line(good, bad)
                + f'<p class="sp-details-name"><b>{esc(S.LABELS[rule])}</b> · Kalshi 15-minute windows · paper · '
                  f'{esc(S.VERSION)}</p><p class="sp-def">{esc(text)} Frozen: {len(S.MARKETS)} markets.</p>'
                + _split_html(("Market", "Bets", "Won v priced", "Return after fees", "z (by day)"), good, bad, tr, none)
                + f'<p class="sm">Control (the same rule on the other markets, pooled): {esc(ctl)}.</p>')
        per = {s: (x["n"] if x else 0) for s, x in ser.items()}
        rows.append(_row(rule, S.LABELS[rule], r["all"], per, body).replace('data-sport="swing15"', 'data-sport="steadyfav"'))
    for ctrl, rule in S.CONTROLS.items():
        c = rec[ctrl]["all"]
        body = (f'<p class="sp-details-name"><b>{esc(S.LABELS[ctrl])}</b> · paper · {esc(S.VERSION)}</p>'
                f'<p class="sp-def">Rule {rule[-1].upper()} on the other {rec[ctrl]["markets"]} 15-minute markets, one '
                f'pooled row: does "steady" beat everything else?</p>'
                + (_table(("Pooled", "Bets", "Won v priced", "Return after fees", "z (by day)"),
                          [f'<tr><td>Other markets</td><td class="num">{c["n"]}</td><td class="num">{c["hits"]} v '
                           f'{c["fair"] * c["n"]:.1f}</td><td class="num">{pct(c["mean_roi"])}</td>'
                           f'<td class="num">{_zd(c)}</td></tr>']) if c else '<p class="sm mut">No windows yet.</p>'))
        rows.append(_row(ctrl, S.LABELS[ctrl], c, {"all": c["n"] if c else 0}, body)
                    .replace('data-sport="swing15"', 'data-sport="steadyfav"'))
    old = S.records(state, earlier=True)
    ea, eb = old["steadyfav_a"]["all"], old["steadyfav_b"]["all"]
    early = ("" if not (ea or eb) else
             '<p class="sm mut sf-earlier">Earlier result, not counted (v1 on these four markets, before the start): '
             + "; ".join(f'{k} {x["hits"]}/{x["n"]}, {pct(x["mean_roi"])}' for k, x in (("A", ea), ("B", eb)) if x) + '.</p>')
    head = ('<div class="sp-line sp-head-line" aria-hidden="true"><span class="sp-cell sp-c-name">Rule</span>'
            '<span class="sp-cell sp-c-market">Market</span><span class="sp-cell num">Record</span>'
            '<span class="sp-cell num">ROI after fees</span><span class="sp-cell num">Won v priced</span>'
            '<span class="sp-cell num">Evidence</span><span class="sp-cell sp-c-verdict">Verdict</span></div>')
    names = ", ".join(name(s) for s in S.MARKETS)
    return (f'<h3 class="dm-title" id="steadyfav">Steady Favourites</h3><p class="scope">Steady Favourites · '
            f'{esc(names)} · the favourite bought at minute 2 (A) and at 5 minutes left (B), held to settlement · fresh '
            f'record from {esc(_start(S.FROM))} · review at {W.REVIEW_AT}, decide at {W.DECIDE_AT}. Replaces the S1 '
            f'Swing.</p><p class="sm mut">{SORT_LINE}</p>'
            f'<div class="sp-rules-list" data-list="sandbox">{head}{"".join(rows)}</div>{early}')


def holdtoend_block(state, H):
    """Hold to End v3: one live cell (USDCAD 35c) on a fresh record; USDCAD's earlier hte-v1 result as a muted
    not-counted line; hte-v2 (GBPUSD 35c) in a Retired fold; the 18:00Z cut in the Removed fold."""
    gone = H.records(state, removed=True)
    early = (gone.get("holdtoend_35") or {}).get("series", {}).get("KXUSDCAD15M")
    early_line = ("" if not early else
                  f'<p class="sm mut hte-earlier">Earlier result, not counted: USD/CAD 35c went {early["hits"]}/{early["n"]}, '
                  f'{pct(early["mean_roi"])} after fees ({esc(_start(H.FROM))} to {esc(_start(H.REMOVED_AT))}, hte-v1).</p>')
    ret = H.records(state, retired=True)
    r35 = (ret.get("holdtoend_35") or {}).get("all")
    note = ("" if not r35 else
            f'<p class="sm">hte-v2 final (decide at {W.DECIDE_AT}): {r35["hits"]}/{r35["n"]} against '
            f'{r35["fair"] * r35["n"]:.1f} priced, {pct(r35["mean_roi"])} after fees. No new entries.</p>')
    retired = _removed_fold({"holdtoend_35": "Hold to End v2 · 35c"}, {"holdtoend_35": ret.get("holdtoend_35")},
                            H.RETIRED_AT, lambda k: "Won", word="Retired", note=note)
    line = (f"Hold to End v3 · USD/CAD at 35c · fresh record from {_start(H.FROM_V3)} · review at {W.REVIEW_AT}, "
            f"decide at {W.DECIDE_AT}.")
    return _frozen_block("holdtoend", "Hold to End v3", line, H.VERSION, H.LABELS, H.records(state), "holdtoend",
                         lambda k: "Won", gone, H.REMOVED_AT, extra=early_line + retired)


def _bars(vals, labels):
    top = max(vals) or 1
    return _table(("Minute", "Swaps", ""), [
        f'<tr><td>{esc(l)}</td><td class="num">{v}</td><td><span aria-hidden="true" style="display:inline-block;height:.6em;'
        f'width:{round(100 * v / top)}px;background:currentColor;opacity:.45"></span></td></tr>' for v, l in zip(vals, labels)])


def _rank_tr(r):
    return (f'<tr><td>{mkt(r[0])}</td><td class="num">{r[1]:.2f}</td><td class="num">{r[2]}</td>'
            f'<td class="num">{r[3]:.0f}c</td></tr>')


LS_TRADES = (("leadswap_swing", "leadswap_swing_ctrl", "Swing on swappy markets"),
             ("leadswap_fav", "leadswap_fav_ctrl", "Favourite on steady markets"))


def _picked(picks):
    """{series: [hours in the top 3, hours in the bottom 3]} over every frozen hour."""
    out = {}
    for p in (picks or {}).values():
        for i, side in enumerate(("top", "bottom")):
            for t in p.get(side) or []:
                out.setdefault(t, [0, 0])[i] += 1
    return out


def ls_groups(rt, picks, ranked=()):
    """{trade: (doing, not_doing, not_picked)}: the trade's markets split by REAL return after fees (> 0 doing well,
    <= 0 not), each sorted by bets descending; rows are (series, [n, wins, roi sum], control or None, [top, bottom]).
    not_picked: ranked markets with no bets in the trade. Recomputed from the live record every build."""
    times = _picked(picks)
    out = {}
    for strat, ctrl, _label in LS_TRADES:
        ser = ((rt or {}).get(strat) or {}).get("series") or {}
        cs = ((rt or {}).get(ctrl) or {}).get("series") or {}
        rows = [(s, v, cs.get(s), times.get(s, [0, 0])) for s, v in ser.items() if v and v[0]]
        rows.sort(key=lambda r: (-r[1][0], name(r[0])))
        traded = {r[0] for r in rows}
        seen = sorted({t for t in list(ranked) + list(times) if t not in traded}, key=name)
        out[strat] = ([r for r in rows if r[1][2] > 0], [r for r in rows if r[1][2] <= 0], seen)
    return out


def _ls_tr(r):
    s, v, c, t = r
    tag = _under10(v[0])
    ctl = "—" if not c or not c[0] else f"{c[1]}/{c[0]}, {pct(c[2] / c[0])}"
    return (f'<tr><td>{mkt(s)}{tag}</td><td class="num">{v[0]}</td><td class="num">{v[1]}</td>'
            f'<td class="num">{pct(v[2] / v[0])}</td><td class="num">{ctl}</td><td class="num">{t[0]} / {t[1]}</td></tr>')


LS_HEAD = ("Market", "Bets", "Wins", "Return after fees", "Control (wins/bets, return)",
           "Times picked (hours top 3 / bottom 3)")


def ls_groups_html(rt, picks, ranked=()):
    g = ls_groups(rt, picks, ranked)
    parts = [f'<p class="sm mut">{SORT_LINE}</p>']
    for strat, _ctrl, label in LS_TRADES:
        good, bad, none = g[strat]
        parts.append(
            f'<div class="ls-trade" data-trade="{strat}"><h4>{esc(label)}</h4>{count_line(good, bad)}'
            + _split_html(LS_HEAD, good, bad, _ls_tr)
            + f'<details class="fold"><summary>Not picked yet ({len(none)})</summary><p class="sm">'
            + (", ".join(mkt(t) for t in none) or "none") + '</p></details></div>')
    return "".join(parts)


def leadswap_block(state):
    """The Lead Swap Board (leadswap.py): the routing record rows, then the board, persistence and timing folds."""
    import leadswap as L
    led = L.load()
    if not led.get("board"):
        led = L.update(state, L.empty())
    b, per, rt = led["board"], led["persistence"] or {}, led["routing"] or {}
    rows = []
    for strat, label in L.STRATS.items():
        c = rt.get(strat)
        trs = [f'<tr><td>{mkt(s)}</td><td class="num">{v[0]}</td><td class="num">{v[1]}</td>'
               f'<td class="num">{pct(v[2] / v[0])}</td></tr>' for s, v in sorted(((c or {}).get("series") or {}).items())]
        what = ("v1's S1 35c entry held to settlement" if "swing" in strat else "v1's S3 favourite at minute 10, held")
        clus = "" if not c else "; %d clusters, z %s" % (c["clusters"], _z(c["z"]))
        bf = ("" if not c or c.get("before_freeze") is None else
              " %d of %d entries came before that hour's picks were frozen (~:04); the picks use only data to :00, "
              "but a live version could only act from :05." % (c["before_freeze"], c["n"]))
        who = ("the top 3" if strat in ("leadswap_swing", "leadswap_fav_ctrl") else "the bottom 3")
        body = (f'<p class="sp-details-name"><b>{esc(label)}</b> · Kalshi 15-minute windows · paper · {esc(L.VERSION)}</p>'
                f'<p class="sp-def">{esc(what)}, on {esc(who)} series by lead swaps over the past 2 hours, picked at the '
                f'top of each hour and frozen. z clusters one block (crypto, metals, energy, yields, FX, indices) in one '
                f'window{clus}.{bf}</p>'
                + _table(("Market", "n", "Won", "ROI after fees"), trs))
        rows.append(_row(strat, label, c, {"all": c["n"] if c else 0}, body).replace('data-sport="swing15"', 'data-sport="leadswap"'))
    head = ('<div class="sp-line sp-head-line" aria-hidden="true"><span class="sp-cell sp-c-name">Rule</span>'
            '<span class="sp-cell sp-c-market">Market</span><span class="sp-cell num">Record</span>'
            '<span class="sp-cell num">ROI after fees</span><span class="sp-cell num">Won v priced</span>'
            '<span class="sp-cell num">Evidence</span><span class="sp-cell sp-c-verdict">Verdict</span></div>')
    sl = L.SPOTLAG
    spot = ("Spot lag recorder: not started" if not sl.get("since") else
            f"Spot lag recorder: recording since {_start(sl['since'])}"
            + (f", until {_start(sl['until'])}" if sl.get("until") else "")
            + " (Coinbase spot v Kalshi BTC/ETH/SOL 15-minute books, every second; record only)")
    pk = led.get("picks") or {}
    last = pk[max(pk)] if pk else None
    picks_line = ("" if not last else
                  f'<p class="sm">Picks for {esc(_start(max(pk)))} (frozen {esc(_start(last.get("at") or max(pk)))}): '
                  f'swing → {", ".join(mkt(t) for t in last.get("top") or []) or "none"}; favourite → '
                  f'{", ".join(mkt(t) for t in last.get("bottom") or []) or "none"}.</p>')
    rh = ("Market", "Swaps a window", "Windows", "Mid range 0-9")
    med = "—" if b["median_swing"] is None else "%gc" % b["median_swing"]
    f14 = "—" if b["fav14_won"] is None else "%.0f%%" % (b["fav14_won"] * 100)
    p2, p24 = b["past2h"], b["past24h"]
    board = (f'<details class="fold" open><summary>Board · last 2 hours (8 windows) and last 24 hours</summary>'
             f'{picks_line}'
             f'<p class="sm">Most swaps, last 2 hours</p>{_table(rh, [_rank_tr(r) for r in p2[:5]])}'
             f'<p class="sm">Most stable, last 2 hours</p>{_table(rh, [_rank_tr(r) for r in p2[::-1][:5]])}'
             f'<p class="sm">Most swaps, last 24 hours</p>{_table(rh, [_rank_tr(r) for r in p24[:5]])}'
             f'<p class="sm">Most stable, last 24 hours</p>{_table(rh, [_rank_tr(r) for r in p24[::-1][:5]])}'
             f'<p class="sm mut">Last 24 hours: {b["windows_24h"]} windows, {b["swaps_24h"]} swaps; median swing '
             f'{med}; the minute-14 favourite won {f14}.</p></details>')
    timing = (f'<details class="fold"><summary>When in the window the swaps happen (last 24 hours)</summary>'
              f'{_bars(b["minutes"], [str(m) for m in range(15)])}</details>')
    hours = list(range(24))
    heat_rows = []
    for s, hs in sorted(b["heat"].items(), key=lambda kv: (b["blocks"].get(kv[0], ""), kv[0])):
        cells = []
        for h in hours:
            v = hs.get(str(h))
            if not v or not v[1]:
                cells.append('<td class="num mut">·</td>')
                continue
            r = v[0] / v[1]
            cells.append(f'<td class="num" style="background:rgba(127,127,127,{min(.6, r / 4):.2f})">{r:.1f}</td>')
        heat_rows.append(f'<tr><td>{mkt(s)}</td>{"".join(cells)}</tr>')
    heat = ('<details class="fold"><summary>Swaps a window by hour of day (ET), every series</summary><div class="tbl">'
            '<table><thead><tr><th>Market</th>' + "".join(f'<th class="num">{h}</th>' for h in hours)
            + '</tr></thead><tbody>' + "".join(heat_rows) + '</tbody></table></div></details>')
    corr = [f'<tr><td>{esc(f)}</td><td class="num">{v["n"]}</td><td class="num">{_z(v["corr"])}</td></tr>'
            for f, v in (per.get("corr") or {}).items()]
    frac = lambda x: "—" if x is None else f"{x * 100:.0f}%"
    persist = (f'<details class="fold"><summary>Persistence: does the ranking carry into the next hour?</summary>'
               f'<p class="sm">Over {per.get("hours", 0)} hours, the past-2h top 3 were still top 3 in that hour '
               f'{frac(per.get("top"))} of the time and the bottom 3 stayed bottom 3 {frac(per.get("bottom"))}; '
               f'chance is {frac(per.get("chance"))}. FX swaps more by construction (small moves against the strike), so '
               f'the top 3 is mostly FX; within each block, the past-2h top stayed top '
               f'{frac((per.get("within_all") or {}).get("stay"))} against chance '
               f'{frac((per.get("within_all") or {}).get("chance"))}.</p>'
               + _table(("Block", "Slots", "Stayed top", "Chance"),
                        [f'<tr><td>{esc(bk)}</td><td class="num">{v["slots"]}</td><td class="num">{frac(v["stay"])}</td>'
                         f'<td class="num">{frac(v["chance"])}</td></tr>' for bk, v in (per.get("within") or {}).items()])
               + _table(("Group", "Windows", "Corr: past-2h swaps v the window"), corr) + '</details>')
    return (f'<h3 class="dm-title" id="leadswap">Lead Swap Board</h3><p class="scope">How often the lead (YES mid across '
            f'50c) swaps on every 15-minute series; swing trade to the most swaps, favourite to the most stable, each '
            f'against its opposite; picks frozen at about :04 each hour (a live version could only act from :05); fresh '
            f'record from {esc(_start(L.FROM))}; review at {W.REVIEW_AT}, decide at {W.DECIDE_AT}.</p><p class="sm mut" id="spotlag-status">{esc(spot)}</p>'
            f'<div class="sp-rules-list" data-list="sandbox">{head}{"".join(rows)}</div>'
            f'{ls_groups_html(rt, pk, [r[0] for r in (b.get("past24h") or []) + (b.get("past2h") or [])])}'
            f'{board}{persist}{timing}{heat}')


def section(state=None):
    state = W.load() if state is None else state
    allc = W.cells(state)
    n_w = len(state.get("windows") or {})
    import swing15v2 as V
    s1_final = W.cells(state, lambda w: W._ts(w["open"]) < W._ts(V.RETIRED_AT))
    defs = {
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
                f'Financials (scanned {len(state.get("series") or [])} / with windows '
                f'{len({w["series"] for w in (state.get("windows") or {}).values()})})</dd>'
                '<dt>Fees</dt><dd>Taker 0.07·p(1−p) on an entry and a sell at the bid; maker 0.0175·p(1−p) on a resting '
                'sell</dd><dt>Read</dt><dd>Review at 10 and decide at 30 settled windows per strategy and series; z '
                'clustered by day</dd></dl>')
        cnt, mk = _v1_markets(state, ck)
        body = cnt + body + f'<p class="sm mut">{SORT_LINE}</p>' + mk
        body += f'<details class="fold"><summary>Splits: group and hours</summary>{_splits(state, ck)}</details>'
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
    try:
        v2 = v2_block(state)
    except Exception:                                           # noqa: BLE001  (v2 never breaks the v1 section)
        v2 = ""
    try:
        lsb = leadswap_block(state)
    except Exception:                                           # noqa: BLE001  (the board never breaks the section)
        lsb = ""
    # 2026-11-09 (Olu: easy to review): one block, in order: the Lead Swap Board, Swing v2, The Flip Side v2, Hold to
    # End, then v1, the full collector on every series, collapsed by default.
    try:
        sf = steadyfav_block(state)
    except Exception:                                           # noqa: BLE001  (never breaks the section)
        sf = ""
    return (f'<h2 class="dm-title">15-Minute Swing</h2>{sf}{lsb}{v2}'
            f'<details class="fold sw15-v1"><summary><b>15-Minute Swing v1 · every market</b> · the full collector; '
            f'record from {esc(_start(W.FROM))}</summary>'
            f'<p class="scope">Every Kalshi 15-minute window in Crypto, '
            f'Commodities and Financials · S2 and S3 pre-registered (S1 retired) · paper</p>'
            f'<div class="sp-rules-list" data-list="sandbox">{head}{"".join(rows)}</div>{_v1_s1_retired(state, s1_final)}'
            f'{method}</details>')


def index_rows(state=None):
    state = W.load() if state is None else state
    allc = W.cells(state)
    out = []
    import steadyfav as S                                       # Steady Favourites (2026-11-09): first
    for key, r in S.records(state).items():
        c = r["all"]
        out.append(dict(lane=key, label="Steady Favourites · " + S.LABELS[key], n=c["n"] if c else 0,
                        roi=c["mean_roi"] if c else None, hit=c["hit_rate"] if c else None,
                        fair=c["fair"] if c else None, status=f"{c['n'] if c else 0}/{W.DECIDE_AT}"))
    for key, label in W.STRATS.items():
        if key == "swing15_s1":
            continue                                             # retired 2026-11-09 22:00Z (graded underneath)
        ck = HEADLINE_S1 if key == "swing15_s1" else (key,)
        c = allc.get(ck)
        per = _per_series(state, ck)
        out.append(dict(lane=key, label=label + (" · 25c · 2x · hold" if key == "swing15_s1" else ""),
                        n=c["n"] if c else 0, roi=c["mean_roi"] if c else None,
                        hit=c["hit_rate"] if c else None, fair=c["fair"] if c else None,
                        status=(f"{max(per.values(), default=0)}/{W.DECIDE_AT} in its best series")))
    import swing15v2 as V                                       # v2 (2026-11-09): its own rows, a fresh record
    for key, r in V.records(state).items():
        if not r["series"]:
            continue
        c = r["all"]
        best = max(((x or {}).get("n", 0) for x in r["series"].values()), default=0)
        out.append(dict(lane=key, label="Swing v3 · " + V.LABELS[key], n=c["n"] if c else 0, roi=c["mean_roi"] if c else None,
                        hit=c["hit_rate"] if c else None, fair=c["fair"] if c else None,
                        status=f"{best}/{W.DECIDE_AT} in its best market"))
    import flipside_v2 as F                                     # The Flip Side v2 (2026-11-09)
    for key, r in F.records(state).items():
        if not r["series"]:
            continue
        c = r["all"]
        best = max(((x or {}).get("n", 0) for x in r["series"].values()), default=0)
        out.append(dict(lane=key, label="Flip Side v3 · " + F.LABELS[key], n=c["n"] if c else 0,
                        roi=c["mean_roi"] if c else None, hit=c["hit_rate"] if c else None,
                        fair=c["fair"] if c else None, status=f"{best}/{W.DECIDE_AT} in its best market"))
    import holdtoend as H                                       # Hold to End (2026-11-09)
    import leadswap as L
    for key, r in H.records(state).items():
        if not r["series"]:
            continue                                            # hte-v2 removed the 25c row entirely
        c = r["all"]
        best = max(((x or {}).get("n", 0) for x in r["series"].values()), default=0)
        out.append(dict(lane=key, label="Hold to End v3 · " + H.LABELS[key].replace("Hold to End · ", ""), n=c["n"] if c else 0,
                        roi=c["mean_roi"] if c else None, hit=c["hit_rate"] if c else None,
                        fair=c["fair"] if c else None, status=f"{best}/{W.DECIDE_AT} in its best market"))
    rt = (L.load().get("routing") or {})                        # Lead Swap Board routing (2026-11-09)
    for key, label in L.STRATS.items():
        c = rt.get(key)
        out.append(dict(lane=key, label="Lead Swap · " + label, n=c["n"] if c else 0,
                        roi=c["mean_roi"] if c else None, hit=c["hit_rate"] if c else None,
                        fair=c["fair"] if c else None, status=f"{c['n'] if c else 0}/{W.DECIDE_AT}"))
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
            'Crypto, Commodities and Financials · pre-registered strategies · paper · not in Production</p>'
            '<div class="tbl"><table><tr><th>Strategy</th><th>Page</th><th class="num">Windows</th>'
            '<th class="num">Hit v fair</th><th class="num">ROI after fees</th><th>Evidence</th></tr>'
            + rows + '</table></div></section>')
