#!/usr/bin/env python3
"""record_build.py — every measured result in one place: public_site/record.html.

WHY IT IS ITS OWN PAGE
----------------------
The numbers were split across two boards — the slate's record sat under the picks, the
leads' record sat behind a tab on Streaks, and the fire runs were measured in a file nobody
opened. Each page showed a slice and none showed the answer. Since whether any of this
works is the only question that matters, it gets its own page rather than a footnote on two
others.

WHAT IS MEASURED, AND AGAINST WHAT
----------------------------------
No odds anywhere, so nothing here is profit and none of it should be read as ROI. Every
section compares a hit rate against **what the teams involved manage anyway**:

  * picks and leads -> the named side's own rate (or the two sides' mean for a
    fixture-level outcome). A league average would credit the pick for team quality —
    measured, that inflated "team to score" from -1.5pp to +9.3pp.
  * fire runs -> the team's own rate for that streak. Against the population it read
    +12.8pp and "significant"; against the team, -3.1pp and nothing.

LIFT IS THE NUMBER. A hit rate on its own is unreadable, and three lanes in this repo have
already died from being read without a reference.

Usage:  python3 record_build.py   →  public_site/record.html
"""
import os, html, datetime

import streaks_fetch
import streaks_track as T
import fire_track as F
import slate as S

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


def tiles(pairs):
    return ('<div class="tiles">' + "".join(
        f'<div class="tile"><b>{esc(v)}</b><span>{esc(k)}</span></div>'
        for k, v in pairs) + '</div>')


def page_html(sl, ld, fr, hist, now):
    def section(title, blurb, rep, rows_html, empty):
        if not rep["graded"]:
            return f'<h2>{title}</h2><div class="note">{blurb}</div><div class="note">{empty}</div>'
        return f'<h2>{title}</h2><div class="note">{blurb}</div>{rows_html}'

    slate_body = tiles([("Graded", sl["graded"]), ("Hit rate", pct(sl["rate"])),
                        ("Live", sl["live"]), ("Void", sl["void"])]) + \
        perf_table(sl["rows"], lambda r: BET_NAME.get(r["kind"], r["kind"]))
    leads_body = tiles([("Graded", ld["graded"]), ("Hit rate", pct(ld["overall_rate"])),
                        ("Pending", ld["pending"]), ("Void", ld["void"])]) + \
        perf_table(ld["rows"], lambda r: BET_NAME.get(r["kind"], r["kind"]))
    fire_body = tiles([("Graded", fr["graded"]), ("Extended", pct(fr["rate"])),
                       ("Pending", fr["pending"]), ("", "")][:3]) + \
        perf_table(fr["rows"], lambda r: r["label"], base_head="own rate")

    hist_rows = "".join(
        f"""<tr><td class="mut">{esc((p.get('kickoff') or p['date'])[:10])}</td>
        <td>{esc(p['match'])}</td><td>{esc(p['headline'])}</td>
        <td class="num">{esc(p.get('final') or '—')}</td>
        <td><span class="st {p['status']}">{esc(p['status'].upper())}</span></td></tr>"""
        for p in hist[:60])

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
<div class="nav"><a href="./">Picks</a><a href="./streaks.html">Streaks</a>
<a class="on" href="./record.html">Record</a><a href="./today.html">Today</a></div>

<div class="note warn">There are no odds anywhere on this site, so <b>none of this is
profit</b> and none of it should be read as ROI. Each rate is compared against
<b>what the teams involved manage anyway</b> — the named side's own rate for a claim about
one team, the two sides' mean for a fixture-level outcome. A league average would credit a
pick for team quality: measured here, that difference moved "team to score" from
<b>-1.5pp to +9.3pp</b>, and moved on-fire runs from <b>-3.1pp to +12.8pp and
"significant"</b>. <b>Lift is the number</b>; a hit rate alone is unreadable, and three
lanes in this repo have already died from being read without a reference.</div>

{section("Picks — the 3-card slate",
         "Three picks drawn automatically, graded on the final score.", sl, slate_body,
         "Nothing graded yet — the first picks settle as their fixtures are played.")}

{section("Leads — every confluence published",
         "Every lead the Streaks board has shown, graded whether or not it was picked. "
         "A wider sample than the slate, since the slate only ever holds three.",
         ld, leads_body,
         "Nothing graded yet.")}

{section("On fire — do long runs continue?",
         "Each long run logged against the fixture that tests it. Judged against the "
         "team's OWN rate: the question is not whether a side on a hot run keeps scoring, "
         "it is whether they do it MORE than they usually would.",
         fr, fire_body,
         "Nothing graded yet.")}

{f'''<h2>Settled picks ({len(hist)})</h2>
<div class="tbl"><table>
<tr><th>Date</th><th>Match</th><th>Pick</th><th class="num">Final</th><th></th></tr>
{hist_rows}</table></div>''' if hist else ''}

<footer>Read-only static export · auto-drawn research, not betting advice.</footer>
</div></body></html>"""


def build():
    fixtures = streaks_fetch.load_or_fetch()["fixtures"]
    sl = S.report(fixtures)
    ld = T.report(fixtures)
    fr = F.report(fixtures)
    hist = S.report(fixtures)["history"]
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%b %d %Y · %H:%M UTC")

    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, "record.html")
    with open(out, "w") as f:
        f.write(page_html(sl, ld, fr, hist, now))
    print(f"wrote {out}  ({os.path.getsize(out)/1024:.0f} KB) — "
          f"slate {sl['graded']}, leads {ld['graded']}, fire {fr['graded']} graded")


if __name__ == "__main__":
    build()
