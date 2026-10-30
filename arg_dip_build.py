"""The Soccer page's "Argentina · goalless dip" section for arg_goalless_dip (arg_dip.py), near the top.

Read from the lane's own ledger (data/arg_dip_ledger.json). The record is the matches since SINCE; the in-sample
research block is shown once, collapsed and labelled, and never feeds the record, the status or the index row.
Header-row tables, so the page's label_cells names each cell for the phone layout. Never breaks the page:
soccer_build wraps the call.

Every goalless-dip lane renders through these functions (2026-10-30): a lane is its engine config (arg_dip.ARG,
top5_dip.TOP5) plus a page config here (ARG_PAGE, TOP5_PAGE) with its section id, copy and link. PAGES lists
them in page order; each takes `page` and defaults to Argentina.
"""
import datetime as dt
import html as _h
import os

import arg_dip as A
import top5_dip as T


def esc(x):
    return _h.escape(str(x))


def pct(v, sign=True):
    return "—" if v is None else (f"{v * 100:+.1f}%" if sign else f"{v * 100:.0f}%").replace("-", "−")


def zfmt(v):
    return "—" if v is None else f"{v:+.2f}".replace("-", "−")


def clock(ts):
    t = dt.datetime.fromtimestamp(ts, A.UTC).astimezone(A.D.ET)
    return f"{t:%b %-d, %-I:%M %p}"


def read_of(fills):
    if fills < A.REVIEW_N:
        return f"too early ({fills} of {A.REVIEW_N})"
    if fills < A.DECIDE_N:
        return f"review ({fills} of {A.DECIDE_N} to decide)"
    return "decide"


def variant_table(entries, tid, page=None):
    page = page or ARG_PAGE
    cfg = page["cfg"]
    body = []
    for f in cfg["fractions"]:
        s = A.summary(entries, f)
        head = f == cfg["headline"]
        body.append(
            f'<tr data-variant="{A.vkey(f)}"{" class=\"hl\"" if head else ""}><td><b>Buy at {A.vkey(f)}% of P'
            f'{" (headline)" if head else ""}</b></td><td class="num">{s["matches"]}</td>'
            f'<td class="num">{s["fills"]} ({pct(s["fill_rate"], sign=False)})</td><td class="num">{s["thin"]}</td>'
            f'<td class="num">{s["sold"]}</td><td class="num">{s["zero"]}</td><td class="num">{pct(s["roi"])}</td>'
            f'<td class="num">{pct(s["hold"])}</td><td class="num">{zfmt(s["z"])}</td><td class="num">{s["days"]}</td>'
            f'<td class="num">{pct(s["old"])}</td><td class="num">{pct(s["new"])}</td><td>{esc(read_of(s["fills"]))}</td></tr>')
    return (f'<div class="tbl"><table id="{tid}"><tr><th>Buy</th><th class="num">Matches seen</th>'
            '<th class="num">Buys filled (fill rate)</th><th class="num">Thin touches</th><th class="num">Sold at P</th>'
            f'<th class="num">{esc(page["zero_head"])}</th><th class="num">ROI per fill</th><th class="num">Hold, same fills</th>'
            '<th class="num">z (by matchday)</th><th class="num">Matchdays</th><th class="num">Older half</th>'
            '<th class="num">Newer half</th><th>Read</th></tr>' + "".join(body) + "</table></div>")


def league_table(entries, tid, cfg):
    """The headline buy per league: a lane over several series shows where its fills come from."""
    body = []
    for lg in dict.fromkeys(cfg["leagues"].values()):
        mine = [e for e in entries if e.get("league") == lg]
        s = A.summary(mine, cfg["headline"])
        body.append(f'<tr data-league="{esc(lg)}"><td><b>{esc(lg)}</b></td><td class="num">{s["matches"]}</td>'
                    f'<td class="num">{s["fills"]}</td><td class="num">{s["sold"]}</td><td class="num">{pct(s["roi"])}</td>'
                    f'<td class="num">{pct(s["hold"])}</td><td class="num">{zfmt(s["z"])}</td></tr>')
    return (f'<div class="tbl"><table id="{tid}"><tr><th>League</th><th class="num">Matches seen</th>'
            f'<th class="num">Buys filled at {A.vkey(cfg["headline"])}%</th><th class="num">Sold at P</th>'
            '<th class="num">ROI per fill</th><th class="num">Hold, same fills</th><th class="num">z (by matchday)</th></tr>'
            + "".join(body) + "</table></div>")


def fills_list(entries, limit=30, page=None):
    page = page or ARG_PAGE
    cfg = page["cfg"]
    rows = []
    for e in sorted(entries, key=lambda e: e["kickoff"], reverse=True):
        b = (e.get("buys") or {}).get(A.vkey(cfg["headline"]))
        if not b:
            continue
        cost = b["limit"] + A.fee(b["limit"])
        proceeds = (e["p"] - A.fee(e["p"])) if b["sold"] else b["payout"]
        thin = "" if b["counted"] else (" · thin touch (the price did not hold), not counted" if b.get("held") is False
                                         and b["fill_volume"] >= A.MIN_FILL - A.EPS else " · thin touch, not counted")
        league = f'{esc(e["league"])} · ' if e.get("league") else ""
        rows.append(f'<tr><td>{esc(clock(e["kickoff"]))}</td><td>{league}{esc(e["title"])}</td><td class="num">{e["p"] * 100:.0f}c</td>'
                    f'<td class="num">{b["limit"] * 100:.0f}c</td><td class="num">{(b["fill_at"] - e["kickoff"]) / 60:.0f}\'</td>'
                    f'<td class="num">{b["fill_volume"]:g}</td>'
                    f'<td>{"sold at P" if b["sold"] else "held"}{thin}</td>'
                    f'<td>{page["zero_label"] if e["result"] == "no" else page["goal_label"]}</td>'
                    f'<td class="num">{pct((proceeds - cost) / cost) if b["counted"] else "—"}</td></tr>')
        if len(rows) >= limit:
            break
    body = "".join(rows) or '<tr><td colspan="9" class="mut">No buy has filled yet.</td></tr>'
    return ('<div class="tbl"><table><tr><th>Kickoff (ET)</th><th>Match</th><th class="num">P</th><th class="num">Buy at</th>'
            '<th class="num">Filled (min after kickoff)</th><th class="num">Contracts at or below, 60 min</th><th>Sell</th>'
            '<th>Ended</th><th class="num">ROI after fees</th></tr>' + body + "</table></div>")


def skips_line(skips):
    why = {}
    for v in (skips or {}).values():
        k = v.split(":")[0]
        why[k] = why.get(k, 0) + 1
    return f"Matches skipped: {len(skips or {})}" + (" (" + "; ".join(f"{k}: {n}" for k, n in sorted(why.items())) + ")" if why else "")


def watching(state):
    up = state.get("upcoming") or []
    if not up:
        return '<p class="sm mut">Watching next: no open match listed at the last read.</p>'
    return ('<p class="sm"><b>Watching next</b> · ' + "; ".join(f"{esc(clock(u['kickoff']))} {esc(u['title'])}" for u in up[:6])
            + ".</p>")


def load_state(page):
    cfg = page["cfg"]
    return A.load(cfg=cfg) if os.path.exists(cfg["path"]) else A.load("/nonexistent", cfg=cfg)


def index_row(state=None, page=None):
    """The Sandbox index's row for a lane: the live record only."""
    page = page or ARG_PAGE
    cfg = page["cfg"]
    state = state if state is not None else load_state(page)
    s = A.summary(state.get("entries") or [], cfg["headline"])
    return dict(lane=cfg["lane"], label=cfg["label"], href=f'./soccer.html#{page["id"]}', matches=s["matches"],
                fills=s["fills"], roi=s["roi"], hold=s["hold"], status=A.status(s["fills"]))


def index_rows():
    """Every goalless-dip lane's index row, in page order. A lane whose row fails is left out."""
    out = []
    for page in PAGES:
        try:
            out.append(index_row(page=page))
        except Exception:                                       # noqa: BLE001
            continue
    return out


RULE = ("KXARGPREMDIVTOTAL, the over 0.5 rung, every league match. Kickoff is Kalshi's occurrence time minus 4 hours. "
        "P is the YES ask an hour before kickoff from 1-minute candles, with a spread of 5c or less and only if that ask "
        f"passes the entry-validity check ({A.MS.MIN_SIZE}+ contracts traded at or through it within "
        f"{A.MS.PRINT_WINDOW_MIN} minutes, never under half the last trade). From kickoff a YES buy rests at 65% of P "
        "(the headline; 75% and 55% are tracked on the same matches). It fills when a trade prints at or below it, and "
        f"counts only when {A.MIN_FILL}+ contracts printed at or below it within {A.FILL_WINDOW_MIN} minutes of the first "
        "touch (a replay cannot read the book at the fill); fewer is a thin touch, not counted. At the fill a sell rests at "
        "P; it fills when a later trade prints at or above P, else the position settles (1 if a goal, 0 at 0-0). Maker "
        "fee 0.0175 p(1-p) in and out. The control is the same fills held to settlement; an unfilled buy costs nothing. "
        "An outcome is a match; z is clustered by matchday.")

TOP5_RULE = ("The over 1.5 rung of KXEPLTOTAL, KXLALIGATOTAL, KXSERIEATOTAL, KXBUNDESLIGATOTAL, KXLIGUE1TOTAL and "
             "KXUCLTOTAL, every match. Kickoff is Kalshi's occurrence time minus 4 hours. P is the YES ask an hour "
             "before kickoff from 1-minute candles, 10c to 95c, with a spread of 5c or less and only if that ask passes "
             f"the entry-validity check ({A.MS.MIN_SIZE}+ contracts traded at or through it within "
             f"{A.MS.PRINT_WINDOW_MIN} minutes, never under half the last trade). From kickoff a YES buy rests at 55% "
             "of P (the headline; 65% is tracked on the same matches). It counts as a fill only when a trade prints at "
             f"or below it, {A.MIN_FILL}+ contracts print at or below it within {A.FILL_WINDOW_MIN} minutes of that "
             f"first touch, and the low price held: the prints at or below it span {A.HELD_SPAN_S // 60}+ minutes "
             f"within {A.HELD_WINDOW_MIN} minutes of the first touch, or {A.HELD_CONTRACTS}+ contracts print there. "
             "Anything less is a thin touch, not counted: brief stray prints are ones a real resting bid would rarely "
             "get. At the fill a sell rests at P; it fills when a later trade prints at or above P, else the position "
             "settles (1 at 2+ goals, 0 otherwise). Maker fee 0.0175 p(1-p) in and out. The control is the same fills "
             "held to settlement; an unfilled buy costs nothing. An outcome is a match; z is clustered by matchday, "
             "and the league is shown per row.")


def section(state=None, page=None):
    page = page or ARG_PAGE
    cfg = page["cfg"]
    sid = page["id"]
    if state is None:
        state = load_state(page)
    entries = [e for e in state.get("entries") or [] if e.get("buys") is not None]
    ins = state.get("insample") or {}
    head = A.vkey(cfg["headline"])
    s = A.summary(entries, cfg["headline"])
    summ = (f'{s["matches"]} matches seen · {s["fills"]} bought at {head}% · {s["sold"]} sold at P · {A.status(s["fills"])}'
            if entries else f'no match has settled since the record began on {state.get("since")}')
    body = (variant_table(entries, f"{sid}-live", page) if entries else
            f'<p class="sm mut">No match has settled since the record began on {esc(state.get("since"))}. The first rows '
            'appear after the first matches finish.</p>')
    if entries and cfg.get("leagues"):
        body += f'<p class="sm"><b>By league</b> · the headline buy at {head}% of P</p>' + league_table(entries, f"{sid}-leagues", cfg)
    ins_entries = ins.get("entries") or []
    window = ins.get("window", cfg["insample"])
    ins_leagues = (league_table(ins_entries, f"{sid}-insample-leagues", cfg) if cfg.get("leagues") else "")
    ins_block = (f'<details class="section-disclosure" id="{sid}-insample"><summary><b>In-sample research</b><span>'
                 f'{esc(window[0])} to {esc(window[1])} · the matches the rule '
                 'was found on · not evidence, never in the record</span></summary>'
                 '<p class="sm">Replayed once by the same code. The rule was chosen on these matches, so they cannot '
                 'test it: only matches from the record date on count.</p>'
                 + (f'<p class="sm">{esc(page["insample_note"])}</p>' if page.get("insample_note") else "")
                 + variant_table(ins_entries, f"{sid}-insample-table", page) + ins_leagues
                 + f'<p class="sm mut">{esc(skips_line(ins.get("skips")))}.</p>'
                 '</details>') if ins_entries else ""
    last = state.get("last_run")
    return f"""<section id="{sid}">
<h2>{esc(page["title"])}</h2>
<p class="shell-kicker">Paper only · no orders · fresh record since {esc(state.get("since"))} · an outcome is a match · review at {A.REVIEW_N} filled matches, decide at {A.DECIDE_N}</p>
<details class="section-disclosure" data-lane="{cfg["lane"]}" open><summary><b>{esc(cfg["label"])}</b><span>{esc(summ)}</span></summary>
<p class="sm">{esc(page["intro"])}</p>
<p class="sm">{esc(page["rule"])}</p>
<p class="sm"><b>{esc(page["oos"])}</b></p>
{body}
<p class="sm mut">{esc(skips_line(state.get("skips")))}.</p>
{watching(state)}
<details class="section-disclosure"><summary><b>Fills</b><span>latest 30 at {head}% of P</span></summary>{fills_list(entries, page=page)}</details>
{ins_block}
</details>
<p class="sm mut">Last read {esc(last or 'not yet')}{(' · ' + esc(state['error'])) if state.get('error') else ''}.</p>
</section>"""


def place(html, state=None):
    """Put the goalless-dip sections right after the page's cheap-side section (o35), else before its first
    section, in PAGES order (Argentina first; `state`, when given, is Argentina's). Never breaks."""
    try:
        import sandbox_build
        secs = []
        for page in PAGES:
            try:
                secs.append(sandbox_build.label_cells(section(state if page is ARG_PAGE else None, page)))
            except Exception:                                   # noqa: BLE001
                continue
        sec = "".join(secs)
        start = html.find('<section id="cheap-side">')
        at = html.find("</section>", start) + len("</section>") if start >= 0 else html.find("<section id=", html.find("<main"))
        return html[:at] + sec + html[at:] if at >= 0 else html
    except Exception:                                           # noqa: BLE001
        return html


ARG_PAGE = dict(cfg=A.ARG, id="arg-dip", title="Argentina · goalless dip", rule=RULE, oos=A.OOS_NOTE,
                intro=("Before kickoff over 0.5 costs about 88c and about 9 matches in 10 have a goal. During a long 0-0 "
                       "the price slides; this lane buys that slide and sells it back at the pregame price."),
                zero_head="Ended 0-0", zero_label="0-0", goal_label="goal")
TOP5_PAGE = dict(cfg=T.TOP5, id="top5-dip", title="Top-5 soccer · goalless dip", rule=TOP5_RULE, oos=T.OOS_NOTE,
                 intro=("Before kickoff over 1.5 in the top five leagues and the Champions League costs about 82c. During a "
                        "long goalless spell the price slides and, in the research, slid too far; this lane buys that "
                        "slide and sells it back at the pregame price."),
                 insample_note=T.INSAMPLE_NOTE,
                 zero_head="Ended under 2 goals", zero_label="under 2 goals", goal_label="2+ goals")
PAGES = (ARG_PAGE, TOP5_PAGE)
