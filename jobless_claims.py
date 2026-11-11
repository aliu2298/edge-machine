#!/usr/bin/env python3
"""Jobless claims NO 70-85c before the release: a Sandbox PAPER lane (2026-11-11, Olu, from the econ weekly study).

Pre-registered in docs/prereg_jobless_claims_2026-11-11.md before the first entry. A price-band test: it selects by price
only, with no filter yet.

Rule: Kalshi KXJOBLESSCLAIMS (weekly initial claims, "claims >= X" rungs). In the window from 3h to 1h before each
event's close (8:29 ET, one minute before the 8:30 ET print; a holiday week moves with the event, never the weekday),
the first minute per rung with a spread of 10c or less and the NO ask at 70-85c: buy NO at that ask, hold to settlement,
taker fee in. An entry counts only when 10+ contracts traded at or through its ask within 60 minutes after it
(chaos_replay.entry_check, the cheap-side lanes' ask check). The YES side at 70-85c on the same ladder is the
comparison line. Everything is replayed from Kalshi's 1-minute candles, so the time of a read never moves a price.

Judged by weeks: one release = one cluster. Review at 8 settled weeks, decide at 12.

Runs from jobless-claims.yml, asked for by the VPS on Wednesdays and Thursdays from 07:30 ET (lane_windows.jobless_windows)
plus a backup cron. Own ledger data/jobless_claims_ledger.json. Paper only: no order is placed.
"""
import datetime as dt
import json
import os
import sys

import chaos_replay as C
import daily_track as D

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "data", "jobless_claims_ledger.json")
PREREG = "docs/prereg_jobless_claims_2026-11-11.md"
LANE = "jobless_no_70_85"
SERIES = "KXJOBLESSCLAIMS"
REGISTERED = "2026-11-11"
SINCE = "2026-11-12"                    # the first release counted (fresh record, no backfill)
BAND = (0.70, 0.85)                     # the side's ask, both ends inclusive
MAX_SPREAD = 0.10
WINDOW_H = (3, 1)                       # hours before the event's close: from 3h to 1h
SIDE, COMPARE = "no", "yes"
REVIEW_WEEKS, DECIDE_WEEKS = 8, 12
GIVE_UP_H = 12                          # an event still without candles this long after its close is noted, not retried
EPS = 1e-9
LABEL = "Jobless claims · NO 70-85c before the release"
COMPARE_LABEL = "Comparison · YES 70-85c, same ladder"
EVIDENCE = ("Econ weekly study, 2026-11-11 (in-sample, not counted): last 10 settled weeks, entry 1-3h before the print. "
            "NO 70-85c won 8 of 8 weeks with an entry v 6.2 priced, hold +28%, halves +27% / +29%, +26% without the best "
            "week, weekly z +1.54. The YES 70-85c side of the same ladder lost 39%. Ten weeks is thin: a reason to test, "
            "not a result.")


def empty():
    return {"version": "jobless-v1", "lane": LANE, "registered": REGISTERED, "since": SINCE, "events": {},
            "last_run": None, "error": None}


def load(path=PATH):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return empty()


def save(state, path=PATH):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=1, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


def iso(ts):
    return dt.datetime.fromtimestamp(ts, C.UTC).isoformat()


def cost(p):
    return p + C.taker_fee(p)


def in_band(x):
    return BAND[0] - EPS <= x <= BAND[1] + EPS


def window(close_ts):
    """(start_ts, end_ts): the entry window, on minute ends."""
    return close_ts - WINDOW_H[0] * 3600, close_ts - WINDOW_H[1] * 3600


def pick(minutes, side, close_ts):
    """The index of the first minute in the window with a spread of 10c or less and the side's ask in band, or None."""
    a, b = window(close_ts)
    for i, m in enumerate(minutes):
        if not a <= m["ts"] <= b:
            continue
        v = C.view(m, side)
        if v["bid"] > 0 and v["ask"] < 1 and v["ask"] - v["bid"] <= MAX_SPREAD + EPS and in_band(v["ask"]):
            return i
    return None


def entries_for(event, markets, candles, close_ts):
    """Every entry (both sides) of one event, from its 1-minute candles: dict(event, ticker, strike, side, price, at, i)."""
    a, b = window(close_ts)
    out = []
    for m in sorted(markets, key=lambda m: D.number(m.get("floor_strike")) or 0):
        rows = C.dense(candles.get(m["ticker"]) or [], a - 30 * 60, close_ts)
        for side in (SIDE, COMPARE):
            i = pick(rows, side, close_ts)
            if i is None:
                continue
            out.append(dict(event=event, ticker=m["ticker"], strike=D.number(m.get("floor_strike")), side=side,
                            price=round(C.view(rows[i], side)["ask"], 4), at=iso(rows[i]["ts"]), ts=rows[i]["ts"]))
    return out


def check(entry, rows):
    """The ask check on an entry, against its rung's dense minute rows (which must reach 60 minutes past it)."""
    i = next((k for k, r in enumerate(rows) if r["ts"] == entry["ts"]), None)
    if i is None:
        return dict(status="checking")
    return C.entry_check(rows, entry["side"], i)


def grade(entry, result):
    """Settle one entry on its rung's result: won, payout and held ROI per contract after the taker fee."""
    won = result == entry["side"]
    c = cost(entry["price"])
    return dict(entry, result=result, won=won, payout=1.0 if won else 0.0, roi=round((1.0 if won else 0.0) / c - 1, 4))


def _events(fetch):
    out = []
    for status in ("open", "closed", "settled"):
        out += [e.get("event_ticker") for e in D.pages(f"events?series_ticker={SERIES}&status={status}&limit=200", "events", fetch)]
    since = dt.date.fromisoformat(SINCE)
    return sorted({e for e in out if e and (C.event_date(e) or dt.date.min) >= since})


def run(state, now=None, fetch=D.get):
    """One read: freeze each event's entries once its window has ended, check their asks once an hour has passed, and settle
    them on Kalshi's result. Idempotent: a frozen entry is never re-picked."""
    now = now or dt.datetime.now(dt.timezone.utc)
    now_ts = int(now.timestamp())
    errs = []
    for ev in _events(fetch):
        st = state["events"].setdefault(ev, {"entries": [], "frozen": False, "note": None})
        if st.get("done"):
            continue
        try:
            markets, archived = C.event_markets(ev, fetch)
            closes = [x for x in (C._ts(m.get("close_time")) for m in markets) if x]
            if not markets or not closes:
                continue
            close_ts = max(closes) - max(closes) % 60
            st["close"] = iso(close_ts)
            a, b = window(close_ts)
            if now_ts < b:
                continue                                        # the window is still open
            hi = min(now_ts - now_ts % 60, close_ts)
            candles = C.fetch_candles(SERIES, ev, markets, a - 30 * 60, hi, fetch, archived)
            if not any(candles.values()):
                if now_ts > close_ts + GIVE_UP_H * 3600 and not st["frozen"]:
                    st.update(frozen=True, note="no quotes in the window")
                continue
            if not st["frozen"]:
                st["entries"] = entries_for(ev, markets, candles, close_ts)
                st["frozen"] = True
                st["note"] = None if st["entries"] else "no rung in band with a spread of 10c or less"
            for e in st["entries"]:
                if (e.get("ask_check") or {}).get("status") in ("verified", "unverified"):
                    continue
                if now_ts < e["ts"] + (60 + 1) * 60:
                    e["ask_check"] = dict(status="checking")
                    continue
                rows = C.dense(candles.get(e["ticker"]) or [], a - 30 * 60, close_ts)
                e["ask_check"] = check(e, rows)
            results = {m["ticker"]: C.settled_result(m) for m in markets}
            for k, e in enumerate(st["entries"]):
                if e.get("result") is None and results.get(e["ticker"]):
                    st["entries"][k] = grade(e, results[e["ticker"]])
            st["done"] = bool(st["frozen"]) and all(
                e.get("result") and (e.get("ask_check") or {}).get("status") in ("verified", "unverified")
                for e in st["entries"]) and (bool(st["entries"]) or now_ts > close_ts + GIVE_UP_H * 3600)
        except Exception as x:                                  # noqa: BLE001  one event never stops the others
            errs.append(f"{ev}: {type(x).__name__}: {str(x)[:80]}")
    state["last_run"] = now.isoformat()
    state["error"] = "; ".join(errs)[:600] or None
    return state


# ---------- the record ----------

def entries(state, side=SIDE):
    return [e for ev in sorted((state.get("events") or {})) for e in state["events"][ev].get("entries") or []
            if e["side"] == side]


def counted(es):
    """The entries the record counts: the ask verified."""
    return [e for e in es if (e.get("ask_check") or {}).get("status") == "verified"]


def week_record(es):
    """Judged by weeks: one release = one cluster. A week counts once every counted entry of it has settled."""
    by = {}
    for e in counted(es):
        by.setdefault(e["event"], []).append(e)
    weeks = sorted((k, v) for k, v in by.items() if all(e.get("result") for e in v))
    rois = [sum(e["roi"] for e in v) / len(v) for _, v in weeks]
    n = len(weeks)
    mean = sum(rois) / n if n else None
    z = None
    if n >= 3:
        sd = (sum((x - mean) ** 2 for x in rois) / (n - 1)) ** 0.5
        z = round(mean / (sd / n ** 0.5), 2) if sd > 0 else None
    settled = [e for _, v in weeks for e in v]
    return dict(weeks=n, positive=sum(r > 0 for r in rois), roi_week=mean, z=z,
                n=len(settled), won=sum(1 for e in settled if e["won"]), priced=round(sum(e["price"] for e in settled), 2),
                open=sum(1 for e in counted(es) if not e.get("result")),
                unverified=sum(1 for e in es if (e.get("ask_check") or {}).get("status") == "unverified"),
                by_week=[(k, r) for (k, _), r in zip(weeks, rois)])


def stage(rec):
    if rec["weeks"] >= DECIDE_WEEKS:
        return "decide"
    if rec["weeks"] >= REVIEW_WEEKS:
        return "review"
    return "early"


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    out = argv[argv.index("--out") + 1] if "--out" in argv else PATH
    state = load(out)
    run(state)
    save(state, out)
    rec, cmp_ = week_record(entries(state)), week_record(entries(state, COMPARE))
    print(f"jobless_claims: {rec['weeks']} weeks ({rec['positive']} positive), {rec['n']} entries, {rec['open']} open; "
          f"comparison {cmp_['weeks']} weeks; error {state['error']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
