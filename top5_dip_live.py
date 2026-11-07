"""top5_goalless_dip_live: the paper record that FOLLOWS the live executor (2026-11-05, Olu).

The Sandbox lane (top5_dip.py) recomputes P from candles and judges the entry from trade prints. The live executor judges both from the live
book at the read an hour before kickoff, which no replay can reproduce. So this record takes its ENTRIES from the executor's own decision
snapshots (data/top5_dip_decisions.json, public market fields only, pushed from edge-vps by the same job that pushes the NBA snapshots) and
replays only the FILLS from trade prints, with the Sandbox lane's own engine (arg_dip.evaluate) and its held-fill rule:

  entry   a decision with rule_ok (the tight read, the 10-95c band, the book check) sets P (the YES ask at the read) and the bid
          round(0.55 P, 2). A decision the executor ended as a crossed bid (the book was already at or under the bid at kickoff) is NO ENTRY:
          never a fill. A bid the executor was stopped from posting (the per-matchday cap, the loss cap, funding, a halt, or posting late) still
          counts here, and the report names the difference.
  fill    a trade at or below the limit after kickoff, 10+ contracts at or below it within an hour of the first touch, and the low price HELD.
  sell    a resting sell at P placed at the fill; it fills when a later trade prints at or above P; else the match settles.
  fees    maker 0.0175 p(1-p) in and out; nothing at settlement.

  provisional  (2026-11-06) the market need not have settled for the record to know what happened to a bid. Once the replay shows the fill and
          the sell (a print at or above P after it, under the held-fill rule) the entry is written as "sold at P"; a fill still held is
          "filled, open". Both carry `provisional: true`, no result, and are re-read every run until Kalshi settles the market, when the
          same entry is completed with its result (a sold entry keeps its sale, a held one pays the settlement). A bid with no counted fill
          yet waits as before. Everton v Coventry sold at 80c at 21:12Z and the entry used to land only at 22:26Z, after settlement.

Own ledger data/top5_dip_live.json in the Sandbox lane's own shape, so its summary is arg_dip.summary. The record starts on the first
matchday a snapshot exists.
"""
import datetime as dt
import json
import os
import sys

import arg_dip as A
import chaos_replay as C
import daily_track as D
import top5_dip as T

ROOT = os.path.dirname(os.path.abspath(__file__))
DECISIONS = os.path.join(ROOT, "data", "top5_dip_decisions.json")
PATH = os.path.join(ROOT, "data", "top5_dip_live.json")
LANE = "top5_goalless_dip_live"
VERSION = "top5dip-live-v1"
HEADLINE = 0.55
MAX_PER_RUN = 40
UTC = dt.timezone.utc
CFG = dict(T.TOP5, lane=LANE, version=VERSION, fractions=(HEADLINE,), headline=HEADLINE, path=PATH, since=None)


def load(path=None):
    try:
        with open(path or PATH) as f:
            s = json.load(f)
    except FileNotFoundError:
        s = {}
    s.setdefault("lane", LANE)
    s.setdefault("version", VERSION)
    s.setdefault("since", None)
    s.setdefault("entries", [])
    s.setdefault("no_entry", {})
    return s


def load_decisions(path=None):
    try:
        with open(path or DECISIONS) as f:
            return (json.load(f) or {}).get("decisions") or {}
    except (FileNotFoundError, ValueError):
        return {}


def counts(d):
    """True when this decision is an entry of the paper record: the rule's verdict is yes and the executor did not end it as a crossed bid."""
    return bool(d.get("rule_ok")) and not d.get("crossed") and d.get("outcome") != "no_entry" and d.get("P") is not None


def _settled(m):
    return bool(m) and m.get("status") in ("finalized", "settled") and m.get("result") in ("yes", "no")


def run(state, decisions=None, now=None, fetch=D.get):
    """Replay every counting decision once the replay shows a fill. A settled market gives the final entry; before settlement a counted
    fill gives a PROVISIONAL one ("sold at P" or "filled, open"), re-read each run until the market settles and then completed in place.
    A settled entry is never rewritten."""
    now = now or dt.datetime.now(UTC)
    decisions = load_decisions() if decisions is None else decisions
    days = sorted(d.get("matchday") for d in decisions.values() if d.get("matchday"))
    state["since"] = state.get("since") or (days[0] if days else None)
    final = {e["id"] for e in state["entries"] if not e.get("provisional")} | set(state["no_entry"])
    at = {e["id"]: i for i, e in enumerate(state["entries"]) if e.get("provisional")}
    obs = dict(at=now.isoformat(), new=0, waiting=0, provisional=0, errors=[])
    done = 0
    for key, d in sorted(decisions.items(), key=lambda kv: kv[1].get("kickoff") or ""):
        if key in final:
            continue
        if d.get("outcome") == "no_entry" or d.get("crossed"):
            state["no_entry"][key] = d.get("why") or "bid crossed"
            continue
        if not counts(d):
            continue
        if done >= MAX_PER_RUN:
            break
        kick = D.instant(d.get("kickoff"))
        if kick is None or kick > now:
            obs["waiting"] += 1
            continue
        kick = int(kick.timestamp())
        try:
            ms, _archived = C.event_markets(d["event"], fetch)
            m = A.rung(ms, 1.5)
            if m is None:
                obs["waiting"] += 1
                continue
            settled = _settled(m)
            prints = A.prints_of(A.fetch_trades(m["ticker"], kick - 3600, fetch))
            buys = A.evaluate(prints, kick, d["P"], m["result"] if settled else None, CFG)
            b = buys.get(A.vkey(HEADLINE))
            if not settled and not (b and b.get("counted")):
                obs["waiting"] += 1                      # no counted fill to report yet
                continue
            entry = dict(id=key, event=d["event"], title=m.get("title") or d["event"], kickoff=kick, matchday=d.get("matchday"), league=d.get("league"),
                         result=m["result"] if settled else None, p=d["P"], bot_limit=d.get("limit"), outcome=d.get("outcome"), prints=len(prints),
                         logged=now.isoformat(), version=VERSION, buys=buys)
            if not settled:
                entry["provisional"] = True
                b["payout"] = None                       # unknown until the market settles
        except Exception as e:                                   # noqa: BLE001
            obs["errors"].append(f"{key}: {str(e)[:80]}")
            continue
        if key in at:
            entry["logged"] = state["entries"][at[key]].get("logged") or entry["logged"]
            state["entries"][at[key]] = entry
        else:
            state["entries"].append(entry)
            obs["new"] += 1
        obs["provisional"] += 1 if entry.get("provisional") else 0
        done += 1
    state["last_run"] = now.isoformat()
    state["error"] = "; ".join(obs["errors"])[:400] or None
    state["observations"] = obs
    return state


def summary(state):
    """The research-style read of the SETTLED entries; a provisional one joins it when the market settles."""
    return A.summary([e for e in state["entries"] if not e.get("provisional")], HEADLINE)


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
    print("top5_dip_live entries", len(st["entries"]), "since", st["since"], "this run", st.get("observations"), "error", st.get("error"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
