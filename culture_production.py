"""Publish the Trump mentions lane (mentions_rate) as a Production pair, on its own ledger's clock.

Moved to Production by hand on 2026-10-20 (Olu): 7 of 8 settled at an average 0.78, +11.2% after
fees, every one of them from the one KXTRUMPSAY Oct 19 event, with 40 open (38 NO). That record
is thin and single-event, and the move was his call with that said.

The Culture lanes run on their own ledger (data/culture_ledger.json, culture_track.py), so this
is the same shape as Econ Daily (daily_production.py): a read-only adapter that turns the lane's
frozen entries into Sandbox-style quotes, builds a feed with production.build_feed, and writes
data/culture_production_leads.json. It never writes the culture ledger. Each lead names the exact
Kalshi contract (KXTRUMPSAY..., "Will Trump say \"X\" before ...?") and the side: YES that he
says it, NO that he does not. Kalshi closes a mentions market the moment the word is said, so
the contract's close is a deadline, not a start; a follower must re-check it is still open.
"""
import datetime as dt
import os

import culture_track as K
import daily_track as D

SOURCE = "mentions_rate"
SPORT = "culture_mentions"
PAIR = f"{SOURCE}|{SPORT}"
PROMOTED = "2026-10-21T00:45:00+00:00"
MOVED_ON = "2026-10-20"
PATH = os.path.join(K.ROOT, "data", "culture_production_leads.json")
HEALTHY_HOURS = 3                       # culture.yml reads hourly; a stale scan publishes no open lead


def pairs():
    return {PAIR: dict(stage="production", ready_at=PROMOTED, promoted_at=PROMOTED, by_hand=MOVED_ON)}


def quotes(state):
    """The lane's entries as Sandbox-style quotes. Read-only: nothing is copied into any ledger."""
    out = []
    for r in ((state.get("lanes") or {}).get(SOURCE) or {}).get("picks") or []:
        close, logged, price = D.instant(r.get("close")), D.instant(r.get("logged")), D.number(r.get("price"))
        if (not close or not logged or price is None or not 0 < price < 1
                or not str(r.get("series") or "").startswith("KXTRUMPSAY") or r.get("side") not in ("yes", "no")):
            continue
        status = {"open": "open", "won": "won", "lost": "lost", "no_result": "settled"}.get(r.get("status"))
        if status is None:
            continue
        pick = "a" if r["side"] == "yes" else "b"
        payout = r.get("payout")
        out.append(dict(
            id=f"{SOURCE}:{r['id']}", source=SOURCE, sport=SPORT, venue="kalshi_binary",
            market_id=r["id"], event=r.get("event"), label=r.get("name") or r["id"],
            side_a=r.get("title") or r["id"], side_b="No", kalshi_title=r.get("title"),
            date=close.date().isoformat(), start=close.isoformat(), logged=logged.isoformat(),
            price=price, price_a=price if pick == "a" else None, price_b=price if pick == "b" else None,
            price_draw=None, pick=pick, bet=True, stake=100.0, status=status,
            pnl=round(float(r.get("profit") or 0), 2) if status != "open" else 0.0,
            result=("price" if status == "settled" else "a" if (status == "won") == (pick == "a") else "b")
                   if status != "open" else None,
            settle_px=payout, settled=r.get("settled"), prob_a=None, edge=r.get("edge"),
            untraded=False, start_source="contract_close", url="", series=r.get("series")))
    return out


def feed(state, now=None, previous=None):
    import production as P
    now = now or dt.datetime.now(dt.timezone.utc)
    lane = (state.get("lanes") or {}).get(SOURCE) or {}
    stamp = D.instant(lane.get("last_success"))
    rows = quotes(state)
    healthy = stamp is not None and not lane.get("error") and dt.timedelta(0) <= now - stamp <= dt.timedelta(hours=HEALTHY_HOURS)
    if not healthy:
        rows = [r for r in rows if r["status"] != "open"]
    blob = P.build_feed({"quotes": rows}, {"pairs": pairs()}, now=stamp or now, previous=previous)
    blob["collector_error"] = lane.get("error")
    blob["collector_healthy"] = healthy
    return blob


def page_inputs(d, st, blob, state, now=None):
    """Augment page inputs in memory, preserving the original ledger, stage and feed objects."""
    current = feed(state, now=now)
    return (dict(d, quotes=list(d.get("quotes") or []) + quotes(state)),
            dict(st, pairs={**(st.get("pairs") or {}), **pairs()}),
            dict(blob, leads={**(blob.get("leads") or {}), **current["leads"]},
                 pairs={**(blob.get("pairs") or {}), **current["pairs"]}))


def main():
    import production as P
    previous = P.load_feed(PATH)
    P.save_feed(feed(K.load(), previous=previous), PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
