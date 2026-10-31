"""arg_goalless_dip: Argentina, buy the goalless dip on over 0.5 (2026-10-30, Olu). Sandbox PAPER.

THE RULE, pre-registered before the first entry (2026-10-31):
  market   Kalshi KXARGPREMDIVTOTAL, the over 0.5 rung (floor_strike 0.5), every league match.
  kickoff  the market's occurrence_datetime minus 4 hours (verified for Kalshi soccer).
  P        the pregame YES ask an hour before kickoff, from 1-minute candles (the last minute quote at or
           before that time), with a spread of 5c or less, and only if that ask passes the entry-validity
           check (mentions_split, 2026-10-30): 10+ contracts traded at or through it within 60 minutes after,
           and not under half the last trade before it. A match without such a P is skipped.
  BUY      a resting YES buy at round(0.65 x P, 2) from kickoff (the HEADLINE; 0.75 x P and 0.55 x P are
           tracked on the same matches). It fills when a trade prints at or below the limit after kickoff.
           A replay reads the match after the fact, so the book at the fill cannot be read: the fill counts
           only when 10+ contracts printed at or below the limit within 60 minutes of the first touch (the
           print rule of the entry-validity check); fewer is a "thin touch", recorded and not counted.
  SELL     a resting sell at P placed at the fill. It fills when a later trade prints at or above P; else
           the position settles (1 if over 0.5, 0 if the match ends 0-0).
  FEES     maker 0.0175 p(1-p) in and out (both orders rest); nothing at settlement.
  CONTROL  the same fills held to settlement. An unfilled buy is "no fill" and costs nothing.
  READ     an outcome is a MATCH; z is clustered by matchday (the date in the event ticker). ROI is the mean
           per fill (equal stake). Review at 10 filled matches, decide at 30.

RECORD: fresh from 2026-10-31, the first Argentine matchday after the lane was built. The research behind it
(209 matches, 2026-01-15 to 2026-10-29: buy at 65% +22.3% per fill, z +2.8) is IN-SAMPLE: it is replayed once
by this code (python3 arg_dip.py --backfill) into state["insample"], shown once and labelled, and never
counted in the record. Research files: ~/edge-research/arg_o15_exits_2026-10-30/ (dip.py).
OUT OF SAMPLE (2026-10-30): Out-of-sample check, Brasileirão over 0.5 (135 matches, Jan-Oct 2026): the dip buy did NOT replicate (−2% to −22% per fill, z −0.6 to −0.8). Treat this as an Argentina-only watch.

Own ledger data/arg_dip_ledger.json; read hourly by .github/workflows/arg-dip.yml from settled matches.
Paper only: no order is placed, and Production has no executor for resting in-play buys.

THE ENGINE (2026-10-30): the same code runs every goalless-dip lane. A lane is a config dict (ARG below; the
top-5 over 1.5 lane is top5_dip.TOP5): its series, rung, buy fractions, headline, record date, in-sample window,
ledger and whether a fill must also HOLD. Every function takes `cfg` and defaults to ARG, so this lane reads as
it always has.
"""
import datetime as dt
import json
import math
import os
import statistics as stat
import sys

import chaos_replay as C
import daily_track as D
import mentions_split as MS

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "data", "arg_dip_ledger.json")
LANE = "arg_goalless_dip"
LABEL = "Argentina · buy the goalless dip (over 0.5)"
SERIES = "KXARGPREMDIVTOTAL"
STRIKE = 0.5
SINCE = "2026-10-31"
OOS_NOTE = ("Out-of-sample check, Brasileirão over 0.5 (135 matches, Jan-Oct 2026): the dip buy did NOT replicate "
            "(−2% to −22% per fill, z −0.6 to −0.8). Treat this as an Argentina-only watch.")
INSAMPLE = ("2026-01-15", "2026-10-30")
FRACTIONS = (0.65, 0.75, 0.55)
HEADLINE = 0.65
KICKOFF_BACK_H = 4
P_LEAD_MIN = 60
MAX_SPREAD = 0.05
MIN_FILL = MS.MIN_SIZE
FILL_WINDOW_MIN = MS.PRINT_WINDOW_MIN
MAKER = 0.0175
REVIEW_N, DECIDE_N = 10, 30
MAX_EVENTS_PER_RUN = 60
VERSION = "argdip-v1"
EPS = 1e-9
UTC = dt.timezone.utc
# The held-fill rule a lane may switch on (top-5, 2026-10-30): beyond MIN_FILL in FILL_WINDOW_MIN, the low price
# must HOLD: prints at or below the limit span HELD_SPAN_S within HELD_WINDOW_MIN of the first touch, or
# HELD_CONTRACTS+ contracts print there. A brief stray touch a real resting bid would rarely get is "thin".
HELD_WINDOW_MIN = 5
HELD_SPAN_S = 120
HELD_CONTRACTS = 50

ARG = dict(lane=LANE, label=LABEL, series=(SERIES,), strike=STRIKE, since=SINCE, insample=INSAMPLE,
           fractions=FRACTIONS, headline=HEADLINE, path=PATH, version=VERSION, held=False)


def series_of(event):
    """The series an event ticker belongs to (KXEPLTOTAL-26OCT31CFCMUN -> KXEPLTOTAL)."""
    return str(event or "").split("-")[0]


def fee(p):
    return MAKER * p * (1 - p)


def vkey(f):
    return f"{round(f * 100)}"


def _ts(raw):
    t = D.instant(raw)
    return int(t.timestamp()) if t else None


def matchday(event):
    d = C.event_date(event)
    return d.isoformat() if d else None


# ------------------------------------------------------------------ inputs
def prints_of(trades):
    """[(ts, yes price, contracts)] oldest first, from /markets/trades rows."""
    out = []
    for t in trades or []:
        ts, yes, n = _ts(t.get("created_time")), D.number(t.get("yes_price_dollars")), D.number(t.get("count_fp")) or 0.0
        if ts is not None and yes is not None:
            out.append((ts, yes, n))
    return sorted(out)


def fetch_trades(ticker, min_ts, fetch, max_pages=30):
    """The market's trades since min_ts, from the live endpoint or, once archived, the historical one."""
    for base in ("markets/trades", "historical/trades"):
        rows, cur = [], None
        for _ in range(max_pages):
            d = fetch(f"{base}?ticker={ticker}&min_ts={min_ts}&limit=1000" + (f"&cursor={cur}" if cur else ""))
            rows += d.get("trades") or []
            cur = d.get("cursor")
            if not cur or not d.get("trades"):
                break
        if rows:
            return rows
    return []


def pregame_quote(candles, at_ts):
    """(minute end, bid, ask) of the last 1-minute quote at or before at_ts (+1 minute), or None. Archived
    candles carry "close", live ones "close_dollars"."""
    best = None
    for c in sorted(candles or [], key=lambda c: c.get("end_period_ts") or 0):
        end = c.get("end_period_ts")
        if not end or end > at_ts + 60:
            continue
        b, a = C._f(c.get("yes_bid"), "close"), C._f(c.get("yes_ask"), "close")
        if b is not None and a is not None and a > 0:
            best = (end, b, a)
    return best


def p_check(prints, quote_ts, p):
    """The entry-validity check on the pregame ask P, from trade prints: unverified when P is under half the
    last trade before it, else verified only with MIN_SIZE+ contracts traded at or through P (a YES price at
    or under P) within PRINT_WINDOW_MIN minutes after the quote."""
    before = [x for x in prints if x[0] <= quote_ts]
    last = before[-1][1] if before else None
    if last is not None and p < MS.LAST_TRADE_FLOOR * last - EPS:
        return dict(status="unverified", last_trade=last, reason=f"ask {p:.2f} under half the last trade {last:.2f}")
    printed = round(sum(n for t, px, n in prints if quote_ts < t <= quote_ts + MS.PRINT_WINDOW_MIN * 60
                        and px <= p + EPS), 2)
    if printed >= MS.MIN_SIZE:
        return dict(status="verified", how="print", printed=printed, last_trade=last)
    return dict(status="unverified", printed=printed, last_trade=last,
                reason=f"{printed:g} contracts traded at or through the ask within {MS.PRINT_WINDOW_MIN} minutes "
                       f"(under {MS.MIN_SIZE})")


# ------------------------------------------------------------------ the rule
def held_at(live, i, limit):
    """Whether the low price held after the first touch at live[i]: prints at or below the limit span
    HELD_SPAN_S within HELD_WINDOW_MIN of it, or HELD_CONTRACTS+ contracts printed there."""
    t0 = live[i][0]
    w = [x for x in live[i:] if x[0] <= t0 + HELD_WINDOW_MIN * 60 and x[1] <= limit + EPS]
    return (w[-1][0] - t0 >= HELD_SPAN_S) or sum(x[2] for x in w) >= HELD_CONTRACTS - EPS


def evaluate(prints, kickoff, p, result, cfg=None):
    """{fraction key: buy outcome} on one match. None: no print reached the limit after kickoff. A touch
    carries the limit, the first touch, the contracts printed at or below the limit within FILL_WINDOW_MIN
    of it, whether that counts as a fill (MIN_FILL+, and, for a lane with cfg["held"], the low price held),
    and whether the sell at P filled after it."""
    cfg = cfg or ARG
    live = [x for x in prints if x[0] >= kickoff]
    payout = 1.0 if result == "yes" else 0.0
    out = {}
    for f in cfg["fractions"]:
        limit = round(f * p, 2)
        i = next((k for k, x in enumerate(live) if x[1] <= limit + EPS), None) if limit >= 0.02 else None
        if i is None:
            out[vkey(f)] = None
            continue
        t0 = live[i][0]
        vol = round(sum(n for t, px, n in live[i:] if t <= t0 + FILL_WINDOW_MIN * 60 and px <= limit + EPS), 2)
        sold = next((x for x in live[i + 1:] if x[1] >= p - EPS), None)
        counted = vol >= MIN_FILL - EPS
        b = dict(limit=limit, fill_at=t0, fill_print=live[i][1], fill_volume=vol, counted=counted,
                 sold=sold is not None, sold_at=sold[0] if sold else None, payout=payout)
        if cfg.get("held"):
            b["held"] = held_at(live, i, limit)
            b["counted"] = counted and b["held"]
        out[vkey(f)] = b
    return out


def rows_of(entries, f):
    """One row per counted fill at fraction f: ROI per fill after fees, the same fill held, and its matchday."""
    out = []
    for e in entries:
        b = (e.get("buys") or {}).get(vkey(f))
        if not b or not b.get("counted"):
            continue
        cost = b["limit"] + fee(b["limit"])
        proceeds = (e["p"] - fee(e["p"])) if b["sold"] else b["payout"]
        out.append(dict(event=e["event"], day=e["matchday"], kickoff=e["kickoff"], roi=(proceeds - cost) / cost,
                        hold=(b["payout"] - cost) / cost, sold=b["sold"], zero=e["result"] == "no",
                        league=e.get("league")))
    return out


def z_by_day(vals_days):
    """Mean of the matchday means over their standard error, 3+ matchdays; else None."""
    g = {}
    for v, d in vals_days:
        g.setdefault(d, []).append(v)
    m = [stat.mean(x) for x in g.values()]
    if len(m) < 3 or stat.stdev(m) <= 0:
        return None
    return stat.mean(m) / (stat.stdev(m) / math.sqrt(len(m)))


def summary(entries, f):
    """A variant's read over the matches in `entries` (all with a valid P)."""
    rows = sorted(rows_of(entries, f), key=lambda r: r["kickoff"])
    mean = lambda xs: stat.mean(xs) if xs else None
    k = len(rows) // 2
    touched = sum(1 for e in entries if (e.get("buys") or {}).get(vkey(f)))
    return dict(matches=len(entries), fills=len(rows), thin=touched - len(rows),
                fill_rate=len(rows) / len(entries) if entries else None, sold=sum(r["sold"] for r in rows),
                zero=sum(r["zero"] for r in rows), roi=mean([r["roi"] for r in rows]),
                hold=mean([r["hold"] for r in rows]), z=z_by_day([(r["roi"], r["day"]) for r in rows]),
                days=len({r["day"] for r in rows}),
                old=mean([r["roi"] for r in rows[:k]]) if len(rows) >= 4 else None,
                new=mean([r["roi"] for r in rows[k:]]) if len(rows) >= 4 else None)


def status(fills):
    if fills >= DECIDE_N:
        return f"{fills} filled matches · decide now (30 reached)"
    if fills >= REVIEW_N:
        return f"{fills} filled matches · review due (10 reached) · decide at 30"
    return f"{fills} filled match{'' if fills == 1 else 'es'} · review at 10, decide at 30"


# ------------------------------------------------------------------ the ledger
def load(path=None, cfg=None):
    cfg = cfg or ARG
    try:
        with open(path or cfg["path"]) as f:
            s = json.load(f)
    except FileNotFoundError:
        s = {}
    s.setdefault("lane", cfg["lane"])
    s.setdefault("since", cfg["since"])
    s.setdefault("version", cfg["version"])
    s.setdefault("entries", [])
    s.setdefault("seen", {})
    s.setdefault("skips", {})
    s.setdefault("insample", dict(window=list(cfg["insample"]), entries=[], skips={}, built=None))
    return s


def rung(markets, strike):
    return next((m for m in markets if D.number(m.get("floor_strike")) == strike), None)


def over05(markets):
    return rung(markets, STRIKE)


def replay(event, fetch, now, cfg=None):
    """(entry, None) for a settled match, (None, reason) to skip it, or (None, None) while it is not settled."""
    cfg = cfg or ARG
    ms, archived = C.event_markets(event, fetch)
    m = rung(ms, cfg["strike"])
    if m is None:
        return None, f"no over {cfg['strike']:g} market"
    if m.get("status") not in ("finalized", "settled") or m.get("result") not in ("yes", "no"):
        return None, None
    occ = _ts(m.get("occurrence_datetime"))
    if occ is None:
        return None, "no occurrence time"
    kickoff = occ - KICKOFF_BACK_H * 3600
    close = _ts(m.get("close_time"))
    if close is not None and close <= kickoff:
        # a match moved earlier keeps its old occurrence time (Nice v Rennes, 2026-10-30): no pregame quote exists
        return None, "market closed before its listed kickoff (match moved)"
    q_at = kickoff - P_LEAD_MIN * 60
    cs = C.fetch_candles(series_of(event), event, [m], q_at - 30 * 60, q_at + 60, fetch, archived).get(m["ticker"])
    q = pregame_quote(cs, q_at)
    if q is None:
        return None, "no pregame quote an hour before kickoff"
    q_ts, bid, ask = q
    if ask - bid > MAX_SPREAD + EPS:
        return None, f"pregame spread {ask - bid:.2f} over 5c"
    lo, hi = cfg.get("p_range") or (0.0, 1.0)
    if not lo - EPS <= ask <= hi + EPS:
        return None, f"pregame ask {ask:.2f} outside {lo * 100:.0f}-{hi * 100:.0f}c"
    prints = prints_of(fetch_trades(m["ticker"], q_at - 30 * 60, fetch))
    chk = p_check(prints, q_ts, ask)
    base = dict(id=m["ticker"], event=event, title=m.get("title") or event, kickoff=kickoff, matchday=matchday(event),
                result=m["result"], p=ask, p_bid=bid, p_at=q_ts, p_check=chk, prints=len(prints),
                logged=now.isoformat(), version=cfg["version"])
    if len(cfg["series"]) > 1:
        base["league"] = cfg.get("leagues", {}).get(series_of(event), series_of(event))
    if chk["status"] != "verified":
        return dict(base, buys={}), "pregame ask unverified: " + chk["reason"]
    return dict(base, buys=evaluate(prints, kickoff, ask, m["result"], cfg)), None


def run(state, now=None, fetch=D.get, backfill=False, cfg=None):
    """Replay every settled match since the record began (or, with backfill, the in-sample window once)."""
    cfg = cfg or ARG
    now = now or dt.datetime.now(UTC)
    book = state["insample"] if backfill else state
    lo, hi = ((dt.date.fromisoformat(cfg["insample"][0]), dt.date.fromisoformat(cfg["insample"][1])) if backfill
              else (dt.date.fromisoformat(state["since"]), now.date()))
    seen = {e["event"] for e in book["entries"]} | set(book["skips"]) | set(book.get("seen") or {})
    obs = dict(at=now.isoformat(), new=0, waiting=0, skipped=0, errors=[])
    events = []
    for series in cfg["series"]:
        try:
            events += C.list_events(series, lo, fetch, until=hi, cap=800)
        except Exception as e:                                  # noqa: BLE001
            obs["errors"].append(f"listing {series}: {str(e)[:80]}")
    done = 0
    for event in sorted(events):
        day = C.event_date(event)
        if event in seen or day is None or not lo <= day <= hi:
            continue
        if not backfill and done >= MAX_EVENTS_PER_RUN:
            break
        try:
            entry, why = replay(event, fetch, now, cfg)
        except Exception as e:                                  # noqa: BLE001
            obs["errors"].append(f"{event}: {str(e)[:80]}")
            continue
        if entry is None and why is None:
            obs["waiting"] += 1
            continue
        if why:
            book["skips"][event] = why
            obs["skipped"] += 1
        else:
            book["entries"].append(entry)
            obs["new"] += 1
        done += 1
    if backfill:
        book["built"] = now.isoformat()
    else:
        state["upcoming"] = upcoming(fetch, now, since=state["since"], cfg=cfg)
        state["last_run"] = now.isoformat()
        state["error"] = "; ".join(obs["errors"])[:600] or None
        state["observations"] = obs
    return state


def upcoming(fetch, now, n=10, since=SINCE, cfg=None):
    """The next open matches the lane will count (matchday on or after `since`): [(kickoff, event, title)],
    soonest first."""
    cfg = cfg or ARG
    evs = []
    for series in cfg["series"]:
        try:
            evs += D.pages(f"events?series_ticker={series}&status=open&with_nested_markets=true&limit=200", "events", fetch)
        except Exception:                                       # noqa: BLE001
            continue
    out = []
    for ev in evs:
        m = rung(ev.get("markets") or [], cfg["strike"])
        occ = _ts((m or {}).get("occurrence_datetime"))
        if (m and occ and occ - KICKOFF_BACK_H * 3600 >= now.timestamp() - 3 * 3600
                and (matchday(ev.get("event_ticker")) or "") >= since):
            out.append(dict(kickoff=occ - KICKOFF_BACK_H * 3600, event=ev.get("event_ticker"), title=ev.get("title") or ""))
    return sorted(out, key=lambda x: x["kickoff"])[:n]


def main(argv=None, cfg=None):
    cfg = cfg or ARG
    argv = sys.argv[1:] if argv is None else argv
    path = cfg["path"]
    st = load(cfg=cfg)
    try:
        run(st, backfill="--backfill" in argv, cfg=cfg)
    except Exception as e:                                      # noqa: BLE001
        st["error"] = (type(e).__name__ + ": " + str(e))[:300]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(st, f, indent=1, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)
    ins = st["insample"]
    print(cfg["lane"], "entries", len(st["entries"]), "skips", len(st["skips"]), "in-sample", len(ins["entries"]),
          "this run", st.get("observations"), "error", st.get("error"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
