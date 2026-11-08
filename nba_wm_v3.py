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
V4_VERSIONS = ("wm-yes-v4", "wm-nofade-v4")       # the versions the executor pins from 2026-11-08 (nba_wm_v4prod.py replays them)
SELLS = ((2.0, 0.5), (3.0, 0.5))
SELL_CAP = 0.98
EPS = 1e-9
UTC, ET = dt.timezone.utc, D.ET
MAX_PER_RUN = 40


def is_v4(d):
    return d.get("bot_version") in V4_VERSIONS


def take_v3(d):
    """Version 3's ledger takes every decision NOT pinned to version 4 (older or absent versions as before)."""
    return not is_v4(d)


# The replay's per-version settings: nba_wm_v4prod passes its own. `dip` = the NO bid as a share of P (version 3: 75%).
CFG = dict(path=PATH, yes_version=YES_VERSION, no_version=NO_VERSION, sells=SELLS, take=take_v3, dip=N.HEAD, version="v3")


def night_of(tip):
    return dt.datetime.fromtimestamp(tip, UTC).astimezone(ET).date().isoformat()


def load(path=None, version="v3"):
    try:
        with open(path or PATH) as f:
            s = json.load(f)
    except FileNotFoundError:
        s = {}
    s.setdefault("version", version)
    s.setdefault("since", None)
    s.setdefault("rows", {})
    return s


def load_decisions(path=None):
    try:
        with open(path or DECISIONS) as f:
            return (json.load(f) or {}).get("decisions") or {}
    except (FileNotFoundError, ValueError):
        return {}


def yes_trade(prints, tip, ask, pay, sells=SELLS):
    """The YES split from a snapshot: cost = the ask + the taker fee; each leg fills on a later YES print STRICTLY above its target.
    `prints` [(ts, yes price, contracts)]; `pay` 1.0 when the bucket settled yes, else 0.0. `sells` [(multiple, share)]: 2x / 3x for
    version 3, 2x / 2.5x for version 4 (the second leg's flag is filled_3x or filled_25x)."""
    cost = C.cost(ask)
    legs, proceeds = [], 0.0
    for mult, share in sells:
        target = round(min(ask * mult, SELL_CAP), 2)
        hit = next((p for p in prints if p[0] >= tip and p[1] > target + EPS), None)
        legs.append(dict(multiple=mult, target=target, filled=hit is not None))
        proceeds += share * ((target - C.maker_fee(target)) if hit else pay)
    return dict(ask=ask, cost=round(cost, 5), profit=round(proceeds - cost, 5), roi=round((proceeds - cost) / cost, 4), won=proceeds > cost,
                hold_roi=round((pay - cost) / cost, 4), filled_2x=legs[0]["filled"], reason="split",
                **{"filled_" + f"{sells[1][0]:g}".replace(".", "") + "x": legs[1]["filled"]})


def no_row(prints_no, tip, P, no_wins, dip=N.HEAD):
    """The NO fade from a snapshot: N.dip_trade with the strict rules (no cross check here: the executor's own bid_crossed ends it)."""
    return N.dip_trade(prints_no, tip, P, dip, no_wins, strict=True)


def first_night(decisions, take=take_v3):
    nights = [night_of(_ts(d["tip"])) for d in decisions.values() if _ts(d.get("tip")) and take(d)]
    return min(nights) if nights else None


def _ts(raw):
    t = D.instant(raw)
    return int(t.timestamp()) if t else None


def run(state, decisions=None, now=None, fetch=D.get, cfg=None):
    """Replay every rule_ok decision of a settled market once. New rows only; a row is never rewritten. `cfg` picks the version
    (CFG = version 3; nba_wm_v4prod.CFG = version 4): which decisions it takes (by the executor's bot_version) and its sells."""
    cfg = cfg or CFG
    now = now or dt.datetime.now(UTC)
    decisions = load_decisions() if decisions is None else decisions
    decisions = {k: d for k, d in decisions.items() if cfg["take"](d)}
    state["since"] = state.get("since") or first_night(decisions, cfg["take"])
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
                       decided_at=d.get("decided_at"), version=cfg["yes_version"] if d["lane"] == YES_LANE else cfg["no_version"], result=m["result"])
            if d["lane"] == YES_LANE:
                if d.get("yes_ask") is None:
                    continue
                row.update(yes_trade(W.yes_prints(prints), tip, d["yes_ask"], 1.0 if m["result"] == "yes" else 0.0, cfg["sells"]))
                if d.get("fav_share") is not None:
                    row["fav_share"] = d["fav_share"]
            else:
                if d["outcome"] == "bid_crossed" or d.get("P") is None:
                    row.update(no_entry=True, reason="bid_crossed" if d["outcome"] == "bid_crossed" else "no plan")
                else:
                    dip = cfg["dip"]
                    if cfg["version"] != "v3" and d.get("limit"):      # version 4: the decision's own limit (65% of P)
                        dip = d["limit"] / d["P"]
                    f = no_row(O.prints_of(prints), tip, d["P"], m["result"] == "no", dip)
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
