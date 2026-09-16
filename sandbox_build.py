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
SPORT_KEYS = ["soccer", "soccer_btts", "soccer_o15", "soccer_team1", "soccer_team2", "soccer_u35", "soccer_p05", "tennis", "table_tennis", "boxing", "mma", "nfl", "cricket", "mlb"]

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
        clv_cell = "—"
        if a and a["clv"] is not None:
            clv_cell = (f'<span class="{cls(a["clv"]) if a["clv_n"] >= MIN_N else "mut"}">'
                        f'{"+" if a["clv"] >= 0 else ""}{a["clv"]*100:.1f}¢</span>'
                        f'<div class="sm mut">{a["clv_n"]} bet{"" if a["clv_n"] == 1 else "s"}</div>')
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
<td class="num">{clv_cell}</td>
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
    return "\n".join(out)


GROUPS = [
    ("working", "Working", "ok", "30+ settled bets and ahead of the price: wins beat what the prices implied and ROI is positive."),
    ("failing", "Not working", "bad", "30+ settled bets and not ahead of the price. Kept running — a record can turn — but nothing here is an edge today."),
    ("leaning", "Too early · leaning ahead", "", "Under 30 settled bets, ahead of the price so far. Unreadable yet: watch, don't trust."),
    ("behind", "Too early · leaning behind", "", "Under 30 settled bets, behind the price so far."),
    ("waiting", "Waiting for results", "", "Bets logged, nothing settled yet."),
]


def pair_status(d, st, name, sport):
    """(group, sandbox record, QA-entry record, open bets, last logged) for one (source, sport)."""
    pair = (st.get("pairs") or {}).get(f"{name}|{sport}") or {}
    since = pair.get("since")
    a = T.assess(d, name, sport, since=since)
    qa = T.assess(d, name, sport, since=since, venues=T.TRADEABLE_VENUES)
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


def pair_rows(d, st):
    """Every betting (source, sport) pair, sorted into GROUPS. -> ({group: [html rows]}, counts)."""
    rows = {g[0]: [] for g in GROUPS}
    for name, meta in S.SOURCES.items():
        if not meta["connected"]:
            continue
        for sport in meta["sports"]:
            group, a, qa, open_n, last, pair = pair_status(d, st, name, sport)
            if group is None:
                continue
            if meta.get("kind") in T.NEVER_PROMOTED_KINDS:
                continue
            gates = T.qa_entry(qa) if qa["n"] else []
            passed = sum(1 for _k, _l, p, _d in gates if p)
            if pair.get("stage") == "qa":
                stage = f'<span class="sig y">IN QA</span><div class="sm mut">since {esc(pair["promoted_at"][:10])}</div>'
            elif (pair.get("fast_track") or {}).get("state") in ("probation", "cleared"):
                stage = f'<span class="sig w">FAST TRACK</span><div class="sm mut">{esc(pair["fast_track"]["state"])}</div>'
            else:
                need = T.sport_rules(sport)["entry"]["min_bets"]
                fill = min(100, int(100 * qa["n"] / need)) if need else 0
                stage = (f'<span class="bar"><i style="width:{fill}%"></i></span> '
                         f'<span class="sm">{qa["n"]}/{need}</span>'
                         f'<div class="sm mut">{passed}/{len(gates) or 4} QA gates</div>')
            won_exp = f'{a["won"]} v {a["expected"]:.1f}' if a["n"] else "—"
            thin = a["n"] < MIN_N
            vb = "—"
            if a["base_roi"] is not None:
                gap = a["own_roi"] - a["base_roi"]
                vb = f'<span class="{"mut" if thin else cls(gap)}">{gap*100:+.1f}pp</span>'
            clv = (f'<span class="{"mut" if a["clv_n"] < MIN_N else cls(a["clv"])}">{a["clv"]*100:+.1f}¢</span>'
                   f'<div class="sm mut">{a["clv_n"]} closes</div>') if a["clv"] is not None else "—"
            rows[group].append((a["z"] if a["n"] else -99, f"""<tr data-g="{group}">
<td><details class="src"><summary><b>{esc(meta['label'].split(' (')[0])}</b>
<div class="sm mut">{esc(S.SPORTS.get(sport, sport))} · {esc(meta['kind'])}</div></summary>
<div class="sm mut">{esc(meta.get('note', ''))}</div></details></td>
<td class="num">{a['n']}<div class="sm mut">{open_n} open</div></td>
<td class="num">{won_exp}<div class="sm mut">{f"z {a['z']:+.2f}" if a['n'] else ''}</div></td>
<td class="num"><span class="{'mut' if thin else cls(a['roi'])}">{pct(a['roi'], sign=True)}</span></td>
<td class="num">{vb}</td>
<td class="num">{clv}</td>
<td>{stage}</td>
<td class="num mut sm">{esc(last[:10]) or '—'}</td></tr>"""))
    counts = {g: len(v) for g, v in rows.items()}
    return {g: [r for _z, r in sorted(v, key=lambda t: -t[0])] for g, v in rows.items()}, counts


PAIR_HEAD = ('<tr><th>Source · sport</th><th class="num">Settled</th><th class="num">Won v priced</th>'
             '<th class="num">ROI</th><th class="num">v blind</th><th class="num">Beat the close</th>'
             '<th>Road to QA</th><th class="num">Last bet</th></tr>')


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
    live_rows, n_live = open_rows(d)
    hist_rows, n_hist = settled_rows(d)
    n_void = sum(1 for q in d["quotes"] if q["status"] == "void" and q["bet"])
    n_unconnected = sum(1 for m in S.SOURCES.values() if not m["connected"])
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    settled_today = [q for q in d["quotes"] if q["bet"] and q["status"] in ("won", "lost")
                     and str(q.get("settled") or "")[:10] == today]
    in_qa = sum(1 for p in (st.get("pairs") or {}).values() if p.get("stage") == "qa")
    leads = sorted(x for x in (T.close_lead_min(q) for q in d["quotes"] if q.get("bet"))
                   if x is not None and x >= 0)
    close_line = (f" A closing price counts only when taken within {T.CLOSE_MAX_LEAD_MIN} minutes "
                  f"of the start ({sum(1 for x in leads if x <= T.CLOSE_MAX_LEAD_MIN)} of {len(leads)} so far).")

    groups, counts = pair_rows(d, st)
    on = ' class="on"'
    # Open on the first group that has anything in it.
    first = next((g for g, *_r in GROUPS if counts[g]), "working")
    tabs = "".join(f'<button type="button" data-tab="{g}"{on if g == first else ""}>{esc(t)}<b>{counts[g]}</b></button>'
                   for g, t, _c, _n in GROUPS)
    body = []
    for g, title, klass, note in GROUPS:
        if not groups[g]:
            body.append(f'<tr class="grp {klass}" data-g="{g}"><td colspan="8">{esc(title)} · none right now</td></tr>'
                        f'<tr data-g="{g}"><td colspan="8" class="mut sm">{esc(note)}</td></tr>')
            continue
        body.append(f'<tr class="grp {klass}" data-g="{g}"><td colspan="8">{esc(title)} · {len(groups[g])}</td></tr>'
                    f'<tr data-g="{g}"><td colspan="8" class="mut sm">{esc(note)}</td></tr>')
        body.extend(groups[g])

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
.st,.sig{{display:inline-block;font-size:9.5px;font-weight:800;letter-spacing:.05em;
border-radius:999px;padding:2px 7px;border:1px solid;white-space:nowrap}}
.st.won,.sig.y{{color:var(--pos);border-color:#3fb97055;background:#3fb97014}}
.st.lost,.st.miss{{color:var(--neg);border-color:#e06c7555;background:#e06c7514}}
.st.void,.sig.n{{color:var(--mut);border-color:var(--bd)}}
.sig.w{{color:var(--warn);border-color:#f0b42955;background:#f0b42914}}
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
<div class="nav"><a href="./">Leads</a>
<a href="./streaks.html">Streaks</a><a href="./record.html">Record</a>
<a href="./today.html">Today</a><a class="on" href="./sandbox.html">Sandbox</a><a href="./qa.html">QA</a><a href="./production.html">Production</a></div>

<div class="note warn">Each <b>source in a sport</b> is tracked on its own: logged before the start at the price
available then, flat ${int(T.STAKE)} a bet, settled on the real result. A pair is only <b>readable at
{MIN_N}+ settled bets</b>; below that it is sorted by which way it leans, nothing more. Pairs that
clear the QA entry gate move to <a href="./qa.html">QA</a>.</div>

<div class="tiles">
<div class="tile"><b class="{'pos' if counts['working'] else ''}">{counts['working']}</b><span>working</span></div>
<div class="tile"><b class="{'neg' if counts['failing'] else ''}">{counts['failing']}</b><span>not working</span></div>
<div class="tile"><b>{counts['leaning'] + counts['behind'] + counts['waiting']}</b><span>too early to tell</span></div>
<div class="tile"><b>{in_qa}</b><span>in QA</span></div>
<div class="tile"><b>{n_live:,}</b><span>bets running</span></div>
<div class="tile"><b>{sum(1 for q in settled_today if q['status'] == 'won')}/{len(settled_today)}</b><span>won today</span></div>
</div>
{feed_health(d)}

<h2>Sources and rules</h2>
<div class="tabs" id="tabs">{tabs}<button type="button" data-tab="all">All</button></div>
<div class="tbl"><table id="pairs">{PAIR_HEAD}{''.join(body)}</table></div>
<div class="note sm"><b>Won v priced</b>: wins against the wins the prices implied — the test that matters while
samples are small. <b>v blind</b>: ROI minus the best blind rule (back the favourite / underdog / draw, or
the rule's own population) on the same contests. <b>Beat the close</b>: closing price minus price paid.
<b>Road to QA</b>: settled bets on the US exchanges against what QA needs for that sport, and how many of its
four entry gates hold. <b>Thresholds are per sport</b>: most need {T.QA_ENTRY['min_bets']}+ bets over {T.QA_ENTRY['min_days']}+ days
at z ≥ {T.QA_ENTRY['z_min']:g}; high-volume sports ({', '.join(S.SPORTS[x] for x in T.HIGH_VOLUME_SPORTS)}) need
{T.SPORT_RULES['high']['entry']['min_bets']}+ bets at z ≥ {T.SPORT_RULES['high']['entry']['z_min']:g}, with no day span — a stricter bar in place of the calendar. Click a source for what it is. Grey figures are under {MIN_N} bets.</div>

<h2>Running now ({n_live:,})</h2>
{('<input class="flt" type="search" data-for="live" placeholder="Filter running bets — team, source, sport…">' + '<div id="live">' + collapse(live_rows, LIVE_HEAD, n_live, "running bets") + '</div>') if n_live else '<div class="note">No open bets.</div>'}

<h2>Settled ({n_hist - n_void:,}{f" · {n_void} void" if n_void else ""})</h2>
{('<input class="flt" type="search" data-for="hist" placeholder="Filter settled bets — team, source, sport…">' + '<div id="hist">' + collapse(hist_rows, HIST_HEAD, n_hist, "settled bets") + '</div>') if n_hist else '<div class="note">Nothing settled yet.</div>'}

<h2>Reference</h2>
<details class="ref"><summary>Stamp of approval — every criterion, every source</summary>
<div class="note">The stamp needs <b>{T.APPROVAL['min_bets']}+ settled bets spanning {T.APPROVAL['min_days']}+ days</b>
({T.SPORT_RULES['high']['approval']['min_bets']}+ fresh bets at z ≥ {T.SPORT_RULES['high']['approval']['z_min']:g}, no day span, in high-volume sports),
wins beating the price by z ≥ {T.APPROVAL['z_min']:g}, ROI beating every blind rule on the same contests,
still profitable without its biggest win, and profitable in both halves. Fixed 2026-09-12.</div>
{approval_table(d, scores)}</details>
<details class="ref"><summary>Blind baselines — what choosing nothing made</summary>{baseline_table(d)}</details>
<details class="ref"><summary>Pinnacle v venue</summary>{pinnacle_table(d)}</details>
<details class="ref"><summary>Feed coverage on the last run</summary>{coverage_table(cov)}</details>
<details class="ref"><summary>Retired, or declared but not connected ({n_unconnected})</summary>
<div class="tbl"><table><tr><th>Source</th><th>Why it is not scored</th></tr>{unconnected_rows(d)}</table></div></details>
<details class="ref"><summary>Method</summary><div class="note">
Tipsters and rules name a side and are backed every time; models, books and exchanges state a probability
and are backed only on a {int(T.EDGE_MIN*100)}pp disagreement with the price. <b>Polymarket US</b> is the venue
wherever it lists a contest; <b>Kalshi</b> is the venue for soccer and anything Polymarket US is missing, with
soccer kickoffs taken from ESPN. A contest is logged only with a real book (spread ≤ {int(S.MAX_SPREAD*100)}¢), at the
ask. Until 2026-09-13 the venue was polymarket.com; those bets still settle there but never count toward QA.
Quotes logged before the book rule on boxing, cricket and table tennis were voided ({esc(T.PRE_GATE_NOTE)}).{odds_line}{close_line}
A positive ROI under {MIN_N} settled bets is not a finding.</div></details>

<footer>Read-only static export · rebuilt by GitHub Actions · research, not betting advice.</footer>
<script>
document.querySelectorAll('#tabs button').forEach(b => b.addEventListener('click', () => {{
  document.querySelectorAll('#tabs button').forEach(x => x.classList.toggle('on', x === b));
  const t = b.dataset.tab;
  document.querySelectorAll('#pairs tr[data-g]').forEach(tr => tr.hidden = t !== 'all' && tr.dataset.g !== t);
}}));
document.querySelector('#tabs button.on')?.click();
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
  }});
}}));
</script>
</div></body></html>"""


QA_OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "public_site", "qa.html")


def _ticks(gate):
    passed = sum(1 for _k, _l, p, _d in gate if p)
    cells = "".join(
        f'<td><span class="{"pos" if p else "neg"}">{"✓" if p else "✗"}</span>'
        f'<div class="sm mut">{esc(det)}</div></td>' for _k, _l, p, det in gate)
    return passed, cells


def qa_page(d, st, style):
    """QA: promoted (source, sport) pairs, judged only on bets logged after promotion."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    pairs = st.get("pairs") or {}
    in_qa = {k: v for k, v in pairs.items() if v.get("stage") == "qa"}
    label = lambda key: (f'{S.SOURCES[key.split("|")[0]]["label"].split(" (")[0].split(" /")[0]} · '
                         f'{S.SPORTS.get(key.split("|")[1], key.split("|")[1])}')

    # In QA
    ready_head = "".join(f"<th>{esc(l)}</th>" for _k, l, _p, _d in T.ready_gate(T.assess(d, "__none__")))
    qa_rows, n_ready = [], 0
    for key, pair in sorted(in_qa.items(), key=lambda kv: kv[1]["promoted_at"]):
        name, sport = key.split("|")
        a = T.assess(d, name, sport, since=T.qa_since(pair, sport, key), venues=T.TRADEABLE_VENUES)
        gate = T.ready_gate(a)
        passed, cells = _ticks(gate)
        ready = passed == len(gate)
        n_ready += ready
        if pair.get("ready_at"):
            status = '<span class="sig y">✓ PRODUCTION-READY</span>'
        elif ready and pair.get("ready_since"):
            held = (datetime.now(timezone.utc) - datetime.fromisoformat(pair["ready_since"])).days
            status = (f'<span class="sig w">HOLDING · day {held} of {T.READY_HOLD_DAYS}</span>'
                      f'<div class="sm mut">gate passing since {esc(pair["ready_since"][:10])}</div>')
        else:
            status = f'<span class="sig w">IN QA · {passed}/{len(gate)}</span>'
        ready = bool(pair.get("ready_at"))
        qa_rows.append(f"""<tr><td><b>{esc(label(key))}</b>
<div class="sm mut">promoted {esc(pair['promoted_at'][:10])} on {pair.get('entry', {}).get('n', '?')} sandbox bets{(' · moved by hand · production at ' + str(T.PAIR_OVERRIDES[key]['production_at']) + ' bets') if key in T.PAIR_OVERRIDES else (' · judged on its whole record' if T.sport_rules(sport).get('qa_counts_sandbox') else '')}</div></td>
<td>{status}</td>
<td class="num">{a['n']}<div class="sm mut">{a['span_days']:.0f} days</div></td>
<td class="num"><span class="{cls(a['roi']) if a['n'] >= MIN_N else 'mut'}">{pct(a['roi'], sign=True)}</span>
<div class="sm mut">{pct(a['roi_fee'], sign=True)} after fees</div></td>
<td class="num">{f"{a['clv']*100:+.1f}¢" if a['clv'] is not None else '—'}
<div class="sm mut">{f"{a['clv_beat']:.0%} beat close" if a['clv'] is not None else ''}</div></td>
{cells}</tr>""")
    qa_table = (f"""<div class="tbl"><table>
<tr><th>Pair</th><th>Status</th><th class="num">Fresh bets</th><th class="num">ROI</th>
<th class="num">CLV</th>{ready_head}</tr>
{''.join(qa_rows)}</table></div>""" if qa_rows else
        '<div class="note">Nothing has been promoted yet — no Sandbox pair has cleared the entry gate. '
        'The first to do so will appear here, judged only on bets they make from that moment on.</div>')

    # History
    events = list(reversed(st.get("events") or []))
    hist = "".join(
        f"""<tr><td class="mut">{esc(e['at'][:16].replace('T', ' '))}</td><td><b>{esc(label(e['pair']))}</b></td>
<td>{('<span class="sig w">FAST TRACK · ' + esc(e['to'].split('_')[-1].upper()) + '</span>') if e['to'].startswith('fast_track') else '<span class="sig y">→ QA</span>' if e['to'] == 'qa' else '<span class="sig y">✓ READY</span>' if e['to'] == 'ready' else '<span class="st miss">READY WITHDRAWN</span>' if e['to'] == 'unready' else '<span class="st miss">→ SANDBOX</span>'}</td>
<td class="sm mut">{esc(e.get('reason') or '')} n={e['evidence'].get('n')} · z {e['evidence'].get('z', 0):+.2f} · ROI {pct(e['evidence'].get('roi'), sign=True)}</td></tr>"""
        for e in events)
    hist_table = (collapse(hist, "<tr><th>When</th><th>Pair</th><th>Change</th><th>Evidence</th></tr>",
                           len(events), "changes") if hist else
                  '<div class="note">No promotions or demotions yet.</div>')

    E, A = T.QA_ENTRY, T.APPROVAL
    H, HV = T.SPORT_RULES["high"]["entry"], " and ".join(S.SPORTS[x] for x in T.HIGH_VOLUME_SPORTS).lower()
    return f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Edge Machine · QA</title>
<meta name="description" content="Only the Sandbox pairs that succeeded, re-tested on fresh bets before Production.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
{style}</head><body><div class="wrap">

<h1>QA</h1>
<div class="sub">Where the real deal is separated from the noise · updated {esc(now)}</div>
<div class="nav"><a href="./">Leads</a>
<a href="./streaks.html">Streaks</a><a href="./record.html">Record</a>
<a href="./today.html">Today</a><a href="./sandbox.html">Sandbox</a><a class="on" href="./qa.html">QA</a><a href="./production.html">Production</a></div>

<div class="note warn">QA lists only what has <b>succeeded in the Sandbox</b>: a (source, sport) pair
arrives here once it clears the entry gate for its sport — {E['min_bets']}+ settled bets spanning {E['min_days']}+ days and wins beating
the price by z ≥ {E['z_min']:g} ({H['min_bets']}+ bets at z ≥ {H['z_min']:g}, no day span, in {HV}), beating every blind rule, still profitable without its biggest win.
Pairs still working towards that are on the <a href="./sandbox.html">Sandbox</a> page. From promotion on, a pair
is judged <b>only on bets it logs after the promotion</b> — the history that earned the move
never counts twice. QA asks what the Sandbox cannot: did it <b>beat the closing price</b>, and
does it survive the <b>taker fee</b> a follower would pay. Only bets on the US exchanges count
here — <b>Polymarket US and Kalshi</b>; a record logged on polymarket.com
(the Sandbox venue until 2026-09-13) stays on the Sandbox page and never moves a pair.</div>

<div class="tiles">
<div class="tile"><b>{len(in_qa)}</b><span>pairs in QA</span></div>
<div class="tile"><b class="{'pos' if n_ready else ''}">{n_ready}</b><span>production-ready</span></div>
<div class="tile"><b>{sum(1 for e in st.get('events') or [] if e['to'] == 'sandbox')}</b><span>demotions</span></div>
</div>

<h2>In QA</h2>
{qa_table}
<div class="note"><b>Production-ready</b> is the full stamp applied to the fresh QA record —
{A['min_bets']}+ bets spanning {A['min_days']}+ days, z ≥ {A['z_min']:g} (for {HV}: {T.SPORT_RULES['high']['approval']['min_bets']}+ fresh bets, no day span,
z ≥ {T.SPORT_RULES['high']['approval']['z_min']:g}), beats every blind rule, still
profitable without its biggest win and in both halves — <b>plus</b> buying below the closing
price on average, measured on {T.READY_CLV['min_n']}+ closing prices covering at least
{T.READY_CLV['min_share']:.0%} of the bets, and staying profitable after the taker fee (Polymarket US
0.06·p·(1−p), Kalshi 0.07), and <b>every bet must be a standard exchange market the Production
feed can publish</b> — today a soccer side (home or away) on a Kalshi game market, or Yes on a
Kalshi over-1.5 or team-goals market; no draws and no other sport yet. The gate is checked every run, so a pair is marked ready only once
it has <b>held for {T.READY_HOLD_DAYS} days</b>, and the mark is withdrawn the first run it fails.
A pair goes <b>back to the Sandbox</b> after {T.QA_DEMOTE['min_bets']} fresh bets if it is behind the price,
not beating every blind rule, or behind the closing price — or, at any count, after
{T.STALE_DAYS} days without a new bet — and must re-qualify on bets logged after the demotion.
Baselines are benchmarks and are never promoted.</div>

<h2>History</h2>
{hist_table}

<footer>Read-only static export · rebuilt by GitHub Actions · research, not betting advice.</footer>
</div></body></html>"""


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    page = build()
    with open(OUT, "w") as f:
        f.write(page)
    print(f"wrote {OUT}")
    # QA shares the Sandbox page's stylesheet rather than keeping a second copy of it.
    style = re.search(r"<style>.*?</style>", page, re.S).group(0)
    with open(QA_OUT, "w") as f:
        f.write(qa_page(T.load(), T.load_stages(), style))
    print(f"wrote {QA_OUT}")
    import production
    prod_out = os.path.join(os.path.dirname(QA_OUT), "production.html")
    with open(prod_out, "w") as f:
        f.write(production.page(T.load(), T.load_stages(), production.load_feed(), style))
    print(f"wrote {prod_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
