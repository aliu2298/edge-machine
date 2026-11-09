#!/usr/bin/env python3
"""Spot lag recorder (2026-11-09): RECORD ONLY. No orders, no account, no keys, nothing to do with the trading engine.

Question: do Kalshi's 15-minute crypto markets (KXBTC15M, KXETH15M, KXSOL15M) lag the real spot price by a few
seconds? A 1-minute test was suggestive but unproven ("spot moved >= 5bps, Kalshi had not followed" won ~60 v 50.5
expected, z ~1.5). This records the raw material at 1-second resolution for 5 days.

Every second, per coin (BTC, ETH, SOL):
  spot   Coinbase Exchange public REST ticker (/products/<P>-USD/ticker): last trade price, its time, best bid/ask.
  book   Kalshi public REST: the CURRENT open 15-minute market's yes_bid / yes_ask / last price (all three coins in
         one /markets?tickers= request a second).
  trades after each window closes (+30s), every trade print of that market (/markets/trades: ts, yes price, count).
Kalshi traffic is held to <= 2 requests a second in all (the book 1.2, prints and lookups 0.7, two token buckets); Coinbase gets 3 a second (one a coin).
Standard library only, a generic User-Agent, public endpoints only.

Storage: one gzip JSON-lines file per coin per UTC day, <out>/<YYYY-MM-DD>/<coin>.jsonl.gz, each line
{"k": "spot"|"book"|"trade"|"window", ...}: spot and book rows carry "t", the capture unix time in ms (the request's
midpoint) and "rtt"; a trade row is "r": [print time ms, YES price, contracts, taker side], de-duplicated by trade id;
a "window" row closes each market's prints (ticker, open, close, count). The gzip stream is sync-flushed every 60 s so a crash
loses at most a minute. One heartbeat line a minute on stdout (the journal) and in <out>/heartbeat.log.
It stops by itself: past --until it exits 0 (and exits 0 at once if started after it), so Restart=on-failure never
brings it back.
"""
import argparse
import datetime as dt
import gzip
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib

UA = "spot-lag-recorder/1.0"
COINBASE = "https://api.exchange.coinbase.com/products/{}-USD/ticker"
KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
COINS = {"BTC": "KXBTC15M", "ETH": "KXETH15M", "SOL": "KXSOL15M"}
# Kalshi: <= 2 requests a second in all. The book gets its own 1.2 a second so the once-a-window print reads (a BTC
# window is ~35 pages) and the market lookups (0.7 a second) never starve it.
BOOK_RPS, BACKGROUND_RPS = 1.2, 0.7
TRADES_DELAY_S = 30


def _num(x):
    try:
        return None if x is None or x == "" else float(x)
    except (TypeError, ValueError):
        return None


def _ts(iso):
    return dt.datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()


def fetch(url, timeout=5):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


class Bucket:
    """A token bucket shared by every Kalshi request."""

    def __init__(self, rate):
        # Capacity at least one token: a rate under 1 a second must still be able to hold the one a request needs.
        self.rate, self.cap = rate, max(1.0, rate)
        self.tokens, self.last, self.lock = self.cap, time.monotonic(), threading.Lock()

    def take(self):
        while True:
            with self.lock:
                now = time.monotonic()
                self.tokens = min(self.cap, self.tokens + (now - self.last) * self.rate)
                self.last = now
                if self.tokens >= 1:
                    self.tokens -= 1
                    return
            time.sleep(0.05)


class Store:
    """One gzip JSON-lines file per coin per UTC day; sync-flushed every minute."""

    def __init__(self, out):
        self.out, self.files, self.lock = out, {}, threading.Lock()
        self.count = {c: {"spot": 0, "book": 0, "trade": 0, "window": 0} for c in COINS}

    def write(self, coin, row):
        day = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
        line = (json.dumps(row, separators=(",", ":")) + "\n").encode()
        with self.lock:
            key = (day, coin)
            f = self.files.get(key)
            if f is None:
                for k in [k for k in self.files if k[1] == coin]:
                    self.files.pop(k).close()            # the day rolled over: close yesterday's file
                os.makedirs(os.path.join(self.out, day), exist_ok=True)
                f = self.files[key] = gzip.open(os.path.join(self.out, day, coin + ".jsonl.gz"), "ab", compresslevel=6)
            f.write(line)
            self.count[coin][row["k"]] += 1

    def flush(self):
        with self.lock:
            for f in self.files.values():
                f.flush(zlib.Z_SYNC_FLUSH)

    def take_counts(self):
        with self.lock:
            c, self.count = self.count, {k: {"spot": 0, "book": 0, "trade": 0, "window": 0} for k in COINS}
            return c

    def close(self):
        with self.lock:
            for f in self.files.values():
                f.close()
            self.files.clear()


class Recorder:
    def __init__(self, out, until, get=fetch, clock=time.time, sleep=time.sleep):
        self.store, self.until, self.get, self.clock, self.sleep = Store(out), until, get, clock, sleep
        self.out = out
        self.bucket = Bucket(BOOK_RPS)
        self.background = Bucket(BACKGROUND_RPS)
        self.stop = threading.Event()
        self.markets = {}              # coin -> {"ticker", "close"}
        self.pending = []              # [(due, coin, ticker, open_ts, close_ts)] trades to read after a close
        self.queued = set()            # tickers whose trades are queued or read (each window read once)
        self.upcoming = {}             # coin -> [the current market, the next one] from discover()
        self.errors = {"spot": 0, "book": 0, "trade": 0, "discover": 0}
        self.lock = threading.Lock()

    # -- Kalshi
    def kget(self, path, bucket=None):
        (bucket or self.bucket).take()
        return self.get(KALSHI + path)

    def discover(self, coin):
        """The current market and the next one. Kalshi creates each 15-minute market hours ahead (status initialized)
        but lists it as open only ~30s after its window starts, so the next market is known BEFORE the close and the
        book switches to it the moment the current one closes. A market that has closed never counts."""
        now = self.clock()
        d = self.kget("/markets?" + urllib.parse.urlencode({"series_ticker": COINS[coin], "min_close_ts": int(now),
                                                            "max_close_ts": int(now) + 1800, "limit": 10}),
                      self.background)
        ms = sorted((m for m in d.get("markets") or [] if _ts(m["close_time"]) > now + 1), key=lambda m: m["close_time"])
        self.upcoming[coin] = [dict(ticker=m["ticker"], open=_ts(m["open_time"]), close=_ts(m["close_time"]),
                                    strike=m.get("floor_strike")) for m in ms[:2]]
        cur = [m for m in self.upcoming[coin] if m["open"] <= now + 1]
        if cur and coin not in self.markets:
            self.markets[coin] = cur[0]

    def book_once(self):
        now = self.clock()
        for coin in COINS:
            m = self.markets.get(coin)
            if not m or now >= m["close"]:
                if m and m["ticker"] not in self.queued:
                    self.queued.add(m["ticker"])
                    with self.lock:
                        self.pending.append((m["close"] + TRADES_DELAY_S, coin, m["ticker"], m["open"], m["close"]))
                    self.markets.pop(coin, None)
                # Switch to the next market at once, from the list discover() keeps (no lookup on this thread).
                nxt = [x for x in self.upcoming.get(coin) or [] if x["close"] > now + 1 and x["open"] <= now + 1]
                if nxt:
                    self.markets[coin] = nxt[0]
        # The next market is found by discover_loop on its own thread: right after a close Kalshi can take ~20s to
        # list it, and a lookup here would hold up the book of the other coins.
        tickers = [m["ticker"] for m in self.markets.values()]
        if not tickers:
            return
        t0 = self.clock()
        d = self.kget("/markets?" + urllib.parse.urlencode({"tickers": ",".join(tickers), "limit": len(tickers)}))
        t1 = self.clock()
        by = {m["ticker"]: m for m in d.get("markets") or []}
        for coin, mk in list(self.markets.items()):
            m = by.get(mk["ticker"])
            if not m:
                continue
            self.store.write(coin, {"k": "book", "t": round((t0 + t1) / 2 * 1000), "rtt": round((t1 - t0) * 1000),
                                    "tk": mk["ticker"], "strike": mk.get("strike"),
                                    "yb": _num(m.get("yes_bid_dollars")), "ya": _num(m.get("yes_ask_dollars")),
                                    "last": _num(m.get("last_price_dollars")), "vol": _num(m.get("volume_fp"))})

    def trades_due(self):
        now = self.clock()
        with self.lock:
            due = [p for p in self.pending if p[0] <= now]
            self.pending = [p for p in self.pending if p[0] > now]
        for _due, coin, ticker, o, c in due:
            try:
                cursor, n, seen = None, 0, set()
                for _ in range(50):
                    q = {"ticker": ticker, "min_ts": int(o), "max_ts": int(c) + 1, "limit": 1000}
                    if cursor:
                        q["cursor"] = cursor
                    d = self.kget("/markets/trades?" + urllib.parse.urlencode(q), self.background)
                    for tr in d.get("trades") or []:
                        if tr.get("trade_id") in seen:
                            continue
                        seen.add(tr.get("trade_id"))
                        # Compact (BTC prints ~24k trades a window): [time ms, YES price, contracts, taker side y/n].
                        self.store.write(coin, {"k": "trade", "r": [round(_ts(tr["created_time"]) * 1000),
                                                                     _num(tr.get("yes_price_dollars")),
                                                                     _num(tr.get("count_fp")),
                                                                     (tr.get("taker_side") or "?")[:1]]})
                        n += 1
                    cursor = d.get("cursor")
                    if not cursor or not d.get("trades"):
                        break
                self.store.write(coin, {"k": "window", "t": round(self.clock() * 1000), "tk": ticker, "open": int(o),
                                        "close": int(c), "trades": n})
            except Exception:                                    # noqa: BLE001
                self.errors["trade"] += 1

    # -- Coinbase
    def spot_once(self, coin):
        t0 = self.clock()
        d = self.get(COINBASE.format(coin))
        t1 = self.clock()
        self.store.write(coin, {"k": "spot", "t": round((t0 + t1) / 2 * 1000), "rtt": round((t1 - t0) * 1000),
                                "p": _num(d.get("price")), "b": _num(d.get("bid")), "a": _num(d.get("ask")),
                                "pt": round(_ts(d["time"]) * 1000) if d.get("time") else None,
                                "id": d.get("trade_id")})

    # -- loops
    def every_second(self, fn, kind):
        nxt = int(self.clock()) + 1
        while not self.stop.is_set():
            self.sleep(max(0.0, nxt - self.clock()))
            nxt += 1
            if self.clock() > nxt + 2:                           # fell behind (slow network): skip ahead, never burst
                nxt = int(self.clock()) + 1
            try:
                fn()
            except Exception:                                    # noqa: BLE001
                self.errors[kind] += 1

    def heartbeat(self, started):
        c = self.store.take_counts()
        line = (f"{dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')} up {int(self.clock() - started)}s "
                + " ".join(f"{k} spot {v['spot']} book {v['book']} trade {v['trade']}" for k, v in c.items())
                + " errors " + ",".join(f"{k}={v}" for k, v in self.errors.items())
                + " markets " + ",".join(m["ticker"] for m in self.markets.values()))
        print(line, flush=True)
        with open(os.path.join(self.out, "heartbeat.log"), "a") as f:
            f.write(line + "\n")
        return line

    def run(self):
        started = self.clock()
        if started >= self.until:
            print("past --until: nothing to record", flush=True)
            return 0
        os.makedirs(self.out, exist_ok=True)
        threads = [threading.Thread(target=self.every_second, args=(lambda c=c: self.spot_once(c), "spot"), daemon=True)
                   for c in COINS]
        threads.append(threading.Thread(target=self.every_second, args=(self.book_once, "book"), daemon=True))
        threads.append(threading.Thread(target=self.trades_loop, daemon=True))
        threads.append(threading.Thread(target=self.every_second, args=(self.discover_missing, "discover"), daemon=True))
        for t in threads:
            t.start()
        try:
            while self.clock() < self.until:
                self.sleep(60 - (self.clock() % 60))
                self.store.flush()
                self.heartbeat(started)
        finally:
            self.stop.set()
            self.store.flush()
            self.store.close()
        print("reached --until: stopped", flush=True)
        return 0

    def discover_missing(self):
        """Look up a coin with no current market, or with no next market known yet (refreshed once per window)."""
        now = self.clock()
        for coin in COINS:
            ahead = [x for x in self.upcoming.get(coin) or [] if x["open"] > now]
            if coin not in self.markets or not ahead:
                try:
                    self.discover(coin)
                except Exception:                                # noqa: BLE001
                    self.errors["discover"] += 1

    def trades_loop(self):
        while not self.stop.is_set():
            self.trades_due()
            self.sleep(5)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Spot v Kalshi 15-minute crypto recorder (record only)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--until", required=True, help="UTC ISO time to stop, e.g. 2026-11-14T16:00:00Z")
    a = ap.parse_args(argv)
    return Recorder(a.out, _ts(a.until)).run()


if __name__ == "__main__":
    sys.exit(main())
