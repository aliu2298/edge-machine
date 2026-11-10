#!/usr/bin/env python3
"""15-Minute Swing (swing15.py, sw15-v1): honest fills on a fake Kalshi, the ledger shards, the page. No network."""
import datetime as dt
import json
import os
import re
import sys
import tempfile
import urllib.parse

import sandbox_audit
import swing15 as W
import swing15_build as WB

FAILS = []


def check(why, got, want):
    good = got == want
    print(f"  {'ok  ' if good else 'FAIL'} {why}" + ("" if good else f" — got {got!r}, want {want!r}"))
    if not good:
        FAILS.append(why)


OPEN = int(dt.datetime(2026, 11, 9, 15, 0, tzinfo=dt.timezone.utc).timestamp())      # 10:00 ET Monday
ISO = lambda ts: dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def candle(k, lo, hi, bid, ask):
    return {"end_period_ts": OPEN + 60 * k, "price": {"low_dollars": lo, "high_dollars": hi},
            "yes_bid": {"close_dollars": bid}, "yes_ask": {"close_dollars": ask}}


def fake(candles, prints, series=("KXBTC15M", "Crypto"), result="yes"):
    m = dict(ticker="KXBTC15M-26NOV091015-15", open_time=ISO(OPEN), close_time=ISO(OPEN + 900), result=result)

    def get(path):
        if path.startswith("/series?"):
            return {"series": [dict(ticker=series[0], category=series[1], frequency="fifteen_min", fee_multiplier=1),
                               dict(ticker="KXKPOWMID15M", category="Elections", frequency="fifteen_min"),
                               dict(ticker="KXGBPUSD15MTEST", category="Financials", frequency="fifteen_min"),
                               dict(ticker="KXINXU", category="Financials", frequency="daily")]}
        if path.startswith("/markets?"):
            return {"markets": [m]}
        if "/candlesticks?" in path:
            return {"candlesticks": candles}
        if path.startswith("/markets/trades?"):
            q = dict(urllib.parse.parse_qsl(path.split("?", 1)[1]))
            a, b = int(q["min_ts"]), int(q["max_ts"])
            return {"trades": [dict(created_time=ISO(ts) if float(ts).is_integer() else
                                    dt.datetime.fromtimestamp(ts, dt.timezone.utc).isoformat(),
                                    yes_price_dollars=f"{p:.4f}", count_fp=f"{n:.2f}")
                               for ts, p, n in prints if a <= ts < b][::-1]}
        raise AssertionError(path)
    return m, get


print("scope")
_m, g = fake([], [])
check("only fifteen_min series in Crypto, Commodities, Financials; the Elections and TEST series left out",
      W.discover(g), [("KXBTC15M", "Crypto", 1.0)])
check("ids and version", (tuple(W.STRATS), W.VERSION), (("swing15_s1", "swing15_s2", "swing15_s3"), "sw15-v1"))
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "swing15.py")).read()
check("public data only: no order, auth or key", [w for w in ("/portfolio", "/orders", "KALSHI-ACCESS", "POST", "api_key") if w in src], [])

print("\nS1: entry at the band on whichever side prints there first in the first 5 minutes")
cs = [candle(1, .45, .55, .49, .51), candle(2, .20, .55, .24, .26), candle(3, .20, .40, .30, .32),
      candle(4, .30, .55, .50, .52), candle(5, .40, .60, .55, .57)]
cs += [candle(k, .40, .62, .55, .57) for k in range(6, 15)] + [candle(14, .40, .62, .58, .60), candle(15, .5, .9, .8, .9)]
pr = [(OPEN + 70, .50, 10), (OPEN + 75, .24, 5),              # minute 2: YES prints 24c, under 25c: the 25c band enters YES
      (OPEN + 100, .40, 30), (OPEN + 130, .52, 30),           # 2x of 25c is 50c: 30 contracts at 52c within 60s do NOT count
      (OPEN + 200, .51, 20), (OPEN + 210, .55, 25),           # after 60s: 20 + 25 = 45 at or above 50c: still short of 50
      (OPEN + 220, .40, 10)]                                  # 40c: not 2x, but the 1.5x target (37.5c) reaches 55
m, g = fake(cs, pr)
r = W.grade("KXBTC15M", "Crypto", 1.0, m, get=g)
e = r["s1"]["0.25"]
check("the 25c band enters YES (a 24c print, filled at the band)", (e["side"], e["won"]), ("yes", 1.0))
check("15c never printed in the first 5 minutes: no entry", r["s1"]["0.15"], None)
x = e["exits"]["2.0"]
cost = .25 + W.fee(.25, W.TAKER)
check("2x needs 50 contracts at or above 50c printed 60s+ after entry: 45 is not a fill",
      (x["filled"], x["roi_hold"]), (False, round(1 / cost - 1, 4)))
check("unfilled, also sold at the bid with 1 minute left (minute 14's bid, taker fee)",
      x["roi_bid"], round((.58 - W.fee(.58, W.TAKER)) / cost - 1, 4))
x15 = e["exits"]["1.5"]
check("1.5x (37.5c) fills on the 50th contract at or above it 60s+ after entry, at the target less the maker fee",
      (x15["filled"], x15["roi_hold"]), (True, round((.375 - W.fee(.375, W.MAKER)) / cost - 1, 4)))
check("the 35c band entered on the same 24c print", r["s1"]["0.35"]["side"], "yes")

print("\nS1 on the NO side")
cs2 = [candle(1, .45, .55, .49, .51), candle(2, .45, .80, .78, .80)] + [candle(k, .45, .60, .55, .57) for k in range(3, 16)]
pr2 = [(OPEN + 80, .79, 3)]                                     # YES 79c = NO 21c: the 25c band enters NO
m2, g2 = fake(cs2, pr2, result="no")
r2 = W.grade("KXBTC15M", "Crypto", 1.0, m2, get=g2)
check("a YES print at 79c is a NO print at 21c: the 25c band enters NO, and wins on a NO result",
      (r2["s1"]["0.25"]["side"], r2["s1"]["0.25"]["won"]), ("no", 1.0))
check("NO's bid with a minute left is 1 − the YES ask", r2["s1"]["0.25"]["bid14"], round(1 - .57, 4))

print("\nS2 and S3: the favourite at minute 2 and minute 10, at its ask, filled on a print at or through it")
check("S2: minute 2 mid 25c → NO favourite at 1 − bid = 76c; minute 3 prints YES 20c (≤ the 24c bid): filled; YES won → lost",
      {k: r["s2"][k] for k in ("status", "side", "price", "won")}, dict(status="filled", side="no", price=.76, won=0.0))
check("S3: minute 10 mid 56c → YES at the 57c ask; minute 11 low 40c: filled and won",
      (r["s3"]["status"], r["s3"]["side"], r["s3"]["price"], r["s3"]["roi"]), ("filled", "yes", .57, round(1 / (.57 + W.fee(.57, W.TAKER)) - 1, 4)))
cs3 = [dict(c) for c in cs]
cs3[10] = candle(11, .60, .62, .55, .57)
m3, g3 = fake(cs3, pr)
check("no print at or through the ask in the next minute: no fill", W.grade("KXBTC15M", "Crypto", 1.0, m3, get=g3)["s3"]["status"], "no_fill")

print("\nschema 2: every graded row keeps enough to re-analyse it (2026-11-09)")
check("the schema and the minute table: 15 rows, minute 0..14, one column per MINUTE_COLS",
      (r["schema"], len(r["minutes"]), r["minutes"][0][0], r["minutes"][-1][0], len(r["minutes"][0]), r["minute_cols"][:5]),
      (2, 15, 0, 14, len(W.MINUTE_COLS), ["m", "yes_bid", "yes_ask", "no_bid", "no_ask"]))
check("minute 1's row: YES bid/ask, NO bid = 1 − YES ask, the traded range and last",
      r["minutes"][1][1:8], [.24, .26, .74, .76, .20, .55, None])
check("the market block has numeric volume, open interest and the result at settlement",
      {k: r["market"].get(k) for k in ("volume", "open_interest", "result")}, dict(volume=None, open_interest=None, result="yes"))
check("the window close and the skip flags", (r["close"], r["closed_early"], r["missing_minutes"]),
      (ISO(OPEN + 900), False, []))
t = e["trigger"]
check("the S1 trigger: band, minute 1 (the second minute), the 24c print of 5 contracts",
      (t["band"], t["minute"], t["ts"], t["print_yes"], t["print_side"], t["print_contracts"]), (.25, 1, OPEN + 75, .24, .24, 5))
check("contracts at or under the band in the entry minute, from the trigger on", t["contracts_at_or_under"], 5)
check("2x: the first touch at or above 50c 60s+ after entry, 45 contracts in all, never filled",
      (x["target"], x["touch_ts"], x["fill_ts"], x["touch_contracts"]), (.5, OPEN + 200, None, 45))
check("1.5x: touched and filled, with its fill time", (x15["touch_ts"], x15["fill_ts"] is not None), (OPEN + 200, True))
check("the entry side's peak after entry", e["peak_side"], .9)
check("the skip reason for each band: 15c was never in the range (lows 20c, highs 60c)",
      (r["s1_skip"]["0.15"], r["s1_skip"]["0.25"]), ("not_reached", None))
check("S2 keeps the quote it read and the next minute's range",
      {k: r["s2"][k] for k in ("minute", "yes_bid", "yes_ask", "mid", "next_low")}, dict(minute=2, yes_bid=.24, yes_ask=.26, mid=.25, next_low=.20))
check("S3's no_fill keeps its quote too", (W.grade("KXBTC15M", "Crypto", 1.0, m3, get=g3)["s3"]["yes_ask"]), .57)
# A range that reaches 15c with no print there: no_print.
mn, gn = fake([candle(1, .10, .55, .49, .51)] + cs[1:], pr)
check("15c inside minute 0's range but never printed: no_print", W.grade("KXBTC15M", "Crypto", 1.0, mn, get=gn)["s1_skip"]["0.15"], "no_print")
mk, gk = fake([], [])
rk = W.grade("KXBTC15M", "Crypto", 1.0, dict(mk, close_time=ISO(OPEN + 600)), get=gk)
check("no candles at all: every band says no_candles, S2 no_candle, closed early and all 15 minutes missing",
      (set(rk["s1_skip"].values()), rk["s2"]["status"], rk["closed_early"], len(rk["missing_minutes"])),
      ({"no_candles"}, "no_candle", True, 15))

print("\nthe run and the ledger")
with tempfile.TemporaryDirectory() as tmp:
    path, shards = os.path.join(tmp, "swing15_ledger.json"), os.path.join(tmp, "swing15")
    st = W.load(path, shards)
    st["touched"] = []
    W.run(st, now=dt.datetime.fromtimestamp(OPEN + 3600, dt.timezone.utc), get=g, log=lambda *_: None)
    touched = st.pop("touched")
    W.save(st, path, shards, touched=touched)
    check("one window graded into its ET day and hour's shard (10:00 ET opens in hour 10)",
          (sorted(os.listdir(shards)), sorted(os.listdir(os.path.join(shards, "2026-11-09")))), (["2026-11-09"], ["10.json"]))
    st2 = W.load(path, shards)
    st2["touched"] = []
    W.run(st2, now=dt.datetime.fromtimestamp(OPEN + 3600, dt.timezone.utc), get=g, log=lambda *_: None)
    check("de-duplicated by ticker: a second run grades nothing", st2["runs"][-1]["graded"], 0)
    check("the run counts series scanned and series with windows", (st["runs"][-1]["series"], st["runs"][-1]["series_with_windows"]), (1, 1))
    check("the index holds no windows", "windows" in json.load(open(path)), False)
    st3 = W.load(path, shards)
    st3["windows"][m["ticker"]]["schema"] = 1
    st3["touched"] = []
    W.run(st3, now=dt.datetime.fromtimestamp(OPEN + 3600, dt.timezone.utc), get=g, log=lambda *_: None)
    check("a row from before schema 2 is graded again", (st3["runs"][-1]["graded"], st3["windows"][m["ticker"]]["schema"]), (1, 2))
    old = dict(m, open_time=ISO(int(W._ts(W.FROM)) - 900))
    check("a window that opened before the registration is never graded",
          W.run(W.empty(), now=dt.datetime.fromtimestamp(OPEN + 3600, dt.timezone.utc),
                get=lambda p: {"markets": [old]} if p.startswith("/markets?") else g(p), log=lambda *_: None)["runs"][-1]["graded"], 0)

print("\nthe record")
state = dict(W.empty(), windows={r["ticker"]: r, "X": dict(r2, ticker="X")}, series=[{}])
c = W.cells(state)
check("S1 25c · 2x · hold: two windows, neither filled", (c[WB.HEADLINE_S1]["n"], c[WB.HEADLINE_S1]["hits"]), (2, 0))
check("its fair touch rate is entry / target = 0.5", c[WB.HEADLINE_S1]["fair"], .5)
check("cluster z by day: two misses on one day against 0.5 each", round(c[WB.HEADLINE_S1]["z"], 3), -1.0)

print("\nthe page")
html = WB.section(state)
check("S2 and S3 rows in the Rules-list design; S1 retired (2026-11-09) but still graded underneath",
      (re.findall(r'data-source="(swing15_s\d)"', html), c[WB.HEADLINE_S1]["n"]), (["swing15_s2", "swing15_s3"], 2))
check("seven columns: the Kalshi market column is gone, vs control and Status in",
      all(h in html.split('sp-head-line')[1].split("</div>")[0]
          for h in ("vs control", "Record", "Return after fees", "Won v priced", "Evidence", "Status"))
      and ">Kalshi</span>" not in html, True)
check("too early under 10 windows a series", "Too early" in html, True)
check("the scope says scanned / with windows", "scanned 1 / with windows 1" in html, True)
check("no dollar sign, no guarded phrase", (re.search(r"\$\d", html), sandbox_audit.COPY_RE.findall(html + WB.index_html(state))), (None, []))
check("the Sandbox index rows link to the section", 'href="./daily_markets.html#swing15"' in WB.index_html(state), True)

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
