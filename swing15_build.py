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


def _frozen_block(anchor, title, line, version, labels, rec, sport, won_word):
    """A frozen-cell lane block (sw15-v2, flip-v2): one row per strategy, each market's n, wins and ROI in its fold."""
    rows = []
    for strat, label in labels.items():
        r = rec[strat]
        per = {s: (x["n"] if x else 0) for s, x in r["series"].items()}
        trs = [f'<tr><td>{esc(s)}</td><td class="num">{x["n"] if x else 0}</td>'
               f'<td class="num">{x["hits"] if x else "—"}</td><td class="num">{pct(x["mean_roi"]) if x else "—"}</td></tr>'
               for s, x in r["series"].items()]
        skips = r.get("skips") or {}
        body = (f'<p class="sp-details-name"><b>{esc(label)}</b> · Kalshi 15-minute windows · paper · {esc(version)}</p>'
                f'<p class="sp-def">Frozen at registration: {len(r["series"])} markets. Held to settlement; taker fee '
                f'on entry.</p>' + _table(("Market", "n", won_word(strat), "ROI after fees"), trs)
                + (f'<p class="sm mut">Skipped: {esc(", ".join(f"{k} {v}" for k, v in sorted(skips.items())))}</p>'
                   if skips else ""))
        rows.append(_row(strat, label, r["all"], per, body).replace('data-sport="swing15"', f'data-sport="{sport}"'))
    head = ('<div class="sp-line sp-head-line" aria-hidden="true"><span class="sp-cell sp-c-name">Rule</span>'
            '<span class="sp-cell sp-c-market">Market</span><span class="sp-cell num">Record</span>'
            '<span class="sp-cell num">ROI after fees</span><span class="sp-cell num">Won v priced</span>'
            '<span class="sp-cell num">Evidence</span><span class="sp-cell sp-c-verdict">Verdict</span></div>')
    return (f'<h3 class="dm-title" id="{anchor}">{esc(title)}</h3><p class="scope">{esc(line)}</p>'
            f'<div class="sp-rules-list" data-list="sandbox">{head}{"".join(rows)}</div>')


def _start(iso):
    return iso[:16].replace("T", " ") + " UTC"


def v2_block(state):
    """15-Minute Swing v2 (swing15v2.py), then The Flip Side v2 (flipside_v2.py). Above v1."""
    import swing15v2 as V
    out = _frozen_block("swing15v2", "15-Minute Swing v2",
                        f"Cells picked from one overnight session; fresh record from {_start(V.FROM)}; review at "
                        f"{W.REVIEW_AT}, decide at {W.DECIDE_AT}.", V.VERSION, V.LABELS, V.records(state), "swing15v2",
                        lambda k: "Sells filled" if k == "swing15v2_s1" else "Won")
    try:
        import flipside_v2 as F
        out += _frozen_block("flipside_v2", "The Flip Side v2",
                             "Opposite side of the 15-Minute Swing; cells picked from one overnight session; 14-day "
                             f"backtest of the flips ran −0.5% to −16%; fresh record from {_start(F.FROM)}; review at "
                             f"{W.REVIEW_AT}, decide at {W.DECIDE_AT}.", F.VERSION, F.LABELS, F.records(state),
                             "flipside_v2", lambda k: "Won")
    except Exception:                                           # noqa: BLE001  (never breaks the section)
        pass
    try:
        import holdtoend as H
        out += _frozen_block("holdtoend", "Hold to End",
                             "Cheap side bought at 25c/35c in the first 5 minutes, held to settlement, no sell; cells over "
                             f"+10% in one overnight session; fresh record from {_start(H.FROM)}; review at "
                             f"{W.REVIEW_AT}, decide at {W.DECIDE_AT}.", H.VERSION, H.LABELS, H.records(state),
                             "holdtoend", lambda k: "Won")
    except Exception:                                           # noqa: BLE001  (never breaks the section)
        pass
    return out


def _bars(vals, labels):
    top = max(vals) or 1
    return _table(("Minute", "Swaps", ""), [
        f'<tr><td>{esc(l)}</td><td class="num">{v}</td><td><span aria-hidden="true" style="display:inline-block;height:.6em;'
        f'width:{round(100 * v / top)}px;background:currentColor;opacity:.45"></span></td></tr>' for v, l in zip(vals, labels)])


def _rank_tr(r):
    return (f'<tr><td>{esc(r[0])}</td><td class="num">{r[1]:.2f}</td><td class="num">{r[2]}</td>'
            f'<td class="num">{r[3]:.0f}c</td></tr>')


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
        trs = [f'<tr><td>{esc(s)}</td><td class="num">{v[0]}</td><td class="num">{v[1]}</td>'
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
    rh = ("Series", "Swaps a window", "Windows", "Mid range 0-9")
    med = "—" if b["median_swing"] is None else "%gc" % b["median_swing"]
    f14 = "—" if b["fav14_won"] is None else "%.0f%%" % (b["fav14_won"] * 100)
    p2, p24 = b["past2h"], b["past24h"]
    board = (f'<details class="fold" open><summary>Board · last 2 hours (8 windows) and last 24 hours</summary>'
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
        heat_rows.append(f'<tr><td>{esc(s)}</td>{"".join(cells)}</tr>')
    heat = ('<details class="fold"><summary>Swaps a window by hour of day (ET), every series</summary><div class="tbl">'
            '<table><thead><tr><th>Series</th>' + "".join(f'<th class="num">{h}</th>' for h in hours)
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
            f'{board}{persist}{timing}{heat}')


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
                f'Financials (scanned {len(state.get("series") or [])} / with windows '
                f'{len({w["series"] for w in (state.get("windows") or {}).values()})})</dd>'
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
    return (f'<h2 class="dm-title">15-Minute Swing</h2>{lsb}{v2}'
            f'<details class="fold sw15-v1"><summary><b>15-Minute Swing v1 · every market</b> · the full collector; '
            f'record from {esc(_start(W.FROM))}</summary>'
            f'<p class="scope">Every Kalshi 15-minute window in Crypto, '
            f'Commodities and Financials · three pre-registered strategies · paper</p>'
            f'<div class="sp-rules-list" data-list="sandbox">{head}{"".join(rows)}</div>{method}</details>')


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
    import swing15v2 as V                                       # v2 (2026-11-09): its own rows, a fresh record
    for key, r in V.records(state).items():
        c = r["all"]
        best = max(((x or {}).get("n", 0) for x in r["series"].values()), default=0)
        out.append(dict(lane=key, label="v2 · " + V.LABELS[key], n=c["n"] if c else 0, roi=c["mean_roi"] if c else None,
                        hit=c["hit_rate"] if c else None, fair=c["fair"] if c else None,
                        status=f"{best}/{W.DECIDE_AT} in its best market"))
    import flipside_v2 as F                                     # The Flip Side v2 (2026-11-09)
    for key, r in F.records(state).items():
        c = r["all"]
        best = max(((x or {}).get("n", 0) for x in r["series"].values()), default=0)
        out.append(dict(lane=key, label="Flip Side v2 · " + F.LABELS[key], n=c["n"] if c else 0,
                        roi=c["mean_roi"] if c else None, hit=c["hit_rate"] if c else None,
                        fair=c["fair"] if c else None, status=f"{best}/{W.DECIDE_AT} in its best market"))
    import holdtoend as H                                       # Hold to End (2026-11-09)
    import leadswap as L
    for key, r in H.records(state).items():
        c = r["all"]
        best = max(((x or {}).get("n", 0) for x in r["series"].values()), default=0)
        out.append(dict(lane=key, label=H.LABELS[key], n=c["n"] if c else 0,
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
            'Crypto, Commodities and Financials · three pre-registered strategies · paper · not in Production</p>'
            '<div class="tbl"><table><tr><th>Strategy</th><th>Page</th><th class="num">Windows</th>'
            '<th class="num">Hit v fair</th><th class="num">ROI after fees</th><th>Evidence</th></tr>'
            + rows + '</table></div></section>')
