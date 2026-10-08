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
RUNGS_PER_DAY = 12       # most-traded rungs whose candles are read per day
TIMEOUT = 30
_last = [0.0]


def _get(path, tries=3):
    """GET JSON from Kalshi, paced to about six requests a second."""
    url = path if path.startswith("http") else API + path
    err = None
    for i in range(tries):
        wait = 0.17 - (time.monotonic() - _last[0])
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
            time.sleep(1.0 * (i + 1))
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
                         bid=bid, ask=ask, size=_ask_size(m), vol=_num(m.get("volume")) or 0,
                         oi=_num(m.get("open_interest")) or 0))
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


def day_read(series, ms, close):
    """One settled day: was there an in-band, tight rung inside the window?"""
    start, end = close - timedelta(hours=WINDOW_H[1] + 1), close - timedelta(hours=WINDOW_H[0] - 1)
    picked = sorted(ms, key=lambda m: -(_num(m.get("volume")) or 0))[:RUNGS_PER_DAY]
    spreads, band_tight, band_any = [], 0, 0
    with ThreadPoolExecutor(max_workers=3) as ex:
        allc = list(ex.map(lambda m: _candles(series, m["ticker"], start, end), picked))
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
                if ask - bid <= MAX_SPREAD:
                    band_tight += 1
    return dict(day=close.astimezone(ET).strftime("%b %-d"), close=_et(close),
                in_band_hours=band_any, tight_hours=band_tight,
                med_spread=(statistics.median(spreads) if spreads else None),
                volume=sum((_num(m.get("volume")) or 0) for m in ms))


def classify(s, shape, title):
    t = (s.get("ticker") or "").upper()
    if t.startswith("KXUST") or re.search(r"(?i)treasury|yield", title):
        return "treasury"
    if re.search(r"\b[A-Z]{3}/?[A-Z]{3}\b", title) or re.search(r"^KX[A-Z]{6}", t):
        return "fx"
    return "other"


def main():
    days = DAYS
    if "--days" in sys.argv:
        days = int(sys.argv[sys.argv.index("--days") + 1])
    series = (_get("/series?category=Financials&limit=500") or {}).get("series") or []
    daily = [s for s in series if str(s.get("frequency", "")).lower() == "daily"]
    print(f"Financials series: {len(series)}, daily: {len(daily)}\n")
    report, out_of_scope = [], []
    for s in sorted(daily, key=lambda s: s.get("ticker") or ""):
        tk = s.get("ticker")
        title = s.get("title") or ""
        srcs = ", ".join(x.get("name") or x.get("url") or "?" for x in (s.get("settlement_sources") or [])) or "?"
        open_ms = _markets(tk, "open")
        ev = _events(open_ms)
        if not ev:
            out_of_scope.append((tk, title, "no open markets"))
            continue
        soon = min(ev.values(), key=lambda ms: _close(ms) or datetime.max.replace(tzinfo=timezone.utc))
        shape = _shape(soon)
        group = classify(s, shape, title)
        if not _nested(soon):
            out_of_scope.append((tk, title, f"{len(soon)} markets, strikes {shape} (not a nested ladder)"))
            continue
        if group == "other":
            out_of_scope.append((tk, title, f"nested {shape} ladder but neither FX nor Treasury"))
            continue
        close = _close(soon)
        live = live_read(soon)
        settled = _events(_markets(tk, "settled"))
        past = sorted(((c, ms) for ms in settled.values() if (c := _close(ms))), key=lambda x: x[0])[-days:]
        hist = [day_read(tk, ms, c) for c, ms in past]
        report.append(dict(ticker=tk, group=group, title=title, source=srcs, close=_et(close),
                           close_utc=close.isoformat() if close else None, shape=shape, live=live, days=hist))
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
             "| Series | Group | Close (ET) | Rungs | Live: two-sided / in band / tight / deep | Days with a tight in-band rung | Median window spread | Volume/day | Verdict |",
             "|---|---|---|---|---|---|---|---|---|"]
    for r in sorted(report, key=lambda r: (r["group"], r["ticker"])):
        live, hist = r["live"], r["days"]
        tight_days = sum(1 for d in hist if d["tight_hours"])
        spreads = [d["med_spread"] for d in hist if d["med_spread"] is not None]
        vols = [d["volume"] for d in hist]
        med_sp = f"{statistics.median(spreads):g}¢" if spreads else "—"
        med_vol = f"{statistics.median(vols):g}" if vols else "—"
        lines.append(f"| {r['ticker']} | {r['group']} | {r['close']} | {live['rungs']} | "
                     f"{live['two_sided']} / {live['in_band']} / {live['tight']} / {live['deep']} | "
                     f"{tight_days} of {len(hist)} | {med_sp} | {med_vol} | {verdict(r)} |")
    lines += ["", "### Per series", ""]
    for r in sorted(report, key=lambda r: (r["group"], r["ticker"])):
        lines.append(f"- **{r['ticker']}** — {r['title']} · settles on {r['source']} · closes {r['close']} "
                     f"({r['close_utc']}) · {r['shape']} ladder")
        band = r["live"]["band_rows"]
        if band:
            lines.append("  - live in-band rungs: " + "; ".join(
                f"{b['strike']:g} ask {b['ask']}¢ bid {b['bid']}¢ size {b['size'] if b['size'] is not None else '?'}"
                for b in band))
        else:
            lines.append("  - live in-band rungs: none")
        for d in r["days"]:
            lines.append(f"  - {d['day']}: in-band rung-hours {d['in_band_hours']}, tight {d['tight_hours']}, "
                         f"median spread {d['med_spread'] if d['med_spread'] is not None else '—'}, volume {d['volume']:g}")
    lines += ["", "### Out of scope / not a nested daily ladder", ""]
    for tk, title, why in out_of_scope:
        lines.append(f"- {tk} — {title}: {why}")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
