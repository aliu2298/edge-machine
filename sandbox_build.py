"""Renders the Sandbox Tracker ledger into public_site/sandbox.html.

Pure presentation — it reads the ledger and writes a page, and never fetches or grades.
That split is deliberate: the page can always be rebuilt from the ledger, so a rendering
bug can never cost a settled result.
"""

import html
import json
import os
import re
import sys
from datetime import datetime, timezone

import sandbox_sources as S
import sandbox_track as T

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "public_site", "sandbox.html")

# Below this many settled bets, ROI is noise dressed as a finding. Three lanes in this
# repo have already died from a rate being read without the sample behind it, so the
# board refuses to call a winner until the number can carry the claim.
MIN_N = T.READ_FLOOR

STAMP = {
    "approved": '<span class="sig y">✓ APPROVED</span>',
    "watch":    '<span class="sig w">WATCH</span>',
    "failing":  '<span class="st miss">FAILING</span>',
    "unproven": '<span class="sig n">NO READ</span>',
}

# The board covers two different things now, and one table of fourteen columns would be
# unreadable. Sports are contests between two named sides; the rest are yes/no questions
# with a forecaster on the other side of them.
SPORT_KEYS = ["soccer", "tennis", "table_tennis", "boxing", "mma", "nfl", "cricket", "mlb"]

# Long lists are the part of the page that grows without bound. The first few rows show
# what the list is; the rest sit behind a toggle so the tables that carry the verdicts
# stay near the top.
SHOW_ROWS = 8
MARKET_KEYS = ["climate", "crypto", "economics", "commodities", "finance", "politics",
               "elections"]


def esc(x):
    return html.escape(str(x))


def pct(x, digits=1, sign=False):
    if x is None:
        return "—"
    return f"{x*100:+.{digits}f}%" if sign else f"{x*100:.{digits}f}%"


def money(x):
    if x is None:
        return "—"
    return f"{'+' if x >= 0 else '−'}${abs(x):,.0f}"


def cls(x):
    return "pos" if (x or 0) > 0 else ("neg" if (x or 0) < 0 else "mut")




def feed_health(d):
    """Name any connected source whose feed could not be READ on the last run.

    A source that could not be fetched and a source with nothing to say produce the same
    empty row, and the board would keep reporting "no bets" for weeks without anyone
    knowing why. So this separates the two.

    Where an adapter reports whether its pages loaded (the tipster sites), that is used:
    a page that loaded is healthy even with no usable tip. The first version counted
    matched calls instead, and flagged Oddspedia as broken on a day its page loaded fine
    carrying two tips on opposite sides of one match — which the consensus rule rightly
    turns into no call at all.

    Sources that report no status fall back to counts, flagged only when empty across
    EVERY sport they cover: a single quiet sport is just an empty fixture list, and
    warning about that would train the reader to ignore this line.
    """
    cov = d.get("coverage") or {}
    status = d.get("feed_status") or {}
    if not cov and not status:
        return ""
    dark = []
    for name, meta in S.SOURCES.items():
        if not meta["connected"] or name == "polymarket":
            continue
        st = status.get(name)
        if st is not None:
            if st.startswith("down"):
                reason = st.split(":", 1)[1].strip() if ":" in st else "unreachable"
                dark.append(f"{meta['label']} ({reason})")
            continue
        counts = [(cov.get(sp) or {}).get(name) for sp in meta["sports"]]
        seen = [c for c in counts if c is not None]
        if seen and not any(seen):
            dark.append(meta["label"])
    if not dark:
        return ""
    return (f'<div class="note warn"><b>Feed check:</b> '
            f'{esc(", ".join(dark))} could not be read on the last run. That is a broken '
            f'feed, not an absence of opinion — until it is fixed, the row below '
            f'understates that source rather than describing it.</div>')


def sport_matrix(d, keys=None):
    """Source x sport: ROI where there is enough settled to say, sample size always shown.

    This is the board's answer to the actual question. A single blended ROI per source
    hides the thing that matters — a tipster can be strong at one sport and hopeless at
    another — and rows are grouped by kind because tipsters, models and markets are
    staked differently and are not comparable on turnover.
    """
    keys = keys or list(S.SPORTS)
    head = "".join(f'<th class="num">{esc(S.SPORTS[k])}</th>' for k in keys)
    ncols = 2 + len(keys)
    # Every connected kind must appear in exactly one group, or the source silently
    # vanishes from the board — which is what happened to the weather forecaster and the
    # spot baseline the first time they published.
    groups = [("Tipsters", ("Tipster site",)),
              ("Forecasters", ("Forecaster", "Baseline")),
              ("Models and books", ("Statistical model", "Sportsbook", "Sportsbook consensus")),
              ("Prediction markets", ("Prediction market",))]
    out = []
    for title, kinds in groups:
        names = [n for n, m in S.SOURCES.items() if m["connected"] and m["kind"] in kinds
                 and any(k in m["sports"] for k in keys)]
        if not names:
            continue
        out.append(f'<tr class="grp"><td colspan="{ncols}">{esc(title)}</td></tr>')
        for name in sorted(names, key=lambda n: S.SOURCES[n]["label"]):
            meta = S.SOURCES[name]
            cells = []
            for sport in keys:
                if sport not in meta["sports"]:
                    cells.append('<td class="num mut">·</td>')
                    continue
                s = T.score(d, sport=sport)[name]
                if not s["settled"]:
                    pend = s["bets"]
                    cells.append(f'<td class="num mut">{("%d open" % pend) if pend else "—"}</td>')
                    continue
                thin = s["settled"] < MIN_N
                klass = "mut" if thin else cls(s["pnl"])
                tick = (' <span class="pos">✓</span>'
                        if T.assess(d, name, sport)["status"] == "approved" else "")
                cells.append(f'<td class="num"><span class="{klass}">{pct(s["roi"], sign=True)}</span>'
                             f'{tick}<div class="sm mut">n={s["settled"]}</div></td>')
            tot = T.score(d)[name]  # lifetime, across every domain
            tot_roi = (f'<span class="{cls(tot["pnl"]) if tot["settled"] >= MIN_N else "mut"}">'
                       f'{pct(tot["roi"], sign=True)}</span>' if tot["settled"]
                       else '<span class="mut">—</span>')
            out.append(f"""<tr><td><b>{esc(meta['label'])}</b></td>{''.join(cells)}
<td class="num">{tot_roi}<div class="sm mut">n={tot['settled']}</div></td></tr>""")
    return f"""<div class="tbl"><table>
<tr><th>Source</th>{head}<th class="num">All</th></tr>
{''.join(out)}</table></div>"""


def vs_price(d, name, sport=None):
    """Wins, and the wins the PRICES implied. Returns (won, expected) or None.

    At these sample sizes this says more than ROI does. Each backed price is the
    market's own probability that the bet lands, so adding them up gives the number of
    winners a source should have had by luck alone. Beating the price is the whole test;
    a hot ROI on heavy favourites is not an edge.
    """
    rows = [q for q in d["quotes"] if q["source"] == name and q["bet"]
            and q["status"] in ("won", "lost") and (sport is None or q["sport"] == sport)]
    if not rows:
        return None
    return sum(1 for q in rows if q["status"] == "won"), sum(q["price"] for q in rows)


def leaderboard(scores, d):
    rows = []
    for name, s in sorted(scores.items(),
                          key=lambda kv: (kv[1]["connected"], kv[1]["settled"]), reverse=True):
        if not s["connected"]:
            continue
        thin = s["settled"] < MIN_N
        roi = (f'<span class="{cls(s["roi"])}">{pct(s["roi"], sign=True)}</span>'
               if s["roi"] is not None and not thin
               else f'<span class="mut">{pct(s["roi"], sign=True)}</span>')
        # The verdict IS the stamp: "profitable" on its own was a hot ROI with nothing
        # behind it. Sources that never bet (Polymarket, the spine) carry no stamp.
        verdict = (STAMP[T.assess(d, name)["status"]] if s["bets"]
                   else '<span class="mut sm">price only</span>')
        vp = vs_price(d, name)
        vp_cell = "—"
        if vp:
            won, exp = vp
            vp_cell = (f'{won} v {exp:.1f}<div class="sm mut">'
                       f'{"+" if won - exp >= 0 else ""}{won - exp:.1f}</div>')
        rows.append(f"""<tr>
<td><b>{esc(s['label'])}</b><div class="mut sm">{esc(s['kind'])} · {esc(s['site'])}</div></td>
<td class="num">{s['quotes']:,}</td><td class="num">{s['bets']:,}</td>
<td class="num">{s['settled']:,}</td>
<td class="num">{pct(s['hit']) if s['hit'] is not None else '—'}</td>
<td class="num">{vp_cell}</td>
<td class="num">{roi}</td>
<td class="num {cls(s['pnl'])}">{money(s['pnl']) if s['settled'] else '—'}</td>
<td class="num">{f"{s['brier']:.4f}" if s['brier'] is not None else '—'}</td>
<td>{verdict}</td></tr>""")
    return "\n".join(rows)


def approval_table(d, scores):
    """Every betting source against every criterion, so a stamp can be checked, not trusted."""
    head = "".join(f'<th>{esc(label)}</th>' for _k, label, _p, _d in
                   T.assess(d, "__none__")["criteria"])
    rows = []
    order = {"approved": 0, "watch": 1, "failing": 2, "unproven": 3}
    judged = [(name, T.assess(d, name)) for name, s in scores.items()
              if s["connected"] and s["bets"]]
    for name, a in sorted(judged, key=lambda kv: (order[kv[1]["status"]], -kv[1]["n"])):
        cells = "".join(
            f'<td><span class="{"pos" if passed else "neg"}">{"✓" if passed else "✗"}</span>'
            f'<div class="sm mut">{esc(detail)}</div></td>'
            for _k, _l, passed, detail in a["criteria"])
        rows.append(f'<tr><td><b>{esc(S.SOURCES[name]["label"])}</b></td>'
                    f'<td>{STAMP[a["status"]]}</td>{cells}</tr>')
    return f"""<div class="tbl"><table>
<tr><th>Source</th><th>Stamp</th>{head}</tr>
{''.join(rows)}</table></div>"""


def baseline_table(d):
    """The blind strategies, per sport — the bar every source's choices have to clear."""
    rows = []
    for sport in SPORT_KEYS:
        b = T.baselines(d, sport)
        for kind, label in (("favourite", "Back the favourite"),
                            ("underdog", "Back the underdog"), ("draw", "Back every draw")):
            r = b[kind]
            if not r["n"]:
                continue
            rows.append(f"""<tr><td>{esc(S.SPORTS[sport])}</td><td><b>{label}</b></td>
<td class="num">{r['n']}</td><td class="num">{r['won']} v {r['expected']:.1f}</td>
<td class="num"><span class="{cls(r['pnl']) if r['n'] >= MIN_N else 'mut'}">{pct(r['roi'], sign=True)}</span></td>
<td class="num {cls(r['pnl'])}">{money(r['pnl'])}</td></tr>""")
    if not rows:
        return '<div class="note">No settled contests yet.</div>'
    return f"""<div class="tbl"><table>
<tr><th>Sport</th><th>Blind strategy</th><th class="num">Contests</th>
<th class="num">Won v priced</th><th class="num">ROI</th><th class="num">P/L</th></tr>
{''.join(rows)}</table></div>"""


def coverage_table(cov):
    """Sport x source grid of what each feed actually returned on the last run."""
    names = [n for n, m in S.SOURCES.items() if m["connected"]]
    head = "".join(f'<th class="num">{esc(S.SOURCES[n]["label"].split(" (")[0])}</th>'
                   for n in names)
    rows = []
    for sport, label in S.SPORTS.items():
        cells = []
        for n in names:
            v = (cov.get(sport) or {}).get(n)
            if sport not in S.SOURCES[n]["sports"]:
                cells.append('<td class="num mut">n/a</td>')
            elif v is None:
                cells.append('<td class="num neg">—</td>')
            elif v == 0:
                cells.append('<td class="num neg">0</td>')
            else:
                cells.append(f'<td class="num pos">{v:,}</td>')
        rows.append(f"<tr><td><b>{esc(label)}</b></td>{''.join(cells)}</tr>")
    return f"""<div class="tbl"><table>
<tr><th>Sport</th>{head}</tr>
{''.join(rows)}</table></div>"""


def open_rows(d, limit=30):
    """Running bets, grouped by sport and soonest first."""
    live = [q for q in d["quotes"] if q["status"] == "open" and q["bet"]]
    live.sort(key=lambda q: (list(S.SPORTS).index(q["sport"]), q["start"]))
    out, seen_sport = [], None
    for q in live[:limit]:
        if q["sport"] != seen_sport:
            seen_sport = q["sport"]
            n = sum(1 for x in live if x["sport"] == seen_sport)
            out.append(f'<tr class="grp"><td colspan="7">{esc(S.SPORTS[seen_sport])} '
                       f'· {n} running</td></tr>')
        side = q["side_a"] if q["pick"] == "a" else (q["side_b"] if q["pick"] == "b" else "Draw")
        out.append(f"""<tr><td class="mut">{esc(q['date'])}</td>
<td>{esc(S.SPORTS[q['sport']])}</td>
<td><a href="{esc(q['url'])}" target="_blank" rel="noopener">{esc(q['label'])}</a></td>
<td>{esc(S.SOURCES[q['source']]['label'].split(' (')[0])}</td>
<td><b>{esc(side)}</b></td>
<td class="num">{q['price']:.2f}</td>
<td class="num pos">{pct(q['edge'], sign=True) if q.get('edge') is not None else '<span class="mut">pick</span>'}</td></tr>""")
    return "\n".join(out), len(live)


def settled_rows(d, limit=40):
    """Settled bets, newest first, grouped by the day they settled."""
    done = [q for q in d["quotes"] if q["status"] in ("won", "lost", "void") and q["bet"]]
    done.sort(key=lambda q: q.get("settled") or "", reverse=True)
    out, seen_day = [], None
    for q in done[:limit]:
        day = (q.get("settled") or "")[:10]
        if day != seen_day:
            seen_day = day
            won = sum(1 for x in done if (x.get("settled") or "")[:10] == day and x["status"] == "won")
            n = sum(1 for x in done if (x.get("settled") or "")[:10] == day)
            pl = sum(x["pnl"] for x in done if (x.get("settled") or "")[:10] == day)
            out.append(f'<tr class="grp"><td colspan="8">{esc(day)} · {won}/{n} won · '
                       f'{money(pl)}</td></tr>')
        side = q["side_a"] if q["pick"] == "a" else (q["side_b"] if q["pick"] == "b" else "Draw")
        out.append(f"""<tr><td class="mut">{esc(q['date'])}</td>
<td>{esc(S.SPORTS[q['sport']])}</td><td>{esc(q['label'])}</td>
<td>{esc(S.SOURCES[q['source']]['label'].split(' (')[0])}</td>
<td>{esc(side)}</td><td class="num">{q['price']:.2f}</td>
<td><span class="st {q['status']}">{q['status'].upper()}</span></td>
<td class="num {cls(q['pnl'])}">{money(q['pnl'])}</td></tr>""")
    return "\n".join(out), len(done)


LIVE_HEAD = ('<tr><th>Date</th><th>Sport</th><th>Contest</th><th>Source</th>'
             '<th>Backing</th><th class="num">Price</th><th class="num">Edge</th></tr>')
HIST_HEAD = ('<tr><th>Date</th><th>Sport</th><th>Contest</th><th>Source</th><th>Backed</th>'
             '<th class="num">Price</th><th></th><th class="num">P/L</th></tr>')


def collapse(rows_html, head, total, noun):
    """The first SHOW_ROWS rows in the open, the rest behind a toggle.

    Group header rows (class="grp") travel with the rows they introduce and do not count
    toward the limit, so a header is never left stranded above an empty table.
    """
    # Split on row tags: each row template spans several lines of source.
    rows = [r for r in re.split(r"(?=<tr[\s>])", rows_html) if r.strip()]
    grp = 'class="grp"'
    shown, hidden, real = [], [], 0
    for r in rows:
        if grp not in r:
            real += 1
        (shown if real <= SHOW_ROWS else hidden).append(r)
    # A header whose rows all fell into the hidden part belongs with them.
    while shown and grp in shown[-1]:
        hidden.insert(0, shown.pop())
    table = f'<div class="tbl"><table>{head}{"".join(shown)}</table></div>'
    if not hidden:
        return table
    n_hidden = sum(1 for r in hidden if grp not in r)
    n_listed = sum(1 for r in rows if grp not in r)
    extra = f" — the latest {n_listed} of {total:,}" if total > n_listed else ""
    return (table + f'<details class="more"><summary>Show {n_hidden} more {noun}{extra}'
            f'</summary><div class="tbl"><table>{head}{"".join(hidden)}</table></div>'
            f'</details>')


def unconnected_rows():
    out = []
    for name, m in S.SOURCES.items():
        if m["connected"]:
            continue
        out.append(f"""<tr><td><b>{esc(m['label'])}</b>
<div class="mut sm">{esc(m['kind'])} · {esc(m['site'])}</div></td>
<td class="mut">{esc(m['note'])}</td></tr>""")
    return "\n".join(out)


def build():
    d = T.load()
    scores = T.score(d)
    cov = d.get("coverage") or {}
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    # Pinnacle is read through a metered API; showing the balance keeps a quota running
    # dry from looking like Pinnacle having nothing to price.
    ou = (d.get("meta") or {}).get("odds_api") or {}
    odds_line = (f" Pinnacle prices come through The Odds API: {ou.get('calls', 0)} paid "
                 f"call{'s' if ou.get('calls', 0) != 1 else ''} last run, "
                 f"{ou['remaining']} credits left this month."
                 if ou.get("remaining") is not None else "")

    quotes = len(d["quotes"])
    bets = sum(1 for q in d["quotes"] if q["bet"])
    settled = sum(1 for q in d["quotes"] if q["status"] in ("won", "lost"))
    pnl = sum(q["pnl"] for q in d["quotes"] if q["status"] in ("won", "lost"))
    staked = sum(q["stake"] for q in d["quotes"] if q["status"] in ("won", "lost"))
    live_rows, n_live = open_rows(d)
    n_unconnected = sum(1 for m in S.SOURCES.values() if not m["connected"])
    hist_rows, n_hist = settled_rows(d)

    # The floor has to be judged on the SAME unit the table prints. Every cell greys
    # itself on its own settled count, but this banner used to compare the lifetime
    # TOTAL against MIN_N — so at 57 settled across seven sources it announced "the ROI
    # column is now readable" while greying out every figure in it, the best single
    # source sitting at n=15. A total is not a sample; nobody bets "all sources".
    best = max((v["settled"] for v in scores.values()), default=0)
    ready = [n for n, v in scores.items() if v["settled"] >= MIN_N]
    if settled == 0:
        verdict = ("Nothing is settled yet, so no source has a record. The first "
                   "fixtures settle within a day of the first run.")
    elif not ready:
        verdict = (f"{settled:,} settled bets across every source, but the most any "
                   f"single source has is {best}. Nothing here is readable until one "
                   f"of them reaches {MIN_N} on its own — a total is not a sample.")
    else:
        verdict = (f"{settled:,} settled bets. "
                   f"{len(ready)} source{'' if len(ready) == 1 else 's'} past the "
                   f"{MIN_N}-bet floor ({', '.join(sorted(ready))}) — only those "
                   f"figures are readable; the rest stay greyed.")

    return f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sandbox Tracker</title>
<meta name="description" content="Which sports tipsters actually make money, tracked per sport at real prices and settled on real results.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
:root{{--bg:#0a0d14;--card:#10141d;--bd:#232936;--fg:#eef2f7;--mut:#8b94a7;
--pos:#3fb970;--neg:#e06c75;--warn:#f0b429;--acc:#7aa2f7}}
*{{box-sizing:border-box;margin:0}}
body{{background:var(--bg);color:var(--fg);font:15px/1.45 Inter,system-ui,sans-serif;
letter-spacing:-.011em;-webkit-font-smoothing:antialiased;padding:28px 16px 60px}}
.wrap{{max-width:1040px;margin:0 auto}}
h1{{font-size:22px;font-weight:800;letter-spacing:-.02em}}
h2{{font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;
color:var(--mut);margin:34px 0 12px}}
.sub{{color:var(--mut);font-size:13px;margin-top:4px}}
.sm{{font-size:11px}}
.mut{{color:var(--mut)}}.pos{{color:var(--pos)}}.neg{{color:var(--neg)}}
a{{color:var(--acc);text-decoration:none}}a:hover{{text-decoration:underline}}
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
.tile{{flex:1;min-width:112px;background:var(--card);border:1px solid var(--bd);
border-radius:10px;padding:11px 13px}}
.tile b{{display:block;font-size:19px;font-weight:800;font-variant-numeric:tabular-nums}}
.tile span{{font-size:11px;color:var(--mut)}}
.tbl{{background:var(--card);border:1px solid var(--bd);border-radius:11px;
overflow-x:auto;margin-bottom:13px}}
table{{width:100%;border-collapse:collapse;font-size:12.5px}}
th{{text-align:left;font-size:10px;text-transform:uppercase;letter-spacing:.07em;
color:var(--mut);padding:9px 11px;border-bottom:1px solid var(--bd);white-space:nowrap}}
td{{padding:9px 11px;border-bottom:1px solid #1a1f2b;vertical-align:top}}
tr:last-child td{{border-bottom:none}}
.num{{font-variant-numeric:tabular-nums;text-align:right;white-space:nowrap}}
.st,.sig{{display:inline-block;font-size:9.5px;font-weight:800;letter-spacing:.05em;
border-radius:999px;padding:2px 7px;border:1px solid;white-space:nowrap}}
.st.won,.sig.y{{color:var(--pos);border-color:#3fb97055;background:#3fb97014}}
.st.lost,.st.miss{{color:var(--neg);border-color:#e06c7555;background:#e06c7514}}
.st.void,.sig.n{{color:var(--mut);border-color:var(--bd)}}
.sig.w{{color:var(--warn);border-color:#f0b42955;background:#f0b42914}}
details.more{{margin:-4px 0 14px}}
details.more>summary{{cursor:pointer;font-size:12px;font-weight:700;color:var(--acc);
padding:6px 2px;list-style:none}}
details.more>summary::-webkit-details-marker{{display:none}}
details.more>summary::before{{content:"▸ "}}
details.more[open]>summary::before{{content:"▾ "}}
.grp td{{font-size:10px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:var(--mut);background:#0d1119;padding:7px 11px}}
footer{{margin-top:40px;font-size:12px;color:var(--mut);text-align:center}}
@media (max-width:600px){{body{{padding:18px 10px 44px;font-size:14px}}h1{{font-size:19px}}}}
</style></head><body><div class="wrap">

<h1>Sandbox Tracker</h1>
<div class="sub">Which tipster actually makes money · {len(S.SPORTS)} sports · updated {esc(now)}</div>
<div class="nav"><a href="./">Leads</a>
<a href="./streaks.html">Streaks</a><a href="./record.html">Record</a>
<a href="./today.html">Today</a><a class="on" href="./sandbox.html">Sandbox</a></div>

<div class="note warn">Every source here is logged <b>before the contest starts</b> and
stamped with the <b>price that existed at that moment</b>, then settled for real when the
market resolves. Two kinds of source are tracked and they are staked differently.
<b>Tipsters</b> name a side: that side is backed at the going price, every time, because
that is how a tipster is actually followed — high turnover, no Brier score, and a real
ROI. <b>Models, books and exchanges</b> state a probability: they are backed only when
they disagree with the price by {int(T.EDGE_MIN*100)}pp or more, and they also get an
accuracy score. Everything is flat ${int(T.STAKE)} a bet, so nothing here is bet-sizing
skill. {esc(verdict)}</div>

<div class="tiles">
<div class="tile"><b>{quotes:,}</b><span>predictions logged</span></div>
<div class="tile"><b>{bets:,}</b><span>bets placed</span></div>
<div class="tile"><b>{settled:,}</b><span>settled</span></div>
<div class="tile"><b class="{cls(pnl)}">{money(pnl) if settled else '—'}</b><span>net P/L</span></div>
<div class="tile"><b class="{cls(pnl)}">{pct(pnl/staked, sign=True) if staked else '—'}</b><span>ROI on turnover</span></div>
<div class="tile"><b>{n_live:,}</b><span>bets running</span></div>
</div>

<h2>Which tipster is profitable, and at what?</h2>
{feed_health(d)}
{sport_matrix(d, SPORT_KEYS)}
<div class="note"><b>ROI per source, per sport</b>, at the price actually available.
Greyed figures are under {MIN_N} settled bets and mean nothing yet — the sample is
printed under every number so a hot streak cannot be mistaken for an edge. A dot means
the source does not cover that sport at all.</div>

<h2>Stamp of approval</h2>
<div class="note">A source earns the stamp only when <b>every</b> criterion holds, and it is
re-judged every run, so it can be lost. The rules were fixed on 2026-09-12, before any
source had met them, and they are the same for tipsters, models, books and exchanges:
<b>{T.APPROVAL['min_bets']}+ settled bets across {T.APPROVAL['min_weeks']}+ different weeks</b>
(one weekend is one draw of the weather — on 2026-09-12 the tracked leagues drew 34% of the
time against a normal ~26%); <b>wins beat the price</b> by z ≥ {T.APPROVAL['z_min']:g};
<b>ROI beats every blind rule on the same contests</b> — back the favourite, back the
underdog, back the draw — each a fixed rule that ignores the source, so beating all three
means its choices added something; <b>still profitable without its single biggest win</b>;
and <b>profitable in both halves</b> of its record. <b>Watch</b> means readable and ahead of
the price but not yet through every gate; <b>failing</b> means readable and not ahead of
the price at all; <b>no read</b> means under {MIN_N} settled bets.</div>
{approval_table(d, scores)}

<h2>Blind baselines</h2>
<div class="note">What choosing nothing would have made on the same contests, priced at the
first moment any source looked at each one. A source whose record is no better than
<b>back the favourite</b>, <b>back the underdog</b> or <b>back every draw</b> has not shown it
can pick — it has shown what the weather was.</div>
{baseline_table(d)}

<h2>Markets beyond sport</h2>
{sport_matrix(d, MARKET_KEYS)}
<div class="note">Yes/no markets rather than contests, so the opponent is the market
price itself. <b>Climate</b> is the one with a genuinely independent forecaster — the
National Weather Service against Kalshi's temperature buckets for the same city and day —
and it settles overnight, so it reaches a readable sample in about a week. <b>Crypto</b>
carries a no-change spot baseline, which is the null hypothesis rather than a forecast.
<b>Politics</b> and <b>elections</b> are listed but not fetched: Kalshi has thousands of
political questions and almost none resolve inside this board's horizon, so nothing there
could settle and be scored.</div>

<h2>Overall record</h2>
<div class="tbl"><table>
<tr><th>Source</th><th class="num">Logged</th><th class="num">Bets</th>
<th class="num">Settled</th><th class="num">Hit</th><th class="num">Won v priced</th><th class="num">ROI</th>
<th class="num">P/L</th><th class="num">Brier</th><th>Verdict</th></tr>
{leaderboard(scores, d)}
</table></div>
<div class="note"><b>Won v priced</b> is the honest column while samples are small: each backed price is
the market's own chance that the bet lands, so their sum is how many winners luck alone
would have produced. Two wins from bets the market priced at 1.6 is noise, not an edge.
<b>Brier</b> scores raw accuracy on every logged probability, bet or
not — lower is better, 0.25 is a coin flip. It is blank for tipsters by design: naming a
side states no probability, so there is nothing to calibrate. <b>Compare on ROI, never on
P/L</b> — a tipster backs every game it calls while a model bets only where it disagrees
with the price, so turnover differs by an order of magnitude. Polymarket cannot win its
own table: its price is what everything else is measured against.</div>

<h2>Running now ({n_live:,})</h2>
{collapse(live_rows, LIVE_HEAD, n_live, "running bets") if n_live else '<div class="note">No open bets — no source currently disagrees with the market by enough to act on.</div>'}

<h2>Settled ({n_hist:,})</h2>
{collapse(hist_rows, HIST_HEAD, n_hist, "settled bets") if n_hist else '<div class="note">Nothing settled yet. Bets settle when Polymarket resolves the market, usually within hours of the contest finishing.</div>'}

<details class="more"><summary>Declared but not connected ({n_unconnected})</summary>
<div class="tbl"><table>
<tr><th>Source</th><th>Why it is not scored</th></tr>
{unconnected_rows()}
</table></div>
<div class="note">These are listed rather than dropped so the roster stays honest: a
source missing from a board is indistinguishable from a source with nothing to say.
Adding one is a single function returning <code>{{a, b, pick}}</code> or
<code>{{a, b, prob_a}}</code> per contest; the matching, staking, settling and scoring
are already shared. Cloudflare is no longer a blocker either — Scores24 is fetched
through a real headless browser, and any other site behind the same wall can reuse
that step.</div></details>

<h2>Method</h2>
<div class="note">
Every source is logged <b>before kick-off</b> at the <b>price available then</b>, staked
flat ${int(T.STAKE)}, and settled on the real result. Tipsters name a side and are backed
every time; models and books state a probability and are backed only on a
{int(T.EDGE_MIN*100)}pp disagreement with the price.<br><br>
<b>Prices and settlement.</b> Polymarket is the venue wherever it lists a contest,
and settles it — but a Polymarket contest is only logged once it has a <b>real book</b>:
a spread of {int(S.MAX_SPREAD*100)}¢ or less with at least ${int(S.MIN_LIQUIDITY)} on it,
booked at the <b>ask</b>. A just-listed market shows a midpoint near 50¢ with nothing
behind it; before this rule, boxing bouts were logged at 51¢ that traded at 88¢ once
money arrived. Boxing, cricket and table-tennis quotes logged before the rule were voided
({esc(T.PRE_GATE_NOTE)}).{odds_line}<br><br>
<b>Kalshi</b> is the venue for soccer — Polymarket lists barely any
soccer matches — and for any fight, match or game Polymarket is missing. On Kalshi a tip
is backed at the <b>ask</b>, the price backing it would actually cost, and only where
that book is tight (a spread of 10¢ or less). Soccer is <b>three-way</b>: a Draw tip wins
on a draw, and a backed side loses to it and is never refunded.<br><br>
<b>What would falsify a source.</b> A positive ROI under {MIN_N} settled bets is not a
finding. Beating the price is the only test that counts — a high hit rate on heavy
favourites is not an edge, it is just backing the favourite.
</div>

<footer>Read-only static export · rebuilt by GitHub Actions · research, not betting advice.</footer>
</div></body></html>"""


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        f.write(build())
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
