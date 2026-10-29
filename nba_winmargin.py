#!/usr/bin/env python3
"""NBA win margin tracker (2026-10-29): an OBSERVATION record of Kalshi's NBA win-margin buckets.

Observation only. No buying or selling rule, no orders, no executor, no Production feed.

Why it exists: a research pass on 2026-10-28 found that KXNBAWINMARGIN bucket contracts ("Boston
wins by 1-5 points") priced 5-35c an hour before the tip traded at 2x their entry ask far more
often than a fair price implies. A fair contract bought at ask a touches 2a about half the time
(a/2a), 3a a third of the time and 5a a fifth. This file keeps the evidence growing, game by game.

For every settled 2026-27 NBA game (from opening night, 2026-10-20) it keeps, in
data/nba_winmargin_tracker.json:
  * all eight bucket markets (each team x 1-5, 6-10, 11-20, 21+) with Kalshi's settled result;
  * the tip: the matching KXNBAGAME market's expected_expiration_time minus 3 hours (verified
    against the 2026-27 tips);
  * the entry quote 1 hour before the tip: the YES bid and ask closing the last 1-minute event
    candle that ended at or before tip - 1h (entry = the ask);
  * every trade print from tip - 1h to settlement, reduced to per-contract metrics (below) and,
    for the summary population, a per-minute path (the highest print of each minute);
  * the conditions: bucket, the bucket team's pregame win share (that team's bucket mids summed at
    the entry, normalised over both teams; favourite >= 55%, underdog < 45%, toss-up between),
    entry band (5-10c, 10-20c, 20-35c) and home/away (home = the last three letters of the event
    suffix, KXNBAWINMARGIN-26OCT26GSWDEN -> DEN).

Metrics, from trade prints at or after the entry only:
  peak         the highest print / the ask;
  r2/r3/r5     a print at >= 2x / 3x / 5x the ask (3x and 5x are only possible below 33c / 20c);
  first2       minutes from the tip to the first print >= 2x (negative = before the tip);
  above2       minutes at >= 2x, a step function: each print at >= 2x holds until the next print,
               the last print holds one minute;
  vol2         contracts traded at prints >= 2x;
  won          Kalshi settled YES; won_minus_ask = won - ask (per contract, in dollars).
The summary population is an entry ask of 5-35c with a bid-ask spread of 5c or less.
"""
import datetime as dt
import json
import os
import re
import urllib.parse

import daily_track as D

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "data", "nba_winmargin_tracker.json")
VERSION = "nba-winmargin-v1"
SERIES, GAME_SERIES = "KXNBAWINMARGIN", "KXNBAGAME"
SEASON_START = dt.date(2026, 10, 20)
TIP_FROM_EXPIRY = dt.timedelta(hours=3)
ENTRY_BEFORE = dt.timedelta(hours=1)
CANDLE_LOOKBACK = dt.timedelta(hours=6)    # an unchanged book prints no candle; look back for the last one
GIVE_UP = dt.timedelta(days=3)
POP_LO, POP_HI, POP_SPREAD = 0.05, 0.35, 0.05
BUCKETS = ("1-5", "6-10", "11-20", "21+")
FAV, DOG = 0.55, 0.45
EPS = 1e-9
MONTHS = {m: i for i, m in enumerate(("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT",
                                      "NOV", "DEC"), 1)}


def empty():
    return {"version": VERSION, "season_start": SEASON_START.isoformat(), "games": {}, "runs": []}


def load(path=PATH):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return empty()


def save(state, path=PATH):
    """One game per line (compact) so a season stays a few MB and a nightly diff is a few lines."""
    tmp = path + ".tmp"
    games = state.get("games") or {}
    rest = {k: v for k, v in state.items() if k != "games"}
    with open(tmp, "w") as f:
        f.write("{\n \"games\": {")
        f.write(",".join(f"\n  {json.dumps(k)}: {json.dumps(games[k], sort_keys=True, separators=(',', ':'))}"
                         for k in sorted(games)))
        f.write("\n }")
        for k in sorted(rest):
            f.write(f",\n {json.dumps(k)}: {json.dumps(rest[k], sort_keys=True)}")
        f.write("\n}\n")
    os.replace(tmp, path)


# ---------- tickers ----------

def suffix_of(event_ticker):
    return str(event_ticker or "").split("-", 1)[-1]


def game_date(suffix):
    """26OCT26GSWDEN -> 2026-10-26 (the ET game date in Kalshi's ticker), else None."""
    m = re.match(r"(\d\d)([A-Z]{3})(\d\d)", suffix or "")
    if not m or m.group(2) not in MONTHS:
        return None
    try:
        return dt.date(2000 + int(m.group(1)), MONTHS[m.group(2)], int(m.group(3)))
    except ValueError:
        return None


def teams_of(suffix):
    """(away, home) from 26OCT26GSWDEN: the last three letters are the home team."""
    tag = re.sub(r"^\d\d[A-Z]{3}\d\d", "", suffix or "")
    return (tag[:-3], tag[-3:]) if len(tag) >= 6 else (None, None)


def bucket_of(m):
    """'1-5' / '6-10' / '11-20' / '21+' from the ticker's last part (LAL1TO5, LAL21PLUS)."""
    last = str(m.get("ticker") or "").rsplit("-", 1)[-1]
    x = re.match(r"([A-Z]+)(\d+)(?:TO(\d+)|(PLUS))$", last)
    if not x:
        return None, None
    lo, hi = x.group(2), x.group(3)
    return x.group(1), (f"{lo}-{hi}" if hi else f"{lo}+")


def band_of(ask):
    return "5-10c" if ask < 0.10 - EPS else "10-20c" if ask < 0.20 - EPS else "20-35c"


def side_of(share):
    if share is None:
        return None
    return "favourite" if share >= FAV - EPS else "underdog" if share < DOG - EPS else "toss-up"


def in_population(row):
    b, a = row.get("bid"), row.get("ask")
    return (a is not None and b is not None and POP_LO - EPS <= a <= POP_HI + EPS and a - b <= POP_SPREAD + EPS)


# ---------- metrics ----------

def metrics(trades, ask, tip_ts, entry_ts):
    """Per-contract metrics from (ts, price, count) prints at or after entry_ts. None without a print."""
    tr = sorted((t, p, c) for t, p, c in trades if t >= entry_ts)
    if not tr or not ask:
        return None
    peak, first, above, vol2 = 0.0, None, 0.0, 0.0
    nxt = [t for t, _, _ in tr[1:]] + [tr[-1][0] + 60]
    for (t, p, c), t2 in zip(tr, nxt):
        peak = max(peak, p)
        if p >= 2 * ask - EPS:
            if first is None:
                first = (t - tip_ts) / 60
            above += (t2 - t) / 60
            vol2 += c
    hit = lambda k: (peak >= k * ask - EPS) if k * ask <= 0.99 + EPS else None   # noqa: E731
    return dict(peak=round(peak / ask, 3), r2=peak >= 2 * ask - EPS, r3=hit(3), r5=hit(5),
                first2=None if first is None else round(first, 1), above2=round(above, 1),
                vol2=round(vol2, 2), prints=len(tr))


def path_of(trades, tip_ts, entry_ts):
    """[[minute from tip, highest print that minute in cents], ...] from the entry on."""
    by = {}
    for t, p, _ in trades:
        if t >= entry_ts:
            k = int((t - tip_ts) // 60)
            by[k] = max(by.get(k, 0), round(p * 100))
    return [[k, by[k]] for k in sorted(by)]


# ---------- Kalshi ----------

def settled_events(fetch=D.get):
    return D.pages(f"events?series_ticker={SERIES}&status=settled&limit=200", "events", fetch)


def tip_of(suffix, fetch=D.get):
    ms = (fetch(f"markets?event_ticker={GAME_SERIES}-{suffix}&limit=5") or {}).get("markets") or []
    exp = [D.instant(m.get("expected_expiration_time")) for m in ms]
    exp = [e for e in exp if e]
    return (min(exp) - TIP_FROM_EXPIRY) if exp else None


def entry_quotes(cs, entry_ts):
    """{ticker: (bid, ask)} closing the last 1-minute candle that ended at or before entry_ts."""
    out = {}
    for tk, candles in zip(cs.get("market_tickers") or [], cs.get("market_candlesticks") or []):
        last = None
        for c in sorted((c for c in candles or [] if isinstance(c.get("end_period_ts"), (int, float))),
                        key=lambda c: c["end_period_ts"]):
            if c["end_period_ts"] <= entry_ts:
                last = c
            else:
                break
        if last is None:
            continue
        b = D.number((last.get("yes_bid") or {}).get("close_dollars"))
        a = D.number((last.get("yes_ask") or {}).get("close_dollars"))
        if b is not None and a is not None and a > 0:
            out[tk] = (round(b, 4), round(a, 4))
    return out


def trades_of(ticker, min_ts, fetch=D.get):
    rows = D.pages(f"markets/trades?ticker={urllib.parse.quote(ticker, safe='')}&min_ts={int(min_ts)}&limit=1000",
                   "trades", fetch)
    out = []
    for y in rows:
        t, p = D.instant(y.get("created_time")), D.number(y.get("yes_price_dollars"))
        if t is None or p is None:
            continue
        out.append((int(round(t.timestamp())), p, D.number(y.get("count_fp")) or 0.0))
    return sorted(out)


def shares(rows):
    """{team: pregame win share}: each team's bucket mids summed at the entry, normalised."""
    s = {}
    for r in rows:
        if r.get("bid") is not None and r.get("ask") is not None:
            s[r["team"]] = s.get(r["team"], 0.0) + (r["bid"] + r["ask"]) / 2
    tot = sum(s.values())
    return {k: round(v / tot, 4) for k, v in s.items()} if tot > 0 else {}


def track_game(event_ticker, fetch=D.get):
    """One settled game's record, or None when its tip or markets cannot be read."""
    suffix = suffix_of(event_ticker)
    tip = tip_of(suffix, fetch)
    if tip is None:
        return None
    ms = D.pages(f"markets?event_ticker={urllib.parse.quote(event_ticker, safe='')}&limit=200", "markets", fetch)
    if not ms:
        return None
    tip_ts = int(tip.timestamp())
    entry_ts = tip_ts - int(ENTRY_BEFORE.total_seconds())
    cs = fetch(f"series/{SERIES}/events/{urllib.parse.quote(event_ticker, safe='')}/candlesticks"
               f"?start_ts={entry_ts - int(CANDLE_LOOKBACK.total_seconds())}&end_ts={entry_ts}&period_interval=1")
    q = entry_quotes(cs or {}, entry_ts)
    away, home = teams_of(suffix)
    rows = []
    for m in ms:
        team, bucket = bucket_of(m)
        if bucket is None:
            continue
        bid, ask = q.get(m["ticker"], (None, None))
        res = D.payout(m)
        rows.append(dict(ticker=m["ticker"], team=team, name=m.get("yes_sub_title"), bucket=bucket,
                         home=team == home, bid=bid, ask=ask,
                         result=None if res is None else ("yes" if res == 1 else "no" if res == 0 else "void")))
    sh = shares(rows)
    for r in rows:
        r["share"] = sh.get(r["team"])
        r["side"] = side_of(r["share"])
        r["band"] = band_of(r["ask"]) if r["ask"] is not None else None
        r["pop"] = in_population(r)
        r["m"] = None
        if r["ask"] is None:
            continue
        tr = trades_of(r["ticker"], entry_ts, fetch)
        r["m"] = metrics(tr, r["ask"], tip_ts, entry_ts)
        if r["result"] in ("yes", "no"):
            r["won_minus_ask"] = round((1.0 if r["result"] == "yes" else 0.0) - r["ask"], 4)
        if r["pop"]:
            r["path"] = path_of(tr, tip_ts, entry_ts)
    rows.sort(key=lambda r: (not r["home"], BUCKETS.index(r["bucket"]) if r["bucket"] in BUCKETS else 9))
    d = game_date(suffix)
    return dict(event=event_ticker, night=d.isoformat() if d else None, tip=tip.isoformat(), away=away, home=home,
                rows=rows, settled=all(r["result"] is not None for r in rows), version=VERSION)


def run(state, now=None, fetch=D.get, limit=None):
    """Track every settled game since opening night not yet final in the ledger. Returns new event tickers."""
    now = now or dt.datetime.now(dt.timezone.utc)
    games = state.setdefault("games", {})
    errs, new = [], []
    try:
        evs = settled_events(fetch)
    except Exception as e:                                      # noqa: BLE001
        evs = []
        errs.append(f"events: {str(e)[:80]}")
    todo = []
    for e in evs:
        ev = e.get("event_ticker")
        d = game_date(suffix_of(ev))
        if not ev or d is None or d < SEASON_START or (games.get(ev) or {}).get("final"):
            continue
        todo.append((d, ev))
    for _, ev in sorted(todo)[:limit]:
        try:
            g = track_game(ev, fetch)
        except Exception as e:                                  # noqa: BLE001
            errs.append(f"{ev}: {str(e)[:80]}")
            continue
        if g is None:
            errs.append(f"{ev}: no tip or markets")
            continue
        late = now - D.instant(g["tip"]) > GIVE_UP
        g["final"] = bool(g["settled"] or late)
        g["tracked"] = now.isoformat()
        games[ev] = g
        new.append(ev)
    state["version"] = VERSION
    state["last_run"] = now.isoformat()
    state["error"] = "; ".join(errs)[:1000] or None
    state["runs"] = (state.get("runs") or [])[-50:] + [dict(at=now.isoformat(), new=len(new), games=len(games))]
    return new


# ---------- summaries (the NBA page reads these) ----------

def population(state):
    """Every summary-population row, oldest tip first, with its game's night and tip attached."""
    out = []
    for g in sorted((state.get("games") or {}).values(), key=lambda g: (g.get("tip") or "", g.get("event") or "")):
        for r in g.get("rows") or []:
            if r.get("pop") and r.get("m") and r.get("result") in ("yes", "no"):
                out.append(dict(r, night=g.get("night"), tip=g.get("tip"), event=g.get("event")))
    return out


def _median(xs):
    xs = sorted(xs)
    if not xs:
        return None
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


def stats(rows):
    """The summary numbers for one group of population rows."""
    n = len(rows)
    if not n:
        return dict(n=0)
    m = [r["m"] for r in rows]
    hit = [x for x in m if x["r2"]]
    p3 = [x for x in m if x["r3"] is not None]
    p5 = [x for x in m if x["r5"] is not None]
    return dict(n=n, ask=sum(r["ask"] for r in rows) / n,
                r2=len(hit) / n,
                r3=sum(x["r3"] for x in p3) / len(p3) if p3 else None, n3=len(p3),
                r5=sum(x["r5"] for x in p5) / len(p5) if p5 else None, n5=len(p5),
                held10=sum(x["above2"] >= 10 for x in m) / n,
                first2=_median([x["first2"] for x in hit]),
                above2=_median([x["above2"] for x in hit]),
                vol2=_median([x["vol2"] for x in hit]),
                won=sum(r["result"] == "yes" for r in rows) / n,
                won_minus_ask=sum(r["won_minus_ask"] for r in rows) / n)


def group(rows, key, order):
    out = []
    for k in order:
        sel = [r for r in rows if key(r) == k]
        if sel:
            out.append((k, stats(sel)))
    return out


def halves(rows):
    """(older, newer) halves of a list already in tip order; the odd row goes to the newer half."""
    h = len(rows) // 2
    return rows[:h], rows[h:]


def last_night(state):
    games = [g for g in (state.get("games") or {}).values() if g.get("night")]
    if not games:
        return None, []
    night = max(g["night"] for g in games)
    return night, sorted((g for g in games if g["night"] == night), key=lambda g: (g.get("tip") or "", g["event"]))


def summary(state):
    gs = state.get("games") or {}
    return dict(games=len(gs), final=sum(1 for g in gs.values() if g.get("final")), population=len(population(state)))


def main(argv=None):
    state = load()
    new = run(state)
    save(state)
    print("win margin tracker", summary(state), "new", len(new), "error", state["error"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
