"""mls_tie_split: MLS pre-match TIE, split sell at 2x / 3x (2026-11-07, Olu: "Build it as paper"). Sandbox PAPER.

WHERE IT COMES FROM. ~/edge-research/soccer_shapes_2026-11-07/ (README): cheap-contract price shapes on every Kalshi soccer
market, with six match filters pre-registered before they were read. One filtered cell passed every rule: the KXMLSGAME
TIE bought an hour before kickoff with a split sell (half at 2x, half at 3x). Trade-level research numbers:
  live Sep 3 - Nov 6:     164 matches, +6% per entry (z +0.7), both halves positive (+7% / +5%), held +17%
  holdout Aug 1 - Aug 30:  75 matches, +27% (z +2.3), rebuilt from trade prints (last print + 1c as the ask)
The research verdict was WATCH, not edge: the live z is low, and Pinnacle closing prices on 5,800 MLS matches
(2012-2025) price the draw exactly fair (25.3% priced, 25.2% drew). This lane is a forward test of that cell.

THE RULE, pre-registered (2026-11-07), the research cell unchanged:
  markets  the TIE of every Kalshi KXMLSGAME event. No other filter (the league IS the match filter).
  kickoff  ESPN's MLS scoreboard, matched by the two team codes in the event ticker (Kalshi's occurrence time is not
           reliable for MLS). A match ESPN cannot place is retried, then skipped after SKIP_AFTER_D days.
  ENTRY    the TIE's YES ask an hour before kickoff, from 1-minute candles (the last quote at or before that minute), only
           if the ask is 1-35c and the bid is within 5c. Bought at that ask (taker), taker fee 0.07 p(1-p).
  EXIT     two resting sells placed at the fill, each on half the position: 2x and 3x the entry (capped 98c). A leg sells
           only when trades printed AT or ABOVE its target, from 60 s after the fill on, add up to 50+ contracts (the
           research rule: a single small print does not reach a resting order). Maker fee 0.0175 p(1-p) on a sold leg.
           An unsold leg is held to settlement (1 if the match is drawn after regulation, else 0).
  CONTROL  the same entry held to settlement.
  READ     one outcome per match. ROI is the mean per entry (equal stake). z is by matchday (the date in the event
           ticker). Review at 10 settled entries, decide at 30.

RECORD: fresh from SINCE. The in-sample window (Aug 1 - Nov 7, the research months) is replayed once
(python3 mls_tie_split.py --backfill) into state["insample"], shown collapsed and labelled, never counted.
The MLS regular season is over; only playoff matches remain until the 2027 season, so the record grows slowly.

Own ledger data/mls_tie_split_ledger.json; read hourly by .github/workflows/mls-tie.yml from settled matches.
Paper only: no order is placed.
"""
import datetime as dt
import json
import math
import os
import re
import statistics as stat
import sys

import arg_dip as A
import chaos_lanes as CL
import chaos_replay as C
import daily_track as D

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "data", "mls_tie_split_ledger.json")
LANE = "mls_tie_split"
LABEL = "MLS tie · split sell 2x/3x"
SERIES = "KXMLSGAME"
ESPN_PATH = "soccer/usa.1"
SINCE = "2026-11-08"
INSAMPLE = ("2026-08-01", "2026-11-07")
LEAD_MIN = 60
ASK_RANGE = (0.01, 0.35)
MAX_SPREAD = 0.05
LEGS = ((2.0, 0.5), (3.0, 0.5))
CAP = 0.98
SELL_DELAY_S = 60
SELL_MIN = 50.0
SKIP_AFTER_D = 3
MAX_EVENTS_PER_RUN = 60
REVIEW_N, DECIDE_N = 10, 30
VERSION = "mlstie-v1"
EPS = 1e-9
UTC = dt.timezone.utc
# Kalshi ticker codes that differ from ESPN's abbreviations.
ALIAS = {"DCU": "DC", "NYRB": "RBNY", "LAG": "LA"}


# ------------------------------------------------------------------ kickoff
def codes(event):
    """The team-code string of an event ticker (KXMLSGAME-26NOV01PORHOU -> PORHOU)."""
    return re.sub(r"^.*?-\d\d[A-Z]{3}\d\d", "", str(event or ""))


def espn_code(code):
    """Kalshi's concatenated codes in ESPN's spelling, longest alias first (CINDCU -> CINDC)."""
    for k in sorted(ALIAS, key=len, reverse=True):
        code = code.replace(k, ALIAS[k])
    return code


def kickoff_from(boards, event):
    """Kickoff (unix s) of the ESPN game whose home + away abbreviations spell the ticker's codes, or None."""
    want = espn_code(codes(event))
    for evs in boards:
        for ev in evs or []:
            comp = (ev.get("competitions") or [{}])[0]
            side = {c.get("homeAway"): (c.get("team") or {}).get("abbreviation", "") for c in comp.get("competitors") or []}
            if side.get("home", "") + side.get("away", "") == want and ev.get("date"):
                t = D.instant(ev["date"])
                return int(t.timestamp()) if t else None
    return None


def espn_kickoff(event):
    day = C.event_date(event)
    if not day:
        return None
    return kickoff_from([CL._board(ESPN_PATH, day + dt.timedelta(days=k)) for k in (0, 1, -1)], event)


# ------------------------------------------------------------------ one match
def leg_target(entry, mult):
    return round(min(math.ceil(round(mult * entry * 100, 6)) / 100, CAP), 2)


def simulate(prints, entry_ts, ask, won):
    """The split-sell trade on one entry, from the TIE's trade prints [(ts, yes price, contracts)]."""
    cost = C.cost(ask)
    pay = 1.0 if won else 0.0
    legs, proceeds = [], 0.0
    for mult, share in LEGS:
        tgt = leg_target(ask, mult)
        cum, sold_ts = 0.0, None
        for t, px, n in prints:
            if t < entry_ts + SELL_DELAY_S or px < tgt - EPS:
                continue
            cum += n
            if cum >= SELL_MIN - EPS:
                sold_ts = t
                break
        legs.append(dict(multiple=mult, target=tgt, sold_ts=sold_ts))
        proceeds += share * ((tgt - C.maker_fee(tgt)) if sold_ts is not None else pay)
    return dict(cost=round(cost, 5), roi=round((proceeds - cost) / cost, 4), hold=round((pay - cost) / cost, 4), legs=legs)


def replay(event, fetch, now, kick_fn=None):
    """(entry, None) for a settled match, (None, reason) to skip it, or (None, None) to retry it on a later run."""
    kick_fn = kick_fn or espn_kickoff
    ms, archived = C.event_markets(event, fetch)
    m = next((x for x in ms if str(x.get("ticker", "")).endswith("-TIE")), None)
    if m is None:
        return None, "no Tie market"
    res = C.settled_result(m)
    if res is None:
        return None, None
    kick = kick_fn(event)
    if kick is None:
        day = C.event_date(event)
        if day and (now.date() - day).days > SKIP_AFTER_D:
            return None, "no ESPN kickoff for the team codes"
        return None, None
    q_at = kick - LEAD_MIN * 60
    cs = C.fetch_candles(SERIES, event, [m], q_at - 30 * 60, q_at + 60, fetch, archived).get(m["ticker"])
    q = A.pregame_quote(cs, q_at)
    if q is None:
        return None, "no quote an hour before kickoff"
    q_ts, bid, ask = q
    if ask - bid > MAX_SPREAD + EPS:
        return None, f"spread {ask - bid:.2f} over 5c"
    if not ASK_RANGE[0] - EPS <= ask <= ASK_RANGE[1] + EPS:
        return None, f"ask {ask:.2f} outside 1-35c"
    prints = A.prints_of(A.fetch_trades(m["ticker"], q_at - 30 * 60, fetch))
    won = res == "yes"
    trade = simulate(prints, q_at, ask, won)
    return dict(id=m["ticker"], event=event, title=m.get("title") or event, kickoff=kick, entry_ts=q_at,
                matchday=A.matchday(event), ask=ask, bid=bid, quote_ts=q_ts, won=won, prints=len(prints),
                check=A.p_check(prints, q_ts, ask)["status"], logged=now.isoformat(), version=VERSION, **trade), None


# ------------------------------------------------------------------ the ledger
def empty():
    return dict(lane=LANE, version=VERSION, since=SINCE, entries=[], skips={}, last_run=None, error=None,
                insample=dict(window=list(INSAMPLE), entries=[], skips={}, built=None))


def load(path=PATH):
    try:
        with open(path) as f:
            s = json.load(f)
    except FileNotFoundError:
        return empty()
    base = empty()
    for k, v in base.items():
        s.setdefault(k, v)
    return s


def save(state, path=PATH):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=1, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


def run(state, now=None, fetch=D.get, backfill=False, kick_fn=None):
    """Replay every settled MLS match since the record began (or, with backfill, the in-sample window once)."""
    now = now or dt.datetime.now(UTC)
    book = state["insample"] if backfill else state
    lo, hi = ((dt.date.fromisoformat(INSAMPLE[0]), dt.date.fromisoformat(INSAMPLE[1])) if backfill
              else (dt.date.fromisoformat(state["since"]), now.date()))
    seen = {e["event"] for e in book["entries"]} | set(book["skips"])
    errors, done = [], 0
    try:
        events = C.list_events(SERIES, lo, fetch, until=hi, cap=800)
    except Exception as exc:                                    # noqa: BLE001
        events, _ = [], errors.append(f"listing: {str(exc)[:80]}")
    for event in sorted(events):
        day = C.event_date(event)
        if event in seen or day is None or not lo <= day <= hi:
            continue
        if not backfill and done >= MAX_EVENTS_PER_RUN:
            break
        try:
            entry, why = replay(event, fetch, now, kick_fn)
        except Exception as exc:                                # noqa: BLE001
            errors.append(f"{event}: {str(exc)[:80]}")
            continue
        if entry is None and why is None:
            continue
        if why:
            book["skips"][event] = why
        else:
            book["entries"].append(entry)
        done += 1
    book["entries"].sort(key=lambda e: (e["kickoff"], e["event"]))
    if backfill:
        book["built"] = now.isoformat()
    else:
        state["last_run"] = now.isoformat()
        state["error"] = "; ".join(errors)[:600] or None
    return state


# ------------------------------------------------------------------ the record
def summary(entries):
    """Entries, legs sold, split ROI and the hold control (mean per entry), z by matchday, and the two halves."""
    es = sorted(entries, key=lambda e: e["kickoff"])
    mean = lambda xs: stat.mean(xs) if xs else None
    k = len(es) // 2
    return dict(n=len(es), won=sum(1 for e in es if e["roi"] > 0), draws=sum(1 for e in es if e["won"]),
                priced=sum(e["ask"] for e in es), roi=mean([e["roi"] for e in es]), hold=mean([e["hold"] for e in es]),
                sold2=sum(1 for e in es if e["legs"][0]["sold_ts"]), sold3=sum(1 for e in es if e["legs"][1]["sold_ts"]),
                z=A.z_by_day([(e["roi"], e["matchday"]) for e in es]), days=len({e["matchday"] for e in es}),
                old=mean([e["roi"] for e in es[:k]]) if len(es) >= 4 else None,
                new=mean([e["roi"] for e in es[k:]]) if len(es) >= 4 else None)


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    state = run(load(), backfill="--backfill" in argv)
    save(state)
    s, i = summary(state["entries"]), summary(state["insample"]["entries"])
    print(f"{LANE}: {s['n']} entries since {state['since']} (in-sample {i['n']}, split {i['roi']}, hold {i['hold']}); "
          f"error {state['error']}")
    return 1 if state["error"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
