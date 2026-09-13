#!/usr/bin/env python3
"""record_build.py — every measured result in one place: public_site/record.html.

WHY IT IS ITS OWN PAGE
----------------------
The numbers were split across boards — the leads' record sat behind a tab on Streaks,
and the fire runs were measured in a file nobody opened. Each page showed a slice and none
showed the answer. Since whether any of this works is the only question that matters, it
gets its own page rather than a footnote on two others.

The 3-card slate that used to head this page was retired on 2026-09-12: it only ever
re-drew three of the leads already measured below, so its 28 graded picks were a strict
subset of the leads ledger and its section added a second, smaller read of the same
evidence.

WHAT IS MEASURED, AND AGAINST WHAT
----------------------------------
The lift sections carry no odds and are not profit. They compare a hit rate against **what
the teams involved manage anyway**:

  * leads -> the named side's own rate (or the two sides' mean for a fixture-level
    outcome). A league average would credit the lead for team quality — measured, that
    inflated "team to score" from -1.5pp to +9.3pp.
  * fire runs -> NOTHING. There is no honest baseline for a streak, so the fire section
    shows the ledger descriptively and puts significance in a separate permutation test.
    Three baselines were tried and all three were wrong; see fire_track's docstring.

LIFT IS THE NUMBER where a reference exists. A hit rate on its own is unreadable, and
three lanes in this repo have already died from being read without a reference.

The PRICED section (added 2026-09-12) is the one place profit is measured: every lead is
graded at a flat 1 unit on the Bovada line captured the first build it was listed, on
three pre-registered markets. Its yardstick is the book's vig-free probability.

Usage:  python3 record_build.py   →  public_site/record.html
"""
import os, html, datetime

import streaks_fetch
import streaks_track as T
import fire_track as F
import book_track as K

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(ROOT, "public_site")

BET_NAME = {
    "btts": "Both teams to score", "total_gte:3": "Over 2.5 goals",
    "total_gte:2": "Over 1.5 goals", "total_lte:2": "Under 2.5 goals",
    "team_gte:2": "Team to score 2+", "team_gte:1": "Team to score",
    "team_eq:0": "Team to fail to score",
}


def esc(x):
    return html.escape(str(x if x is not None else ""))


def pct(x, dp=0):
    return "—" if x is None else f"{x*100:.{dp}f}%"


def lift_cell(v):
    if v is None:
        return '<td class="num mut">—</td>'
    cls = "pos" if v >= 0 else "neg"
    return f'<td class="num {cls}">{"+" if v >= 0 else ""}{v*100:.1f}pp</td>'


def perf_table(rows, label_of, base_head="team base"):
    if not rows:
        return ""
    body = "".join(
        f"""<tr><td>{esc(label_of(r))}</td>
        <td class="num">{r['n']}</td>
        <td class="num">{r.get('hits', r.get('extended'))}</td>
        <td class="num">{pct(r['rate'])}</td>
        <td class="num mut" title="{esc('league avg ' + pct(r['league_base'])) if r.get('league_base') is not None else ''}">{pct(r['base'])}</td>
        {lift_cell(r['lift'])}
        <td><span class="sig {'y' if r['significant'] else 'n'}">
          {'SIGNIFICANT' if r['significant'] else 'not sig'}</span></td></tr>"""
        for r in rows)
    return f"""<div class="tbl"><table>
<tr><th>Market</th><th class="num">n</th><th class="num">hits</th><th class="num">rate</th>
    <th class="num">{esc(base_head)}</th><th class="num">lift</th><th></th></tr>
{body}</table></div>"""


def price_table(rows):
    if not rows:
        return ""
    body = "".join(
        f"""<tr><td>{esc(r['label'])}{' <span class="mut">· a lane\'s own claim</span>' if r['market'] in ('over15', 'team2plus') else ''}</td>
        <td class="num">{r['n']}</td>
        <td class="num">{r['hits']}</td>
        <td class="num">{pct(r['rate'])}</td>
        <td class="num mut">{r['avg_price']:.2f}</td>
        <td class="num mut" title="hit rate needed to break even at the average price">{pct(r['breakeven'])}</td>
        <td class="num mut" title="the book's own probability, vig removed">{pct(r['fair'])}</td>
        {lift_cell(r['lift'])}
        <td class="num {'pos' if r['roi'] >= 0 else 'neg'}">{'+' if r['roi'] >= 0 else ''}{r['roi']*100:.1f}%</td>
        <td><span class="sig {'y' if r['significant'] else 'n'}">
          {'SIGNIFICANT' if r['significant'] else 'not sig'}</span></td></tr>"""
        for r in rows)
    return f"""<div class="tbl"><table>
<tr><th>Market</th><th class="num">n</th><th class="num">hits</th><th class="num">rate</th>
    <th class="num">avg price</th><th class="num">break-even</th><th class="num">book fair</th>
    <th class="num">lift v book</th><th class="num">ROI</th><th></th></tr>
{body}</table></div>"""


def model_tables(mr):
    if not mr["rows"]:
        return "", ""
    brier = "".join(
        f"""<tr><td>{esc(r['label'])}</td><td class="num">{r['n']}</td>
        <td class="num">{pct(r['actual'])}</td>
        <td class="num mut">{pct(r['model_avg'])}</td><td class="num mut">{pct(r['book_avg'])}</td>
        <td class="num">{r['brier_model']:.4f}</td><td class="num">{r['brier_book']:.4f}</td>
        <td><span class="sig {'y' if r['model_better'] else 'n'}">
          {'MODEL AHEAD' if r['model_better'] else 'book ahead'}</span></td></tr>"""
        for r in mr["rows"])
    brier_t = f"""<div class="tbl"><table>
<tr><th>Market</th><th class="num">n</th><th class="num">actual</th><th class="num">model avg</th>
    <th class="num">book fair</th><th class="num">Brier model</th><th class="num">Brier book</th><th></th></tr>
{brier}</table></div>"""

    def cell(g):
        if not g["n"]:
            return '<td class="num mut">—</td><td class="num mut">—</td><td class="num mut">—</td>'
        cls = "pos" if g["roi"] >= 0 else "neg"
        return (f'<td class="num">{g["n"]}</td><td class="num">{pct(g["rate"])}</td>'
                f'<td class="num {cls}">{"+" if g["roi"] >= 0 else ""}{g["roi"]*100:.1f}%</td>')
    value = "".join(
        f"""<tr><td>{esc(r['label'])}</td>{cell(r['value'])}{cell(r['rest'])}</tr>"""
        for r in mr["rows"])
    value_t = f"""<div class="tbl"><table>
<tr><th>Market</th><th class="num">value n</th><th class="num">hit</th><th class="num">ROI</th>
    <th class="num">rest n</th><th class="num">hit</th><th class="num">ROI</th></tr>
{value}</table></div>"""
    return brier_t, value_t


def book_tables(bk):
    """The book on every fixture: by market, league, venue, price band; the value
    split; and the teams past the floor. z is the number to read (see book_track)."""
    def zcell(z):
        cls = "pos" if z >= 0 else "neg"
        return f'<td class="num {cls}">{z:+.2f}</td>'

    def roicell(v):
        cls = "pos" if v >= 0 else "neg"
        return f'<td class="num {cls}">{"+" if v >= 0 else ""}{v*100:.1f}%</td>'

    def seg_rows(rows, label_of):
        return "".join(
            f"""<tr><td>{esc(label_of(r))}</td><td class="num">{r['n']}</td>
            <td class="num">{pct(r['rate'])}</td><td class="num mut">{pct(r['fair'])}</td>
            <td class="num">{r['excess']:+.1f}</td>{zcell(r['z'])}{roicell(r['roi'])}</tr>"""
            for r in rows)
    head = ('<tr><th>{}</th><th class="num">n</th><th class="num">hit</th>'
            '<th class="num">book fair</th><th class="num">excess</th><th class="num">z</th>'
            '<th class="num">ROI</th></tr>')
    tbl = lambda label, rows, lo: (f'<div class="tbl"><table>{head.format(label)}'
                                  f'{seg_rows(rows, lo)}</table></div>') if rows else ""
    market_t = tbl("Market", bk["by_market"], lambda r: r["label"])
    league_t = tbl("League", bk["by_league"], lambda r: r["league"])
    band_t = tbl("Book fair prob", bk["bands"],
                 lambda r: f"{r['lo']*100:.0f}–{r['hi']*100:.0f}%")
    brier = "".join(
        f"""<tr><td>{esc(r['label'])}</td><td class="num">{r.get('n_model', 0)}</td>
        <td class="num">{r['brier_model']:.4f}</td><td class="num">{r['brier_book']:.4f}</td>
        <td><span class="sig {'y' if r['model_better'] else 'n'}">
          {'MODEL AHEAD' if r['model_better'] else 'book ahead'}</span></td></tr>"""
        for r in bk["by_market"] if r.get("n_model"))
    brier_t = (f'<div class="tbl"><table><tr><th>Market</th><th class="num">n</th>'
               f'<th class="num">Brier model</th><th class="num">Brier book</th><th></th></tr>'
               f'{brier}</table></div>') if brier else ""
    vr = []
    for label, g in (("Value (model ≥ book + %dpp)" % round(bk["margin"] * 100), bk["value"]),
                     ("Rest", bk["rest"])):
        if g:
            vr.append(dict(g, label=label))
    value_t = tbl("Model v book", vr, lambda r: r["label"])
    teams = bk["paying"] or bk["top_teams"]
    team_rows = "".join(
        f"""<tr><td>{esc(t)}{' <span class="sig y">PAYING</span>' if a['paying'] else ''}</td>
        <td class="num">{a['n']}</td><td class="num">{pct(a['rate'])}</td>
        <td class="num mut">{pct(a['fair'])}</td><td class="num">{a['excess']:+.1f}</td>
        {zcell(a['z'])}{roicell(a['roi'])}</tr>"""
        for t, a in teams)
    team_t = (f'<div class="tbl"><table>{head.format("Team")}{team_rows}</table></div>'
              if team_rows else
              f'<div class="note">No team has reached the floor of {bk["team_floor"]} '
              f'priced observations yet ({bk["teams_tested"]} teams tested so far).</div>')
    return market_t, league_t, band_t, brier_t, value_t, team_t


def fire_tables(fr):
    """Ledger and test, rendered apart on purpose.

    They are different samples answering different questions, and the reason the fire
    numbers were wrong twice is that a settled-run count was read as if it were evidence.
    The ledger gets no lift column and no verdict; only the test carries a verdict.
    """
    led = "".join(
        f"""<tr><td>{esc(r['label'])}</td><td class="num">{r['n']}</td>
        <td class="num">{r['extended']}</td><td class="num">{pct(r['rate'])}</td></tr>"""
        for r in fr["rows"])
    ledger = f"""<div class="tbl"><table>
<tr><th>Streak</th><th class="num">n</th><th class="num">extended</th>
    <th class="num">rate</th></tr>{led}</table></div>""" if led else ""

    tst = "".join(
        f"""<tr><td>{esc(t['label'])}</td><td class="num">{t['teams']}</td>
        <td class="num">{t['on_n']}/{t['off_n']}</td>
        {lift_cell(t['diff'])}
        <td class="num mut">{t['null_lo']*100:+.0f} to {t['null_hi']*100:+.0f}pp</td>
        <td class="num mut">{t['p_adj']:.2f}</td>
        <td><span class="sig {'y' if t['significant'] else 'n'}">
          {'SIGNIFICANT' if t['significant'] else 'no result'}</span></td></tr>"""
        for t in fr.get("test", []))
    test = f"""<div class="tbl"><table>
<tr><th>Streak</th><th class="num">teams</th><th class="num">on/off</th>
    <th class="num">diff</th><th class="num">shuffled 95%</th>
    <th class="num">p adj</th><th></th></tr>{tst}</table></div>""" if tst else ""
    return ledger, test


def tiles(pairs):
    return ('<div class="tiles">' + "".join(
        f'<div class="tile"><b>{esc(v)}</b><span>{esc(k)}</span></div>'
        for k, v in pairs) + '</div>')


def page_html(ld, fr, bk, now):
    def section(title, blurb, rep, rows_html, empty):
        if not rep["graded"]:
            return f'<h2>{title}</h2><div class="note">{blurb}</div><div class="note">{empty}</div>'
        return f'<h2>{title}</h2><div class="note">{blurb}</div>{rows_html}'

    leads_body = tiles([("Graded", ld["graded"]), ("Hit rate", pct(ld["overall_rate"])),
                        ("Pending", ld["pending"]), ("Void", ld["void"])]) + \
        perf_table(ld["rows"], lambda r: BET_NAME.get(r["kind"], r["kind"]))
    pr = ld.get("priced") or {"rows": [], "graded": 0, "pending": 0, "claim_roi": None}
    lane = pr.get("lane_roi") or {}
    roi = lambda k: "—" if lane.get(k) is None else f"{lane[k]*100:+.1f}%"
    priced_body = tiles([("Settled at a price", pr["graded"]),
                         ("Over 1.5 lane ROI", roi("over15")),
                         ("Team 2+ lane ROI", roi("team2plus")),
                         ("Priced, pending", pr["pending"])]) + price_table(pr["rows"])
    priced_rep = {"graded": pr["graded"]}
    mr = ld.get("model") or {"rows": [], "graded": 0, "pending": 0, "margin": 0.05}
    brier_t, value_t = model_tables(mr)
    model_body = (tiles([("Scored, model v book", mr["graded"]),
                         ("Model ahead on", f"{sum(1 for r in mr['rows'] if r['model_better'])}"
                          f" of {len(mr['rows'])} markets" if mr["rows"] else "—"),
                         ("Pending, modelled", mr["pending"])]) + brier_t +
                  '<div class="note">Pre-registered value split: a lead is <b>value</b> when '
                  f'the model\'s probability beats the book\'s fair probability by '
                  f'<b>{mr["margin"]*100:.0f}pp</b> or more. If the model carries anything the '
                  'book does not, the value group should out-hit and out-earn the rest. '
                  'The margin was fixed before any of this settled.</div>' + value_t)
    model_rep = {"graded": mr["graded"]}
    ov = bk.get("overall") or {}
    market_t, league_t, band_t, brier_t, value_t, team_t = book_tables(bk) if ov else ("",) * 6
    book_body = (tiles([("Fixtures priced", bk["fixtures"]), ("Settled", bk["graded"]),
                        ("Observations", bk["observations"]),
                        ("Hit v book", f"{pct(ov.get('rate'))} v {pct(ov.get('fair'))}"),
                        ("z", f"{ov.get('z', 0):+.2f}"),
                        ("ROI", "—" if ov.get("roi") is None else f"{ov['roi']*100:+.1f}%")]) +
                 market_t +
                 '<div class="note"><b>By league.</b> A mispricing is far more likely to be '
                 'structural — a thin market, a shaded favourite — than a property of one '
                 'club, and a league pools dozens of teams, so this reads weeks before any '
                 'team row can.</div>' + league_t +
                 '<div class="note"><b>Calibration of the book.</b> Each band groups '
                 'observations by the probability the book implied; a well-priced book hits '
                 'at that rate in every band. Excess in a band is where the price is wrong '
                 'for everyone, not for one team.</div>' + band_t +
                 ('<div class="note"><b>Model v book, on every fixture</b> — the same test as '
                  'the section above, on a sample nobody hand-picked.</div>' + brier_t + value_t
                  if brier_t else '') +
                 f'<div class="note"><b>Teams.</b> Pooled across every priced market in a '
                 f'team\'s games (its own 2+ counts for it alone). A team is tagged '
                 f'<b>PAYING</b> only past <b>{bk["team_floor"]}</b> observations with '
                 f'<b>z ≥ {bk["team_z"]:.0f}</b> — and with <b>{bk["teams_tested"]}</b> teams '
                 f'tested, about {max(1, round(bk["teams_tested"] * 0.023))} would reach that by '
                 f'chance, so read the tag as a shortlist, not a verdict.</div>' + team_t)
    book_rep = {"graded": bk["graded"]}
    fire_led, fire_test = fire_tables(fr)
    fire_body = (tiles([("Graded", fr["graded"]), ("Extended", pct(fr["rate"])),
                        ("Pending", fr["pending"])]) + fire_led +
                 '<div class="note">Above is only a tally — it carries no verdict, because '
                 'a ledger of streaks contains no clean control. Below is the actual test: '
                 'for each team, its hit rate <b>while on a run</b> against its own rate '
                 '<b>while not</b>, compared to the same statistic computed on <b>'
                 f'{F.PERMUTATIONS} shuffles of that team\'s own games</b>. Shuffling '
                 'destroys the runs and '
                 'nothing else, so the shuffled band is what "no signal" looks like — and '
                 'it sits far below zero, because a run ends the moment it fails and the '
                 'games after one are pre-selected against. <b>Only a diff outside that '
                 'band means anything.</b></div>' + fire_test)

    # Every graded lead, newest first. This used to be the slate's settled picks; the
    # leads ledger is the superset, so it is the list shown now.
    hist = ld.get("recent") or []
    hist_rows = "".join(
        f"""<tr><td class="mut">{esc((p.get('kickoff') or p['date'])[:10])}</td>
        <td>{esc(p['match'])}</td><td>{esc(p['headline'])}</td>
        <td class="num">{esc(p.get('final') or '—')}</td>
        <td><span class="st {p['status']}">{esc(p['status'].upper())}</span></td></tr>"""
        for p in hist)

    return f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Edge Machine · Record</title>
<meta name="description" content="Every measured result, judged against what the teams involved do anyway.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
:root{{--bg:#0a0d14;--card:#10141d;--bd:#232936;--fg:#eef2f7;--mut:#8b94a7;
--pos:#3fb970;--neg:#e06c75;--warn:#f0b429;--acc:#7aa2f7}}
*{{box-sizing:border-box;margin:0}}
body{{background:var(--bg);color:var(--fg);font:15px/1.45 Inter,system-ui,sans-serif;
letter-spacing:-.011em;-webkit-font-smoothing:antialiased;padding:28px 16px 60px}}
.wrap{{max-width:920px;margin:0 auto}}
h1{{font-size:22px;font-weight:800;letter-spacing:-.02em}}
h2{{font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;
color:var(--mut);margin:34px 0 12px}}
.sub{{color:var(--mut);font-size:13px;margin-top:4px}}
.mut{{color:var(--mut)}}.pos{{color:var(--pos)}}.neg{{color:var(--neg)}}
.nav{{display:flex;gap:8px;margin-top:14px;flex-wrap:wrap}}
.nav a{{font-size:12px;font-weight:700;text-decoration:none;color:var(--mut);
border:1px solid var(--bd);border-radius:999px;padding:5px 13px}}
.nav a:hover{{color:var(--fg);border-color:var(--mut)}}
.nav a.on{{color:var(--fg);border-color:var(--mut);background:#161b26}}
.note{{font-size:12.5px;color:var(--mut);line-height:1.6;background:var(--card);
border:1px solid var(--bd);border-radius:10px;padding:12px 14px;margin-bottom:12px}}
.note b{{color:var(--fg);font-weight:600}}
.note.warn{{border-color:#f0b42944;background:#f0b4290a}}
.tiles{{display:flex;gap:9px;flex-wrap:wrap;margin-bottom:13px}}
.tile{{flex:1;min-width:100px;background:var(--card);border:1px solid var(--bd);
border-radius:10px;padding:11px 13px}}
.tile b{{display:block;font-size:19px;font-weight:800;font-variant-numeric:tabular-nums}}
.tile span{{font-size:11px;color:var(--mut)}}
.tbl{{background:var(--card);border:1px solid var(--bd);border-radius:11px;
overflow-x:auto;margin-bottom:13px}}
table{{width:100%;border-collapse:collapse;font-size:12.5px}}
th{{text-align:left;font-size:10px;text-transform:uppercase;letter-spacing:.07em;
color:var(--mut);padding:9px 11px;border-bottom:1px solid var(--bd);white-space:nowrap}}
td{{padding:9px 11px;border-bottom:1px solid #1a1f2b;white-space:nowrap}}
tr:last-child td{{border-bottom:none}}
.num{{font-variant-numeric:tabular-nums;text-align:right}}
.st,.sig{{font-size:9.5px;font-weight:800;letter-spacing:.05em;border-radius:999px;
padding:2px 7px;border:1px solid}}
.st.hit,.sig.y{{color:var(--pos);border-color:#3fb97055;background:#3fb97014}}
.st.miss{{color:var(--neg);border-color:#e06c7555;background:#e06c7514}}
.st.void,.sig.n{{color:var(--mut);border-color:var(--bd)}}
footer{{margin-top:40px;font-size:12px;color:var(--mut);text-align:center}}
@media (max-width:600px){{body{{padding:18px 10px 44px;font-size:14px}}h1{{font-size:19px}}}}
</style></head><body><div class="wrap">
<h1>Edge Machine · Record</h1>
<div class="sub">Everything that has been graded · all times CT · updated {esc(now)}</div>
<div class="nav"><a href="./">Leads</a>
<a href="./streaks.html">Streaks</a><a class="on" href="./record.html">Record</a>
<a href="./today.html">Today</a><a href="./sandbox.html">Sandbox</a><a href="./qa.html">QA</a></div>

<div class="note warn">The lift sections carry no odds and <b>are not profit</b>; the one
place money is measured is the priced section, which grades every lead at the Bovada line
captured when it was first listed. Everywhere else each rate is compared against
<b>what the teams involved manage anyway</b> — the named side's own rate for a claim about
one team, the two sides' mean for a fixture-level outcome. A league average would credit a
lead for team quality: measured here, that difference moved "team to score" from
<b>-1.5pp to +9.3pp</b>. On-fire runs get no baseline at all — three were tried and all
three were wrong, so that section is measured against a shuffled schedule instead.
<b>The reference is the number</b>; a rate alone is unreadable, and three lanes in this
repo have already died from being read without one.</div>

{section("Leads — every confluence published",
         "Every lead the Leads board has shown, graded on the final score once the "
         "fixture is played.",
         ld, leads_body,
         "Nothing graded yet.")}

{section("Leads at the price — does it pay?",
         "Flat 1 unit on every lead at the Bovada line captured the <b>first build it was "
         "listed</b> — never revised, never taken after kickoff. Three fixture-level "
         "markets are logged on every lead, fixed in advance, so no market is chosen "
         "after seeing which one paid; a <b>side to score 2+</b> lead is also priced on "
         "its own claim from the book's team total. Each lane is judged on its own claim. <b>Break-even</b> is the hit rate the average price "
         "demands; <b>book fair</b> is the probability the sportsbook itself implies with "
         "the vig stripped out — a real edge has to clear both, and on the day this was "
         "added over 1.5 traded at ~1.20, a break-even of 83% against leads that hit 82%.",
         priced_rep, priced_body,
         "Nothing settled at a price yet — pricing started 2026-09-12 and a lead counts "
         "only if it was priced before kickoff and has since been played.")}

{section("Model v book — is any estimate better than the price?",
         "Every streak rule here was measured against the teams' own rates and none "
         "lifted them, because a run is the noisiest estimate of a rate there is. The "
         "number that pays is against the <b>book</b>. So each priced lead also carries a "
         "<b>model</b> probability — independent Poissons on each side's shrunk attack and "
         "defence ratings (see model.py), logged at the same moment as the price and "
         "never revised — and both are scored on the leads that have since settled. "
         "<b>Brier</b> is the mean squared error of a probability: lower is better, and "
         "the only question that matters is whether the model's is lower than the book's.",
         model_rep, model_body,
         "Nothing scored yet — model probabilities started 2026-09-12, alongside prices.")}

{section("The book, on every fixture — who pays at the price?",
         "Every competitive fixture in the pull is priced once it is inside 24h of "
         "kickoff — whatever the form on either side — and graded on the final score. "
         "That makes it a calibration ledger for the <b>book</b> itself, with no "
         "selection by streak: hits against the hits the book's own vig-free "
         "probabilities predicted. <b>Excess</b> is hits minus expected; <b>z</b> is that "
         "in standard deviations, and it is the number to read — flat-stake ROI is shown "
         "for the money view, but at n=10 its standard deviation is about 24 points.",
         book_rep, book_body,
         "Nothing settled yet — the book ledger started 2026-09-12; fixtures are priced "
         "the day before kickoff and graded the day after.")}

{section("On fire — do long runs continue?",
         "Each long run logged against the fixture that tests it. The question is not "
         "whether a side on a hot run keeps scoring — it is whether they do it more than "
         "the same side does anyway, and more than a shuffled schedule would fake.",
         fr, fire_body,
         "Nothing graded yet.")}

{f'''<h2>Recently settled leads ({len(hist)})</h2>
<div class="tbl"><table>
<tr><th>Date</th><th>Match</th><th>Pick</th><th class="num">Final</th><th></th></tr>
{hist_rows}</table></div>''' if hist else ''}

<footer>Read-only static export · research, not betting advice.</footer>
</div></body></html>"""


def build():
    fixtures = streaks_fetch.load_or_fetch()["fixtures"]
    ld = T.report(fixtures)
    fr = F.report(fixtures)
    bk = K.report(K.load())
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%b %d %Y · %H:%M UTC")

    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, "record.html")
    with open(out, "w") as f:
        f.write(page_html(ld, fr, bk, now))
    print(f"wrote {out}  ({os.path.getsize(out)/1024:.0f} KB) — "
          f"leads {ld['graded']}, fire {fr['graded']}, book {bk['graded']} graded")


if __name__ == "__main__":
    build()
