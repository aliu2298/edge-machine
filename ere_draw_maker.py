"""ere_draw_maker: Eredivisie draw band, entered as a MAKER instead of a taker (2026-11-06, Olu). Sandbox PAPER.

THE RULE. Exactly ere_draw's selection (the Kalshi Eredivisie TIE when the board's de-vigged draw sits in 0.20-0.25 and
the ask is 0.26 or less) and nothing else: this lane reads ere_draw's own logged bets, so a match is in it when, and only
when, ere_draw logged it. What changes is the ENTRY. ere_draw takes the ask at selection. This lane rests a YES bid on the
TIE at (that ask - 1c) from BID_LEAD_H (24) hours before kickoff, or from the moment the match first qualified if that is
later, until kickoff, and holds a fill to settlement.

FILL, queue-honest (the rule adopted for o35): the bid fills only when a TRADE prints STRICTLY below the bid price between
the time it is placed and kickoff, because an order resting at the bid sits behind the queue of orders already there and a
print AT the bid does not reach it. The fill is at the bid. Maker fee MAKER x p(1-p) on the entry; nothing at settlement.
No fill costs nothing and is recorded as "not filled".

BESIDE ere_draw. Every match carries ere_draw's own taker result (the ask at selection, the 7% taker fee, the same
settlement), so the page reads the fill rate, the maker ROI on the fills, the taker ROI on the SAME fills, and the taker
ROI on every match. The point of the lane: a taker pays about 1.3c of fee plus the spread on a draw near 25c; a maker 1c
under saves about 2c, roughly 8pp of ROI on a 20% gross edge, WITHOUT changing the selection. ere_draw itself is unchanged.

READ. An outcome is a MATCH (the date in the event ticker is the cluster for the page's z). ROI is the mean per fill (equal
stake). Review at 10 settled fills, decide at 30. The record is fresh from SINCE (the first Eredivisie matchday after the
lane was built); ere_draw's earlier settled matches are replayed once (python3 ere_draw_maker.py --backfill) into
state["insample"], shown collapsed and labelled, and never counted in the record.

Own ledger data/ere_draw_maker_ledger.json; read hourly by .github/workflows/ere-draw-maker.yml. Paper only: no order is placed.
"""
import datetime as dt
import json
import math
import os
import sys

import arg_dip as A
import chaos_replay as C
import daily_track as D
import o35_cheap_no as O
import sandbox_track as T

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "data", "ere_draw_maker_ledger.json")
LANE = "ere_draw_maker"
PARENT = "ere_draw"
LABEL = "Eredivisie draw · maker bid"
SINCE = "2026-11-06"
BID_LEAD_H = 24
TICK = 0.01
EVAL_AFTER_MIN = 10          # a match is read this long after kickoff: every print that could fill the bid is on file
REVIEW_N, DECIDE_N = 10, 30
VERSION = "eredraw-maker-v1"
EPS = 1e-9
UTC = dt.timezone.utc


# ------------------------------------------------------------------ inputs
def ts_of(raw):
    try:
        t = dt.datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    return int((t if t.tzinfo else t.replace(tzinfo=UTC)).timestamp())


def tie_ticker(q):
    return f"{q['market_id']}-TIE"


def parent_bets(d):
    """ere_draw's logged bets, one per match, oldest kickoff first. Read-only."""
    out = [q for q in T.bet_rows(d) if q.get("source") == PARENT and q.get("sport") == "soccer" and q.get("market_id")]
    seen, rows = set(), []
    for q in sorted(out, key=lambda q: (q.get("start") or "", q.get("market_id"))):
        if q["market_id"] in seen:
            continue
        seen.add(q["market_id"])
        rows.append(q)
    return rows


def maker_fee(p):
    return C.maker_fee(p)


def taker_roi(q):
    """ere_draw's own result on the match: P/L over the stake after the taker fee, or None while open."""
    if q.get("status") not in ("won", "lost", "no_result"):
        return None
    return T.pnl_after_fee(q) / T.STAKE


def maker_roi(bid, won):
    cost = bid + maker_fee(bid)
    return (1.0 - cost) / cost if won else -1.0


# ------------------------------------------------------------------ one match
def evaluate(q, prints, now_ts):
    """The maker entry for one ere_draw bet from its TIE market's trade prints [(ts, yes price, contracts)]."""
    ask = float(q["price"])
    bid = round(ask - TICK, 2)
    kick = ts_of(q["start"])
    logged = ts_of(q.get("logged")) or (kick - BID_LEAD_H * 3600)
    placed = max(logged, kick - BID_LEAD_H * 3600)
    e = dict(id=q["market_id"], match=q.get("label"), start=q["start"], kick_ts=kick, ask=ask, bid=bid, placed_ts=placed,
             version=VERSION, evaluated_ts=now_ts, prints=len(prints))
    if bid < TICK - EPS or placed >= kick:
        e.update(filled=False, why="no room to rest a bid" if bid < TICK - EPS else "qualified at kickoff")
        return e
    hits = [(t, px, n) for t, px, n in prints if placed < t <= kick and px < bid - EPS]
    if hits:
        t, px, n = hits[0]
        e.update(filled=True, fill_ts=t, fill_print=round(px, 4), fill_contracts=round(n, 2), fill_price=bid)
    else:
        e.update(filled=False, why="no print below the bid before kickoff")
    return e


def settle(e, q):
    """Fold the parent's current status into the entry: the match result and both ROIs."""
    e["status"] = q.get("status")
    e["taker_roi"] = taker_roi(q)
    e["taker_price"] = float(q["price"])
    if e.get("filled") and q.get("status") in ("won", "lost"):
        e["maker_roi"] = maker_roi(e["bid"], q["status"] == "won")
    else:
        e["maker_roi"] = None
    return e


# ------------------------------------------------------------------ state
def empty():
    return dict(version=VERSION, since=SINCE, last_run=None, error=None, entries=[], insample=[])


def load(path=PATH):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return empty()


def save(state, path=PATH):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=1, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


def run(state, d, now=None, fetch=D.get, backfill=False):
    """Read every ere_draw match whose kickoff has passed and that this lane has not read; settle all known ones."""
    now = now or dt.datetime.now(UTC)
    now_ts = int(now.timestamp())
    state.setdefault("insample", [])
    errors = []
    bets = parent_bets(d)
    for key in ("entries", "insample"):
        have = {e["id"]: e for e in state[key]}
        for q in bets:
            kick = ts_of(q.get("start"))
            if kick is None:
                continue
            fresh = q["start"][:10] >= SINCE
            if (key == "entries") != fresh:
                continue
            if key == "insample" and not backfill and q["market_id"] not in have:
                continue
            e = have.get(q["market_id"])
            if e is None:
                if now_ts < kick + EVAL_AFTER_MIN * 60:
                    continue
                try:
                    prints = A.prints_of(O.fetch_trades(tie_ticker(q), max(0, kick - (BID_LEAD_H + 1) * 3600), fetch))
                except Exception as exc:                    # noqa: BLE001
                    errors.append(f"{q['market_id']}: {type(exc).__name__}: {exc}")
                    continue
                e = evaluate(q, prints, now_ts)
                state[key].append(e)
                have[e["id"]] = e
            settle(e, q)
        state[key].sort(key=lambda e: (e["start"], e["id"]))
    state["last_run"] = now.isoformat()
    state["error"] = "; ".join(errors)[:600] or None
    return state


# ------------------------------------------------------------------ the record
def summary(entries):
    """Matches read, fills, and the maker and taker figures on the settled fills. All ROIs are the mean per entry."""
    read = list(entries)
    fills = [e for e in read if e.get("filled")]
    done = [e for e in fills if e.get("maker_roi") is not None]
    won = sum(1 for e in done if e["status"] == "won")
    exp = sum(e["bid"] for e in done)
    var = sum(e["bid"] * (1 - e["bid"]) for e in done)
    mean = lambda xs: (sum(xs) / len(xs)) if xs else None
    same = [e["taker_roi"] for e in done if e.get("taker_roi") is not None]
    every = [e["taker_roi"] for e in read if e.get("taker_roi") is not None]
    days = len({C.event_date(e["id"]) for e in done})
    return dict(matches=len(read), filled=len(fills), fill_rate=(len(fills) / len(read)) if read else None,
                n=len(done), won=won, expected=exp, maker=mean([e["maker_roi"] for e in done]), taker_same=mean(same),
                taker_all=mean(every), taker_all_n=len(every), open_fills=len(fills) - len(done),
                z=((won - exp) / math.sqrt(var)) if var > 0 else 0.0, days=days)


def record(state):
    """The lane's record in the sport template's shape: the settled fills since SINCE."""
    s = summary(state.get("entries") or [])
    return dict(n=s["n"], n_price=0, won=s["won"], expected=s["expected"], roi_fee=s["maker"], z=s["z"], n_bets=s["n"], unit="bet")


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    d = T.load()
    state = run(load(), d, backfill="--backfill" in argv)
    save(state)
    s, i = summary(state["entries"]), summary(state["insample"])
    print(f"{LANE}: {s['matches']} matches read, {s['filled']} filled, {s['n']} settled fills "
          f"(in-sample {i['matches']} read, {i['filled']} filled); error {state['error']}")
    return 1 if state["error"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
