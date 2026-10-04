#!/usr/bin/env python3
"""The NBA page: dynamic last-five pace labels, rendered from data/nba_pace.json.

This page shows a MECHANISM TEST, not a lane with an edge, and it says so at the top. The
counters are the point -- labelled, projected, graded, flipped -- because the question
being asked of the preseason is whether a label that is supposed to move transitions
cleanly, not whether it forecasts anything. Preseason basketball forecasts nothing.

No prices appear here because the lane has none. Nothing on this page is a bet, and the
Sandbox's gates never see it.
"""
import datetime
import json
import os

import fmt
import site_chrome as C

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "data", "nba_pace.json")
OUT = os.path.join(ROOT, "public_site", "nba.html")

# What each label means, spelled out once rather than left as jargon on every row.
TAGS = {
    "O+D+": "scores more, allows more",
    "O+D-": "scores more, allows less",
    "O-D+": "scores less, allows more",
    "O-D-": "scores less, allows less",
}


def esc(x):
    return C.esc("" if x is None else x)


def _num(v, nd=1, dash="—"):
    return dash if v is None else f"{v:.{nd}f}"


def _signed(v, nd=1):
    return "—" if v is None else f"{v:+.{nd}f}"


def tag_cell(tag):
    if not tag:
        return '<td class="mut">—</td>'
    cls = "pos" if tag == "O+D+" else ("neg" if tag == "O-D-" else "")
    return (f'<td><span class="{cls}" title="{esc(TAGS.get(tag, tag))}">'
            f'{esc(tag)}</span></td>')


def mechanism(blob):
    allg = blob["games"]
    skips = [g for g in allg if g.get("skipped")]
    games = [g for g in allg if not g.get("skipped")]
    done = [g for g in games if g.get("completed")]
    miss_exp = sum(1 for g in games if g.get("roll_exp_ft") is None)
    miss_lab = sum(1 for g in games
                   if not g.get("roll_lab_home_ft") or not g.get("roll_lab_away_ft"))
    ungraded = sum(1 for g in done if g.get("act_ft") is None)
    short = sum(1 for g in games if (g.get("roll_home_n") or 0) < blob["window"]
                or (g.get("roll_away_n") or 0) < blob["window"])
    flips = sum(blob.get("label_flips", {}).values())
    bad = miss_exp + miss_lab + ungraded
    rows = [
        ("games listed", len(allg), ""),
        ("labellable", len(games), ""),
        ("completed and graded", len(done) - ungraded, ""),
        ("skipped — no NBA record to roll", len(skips), "mut"),
        ("missing an expectation", miss_exp, "neg" if miss_exp else "pos"),
        ("missing a label", miss_lab, "neg" if miss_lab else "pos"),
        ("finished but ungraded", ungraded, "neg" if ungraded else "pos"),
        ("short window (&lt; %d games)" % blob["window"], short, "mut"),
        ("label flips", flips, ""),
    ]
    cells = "".join(
        f'<div class="tile"><b class="{c}">{v:,}</b><span>{k}</span></div>'
        for k, v, c in rows)
    verdict = ("The mechanism is holding: every labellable game carries a label, an "
               "expectation and — once played — a graded result."
               if bad == 0 else
               f"<b class='neg'>The mechanism is not holding.</b> {bad} game(s) are "
               "missing a label, an expectation or a grade.")
    return f'<div class="tiles">{cells}</div>\n<div class="note">{verdict}</div>'


def accuracy(blob):
    done = [g for g in blob["games"]
            if not g.get("skipped") and g.get("completed") and g.get("act_ft") is not None]
    if not done:
        return ('<div class="note">No completed games yet. The accuracy table fills in '
                'as preseason results land.</div>')
    out = []
    for p, lbl in (("q1", "First quarter"), ("h1", "First half"), ("ft", "Full game")):
        rows = [g for g in done
                if g.get("act_" + p) is not None and g.get("roll_exp_" + p) is not None]
        if not rows:
            out.append(f"<tr><td>{esc(lbl)}</td><td class='num'>0</td>"
                       + "<td class='num mut'>—</td>" * 5 + "</tr>")
            continue
        e = [g["roll_exp_" + p] for g in rows]
        a = [g["act_" + p] for g in rows]
        n = len(rows)
        me, ma = sum(e) / n, sum(a) / n
        bias = ma - me
        mae = sum(abs(x - y) for x, y in zip(a, e)) / n
        if n >= 3:
            num = sum((x - me) * (y - ma) for x, y in zip(e, a))
            den = (sum((x - me) ** 2 for x in e) * sum((y - ma) ** 2 for y in a)) ** 0.5
            r = f"{num/den:+.3f}" if den else "—"
        else:
            r = "—"
        out.append(
            f"<tr><td>{esc(lbl)}</td><td class='num'>{n}</td>"
            f"<td class='num'>{_num(me)}</td><td class='num'>{_num(ma)}</td>"
            f"<td class='num {'neg' if bias < 0 else 'pos'}'>{_signed(bias)}</td>"
            f"<td class='num'>{_num(mae)}</td><td class='num'>{esc(r)}</td></tr>")
    head = ("<tr><th>Period</th><th>Graded</th><th>Expected</th><th>Actual</th>"
            "<th>Bias</th><th>Mean error</th><th>Correlation</th></tr>")
    return f'<div class="tbl"><table>{head}{"".join(out)}</table></div>'


def games_table(blob):
    rows = []
    for g in sorted(blob["games"], key=lambda x: (str(x.get("start")), x.get("id") or "")):
        when = str(g.get("day") or "")
        match = f"{esc(g.get('away'))} at {esc(g.get('home'))}"
        if g.get("skipped"):
            rows.append(
                f'<tr class="mut"><td>{esc(when)}</td><td>{match}</td>'
                f'<td colspan="8">{esc(g["skipped"])} — cannot be labelled</td></tr>')
            continue
        played = g.get("completed") and g.get("act_ft") is not None
        cells = [f"<td>{esc(when)}</td>", f"<td>{match}</td>",
                 tag_cell(g.get("roll_lab_away_ft")), tag_cell(g.get("roll_lab_home_ft"))]
        for p in ("q1", "h1", "ft"):
            exp, act = g.get("roll_exp_" + p), g.get("act_" + p)
            cells.append(f"<td class='num'>{_num(exp)}</td>")
            if played and act is not None:
                d = act - exp if exp is not None else None
                cells.append(f"<td class='num'>{act}<span class='mut sm'> "
                             f"{_signed(d)}</span></td>")
            else:
                cells.append("<td class='num mut'>—</td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")
    head = ("<tr><th>Date</th><th>Game</th><th>Away</th><th>Home</th>"
            "<th>Q1 exp</th><th>Q1 actual</th><th>1H exp</th><th>1H actual</th>"
            "<th>FT exp</th><th>FT actual</th></tr>")
    return f'<div class="tbl"><table>{head}{"".join(rows)}</table></div>'


def seed_table(blob):
    seed = blob.get("seed", {})
    teams = seed.get("teams", {})
    if not teams:
        return ""
    calc = {}
    for t, w in teams.items():
        ft = w.get("ft") or []
        if not ft:
            continue
        calc[t] = (sum(x[0] for x in ft) / len(ft), sum(x[1] for x in ft) / len(ft))
    if not calc:
        return ""
    lo = sum(v[0] for v in calc.values()) / len(calc)
    ld = sum(v[1] for v in calc.values()) / len(calc)
    rows = []
    for t, (o, d) in sorted(calc.items(), key=lambda kv: -(kv[1][0] + kv[1][1])):
        tag = ("O+" if o >= lo else "O-") + ("D+" if d >= ld else "D-")
        rows.append(f"<tr><td>{esc(t)}</td><td class='num'>{_num(o)}</td>"
                    f"<td class='num'>{_num(d)}</td><td class='num'>{_num(o+d)}</td>"
                    f"{tag_cell(tag)}</tr>")
    head = ("<tr><th>Team</th><th>Scored</th><th>Allowed</th><th>Combined</th>"
            "<th>Label</th></tr>")
    span = seed.get("span", ["", ""])
    note = (f'<div class="note sm">Each team\'s last {blob["window"]} regular-season games '
            f'of 2025-26, {esc(span[0])} to {esc(span[1])} ({seed.get("games", 0)} games). '
            f'This is the starting window; preseason results roll into it from the left.</div>')
    return f'{note}<div class="tbl"><table>{head}{"".join(rows)}</table></div>'


def build(blob=None, now=None):
    blob = blob or json.load(open(SRC))
    now = now or datetime.datetime.now(datetime.timezone.utc)
    flips = blob.get("label_flips", {})
    worst = ", ".join(f"{t} ×{n}" for t, n in list(flips.items())[:6]) or "none yet"
    body = f"""<h1>NBA pace labels</h1>
<p class="lede">A team is labelled on its last {blob['window']} games — does it score more
than average, does it allow more than average — and the two labels are combined into an
expected total. Preseason only. No prices, no bets.</p>

<div class="note"><b>This is a test of the mechanism, not a forecast.</b> It asks whether a
label that is supposed to move transitions cleanly: every scheduled game labelled and
projected before tip-off, every finished game graded, the window advancing as results land.
Preseason basketball predicts nothing — starters play fifteen minutes and the bench decides
the result — which is exactly why it is the right place to find the breaks.</div>

<section id="mechanism">
<h2>Mechanism</h2>
{mechanism(blob)}
<div class="note sm">Teams flipping their label so far: {esc(worst)}. A flip means a team
crossed the scores-more or allows-more line between games. At a {blob['window']}-game window
this is expected to be frequent: the same seed below agreed with those teams' own
full-season 2025-26 labels for only <b>15 of 30</b> teams, with Memphis 16.9 points out on
defence because eliminated teams rest starters in April. A five-game window is measured, and
too short — the fix is a wider window or shrinkage toward a prior, not a different five
games.</div>
</section>

<section id="accuracy">
<h2>Accuracy</h2>
<div class="note sm">Secondary, and not expected to work. Bias is actual minus expected.</div>
{accuracy(blob)}
</section>

<section id="games">
<h2>Games</h2>
<div class="note sm">Labels and expectations are recorded before tip-off and never
recomputed. The small number beside an actual is the miss.</div>
{games_table(blob)}
</section>

<section id="seed">
<h2>Starting window</h2>
{seed_table(blob)}
</section>
<footer>Read-only static export · rebuilt by GitHub Actions · research, not betting advice.</footer>
"""
    return C.document(
        "Edge Machine · NBA",
        "Dynamic last-five pace labels for NBA teams, tested on the preseason.",
        "nba",
        (("mechanism", "Mechanism"), ("accuracy", "Accuracy"),
         ("games", "Games"), ("seed", "Starting window")),
        C.stamp(now),
        body,
    )


def main():
    if not os.path.exists(SRC):
        print(f"no {SRC} — run nba_pace.py --run first")
        return 1
    html = build()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    tmp = OUT + ".tmp"
    with open(tmp, "w") as f:
        f.write(html)
    os.replace(tmp, OUT)
    print(f"wrote {OUT} ({len(html):,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
