#!/usr/bin/env python3
"""Offline checks for the NBA Win Margin Tracker (nba_winmargin.py) and its NBA page section."""
import datetime as dt
import re
import sys

import nba_winmargin as W
import nba_winmargin_build as B
import sandbox_audit

FAILS = []
UTC = dt.timezone.utc


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


TIP = int(dt.datetime(2026, 10, 29, 23, 0, tzinfo=UTC).timestamp())
ENTRY = TIP - 3600


def candle(end, bid, ask):
    return dict(end_period_ts=end, yes_bid=dict(close_dollars=f"{bid:.4f}"), yes_ask=dict(close_dollars=f"{ask:.4f}"))


print("buckets, bands, roles")
check("bucket from the title", [W.bucket_of(t) for t in ("Washington wins by 1-5 points", "Cleveland wins by 21+ points", "Cleveland wins by 11-20 points", "Tie")],
      ["1-5", "21+", "11-20", None])
check("entry bands", [W.band_of(a) for a in (0.05, 0.0999, 0.10, 0.1999, 0.20, 0.35, 0.36, 0.04)], ["5-10c", "5-10c", "10-20c", "10-20c", "20-35c", "20-35c", None, None])
check("roles: 55% or more favourite, under 45% underdog", [W.role_of(p) for p in (0.7, 0.55, 0.5, 0.45, 0.44)], ["favourite", "favourite", "toss-up", "toss-up", "underdog"])
check("tip: a game's night is the ET date of the tip", W.night_of(TIP), "2026-10-29")

print("\nthe entry quote: the last 1-minute candle at the entry hour")
cs = [candle(ENTRY - 600, 0.06, 0.09), candle(ENTRY, 0.07, 0.10), candle(ENTRY + 60, 0.08, 0.11), candle(ENTRY + 120, 0.5, 0.9)]
check("the candle ending at the entry hour (a minute of slack), never a later one", W.entry_quote(cs, ENTRY), (0.08, 0.11))
check("no quote that early is no entry", W.entry_quote([candle(ENTRY + 600, 0.1, 0.2)], ENTRY), None)
check("a candle with no ask is skipped", W.entry_quote([candle(ENTRY, 0.07, 0.10), dict(end_period_ts=ENTRY + 30, yes_bid=dict(close_dollars="0.0800"))], ENTRY), (0.07, 0.10))

print("\nper-contract metrics from trade prints")
a = 0.10
P = [(ENTRY + 60, 0.30, 99.0),            # before the tip: a pre-game spike does not count as reaching
     (TIP + 600, 0.12, 5.0),
     (TIP + 1200, 0.20, 40.0),            # first at 2x: 20 minutes in
     (TIP + 1800, 0.35, 15.0),            # 3.5x
     (TIP + 2400, 0.15, 7.0),             # falls back below 2x
     (TIP + 3000, 0.25, 11.0)]            # back above, the last print
m = W.metrics(P, TIP, a)
check("peak over the prints from the entry hour", m["peak"], 3.5)
check("reached 2x and 3x, not 5x (a 50c target is reachable and was not hit)", (m["reach2"], m["reach3"], m["reach5"]), (True, True, False))
check("first minute at 2x is minutes from the tip", (m["first2"], m["first3"], m["first5"]), (20.0, 30.0, None))
check("minutes above 2x: 10 at the 20c print, 10 at the 35c print, none at 15c, the last print holds a minute", m["above2"], 21.0)
check("contracts traded at 2x or more after the tip", m["vol2"], 40.0 + 15.0 + 11.0)
check("a pre-tip print at 3x does not make it reach: pre-tip only", W.metrics([(ENTRY + 60, 0.3, 50.0), (TIP + 600, 0.11, 5.0)], TIP, a)["reach2"], False)
check("a multiple above 99c cannot be reached (None, not false)", (W.metrics([(TIP + 60, 0.5, 5.0)], TIP, 0.25)["reach5"], W.metrics([(TIP + 60, 0.5, 5.0)], TIP, 0.25)["reach3"]), (None, False))
check("no prints after the entry hour: no metrics", W.metrics([(ENTRY - 10, 0.3, 5.0)], TIP, a), None)
check("trade rows from /markets/trades are YES prices, oldest first",
      W.yes_prints([dict(created_time="2026-10-29T23:10:00.000000Z", yes_price_dollars="0.2000", no_price_dollars="0.8000", count_fp="3.00"),
                    dict(created_time="2026-10-29T23:05:00.000000Z", yes_price_dollars="0.1000", no_price_dollars="0.9000", count_fp="1.00")]),
      [(TIP + 300, 0.1, 1.0), (TIP + 600, 0.2, 3.0)])

print("\nteam shares and spread")
sh = W.team_shares([("WAS", (0.04, 0.06)), ("WAS", (0.10, 0.12)), ("CLE", (0.28, 0.32)), ("CLE", (0.28, 0.32))])
check("each team's bucket mids over both teams'", (round(sh["WAS"], 3), round(sh["CLE"], 3)), (0.211, 0.789))
mk = [dict(ticker="S-1", yes_sub_title="Cleveland wins by over 9.5 points", floor_strike=9.5),
      dict(ticker="S-2", yes_sub_title="Cleveland wins by over 5.5 points", floor_strike=5.5)]
cc = {"S-1": [candle(ENTRY, 0.44, 0.48)], "S-2": [candle(ENTRY, 0.60, 0.64)]}
check("the spread rung nearest 50c", W.spread_of(mk, cc, ENTRY), dict(team="Cleveland", margin=9.5))

print("\ngame rows")
EV = "KXNBAWINMARGIN-26OCT29WASCLE"
mkts = [dict(ticker=EV + "-WAS1TO5", yes_sub_title="Washington wins by 1-5 points", result="no"),
        dict(ticker=EV + "-CLE1TO5", yes_sub_title="Cleveland wins by 1-5 points", result="yes"),
        dict(ticker=EV + "-CLE21PLUS", yes_sub_title="Cleveland wins by 21+ points", result="no"),
        dict(ticker=EV + "-WAS6TO10", yes_sub_title="Washington wins by 6-10 points", result="no")]
entry = {EV + "-WAS1TO5": (0.08, 0.10), EV + "-CLE1TO5": (0.28, 0.30), EV + "-CLE21PLUS": (0.02, 0.03), EV + "-WAS6TO10": (0.20, 0.30)}
trades = {EV + "-WAS1TO5": [(TIP + 600, 0.25, 30.0)], EV + "-CLE1TO5": [(TIP + 900, 0.31, 4.0)]}
NOW = dt.datetime(2026, 10, 30, 12, 0, tzinfo=UTC)
rows = {r["id"].split("-")[-1]: r for r in W.game_rows(EV, mkts, TIP, entry, trades, None, NOW)}
check("a row per quoted contract", sorted(rows), ["CLE1TO5", "CLE21PLUS", "WAS1TO5", "WAS6TO10"])
w = rows["WAS1TO5"]
check("away and home from the code (AWAYHOME): WAS away, CLE home", (w["side"], rows["CLE1TO5"]["side"]), ("away", "home"))
check("bucket, ask, spread, band, eligible, result", (w["bucket"], w["ask"], w["spread"], w["band"], w["eligible"], w["won"]), ("1-5", 0.10, 0.02, "10-20c", True, False))
check("the 3c contract is not eligible (ask under 5c) and carries no metrics; the 10c spread contract is not either (spread over 5c)",
      (rows["CLE21PLUS"]["eligible"], rows["CLE21PLUS"]["m"], rows["WAS6TO10"]["eligible"]), (False, None, False))
check("the team's pregame share and role from the bucket mids", (w["team_share"], w["role"], rows["CLE1TO5"]["role"]), (0.5191, "toss-up", "toss-up"))
check("metrics are filled from the prints: the 25c print is 2.5x", (w["m"]["reach2"], w["m"]["reach3"], w["m"]["peak"]), (True, False, 2.5))
check("rows are stamped", (w["version"], w["logged"]), (W.VERSION, NOW.isoformat()))
check("the path keeps the prints relative to the tip, in cents", w["path"], [[600, 25, 30]])

print("\nrunning against a fake Kalshi")
EVT = "KXNBAWINMARGIN-26OCT29WASCLE"
SUF = "26OCT29WASCLE"
cand = {t: [candle(ENTRY, *q)] for t, q in entry.items()}


def fetch(path):
    if path.startswith("events?series_ticker=KXNBAWINMARGIN"):
        return {"events": [dict(event_ticker=EVT), dict(event_ticker="KXNBAWINMARGIN-26OCT29AAABBB")], "cursor": None}
    if path.startswith("markets?limit=200&event_ticker=" + EVT):
        return {"markets": mkts, "cursor": None}
    if path.startswith("markets?limit=200&event_ticker=KXNBAWINMARGIN-26OCT29AAABBB"):
        return {"markets": [dict(mkts[0], result="")], "cursor": None}
    if path.startswith("markets?limit=5&event_ticker=KXNBAGAME-" + SUF):
        return {"markets": [dict(expected_expiration_time=dt.datetime.fromtimestamp(TIP + 3 * 3600, UTC).strftime("%Y-%m-%dT%H:%M:%SZ"))], "cursor": None}
    if path.startswith("series/KXNBAWINMARGIN/events/" + EVT):
        return {"market_tickers": list(cand), "market_candlesticks": list(cand.values())}
    if path.startswith("markets?limit=200&event_ticker=KXNBASPREAD"):
        return {"markets": [], "cursor": None}
    if path.startswith("markets/trades?ticker="):
        t = path.split("ticker=")[1].split("&")[0]
        return {"trades": [dict(created_time=dt.datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%dT%H:%M:%S.000000Z"), yes_price_dollars=f"{p:.4f}",
                                no_price_dollars=f"{1 - p:.4f}", count_fp=f"{n:.2f}") for ts, p, n in trades.get(t, [])], "cursor": None}
    raise AssertionError(path)


st = W.load("/nonexistent")
check("a fresh record begins 2026-10-20", st["since"], "2026-10-20")
W.run(st, NOW, fetch)
check("the settled game is recorded, the unsettled one waits", (len(st["seen"]), st["observations"]["waiting"], len(st["rows"])), (1, 1, 4))
check("the tip is the KXNBAGAME time minus 3 hours", st["rows"][0]["tip"], TIP)
calls = []
W.run(st, NOW + dt.timedelta(hours=1), lambda p: (calls.append(p), fetch(p))[1])
check("a second run does not read the game again", (len(st["rows"]), any("trades" in c for c in calls)), (4, False))
old = W.load("/nonexistent")
old["since"] = "2026-11-02"
W.run(old, NOW, fetch)
check("a game before the first night is not recorded", old["rows"], [])
st["rows"][0]["night"] = "2026-10-01"
st["rows"][0]["path"] = [[1, 2, 3]]
W.run(st, NOW + dt.timedelta(hours=2), fetch)
check("raw prints are kept for the last three nights only", st["rows"][0]["path"], [])
check("a game with no spread markets is still marked read for the spread line", EVT in st["spread_seen"], True)
back = W.load("/nonexistent")
back["seen"] = {EVT: "earlier"}
bcalls = []
W.run(back, NOW, lambda p: (bcalls.append(p), fetch(p))[1])
check("backfill: a game already read for the buckets is read again for the spread line only", (back["rows"], EVT in back["spread_seen"], any("trades" in c for c in bcalls)), ([], True, False))

print("\ncomeback underdog spread line")
SP = [dict(ticker="KXNBASPREAD-26OCT29WASCLE-WAS3", floor_strike=2.5, result="no"),
      dict(ticker="KXNBASPREAD-26OCT29WASCLE-WAS9", floor_strike=8.5, result="no"),
      dict(ticker="KXNBASPREAD-26OCT29WASCLE-CLE6", floor_strike=5.5, result="yes"),
      dict(ticker="KXNBASPREAD-26OCT29WASCLE-WAS15", floor_strike=14.5, result="no")]
sent = {SP[0]["ticker"]: (0.18, 0.20), SP[1]["ticker"]: (0.08, 0.10), SP[2]["ticker"]: (0.60, 0.62), SP[3]["ticker"]: (0.01, 0.03)}
spr = {SP[0]["ticker"]: [(TIP + 900, 0.45, 12.0)], SP[1]["ticker"]: [(TIP + 900, 0.15, 2.0)]}
sr = {r["id"].rsplit("-", 1)[-1]: r for r in W.spread_rows("KXNBAWINMARGIN-26OCT29WASCLE", SP, sent, {"WAS": 0.3, "CLE": 0.7}, TIP, lambda t: spr.get(t, []), NOW)}
check("only the underdog's rungs (WAS), not the favourite's", sorted(sr), ["WAS15", "WAS3", "WAS9"])
check("WAS is not a Comeback team; the line and share are kept", (sr["WAS3"]["comeback"], sr["WAS3"]["line"], sr["WAS3"]["team_share"]), (False, 2.5, 0.3))
check("the 20c rung reached 2x, the 10c rung did not, the 3c rung is not eligible", (sr["WAS3"]["m"]["reach2"], sr["WAS9"]["m"]["reach2"], sr["WAS15"]["eligible"], sr["WAS15"]["m"]), (True, False, False, None))
check("a Comeback underdog is flagged", W.spread_rows("E", [dict(ticker="KXNBASPREAD-26OCT29CLEOKC-OKC3", floor_strike=2.5, result="no")], {"KXNBASPREAD-26OCT29CLEOKC-OKC3": (0.2, 0.22)}, {"OKC": 0.4, "CLE": 0.6}, TIP, lambda t: [], NOW)[0]["comeback"], True)
check("a 50/50 game has no underdog", W.spread_rows("E", SP, sent, {"WAS": 0.5, "CLE": 0.5}, TIP, lambda t: [], NOW), [])
check("moneyline shares from the KXNBAGAME mids", W.ml_shares([dict(ticker="KXNBAGAME-26OCT29WASCLE-WAS"), dict(ticker="KXNBAGAME-26OCT29WASCLE-CLE")],
      {"KXNBAGAME-26OCT29WASCLE-WAS": [candle(ENTRY, 0.29, 0.31)], "KXNBAGAME-26OCT29WASCLE-CLE": [candle(ENTRY, 0.69, 0.71)]}, ENTRY), {"WAS": 0.3, "CLE": 0.7})
check("one side unquoted: no moneyline shares", W.ml_shares([dict(ticker="X-WAS"), dict(ticker="X-CLE")], {"X-WAS": [candle(ENTRY, 0.29, 0.31)]}, ENTRY), {})
check("by game: one game, a rung reached 2x", W.by_game(W.eligible(list(sr.values()))), (1, 1))
check("the Comeback list is the 2025-26 profile", sorted(W.COMEBACK), ["BOS", "CLE", "DEN", "HOU", "MIN", "NYK", "OKC", "SAS"])

print("\nsummaries")
mk2 = lambda ask, won, r2, first, above, vol, bucket="1-5", tip=1, **k: dict(
    ask=ask, won=won, bucket=bucket, tip=tip, id=f"{ask}{tip}{bucket}", eligible=True, role="underdog", band="5-10c",
    m=dict(reach2=r2, reach3=r2 and k.get("r3", False), reach5=None, first2=first, above2=above, vol2=vol), night="2026-10-29", team="X")
rs = [mk2(0.10, True, True, 20.0, 15.0, 50.0), mk2(0.10, False, True, 40.0, 5.0, 10.0), mk2(0.10, False, False, None, 0.0, 0.0), mk2(0.20, False, False, None, 0.0, 0.0)]
s = W.summarize(rs)
check("n, share reaching 2x, held 10+ minutes", (s["n"], s["r2"], s["held"]), (4, 0.5, 0.25))
check("medians are over the contracts that reached 2x", (s["first"], s["above"], s["vol"]), (30.0, 10.0, 30.0))
check("a 5x target of None is left out of the rate", s["r5"], None)
check("won minus ask: 1 of 4 won, average ask 12.5c", round(s["edge"], 4), round(0.25 - 0.125, 4))
check("no contracts is an empty summary", W.summarize([]), dict(n=0))
check("halves by tip time", [x["n"] for x in W.halves([mk2(0.1, True, True, 1.0, 1.0, 1.0, tip=i) for i in range(5)])], [2, 3])
check("under four contracts: no halves", W.halves(rs[:3]), (None, None))

print("\nthe NBA page section")
empty = B.section(W.load("/nonexistent"))
check("an empty record says so", ("No game has been recorded yet" in empty, 'id="tracker"' in empty), (True, True))
real = W.load("/nonexistent")
real["rows"] = list(st["rows"]) + [dict(r, id=r["id"] + str(i), tip=TIP + i, bucket=b) for i, (r, b) in enumerate(zip(W.game_rows(EV, mkts, TIP, entry, trades, None, NOW) * 3, ["6-10", "11-20", "21+", "1-5"] * 3))]
for r in real["rows"]:
    r["night"] = "2026-10-29"
real["seen"] = {EV: "x"}
html = B.section(real)
check("observation only, plainly", ("Observation only — no buying or selling rule" in html), True)
check("the comeback underdog spread line is on the section", "Comeback underdog spread line" in html, True)
check("the three tables, the halves and last night's games", all(x in html for x in ("<th>Bucket</th>", "<th>Team</th>", "<th>Entry ask</th>", "Older and newer halves", "Last night's games")), True)
check("every column the coordinator asked for", all(c in html for c in B.COLS), True)
check("the fair benchmark is stated: 50, 33 and 20%", all(x in html for x in ("about 50% of the time", "3x 33%", "5x 20%")), True)
check("last night's price path in words, no inline SVG or style (the NBA page forbids both)", ("peak " in html and " at minute " in html, "<svg" in html, "style=" in html), (True, False, False))
check("header-row tables (no thead), labelled for the phone by the page", "<thead>" not in html, True)
check("no private-system words in the copy", sandbox_audit.COPY_RE.search(html), None)
import nba_pace_build as NB
import json
if __import__("os").path.exists(NB.SRC):
    page = NB.build(json.load(open(NB.SRC)))
    ids = re.findall(r'<section id="([^"]+)"', page[page.find("<main"):])
    check("on the NBA page: the glance, the lane cards, the tracker, then Upcoming",
          [i for i in ids if i in ("glance", "cheap-side", "wm-yes", "wm-no", "ml-dog", "tracker", "matchups")],
          ["glance", "cheap-side", "wm-yes", "wm-no", "ml-dog", "tracker", "matchups"])
    check("with a nav link", 'href="#tracker"' in page, True)

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
