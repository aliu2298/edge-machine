#!/usr/bin/env python3
"""Kalshi Invest big-move lane (2026-11-06): a 1-minute collector, the venue-gap log and the forward paper tracker.

PAPER ONLY. This module reads Kalshi's PUBLIC perps market data and nothing else: it holds no key, never
authenticates, and never places, amends or cancels an order. Everything is 1x (no leverage).

  collect   one snapshot of every Equities/Indices perp (bid, ask, last, reference price) appended to
            <work>/ticks/YYYY-MM-DD.csv. Run every minute.
  track     reads the ticks, logs the big-move events of the four registered rules, grades them on Kalshi
            prices with the honest fill rule, logs Kalshi-only gaps (perp v the stock's reference) and their
            snap-back, and writes data/invest_state.json. Run every 15 minutes.

Public API (docs.kalshi.com/margin, perps_openapi.yaml):
  GET /trade-api/v2/margin/markets                      bid/ask/last/reference_price for all perps, one call
  GET /trade-api/v2/margin/trades?ticker=&min_ts=&max_ts=  public prints (fill confirmation)

The honest fill rule
  entry   a taker at the ask (Up) / bid (Down) of the first snapshot after the signal; it counts as filled only
          if a trade printed at or through that price within the next 60 s; else the next snapshot, up to 5.
  TP      a resting limit at entry x (1 +/- tp): filled only when a trade prints strictly THROUGH it, at the level.
  stop    a taker exit at the bid (Up) / ask (Down) of the first snapshot at or beyond the stop level.
  time    a taker exit at the bid / ask of the first snapshot once the hold's regular-hours minutes have passed.
  fees    0.12% of notional a taker side, 0.02% maker (the TP fill). The spread is paid on every taker side.
"""
import argparse
import csv
import datetime as dt
import gzip
import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(ROOT, "data", "invest_state.json")
API = "https://external-api.kalshi.com/trade-api/v2/margin"
ET = ZoneInfo("America/New_York")
CLASSES = ("Equities", "Indices")
NO_PRICE = 1e12                        # the API's empty-side sentinel is 922337203685477.5807
TAKER, MAKER = 0.0012, 0.0002
FILL_TRIES = 5
KEEP_DAYS = 14
FIELDS = ("ts", "ticker", "sym", "bid", "ask", "last", "ref", "open")

# Venue angle (pre-registered 2026-11-06, forward only): a Kalshi-only gap is a snapshot whose perp mid sits
# >= 1% from the stock's reference price while the market is open; one flag per ticker per hour; the gap is
# re-read 5, 15 and 60 minutes later (the snap-back).
GAP_FLAG = 0.01
GAP_LOOK = (5, 15, 60)

# The four forward rules, one per action x direction. Each is the research grid's best cell for that rule
# by margin over the random-entry baseline (research/invest_bigmove, PREREGISTRATION.md); `cleared` says
# whether it passed the pre-registered bar. A rule that did not clear is a paper OBSERVATION only.
RULES = {
    # Research 2026-11-06 (A1 baseline): 648 cells, 0 cleared, 0 watch. These are each rule's best research cell by
    # margin, as pre-registered; every one FAILED its holdout, so all four are forward observations only.
    "fade_drop":   dict(act="fade", dir="drop", win="1h", size=0.05, tp=0.08, sl=0.04, hold="1d", cleared=False),
    "fade_jump":   dict(act="fade", dir="jump", win="day", size=0.08, tp=0.08, sl=0.04, hold="5d", cleared=False),
    "follow_drop": dict(act="follow", dir="drop", win="day", size=0.08, tp=0.08, sl=0.04, hold="5d", cleared=False),
    "follow_jump": dict(act="follow", dir="jump", win="1h", size=0.08, tp=0.08, sl=0.04, hold="1h", cleared=False),
}
RULES_REGISTERED = "2026-11-06"
HOLD_MIN = {"1h": 60, "1d": 390, "5d": 1950}
LABELS = {"fade_drop": "Fade a drop · Up", "fade_jump": "Fade a jump · Down",
          "follow_drop": "Follow a drop · Down", "follow_jump": "Follow a jump · Up"}


def side_of(rule):
    """+1 Up, -1 Down: fade buys the drop and sells the jump; follow goes with it."""
    r = RULES[rule]
    up = (r["dir"] == "drop") == (r["act"] == "fade")
    return 1 if up else -1


# ---------------------------------------------------------------- the public API (read-only)

def _get(path, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(API + path, headers={"User-Agent": "edge-machine/1.0", "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=20) as f:
                return json.load(f)
        except Exception as e:                                  # noqa: BLE001
            last = e
            time.sleep(1 + 2 * i)
    raise RuntimeError(f"kalshi perps {path.split('?')[0]}: {type(last).__name__}")


def _px(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if v <= 0 or v >= NO_PRICE else v


def snapshot_rows(markets, ts):
    out = []
    for m in markets:
        if m.get("asset_class") not in CLASSES or m.get("status") != "active":
            continue
        out.append(dict(ts=int(ts), ticker=m["ticker"], sym=m.get("title", ""), bid=_px(m.get("bid")),
                        ask=_px(m.get("ask")), last=_px(m.get("price")),
                        ref=_px((m.get("reference_price") or {}).get("price")),
                        open=int(bool((m.get("schedule") or {}).get("is_open")))))
    return out


def trades(ticker, min_ts, max_ts, get=_get):
    """[(ts seconds, price)] public prints, oldest first."""
    out, cursor = [], None
    for _ in range(20):
        q = {"ticker": ticker, "min_ts": int(min_ts), "max_ts": int(max_ts), "limit": 1000}
        if cursor:
            q["cursor"] = cursor
        d = get("/trades?" + urllib.parse.urlencode(q))
        for t in d.get("trades") or []:
            ts = dt.datetime.fromisoformat(t["created_time"].replace("Z", "+00:00")).timestamp()
            out.append((ts, float(t["price"])))
        cursor = d.get("cursor")
        if not cursor or not d.get("trades"):
            break
    return sorted(out)


# ---------------------------------------------------------------- collect

def collect(work, get=_get, now=None):
    now = now or time.time()
    rows = snapshot_rows((get("/markets") or {}).get("markets") or [], now)
    day = dt.datetime.fromtimestamp(now, dt.timezone.utc).date().isoformat()
    os.makedirs(os.path.join(work, "ticks"), exist_ok=True)
    path = os.path.join(work, "ticks", f"{day}.csv")
    new = not os.path.exists(path)
    with open(path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r[k] is None else r[k]) for k in FIELDS})
    _housekeep(work, day)
    return len(rows)


def _housekeep(work, today):
    """gzip finished days, drop days older than KEEP_DAYS."""
    d = os.path.join(work, "ticks")
    cut = (dt.date.fromisoformat(today) - dt.timedelta(days=KEEP_DAYS)).isoformat()
    for name in os.listdir(d):
        day = name[:10]
        p = os.path.join(d, name)
        if day < cut:
            os.remove(p)
        elif name.endswith(".csv") and day < today:
            with open(p, "rb") as src, gzip.open(p + ".gz", "wb") as dst:
                dst.write(src.read())
            os.remove(p)


def load_ticks(work, since_ts):
    """{ticker: [row, ...]} oldest first, from every day file since `since_ts`."""
    d = os.path.join(work, "ticks")
    out = {}
    if not os.path.isdir(d):
        return out
    first = dt.datetime.fromtimestamp(since_ts, dt.timezone.utc).date().isoformat()
    for name in sorted(os.listdir(d)):
        if name[:10] < first:
            continue
        op = gzip.open if name.endswith(".gz") else open
        with op(os.path.join(d, name), "rt", newline="") as f:
            for r in csv.DictReader(f):
                ts = int(r["ts"])
                if ts < since_ts:
                    continue
                out.setdefault(r["ticker"], []).append(dict(
                    ts=ts, sym=r["sym"], bid=_px(r["bid"]), ask=_px(r["ask"]), last=_px(r["last"]),
                    ref=_px(r["ref"]), open=r["open"] == "1"))
    for v in out.values():
        v.sort(key=lambda r: r["ts"])
    return out


# ---------------------------------------------------------------- the clock

def et(ts):
    return dt.datetime.fromtimestamp(ts, ET)


def rth_minute(ts):
    """ET minute of day if `ts` is in regular hours on a weekday (9:30-16:00), else None."""
    t = et(ts)
    m = t.hour * 60 + t.minute
    return m if t.weekday() < 5 and 570 <= m < 960 else None


# ---------------------------------------------------------------- events (signals on the reference price)

def _sessions(rows):
    """{ET date: [rows in regular hours]}"""
    out = {}
    for r in rows:
        if r["ref"] is not None and rth_minute(r["ts"]) is not None:
            out.setdefault(et(r["ts"]).date().isoformat(), []).append(r)
    return out


def detect(ticks, rule, known):
    """New events for `rule` from the ticks: (ticker, signal ts, move). One per ticker, day and rule."""
    R = RULES[rule]
    X, sgn = R["size"], (-1 if R["dir"] == "drop" else 1)
    new = []
    for ticker, rows in ticks.items():
        ses = _sessions(rows)
        days = sorted(ses)
        for i, day in enumerate(days):
            if i == 0 or f"{rule}|{ticker}|{day}" in known:
                continue
            prev = ses[days[i - 1]]
            prev_close = prev[-1]["ref"] if rth_minute(prev[-1]["ts"]) >= 955 else None
            rows_d = ses[day]
            hit = None
            if R["win"] == "gap" and prev_close:
                first = next((r for r in rows_d if rth_minute(r["ts"]) <= 572), None)
                if first:
                    mv = first["ref"] / prev_close - 1
                    hit = (first["ts"], mv) if sgn * mv >= X else None
            elif R["win"] == "day" and prev_close:
                at = next((r for r in rows_d if 955 <= rth_minute(r["ts"]) <= 957), None)
                if at:
                    mv = at["ref"] / prev_close - 1
                    hit = (at["ts"], mv) if sgn * mv >= X else None
            elif R["win"] == "1h":
                by_ts = [(r["ts"], r["ref"]) for r in rows_d]
                for j, (ts, ref) in enumerate(by_ts):
                    if rth_minute(ts) < 630 or rth_minute(ts) > 958:
                        continue
                    back = [p for t0, p in by_ts[:j] if abs((ts - 3600) - t0) <= 90]
                    if back and sgn * (ref / back[-1] - 1) >= X:
                        hit = (ts, ref / back[-1] - 1)
                        break
            if hit:
                new.append(dict(id=f"{rule}|{ticker}|{day}", rule=rule, ticker=ticker, sym=rows_d[0]["sym"],
                                day=day, signal_ts=hit[0], move=round(hit[1], 5), status="pending"))
    return new


# ---------------------------------------------------------------- grading (honest fills on Kalshi prices)

def grade(ev, rows, prints, now):
    """Fill and exit one event in place. `rows` the ticker's ticks, `prints(t0, t1)` its trades."""
    R = RULES[ev["rule"]]
    side = side_of(ev["rule"])
    after = [r for r in rows if r["ts"] > ev["signal_ts"]]
    if ev["status"] == "pending":
        tries = 0
        for r in after:
            px = r["ask"] if side > 0 else r["bid"]
            if px is None:
                continue
            if r["ts"] + 60 > now:
                return ev                                   # the confirming minute has not passed yet
            tries += 1
            got = prints(r["ts"], r["ts"] + 60)
            if any((p >= px) if side > 0 else (p <= px) for _t, p in got):
                ev.update(status="open", entry_ts=r["ts"], entry=px, spread_in=_spread(r))
                break
            if tries >= FILL_TRIES:
                ev.update(status="no_fill", note=f"no print at or through the quote in {FILL_TRIES} minutes")
                return ev
        else:
            return ev
    if ev["status"] != "open":
        return ev
    E = ev["entry"]
    tp_lvl = E * (1 + side * R["tp"])
    sl_lvl = E * (1 - side * R["sl"])
    hold, used = HOLD_MIN[R["hold"]], 0
    later = [r for r in rows if r["ts"] > ev["entry_ts"]]
    t_prev = ev["entry_ts"]
    for r in later:
        # the TP: a resting limit, filled only by a print strictly through it between the last snapshot and this one
        thru = [t for t, p in prints(t_prev, r["ts"]) if ((p > tp_lvl) if side > 0 else (p < tp_lvl))]
        if thru:
            return _close(ev, thru[0], tp_lvl, "tp", MAKER)
        t_prev = r["ts"]
        if rth_minute(r["ts"]) is not None:
            used += 1
        px = r["bid"] if side > 0 else r["ask"]
        if px is None:
            continue
        if (px <= sl_lvl) if side > 0 else (px >= sl_lvl):
            return _close(ev, r["ts"], px, "stop", TAKER)
        if used >= hold:
            return _close(ev, r["ts"], px, "time", TAKER)
    return ev


def _spread(r):
    if r["bid"] is None or r["ask"] is None:
        return None
    return round((r["ask"] - r["bid"]) / ((r["ask"] + r["bid"]) / 2) * 1e4, 1)


def _close(ev, ts, px, why, exit_fee):
    side = side_of(ev["rule"])
    gross = side * (px / ev["entry"] - 1)
    ev.update(status="settled", exit_ts=int(ts), exit=px, exit_why=why,
              gross=round(gross, 5), net=round(gross - TAKER - exit_fee, 5))
    return ev


# ---------------------------------------------------------------- the venue angle

def venue_flags(ticks, known, now):
    """Kalshi-only gaps: perp mid >= GAP_FLAG from the reference while open; one per ticker an hour."""
    out = []
    last_flag = {}
    for f in known:
        last_flag[f["ticker"]] = max(last_flag.get(f["ticker"], 0), f["ts"])
    for ticker, rows in ticks.items():
        for i, r in enumerate(rows):
            if not r["open"] or r["bid"] is None or r["ask"] is None or r["ref"] is None:
                continue
            gap = ((r["bid"] + r["ask"]) / 2) / r["ref"] - 1
            if abs(gap) < GAP_FLAG or r["ts"] - last_flag.get(ticker, 0) < 3600:
                continue
            last_flag[ticker] = r["ts"]
            out.append(dict(ticker=ticker, sym=r["sym"], ts=r["ts"], gap=round(gap, 5), spread_bp=_spread(r),
                            rth=rth_minute(r["ts"]) is not None))
    return out


def snap_back(flag, rows):
    """Fill in the gap 5/15/60 minutes later when those snapshots exist."""
    for m in GAP_LOOK:
        k = f"gap_{m}m"
        if flag.get(k) is not None:
            continue
        r = next((x for x in rows if x["ts"] >= flag["ts"] + 60 * m), None)
        if r and r["bid"] is not None and r["ask"] is not None and r["ref"]:
            flag[k] = round(((r["bid"] + r["ask"]) / 2) / r["ref"] - 1, 5)
    return flag


# ---------------------------------------------------------------- state

def load(path=STATE):
    try:
        with open(path) as f:
            s = json.load(f)
    except (OSError, ValueError):
        s = {}
    s.setdefault("events", [])
    s.setdefault("flags", [])
    s.setdefault("collector", {})
    return s


def save(s, path=STATE):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(s, f, indent=1, sort_keys=True)
    os.replace(tmp, path)


def summary(s):
    """Per rule: settled, wins, average net, t, open, no-fill."""
    out = {}
    for k in RULES:
        ev = [e for e in s["events"] if e["rule"] == k]
        done = [e["net"] for e in ev if e["status"] == "settled"]
        n = len(done)
        mean = sum(done) / n if n else None
        sd = math.sqrt(sum((x - mean) ** 2 for x in done) / (n - 1)) if n > 1 else 0
        out[k] = dict(n=n, win=(sum(x > 0 for x in done) / n if n else None), net=mean,
                      t=(mean / (sd / math.sqrt(n)) if n > 1 and sd > 0 else None),
                      open=sum(e["status"] == "open" for e in ev),
                      pending=sum(e["status"] == "pending" for e in ev),
                      no_fill=sum(e["status"] == "no_fill" for e in ev))
    return out


def track(work, state_path=STATE, now=None, get=_get):
    now = now or time.time()
    s = load(state_path)
    since = now - KEEP_DAYS * 86400
    ticks = load_ticks(work, since)
    known = {e["id"] for e in s["events"]}
    for rule in RULES:
        for ev in detect(ticks, rule, known):
            if ev["signal_ts"] >= s.get("live_from_ts", 0):
                s["events"].append(ev)
                known.add(ev["id"])
    cache = {}

    def prints_for(ticker):
        def f(t0, t1):
            key = (ticker, int(t0) // 3600)
            if key not in cache:
                h0 = (int(t0) // 3600) * 3600
                cache[key] = trades(ticker, h0, h0 + 3600, get=get) if h0 < now else []
            got = cache[key]
            if int(t1) // 3600 != int(t0) // 3600:
                got = got + f((int(t0) // 3600 + 1) * 3600, t1)
            return [(t, p) for t, p in got if t0 <= t < t1]
        return f
    for ev in s["events"]:
        if ev["status"] in ("pending", "open") and ev["ticker"] in ticks:
            try:
                grade(ev, ticks[ev["ticker"]], prints_for(ev["ticker"]), now)
            except RuntimeError as e:
                ev["note"] = str(e)[:120]
    s["flags"] += venue_flags(ticks, s["flags"], now)
    for f in s["flags"]:
        if f["ts"] > now - 2 * 86400 and f["ticker"] in ticks:
            snap_back(f, ticks[f["ticker"]])
    s["flags"] = s["flags"][-500:]
    rows_today = sum(1 for v in ticks.values() for r in v if r["ts"] > now - 86400)
    last = max((r["ts"] for v in ticks.values() for r in v), default=None)
    s["collector"] = dict(last_ts=last, markets=len(ticks), rows_24h=rows_today)
    s["rules"] = {k: dict(v, registered=RULES_REGISTERED, side="Up" if side_of(k) > 0 else "Down") for k, v in RULES.items()}
    s["last_run"] = dt.datetime.fromtimestamp(now, dt.timezone.utc).isoformat(timespec="seconds")
    save(s, state_path)
    return s


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=("collect", "track"))
    ap.add_argument("--work", default=os.path.expanduser("~/invest"))
    ap.add_argument("--state", default=STATE)
    a = ap.parse_args(argv)
    if a.cmd == "collect":
        print(f"{collect(a.work)} markets")
    else:
        s = track(a.work, a.state)
        for k, v in summary(s).items():
            print(k, v)
    return 0


if __name__ == "__main__":
    sys.exit(main())
