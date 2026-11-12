"""Calibrate fillsim's two free numbers on LIVE fills (2026-11-12). Research tooling: read-only, public data only.

fillsim cannot see the queue at a price or how long a follow-up order takes to go up. This sets both from what really happened:

  resting BUYS   every bid the follower logged as posted (data/nba_wm_decisions.json: the NBA NO fade; data/top5_dip_decisions.json)
                 against whether it really filled (data/live_record.json). Over 3.5 NO has no decision log, so its bids are the
                 Sandbox ledger's matches in the live window and leagues: weaker evidence, shown apart, not used to pick.
  resting SELLS  every live fill's sell legs (the YES split's 2x / 3x / 2.5x from the tip; the NO fade's and the dips' sell back at
                 the pregame price; over 3.5's 40c) against the legs that really sold.

Each set is split in two by a hash of the ticker. The rule is picked on half A and its hit rate reported on half B.
Run: python3 fillsim_calibrate.py [--json out.json]
"""
import datetime as dt
import hashlib
import json
import os
import sys

import fillsim as F
import fillsim_tape as T

ROOT = os.path.dirname(os.path.abspath(__file__))
QUEUES = (0.0, 5.0, 10.0, 25.0, 50.0, 100.0, 1e9)
WAITS = (0.0, 5.0, 15.0, 30.0, 60.0, 120.0, 300.0)
O35_WINDOW = ("2026-11-01T10:00", "2026-11-06T19:35")      # the lane's first and last live kickoff


def load(name):
    with open(os.path.join(ROOT, "data", name + ".json")) as f:
        return json.load(f)


def ts(iso):
    return dt.datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()


def half(ticker):
    return "A" if int(hashlib.md5(ticker.encode()).hexdigest(), 16) % 2 == 0 else "B"


def qname(q):
    return "never" if q >= 1e8 else f"{q:g}"


# ---------------------------------------------------------------- the live sets
def buy_cases(tape=T.tape):
    """[dict(set, ticker, side, placed, limit, qty, live (filled?), prints)] for every posted bid with a known live outcome."""
    live = load("live_record")["lanes"]
    out = []
    got = {r["id"] for r in live["nba_wm_nofade"]}
    for d in load("nba_wm_decisions")["decisions"].values():
        if d["lane"] == "nba_wm_nofade" and d["outcome"] == "bid_posted":
            out.append(dict(set="nba_no_fade", ticker=d["ticker"], side="no", placed=ts(d["decided_at"]), limit=d["limit"],
                            qty=d.get("qty") or 1.0, live=d["ticker"] in got, target=d["P"]))
    got = {r["id"] for r in live["top5_dip"]}
    for d in load("top5_dip_decisions")["decisions"].values():
        if d["outcome"] == "entered":
            out.append(dict(set="top5_dip", ticker=d["ticker"], side="yes", placed=ts(d["decided_at"]), limit=d["limit"],
                            qty=d.get("qty") or 1.0, live=d["ticker"] in got, target=d["P"]))
    got = {r["id"] for r in live["o35_cheap_no"]}
    leagues = set(load("production_o35_leads")["rule"]["leagues"])
    lo, hi = ts(O35_WINDOW[0] + ":00+00:00"), ts(O35_WINDOW[1] + ":00+00:00")
    seen = set()
    for e in load("o35_cheap_no_ledger")["entries"]:
        if e["id"] in seen or not lo <= e["kickoff"] <= hi or e.get("league") not in leagues:
            continue
        seen.add(e["id"])
        out.append(dict(set="o35_no (no bid log)", ticker=e["id"], side="no", placed=e["kickoff"] + 3600.0, limit=0.10, qty=10.0,
                        live=e["id"] in got, target=0.40))
    for c in out:
        c["prints"] = tape(c["ticker"])
        c["half"] = half(c["ticker"])
    return out


def sell_cases(buys, tape=T.tape):
    """[dict(set, ticker, side, target, from_ts | fill case, live (sold?))]: one per sell leg of a live fill."""
    live = load("live_record")["lanes"]
    dec = load("nba_wm_decisions")["decisions"]
    out = []
    for r in live["nba_wm_yes"]:
        d = dec.get("yes:" + r["id"])
        if not d or d["outcome"] != "enter" or r["st"] == "open":
            continue
        mults = (2.0, 2.5) if d["bot_version"] >= "wm-yes-v4" else (2.0, 3.0)
        sold = set((r.get("legs") or "").split("+"))
        for m in mults:
            out.append(dict(set="nba_yes_split", ticker=r["id"], side="yes", target=round(min(d["yes_ask"] * m, 0.98), 2),
                            up=ts(d["tip"]), entry_ts=ts(d["decided_at"]), qty=(d.get("filled") or 1.0) / 2, live=f"{m:g}x" in sold))
    rows = {(s, r["id"]): r for s, k in (("nba_no_fade", "nba_wm_nofade"), ("top5_dip", "top5_dip"), ("o35_no (no bid log)", "o35_cheap_no"))
            for r in live[k]}
    for c in buys:
        r = rows.get((c["set"], c["ticker"]))
        if r is None or r["st"] == "open":
            continue
        out.append(dict(set=c["set"].replace(" (no bid log)", "") + "_sell", ticker=c["ticker"], side=c["side"], target=c["target"],
                        buy=c, qty=c["qty"], live=bool(r.get("legs"))))
    for c in out:
        c["prints"] = tape(c["ticker"])
        c["half"] = half(c["ticker"])
    return out


# ---------------------------------------------------------------- scoring
def buy_filled(c, rules):
    # A logged bid was accepted by the exchange, so it did not cross; a bid taken from a paper ledger may have.
    r = F.resting_buy(c["prints"], c["placed"], c["limit"], c["side"], c["qty"], rules, check_cross="no bid log" in c["set"])
    return r["qty"] > F.EPS, r


def first_touch(c):
    for p in c["prints"][F._from(c["prints"], c["placed"]):]:
        if F.px_of(p, c["side"]) <= c["limit"] + F.EPS:
            return p[0]
    return None


def sell_filled(c, rules, buy_rules):
    if "up" in c:                                           # already resting from the tip
        r = F.resting_sell(c["prints"], c["up"], c["target"], c["side"], c["qty"], rules, after_fill=False)
    else:                                                   # posted after the live fill: when that was, the tape has to say
        ok, b = buy_filled(c["buy"], buy_rules)
        t0 = (b["fill_ts"] or b["first_ts"]) if ok else first_touch(c["buy"])
        if t0 is None:
            return None
        r = F.resting_sell(c["prints"], t0, c["target"], c["side"], c["qty"], rules)
    return r["qty"] > F.EPS


def score(cases, pred):
    """dict(n, live, sim, both, hit (share the sim calls right), over (sim fills live did not), under (live fills the sim missed))."""
    got = [(c["live"], pred(c)) for c in cases]
    got = [(a, b) for a, b in got if b is not None]
    n = len(got)
    both = sum(1 for a, b in got if a and b)
    return dict(n=n, live=sum(1 for a, _ in got if a), sim=sum(1 for _, b in got if b), both=both,
                hit=(sum(1 for a, b in got if a == b) / n) if n else None,
                over=sum(1 for a, b in got if b and not a), under=sum(1 for a, b in got if a and not b))


def pick(table):
    """The variant with the best half-A hit rate; ties go to the stricter (later) variant."""
    best = None
    for key, row in table:
        if row["A"]["hit"] is not None and (best is None or row["A"]["hit"] >= best[1]["A"]["hit"] - 1e-12):
            best = (key, row)
    return best


def run(tape=T.tape):
    buys = buy_cases(tape)
    core = [c for c in buys if "no bid log" not in c["set"]]
    out = dict(version=F.VERSION, buys={}, sells={}, sets={})
    table = []
    for offer in (True, False):
        for q in QUEUES:
            rules = dataclass_replace(queue_ahead=q, offer_fills=offer)
            row = {h: score([c for c in core if c["half"] == h], lambda c: buy_filled(c, rules)[0]) for h in "AB"}
            row["all"] = score(core, lambda c: buy_filled(c, rules)[0])
            row["by_set"] = {s: score([c for c in buys if c["set"] == s], lambda c: buy_filled(c, rules)[0])
                             for s in sorted({c["set"] for c in buys})}
            table.append(((qname(q), offer), row))
    key, row = pick(table)
    out["buys"] = dict(table=[dict(queue=k[0], offer_fills=k[1], **r) for k, r in table], picked=dict(queue=key[0], offer_fills=key[1]))
    q_buy = next(q for q in QUEUES if qname(q) == key[0])
    buy_rules = dataclass_replace(queue_ahead=q_buy, offer_fills=key[1])

    sells = sell_cases(buys, tape)
    resting = [c for c in sells if "up" in c]               # no wait involved: these pick the sell queue
    after = [c for c in sells if "up" not in c]             # posted after a fill: these pick the wait
    stable = []
    for offer in (True, False):
        for q in QUEUES:
            rules = dataclass_replace(queue_ahead=q, offer_fills=offer)
            row = {h: score([c for c in resting if c["half"] == h], lambda c: sell_filled(c, rules, buy_rules)) for h in "AB"}
            row["all"] = score(resting, lambda c: sell_filled(c, rules, buy_rules))
            stable.append(((qname(q), offer), row))
    skey, _ = pick(stable)
    q_sell = next(q for q in QUEUES if qname(q) == skey[0])
    wtable = []
    for w in WAITS:
        rules = dataclass_replace(queue_ahead=q_sell, offer_fills=skey[1], latency_s=w)
        row = {h: score([c for c in after if c["half"] == h], lambda c: sell_filled(c, rules, buy_rules)) for h in "AB"}
        row["all"] = score(after, lambda c: sell_filled(c, rules, buy_rules))
        row["by_set"] = {s: score([c for c in after if c["set"] == s], lambda c: sell_filled(c, rules, buy_rules))
                         for s in sorted({c["set"] for c in after})}
        wtable.append((w, row))
    wkey, _ = pick(wtable)
    out["sells"] = dict(queue_table=[dict(queue=k[0], offer_fills=k[1], **r) for k, r in stable], picked=dict(queue=skey[0], offer_fills=skey[1]),
                        wait_table=[dict(wait_s=w, **r) for w, r in wtable], picked_wait_s=wkey)
    out["sets"] = dict(buys={s: sum(1 for c in buys if c["set"] == s) for s in sorted({c["set"] for c in buys})},
                       sells={s: sum(1 for c in sells if c["set"] == s) for s in sorted({c["set"] for c in sells})})
    return out


def dataclass_replace(**kw):
    import dataclasses
    return dataclasses.replace(F.HONEST, **kw)


def _fmt(r):
    return "      -      " if not r["n"] else f"{r['hit'] * 100:5.1f}% {r['sim']:>3}/{r['live']:<3}"


def report(out):
    lines = ["RESTING BUYS (posted bids v whether they really filled). Each cell: share called right, sim fills / live fills.",
             f"  sets: {out['sets']['buys']}",
             f"  {'queue':>6} {'offer':>5}  {'half A':>13} {'half B':>13} {'all':>13}   by set"]
    for r in out["buys"]["table"]:
        sets = "  ".join(f"{s}: {_fmt(v)} (+{v['over']} -{v['under']})" for s, v in r["by_set"].items())
        lines.append(f"  {r['queue']:>6} {str(r['offer_fills']):>5}  {_fmt(r['A'])} {_fmt(r['B'])} {_fmt(r['all'])}   {sets}")
    lines.append(f"  picked on half A: {out['buys']['picked']}")
    lines += ["", "RESTING SELLS already up before the move (the YES split's legs, from the tip).",
              f"  sets: {out['sets']['sells']}", f"  {'queue':>6} {'offer':>5}  {'half A':>13} {'half B':>13} {'all':>13}"]
    for r in out["sells"]["queue_table"]:
        lines.append(f"  {r['queue']:>6} {str(r['offer_fills']):>5}  {_fmt(r['A'])} {_fmt(r['B'])} {_fmt(r['all'])}")
    lines.append(f"  picked on half A: {out['sells']['picked']}")
    lines += ["", "SELLS POSTED AFTER A FILL: how long before the sell is really up.",
              f"  {'wait s':>6}  {'half A':>13} {'half B':>13} {'all':>13}   by set"]
    for r in out["sells"]["wait_table"]:
        sets = "  ".join(f"{s}: {_fmt(v)} (+{v['over']} -{v['under']})" for s, v in r["by_set"].items())
        lines.append(f"  {r['wait_s']:>6g}  {_fmt(r['A'])} {_fmt(r['B'])} {_fmt(r['all'])}   {sets}")
    lines.append(f"  picked on half A: {out['sells']['picked_wait_s']:g} s")
    return "\n".join(lines)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    out = run()
    print(report(out))
    if "--json" in argv:
        with open(argv[argv.index("--json") + 1], "w") as f:
            json.dump(out, f, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
