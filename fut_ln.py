#!/usr/bin/env python3
"""Soccer futures longshot NO: a Sandbox PAPER watch, "a watch, not a pass" (Olu 2026-11-14; spec = `futures_longshot_no` in docs PR 460, soccer futures study).
No orders, no VPS, nothing live.

THE LEAD: selling league-winner longshots (buying NO when a team's title YES is 3-15c) made +7.8% a bet in both seasons Kalshi has (24 bets in 11
league-seasons, no longshot won in 24 tries; found +7.0%, later +8.5%; held about 4.5 months, about +22% a year). Thin: the chance of that run under fair
prices is 0.13, and ONE winning longshot wipes out about 11 wins. Found by the study's pre-registered rules, but never confirmed.

THE RULE (docs PR 460, "Sandbox paper spec", exactly):
  * WHEN: the 1st of each month, September to April. First checkpoint here: 2026-12-01 (the build was Nov 14). A run in the first 3 days of a month still
    takes that month's checkpoint if the 1st was missed (the prices are the run's own); it is taken once a month.
  * MARKETS: every league-winner market in the EPL, La Liga, Serie A, Bundesliga, Ligue 1, Eredivisie, Primeira, Super Lig, Belgian Pro League and EFL
    Championship whose YES bid is 3c to 15c and whose spread (ask - bid) is 10c or less.
  * ENTRY: paper-buy NO at 1 - the YES bid, one entry per market per season (the market ticker is the season's), held to settlement, Kalshi taker fee
    0.07 x p x (1 - p) on the entry; nothing on settlement.
  * BASELINES: the same rule on the top-4 and relegation markets (which lose in the study). Kept apart, never pooled with the watch.
  * READ: review at 10 settled entries, decide at 30, by an EXACT binomial (not z) because losses are rare: the chance of seeing this few longshot wins or
    fewer if every longshot won at the probability its own YES bid priced (the exact Poisson-binomial tail). Settlement is a season away (about 4.5
    months), so 30 settled entries take until about mid-2027.

DISPLAY: next to the return, the capital tied up (the share of a bet that is at risk: the average cost of an entry, and the days it is held) and the
annualised figure (1 + return) ^ (365 / average days held) - 1, because the return arrives once, months later.

Runs daily in fut-ln.yml (GitHub Actions). Idempotent: one checkpoint a month, one entry per market, a settle recorded once. Own ledger data/fut_ln_ledger.json.
"""
import datetime as dt
import json
import math
import os
import sys

import daily_track as D

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "data", "fut_ln_ledger.json")
VERSION = "fut-ln-v1"
REGISTERED = "2026-11-14"
FIRST_MONTH = "2026-12"
MONTHS = (9, 10, 11, 12, 1, 2, 3, 4)
GRACE_DAYS = 3
LO, HI, MAX_SPREAD = 0.03, 0.15, 0.10
TAKER = 0.07
REVIEW_AT, DECIDE_AT = 10, 30
LEAGUES = {
    "EPL": dict(winner="KXPREMIERLEAGUE", top4="KXEPLTOP4", relegation="KXEPLRELEGATION"),
    "La Liga": dict(winner="KXLALIGA", top4="KXLALIGATOP4", relegation="KXLALIGARELEGATION"),
    "Serie A": dict(winner="KXSERIEA", top4="KXSERIEATOP4", relegation="KXSERIEARELEGATION"),
    "Bundesliga": dict(winner="KXBUNDESLIGA", top4="KXBUNDESLIGATOP4", relegation="KXBUNDESLIGARELEGATION"),
    "Ligue 1": dict(winner="KXLIGUE1", top4="KXLIGUE1TOP4", relegation="KXLIGUE1RELEGATION"),
    "Eredivisie": dict(winner="KXEREDIVISIE"),
    "Primeira": dict(winner="KXLIGAPORTUGAL"),
    "Super Lig": dict(winner="KXSUPERLIG"),
    "Belgian Pro League": dict(winner="KXBELGIANPL"),
    "EFL Championship": dict(winner="KXEFLCHAMPIONSHIP"),
}
GROUPS = {"winner": "League winner", "top4": "Top 4", "relegation": "Relegation"}
SERIES = [(s, lg, g) for lg, c in LEAGUES.items() for g, s in c.items()]


def num(v):
    try:
        return None if v in (None, "") else float(v)
    except (TypeError, ValueError):
        return None


def fee(p):
    return TAKER * p * (1 - p)


def empty():
    return dict(version=VERSION, registered=REGISTERED, first_month=FIRST_MONTH, checkpoints={}, entries={}, updated=None, errors=[])


def load(path=PATH):
    try:
        with open(path) as f:
            return dict(empty(), **json.load(f))
    except (OSError, ValueError):
        return empty()


def save(state, path=PATH):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, separators=(",", ":"), sort_keys=True)
    os.replace(tmp, path)


def due(state, now):
    """The month key of the checkpoint to take now, or None: Sep-Apr, from FIRST_MONTH, the 1st to the 3rd, once a month."""
    key = now.strftime("%Y-%m")
    if now.month not in MONTHS or key < state.get("first_month", FIRST_MONTH) or now.day > GRACE_DAYS or key in state["checkpoints"]:
        return None
    return key


def qualifies(m):
    """(yes_bid, yes_ask) when the market's YES bid is 3-15c and its spread is 10c or less, else None."""
    bid, ask = num(m.get("yes_bid_dollars")), num(m.get("yes_ask_dollars"))
    if bid is None or ask is None or ask <= 0 or not (LO - 1e-9 <= bid <= HI + 1e-9) or ask - bid > MAX_SPREAD + 1e-9:
        return None
    return bid, ask


def take(state, key, now, get=D.get):
    """Enter every qualifying market of every series once. Returns the number of new entries."""
    added, errs = 0, []
    for series, league, group in SERIES:
        try:
            d = get(f"events?series_ticker={series}&status=open&with_nested_markets=true&limit=20") or {}
        except Exception as exc:                                    # noqa: BLE001
            errs.append(f"{series}: {str(exc)[:50]}")
            continue
        for ev in d.get("events") or []:
            for m in ev.get("markets") or []:
                q = qualifies(m)
                if not q or m["ticker"] in state["entries"]:
                    continue
                bid, ask = q
                no = round(1 - bid, 4)
                state["entries"][m["ticker"]] = dict(
                    ticker=m["ticker"], series=series, league=league, group=group, event=ev["event_ticker"], team=m.get("yes_sub_title") or "",
                    month=key, day=now.strftime("%Y-%m-%d"), yes_bid=bid, yes_ask=ask, spread=round(ask - bid, 4), no_price=no, fee=round(fee(no), 5),
                    exp=m.get("expected_expiration_time"), status="open")
                added += 1
    state["checkpoints"][key] = dict(day=now.strftime("%Y-%m-%d"), added=added)
    state["errors"] = errs[:10]
    return added


def settle(state, get=D.get):
    """Settle every open entry whose market now has a result. Returns the number settled."""
    done = 0
    for series in sorted({e["series"] for e in state["entries"].values() if e["status"] == "open"}):
        d, cur, seen = None, None, {}
        for _ in range(3):
            d = get(f"events?series_ticker={series}&status=settled&limit=50&with_nested_markets=true" + (f"&cursor={cur}" if cur else "")) or {}
            for ev in d.get("events") or []:
                for m in ev.get("markets") or []:
                    seen[m["ticker"]] = m
            cur = d.get("cursor")
            if not cur:
                break
        for e in state["entries"].values():
            m = seen.get(e["ticker"])
            if e["status"] != "open" or not m or m.get("result") not in ("yes", "no"):
                continue
            cost = e["no_price"] + e["fee"]
            win = m["result"] == "no"
            e.update(status="won" if win else "lost", result=m["result"], roi=round(((1 - cost) if win else -cost) / cost, 4), settled=m.get("settlement_ts") or m.get("close_time"))
            done += 1
    return done


def run(state, now=None, get=D.get):
    now = now or dt.datetime.now(dt.timezone.utc)
    key = due(state, now)
    added = take(state, key, now, get) if key else 0
    settled = settle(state, get)
    state["updated"] = now.isoformat(timespec="seconds")
    return added, settled


# ---------------------------------------------------------------- the record
def exact_tail(ps, k):
    """P(wins <= k) for independent longshots that each win with probability ps[i]: the exact Poisson-binomial tail."""
    dist = [1.0]
    for p in ps:
        nd = [0.0] * (len(dist) + 1)
        for i, q in enumerate(dist):
            nd[i] += q * (1 - p)
            nd[i + 1] += q * p
        dist = nd
    return sum(dist[:k + 1])


def days_between(a, b):
    x, y = D.instant(a), D.instant(b)
    return max(0.0, (y - x).total_seconds() / 86400) if x and y else None


def record(state, group):
    es = [e for e in state["entries"].values() if e["group"] == group]
    done = [e for e in es if e["status"] in ("won", "lost")]
    opn = [e for e in es if e["status"] == "open"]
    n = len(done)
    wins = sum(e["status"] == "won" for e in done)
    roi = (sum(e["roi"] * (e["no_price"] + e["fee"]) for e in done) / sum(e["no_price"] + e["fee"] for e in done)) if done else None
    held = [days_between(e["day"] + "T00:00:00+00:00", e["exp"]) for e in es]
    held = [x for x in held if x is not None]
    avg_days = sum(held) / len(held) if held else None
    ann = ((1 + roi) ** (365 / avg_days) - 1) if roi is not None and avg_days and 1 + roi > 0 else None
    cost = [e["no_price"] + e["fee"] for e in es]
    ps = [e["yes_bid"] for e in done]
    longshot_wins = n - wins
    p_exact = exact_tail(ps, longshot_wins) if done else None
    gains = [1 - c for c, e in zip((e["no_price"] + e["fee"] for e in done), done) if e["status"] == "won"]
    losses = [e["no_price"] + e["fee"] for e in done if e["status"] == "lost"]
    ratio = (sum(losses) / len(losses)) / (sum(gains) / len(gains)) if losses and gains else None
    if n < REVIEW_AT:
        read = f"too early ({n} of {REVIEW_AT} settled entries; review at {REVIEW_AT}, decide at {DECIDE_AT})"
    else:
        read = (f"{'decide' if n >= DECIDE_AT else 'review'} at {DECIDE_AT if n >= DECIDE_AT else REVIEW_AT}: {longshot_wins} longshot "
                f"win{'s' if longshot_wins != 1 else ''} in {n}; chance of this few or fewer at the prices paid {p_exact:.2f}")
    return dict(group=group, n=n, open=len(opn), entries=len(es), wins=wins, longshot_wins=longshot_wins, roi=roi, avg_days=avg_days, annualised=ann,
                avg_cost=(sum(cost) / len(cost)) if cost else None, p_exact=p_exact, ratio=ratio, read=read, leagues=len({e["league"] for e in es}))


def records(state):
    return {g: record(state, g) for g in GROUPS}


def main():
    state = load()
    a, b = run(state)
    save(state)
    r = records(state)
    print(VERSION, "entered", a, "settled", b, {g: (r[g]["entries"], r[g]["n"]) for g in GROUPS}, "checkpoints", sorted(state["checkpoints"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
