"""NBA win margin paper VERSION 3 (2026-11-03, Olu): the entries are the executor's own decisions.

Versions 1 and 2 judged the entry from candles and trade prints (the ask check was "10+ contracts printed in the following hour"); the
executor judges it from the live order book at the decision time, which no replay can reproduce. So version 3 takes its ENTRIES from the
executor's T-1h decision snapshots (data/nba_wm_decisions.json, public market fields only, pushed from edge-vps by scripts/
vps_nba_wm_decisions.sh) and replays only the FILLS from trade prints, as version 2 does:

  YES split   a decision with rule_ok (the tight read, the 10-20c band, the book check) enters at the snapshot's ask (a taker buy, with
              the taker fee). From the tip on two sells rest at 2x and 3x of the ask (cap 98c): a leg fills only on a print STRICTLY above
              its target; an unfilled leg settles. The hold control is the same entry kept to settlement.
  NO fade     a decision with rule_ok sets the pregame NO price P and the limit round(0.75 P, 2). From the tip a post-only bid rests: it
              fills on a print STRICTLY under the limit with 10+ contracts strictly under it within an hour; the sell back at P needs a print
              STRICTLY above P; else settlement. A decision the executor ended as bid_crossed (the NO price was at or under the bid at the
              tip) is no entry. Maker fees on both legs.

Operational stops (the per-night cap, the loss cap, funding, a halt) are the executor's, not the rule's: a decision with rule_ok counts in
paper even when one of them stopped the order, and the report names the difference. The record starts on the first night a snapshot
exists; nights before it stay version 2, kept as their own block. Own ledger data/nba_wm_v3.json.
"""
import datetime as dt
import json
import os
import sys

import chaos_replay as C
import daily_track as D
import nba_winmargin as W
import nba_wm_nofade as N
import o35_cheap_no as O

ROOT = os.path.dirname(os.path.abspath(__file__))
DECISIONS = os.path.join(ROOT, "data", "nba_wm_decisions.json")
PATH = os.path.join(ROOT, "data", "nba_wm_v3.json")
YES_LANE, NO_LANE = "nba_winmargin_live", N.LANE
YES_VERSION, NO_VERSION = "wm-yes-v3", "wm-nofade-v3"
SELLS = ((2.0, 0.5), (3.0, 0.5))
SELL_CAP = 0.98
EPS = 1e-9
UTC, ET = dt.timezone.utc, D.ET
MAX_PER_RUN = 40


def night_of(tip):
    return dt.datetime.fromtimestamp(tip, UTC).astimezone(ET).date().isoformat()


def load(path=None):
    try:
        with open(path or PATH) as f:
            s = json.load(f)
    except FileNotFoundError:
        s = {}
    s.setdefault("version", "v3")
    s.setdefault("since", None)
    s.setdefault("rows", {})
    return s


def load_decisions(path=None):
    try:
        with open(path or DECISIONS) as f:
            return (json.load(f) or {}).get("decisions") or {}
    except (FileNotFoundError, ValueError):
        return {}


def yes_trade(prints, tip, ask, pay):
    """The YES split from a snapshot: cost = the ask + the taker fee; each leg fills on a later YES print STRICTLY above its target.
    `prints` [(ts, yes price, contracts)]; `pay` 1.0 when the bucket settled yes, else 0.0."""
    cost = C.cost(ask)
    legs, proceeds = [], 0.0
    for mult, share in SELLS:
        target = round(min(ask * mult, SELL_CAP), 2)
        hit = next((p for p in prints if p[0] >= tip and p[1] > target + EPS), None)
        legs.append(dict(multiple=mult, target=target, filled=hit is not None))
        proceeds += share * ((target - C.maker_fee(target)) if hit else pay)
    return dict(ask=ask, cost=round(cost, 5), profit=round(proceeds - cost, 5), roi=round((proceeds - cost) / cost, 4), won=proceeds > cost,
                hold_roi=round((pay - cost) / cost, 4), filled_2x=legs[0]["filled"], filled_3x=legs[1]["filled"], reason="split")


def no_row(prints_no, tip, P, no_wins):
    """The NO fade from a snapshot: N.dip_trade with the strict rules (no cross check here: the executor's own bid_crossed ends it)."""
    return N.dip_trade(prints_no, tip, P, N.HEAD, no_wins, strict=True)


def first_night(decisions):
    nights = [night_of(_ts(d["tip"])) for d in decisions.values() if _ts(d.get("tip"))]
    return min(nights) if nights else None


def _ts(raw):
    t = D.instant(raw)
    return int(t.timestamp()) if t else None


def run(state, decisions=None, now=None, fetch=D.get):
    """Replay every rule_ok decision of a settled market once. New rows only; a row is never rewritten."""
    now = now or dt.datetime.now(UTC)
    decisions = load_decisions() if decisions is None else decisions
    state["since"] = state.get("since") or first_night(decisions)
    obs = dict(at=now.isoformat(), new=0, waiting=0, errors=[])
    todo = [(k, d) for k, d in sorted(decisions.items(), key=lambda kv: kv[1].get("tip") or "") if k not in state["rows"] and d.get("rule_ok")
            and d.get("outcome") not in ("would_enter",)]
    done = 0
    markets = {}
    for key, d in todo:
        if done >= MAX_PER_RUN:
            break
        tip = _ts(d["tip"])
        if tip is None or tip > now.timestamp():
            obs["waiting"] += 1
            continue
        try:
            if d["event"] not in markets:
                markets[d["event"]] = C.event_markets(d["event"], fetch)[0]
            m = next((x for x in markets[d["event"]] if x["ticker"] == d["ticker"]), None)
            if m is None or m.get("result") not in ("yes", "no") or m.get("status") not in ("finalized", "settled"):
                obs["waiting"] += 1
                continue
            prints = O.fetch_trades(d["ticker"], tip - 3600, fetch)
            row = dict(key=key, lane=d["lane"], ticker=d["ticker"], event=d["event"], night=night_of(tip), tip=tip, outcome=d["outcome"],
                       decided_at=d.get("decided_at"), version=YES_VERSION if d["lane"] == YES_LANE else NO_VERSION, result=m["result"])
            if d["lane"] == YES_LANE:
                if d.get("yes_ask") is None:
                    continue
                row.update(yes_trade(W.yes_prints(prints), tip, d["yes_ask"], 1.0 if m["result"] == "yes" else 0.0))
            else:
                if d["outcome"] == "bid_crossed" or d.get("P") is None:
                    row.update(no_entry=True, reason="bid_crossed" if d["outcome"] == "bid_crossed" else "no plan")
                else:
                    f = no_row(O.prints_of(prints), tip, d["P"], m["result"] == "no")
                    if f is None:
                        row.update(no_entry=True, reason="no fill")
                    else:
                        row.update(f, P=d["P"], roi=f["profit"] / f["cost"])
        except Exception as e:                                   # noqa: BLE001
            obs["errors"].append(f"{key}: {str(e)[:80]}")
            continue
        state["rows"][key] = row
        obs["new"] += 1
        done += 1
    state["last_run"] = now.isoformat()
    state["error"] = "; ".join(obs["errors"])[:400] or None
    state["observations"] = obs
    return state


def yes_rows(state):
    """Settled YES entries in the shape chaos_replay.stats reads."""
    return [r for r in state["rows"].values() if r["lane"] == YES_LANE and "roi" in r]


def no_games(state):
    """One row per game with a NO fill: cost and profit summed over the game's filled buckets (the game is the outcome)."""
    by = {}
    for r in state["rows"].values():
        if r["lane"] == NO_LANE and not r.get("no_entry") and "profit" in r:
            by.setdefault(r["event"], []).append(r)
    out = []
    for ev, rs in by.items():
        cost, profit = sum(r["cost"] for r in rs), sum(r["profit"] for r in rs)
        out.append(dict(event=ev, night=rs[0]["night"], fills=len(rs), cost=cost, profit=profit, roi=profit / cost, won=profit > 0,
                        reason="game", sold=sum(1 for r in rs if r.get("sold_at"))))
    return out


def main(argv=None):
    st = load()
    try:
        run(st)
    except Exception as e:                                       # noqa: BLE001
        st["error"] = (type(e).__name__ + ": " + str(e))[:300]
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    tmp = PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(st, f, indent=1, sort_keys=True)
        f.write("\n")
    os.replace(tmp, PATH)
    print("nba_wm_v3 rows", len(st["rows"]), "since", st["since"], "this run", st.get("observations"), "error", st.get("error"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
