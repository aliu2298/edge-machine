"""The Challenger "won here" underdog in Production (2026-11-20, Olu: "Use option 2 in production").

The rule is the Sandbox paper lane challenger_won_here_hold (challenger_form.py), unchanged in its idea: back the Challenger player
priced 15-30c (spread 5c or less) about an hour before the match who has ALREADY WON a match at this tournament (qualifying counts),
against an opponent who has not played one there, held to settlement, $1 a bet. What changes is where the tournament comes from.
Kalshi stopped naming it in product_metadata.competition on 2026-11-11, so challenger_tournament.py reads it from the market rules
text, which still names it. The replay over the named era (events through 2026-11-10) matched the named field on every event and
reproduced every paper pick (data in docs/prereg_challenger_won_here_live_2026-11-20.md). The paper lane keeps its own reading as
the control; this lane starts a fresh live record.

What this file does: every run it reads Kalshi's open Challenger events, lists the matches whose start is inside the next
LOOKAHEAD_H hours and whose pick passes the filter (the filter does not depend on the price; the follower buys only when the ask
is inside the band, an hour or so before the start), keeps its own ledger of those listings, grades them from Kalshi's results,
and writes the feed the follower reads: data/challenger_production_leads.json. The follower owns every order.

Run by the feeds heartbeat (twice an hour), so a pick is listed within half an hour of becoming one. Read-only on Kalshi.
"""
import datetime as dt
import json
import os
import sys

import challenger_form as F
import challenger_tournament as T
import daily_track as D

ROOT = os.path.dirname(os.path.abspath(__file__))
LEDGER = os.path.join(ROOT, "data", "challenger_production_ledger.json")
PATH = os.path.join(ROOT, "data", "challenger_production_leads.json")
LANE = "challenger_won_here"
SPORT = "tennis"
PAIR = f"{LANE}|{SPORT}"
NAME = "Challenger underdog who has won here (live)"
MOVED_ON = "2026-11-20"
PROMOTED = "2026-11-21T00:00:00+00:00"       # the live record counts from here; the follower starts buying with the first listing after it
BAND = (0.15, 0.30)
MAX_SPREAD = 0.05
LOOKAHEAD_H = 3                              # an event is listed up to this long before its start; the follower's own window is the last hour
LOOKBACK_DAYS = F.LOOKBACK_DAYS
HEALTHY_HOURS = 3
STAKE = 100.0
UTC = dt.timezone.utc


def load():
    try:
        with open(LEDGER) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"quotes": {}, "last_run": None, "error": None}


def save(state):
    with open(LEDGER, "w") as f:
        json.dump(state, f, indent=1, sort_keys=True)
        f.write("\n")


def _iso(ts):
    return dt.datetime.fromtimestamp(ts, UTC).replace(microsecond=0).isoformat()


def _quote(event, market, other, player, opponent, start_ts, now, price):
    day = _iso(start_ts)[:10]
    return dict(
        id=f"{LANE}:{market['ticker']}", source=LANE, sport=SPORT, venue="kalshi", market_id=event["event_ticker"],
        tickers={"a": market["ticker"], "b": other["ticker"]}, titles={"a": player, "b": opponent}, event=event["event_ticker"], label=f"{player} v {opponent}", side_a=player, side_b=opponent, kalshi_title=f"{player} wins",
        league="Tennis", team=player, opponent=opponent, date=day, start=_iso(start_ts), logged=now.replace(microsecond=0).isoformat(),
        price=price, price_a=price, price_b=None, price_draw=None, pick="a", bet=True, stake=STAKE, status="open", pnl=0.0, result=None,
        settle_px=None, settled=None, prob_a=None, edge=None, untraded=False, start_source="kalshi_challenger", url="", rule="won_here",
        tournament=T.tournament(event))


def _ask(market):
    try:
        return round(float(market.get("yes_ask_dollars")), 4)
    except (TypeError, ValueError):
        return None


def _venue_result(m):
    """'a', 'b', 'void', ('price', dollars) or None for side A's Kalshi market.

    A plain yes or no is side A or side B. Kalshi finalizes a match that never had a ball
    played (walkover, injury before the start) as result 'scalar' with a fair price per side
    (2026-11-24: Florianopolis Huertas Del Pino v Storck Franca paid 0.38 / 0.62). That goes
    through the Sandbox's own reading, sandbox_sources.classify_kalshi_market: 0.99 or more is
    side A, 0.01 or less is side B, a number between is a price payout, anything unusable is void.
    Any other result stays open.
    """
    result = str(m.get("result") or "").strip().lower()
    if result == "yes":
        return "a"
    if result == "no":
        return "b"
    if result != "scalar":
        return None
    import sandbox_sources as S
    return S.classify_kalshi_market(m)


def scan(now, state, fetch=D.get):
    """List new picks into the ledger from the open events, then grade the open ones from the settled window."""
    errors = []
    first = (now - dt.timedelta(days=LOOKBACK_DAYS + 1)).date()
    try:
        settled = F.window(F.SERIES, first, fetch)
        opened = D.pages(f"events?series_ticker={F.SERIES}&status=open&limit=200&with_nested_markets=true", "events", fetch)
    except Exception as e:                                          # noqa: BLE001
        state["error"] = f"{type(e).__name__}: {str(e)[:100]}"
        return state
    state["error"] = None
    horizon = now.timestamp() + LOOKAHEAD_H * 3600
    for ev in opened:
        ms = ev.get("markets") or []
        if len(ms) != 2 or any(m.get("status") not in ("active", "open") or m.get("result") for m in ms):
            continue
        start = min((F._ts(m.get("occurrence_datetime")) or 9e12) for m in ms)
        if not now.timestamp() <= start <= horizon:
            continue
        for ticker, player, opponent in T.picks(ev, now.timestamp(), settled):
            qid = f"{LANE}:{ticker}"
            market = next(m for m in ms if m["ticker"] == ticker)
            other = next(m for m in ms if m["ticker"] != ticker)
            if qid not in state["quotes"]:
                state["quotes"][qid] = _quote(ev, market, other, player, opponent, start, now, _ask(market))
            elif state["quotes"][qid]["status"] == "open":
                state["quotes"][qid]["price"] = state["quotes"][qid]["price_a"] = _ask(market) or state["quotes"][qid]["price"]
    by_ticker = {m["ticker"]: m for ev in settled for m in ev.get("markets") or []}
    for q in state["quotes"].values():
        m = by_ticker.get(q["tickers"]["a"])
        if q["status"] != "open" or not m:
            continue
        res = _venue_result(m)
        if res is None:
            continue
        p = q["price"]
        if isinstance(res, tuple):                      # a fair-price payout (walkover, retirement before a ball)
            paid = res[1]
            q.update(status="settled", result="price", settled=m.get("settlement_ts"), settle_px=paid,
                     pnl=round(STAKE * (paid / p - 1), 2) if p else 0.0)
            continue
        if res == "void":
            q.update(status="void", result="void", settled=m.get("settlement_ts"), settle_px=None, pnl=0.0)
            continue
        won = res == "a"
        q.update(status="won" if won else "lost", result="a" if won else "b", settled=m.get("settlement_ts"),
                 settle_px=1.0 if won else 0.0, pnl=round(STAKE * (1 / p - 1), 2) if won and p else -STAKE)
    state["last_run"] = now.replace(microsecond=0).isoformat()
    return state


def healthy(state, now):
    stamp = D.instant(state.get("last_run"))
    return stamp is not None and not state.get("error") and dt.timedelta(0) <= now - stamp <= dt.timedelta(hours=HEALTHY_HOURS)


def pairs():
    return {PAIR: dict(stage="production", ready_at=PROMOTED, promoted_at=PROMOTED, by_hand=MOVED_ON)}


def quotes(state):
    return sorted(state["quotes"].values(), key=lambda q: q["start"])


def feed(state, now=None, previous=None, heartbeat=False):
    import production as P
    now = now or dt.datetime.now(UTC)
    ok = healthy(state, now)
    rows = [q for q in quotes(state) if q["status"] != "open" or ok]
    built = now if heartbeat else (D.instant(state.get("last_run")) or now)
    blob = P.build_feed({"quotes": rows}, {"pairs": pairs()}, now=built, previous=previous)
    blob["collector_healthy"] = {LANE: ok}
    blob["collector_error"] = state.get("error")
    blob["bands"] = {PAIR: list(BAND)}
    return blob


def page_inputs(d, st, blob, state, now=None):
    """Augment page inputs in memory; the ledger, stage and feed objects are untouched."""
    current = feed(state, now=now)
    return (dict(d, quotes=list(d.get("quotes") or []) + quotes(state)),
            dict(st, pairs={**(st.get("pairs") or {}), **pairs()}),
            dict(blob, leads={**(blob.get("leads") or {}), **current["leads"]},
                 pairs={**(blob.get("pairs") or {}), **current["pairs"]}))


def main(argv=None):
    import production as P
    now = dt.datetime.now(UTC)
    state = scan(now, load())
    save(state)
    previous = P.load_feed(PATH)
    P.save_feed(feed(state, now=now, previous=previous, heartbeat=True), PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
