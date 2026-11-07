#!/usr/bin/env python3
"""earnings_news.py: Earnings & news calls, a Sandbox PAPER lane on Kalshi Invest perps (2026-11-07).

PAPER ONLY. This file reads PUBLIC data only: Kalshi's perps and event APIs and Nasdaq's earnings
calendar. It holds no key, never authenticates, and never places, amends or cancels an order.

Olu's ask: stop leaning on backtests. Read news and earnings, and call moves BEFORE they happen. Every
call is timestamped and committed before its entry. The four pre-registered families (F1 kpi_drift,
F2a runup, F2b post_drift, F3 news, F4 sentiment) are fixed in earnings_news_families.md. Its
SHA-256 is pinned in FAMILIES_SHA256, and test_earnings_news.py fails if the file changes.

  python3 earnings_news.py run        hourly (earnings-news.yml): refresh the calendar, snapshot the
                                      KPI ladders, log every rule call that is due, then grade
  python3 earnings_news.py news --sym NVDA --dir up --horizon 1d --conf 0.6 \\
          --reason "..." --url https://... --published 2026-11-07T01:10:00Z
                                      log one F3 news call (now), never retro-dated
  python3 earnings_news.py grade      grade whatever has come due
"""
import argparse
import datetime as dt
import hashlib
import json
import math
import os
import random
import re
import sys
import time
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "data", "earnings_news.json")
FAMILIES_FILE = os.path.join(ROOT, "earnings_news_families.md")
FAMILIES_SHA256 = "fe3a9ccd04fb22fccf12c99ace3ffabe7398cff4da1f058e3ea1bedf6f54cfd9"
REGISTERED = "2026-11-07"

PERPS = "https://external-api.kalshi.com/trade-api/v2/margin"
PERPS_V1 = "https://api.elections.kalshi.com/v1/margin_markets/"
EVENTS = "https://api.elections.kalshi.com/trade-api/v2"
NASDAQ = "https://api.nasdaq.com/api/calendar/earnings?date="
ET = ZoneInfo("America/New_York")
UTC = dt.timezone.utc
NO_PRICE = 1e12
TAKER = 0.0012
SPY = "KXSPYPERP"

# Pre-registered constants (earnings_news_families.md). Never tune these against the record.
CAL_DAYS = 21                     # calendar look-ahead
FILL_WINDOW_S = 300               # a print at or through the quote within 5 minutes
FILL_TRIES = 6                    # quotes 5 minutes apart: 30 minutes
F1_RUNG_SPREAD = 0.20
F1_MIN_RUNGS = 3
F1_BASE_DAYS = 5
F1_MOVE = 0.25
F1_WINDOW_H = (30, 6)
F2B_MIN = 0.02
F2B_HOLD = 5
F2A_SESSIONS = 5
F4_HI, F4_LO = 0.65, 0.35
F4_MIN_NOTIONAL = 500_000
LOG_HOUR_ET = 15                  # F2b and F4 log at the first run at or after 15:00 ET
REVIEW_AT, DECIDE_AT = 10, 30
HORIZONS = ("1h", "1d", "5d")

FAMILIES = {
    "kpi_drift":  "F1 · KPI ladder drift into the report",
    "runup":      "F2a · Drift into the report",
    "post_drift": "F2b · Post-earnings drift",
    "news":       "F3 · News-cycle calls",
    "sentiment":  "F4 · Trader sentiment extremes",
}

# NYSE full-day closures. A perp trades on them, but they are not trading days for counting sessions.
HOLIDAYS = {dt.date(2026, 11, 26), dt.date(2026, 12, 25), dt.date(2027, 1, 1), dt.date(2027, 1, 18),
            dt.date(2027, 2, 15), dt.date(2027, 3, 26), dt.date(2027, 5, 31)}


# ---------------------------------------------------------------- time

def now_utc():
    return dt.datetime.now(UTC)


def iso(t):
    return t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def is_trading_day(d):
    return d.weekday() < 5 and d not in HOLIDAYS


def add_sessions(d, n):
    """The trading day n sessions after (n > 0) or before (n < 0) date d."""
    step = 1 if n > 0 else -1
    k = 0
    while k < abs(n):
        d += dt.timedelta(days=step)
        if is_trading_day(d):
            k += 1
    return d


def at_et(d, hh, mm=0):
    return dt.datetime(d.year, d.month, d.day, hh, mm, tzinfo=ET).astimezone(UTC)


def report_time(row):
    """(report instant, reaction session D, P = last 16:00 ET close before the report)."""
    d = dt.date.fromisoformat(row["date"])
    if row.get("time") == "after-hours":
        t = at_et(d, 16, 5)
        D = add_sessions(d, 1)
        P = at_et(d, 16) if is_trading_day(d) else at_et(add_sessions(d, -1), 16)
    else:                                   # pre-market, or not supplied: the earliest it could be
        t = at_et(d, 7)
        D = d if is_trading_day(d) else add_sessions(d, 1)
        P = at_et(add_sessions(d, -1), 16)
    return t, D, P


def next_trading_same_clock(t, n=1):
    loc = t.astimezone(ET)
    d = add_sessions(loc.date(), n)
    return dt.datetime(d.year, d.month, d.day, loc.hour, loc.minute, tzinfo=ET).astimezone(UTC)


# ---------------------------------------------------------------- public HTTP (read-only)

def _get(url, headers=None, tries=3):
    last = None
    h = {"User-Agent": "edge-machine/1.0", "Accept": "application/json"}
    h.update(headers or {})
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=30) as f:
                return json.load(f)
        except Exception as e:                                  # noqa: BLE001
            last = e
            time.sleep(1 + 2 * i)
    raise RuntimeError(f"GET {url.split('?')[0]}: {type(last).__name__}")


def px(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if v <= 0 or v >= NO_PRICE else v


def perps_list(get=_get):
    d = get(PERPS + "/markets")
    ms = d.get("markets", d) if isinstance(d, dict) else d
    # "inactive" perps are listed but not yet open (36 open on 2026-11-09); they belong on the calendar.
    return [m for m in ms if m.get("asset_class") == "Equities" and m.get("status") in ("active", "inactive")]


def candles(ticker, t0, t1, get=_get, period=1):
    """[(end_ts, bid, ask)] quotes per `period` minutes, oldest first."""
    q = urllib.parse.urlencode({"period_interval": period, "start_ts": int(t0), "end_ts": int(t1)})
    d = get(f"{PERPS}/markets/{ticker}/candlesticks?{q}")
    out = []
    for c in d.get("candlesticks") or []:
        out.append((int(c["end_period_ts"]), px((c.get("bid") or {}).get("close")),
                    px((c.get("ask") or {}).get("close"))))
    return out


def perp_open(ts):
    """Kalshi Invest perps trade Sunday 18:00 ET to Friday 17:00 ET. A quote outside that is stale."""
    loc = dt.datetime.fromtimestamp(ts, ET)
    wd, h = loc.weekday(), loc.hour
    if wd == 5:
        return False
    if wd == 4:
        return h < 17
    if wd == 6:
        return h >= 18
    return True


def next_open(ts):
    t = int(ts)
    while not perp_open(t):
        t = (t // 3600 + 1) * 3600
    return t


def first_quote_after(ticker, t, until, get=_get):
    """The first open instant at or after t inside an hour with a two-sided quote, or None. Hourly candles
    find the hour (a call logged while the perp is closed enters at the reopen); the caller finds the minute."""
    t = next_open(t)
    if t > until:
        return None
    for end, b, a in candles(ticker, t, until, get=get, period=60):
        if end >= t and b and a and perp_open(end - 60):
            return max(t, end - 3600)
    return None


def prints(ticker, t0, t1, get=_get):
    """[(ts, price)] public trades, oldest first."""
    out, cursor = [], None
    for _ in range(10):
        q = {"ticker": ticker, "min_ts": int(t0), "max_ts": int(t1), "limit": 1000}
        if cursor:
            q["cursor"] = cursor
        d = get(f"{PERPS}/trades?" + urllib.parse.urlencode(q))
        for t in d.get("trades") or []:
            p = px(t.get("price"))
            if p is not None:
                out.append((parse(t["created_time"]).timestamp(), p))
        cursor = d.get("cursor")
        if not cursor or not d.get("trades"):
            break
    return sorted(out)


# ---------------------------------------------------------------- the honest fill

def honest_fill(ticker, due, buy, get=_get, now=None):
    """Fill at the quote of the first candle ending at or after `due` (or the reopen, when the perp is
    closed at `due`), confirmed by a print at or through it within FILL_WINDOW_S; up to FILL_TRIES quotes
    FILL_WINDOW_S apart. -> ('filled', ts, price) / ('no_fill', None, None) / ('pending', None, None)."""
    now = now or now_utc()
    start = first_quote_after(ticker, due.timestamp(), now.timestamp() + 3600, get=get)
    if start is None:
        return ("pending", None, None)       # closed since `due`: wait for the reopen
    horizon = start + FILL_TRIES * FILL_WINDOW_S + FILL_WINDOW_S
    hi = min(horizon, now.timestamp()) + 60
    cs = candles(ticker, start - 60, hi, get=get)
    pr = prints(ticker, start - 60, hi, get=get)
    tried, nxt = 0, start
    for end, bid, ask in cs:
        if end < nxt:
            continue
        q = ask if buy else bid
        if q is None or not perp_open(end - 60):
            continue
        if end + FILL_WINDOW_S > now.timestamp():
            return ("pending", None, None)
        tried += 1
        if any(end - 60 <= ts <= end + FILL_WINDOW_S and ((p >= q) if buy else (p <= q)) for ts, p in pr):
            return ("filled", end, q)
        if tried >= FILL_TRIES:
            return ("no_fill", None, None)
        nxt = end + FILL_WINDOW_S
    return ("pending", None, None) if now.timestamp() < horizon else ("no_fill", None, None)


def leg(ticker, side, entry_due, exit_due, get=_get, now=None):
    """One graded position: {'status', 'entry', 'exit', 'net'}; side +1 Up, -1 Down."""
    st, et_, ep = honest_fill(ticker, entry_due, buy=side > 0, get=get, now=now)
    if st != "filled":
        return {"status": st}
    exit_due = max(exit_due, dt.datetime.fromtimestamp(et_, UTC) + dt.timedelta(minutes=1))
    st2, xt, xp = honest_fill(ticker, exit_due, buy=side < 0, get=get, now=now)
    if st2 == "pending":
        return {"status": "open", "entry_ts": et_, "entry": ep}
    if st2 != "filled":
        return {"status": "exit_no_fill", "entry_ts": et_, "entry": ep}
    net = side * (xp - ep) / ep - 2 * TAKER
    return {"status": "settled", "entry_ts": et_, "entry": ep, "exit_ts": xt, "exit": xp, "net": round(net, 6)}


# ---------------------------------------------------------------- state

def load(path=PATH):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {"registered": REGISTERED, "calendar": [], "kpi_reads": [], "predictions": []}


def save(state, path=PATH):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=1, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


def pid(family, sym, key):
    return f"{family}:{sym}:{key}"


def coin(prediction_id):
    """The random baseline's fixed side for one prediction: +1 or -1, from its id."""
    return 1 if hashlib.sha256(prediction_id.encode()).digest()[0] % 2 == 0 else -1


def add_prediction(state, p):
    if any(q["id"] == p["id"] for q in state["predictions"]):
        return False
    p.setdefault("random_side", coin(p["id"]))
    state["predictions"].append(p)
    return True


# ---------------------------------------------------------------- calendar (A)

def kalshi_company_events(syms, get=_get):
    """Open events of each symbol's quarterly KPI series (KX<SYM>) and earnings-call mention series."""
    out = []
    for sym in syms:
        for series in (f"KX{sym}", f"KXEARNINGSMENTION{sym}"):
            try:
                d = get(EVENTS + "/events?" + urllib.parse.urlencode({"series_ticker": series, "status": "open"}))
            except RuntimeError:
                continue
            out += d.get("events") or []
            time.sleep(0.7)
    return out


MONTHS = {m: i for i, m in enumerate(("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT",
                                      "NOV", "DEC"), 1)}


def event_month(event_ticker):
    m = re.search(r"-(\d\d)([A-Z]{3})", event_ticker)
    if not m or m.group(2) not in MONTHS:
        return None
    return (2000 + int(m.group(1)), MONTHS[m.group(2)])


def match_markets(sym, report_date, events):
    """(quarterly KPI events resolving at this report, earnings-call mention events)."""
    d = dt.date.fromisoformat(report_date)
    kpi, men = [], []
    for e in events:
        st, et_ = e.get("series_ticker", ""), e.get("event_ticker", "")
        if st == f"KXEARNINGSMENTION{sym}":
            mm = event_month(et_)
            if mm and abs((mm[0] * 12 + mm[1]) - (d.year * 12 + d.month)) <= 1:
                men.append(et_)
        elif st == f"KX{sym}" and event_month(et_) == (d.year, d.month):
            kpi.append({"event": et_, "title": e.get("title", "")})
    return kpi, men


def refresh_calendar(state, now=None, get=_get, events=None):
    """Next report for every Invest stock inside CAL_DAYS, from Nasdaq; Kalshi KPI and mention matches."""
    now = now or now_utc()
    perps = perps_list(get=get)
    syms = {m["title"].replace(".", ""): m["ticker"] for m in perps}
    rows = {}
    d = now.astimezone(ET).date()
    for i in range(CAL_DAYS + 1):
        day = d + dt.timedelta(days=i)
        if day.weekday() >= 5:
            continue
        try:
            r = get(NASDAQ + day.isoformat(), headers={"User-Agent": "Mozilla/5.0"})
        except RuntimeError:
            return False                     # keep the committed calendar when Nasdaq is unreachable
        for row in (r.get("data") or {}).get("rows") or []:
            s = row["symbol"].replace(".", "")
            if s in syms and s not in rows:
                rows[s] = {"sym": s, "perp": syms[s], "date": day.isoformat(), "name": row.get("name", ""),
                           "time": (row.get("time") or "").replace("time-", ""),
                           "eps_forecast": row.get("epsForecast", ""), "n_ests": row.get("noOfEsts", ""),
                           "fiscal_q": row.get("fiscalQuarterEnding", "")}
        time.sleep(0.5)
    events = kalshi_company_events(sorted(rows), get=get) if events is None else events
    for r in rows.values():
        r["kpi"], r["mentions"] = match_markets(r["sym"], r["date"], events)
    old = {c["sym"]: c for c in state.get("calendar") or []}
    # A report that has passed stays on the calendar until its F2b drift has been logged.
    for s, c in old.items():
        if s not in rows and dt.date.fromisoformat(c["date"]) >= d - dt.timedelta(days=10):
            rows[s] = c
    state["calendar"] = sorted(rows.values(), key=lambda r: (r["date"], r["sym"]))
    state["calendar_at"] = iso(now)
    return True


# ---------------------------------------------------------------- F1 KPI ladder reads

def ladder_read(markets):
    """{'median', 'width', 'rungs'} from a 'greater' ladder, or None when it cannot be read."""
    pts = []
    for m in markets:
        if m.get("strike_type") != "greater" or m.get("floor_strike") is None:
            continue
        try:
            b = float(m.get("yes_bid_dollars") or 0)
            a = float(m.get("yes_ask_dollars") or 0)
        except (TypeError, ValueError):
            continue
        if a <= 0 or a - b > F1_RUNG_SPREAD:
            continue
        pts.append((float(m["floor_strike"]), (a + b) / 2))
    pts.sort()
    if len(pts) < F1_MIN_RUNGS:
        return None
    ks = [k for k, _ in pts]
    ps, run = [], 1.0
    for _, p in pts:                         # P(X > k) can only fall as k rises
        run = min(run, p)
        ps.append(run)
    if not (ps[0] >= 0.5 >= ps[-1]):
        return None

    def cross(level):
        for i in range(1, len(ps)):
            if ps[i - 1] >= level >= ps[i]:
                if ps[i - 1] == ps[i]:
                    return (ks[i - 1] + ks[i]) / 2
                return ks[i - 1] + (ps[i - 1] - level) / (ps[i - 1] - ps[i]) * (ks[i] - ks[i - 1])
        return None
    med = cross(0.5)
    hi, lo = cross(0.25), cross(0.75)
    width = (hi - lo) if hi is not None and lo is not None else ks[-1] - ks[0]
    return {"median": med, "width": width, "rungs": len(pts)}


def snapshot_kpis(state, now=None, get=_get):
    now = now or now_utc()
    for c in state.get("calendar") or []:
        for k in c.get("kpi") or []:
            try:
                d = get(f"{EVENTS}/events/{k['event']}?with_nested_markets=true")
            except RuntimeError:
                continue
            ms = (d.get("event") or {}).get("markets") or d.get("markets") or []
            r = ladder_read(ms)
            state["kpi_reads"].append({"event": k["event"], "sym": c["sym"], "at": iso(now),
                                       "read": r})
            time.sleep(0.7)


# ---------------------------------------------------------------- the rule families

def mid_at(ticker, t, get=_get):
    cs = candles(ticker, t.timestamp() - 1800, t.timestamp() + 60, get=get)
    for end, b, a in reversed(cs):
        if b and a:
            return (a + b) / 2
    return None


def log_rules(state, now=None, get=_get, perps=None):
    """Log every F1 / F2a / F2b / F4 call that is due now. Returns the ids logged."""
    now = now or now_utc()
    logged = []
    loc = now.astimezone(ET)
    for c in state.get("calendar") or []:
        t, D, P = report_time(c)
        sym, perp = c["sym"], c["perp"]
        base = {"sym": sym, "perp": perp, "report": c["date"], "report_time": c.get("time")}
        # F2a runup: logged at least an hour before its entry (16:00 ET, 5 sessions before P).
        entry = at_et(add_sessions(P.astimezone(ET).date(), -F2A_SESSIONS), 16)
        if now <= entry - dt.timedelta(hours=1):
            p = dict(base, id=pid("runup", sym, c["date"]), family="runup", side=1, logged_at=iso(now),
                     entry_due=iso(entry), exit_due=iso(P),
                     reason=f"Up into the {c['date']} report ({c.get('time') or 'time not supplied'}).")
            if add_prediction(state, p):
                logged.append(p["id"])
        # F1 kpi_drift: the first run 30 to 6 hours before the report.
        lo, hi = t - dt.timedelta(hours=F1_WINDOW_H[0]), t - dt.timedelta(hours=F1_WINDOW_H[1])
        for k in c.get("kpi") or []:
            the_id = pid("kpi_drift", sym, k["event"])
            if not (lo <= now <= hi) or any(q["id"] == the_id for q in state["predictions"]):
                continue
            reads = [r for r in state["kpi_reads"] if r["event"] == k["event"] and r.get("read")]
            early = [r for r in reads if parse(r["at"]) <= t - dt.timedelta(days=F1_BASE_DAYS)]
            latest = reads[-1] if reads else None
            if not early or not latest or parse(latest["at"]) < now - dt.timedelta(hours=2):
                why = "no ladder read from 5+ days before" if not early else "no current ladder read"
                p = dict(base, id=the_id, family="kpi_drift", side=0, status="no_call", logged_at=iso(now),
                         reason=f"{k['event']}: {why}.")
                add_prediction(state, p)
                logged.append(the_id)
                continue
            e0, e1 = early[0]["read"], latest["read"]
            move = e1["median"] - e0["median"]
            thr = F1_MOVE * e0["width"]
            side = 1 if move >= thr else -1 if move <= -thr else 0
            reason = (f"{k['title'] or k['event']}: ladder median {e0['median']:g} → {e1['median']:g} "
                      f"(move {move:+g}, threshold ±{thr:g}).")
            p = dict(base, id=the_id, family="kpi_drift", side=side, logged_at=iso(now), reason=reason,
                     kpi_event=k["event"], kpi_from=early[0]["at"], kpi_to=latest["at"])
            if side:
                p.update(entry_due=iso(now), exit_due=iso(at_et(D, 16)))
            else:
                p["status"] = "no_call"
            add_prediction(state, p)
            logged.append(the_id)
        # F2b post_drift: the first run at or after 15:00 ET on D.
        the_id = pid("post_drift", sym, c["date"])
        if loc.date() == D and loc.hour >= LOG_HOUR_ET and not any(q["id"] == the_id for q in state["predictions"]):
            m0, m1 = mid_at(perp, P, get=get), mid_at(perp, now, get=get)
            if m0 and m1:
                R = m1 / m0 - 1
                side = (1 if R > 0 else -1) if abs(R) >= F2B_MIN else 0
                p = dict(base, id=the_id, family="post_drift", side=side, logged_at=iso(now),
                         reaction=round(R, 5),
                         reason=f"Reaction since the last close before the report: {R * 100:+.1f}%.")
                if side:
                    p.update(entry_due=iso(now), exit_due=iso(at_et(add_sessions(D, F2B_HOLD), 16)))
                else:
                    p["status"] = "no_call"
                add_prediction(state, p)
                logged.append(the_id)
    # F4 sentiment: once a trading day, the first run at or after 15:00 ET.
    if is_trading_day(loc.date()) and loc.hour >= LOG_HOUR_ET:
        day = loc.date().isoformat()
        if not any(q["family"] == "sentiment" and q.get("day") == day for q in state["predictions"]) \
                and not any(s == day for s in state.get("sentiment_days") or []):
            perps = perps_list(get=get) if perps is None else perps
            for m in perps:
                try:
                    v = get(PERPS_V1 + m["ticker"])["market"]
                except RuntimeError:
                    continue
                time.sleep(0.3)
                lg, sh = float(v.get("taker_long_volume_24h") or 0), float(v.get("taker_short_volume_24h") or 0)
                notional = float(v.get("volume_24h_notional_value_dollars") or 0)
                if lg + sh <= 0 or notional < F4_MIN_NOTIONAL:
                    continue
                share = lg / (lg + sh)
                side = 1 if share >= F4_HI else -1 if share <= F4_LO else 0
                if not side:
                    continue
                p = {"id": pid("sentiment", m["title"], day), "family": "sentiment", "sym": m["title"],
                     "perp": m["ticker"], "day": day, "side": side, "logged_at": iso(now),
                     "crowd_up": round(share, 3), "entry_due": iso(now),
                     "exit_due": iso(next_trading_same_clock(now)),
                     "reason": f"Kalshi traders {share * 100:.0f}% Up on 24h taker volume."}
                if add_prediction(state, p):
                    logged.append(p["id"])
            state.setdefault("sentiment_days", []).append(day)
    return logged


def log_news(state, sym, direction, horizon, conf, reason, url, published, now=None, perps=None, get=_get):
    """One F3 call, logged NOW. The entry is the first honest fill after this moment."""
    now = now or now_utc()
    if horizon not in HORIZONS:
        raise ValueError(f"horizon must be one of {HORIZONS}")
    if not 0.5 <= conf <= 1.0:
        raise ValueError("confidence must be 0.5 to 1.0")
    pub = parse(published)
    if pub > now or now - pub > dt.timedelta(hours=6):
        raise ValueError("not material: the source must be published 0-6 hours before logging")
    perps = perps_list(get=get) if perps is None else perps
    perp = {m["title"].replace(".", ""): m["ticker"] for m in perps}.get(sym)
    if not perp:
        raise ValueError(f"{sym} is not an Invest stock")
    side = {"up": 1, "down": -1}[direction.lower()]
    entry = now
    exit_ = (entry + dt.timedelta(hours=1) if horizon == "1h" else
             next_trading_same_clock(entry, 1 if horizon == "1d" else 5))
    p = {"id": pid("news", sym, iso(now)), "family": "news", "sym": sym, "perp": perp, "side": side,
         "horizon": horizon, "confidence": conf, "reason": reason, "url": url, "published": iso(pub),
         "logged_at": iso(now), "entry_due": iso(entry), "exit_due": iso(exit_)}
    add_prediction(state, p)
    return p


# ---------------------------------------------------------------- grading (C)

def grade(state, now=None, get=_get):
    now = now or now_utc()
    for p in state["predictions"]:
        if p.get("status") in ("no_call", "settled", "no_fill", "exit_no_fill") or not p.get("side"):
            continue
        if not p.get("entry_due") or parse(p["entry_due"]) > now:
            continue
        e, x = parse(p["entry_due"]), parse(p["exit_due"])
        try:
            call = leg(p["perp"], p["side"], e, x, get=get, now=now)
        except RuntimeError:
            continue
        p["status"] = call["status"]
        p["call"] = call
        if call["status"] != "settled":
            continue
        # Baselines over the identical due times, the same fill rule.
        b = {}
        for key, tk, side in (("up", p["perp"], 1), ("random", p["perp"], p["random_side"]), ("spy", SPY, 1)):
            try:
                r = leg(tk, side, e, x, get=get, now=now)
            except RuntimeError:
                r = {"status": "error"}
            b[key] = r
        if any(r["status"] == "open" for r in b.values()):
            p["status"] = "open"
            continue
        p["baselines"] = b
        p["net"] = call["net"]
        p["graded_at"] = iso(now)


def paired(rows, key):
    d = [r["net"] - r["baselines"][key]["net"] for r in rows
         if r.get("baselines", {}).get(key, {}).get("status") == "settled"]
    n = len(d)
    if n == 0:
        return {"n": 0, "mean": None, "z": None}
    m = sum(d) / n
    if n < 2:
        return {"n": n, "mean": m, "z": None}
    sd = math.sqrt(sum((v - m) ** 2 for v in d) / (n - 1))
    return {"n": n, "mean": m, "z": (m / (sd / math.sqrt(n))) if sd > 0 else None}


def summary(state):
    out = {}
    for fam, label in FAMILIES.items():
        ps = [p for p in state["predictions"] if p["family"] == fam]
        settled = [p for p in ps if p.get("status") == "settled"]
        nets = [p["net"] for p in settled]
        s = {"label": label, "logged": len([p for p in ps if p.get("side")]),
             "no_call": len([p for p in ps if p.get("status") == "no_call"]),
             "open": len([p for p in ps if p.get("side") and p.get("status") not in
                          ("settled", "no_fill", "exit_no_fill")]),
             "no_fill": len([p for p in ps if p.get("status") in ("no_fill", "exit_no_fill")]),
             "settled": len(settled),
             "win": (sum(1 for v in nets if v > 0) / len(nets)) if nets else None,
             "avg_net": (sum(nets) / len(nets)) if nets else None,
             "vs": {k: paired(settled, k) for k in ("up", "random", "spy")}}
        if fam == "sentiment":                # the fade mirror: the other side, the costs paid again
            s["fade_avg_net"] = (sum(-v - 4 * TAKER for v in nets) / len(nets)) if nets else None
        n = s["settled"]
        zs = [v["z"] for v in s["vs"].values()]
        if n >= DECIDE_AT:
            s["verdict"] = "paying" if all(z is not None and z >= 2 for z in zs) else "no edge"
        elif n >= REVIEW_AT:
            s["verdict"] = "review due"
        else:
            s["verdict"] = f"collecting {n}/{REVIEW_AT}"
        out[fam] = s
    return out


def families_sha():
    with open(FAMILIES_FILE, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


# ---------------------------------------------------------------- CLI

def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run")
    sub.add_parser("grade")
    sub.add_parser("calendar")
    n = sub.add_parser("news")
    n.add_argument("--sym", required=True)
    n.add_argument("--dir", required=True, choices=("up", "down"))
    n.add_argument("--horizon", required=True, choices=HORIZONS)
    n.add_argument("--conf", required=True, type=float)
    n.add_argument("--reason", required=True)
    n.add_argument("--url", required=True)
    n.add_argument("--published", required=True)
    a = ap.parse_args(argv)
    if families_sha() != FAMILIES_SHA256:
        sys.exit("earnings_news_families.md changed after registration: add a NEW family, never edit one")
    state = load()
    if a.cmd in ("run", "calendar"):
        try:
            if not refresh_calendar(state):
                print("calendar: Nasdaq unreachable, the committed calendar is kept")
        except RuntimeError as e:
            print(f"calendar: {e}; the committed calendar is kept")
    if a.cmd == "run":
        snapshot_kpis(state)
        print("logged:", log_rules(state))
    if a.cmd == "news":
        p = log_news(state, a.sym.upper(), a.dir, a.horizon, a.conf, a.reason, a.url, a.published)
        print("logged:", p["id"])
    if a.cmd in ("run", "grade"):
        grade(state)
    save(state)


if __name__ == "__main__":
    main()
