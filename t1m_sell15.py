"""t1m_sell15: T1-M with a resting sell at 1.5x, an OBSERVATION-ONLY Sandbox readout (2026-11-08, Olu: "add the 1.5x sell
readout next to T1-M in sandbox").

T1-M (soccer_team_rules.SIBLINGS["T1M"], in Production since #354) buys the match over 3.5 YES at the ask 90-20 minutes
before kickoff on a T1 match and holds it. This readout takes THE SAME ENTRIES (T1-M's own ledger rows: same match, same
contract, same entry price and time) and asks what a resting sell at 1.5x the entry would have done, next to the hold. It
places nothing and changes nothing in T1-M: its bets, stake and Production record are read, never written.

THE RULE, frozen from the soccer price study's phase 5 (~/edge-research/soccer_shapes_2026-11-07/README, pre-registered
2026-11-08T21:26Z):
  TARGET   round(1.5 x entry, 2). An entry above 66c has no target under 99c: logged, not in the comparison.
  TOUCH    after kickoff, up to the market's close, the trade prints at a YES price at or above the target add up to 50+
           contracts, counting no print inside the 60 seconds after a SWEEP second (an in-play second whose highest print
           is 5c or more above the last print before it).
  EXIT     touched: sold at the target, taker fee on both legs (the headline). Not touched: held to Kalshi's settlement.
           The maker-sell variant (maker fee on the exit) is shown in the fold only.
  FEES     the study's: Kalshi's fee on a $1 stake, rounded up to the cent; the hold beside it pays the same entry fee.

RECORD: fresh from REGISTERED (T1-M entries whose match kicks off at or after it). Review at 10 settled entries, decide at
30. The backfill on T1's ledger matches since 2026-10-18 (python3 t1m_sell15.py --backfill, entry = the over 3.5 ask at
T1's logged time, as in phase 5) is kept apart in state["insample"]: shown, labelled in-sample, never counted. Phase 5's
note: z +0.9, not robust to the label recompute, about 60 matches needed.

Read hourly after settlement by .github/workflows/soccer-p4.yml (same VPS stamp). Own ledger data/t1m_sell15_ledger.json.
"""
import datetime as dt
import json
import math
import os
import statistics as stat
import sys

import chaos_replay as C
import daily_track as D
import nhl_goal_lanes as NG
import soccer_p4_lanes as P

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "data", "t1m_sell15_ledger.json")
TEAM_LEDGER = os.path.join(ROOT, "data", "soccer_team_rules_ledger.json")
LANE = "t1m_sell15"
LABEL = "T1-M · 1.5x sell (readout)"
PARENT = "st_t1"
VERSION = "t1m-sell15-v1"
REGISTERED = "2026-11-09T00:00:00Z"
BACKFILL_FROM = "2026-10-18"
MULT = 1.5
FAIR = 1 / MULT
SWEEP_JUMP, SWEEP_HOLD_S = 0.05, 60
DEPTH_MIN = 50.0
TAKER_K, MAKER_K = 0.07, 0.0175
REVIEW_N, DECIDE_N, NEED_N = 10, 30, 60
EPS = 1e-9
UTC = dt.timezone.utc
PHASE5_NOTE = ("Phase 5 read this on T1's 26 ledger matches since Oct 18: sell at 1.5x +10.7% after fees v hold +1.3%, "
               "z +0.9. With the labels recomputed point in time the same rule read −2.7%: not robust to the label "
               "recompute. About 60 matches are needed to read a +10% edge at z 2.")


# ------------------------------------------------------------------ the phase-5 rule
fee = P.fee


def target(entry):
    t = round(entry * MULT, 2)
    return t if entry * MULT <= 0.99 + EPS else None


def eligible(prints):
    """In-play prints [(ts, yes price, contracts)] minus those inside [s, s + 60) of any sweep second s."""
    bysec = {}
    for x in prints:
        bysec.setdefault(int(x[0]), []).append(x)
    sweeps, last = [], None
    for s in sorted(bysec):
        xs = bysec[s]
        if last is not None and max(x[1] for x in xs) >= last + SWEEP_JUMP - EPS:
            sweeps.append(s)
        last = xs[-1][1]
    return [x for x in prints if not any(s <= x[0] < s + SWEEP_HOLD_S for s in sweeps)], len(sweeps)


def outcome(entry, won, prints):
    """dict(target, touched, hold, sell, sell_maker, sweeps): ROIs per $1 after the study's fees. `prints`: in play only."""
    cost = entry + fee(entry, TAKER_K)
    pay = 1.0 if won else 0.0
    hold = (pay - cost) / cost
    tgt = target(entry)
    el, nsw = eligible(sorted(prints))
    if tgt is None:
        return dict(target=None, touched=None, hold=round(hold, 4), sell=None, sell_maker=None, sweeps=nsw)
    touched = sum(x[2] for x in el if x[1] >= tgt - EPS) >= DEPTH_MIN - EPS
    sell = ((tgt - fee(tgt, TAKER_K)) - cost) / cost if touched else hold
    sell_m = ((tgt - fee(tgt, MAKER_K)) - cost) / cost if touched else hold
    return dict(target=tgt, touched=touched, hold=round(hold, 4), sell=round(sell, 4), sell_maker=round(sell_m, 4), sweeps=nsw)


# ------------------------------------------------------------------ reading
def market(ticker, fetch):
    d = fetch(f"markets/{ticker}") or {}
    return d.get("market") or {}


def read_entry(ticker, entry, entry_ts, ko, fetch):
    """The settled outcome of one entry, or None while the market is unsettled."""
    m = market(ticker, fetch)
    res = C.settled_result(m)
    if res is None:
        return None
    close = C._ts(m.get("close_time")) or ko + 4 * 3600
    prints = [x for x in NG.fetch_prints(ticker, int(ko), int(close + 600), fetch) if ko < x[0] <= close]
    return dict(ticker=ticker, entry=entry, entry_ts=entry_ts, ko=ko, won=res == "yes",
                **outcome(entry, res == "yes", prints))


def t1m_picks(path=TEAM_LEDGER):
    try:
        with open(path) as f:
            led = json.load(f)
    except FileNotFoundError:
        return []
    return ((led.get("rules") or {}).get("T1M") or {}).get("picks") or []


def run(state, now=None, fetch=D.get, picks=None):
    """Read every settled T1-M entry whose match kicks off at or after REGISTERED, once."""
    now = now or dt.datetime.now(UTC)
    seen = {e["id"] for e in state["entries"]} | set(state["skips"])
    errors = []
    for p in (picks if picks is not None else t1m_picks()):
        ko = C._ts(p.get("start"))
        if p["id"] in seen or ko is None:
            continue
        if ko < C._ts(REGISTERED):
            state["skips"][p["id"]] = "kicked off before the readout was registered (in the backfill, not the record)"
            continue
        if p.get("status") not in ("won", "lost", "no_result"):
            continue
        try:
            rec = read_entry(p["ticker"], float(p["price"]), C._ts(p.get("logged")), ko, fetch)
        except Exception as exc:                                # noqa: BLE001
            errors.append(f"{p['id']}: {str(exc)[:80]}")
            continue
        if rec is None:
            continue
        state["entries"].append(dict(rec, id=p["id"], match=p.get("match"), league=p.get("league"),
                                     day=(p.get("start") or "")[:10], logged=now.isoformat(), version=VERSION))
    state["entries"].sort(key=lambda e: (e["ko"], e["id"]))
    state["last_run"] = now.isoformat()
    state["error"] = "; ".join(errors)[:600] or None
    return state


def backfill(state, fetch=D.get, ledger_path=TEAM_LEDGER, now=None):
    """The in-sample read: T1's ledger matches since BACKFILL_FROM, the over 3.5 YES ask at T1's (or T1-M's, whichever is
    first) logged time, the same rule. Kept in state["insample"], never counted."""
    now = now or dt.datetime.now(UTC)
    with open(ledger_path) as f:
        led = json.load(f)
    first = {}
    for rule in ("T1", "T1M"):
        for p in ((led.get("rules") or {}).get(rule) or {}).get("picks") or []:
            if (p.get("start") or "") < BACKFILL_FROM:
                continue
            lg = p["event"].split("-")[0].replace("TEAMTOTAL", "TOTAL")
            ev = f'{lg}-{p["event"].split("-", 1)[1]}'
            t = C._ts(p.get("logged"))
            if ev not in first or t < first[ev]["t"]:
                first[ev] = dict(t=t, start=p.get("start"), match=p.get("match"), league=p.get("league"))
    out, skips = [], {}
    for ev, x in sorted(first.items()):
        ms, arch = C.event_markets(ev, fetch)
        m = next((m for m in ms if D.number(m.get("floor_strike")) == 3.5), None)
        if m is None or C.settled_result(m) is None:
            skips[ev] = "no settled over 3.5 market"
            continue
        ko = C._ts(x["start"])
        cs = C.fetch_candles(ev.split("-")[0], ev, [m], int(x["t"]) - 3600, int(x["t"]) + 60, fetch, arch)
        yb, ya, _ = NG.series_at(NG.compact(cs.get(m["ticker"])), x["t"])
        if yb is None or ya is None or ya - yb > 0.05 + EPS or not 0.03 - EPS <= ya <= 0.97 + EPS:
            skips[ev] = "no tight quote at T1's entry time"
            continue
        rec = read_entry(m["ticker"], ya, x["t"], ko, fetch)
        if rec:
            out.append(dict(rec, id=f"insample:{ev}", match=x["match"], league=x["league"], day=(x["start"] or "")[:10]))
    state["insample"] = dict(entries=sorted(out, key=lambda e: e["ko"]), skips=skips, built=now.isoformat(),
                             since=BACKFILL_FROM)
    return state


# ------------------------------------------------------------------ the ledger
def empty():
    return dict(version=VERSION, registered=REGISTERED, entries=[], skips={}, last_run=None, error=None,
                insample=dict(entries=[], skips={}, built=None, since=BACKFILL_FROM))


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
    NG.save(state, path)


# ------------------------------------------------------------------ the readout
def _z(xs, ref=0.0):
    if len(xs) < 3:
        return None
    sd = stat.pstdev(xs)
    return (stat.mean(xs) - ref) / (sd / math.sqrt(len(xs))) if sd > 0 else None


def summary(entries):
    """Side by side on the same entries with a target: n, touches v fair, hold and sell ROI, the paired difference and its
    z, both halves (by kickoff), the maker variant. One entry a match, so z by entry is z by match."""
    rows = [e for e in entries if e.get("target") is not None]
    mean = lambda xs: stat.mean(xs) if xs else None     # noqa: E731
    n = len(rows)
    k = n // 2
    touch = sum(1 for e in rows if e["touched"])
    diffs = [e["sell"] - e["hold"] for e in rows]
    tz = (touch - n * FAIR) / math.sqrt(n * FAIR * (1 - FAIR)) if n else None
    half = lambda key, part: mean([e[key] for e in part]) if len(rows) >= 4 else None   # noqa: E731
    return dict(n=n, logged=len(entries), no_target=len(entries) - n, matches=len({e["id"] for e in rows}), touched=touch,
                touch_rate=touch / n if n else None, touch_z=tz, won=sum(1 for e in rows if e["won"]),
                hold=mean([e["hold"] for e in rows]), sell=mean([e["sell"] for e in rows]),
                maker=mean([e["sell_maker"] for e in rows]), diff=mean(diffs), diff_z=_z(diffs),
                sell_z=_z([e["sell"] for e in rows]), hold_z=_z([e["hold"] for e in rows]),
                sell_h=(half("sell", rows[:k]), half("sell", rows[k:])), hold_h=(half("hold", rows[:k]), half("hold", rows[k:])),
                diff_h=(mean(diffs[:k]) if n >= 4 else None, mean(diffs[k:]) if n >= 4 else None))


def read_of(n):
    if n < REVIEW_N:
        return f"too early ({n} of {REVIEW_N} settled entries)"
    if n < DECIDE_N:
        return f"review ({n} of {DECIDE_N} to decide)"
    return "decide" + (f"; about {NEED_N} needed to read a +10% edge at z 2" if n < NEED_N else "")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    state = load()
    state = backfill(state) if "--backfill" in argv else run(state)
    save(state)
    s, i = summary(state["entries"]), summary(state["insample"]["entries"])
    print(f"t1m_sell15: {s['n']} entries (touched {s['touched']}), sell {s['sell']} hold {s['hold']}; in-sample {i['n']} "
          f"(touched {i['touched']}), sell {i['sell']} hold {i['hold']}; error {state['error']}")
    return 1 if state["error"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
