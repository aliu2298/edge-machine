"""AAA gas weekly cheap NO in Production (2026-11-22, Olu: "yes, move gas weekly to Production at $1").

The rule is the Sandbox paper lane gas_week_cheap_no (mentions_split.GAS_WEEK), unchanged: on the weekly KXAAAGASW ladder ("US gas prices this
week"), for each rung, the first minute quote inside 6h of the rung's open with a spread of 10c or less and a NO ask of 0.15-0.30 (the NO ask
is 1 - the YES bid); buy the NO at that ask and HOLD it to settlement. The ask check (the print or the book confirms the quoted ask was real)
must have verified the entry. About 3 entries a week, all on one weekly event. $1 a bet. The 2x/3x split stays a secondary shadow line on
the paper lane's own page; nothing here sells.

What this file does: every run it reads the paper lane's ledger (read only), lists each NEW verified entry logged since PROMOTED, keeps its own
ledger of those listings, grades them from the paper entries' settlement, and writes the feed the follower reads:
data/gas_week_production_leads.json. The follower owns every order, buys the real NO ask only if it is still 15-30c and the book is 10c wide
or less, and holds to settlement.

OFFER WINDOW. The rule enters at a minute; the follower can only act on what it has read. A listing is on offer for OFFER_H hours after the
paper entry was logged (the lead's `kickoff` field is the end of that offer, the follower's own 30-minute floor applies), then it drops out of
what the follower can buy. An entry logged more than LATE_LOG_H after its own entry minute (a replayed one) is never listed.

Run by the feeds heartbeat (twice an hour). Read-only on Kalshi (the close time of a new listing only).
"""
import datetime as dt
import json
import os
import sys

import daily_track as D

ROOT = os.path.dirname(os.path.abspath(__file__))
SOURCE_LEDGER = os.path.join(ROOT, "data", "gas_week_cheap_no_ledger.json")
LEDGER = os.path.join(ROOT, "data", "gas_week_production_ledger.json")
PATH = os.path.join(ROOT, "data", "gas_week_production_leads.json")
LANE = "gas_week_cheap_no"
SPORT = "gas_week"
PAIR = f"{LANE}|{SPORT}"
NAME = "AAA gas weekly cheap NO (live)"
MOVED_ON = "2026-11-22"
PROMOTED = "2026-11-22T21:00:00+00:00"       # the live record counts from here: only entries LOGGED after it are listed
BAND = (0.15, 0.30)
MAX_SPREAD = 0.10
OFFER_H = 4                                  # a listing is on offer this long after its paper entry was logged
LATE_LOG_H = 3                               # an entry logged later than this after its own minute is a replay: never listed
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


def _read_source(path=SOURCE_LEDGER):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _close_time(ticker, fetch):
    try:
        import urllib.parse
        m = fetch("markets/" + urllib.parse.quote(ticker, safe="")).get("market") or {}
        return m.get("close_time")
    except Exception:                                               # noqa: BLE001
        return None


def listable(e, now):
    """Is this paper entry one the live lane lists NOW? (verified ask, a fresh live entry, logged after promotion, still on offer)"""
    if str(e.get("side") or "").lower() != "no":
        return False
    if (e.get("ask_check") or {}).get("status") != "verified":
        return False
    logged, entered = D.instant(e.get("logged")), D.instant(e.get("entry_at"))
    if logged is None or entered is None or logged < D.instant(PROMOTED):
        return False
    if logged - entered > dt.timedelta(hours=LATE_LOG_H):
        return False
    return now < logged + dt.timedelta(hours=OFFER_H)


def _quote(e, now, fetch):
    ticker = str(e["id"])
    logged = D.instant(e["logged"])
    ends = logged + dt.timedelta(hours=OFFER_H)
    price = round(float(e["price"]), 4)
    return dict(
        id=f"{LANE}:{ticker}", source=LANE, sport=SPORT, venue="kalshi_binary", market_id=ticker, event=ticker.rsplit("-", 1)[0],
        label=f"AAA gas, week to {ticker.split('-')[1]}", side_a=str(e.get("word") or ticker), side_b="No", kalshi_title=str(e.get("word") or ""),
        league="AAA gas weekly", date=ends.date().isoformat(), start=ends.replace(microsecond=0).isoformat(),
        logged=logged.replace(microsecond=0).isoformat(), entry_at=e.get("entry_at"), closes=_close_time(ticker, fetch),
        price=price, price_a=round(1 - price, 4), price_b=price, price_draw=None, pick="b", bet=True, stake=STAKE, status="open", pnl=0.0,
        result=None, settle_px=None, settled=None, prob_a=None, edge=None, untraded=False, start_source="gas_week_offer", url="",
        spread=e.get("spread"), ask_check=(e.get("ask_check") or {}).get("how"))


def scan(now, state, source=None, fetch=D.get):
    """List new fresh entries into the ledger, then grade the open ones from the paper lane's settlements."""
    src = source if source is not None else _read_source()
    if src is None:
        state["error"] = "the paper lane's ledger could not be read"
        return state
    state["error"] = None
    entries = {str(e.get("id")): e for e in src.get("entries") or []}
    for e in entries.values():
        qid = f"{LANE}:{e.get('id')}"
        if qid not in state["quotes"] and listable(e, now):
            state["quotes"][qid] = _quote(e, now, fetch)
    for q in state["quotes"].values():
        e = entries.get(q["market_id"])
        if q["status"] != "open" or not e or e.get("status") != "settled":
            continue
        pay = e.get("payout")
        won = pay is not None and float(pay) >= 0.999
        lost = pay is not None and float(pay) <= 0.001
        p = q["price"]
        if won or lost:
            q.update(status="won" if won else "lost", result="b" if won else "a", settle_px=1.0 if won else 0.0,
                     pnl=round(STAKE * (1 / p - 1), 2) if won and p else -STAKE, settled=e.get("settled"))
        else:
            q.update(status="void", result=None, settle_px=None, pnl=0.0, settled=e.get("settled"))
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
