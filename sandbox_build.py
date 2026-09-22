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
SPORT_KEYS = [k for k in S.SPORTS if k.startswith("soccer")] + ["tennis", "table_tennis", "boxing", "mma", "nfl", "cricket", "mlb", "nhl_rest", "nhl_pl"]

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
        if not meta["connected"] or name == "polymarket_us":
            continue
        # A rule reads data we already hold; zero picks means no match qualified, not a dead feed.
        if meta.get("kind") == "Rule":
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
              ("Rules", ("Rule",)),
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
        a = T.assess(d, name) if s["bets"] else None
        vb_cell = "—"
        if a and a["base_roi"] is not None:
            gap = a["own_roi"] - a["base_roi"]
            kind = a["criteria"][2][3].split(" back the ")[-1]
            vb_cell = (f'<span class="{cls(gap) if not thin else "mut"}">{"+" if gap >= 0 else ""}'
                       f'{gap*100:.1f}pp</span><div class="sm mut">v back the {esc(kind)}</div>')
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
<td class="num">{vb_cell}</td>
<td class="num">{close_cell(a)}</td>
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


def pinnacle_table(d):
    """The Pinnacle-versus-venue rule, on contests nothing else covers and on the rest."""
    rows = []
    for label, flag in (("Contests nothing else covers", True), ("Contests others also cover", False)):
        qs = [q for q in d["quotes"] if q["source"] == "pinnacle" and q.get("uncovered") is flag
              and q["status"] != "void"]
        bets = [q for q in qs if q["bet"]]
        done = [q for q in bets if q["status"] in ("won", "lost")]
        won = sum(1 for q in done if q["status"] == "won")
        pnl = sum(q["pnl"] for q in done)
        exp = sum(q["price"] for q in done)
        edges = [q["edge"] for q in qs if q.get("edge") is not None]
        rows.append(f"""<tr><td><b>{label}</b></td><td class="num">{len(qs)}</td>
<td class="num">{len(bets)}</td><td class="num">{len(done)}</td>
<td class="num">{f"{won} v {exp:.1f}" if done else "—"}</td>
<td class="num"><span class="{cls(pnl) if len(done) >= MIN_N else 'mut'}">{pct(pnl / (len(done) * T.STAKE), sign=True) if done else '—'}</span></td>
<td class="num mut">{f"{max(edges)*100:+.1f}pp" if edges else "—"}</td></tr>""")
    ou = (d.get("meta") or {}).get("odds_api") or {}
    spent = ", ".join(f"{x['key']} ({x['uncovered']} uncovered)" for x in ou.get("spent_on", [])) or "none"
    retired = ", ".join(ou.get("retired") or []) or "none"
    return f"""<div class="tbl"><table>
<tr><th>Pinnacle v venue</th><th class="num">Quotes</th><th class="num">Bets</th>
<th class="num">Settled</th><th class="num">Won v priced</th><th class="num">ROI</th>
<th class="num">Largest gap</th></tr>
{''.join(rows)}</table></div>
<div class="note">Pinnacle's de-vigged probability against the venue's ask, backed only where it
beats the ask by {int(T.EDGE_MIN*100)}pp or more. Credits are spent where nothing else looks: every run
ranks the sports by how many listed contests have no tipster, model or book, and spends its
paced share of the month's credits from the top, and only on sport keys with at least one
uncovered contest. A sport stops getting paid calls once Pinnacle has {S.PINNACLE_RETIRE_N} quotes
there without one reaching the {int(T.EDGE_MIN*100)}pp edge — its venue already prices like Pinnacle
(retired now: {esc(retired)}). Unspent credits stay in the
balance for later runs. Lines more than {S.PINNACLE_MAX_AGE_MIN} minutes old
are skipped ({ou.get('stale', 0)} last run). Last run's paid calls: {esc(spent)}.</div>"""


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


def open_rows(d, limit=None):
    """Running bets, grouped by sport and soonest first."""
    live = [q for q in d["quotes"] if q["status"] == "open" and q["bet"]]
    live.sort(key=lambda q: (list(S.SPORTS).index(q["sport"]), q["start"]))
    out, seen_sport = [], None
    for q in (live[:limit] if limit else live):
        if q["sport"] != seen_sport:
            seen_sport = q["sport"]
            n = sum(1 for x in live if x["sport"] == seen_sport)
            out.append(f'<tr class="grp"><td colspan="7">{esc(S.SPORTS[seen_sport])} '
                       f'· {n} running</td></tr>')
        side = q["side_a"] if q["pick"] == "a" else (q["side_b"] if q["pick"] == "b" else "Draw")
        out.append(f"""<tr><td class="mut">{esc(q['date'])}</td>
<td>{esc(S.SPORTS[q['sport']])}</td>
<td><a href="{esc(q['url'])}" target="_blank" rel="noopener">{esc(S.display_label(q))}</a></td>
<td>{esc(S.SOURCES[q['source']]['label'].split(' (')[0])}</td>
<td><b>{esc(side)}</b></td>
<td class="num">{q['price']:.2f}</td>
<td class="num pos">{pct(q['edge'], sign=True) if q.get('edge') is not None else '<span class="mut">pick</span>'}</td></tr>""")
    return "\n".join(out), len(live)


def settled_rows(d, limit=None):
    """Settled bets, newest first, grouped by the day they settled."""
    done = [q for q in d["quotes"] if q["status"] in ("won", "lost", "void") and q["bet"]]
    done.sort(key=lambda q: q.get("settled") or "", reverse=True)
    out, seen_day = [], None
    for q in (done[:limit] if limit else done):
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
<td>{esc(S.SPORTS[q['sport']])}</td><td>{esc(S.display_label(q))}</td>
<td>{esc(S.SOURCES[q['source']]['label'].split(' (')[0])}</td>
<td>{esc(side)}</td><td class="num">{q['price']:.2f}</td>
<td><span class="st {q['status']}">{q['status'].upper()}</span></td>
<td class="num {cls(q['pnl'])}">{money(q['pnl'])}</td></tr>""")
    return "\n".join(out), len(done)


def _folds(groups, head, cls_="grp-fold"):
    """[(summary html, rows html)] -> one closed fold per group, each a full table."""
    return "\n".join(f'<details class="{cls_}"><summary>{summ}</summary>'
                     f'<div class="tbl"><table>{head}{rows}</table></div></details>'
                     for summ, rows in groups)


def open_folds(d):
    """Running bets, one fold per sport, soonest first inside each."""
    live = [q for q in d["quotes"] if q["status"] == "open" and q["bet"]]
    live.sort(key=lambda q: (list(S.SPORTS).index(q["sport"]), q["start"]))
    by = {}
    for q in live:
        by.setdefault(q["sport"], []).append(q)
    groups = []
    for sport, qs in by.items():
        rows, _n = open_rows(dict(d, quotes=qs))
        rows = re.sub(r'<tr class="grp">.*?</tr>', "", rows, flags=re.S)
        groups.append((f'<b>{esc(S.SPORTS[sport])}</b> <span class="mut">· {len(qs)} running · '
                       f'next {esc(qs[0]["date"])}</span>', rows))
    return _folds(groups, LIVE_HEAD), len(live)


def settled_folds(d):
    """Settled bets, one fold per day they settled, newest first."""
    done = [q for q in d["quotes"] if q["status"] in ("won", "lost", "void") and q["bet"]]
    done.sort(key=lambda q: q.get("settled") or "", reverse=True)
    by = {}
    for q in done:
        by.setdefault((q.get("settled") or "")[:10], []).append(q)
    groups = []
    for day, qs in by.items():
        rows, _n = settled_rows(dict(d, quotes=qs))
        rows = re.sub(r'<tr class="grp">.*?</tr>', "", rows, flags=re.S)
        won = sum(1 for q in qs if q["status"] == "won")
        n = sum(1 for q in qs if q["status"] in ("won", "lost"))
        pl = sum(q["pnl"] for q in qs)
        groups.append((f'<b>{esc(day)}</b> <span class="mut">· {won}/{n} won · </span>'
                       f'<span class="{cls(pl)}">{money(pl)}</span>', rows))
    return _folds(groups, HIST_HEAD), len(done)


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


def unconnected_rows(d=None):
    out = []
    for name, m in S.SOURCES.items():
        if m["connected"]:
            continue
        rec = ""
        if m.get("retired") and d is not None:
            n = sum(1 for q in T.all_bets(d) if q["source"] == name and q.get("bet") and q["status"] in ("won", "lost"))
            rec = f'<div class="sm">{n} settled bets kept on record</div>'
        why = (f'<b class="neg">Retired</b> {esc(m["retired"])}' if m.get("retired") else esc(m["note"]))
        out.append(f"""<tr><td><b>{esc(m['label'])}</b>
<div class="mut sm">{esc(m['kind'])} · {esc(m['site'])}</div>{rec}</td>
<td class="mut">{why}</td></tr>""")
    # A source can lose one sport and keep the others: that pair is retired on its own.
    for name, m in S.SOURCES.items():
        for sport, reason in (m.get("retired_sports") or {}).items():
            rec = ""
            if d is not None:
                n = sum(1 for q in T.all_bets(d) if q["source"] == name and q["sport"] == sport
                        and q.get("bet") and q["status"] in ("won", "lost"))
                rec = f'<div class="sm">{n} settled bets kept on record</div>'
            out.append(f"""<tr><td><b>{esc(m['label'].split(' (')[0])} · {esc(S.SPORTS.get(sport, sport))}</b>
<div class="mut sm">{esc(m['kind'])} · {esc(m['site'])}</div>{rec}</td>
<td class="mut"><b class="neg">Retired</b> {esc(reason)}</td></tr>""")
    return "\n".join(out)


def pair_status(d, st, name, sport):
    """(group, sandbox record, QA-entry record, open bets, last logged) for one (source, sport)."""
    pair = (st.get("pairs") or {}).get(f"{name}|{sport}") or {}
    since = pair.get("since")
    # JUDGED ON THE US EXCHANGES ONLY — the bets that could ever reach Production. The whole
    # record includes the retired polymarket.com venue, and ranking on it showed Covers MLB as
    # working at +8.3% after fees when its exchange record was -22.1%: a pair can look ready on
    # bets that were never tradeable. The whole record is kept alongside, as context.
    a = T.assess(d, name, sport, since=since, venues=T.TRADEABLE_VENUES)
    whole = T.assess(d, name, sport, since=since)
    a = dict(a, whole_n=whole["n"], whole_roi=whole["roi"])
    qa = a
    mine = [q for q in d["quotes"] if q["source"] == name and q["sport"] == sport and q.get("bet")]
    open_n = sum(1 for q in mine if q["status"] == "open")
    last = max((str(q.get("logged") or "") for q in mine), default="")
    if not a["n"]:
        group = "waiting" if open_n else None
    elif a["n"] >= MIN_N:
        group = "working" if (a["roi"] or 0) > 0 and a["z"] > 0 else "failing"
    else:
        group = "leaning" if (a["roi"] or 0) > 0 and a["z"] > 0 else "behind"
    return group, a, qa, open_n, last, pair


# ------------------------------------------------------------------ the page's verdicts
# One plain word per pair instead of a z score. The numbers stay on the row; the word says
# what they add up to, on the same floor the ladder uses (MIN_N settled bets to read).
VERDICTS = {                     # key -> (label, chip class, sort order)
    "proven":    ("Proven edge", "y", 0),
    "working":   ("Working", "y", 1),
    "promising": ("Promising", "w", 2),
    "behind":    ("Behind so far", "n", 3),
    "early":     ("Too early", "n", 4),
    "noedge":    ("No edge", "x", 5),
    "waiting":   ("Waiting for results", "n", 6),
    "removed":   ("Removed from Production", "x", 5),
    "nobets":    ("No qualifying match yet", "n", 7),
    "retired":   ("Retired", "x", 8),
}
EARLY_N = 10      # under this, even a lean is not worth a word: 1-0 is not "promising"


def verdict(a):
    """proven / working / no edge at MIN_N+ settled; promising / behind from EARLY_N; early below."""
    if not a["n"]:
        return "waiting"
    if a["n"] < EARLY_N:
        return "early"
    ahead = (a.get("roi_fee") or 0) > 0 and a["z"] > 0
    if a["n"] >= MIN_N:
        return ("proven" if a["z"] >= 2 else "working") if ahead else "noedge"
    return "promising" if ahead else "behind"


def family(sport):
    """The section a pair sits in: Soccer's markets together, the yes/no markets together."""
    return "Markets" if sport in MARKET_KEYS else S.SPORTS.get(sport, sport).split(" · ")[0]


def pair_list(d, st, include_retired=True):
    """Every (source, sport) pair that has bet, with its record and verdict.

    Retired pairs are listed too, marked, so a sport's section accounts for its own history
    rather than sending the reader to the Reference table to find where the bets went.
    """
    out = []
    for name, meta in S.SOURCES.items():
        if meta.get("kind") in T.NEVER_PROMOTED_KINDS:
            continue
        sports = list(meta["sports"]) if meta["connected"] else []
        gone = {} if not include_retired else dict(
            {sp: why for sp, why in (meta.get("retired_sports") or {}).items()},
            **({sp: meta["retired"] for sp in meta["sports"]} if not meta["connected"] and meta.get("retired") else {}))
        for sport in sports + [sp for sp in gone if sp not in sports]:
            group, a, _qa, open_n, last, pair = pair_status(d, st, name, sport)
            # A cup or international twin is listed from the day it is wired, so it can be
            # reviewed before its first qualifying match; other pairs appear once they bet.
            # A consensus row is listed from the day it is wired too: it only ever bets where
            # two sources agree, so it can sit empty for days and should be visible meanwhile.
            if group is None and not _scope(sport) and name not in T.CONSENSUS:
                continue
            # A pair taken out of Production restarts its count, which on its own reads as a
            # brand-new source ("Waiting for results") and hides the record it was removed on.
            removed = None
            if pair.get("demoted_at") and pair.get("stage") != "production":
                removed = dict(at=str(pair["demoted_at"])[:10],
                               a=T.assess(d, name, sport, until=pair["demoted_at"],
                                          venues=T.TRADEABLE_VENUES))
            v = verdict(a) if group is not None else "nobets"
            if removed and v in ("waiting", "early"):
                v = "removed"
            if sport in gone:
                v = "retired"
            out.append(dict(name=name, sport=sport, meta=meta, a=a, open=open_n, last=last,
                            fade=T.faded(d, name, sport, venues=T.TRADEABLE_VENUES),
                            gone=gone.get(sport), prod=pair.get("stage") == "production",
                            moved=str(pair.get("by_hand") or pair.get("promoted_at") or "")[:10],
                            removed=removed, v=v))
    return out


def _who(r):
    """'Tennis favourite-band rule' or 'ESPN FPI / Matchup Predictor · MLB'."""
    label = r["meta"]["label"].split(" (")[0]
    kind = r["meta"].get("kind")
    sfx = _scope(r["sport"])
    if kind == "Rule":
        return f"{label} · {S.SCOPE_LABEL[sfx]}" if sfx else label
    return f"{label} · {S.SPORTS.get(r['sport'], r['sport'])}"


def _scope(sport):
    """'_cup' / '_intl' for a soccer form twin, '' otherwise."""
    return next((x for x in S.SCOPE_LABEL if str(sport).endswith(x)), "")


def _rec(r):
    a = r["a"]
    return (f'{a["won"]} won v {a["expected"]:.1f} the prices implied on {a["n"]} bets, '
            f'{pct(a["roi_fee"], sign=True)} after fees')


def insights(rows, now=None):
    """What the Sandbox says, in sentences — the reason to open the page."""
    now = now or datetime.now(timezone.utc)
    li = []
    good = sorted((r for r in rows if r["v"] in ("proven", "working")), key=lambda r: -r["a"]["z"])
    if good:
        li.append("<b>Holding up over 30+ bets:</b> " + "; ".join(
            f'{esc(_who(r))} — {esc(_rec(r))}{" (in Production)" if r["prod"] else ""}' for r in good) + ".")
    else:
        li.append(f"<b>Nothing is proven yet:</b> no rule or tipster has {MIN_N}+ settled bets and a lead over the prices.")
    close = sorted((r for r in rows if r["v"] == "promising"), key=lambda r: -r["a"]["n"])[:3]
    if close:
        li.append("<b>Closest to proven:</b> " + "; ".join(
            f'{esc(_who(r))} ({r["a"]["n"]} of {MIN_N} bets, {pct(r["a"]["roi_fee"], sign=True)})'
            for r in close) + ".")
    bad = sorted((r for r in rows if r["v"] == "noedge"), key=lambda r: r["a"]["roi_fee"] or 0)
    if bad:
        li.append("<b>No edge after 30+ bets:</b> " + "; ".join(
            f'{esc(_who(r))} ({pct(r["a"]["roi_fee"], sign=True)} on {r["a"]["n"]})' for r in bad) + ".")
    worst = sorted((r for r in rows if r["v"] == "behind" and r["a"]["n"] >= 10),
                   key=lambda r: r["a"]["roi_fee"] or 0)[:3]
    if worst:
        li.append("<b>Losing early:</b> " + "; ".join(
            f'{esc(_who(r))} ({pct(r["a"]["roi_fee"], sign=True)} on {r["a"]["n"]})' for r in worst) + ".")
    prod = [r for r in rows if r["prod"]]
    if prod:
        li.append(f'<b>In <a href="./production.html">Production</a> ({len(prod)}):</b> ' + "; ".join(
            f'{esc(_who(r))} ({r["a"]["n"]} bets, {pct(r["a"]["roi_fee"], sign=True)})' if r["a"]["n"]
            else f'{esc(_who(r))} (no settled bets yet)' for r in prod) + ".")
    gone = [r for r in rows if r.get("removed") and r["removed"]["a"]["n"]]
    if gone:
        li.append("<b>Removed from Production:</b> " + "; ".join(
            f'{esc(_who(r))} on {esc(r["removed"]["at"])} — {r["removed"]["a"]["won"]} won v '
            f'{r["removed"]["a"]["expected"]:.1f} priced over {r["removed"]["a"]["n"]} bets, '
            f'{pct(r["removed"]["a"]["roi_fee"], sign=True)} after fees' for r in gone)
            + ". Back in the Sandbox, counting again.")
    recent = []
    for m in S.SOURCES.values():
        items = ([(None, m["retired"])] if m.get("retired") else []) + list((m.get("retired_sports") or {}).items())
        for sport, why in items:
            try:
                when = datetime.strptime(str(why)[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            if (now - when).days <= 7:
                recent.append(m["label"].split(" (")[0] + (f" · {S.SPORTS.get(sport, sport)}" if sport else ""))
    if recent:
        li.append(f"<b>Retired this week:</b> {esc(', '.join(recent))} — listed under Reference with their records.")
    return '<ul class="ins">' + "".join(f"<li>{x}</li>" for x in li) + "</ul>"


SPORT_HEAD = ('<tr><th class="num">#</th><th>Rule or tipster</th><th>Verdict</th>'
              '<th class="num">Record</th>'
              '<th class="num">Won v priced</th><th class="num">ROI after fees</th>'
              '<th class="num">v the close</th>'
              '<th class="num">If faded</th>'
              '<th class="num">Open</th><th>Stage</th></tr>')


def close_cell(a):
    """Where this pair's entry prices sat against the closing price.

    Beside the record rather than inside it, because it answers a different question: not
    "did these bets win" but "did the price move toward them before the start". It is the
    only figure here that reads in tens of bets instead of thousands, which is the whole
    reason it is on the page — an efficient market will never hand over 5,000 settled bets.
    Greyed until there are enough fresh closes to say anything, and a pair that is level is
    told so plainly: taking the price the market ends at is what most of them do.
    """
    if not a or a.get("clv") is None or not a.get("clv_n"):
        return '<span class="mut">—</span>'
    read = a.get("clv_read")
    tone = {"ahead": "pos", "behind": "neg"}.get(read, "mut")
    t = a.get("clv_t")
    bits = (f't {t:+.2f} · ' if t is not None else "") + f'{a["clv_n"]} close' + ("" if a["clv_n"] == 1 else "s")
    return (f'<span class="{tone}">{a["clv"] * 100:+.1f}¢</span>'
            f'<div class="sm mut">{bits}{" · " + read if read else ""}</div>')


def rank_key(r):
    """How far ahead of the price a pair is, per bet — the thing every verdict here turns on.

    Not ROI. ROI says how much a pair made, which depends on the prices it happened to be
    offered: a tipster backing 0.30 shots and one backing 0.85 favourites can post the same
    ROI off completely different skill. Wins above what the prices implied, divided by the
    bets, is the same number for both and is what "beating the market" actually means.
    """
    a = r["a"]
    return (a["won"] - a["expected"]) / a["n"] if a["n"] else 0.0


def rank_rows(rs):
    """A sport's pairs, best first, as [(rank|None, provisional, row)].

    Ranked in TIERS, because a ranking that lets 3-0 outrank 201-37 is worse than no
    ranking at all. A pair readable on its own terms (MIN_N settled) is ranked first; one
    with enough to lean on but not to read is ranked below every readable pair however
    pretty its numbers, and marked provisional. Anything thinner, and anything retired, is
    not ranked at all — there is nothing there to rank.
    """
    readable, thin, unranked, retired = [], [], [], []
    for r in rs:
        if r["v"] == "retired":
            retired.append(r)
        elif r["a"]["n"] >= MIN_N:
            readable.append(r)
        elif r["a"]["n"] >= EARLY_N:
            thin.append(r)
        else:
            unranked.append(r)
    readable.sort(key=lambda r: (-rank_key(r), -r["a"]["n"]))
    thin.sort(key=lambda r: (-rank_key(r), -r["a"]["n"]))
    unranked.sort(key=lambda r: (-r["a"]["n"], not r["prod"]))
    retired.sort(key=lambda r: -r["a"]["n"])
    out = [(i + 1, False, r) for i, r in enumerate(readable)]
    out += [(len(readable) + i + 1, True, r) for i, r in enumerate(thin)]
    return out + [(None, False, r) for r in unranked + retired]


def _row(r, rank=None, provisional=False):
    a, meta = r["a"], r["meta"]
    label, chip, _o = VERDICTS[r["v"]]
    rm = r.get("removed")
    if rm and rm["a"]["n"]:
        ra = rm["a"]
        more_rm = (f'<div class="sm mut">Removed {esc(rm["at"])} on {ra["won"]} won v {ra["expected"]:.1f} '
                   f'priced over {ra["n"]} bets, {pct(ra["roi_fee"], sign=True)} after fees'
                   f'{" — no edge" if (ra["roi_fee"] or 0) <= 0 or ra["z"] <= 0 else ""}. '
                   f'Counting again from then.</div>')
    else:
        more_rm = ""
    more = (f'<div class="sm mut">{MIN_N - a["n"]} more {"market-days" if a.get("unit") == "market-day" else "matches" if a.get("unit") == "match" else "settled"} to read</div>'
            if r["v"] in ("promising", "behind", "early") else "")
    sub = S.SPORTS.get(r["sport"], r["sport"])
    thin = a["n"] < MIN_N
    unit = (f'{a["n"]} {a["unit"]}{"" if a["n"] == 1 else ("es" if a["unit"] == "match" else "s")} · {a["n_bets"]} bets'
            if a.get("unit") in ("market-day", "match") else f'{a["n"]} settled')
    rec = (f'{a["won"]}–{a["n"] - a["won"]}<div class="sm mut">{unit}</div>' if a["n"] else "—")
    # The per-bet figure is what the ranking sorts on, shown here so a position can be
    # checked against the row rather than taken on trust.
    vp = (f'{a["won"]} v {a["expected"]:.1f}<div class="sm mut">{a["won"] - a["expected"]:+.1f} wins '
          f'· {rank_key(r):+.3f}/bet</div>' if a["n"] else "—")
    roi = (f'<span class="{"mut" if thin else cls(a["roi_fee"])}">{pct(a["roi_fee"], sign=True)}</span>'
           if a["n"] else "—")
    stage = (f'<span class="sig y">PRODUCTION</span><div class="sm mut">since {esc(r["moved"])}</div>'
             if r["prod"] else '<span class="mut sm">Sandbox</span>')
    # Backing the other side of the same bets. A big positive here is the loud complaint:
    # the selection is finding something and the direction is inverted. Greyed under the
    # read floor, and a dash where there is no single other side (three-way contests).
    fd = r.get("fade") or {}
    fade = ('<span class="mut">—</span>' if not fd.get("n") or fd.get("roi") is None else
            f'<span class="{"mut" if fd["n"] < MIN_N else cls(fd["roi"])}">{pct(fd["roi"], sign=True)}</span>'
            f'<div class="sm mut">{fd["won"]} v {fd["expected"]:.1f} on {fd["n"]}'
            f'{" " + fd["unit"] + ("s" if fd["n"] != 1 else "") if fd.get("unit") else ""}</div>')
    sfx = _scope(r["sport"])
    frags = S.CUP_FRAGS if sfx == "_cup" else S.INTL_FRAGS
    scope_note = (f'<div class="sm"><b>{esc(S.SCOPE_NOTE[sfx].format(", ".join(frags.values())))}</b></div>'
                  if sfx else "")
    tag = f' <span class="sig w">{esc(S.SCOPE_LABEL[sfx].upper())}</span>' if sfx else ""
    if r.get("gone"):
        scope_note = f'<div class="sm"><b>{esc(str(r["gone"]))}</b></div>' + scope_note
    # The rank is greyed while a pair is too thin to read, so the number never pretends to
    # more than it has. An unranked pair shows a dash, not a position it has not earned.
    rk = ('<span class="mut">—</span>' if rank is None else
          f'<span class="{"mut" if provisional else "rank"}">{rank}</span>'
          + ('<div class="sm mut">early</div>' if provisional else ''))
    return f"""<tr><td class="num">{rk}</td><td><details class="src"><summary><b>{esc(meta['label'].split(' (')[0])}</b>{tag}
<div class="sm mut">{esc(sub)} · {esc(meta['kind'])}</div></summary>
{scope_note}<div class="sm mut">{esc(meta.get('note', ''))}</div></details></td>
<td><span class="sig {chip}">{esc(label)}</span>{more}{more_rm}</td>
<td class="num">{rec}</td><td class="num">{vp}</td><td class="num">{roi}</td>
<td class="num">{close_cell(a)}</td>
<td class="num">{fade}</td>
<td class="num">{r['open'] or '—'}</td><td>{stage}</td></tr>"""


def eliminated(r):
    """A pair that fails in every direction, moved out of the sport sections (S.ELIMINATED)."""
    return (r["name"], r["sport"]) in S.ELIMINATED


def eliminated_section(rows):
    """The eliminated pairs, in one collapsed list below the sports: out of sight, on record."""
    gone = sorted((r for r in rows if eliminated(r)), key=lambda r: -r["a"]["n"])
    if not gone:
        return ""
    n_bets = sum(r["a"]["n"] for r in gone)
    return f"""<details class="sport"><summary><b>Eliminated</b>
<span class="mut"> · {len(gone)} pairs · {n_bets} settled bets · failed in every direction</span></summary>
<div class="note sm">Each of these lost after fees AND lost when the other side of the same bets was
backed instead. That is what a pair with no information looks like: with no skill, both sides of a
book lose, because the spread is paid whichever way you face. Retired pairs stay in their own sport;
these were moved out of the sport sections so they stop taking up room. They log nothing new, and
their bets are still counted in the line below.</div>
<div class="tbl"><table>{SPORT_HEAD}{''.join(_row(r) for r in gone)}</table></div></details>"""


def reconcile(d, rows):
    """Where every settled bet is. The sections judge a subset on purpose — a retired venue's
    bets, a baseline's, and anything logged before a pair's clock was reset are all excluded
    from a verdict — so the page says so in numbers rather than leaving a gap to find."""
    bets = [q for q in T.all_bets(d) if q.get("bet") and q["status"] in ("won", "lost")]
    shown = {(r["name"], r["sport"]) for r in rows}
    in_sections = sum((r["a"].get("n_bets") or r["a"]["n"]) for r in rows)
    venue = base = before = other = 0
    for q in bets:
        key = (q["source"], q["sport"])
        if key in shown:
            if (q.get("venue") or "polymarket") not in T.TRADEABLE_VENUES:
                venue += 1
            continue
        if (S.SOURCES.get(q["source"]) or {}).get("kind") in T.NEVER_PROMOTED_KINDS:
            base += 1
        else:
            other += 1
    before = max(0, len(bets) - in_sections - venue - base - other)
    parts = [f"{venue:,} on the retired polymarket.com venue" if venue else "",
             f"{before:,} logged before a pair's clock was reset" if before else "",
             f"{base:,} from the never-betting baselines" if base else "",
             f"{other:,} elsewhere" if other else ""]
    return (f'<div class="note sm"><b>Where the {len(bets):,} settled bets are:</b> '
            f'{in_sections:,} sit in the sections above, counted toward a verdict. The rest are kept '
            f'on record but not judged — ' + ", ".join(p for p in parts if p) + '.</div>')


LEAGUE_HEAD = ('<tr><th>Rule or tipster</th><th>Market</th><th class="num">Record</th>'
               '<th class="num">Won v priced</th><th class="num">ROI after fees</th>'
               '<th class="num">If faded</th></tr>')

SUMMARY_HEAD = ('<tr><th>Competition</th><th class="num">Settled</th><th class="num">Both sides cost</th>'
                '<th class="num">Won v priced</th><th class="num">ROI after fees</th>'
                '<th class="num">If faded</th><th>Best rule here</th></tr>')

LEAGUE_FOLD_N = 8     # a competition gets its own table once it has this many settled bets
LEAGUE_MIN = 3        # under three, a competition has nothing to show, not even a lean


def _cell(v, n, fade=False):
    """A percentage, greyed while the competition is too thin for the number to mean anything."""
    return ('<span class="mut">—</span>' if v is None else
            f'<span class="{"mut" if n < EARLY_N else cls(v)}">{pct(v, sign=True)}</span>')


def _league_row(r, sp):
    """One rule's record inside one competition. The sport table's columns, thinner."""
    rec = f'{sp["won"]}–{sp["n"] - sp["won"]}<div class="sm mut">{sp["n"]} settled</div>'
    vp = (f'{sp["won"]} v {sp["expected"]:.1f}<div class="sm mut">{sp["won"] - sp["expected"]:+.1f} wins '
          f'· {sp["edge"]:+.3f}/bet</div>')
    fade = ('<span class="mut">—</span>' if not sp["fade_n"] or sp["fade_roi"] is None else
            _cell(sp["fade_roi"], sp["n"])
            + f'<div class="sm mut">{sp["fade_won"]} v {sp["fade_expected"]:.1f} on {sp["fade_n"]}</div>')
    mkt = S.SPORTS.get(r["sport"], r["sport"]).split(" · ", 1)
    prod = '<span class="sig y">PRODUCTION</span>' if r["prod"] else ""
    return (f'<tr><td><b>{esc(r["meta"]["label"].split(" (")[0])}</b> {prod}</td>'
            f'<td class="sm mut">{esc(mkt[1] if len(mkt) > 1 else mkt[0])}</td>'
            f'<td class="num">{rec}</td><td class="num">{vp}</td>'
            f'<td class="num">{_cell(sp["roi_fee"], sp["n"])}</td><td class="num">{fade}</td></tr>')


def _league_totals(items):
    """Every rule's bets in one competition added together — the summary row's numbers."""
    n = sum(sp["n"] for _r, sp in items)
    won = sum(sp["won"] for _r, sp in items)
    exp = sum(sp["expected"] for _r, sp in items)
    roi = sum(sp["roi_fee"] * sp["n"] for _r, sp in items) / n if n else None
    fn = sum(sp["fade_n"] for _r, sp in items)
    fade = (sum(sp["fade_roi"] * sp["fade_n"] for _r, sp in items if sp["fade_roi"] is not None)
            / fn) if fn else None
    return n, won, exp, roi, fade


def league_panel(d, rs):
    """Soccer's records split by the competition each bet was struck in.

    A table of every competition first, so the question "which league is a rule working in"
    is answered by scanning one column rather than opening thirty folds; then a table per
    competition with enough bets to be worth opening. Each competition carries its toll —
    what both sides of its markets cost above 100 — because that is the number every rule in
    it clears before it earns anything, and it runs from about 1.5% on a league match winner
    to 6.6% in a cup.
    """
    splits = {}
    for r in rs:
        if not r["a"]["n"]:
            continue
        for sp in T.league_split(d, r["name"], r["sport"], venues=T.TRADEABLE_VENUES):
            splits.setdefault(sp["league"], []).append((r, sp))
    if not splits:
        return ""
    cost = T.league_cost(d, {r["sport"] for r in rs}, venues=T.TRADEABLE_VENUES)
    for items in splits.values():
        items.sort(key=lambda t: (-t[1]["edge"], -t[1]["n"]))
    # Ranked the way the sport tables rank: by wins above what the prices implied, per bet —
    # but in TIERS, because on this little data per competition an ordering that lets 3-1
    # outrank 18-7 is worse than none. A competition with enough settled bets to lean on is
    # ordered first; everything thinner sits below it however pretty its numbers, and
    # "Other competitions" is a bag of one-offs rather than a competition, so it sits last.
    def _order_key(lg):
        n, won, exp, _roi, _fade = _league_totals(splits[lg])
        return (lg == "Other competitions", n < EARLY_N, -(won - exp) / n)

    order = sorted((lg for lg in splits if _league_totals(splits[lg])[0] >= LEAGUE_MIN), key=_order_key)
    if not order:
        return ""
    summary, folds = [], []
    for lg in order:
        items = splits[lg]
        n, won, exp, roi, fade = _league_totals(items)
        hold, hold_n = cost.get(lg, (None, 0))
        best = items[0]
        thin = "" if n >= EARLY_N else '<div class="sm mut">too thin to read</div>'
        summary.append(
            f'<tr><td><b>{esc(lg)}</b>{thin}</td><td class="num">{n}</td>'
            f'<td class="num">{"—" if hold is None else f"{hold * 100:.1f}%"}'
            f'<div class="sm mut">{f"on {hold_n} quoted" if hold is not None else ""}</div></td>'
            f'<td class="num">{won} v {exp:.1f}<div class="sm mut">{won - exp:+.1f} wins '
            f'· {(won - exp) / n:+.3f}/bet</div></td>'
            f'<td class="num">{_cell(roi, n)}</td><td class="num">{_cell(fade, n)}</td>'
            f'<td class="sm">{esc(best[0]["meta"]["label"].split(" (")[0])}'
            f'<div class="sm mut">{best[1]["won"]}–{best[1]["n"] - best[1]["won"]} '
            f'· {best[1]["edge"]:+.3f}/bet</div></td></tr>')
        if n >= LEAGUE_FOLD_N:
            folds.append(f"""<details class="sport"><summary><b>{esc(lg)}</b>
<span class="mut"> · {n} settled{"" if hold is None else f" · both sides cost {hold * 100:.1f}%"}
 · {len(items)} rule{"" if len(items) == 1 else "s"}</span></summary>
<div class="tbl"><table>{LEAGUE_HEAD}{''.join(_league_row(r, sp) for r, sp in items)}</table></div></details>""")
    return f"""<details class="sport"><summary><b>By competition</b>
<span class="mut"> · {len(order)} competitions · which league a rule works in, and what that league costs</span></summary>
<div class="note sm">The same rules, split by the competition each bet was struck in, because they
are not one market: over the two years of results on file the Bundesliga scored 3.49 goals a game
and Serie A 2.38, and the toll in the <b>Both sides cost</b> column runs from about 1.5% to 6.6%.
That toll is what a rule has to clear in that competition before it earns anything.
<b>Read this as description, not as a verdict.</b> Cutting a record this many ways multiplies the
looks, and the best slice always looks good: across 47 league-by-market cells of the market's own
prices, five beat z 1.5 where chance alone produces six, and none reached z 2 where chance
produces two. Figures are greyed under {EARLY_N} settled, nothing here promotes or retires a rule,
and the verdict column above goes on reading the whole record. A competition gets its own table at
{LEAGUE_FOLD_N} settled bets; below that it is a summary row only.</div>
<div class="tbl"><table>{SUMMARY_HEAD}{''.join(summary)}</table></div>
{''.join(folds)}</details>"""


# Soccer only, for now: it is the one sport where the same rule meets a materially
# different market in each competition, and the one with enough competitions to sort.
BY_LEAGUE = ("Soccer",)


def sport_sections(d, rows):
    """One folding section per sport: Production and the strongest records first."""
    fams = {}
    for r in rows:
        fams.setdefault(family(r["sport"]), []).append(r)
    order = sorted(fams, key=lambda f: (-sum(r["prod"] for r in fams[f]),
                                        -sum(r["a"]["n"] for r in fams[f])))
    out = []
    for f in order:
        ranked = rank_rows(fams[f])
        rs = [r for _rk, _p, r in ranked]
        n_prod = sum(r["prod"] for r in rs)
        # The top of the ranking, named in the summary, so the order is visible without
        # opening the section. Only a readable pair can be "best" — never a provisional one.
        best = next((r for rk, prov, r in ranked if rk and not prov), None)
        bits = [f"{len(rs)} tested"] + ([f"{n_prod} in Production"] if n_prod else [])
        if best:
            bits.append(f"best: {best['meta']['label'].split(' (')[0]} "
                        f"{best['a']['won'] - best['a']['expected']:+.1f} wins v the price "
                        f"on {best['a']['n']}")
        out.append(f"""<details class="sport"><summary><b>{esc(f)}</b>
<span class="mut"> · {esc(' · '.join(bits))}</span></summary>
<div class="note sm">Ranked best to worst by <b>wins above what the prices implied, per bet</b> —
not by ROI, which mostly reflects the prices a pair happened to be offered. A pair is ranked
once it has {MIN_N} settled; between {EARLY_N} and {MIN_N} it ranks below every readable pair and
is greyed; under {EARLY_N}, and once retired, it is not ranked at all.
<b>If faded</b> is what backing the OTHER side of the same bets would have returned. It is not
this row's ROI with the sign flipped — both sides of a book are sold above fair, so fading an
average rule loses that overround plus its fee. A large positive there means the rule is
picking the wrong side, which is a different complaint from having no edge.
<b>v the close</b> is how far the price moved toward this pair's pick between its bet and the
start, in cents per bet, with t — the mean over its own standard error. It answers a different
question from the record, and far sooner: a win record carries the outcome's own noise, so on a
market priced near even a real 2% edge needs thousands of settled bets to reach z 2, while the
same rule's closing prices can read in tens. Read at {T.CLV_MIN_N}+ fresh closes and called
<b>ahead</b> or <b>behind</b> at t {T.CLV_T:g}; <b>level</b> is a real answer, not a missing one.
Beating the close is not the same as making money, and nothing is promoted or retired on it
alone.</div>
<div class="tbl"><table>{SPORT_HEAD}{''.join(_row(r, rk, prov) for rk, prov, r in ranked)}</table></div>
{league_panel(d, rs) if f in BY_LEAGUE else ''}</details>""")
    return "\n".join(out)


TRADE_HEAD = ('<tr><th>Rule</th><th>Verdict</th><th class="num">Entry days</th>'
              '<th class="num">Trades</th><th class="num">Mean per day</th>'
              '<th class="num">Edge</th><th class="num">P/L</th><th class="num">Last</th></tr>')


def trading_rows(md):
    """The trading lane: one row per rule, counted per ENTRY DAY (see market_track)."""
    import market_track as MT
    rows = []
    for r in sorted(MT.report(md), key=lambda r: (MT.VERDICTS[r["verdict"]][2], -r["days"])):
        meta = MT.RULES[r["rule"]]
        label, chip, _o = MT.VERDICTS[r["verdict"]]
        more = (f'<div class="sm mut">{MT.READ_FLOOR - r["days"]} more entry days to read</div>'
                if r["verdict"] in ("promising", "behind", "early") else "")
        pc = lambda x: "—" if x is None else f'<span class="{cls(x)}">{x*100:+.2f}%</span>'
        # A stock pick is judged against SPY over its own days; a timing rule on an index or a
        # coin against cash, since set against its own asset it would show zero edge by design.
        vs = "v cash" if meta.get("bench") == "cash" else "v SPY"
        rows.append(f"""<tr><td><details class="src"><summary><b>{esc(meta['label'])}</b>
<div class="sm mut">{esc(meta['lane'].title())} · {esc(r['rule'])}</div></summary>
<div class="sm mut">{esc(meta['note'])}</div></details></td>
<td><span class="sig {chip}">{esc(label)}</span>{more}</td>
<td class="num">{r['days']}</td>
<td class="num">{r['trades']}<div class="sm mut">{r['open']} open</div></td>
<td class="num">{pc(r['mean'])}<div class="sm mut">{f"t {r['t']:+.2f}" if r['days'] > 1 else ''}</div></td>
<td class="num">{pc(r['edge'])}<div class="sm mut">{vs}{f" · t {r['edge_t']:+.2f}" if r['days'] > 1 else ''}</div></td>
<td class="num {cls(r['total'])}">{money(r['total']) if r['trades'] else '—'}</td>
<td class="num mut sm">{esc(r['last'][:10]) or '—'}</td></tr>
<tr><td colspan="8" class="sm mut">Backtest before the lane went live ({esc(str((r.get('research_window') or ['', ''])[0]))} to
{esc(str((r.get('research_window') or ['', ''])[1]))}, not part of the record above):
{r['research_days']} entry days, {r['research_trades']} trades,
{'—' if r['research_edge'] is None else f"{r['research_edge']*100:+.2f}%"} a day {vs}, t {r['research_t']:+.2f}.</td></tr>""")
    return "\n".join(rows)


def build():
    d = T.load()
    st = T.load_stages()
    scores = T.score(d)
    cov = d.get("coverage") or {}
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    ou = (d.get("meta") or {}).get("odds_api") or {}
    odds_line = (f" Pinnacle prices come through The Odds API: {ou.get('calls', 0)} of "
                 f"{ou.get('allowance', '?')} allowed paid calls last run, "
                 f"{ou['remaining']} credits left until they reset on the 1st."
                 if ou.get("remaining") is not None else "")
    live_html, n_live = open_folds(d)
    hist_html, n_hist = settled_folds(d)
    n_void = sum(1 for q in d["quotes"] if q["status"] == "void" and q["bet"])
    n_unconnected = sum(1 for m in S.SOURCES.values() if not m["connected"])
    in_prod = sum(1 for p in (st.get("pairs") or {}).values() if p.get("stage") == "production")
    # Counted over the pairs still running. Pooling every bet ever logged put this at 46%,
    # but 952 of the misses were one retired rule that quoted hundreds of ladder rungs a day
    # and can never improve — a number dragged down by history says nothing about whether the
    # snapshots are working now.
    live = {(r["name"], r["sport"]) for r in pair_list(d, st) if r["v"] != "retired"}
    leads = sorted(x for x in (T.close_lead_min(q) for q in d["quotes"]
                               if q.get("bet") and (q["source"], q["sport"]) in live)
                   if x is not None and x >= 0)
    close_line = (f" A closing price counts only when taken within {T.CLOSE_MAX_LEAD_MIN} minutes "
                  f"of the start ({sum(1 for x in leads if x <= T.CLOSE_MAX_LEAD_MIN)} of {len(leads)} "
                  f"on the pairs still running).") if leads else ""

    rows = pair_list(d, st)
    # Eliminated pairs leave the sport sections and the insights, but NOT the reconciliation:
    # every settled bet still has to be accounted for, out of sight or not.
    shown = [r for r in rows if not eliminated(r)]
    vc = {k: sum(1 for r in rows if r["v"] == k and not r.get("gone")) for k in VERDICTS}
    import market_track as MT, market_sources as MS
    md = MT.load()
    trade_rules = MT.report(md)
    trade_open = sum(r["open"] for r in trade_rules)
    trade_note = ("" if MS.configured() else
                  '<div class="note">These rules are scanned and graded on the machine that holds '
                  'the market data keys, and the record below is what it published. This page is '
                  'built elsewhere and only renders it, so it does not reach the market itself.</div>')

    return f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sandbox Tracker</title>
<meta name="description" content="Every source and rule under test, per sport, at real prices and settled on real results — what is working and what is not.">
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
.rank{{font-weight:800;font-size:15px}}
.st,.sig{{display:inline-block;font-size:9.5px;font-weight:800;letter-spacing:.05em;
border-radius:999px;padding:2px 7px;border:1px solid;white-space:nowrap}}
.st.won,.sig.y{{color:var(--pos);border-color:#3fb97055;background:#3fb97014}}
.st.lost,.st.miss{{color:var(--neg);border-color:#e06c7555;background:#e06c7514}}
.st.void,.sig.n{{color:var(--mut);border-color:var(--bd)}}
.sig.w{{color:var(--warn);border-color:#f0b42955;background:#f0b42914}}
.sig.x{{color:var(--neg);border-color:#e06c7555;background:#e06c7514}}
ul.ins{{padding-left:18px;display:grid;gap:7px;color:var(--fg);font-size:13.5px;line-height:1.55}}
details.sport{{background:var(--card);border:1px solid var(--bd);border-radius:11px;margin-bottom:10px}}
details.sport>summary{{cursor:pointer;padding:12px 14px;font-size:14px;list-style:none}}
details.sport>summary::-webkit-details-marker{{display:none}}
details.sport>summary::before{{content:"▸ ";color:var(--mut)}}
details.sport[open]>summary::before{{content:"▾ "}}
details.sec{{margin-top:26px}}
details.sec>summary{{cursor:pointer;list-style:none}}details.sec>summary::-webkit-details-marker{{display:none}}
details.sec>summary h2{{display:inline;margin:0}}
details.sec>summary::before{{content:"▸ ";color:var(--mut);font-size:12px}}
details.sec[open]>summary::before{{content:"▾ "}}
details.sec[open]>summary{{margin-bottom:12px}}
details.grp-fold{{background:var(--card);border:1px solid var(--bd);border-radius:10px;margin-bottom:8px}}
details.grp-fold>summary{{cursor:pointer;padding:10px 13px;font-size:13px;list-style:none}}
details.grp-fold>summary::-webkit-details-marker{{display:none}}
details.grp-fold>summary::before{{content:"▸ ";color:var(--mut)}}
details.grp-fold[open]>summary::before{{content:"▾ "}}
details.grp-fold .tbl{{border:none;border-top:1px solid var(--bd);border-radius:0 0 10px 10px;margin:0}}
.folds-ctl{{display:flex;gap:6px;margin-bottom:10px}}
.folds-ctl button{{font:inherit;font-size:11.5px;font-weight:700;color:var(--mut);background:var(--card);
border:1px solid var(--bd);border-radius:999px;padding:4px 11px;cursor:pointer}}
.folds-ctl button:hover{{color:var(--fg)}}
details.sport .tbl{{border:none;border-top:1px solid var(--bd);border-radius:0 0 11px 11px;margin:0}}
details.more{{margin:-4px 0 14px}}
input.flt{{font:inherit;font-size:13px;color:var(--fg);background:var(--card);border:1px solid var(--bd);
border-radius:9px;padding:8px 12px;outline:none;width:100%;margin-bottom:9px}}
input.flt:focus{{border-color:var(--acc)}}
details.more>summary{{cursor:pointer;font-size:12px;font-weight:700;color:var(--acc);
padding:6px 2px;list-style:none}}
details.more>summary::-webkit-details-marker{{display:none}}
details.more>summary::before{{content:"▸ "}}
details.more[open]>summary::before{{content:"▾ "}}
.grp td{{font-size:10px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:var(--mut);background:#0d1119;padding:7px 11px}}
.tabs{{display:flex;gap:6px;flex-wrap:wrap;margin:6px 0 12px}}
.tabs button{{font:inherit;font-size:12px;font-weight:700;color:var(--mut);background:var(--card);
border:1px solid var(--bd);border-radius:999px;padding:6px 13px;cursor:pointer}}
.tabs button.on{{color:var(--fg);border-color:var(--mut);background:#161b26}}
.tabs button b{{margin-left:5px}}
.grp.ok td{{color:var(--pos)}}.grp.bad td{{color:var(--neg)}}
details.src>summary{{cursor:pointer;list-style:none}}details.src>summary::-webkit-details-marker{{display:none}}
details.src .sm{{margin-top:6px;max-width:420px;line-height:1.5}}
details.ref{{background:var(--card);border:1px solid var(--bd);border-radius:11px;padding:10px 14px;margin-bottom:10px}}
details.ref>summary{{cursor:pointer;font-size:12.5px;font-weight:700}}
details.ref[open]>summary{{margin-bottom:10px}}
.bar{{display:inline-block;width:64px;height:5px;border-radius:3px;background:#1a1f2b;vertical-align:middle;overflow:hidden}}
.bar i{{display:block;height:100%;background:var(--acc)}}
footer{{margin-top:40px;font-size:12px;color:var(--mut);text-align:center}}
@media (max-width:600px){{body{{padding:18px 10px 44px;font-size:14px}}h1{{font-size:19px}}}}
</style></head><body><div class="wrap">

<h1>Sandbox</h1>
<div class="sub">Every source and rule under test, per sport · updated {esc(now)}</div>
<div class="nav"><a class="on" href="./sandbox.html">Sandbox</a><a class="" href="./production.html">Production</a></div>

<div class="tiles">
<div class="tile"><b>{in_prod}</b><span>in Production</span></div>
<div class="tile"><b class="{'pos' if vc['proven'] + vc['working'] else ''}">{vc['proven'] + vc['working']}</b><span>working (30+ bets)</span></div>
<div class="tile"><b>{vc['promising']}</b><span>promising (10+ bets)</span></div>
<div class="tile"><b class="{'neg' if vc['noedge'] else ''}">{vc['noedge']}</b><span>no edge</span></div>
<div class="tile"><b>{n_live:,}</b><span>bets running</span></div>
</div>
{feed_health(d)}

<div class="tabs" id="lanes"><button type="button" data-lane="sports" class="on">Sports<b>{len(rows)}</b></button><button type="button" data-lane="trading">Trading<b>{len(trade_rules)}</b></button></div>

<div data-lane="sports">
<details class="sec" open><summary><h2>What the Sandbox says</h2></summary>
<div class="note">{insights(shown)}</div></details>

<details class="sec" open><summary><h2>Every rule and tipster, by sport</h2></summary>
<div class="folds-ctl"><button type="button" data-fold="sport" data-open="1">Open all</button><button type="button" data-fold="sport" data-open="0">Close all</button></div>
{sport_sections(d, shown)}
{eliminated_section(rows)}
{reconcile(d, rows)}
<div class="note sm"><b>Record</b>: settled bets won–lost on the US exchanges, flat ${int(T.STAKE)} a bet at the price
available before the start. <b>Won v priced</b>: wins against the wins the prices implied — beating that is the
whole test. <b>Verdict</b>: read only at {MIN_N}+ settled bets — <i>Proven edge</i> is ahead of the prices by
z ≥ 2, <i>Working</i> is ahead, <i>No edge</i> is not; under {MIN_N} a pair is only <i>Promising</i> or
<i>Behind so far</i>, and under {EARLY_N} it is <i>Too early</i>. Production is entered by hand. Click a name for what it is.</div>
</details>

<details class="sec"><summary><h2>Running now ({n_live:,})</h2></summary>
{('<input class="flt" type="search" data-for="live" placeholder="Filter running bets — team, source, sport…">' + '<div id="live">' + live_html + '</div>') if n_live else '<div class="note">No open bets.</div>'}
</details>

<details class="sec"><summary><h2>Settled ({n_hist - n_void:,}{f" · {n_void} void" if n_void else ""})</h2></summary>
{('<input class="flt" type="search" data-for="hist" placeholder="Filter settled bets — team, source, sport…">' + '<div id="hist">' + hist_html + '</div>') if n_hist else '<div class="note">Nothing settled yet.</div>'}
</details>

</div>

<div data-lane="trading" hidden>
<div class="tiles">
<div class="tile"><b>{sum(1 for r in trade_rules if r['verdict'] in ('proven', 'working'))}</b><span>working (30+ days)</span></div>
<div class="tile"><b>{sum(1 for r in trade_rules if r['verdict'] == 'promising')}</b><span>promising</span></div>
<div class="tile"><b class="{'neg' if any(r['verdict'] == 'noedge' for r in trade_rules) else ''}">{sum(1 for r in trade_rules if r['verdict'] == 'noedge')}</b><span>no edge</span></div>
<div class="tile"><b>{sum(r['trades'] for r in trade_rules):,}</b><span>trades logged</span></div>
<div class="tile"><b>{trade_open:,}</b><span>open now</span></div>
</div>
{trade_note}
<h2>Stock rules under test</h2>
<div class="tbl"><table>{TRADE_HEAD}{trading_rows(md)}</table></div>
<div class="note sm">Each rule is <b>pre-registered</b>: its thresholds and the reason for them are fixed before it
logs a trade. A trade is logged only from bars that closed BEFORE it, and enters at the <b>next</b> bar's open —
never the signal bar's close. Costs of {int(MS.COST_BPS_PER_SIDE)}bp a side are charged on entry and exit.
<b>Judged per entry day</b>, because names bought the same morning rise and fall together, and against
<b>SPY over the identical days</b>: beating a rising market is not an edge. Read at {MT.READ_FLOOR}+ entry days;
under {MT.EARLY_N} a rule is only <i>Too early</i>. Click a rule for what it does.</div>
</div>

<div data-lane="sports">
<details class="sec"><summary><h2>Reference</h2></summary>
<details class="ref"><summary>Retired, or declared but not connected ({n_unconnected})</summary>
<div class="tbl"><table><tr><th>Source</th><th>Why it is not scored</th></tr>{unconnected_rows(d)}</table></div></details>
<details class="ref"><summary>Stamp of approval — every criterion, every source</summary>
<div class="note">The stamp needs <b>{T.APPROVAL['min_bets']}+ settled bets spanning {T.APPROVAL['min_days']}+ days</b>
({T.SPORT_RULES['high']['approval']['min_bets']}+ fresh bets at z ≥ {T.SPORT_RULES['high']['approval']['z_min']:g}, no day span, in high-volume sports),
wins beating the price by z ≥ {T.APPROVAL['z_min']:g}, ROI beating every blind rule on the same contests,
still profitable without its biggest win, and profitable in both halves. Fixed 2026-09-12.</div>
{approval_table(d, scores)}</details>
<details class="ref"><summary>Blind baselines — what choosing nothing made</summary>{baseline_table(d)}</details>
<details class="ref"><summary>Pinnacle v venue</summary>{pinnacle_table(d)}</details>
<details class="ref"><summary>Feed coverage on the last run</summary>{coverage_table(cov)}</details>
<details class="ref"><summary>Method</summary><div class="note">
Tipsters and rules name a side and are backed every time; models, books and exchanges state a probability
and are backed only on a {int(T.EDGE_MIN*100)}pp disagreement with the price. <b>Polymarket US</b> is the venue
wherever it lists a contest; <b>Kalshi</b> is the venue for soccer and anything Polymarket US is missing, with
soccer kickoffs taken from ESPN. A contest is logged only with a real book (spread ≤ {int(S.MAX_SPREAD*100)}¢), at the
ask. Until 2026-09-13 the venue was polymarket.com; those bets still settle there but are not counted when a pair is judged.
Quotes logged before the book rule on boxing, cricket and table tennis were voided ({esc(T.PRE_GATE_NOTE)}).{odds_line}{close_line}
A positive ROI under {MIN_N} settled bets is not a finding.</div></details>

</details>

</div>

<footer>Read-only static export · rebuilt by GitHub Actions · research, not betting advice.</footer>
<script>
document.querySelectorAll('#lanes button').forEach(b => b.addEventListener('click', () => {{
  document.querySelectorAll('#lanes button').forEach(x => x.classList.toggle('on', x === b));
  document.querySelectorAll('[data-lane]:not(button)').forEach(el => el.hidden = el.dataset.lane !== b.dataset.lane);
}}));
document.querySelectorAll('.folds-ctl button').forEach(b => b.addEventListener('click', () => {{
  document.querySelectorAll('details.' + b.dataset.fold).forEach(dt => dt.open = b.dataset.open === '1');
}}));
document.querySelectorAll('input.flt').forEach(inp => inp.addEventListener('input', () => {{
  const box = document.getElementById(inp.dataset.for), q = inp.value.trim().toLowerCase();
  box.querySelectorAll('details').forEach(dt => {{ if (q) dt.open = true; }});
  box.querySelectorAll('table').forEach(t => {{
    let grp = null, any = false;
    t.querySelectorAll('tr').forEach(tr => {{
      if (tr.querySelector('th')) return;
      if (tr.classList.contains('grp')) {{ if (grp) grp.hidden = !any; grp = tr; any = false; return; }}
      const hit = !q || tr.textContent.toLowerCase().includes(q);
      tr.hidden = !hit; any = any || hit;
    }});
    if (grp) grp.hidden = !any;
    const fold = t.closest('details.grp-fold');
    if (fold) fold.hidden = q && !t.querySelector('tr:not([hidden]) td');
  }});
}}));
</script>
</div></body></html>"""


# The QA page is gone (2026-09-18): the ladder is Sandbox, then Production by hand.
def _ticks(gate):
    passed = sum(1 for _k, _l, p, _d in gate if p)
    cells = "".join(
        f'<td><span class="{"pos" if p else "neg"}">{"✓" if p else "✗"}</span>'
        f'<div class="sm mut">{esc(det)}</div></td>' for _k, _l, p, det in gate)
    return passed, cells


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    page = build()
    with open(OUT, "w") as f:
        f.write(page)
    print(f"wrote {OUT}")
    # Production shares the Sandbox page's stylesheet rather than keeping a second copy of it.
    style = re.search(r"<style>.*?</style>", page, re.S).group(0)
    import production
    prod_out = os.path.join(os.path.dirname(OUT), "production.html")
    with open(prod_out, "w") as f:
        f.write(production.page(T.load(), T.load_stages(), production.load_feed(), style))
    print(f"wrote {prod_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
