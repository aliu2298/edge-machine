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
DESCRIPTION = ("The teams, players and assets the Edge Machine's active lanes win and lose most on, then every settled bet "
               "in its own rules, retired lanes included.")
SECTIONS = (("active", "Active lanes"), ("superpack", "Superpack"), ("top", "All lanes"), ("detail", "Cheap-contract spike detail"))
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
        '<details class="lb-fold"><summary>How the spike board is measured</summary><div class="sm">'
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


def money(v):
    return f"{'+' if v >= 0 else '-'}${abs(v):,.2f}"


PROFIT_COLS = ("#", "Name", "Sport", "Bets", "Won", "Profit", "ROI", "Profitable weeks", "Lanes")


def lanes_cell(lanes):
    shown = ", ".join(esc(x) for x in lanes[:3])
    return shown + (f" +{len(lanes) - 3}" if len(lanes) > 3 else "")


def profit_table(stats):
    if not stats:
        return f'<p class="sm mut">No name has {L.MIN_BETS} settled bets yet.</p>'
    mark = ' <span class="mut">match</span>'
    body = "".join(
        f'<tr><td class="num">{i}</td><td>{esc(s["name"])}{mark if s["matches"] else ""}</td>'
        f'<td>{esc(s["sport"])}</td><td class="num">{s["n"]}</td><td class="num">{pct(s["won"])}</td>'
        f'<td class="num">{money(s["profit"])}</td><td class="num">{pct(s["roi"], True)}</td>'
        f'<td class="num">{s["good_weeks"]} of {s["weeks"]}</td><td>{lanes_cell(s["lanes"])}</td></tr>'
        for i, s in enumerate(stats, 1))
    head = "".join(f"<th>{c}</th>" if c in ("Name", "Sport", "Lanes") else f'<th class="num">{c}</th>' for c in PROFIT_COLS)
    return f'<div class="tbl"><table><tr>{head}</tr>{body}</table></div>'


def persistence_line(p):
    n, k = p["tested"], p["beats"]
    share = f" ({k / n * 100:.0f}%)" if n else ""
    rule = (f"Proven means {L.PROOF_WEEKS}+ weeks tested and the top quarter of names beating the bottom quarter "
            f"clearly above chance (one-sided binomial p under {L.PROOF_P}, about 8 of 10).")
    if p["proven"]:
        return (f"Last week's most profitable names beat the least profitable the next week in {k} of {n} weeks{share}: "
                f"proven (p = {p['p']:.3f}). {rule}")
    return (f"Last week's most profitable names beat the least profitable the next week in {k} of {n} weeks{share}: "
            f"not proven. {rule} Earlier work found hot teams do not stay hot.")


ACTIVE_COLS = ("#", "Name", "Sport", "Bets", "Won", "Profit at $1 after fees", "ROI", "Profitable weeks", "Lanes")


def marked_lanes(marks):
    """Each lane with its stage, Production first: "sr · P" style marks, at most four shown."""
    tag = {"Production": "P", "Sandbox": "S"}
    order = sorted(marks, key=lambda m: (m[1] != "Production",))
    shown = ", ".join(f'{esc(ln)} <span class="{"pos" if st == "Production" else "mut"}">{tag[st]}</span>' for ln, st in order[:4])
    return shown + (f" +{len(order) - 4}" if len(order) > 4 else "")


def active_table(stats, empty):
    """The active-lanes table. An ROI on fewer than L.GREY_UNDER settled bets is greyed, as on the Production page."""
    if not stats:
        return f'<p class="sm mut">{esc(empty)}</p>'
    mark = ' <span class="mut">match</span>'
    body = "".join(
        f'<tr><td class="num">{i}</td><td>{esc(s["name"])}{mark if s["matches"] else ""}</td>'
        f'<td>{esc(s["sport"])}</td><td class="num">{s["n"]}</td><td class="num">{pct(s["won"])}</td>'
        f'<td class="num">{money(s["profit"])}</td>'
        f'<td class="num">{pct(s["roi"], True) if s["n"] >= L.GREY_UNDER else f"<span class=\"mut\">{pct(s["roi"], True)}</span>"}</td>'
        f'<td class="num">{s["good_weeks"]} of {s["weeks"]}</td><td>{marked_lanes(s["lane_marks"])}</td></tr>'
        for i, s in enumerate(stats, 1))
    head = "".join(f"<th>{c}</th>" if c in ("Name", "Sport", "Lanes") else f'<th class="num">{c}</th>' for c in ACTIVE_COLS)
    return f'<div class="tbl"><table class="lb-active"><tr>{head}</tr>{body}</table></div>'


def active_section(ab):
    return (
        '<section id="active"><h1>Leaderboard</h1>'
        '<p class="lede">The teams, players and assets the Edge Machine\'s active lanes win and lose most on.</p>'
        f'<p class="sm"><b>Active lanes only.</b> Every settled bet from a lane that is active now: the Production pairs and '
        f'the Sandbox lanes still taking entries ({ab["bets"]:,} bets, {ab["lanes"]} lanes, {ab["production"]} of them in '
        f'Production). Retired lanes, baselines, tipster and copy sources and tracker rows are left out ({ab["left_out"]:,} '
        f'bets); each lane\'s status is the one its page and the Sandbox stamp table show. A name needs {L.ACTIVE_MIN_BETS}+ '
        f'settled bets ({ab["qualified"]} of {ab["names"]} do), since active lanes are young; an ROI on fewer than '
        f'{L.GREY_UNDER} is greyed. Profit is at $1 a bet, after fees. P marks a Production lane, S a Sandbox one.</p>'
        f'<h2>Top {L.ACTIVE_TOP}</h2>'
        + active_table(ab["top"], f"No name has {L.ACTIVE_MIN_BETS} settled bets from active lanes yet.")
        + f'<h2>Bottom {L.ACTIVE_BOTTOM}</h2><p class="sm">The names the active lanes are losing on, from the names not in the '
          'top list.</p>'
        + active_table(ab["bottom"], f"Needs more than {L.ACTIVE_TOP} qualifying names before a bottom list is separate.")
        + f'<p class="sm">{persistence_line(ab["persistence"])} Counted on active-lane bets only, so this view is descriptive, '
          'not a pick list.</p></section>')


def _sp_row(name, r, status_text, anchor=None):
    roi = pct(r["roi"], True) if r["settled"] else "pending"
    if r["settled"] and r["settled"] < L.GREY_UNDER:
        roi = f'<span class="mut">{roi}</span>'
    return (f'<tr{f" data-lane={chr(34)}{anchor}{chr(34)}" if anchor else ""}><td><b>{esc(name)}</b></td><td class="num">{r["entries"]}</td>'
            f'<td class="num">{r["open"]}</td><td class="num">{r["settled"]}</td><td class="num">{r["won"]}</td>'
            f'<td class="num">{money(r["profit"]) if r["settled"] else "—"}</td><td class="num">{roi}</td><td>{esc(status_text)}</td></tr>')


def superpack_section(state=None, persistence=None):
    """Superpack's card (2026-11-05, Olu): the registration, its record beside the two baselines, the persistence note,
    and its latest entries with the top 10 each was chosen on. Paper only. Never breaks the page."""
    import superpack as SPK
    try:
        state = state if state is not None else SPK.load()
    except Exception:                                           # noqa: BLE001
        return '<section id="superpack"><h2>Superpack</h2><p class="sm mut">Its ledger could not be read on this run.</p></section>'
    r, a, m = SPK.record(state["entries"]), SPK.record(state["pool"]), SPK.record(state["mirror"])
    since = state.get("since")
    rows = (_sp_row("Superpack · top 10 names", r, SPK.status(r["settled"]), SPK.LANE)
            + _sp_row("Baseline (a) · every active-lane bet", a, "baseline, not a lane")
            + _sp_row("Baseline (b) · the bottom 10, same copy rule", m, "baseline, not a lane"))
    latest = sorted(state["entries"], key=lambda e: (e.get("logged") or "", e["id"]), reverse=True)[:10]
    trs = "".join(
        f'<tr><td>{esc(", ".join(e["matched"]))}</td><td>{esc(e["sport"])}</td><td>{esc(e["lane"])}</td>'
        f'<td>{esc(str(e.get("side") or "").upper())} at {pct(e.get("price"))}</td><td>{esc(str(e.get("logged") or "")[:16].replace("T", " "))}</td>'
        f'<td>{esc(str((e.get("snapshot") or {}).get("as_of") or "")[:16].replace("T", " "))}</td>'
        f'<td>{esc(e["status"])}{"" if e["profit"] is None else " · " + money(e["profit"])}</td></tr>' for e in latest)
    entries = ('<div class="tbl"><table class="superpack-entries"><tr><th>Top-10 name</th><th>Sport</th><th>Copied lane</th>'
               '<th>Side and ask</th><th>Logged (UTC)</th><th>Top 10 as of</th><th>Status</th></tr>' + trs + '</table></div>'
               if latest else '<p class="sm mut">No entry yet: it copies only bets logged after its first run'
               + (f' ({esc(since[:16].replace("T", " "))} UTC)' if since else '') + '.</p>')
    note = f'<p class="sm">{persistence_line(persistence)}</p>' if persistence else ""
    return (
        f'<section id="superpack"><h2>{esc(SPK.LABEL)}</h2>'
        '<p class="sm"><b>Sandbox · paper · not in Production and in no feed.</b> '
        f'Pre-registered {esc(SPK.REGISTERED)}, before it logged anything; fresh record from its first entry.</p>'
        f'<p class="sm">{esc(SPK.RULE)}</p>'
        '<p class="sm">Judged against two baselines logged by the same rule from the same start: (a) every active-lane '
        'bet, every name, the main comparison, so Superpack counts only if the top-10 names beat the lanes\' own average; '
        '(b) the bottom 10, a mirror test.</p>'
        f'<p class="sm"><b>Weakness.</b> {esc(SPK.WEAKNESS)}</p>'
        '<div class="tbl"><table class="superpack-record"><tr><th>Row</th><th class="num">Entries</th><th class="num">Open</th>'
        '<th class="num">Settled</th><th class="num">Won</th><th class="num">Profit at $1 after fees</th><th class="num">ROI</th>'
        f'<th>Status</th></tr>{rows}</table></div>{note}'
        f'<h3>Latest entries</h3>{entries}'
        f'<p class="sm mut">{len(state.get("skips") or [])} bets skipped because active lanes were on both sides of the same '
        'contract. A copied bet settles on the copied lane\'s own per-$1 result, after its fees.</p></section>')


def superpack_index_row(state=None):
    """Superpack's row in the Sandbox's lane index (chaos_build.index's columns)."""
    import superpack as SPK
    state = state if state is not None else SPK.load()
    r = SPK.record(state["entries"])
    return (f'<tr data-lane="{SPK.LANE}"><td><b>{esc(SPK.LABEL)}</b></td><td><a href="./leaderboard.html#superpack">Leaderboard</a></td>'
            f'<td class="num">{r["entries"]}</td><td class="num">{r["settled"]}</td><td class="num">{r["won"]}</td>'
            f'<td class="num">{pct(r["roi"], True) if r["settled"] else "—"}</td><td class="num">—</td><td>{esc(SPK.status(r["settled"]))}</td></tr>')


def tipster_list():
    return ", ".join(sorted(L.TIPSTER_SOURCES))


def close_table(stats):
    if not stats:
        return '<p class="sm mut">Nobody has 5-9 settled bets.</p>'
    return profit_table(stats)


def spike_fold(b, skipped, unmapped):
    ranked, watching = b["ranked"], b["watching"]
    sports = "".join(
        f'<h4 id="sport-{esc(sp.lower())}">{esc(sp)}</h4>'
        + table(b["by_sport"][sp], f"No {sp} name has {L.MIN_CONTRACTS} verified contracts across {L.MIN_EVENTS} events yet.")
        for sp in L.SPORTS)
    return (
        '<details class="lb-fold"><summary>Cheap-contract spike detail</summary>'
        "<p class=\"sm\">How often a name's cheap contracts (priced 5-35c) traded up to twice and three times their entry, "
        'from the verified cheap-side entries. A different question from profit: it describes where spikes happened.</p>'
        f'{persistence_block(b["persistence"])}'
        f'<h3>Top 10 by spike rate</h3><p class="sm">{len(ranked)} ranked, {len(watching)} watching, out of {b["entities"]} '
        f'names and {b["contracts"]} verified contracts.</p>'
        + table(b["top"], f"Nothing ranks yet: a name needs {L.MIN_CONTRACTS} verified contracts across {L.MIN_EVENTS} events.")
        + f'<h3>By sport</h3>{sports}<h3>Bottom 5</h3>'
        + table(b["bottom"], "Needs more than ten ranked names before a bottom list is separate from the top.")
        + f'<h3>Watching (too few yet)</h3>{watching_table(watching)}{method_block(b, skipped, unmapped)}</details>')


def build(bets=None, contracts=None, skipped=None, unmapped=None, now=None, bet_skipped=None):
    now = SP.as_utc(now)
    if bets is None:
        bets, bet_skipped, unmapped, contracts, skipped = L.collect_bets()
    bet_skipped, skipped, unmapped = bet_skipped or {}, skipped or {}, unmapped or {}
    pb = L.profit_board(bets)
    ab = L.active_board(bets, now=now)
    b = L.board(contracts or [])
    left = "; ".join(f"{esc(k)} {v}" for k, v in sorted({**bet_skipped, **unmapped}.items())) or "nothing"
    body = (
        active_section(ab)
        + superpack_section(persistence=ab["persistence"])
        + '<section id="top"><h2>All lanes</h2>'
        '<p class="lede">The teams, players and assets that made the Edge Machine\'s own rules the most paper profit.</p>'
        f'<p class="sm"><b>Edge Machine rules only.</b> Top {L.TOP_BETS} of {pb["qualified"]} names with {L.MIN_BETS}+ settled bets, from '
        f'every settled bet in every rule lane, Production and Sandbox, <b>retired lanes included</b> ({pb["bets"]:,} bets, '
        f'{pb["lanes"]} lanes). Tipster and copy sources are left out of this view ({esc(tipster_list())}); the second view adds '
        'them. Profit is in dollars at $1 a bet, after fees, as each lane computes it. A match bet (an over, both teams to score) '
        'counts for both teams and is marked match. Tracker rows that are not bets are left out.</p>'
        + profit_table(pb["top"])
        + f'<p class="sm">{persistence_line(pb["persistence"])}</p>'
        + f'<details class="lb-fold"><summary>Including tipster lanes</summary><p class="sm">Top {L.TOP_BETS} of {pb["qualified_all"]} names '
          f'with {L.MIN_BETS}+ settled bets, adding {pb["tipster_bets"]:,} bets from the tipster and copy sources '
          f'({esc(tipster_list())}).</p>{profit_table(pb["with_tipsters"])}</details>'
        + f'<details class="lb-fold"><summary>Close to qualifying ({L.CLOSE_MIN}-{L.MIN_BETS - 1} settled bets)</summary>'
          f'{close_table(pb["close"])}</details>'
        + '<p class="sm mut">Names: the team or player on the bet; a coin or commodity from its market series (AAA gas, WTI, '
          'gold, Bitcoin); Trump for mentions; the index for finance markets; the title for Rotten Tomatoes. '
          f'Not counted: {left}.</p></section>'
        + f'<section id="detail">{spike_fold(b, skipped, unmapped)}</section>')
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
