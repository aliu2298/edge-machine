#!/usr/bin/env python3
"""Offline checks for nhl_goal_lanes (2026-11-08): goal timing from the moneyline's own reaction, the entry 3 minutes
later, the favourite's "needs 2" puck-line rung, the thin-book filter, the quote rules, the taker depth rule and maker
variant, the fresh record (no game before registration), one read per game, and the NHL page rows."""
import datetime as dt
import sys

import chaos_replay as C
import nhl_build as NB
import nhl_goal_lanes as N
import sandbox_audit
import site_chrome

FAILS = []
UTC = dt.timezone.utc


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


def near(a, b):
    return abs(a - b) < 1e-4


print("pure pieces")
rows = [[60, 0.40, 0.42, 0, 0, 0, 0, 0], [120, None, 0.43, 0, 0, 0, 0, 0], [180, 0.50, 0.52, 0, 0, 0, 0, 0]]
check("each side carried from its last value, nothing after ts", N.series_at(rows, 150), (0.40, 0.43, 120))
check("a quote older than 3 minutes is not used", N.quote(rows, 180 + 181, None), None)
check("a quote within a minute of the close is not used", N.quote(rows, 150, 200), None)
check("a wide quote is not used", N.quote([[60, 0.40, 0.46, 0, 0, 0, 0, 0]], 60, None), None)
mid = {t: (0.60 if t < 1000 else 0.65) for t in range(0, 4000, 60)}
gs = N.time_goals([dict(wall=1000, side="home"), dict(wall=1010, side="home")], lambda t: mid.get(t - t % 60))
check("two goals cannot share one price minute: the second takes the next qualifying one", (gs[0]["tj"], gs[1]["tj"]), (1020, 1080))
gs = [dict(wall=1000, side="home", tj=1020), dict(wall=1100, side="away", tj=1140)]
check("a goal inside the 3 minutes drops the earlier moment", [ts for ts, _ in N.moments(gs)], [1320])
check("v2: an untimed goal near the entry fails the state check",
      N.valid_v2([dict(wall=1000, side="home", tj=1020), dict(wall=1400, side="away", tj=None)], 1200), False)
check("team codes: TOR2 is the home team, BOS3 the away one", (N.team_of("X-TOR2", "TOR", "BOS"), N.team_of("X-BOS3", "TOR", "BOS")),
      ("home", "away"))
t, m = N.fills(dict(ts=0, ask=0.75, bid=0.73, side="no"), [(10, 0.26, 30.0), (200, 0.25, 20.0), (400, 0.20, 99.0), (500, 0.30, 1.0)], True)
check("taker: 50 contracts at or through the NO ask within 5 minutes (a NO print = 1 - YES)", (t["filled"], t["depth"]), (True, 50.0))
c = 0.75 + 0.07 * 0.75 * 0.25
check("taker ROI held to settlement after the taker fee", near(t["roi"], (1 - c) / c), True)
check("maker: a print through the NO bid within 15 minutes fills at the bid", (m["filled"], near(m["cost"], 0.73 + 0.0175 * 0.73 * 0.27)),
      (True, True))
t, _ = N.fills(dict(ts=0, ask=0.93, bid=0.92, side="yes"), [(10, 0.93, 49.0), (20, 0.94, 500.0)], True)
check("49 contracts at the ask (a print above it is not through it) is no fill", t["filled"], False)

print("\nthe run on one synthetic game")
KO = int(dt.datetime(2026, 11, 9, 0, 0, tzinfo=UTC).timestamp())
W1, W2 = KO + 1800 + 20, KO + 2700 + 20          # a home goal, then an away goal
EV = "KXNHLGAME-26NOV08BOSTOR"
EARLY = "KXNHLGAME-26NOV08NJNYR"
SUF = EV.split("-", 1)[1]
CLOSE = KO + 3 * 3600


def mid(t):
    return 0.72 if W1 + 60 <= t < W2 + 60 else 0.60


QUOTES = {
    f"{EV}-TOR": lambda t: (mid(t) - 0.01, mid(t) + 0.01),
    f"{EV}-BOS": lambda t: (1 - mid(t) - 0.01, 1 - mid(t) + 0.01),
    f"KXNHLSPREAD-{SUF}-TOR2": lambda t: (0.25, 0.27),
    f"KXNHLTOTAL-{SUF}-3": lambda t: (0.92, 0.93),
}
MARKETS = {
    EV: [dict(ticker=f"{EV}-TOR", result="yes"), dict(ticker=f"{EV}-BOS", result="no")],
    f"KXNHLSPREAD-{SUF}": [dict(ticker=f"KXNHLSPREAD-{SUF}-TOR2", result="no", floor_strike=1.5)],
    f"KXNHLTOTAL-{SUF}": [dict(ticker=f"KXNHLTOTAL-{SUF}-3", result="yes", floor_strike=2.5)],
    EARLY: [dict(ticker=f"{EARLY}-NYR", result="yes"), dict(ticker=f"{EARLY}-NJ", result="no")],
}
calls = []


def iso(t):
    return dt.datetime.fromtimestamp(t, UTC).isoformat()


def fetch(path, *a, **k):
    calls.append(path)
    if path.startswith("events?"):
        return {"events": [{"event_ticker": EV}, {"event_ticker": EARLY}], "cursor": ""}
    if "markets?limit=200&event_ticker=" in path and "historical" not in path:
        ev = path.split("event_ticker=")[1].split("&")[0]
        return {"markets": [dict(m, status="finalized", close_time=iso(CLOSE)) for m in MARKETS.get(ev, [])], "cursor": ""}
    if "candlesticks" in path:
        ev = path.split("/events/")[1].split("/")[0]
        lo = int(path.split("start_ts=")[1].split("&")[0])
        hi = int(path.split("end_ts=")[1].split("&")[0])
        tick = [m["ticker"] for m in MARKETS[ev]]
        cs = [[dict(end_period_ts=t, yes_bid=dict(close_dollars=str(round(QUOTES[x](t)[0], 2))),
                    yes_ask=dict(close_dollars=str(round(QUOTES[x](t)[1], 2))), volume_fp="10")
               for t in range(lo - lo % 60 + 60, hi, 60)] for x in tick]
        return {"market_tickers": tick, "market_candlesticks": cs}
    if "trades?" in path:
        tk = path.split("ticker=")[1].split("&")[0]
        lo = int(path.split("min_ts=")[1].split("&")[0])
        if tk.endswith("TOR2"):
            return {"trades": [dict(created_time=iso(lo + 100), yes_price_dollars="0.26", count_fp="60"),
                               dict(created_time=iso(lo + 200), yes_price_dollars="0.30", count_fp="5")], "cursor": ""}
        return {"trades": [dict(created_time=iso(lo + 100), yes_price_dollars="0.93", count_fp="20")], "cursor": ""}
    return {}


def board(day):
    comp = lambda ab, ha, tid: dict(homeAway=ha, team=dict(abbreviation=ab, id=tid))   # noqa: E731
    return [dict(id="g1", date=iso(KO), competitions=[dict(status=dict(type=dict(completed=True)),
                                                           competitors=[comp("TOR", "home", "1"), comp("BOS", "away", "2")])]),
            dict(id="g0", date="2026-11-08T05:00Z", competitions=[dict(status=dict(type=dict(completed=True)),
                                                                       competitors=[comp("NYR", "home", "3"), comp("NJ", "away", "4")])])]


def summary(gid):
    play = lambda w, tid: dict(scoringPlay=True, period=dict(number=1), wallclock=iso(w), team=dict(id=tid))   # noqa: E731
    return {"plays": [play(W1, "1"), play(W2, "2")]}


now = dt.datetime(2026, 11, 10, tzinfo=UTC)
st = N.run(N.empty(), now=now, fetch=fetch, board_fn=board, summary_fn=summary)
check("the game is read; the one that started before registration is skipped as in-sample",
      ([g["event"] for g in st["games"]], list(st["skips"].values())),
      ([EV], ["started before the lanes were registered (in-sample, not replayed)"]))
g = st["games"][0]
check("the home favourite, a thin book, both goals price-timed", (g["fav"], g["thin"], g["goals"], g["timed"]), ("home", True, 2, 2))
pl = [e for e in g["entries"] if e["kind"] == "pl"]
check("one puck-line row: after the equaliser, the favourite's 1.5 rung needs 2, NO at 75c",
      [(e["ticker"].rsplit("-", 1)[1], e["home_goals"], e["away_goals"], e["ask"], e["side"]) for e in pl], [("TOR2", 1, 1, 0.75, "no")])
check("entered 3 minutes after the price minute of the second goal", pl[0]["ts"], (W2 + 60) - (W2 + 60) % 60 + 60 + 180)
check("the puck-line row filled on depth, won (TOR did not win by 2), and the maker variant filled",
      (pl[0]["taker"]["filled"], pl[0]["won"], pl[0]["maker"]["filled"]), (True, True, True))
ov = [e for e in g["entries"] if e["kind"] == "over"]
check("an over row at each goal moment, neither filled (20 contracts)", [(e["ask"], e["taker"]["filled"]) for e in ov], [(0.93, False)] * 2)
n = len(calls)
N.run(st, now=now, fetch=fetch, board_fn=board, summary_fn=summary)
check("a second run reads no game again", [p for p in calls[n:] if not p.startswith("events?")], [])
pend = N.run(N.empty(), now=dt.datetime(2026, 11, 9, 1, tzinfo=UTC), fetch=fetch, board_fn=lambda d: [],
             summary_fn=summary)
check("no ESPN game yet within 3 days: retried, not skipped", (pend["games"], pend["skips"]), ([], {}))

print("\nthe record")
s = N.summary(N.rows_for(st, "nhl_pl_no_goal"))
check("lane 1: one settled entry, one game, won", (s["n"], s["games"], s["won"], s["logged"]), (1, 1, 1, 1))
check("lane 1 baseline holds the same row", N.summary(N.rows_for(st, "nhl_pl_no_goal_all"))["n"], 1)
st2 = dict(st, games=[dict(g, thin=False)])
check("a deep book is out of lane 1 but in its baseline",
      (N.summary(N.rows_for(st2, "nhl_pl_no_goal"))["n"], N.summary(N.rows_for(st2, "nhl_pl_no_goal_all"))["n"]), (0, 1))
s = N.summary(N.rows_for(st, "nhl_over_goal"))
check("lane 2: two logged rows, no fill, nothing in the record", (s["n"], s["logged"]), (0, 2))
check("z clusters rows by game", N.z_by_game([(0.1, "a"), (0.1, "a"), (-0.05, "b"), (0.2, "c")]) is not None, True)
check("reads: early, review, lane 1 waits for 60 games",
      (N.read_of(3, 3, "nhl_pl_no_goal")[:9], N.read_of(12, 9, "nhl_over_goal")[:6], "60 games" in N.read_of(31, 25, "nhl_pl_no_goal")),
      ("too early", "review", True))

print("\nthe NHL page")
check("the NHL pill sits in the nav after NFL", [k for k, _, _ in site_chrome.PAGES][4:6], ["nfl", "nhl"])
html = NB.build(state=st, d={}, st={}, now=now)
check("one row per lane, two rows", html.count('<details class="sp-rule'), 2)
check("each baseline sits inside its lane's fold, not as a row", (html.count("Baseline · puck line NO"), 'data-source="nhl_pl_no_goal_all"' in html),
      (1, False))
check("the folds carry entry, games, moment, fill, record, research, the maker variant and the entries",
      all(x in html for x in ("Entry", "Games", "Moment", "Fill", "Record", "Research", "Maker variant", "Entries")), True)
rows = [NB.template_row(st, lane) for lane in NB.HEADLINES]
words = "".join(r["own"]["details"] + r["own"]["label"] for r in rows)
check("public copy: the rows' words pass the copy guard", bool(sandbox_audit.COPY_RE.search(words)), False)
check("no dollar amounts on the page words", "$" in words, False)
check("Sandbox, not Production", [r["prod"] for r in rows], [False, False])
check("the study's verdicts sit in a closed fold", ('id="research"' in html, "Research: the Kalshi NHL markets" in html,
      bool(sandbox_audit.COPY_RE.search(NB.research_html()))), (True, True, False))
import tab_activity
check("the NHL tab follows the archive rule: active once a lane has a settled entry",
      (tab_activity.LABEL["nhl"], "nhl" in tab_activity.TABS), ("NHL", True))

if FAILS:
    print(f"\nFAILED {len(FAILS)}")
    sys.exit(1)
print("ALL PASS")
