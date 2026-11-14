"""The before-start bid as paper-watch sections of the Fights page (UFC, boxing) and the NFL page (bs_bid.py). Presentation only: nothing here grades,
replays or calls the venue. Percentages only. The headline column is the 25-second order delay; the 2-second and first-fill-only columns sit beside it.
"""
import fmt
import bs_bid as B
import nl_dump_build as NB
import site_chrome as C

NOTE = "Paper watch of one research lead: observation only, never in Production. Replayed once after each event settles."
SHARED = [
    ("Rule", "From the first trade until the cutoff, every minute a bid rests 15c under the last trade, on both sides of the market. It fills only when a trade prints "
             "strictly through it, and is sold when the price is back within 5c of where it was before the drop; what is not sold rides to the result"),
    ("Start", "Kalshi's own schedule for the event, not the market's expected expiry. Fights: bids stop 12 hours before it. NFL: 3 hours before it"),
    ("Why before the start", "With nothing on, no news arrives, so a drop is nearly always a sweep and the price drifts back. A wide, thin book lets a bid inside the gap get hit and a sell get lifted"),
    ("Skips", "No bid when nothing traded in the last 10 minutes, when the price is over 95c, or when the bid would sit under 5c"),
    ("Order delay", "The headline column puts each order up 25 seconds after the minute starts, the speed of today's order path. The 2-second column is the comparison"),
    ("First fills", "Many fills are repeats in one market, so the first-fill-only column counts the first fill of each fight or game and nothing else. The keep rule uses it"),
    ("Counts", "Only bids placed after Nov 14 2026, 12:00 UTC, on events from Nov 14"),
    ("Pre-registered", "Nov 14 2026, before the first bid it counts"),
]
LEAD = {
    "ufc": "Before-start study (Nov 14): fights, +16.8% on 36 bets on the found dates and +17.4% on 160 bets (t 4.3) on the later dates, mostly boxing on the later dates. It passed its written test",
    "boxing": "Before-start study (Nov 14): fights, +16.8% on 36 bets on the found dates and +17.4% on 160 bets (t 4.3) on the later dates, mostly boxing on the later dates. It passed its written test",
    "nfl": "Before-start study (Nov 14): about +14.7% on 47 bets over both halves; it fell just short on the found dates (+15.4% on 19 bets, t 1.4). A watch, not a pass",
}
FEES = {False: "No fee on a resting fill (Kalshi lists no maker fee on this series); the taker fee on a sale that crosses",
        True: "Kalshi charges a maker fee on this series: every resting fill, buy and sell, pays it; the taker fee on a sale that crosses"}


def _pct(x):
    return NB._pct(x)


def _t(s):
    return "—" if s["t"] is None or not s["n"] else f"{s['t']:+.2f}".replace("-", "−")


def _table(r):
    e = C.esc
    heads = ("Column", "Fills", "Events", "Return after fees", "Score")
    body = ""
    for label, s in (("25 seconds (headline)", r["headline"]), ("2 seconds", r["compare"]), ("First fill of each event only", r["first"])):
        cells = (s["n"], s["clusters"], _pct(s["roi"]), _t(s))
        body += (f'<tr><td data-l="Column">{e(label)}</td>' + "".join(f'<td class="num" data-l="{h}">{e(c)}</td>' for h, c in zip(heads[1:], cells)) + "</tr>")
    return ('<div class="tbl"><table><thead><tr>' + "".join(f"<th{'' if i == 0 else ' class=\"num\"'}>{h}</th>" for i, h in enumerate(heads))
            + f"</tr></thead><tbody>{body}</tbody></table></div>")


def _entries(state, g, limit=12):
    e = C.esc
    rows = B.bets(state, g, B.HEADLINE)
    if not rows:
        return '<p class="sm mut">No fill yet.</p>'
    rows = sorted(rows, key=lambda r: (r[2]["day"], r[2]["fill"]), reverse=True)[:limit]
    heads = ("Event", "Side", "Bid", "From", "Return", "How")
    body = ""
    for _roi, _ev, p in rows:
        cells = (f'{p["match"]} · {p.get("leg") or ""}'.strip(" ·"), p["side"].upper(), f'{p["L"] * 100:.0f}c', f'{p["R"] * 100:.0f}c', _pct(p["roi"]),
                 "sold back" if p["sold"] else "held to the result")
        body += "<tr>" + "".join(f'<td data-l="{h}"{"" if i in (0, 1, 5) else " class=\"num\""}>{e(c)}</td>' for i, (h, c) in enumerate(zip(heads, cells))) + "</tr>"
    return ('<div class="tbl"><table><thead><tr>' + "".join(f"<th>{h}</th>" for h in heads) + f"</tr></thead><tbody>{body}</tbody></table></div>"
            f'<p class="sm mut">The {len(rows)} newest fills of the headline column.</p>')


def _days(state, g):
    days = sorted({v["day"] for v in state["markets"].values() if v["group"] == g})
    return f"{len(days)} event day{'s' if len(days) != 1 else ''} read, {fmt.when(days[0])} to {fmt.when(days[-1])}" if days else "No event read yet"


def section(groups, state=None, anchor="bs-bid", title="Before-start bid · paper watch"):
    """One <section> for the given groups: the rule once, then a record table per row."""
    state = state if state is not None else B.load()
    rec = B.records(state)
    e = C.esc
    shared = "".join(f"<li><b>{e(k)}</b> {e(v)}</li>" for k, v in SHARED)
    rowsh = ""
    for g in groups:
        cfg, r = B.GROUPS[g], rec[g]
        rowsh += (f'<h3 id="{anchor}-{g}">{e(cfg["label"])} · {e(cfg["watch"])}</h3>'
                  f'<p class="sm">{e(r["read"][0].upper() + r["read"][1:])}. {e(_days(state, g))}.</p>'
                  f'<p class="sm mut">{e(LEAD[g])}. {e(FEES[cfg["maker"]])}.</p>' + _table(r) + _entries(state, g))
    return (f'<section id="{anchor}"><h2>{e(title)}</h2><p class="sm mut">{e(NOTE)}</p>{rowsh}'
            f'<details class="fold"><summary>The rule and the pre-registered read</summary><ul class="sm">{shared}'
            f'<li><b>Read</b> At 50 and at 100 fills a row. Keep needs a positive return after fees, a score of 2 or more clustered by card day (game day), and the row still '
            f'positive counting only the first fill of each event. Retire if under that at 100 fills. No retuning of depth, clock or exit before then</li></ul></details></section>')


def place(html, sec, before):
    """Put the section just before the marker; at the end of the body if the marker is not on the page."""
    return html.replace(before, sec + before, 1) if before in html else html.replace("</main>", sec + "</main>", 1)
