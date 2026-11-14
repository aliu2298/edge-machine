"""The soccer futures longshot NO watch as three rows of the Soccer page's Sandbox table (fut_ln.py): the watch (league winners) and its two baselines
(top 4, relegation), kept apart. Presentation only: nothing here grades or calls the venue. Percentages only. Next to the return it shows the capital tied
up and the annualised figure; the read is the exact binomial of the doc.
"""
import fmt
import fut_ln as F
import nl_dump_build as NB
import soccer_lanes as L

SPORT = "soccer_futures_no"
NOTE_WATCH = "A watch, not a pass: a lead from the soccer futures study. Paper only, never in Production"
NOTE_BASE = "Baseline for the watch: the same rule where the study says it loses. Paper only"
SHARED = [
    ("Rule", "On the 1st of each month, September to April, buy NO (paper) on every league-winner market whose YES bid is 3c to 15c and whose spread is 10c or less, "
             "at 1 minus the YES bid. One entry per market per season, held to settlement, with Kalshi's taker fee on the entry"),
    ("Leagues", "Premier League, La Liga, Serie A, Bundesliga, Ligue 1, Eredivisie, Primeira, Super Lig, Belgian Pro League, EFL Championship"),
    ("The lead", "Soccer futures study (Nov 14): +7.8% a bet on 24 bets in 11 league-seasons, both seasons Kalshi has, found +7.0% and later +8.5%, no longshot winning in 24 tries; "
                 "about +22% a year because the money is tied up about 4.5 months. Chance of that run if prices were fair: 0.13. Never confirmed"),
    ("The risk", "A watch, not a pass: one longshot that wins costs about 11 wins"),
    ("Baselines", "The same entries on top-4 and relegation markets, which lose in the study. Shown apart, never pooled with the watch"),
    ("Read", "Review at 10 settled entries, decide at 30, by an exact binomial and not a z score, because losses are rare: the chance of this few longshot wins or fewer "
             "if each longshot won at the probability its own YES bid priced"),
    ("Pace", "About 20 to 25 entries a season, settled a season later, so 30 settled entries take until about mid-2027. First checkpoint Dec 1 2026"),
    ("Pre-registered", "Nov 14 2026, before the first entry. Entries are never changed or dropped"),
]


def _pct(x):
    return NB._pct(x)


def _share(x):
    return "—" if x is None else f"{x * 100:.0f}c"


def _table(r, open_rows):
    heads = ("Settled", "Longshot wins", "Open", "Return after fees", "Days tied up", "Annualised", "Cost of an entry", "Chance at the prices paid")
    cells = (r["n"], r["longshot_wins"] if r["n"] else "—", r["open"], _pct(r["roi"]), "—" if r["avg_days"] is None else f"{r['avg_days']:.0f}", _pct(r["annualised"]),
             _share(r["avg_cost"]), "—" if r["p_exact"] is None else f"{r['p_exact']:.2f}")
    return ('<div class="tbl"><table><thead><tr>' + "".join(f"<th{'' if i == 0 else ' class=\"num\"'}>{h}</th>" for i, h in enumerate(heads))
            + "</tr></thead><tbody><tr>" + "".join(f'<td class="num" data-l="{h}">{L.esc(c)}</td>' for h, c in zip(heads, cells)) + "</tr></tbody></table></div>"
            '<p class="sm mut">Days tied up: from the entry to Kalshi\'s expected settlement. Annualised: the return compounded to a year at those days. '
            'Cost of an entry: what a NO costs, so what is at risk for a payout of 100c.</p>')


def _ratio(r):
    return "—" if not r["ratio"] else f"about {r['ratio']:.0f}"


def rows(state=None):
    state = state if state is not None else F.load()
    rec = F.records(state)
    out = []
    for g, name in F.GROUPS.items():
        r = rec[g]
        es = [e for e in state["entries"].values() if e["group"] == g]
        label = f"Futures longshot NO · {name} · " + ("paper watch" if g == "winner" else "baseline")
        picks = [dict(status=e["status"], price=e["no_price"], profit=100 * e["roi"], start=e["day"]) for e in es if e["status"] in ("won", "lost")]
        a = L.pick_record(picks)
        a["z"] = 0.0
        cols = [("Market", lambda p: f'{p["league"]} · {p["team"]}'), ("Month", lambda p: p["month"]), ("YES bid", lambda p: f'{p["yes_bid"] * 100:.0f}c'),
                ("Paid for NO", lambda p: f'{p["no_price"] * 100:.0f}c'),
                ("Result", lambda p: {"open": "open", "won": "won (longshot lost)", "lost": "lost (longshot won)"}[p["status"]]),
                ("Return", lambda p: _pct(p.get("roi")) if p["status"] != "open" else "—")]
        entries = [dict(e, start=e["day"]) for e in es]
        details = (L.params_html([("Row", name), ("Record", f"{r['entries']} entr{'y' if r['entries'] == 1 else 'ies'} over {r['leagues']} league{'s' if r['leagues'] != 1 else ''}. {r['read']}"),
                                  ("One win costs", _ratio(r) + " wins")] + SHARED) + _table(r, es))
        row = L.row(f"futures_longshot_no" + ("" if g == "winner" else f"_{g}"), SPORT, label, name, a, details, open_n=r["open"], entries=L.entries_table(entries, cols),
                    kind="Observation", note=NOTE_WATCH if g == "winner" else NOTE_BASE, anchor=f"futures-longshot-no-{g}")
        row["pin"] = True
        if g != "winner":
            row["after"] = "futures_longshot_no"
        row["own"]["entries_only"] = True
        out.append(row)
    return out
