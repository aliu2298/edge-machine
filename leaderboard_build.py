"""leaderboard.html (2026-10-30, Olu): the named teams, players and assets whose cheap contracts keep spiking.

Read from the ledgers the trackers already write (leaderboard.py); rebuilt with the page build, so it refreshes as
they do. The persistence test comes first: until it is positive the board describes where spikes happened, it is
not a pick list. No inline style or SVG, header-row tables (labelled for the phone cards by sandbox_build.label_cells).
The sport filter is a row of in-page links to one table per sport.
"""
import html as _h
import os

import leaderboard as L
import site_chrome as C
import sport_page as SP

KEY = "leaderboard"
TITLE = "Edge Machine · Leaderboard"
DESCRIPTION = ("Which teams, players and assets keep spiking on cheap contracts, ranked by how often the traded price "
               "reached 2x, shrunk so a few lucky contracts cannot top it, and checked week to week.")
SECTIONS = (("persistence", "Does it persist?"), ("top", "Top 10"), ("sports", "By sport"), ("bottom", "Bottom 5"),
            ("watching", "Watching"), ("method", "How it's measured"))
COLS = ("#", "Name", "Sport", "Contracts", "Events", "Per week", "Reached 2x", "Reached 3x", "Split ROI", "Hold ROI",
        "Traded at 2x+", "Holds up?", "Score")


def esc(x):
    return _h.escape(str(x))


def plural(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


def pct(v, sign=False):
    return "—" if v is None else (f"{v * 100:+.0f}%" if sign else f"{v * 100:.0f}%")


def num(v, d=0):
    return "—" if v is None else f"{v:,.{d}f}"


def holds_cell(s):
    if s["holds"] is None:
        return f'<span class="mut">needs {L.HALF_MIN} per half</span>'
    return f'{"✅" if s["holds"] else "No"} · {pct(s["old"])} v {pct(s["new"])}'


def breakdown(s):
    """The entity's own contracts by market type, as a fold under its name (no script needed)."""
    rows = "".join(
        f'<li><b>{esc(m["market"])}</b>{" (match contract)" if m["match"] else ""}: {plural(m["n"], "contract")}, {plural(m["events"], "event")} · '
        f'reached 2x {pct(m["r2"])}, 3x {pct(m["r3"])} · split {pct(m["split"], True)}, hold {pct(m["hold"], True)}'
        f'{" · median traded at 2x+ " + num(m["vol"]) if m["vol"] is not None else ""}</li>'
        for m in s["markets"])
    return f'<details class="lb-fold"><summary>{esc(s["name"])}</summary><ul class="sm">{rows}</ul></details>'


def row(i, s):
    tag = ' <span class="mut">match</span>' if s["matches"] else ""
    return (f'<tr><td class="num">{i}</td><td>{breakdown(s)}{tag}</td><td>{esc(s["sport"])}</td>'
            f'<td class="num">{s["n"]}</td><td class="num">{s["events"]}</td><td class="num">{num(s["per_week"], 1)}</td>'
            f'<td class="num">{pct(s["r2"])}</td><td class="num">{pct(s["r3"])}</td>'
            f'<td class="num">{pct(s["split"], True)}</td><td class="num">{pct(s["hold"], True)}</td>'
            f'<td class="num">{num(s["vol"])}</td><td>{holds_cell(s)}</td>'
            f'<td class="num">{"—" if s["score"] is None else f"{s["score"] * 100:+.1f}pp"}</td></tr>')


def table(stats, empty):
    if not stats:
        return f'<p class="sm mut">{esc(empty)}</p>'
    body = "".join(row(i, s) for i, s in enumerate(stats, 1))
    head = "".join(f'<th class="num">{c}</th>' if c not in ("Name", "Sport", "Holds up?") else f"<th>{c}</th>" for c in COLS)
    return f'<div class="tbl"><table><tr>{head}</tr>{body}</table></div>'


def persistence_block(p):
    if p["proven"]:
        verdict = ('<p class="lede"><b>Positive so far.</b> Last week\'s top quarter has beaten the bottom quarter in most '
                   'weeks and the split-half rank correlation is above zero. It is still a short record.</p>')
    else:
        verdict = ('<p class="lede"><b>Not proven.</b> This board describes where spikes happened. It is not a proven pick '
                   'list: earlier work found hot teams do not stay hot (the team-total ladder record did not persist, '
                   'correlation −0.20), and a few lucky contracts look like a streak.</p>')
    rec = (f'<p class="sm">Running record: the top quarter beat the bottom quarter in <b>{p["beats"]} of {p["tested"]}</b> '
           f'weeks tested. Split-half rank correlation (older events v newer events, entities with {L.HALF_MIN * 2}+ '
           f'contracts): <b>{"—" if p["rho"] is None else f"{p["rho"]:+.2f}"}</b> across {p["rho_n"]} entities.</p>')
    weeks = ""
    if p["weeks"]:
        body = "".join(
            f'<tr><td>{esc(w["last"])}</td><td>{esc(w["this"])}</td><td class="num">{pct(w["top"])}</td>'
            f'<td class="num">{pct(w["bottom"])}</td><td class="num">{w["n_top"]} v {w["n_bottom"]}</td>'
            f'<td>{"Top beat bottom" if w["beat"] else ("Level" if w["tie"] else "Bottom beat top")}</td></tr>'
            for w in p["weeks"])
        weeks = ('<div class="tbl"><table><tr><th>Ranked in</th><th>Tested in</th><th class="num">Top quarter reached 2x</th>'
                 '<th class="num">Bottom quarter reached 2x</th><th class="num">Contracts</th><th>Result</th></tr>'
                 f'{body}</table></div>')
    else:
        weeks = (f'<p class="sm mut">No week can be tested yet: it needs {L.WEEK_ENTITIES_MIN}+ entities with '
                 f'{L.WEEK_MIN}+ verified contracts in a week, then the next week to read them on.</p>')
    return f'{verdict}{rec}{weeks}'


def watching_table(stats):
    if not stats:
        return '<p class="sm mut">Nothing is waiting.</p>'
    body = "".join(
        f'<tr><td>{breakdown(s)}</td><td>{esc(s["sport"])}</td><td class="num">{s["n"]}</td><td class="num">{s["events"]}</td>'
        f'<td class="num">{pct(s["r2"])}</td><td class="num">{pct(s["r3"])}</td><td class="num">{pct(s["split"], True)}</td>'
        f'<td class="num">{max(0, L.MIN_CONTRACTS - s["n"])} / {max(0, L.MIN_EVENTS - s["events"])}</td></tr>'
        for s in stats)
    return ('<div class="tbl"><table><tr><th>Name</th><th>Sport</th><th class="num">Contracts</th><th class="num">Events</th>'
            '<th class="num">Reached 2x</th><th class="num">Reached 3x</th><th class="num">Split ROI</th>'
            f'<th class="num">Still needs (contracts / events)</th></tr>{body}</table></div>')


def method_block(b, skipped, unmapped):
    left = "".join(f"<li>{esc(k)}: {v}</li>" for k, v in sorted(skipped.items())) or "<li>Nothing.</li>"
    miss = "".join(f"<li>{esc(k)}: {v}</li>" for k, v in sorted(unmapped.items())) or "<li>Nothing.</li>"
    return (
        '<details class="lb-fold"><summary>How it\'s measured</summary><div class="sm">'
        '<p><b>Contract.</b> One cheap entry from a ledger the Edge Machine already keeps: the NBA moneyline underdog, team total '
        'and win margin trackers, spreads (including the Comeback line), the tennis and college football chaos lanes, the '
        'over 3.5 cheap NO bids, and the WTI, gas, album, mentions and fight lanes. Only entries whose ask was real count: '
        'the lane\'s own ask check, or the same test (10+ contracts traded at or under the ask in the hour after the entry) '
        'on a tracker row. Dead fills and open markets are left out.</p>'
        '<p><b>Reached 2x / 3x.</b> The share of contracts whose traded price hit twice (three times) the entry. Fair is 50% '
        '(33%). Split ROI is half sold at 2x and half at 3x on trade prints, after fees; hold ROI keeps the contract to the '
        'end. Traded at 2x+ is the median contracts that changed hands at 2x or better, where the source records it.</p>'
        f'<p><b>Score.</b> Reached-2x minus 50%, shrunk toward the average of that sport and market type with a prior worth '
        f'{L.PRIOR_N} contracts, so 3 for 3 cannot top the board. A name ranks only with {L.MIN_CONTRACTS}+ verified contracts '
        f'across {L.MIN_EVENTS}+ events; the rest are Watching.</p>'
        '<p><b>Holds up?</b> Reached-2x in the name\'s older half of events v its newer half; ✅ when both beat fair.</p>'
        '<p><b>Names.</b> NBA by the team in the ticker; a match contract (over 3.5) counts for both teams and is marked '
        'match; tennis and college football by the code in the ticker (Kalshi does not give a name in the ledgers); '
        'commodities by WTI and AAA gas; Trump for the mentions lanes; the fighter for fights. No cheap-side crypto ledger '
        'exists yet, so no crypto name can appear.</p>'
        f'<p>Left out of {b["contracts"]} counted contracts:</p><ul>{left}</ul><p>Could not be named:</p><ul>{miss}</ul>'
        '<p>The NBA win margin rows from Oct 20-29 are the data that lane was chosen on, so they flatter its names; the '
        'lane\'s own record starts on Oct 30.</p>'
        '<p>The win margin tracker clears a row\'s price path after three nights, so older rows can be checked only if '
        'they were stamped before that; from now on each row is stamped while its path is kept.</p></div></details>')


def build(contracts=None, skipped=None, unmapped=None, now=None):
    now = SP.as_utc(now)
    if contracts is None:
        contracts, skipped, unmapped = L.collect_all()
    skipped, unmapped = skipped or {}, unmapped or {}
    b = L.board(contracts)
    ranked, watching = b["ranked"], b["watching"]
    sports = "".join(
        f'<h3 id="sport-{esc(sp.lower())}">{esc(sp)}</h3>'
        + table(b["by_sport"][sp], f"No {sp} name has {L.MIN_CONTRACTS} verified contracts across {L.MIN_EVENTS} events yet.")
        for sp in L.SPORTS)
    pills = '<nav class="toc" aria-label="Sport">' + '<a href="#top">All</a>' + "".join(
        f'<a href="#sport-{esc(sp.lower())}">{esc(sp)}</a>' for sp in L.SPORTS) + "</nav>"
    body = (
        '<section id="persistence"><h1>Leaderboard</h1>'
        '<p class="lede">The teams, players and assets whose cheap contracts keep spiking. Paper only, read from the '
        'ledgers the trackers already write.</p>'
        f'{persistence_block(b["persistence"])}</section>'
        f'<section id="top"><h2>Top 10</h2><p class="sm">{len(ranked)} ranked, {len(watching)} watching, out of '
        f'{b["entities"]} names and {b["contracts"]} verified contracts.</p>{pills}'
        + table(b["top"], f"Nothing ranks yet: a name needs {L.MIN_CONTRACTS} verified contracts across {L.MIN_EVENTS} events. "
                          "The closest are under Watching.") + '</section>'
        f'<section id="sports"><h2>By sport</h2>{sports}</section>'
        f'<section id="bottom"><h2>Bottom 5</h2><p class="sm">Ranked names whose cheap contracts die most.</p>'
        + table(b["bottom"], "Needs more than ten ranked names before a bottom list is separate from the top.") + '</section>'
        f'<section id="watching"><h2>Watching (too few yet)</h2>{watching_table(watching)}</section>'
        f'<section id="method">{method_block(b, skipped, unmapped)}</section>')
    html = C.document(TITLE, DESCRIPTION, KEY, SECTIONS, C.stamp(now), body,
                      script_src="./site.js", scripts=("./tables.js",))
    import sandbox_build
    return sandbox_build.label_cells(html)


def main():
    out = os.path.join(L.ROOT, "public_site", "leaderboard.html")
    with open(out, "w") as f:
        f.write(build())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
