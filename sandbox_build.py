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
from datetime import datetime, timedelta, timezone

import fmt
import sandbox_sources as S
import sandbox_track as T
import site_chrome

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


# ASCII http(s) only, scheme case ignored. javascript: and data: are not links.
# Without re.ASCII, IGNORECASE treats the long s (ſ) as s, so "httpſ://" matches.
_SAFE_SCHEME = re.compile(r"^https?://", re.IGNORECASE | re.ASCII)


def safe_href(url, label):
    """Render label as an external link only when url is http or https.

    Contest links come from stored rows. Kalshi ones are built as https at
    render time; every other venue keeps the url it was logged with, and that
    stored value is not checked when it is written. Trim, then allow only an
    ASCII http:// or https://. Anything else — javascript: (including a tab or
    newline inside the word), data:, a scheme-relative url, an entity-encoded
    scheme, or a non-ASCII lookalike — is the escaped label with no href. The
    url is escaped too, so a quote in it cannot open a new attribute, and an
    external link does not leak the referrer.
    """
    text = esc(label)
    href = str("" if url is None else url).strip()
    if not _SAFE_SCHEME.match(href):
        return text
    return (f'<a href="{esc(href)}" target="_blank" rel="noopener noreferrer">'
            f"{text}</a>")


def pct(x, digits=1, sign=False):
    return fmt.pct(x, digits=digits, sign=sign)


def money(x):
    return fmt.money(x)


def cls(x):
    """Colour for a whole-dollar figure. A value that rounds to $0 is neutral."""
    return fmt.tone(x, spec=",.0f", scale=1)


def _pct_span(x, digits=1, thin=False):
    """A percent with a colour class that follows the displayed digits."""
    if x is None:
        return '<span class="mut">—</span>'
    klass = "mut" if thin else fmt.tone(x, spec=f".{digits}f", scale=100)
    return f'<span class="{klass}">{pct(x, digits=digits, sign=True)}</span>'


def _td_num(inner, digits, extra=""):
    """A numeric cell. data-v is the displayed number, escaped, never the raw text."""
    classes = "num" + (f" {extra}" if extra else "")
    if digits is None:
        return f'<td class="{classes}">{inner}</td>'
    return f'<td class="{classes}" data-v="{esc(digits)}">{inner}</td>'


def _price_cell(price):
    return _td_num(fmt.cents(price), fmt.shown_cents_digits(price))


def _money_cell(pnl):
    extra = cls(pnl) if pnl is not None else ""
    return _td_num(money(pnl), fmt.shown_digits(pnl, spec=",.0f", scale=1), extra)


def _edge_cell(edge, digits=1):
    if edge is None:
        return '<td class="num"><span class="mut">pick</span></td>'
    return _td_num(_pct_span(edge, digits), fmt.shown_digits(edge, spec=f".{digits}f", scale=100))


def _row_id(q):
    return f' data-id="{esc(q.get("id") or "")}"'


def _side(q):
    if q.get("pick") == "a":
        return q.get("side_a")
    if q.get("pick") == "b":
        return q.get("side_b")
    return "Draw"


def _source_label(q):
    return S.SOURCES[q["source"]]["label"].split(" (")[0]




def _coverage_signal(cell):
    """The count feed_health can test, or None when the cell is not a signal.

    An int is the shape stored before offered-row counts. A dict uses the picks.
    An empty offer returns None, so an empty board does not mark the feed dark.
    A bare int 0 is unchanged, so a stored ledger still flags the way it did.
    """
    if isinstance(cell, dict):
        if int(cell.get("offered") or 0) == 0:
            return None
        return int(cell.get("picked") or 0)
    return cell


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
        if name in S.REMOVED_SOURCES:
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
        counts = [_coverage_signal((cov.get(sp) or {}).get(name)) for sp in meta["sports"]]
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

    `d` is the filtered page copy. This is a cross-lane total, so a removed
    lane's bets are not a cell.

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
                klass = "mut" if thin else fmt.tone(s["roi"], spec=".1f", scale=100)
                tick = (' <span class="pos">✓</span>'
                        if T.assess(d, name, sport)["status"] == "approved" else "")
                cells.append(f'<td class="num"><span class="{klass}">{pct(s["roi"], sign=True)}</span>'
                             f'{tick}<div class="sm mut">n={s["settled"]}</div></td>')
            tot = T.score(d)[name]  # lifetime, across every domain
            tot_roi = (f'<span class="{fmt.tone(tot["roi"], ".1f", 100) if tot["settled"] >= MIN_N else "mut"}">'
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
    rows = [q for q in T.bet_rows(d) if q["source"] == name
            and q["status"] in ("won", "lost") and not T.climate_excluded(q)
            and (sport is None or q["sport"] == sport)]
    if not rows:
        return None
    return sum(1 for q in rows if q["status"] == "won"), sum(q["price"] for q in rows)


def leaderboard(scores, d):
    """One row per source. `d` and `scores` are the filtered page copy.

    A removed lane's bets are not in this total, even when the source still
    has a kept sport.
    """
    rows = []
    for name, s in sorted(scores.items(),
                          key=lambda kv: (kv[1]["connected"], kv[1]["settled"]), reverse=True):
        if not s["connected"]:
            continue
        thin = s["settled"] < MIN_N
        roi = (f'<span class="{fmt.tone(s["roi"], ".1f", 100)}">{pct(s["roi"], sign=True)}</span>'
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
            vb_cell = (f'<span class="{"mut" if thin else fmt.tone(gap, ".1f", 100)}">'
                       f'{pct(gap, digits=1, sign=True).replace("%", "pp")}</span>'
                       f'<div class="sm mut">v back the {esc(kind)}</div>')
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
<td class="num {cls(s['pnl'])}">{money(s['pnl']) if s['staked'] else '—'}</td>
<td class="num">{f"{s['brier']:.4f}" if s['brier'] is not None else '—'}</td>
<td>{verdict}</td></tr>""")
    return "\n".join(rows)


def stamp_ledger(full, name):
    """The full ledger minus this source's own removed rows.

    A kept source has none, so its stamp row is the number main shows. Another
    source's removed rows stay, which is what keeps that baseline on main's
    number. This source's removed lanes and sports do not count in its row.
    """
    def drop(q):
        return q.get("source") == name and S.removed_row(q)

    out = dict(full)
    out["quotes"] = [q for q in (full.get("quotes") or []) if not drop(q)]
    if "_archive" in full:
        out["_archive"] = [q for q in (full.get("_archive") or []) if not drop(q)]
    return out


def approval_table(d, scores, full=None):
    """Every betting source against every criterion, so a stamp can be checked, not trusted.

    `scores` decides who has a row, from the filtered page copy. Each row is
    judged on `full` minus that source's own removed rows. A kept source has
    none, so its numbers are main's. A source that also had a removed sport
    is judged without those bets. A reset lane is judged only on bets logged
    since the tour clock, so a kept-tour bet from before that clock is not
    its stamp. pm_combo4 is not a reset lane, and neither is any other source.
    """
    full = d if full is None else full
    head = "".join(f'<th>{esc(label)}</th>' for _k, label, _p, _d in
                   T.assess(d, "__none__")["criteria"])
    rows = []
    order = {"approved": 0, "watch": 1, "failing": 2, "unproven": 3}
    judged = []
    for name, s in scores.items():
        if not (s["connected"] and name not in S.REMOVED_SOURCES
                and (s["bets"] or name in S.TENNIS_FAV_RESET)):
            continue
        since = S.tour_clock_since(source=name)
        judged.append((name, T.assess(stamp_ledger(full, name), name, since=since)))
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
    """The blind strategies, per sport — the bar every source's choices have to clear.

    `d` is the filtered page copy. A contest that only a removed lane quoted
    is not a row here. A kept lane's own baseline is a different number, read
    from the full ledger on that lane's row.
    """
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
<td class="num"><span class="{fmt.tone(r['roi'], '.1f', 100) if r['n'] >= MIN_N else 'mut'}">{pct(r['roi'], sign=True)}</span></td>
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
              and q["status"] != "void" and not T.climate_excluded(q)]
        bets = [q for q in qs if q["bet"]]
        done = [q for q in bets if q["status"] in ("won", "lost")]
        priced = [q for q in bets if q.get("status") == "settled" and q.get("result") == "price"]
        won = sum(1 for q in done if q["status"] == "won")
        pnl = sum(q["pnl"] for q in done) + sum(q["pnl"] for q in priced)
        exp = sum(q["price"] for q in done)
        edges = [q["edge"] for q in qs if q.get("edge") is not None]
        rows.append(f"""<tr><td><b>{label}</b></td><td class="num">{len(qs)}</td>
<td class="num">{len(bets)}</td><td class="num">{len(done)}</td>
<td class="num">{f"{won} v {exp:.1f}" if done else "—"}</td>
<td class="num"><span class="{fmt.tone(pnl / ((len(done) + len(priced)) * T.STAKE), '.1f', 100) if (done or priced) and len(done) + len(priced) >= MIN_N else 'mut'}">{pct(pnl / ((len(done) + len(priced)) * T.STAKE), sign=True) if done or priced else '—'}</span></td>
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
    names = [n for n, m in S.SOURCES.items()
             if m["connected"] and n not in S.REMOVED_SOURCES]
    head = "".join(f'<th class="num">{esc(S.SOURCES[n]["label"].split(" (")[0])}</th>'
                   for n in names)
    rows = []
    for sport, label in S.SPORTS.items():
        # MLB leaves with the venue list. NHL · Rest leaves with its lane.
        # Every other sport stays, including one whose only lane is already
        # gone (NHL · Puck line) and one no source lists (Economics, Finance,
        # Politics, Elections).
        if sport in S.REMOVED_SPORTS or sport in S.REMOVED_VENUE_SPORTS or sport == "nhl_rest":
            continue
        cells = []
        for n in names:
            v = (cov.get(sport) or {}).get(n)
            if sport not in S.SOURCES[n]["sports"] or (n, sport) in S.REMOVED_LANES:
                cells.append('<td class="num mut">n/a</td>')
            elif isinstance(v, dict) and "offered" in v:
                picked = int(v.get("picked") or 0)
                offered = int(v.get("offered") or 0)
                cls = "neg" if picked == 0 else "pos"
                cells.append(f'<td class="num {cls}">{picked:,} of {offered:,}</td>')
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
    """Running bets, soonest first. One flat table: Contest, then Price."""
    live = [q for q in d["quotes"] if q["status"] == "open" and q["bet"]
            and not T.climate_excluded(q) and not S.removed_row(q)]
    live.sort(key=lambda q: (q.get("start") or "", q.get("sport") or "", str(q.get("id") or "")))
    out = []
    for q in (live[:limit] if limit else live):
        out.append(f"""<tr{_row_id(q)}><td>{safe_href(S.market_url(q), S.display_label(q))}</td>
{_price_cell(q.get('price'))}
<td>{esc(S.SPORTS.get(q['sport'], q['sport']))}</td>
<td><b>{esc(_side(q))}</b></td>
<td>{esc(_source_label(q))}</td>
{_open_date_cell(q)}
{_edge_cell(q.get('edge'))}</tr>""")
    return "\n".join(out), len(live)


_HIST = ("won", "lost", "void", "settled")


def _badge(q):
    """(css class, label). A price payout is not painted as a win, a loss, or a void."""
    if q.get("result") == "price":
        return "price", "PRICE"
    return q.get("status") or "", str(q.get("status") or "").upper()


def _day_summary(qs):
    # A void stays in the list and adds nothing (its P/L is 0). A city-day
    # repeat keeps its original P/L, so it has to be left out of the sum.
    counted = [q for q in qs if not T.climate_excluded(q)]
    won = sum(1 for q in counted if q["status"] == "won")
    n = sum(1 for q in counted if q["status"] in ("won", "lost"))
    n_price = sum(1 for q in counted if q.get("result") == "price")
    pl = sum(q["pnl"] for q in counted)
    extra = f" · {n_price} priced" if n_price else ""
    return won, n, extra, pl


def _cityday_repeat(q):
    """A repeat city-day quote. A void is not one, even with a stale flag.

    load() clears excluded='nws_cityday' on voids. A caller that skips load
    can leave the flag in place. That row is still a void: it stays on the
    settled pages and in the void count, and out of the city-day count.
    """
    return T.climate_excluded(q) and q.get("status") != "void"


def settled_rows(d, limit=None):
    """Settled bets, newest first. One flat table: Contest, then P/L."""
    done = [q for q in T.bet_rows(d) if q["status"] in _HIST and q["bet"]
            and not _cityday_repeat(q) and not S.removed_row(q)]
    done.sort(key=lambda q: (q.get("settled") or "", str(q.get("id") or "")), reverse=True)
    out = []
    for q in (done[:limit] if limit else done):
        klass, label = _badge(q)
        out.append(f"""<tr{_row_id(q)}><td>{esc(S.display_label(q))}</td>
{_money_cell(q.get('pnl'))}
<td>{esc(S.SPORTS.get(q['sport'], q['sport']))}</td>
<td>{esc(_side(q))}</td>
<td>{esc(_source_label(q))}</td>
<td><span class="st {klass}">{esc(label)}</span></td>
{_price_cell(q.get('price'))}
<td class="mut">{esc(_settled_day(q))}</td></tr>""")
    return "\n".join(out), len(done)


LIVE_HEAD = ('<tr><th>Contest</th><th class="num">Price</th><th>Sport</th>'
             '<th>Backing</th><th>Source</th><th>Date</th><th class="num">Edge</th></tr>')
HIST_HEAD = ('<tr><th>Contest</th><th class="num">P/L</th><th>Sport</th><th>Backed</th>'
             '<th>Source</th><th>Status</th><th class="num">Price</th><th>Settled</th></tr>')


# Recently settled is this many America/Chicago calendar days, ending on the build date.
RECENT_DAYS = 7


def _settled_day(q):
    """Chicago calendar date the bet settled, or a placeholder if it cannot be read."""
    try:
        return fmt.chicago(q.get("settled")).date().isoformat()
    except (TypeError, ValueError, OverflowError, OSError):
        return "—"


def _open_date_cell(q):
    """Date on a running row. A missing or unreadable kickoff date is the same dash
    the settled tables use. Its data-v is empty, which a numeric sort leaves last.
    A readable calendar date is shown as stored.
    """
    raw = q.get("date")
    text = raw.strip() if isinstance(raw, str) else ""
    if not text:
        return '<td class="mut" data-v="">—</td>'
    try:
        if len(text) == 10:
            day = datetime.strptime(text, "%Y-%m-%d").date()
        else:
            day = fmt.chicago(text).date()
    except (TypeError, ValueError, OverflowError, OSError):
        return '<td class="mut" data-v="">—</td>'
    return f'<td class="mut" data-v="{day.strftime("%Y%m%d")}">{esc(text)}</td>'


def _chicago_today(now):
    return fmt.chicago(now).date()


def _is_recent(q, today):
    """True when the settled Chicago date is one of the last RECENT_DAYS, including today."""
    try:
        day = fmt.chicago(q.get("settled")).date()
    except (TypeError, ValueError, OverflowError, OSError):
        return False
    return 0 <= (today - day).days < RECENT_DAYS


def partition_settled(d, now):
    """(recent, older) settled bets. Recent is the last 7 Chicago dates through `now`.

    Every settled bet that still counts is in exactly one of the two lists. The
    list is the live quotes plus archived bets (one row per id; compact price
    rows are not bets). A repeat city-day quote is in neither. A void is not a
    repeat, so a stale city-day flag does not remove it. A timestamp that cannot
    be placed on the Chicago calendar is older, so it still appears on an archive
    page. Removed rows are left out. Refused tours and eliminated pairs are
    filtered by the caller, the same way they were before the archive was read.
    """
    today = _chicago_today(now)
    done = [q for q in T.bet_rows(d) if q["status"] in _HIST and q["bet"]
            and not _cityday_repeat(q) and not S.removed_row(q)]
    done.sort(key=lambda q: (q.get("settled") or "", str(q.get("id") or "")), reverse=True)
    recent, older = [], []
    for q in done:
        (recent if _is_recent(q, today) else older).append(q)
    return recent, older


def week_slug(q):
    """ISO week of the Chicago settled date, 'YYYY-Www'. Undated if it will not parse."""
    try:
        day = fmt.chicago(q.get("settled")).date()
    except (TypeError, ValueError, OverflowError, OSError):
        return "undated"
    iso = day.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def archive_groups(older):
    """{slug: [quotes]} for bets that are not on the main page."""
    groups = {}
    for q in older:
        groups.setdefault(week_slug(q), []).append(q)
    return groups


def _week_order(slugs):
    dated = sorted((s for s in slugs if s != "undated"), reverse=True)
    if "undated" in slugs:
        dated.append("undated")
    return dated


def _tools(placeholder, label, view=False):
    """Search box, and on the first card-capable table the Cards | Table control."""
    toggle = site_chrome.VIEW_TOGGLE if view else ""
    return (f'<div class="table-tools">{toggle}<input class="flt" type="search" '
            f'placeholder="{esc(placeholder)}" aria-label="{esc(label)}"></div>')


def _sortable(head, rows):
    return f'<div class="tbl"><table class="sortable">{head}{rows}</table></div>'


def _archive_links(groups, prefix):
    items = []
    for slug in _week_order(groups):
        n = len(groups[slug])
        label = "Undated" if slug == "undated" else slug
        items.append(
            f'<li><a href="{esc(prefix + slug + ".html")}">{esc(label)}</a>'
            f' <span class="mut">· {n:,} settled</span></li>')
    return '<ul class="weeks">' + "".join(items) + "</ul>" if items else ""


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
        if m["connected"] or name in S.REMOVED_SOURCES:
            continue
        rec = ""
        if m.get("retired") and d is not None:
            n = sum(1 for q in T.bet_rows(d) if q["source"] == name
                    and q["status"] in ("won", "lost") and not T.climate_excluded(q))
            rec = f'<div class="sm">{n} settled bets kept on record</div>'
        why = (f'<b class="neg">Retired</b> {esc(m["retired"])}' if m.get("retired") else esc(m["note"]))
        out.append(f"""<tr><td><b>{esc(m['label'])}</b>
<div class="mut sm">{esc(m['kind'])} · {esc(m['site'])}</div>{rec}</td>
<td class="mut">{why}</td></tr>""")
    # A source can lose one sport and keep the others: that pair is retired on its own.
    for name, m in S.SOURCES.items():
        for sport, reason in (m.get("retired_sports") or {}).items():
            if S.lane_removed(name, sport):
                continue
            rec = ""
            if d is not None:
                n = sum(1 for q in T.bet_rows(d) if q["source"] == name and q["sport"] == sport
                        and q["status"] in ("won", "lost")
                        and not T.climate_excluded(q))
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
    mine = [q for q in T.bet_rows(d) if q["source"] == name and q["sport"] == sport
            and not S.tennis_refused_row(q)]
    open_n = sum(1 for q in mine if q["status"] == "open" and not T.climate_excluded(q))
    last = max((str(q.get("logged") or "") for q in mine), default="")
    if not a["n"]:
        # A tour-clock reset with nothing counted yet stays Waiting. Dropping
        # the row would hide the lane for having no entries.
        reset_empty = S.tour_clock_since(since=pair.get("since")) is not None
        group = "waiting" if open_n or reset_empty else None
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
    "build_fail": ("Fails BUILD", "x", 5),
}
EARLY_N = 10      # under this, even a lean is not worth a word: 1-0 is not "promising"


def verdict(a):
    """proven / working / no edge at MIN_N+ settled; promising / behind from EARLY_N; early below.

    When the row carries BUILD sub-periods, a fail is build_passes and nothing else.
    A row without them is the live record, unchanged.
    """
    blocks = a.get("build_subperiods")
    if blocks is not None and not S.build_passes(blocks):
        return "build_fail"
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


def _fade_book(d, pair):
    """The book T.faded() reads for one pair.

    Other lanes pass the ledger through unchanged. A tour-clock reset passes
    only bets logged at or after the clock, and only on a kept tour, so the
    If-faded cell is that set and T.faded() itself is not retargeted.
    """
    clock = S.tour_clock_since(since=pair.get("since"))
    if clock is None:
        return d

    def keep(q):
        return str(q.get("logged") or "") >= clock and not S.tennis_refused_row(q)
    out = dict(d)
    out["quotes"] = [q for q in (d.get("quotes") or []) if keep(q)]
    if d.get("_archive"):
        out["_archive"] = [q for q in d["_archive"] if keep(q)]
    return out


def pair_list(d, st, include_retired=True):
    """Every (source, sport) pair that has bet, with its record and verdict.

    Retired pairs are listed too, marked, so a sport's section accounts for its own history
    rather than sending the reader to the Reference table to find where the bets went.
    """
    out = []
    for name, meta in S.SOURCES.items():
        if name in S.REMOVED_SOURCES:
            continue
        if meta.get("kind") in T.NEVER_PROMOTED_KINDS:
            continue
        sports = list(meta["sports"]) if meta["connected"] else []
        gone = {} if not include_retired else dict(
            {sp: why for sp, why in (meta.get("retired_sports") or {}).items()},
            **({sp: meta["retired"] for sp in meta["sports"]} if not meta["connected"] and meta.get("retired") else {}))
        for sport in sports + [sp for sp in gone if sp not in sports]:
            if S.lane_removed(name, sport):
                continue
            group, a, _qa, open_n, last, pair = pair_status(d, st, name, sport)
            # A cup or international twin is listed from the day it is wired, so it can be
            # reviewed before its first qualifying match; other pairs appear once they bet.
            # A consensus row is listed from the day it is wired too: it only ever bets where
            # two sources agree, so it can sit empty for days and should be visible meanwhile.
            # A pair whose stage row carries a RESET has an empty window by construction --
            # the reset is why -- so skipping it for having no bets deletes the row entirely
            # and takes the record it was removed on with it. pm_combo4 left Production on
            # 2026-10-03 with no ongoing volume and disappeared from the page outright, while
            # olbg|boxing survived its own removal only because boxing kept betting. The
            # "removed" branch below exists for exactly this and never got the chance to run.
            reset_row = bool(pair.get("since")) and bool(
                T.assess(d, name, sport, venues=T.TRADEABLE_VENUES)["n"])
            if (group is None and not _scope(sport)
                    and name not in T.CONSENSUS and not reset_row):
                continue
            # A pair taken out of Production restarts its count, which on its own reads as a
            # brand-new source ("Waiting for results") and hides the record it was removed on.
            removed = None
            if pair.get("demoted_at") and pair.get("stage") != "production":
                removed = dict(at=str(pair["demoted_at"])[:10],
                               a=T.assess(d, name, sport, until=pair["demoted_at"],
                                          venues=T.TRADEABLE_VENUES))
            v = verdict(a) if group is not None else "nobets"
            # "nobets" included: a removed pair with no volume since the removal has an empty
            # window by construction, and reading it as a source that has never bet is the
            # same erasure as dropping the row. pm_combo4 has four settled baskets.
            if removed and v in ("waiting", "early", "nobets"):
                v = "removed"
            if sport in gone:
                v = "retired"
            out.append(dict(name=name, sport=sport, meta=meta, a=a, open=open_n, last=last,
                            fade=T.faded(_fade_book(d, pair), name, sport, venues=T.TRADEABLE_VENUES),
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
    for name, m in S.SOURCES.items():
        if name in S.REMOVED_SOURCES:
            continue
        items = ([(None, m["retired"])] if m.get("retired") else []) + list((m.get("retired_sports") or {}).items())
        for sport, why in items:
            if sport and S.lane_removed(name, sport):
                continue
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
    # Colour follows the cents that are printed. "behind" does not paint 0.0¢ red.
    tone = fmt.tone(a.get("clv"), spec=".1f", scale=100)
    t = a.get("clv_t")
    stat = (fmt.tstat(t) + " · ") if t is not None else ""
    bits = stat + f'{a["clv_n"]} close' + ("" if a["clv_n"] == 1 else "s")
    return (f'<span class="{tone}">{fmt.signed_cents(a["clv"])}</span>'
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


def _row(r, rank=None, provisional=False, in_market=False):
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
    roi = (f'<span class="{"mut" if thin else fmt.tone(a["roi_fee"], ".1f", 100)}">{pct(a["roi_fee"], sign=True)}</span>'
           if a["n"] else "—")
    stage = (f'<span class="sig y">PRODUCTION</span><div class="sm mut">since {esc(r["moved"])}</div>'
             if r["prod"] else '<span class="mut sm">Sandbox</span>')
    # Backing the other side of the same bets. A big positive here is the loud complaint:
    # the selection is finding something and the direction is inverted. Greyed under the
    # read floor, and a dash where there is no single other side (three-way contests).
    fd = r.get("fade") or {}
    fade = ('<span class="mut">—</span>' if not fd.get("n") or fd.get("roi") is None else
            f'<span class="{"mut" if fd["n"] < MIN_N else fmt.tone(fd["roi"], ".1f", 100)}">{pct(fd["roi"], sign=True)}</span>'
            f'<div class="sm mut">{fd["won"]} v {fd["expected"]:.1f} on {fd["n"]}'
            f'{" " + fd["unit"] + ("s" if fd["n"] != 1 else "") if fd.get("unit") else ""}</div>')
    sfx = _scope(r["sport"])
    tag = f' <span class="sig w">{esc(S.SCOPE_LABEL[sfx].upper())}</span>' if sfx else ""
    # What a pair IS lives in one place per sport now ("How each rule is defined"), not in
    # every row. A table is for comparing records; a paragraph inside a row is read once and
    # then scrolled past forever, and 26 of them made the soccer section unreadable.
    gone = ""
    # The rank is greyed while a pair is too thin to read, so the number never pretends to
    # more than it has. An unranked pair shows a dash, not a position it has not earned.
    rk = ('<span class="mut">—</span>' if rank is None else
          f'<span class="{"mut" if provisional else "rank"}">{rank}</span>'
          + ('<div class="sm mut">early</div>' if provisional else ''))
    # A lone market family (Commodities, after weather left) used to print the
    # sport name under the rule. The subtitle is the kind — Rule — the same
    # word the folded market sections already use.
    subline = meta["kind"] if (in_market or r["sport"] in MARKET_KEYS) else sub
    return f"""<tr><td class="num">{rk}</td>
<td><b>{esc(meta['label'].split(' (')[0])}</b>{tag}
<div class="sm mut">{esc(subline)}</div>{gone}</td>
<td><span class="sig {chip}">{esc(label)}</span>{more}{more_rm}</td>
<td class="num">{rec}</td><td class="num">{vp}</td><td class="num">{roi}</td>
<td class="num">{close_cell(a)}</td>
<td class="num">{fade}</td>
<td class="num">{r['open'] or '—'}</td><td>{stage}</td></tr>"""


def definitions(rs):
    """Every rule in this sport, in its own words, in ONE collapsed block.

    The pre-registration is the record: what a rule backs, where the claim came from, and
    what was fixed before it ran. That has to stay readable, and it has to stay out of the
    table, which exists to compare numbers. Cup and international twins share their parent's
    definition, so each is written once and its scopes are named beside it.
    """
    seen = {}
    for r in rs:
        note = (r["meta"].get("note") or "").strip()
        if not note:
            continue
        key = r["meta"]["label"].split(" (")[0]
        seen.setdefault(key, [note, set(), r["meta"]["kind"], []])
        sfx = _scope(r["sport"])
        seen[key][1].add(S.SCOPE_LABEL[sfx] if sfx else "League")
        # Why a pair was retired belongs with its definition, not in the row: it is the last
        # thing written about it and the least often read.
        if r.get("gone") and str(r["gone"]) not in seen[key][3]:
            seen[key][3].append(str(r["gone"]))
    if not seen:
        return ""
    items = []
    for name, (note, scopes, kind, why) in sorted(seen.items()):
        where = ", ".join(sorted(scopes, key=lambda x: ("League", "Cups", "Internationals").index(x)
                                 if x in ("League", "Cups", "Internationals") else 9))
        # A cup or international twin is a SEPARATE record on a different set of competitions,
        # and which ones is part of the definition — it used to sit in the row and now lives
        # here, so the table stays a table and the scope is still written down somewhere.
        extra = "".join(
            f'<div class="sm"><b>{esc(S.SCOPE_NOTE[sfx].format(", ".join((S.CUP_FRAGS if sfx == "_cup" else S.INTL_FRAGS).values())))}</b></div>'
            for sfx, lab in S.SCOPE_LABEL.items() if lab in scopes)
        retired = "".join(f'<div class="sm"><b>Retired.</b> <span class="mut">{esc(w)}</span></div>'
                          for w in why)
        items.append(f'<div class="def"><b>{esc(name)}</b>'
                     f'<span class="mut sm"> · {esc(kind)} · {esc(where)}</span>'
                     f'{extra}{retired}<div class="sm mut">{esc(note)}</div></div>')
    return (f'<details class="sport"><summary><b>How each rule is defined</b>'
            f'<span class="mut"> · {len(items)} of them, as registered</span></summary>'
            f'<div class="note sm">What each one backs, where the claim came from, and what was '
            f'fixed before it ran. Written once and left alone: a definition that moves after the '
            f'bets start is not a pre-registration.</div>{"".join(items)}</details>')


def eliminated(r):
    """A pair that fails in every direction, moved out of the sport sections (S.ELIMINATED)."""
    return (r["name"], r["sport"]) in S.ELIMINATED


def _eliminated_visible(r):
    """True when an eliminated pair is drawn.

    Every removed source stays off this list, not only weather. covers, the
    NHL puck line, and both weather lanes are in S.ELIMINATED and in the
    removed set, so none of them comes back here.
    """
    return eliminated(r) and not S.lane_removed(r["name"], r.get("sport"))


def eliminated_section(rows):
    """The eliminated pairs, in one collapsed list below the sports: out of sight, on record."""
    gone = sorted((r for r in rows if _eliminated_visible(r)), key=lambda r: -r["a"]["n"])
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
    bets = [q for q in T.bet_rows(d) if q["status"] in ("won", "lost")
            and not T.climate_excluded(q) and not S.removed_row(q)]
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
            f'<span class="{"mut" if n < EARLY_N else fmt.tone(v, ".1f", 100)}">{pct(v, sign=True)}</span>')


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
            cost_bit = "" if hold is None else f" · both sides cost {hold * 100:.1f}%"
            folds.append(f"""<details class="sport"><summary><b>{esc(lg)}</b>
<span class="mut"> · {n} settled{cost_bit} · {len(items)} rule{"" if len(items) == 1 else "s"}</span></summary>
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


_TH = re.compile(r"<th(\s[^>]*)?>(.*?)</th>", re.S)
_TD = re.compile(r"<td(\s[^>]*)?>(.*?)</td>", re.S)
_DASH = re.compile(r"^(?:\s|—|-)*$")
_TR = re.compile(r"<tr(\s[^>]*)?>.*?</tr>", re.S)
_TABLE = re.compile(r"<table(\s[^>]*)?>(.*?)</table>", re.S)
_ATTR_INT = re.compile(r"\b([A-Za-z]+)\s*=\s*\"(\d+)\"")


def cards_css(sel):
    """One card per row instead of a wide table: the phone layout.

    Written once and applied twice on purpose. CSS cannot say "narrow screen OR the reader
    asked for it" in a single rule, so the same block is emitted inside the width query
    (unless the reader has asked for the table) and again for an explicit request. A reader
    on a phone who wants the full grid, and one on a laptop checking how it reads on a
    phone, both get what they asked for, and the choice is remembered.
    """
    return f"""
{sel} .tbl{{overflow-x:visible}}
{sel} table{{display:block}}
{sel} thead{{display:none}}
{sel} tbody,{sel} tr,{sel} td{{display:block;width:100%}}
{sel} tr{{padding:12px 14px;border-bottom:1px solid var(--bd)}}
{sel} tr:last-child{{border-bottom:none}}
{sel} td{{padding:3px 0;border:none;display:flex;gap:14px;align-items:baseline;
justify-content:space-between;text-align:right}}
{sel} td::before{{content:attr(data-l);color:var(--mut);font-size:10px;font-weight:700;
text-transform:uppercase;letter-spacing:.07em;text-align:left;white-space:nowrap;flex:0 0 auto}}
{sel} td{{flex-wrap:wrap}}
{sel} td>.sm{{flex:1 0 100%;text-align:right}}
{sel} td[data-l="#"]{{justify-content:flex-start;gap:8px;text-align:left}}
{sel} td[data-l="#"]::before{{content:none}}
{sel} td[data-l="Rule or tipster"],{sel} td[data-l="Competition"],{sel} td[data-l="Rule"],
{sel} td[data-l="Contest"],{sel} td[data-l="Source"]{{display:block;text-align:left;
padding:0 0 7px}}
{sel} td:first-child:not([data-l="#"]),{sel} td[data-l="#"]+td{{display:block;
text-align:left;padding:0 0 7px}}
{sel} td:first-child:not([data-l="#"])::before,{sel} td[data-l="#"]+td::before{{content:none}}
{sel} td:first-child:not([data-l="#"])>.sm,{sel} td[data-l="#"]+td>.sm{{text-align:left}}
{sel} td[data-l=""]::before{{content:none}}
{sel} td[data-empty]{{display:none}}
{sel} td[data-l="#"]>.sm{{flex:0 0 auto;text-align:left}}
"""


def _attr_int(attrs, name):
    """colspan/rowspan from a generated opening tag. Missing or zero means one."""
    for key, val in _ATTR_INT.findall(attrs or ""):
        if key.lower() == name:
            n = int(val)
            return n if n >= 1 else 1
    return 1


def _th_text(inner):
    """Header text with tags turned into spaces, so 'Leads<br>to come' stays two words."""
    return re.sub(r"<[^>]+>", " ", inner).strip()


def _header_rows(body):
    """The leading <tr> rows that are headers, and nothing after the first data row.

    Group rows are <tr class="grp"> and are not matched here, same as before. A header
    row is one that contains <th and no <td>.
    """
    rows = []
    for rm in _TR.finditer(body):
        row = rm.group(0)
        if "<th" in row and "<td" not in row:
            rows.append(rm)
            continue
        break
    return rows


def _column_labels(header_rows):
    """The name of each column, honouring rowspan and colspan.

    A cell's label is the header in the lowest header row of its column. A group
    title (colspan on the top row only) is not that name — the sub-header under it
    is. A rowspan cell occupies the rows below it, so it stays the label of that
    column. Reading every <th> in document order and pairing it with the Nth <td>
    mis-names the Production table: the group titles are not columns, and the
    second header row was being used as if it were the next cells of the first.
    """
    covered = {}
    ncols = 0
    for r, row_html in enumerate(header_rows):
        c = 0
        for m in _TH.finditer(row_html):
            while (r, c) in covered:
                c += 1
            attrs = m.group(1) or ""
            colspan = _attr_int(attrs, "colspan")
            rowspan = _attr_int(attrs, "rowspan")
            text = _th_text(m.group(2))
            for dr in range(rowspan):
                for dc in range(colspan):
                    covered[(r + dr, c + dc)] = text
            c += colspan
        ncols = max(ncols, c)
    labels = []
    nrows = len(header_rows)
    for col in range(ncols):
        lab = ""
        for r in range(nrows - 1, -1, -1):
            if (r, col) in covered:
                lab = covered[(r, col)]
                break
        labels.append(lab)
    return labels


def label_cells(page):
    """Give every table cell the name of its own column, for the phone layout.

    A ten-column table cannot be read on a 375px screen: three columns fit and the reader
    has to swipe sideways for the record, which is the part they came for. Under 760px the
    stylesheet stacks each row into a card and prints the column name beside the value —
    which only works if the cell knows its column. That is attached here, read from each
    table's own header, rather than written by hand in six different row builders where
    a column added to one and not the other would silently mislabel a number.

    Headers may be more than one row. rowspan and colspan are followed so a cell is
    named for the column it sits in, and every header row stays in <thead> — a second
    header row left in the body is a row of labels the phone layout would show as data.

    Generated markup only: no nested tables, every cell opened with a plain <td>.
    """
    out, pos = [], 0
    for m in _TABLE.finditer(page):
        out.append(page[pos:m.start()])
        attrs = m.group(1) or ""
        body = m.group(2)
        heads = _column_labels([rm.group(0) for rm in _header_rows(body)])

        def one_row(rm):
            col = [0]

            def cell(cm):
                attrs = cm.group(1) or ""
                k = col[0]
                col[0] += _attr_int(attrs, "colspan")
                lab = heads[k] if k < len(heads) else ""
                # A cell holding nothing but a dash is a column this row has no answer for.
                # Worth a blank in a grid, where the eye skips it; worth nothing on a phone,
                # where it is a whole labelled line saying "no". Marked here, hidden there.
                inner = re.sub(r"<[^>]+>", "", cm.group(2))
                empty = ' data-empty="1"' if _DASH.match(html.unescape(inner)) else ""
                open_tag = cm.group(0)[:cm.group(0).index(">")]
                return f'{open_tag} data-l="{esc(lab)}"{empty}>{cm.group(2)}</td>'
            return _TD.sub(cell, rm.group(0))

        body = _TR.sub(one_row, body)
        headers = _header_rows(body)
        if headers:
            first, last = headers[0], headers[-1]
            body = (body[:first.start()] + "<thead>" + body[first.start():last.end()]
                    + "</thead><tbody>" + body[last.end():] + "</tbody>")
        out.append(f"<table{attrs}>" + body + "</table>")
        pos = m.end()
    out.append(page[pos:])
    return "".join(out)


def legend():
    """What the columns mean — once, folded, for a reader who wants it.

    It used to be repeated in full under every sport, which is ten copies of the same
    paragraph in a page whose job is to let someone compare numbers.
    """
    return f"""<details class="sport"><summary><b>How to read this</b>
<span class="mut"> · what the columns mean</span></summary>
<div class="note sm"><b>Record</b> is settled bets won\u2013lost on the US exchanges, flat
${int(T.STAKE)} a bet at the price available before the start. <b>Won v priced</b> is wins against
the wins the prices implied \u2014 beating that is the whole test, and the ranking sorts on it per
bet rather than on ROI, which mostly reflects the prices a pair happened to be offered.
<b>Verdict</b> is read only at {MIN_N}+ settled bets: <i>Proven edge</i> is ahead of the prices by
z \u2265 2, <i>Working</i> is ahead, <i>No edge</i> is not; under {MIN_N} a pair is only
<i>Promising</i> or <i>Behind so far</i>, and under {EARLY_N} it is <i>Too early</i> and is not
ranked at all. <b>If faded</b> is what backing the OTHER side of the same bets would have
returned \u2014 not this row's ROI with the sign flipped, since both sides of a book are sold
above fair, so fading an average rule loses that overround plus its fee; a large positive there
means the rule is picking the wrong side, which is a different complaint from having no edge.
<b>v the close</b> is how far the price moved toward the pick between the bet and the start, in
cents, with t \u2014 the mean over its own standard error. It answers a different question and
answers it sooner: a win record carries the outcome's own noise, so near an even price a real 2%
edge needs thousands of settled bets to reach z 2, while the same closing prices read in tens.
Called <b>ahead</b> or <b>behind</b> at t {T.CLV_T:g} over {T.CLV_MIN_N}+ fresh closes;
<b>level</b> is a real answer, not a missing one. Beating the close is not the same as making
money, and nothing is promoted or retired on it alone. Production is entered by hand.</div>
</details>"""


def _base_sport(sport):
    """The market a pair trades, with its scope stripped: soccer_o15_cup -> soccer_o15."""
    for sfx in S.SCOPE_LABEL:
        if str(sport).endswith(sfx):
            return str(sport)[:-len(sfx)]
    return str(sport)


def market_folds(d, rs, fam):
    """Soccer's rules grouped by the MARKET they trade, rather than listed flat.

    Soccer is not one test, it is eight: over 1.5, over 2.5, under 3.5, a side to score 1+,
    a side to score 2+, a side +0.5, both to score, corners. Each asks a different question
    at a different toll — 2.4% on a side +0.5 against 4.8% on a side to score 1+, on the same
    fixtures — and each carries a cup and an international twin. Listed flat that came to 26
    rows of which 22 had never settled a bet, which is a list nobody reads. Grouped, a reader
    picks the market first and then reads three or four rows, and each market's rules are
    ranked against each other rather than against rules answering a different question.
    """
    groups = {}
    for r in rs:
        groups.setdefault(_base_sport(r["sport"]), []).append(r)
    out = []
    for base in sorted(groups, key=lambda b: (-sum(r["a"]["n"] for r in groups[b]),
                                              S.SPORTS.get(b, b))):
        g = groups[base]
        ranked = rank_rows(g)
        n = sum(r["a"]["n"] for r in g)
        hold, _hn = T.market_cost(d, {base, base + "_cup", base + "_intl"},
                                  venues=T.TRADEABLE_VENUES)
        prod = sum(r["prod"] for r in g)
        bits = [f"{len(g)} rule" + ("" if len(g) == 1 else "s"),
                f"{n} settled" if n else "nothing settled yet"]
        if hold is not None:
            bits.append(f"both sides cost {hold * 100:.1f}%")
        if prod:
            bits.append(f"{prod} in Production")
        # A sport key whose label IS the section's own title names nothing — "Soccer" under
        # Soccer, "Tennis" under Tennis. That domain is the match-winner market, so it is
        # called what it is. Climate and Commodities under Markets keep their own names.
        full = S.SPORTS.get(base, base)
        name = "Match winner" if full == fam else full.split(" · ")[-1]
        out.append(f"""<details class="sport"><summary><b>{esc(name)}</b>
<span class="mut"> · {esc(' · '.join(bits))}</span></summary>
<div class="tbl"><table>{SPORT_HEAD}{''.join(_row(r, rk, pv, in_market=True) for rk, pv, r in ranked)}</table></div></details>""")
    return "\n".join(out)


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
{market_folds(d, rs, f) if len({_base_sport(r["sport"]) for r in rs}) > 1 else '<div class="tbl"><table>' + SPORT_HEAD + ''.join(_row(r, rk, prov) for rk, prov, r in ranked) + '</table></div>'}
{league_panel(d, rs) if f in BY_LEAGUE else ''}
{definitions(rs)}</details>""")
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
                if r["verdict"] in ("promising", "behind", "early") else
                f'<div class="sm mut">{esc(meta["retired"])}</div>' if r["verdict"] == "retired" else "")
        pc = lambda x: "—" if x is None else f'<span class="{fmt.tone(x, ".2f", 100)}">{fmt.pct(x, digits=2, sign=True)}</span>'
        # A stock pick is judged against SPY over its own days; a timing rule on an index or a
        # coin against cash, since set against its own asset it would show zero edge by design.
        vs = "v cash" if meta.get("bench") == "cash" else "v SPY"
        rows.append(f"""<tr><td><details class="src"><summary><b>{esc(meta['label'])}</b>
<div class="sm mut">{esc(meta['lane'].title())} · {esc(r['rule'])}</div></summary>
<div class="sm mut">{esc(meta['note'])}</div></details></td>
<td><span class="sig {chip}">{esc(label)}</span>{more}</td>
<td class="num">{r['days']}</td>
<td class="num">{r['trades']}<div class="sm mut">{r['open']} open</div></td>
<td class="num">{pc(r['mean'])}<div class="sm mut">{fmt.tstat(r['t']) if r['days'] > 1 else ''}</div></td>
<td class="num">{pc(r['edge'])}<div class="sm mut">{vs}{(" · " + fmt.tstat(r['edge_t'])) if r['days'] > 1 else ''}</div></td>
<td class="num {cls(r['total'])}">{money(r['total']) if r['trades'] else '—'}</td>
<td class="num mut sm">{esc(r['last'][:10]) or '—'}</td></tr>
<tr><td colspan="8" class="sm mut">Backtest before the lane went live ({esc(str((r.get('research_window') or ['', ''])[0]))} to
{esc(str((r.get('research_window') or ['', ''])[1]))}, not part of the record above):
{r['research_days']} entry days, {r['research_trades']} trades,
{'—' if r['research_edge'] is None else fmt.pct(r['research_edge'], digits=2, sign=True)} a day {vs}, {fmt.tstat(r['research_t'])}.</td></tr>""")
    return "\n".join(rows)


def _as_now(now):
    now_dt = now or datetime.now(timezone.utc)
    if now_dt.tzinfo is None:
        now_dt = now_dt.replace(tzinfo=timezone.utc)
    return now_dt.astimezone(timezone.utc)


_FOOT = "Read-only static export · rebuilt by GitHub Actions · research, not betting advice."


def _week_crumb(slug):
    """2026-W39 -> W39. The archive trail uses the short week name."""
    if slug == "undated":
        return "Undated"
    match = re.fullmatch(r"\d{4}-(W\d{2})", slug or "")
    return match.group(1) if match else (slug or "")


def _archive_document(title, description, sections, body, now_dt, crumb):
    return site_chrome.document(
        title, description, "sandbox", sections,
        site_chrome.stamp(now_dt), body,
        script_src="./site.js", scripts=("./tables.js",),
        prefix="../", crumb=crumb,
    )


def archive_index_html(groups, now_dt):
    links = _archive_links(groups, "./")
    body = f"""<h1>Archive</h1>
<p class="lede">Settled bets older than the last {RECENT_DAYS} days in America/Chicago, one page per ISO week. Each bet is here or on the Sandbox, never both. Paper only.</p>
<section id="weeks">
<h2>Weeks</h2>
{links or '<div class="note">Nothing archived.</div>'}
</section>
<p><a href="../sandbox.html#archive">Back to the Sandbox</a></p>
<footer>{_FOOT}</footer>
"""
    return _archive_document(
        "Edge Machine · Archive",
        "Settled Sandbox bets by week.",
        (("weeks", "Weeks"),),
        body, now_dt,
        (("Sandbox", "../sandbox.html"), ("Archive", None)),
    )


_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _ct_phrase(value):
    """5:15 PM CT Sep 28. The clock is America/Chicago, including the date."""
    local = fmt.chicago(value)
    return f"{fmt.clock(value)} {_MONTHS[local.month - 1]} {local.day}"


def _outage_days(o):
    start = fmt.chicago(o["start"])
    end = fmt.chicago(o["end"])
    if end < start:
        start, end = end, start
    return start.date(), end.date()


def outage_sentence(o):
    """The plain-English line for one outage. Times come from the record.

    A later outage with the same shape — nothing logged, nothing back-filled —
    gets the same sentence. One that did log, or was back-filled, does not claim
    the counts are a hole.
    """
    span = f"from {_ct_phrase(o['start'])} to {_ct_phrase(o['end'])}"
    if o.get("logged") is False and o.get("backfilled") is False:
        return (f"No quotes were logged {span} because of a tracker failure. "
                "Counts for those days are lower for that reason, not because of fewer opportunities.")
    if o.get("backfilled") is True:
        return ""
    return (f"The tracker failed {span}. "
            "Counts for those days are lower for that reason, not because of fewer opportunities.")


def outage_notes(d, day_lo=None, day_hi=None):
    """Note HTML for outages whose Chicago dates overlap [day_lo, day_hi].

    day_lo and day_hi both None means the counts cover the whole record, which
    is what a lane total does. Empty when nothing overlaps, so a page with no
    outage in range is unchanged. The trailing newline is part of the note, so
    dropping the note puts the surrounding markup back where it was.
    """
    if not d:
        return ""
    bits = []
    for o in (d.get("meta") or {}).get("outages") or []:
        if not isinstance(o, dict) or not o.get("start") or not o.get("end"):
            continue
        if day_lo is not None and day_hi is not None:
            a, b = _outage_days(o)
            if a > day_hi or b < day_lo:
                continue
        text = outage_sentence(o)
        if text:
            bits.append(f'<div class="note">{esc(text)}</div>')
    if not bits:
        return ""
    return "\n".join(bits) + "\n"


def _week_bounds(slug):
    """(Monday, Sunday) for an ISO week slug, or None for the undated bucket."""
    if not slug or slug == "undated":
        return None
    try:
        monday = datetime.strptime(slug + "-1", "%G-W%V-%u").date()
    except ValueError:
        return None
    return monday, monday + timedelta(days=6)


def archive_week_html(slug, rows, now_dt, d=None):
    rows_html, n = settled_rows({"quotes": rows})
    label = "Undated" if slug == "undated" else slug
    noun = "bet" if n == 1 else "bets"
    bounds = _week_bounds(slug)
    note = outage_notes(d, *bounds) if d is not None and bounds else ""
    body = f"""<h1>Archive · {esc(label)}</h1>
<p class="lede">{n:,} settled {noun}. Paper only. <a href="./index.html">All weeks</a> · <a href="../sandbox.html#recently-settled">Recently settled</a></p>
{note}{_tools("Search contests…", "Search this week", view=True) if n else ""}
{_sortable(HIST_HEAD, rows_html) if n else '<div class="note">Nothing settled this week.</div>'}
<footer>{_FOOT}</footer>
"""
    return _archive_document(
        f"Edge Machine · {label}",
        f"Sandbox bets settled in {label}.",
        (),
        body, now_dt,
        (("Sandbox", "../sandbox.html"), ("Archive", "./index.html"),
         (_week_crumb(slug), None)),
    )


def hide_refused_tours(d):
    """A page copy with reset-lane bets on a refused tour left out.

    The ledger file is not written. Stored rows stay where they are.
    pm_combo4 is not a reset lane, so its baskets stay in this copy.
    """
    if not d:
        return d
    out = dict(d)
    out["quotes"] = [q for q in (d.get("quotes") or []) if not S.tennis_refused_row(q)]
    if "_archive" in d:
        out["_archive"] = [q for q in (d.get("_archive") or []) if not S.tennis_refused_row(q)]
    return out


def hide_removed(d):
    """A page copy with removed quotes, coverage, and feed status left out.

    The ledger file is not written. Stored rows stay where they are. Weather
    and the tip lanes use the same gate.
    """
    if not d:
        return d
    out = dict(d)
    out["quotes"] = [q for q in d.get("quotes") or [] if not S.removed_row(q)]
    if "_archive" in d:
        out["_archive"] = [q for q in d.get("_archive") or [] if not S.removed_row(q)]
    cov = d.get("coverage")
    if cov:
        out["coverage"] = {
            sp: {name: n for name, n in (cells or {}).items()
                 if not S.lane_removed(name, sp)}
            for sp, cells in cov.items()
            if sp not in S.REMOVED_SPORTS and sp not in S.REMOVED_VENUE_SPORTS}
    status = d.get("feed_status")
    if status:
        out["feed_status"] = {k: v for k, v in status.items() if k not in S.REMOVED_SOURCES}
    return out


def render_pages(now=None, d=None, st=None):
    """Sandbox HTML, the archive index, and {{week slug: week HTML}}.

    Presentation only. `now` is the build time the 7-day window is measured from.
    Removed rows stay in the ledger. Headlines, counts and the bet tables use a
    copy without them. Baseline, comparison and verdict keep the full ledger,
    so hiding a lane does not move a kept lane's numbers. Each stamp row uses
    that ledger minus only the source being judged.
    """
    raw = T.load() if d is None else d
    shown = hide_refused_tours(hide_removed(raw))
    st = T.load_stages() if st is None else st
    now_dt = _as_now(now)
    sandbox = _sandbox_html(shown, st, now_dt, full=raw)
    recent, older = partition_settled(shown, now_dt)
    groups = archive_groups(older)
    weeks = {slug: archive_week_html(slug, groups[slug], now_dt, shown) for slug in _week_order(groups)}
    return sandbox, archive_index_html(groups, now_dt), weeks


def archive_documents(now=None, d=None, st=None):
    """{{'archive/index.html': html, 'archive/YYYY-Www.html': html}}."""
    _sandbox, index, weeks = render_pages(now, d=d, st=st)
    out = {"archive/index.html": index}
    for slug, html in weeks.items():
        out[f"archive/{slug}.html"] = html
    return out


def build(now=None, d=None, st=None):
    sandbox, _index, _weeks = render_pages(now, d=d, st=st)
    return sandbox


def _sandbox_html(d, st, now_dt, full=None):
    """`d` is the page copy. `full` is the unfiltered ledger.

    Each lane's own baseline, comparison and verdict read `full`, the ledger
    the tracker assesses. Each stamp row reads `full` minus that source's own
    removed rows, so a kept source matches the unfiltered number and its own
    removed sport does not count. A reset lane's stamp is only the bets logged
    since the tour clock. Blind baselines and every other cross-lane
    total — a leaderboard, a source-by-sport cell, a by-sport or
    by-competition total — read `d`.
    """
    full = d if full is None else full
    for q in T.all_bets(d):
        if q.get("bet") and q.get("status") in _HIST:
            T.note_unreadable_start(q)
    # `scores` decides which stamp rows exist. Each row is judged on `full`
    # minus that source's own removed rows. The blind-baseline table and the
    # by-sport sections below take `d`.
    scores = T.score(d)
    cov = d.get("coverage") or {}
    ou = (d.get("meta") or {}).get("odds_api") or {}
    odds_line = (f" Pinnacle prices come through The Odds API: {ou.get('calls', 0)} of "
                 f"{ou.get('allowance', '?')} allowed paid calls last run, "
                 f"{ou['remaining']} credits left until they reset on the 1st."
                 if ou.get("remaining") is not None else "")
    live_rows, n_live = open_rows(d)
    recent, older = partition_settled(d, now_dt)
    groups = archive_groups(older)
    recent_rows, _n_recent = settled_rows({"quotes": recent})
    n_hist = len(recent) + len(older)
    n_void = sum(1 for q in T.bet_rows(d)
                 if q["status"] == "void" and not S.removed_row(q))
    # A stale city-day flag does not make a void a repeat. The void stays in
    # this count and on the settled pages, and out of the city-day count.
    # Weather is not on the page, so its repeats are not in this count.
    n_city = sum(1 for q in T.bet_rows(d)
                 if _cityday_repeat(q) and not S.removed_row(q))
    _city = (f" · {n_city} city-day repeat set aside" if n_city == 1
             else (f" · {n_city} city-day repeats set aside" if n_city else ""))
    today = _chicago_today(now_dt)
    recent_note = outage_notes(d, today - timedelta(days=RECENT_DAYS - 1), today)
    # Lane tables add up every quote ever logged, so they cover any recorded outage.
    lane_note = outage_notes(d)
    archive_links = _archive_links(groups, "./archive/")
    n_unconnected = sum(1 for name, m in S.SOURCES.items()
                        if not m["connected"] and name not in S.REMOVED_SOURCES)
    in_prod = sum(1 for p in (st.get("pairs") or {}).values() if p.get("stage") == "production")
    # Counted over the pairs still running. Pooling every bet ever logged put this at 46%,
    # but 952 of the misses were one retired rule that quoted hundreds of ladder rungs a day
    # and can never improve — a number dragged down by history says nothing about whether the
    # snapshots are working now.
    # Per-lane rows. The baseline, comparison and verdict on each one read
    # `full`; the sport sections then total those rows, which are kept lanes.
    rows = pair_list(full, st)
    live = {(r["name"], r["sport"]) for r in rows if r["v"] != "retired"}
    leads = sorted(x for x in (T.close_lead_min(q) for q in T.bet_rows(d)
                               if (q["source"], q["sport"]) in live)
                   if x is not None and x >= 0)
    close_line = (f" A closing price counts only when taken within {T.CLOSE_MAX_LEAD_MIN} minutes "
                  f"of the start ({sum(1 for x in leads if x <= T.CLOSE_MAX_LEAD_MIN)} of {len(leads)} "
                  f"on the pairs still running).") if leads else ""
    # Eliminated pairs leave the sport sections and the insights, but NOT the reconciliation:
    # every settled bet still has to be accounted for, out of sight or not.
    shown = [r for r in rows if not eliminated(r)]
    vc = {k: sum(1 for r in rows if r["v"] == k and not r.get("gone")) for k in VERDICTS}

    body = f"""<h1>Sandbox</h1>
<p class="lede">Which rules and tipsters are making money, and which are failing. Every one is backed at real prices and settled on real results. Paper only.</p>
<div class="tiles">
<div class="tile"><b>{in_prod}</b><span>in Production</span></div>
<div class="tile"><b class="{'pos' if vc['proven'] + vc['working'] else ''}">{vc['proven'] + vc['working']}</b><span>working (30+ bets)</span></div>
<div class="tile"><b>{vc['promising']}</b><span>promising (10+ bets)</span></div>
<div class="tile"><b class="{'neg' if vc['noedge'] else ''}">{vc['noedge']}</b><span>no edge</span></div>
<div class="tile"><b>{n_live:,}</b><span>bets running</span></div>
</div>
{feed_health(d)}

<section id="running">
<h2>Running ({n_live:,})</h2>
<p class="sm mut">Bets still open. The price is the number next to the contest.</p>
{_tools("Search contests…", "Search running bets", view=True) if n_live else ""}
{_sortable(LIVE_HEAD, live_rows) if n_live else '<div class="note">No open bets.</div>'}
</section>

<section id="recently-settled">
<h2>Recently settled ({len(recent):,})</h2>
<p class="sm mut">The last {RECENT_DAYS} days in America/Chicago, through the build date. {n_hist - n_void:,} settled on the record{f" · {n_void} void" if n_void else ""}{_city}; older bets are in the archive.</p>
{recent_note}{_tools("Search contests…", "Search recently settled bets", view=not n_live) if recent else ""}
{_sortable(HIST_HEAD, recent_rows) if recent else f'<div class="note">Nothing settled in the last {RECENT_DAYS} days.</div>'}
</section>

<section id="archive">
<h2>Archive</h2>
<p class="sm mut">One page per week. <a href="./archive/index.html">Archive index</a></p>
{archive_links or '<div class="note">Nothing archived.</div>'}
</section>

<section id="summary">
<details class="sec"><summary><h2>What the Sandbox says</h2></summary>
<div class="note">{insights(shown)}</div></details>
</section>

<section id="by-sport">
<details class="sec" open><summary><h2>Every rule and tipster, by sport</h2></summary>
<div class="folds-ctl"><button type="button" data-fold="sport" data-open="1">Open all</button><button type="button" data-fold="sport" data-open="0">Close all</button></div>
{legend()}
{lane_note}{sport_sections(d, shown)}
{eliminated_section(rows)}
{reconcile(d, rows)}

</details>
</section>

<section id="reference">
<details class="sec"><summary><h2>Reference</h2></summary>
<details class="ref"><summary>Retired, or declared but not connected ({n_unconnected})</summary>
<div class="tbl"><table><tr><th>Source</th><th>Why it is not scored</th></tr>{unconnected_rows(d)}</table></div></details>
<details class="ref"><summary>Stamp of approval — every criterion, every source</summary>
<div class="note">The stamp needs <b>{T.APPROVAL['min_bets']}+ settled bets spanning {T.APPROVAL['min_days']}+ days</b>
({T.SPORT_RULES['high']['approval']['min_bets']}+ fresh bets at z ≥ {T.SPORT_RULES['high']['approval']['z_min']:g}, no day span, in high-volume sports),
wins beating the price by z ≥ {T.APPROVAL['z_min']:g}, ROI beating every blind rule on the same contests,
still profitable without its biggest win, and profitable in both halves. Fixed 2026-09-12.</div>
{approval_table(d, scores, full=full)}</details>
<details class="ref"><summary>Blind baselines — what choosing nothing made</summary>{baseline_table(d)}</details>
{"" if "pinnacle" in S.REMOVED_SOURCES else f'<details class="ref"><summary>Pinnacle v venue</summary>{pinnacle_table(d)}</details>'}
<details class="ref"><summary>Feed coverage on the last run</summary>{coverage_table(cov)}
<div class="note">A cell of the form k of n is quotes matched out of the board rows that lane examined: the right series, before its own band. 0 of 0 means nothing was offered. 0 of n means rows were offered and none qualified. A bare number is a count from a run that stored no denominator.</div></details>
<details class="ref" id="method"><summary>Method</summary><div class="note">
Tipsters and rules name a side and are backed every time; models, books and exchanges state a probability
and are backed only on a {int(T.EDGE_MIN*100)}pp disagreement with the price. <b>Polymarket US</b> is the venue
wherever it lists a contest; <b>Kalshi</b> is the venue for soccer and anything Polymarket US is missing, with
soccer kickoffs taken from ESPN. A contest is logged only with a real book (spread ≤ {int(S.MAX_SPREAD*100)}¢), at the
ask. Until 2026-09-13 the venue was polymarket.com; those bets still settle there but are not counted when a pair is judged.
Quotes logged before the book rule on boxing, cricket and table tennis were voided ({esc(T.PRE_GATE_NOTE)}).{odds_line}{close_line}
A positive ROI under {MIN_N} settled bets is not a finding.</div></details>

</details>
</section>

<footer>Read-only static export · rebuilt by GitHub Actions · research, not betting advice.</footer>
"""
    sections = (
        ("running", "Running"),
        ("recently-settled", "Recently settled"),
        ("archive", "Archive"),
        ("summary", "What it says"),
        ("by-sport", "By sport"),
        ("reference", "Reference"),
    )
    return site_chrome.document(
        "Sandbox Tracker",
        "Every source and rule under test, per sport, at real prices and settled on real results — what is working and what is not.",
        "sandbox",
        sections,
        site_chrome.stamp(now_dt),
        body,
        script_src="./site.js",
        scripts=("./tables.js",),
    )



# The QA page is gone (2026-09-18): the ladder is Sandbox, then Production by hand.
def _ticks(gate):
    passed = sum(1 for _k, _l, p, _d in gate if p)
    cells = "".join(
        f'<td><span class="{"pos" if p else "neg"}">{"✓" if p else "✗"}</span>'
        f'<div class="sm mut">{esc(det)}</div></td>' for _k, _l, p, det in gate)
    return passed, cells


def trading_page(now=None):
    """public_site/trading.html — the trading lane, on its own page.

    Same rows as the old hidden tab: trading_rows() is unchanged apart from
    the percent sign glyph.
    """
    import market_sources as MS
    import market_track as MT
    now_dt = now or datetime.now(timezone.utc)
    if now_dt.tzinfo is None:
        now_dt = now_dt.replace(tzinfo=timezone.utc)
    md = MT.load()
    trade_rules = MT.report(md)
    trade_open = sum(r["open"] for r in trade_rules)
    trade_note = ("" if MS.configured() else
                  '<div class="note">These rules are scanned and graded on the machine that holds '
                  'the market data keys, and the record below is what it published. This page is '
                  'built elsewhere and only renders it, so it does not reach the market itself.</div>')
    body = f"""<h1>Trading</h1>
<p class="lede">Stock and crypto rules under test, judged per entry day. Paper only.</p>
<div class="tiles">
<div class="tile"><b>{sum(1 for r in trade_rules if r['verdict'] in ('proven', 'working'))}</b><span>working (30+ days)</span></div>
<div class="tile"><b>{sum(1 for r in trade_rules if r['verdict'] == 'promising')}</b><span>promising</span></div>
<div class="tile"><b class="{'neg' if any(r['verdict'] == 'noedge' for r in trade_rules) else ''}">{sum(1 for r in trade_rules if r['verdict'] == 'noedge')}</b><span>no edge</span></div>
<div class="tile"><b>{sum(r['trades'] for r in trade_rules):,}</b><span>trades logged</span></div>
<div class="tile"><b>{trade_open:,}</b><span>open now</span></div>
</div>
{trade_note}
<section id="rules">
<h2>Stock rules under test</h2>
<div class="tbl"><table>{TRADE_HEAD}{trading_rows(md)}</table></div>
<div class="note sm">Each rule is <b>pre-registered</b>: its thresholds and the reason for them are fixed before it
logs a trade. A trade is logged only from bars that closed BEFORE it, and enters at the <b>next</b> bar's open —
never the signal bar's close. Costs of {int(MS.COST_BPS_PER_SIDE)}bp a side are charged on entry and exit.
<b>Judged per entry day</b>, because names bought the same morning rise and fall together, and against
<b>SPY over the identical days</b>: beating a rising market is not an edge. Read at {MT.READ_FLOOR}+ entry days;
under {MT.EARLY_N} a rule is only <i>Too early</i>. Click a rule for what it does.</div>
</section>
<footer>Read-only static export · rebuilt by GitHub Actions · research, not betting advice.</footer>
"""
    return site_chrome.document(
        "Edge Machine · Trading",
        "Stock and crypto rules under test, judged per entry day at real prices.",
        "trading",
        (("rules", "Rules"),),
        site_chrome.stamp(now_dt),
        body,
    )


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


def main():
    now = datetime.now(timezone.utc)
    sandbox, index, weeks = render_pages(now)
    _write(OUT, label_cells(sandbox))
    print(f"wrote {OUT}")
    import production
    prod_out = os.path.join(os.path.dirname(OUT), "production.html")
    _write(prod_out, label_cells(production.page(T.load(), T.load_stages(), production.load_feed(), "")))
    print(f"wrote {prod_out}")
    trade_out = os.path.join(os.path.dirname(OUT), "trading.html")
    _write(trade_out, label_cells(trading_page(now)))
    print(f"wrote {trade_out}")
    # Soccer rides the same rebuild because it reads the same ledger. A failure here must
    # not cost the Sandbox and Production pages that already rendered above.
    #
    # No Kalshi call happens here. lane-preflight.yml is deliberately `contents: read` with
    # no credentials, and a separate test asserts this job does not run the pre-flight at
    # all, because backup-refresh judges the tracker by its last success and a red
    # pre-flight must not read as a dead tracker. The Soccer page therefore renders the
    # pre-flight file only when one exists, and says how old it is.
    try:
        import soccer_build
        soccer_out = os.path.join(os.path.dirname(OUT), "soccer.html")
        _write(soccer_out, label_cells(soccer_build.build(now=now)))
        print(f"wrote {soccer_out}")
    except Exception as exc:                                    # noqa: BLE001
        print(f"::warning::soccer page not rebuilt ({type(exc).__name__}: {exc})")
    # Tennis and Cricket read the same ledger. Each failure stays on its own page.
    # The Kalshi pre-flight file is soccer-specific, so neither page reads it.
    try:
        import tennis_build
        tennis_out = os.path.join(os.path.dirname(OUT), "tennis.html")
        _write(tennis_out, label_cells(tennis_build.build(now=now)))
        print(f"wrote {tennis_out}")
    except Exception as exc:                                    # noqa: BLE001
        print(f"::warning::tennis page not rebuilt ({type(exc).__name__}: {exc})")
    try:
        import cricket_build
        cricket_out = os.path.join(os.path.dirname(OUT), "cricket.html")
        _write(cricket_out, label_cells(cricket_build.build(now=now)))
        print(f"wrote {cricket_out}")
    except Exception as exc:                                    # noqa: BLE001
        print(f"::warning::cricket page not rebuilt ({type(exc).__name__}: {exc})")
    archive_dir = os.path.join(os.path.dirname(OUT), "archive")
    os.makedirs(archive_dir, exist_ok=True)
    keep = {"index.html"}
    _write(os.path.join(archive_dir, "index.html"), label_cells(index))
    for slug, html in weeks.items():
        name = slug + ".html"
        keep.add(name)
        _write(os.path.join(archive_dir, name), label_cells(html))
    for name in os.listdir(archive_dir):
        if name.endswith(".html") and name not in keep:
            os.remove(os.path.join(archive_dir, name))
    print(f"wrote {len(keep)} archive pages in {archive_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
