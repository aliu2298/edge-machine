#!/usr/bin/env python3
"""The Soccer page: every soccer lane, including the ones that have never fired.

WHY IT EXISTS SEPARATELY. Soccer is 29 of the Sandbox's tested pairs, more than every
other sport combined, and they are spread across 23 market domains -- over 1.5, BTTS, team
totals, corners, each of them again for cups and again for internationals. Inside the
Sandbox they are one folding section among eight.

WHAT THIS PAGE ADDS THAT THE SANDBOX CANNOT. Ten connected soccer lanes have no row in the
Sandbox at all, because `pair_list` builds from the ledger and they have never logged a
single quote: the eight European league rules pre-registered in late September, plus two
MLS bands. A lane that has never fired is invisible exactly when you most want to know
about it, and the reason is never the rule -- it is that Kalshi is not listing the market.
The Idle section names them and gives each one the pre-flight's own verdict.

THE PRE-FLIGHT IS READ FROM DISK, NOT CALLED, AND NOTHING AUTOMATIC WRITES IT. The page is
rebuilt every three hours by the tracker, and a live venue call here would turn a Kalshi
hiccup into a failed publish. Nor can the pre-flight job write the file: lane-preflight.yml
is deliberately `contents: read` with no credentials, and a test asserts the tracker does
not run the check at all, because backup-refresh judges the tracker by its last success and
a red pre-flight must not read as a dead tracker. Both guards are worth more than this
column, so the file is refreshed by hand and the page states its age. Absent, the column is
blank and says why.

Records, verdicts and the by-league panel are the Sandbox's own, reused rather than
reimplemented, so the two pages can never disagree about the same pair.
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
OUT = os.path.join(ROOT, "public_site", "soccer.html")

FAMILY = "Soccer"
# How stale the pre-flight may be before the page stops presenting it as current. Its own
# workflow runs every three hours, so a file older than this means that job is failing.
STALE_HOURS = 8


def esc(x):
    return C.esc("" if x is None else x)


def soccer_rows(d, st):
    return [r for r in B.pair_list(d, st) if B.family(r["sport"]) == FAMILY]


def idle_lanes(d):
    """Connected soccer lanes with no quote in the ledger at all, so no Sandbox row.

    Keyed on the ledger rather than on bets: a lane that was offered a market and declined
    it HAS rows and belongs in the Sandbox. These have never been offered anything.
    """
    seen = {q.get("source") for q in d.get("quotes", [])}
    out = []
    for name, meta in S.SOURCES.items():
        if not meta.get("connected") or name in seen:
            continue
        sports = [s for s in (meta.get("sports") or []) if str(s).startswith("soccer")]
        if not sports:
            continue
        out.append(dict(name=name, label=meta.get("label", name), sports=sports,
                        kind=meta.get("kind", "")))
    return sorted(out, key=lambda r: r["label"])


def preflight(path=PREFLIGHT, now=None):
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


def idle_table(d, by_lane):
    lanes = idle_lanes(d)
    if not lanes:
        return '<div class="note">Every connected soccer lane has logged at least once.</div>'
    rows = []
    for r in lanes:
        sports = ", ".join(S.SPORTS.get(s, s) for s in r["sports"])
        rows.append(
            f'<tr><td>{esc(r["label"])}</td><td class="sm mut">{esc(sports)}</td>'
            f'{_state_cell(by_lane.get(r["name"], []))}</tr>')
    head = ('<tr><th>Lane</th><th>Market</th><th>Kalshi status</th></tr>')
    return f'<div class="tbl"><table>{head}{"".join(rows)}</table></div>'


def build(d=None, st=None, now=None):
    now = now or datetime.datetime.now(datetime.timezone.utc)
    d = d if d is not None else T.load()
    st = st if st is not None else T.load_stages()
    rows = soccer_rows(d, st)
    idle = idle_lanes(d)
    by_lane, pf_note = preflight(now=now)

    settled = sum(r["a"]["n"] for r in rows)
    prod = sum(1 for r in rows if r.get("prod"))
    open_bets = sum(1 for q in d.get("quotes", [])
                    if q.get("bet") and q.get("status") == "open"
                    and str(q.get("sport") or "").startswith("soccer"))
    tiles = "".join(f'<div class="tile"><b>{v:,}</b><span>{k}</span></div>' for k, v in (
        ("lanes with a record", len(rows)),
        ("settled bets", settled),
        ("bets running", open_bets),
        ("in Production", prod),
        ("registered, never fired", len(idle)),
    ))

    body = f"""<h1>Soccer</h1>
<p class="lede">Every soccer rule and tipster under test — over 1.5, both teams to score,
team totals, corners, each again for cups and internationals — plus the lanes that have
been registered and have never had a market to bet.</p>
<div class="tiles">{tiles}</div>

<section id="idle">
<h2>Registered, never fired</h2>
<div class="note">These lanes are connected and waiting, and have <b>no row in the
Sandbox</b> — it builds from the ledger, and they have never logged a quote. That is not
the rule failing. It is Kalshi not listing the market, and the status below is the
pre-flight's own verdict on each one.</div>
{pf_note}
{idle_table(d, by_lane)}
</section>

<section id="lanes">
<h2>Lanes with a record</h2>
{B.sport_sections(d, rows)}
</section>
<footer>Read-only static export · rebuilt by GitHub Actions · research, not betting advice.</footer>
"""
    return C.document(
        "Edge Machine · Soccer",
        "Every soccer rule and tipster under test, and the lanes still waiting for a market.",
        "soccer",
        (("idle", "Registered, never fired"), ("lanes", "Lanes with a record")),
        C.stamp(now),
        body,
        script_src="./site.js",
        scripts=("./tables.js",),
    )


def main():
    html = build()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    tmp = OUT + ".tmp"
    with open(tmp, "w") as f:
        f.write(html)
    os.replace(tmp, OUT)
    print(f"wrote {OUT} ({len(html):,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
