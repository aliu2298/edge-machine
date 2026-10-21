"""The NBA page's Value lanes and Ladder tracker sections (nba_value.py, nba_ladder_track.py), paper only.

Two sections in the board's own style (nba_rules_build.py): the four value lanes with their
records, baselines and recent entries, and the ladder tracker's three tables, team climb, price
drift and calibration, with the calibration table (the board carries no SVG, meters or inline style). Never breaks the board: nba_pace_build
wraps the call.
"""
import html as _h
import os

import fmt
import nba_ladder_track as T
import nba_value as V


def esc(x):
    return _h.escape(str(x))


def _pct(v, sign=False):
    if v is None:
        return "—"
    return f"{v * 100:+.0f}%" if sign else f"{v * 100:.0f}%"


def _num(v, d=1, sign=True):
    if v is None:
        return "—"
    return f"{v:+.{d}f}" if sign else f"{v:.{d}f}"


def _picks(state, lane):
    return ((state.get("rules") or {}).get(lane) or {}).get("picks") or []


def _record(a):
    if not (a["n"] or a["n_price"]):
        return "no settled entries"
    roi = "—" if a["roi_fee"] is None else f"{a['roi_fee'] * 100:+.1f}%"
    return (f"{a['won']}/{a['n']} won · {a['won']} v {a['expected']:.1f} priced · model {a['model_exp']:.1f} · "
            f"z {a['z']:+.2f} ({a['nights']} night{'s' if a['nights'] != 1 else ''}) · ROI {roi} after fee")


def lanes_html(state):
    rows = []
    for lane in (V.TT_1H, V.TT_24H, V.Q1_1H, V.Q1_24H):
        a, b = V.stats(_picks(state, lane)), V.stats(_picks(state, V.BASE[lane]))
        roi = "—" if a["roi_fee"] is None else f"{a['roi_fee'] * 100:+.1f}%"
        broi = "—" if b["roi_fee"] is None else f"{b['roi_fee'] * 100:+.1f}%"
        n = a["n"] + a["n_price"]
        read = "verdict at 30" if n >= 30 else "review at 10+" if n >= 10 else "too early to read"
        rows.append(f'<tr data-source="{esc(lane)}"><td><b>{esc(V.NAMES[lane])}</b><br><span class="sm mut">{esc(lane)}</span></td>'
                    f'<td class="num">{n}</td><td class="num">{a["won"]}</td><td class="num">{a["expected"]:.1f}</td>'
                    f'<td class="num">{a["z"]:+.2f}</td><td class="num">{roi}</td><td class="num">{a["open"]}</td>'
                    f'<td class="num">{b["n"] + b["n_price"]} · {broi}</td><td>{esc(read)}</td></tr>')
    recent = sorted((p for lane in V.LANES for p in _picks(state, lane)),
                    key=lambda p: (p.get("start") or "", p.get("rule"), p.get("unit")), reverse=True)[:30]
    ent = []
    for p in recent:
        res = {"open": "open", "won": "won", "lost": "lost", "no_result": "no result"}.get(p["status"], p["status"])
        money = f" · ${p['profit']:+.2f}" if p.get("profit") is not None else ""
        ent.append(f'<tr><td>{esc(fmt.when(p["start"]))}</td><td>{esc(p["match"])}</td><td>{esc(p["rule"])}</td>'
                   f'<td>{esc(p["unit"])} {"over" if p["side"] == "yes" else "under"} {esc(p["line"])}</td>'
                   f'<td>{esc(p["side"].upper())}</td><td class="num">{p["price"] * 100:.0f}c</td>'
                   f'<td class="num">{p["p"]:.2f}</td><td class="num">{p["edge"]:+.3f}</td><td>{esc(res + money)}</td></tr>')
    body = "".join(ent) or ('<tr><td colspan="9" class="mut">No entries yet: each lane looks once per game, '
                            '26-18 hours or 90-60 minutes before tip, and enters only at an edge of 0.05 or more '
                            'after the fee.</td></tr>')
    defs = "".join(f'<p class="sm"><b>{esc(V.NAMES[k])}</b>: {esc(V.DEFINITION[k])}</p>' for k in (V.TT_1H, V.Q1_1H))
    last = state.get("last_run")
    return f"""<section id="value">
<div class="nba-section-head"><div><h2>Value lanes</h2><p class="shell-kicker">Model probability v the Kalshi price · team totals and 1st-quarter totals · paper at the ask, 7% fee · not in Production</p></div></div>
<div class="tbl"><table><thead><tr><th>Lane</th><th class="num">Settled</th><th class="num">Won</th><th class="num">Priced</th><th class="num">z (by night)</th><th class="num">ROI after fee</th><th class="num">Open</th><th class="num">Blind baseline</th><th>Read</th></tr></thead>
<tbody>{"".join(rows)}</tbody></table></div>
<details class="section-disclosure"><summary><b>Entries</b><span>latest 30</span></summary>
<div class="tbl"><table><thead><tr><th>Tip</th><th>Game</th><th>Lane</th><th>Rung</th><th>Side</th><th class="num">Price</th><th class="num">Model P</th><th class="num">Edge</th><th>Result</th></tr></thead>
<tbody>{body}</tbody></table></div></details>
<details class="section-disclosure"><summary><b>Rules and pre-registration</b><span>registered {esc(V.REGISTERED)}</span></summary>
{defs}<p class="sm mut">The 24h lanes are the same rule, looked at 26-18 hours before tip. {esc(V.PREREG)}</p></details>
<p class="sm mut">Last scan {esc(fmt.when(last) if last else "not yet")}{(" · " + esc(state["error"])) if state.get("error") else ""}.</p>
</section>"""


def _climb_rows(track):
    tab = T.climb_table(track.get("tracked") or {})
    moves = T.line_moves(track.get("tracked") or {})
    drift = T.drift_table(track.get("tracked") or {})
    rows = []
    for team in sorted(tab, key=lambda t: (-(tab[t]["off_avg"] or -99), t)):
        r = tab[team]
        d = drift.get(team) or {}
        mv = moves.get(team) or []
        rows.append(f'<tr><td><b>{esc(team)}</b></td><td class="num">{r["off_n"]}</td>'
                    f'<td class="num">{_num(r["off_avg"])}</td><td class="num">{_pct(r["off_beat"])}</td>'
                    f'<td class="num">{_num(r["def_avg"])}</td><td class="num">{_pct(r["def_beat"])}</td>'
                    f'<td class="num">{_num(d.get("avg") and d["avg"] * 100, 1)}{"c" if d.get("avg") is not None else ""}</td>'
                    f'<td class="num">{_num(sum(mv) / len(mv) if mv else None)}</td></tr>')
    return "".join(rows) or '<tr><td colspan="8" class="mut">No tracked game yet.</td></tr>'


CAL_HEAD = ('<tr><th>Model P</th><th class="num">Rungs</th><th class="num">Model P</th><th class="num">Hit</th>'
            '<th class="num">Avg ask</th><th class="num">Hit − ask</th></tr>')


def _cal_rows(cal):
    """One row per model-P bucket: the model's P, the hit rate and Kalshi's ask, each a number and a bar."""
    return "".join(f'<tr><td>{lo * 100:.0f}-{hi * 100:.0f}%</td><td class="num">{n}</td>'
                   f'<td class="num">{mp * 100:.0f}%</td>'
                   f'<td class="num">{hr * 100:.0f}%</td>'
                   f'<td class="num">{ask * 100:.0f}c</td>'
                   f'<td class="num">{(hr - ask) * 100:+.0f} pts</td></tr>'
                   for lo, hi, n, mp, hr, ask in cal) or '<tr><td colspan="6" class="mut">No settled two-sided rung yet.</td></tr>'


def _ask_line(cal):
    if not cal:
        return "no settled two-sided rung yet"
    return "; ".join(f"ask {lo * 100:.0f}-{hi * 100:.0f}c hit {hr * 100:.0f}% (n {n})" for lo, hi, n, _mp, hr, _a in cal)


def tracker_html(track):
    tr = track.get("tracked") or {}
    s = T.summary(track)
    drift = T.drift_table(tr)
    cal_tt, cal_q1 = T.calibration(tr, "tt"), T.calibration(tr, "q1")
    cal_tt_ask, cal_q1_ask = T.calibration(tr, "tt", by="ask"), T.calibration(tr, "q1", by="ask")

    def drift_line(key, label):
        d = drift.get(key)
        if not d:
            return f"{label}: no rung two-sided at both 24h and 1h yet"
        return (f"{label}: {d['n']} rungs, average ask move {d['avg'] * 100:+.1f}c from 24h to 1h; "
                f"{d['moved']} moved 2c or more, and {_pct(d['matched'])} of those moved the way the rung settled")

    last = track.get("last_run")
    return f"""<section id="ladder">
<div class="nba-section-head"><div><h2>Ladder tracker</h2><p class="shell-kicker">Every finished game's Kalshi team-total and 1Q ladders, 24h to 1h before tip · observation, no bets</p></div>
<span class="nba-count">{s["games"]} game{"s" if s["games"] != 1 else ""} · {s["rungs"]} rungs</span></div>
<h3>Calibration · team totals</h3>
<p class="sm mut">Every rung quoted two-sided 1 hour before tip: the model's P against how often it hit and Kalshi's average YES ask, by model-P bucket. Where the hit rate runs above the ask, Kalshi priced the over too low; where it tracks the model's P, the model holds.</p>
<div class="tbl"><table><thead>{CAL_HEAD}</thead>
<tbody>{_cal_rows(cal_tt)}</tbody></table></div>
<p class="sm mut">By Kalshi's ask instead: {esc(_ask_line(cal_tt_ask))}.</p>
<details class="section-disclosure"><summary><b>Calibration · 1st-quarter totals</b><span>{sum(r[2] for r in cal_q1)} rungs</span></summary>
<div class="tbl"><table><thead>{CAL_HEAD}</thead>
<tbody>{_cal_rows(cal_q1)}</tbody></table></div>
<p class="sm mut">By Kalshi's ask instead: {esc(_ask_line(cal_q1_ask))}.</p></details>
<h3>Team climb and drift</h3>
<p class="sm mut">Climb is points minus Kalshi's 50c line (the rung whose 1h mid is nearest 0.50); beat is how often the team cleared it. Opp. climb is the opponents' climb against their own line. Ask drift is the average YES ask change from 24h to 1h on that team's rungs with a 1h mid of 15-85c; line move is the 50c line at 1h minus at 24h, in points.</p>
<div class="tbl"><table><thead><tr><th>Team</th><th class="num">Games</th><th class="num">Climb</th><th class="num">Beat</th><th class="num">Opp. climb</th><th class="num">Opp. beat</th><th class="num">Ask drift</th><th class="num">Line move</th></tr></thead>
<tbody>{_climb_rows(track)}</tbody></table></div>
<p class="sm">{esc(drift_line("tt", "Team totals"))}.</p>
<p class="sm">{esc(drift_line("q1", "1st-quarter totals"))}.</p>
<p class="sm mut">Quotes are the close of Kalshi's hourly candle at or before each time; a one-sided book is recorded but not used here. {s["nights"]} game night{"s" if s["nights"] != 1 else ""} since {esc(T.SEASON_START.isoformat())}. Last run {esc(fmt.when(last) if last else "not yet")}{(" · " + esc(track["error"])) if track.get("error") else ""}.</p>
</section>"""


def section(state=None, track=None):
    if state is None:
        state = V.load() if os.path.exists(V.PATH) else V.empty()
    if track is None:
        track = T.load() if os.path.exists(T.PATH) else T.empty()
    return lanes_html(state) + "\n" + tracker_html(track)
