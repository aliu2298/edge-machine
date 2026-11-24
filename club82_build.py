"""The Soccer page's collapsible "Club 82" block (club82.py): two Sandbox paper lanes, each with its record beside its control, the teams at 82%+ now,
the 75-81% watch teams, recent picks and the logged skips. Percentages only. Tables carry no thead so the shared label pass names every cell for the
phone cards. Never breaks the page: soccer_build wraps the call."""
import html as _h

import club82 as C
import fmt


def esc(x):
    return _h.escape(str(x))


def _pct(v, sign=False, d=1):
    return "—" if v is None else (f"{v * 100:+.{d}f}%".replace("-", "−") if sign else f"{v * 100:.{d}f}%")


def _picks(state, ln):
    return ((state.get("rules") or {}).get(ln) or {}).get("picks") or []


def _wl(s):
    return f"{s['won']}-{s['n'] - s['won']}"


def record_table(state):
    body = ""
    for k in C.KINDS:
        a, b = C.stats(_picks(state, C.lane(k))), C.stats(_picks(state, C.lane(k, True)))
        body += (f'<tr data-source="{esc(C.lane(k))}"><td><b>{esc(C.NAMES[k])}</b></td><td class="num">{_wl(a)}</td><td class="num">{_pct(a["ret"], True)}</td>'
                 f'<td class="num">{_wl(b)} · {_pct(b["ret"], True)}</td><td class="num">{a["open"]}</td><td>{esc(C.status_text(a["n"]))}</td></tr>')
    return ('<div class="tbl"><table class="club82-record"><tr><th>Lane</th><th class="num">Won-lost</th><th class="num">Return after fees</th>'
            f'<th class="num">Every-game control</th><th class="num">Open</th><th>Read</th></tr>{body}</table></div>')


def tracker_rows(state, fixtures, kind):
    """Every team's row: from the fixtures when handed in, else from the tracker the last run stored in the ledger."""
    if fixtures:
        return list(C.team_rows(fixtures, kind).values())
    return list((state.get("tracker") or {}).get(kind) or [])


def teams_table(rows, kind, watch=False):
    if watch:
        rows = [v for v in rows if v["n"] >= C.MIN_GAMES and C.WATCH - C.EPS <= v["rate"] < C.THRESHOLD - C.EPS and not v["qualifies"]]
    else:
        rows = [v for v in rows if v["qualifies"]]
    rows.sort(key=lambda v: (-v["rate"], -v["n"], v["name"]))
    body = "".join(f'<tr data-team="{esc(v["name"])}"><td><b>{esc(v["name"])}</b></td><td class="num">{v["hits"]}/{v["n"]}</td><td class="num">{_pct(v["rate"], d=0)}</td>'
                   f'<td>{esc(v["since"] or "—")}</td></tr>' for v in rows)
    if not body:                  # an empty-state sentence, not a one-cell table row: a spanning cell blows the phone cards out past the viewport
        return f'<p class="sm mut">{"No team in the 75-81% band." if watch else "No team is at 82% yet."}</p>', 0
    return ('<div class="tbl"><table class="club82-teams"><tr><th>Team</th><th class="num">Hits/games</th><th class="num">Rate</th>'
            f'<th>{"Rate band since" if watch else "Qualified since"}</th></tr>{body}</table></div>'), len(rows)


def picks_table(rows, empty):
    return HEAD.format(rows) if rows else f'<p class="sm mut">{esc(empty)}</p>'


def _row(p):
    res = {"open": "open", "won": "won", "lost": "lost", "no_result": "no result"}.get(p["status"], p["status"])
    if p.get("profit") is not None:
        res += f" · {_pct(p['profit'] / 100, True)}"
    who = ", ".join(p.get("qualifying_teams") or []) or p.get("team") or "control"
    bet = "under 3.5 (NO)" if p["kind"] == "u35" else f"{p.get('team', '')} 2+ (YES)"
    return (f'<tr><td>{esc(fmt.when(p["start"]))}</td><td>{esc(p["match"])}</td><td>{esc(bet)}</td><td class="num">{p["price"] * 100:.0f}c</td>'
            f'<td>{esc(who)}</td><td>{esc(res)}</td></tr>')


HEAD = ('<div class="tbl"><table class="club82-picks"><tr><th>Kickoff</th><th>Match</th><th>Bet</th><th class="num">Price</th><th>Qualifying</th><th>Result</th></tr>'
        '{}</table></div>')


def lane_html(state, fixtures, k):
    picks = sorted(_picks(state, C.lane(k)), key=lambda p: (p["start"], p["id"]), reverse=True)
    ctl = sorted(_picks(state, C.lane(k, True)), key=lambda p: (p["start"], p["id"]), reverse=True)
    recent = picks_table("".join(_row(p) for p in picks[:5]), "No entries yet. A match enters when a team clears the bar before kickoff.")
    allrows = picks_table("".join(_row(p) for p in picks), "No entries yet.")
    ctlrows = picks_table("".join(_row(p) for p in ctl[:60]), "No control rows yet.")
    skips = [s for s in (state.get("skips") or {}).values() if s["kind"] == k]
    skips.sort(key=lambda s: s["start"], reverse=True)
    skip_rows = "".join(f'<tr><td>{esc(fmt.when(s["start"]))}</td><td>{esc(s["match"])}</td><td>{esc(s.get("team") or "match")}</td><td>{esc(s["reason"])}</td>'
                        f'<td>{"yes" if s["qualifying"] else "no"}</td></tr>' for s in skips[:60])
    rows = tracker_rows(state, fixtures, k)
    now_t, n_now = teams_table(rows, k)
    watch_t, n_watch = teams_table(rows, k, watch=True)
    return (f'<h4 class="sm">{esc(C.NAMES[k])} · hit = {esc(C.HITS[k])}</h4>'
            f'<h4 class="sm">Teams at 82%+ now · {n_now}</h4>{now_t}'
            f'<details class="section-disclosure"><summary><b>Watch · 75-81%</b><span>{n_watch} team{"s" if n_watch != 1 else ""} under the bar</span></summary>{watch_t}</details>'
            f'<h4 class="sm">Recent picks</h4>{recent}'
            f'<details class="section-disclosure"><summary><b>All entries</b><span>{len(picks)}</span></summary>{allrows}</details>'
            f'<details class="section-disclosure"><summary><b>Control rows</b><span>latest 60 of {len(ctl)}</span></summary>{ctlrows}</details>'
            f'<details class="section-disclosure"><summary><b>Skipped reads</b><span>{len(skips)} logged · no market, no quote or a wide spread</span></summary>'
            + (f'<div class="tbl"><table class="club82-skips"><tr><th>Kickoff</th><th>Match</th><th>Team</th><th>Why</th><th>Qualifying</th></tr>{skip_rows}</table></div>' if skip_rows else '<p class="sm mut">None logged.</p>') + '</details>')


def summary_line(state):
    parts = []
    for k in C.KINDS:
        a, b = C.stats(_picks(state, C.lane(k))), C.stats(_picks(state, C.lane(k, True)))
        parts.append(f"{C.NAMES[k].split(' (')[0]} {_wl(a)} {_pct(a['ret'], True)} v control {_pct(b['ret'], True)}")
    return " · ".join(parts)


def section(state=None, fixtures=None):
    state = state if state is not None else C.load()
    fixtures = fixtures or []
    entries = sum(len(_picks(state, C.lane(k))) for k in C.KINDS)
    through = (max((f["kickoff"][:10] for f in C.season_games(fixtures)), default=None) if fixtures else state.get("games_through")) or "not yet"
    last = state.get("last_run")
    err = f" · {esc(state['error'])}" if state.get("error") else ""
    lanes = "".join(lane_html(state, fixtures, k) for k in C.KINDS)
    html = (f'<section id="club82" class="sp-section"><details class="fold nba-qline club82-fold" id="club82-fold"><summary><h3>Club 82 (Sandbox)</h3>'
            f'<span class="sm mut">{esc(summary_line(state))}</span></summary>'
            f'<p class="sm mut">paper · {entries} entr{"y" if entries == 1 else "ies"} · tracker through {esc(through)}</p>'
            f'<p class="sm">Paper only, on Kalshi. A team qualifies when its 2026-27 hit rate, across the Premier League, La Liga, Serie A, Bundesliga, Ligue 1 and the Champions League together '
            f'(90 minutes), is {C.THRESHOLD * 100:.0f}% or better over {C.MIN_GAMES}+ games, counting only games before the kickoff. Under 3.5: NO when either team qualifies, one entry a match. '
            f'Team 2+: YES on the team-total over 1.5 for each qualifying team. The price is read 30 to 60 minutes before kickoff (spread 5c or less), held to settlement. '
            f'Each lane has a control read at the same moment: every match\'s under 3.5, every team\'s over 1.5. Read at {C.REVIEW_AT[0]} settled, then {C.REVIEW_AT[1]}.</p>'
            f'{record_table(state)}{lanes}'
            f'<p class="sm mut">Last read {esc(fmt.when(last) if last else "not yet")}{err}. Registered {esc(C.REGISTERED)}.</p></details></section>')
    import sandbox_build                                         # the sport page's own label pass runs before this block is put in
    return sandbox_build.label_cells(html)


def index_html(state=None):
    """The Sandbox page's index of the two lanes: one row each, linking to the block on the Soccer page."""
    state = state if state is not None else C.load()
    body = ""
    for k in C.KINDS:
        a, b = C.stats(_picks(state, C.lane(k))), C.stats(_picks(state, C.lane(k, True)))
        body += (f'<tr data-lane="{esc(C.lane(k))}"><td><b>Club 82 · {esc(C.NAMES[k])}</b></td><td><a href="./soccer.html#club82">Soccer</a></td>'
                 f'<td class="num">{_wl(a)}</td><td class="num">{_pct(a["ret"], True)}</td><td class="num">{_wl(b)} · {_pct(b["ret"], True)}</td><td>{esc(C.status_text(a["n"]))}</td></tr>')
    return ('<section id="club82-index"><h2>Club 82</h2><p class="shell-kicker">Teams at 82%+ for under 3.5 or for scoring 2+ this season · each lane is on the Soccer page '
            'beside its every-game control · paper · not in Production</p>'
            '<div class="tbl"><table class="shadow-index club82-index"><tr><th>Lane</th><th>Page</th><th class="num">Won-lost</th><th class="num">Return after fees</th>'
            f'<th class="num">Every-game control</th><th>Status</th></tr>{body}</table></div></section>')
