"""Re-grade the own-engine Sandbox lanes on fillsim, beside the page and the live record (2026-11-12). Research tooling.

Read-only: it reads each lane's ledger and Kalshi's public trade prints, writes one JSON file, and changes no ledger and no page.

For every entry a lane counts on its page it asks fillsim (rule set honest-v1) what a real order would have done, from the market's
trade prints, and puts three figures side by side:

  page    the lane's own return for that entry, as its ledger holds it (what the page averages)
  honest  fillsim's return for the same entry (or "no entry": the ask never traded, the bid would have crossed, a touch only)
  live    what the follower really made on that market, where it traded it (data/live_record.json)

Every return is per $1 staked after fees, and a lane's figure is the plain mean over its entries (equal stakes), the way the pages
and the live record already do it. z is clustered (a night, a week or an event is one outcome).

Run: python3 fillsim_regrade.py [--lane NAME ...] [--touch] [--json out.json]
--touch grades with the upper bracket (every print at the order's price fills it) instead of honest-v1.
"""
import datetime as dt
import json
import math
import os
import sys

import fillsim as F
import fillsim_tape as T

ROOT = os.path.dirname(os.path.abspath(__file__))
UTC = dt.timezone.utc
RULES = [F.HONEST]          # the rule set the adapters grade with (run() swaps it to grade the same entries twice)
RESULT = [T.result]         # how a market's settled result is read (run() swaps it for an offline run)


def load(name):
    with open(os.path.join(ROOT, "data", name + ".json")) as f:
        return json.load(f)


def ts(raw):
    return F._ts(raw)


def day(t):
    return dt.datetime.fromtimestamp(t, UTC).date().isoformat()


def row(key, cluster, page, sim, hold_page=None, note=None):
    """One entry: the page's return and fillsim's trade for it."""
    return dict(key=key, cluster=cluster, page=page, page_hold=hold_page,
                honest=sim.get("roi") if sim["status"] == "settled" else None,
                honest_hold=sim.get("hold") if sim["status"] == "settled" else None,
                status=sim["status"], why=sim.get("why"), note=note,
                legs=[(l["target"], l["status"]) for l in sim.get("legs") or []])


# ---------------------------------------------------------------- adapters
def split_lane(ledger, tape):
    """The cheap-side split family (mentions_split.py: Trump mentions, Album, WTI, gas, and the fights lanes): a taker buy at the
    logged ask, two resting sells, the rest held."""
    import mentions_split as MS
    state = load(ledger)
    out = []
    for e in MS.counted(state):
        if e.get("roi") is None or e.get("payout") is None:
            continue
        snap = e.get("book") or {}
        live_book = (e.get("ask_check") or {}).get("source") == "live" and (e.get("ask_check") or {}).get("how") == "book"
        sim = F.trade(tape(e["id"]), e.get("side", "yes"),
                      dict(kind="taker", ts=ts(e["entry_at"]), price=e["price"], book_size=snap.get("at_or_under") if live_book else None),
                      [dict(target=l["target"], share=l["share"]) for l in e["legs"]], payout=e["payout"], rules=RULES[0])
        out.append(row(e["id"], e["event"], e["roi"], sim, e.get("roi_held")))
    return out


def o35_lane(tape, version="v4"):
    """Over 3.5 cheap NO: a post-only NO bid at 10c from an hour after kickoff, a resting sell at 40c. v5 cancels the bid at minute 80."""
    import o35_cheap_no as O
    state = load("o35_cheap_no_ledger")
    since = O.SINCE_V5 if version == "v5" else state["since"]
    out = []
    for e in state["entries"]:
        if e["night"] < since or e.get("version") != O.VERSION:
            continue
        b = ((e.get("v5") if version == "v5" else e.get("bids")) or {}).get("10")
        page = None
        if b:
            s = b["sells"]["4"]
            cost = b["limit"] + O.fee(b["limit"])
            page = ((s["target"] - O.fee(s["target"])) if s["filled"] else b["payout"]) / cost - 1
        entry = dict(kind="rest", ts=e["kickoff"] + O.BID_AFTER_MIN * 60, price=0.10)
        if version == "v5":
            entry["cancel_ts"] = e["kickoff"] + O.CANCEL_MIN * 60
        sim = F.trade(tape(e["id"]), "no", entry, [dict(target=0.40, share=1.0)], payout=1.0 if e["result"] == "no" else 0.0, rules=RULES[0])
        hold = None if not b else b["payout"] / (b["limit"] + O.fee(b["limit"])) - 1
        out.append(row(e["id"], e["night"], page, sim, hold))
    return out


def nofade_lane(tape):
    """NBA win margin NO fade: a post-only NO bid at 75% of the pregame NO price from the tip, sold back at the pregame price."""
    import nba_wm_nofade as N
    out = []
    for g in load("nba_wm_nofade")["entries"]:
        if g.get("insample") or N.phase_of(g["night"]) != "v2":
            continue
        for b in g["buckets"]:
            if (b.get("ask") or {}).get("status") != "verified":
                continue
            limit = round(N.HEAD * b["P"], 2)
            if limit < N.MIN_LIMIT or limit >= b["P"]:
                continue
            f = (b.get("fills") or {}).get(N.vkey(N.HEAD))
            sim = F.trade(tape(b["id"]), "no", dict(kind="rest", ts=float(g["tip"]), price=limit), [dict(target=b["P"], share=1.0)],
                          payout=1.0 if b["no_wins"] else 0.0, rules=RULES[0])
            hold = None if not f else (1.0 if b["no_wins"] else 0.0) / f["cost"] - 1
            out.append(row(b["id"], g["night"], None if not f else f["profit"] / f["cost"], sim, hold))
    return out


def dip_lane(ledger, cfg, tape, live_bids=False):
    """A goalless-dip lane (arg_dip.py engine): a post-only YES bid at a fraction of the pregame price from kickoff, sold back at it."""
    import arg_dip as A
    f = cfg["headline"]
    out = []
    for e in load(ledger)["entries"]:
        if e.get("result") not in ("yes", "no") or (e.get("p_check") or {"status": "verified"}).get("status") != "verified":
            continue
        limit = e.get("bot_limit") if live_bids and e.get("bot_limit") else round(f * e["p"], 2)
        b = (e.get("buys") or {}).get(A.vkey(f))
        page = hold = None
        if b and b.get("counted"):
            cost = b["limit"] + A.fee(b["limit"])
            page = ((e["p"] - A.fee(e["p"])) if b["sold"] else b["payout"]) / cost - 1
            hold = b["payout"] / cost - 1
        sim = F.trade(tape(e["id"]), "yes", dict(kind="rest", ts=float(e["kickoff"]), price=limit), [dict(target=e["p"], share=1.0)],
                      payout=1.0 if e["result"] == "yes" else 0.0, rules=RULES[0])
        out.append(row(e["id"], str(e.get("matchday")), page, sim, hold))
    return out


def dip_hold_lane(tape, bid=0.10):
    """Trump mentions dip hold: a resting YES bid at 10c on each word from its first trade, held to the end."""
    import mentions_dip_hold as M
    state = load("mentions_dip_hold_ledger")
    page = {e["ticker"]: e["roi"] for e in M.entries(state, bid) if e["roi"] is not None}
    out = []
    for ev, body in sorted((state.get("events") or {}).items()):
        for tk, m in sorted((body.get("markets") or {}).items()):
            pay = M.payout(m)
            if pay is None or m.get("first_px") is None or m["first_px"] <= bid + F.EPS:
                continue                                    # unsettled, never traded, or opened at or under the bid: the lane's "no dip"
            sim = F.trade(tape(tk), "yes", dict(kind="rest", ts=m["first_ts"] + 1e-3, price=bid, cancel_ts=m.get("close_ts"),
                                                 check_cross=False), [], payout=pay, rules=RULES[0])
            if tk in page or sim["status"] == "settled":
                out.append(row(tk, ev, page.get(tk), sim, page.get(tk)))
    return out


def chaos_lane(name, tape):
    """A chaos_replay lane: a taker buy at the replayed ask an hour before the start, then its headline exit (hold, one target, or
    legs). Each trade's result is read from the lane's own hold row (a target row does not say who won)."""
    import chaos_replay as C
    import chaos_lanes
    L = load("chaos_ledger")["lanes"][name]
    cfg = next((x for x in chaos_lanes.LANES if x["id"] == name), {})
    h = (L.get("entry_hours") or C.ENTRY_HOURS)[0]
    trades = C.counted(L["trades"], L)
    held = {t["ticker"]: t for t in C._rows(trades, C.vkey(h, "hold"))}
    out = []
    for t in C._rows(trades, C.vkey(h, L["headline"])):
        base = held.get(t["ticker"])
        won = t["side_won"] if "side_won" in t else (base["won"] if base else None)
        if won is None or t.get("stop") is not None:
            continue
        if t.get("legs"):
            exits = [dict(target=l["target"], share=w) for l, (_m, w) in zip(t["legs"], C.LEGGED[t["exit_key"]])]
        elif t.get("target") is not None:
            exits = [dict(target=math.ceil(t["target"] * 100 - 1e-6) / 100, share=1.0)]
        else:
            exits = []
        if cfg.get("fill_from_start"):
            for x in exits:
                x["from_ts"] = t["start_ts"]
        sim = F.trade(tape(t["ticker"]), t["side"], dict(kind="taker", ts=t["entry_ts"], price=t["entry"]), exits, payout=1.0 if won else 0.0, rules=RULES[0])
        out.append(row(t["ticker"], t["night"], t["roi"], sim, base["roi"] if base else None))
    return out


def yes_bot_lane(tape, result=None):
    """The YES split exactly as the follower traded it: its own logged entries (data/nba_wm_decisions.json: the ask it paid, the
    contracts it got, the tip), its sells by version (2x and 3x; 2x and 2.5x from wm-yes-v4) in whole contracts, resting from the tip."""
    out = []
    for d in load("nba_wm_decisions")["decisions"].values():
        if d["lane"] != "nba_winmargin_live" or d["outcome"] != "enter" or not d.get("filled"):
            continue
        res = (result or RESULT[0])(d["ticker"])
        if res is None:
            continue
        mults = (2.0, 2.5) if d["bot_version"] >= "wm-yes-v4" else (2.0, 3.0)
        tip = ts(d["tip"])
        sim = F.trade(tape(d["ticker"]), "yes", dict(kind="taker", ts=ts(d["decided_at"]), price=d["yes_ask"], book_size=math.inf),
                      [dict(target=round(min(d["yes_ask"] * m, 0.98), 2), share=0.5, from_ts=tip) for m in mults],
                      payout=1.0 if res == "yes" else 0.0, qty=d["filled"], whole=True, rules=RULES[0])
        out.append(row(d["ticker"], d["slate"], None, sim))
    return out


def nofade_bot_lane(tape, result=None):
    """The NO fade exactly as the follower bid it: every bid it logged as posted (its own limit and size, up from when it was posted),
    sold back at its own pregame price."""
    out = []
    for d in load("nba_wm_decisions")["decisions"].values():
        if d["lane"] != "nba_wm_nofade" or d["outcome"] != "bid_posted":
            continue
        res = (result or RESULT[0])(d["ticker"])
        if res is None:
            continue
        sim = F.trade(tape(d["ticker"]), "no", dict(kind="rest", ts=ts(d["decided_at"]), price=d["limit"], check_cross=False),
                      [dict(target=d["P"], share=1.0)], payout=1.0 if res == "no" else 0.0, qty=d.get("qty") or 1.0, rules=RULES[0])
        out.append(row(d["ticker"], d["slate"], None, sim))
    return out


def _dip_cfgs():
    import arg_dip as A
    import top5_dip as T5
    import top5_dip_live as TL
    return A.ARG, T5.TOP5, TL.CFG


# name -> (label, headline exit: "sell" or "hold", live_record lane or None, adapter, retired?)
def lanes():
    arg, top5, top5_live = _dip_cfgs()
    return {
        "o35_cheap_no_v4": ("Over 3.5 cheap NO (v4, as traded live)", "sell", "o35_cheap_no", lambda tp: o35_lane(tp, "v4"), False),
        "o35_cheap_no_v5": ("Over 3.5 cheap NO (v5, cancel at minute 80)", "sell", None, lambda tp: o35_lane(tp, "v5"), False),
        "nba_wm_nofade": ("NBA win margin NO fade", "sell", "nba_wm_nofade", nofade_lane, False),
        "nba_winmargin_live": ("NBA win margin YES split", "sell", "nba_wm_yes", lambda tp: chaos_lane("nba_winmargin_live", tp), False),
        "nba_wm_yes_bot": ("NBA win margin YES split (the live entries)", "sell", "nba_wm_yes", yes_bot_lane, False),
        "nba_wm_nofade_bot": ("NBA win margin NO fade (the live bids)", "sell", "nba_wm_nofade", nofade_bot_lane, False),
        "top5_dip": ("Top-5 goalless dip (Sandbox)", "sell", None, lambda tp: dip_lane("top5_dip_ledger", top5, tp), False),
        "top5_dip_live": ("Top-5 goalless dip (the live bids)", "sell", "top5_dip", lambda tp: dip_lane("top5_dip_live", top5_live, tp, True), False),
        "arg_dip": ("Argentina goalless dip", "sell", "arg_dip", lambda tp: dip_lane("arg_dip_ledger", arg, tp), False),
        "mentions_dip_hold": ("Trump mentions 10c dip bid, hold", "hold", None, dip_hold_lane, False),
        "wti_cheap_yes": ("WTI cheap YES split", "sell", None, lambda tp: split_lane("wti_cheap_yes_ledger", tp), False),
        "gas_week_cheap_no": ("AAA gas weekly cheap NO", "hold", None, lambda tp: split_lane("gas_week_cheap_no_ledger", tp), False),
        "boxing_cheap_dog": ("Boxing cheap underdog split", "sell", None, lambda tp: split_lane("boxing_cheap_dog_ledger", tp), False),
        "ufc_dog": ("UFC underdog split", "sell", None, lambda tp: split_lane("ufc_dog_ledger", tp), False),
        "cfb_dog_tp50": ("College football underdog, +50% sell", "sell", None, lambda tp: chaos_lane("cfb_dog_tp50", tp), False),
        "cfb_home_dog_x4": ("College football home underdog, legs", "sell", None, lambda tp: chaos_lane("cfb_home_dog_x4", tp), False),
        "challenger_cheap_hold_base": ("Challenger cheap side, hold (baseline)", "hold", None, lambda tp: chaos_lane("challenger_cheap_hold_base", tp), False),
        "challenger_won_here_hold": ("Challenger won-here, hold", "hold", None, lambda tp: chaos_lane("challenger_won_here_hold", tp), False),
        "gas_cheap_no": ("AAA gas daily cheap NO (retired Nov 11)", "sell", None, lambda tp: split_lane("gas_cheap_no_ledger", tp), True),
        "album_cheap_rungs": ("Album cheap YES (retired Nov 11)", "sell", None, lambda tp: split_lane("album_cheap_rungs_ledger", tp), True),
        "album_cheap_no": ("Album cheap NO (retired Nov 11)", "sell", None, lambda tp: split_lane("album_cheap_no_ledger", tp), True),
    }


# ---------------------------------------------------------------- summaries
def stats(vals):
    """n, mean and clustered z of [(value, cluster)]: the larger of the plain and the cluster-summed standard error; z needs 3 clusters."""
    n = len(vals)
    if not n:
        return dict(n=0, roi=None, z=None, clusters=0)
    mean = sum(v for v, _ in vals) / n
    groups = {}
    for v, c in vals:
        groups.setdefault(c, []).append(v - mean)
    iid = (sum((v - mean) ** 2 for v, _ in vals) / max(n - 1, 1)) ** 0.5 / n ** 0.5
    clu = sum(sum(g) ** 2 for g in groups.values()) ** 0.5 / n
    se = max(iid, clu)
    return dict(n=n, roi=round(mean, 4), z=round(mean / se, 2) if len(groups) >= 3 and se > 1e-9 else None, clusters=len(groups))


def summarize(rows, exit_kind, live_rows=None):
    pk, hk = ("page", "honest") if exit_kind == "sell" else ("page_hold", "honest_hold")
    page = [(r[pk], r["cluster"]) for r in rows if r[pk] is not None]
    honest = [(r[hk], r["cluster"]) for r in rows if r[hk] is not None]
    both = [r for r in rows if r[pk] is not None and r[hk] is not None]
    why = {}
    for r in rows:
        if r[pk] is not None and r[hk] is None:
            k = (r["why"] or r["status"]).split(":")[0]
            why[k] = why.get(k, 0) + 1
    out = dict(page=stats(page), honest=stats(honest), page_on_kept=stats([(r[pk], r["cluster"]) for r in both]),
               dropped=dict(n=sum(why.values()), why=why), added=sum(1 for r in rows if r[pk] is None and r[hk] is not None),
               honest_other_exit=stats([(r["honest_hold" if exit_kind == "sell" else "honest"], r["cluster"]) for r in rows
                                        if r["honest_hold" if exit_kind == "sell" else "honest"] is not None]))
    if live_rows is not None:
        done = {r["id"]: r for r in live_rows if r.get("r") is not None and r.get("st") != "open"}
        out["live"] = stats([(r["r"], r["ko"][:10]) for r in done.values()])
        by = {r["key"]: r for r in rows}
        same = [(by[k], v) for k, v in done.items() if k in by]
        out["same_bets"] = dict(n=len(same),
                                page=stats([(r[pk], r["cluster"]) for r, _ in same if r[pk] is not None]),
                                honest=stats([(r[hk], r["cluster"]) for r, _ in same if r[hk] is not None]),
                                live=stats([(v["r"], r["cluster"]) for r, v in same]),
                                live_not_in_ledger=len(done) - len(same),
                                honest_fills_live_missed=sum(1 for r in rows if r[hk] is not None and r["key"] not in done))
    return out


def run(names=None, tape=T.settled_tape, log=print, rules=F.HONEST, result=T.result):      # every entry graded here is settled
    RULES[0], RESULT[0] = rules, result
    live = load("live_record")["lanes"]
    out = dict(rules=rules.name, generated=dt.datetime.now(UTC).isoformat(timespec="seconds"), lanes={})
    for name, (label, exit_kind, live_key, adapter, retired) in lanes().items():
        if names and name not in names:
            continue
        try:
            rows = adapter(tape)
        except Exception as e:                                      # one lane's data must not stop the others
            log(f"{name}: FAILED {type(e).__name__}: {e}")
            out["lanes"][name] = dict(label=label, error=f"{type(e).__name__}: {e}")
            continue
        s = summarize(rows, exit_kind, live.get(live_key) if live_key else None)
        out["lanes"][name] = dict(label=label, exit=exit_kind, retired=retired, live_lane=live_key, summary=s, rows=rows)
        log(line(name, s))
    return out


def _f(s):
    if not s or not s["n"]:
        return f"{'-':>18}"
    z = "" if s["z"] is None else f" z{s['z']:+.1f}"
    return f"{s['roi'] * 100:+7.1f}% n{s['n']:<4}{z:<7}"


def line(name, s):
    live = _f(s.get("live")) if "live" in s else f"{'':>18}"
    return f"{name:28} page {_f(s['page'])} honest {_f(s['honest'])} live {live} dropped {s['dropped']['n']} {s['dropped']['why']}"


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    names = [argv[i + 1] for i, a in enumerate(argv) if a == "--lane"]
    out = run(names or None, rules=F.TOUCH if "--touch" in argv else F.HONEST)
    if "--json" in argv:
        with open(argv[argv.index("--json") + 1], "w") as f:
            json.dump(out, f, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
