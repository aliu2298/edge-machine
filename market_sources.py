#!/usr/bin/env python3
"""market_sources.py — bars and the universe for the Sandbox's TRADING lane.

Data comes from Alpaca (the account is the user's; keys live in ~/.alpaca-credentials, mode
600, written by hand and never printed). Yahoo and Stooq both refuse this host, so there is
no keyless fallback for stocks; without credentials every fetch returns nothing and the lane
simply logs no trades, exactly as a dark feed does in the sports lane.

The S&P 500 membership list is keyless (the `datasets` mirror of the index constituents) and
is cached on disk, because a rule's universe must not change silently between runs.
"""
import csv
import datetime
import io
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
UNIVERSE_PATH = os.path.join(ROOT, "data", "sp500.json")
# Credentials, in order. The second is the June 2026 swing-trader project's own .env, so the
# keys already on this machine are reused rather than copied around. Values are never read
# into a log, a page or a commit — only handed to the request headers.
CRED_FILES = [(os.path.expanduser("~/.alpaca-credentials"), "APCA_API_KEY_ID", "APCA_API_SECRET_KEY"),
              (os.path.expanduser("~/Swing trader/.env"), "ALPACA_API_KEY", "ALPACA_SECRET_KEY")]
DATA_HOST = "https://data.alpaca.markets"
SP500_CSV = ("https://raw.githubusercontent.com/datasets/s-and-p-500-companies/"
             "master/data/constituents.csv")

# Costs charged on BOTH sides of every logged trade. Alpaca charges no commission on US
# equities, so this is spread plus slippage: 5bp a side is the realistic cost of crossing on
# a liquid S&P 500 name, and today's BTC work is the reminder that a rule which only works at
# zero cost is not a rule. Raised for anything thinner by MIN_DOLLAR_VOLUME below.
COST_BPS_PER_SIDE = 5.0
MIN_DOLLAR_VOLUME = 20_000_000      # a name must trade this much a day to be logged at all


def _creds():
    """(key_id, secret) from the first credentials file that has them, or (None, None)."""
    for path, k_key, k_sec in CRED_FILES:
        try:
            with open(path) as f:
                kv = {}
                for line in f:
                    line = line.strip()
                    if "=" in line and not line.startswith("#"):
                        a, b = line.split("=", 1)
                        kv[a.strip()] = b.strip().strip('"').strip("'")
        except OSError:
            continue
        if kv.get(k_key) and kv.get(k_sec):
            return kv[k_key], kv[k_sec]
    return None, None


def configured():
    """Are credentials present? Used by the page to say why a lane is quiet."""
    return all(_creds())


def _get(url, tries=3, timeout=30):
    key, sec = _creds()
    if not (key and sec):
        raise RuntimeError("no Alpaca credentials")
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={
                "APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": sec,
                "User-Agent": "edge-machine/1.0", "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as f:
                return json.load(f)
        except urllib.error.HTTPError as e:
            last = RuntimeError(f"HTTP {e.code}")
            if e.code in (401, 403):
                raise last                      # bad keys: fail loudly, never retry
            time.sleep(1.5 * (i + 1))
        except Exception as e:                  # network-shaped: retry
            last = e
            time.sleep(1.5 * (i + 1))
    raise last or RuntimeError("unreachable")


def universe(refresh_days=7):
    """The S&P 500 symbols, cached. A rule's universe must not drift silently between runs."""
    try:
        blob = json.load(open(UNIVERSE_PATH))
        age = (datetime.date.today() - datetime.date.fromisoformat(blob["fetched"])).days
        if age < refresh_days and blob.get("symbols"):
            return blob["symbols"]
    except (OSError, ValueError, KeyError):
        blob = None
    try:
        req = urllib.request.Request(SP500_CSV, headers={"User-Agent": "edge-machine/1.0"})
        with urllib.request.urlopen(req, timeout=30) as f:
            rows = list(csv.DictReader(io.StringIO(f.read().decode())))
        syms = sorted({r["Symbol"].replace(".", "-") for r in rows if r.get("Symbol")})
    except Exception:
        return (blob or {}).get("symbols", [])   # keep the last good list
    if len(syms) < 400:
        return (blob or {}).get("symbols", [])
    os.makedirs(os.path.dirname(UNIVERSE_PATH), exist_ok=True)
    with open(UNIVERSE_PATH, "w") as f:
        json.dump({"fetched": datetime.date.today().isoformat(), "symbols": syms}, f)
    return syms


def bars(symbols, timeframe="1Day", start=None, end=None, limit=10000, feed="iex"):
    """{symbol: [bar, ...]} from Alpaca, oldest first. Bars are dicts with t/o/h/l/c/v.

    `feed` is IEX on the free plan. Returns {} without credentials rather than raising, so a
    run on a machine with no keys is quiet instead of broken.
    """
    if not configured() or not symbols:
        return {}
    out, syms = {}, list(symbols)
    start = start or (datetime.date.today() - datetime.timedelta(days=400)).isoformat()
    for i in range(0, len(syms), 100):           # the API takes a batch of symbols per call
        chunk = syms[i:i + 100]
        page = None
        while True:
            q = {"symbols": ",".join(chunk), "timeframe": timeframe, "start": start,
                 "limit": limit, "feed": feed, "adjustment": "split"}
            if end:
                q["end"] = end
            if page:
                q["page_token"] = page
            try:
                d = _get(f"{DATA_HOST}/v2/stocks/bars?{urllib.parse.urlencode(q)}")
            except Exception:
                break
            for sym, rows in (d.get("bars") or {}).items():
                out.setdefault(sym, []).extend(rows)
            page = d.get("next_page_token")
            if not page:
                break
        time.sleep(0.2)
    for sym in out:
        out[sym].sort(key=lambda b: b["t"])
    return out


def dollar_volume(bar):
    return float(bar.get("c", 0)) * float(bar.get("v", 0))


def cost(price, bps=COST_BPS_PER_SIDE):
    """One side's cost in dollars per share."""
    return float(price) * bps / 10000.0


def session_bars(day_bars, day):
    """The regular-session 5-minute bars of one date (13:30-20:00 UTC), oldest first."""
    out = []
    for b in day_bars:
        try:
            t = datetime.datetime.fromisoformat(str(b["t"]).replace("Z", "+00:00"))
        except (KeyError, ValueError):
            continue
        if t.date() != day:
            continue
        mins = t.hour * 60 + t.minute
        if 13 * 60 + 30 <= mins < 20 * 60:
            out.append(dict(b, dt=t))
    return out
