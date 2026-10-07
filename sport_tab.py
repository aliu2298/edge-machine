#!/usr/bin/env python3
"""One sport's page, built the way the Soccer tab is built.

Records, verdicts and the by-market panels are the Sandbox's own functions, so a
sport tab cannot disagree with the Sandbox about the same pair. The idle table
names connected lanes that have never logged a quote. The Kalshi pre-flight file
is a soccer check, so only the Soccer page shows that column.
"""
import datetime
import json
import os

import sandbox_build as B
import sandbox_sources as S
import sandbox_track as T
import site_chrome as C

ROOT = os.path.dirname(os.path.abspath(__file__))
PREFLIGHT = os.path.join(ROOT, "data", "lane_preflight.json")

# How stale the pre-flight may be before the Soccer page stops presenting it as current.
# Its own workflow runs every three hours, so a file older than this means that job is failing.
STALE_HOURS = 8

_FOOT = "Read-only static export · rebuilt by GitHub Actions · research, not betting advice."


def esc(x):
    return C.esc("" if x is None else x)


def idle_lanes(prefix, d, skip=()):
    """Connected lanes in this sport with no quote and no archived bet, so no Sandbox row.

    `prefix` is the sport-key prefix ("soccer", "tennis", "cricket"). Table tennis
    does not use the tennis prefix. A lane the Sandbox already lists, and a lane
    taken off the board, are not idle. A compact price row is not a bet, so it
    does not take a lane off this list.
    """
    seen = {q.get("source") for q in d.get("quotes", [])}
    # A lane whose only bets have been rolled into the archive has fired.
    # Compact price rows are not bets and do not count as a firing.
    for q in d.get("_archive") or []:
        if q.get("bet"):
            seen.add(q.get("source"))
    skipped = set(skip)
    out = []
    for name, meta in S.SOURCES.items():
        if not meta.get("connected") or name in seen or name in skipped:
            continue
        sports = [s for s in (meta.get("sports") or [])
                  if str(s).startswith(prefix) and not S.lane_removed(name, s)]
        if not sports:
            continue
        out.append(dict(name=name, label=meta.get("label", name), sports=sports,
                        kind=meta.get("kind", "")))
    return sorted(out, key=lambda r: r["label"])


def family_rows(d, st, family):
    """The Sandbox rows for one family, minus pairs moved out of the sport sections.

    `pair_list` already drops `lane_removed`. Eliminated pairs are drawn in the
    Sandbox's own eliminated list, not in the family section this page repeats.
    """
    return [r for r in B.pair_list(d, st)
            if B.family(r["sport"]) == family and not B.eliminated(r)]


def _open_bets(d, prefix):
    return sum(1 for q in d.get("quotes", [])
               if q.get("bet") and q.get("status") == "open"
               and str(q.get("sport") or "").startswith(prefix)
               and not S.removed_row(q) and not S.tennis_refused_row(q))


def _tiles(rows, idle, open_bets):
    settled = sum(r["a"]["n"] for r in rows)
    prod = sum(1 for r in rows if r.get("prod"))
    return "".join(f'<div class="tile"><b>{v:,}</b><span>{k}</span></div>' for k, v in (
        ("lanes with a record", len(rows)),
        ("settled bets", settled),
        ("bets running", open_bets),
        ("in Production", prod),
        ("registered, never fired", len(idle)),
    ))


def preflight_report(path=PREFLIGHT, now=None):
    """(by_lane, note). Never raises: a missing file is a stated absence, not a crash."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    try:
        blob = json.load(open(path))
    except (OSError, ValueError):
        return {}, ('<div class="note">No Kalshi pre-flight has been recorded, so the '
                    'status column is blank. The check runs every three hours in its own '
                    'job and reports there; it is <b>read-only by design</b> and does not '
                    'write to the repository, so this column fills in only when the file '
                    'is refreshed by hand with <code>python3 lane_preflight.py</code>.</div>')
    by = {}
    for row in blob.get("lanes", []):
        by.setdefault(row.get("lane"), []).append(row)
    checked = blob.get("checked", "")
    try:
        when = datetime.datetime.strptime(checked, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=datetime.timezone.utc)
        age = (now - when).total_seconds() / 3600
    except ValueError:
        return by, '<div class="note">The pre-flight stamp could not be read.</div>'
    if age > STALE_HOURS:
        return by, (f'<div class="note"><b class="neg">This status is {age:.0f}h old.</b> '
                    f'The pre-flight is read-only by design and does not commit, so this '
                    f'file only moves when it is refreshed by hand. Read the column as '
                    f'history, not as now — the live check is in its own job\'s summary.</div>')
    return by, (f'<div class="note sm">Kalshi checked {age:.1f}h ago. '
                f'“Listed but not on the board” means the market exists but sits outside '
                f'the four-day window the feed reads — a calendar fact, not a fault.</div>')


def _state_cell(rows):
    if not rows:
        return '<td class="mut">—</td>'
    worst = {"never seen": 0, "exists but no open markets": 1,
             "listed but not on the board": 2, "listed": 3}
    rows = sorted(rows, key=lambda r: worst.get(r.get("state"), 1))
    r = rows[0]
    state = r.get("state", "")
    cls = "neg" if state == "never seen" else ("mut" if state != "listed" else "pos")
    detail = r.get("detail") or ""
    series = " · ".join(sorted({x.get("series", "") for x in rows}))
    return (f'<td><span class="{cls}">{esc(state)}</span>'
            f'<div class="sm mut">{esc(series)}{" — " + esc(detail) if detail else ""}</div></td>')


def _count_cell(v):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return '<td class="num mut">—</td>'
    n = int(v)
    cls = "pos" if n else "neg"
    return f'<td class="num {cls}">{n:,}</td>'


def venue_listing(d, family):
    """The Polymarket US listing for this family, from the ledger's stored counts.

    The venue logs prices and does not bet, so `pair_list` gives it no row. The
    Kalshi pre-flight is not consulted. A removed sport, including table tennis,
    is left out.
    """
    meta = S.SOURCES.get("polymarket_us") or {}
    sports = [sp for sp in (meta.get("sports") or [])
              if B.family(sp) == family
              and not S.lane_removed("polymarket_us", sp)
              and sp not in S.REMOVED_VENUE_SPORTS]
    if not sports:
        return ""
    cov = d.get("coverage") or {}
    rows = []
    for sp in sports:
        cell = cov.get(sp) or {}
        rows.append(
            f'<tr><td>{esc(S.SPORTS.get(sp, sp))}</td>'
            f'{_count_cell(cell.get("polymarket_us"))}'
            f'{_count_cell(cell.get("polymarket_us_listed"))}'
            f'{_count_cell(cell.get("polymarket_us_priced"))}</tr>')
    head = ('<tr><th>Market</th><th class="num">Taken</th>'
            '<th class="num">Listed</th><th class="num">Priced</th></tr>')
    return f"""<section id="listing">
<h2>Polymarket US</h2>
<div class="note">The venue listing. It logs prices and has no record in the table below, so the Sandbox does not give it a row. The counts are what the last run stored.</div>
<div class="tbl"><table>{head}{''.join(rows)}</table></div>
</section>"""


def build(family, key, title, lede, d=None, st=None, now=None, description=None,
         preflight=False, cards=False):
    """One sport tab. `preflight` is the Soccer Kalshi column; other sports leave it off.

    `cards` is the rule-card grid. Soccer, Tennis, and Cricket each ask for
    it, and each has its own renderer, so a change on one page does not move
    the others.
    """
    now = now or datetime.datetime.now(datetime.timezone.utc)
    d = d if d is not None else T.load()
    st = st if st is not None else T.load_stages()
    rows = family_rows(d, st, family)
    idle = idle_lanes(key, d, skip=tuple(r["name"] for r in rows))
    tiles = _tiles(rows, idle, _open_bets(d, key))
    if cards:
        if family == "Tennis":
            import tennis_cards
            sections = tennis_cards.render(d, rows, now)
        elif family == "Cricket":
            import cricket_cards
            sections = cricket_cards.render(d, rows, now)
        else:
            import soccer_cards
            sections = soccer_cards.render(d, rows, now)
    else:
        sections = B.sport_sections(d, rows)
    if description is None:
        description = lede

    if preflight:
        by_lane, pf_note = preflight_report(now=now)
        # idle_table re-reads lanes when status is set. Pass the tile list by
        # calling the table builder with the lanes already chosen, so the skip
        # set is the one the tiles counted.
        idle_html = _idle_html(idle, by_lane, status=True, prefix=key)
        if family == "Soccer" and cards:
            body = f"""<div class="soccer-page-head">
<div><span class="soccer-kicker">Edge Machine</span><h1>{esc(family)}</h1>
<p class="lede">{esc(lede)}</p></div>
<div class="tiles">{tiles}</div>
</div>

<section id="lanes">
{sections}
</section>

<section id="health" class="soccer-health">
<details>
<summary><span><b>System & registered lanes</b><small>{len(idle)} waiting for a market</small></span></summary>
<div class="note">These lanes are connected and waiting, and have <b>no row in the
Sandbox</b> because they have never logged a quote. This is market availability, not
evidence that the rule failed.</div>
{pf_note}
{idle_html}
</details>
</section>
<footer>{_FOOT}</footer>
"""
            toc = (("today", "Today"), ("upcoming", "Upcoming"), ("in-play", "Past kickoff"), ("rules", "Rules"),
                   ("health", "System"))
        else:
            body = f"""<h1>{esc(family)}</h1>
<p class="lede">{lede}</p>
<div class="tiles">{tiles}</div>

<section id="idle">
<h2>Registered, never fired</h2>
<div class="note">These lanes are connected and waiting, and have <b>no row in the
Sandbox</b> — it builds from the ledger, and they have never logged a quote. That is not
the rule failing. It is Kalshi not listing the market, and the status below is the
pre-flight's own verdict on each one.</div>
{pf_note}
{idle_html}
</section>

<section id="lanes">
<h2>Lanes with a record</h2>
{sections}
</section>
<footer>{_FOOT}</footer>
"""
            toc = (("idle", "Registered, never fired"), ("lanes", "Lanes with a record"))
    else:
        parts = [f"""<h1>{esc(family)}</h1>
<p class="lede">{lede}</p>
<div class="tiles">{tiles}</div>
"""]
        toc = []
        if idle:
            parts.append(f"""
<section id="idle">
<h2>Registered, never fired</h2>
<div class="note">These lanes are connected and have <b>no row in the record below</b>. They have never logged a quote. The Kalshi pre-flight is a soccer check, so this table does not show a status column.</div>
{_idle_html(idle, {}, status=False, prefix=key)}
</section>
""")
            toc.append(("idle", "Registered, never fired"))
        listing = venue_listing(d, family)
        if listing:
            parts.append("\n" + listing + "\n")
            toc.append(("listing", "Polymarket US"))
        parts.append(f"""
<section id="lanes">
<h2>Lanes with a record</h2>
{sections}
</section>
<footer>{_FOOT}</footer>
""")
        toc.append(("lanes", "Lanes with a record"))
        body = "".join(parts)

    return C.document(
        title,
        description,
        key,
        tuple(toc),
        C.stamp(now),
        body,
        script_src="./site.js",
        scripts=("./tables.js",),
    )


def _idle_html(lanes, by_lane, status, prefix):
    """The idle table from a lane list already filtered. Soccer's column included."""
    if not lanes:
        return f'<div class="note">Every connected {prefix} lane has logged at least once.</div>'
    rows = []
    for r in lanes:
        sports = ", ".join(S.SPORTS.get(s, s) for s in r["sports"])
        state = _state_cell(by_lane.get(r["name"], [])) if status else ""
        rows.append(
            f'<tr><td>{esc(r["label"])}</td><td class="sm mut">{esc(sports)}</td>{state}</tr>')
    if status:
        head = '<tr><th>Lane</th><th>Market</th><th>Kalshi status</th></tr>'
    else:
        head = '<tr><th>Lane</th><th>Market</th></tr>'
    return f'<div class="tbl"><table>{head}{"".join(rows)}</table></div>'


def write(path, html):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write(html)
    os.replace(tmp, path)
    print(f"wrote {path} ({len(html):,} bytes)")
    return 0
