#!/usr/bin/env python3
"""The NHL page (2026-11-08), on the shared sport template (sport_page), the Econ Daily layout: one row per lane, every
word and table inside the row's closed "Rule details" fold. Two Sandbox paper lanes from nhl_goal_lanes.py; each lane's
baseline sits in its own fold, not as a row. Presentation only: every number is the ledger's own.
"""
import datetime as dt
import html as _h
import os

import fmt
import nhl_goal_lanes as N
import soccer_lanes as L
import sport_page as SP
import sport_tab

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "public_site", "nhl.html")
FAMILY = "NHL"
KEY = "nhl"
TITLE = "Edge Machine · NHL"
DESCRIPTION = "Kalshi NHL lanes on paper: the puck line and the totals three minutes after a goal."
SCOPE = "In-play paper lanes three minutes after a goal"
HEADLINES = ("nhl_pl_no_goal", "nhl_over_goal")
BASELINE = {"nhl_pl_no_goal": "nhl_pl_no_goal_all", "nhl_over_goal": "nhl_over_goal_all"}


def esc(x):
    return _h.escape(str(x))


def pct(v):
    return "—" if v is None else f"{v * 100:+.1f}%".replace("-", "−")


def zfmt(v):
    return "—" if v is None else f"{v:+.2f}".replace("-", "−")


def params(lane):
    common = [
        ("Moment", "Three minutes after a goal, timed by the moneyline's own price jump (3c+ toward the scorer within a few "
                   "minutes of ESPN's goal time). Dropped when another goal lands in between."),
        ("Fill", "Taker at the ask, counted only when 50+ contracts trade at or through it within 5 minutes. Taker fee in, "
                 "held to settlement. A maker variant (a resting bid filled by a print through it within 15 minutes) is shown "
                 "below, never as the headline."),
    ]
    if lane == "nhl_pl_no_goal":
        rule = [("Entry", "Puck line: NO on the pre-match favourite's rung that needs exactly two more goals of margin "
                          "(for example \"wins by over 1.5\" with the score level), when the NO ask is 65-80c."),
                ("Games", "Thin pre-match books only: moneyline volume in the 20 minutes before T−1h under the research "
                          "median. The favourite is the side priced above 50% at T−1h.")]
    else:
        rule = [("Entry", "Total goals: YES on every rung that still needs a goal, when its ask is 91-95c."),
                ("Games", "Every game.")]
    cfg = N.BY_LANE[lane]
    rec = [("Record", f"Fresh from {N.REGISTERED[:16].replace('T', ' ')} UTC, paper only, one row per entry, z clustered by game. "
                      f"Review at {N.REVIEW_N} settled entries, decide at {N.DECIDE_N}."
                      + (f" Headline read at about {N.HEADLINE_GAMES} games." if lane == "nhl_pl_no_goal" else "")),
           ("Research", cfg["research"])]
    return rule + common + rec


def record_table(s, lane, head="Record"):
    rows = [
        ("Settled entries · games", f'{s["n"]} · {s["games"]}'),
        ("Won v priced", f'{s["won"]} v {s["priced"]:.1f}'),
        ("ROI per entry, after fees", pct(s["roi"])),
        ("z by game", zfmt(s["z"])),
        ("Earlier half · later half", f'{pct(s["old"])} · {pct(s["new"])}'),
        ("State check v2 only", f'{pct(s["v2"])} ({s["v2_n"]})'),
        ("Logged rows without a fill", str(s["logged"] - s["n"])),
        ("Read", N.read_of(s["n"], s["games"], lane)),
    ]
    body = "".join(f'<tr><td>{esc(k)}</td><td class="num">{esc(v)}</td></tr>' for k, v in rows)
    return f'<div class="tbl"><table><thead><tr><th>{esc(head)}</th><th class="num">Figure</th></tr></thead><tbody>{body}</tbody></table></div>'


def _when(ts):
    return fmt.when(dt.datetime.fromtimestamp(ts, dt.timezone.utc).isoformat())


def entry_table(rows):
    if not rows:
        return '<p class="sm mut">No entry yet.</p>'
    body = []
    for r in sorted(rows, key=lambda r: r["ts"], reverse=True):
        t, m = r["taker"], r["maker"]
        body.append(f'<tr><td>{esc(_when(r["ts"]))}</td><td>{esc(r["title"])}</td><td class="num">{r["home_goals"]}-{r["away_goals"]}</td>'
                    f'<td>{esc(("over " if r["kind"] == "over" else "") + str(r["strike"]))} {r["side"].upper()}</td>'
                    f'<td class="num">{r["ask"] * 100:.0f}c</td><td>{"filled" if t["filled"] else "no fill"}</td>'
                    f'<td>{"won" if r["won"] else "lost"}</td><td class="num">{esc(pct(t["roi"]) if t["filled"] else "—")}</td>'
                    f'<td class="num">{esc(pct(m["roi"]) if m["filled"] else "—")}</td></tr>')
    return ('<div class="tbl"><table><thead><tr><th>Entry</th><th>Game</th><th class="num">Score</th><th>Rung</th>'
            '<th class="num">Ask</th><th>Taker</th><th>Result</th><th class="num">Taker ROI</th><th class="num">Maker ROI</th></tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table></div>')


def panel(state, lane):
    rows = N.rows_for(state, lane)
    base = BASELINE[lane]
    out = [L.params_html(params(lane)), record_table(N.summary(rows), lane),
           record_table(N.summary(rows, "maker"), lane, "Maker variant (fold only)")]
    n = len(rows)
    out.append(f'<details class="section-disclosure"><summary><b>Entries</b><span>{n} logged row{"s" if n != 1 else ""}</span></summary>'
               f'{entry_table(rows)}</details>')
    b = N.BY_LANE[base]
    out.append(f'<details class="section-disclosure baseline"><summary><b>{esc(b["label"])}</b><span>not a lane</span></summary>'
               f'<p class="sm mut">{esc(b["research"])}</p>{record_table(N.summary(N.rows_for(state, base)), base, "Baseline")}</details>')
    return "".join(out)


VERDICTS = (
    ("Moneyline", "Fair. The best in-play cell (the favourite one goal up after a goal) gained in discovery and lost on the holdout."),
    ("Total goals", "Fair. The cheap over 7.5 reached 2x exactly as often as fair, so that watch was dropped. "
                    "Expensive overs after a goal point the same way in both samples: the over lane."),
    ("Puck line", "Fair overall. One cell held on a holdout: the favourite's needs-2 NO after a goal in thin books, the puck-line lane."),
    ("1st period, team totals, overtime, early goal", "Cheap contracts below fair; expensive ones fair to overpriced."),
    ("Player props", "Both sides lose about the book's margin, and they barely trade once play starts."),
    ("Multiple tests", "About 6,300 cells tested; 53 were positive against about 314 expected by chance, and nothing "
                       "passed the Bonferroni bar. Neither lane is an edge claim."),
)


def research_html():
    """The NHL market study's verdicts (2026-11-08), one row per market."""
    body = "".join(f'<tr><td>{esc(k)}</td><td>{esc(v)}</td></tr>' for k, v in VERDICTS)
    return ('<details class="section-disclosure" id="research"><summary><b>Research: the Kalshi NHL markets</b>'
            '<span>2026-27 discovery (Oct 6 to Nov 7) and a 2025-26 holdout (Mar 6 to Apr 17)</span></summary>'
            '<p class="sm">Every NHL market at five moments (an hour before the start, three minutes after a goal, the two '
            'intermissions, the late 3rd with the score unchanged), both sides of the price, six pre-match filters '
            'registered before the results were read.</p>'
            f'<div class="tbl"><table><thead><tr><th>Market</th><th>Verdict</th></tr></thead><tbody>{body}</tbody></table></div></details>')


def template_row(state, lane):
    cfg = N.BY_LANE[lane]
    s = N.summary(N.rows_for(state, lane))
    won = sum(1 for r in N.rows_for(state, lane) if r["taker"]["filled"] and r["taker"]["roi"] > 0)
    return L.row(lane, "nhl", cfg["label"], cfg["market"], L.inplay_record(s["n"], won, s["roi"], s["z"]), panel(state, lane),
                 anchor=lane.replace("_", "-"), kind="In-play",
                 note="Record: taker fills with 50+ contracts of depth, held to settlement, after fees.")


def events(state, rows, now):
    """Completed games with a filled lane entry, inside the template's 14-day window."""
    floor_t = now - dt.timedelta(days=SP.DONE_DAYS)
    by_name = {r["name"]: r for r in rows}
    out = {}
    for lane in HEADLINES:
        for r in N.rows_for(state, lane):
            when = dt.datetime.fromtimestamp(r["ko"], dt.timezone.utc)
            if not r["taker"]["filled"] or when < floor_t or lane not in by_name:
                continue
            q = dict(start=when.isoformat(), venue="kalshi_binary", market_id=r["ticker"], status="won" if r["won"] else "lost")
            text = f'{"Over " if r["kind"] == "over" else "Puck line "}{r["strike"]} {r["side"].upper()}'
            ev = out.setdefault(r["event"], dict(when=when, label=r["title"], picks=[]))
            ev["picks"].append(SP.pick(by_name[lane], q, text, "won" if r["won"] else "lost", price=r["ask"]))
    return [SP.event(e["when"], e["label"], e["picks"], key=(e["label"], e["when"].isoformat())) for e in out.values()]


def build(state=None, d=None, st=None, now=None):
    now = SP.as_utc(now)
    state = state if state is not None else N.load()
    rows = [template_row(state, lane) for lane in HEADLINES]
    last = state.get("last_run")

    def method(d_, rs, now_):
        inner = ('<p class="sm">Both lanes are read after the final horn from Kalshi\'s 1-minute candles and trade prints and '
                 'ESPN\'s play-by-play, so an entry appears once its game has settled. Nothing is placed: paper only.</p>'
                 '<p class="sm">They come from a full breakdown of the Kalshi NHL markets in which nothing passed the '
                 'multiple-test bar; these two cells pointed the same way on a holdout and are tested forward, frozen.</p>'
                 + research_html())
        return "Method and research", "how the lanes are read · the study's verdicts", inner, False

    def empty_reason(d_, rs, idle_, now_):
        return ("the NHL lanes read settled games after the final horn, so nothing is listed ahead"
                + (f"; last read {fmt.when(last)}" if last else "; no read yet"))

    sp = SP.spec(family=FAMILY, key=KEY, title=TITLE, description=DESCRIPTION, scope=SCOPE, venue="Kalshi", rows=rows,
                 events=lambda d_, rs, now_: events(state, rs, now_),
                 rule_name=lambda r: r["own"]["label"], market=lambda d_, r: r["own"]["market"],
                 definition=lambda d_, r: r["own"]["details"], recent=lambda d_, r, n_: "",
                 method=method, empty_reason=empty_reason, scoped=False)
    return SP.page(sp, d, st, now, rows=rows)


def main():
    return sport_tab.write(OUT, build())


if __name__ == "__main__":
    raise SystemExit(main())
