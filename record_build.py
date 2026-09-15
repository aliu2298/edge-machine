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
graded at a flat 1 unit on the price captured the first build it was listed, on
three pre-registered markets — the Bovada line until 2026-09-13, the Kalshi or Polymarket US
ask plus taker fee since. Its yardstick is the book's fair probability (vig-free for Bovada,
the midpoint for an exchange).

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


def rule_change_html(rc):
    """The over-1.5 rule change: the published 9-of-10 rule against the retired run pairings."""
    if not rc:
        return ""
    def row(name, r):
        price = "—" if r["avg_price"] is None else f"{r['avg_price']:.2f}"
        roi = "—" if r["roi"] is None else f"{r['roi'] * 100:+.1f}%"
        return (f'<tr><td><b>{name}</b></td><td class="num">{r["graded"]}</td>'
                f'<td class="num">{pct(r["rate"])}</td><td class="num">{r["priced"]}</td>'
                f'<td class="num">{price}</td><td class="num">{roi}</td>'
                f'<td class="num">{r["pending"]}</td></tr>')
    return f"""<div class="note">On {esc(rc['since'])} the over-1.5 lane changed rule: both sides' games over 1.5
in <b>9+ of their last 10</b>, replacing the run pairings (both sides over 1.5, or both scoring, in
every recent game). The old rule still runs, unpublished, on the same fixtures, so the two are
compared on the same weeks at the same exchange prices. Only leads still on the board at
kickoff count. {rc['both']} fixture(s) were picked by both.</div>
<div class="tbl"><table><tr><th>Rule</th><th class="num">Graded</th><th class="num">Hit</th>
<th class="num">Priced</th><th class="num">Avg price</th><th class="num">ROI</th><th class="num">Pending</th></tr>
{row("9+ of last 10 (published)", rc["v2"])}{row("Run pairings (retired, shadow)", rc["v1"])}</table></div>"""


MIN_N = 30          # the same readability floor the Sandbox uses

GROUPS = [
    ("working", "Working", "ok", "30+ graded and ahead of its reference."),
    ("failing", "Not working", "bad", "30+ graded and not ahead of its reference — the market, the teams' own rate, or a shuffled schedule already explains it."),
    ("leaning", "Too early · leaning ahead", "", "Under 30 graded, ahead so far. Unreadable yet."),
    ("behind", "Too early · leaning behind", "", "Under 30 graded, behind so far."),
]


def _z(rate, base, n):
    if rate is None or base is None or not n or base <= 0 or base >= 1:
        return None
    return (rate - base) / (base * (1 - base) / n) ** 0.5


def findings(ld, fr, bk, rc):
    """Every measured result as one row, so the whole page can be sorted into working / not
    working / too early and ranked. Each row: area, test, n, result, reference, diff, z, roi,
    ahead (bool), sig (bool)."""
    out = []

    def add(area, test, n, result, ref, diff, z, roi, ahead, sig=None):
        out.append(dict(area=area, test=test, n=n, result=result, ref=ref, diff=diff, z=z, roi=roi,
                        ahead=ahead, sig=(abs(z) >= 2 if sig is None and z is not None else bool(sig))))

    for r in ld.get("rows") or []:
        z = _z(r["rate"], r["base"], r["n"])
        add("Leads", BET_NAME.get(r["kind"], r["kind"]), r["n"], pct(r["rate"]), f"{pct(r['base'])} teams' own",
            None if r["lift"] is None else f"{r['lift']*100:+.1f}pp", z, None, (r["lift"] or 0) > 0, r["significant"])
    for r in (ld.get("priced") or {}).get("rows") or []:
        z = _z(r["rate"], r["fair"], r["n"])
        add("Leads at the price", r["label"], r["n"], pct(r["rate"]), f"{pct(r['fair'])} market",
            f"{r['lift']*100:+.1f}pp", z, r["roi"], r["roi"] > 0 and r["lift"] > 0, r["significant"])
    if rc:
        for key, name in (("v2", "Over 1.5 · 9+ of last 10 (published)"), ("v1", "Over 1.5 · run pairings (retired, shadow)")):
            r = rc[key]
            add("Rule change", name, r["graded"], pct(r["rate"]), "same weeks, same prices",
                None, None, r["roi"], (r["roi"] or 0) > 0, False)
    for r in (ld.get("model") or {}).get("rows") or []:
        gap = r["brier_book"] - r["brier_model"]
        add("Model v book (leads)", r["label"], r["n"], f"Brier {r['brier_model']:.3f}", f"book {r['brier_book']:.3f}",
            f"{gap:+.3f}", None, None, r["model_better"], False)
    for r in bk.get("by_market") or []:
        add("Book · every fixture", r["label"], r["n"], pct(r["rate"]), f"{pct(r['fair'])} market",
            f"{r['excess']:+.1f} hits", r["z"], r["roi"], r["z"] > 0 and r["roi"] > 0)
        if r.get("n_model"):
            add("Model v book (every fixture)", r["label"], r["n_model"], f"Brier {r['brier_model']:.3f}",
                f"book {r['brier_book']:.3f}", f"{r['brier_book'] - r['brier_model']:+.3f}", None, None, r["model_better"], False)
    for r in bk.get("by_league") or []:
        add("Book · by league", r["league"], r["n"], pct(r["rate"]), f"{pct(r['fair'])} market",
            f"{r['excess']:+.1f} hits", r["z"], r["roi"], r["z"] > 0 and r["roi"] > 0)
    for r in bk.get("bands") or []:
        add("Book · by price", f"priced {r['lo']*100:.0f}–{r['hi']*100:.0f}%", r["n"], pct(r["rate"]), f"{pct(r['fair'])} market",
            f"{r['excess']:+.1f} hits", r["z"], r["roi"], r["z"] > 0 and r["roi"] > 0)
    for label, g in ((f"model ≥ book + {round(bk.get('margin', 0.05) * 100)}pp", bk.get("value")), ("the rest", bk.get("rest"))):
        if g:
            add("Book · model value split", label, g["n"], pct(g["rate"]), f"{pct(g['fair'])} market",
                f"{g['excess']:+.1f} hits", g["z"], g["roi"], g["z"] > 0 and g["roi"] > 0)
    for t, a in (bk.get("paying") or []) + (bk.get("top_teams") or []) + (bk.get("bottom_teams") or []):
        if any(x["area"] == "Book · by team" and x["test"] == t for x in out):
            continue
        add("Book · by team", t, a["n"], pct(a["rate"]), f"{pct(a['fair'])} market",
            f"{a['excess']:+.1f} hits", a["z"], a["roi"], a["z"] > 0 and a["roi"] > 0, a.get("paying"))
    for t in fr.get("test") or []:
        add("On fire", f"{t['label']} runs continue", t["on_n"], f"{t['diff']*100:+.1f}pp on v off",
            f"shuffled {t['null_lo']*100:+.0f} to {t['null_hi']*100:+.0f}pp", None, None, None,
            t["significant"] and t["diff"] > t["null_hi"], t["significant"])
    return out


def group_of(f):
    if f["n"] >= MIN_N:
        return "working" if f["ahead"] else "failing"
    return "leaning" if f["ahead"] else "behind"


def findings_table(fs):
    rows = {g[0]: [] for g in GROUPS}
    for f in fs:
        rows[group_of(f)].append(f)
    rank = lambda f: (-(f["z"] if f["z"] is not None else (f["roi"] if f["roi"] is not None else 0) * 10), -f["n"])
    body = []
    for g, title, klass, note in GROUPS:
        items = sorted(rows[g], key=rank) if g in ("working", "leaning") else sorted(rows[g], key=lambda f: tuple(-x for x in rank(f)))
        body.append(f'<tr class="grp {klass}" data-g="{g}"><td colspan="8">{esc(title)} · {len(items) or "none right now"}</td></tr>'
                    f'<tr data-g="{g}"><td colspan="8" class="mut sm">{esc(note)}</td></tr>')
        for n, f in enumerate(items, 1):
            thin = f["n"] < MIN_N
            zc = "—" if f["z"] is None else f'<span class="{"mut" if thin else ("pos" if f["z"] > 0 else "neg")}">{f["z"]:+.2f}</span>'
            roi = "—" if f["roi"] is None else f'<span class="{"mut" if thin else ("pos" if f["roi"] > 0 else "neg")}">{f["roi"]*100:+.1f}%</span>'
            badge = ' <span class="sig y">SIG</span>' if f["sig"] and not thin else ""
            body.append(f"""<tr data-g="{g}"><td class="num mut">{n}</td>
<td><b>{esc(f['test'])}</b>{badge}<div class="sm mut">{esc(f['area'])}</div></td>
<td class="num">{f['n']}</td><td class="num">{esc(f['result'])}</td><td class="num mut">{esc(f['ref'])}</td>
<td class="num">{esc(f['diff'] or '—')}</td><td class="num">{zc}</td><td class="num">{roi}</td></tr>""")
    counts = {g: len(v) for g, v in rows.items()}
    return "".join(body), counts


def page_html(ld, fr, bk, now, rc=None):
    def section(title, blurb, rep, rows_html, empty):
        if not rep["graded"]:
            return f'<h2>{title}</h2><div class="note">{blurb}</div><div class="note">{empty}</div>'
        return f'<h2>{title}</h2><div class="note">{blurb}</div>{rows_html}'

    leads_body = tiles([("Graded", ld["graded"]), ("Hit rate", pct(ld["overall_rate"])),
                        ("Pending", ld["pending"]), ("Void", ld["void"]),
                        ("Withdrawn before kickoff", f"{ld.get('withdrawn', 0)}"
                         + (f" · {ld['withdrawn_hits']/ld['withdrawn']:.0%} hit" if ld.get("withdrawn") else ""))]) + \
        perf_table(ld["rows"], lambda r: BET_NAME.get(r["kind"], r["kind"]))
    pr = ld.get("priced") or {"rows": [], "graded": 0, "pending": 0, "claim_roi": None}
    lane = pr.get("lane_roi") or {}
    roi = lambda k: "—" if lane.get(k) is None else f"{lane[k]*100:+.1f}%"
    priced_body = tiles([("Settled at a price", pr["graded"]),
                         ("Over 1.5 lane ROI", roi("over15")),
                         ("Team 2+ lane ROI", roi("team2plus")),
                         ("Priced, pending", pr["pending"]),
                         ("Claims priced on", " · ".join(
                             f"{ {'bovada': 'Bovada', 'kalshi': 'Kalshi', 'polymarket_us': 'Polymarket'}.get(k, k)} {v}"
                             for k, v in sorted((pr.get("by_source") or {}).items())) or "—")]) + price_table(pr["rows"])
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

    table, counts = findings_table(findings(ld, fr, bk, rc))
    first = next((g for g, *_r in GROUPS if counts[g]), "working")
    on = ' class="on"'
    tabs = "".join(f'<button type="button" data-tab="{g}"{on if g == first else ""}>{esc(t)}<b>{counts[g]}</b></button>'
                   for g, t, _c, _n in GROUPS)
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
.sm{{font-size:11px}}
.tabs{{display:flex;gap:6px;flex-wrap:wrap;margin:6px 0 12px}}
.tabs button{{font:inherit;font-size:12px;font-weight:700;color:var(--mut);background:var(--card);
border:1px solid var(--bd);border-radius:999px;padding:6px 13px;cursor:pointer}}
.tabs button.on{{color:var(--fg);border-color:var(--mut);background:#161b26}}
.tabs button b{{margin-left:5px}}
.grp td{{font-size:10px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:var(--mut);background:#0d1119;padding:7px 11px}}
.grp.ok td{{color:var(--pos)}}.grp.bad td{{color:var(--neg)}}
details.ref{{background:var(--card);border:1px solid var(--bd);border-radius:11px;padding:10px 14px;margin-bottom:10px}}
details.ref>summary{{cursor:pointer;font-size:12.5px;font-weight:700}}
details.ref[open]>summary{{margin-bottom:10px}}
footer{{margin-top:40px;font-size:12px;color:var(--mut);text-align:center}}
@media (max-width:600px){{body{{padding:18px 10px 44px;font-size:14px}}h1{{font-size:19px}}}}
</style></head><body><div class="wrap">
<h1>Edge Machine · Record</h1>
<div class="sub">Everything that has been graded · all times CT · updated {esc(now)}</div>
<div class="nav"><a href="./">Leads</a>
<a href="./streaks.html">Streaks</a><a class="on" href="./record.html">Record</a>
<a href="./today.html">Today</a><a href="./sandbox.html">Sandbox</a><a href="./qa.html">QA</a><a href="./production.html">Production</a></div>

<div class="note warn">Every graded result on one table, sorted like the Sandbox: <b>working</b> and <b>not
working</b> need 30+ graded; under that a result is only leaning. Each row is measured against a
<b>reference</b> — the market's price, the teams' own rate, the book, or a shuffled schedule — never a
bare hit rate. Ranked by <b>z</b> (how many standard deviations from the reference), then ROI. <b>SIG</b>
marks |z| ≥ 2, and with this many rows a few of those appear by chance.</div>

<div class="tiles">
<div class="tile"><b class="{'pos' if counts['working'] else ''}">{counts['working']}</b><span>working</span></div>
<div class="tile"><b class="{'neg' if counts['failing'] else ''}">{counts['failing']}</b><span>not working</span></div>
<div class="tile"><b>{counts['leaning'] + counts['behind']}</b><span>too early to tell</span></div>
<div class="tile"><b>{ld['graded']}</b><span>leads graded</span></div>
<div class="tile"><b>{bk.get('graded', 0)}</b><span>fixtures graded at the price</span></div>
<div class="tile"><b>{ld['pending']}</b><span>leads pending</span></div>
</div>

<h2>Results, ranked</h2>
<div class="tabs" id="tabs">{tabs}<button type="button" data-tab="all">All</button></div>
<div class="tbl"><table id="pairs"><tr><th class="num">#</th><th>Test</th><th class="num">n</th><th class="num">Result</th>
<th class="num">Reference</th><th class="num">Diff</th><th class="num">z</th><th class="num">ROI</th></tr>{table}</table></div>

{f'''<h2>Recently settled leads ({len(hist)})</h2>
<div class="tbl"><table>
<tr><th>Date</th><th>Match</th><th>Pick</th><th class="num">Final</th><th></th></tr>
{hist_rows}</table></div>''' if hist else ''}

<h2>Reference</h2>
<details class="ref"><summary>Leads — every lead published, against the teams' own rate</summary>{leads_body}</details>
<details class="ref"><summary>Leads at the price — does it pay?</summary>
<div class="note">Flat 1 unit at the price captured the first build a lead was listed (the exchange ask plus fee since
2026-09-13, Bovada before), never revised, never after kickoff. <b>Break-even</b> is the hit rate the average price demands;
<b>book fair</b> is the market's own probability.</div>{priced_body}</details>
<details class="ref"><summary>Over 1.5 — the rule change of 2026-09-14</summary>{rule_change_html(rc)}</details>
<details class="ref"><summary>Model v book on the leads</summary>{model_body}</details>
<details class="ref"><summary>The book on every fixture — markets, leagues, price bands, teams</summary>{book_body}</details>
<details class="ref"><summary>On fire — do long runs continue?</summary>{fire_body}</details>

<footer>Read-only static export · research, not betting advice.</footer>
<script>
document.querySelectorAll('#tabs button').forEach(b => b.addEventListener('click', () => {{
  document.querySelectorAll('#tabs button').forEach(x => x.classList.toggle('on', x === b));
  const t = b.dataset.tab;
  document.querySelectorAll('#pairs tr[data-g]').forEach(tr => tr.hidden = t !== 'all' && tr.dataset.g !== t);
}}));
document.querySelector('#tabs button.on')?.click();
</script>
</div></body></html>"""


def build():
    fixtures = streaks_fetch.load_or_fetch()["fixtures"]
    ld = T.report(fixtures)
    try:
        import streaks_build as SB
        rc = T.rule_compare(T.load(), T.load(T.SHADOW_LEDGER), SB.RULE_CHANGE)
    except Exception as e:
        print(f"  (rule comparison skipped: {e})")
        rc = None
    fr = F.report(fixtures)
    bk = K.report(K.load())
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%b %d %Y · %H:%M UTC")

    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, "record.html")
    with open(out, "w") as f:
        f.write(page_html(ld, fr, bk, now, rc))
    print(f"wrote {out}  ({os.path.getsize(out)/1024:.0f} KB) — "
          f"leads {ld['graded']}, fire {fr['graded']}, book {bk['graded']} graded")


if __name__ == "__main__":
    build()
