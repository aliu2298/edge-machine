"""The attendance and performers dump bid as a paper-watch section of the Culture page (attendance_dump.py). Presentation only: nothing here grades, replays or calls
the venue. Percentages only. The headline column is the 25-second order delay; the 2-second column is the comparison."""
import attendance_dump as A
import fmt
import nl_dump_build as NB
import site_chrome as C

ANCHOR = "attendance-dump"
NOTE = "Paper watch of one research lead: observation only, never in Production. Replayed once after each event settles. Expect few fills before February."
LEAD = ("Attendance and performers confirm test (Nov 15): on 50 events read once, a bid 20c under the last trade, sold 15c above the bid, returned +28.3% on who "
        "attends and +25.5% on performers after fees, and passed its written test in all four cells. It confirms on other events of the same months, not on a later "
        "season. Events with fewer than 20 fills lost, and the 50c-or-less and 20-fill rows are leads seen after the test, so they run as extra rows and are never the headline")
SHARED = [
    ("Pre-registered", A.PREREG),
    ("Rule", "In every item of the 54 fixed attendance and performer series (who attends, guests, performers, setlists, features, ads; one-winner markets are out), "
             "every minute a bid rests 20c under the last trade on both sides. It fills only when a trade prints strictly through it, and is sold 15c above the bid "
             "(5c under the price before the drop); what is not sold rides to the result"),
    ("Clock", "Each item is bid from its open until that item is confirmed: its first trade at 97c or more after last trading under 90c. Not the event's first "
              "confirmation, and not the listed start. This is the one change from the mentions dump bid"),
    ("Skips", "No bid when nothing traded in the last 10 minutes, when the last trade is over 95c, or when the bid would sit under 5c"),
    ("Order delay", "The headline column puts each order up 25 seconds after the minute starts. The 2-second column is the comparison"),
    ("Rows", "20c under at all prices is the tested rule and the headline, shown for each group. The others: 15c under; 20c under with bids of 50c or less; the "
             "headline row on events that already have 20 fills; and a control that holds the first fill of each side of an item to the result"),
    ("Counts", "Only events that opened after Nov 15 2026, 12:00 UTC. Pre-registered Nov 15 2026, before the first bid it counts"),
]


def _t(s):
    return "—" if s["t"] is None or not s["n"] else f"{s['t']:+.2f}".replace("-", "−")


def _table(rec):
    e = C.esc
    heads = ("Row", "Fills (25 s)", "Events", "Return after fees", "Score", "Return, 2 s")
    body = ""
    items = [(k, A.LABEL[k] + (" · headline" if k == A.HEAD_ROW else ""), rec[k]) for k in A.LABEL] + [
        ("g" + str(i), "Headline row, " + g, dict(headline=s, compare=dict(roi=None))) for i, (g, s) in enumerate(rec["groups"].items())]
    for k, name, r in items:
        h, c = r["headline"], r["compare"]
        cells = (h["n"], h["clusters"], NB._pct(h["roi"]), _t(h), NB._pct(c["roi"]))
        body += (f'<tr><td data-l="Row">{e(name)}</td>' + "".join(f'<td class="num" data-l="{hd}">{e(cl)}</td>' for hd, cl in zip(heads[1:], cells)) + "</tr>")
    return ('<div class="tbl"><table><thead><tr>' + "".join(f"<th{'' if i == 0 else ' class=\"num\"'}>{h}</th>" for i, h in enumerate(heads))
            + f"</tr></thead><tbody>{body}</tbody></table></div>")


def _entries(state, limit=12):
    e = C.esc
    rows = A.bets(state, A.HEAD_ROW, A.HEADLINE)
    if not rows:
        return '<p class="sm mut">No fill yet.</p>'
    rows = sorted(rows, key=lambda r: (r[2]["day"], r[2]["fill"]), reverse=True)[:limit]
    heads = ("Event", "Item", "Side", "Bid", "From", "Return", "How")
    body = ""
    for _roi, _ev, p in rows:
        cells = (p["match"], p.get("leg") or "", p["side"].upper(), f'{p["L"] * 100:.0f}c', f'{p["R"] * 100:.0f}c', NB._pct(p["roi"]),
                 "sold back" if p["sold"] else "held to the result")
        body += "<tr>" + "".join(f'<td data-l="{h}"{" class=\"num\"" if i in (3, 4, 5) else ""}>{e(c)}</td>' for i, (h, c) in enumerate(zip(heads, cells))) + "</tr>"
    return ('<div class="tbl"><table><thead><tr>' + "".join(f"<th>{h}</th>" for h in heads) + f"</tr></thead><tbody>{body}</tbody></table></div>"
            f'<p class="sm mut">The {len(rows)} newest fills of the headline row.</p>')


def section(state=None):
    state = state if state is not None else A.load()
    rec = A.records(state)
    e = C.esc
    days = rec["days"]
    span = (f"{len(days)} event day{'s' if len(days) != 1 else ''} read, {fmt.when(days[0])} to {fmt.when(days[-1])}" if days else "No event read yet")
    shared = "".join(f"<li><b>{e(k)}</b> {e(v)}</li>" for k, v in SHARED)
    head = rec[A.HEAD_ROW]
    return (f'<section id="{ANCHOR}"><h2>Attendance and performers dump bid · paper watch</h2><p class="sm mut">{e(NOTE)}</p>'
            f'<p class="sm">{e(head["read"][0].upper() + head["read"][1:])}. {e(span)}; {rec["events"]} events read, {rec["pending"]} waiting for every item to settle.</p>'
            f'<p class="sm mut">{e(LEAD)}.</p>' + _table(rec) + _entries(state)
            + f'<details class="fold"><summary>The rule and the pre-registered read</summary><ul class="sm">{shared}</ul></details></section>')
