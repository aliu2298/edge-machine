#!/usr/bin/env python3
"""What the sport pages share below the template: the Sandbox rows of one family,
the connected lanes that have never fired, the Kalshi pre-flight report (a soccer
check, so only the Soccer page shows that column), the venue listing, and the
file writer. The pages themselves are sport_page, one template for every sport.
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
    """One sport tab. Kept for older callers: each family's page is its own builder
    on the shared template (sport_page) now, so this hands the call to it."""
    del key, title, lede, description, preflight, cards
    now = now or datetime.datetime.now(datetime.timezone.utc)
    d = d if d is not None else T.load()
    st = st if st is not None else T.load_stages()
    if family == "Tennis":
        import tennis_build
        return tennis_build.build(d, st, now)
    if family == "Cricket":
        import cricket_build
        return cricket_build.build(d, st, now)
    import soccer_build
    return soccer_build.build(d, st, now)


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
