#!/usr/bin/env python3
"""Two Kalshi weather paper lanes (2026-11-13, Olu: "send both to sandbox", from Fable's climate study). Sandbox PAPER only.

  c1v2  Cold lean on daily highs, version 2. At 10:00 pm ET the day before, on each city's next-day high ladder with all six
        brackets quoted: the favourite is the highest mid; buy NO at 1 minus the YES bid on the bracket two COOLER; hold.
        Skipped when the public forecast (NBM station text, a run at least 2 hours old, plus the city shift) is above the favourite.
  l1    Warm lean on daily lows. Same time, all low ladders: NO on the bracket two WARMER than the favourite; hold.

Pre-registered, rules copied unchanged from the study's drafts: docs/prereg_climate_c1v2_2026-11-13.md, docs/prereg_climate_l1_2026-11-13.md.
Fees: fillsim (honest-v1) taker fee on the quoted NO price. Fills are quoted, not trade-confirmed, as in the study. A city-day is one outcome.
Control rows, same time: c1v2 = (a) NO on the bracket two warmer, (b) the bets the forecast skipped (recorded, not counted in the lane);
l1 = NO on the bracket two cooler. The lane logs the depth at the YES bid, and the forecast run each c1v2 decision used.

One read per night, at 10:00 pm Eastern. GitHub's cron runs it in the 02:00Z and 03:00Z hours (10 pm ET is 02:00Z in daylight time, 03:00Z in
standard time) and the run only acts between 22:00 and 22:50 ET, so a late start is logged (lag_min) and a missed night is not made up.
Own ledger data/climate_lanes_ledger.json. Paper only: no order is placed.
"""
import calendar
import datetime as dt
import json
import math
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

import daily_track as D
import fillsim

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "data", "climate_lanes_ledger.json")
SHIFTS_PATH = os.path.join(ROOT, "data", "climate_c1f_shifts.json")
VERSION = "climate-v1"
ET = ZoneInfo("America/New_York")
UTC = dt.timezone.utc
ENTRY_FROM, ENTRY_UNTIL = dt.time(22, 0), dt.time(22, 50)      # Eastern wall clock
MAX_PER_EVENT = 6
FORECAST_LAG_S = 2 * 3600
IEM = "https://mesonet.agron.iastate.edu/cgi-bin/request/mos.py"

# (series suffix, label, station). The 21 daily-high and 21 daily-low series of the study's part 1 build spec.
CITIES = (
    ("NY", "NYC", "New York", "NYC"), ("CHI", "CHI", "Chicago", "MDW"), ("MIA", "MIA", "Miami", "MIA"),
    ("AUS", "AUS", "Austin", "AUS"), ("DEN", "DEN", "Denver", "DEN"), ("LAX", "LAX", "Los Angeles", "LAX"),
    ("PHIL", "PHIL", "Philadelphia", "PHL"), ("TATL", "ATL", "Atlanta", "ATL"), ("TBOS", "BOS", "Boston", "BOS"),
    ("TDAL", "DAL", "Dallas", "DFW"), ("TDC", "DC", "Washington", "DCA"), ("THOU", "HOU", "Houston", "HOU"),
    ("TLV", "LV", "Las Vegas", "LAS"), ("TMIN", "MIN", "Minneapolis", "MSP"), ("TNOLA", "NOLA", "New Orleans", "MSY"),
    ("TOKC", "OKC", "Oklahoma City", "OKC"), ("TPHX", "PHX", "Phoenix", "PHX"), ("TSAN", "SAN", "San Diego", "SAN"),
    ("TSATX", "SATX", "San Antonio", "SAT"), ("TSEA", "SEA", "Seattle", "SEA"), ("TSFO", "SFO", "San Francisco", "SFO"),
)
HIGH_SERIES = {"KXHIGH" + h: (name, stn) for h, _l, name, stn in CITIES}
LOW_SERIES = {"KXLOWT" + l: (name, stn) for _h, l, name, stn in CITIES}
# Hours behind UTC in local STANDARD time (the climate day runs midnight to midnight standard time all year).
LST = {"NYC": 5, "MIA": 5, "PHL": 5, "ATL": 5, "BOS": 5, "DCA": 5, "MDW": 6, "AUS": 6, "DFW": 6, "HOU": 6, "MSP": 6, "MSY": 6, "OKC": 6,
       "SAT": 6, "DEN": 7, "PHX": 7, "LAX": 8, "LAS": 8, "SAN": 8, "SEA": 8, "SFO": 8}

LANES = {
    "c1v2": dict(label="Cold lean · daily highs, version 2", series=HIGH_SERIES, side=-2, control_side=+2, read_at=1000, early_n=300,
                 forecast=True, prereg="docs/prereg_climate_c1v2_2026-11-13.md"),
    "l1": dict(label="Warm lean · daily lows", series=LOW_SERIES, side=+2, control_side=-2, read_at=500, early_n=150,
               forecast=False, prereg="docs/prereg_climate_l1_2026-11-13.md"),
}
EARLY_STOP = -0.03


# ------------------------------------------------------------------ time
def et_now(now):
    return now.astimezone(ET)


def in_window(now):
    """True from 22:00 to 22:50 Eastern."""
    t = et_now(now).time()
    return ENTRY_FROM <= t < ENTRY_UNTIL


def target_day(now):
    """The local day whose ladders are read: tomorrow in Eastern time."""
    return et_now(now).date() + dt.timedelta(days=1)


def event_ticker(series, day):
    return f"{series}-{day:%y}{day:%b}{day:%d}".upper()


def lag_min(now):
    e = et_now(now)
    return round((e - e.replace(hour=22, minute=0, second=0, microsecond=0)).total_seconds() / 60, 1)


# ------------------------------------------------------------------ the ladder
def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def sort_key(m):
    t = m.get("strike_type")
    return -1e9 if t == "less" else 1e9 if t == "greater" else (num(m.get("floor_strike")) or 0.0)


def bounds(m):
    """The bracket as an interval of the real line for a whole-degree outcome (the study's has_lo_hi)."""
    t = m.get("strike_type")
    if t == "greater":
        return num(m["floor_strike"]) + 0.5, 1e9
    if t == "less":
        return -1e9, num(m["cap_strike"]) - 0.5
    return num(m["floor_strike"]) - 0.5, num(m["cap_strike"]) + 0.5


def quotes_of(markets):
    """[(market, yes bid, yes ask)] in bracket order, or None unless all six are quoted (an ask on every bracket)."""
    ms = sorted(markets, key=sort_key)
    if len(ms) != MAX_PER_EVENT:
        return None
    out = []
    for m in ms:
        bid, ask = num(m.get("yes_bid_dollars")), num(m.get("yes_ask_dollars"))
        if bid is None or ask is None or ask <= 0 or bid > ask:
            return None
        out.append((m, bid, ask))
    return out


def favourite(q):
    """Index of the highest mid (the first, the cooler, on a tie)."""
    mids = [(b + a) / 2 for _m, b, a in q]
    return max(range(len(q)), key=lambda i: (mids[i], -i))


def best_bid_depth(book, bid):
    """Contracts resting at the best YES bid."""
    fp = (book or {}).get("orderbook_fp") or (book or {}).get("orderbook") or {}
    levels = fp.get("yes_dollars") or fp.get("yes") or []
    best = None
    for p, n in levels:
        p, n = num(p), num(n)
        if p is None or n is None:
            continue
        if best is None or p > best[0]:
            best = (p, n)
    return None if best is None or abs(best[0] - bid) > 1e-6 else best[1]


# ------------------------------------------------------------------ the public forecast (NBM station text, via IEM)
def iem_url(stn, now):
    q = dict(station="K" + stn, model="NBS", format="csv",
             sts=(now - dt.timedelta(hours=40)).strftime("%Y-%m-%dT%H:%MZ"), ets=now.strftime("%Y-%m-%dT%H:%MZ"))
    return IEM + "?" + urllib.parse.urlencode(q)


IEM_GAP_S = 1.0                      # IEM answers 429 to a burst: one station a second, and a 429 or 5xx is retried with backoff
IEM_WAITS_S = (3, 6, 12, 24, 48)
_iem_last = [0.0]


def get_text(url, opener=urllib.request.urlopen, sleep=time.sleep, clock=time.monotonic):
    req = urllib.request.Request(url, headers={"User-Agent": "edge-machine-paper-dailies"})
    for attempt in range(len(IEM_WAITS_S) + 1):
        wait = IEM_GAP_S - (clock() - _iem_last[0])
        if wait > 0:
            sleep(wait)
        _iem_last[0] = clock()
        try:
            with opener(req, timeout=40) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if (e.code == 429 or e.code >= 500) and attempt < len(IEM_WAITS_S):
                sleep(IEM_WAITS_S[attempt])
                continue
            raise
        except (TimeoutError, ConnectionError, urllib.error.URLError):
            if attempt < len(IEM_WAITS_S):
                sleep(IEM_WAITS_S[attempt])
                continue
            raise


def ep(s):
    return calendar.timegm(dt.datetime.strptime(s[:16], "%Y-%m-%d %H:%M").timetuple())


def parse_nbs(text):
    """{runtime epoch: {ftime epoch: (tmp, txn)}} from IEM's CSV."""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return {}
    head = lines[0].split(",")
    ix = {k: head.index(k) for k in ("runtime", "ftime", "tmp", "txn") if k in head}
    if len(ix) < 4:
        return {}
    out = {}
    for ln in lines[1:]:
        c = ln.split(",")
        try:
            f = lambda k: (num(c[ix[k]]) if c[ix[k]] not in ("", "M") else None)      # noqa: E731
            out.setdefault(ep(c[ix["runtime"]]), {})[ep(c[ix["ftime"]])] = (f("tmp"), f("txn"))
        except (IndexError, ValueError):
            continue
    return out


def day_bounds(stn, day):
    a = calendar.timegm(dt.datetime(day.year, day.month, day.day).timetuple()) + LST[stn] * 3600
    return a, a + 86400


def forecast_high(runs, stn, day, now):
    """The study's calendar-day high forecast: the newest run at least 2 hours old; the larger of its daytime max (TXN at 00Z after the
    day, taken from the newest earlier run that has it when this one does not) and its 3-hourly temperatures inside the standard-time
    day. None when no run or no daytime max can be read."""
    cut = int(now.timestamp()) - FORECAST_LAG_S
    rts = sorted(r for r in runs if r <= cut)
    if not rts:
        return None
    run = runs[rts[-1]]
    d0 = calendar.timegm(dt.datetime(day.year, day.month, day.day).timetuple())
    mx, txn_rt = run.get(d0 + 86400), rts[-1]
    mx = mx[1] if mx else None
    for back in range(1, 5):
        if mx is not None or len(rts) <= back:
            break
        old = runs[rts[-1 - back]].get(d0 + 86400)
        if old and old[1] is not None:
            mx, txn_rt = old[1], rts[-1 - back]
    a, b = day_bounds(stn, day)
    inside = [v[0] for f, v in run.items() if a <= f <= b and v[0] is not None]
    if mx is None:
        return None
    iso = lambda t: dt.datetime.fromtimestamp(t, UTC).strftime("%Y-%m-%dT%H:%MZ")      # noqa: E731
    return dict(value=max([mx] + inside), txn=mx, tmp=max(inside) if inside else None, run=iso(rts[-1]), txn_run=iso(txn_rt))


def load_shifts(path=SHIFTS_PATH):
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def forecast_above(fc, shifts, stn, fav):
    """True when the forecast (plus the city shift) is more than half a degree over the favourite bracket's top, which is its real-line
    edge (the bracket's top degree + 0.5). The open-ended top bracket is never above."""
    if fc is None:
        return False
    _lo, hi = bounds(fav)
    if hi >= 1e8:
        return False
    return fc["value"] + shifts.get(stn, 0.0) > hi + 1e-9


# ------------------------------------------------------------------ the ledger
def empty():
    return dict(version=VERSION, since=None, rows=[], skips={}, nights={}, last_run=None, error=None)


def load(path=PATH):
    try:
        with open(path) as f:
            s = json.load(f)
    except FileNotFoundError:
        return empty()
    for k, v in empty().items():
        s.setdefault(k, v)
    return s


def save(state, path=PATH):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=1, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


def row_id(lane, role, event):
    return f"{lane}|{role}|{event}"


def cost_of(yes_bid):
    """(NO price paid, fee, cost per contract) at the quote: NO costs 1 minus the YES bid, taker fee from fillsim (honest-v1)."""
    p = round(1.0 - yes_bid, 4)
    fee = fillsim.fee(p)
    return p, fee, round(p + fee, 5)


def make_row(lane, role, series, stn, name, event, day, q, idx, fav_i, book, now, forecast=None, above=None):
    m, bid, ask = q[idx]
    p, fee, cost = cost_of(bid)
    row = dict(id=row_id(lane, role, event), lane=lane, role=role, series=series, city=name, station=stn, event=event, day=day.isoformat(),
               ticker=m["ticker"], bracket=m.get("yes_sub_title") or m["ticker"], yes_bid=bid, yes_ask=ask, price=p, fee=fee, cost=cost,
               depth_bid=best_bid_depth(book, bid), favourite=q[fav_i][0]["ticker"], favourite_bracket=q[fav_i][0].get("yes_sub_title"),
               favourite_mid=round((q[fav_i][1] + q[fav_i][2]) / 2, 4), rel=idx - fav_i, logged=now.astimezone(UTC).isoformat(),
               lag_min=lag_min(now), quotes=[[x[0]["ticker"].rsplit("-", 1)[-1], x[1], x[2]] for x in q],
               status="open", won=None, roi=None, version=VERSION)
    if forecast is not None or above is not None:
        row["forecast"] = forecast
        row["forecast_above"] = above
    return row


def enter_city(state, lane, series, now, fetch, shifts, nbs_cache, text_fetch):
    """One city's read for one lane: appends rows, or notes why not. A transient fetch failure raises (retried in the window)."""
    cfg = LANES[lane]
    name, stn = cfg["series"][series]
    day = target_day(now)
    event = event_ticker(series, day)
    key = f"{lane}|{event}"
    have = {r["id"] for r in state["rows"]}
    if key in state["skips"] or any(row_id(lane, role, event) in have for role in ("main", "skipped", "control")):
        return 0
    d = fetch(f"markets?event_ticker={event}&limit=20")
    markets = d.get("markets") if isinstance(d, dict) else None
    if not isinstance(markets, list):
        raise ValueError("no markets list")
    if not markets:
        state["skips"][key] = "no ladder listed"
        return 0
    q = quotes_of(markets)
    if q is None:
        state["skips"][key] = "fewer than six brackets quoted"
        return 0
    fav_i = favourite(q)
    add = []
    book = {}

    def pick(rel):
        i = fav_i + rel
        return i if 0 <= i < len(q) and q[i][1] > 0 else None

    def depth(i):
        t = q[i][0]["ticker"]
        if t not in book:
            try:
                book[t] = fetch(f"markets/{t}/orderbook")
            except Exception:                                   # noqa: BLE001  depth is a log, never a gate
                book[t] = None
        return book[t]

    i_main, i_ctl = pick(cfg["side"]), pick(cfg["control_side"])
    if i_main is None:
        state["skips"][key] = "no bracket two away, or its YES bid is 0"
    else:
        fc, above = None, None
        if cfg["forecast"]:
            try:
                if stn not in nbs_cache:
                    nbs_cache[stn] = parse_nbs(text_fetch(iem_url(stn, now)))
                fc = forecast_high(nbs_cache[stn], stn, day, now)
            except Exception as exc:                            # noqa: BLE001  no forecast: take the bet, mark the row
                fc = None
                nbs_cache[stn] = {}
                state.setdefault("forecast_errors", {})[event] = str(exc)[:80]
            if fc is not None:
                fc = dict(fc, shift=shifts.get(stn, 0.0))
            above = forecast_above(fc, shifts, stn, q[fav_i][0])
            if fc is None:
                fc = dict(value=None, note="no forecast")
        role = "skipped" if above else "main"
        add.append(make_row(lane, role, series, stn, name, event, day, q, i_main, fav_i, depth(i_main), now, fc, above))
    if i_ctl is not None:
        add.append(make_row(lane, "control", series, stn, name, event, day, q, i_ctl, fav_i, depth(i_ctl), now))
    state["rows"].extend(add)
    return len(add)


def run(state, now=None, fetch=D.get, text_fetch=get_text, force=False):
    """The 10 pm ET read for tomorrow's ladders, then grade whatever has settled."""
    now = now or dt.datetime.now(UTC)
    errors = []
    if force or in_window(now):
        night = target_day(now).isoformat()
        info = state["nights"].setdefault(night, dict(first_run=now.astimezone(UTC).isoformat(), lag_min=lag_min(now), rows=0, errors=[]))
        shifts, cache = load_shifts(), {}
        if state["since"] is None:
            state["since"] = night
        for lane, cfg in LANES.items():
            for series in cfg["series"]:
                try:
                    info["rows"] += enter_city(state, lane, series, now, fetch, shifts, cache, text_fetch)
                except Exception as exc:                        # noqa: BLE001
                    errors.append(f"{lane} {series}: {str(exc)[:70]}")
        info["errors"] = errors[:20]
    errors += grade(state, now, fetch)
    state["rows"].sort(key=lambda r: (r["day"], r["lane"], r["role"], r["series"]))
    state["last_run"] = now.astimezone(UTC).isoformat()
    state["error"] = "; ".join(errors)[:600] or None
    return state


def grade(state, now, fetch):
    """Settle every open row whose event has a result for its bracket."""
    errors, events = [], {}
    for r in state["rows"]:
        if r["status"] == "open" and r["day"] < (now.astimezone(UTC).date()).isoformat():
            events.setdefault(r["event"], []).append(r)
    for event, rows in sorted(events.items()):
        try:
            ms = fetch(f"markets?event_ticker={event}&limit=20")["markets"]
        except Exception as exc:                                # noqa: BLE001
            errors.append(f"grade {event}: {str(exc)[:60]}")
            continue
        res = {m["ticker"]: m.get("result") for m in ms}
        for r in rows:
            if res.get(r["ticker"]) in ("yes", "no"):
                won = res[r["ticker"]] == "no"
                r["status"], r["won"] = "settled", won
                r["roi"] = round((1.0 / r["cost"] - 1.0) if won else -1.0, 4)
                r["settled_logged"] = now.astimezone(UTC).isoformat()
    return errors


# ------------------------------------------------------------------ the record
def stats(rows):
    """Settled rows -> n, wins, mean return after fees, t (city-day = one outcome), median depth, share under 10 at the bid."""
    done = [r for r in rows if r["status"] == "settled"]
    n = len(done)
    out = dict(n=n, open=len(rows) - n, won=sum(1 for r in done if r["won"]), roi=None, t=None, priced=None, depth=None, thin=None)
    if not n:
        return out
    xs = [r["roi"] for r in done]
    mean = sum(xs) / n
    out.update(roi=mean, priced=sum(r["price"] for r in done) / n)
    if n >= 3:
        var = sum((x - mean) ** 2 for x in xs) / (n - 1)
        out["t"] = mean / math.sqrt(var / n) if var > 0 else None
    ds = sorted(r["depth_bid"] for r in rows if r.get("depth_bid") is not None)
    if ds:
        out["depth"] = ds[len(ds) // 2]
        out["thin"] = sum(1 for x in ds if x < 10) / len(ds)
    return out


def lane_record(state, lane):
    rows = [r for r in state["rows"] if r["lane"] == lane]
    by = lambda role: [r for r in rows if r["role"] == role]      # noqa: E731
    cfg = LANES[lane]
    main, ctl, skipped = stats(by("main")), stats(by("control")), stats(by("skipped"))
    return dict(lane=lane, label=cfg["label"], main=main, control=ctl, skipped=skipped, read_at=cfg["read_at"], early_n=cfg["early_n"],
                read=read_text(lane, main, ctl, skipped), days=len({r["day"] for r in rows}))


def read_text(lane, main, ctl, skipped):
    """The pre-registered read: once at read_at settled bets; early review below -3% at early_n. Nothing is decided before."""
    cfg = LANES[lane]
    n = main["n"]
    if n >= cfg["read_at"]:
        beats = main["roi"] is not None and main["roi"] > 0 and (ctl["roi"] is None or main["roi"] > ctl["roi"])
        text = "read now: keep (return above zero and above the control)" if beats else "read now: retire (zero or below, or not above the control)"
        if lane == "c1v2" and skipped["n"] and skipped["roi"] is not None and main["roi"] is not None and skipped["roi"] > main["roi"]:
            text += "; the skipped bets returned more: go back to version 1 on the same record"
        return text
    if n >= cfg["early_n"] and main["roi"] is not None and main["roi"] < EARLY_STOP:
        return f"early review: return below −3% at {cfg['early_n']} settled bets"
    return f"too early ({n} of {cfg['read_at']} settled bets; read once at {cfg['read_at']})"


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    state = load()
    before = json.dumps({k: v for k, v in state.items() if k not in ("last_run", "error")}, sort_keys=True)
    old = (state.get("last_run"),)
    state = run(state, force="--force" in argv)
    if before == json.dumps({k: v for k, v in state.items() if k not in ("last_run", "error")}, sort_keys=True):
        state["last_run"] = old[0]          # nothing new to record: leave the file alone so the run commits nothing
    save(state)
    for lane in LANES:
        r = lane_record(state, lane)
        print(f"{lane}: {r['main']['n']} settled, {r['main']['open']} open, control {r['control']['n']}; {r['read']}")
    print(f"error: {state['error']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
