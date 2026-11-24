"""The NBA page's "Club 90 · quarter & half lines" block (nba_qlines.py), paper only, percentages and cents. Six collapsed sections (1Q 2Q 3Q 4Q 1H 2H),
each with the live qualifying-teams table, the lane's record beside its blind control, recent picks and a collapsed entries table. Never breaks the page:
nba_pace_build wraps the call."""
import datetime as dt
import html as _h
import os

import fmt
import nba_qlines as Q
import nba_spotter as S

E2K = {v: k for k, v in S.K2E.items()}        # ESPN's NY, SA, GS, NO, UTAH, WSH -> Kalshi's NYK, SAS, GSW, NOP, UTA, WAS, as the rest of the site writes them
NEAR = 0.85                                    # the open table lists teams at this rate or better (qualifying ones included)


def code(t):
    return E2K.get(t, t)


def game_name(text):
    return " @ ".join(code(x) for x in str(text).split(" @ "))


def esc(x):
    return _h.escape(str(x))


def _pct(v, sign=False, d=1):
    return "—" if v is None else (f"{v * 100:+.{d}f}%".replace("-", "−") if sign else f"{v * 100:.{d}f}%")


def _picks(state, ln):
    return ((state.get("rules") or {}).get(ln) or {}).get("picks") or []


def _won_lost(s):
    return f"{s['won']}-{s['n'] - s['won']}"


def record_row(state, sec, d):
    a, b = Q.stats(_picks(state, Q.lane(sec, d))), Q.stats(_picks(state, Q.lane(sec, d, True)))
    return (f'<tr data-source="{esc(Q.lane(sec, d))}"><td><b>{esc(d.capitalize())} {Q.LINES[sec][d]}</b></td>'
            f'<td class="num">{_won_lost(a)}</td><td class="num">{_pct(a["ret"], True)}</td>'
            f'<td class="num">{_won_lost(b)} · {_pct(b["ret"], True)}</td><td class="num">{a["open"]}</td><td>{esc(Q.status_text(a["n"]))}</td></tr>')


def record_table(state, sec):
    return ('<div class="tbl"><table class="qline-record"><tr><th>Lane</th><th class="num">Won-lost</th><th class="num">Return after fees</th>'
            '<th class="num">Blind control</th><th class="num">Open</th><th>Read</th></tr>'
            + "".join(record_row(state, sec, d) for d in Q.DIRS) + "</table></div>")


def teams_table(games, sec, d, full=False):
    rows = Q.team_rows(games, sec, d)
    items = sorted(rows.items(), key=lambda kv: (-(kv[1]["rate"] or 0), -kv[1]["n"], kv[0]))
    if not full:
        items = [kv for kv in items if kv[1]["qualifies"] or ((kv[1]["rate"] or 0) >= NEAR - Q.EPS and kv[1]["n"] >= Q.MIN_GAMES // 2)]
    body = "".join(f'<tr data-team="{esc(t)}"><td><b>{esc(code(t))}</b></td><td class="num">{v["hits"]}/{v["n"]}</td><td class="num">{_pct(v["rate"], d=0)}</td>'
                   f'<td>{"yes" if v["qualifies"] else "no"}</td><td>{esc(v["since"] or "—")}</td></tr>' for t, v in items)
    if not body:
        body = '<tr><td colspan="5" class="mut">No team is at 85% yet.</td></tr>'
    return ('<div class="tbl"><table class="qline-teams"><tr><th>Team</th><th class="num">Hits/games</th><th class="num">Rate</th><th>Qualifies</th><th>Qualified since</th></tr>'
            f'{body}</table></div>')


def _row(p):
    res = {"open": "open", "won": "won", "lost": "lost", "void": "void"}.get(p["status"], p["status"])
    if p.get("ret") is not None:
        res += f" · {_pct(p['ret'], True)}"
    who = "/".join(code(t) for t in p.get("qualifying") or []) or "blind"
    off = "" if not p.get("offset") else f" (line {p['line']}, rung {p['rung']})"
    mark = ' <span class="sm mut">· backfilled</span>' if p.get("backfilled") else ""
    return (f'<tr><td>{esc(fmt.when(p["start"]))}</td><td>{esc(game_name(p["game"]))}</td><td>{esc(p["direction"])} {p["rung"]}{esc(off)}{mark}</td>'
            f'<td class="num">{p["price"] * 100:.0f}c</td><td>{esc(who)}</td><td>{esc(res)}</td></tr>')


HEAD = ('<div class="tbl"><table class="qline-picks"><tr><th>Tip</th><th>Game</th><th>Bet</th><th class="num">Price</th><th>Qualifying</th><th>Result</th></tr>'
        '{}</table></div>')


def picks_html(state, sec):
    lane_picks = [p for d in Q.DIRS for p in _picks(state, Q.lane(sec, d))]
    lane_picks.sort(key=lambda p: (p["start"], p["id"]), reverse=True)
    recent = "".join(_row(p) for p in lane_picks[:5]) or '<tr><td colspan="6" class="mut">No entries yet. A game enters when a team clears the bar before its tip.</td></tr>'
    blind = [p for d in Q.DIRS for p in _picks(state, Q.lane(sec, d, True))]
    blind.sort(key=lambda p: (p["start"], p["id"]), reverse=True)
    allrows = "".join(_row(p) for p in lane_picks) or '<tr><td colspan="6" class="mut">No entries yet.</td></tr>'
    blindrows = "".join(_row(p) for p in blind[:60]) or '<tr><td colspan="6" class="mut">No control rows yet.</td></tr>'
    return (f'<h4 class="sm">Recent picks</h4>{HEAD.format(recent)}'
            f'<details class="section-disclosure"><summary><b>All entries</b><span>{len(lane_picks)} in this section</span></summary>{HEAD.format(allrows)}</details>'
            f'<details class="section-disclosure"><summary><b>Blind control rows</b><span>latest 60 of {len(blind)}</span></summary>{HEAD.format(blindrows)}</details>')


def backfill_counts(state, sec=None):
    """(backfilled, all) lane entries (never the controls), for one section or every one."""
    rows = [p for s in ([sec] if sec else Q.SECTIONS) for d in Q.DIRS for p in _picks(state, Q.lane(s, d))]
    return sum(1 for p in rows if p.get("backfilled")), len(rows)


def backfill_note(state, sec=None):
    nb, n = backfill_counts(state, sec)
    if not nb:
        return ""
    return (f'<p class="sm mut">{nb} of {n} entries backfilled: the first slate ({esc(Q.BACKFILL_DAY)}) took no live read, so it was recorded afterwards from 1-minute quotes '
            f'at 30 minutes before each tip, through the same rules. The other {n - nb} were live reads. Backfilled rows carry a marker.</p>')


def summary_line(state, sec):
    parts = []
    for d in Q.DIRS:
        a, b = Q.stats(_picks(state, Q.lane(sec, d))), Q.stats(_picks(state, Q.lane(sec, d, True)))
        parts.append(f"{d} {Q.LINES[sec][d]}: {_won_lost(a)} {_pct(a['ret'], True)} v blind {_pct(b['ret'], True)}")
    return " · ".join(parts)


def qualifying_now(games, sec):
    return {d: sorted(t for t, v in Q.team_rows(games, sec, d).items() if v["qualifies"]) for d in Q.DIRS}


def section_html(state, games, sec):
    q = qualifying_now(games, sec)
    head = " · ".join(f"{d}: {', '.join(code(t) for t in q[d]) or 'none'}" for d in Q.DIRS)
    body = ""
    for d in Q.DIRS:
        body += (f'<h4 class="sm">Teams at {NEAR * 100:.0f}%+ · {esc(d)} {Q.LINES[sec][d]} · qualify at {Q.THRESHOLD * 100:.0f}% over {Q.MIN_GAMES}+ games</h4>{teams_table(games, sec, d)}'
                 f'<details class="section-disclosure"><summary><b>All teams · {esc(d)} {Q.LINES[sec][d]}</b><span>every team, {len(Q.team_rows(games, sec, d))} in all</span></summary>{teams_table(games, sec, d, True)}</details>')
    return (f'<details class="fold nba-qline" id="qlines-{esc(sec.lower())}"><summary><h3>Club 90 · {esc(sec)}</h3>'
            f'<span class="sm mut">{esc(summary_line(state, sec))}</span></summary>'
            f'<p class="sm">Qualifying now (games before tonight) · {esc(head)}</p>'
            f'{backfill_note(state, sec)}{record_table(state, sec)}{picks_html(state, sec)}{body}</details>')


def section(state=None, games_doc=None, now=None):
    state = state if state is not None else Q.load()
    games = (games_doc if games_doc is not None else Q.load_games())["games"]
    last = state.get("last_run")
    err = f" · {esc(state['error'])}" if state.get("error") else ""
    sections = "".join(section_html(state, games, sec) for sec in Q.SECTIONS)
    nb, entries = backfill_counts(state)
    backfilled = f" ({nb} backfilled)" if nb else ""
    entries = sum(len(_picks(state, Q.lane(sec, d))) for sec in Q.SECTIONS for d in Q.DIRS)
    through = max((g["day"] for g in games), default=None) or "not yet"
    return f"""<section id="qlines" class="sp-section">
<div class="sp-section-head"><h2>Club 90 · quarter &amp; half lines</h2><span class="sm mut">paper · {entries} entr{"y" if entries == 1 else "ies"}{backfilled} · tracker through {esc(through)}</span></div>
<p class="sm">Paper only, on Kalshi's game-total lines for each quarter and half. A team qualifies on a line when its season hit rate on games before tonight is {Q.THRESHOLD * 100:.0f}% or better over {Q.MIN_GAMES}+ games; a game with a qualifying team is one entry. Over: the YES ask. Under: the NO price. The ask is read 15 to 40 minutes before the tip (spread 5c or less), held to settlement. If the line itself is not listed, the nearest rung 1 to 3 points harder is used. Each lane has a blind control: the same line bet in every game that night. Read at {Q.REVIEW_AT[0]} settled, then {Q.REVIEW_AT[1]}, against the control.</p>
{backfill_note(state)}{sections}
<p class="sm mut">Last read {esc(fmt.when(last) if last else "not yet")}{err}. Registered {esc(Q.REGISTERED)}.</p>
</section>"""


def index_html(state=None):
    """The Sandbox page's index of the six sections: one row each, linking to its fold on the NBA page."""
    state = state if state is not None else Q.load()
    body = ""
    for sec in Q.SECTIONS:
        for d in Q.DIRS:
            a, b = Q.stats(_picks(state, Q.lane(sec, d))), Q.stats(_picks(state, Q.lane(sec, d, True)))
            body += (f'<tr data-lane="{esc(Q.lane(sec, d))}"><td><b>Club 90 · {esc(sec)} {esc(d)} {Q.LINES[sec][d]}</b></td>'
                     f'<td><a href="./nba.html#qlines-{esc(sec.lower())}">NBA</a></td><td class="num">{_won_lost(a)}</td>'
                     f'<td class="num">{_pct(a["ret"], True)}</td><td class="num">{_won_lost(b)} · {_pct(b["ret"], True)}</td>'
                     f'<td>{esc(Q.status_text(a["n"]))}</td></tr>')
    return ('<section id="qlines-index"><h2>Club 90 · quarter &amp; half lines</h2><p class="shell-kicker">Quarter and half game-total lines · teams at 90% or better over 10+ games · '
            'each lane is on the NBA page beside its blind control · paper · not in Production</p>'
            '<div class="tbl"><table class="shadow-index qline-index"><tr><th>Lane</th><th>Page</th><th class="num">Won-lost</th><th class="num">Return after fees</th>'
            '<th class="num">Blind control</th><th>Status</th></tr>' + body + '</table></div></section>')
