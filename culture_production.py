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

2026-10-26 (Olu): back to the Sandbox, on its whole record (Sandbox 35 settled, 23 won, -4.7% after
fees; the contrarian NOs under 0.80 lost). From DEMOTED_AT the pair is no longer listed (pairs() is
empty), so the feed names no open lead and nothing follows it; Polybot's risk.culture_execution was
switched off on the host at the same minute. The leads it published while in Production stay in
this feed for grading only (lane "retired", never in `pairs`), as Econ Daily's favourite band's do
(daily_production), and the pages leave them out. sandbox_track.PAIR_REMOVALS names it too
(keep_record). The lane keeps logging on paper in the Culture ledger under the 2026-10-26
amendment (culture_track.AMENDED_2).
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
DEMOTED_ON = "2026-10-26"
# The minute Polybot stopped reading this feed (risk.culture_execution off on the host): every entry
# the lane logged from PROMOTED to here was published while it was in Production.
DEMOTED_AT = "2026-10-26T16:40:00+00:00"
LABEL = "Trump mentions"
PATH = os.path.join(K.ROOT, "data", "culture_production_leads.json")
HEALTHY_HOURS = 3                       # culture.yml reads hourly; a stale scan publishes no open lead


def listed(now=None):
    """True while the pair was in Production (moved 2026-10-20, out at DEMOTED_AT)."""
    now = now or dt.datetime.now(dt.timezone.utc)
    return now < D.instant(DEMOTED_AT)


def _old_pairs():
    return {PAIR: dict(stage="production", ready_at=PROMOTED, promoted_at=PROMOTED, by_hand=MOVED_ON)}


def pairs(now=None):
    """The Production listing: the pair until DEMOTED_AT, nothing after it."""
    return _old_pairs() if listed(now) else {}


def production_era(r):
    """True for an entry logged while the pair was in Production (PROMOTED to DEMOTED_AT)."""
    t = D.instant(r.get("logged"))
    return t is not None and D.instant(PROMOTED) <= t < D.instant(DEMOTED_AT)


def removed_record(state):
    """The record the pair left Production on: its entries logged while listed, after fees per
    contract (each settled entry once, profit per $100 of cost). -> dict(won, lost, settled, open, roi)."""
    rows = [r for r in ((state.get("lanes") or {}).get(SOURCE) or {}).get("picks") or []
            if production_era(r) and str(r.get("series") or "").startswith("KXTRUMPSAY")]
    done = [r for r in rows if r.get("status") in ("won", "lost", "no_result")]
    return dict(won=sum(r["status"] == "won" for r in done), lost=sum(r["status"] == "lost" for r in done),
                settled=len(done), open=sum(r.get("status") == "open" for r in rows),
                roi=sum(float(r.get("profit") or 0) for r in done) / (100 * len(done)) if done else None)


def removed_note(state):
    """One line for the Production page and the Control Center: when it left, on what record."""
    rec = removed_record(state)
    roi = (f", {rec['roi'] * 100:+.1f}% after fees".replace("-", "\u2212") if rec["roi"] is not None else "")
    return (f"{LABEL} left Production on {DEMOTED_ON} (moved {MOVED_ON}) and is back in the Sandbox on the "
            f"Culture page, its record kept: {rec['won']} won, {rec['lost']} lost while listed{roi}; "
            f"{rec['open']} still open settle on their own.")


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
            # The model's P(said) at entry (2026-10-24), carried on the lead's bet as p_said so a
            # follower's news guard can refuse a NO the market now prices as likely said. Not prob_a:
            # that would make the lead a model pair (model_prob) for every follower reading it.
            p_said=D.number(r.get("model")),
            untraded=False, start_source="contract_close", url="", series=r.get("series")))
    return out


def feed(state, now=None, previous=None):
    import production as P
    now = now or dt.datetime.now(dt.timezone.utc)
    lane = (state.get("lanes") or {}).get(SOURCE) or {}
    stamp = D.instant(lane.get("last_success"))
    healthy = stamp is not None and not lane.get("error") and dt.timedelta(0) <= now - stamp <= dt.timedelta(hours=HEALTHY_HOURS)
    if not listed(now):
        # Out of Production (2026-10-26): no pair, no open lead. Its Production-era leads, kept for
        # grading the positions a follower already holds; never in `pairs`, so a follower that
        # checks the pairs block cannot act on one. Settled leads only, as Econ Daily's are.
        blob = P.build_feed({"quotes": []}, {"pairs": {}}, now=stamp or now, previous=previous)
        old = [q for q in quotes(state) if q["status"] != "open" and production_era(q)]
        if old:
            retired = P.build_feed({"quotes": old}, {"pairs": _old_pairs()}, now=stamp or now, previous=previous)
            for lid, lead in retired["leads"].items():
                if lid not in blob["leads"] and lead.get("status") != "pending":
                    blob["leads"][lid] = dict(lead, lane="retired", retired_on=DEMOTED_ON)
        blob["collector_error"] = lane.get("error")
        blob["collector_healthy"] = healthy
        return blob
    rows = quotes(state)
    if not healthy:
        rows = [r for r in rows if r["status"] != "open"]
    blob = P.build_feed({"quotes": rows}, {"pairs": pairs(now)}, now=stamp or now, previous=previous)
    blob["collector_error"] = lane.get("error")
    blob["collector_healthy"] = healthy
    return blob


def page_inputs(d, st, blob, state, now=None):
    """Augment page inputs in memory, preserving the original ledger, stage and feed objects.
    Out of Production (from DEMOTED_AT) there is nothing to add: the pages read it as a Sandbox lane."""
    if not listed(now):
        return d, st, blob
    current = feed(state, now=now)
    return (dict(d, quotes=list(d.get("quotes") or []) + quotes(state)),
            dict(st, pairs={**(st.get("pairs") or {}), **pairs(now)}),
            dict(blob, leads={**(blob.get("leads") or {}), **current["leads"]},
                 pairs={**(blob.get("pairs") or {}), **current["pairs"]}))


def main():
    import production as P
    previous = P.load_feed(PATH)
    P.save_feed(feed(K.load(), previous=previous), PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
