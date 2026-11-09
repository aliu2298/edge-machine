#!/usr/bin/env python3
"""scripts/spotlag_recorder.py (2026-11-09): public endpoints only, one book row a coin a second, each window's prints
read once and de-duplicated, the stop date. No network."""
import gzip
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts"))
import spotlag_recorder as R  # noqa: E402

FAILS = []


def check(why, got, want):
    good = got == want
    print(f"  {'ok  ' if good else 'FAIL'} {why}" + ("" if good else f" — got {got!r}, want {want!r}"))
    if not good:
        FAILS.append(why)


src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts", "spotlag_recorder.py")).read()
check("public data only: no order, portfolio, auth header or key", [w for w in ("/portfolio", "/orders", "KALSHI-ACCESS",
      "POST", "api_key", "Authorization") if w in src], [])
check("standard library only", [l for l in src.splitlines() if l.startswith(("import ", "from "))
                                and l.split()[1].split(".")[0] not in ("argparse", "datetime", "gzip", "json", "os", "sys",
                                                                         "threading", "time", "urllib", "zlib")], [])

T0 = 1794240000.0                       # 2026-11-09 16:00:00Z, a window boundary
iso = lambda t: R.dt.datetime.fromtimestamp(t, R.dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
now = [T0 - 10]
calls = []


def get(url):
    calls.append(url)
    if "coinbase" in url:
        return {"price": "100.5", "bid": "100.4", "ask": "100.6", "time": iso(now[0] - 0.4), "trade_id": 7}
    path = url.split("/v2", 1)[1]
    if path.startswith("/markets?") and "series_ticker" in path:
        s = path.split("series_ticker=")[1].split("&")[0]
        # Kalshi still lists the window that just closed as open: the recorder must skip it.
        return {"markets": [dict(ticker=f"{s}-OLD", open_time=iso(T0 - 900), close_time=iso(T0)),
                            dict(ticker=f"{s}-NEW", open_time=iso(T0), close_time=iso(T0 + 900), floor_strike=1.0)]
                if now[0] >= T0 else
                [dict(ticker=f"{s}-OLD", open_time=iso(T0 - 900), close_time=iso(T0), floor_strike=1.0)]}
    if path.startswith("/markets?tickers="):
        tks = R.urllib.parse.unquote(path.split("tickers=")[1].split("&")[0]).split(",")
        return {"markets": [dict(ticker=t, yes_bid_dollars="0.40", yes_ask_dollars="0.42", last_price_dollars="0.41",
                                 volume_fp="10") for t in tks]}
    if path.startswith("/markets/trades?"):
        cur = "cursor=" in path
        tr = [dict(trade_id="a", created_time=iso(T0 - 5), yes_price_dollars="0.4", count_fp="3", taker_side="yes"),
              dict(trade_id="b", created_time=iso(T0 - 4), yes_price_dollars="0.5", count_fp="1", taker_side="no")]
        return {"trades": tr, "cursor": None if cur else "c2"}       # page 2 repeats page 1: de-duplicated
    raise AssertionError(url)


with tempfile.TemporaryDirectory() as out:
    r = R.Recorder(out, until=T0 + 3600, get=get, clock=lambda: now[0], sleep=lambda s: None)
    r.bucket = type("B", (), {"take": lambda self: None})()
    r.background = r.bucket
    for c in R.COINS:
        r.spot_once(c)
    r.discover_missing()
    r.book_once()
    check("before the boundary: one book row a coin, on the OLD market", sorted(m["ticker"] for m in r.markets.values()),
          ["KXBTC15M-OLD", "KXETH15M-OLD", "KXSOL15M-OLD"])
    now[0] = T0 + 1
    r.book_once()
    check("at the close the book thread drops the closed market and never looks up the next one itself",
          r.markets, {})
    r.discover_missing()
    r.book_once()
    check("after the close: the NEW market, never the closed one Kalshi still lists",
          sorted(m["ticker"] for m in r.markets.values()), ["KXBTC15M-NEW", "KXETH15M-NEW", "KXSOL15M-NEW"])
    check("each closed window is queued for its prints exactly once", sorted(p[2] for p in r.pending),
          ["KXBTC15M-OLD", "KXETH15M-OLD", "KXSOL15M-OLD"])
    now[0] = T0 + 29
    r.trades_due()
    check("prints are read 30s after the close, not before", len(r.pending), 3)
    now[0] = T0 + 31
    r.trades_due()
    check("then read and the queue emptied", len(r.pending), 0)
    r.store.flush()
    r.store.close()
    day = os.listdir(out)[0]
    rows = [json.loads(l) for l in gzip.open(os.path.join(out, day, "BTC.jsonl.gz"))]
    kinds = [x["k"] for x in rows]
    check("BTC file: 1 spot, 2 book (none in the close second), 2 prints de-duplicated across pages, 1 window row",
          {k: kinds.count(k) for k in set(kinds)}, {"spot": 1, "book": 2, "trade": 2, "window": 1})
    sp = rows[0]
    check("a spot row: price, bid, ask, the print time and the request round trip",
          (sp["p"], sp["b"], sp["a"], sp["pt"]), (100.5, 100.4, 100.6, int((T0 - 10.4) // 1 * 1000)))
    tr = [x["r"] for x in rows if x["k"] == "trade"]
    check("a print row is [time ms, YES price, contracts, taker side]", tr[0], [int((T0 - 5) * 1000), 0.4, 3.0, "y"])
    check("the window row counts its prints", [x for x in rows if x["k"] == "window"][0]["trades"], 2)
    check("Kalshi traffic: the book is one request for all three coins",
          sum("tickers=" in u for u in calls), 2)
    r2 = R.Recorder(out, until=T0, get=get, clock=lambda: T0 + 5, sleep=lambda s: None)
    check("started after --until: exits 0 at once and records nothing", r2.run(), 0)

unit = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "deploy", "spotlag-recorder.service")).read()
check("the unit: capped, restarts only on failure, its own interpreter, not the trading engine venv",
      all(x in unit for x in ("MemoryMax=120M", "CPUQuota=20%", "Restart=on-failure", "ExecStart=/usr/bin/python3 ", "--until"))
      and "polymarket" not in unit.split("[Service]")[1], True)

check("Kalshi budget: book + background stay under 2 requests a second", R.BOOK_RPS + R.BACKGROUND_RPS < 2, True)
b = R.Bucket(0.7)
t = R.time.monotonic()
b.take()
b.take()
check("a bucket under 1 a second still serves requests (it once never did): 2 takes in ~1.4s",
      1.0 < R.time.monotonic() - t < 2.5, True)
print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
