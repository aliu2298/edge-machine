#!/usr/bin/env python3
"""Two display-only WATCH splits on the Production row "Favourite band, below · No 0.70-0.80" (crypto_fav_band_below).
Added Nov 13 2026 by Olu ("add the two splits"). Not rules: nothing here selects, sizes or places a bet, and no feed, follower or server
changes. Each is read at 30 days, from Nov 13 2026, and the full record sits beside them as background, marked not counted.

  Weekend v weekday   the CLOSE date in Eastern time: Saturday or Sunday v Monday to Friday.
  Quiet v busy day    Fable's definition (docs/crypto_lanes_review_2026-11-12.md, research ~/edge-research/crypto_2026-11-12/analyse.py, C4),
                      copied: the range (highest minus lowest) of the picked rung's own NO mid over the five hours before entry, from the
                      hourly quotes 3, 4, 5, 6, 7 and 8 hours before the close (NO mid = 1 minus the YES mid of the hourly candle at that
                      hour; at least 4 of the 6 must exist), quiet when that range is at or below QUIET_MAX, busy when above. QUIET_MAX is
                      the research's median over its first period (Jun 1 to Aug 10, 51 picks), fixed and never refitted.
                      KNOWN AT ENTRY: yes. Every quote is from the hour of the entry quote or earlier (the lane enters about 2.8 hours before
                      the close; the quote nearest to it is the one 3 hours before), so nothing here needs the future.

The ranges are read from Kalshi's hourly candles by this module (run from .github/workflows/crypto-watch.yml) into
data/crypto_watch_ledger.json; the page builder makes no venue call and only reads that file. A market-day is one outcome and
returns are after fees, as the row counts them (sandbox_track.assess on the subset). Paper bookkeeping only.
"""
import datetime as dt
import json
import os
import re
import sys
import urllib.parse
from zoneinfo import ZoneInfo

import daily_track as D
import sandbox_track as T

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "data", "crypto_watch_ledger.json")
LANE = "crypto_fav_band_below"
SPORT = "crypto_fav"
ET = ZoneInfo("America/New_York")
UTC = dt.timezone.utc
WATCH_FROM = "2026-11-13"                 # only bets whose close day is on or after this count
READ_DAYS = 30
QUIET_MAX = 0.32999999999999996           # the research's period-A median (0.33), the exact float the research compared with
HOURS = (3, 4, 5, 6, 7, 8)                # hourly quotes this many hours before the close
MIN_QUOTES = 4
NOTE = "Two watches added Nov 13 by Olu; read at 30 days each."
SPLITS = (("weekend", "Weekend close (Sat, Sun)"), ("weekday", "Weekday close (Mon to Fri)"),
          ("quiet", "Quiet day"), ("busy", "Busy day"))
TICKER_RE = re.compile(r"-(\d\d)([A-Z]{3})(\d\d)(\d\d)(?:-|$)")
MONTHS = {m: i + 1 for i, m in enumerate("JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split())}


def close_of(ticker):
    """The 17:00 ET close of a coin ladder ticker (KXETHD-26NOV1317-T1959.99), as a UTC instant, or None."""
    m = TICKER_RE.search(str(ticker or ""))
    if not m or m.group(2) not in MONTHS:
        return None
    y, mon, d, h = 2000 + int(m.group(1)), MONTHS[m.group(2)], int(m.group(3)), int(m.group(4))
    return dt.datetime(y, mon, d, h, 0, tzinfo=ET).astimezone(UTC)


def is_weekend(close):
    return close.astimezone(ET).weekday() >= 5


# ---------------------------------------------------------------- the picked rung's quiet range
def candles(ticker, lo, hi, fetch):
    """([(end ts, yes bid, yes ask)], historical?) of the rung's hourly candles, live endpoint first, then the archive."""
    series = str(ticker).split("-", 1)[0]
    tk = urllib.parse.quote(ticker, safe="")
    for path, hist in ((f"series/{series}/markets/{tk}/candlesticks", False), (f"historical/markets/{tk}/candlesticks", True)):
        try:
            cs = fetch(f"{path}?start_ts={int(lo)}&end_ts={int(hi)}&period_interval=60").get("candlesticks") or []
        except Exception:                                       # noqa: BLE001
            continue
        if cs:
            def px(c, k):
                x = c.get(k) or {}
                return D.number(x.get("close_dollars", x.get("close")))
            return [(c.get("end_period_ts"), px(c, "yes_bid"), px(c, "yes_ask")) for c in cs], hist
    return [], False


def quote(cs, t, carry):
    """(yes bid, yes ask) of the hourly candle ending at t; with carry (an archived market's sparse candles), the last one before t."""
    best = None
    for e, b, a in cs:
        if e and e <= t + 60 and (carry or e > t - 3600 - 60) and b is not None and a is not None:
            best = (b, a)
    return best


def quiet_range(cs, close_ts, carry=False):
    """The range of the rung's NO mid over the hourly quotes 3 to 8 hours before the close, or None under 4 quotes."""
    mids = []
    for h in HOURS:
        q = quote(cs, close_ts - h * 3600, carry)
        if q:
            mids.append(1 - (q[0] + q[1]) / 2)
    return None if len(mids) < MIN_QUOTES else max(mids) - min(mids)


def load(path=PATH):
    try:
        with open(path) as f:
            s = json.load(f)
    except (OSError, ValueError):
        s = {}
    s.setdefault("rungs", {})
    s.update(version="cwatch-v1", lane=LANE, watch_from=WATCH_FROM, quiet_max=QUIET_MAX)
    return s


def save(state, path=PATH):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=1, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


def lane_bets(d):
    return [q for q in T.bet_rows(d) if q.get("source") == LANE]


def run(state, d, now=None, fetch=D.get, cap=80):
    """Read the range of every bet's rung once, after the hour of its entry quote (close - 3h) is final."""
    now = now or dt.datetime.now(UTC)
    done = errs = 0
    for q in lane_bets(d):
        t = q.get("market_id")
        close = close_of(t)
        if close is None or t in state["rungs"] or now < close - dt.timedelta(hours=3) + dt.timedelta(minutes=5):
            continue
        if done >= cap:
            break
        ct = close.timestamp()
        try:
            cs, hist = candles(t, ct - 9 * 3600, ct - 3 * 3600 + 60, fetch)
        except Exception:                                       # noqa: BLE001
            errs += 1
            continue
        state["rungs"][t] = dict(range=quiet_range(cs, ct, hist), close=close.isoformat(), read=now.isoformat(timespec="seconds"),
                                 quotes=sum(1 for h in HOURS if quote(cs, ct - h * 3600, hist)))
        done += 1
    state["last_run"] = now.isoformat(timespec="seconds")
    state["errors"] = errs
    return done


# ---------------------------------------------------------------- the splits
def split_of(q, state):
    """{weekend|weekday, quiet|busy|None} for one bet of the lane."""
    close = close_of(q.get("market_id"))
    rng = (state["rungs"].get(q.get("market_id")) or {}).get("range")
    return dict(day=None if close is None else ("weekend" if is_weekend(close) else "weekday"),
                calm=None if rng is None else ("quiet" if rng <= QUIET_MAX else "busy"))


def records(d, state, counted=True):
    """{split: assess-record} for the four splits. counted=True: bets whose close day is on or after WATCH_FROM; False: the full
    record, background only. Each subset goes through sandbox_track.assess (a market-day is one outcome, after fees)."""
    bets = lane_bets(d)
    out = {}
    for key, _label in SPLITS:
        pick = []
        for q in bets:
            s = split_of(q, state)
            if key in (s["day"], s["calm"]) and (not counted or str(q.get("date") or "")[:10] >= WATCH_FROM):
                pick.append(q)
        sub = dict(quotes=pick, meta={}, coverage={}, _archive=[])
        a = T.assess(sub, LANE, SPORT) if pick else None
        out[key] = dict(n=a["n"], won=a["won"], expected=a["expected"], roi_fee=a["roi_fee"], bets=len(pick), open=sum(1 for q in pick if q.get("status") == "open")) if a else dict(n=0, won=0, expected=0.0, roi_fee=None, bets=0, open=0)
    return out


# ---------------------------------------------------------------- the page block
def _pct(v):
    return "—" if v is None else f"{v * 100:+.1f}%".replace("-", "−")


def block(d, state=None):
    """The closed fold inside the lane's row: two watch splits (counted from Nov 13) with the full record beside them, not counted."""
    import html as _h
    state = state if state is not None else load()
    mine, full = records(d, state, True), records(d, state, False)
    q = lambda x: _h.escape(str(x))                              # noqa: E731
    days = (dt.datetime.now(UTC).date() - dt.date.fromisoformat(WATCH_FROM)).days + 1
    rd = (dt.date.fromisoformat(WATCH_FROM) + dt.timedelta(days=READ_DAYS)).strftime("%b %-d")

    def cells(r):
        return (f'<td class="num">{r["n"]}</td><td class="num">{r["won"]}</td><td class="num">{_pct(r["roi_fee"])}</td>')
    rows = "".join(f'<tr><td>{q(label)}</td>{cells(mine[k])}<td class="num mut">{mine[k]["open"]}</td>{cells(full[k]).replace("class=\"num\"", "class=\"num mut\"")}</tr>'
                   for k, label in SPLITS)
    head = ('<thead><tr><th>Split</th><th class="num">Market-days</th><th class="num">Won</th><th class="num">Return after fees</th>'
            '<th class="num">Open</th><th class="num mut">Market-days</th><th class="num mut">Won</th><th class="num mut">Return after fees</th></tr></thead>')
    unclassified = sum(1 for qq in lane_bets(d) if split_of(qq, state)["calm"] is None)
    return (f'<details class="fold cwatch"><summary>Watch, not a rule · weekend v weekday · quiet v busy day</summary>'
            f'<p class="sm">{q(NOTE)} Counted from {q(WATCH_FROM)} ({days} day{"s" if days != 1 else ""} so far); each is read on {q(rd)}. Nothing here changes the '
            f'rule, the entry or the stake. The columns on the right are the full record since the lane began, shown as background and not counted.</p>'
            f'<div class="tbl"><table>{head}<tbody>{rows}</tbody></table></div>'
            f'<p class="sm mut"><b>Weekend v weekday:</b> the close date in Eastern time, Saturday and Sunday against Monday to Friday. '
            f'<b>Quiet v busy:</b> the picked rung\'s own No price (mid of the hourly quote) moved {QUIET_MAX * 100:.0f} points or less across the five '
            f'hours up to the entry, from the hourly quotes 3 to 8 hours before the close, at least 4 of the 6 present. That cut is the median of the first '
            f'research period (Jun 1 to Aug 10), fixed. It uses only quotes from before the entry, so it is known at entry. A market-day counts once; a day with a quiet '
            f'coin and a busy one appears in both rows, so the two rows do not add up to the lane. {unclassified} bet{"s" if unclassified != 1 else ""} '
            f'had too few hourly quotes to classify.</p></details>')


def main():
    state = load()
    d = T.load()
    n = run(state, d)
    save(state)
    print(f"crypto_watch: {n} new rungs read, {len(state['rungs'])} in all, {state['errors']} errors")
    return 0


if __name__ == "__main__":
    sys.exit(main())
