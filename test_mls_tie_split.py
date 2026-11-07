#!/usr/bin/env python3
"""Offline checks for mls_tie_split (2026-11-07): the ticker-to-ESPN kickoff match, the entry gates, the split sell (50+
contracts at or above the target from a minute after the entry), the fees, the hold control, the fresh record, the
in-sample replay, and the Soccer page row."""
import datetime as dt
import sys

import chaos_replay as C
import mls_tie_split as M
import sandbox_audit
import soccer_lanes as L

FAILS = []
UTC = dt.timezone.utc


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


def near(a, b):
    return abs(a - b) < 1e-4


print("kickoff from ESPN by the ticker's team codes")
board = [dict(date="2026-11-08T23:30Z", competitions=[dict(competitors=[
    dict(homeAway="home", team=dict(abbreviation="RBNY")), dict(homeAway="away", team=dict(abbreviation="DC"))])])]
check("Kalshi NYRB/DCU spell ESPN's RBNY/DC", M.espn_code(M.codes("KXMLSGAME-26NOV08NYRBDCU")), "RBNYDC")
check("the matching game's kickoff", M.kickoff_from([board], "KXMLSGAME-26NOV08NYRBDCU"),
      int(dt.datetime(2026, 11, 8, 23, 30, tzinfo=UTC).timestamp()))
check("home and away reversed is not the match", M.kickoff_from([board], "KXMLSGAME-26NOV08DCUNYRB"), None)
check("LAG is ESPN's LA, LAFC stays LAFC", (M.espn_code("LAGATX"), M.espn_code("LAFCMIN")), ("LAATX", "LAFCMIN"))

print("\nthe split sell")
T0 = 1_800_000_000
check("targets 2x and 3x, rounded up to the cent, capped at 98c",
      (M.leg_target(0.25, 2), M.leg_target(0.25, 3), M.leg_target(0.34, 3)), (0.5, 0.75, 0.98))
t = M.simulate([(T0 + 30, 0.60, 500.0), (T0 + 120, 0.50, 30.0), (T0 + 200, 0.51, 25.0)], T0, 0.25, False)
check("a print inside the first minute does not count; 50+ contracts at or above 2x sell the first half",
      ([l["sold_ts"] for l in t["legs"]]), [T0 + 200, None])
c = C.cost(0.25)
want = (0.5 * (0.5 - C.maker_fee(0.5)) + 0.5 * 0.0 - c) / c
check("ROI: the sold half at 2x less the maker fee, the unsold half settles at 0, over ask plus taker fee", near(t["roi"], want), True)
check("the hold control loses the stake on no draw", t["hold"], -1.0)
t = M.simulate([(T0 + 120, 0.40, 49.0)], T0, 0.25, True)
check("49 contracts is not a sell; both halves settle at 1 on a draw", ([l["sold_ts"] for l in t["legs"]], near(t["roi"], (1 - c) / c)), ([None, None], True))
t = M.simulate([(T0 + 100, 0.80, 60.0)], T0, 0.25, False)
check("one big print above 3x sells both halves", all(l["sold_ts"] == T0 + 100 for l in t["legs"]), True)

print("\nthe run: gates, fresh record, in-sample replay, no double read")
KICK = int(dt.datetime(2026, 11, 8, 23, 0, tzinfo=UTC).timestamp())
Q = KICK - 3600
calls = []
ASK = {"KXMLSGAME-26NOV08AAABBB": 0.26, "KXMLSGAME-26OCT10CCCDDD": 0.24, "KXMLSGAME-26NOV09EEEFFF": 0.40}


def fetch(path, *a, **k):
    calls.append(path)
    if path.startswith("events?"):
        return {"events": [{"event_ticker": e} for e in ASK], "cursor": ""}
    if "markets?limit=200&event_ticker=" in path:
        ev = path.split("event_ticker=")[1]
        return {"markets": [dict(ticker=f"{ev}-TIE", status="finalized", result="yes", title="Alpha vs Beta"),
                            dict(ticker=f"{ev}-AAA", status="finalized", result="no")], "cursor": ""}
    if "candlesticks" in path:
        ev = path.split("/events/")[1].split("/")[0]
        a = ASK[ev]
        return {"market_tickers": [f"{ev}-TIE"], "market_candlesticks": [[dict(end_period_ts=Q, yes_bid=dict(close_dollars=str(a - 0.01)),
                                                                                yes_ask=dict(close_dollars=str(a)))]]}
    if "trades" in path:
        return {"trades": [dict(created_time=dt.datetime.fromtimestamp(Q + 600, UTC).isoformat(), yes_price_dollars="0.80", count_fp="80")], "cursor": ""}
    return {}


def kick(event):
    return {"KXMLSGAME-26NOV08AAABBB": KICK, "KXMLSGAME-26OCT10CCCDDD": KICK, "KXMLSGAME-26NOV09EEEFFF": KICK}[event]


now = dt.datetime(2026, 11, 10, tzinfo=UTC)
st = M.run(M.empty(), now=now, fetch=fetch, kick_fn=kick)
check("the Nov 8 match is an entry; the Nov 9 one at 40c is skipped; October waits for --backfill",
      ([e["event"] for e in st["entries"]], st["skips"]), (["KXMLSGAME-26NOV08AAABBB"], {"KXMLSGAME-26NOV09EEEFFF": "ask 0.40 outside 1-35c"}))
e = st["entries"][0]
check("entered at the ask an hour before kickoff; both halves sold on 80 contracts at 80c", (e["ask"], e["entry_ts"], all(l["sold_ts"] for l in e["legs"])), (0.26, Q, True))
n = len(calls)
M.run(st, now=now, fetch=fetch, kick_fn=kick)
check("a second run reads no match again", [p for p in calls[n:] if not p.startswith("events?")], [])
st = M.run(st, now=now, fetch=fetch, backfill=True, kick_fn=kick)
check("--backfill replays the October match into the in-sample block, never the record",
      ([x["event"] for x in st["insample"]["entries"]], len(st["entries"])), (["KXMLSGAME-26OCT10CCCDDD"], 1))
nok = M.run(M.empty(), now=now, fetch=fetch, kick_fn=lambda ev: None)
check("no ESPN kickoff within 3 days: retried, not skipped", (nok["entries"], nok["skips"]), ([], {}))

print("\nthe summary")
s = M.summary(st["entries"])
check("one entry, sold both halves, the draw counted", (s["n"], s["won"], s["draws"], s["sold2"], s["sold3"]), (1, 1, 1, 1, 1))

print("\nthe Soccer page row")
row = L.mls_tie_row(st)
check("one Sandbox in-play row", (row["name"], row["prod"], row["meta"]["kind"]), ("mls_tie_split", False, "In-play"))
text = row["own"]["details"]
check("the fold carries entry, exit, control, record, research and the matches",
      all(x in text for x in ("Entry", "Exit", "Control", "Record", "Research", "Split ROI per entry", "Matches")), True)
check("the in-sample replay is collapsed and labelled", ("Earlier matches, replayed once" in text, "not in the record" in text), (True, True))
check("public copy: the row's words pass the copy guard", bool(sandbox_audit.COPY_RE.search(text + row["own"]["label"])), False)
check("no dollar amounts on the page words", "$" in text, False)

if FAILS:
    print(f"\nFAILED {len(FAILS)}")
    sys.exit(1)
print("ALL PASS")
