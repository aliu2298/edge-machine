"""The Weather section of the Daily Markets tab and its Sandbox index rows (climate_lanes.py, 2026-11-13). Paper, no orders.

Two lanes: the cold lean on daily highs (version 2) and the warm lean on daily lows. Each is one collapsed row in the same Rules-list
design as the 15-Minute section; its fold holds the record against its control rows, the last entries, and the rule in words.
Public copy: percentages and counts only. Presentation only: no rule, record or pick depends on this file."""
import html as _h

import climate_lanes as L

ANCHOR = "weather"


def esc(x):
    return _h.escape(str(x))


def pct(v, d=1):
    return "—" if v is None else f"{v * 100:+.{d}f}%".replace("-", "−")


def pct0(v):
    return "—" if v is None else f"{v * 100:.0f}%"


def tfmt(v):
    return "—" if v is None else f"{v:+.2f}".replace("-", "−")


def _tone(s, need):
    if s["n"] < need or s["roi"] is None:
        return "mut"
    return "pos" if s["roi"] > 0 else "neg"


RULES = {
    "c1v2": [
        ("Entry", "10:00 pm Eastern the day before, on each city's next-day high ladder with all six brackets quoted. The favourite is the highest mid; "
                  "buy NO on the bracket two cooler at the quote (1 minus the YES bid), taker fee, hold to settlement."),
        ("Skip", "No bracket two cooler, a YES bid of 0, fewer than six brackets quoted, or the public forecast above the favourite. The forecast is the "
                 "newest NBM station text run at least 2 hours old: the larger of its daytime max and its 3-hourly temperatures inside the day, plus the "
                 "city's shift. No forecast readable: the bet is taken and marked. The skipped bets are recorded as a control."),
        ("Controls", "(a) NO on the bracket two warmer, same time. (b) The bets the forecast skipped, recorded but not counted in the lane."),
        ("Scope", "The 21 daily-high cities of the study. Fills are quoted prices, not trade-confirmed. A city-day is one outcome."),
        ("Read", "Once at 1,000 settled bets. Keep if the return is above zero and above control (a). Retire if zero or below, or not above control (a). "
                 "If the skipped bets returned more than the lane, it goes back to version 1 on the same record. Review early if below −3% at 300."),
        ("Research", "Found Dec 2025 to Jun 2026 and confirmed on Jul to Nov 11 2026: +1.7% a bet on 1,601 city-days, score 2.9 (version 1: +1.4% on 1,730)."),
    ],
    "l1": [
        ("Entry", "10:00 pm Eastern the day before, on each city's next-day low ladder with all six brackets quoted. The favourite is the highest mid; "
                  "buy NO on the bracket two warmer at the quote (1 minus the YES bid), taker fee, hold to settlement."),
        ("Skip", "No bracket two warmer, a YES bid of 0, or fewer than six brackets quoted."),
        ("Controls", "NO on the bracket two cooler, same time. It should lose."),
        ("Scope", "The 21 daily-low cities of the study. Fills are quoted prices, not trade-confirmed. Depth at the YES bid is logged: the books are thin."),
        ("Read", "Once at 500 settled bets. Keep if the return is above zero and above the control. Retire if zero or below, or not above the control. "
                 "Review early if below −3% at 150. Also report the share of entries with fewer than 10 contracts at the bid; it does not decide keep or retire."),
        ("Research", "Found Dec 2025 to Jun 2026: +1.9% on 1,146. Unseen Jul to Nov 11 2026: +2.1% on 1,021, score 3.0. The control lost 2.1%."),
    ],
}


def _params(items):
    return '<dl class="sp-params">' + "".join(f"<dt>{esc(k)}</dt><dd>{esc(v)}</dd>" for k, v in items) + "</dl>"


def _table(head, rows):
    th = "".join(f"<th{' class=\"num\"' if i else ''}>{esc(h)}</th>" for i, h in enumerate(head))
    body = ""
    for r in rows:
        cells = "".join(f'<td data-l="{esc(head[i])}"{" class=\"num\"" if i else ""}>{c}</td>' for i, c in enumerate(r))
        body += f"<tr>{cells}</tr>"
    return f'<div class="tbl"><table><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table></div>'


def record_table(rec, lane):
    rows = []
    for label, s in (("The lane", rec["main"]), ("Control · " + ("NO two warmer" if lane == "c1v2" else "NO two cooler"), rec["control"])) + \
            ((("Control · skipped by the forecast", rec["skipped"]),) if lane == "c1v2" else ()):
        rows.append([esc(label), str(s["n"]), pct0(s["won"] / s["n"]) if s["n"] else "—", pct0(s["priced"]) if s["priced"] else "—",
                     pct(s["roi"]), tfmt(s["t"]), str(s["open"])])
    return _table(["Row", "Settled", "Won", "Priced", "Return after fees", "Score", "Open"], rows)


def entries_table(state, lane, limit=60):
    rows = [r for r in state["rows"] if r["lane"] == lane]
    rows.sort(key=lambda r: (r["day"], r["series"], r["role"]), reverse=True)
    if not rows:
        return '<p class="sm mut">No entry yet. The first read is at 10:00 pm Eastern.</p>'
    out = []
    for r in rows[:limit]:
        role = {"main": "lane", "control": "control", "skipped": "skipped"}[r["role"]]
        res = "open" if r["status"] == "open" else ("won" if r["won"] else "lost")
        fc = r.get("forecast")
        fcs = "" if lane != "c1v2" or r["role"] == "control" else (
            "no forecast" if not fc or fc.get("value") is None else f'{fc["value"]:g} (run {esc(fc["run"][5:])}){" · above" if r.get("forecast_above") else ""}')
        out.append([esc(r["day"][5:]), esc(r["city"]), esc(role), esc(r["bracket"]), pct0(r["price"]),
                    "—" if r.get("depth_bid") is None else f'{r["depth_bid"]:g}', fcs, esc(res), pct(r["roi"])])
    n = len(rows)
    tbl = _table(["Day", "City", "Row", "Bracket", "NO price", "At the bid", "Forecast" if lane == "c1v2" else "", "Result", "Return"], out)
    return (f'<details class="section-disclosure"><summary><b>Entries</b><span>{n} row{"s" if n != 1 else ""}'
            f'{" · newest " + str(limit) if n > limit else ""}</span></summary>{tbl}</details>')


def _row(lane, rec, state):
    s, c = rec["main"], rec["control"]
    status = ('<span class="sig w">Read due</span>' if s["n"] >= rec["read_at"] else
              '<span class="sig w">Review</span>' if rec["read"].startswith("early") else
              f'<span class="sig n">Too early ({s["n"]}/{rec["read_at"]})</span>')
    record = f'{s["won"]}–{s["n"] - s["won"]}' if s["n"] else "—"
    wvp = f'{s["won"]} v {s["priced"] * s["n"]:.1f}' if s["n"] and s["priced"] else "—"
    thin = ""
    if lane == "l1" and s["thin"] is not None:
        thin = f'<p class="sm">Entries with fewer than 10 contracts at the bid: {pct0(s["thin"])} · median at the bid {s["depth"]:g}.</p>'
    body = (f'<p class="sm">{esc(rec["read"])}</p>{record_table(rec, lane)}{thin}{entries_table(state, lane)}'
            f'<details class="fold sw15-rule"><summary>Rule details</summary>{_params(RULES[lane])}'
            f'<p class="sm mut">Pre-registered: {esc(L.LANES[lane]["prereg"])}</p></details>')
    return (f'<details class="sp-rule{"" if s["n"] >= 10 else " is-early"}" id="wx-{lane}" data-source="climate_{lane}" data-sport="weather" '
            f'data-scope="cities" data-stage="sandbox"><summary class="sp-line"><span class="sp-cell sp-c-name"><span class="sp-chev" aria-hidden="true">›</span>'
            f'<b class="sp-name" title="{esc(rec["label"])}">{esc(rec["label"])}</b><span class="sr-only"> · Rule details</span></span>'
            f'<span class="sp-cell sp-c-market" data-l="vs control"><span class="mut">{pct(c["roi"])}</span></span>'
            f'<span class="sp-cell num" data-l="Record">{record}</span>'
            f'<span class="sp-cell num" data-l="Return after fees"><span class="{_tone(s, 10)}">{pct(s["roi"])}</span></span>'
            f'<span class="sp-cell num" data-l="Won v priced">{esc(wvp)}</span>'
            f'<span class="sp-cell num" data-l="Evidence">{min(s["n"], rec["read_at"])}/{rec["read_at"]}</span>'
            f'<span class="sp-cell sp-c-verdict" data-l="Status">{status}</span></summary>'
            f'<div class="sp-details-body">{body}</div></details>')


HEAD_LINE = ('<div class="sp-line sp-head-line" aria-hidden="true"><span class="sp-cell sp-c-name">Rule</span>'
             '<span class="sp-cell sp-c-market">vs control</span><span class="sp-cell num">Record</span>'
             '<span class="sp-cell num">Return after fees</span><span class="sp-cell num">Won v priced</span>'
             '<span class="sp-cell num">Evidence</span><span class="sp-cell sp-c-verdict">Status</span></div>')


def section(state=None):
    state = L.load() if state is None else state
    recs = {lane: L.lane_record(state, lane) for lane in L.LANES}
    since = state.get("since")
    intro = ('<p class="scope sw15-intro">Paper · two Kalshi weather lanes, one read each night at 10:00 pm Eastern · '
             + (f'fresh from {esc(since)}' if since else 'fresh from the first entry') + ' · a city-day is one outcome</p>')
    rows = "".join(_row(lane, recs[lane], state) for lane in ("c1v2", "l1"))
    night = state.get("last_run")
    foot = ('<details class="fold sw15-how"><summary>How the record is kept</summary>'
            '<p class="sm">Each night the lane reads tomorrow\'s ladders once, in a 50-minute window from 10:00 pm Eastern; a late start is logged and a missed '
            'night is not made up. Entries are quoted prices with the taker fee, held to Kalshi\'s own settlement, and graded the next day. '
            'Every row counts as one city-day. The controls are recorded at the same time and shown beside each lane.</p>'
            + (f'<p class="sm mut">Last run {esc(night[:16].replace("T", " "))} UTC' + (f' · error: {esc(state["error"])}' if state.get("error") else "") + '</p>' if night else "")
            + '</details>')
    return (f'<h2 class="dm-title">Weather</h2><div class="sw15-lane">{intro}'
            f'<div class="sp-rules-list" data-list="sandbox">{HEAD_LINE}{rows}</div>{foot}</div>')


def stats_for_tile(state=None):
    """(won, lost, roi) over the two lanes' own bets, for the page's tile and fold line."""
    state = L.load() if state is None else state
    won = lost = 0
    num = 0.0
    for lane in L.LANES:
        s = L.lane_record(state, lane)["main"]
        won += s["won"]
        lost += s["n"] - s["won"]
        num += (s["roi"] or 0.0) * s["n"]
    n = won + lost
    return dict(rules=None, open=None, won=won if n else None, lost=lost, wl=f"{won}–{lost}", label="",
                roi=(f"{num / n * 100:+.1f}%".replace("-", "−") if n else None))


def index_html(state=None):
    """The Sandbox index rows, linking to the section on the Daily Markets tab."""
    try:
        state = L.load() if state is None else state
        recs = [L.lane_record(state, lane) for lane in ("c1v2", "l1")]
    except Exception:                                           # noqa: BLE001
        return ""
    rows = "".join(
        f'<tr data-lane="climate_{esc(r["lane"])}"><td><b>{esc(r["label"])}</b></td><td><a href="./daily_markets.html#{ANCHOR}">Daily Markets</a></td>'
        f'<td class="num">{r["main"]["n"]}</td><td class="num">{pct(r["main"]["roi"])}</td><td class="num">{pct(r["control"]["roi"])}</td>'
        f'<td>{esc(r["read"])}</td></tr>' for r in recs)
    return ('<section id="weather-index"><h2>Weather</h2><p class="shell-kicker">Kalshi daily high and low ladders · two pre-registered lean lanes · '
            'paper · not in Production</p><div class="tbl"><table><tr><th>Lane</th><th>Page</th><th class="num">Settled</th>'
            '<th class="num">Return after fees</th><th class="num">Control</th><th>Read</th></tr>' + rows + '</table></div></section>')
