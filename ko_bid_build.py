"""The before-kickoff dump bid as two rows of the Soccer page's Sandbox table (ko_bid.py). Presentation only: nothing here grades or replays.

Two rows, judged apart: national teams, and club leagues (never tested, forward only). Labelled as a paper watch, percentages only. The headline
column is the 25-second order delay; the 2-second column sits beside it in each row's fold.
"""
import fmt
import ko_bid as K
import nl_dump as N
import nl_dump_build as NB
import soccer_lanes as L

SPORT = "soccer_ko_bid"
NOTE = "Paper watch of one research lead: observation only, never in Production. Replayed once after each game settles."
SHARED = [
    ("Games", "Kalshi's soccer game-winner markets: home, tie and away, every leg of every game. No selection"),
    ("Rule", "From the first trade until 3 hours before the listed kickoff, every minute a bid rests 15c under the last trade, on both sides. It fills only when a trade "
             "prints strictly through it, and is sold when the price is back within 5c of where it was before the drop; what is not sold rides to the result"),
    ("Why before kickoff", "With no game on, a drop is nearly always a sweep and not news, so the price drifts back. In play a drop is half the time a goal, and the same bid loses"),
    ("Skips", "No bid when nothing traded in the last 10 minutes, when the price is over 95c, or when the bid would sit under 5c"),
    ("Order delay", "The headline column puts each order up 25 seconds after the minute starts, the speed of today's order path. The 2-second column is the comparison"),
    ("The lead", "Flash dump condition study: national-team games, 3 hours or more before kickoff, about +17% on 83 bets in 43 games, found after the tables were read. Never confirmed"),
    ("Read", "At 50 and at 100 fills a row. Keep needs a positive return after fees, a score of 2 or more clustered by game, and both halves of the record positive. "
             "Retire if under that at 100 fills. No retuning of depth, clock or exit before then"),
    ("Counts", "Only bids placed after Nov 14 2026, 12:00 UTC, on games from Nov 14"),
    ("Pre-registered", "Nov 14 2026, before the first bid it counts"),
]
FEES = {False: "No fee on a resting fill (Kalshi lists no maker fee on these series); the taker fee on a sale that crosses",
        True: "Kalshi charges a maker fee on these series: every resting fill, buy and sell, pays it; the taker fee on a sale that crosses"}


def _games(state, g):
    days = sorted({v["day"] for v in state["markets"].values() if v["group"] == g})
    return (f"{len(days)} game day{'s' if len(days) != 1 else ''} read, {fmt.when(days[0])} to {fmt.when(days[-1])}" if days else "No game read yet")


def rows(state=None):
    state = state if state is not None else K.load()
    rec = K.records(state)
    out = []
    for g, cfg in K.GROUPS.items():
        r = rec[g]
        s = r["headline"]
        label = f"Before-kickoff dump bid · {cfg['label']} · paper watch"
        cols = [("Game", lambda p: p["match"]), ("Leg", lambda p: p.get("leg") or ""), ("Side", lambda p: p["side"].upper()),
                ("Bid", lambda p: f'{p["L"] * 100:.0f}c'), ("From", lambda p: f'{p["R"] * 100:.0f}c'),
                ("Return", lambda p: NB._pct(p["roi"])), ("How", lambda p: "sold back" if p["sold"] else "held to the result")]
        picks = [dict(b[2], start=b[2]["day"]) for b in K.bets(state, g, K.HEADLINE)]
        details = (L.params_html([("Row", cfg["label"]), ("Leagues", cfg["names"]), ("Record", f"{_games(state, g)}. {r['read']}"),
                                  ("Fees", FEES[cfg["maker"]])]
                                 + ([("Status", "Never tested: forward only, judged on its own")] if g == "club" else []) + SHARED) + NB._table(r))
        a = L.inplay_record(s["n"], s["won"], s["roi"], s["t"])
        row = L.row(f"ko_bid_{g}", SPORT, label, "Match winner", a, details, open_n=0, entries=L.entries_table(picks, cols), kind="Observation",
                    note=NOTE, anchor=f"ko-bid-{g}")
        row["pin"] = True
        if g != "national":
            row["after"] = "ko_bid_national"
        row["own"]["entries_only"] = True
        out.append(row)
    return out
