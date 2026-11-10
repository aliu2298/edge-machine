"""The Trading page's "Earnings & news calls (paper)" section (earnings_news.py). It never breaks the page.

One row per pre-registered family in the Econ Daily row design. Each prediction sits in its family's
fold with its pre-event timestamp, reason, source link and result. No dollar amounts and no ids in
the public copy: returns are in percent, and markets are named, not ticketed.
"""
import datetime as dt
import html as _h

import earnings_news as E

SECTION_ID = "earnings-news"
TITLE = "Earnings & news calls (paper)"
HEAD = ("Family", "Venue", "Settled", "Win", "Avg net", "z", "Status")

DEFS = {
    "kpi_drift": "Kalshi's quarterly KPI ladder for the stock (for example, Home Depot customer transactions) is read "
                 "from 30 to 6 hours before the report. The call is Up when the ladder median has risen by at least "
                 "a quarter of its width since a read taken 5 or more days earlier, and Down when it has fallen by "
                 "that much. It is held to the 16:00 ET close of the reaction session.",
    "runup": "Every Invest stock with a report coming up is called Up from the 16:00 ET close five sessions "
             "before the report to the last close before it. It is read against the market (SPY) over the same "
             "window.",
    "post_drift": "At 15:00 ET on the reaction session, the move since the last close before the report is "
                  "measured. If it is 2% or more either way, the call follows it for five sessions.",
    "news": "A structured call is logged only for MATERIAL company news published in the last 6 hours: "
            "guidance, M&A, a ruling, a major contract, an executive exit, a recall or outage, or a capital action. "
            "Each call has a direction, a horizon (1h, 1d or 5d), a confidence, a one-line reason and the source. "
            "It is priced from the moment it was logged.",
    "sentiment": "Once each trading day at 15:00 ET, Kalshi traders' Up share of 24h taker volume is read on "
                 "every stock with at least half a million of 24h volume. A share of 65% or more is called Up "
                 "(follow the crowd), and 35% or less is called Down, held one trading day. The fade is the "
                 "mirror image of these calls.",
}

CAVEAT = ("Big-cap news is priced within seconds to minutes. A public headline read later is NOT an edge, so a "
          "news call counts only from the moment it was logged, at the price at that moment. The likelier "
          "edges are scheduled events: earnings, and Kalshi KPI ladders that are less efficient than the stock. "
          "Another is Kalshi's thin perp books lagging the real stock.")


def esc(x):
    return _h.escape(str(x))


def _pct(v, sign=True):
    return "—" if v is None else (f"{v * 100:+.2f}%" if sign else f"{v * 100:.0f}%")


def _z(v):
    return "—" if v is None else f"{v:+.2f}"


def _et(s):
    if not s:
        return "—"
    t = E.parse(s).astimezone(E.ET)
    return t.strftime("%b %-d · %-I:%M %p ET").replace("AM", "am").replace("PM", "pm")


def _sig(text, tone):
    return f'<span class="sig {tone}">{esc(text)}</span>'


def _status(s):
    v = s["verdict"]
    tone = {"paying": "y", "no edge": "x", "review due": "w"}.get(v, "n")
    return _sig(v, tone)


def _cells(values):
    name, rest = values[0], values[1:]
    out = [f'<span class="sp-cell sp-c-name">{name}</span>']
    for i, (label, v) in enumerate(zip(HEAD[1:], rest)):
        cls = "sp-cell sp-c-market" if i == 0 else ("sp-cell sp-c-verdict" if label == "Status" else "sp-cell num")
        out.append(f'<span class="{cls}" data-l="{esc(label)}">{v}</span>')
    return "".join(out)


def _head_line():
    cells = "".join(
        f'<span class="sp-cell{" sp-c-name" if i == 0 else " sp-c-market" if i == 1 else " sp-c-verdict" if h == "Status" else " num"}">{esc(h)}</span>'
        for i, h in enumerate(HEAD))
    return f'<div class="sp-line sp-head-line" aria-hidden="true">{cells}</div>'


def _rule(key, name, cells, body):
    title = (f'<span class="sp-chev" aria-hidden="true">›</span><b class="sp-name" title="{esc(name)}">{esc(name)}</b>'
             '<span class="sr-only"> · Family details</span>')
    return (f'<details class="sp-rule" data-source="earnings_news_{esc(key)}"><summary class="sp-line">'
            f'{_cells([title, "Kalshi Invest"] + cells)}</summary>'
            f'<div class="sp-details-body">{body}</div></details>')


def _result(p):
    st = p.get("status")
    if not p.get("side"):
        return _sig("no call", "n")
    if st == "settled":
        return _sig(_pct(p["net"]), "y" if p["net"] > 0 else "x")
    if st in ("no_fill", "exit_no_fill"):
        return _sig("no fill", "n")
    if st == "open":
        return _sig("open", "w")
    return _sig("waiting", "n")


def _pred_table(ps):
    if not ps:
        return '<p class="sm mut">No predictions yet.</p>'
    rows = []
    for p in sorted(ps, key=lambda p: (p["logged_at"], p["sym"]), reverse=True)[:80]:
        call = {1: "Up", -1: "Down"}.get(p.get("side"), "—")
        if p.get("horizon"):
            call += f" · {p['horizon']}"
        if p.get("confidence"):
            call += f" · {p['confidence']:.0%}"
        reason = esc(p.get("reason", ""))
        if p.get("url"):
            reason += f' <a href="{esc(p["url"])}" rel="noopener nofollow" target="_blank">source</a>'
            if p.get("published"):
                reason += f' <span class="mut">({esc(_et(p["published"]))})</span>'
        rows.append(f'<tr><td>{esc(_et(p["logged_at"]))}</td><td><b>{esc(p["sym"])}</b></td><td>{esc(call)}</td>'
                    f'<td>{reason}</td><td>{esc(_et(p.get("entry_due")))} → {esc(_et(p.get("exit_due")))}</td>'
                    f'<td>{_result(p)}</td></tr>')
    return ('<div class="tbl"><table><thead><tr><th>Logged</th><th>Stock</th><th>Call</th><th>Reason</th>'
            '<th>Window</th><th>Result</th></tr></thead><tbody>' + "".join(rows) + '</tbody></table></div>')


def _family_row(key, s, preds):
    vs = s["vs"]
    zs = [v["z"] for v in vs.values() if v["z"] is not None]
    params = [("Logged", f'{s["logged"]} calls · {s["no_call"]} no call · {s["open"]} waiting or open · '
                         f'{s["no_fill"]} no fill'),
              ("v always-Up", f'{_pct(vs["up"]["mean"])} a call · z {_z(vs["up"]["z"])} · n {vs["up"]["n"]}'),
              ("v random side", f'{_pct(vs["random"]["mean"])} a call · z {_z(vs["random"]["z"])} · n {vs["random"]["n"]}'),
              ("v SPY Up", f'{_pct(vs["spy"]["mean"])} a call · z {_z(vs["spy"]["z"])} · n {vs["spy"]["n"]}')]
    if key == "sentiment":
        params.append(("Fade (other side)", f'{_pct(s.get("fade_avg_net"))} avg net'))
    dl = '<dl class="sp-params">' + "".join(f"<dt>{esc(k)}</dt><dd>{esc(v)}</dd>" for k, v in params) + "</dl>"
    body = f'<p class="sp-def">{esc(DEFS[key])}</p>{dl}{_pred_table(preds)}'
    cells = [str(s["settled"]), _pct(s["win"], sign=False), _pct(s["avg_net"]), _z(min(zs) if zs else None),
             _status(s)]
    return _rule(key, s["label"], cells, body)


def _calendar_fold(state):
    cal = state.get("calendar") or []
    rows = []
    for c in cal:
        when = {"pre-market": "Before open", "after-hours": "After close"}.get(c.get("time"), "Time not set")
        d = dt.date.fromisoformat(c["date"]).strftime("%a %b %-d")
        kpi = "; ".join(k["title"] for k in c.get("kpi") or []) or "—"
        rows.append(f'<tr><td>{esc(d)}</td><td>{esc(when)}</td><td><b>{esc(c["sym"])}</b></td>'
                    f'<td>{esc(kpi)}</td><td>{"Yes" if c.get("mentions") else "—"}</td></tr>')
    body = "".join(rows) or '<tr><td colspan="5" class="mut">No Invest stock reports in the next three weeks.</td></tr>'
    at = _et(state.get("calendar_at"))
    return (f'<details class="fold"><summary>Earnings calendar, next three weeks · {len(cal)} Invest stocks</summary>'
            f'<p class="sm mut">Dates from Nasdaq\'s public earnings calendar, refreshed {esc(at)}. They are checked '
            'against Kalshi\'s Insights tab. A KPI ladder is the quarterly Kalshi market that resolves at the report; '
            'a mention market is Kalshi\'s earnings-call word market.</p>'
            '<div class="tbl"><table><thead><tr><th>Date</th><th>When</th><th>Stock</th><th>Kalshi KPI ladder</th>'
            f'<th>Mention market</th></tr></thead><tbody>{body}</tbody></table></div></details>')


def _method_fold():
    return ('<details class="fold"><summary>How the record is kept</summary><div class="note sm">'
            f'The five families were <b>pre-registered on {esc(E.REGISTERED)}</b>, before the first prediction, in '
            'a committed file. The tests pin that file, so a family can never be edited after the fact; a change is a '
            'new family with a fresh record. A prediction counts only if it was committed <b>before</b> its entry. '
            'Its entry is the first honest fill after it was logged. <b>Honest fill</b>: an Up call buys at the ask '
            'and a Down call sells at the bid. The fill counts only when a public trade prints at or through that '
            'quote within 5 minutes. Otherwise it retries every 5 minutes for 30 minutes and is then recorded as no '
            'fill. The exit uses the same rule. At 1x, no leverage, minus the 0.12% taker fee on each side. Funding '
            'is not charged. A call logged while the perp is closed enters at the reopen. <b>Baselines</b>, over the '
            'identical windows: always-Up on the same stock, a random side fixed when the call was logged, and the '
            f'SPY perp Up. The z column is the weakest of the three paired z-scores. Review at {E.REVIEW_AT} settled, '
            f'decide at {E.DECIDE_AT}: <i>paying</i> needs z ≥ 2 against every baseline.</div></details>')


CT = E.ZoneInfo("America/Chicago")
STALE_H = 2                                     # the lane runs hourly: past 2 hours the line turns to a warning


def last_run_line(state, now=None):
    """'Last run <time CT>', in the warning colour when it is more than STALE_H hours old (2026-11-09: GitHub fired the
    hourly cron 3 times in a day and two entries came due unread)."""
    now = now or E.now_utc()
    at = state.get("last_run")
    if not at:
        return '<p class="sm en-last-run en-stale">Last run: not recorded yet.</p>'
    t = E.parse(at)
    loc = t.astimezone(CT)
    when = f"{loc:%b} {loc.day}, {loc.hour % 12 or 12}:{loc:%M} {'AM' if loc.hour < 12 else 'PM'} CT"
    age_h = (now - t).total_seconds() / 3600
    stale = age_h > STALE_H
    return (f'<p class="sm en-last-run{" en-stale" if stale else " mut"}">Last run {esc(when)}'
            + (f' · {age_h:.0f} hours ago, more than {STALE_H}: calls due since then are graded on the next run, '
               f'at their own due-time prices' if stale else "") + '.</p>')


def section_and_counts(state=None, now=None):
    """-> (html, families, settled, open)."""
    state = E.load() if state is None else state
    summ = E.summary(state)
    rows = [_family_row(k, summ[k], [p for p in state["predictions"] if p["family"] == k]) for k in E.FAMILIES]
    caveat = (f'<details class="fold"><summary>Read this first: a headline is not an edge</summary>'
              f'<p class="sm">{esc(CAVEAT)}</p></details>')
    inner = (last_run_line(state, now) + caveat + f'<div class="sp-rules-list" data-list="earnings-news">{_head_line()}{"".join(rows)}</div>'
             + _calendar_fold(state) + _method_fold())
    count = f"{len(E.FAMILIES)} families · paper · 1x"
    html = (f'<section id="{SECTION_ID}"><div class="sp-section-head"><h2>{esc(TITLE)}</h2>'
            f'<span class="sm mut">{esc(count)}</span></div>{inner}</section>')
    settled = sum(s["settled"] for s in summ.values())
    open_ = sum(s["open"] for s in summ.values())
    return html, len(E.FAMILIES), settled, open_


def safe_section():
    try:
        return section_and_counts()[0]
    except Exception as exc:                                    # noqa: BLE001
        return (f'<section id="{SECTION_ID}"><h2>{esc(TITLE)}</h2>'
                f'<p class="sm mut">Section unavailable ({type(exc).__name__}).</p></section>')
