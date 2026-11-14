"""The mentions dump bid as a paper-watch section of the Culture page (mentions_dump.py). Presentation only: nothing here grades, replays or calls the venue.
Percentages only. The headline column is the 25-second order delay; the 2-second column is the comparison."""
import fmt
import mentions_dump as M
import nl_dump_build as NB
import site_chrome as C

ANCHOR = "dump-bid"
NOTE = "Paper watch of one research lead: observation only, never in Production. Replayed once after each event settles."
LEAD = ("Mentions bounce study (Nov 14): across 63 series and 623 settled events, a bid 20c under the last trade, sold back when the price is back within 5c, "
        "returned +16.6% then +12.6% after fees on the two date halves and passed its written test. 15c under was the weakest pass (+7.8%, then +3.9%). "
        "It works on both sides of a word and in every type of event. The 50c-or-less row is a lead seen after the test, so it runs as a second row and is never the headline")
SHARED = [
    ("Rule", "In every Kalshi mention event, every minute a bid rests 20c under the last trade on both sides of every word. It fills only when a trade prints strictly "
             "through it, and is sold when the price is back within 5c of where it was before the drop; what is not sold rides to the result"),
    ("Stop", "Bids stop at the first confirmed word of the event: the first trade at 97c or more in a word that last traded under 90c. The listed start is not used, "
             "since about one event in three has a word confirmed before it"),
    ("Skips", "No bid when nothing traded in the last 10 minutes, when the price is over 95c, or when the bid would sit under 5c"),
    ("Order delay", "The headline column puts each order up 25 seconds after the minute starts, the speed of today's order path. The 2-second column is the comparison"),
    ("Rows", "20c under at all prices is the tested rule and the headline. The second row bids only at 50c or less. The third bids 15c under. The control holds the "
             "first fill of each side of a word to the result"),
    ("Read", "At 100, 300 and 600 fills in the headline column, scored by event (the words of one event move together). Held if the headline row is positive with a "
             "score of 2 or more at 300 fills; retired if negative at 300. The 50c-or-less row is judged the same way and replaces the headline only if it is ahead at 600"),
    ("Counts", "Only bids placed after Nov 14 2026, 19:00 UTC. Pre-registered Nov 14 2026, before the first bid it counts"),
]


def _t(s):
    return "—" if s["t"] is None or not s["n"] else f"{s['t']:+.2f}".replace("-", "−")


def _table(rec):
    e = C.esc
    heads = ("Row", "Fills (25 s)", "Events", "Return after fees", "Score", "Return, 2 s")
    body = ""
    for k in M.ROW:
        h, c = rec[k]["headline"], rec[k]["compare"]
        cells = (h["n"], h["clusters"], NB._pct(h["roi"]), _t(h), NB._pct(c["roi"]))
        name = M.LABEL[k] + (" · headline" if k == M.HEAD_ROW else "")
        body += (f'<tr><td data-l="Row">{e(name)}</td>' + "".join(f'<td class="num" data-l="{hd}">{e(cl)}</td>' for hd, cl in zip(heads[1:], cells)) + "</tr>")
    return ('<div class="tbl"><table><thead><tr>' + "".join(f"<th{'' if i == 0 else ' class=\"num\"'}>{h}</th>" for i, h in enumerate(heads))
            + f"</tr></thead><tbody>{body}</tbody></table></div>")


def _entries(state, limit=12):
    e = C.esc
    rows = M.bets(state, M.HEAD_ROW, M.HEADLINE)
    if not rows:
        return '<p class="sm mut">No fill yet.</p>'
    rows = sorted(rows, key=lambda r: (r[2]["day"], r[2]["fill"]), reverse=True)[:limit]
    heads = ("Event", "Word", "Side", "Bid", "From", "Return", "How")
    body = ""
    for _roi, _ev, p in rows:
        cells = (p["match"], p.get("leg") or "", p["side"].upper(), f'{p["L"] * 100:.0f}c', f'{p["R"] * 100:.0f}c', NB._pct(p["roi"]),
                 "sold back" if p["sold"] else "held to the result")
        body += "<tr>" + "".join(f'<td data-l="{h}"{" class=\"num\"" if i in (3, 4, 5) else ""}>{e(c)}</td>' for i, (h, c) in enumerate(zip(heads, cells))) + "</tr>"
    return ('<div class="tbl"><table><thead><tr>' + "".join(f"<th>{h}</th>" for h in heads) + f"</tr></thead><tbody>{body}</tbody></table></div>"
            f'<p class="sm mut">The {len(rows)} newest fills of the headline row.</p>')


def section(state=None):
    state = state if state is not None else M.load()
    rec = M.records(state)
    e = C.esc
    days = rec["days"]
    span = (f"{len(days)} event day{'s' if len(days) != 1 else ''} read, {fmt.when(days[0])} to {fmt.when(days[-1])}" if days else "No event read yet")
    shared = "".join(f"<li><b>{e(k)}</b> {e(v)}</li>" for k, v in SHARED)
    head = rec[M.HEAD_ROW]
    return (f'<section id="{ANCHOR}"><h2>Mentions dump bid · paper watch</h2><p class="sm mut">{e(NOTE)}</p>'
            f'<p class="sm">{e(head["read"][0].upper() + head["read"][1:])}. {e(span)}; {rec["events"]} events read, {rec["pending"]} waiting for every word to settle.</p>'
            f'<p class="sm mut">{e(LEAD)}.</p>' + _table(rec) + _entries(state)
            + f'<details class="fold"><summary>The rule and the pre-registered read</summary><ul class="sm">{shared}</ul></details></section>')
