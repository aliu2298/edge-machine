"""The NBA page's "NBA Spotter (Sandbox)" section (nba_spotter.py), paper only, percentages and cents. Never breaks the board: nba_pace_build wraps the call."""
import datetime as dt
import html as _h
import os

import fmt
import nba_spotter as S


def esc(x):
    return _h.escape(str(x))


def _pct(v, sign=False, d=0):
    return "—" if v is None else (f"{v * 100:+.{d}f}%" if sign else f"{v * 100:.{d}f}%")


def _pts(v):
    """Dollars a contract as points (cents) a contract."""
    return "—" if v is None else f"{v * 100:+.1f}"


def _t(v):
    return "—" if v is None else f"{v:+.2f}"


def _picks(state, lane):
    return ((state.get("rules") or {}).get(lane) or {}).get("picks") or []


def records_html(state):
    rows = []
    for board in S.BOARDS:
        a, b = S.stats(_picks(state, board)), S.stats(_picks(state, S.BLIND[board]))
        ex, tx, k = S.versus_blind(state, board)
        hit = "—" if not a["n"] else _pct(a["won"] / a["n"])
        sold = "" if board != "spotter_spike" or not a["n"] else f" · sold at 2x {a['sold']}/{a['n']}"
        rows.append(
            f'<tr data-source="{esc(board)}"><td><b>{esc(S.NAMES[board])}</b><br><span class="sm mut">{esc(board)}</span></td>'
            f'<td class="num">{a["n"]}</td><td class="num">{hit}</td><td class="num">{"—" if a["price"] is None else f"{a['price'] * 100:.0f}c"}</td>'
            f'<td class="num">{_pct(a["ret"], True, 1)}</td><td class="num">{_t(a["t"])} ({a["nights"]} night{"s" if a["nights"] != 1 else ""})</td>'
            f'<td class="num">{b["n"]} · {_pct(b["ret"], True, 1)}</td><td class="num">{_pts(ex)} pts{f" (t {_t(tx)}, {k} nights)" if k else ""}</td>'
            f'<td class="num">{a["open"]}</td><td>{esc(S.read_text(state, board))}{esc(sold)}</td></tr>')
    return ('<div class="tbl"><table><thead><tr><th>Board</th><th class="num">Graded</th><th class="num">Hit</th><th class="num">Avg price</th>'
            '<th class="num">Return after fees</th><th class="num">t (by night)</th><th class="num">Blind control</th><th class="num">Over blind</th>'
            f'<th class="num">Open</th><th>Read</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>')


def _row(p, now):
    model = "—" if p.get("p") is None else _pct(p["p"])
    tip = fmt.when(p["start"])
    res = {"open": "open", "won": "won", "lost": "lost"}.get(p["status"], p["status"])
    if p.get("ret") is not None:
        res += f" · {_pct(p['ret'], True)}" + (" (sold at 2x)" if p.get("sold") else "")
    why = p.get("why") or ""
    if p.get("outs"):
        why += f" ({', '.join(p['outs'])} out)"
    tgt = f" → sell {p['target'] * 100:.0f}c" if p.get("target") else ""
    no = "NO on " if p.get("side") == "no" else ""
    return (f'<tr><td>{esc(tip)}</td><td>{esc(p["game"])}</td><td>{no}<b>{esc(p["player"])}</b> {esc(p["rung"])}+ {esc(p["unit"])}</td>'
            f'<td class="num">{p["price"] * 100:.0f}c{esc(tgt)}</td><td class="num">{model}</td><td>{esc(why)}</td>'
            f'<td>{esc(S.NAMES[p["rule"]])}</td><td>{esc(res)}</td></tr>')


HEAD = ('<div class="tbl"><table><thead><tr><th>Tip</th><th>Game</th><th>Contract</th><th class="num">Price</th><th class="num">Model chance</th>'
        '<th>Reason</th><th>Board</th><th>Result</th></tr></thead><tbody>{}</tbody></table></div>')


def picks_html(state, now):
    allp = [p for lane in S.BOARDS for p in _picks(state, lane)]
    tonight = [p for p in allp if p["status"] == "open"]
    tonight.sort(key=lambda p: (p["start"], p["rule"], -(p.get("edge") or 0)))
    todo = "".join(_row(p, now) for p in tonight) or ('<tr><td colspan="8" class="mut">No open picks. Each game is read once, 80 to 35 minutes before its tip; '
                                                       'the hold board needs a model chance 5+ points above the ask.</td></tr>')
    done = sorted((p for lane in S.BOARDS for p in _picks(state, lane) if p["status"] != "open"), key=lambda p: (p["start"], p["rule"]), reverse=True)[:30]
    body = "".join(_row(p, now) for p in done) or '<tr><td colspan="8" class="mut">No graded picks yet.</td></tr>'
    return (f'<h3 class="sm">Open picks</h3>{HEAD.format(todo)}'
            f'<details class="section-disclosure"><summary><b>Graded picks</b><span>latest 30</span></summary>{HEAD.format(body)}</details>')


def summary_line(state):
    """One line for the collapsed section: each board's return after fees against its blind control, and how far the 200-pick read is."""
    parts = []
    for board in S.BOARDS:
        a, b = S.stats(_picks(state, board)), S.stats(_picks(state, S.BLIND[board]))
        name = S.NAMES[board].replace("NBA Spotter, ", "").split(" (")[0]
        parts.append(f"{name} {_pct(a['ret'], True, 1)} v blind {_pct(b['ret'], True, 1)} ({a['n']} graded)")
    return " · ".join(parts)


def section(state=None, now=None):
    state = state if state is not None else S.load()
    now = now or dt.datetime.now(dt.timezone.utc)
    looks = state.get("looks") or {}
    last = state.get("last_run")
    err = f" · {esc(state['error'])}" if state.get("error") else ""
    return f"""<section id="spotter" class="sp-section">
<details class="fold nba-spotter" id="spotter-fold"><summary><h3>NBA Spotter (Sandbox)</h3><span class="sm mut">· paper · {len(looks)} read · {esc(summary_line(state))} · read once at {S.READ_AT} graded picks a board</span></summary>
<p class="sm">Paper only, on Kalshi player props. A frozen model scores every priced player rung about an hour before tip and enters three boards a night, up to 8 each. Hold: the model's chance is 5+ points above the ask, held to the end. Spike: rungs at 49c or less ranked by the spike model, with a paper sell at 2x. Fade (from Nov 19): buy NO where the model's chance is 5+ points below the YES ask, at the real NO ask of 90c or less, held to the end. Each board has a blind control: a random rung in the same game at about the same price with the same exit (the fade's on the NO side).</p>
{records_html(state)}
{picks_html(state, now)}
<details class="section-disclosure"><summary><b>Rules and pre-registration</b><span>registered {esc(S.REGISTERED)}</span></summary>
<p class="sm">Model: fitted once on Oct 20 to Nov 6 2026 and frozen, no refit. Inputs known at entry only: the ask, the injury report's Out list, box scores to date, last season, the spread. Rungs 5c to 60c, spread 5c or less, one rung a player-stat a night, 4 a game at most so the first game does not take every slot. The sell fills only on a later trade print strictly above the target, 25 seconds after the entry at the earliest; fees on both legs; unsold means held to the end.</p>
<p class="sm">Read once, at {S.READ_AT} graded picks a board. Keep only if the return is above zero after fees, t is 2 or better by night, and the board beats its blind control by 2 or more points a contract. Offline, on Nov 7 to 16, neither board reached t 2 (hold +3% with t 0.7, spike +9% with t 0.7); this is the forward test.</p></details>
<p class="sm mut">Last read {esc(fmt.when(last) if last else "not yet")}{err}.</p>
</details>
</section>"""
