"""The Trading page's Kalshi Invest section (invest.py): one row per rule, details in folds. Paper · 1x · no orders."""
import datetime as dt
import html as _h
import json
import os

import invest as I
import trading_layout as L

RESEARCH = os.path.join(I.ROOT, "data", "invest_research.json")
REVIEW_AT = 10
WIN_WORD = {"1h": "in an hour", "day": "on the day (to 15:55 ET)", "gap": "at the open (overnight or weekend gap)"}
WHY = {"tp": "take-profit", "stop": "stop", "time": "time"}


def esc(x):
    return _h.escape(str(x))


def pct(x, d=2, sign=True):
    return "—" if x is None else (f"{x * 100:+.{d}f}%" if sign else f"{x * 100:.{d}f}%")


def load_research(path=RESEARCH):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _cell_line(c):
    """A research cell in one line: n, win, average net, margin v the random baseline."""
    r = c["res"]
    return (f'{r["n"]} events · {pct(r["win"], 0, False)} won · {pct(r["net"])} a trade after costs · '
            f'{pct(r["margin"])} v random entry (t {r["t_margin"]:+.2f})' if r.get("t_margin") is not None else
            f'{r["n"]} events')


def _halves(c):
    out = []
    for k, lab in (("h1", "2023–Jun 2024"), ("h2", "Jul 2024–2025"), ("ho", "2026 holdout")):
        p = c.get(k) or {}
        out.append(f'{lab}: {p.get("n", 0)} · {pct(p.get("net"))} net · {pct(p.get("margin"))} v baseline')
    return "<br>".join(esc(x) for x in out)


def _definition(k):
    R = I.RULES[k]
    side = "Up" if I.side_of(k) > 0 else "Down"
    mv = "drops" if R["dir"] == "drop" else "jumps"
    return (f'When a Kalshi Invest stock\'s reference price {mv} {R["size"] * 100:g}% or more {WIN_WORD[R["win"]]}, '
            f'take {side} at 1x on the next minute; take-profit {R["tp"] * 100:g}%, stop {R["sl"] * 100:g}%, '
            f'out after {R["hold"]} of regular-hours trading.')


def _events_table(evs):
    if not evs:
        return '<p class="sm mut">No events yet.</p>'
    rows = []
    for e in sorted(evs, key=lambda e: e["signal_ts"], reverse=True)[:40]:
        st = {"pending": "waiting for a fill", "open": "open", "no_fill": "no fill",
              "settled": f'settled · {WHY.get(e.get("exit_why"), "")}'}.get(e["status"], e["status"])
        rows.append(f'<tr><td>{esc(e["day"])}</td><td>{esc(e["sym"])}</td><td class="num">{pct(e["move"], 1)}</td>'
                    f'<td>{esc(st)}</td><td class="num">{pct(e.get("gross"))}</td><td class="num">{pct(e.get("net"))}</td>'
                    f'<td class="num">{"—" if e.get("spread_in") is None else esc(e["spread_in"])}</td></tr>')
    return ('<div class="tbl"><table><thead><tr><th>Day</th><th>Stock</th><th class="num">Move</th><th>Status</th>'
            '<th class="num">Gross</th><th class="num">Net</th><th class="num">Spread in, bp</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>')


def _rule_row(k, s, summ, research):
    R = I.RULES[k]
    sm = summ[k]
    cell = (research.get("rules") or {}).get(k)
    body = f'<p class="sp-def">{esc(_definition(k))}</p>'
    pairs = [("Status", "cleared the pre-registered research bar · paper" if R.get("cleared") else
              "did not clear the research bar · forward paper observation only"),
             ("Venue", "Kalshi Invest perp, 1x, no leverage; never places an order"),
             ("Fills", "entry a taker at the ask (Up) or bid (Down), counted only with a print at or through it; "
                       "take-profit only on a print through the level; stop and time exits at the bid / ask; "
                       "0.12% taker, 0.02% maker")]
    if cell:
        pairs.append(("Research", esc(_cell_line(cell))))
        pairs.append(("By period", _halves(cell)))
    pairs.append(("Live", f'{sm["n"]} settled · {sm["open"]} open · {sm["pending"]} waiting · {sm["no_fill"]} no fill'))
    body += L.params(pairs)
    body += L.fold("Events", _events_table([e for e in s["events"] if e["rule"] == k]))
    win = "—" if sm["win"] is None else f'{sm["win"] * 100:.0f}%'
    t = "—" if sm["t"] is None else f'{sm["t"]:+.2f}'
    if k not in I.ACTIVE_RULES:
        status = L.sig("retired Nov 11")                         # 2026-11-11 (Olu): all four retired, records kept
    elif sm["n"] >= REVIEW_AT:
        status = L.sig("review due", "w")
    else:
        status = L.sig(f'{sm["n"]}/{REVIEW_AT} to review' + ("" if R.get("cleared") else " · observation"))
    name = I.LABELS[k]
    venue = f'{R["win"]} {R["size"] * 100:g}%'
    return L.rule(f"invest_{k}", name, venue, str(sm["n"]), win, pct(sm["net"]), t, status, body,
                  muted=not R.get("cleared"))


def _research_fold(research):
    cells = research.get("top") or []
    if not cells:
        return ""
    rows = []
    for c in cells:
        r = c["res"]
        both = "yes" if c.get("both_halves") else "no"
        hold = c.get("hold_ok")
        rows.append(f'<tr><td>{esc(c["win"])} {c["size"] * 100:g}% {esc(c["dir"])}</td><td>{esc(c["act"])}</td>'
                    f'<td>TP {c["tp"] * 100:g}% · stop {c["sl"] * 100:g}% · {esc(c["hold"])}</td>'
                    f'<td class="num">{r["n"]}</td><td class="num">{pct(r["win"], 0, False)}</td>'
                    f'<td class="num">{pct(r["net"])}</td><td class="num">{pct(r["margin"])}'
                    f'{"" if r.get("t_margin") is None else f" · t {r["t_margin"]:+.2f}"}</td>'
                    f'<td>{both}</td><td>{"—" if hold is None else ("yes" if hold else "no")} · {pct((c.get("ho") or {}).get("net"))}</td>'
                    f'<td>{esc(c.get("verdict", ""))}</td></tr>')
    head = ('<div class="tbl"><table><thead><tr><th>Event</th><th>Direction</th><th>Exit</th><th class="num">n</th>'
            '<th class="num">Win</th><th class="num">Avg net</th><th class="num">v baseline</th><th>Both halves</th>'
            '<th>Holdout · net</th><th>Verdict</th></tr></thead><tbody>')
    note = (f'<p class="sm mut">{esc(research.get("note", ""))}</p>')
    return L.fold(f'Research grid · {research.get("n_cells", 0)} cells tested · {esc(research.get("cleared_line", ""))}',
                  note + head + "".join(rows) + "</tbody></table></div>", cls="fold trade-method")


def _venue_fold(s):
    fl = s.get("flags") or []
    rows = []
    for f in sorted(fl, key=lambda f: f["ts"], reverse=True)[:30]:
        when = dt.datetime.fromtimestamp(f["ts"], I.ET)
        rows.append(f'<tr><td>{esc(f"{when:%b} {when.day} {when:%H:%M} ET")}</td><td>{esc(f["sym"])}</td>'
                    f'<td class="num">{pct(f["gap"])}</td>'
                    + "".join(f'<td class="num">{pct(f.get(f"gap_{m}m"))}</td>' for m in I.GAP_LOOK)
                    + f'<td>{"regular hours" if f.get("rth") else "off hours"}</td></tr>')
    done = [f for f in fl if f.get("gap_60m") is not None]
    closed = sum(abs(f["gap_60m"]) < abs(f["gap"]) / 2 for f in done)
    line = (f'{len(fl)} flagged · {len(done)} read at 60 minutes · {closed} of them had closed half the gap'
            if fl else "no Kalshi-only gap of 1% or more yet")
    table = ('<div class="tbl"><table><thead><tr><th>When</th><th>Stock</th><th class="num">Gap</th>'
             + "".join(f'<th class="num">+{m}m</th>' for m in I.GAP_LOOK)
             + f'<th>Session</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>') if rows else ""
    return L.fold(f"Kalshi-only gaps · {esc(line)}",
                  '<p class="sm mut">A snapshot where the perp\'s mid sits 1% or more from the stock\'s reference '
                  'price while the market is open; one per stock an hour. The gap is re-read 5, 15 and 60 minutes '
                  'later: the snap-back. Forward only, observation.</p>' + table, cls="fold trade-method")


def _method_fold(s):
    c = s.get("collector") or {}
    last = c.get("last_ts")
    when = "not running yet" if not last else dt.datetime.fromtimestamp(last, I.ET).strftime("%b %d %H:%M ET")
    return L.fold("How the record is kept", f"""<div class="note sm">Paper only, at 1x: no order is ever placed.
A collector reads Kalshi's public perps market data once a minute (bid, ask, last and the stock's reference price for
every Invest stock and index); the last snapshot: {esc(when)}, {c.get("markets", 0)} markets. Events are read from the
reference price, the stock's own move. Fills are graded on Kalshi's own quotes and prints: the entry counts only when a
trade printed at or through the quote taken, a take-profit only when a print went through its level, and stops and
time exits pay the spread. Kalshi's fee: 0.12% of notional a taker side, 0.02% maker. Funding is 0% on stocks today
and is not charged. Reviewed at {REVIEW_AT}+ settled events per rule. Last run {esc(s.get("last_run") or "not yet")}.</div>""",
                  cls="fold trade-method")


def _rb_events(evs):
    if not evs:
        return '<p class="sm mut">No events yet.</p>'
    st_word = {"pending": "waiting for a fill", "open": "open", "no_fill": "no fill"}
    rows = []
    for e in sorted(evs, key=lambda e: e["signal_ts"], reverse=True)[:40]:
        when = dt.datetime.fromtimestamp(e["signal_ts"], I.ET)
        st = st_word.get(e["status"]) or "settled · " + {"target": "target hit", "stop": "stopped", "time": "time"}.get(
            e.get("exit_why"), "")
        rows.append(f'<tr><td>{esc(f"{when:%b} {when.day} {when:%H:%M} ET")}{" · in-sample" if e.get("backfill") else ""}</td>'
                    f'<td>{esc(e["sym"])}</td><td class="num">{e["level_stock"]:.2f}</td><td class="num">{e["strength"]}</td>'
                    f'<td>{esc(st)}</td><td class="num">{pct(e.get("net"))}</td></tr>')
    return ('<div class="tbl"><table><thead><tr><th>Signal</th><th>Stock</th><th class="num">Support</th>'
            '<th class="num">Methods agreeing</th><th>Status</th><th class="num">Net</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>')


def _rb_row(k, s_rb):
    import rebound as RB
    Ln = RB.LANES[k]
    live = RB.summary(s_rb)[k]
    allx = RB.summary(s_rb, include_backfill=True)[k]
    slide = "10% or more below its 5-day high" if Ln["slide"] == "S5D" else "5% or more below its 24-hour high"
    sup = "a strong support level (two or more ways of finding support agree on it, or it held before)" if Ln["strong"] \
        else "any support level"
    defin = (f'When a Kalshi Invest stock is {slide}, and its price comes within 0.75% of {sup} (a prior low, the prior '
             f'day or week\'s low, the 50- or 200-day average, a gap fill or a round number), wait for selling to slow '
             f'(the 15-minute RSI below 30, then turning up), then go Up at 1x. Stop 1% under the support; target halfway '
             f'back to the slide\'s high; out after {"5 days" if Ln["slide"] == "S5D" else "1 day"}.')
    bf = s_rb and [e for e in s_rb["events"] if e["lane"] == k and e.get("backfill") and e["status"] == "settled"]
    pairs = [("Status", "observation only: it did not clear the research bar (see Research)"),
             ("Research", esc(Ln["research"])),
             ("In-sample",
              f'Nov 6 on, before the fresh record: {len(bf)} settled · '
              f'{pct(sum(e["net"] for e in bf) / len(bf)) if bf else "—"} average net'),
             ("Live", f'{live["n"]} settled · {live["open"]} open · {live["pending"]} waiting · {live["no_fill"]} no fill'),
             ("Fills", "entry at the ask, counted only with a print at or through it; target only on a print through it; "
                       "stop and time exits at the bid; 0.12% taker, 0.02% maker")]
    body = f'<p class="sp-def">{esc(defin)}</p>' + L.params(pairs) + L.fold("Events", _rb_events(
        [e for e in s_rb["events"] if e["lane"] == k]))
    win = "—" if live["win"] is None else f'{live["win"] * 100:.0f}%'
    t = "—" if live["t"] is None else f'{live["t"]:+.2f}'
    status = L.sig(f'observation · {live["n"]}/{RB.REVIEW_AT} to review' if live["n"] < RB.REVIEW_AT else
                   ("observation · review due" if live["n"] < RB.DECIDE_AT else "observation · decide"), "n")
    return L.rule(f"invest_{k}", Ln["label"], "Kalshi Invest", str(live["n"]), win, pct(live["net"]), t, status, body,
                  muted=True)


def _rb_research_fold():
    return L.fold("Rebound after a slide · how it was tested", '<p class="sm">Pre-registered before any result was read: '
                  '56 versions (two slide sizes, seven ways to confirm the support is holding, all or strong supports, '
                  'two targets) on 2023 to 2026 one-minute stock prices for the 58 Invest stocks, against the same slides '
                  'bought with no support check, and against random entries. A version had to beat the no-support '
                  'baseline in both halves of the history and in the last three months, after costs. None did: the best '
                  'matched the baseline in research and lost in the last three months. The two rows above are the best '
                  'of each slide length, run as observation only so they can be watched. The research read regular '
                  'hours only; these lanes read Kalshi\'s price in every open minute, overnight included.</p>',
                  cls="fold trade-method")


RETIRED_NOTE = ("The four big-move rules (fade or follow a drop or a jump) were retired on Nov 11: they only saw a "
                "big move inside one hour or one day, in regular hours, so a slide over several hours or days, or one "
                "overnight, never triggered them. Their records are in Retired at the bottom of this page. The "
                "one-minute price collector keeps running for the next rule.")


def section_and_counts(state=None, research=None, rebound_state=None):
    """The live Invest section: the running rules (none since 2026-11-11), the collector's gap log and method.
    -> (html, running rules, settled, open)."""
    s = I.load() if state is None else state
    summ = I.summary(s)
    live = [k for k in I.RULES if k in I.ACTIVE_RULES]
    rows = [_rule_row(k, s, summ, load_research() if research is None else research) for k in live]
    try:                                                        # Rebound after a slide (2026-11-11), observation only
        import rebound as RB
        s_rb = RB.load() if rebound_state is None else rebound_state
        rows += [_rb_row(k, s_rb) for k in RB.LANES]
        rb = RB.summary(s_rb)
        n_rb, settled_rb, open_rb = len(RB.LANES), sum(v["n"] for v in rb.values()), sum(v["open"] for v in rb.values())
    except Exception:                                           # noqa: BLE001  (never breaks the section)
        n_rb = settled_rb = open_rb = 0
    body = ((L.rules_list(rows, key="invest") if rows else "") + (_rb_research_fold() if n_rb else "")
            + f'<p class="sm invest-retired-note">{esc(RETIRED_NOTE)}</p>' + _venue_fold(s) + _method_fold(s))
    html = L.section("invest", "Kalshi Invest (paper)",
                     f"{len(live) + n_rb} lanes running ({n_rb} observation only) · paper · 1x", body)
    return (html, len(live) + n_rb, sum(summ[k]["n"] for k in live) + settled_rb,
            sum(summ[k]["open"] for k in live) + open_rb)


def retired_html(state=None, research=None):
    """The four retired big-move rules with their final records, for the page's Retired block. Never breaks it."""
    try:
        s = I.load() if state is None else state
        research = load_research() if research is None else research
        summ = I.summary(s)
        gone = [k for k in I.RULES if k not in I.ACTIVE_RULES]
        if not gone:
            return ""
        rows = [_rule_row(k, s, summ, research) for k in gone]
        n = sum(summ[k]["n"] for k in gone)
        return (f'<h3>Kalshi Invest big-move rules, retired Nov 11</h3>'
                f'<p class="sm mut">{len(gone)} rules · {n} settled trade{"s" * (n != 1)} · records kept, no new events.</p>'
                + L.rules_list(rows, key="invest-retired") + _research_fold(research))
    except Exception:                                           # noqa: BLE001
        return ""
