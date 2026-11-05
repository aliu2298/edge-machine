#!/usr/bin/env python3
"""Superpack (2026-11-05, Olu): a Sandbox paper lane that copies the active lanes' bets on the leaderboard's top names.

PRE-REGISTERED 2026-11-05, before it logged anything (RULE below, fixed from here on):
  Whenever an ACTIVE lane (Production or Sandbox: the same set as the leaderboard's active-lanes board) logs a bet
  whose name (team, match, player or asset, as the board keys it) is in that board's top 10 by profit, Superpack logs
  the same bet: same contract, side and price, at the time and ask the lane logged it, $1 flat.
  NO LOOK-AHEAD. The top 10 is the board as it stood when the copied bet was logged, from bets settled before that
  moment only. A bet counts as settled from its own settled stamp; a bet with no stamp counts only from the first run
  that saw it settled (never earlier than it really settled). Each entry stores that dated top 10.
  ONE BET PER CONTRACT. Two lanes on the same contract and side: one entry. Two lanes on opposite sides of the same
  contract: no entry, and the skip is logged.
  RECORD. Fresh from its first entry: review at 10 settled, decide at 30.
  BASELINES, logged by the same rule so they are judged on the same footing:
    (a) every active-lane bet from the same start, every name (the main comparison: Superpack counts only if its
        names beat the lanes' own average);
    (b) the same copy rule on the board's bottom 10 (a mirror test).
  WEAKNESS, stated before it starts: the board's own week-to-week test (last week's top quarter of names v the
  bottom quarter the next week) is 2 of 6, and the spike board's is 1 of 2: hot names have not stayed hot. This
  lane is that test with prices attached. Paper only: not in Production and in no feed.

The ledger (data/superpack_ledger.json) is written by the Sandbox Tracker run, after the other lanes log, from the
ledgers already in the repository. A copied bet's profit is the copied lane's own per-$1 result, after its fees.
"""
import datetime as dt
import json
import os
import sys

import leaderboard as L

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "data", "superpack_ledger.json")
LANE = "superpack"
LABEL = "Superpack · the active lanes' bets on the leaderboard's top 10"
REGISTERED = "2026-11-05"
VERSION = 1
TOP_K = 10
REVIEW_AT, DECIDE_AT = 10, 30
RULE = ("Whenever an active lane (Production or Sandbox, the set on the leaderboard's active-lanes board) logs a bet whose "
        "name is in that board's top 10 by profit, Superpack logs the same bet: same contract, side and price, at the time "
        "and ask the lane logged it, $1 flat. The top 10 is the board as it stood when the copied bet was logged, from "
        "bets settled before then only; each entry stores it. One bet per contract: two lanes on the same side make one "
        "entry, opposite sides make none (the skip is logged). Fresh record from the first entry: review at 10 settled, "
        "decide at 30.")
WEAKNESS = ("The board's own week-to-week test is 2 of 6 (last week's top quarter of names has not beaten the bottom "
            "quarter the next week), and the spike board's is 1 of 2: hot names have not stayed hot. This lane is that "
            "test with prices attached.")
LISTS = ("entries", "mirror", "pool")    # Superpack (top 10), baseline (b) bottom 10, baseline (a) every active-lane bet


def utc(text):
    try:
        t = dt.datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)


def pid(b):
    """A bet's identity across runs: where it was read, its lane and the lane's own id for it."""
    return json.dumps([b.get("src"), b["lane"], list(b["uid"]) if isinstance(b["uid"], (list, tuple)) else b["uid"]])


def ckey(b):
    return str(b.get("contract_id"))


def load(path=PATH):
    try:
        with open(path) as f:
            s = json.load(f)
    except (OSError, ValueError):
        s = {}
    s.setdefault("version", VERSION)
    s.setdefault("lane", LANE)
    s.setdefault("registered", REGISTERED)
    s.setdefault("since", None)
    s.setdefault("seen_settled", {})
    s.setdefault("decided", {})
    s.setdefault("skips", [])
    for k in LISTS:
        s.setdefault(k, [])
    return s


def save(state, path=PATH):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=1, sort_keys=True)
    os.replace(tmp, path)


def settled_at(b, state):
    """When a settled bet may first count in a ranking: its own stamp, else the first run that saw it settled."""
    own = utc(b.get("settled"))
    seen = utc(state["seen_settled"].get(pid(b)))
    return own or seen


def board_at(t, settled, state, stage):
    """The active-lanes board as it stood at `t`: only bets whose settle time is strictly before `t`."""
    known = [b for b in settled if (settled_at(b, state) or t) < t]
    ab = L.active_board(known, stage)
    return ab["top"][:TOP_K], ab["bottom"][:TOP_K]


def names_of(stats):
    return {(s["sport"], s["name"]) for s in stats}


def snapshot(t, stats):
    return dict(as_of=t.isoformat(), names=[dict(sport=s["sport"], name=s["name"], bets=s["n"], profit=round(s["profit"], 4))
                                            for s in stats])


def entry(b, matched, snap, now):
    return dict(id=f"{LANE}:{pid(b)}", pid=pid(b), lane=b["lane"], src=b.get("src"), scope=b.get("scope"), sport=b["sport"],
                entities=b["entities"], matched=sorted(n for _s, n in matched), contract=ckey(b), side=b.get("side"),
                price=b.get("price"), logged=b.get("logged"), entered_at=now.isoformat(), snapshot=snap,
                status="open", profit=None, settled=None)


def run(state, now=None, bets=None, stage=None):
    """One pass: stamp newly settled bets, decide every active-lane bet logged since the first run, settle entries.

    The first run sets `since` and decides nothing: Superpack copies only bets logged after it was registered."""
    now = now or dt.datetime.now(dt.timezone.utc)
    if bets is None:
        bets, *_ = L.collect_bets(include_open=True)
    stage = stage or L.lane_stages(now)
    stages = {}

    def active(b):
        k = (b.get("src"), b["lane"], b.get("scope"))
        if k not in stages:
            stages[k] = stage(b)
        return stages[k]

    for b in bets:
        # Only a bet with no settled stamp of its own needs one (settled_at): the run that first saw it settled.
        if b["profit"] is not None and not utc(b.get("settled")) and pid(b) not in state["seen_settled"]:
            state["seen_settled"][pid(b)] = now.isoformat()
    if not state["since"]:
        state["since"] = now.isoformat()
        state["first_run"] = now.isoformat()
        return state
    since = utc(state["since"])
    settled = [b for b in bets if b["profit"] is not None]
    todo = sorted((b for b in bets if pid(b) not in state["decided"] and active(b)
                   and (utc(b.get("logged")) or since) >= since and utc(b.get("logged"))),
                  key=lambda b: (b["logged"], pid(b)))
    boards, matches = {}, {k: [] for k in LISTS}
    for b in todo:
        t = utc(b["logged"])
        if t not in boards:
            boards[t] = board_at(t, settled, state, stage)
        top, bottom = boards[t]
        keys = {(b["sport"], n) for n in b["entities"]}
        for k, matched, snap in (("entries", keys & names_of(top), snapshot(t, top)),
                                 ("mirror", keys & names_of(bottom), snapshot(t, bottom)), ("pool", keys, None)):
            if matched:
                matches[k].append((b, matched, snap))
    verdicts = {pid(b): {} for b in todo}
    for k in LISTS:
        held = {}                                               # contract -> sides already entered on earlier runs
        for e in state[k]:
            held.setdefault(e["contract"], set()).add(e["side"])
        batch = {}
        for b, matched, snap in matches[k]:
            batch.setdefault(ckey(b), []).append((b, matched, snap))
        for c, group in batch.items():
            group.sort(key=lambda g: (g[0]["logged"], pid(g[0])))
            sides = {g[0].get("side") for g in group} | held.get(c, set())
            if len(sides) > 1:
                # Opposite sides of one contract: neither is taken. An entry made on an earlier run stays; every new
                # bet on the contract is skipped, and the skip is logged.
                for b, _m, _s in group:
                    verdicts[pid(b)][k] = "opposite"
                    state["skips"].append(dict(list=k, pid=pid(b), contract=c, side=b.get("side"), logged=b.get("logged"),
                                               at=now.isoformat(), why="active lanes are on both sides of this contract"))
                continue
            for n, (b, matched, snap) in enumerate(group):
                if c in held or n:
                    verdicts[pid(b)][k] = "duplicate"           # one bet per contract and side
                    continue
                state[k].append(entry(b, matched, snap, now))
                verdicts[pid(b)][k] = "entered"
    for b in todo:
        state["decided"][pid(b)] = dict(at=now.isoformat(), **verdicts[pid(b)])
    by_pid = {pid(b): b for b in settled}
    for k in LISTS:
        for e in state[k]:
            src = by_pid.get(e["pid"])
            if e["status"] == "open" and src is not None:
                e.update(status="won" if src["profit"] > 0 else ("lost" if src["profit"] < 0 else "settled"),
                         profit=round(src["profit"], 6), settled=src.get("settled") or state["seen_settled"].get(e["pid"]))
    state["last_run"] = now.isoformat()
    return state


def record(rows):
    done = [e for e in rows if e["status"] != "open"]
    n = len(done)
    total = sum(e["profit"] for e in done)
    return dict(entries=len(rows), open=len(rows) - n, settled=n, won=sum(e["status"] == "won" for e in done),
                profit=total, roi=(total / n) if n else None)


def status(n):
    if n >= DECIDE_AT:
        return f"{n} settled · decide now (30 reached)"
    if n >= REVIEW_AT:
        return f"{n} settled · review due (10 reached) · decide at 30"
    return f"{n} settled · review at 10, decide at 30"


def quotes(state):
    """The entries as Sandbox-ledger quotes, for the stamp-of-approval table (sandbox_track.assess): $100 a bet."""
    out = []
    for e in state.get("entries") or []:
        if e["status"] not in ("won", "lost"):
            continue
        day = str(e.get("logged") or "")[:10]
        out.append(dict(id=e["id"], source=LANE, sport=LANE, bet=True, status=e["status"], pnl=round(e["profit"] * 100, 4),
                        price=e.get("price") or 0.5, stake=100.0, logged=e.get("logged"), date=day, start=e.get("logged"),
                        pick="a", market_id=e["contract"]))
    return out


def main(argv=None):
    state = load()
    run(state)
    save(state)
    r = record(state["entries"])
    print(f"superpack: since {state['since']}, {r['entries']} entries ({r['open']} open), "
          f"{len(state['mirror'])} mirror, {len(state['pool'])} pool, {len(state['skips'])} skips")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
