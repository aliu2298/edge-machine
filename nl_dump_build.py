"""The Nations League dump bid as rows of the Soccer page's Sandbox table (nl_dump.py). Presentation only: nothing here grades or replays.

Four rows, one record each, labelled as a paper watch. Percentages only. The headline column is the 25-second order delay; the 2-second
column sits beside it in each row's fold, with the rule, the research lead and the pre-registered read.
"""
import fmt
import nl_dump as N
import soccer_lanes as L

ANCHOR = "nl-dump"
SPORT = "soccer_nl_dump"
NOTE = "Paper watch of one research lead: observation only, never in Production. Replayed once after each game settles."
SHARED = [
    ("Games", "Every UEFA Nations League game Kalshi lists a total-goals market for, every rung of the game. No selection"),
    ("Rule", "Every minute of trading a bid rests under the last trade, on both sides. It fills only when a trade prints strictly through it, "
             "and is sold when the price is back within 5c of where it was before the drop; what is not sold rides to the result"),
    ("Skips", "No bid when nothing traded in the last 10 minutes, when the price is over 95c, or when the bid would sit under 5c"),
    ("Order delay", "The headline column puts each order up 25 seconds after the minute starts, the speed of today's order path. The 2-second column is the comparison"),
    ("Fills and fees", "Fills as the research's honest rules: a buy or a sell counts only on a trade strictly through the price; the sell goes up 60 seconds after the fill. "
                       "No fee on a resting fill (Kalshi lists no maker fee on this series); the taker fee on a sale that crosses"),
    ("The lead", "Flash dump map, stage 2 report: about +12% and +10% on the later dates for the 20c bid at about 50 bets each, not significant. Found by reading the table, never confirmed"),
    ("Read", "Once at 100 fills and once at 200 in the headline column. Keep needs a positive return and a score of 2 or more, clustered by game. Otherwise it is retired"),
    ("Score", "A game is one outcome"),
    ("Pre-registered", "Nov 13 2026, before the first game it counts was played. First game day Nov 14. The next international break is in March"),
]


def _pct(x, digits=1):
    return "—" if x is None else f"{x * 100:+.{digits}f}%".replace("-", "−")


def _share(x):
    return "—" if x is None else f"{x * 100:.0f}%"


def _table(rec):
    heads = ("Column", "Fills", "Games", "Return after fees", "Score", "Came back", "Sold")
    body = ""
    for label, s in (("25 seconds (headline)", rec["headline"]), ("2 seconds", rec["compare"])):
        cells = (s["n"], s["clusters"], _pct(s["roi"]), "—" if s["t"] is None or not s["n"] else f"{s['t']:+.2f}".replace("-", "−"),
                 _share(s["back"]), _share(s["sold"]))
        body += (f'<tr><td data-l="Column">{L.esc(label)}</td>'
                 + "".join(f'<td class="num" data-l="{h}">{L.esc(c)}</td>' for h, c in zip(heads[1:], cells)) + "</tr>")
    return ('<div class="tbl"><table><thead><tr>' + "".join(f"<th{'' if i == 0 else ' class=\"num\"'}>{h}</th>" for i, h in enumerate(heads))
            + f"</tr></thead><tbody>{body}</tbody></table></div>"
            '<p class="sm mut">Came back: the share of fills where the price returned within 5c of the pre-drop price inside two minutes. '
            'Sold: the share of fills fully sold at the target.</p>')


def _games(state):
    days = sorted({v["day"] for v in state["markets"].values()})
    return (f"{len(days)} game day{'s' if len(days) != 1 else ''} read, {fmt.when(days[0])} to {fmt.when(days[-1])}" if days else "No game read yet")


def rows(state=None):
    state = state if state is not None else N.load()
    rec = N.records(state)
    out = []
    for key, cfg in N.ROWS.items():
        r = rec[key]
        s = r["headline"]
        label = f"Nations League total goals · {cfg['label']} · paper watch"
        cols = [("Game", lambda p: p["match"]), ("Rung", lambda p: p.get("line") or ""), ("Side", lambda p: p["side"].upper()),
                ("Bid", lambda p: f'{p["L"] * 100:.0f}c'), ("From", lambda p: f'{p["R"] * 100:.0f}c'),
                ("Return", lambda p: _pct(p["roi"])), ("How", lambda p: "sold back" if p["sold"] else "held to the result")]
        picks = [b[2] for b in N.bets(state, key, N.HEADLINE)]
        picks = [dict(p, start=p["day"]) for p in picks]
        details = (L.params_html([("Row", cfg["label"]), ("Record", f"{_games(state)}. {r['read']}")] + SHARED) + _table(r))
        a = L.inplay_record(s["n"], s["won"], s["roi"], s["t"])
        row = L.row(f"nl_dump_{key.lower()}", SPORT, label, "Total goals", a, details, open_n=0,
                    entries=L.entries_table(picks, cols), kind="Observation", note=NOTE, anchor=f"{ANCHOR}-{key.lower()}")
        row["pin"] = True
        if key != "D20":
            row["after"] = "nl_dump_d20"
        row["own"]["entries_only"] = True
        out.append(row)
    return out
