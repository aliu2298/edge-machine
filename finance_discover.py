#!/usr/bin/env python3
"""Discovery for a Finance lane: which Kalshi daily finance ladders are liquid enough.

Read-only against Kalshi's public API (no key, no orders). For every Financials
series that settles once per trading day on a NESTED ladder ("above X" rungs that
one move settles together), this prints:

  * ticker, title, settlement source, close time in Eastern, rung count;
  * the live book of the soonest open ladder: two-sided rungs, the 70-80c band,
    spread and ask size on the in-band rungs;
  * the last few settled days: whether an in-band rung with a spread of 3c or
    less existed 2-3.5h before the close (from hourly candles), the median
    window spread, and the day's volume.

Range buckets ("between" strikes) and up/down coins are listed as out of scope
so the reader can see why. Nothing is written to the repo: the report goes to
stdout and, when set, to GITHUB_STEP_SUMMARY.

Usage:  python3 finance_discover.py [--days N] [--json]
"""
import json
import os
import re
import statistics
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

API = "https://api.elections.kalshi.com/trade-api/v2"
UA = "edge-machine finance discovery (read-only)"
ET = ZoneInfo("America/New_York")
BAND = (70, 80)          # cents, both ends inclusive, as the Crypto lane
MAX_SPREAD = 3           # cents
MIN_ASK_SIZE = 25
WINDOW_H = (2.0, 3.5)    # hours before the close, as the Crypto lane
DAYS = 5                 # settled days sampled per series
RUNGS_PER_DAY = 8       # most-traded rungs whose candles are read per day
TIMEOUT = 30
PACE_S = 0.21            # about five requests a second across every thread
_last = [0.0]
_lock = threading.Lock()
READ_AT = datetime.now(timezone.utc).astimezone(ET).strftime("%a %b %-d %-I:%M %p ET")


def _get(path, tries=4):
    """GET JSON from Kalshi, paced across threads; 429 backs off 2s, 4s, 8s."""
    url = path if path.startswith("http") else API + path
    err = None
    for i in range(tries):
        with _lock:
            wait = PACE_S - (time.monotonic() - _last[0])
            if wait > 0:
                time.sleep(wait)
            _last[0] = time.monotonic()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as f:
                return json.load(f)
        except urllib.error.HTTPError as e:
            err = e
            if e.code == 404:
                return {}
            time.sleep(2.0 * (2 ** i))
        except (OSError, ValueError) as e:
            err = e
            time.sleep(1.0 * (i + 1))
    print(f"  ! {url}: {err}", file=sys.stderr)
    return {}


def _cents(m, key):
    """A price in cents from either the cents field or the *_dollars string."""
    v = m.get(key)
    if v is None:
        d = m.get(key + "_dollars")
        if d is None:
            return None
        try:
            return round(float(d) * 100)
        except (TypeError, ValueError):
            return None
    try:
        return round(float(v))
    except (TypeError, ValueError):
        return None


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _ts(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _et(dt):
    return dt.astimezone(ET).strftime("%a %-I:%M %p ET") if dt else "?"


def _markets(series, status):
    out, cursor = [], ""
    for _ in range(10):
        q = {"series_ticker": series, "status": status, "limit": 200}
        if cursor:
            q["cursor"] = cursor
        d = _get("/markets?" + urllib.parse.urlencode(q))
        out += d.get("markets") or []
        cursor = d.get("cursor") or ""
        if not cursor:
            break
    return out


def _events(markets):
    """{event_ticker: [markets]} with the markets sorted by strike."""
    ev = {}
    for m in markets:
        ev.setdefault(m.get("event_ticker") or "?", []).append(m)
    for ms in ev.values():
        ms.sort(key=lambda m: (_num(m.get("floor_strike")) or _num(m.get("cap_strike")) or 0))
    return ev


def _close(ms):
    ts = [_ts(m.get("close_time")) or _ts(m.get("expiration_time")) for m in ms]
    ts = [t for t in ts if t]
    return min(ts) if ts else None


def _shape(ms):
    kinds = sorted({str(m.get("strike_type") or "?") for m in ms})
    return "+".join(kinds)


def _nested(ms):
    kinds = {str(m.get("strike_type") or "?") for m in ms}
    return len(ms) >= 2 and kinds <= {"greater", "less"} and len(kinds) == 1


def _book(ticker):
    """(yes ask cents, ask size) from the live order book, from the No bids."""
    d = _get(f"/markets/{ticker}/orderbook")
    ob = d.get("orderbook") or d.get("orderbook_fp") or {}
    nos = ob.get("no") or []
    best = None
    for lvl in nos:
        try:
            p, q = float(lvl[0]), float(lvl[1])
        except (TypeError, ValueError, IndexError):
            continue
        if p <= 1.0:            # dollars grid
            p *= 100
        if best is None or p > best[0]:
            best = (p, q)
    if best is None:
        return None, None
    return round(100 - best[0]), best[1]


def _vol(m, key="volume"):
    for k in (key + "_fp", key):
        v = _num(m.get(k))
        if v is not None:
            return v
    return 0.0


def _ask_size(m):
    for k in ("yes_ask_size_fp", "yes_ask_size"):
        v = _num(m.get(k))
        if v is not None:
            return v
    return None


def live_read(ms):
    """The soonest open ladder's book: rungs, two-sided, in band, best in-band quote."""
    rows = []
    for m in ms:
        bid, ask = _cents(m, "yes_bid"), _cents(m, "yes_ask")
        rows.append(dict(t=m.get("ticker"), strike=_num(m.get("floor_strike")) or _num(m.get("cap_strike")),
                         bid=bid, ask=ask, size=_ask_size(m), vol=_vol(m),
                         oi=_vol(m, "open_interest")))
    two = [r for r in rows if r["bid"] not in (None, 0) and r["ask"] not in (None, 100)]
    band = [r for r in two if BAND[0] <= r["ask"] <= BAND[1]]
    # Ask size from the book itself where the market row carries none.
    for r in band[:6]:
        if r["size"] is None:
            _a, q = _book(r["t"])
            r["size"] = q
    tight = [r for r in band if r["ask"] - r["bid"] <= MAX_SPREAD]
    deep = [r for r in tight if r["size"] is not None and r["size"] >= MIN_ASK_SIZE]
    return dict(rungs=len(rows), two_sided=len(two), in_band=len(band), tight=len(tight), deep=len(deep),
                band_rows=[dict(strike=r["strike"], bid=r["bid"], ask=r["ask"], size=r["size"]) for r in band],
                volume=sum(r["vol"] for r in rows), oi=sum(r["oi"] for r in rows))


def _candles(series, ticker, start, end):
    q = urllib.parse.urlencode({"start_ts": int(start.timestamp()), "end_ts": int(end.timestamp()),
                                "period_interval": 60})
    d = _get(f"/series/{series}/markets/{ticker}/candlesticks?{q}")
    return d.get("candlesticks") or []


def _cclose(c, key):
    v = c.get(key)
    if isinstance(v, dict):
        x = v.get("close")
        if x is None:
            x = v.get("close_dollars")
            x = None if x is None else float(x) * 100
        return None if x is None else round(float(x))
    for k in (key + "_close", key + "_close_dollars"):
        if c.get(k) is not None:
            x = float(c[k])
            return round(x * 100 if k.endswith("dollars") else x)
    return None


_shown_candle = [False]


def day_read(series, ms, close):
    """One settled day: was there an in-band, tight rung inside the window?"""
    start, end = close - timedelta(hours=WINDOW_H[1] + 1), close - timedelta(hours=WINDOW_H[0] - 1)
    picked = sorted(ms, key=lambda m: -_vol(m))[:RUNGS_PER_DAY]
    spreads, band_tight, band_any, band_vol = [], 0, 0, 0.0
    with ThreadPoolExecutor(max_workers=2) as ex:
        allc = list(ex.map(lambda m: _candles(series, m["ticker"], start, end), picked))
    if not _shown_candle[0] and any(allc):
        c0 = next(cs for cs in allc if cs)[0]
        print("candle fields:", json.dumps(c0)[:400])
        _shown_candle[0] = True
    for cs in allc:
        for c in cs:
            t = c.get("end_period_ts")
            if t is None:
                continue
            tt = datetime.fromtimestamp(int(t), tz=timezone.utc)
            h = (close - tt).total_seconds() / 3600
            if not (WINDOW_H[0] <= h <= WINDOW_H[1]):
                continue
            bid, ask = _cclose(c, "yes_bid"), _cclose(c, "yes_ask")
            if bid in (None, 0) or ask in (None, 100):
                continue
            if BAND[0] <= ask <= BAND[1]:
                band_any += 1
                spreads.append(ask - bid)
                band_vol += _vol(c)
                if ask - bid <= MAX_SPREAD:
                    band_tight += 1
    return dict(day=close.astimezone(ET).strftime("%b %-d"), close=_et(close),
                in_band_hours=band_any, tight_hours=band_tight,
                med_spread=(statistics.median(spreads) if spreads else None),
                min_spread=(min(spreads) if spreads else None),
                band_window_volume=band_vol,
                volume=sum(_vol(m) for m in ms))


def classify(s, shape, title):
    t = (s.get("ticker") or "").upper()
    if t.startswith("KXUST") or re.search(r"(?i)treasury|yield", title):
        return "treasury"
    if re.search(r"\b[A-Z]{3}/?[A-Z]{3}\b", title) or re.search(r"^KX[A-Z]{6}", t):
        return "fx"
    return "other"


# Tickers seen on Kalshi's Finance tab that the category listing may not carry
# under "daily": the FX "above" ladders and the Treasury yield ladders.
_PAIRS = ("EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "USDMXN", "USDNOK", "USDSEK", "USDBRL",
          "NZDUSD", "AUDUSD", "USDINR")
TARGETS = (tuple(f"KX{p}AD" for p in _PAIRS) + tuple(f"KX{p}AW" for p in _PAIRS) + ("KXNZDUSD",)
           + tuple(f"KXUST{n}A" for n in (2, 5, 7, 10, 30)) + tuple(f"KXUST{n}AD" for n in (2, 5, 7, 10, 30))
           + ("KXTNOTED",))
_FXT = re.compile(r"(?i)\b(EUR|GBP|USD|JPY|CHF|CAD|MXN|NOK|SEK|BRL|NZD|AUD|INR)\s*/?\s*(EUR|GBP|USD|JPY|CHF|CAD|MXN|NOK|SEK|BRL|NZD|AUD|INR)\b|treasury|yield|UST ")


def cadence(settled):
    """How often the series settles: distinct close days in the last 30, by weekday."""
    closes = sorted({c.astimezone(ET).date() for ms in settled.values() if (c := _close(ms))})
    if not closes:
        return "no settled markets"
    cutoff = closes[-1] - timedelta(days=30)
    recent = [d for d in closes if d > cutoff]
    wd = {}
    for d in recent:
        wd[d.strftime("%a")] = wd.get(d.strftime("%a"), 0) + 1
    return (f"{len(recent)} settlements in the 30 days to {closes[-1]:%b %-d}: "
            + ", ".join(f"{k} x{v}" for k, v in sorted(wd.items(), key=lambda x: -x[1])))


def main():
    days = DAYS
    if "--days" in sys.argv:
        days = int(sys.argv[sys.argv.index("--days") + 1])
    series = (_get("/series?category=Financials&limit=500") or {}).get("series") or []
    freqs = {}
    for x in series:
        freqs[str(x.get("frequency"))] = freqs.get(str(x.get("frequency")), 0) + 1
    print(f"Financials series: {len(series)}, by frequency: {freqs}")
    by_tk = {x.get("ticker"): x for x in series}
    # FX / Treasury titled series at ANY frequency, plus the targets by ticker.
    cands = {tk: x for tk, x in by_tk.items() if _FXT.search(x.get("title") or "") or (tk or "").endswith("AW")}
    for tk in TARGETS:
        if tk not in cands:
            d = _get(f"/series/{tk}")
            x = d.get("series") if isinstance(d, dict) else None
            if x:
                cands[tk] = x
                print(f"  {tk}: found by ticker (category {x.get('category')!r}, frequency {x.get('frequency')!r})")
            else:
                print(f"  {tk}: not found by ticker")
    print(f"FX/Treasury candidates: {len(cands)}\n")
    shown_keys = False
    report, out_of_scope = [], []
    only = re.compile(sys.argv[sys.argv.index("--only") + 1]) if "--only" in sys.argv else None
    for tk, s in sorted(cands.items()):
        if only and not only.search(tk):
            continue
        title = s.get("title") or ""
        srcs = ", ".join(x.get("name") or x.get("url") or "?" for x in (s.get("settlement_sources") or [])) or "?"
        open_ms = _markets(tk, "open")
        if open_ms and not shown_keys:
            print("market fields:", sorted(open_ms[0].keys()))
            shown_keys = True
        ev = _events(open_ms)
        freq = str(s.get("frequency"))
        settled = {}
        listed = bool(ev)
        if not ev:
            why = "no open markets"
            if tk in TARGETS or _FXT.search(title) and re.search(r"(?i)daily|AD$", title + " " + tk):
                settled = _events(_markets(tk, "settled"))
                closes = [c for ms in settled.values() if (c := _close(ms))]
                why += f", last settled {max(closes).astimezone(ET):%b %-d %Y}" if closes else ", never settled"
                recent = [c for c in closes if c > datetime.now(timezone.utc) - timedelta(days=10)]
                if recent:
                    # Not listed at read time but settling lately: read it from its history,
                    # with the latest settled ladder standing in for the open one.
                    ev = {k: v for k, v in settled.items() if _close(v) == max(closes)}
            if not ev:
                out_of_scope.append((tk, f"{title} [{freq}]", why))
                continue
        soon = min(ev.values(), key=lambda ms: _close(ms) or datetime.max.replace(tzinfo=timezone.utc))
        shape = _shape(soon)
        group = classify(s, shape, title)
        if not _nested(soon):
            out_of_scope.append((tk, f"{title} [{freq}]", f"{len(soon)} markets, strikes {shape} (not a nested ladder)"))
            continue
        if group == "other":
            out_of_scope.append((tk, f"{title} [{freq}]", f"nested {shape} ladder but neither FX nor Treasury"))
            continue
        close = _close(soon)
        exp = min((t for m in soon if (t := _ts(m.get("expected_expiration_time") or m.get("expiration_time")))),
                  default=None)
        live = live_read(soon) if listed else dict(rungs=len(soon), two_sided=0, in_band=0, tight=0, deep=0,
                                                   band_rows=[], volume=0, oi=0, unlisted=True)
        if listed and not settled:
            settled = _events(_markets(tk, "settled"))
        cad = cadence(settled)
        if "--no-history" in sys.argv:
            days = 0
        past = sorted(((c, ms) for ms in settled.values() if (c := _close(ms))), key=lambda x: x[0])[-days:] if days else []
        hist = [day_read(tk, ms, c) for c, ms in past]
        report.append(dict(ticker=tk, group=group, title=title, source=srcs, close=_et(close),
                           close_utc=close.isoformat() if close else None, shape=shape, live=live, days=hist,
                           frequency=freq, cadence=cad, open_ladders=len(ev) if listed else 0,
                           listed=listed, expiration=_et(exp), expiration_utc=exp.isoformat() if exp else None))
        print(f"{tk:<14} {group:<8} {_et(close):<18} rungs {live['rungs']:>3}  two-sided {live['two_sided']:>3}  "
              f"in band {live['in_band']:>2}  tight {live['tight']:>2}  deep {live['deep']:>2}  "
              f"days tight {sum(1 for d in hist if d['tight_hours'])}/{len(hist)}")
    md = render(report, out_of_scope)
    print("\n" + md)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(md + "\n")
    if "--json" in sys.argv:
        print("\n=== JSON ===")
        print(json.dumps(dict(report=report, out_of_scope=out_of_scope), default=str))
        print("=== END JSON ===")


def verdict(r):
    hist, live = r["days"], r["live"]
    tight_days = sum(1 for d in hist if d["tight_hours"])
    band_days = sum(1 for d in hist if d["in_band_hours"])
    if not hist or (band_days == 0 and live["in_band"] == 0 and live["volume"] == 0):
        return "almost never (no trade, no in-band quote)"
    if hist and tight_days >= max(1, round(0.6 * len(hist))) and (live["deep"] or live["tight"]):
        return "passes on a typical day"
    if tight_days or live["tight"]:
        return "marginal"
    return "almost never"


def render(report, out_of_scope):
    lines = ["## Kalshi daily finance ladders — liquidity floor read", "",
             f"Floor: two-sided quote, spread ≤{MAX_SPREAD}¢, ask size ≥{MIN_ASK_SIZE}, on a rung asking "
             f"{BAND[0]}–{BAND[1]}¢, read {WINDOW_H[0]:g}–{WINDOW_H[1]:g}h before the close. "
             "History from hourly candles (spread only; Kalshi keeps no size history), size from today's book.", "",
             "| Series | Group | Frequency | Close (ET) | Rungs | Live: two-sided / in band / tight / deep | Days with a tight in-band rung | Median window spread | Volume/day | Verdict |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for r in sorted(report, key=lambda r: (r["group"], r["ticker"])):
        live, hist = r["live"], r["days"]
        tight_days = sum(1 for d in hist if d["tight_hours"])
        spreads = [d["med_spread"] for d in hist if d["med_spread"] is not None]
        vols = [d["volume"] for d in hist]
        med_sp = f"{statistics.median(spreads):g}¢" if spreads else "—"
        med_vol = f"{statistics.median(vols):g}" if vols else "—"
        lines.append(f"| {r['ticker']} | {r['group']} | {r['frequency']} | {r['close']} | {live['rungs']} | "
                     f"{live['two_sided']} / {live['in_band']} / {live['tight']} / {live['deep']} | "
                     f"{tight_days} of {len(hist)} | {med_sp} | {med_vol} | {verdict(r)} |")
    lines += ["", "### Per series", ""]
    for r in sorted(report, key=lambda r: (r["group"], r["ticker"])):
        when = "next" if r["listed"] else "latest settled"
        lines.append(f"- **{r['ticker']}** — {r['title']} · frequency `{r['frequency']}` · {r['cadence']} · "
                     f"settles on {r['source']} · {when} close {r['close']} ({r['close_utc']}), "
                     f"expiration {r['expiration']} · "
                     f"{r['open_ladders']} open ladder(s) at read time · {r['shape']}")
        band = r["live"]["band_rows"]
        if not r["listed"]:
            lines.append("  - live book: no ladder listed at read time")
        elif band:
            lines.append(f"  - live in-band rungs at {READ_AT}: " + "; ".join(
                f"{b['strike']:g} ask {b['ask']}¢ bid {b['bid']}¢ size {b['size'] if b['size'] is not None else '?'}"
                for b in band))
        else:
            lines.append(f"  - live in-band rungs at {READ_AT}: none")
        for d in r["days"]:
            lines.append(f"  - {d['day']}: in-band rung-hours {d['in_band_hours']}, tight {d['tight_hours']}, "
                         f"spread median {d['med_spread'] if d['med_spread'] is not None else '—'} / "
                         f"best {d['min_spread'] if d['min_spread'] is not None else '—'}, "
                         f"in-band window volume {d['band_window_volume']:g}, day volume {d['volume']:g}")
    lines += ["", "### Out of scope / not a nested daily ladder", ""]
    for tk, title, why in out_of_scope:
        lines.append(f"- {tk} — {title}: {why}")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
