"""Publish the two NBA team-total value lanes as Production pairs, from their own ledger (2026-10-24).

Moved to Production by hand by Olu on 2026-10-24, with live $1 bets (Kalshi only):

  nba_tt_value_24h   the best-EV KXNBATEAMTOTAL rung per team, read 18-26 hours before tip
                     9/15 settled, average price 35c, +64% after fees (mostly NO, 8/11)
  nba_tt_value_1h    the same, read 60-90 minutes before tip; the 24h lane looks first and holds
                     its ticker, so this one takes its next-best rung            2/2

Both buy, per team and game, the single side and rung with the largest edge when the model's
probability beats the price plus the 7% fee by 0.05 or more, a two-sided quote with a spread of
3c or less, and a price of 0.25 to 0.92 (nba_value.py has the model and the rule). They run on
their own ledger (data/nba_value_ledger.json), so this is the Econ Daily / Trump mentions / soccer
rules shape: a read-only adapter that turns their frozen entries into Sandbox-style quotes on a new
claim domain, nba_tt, builds a feed with production.build_feed and writes
data/nba_value_production_leads.json. It never writes the NBA ledger. Each lead names the exact
Kalshi contract and its side: "Philadelphia over 114.5 points" is the YES, and its NO is the claim
that the team stays under. The tip is the lead's kickoff. It runs inside nba-value.yml right after
the lanes' own read, so a lead is published while there is time to act on it. The 24h lane's leads
are therefore a day ahead of the tip.

The record is the lanes' whole record: the Production page counts "since Production" from the
promotion and keeps every earlier row on the lane. The Sandbox rows beside them (the base_*
baselines, the 1Q lanes, the fade-control lanes) are not published and are untouched.
"""
import datetime as dt
import os

import daily_track as D
import nba_value as NV

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "data", "nba_value_production_leads.json")
SPORT = "nba_tt"
PROMOTED = "2026-10-24T22:13:00+00:00"
MOVED_ON = "2026-10-24"
HEALTHY_HOURS = 3
# lane -> display name
# Both lanes went back to the Sandbox on 2026-10-28 (Olu), paper on their whole records, still
# logged by nba_value.py. The adapter stays so the feed keeps publishing, now with no pair.
PULLED_ON = "2026-10-28"
PULLED = {
    NV.TT_24H: "NBA team total value · 24h before tip",
    NV.TT_1H: "NBA team total value · 1h before tip",
}
PAIRS = {}


def pairs():
    return {f"{lane}|{SPORT}": dict(stage="production", ready_at=PROMOTED, promoted_at=PROMOTED, by_hand=MOVED_ON)
            for lane in PAIRS}


def _team(title, unit):
    """'Philadelphia' from 'Philadelphia over 114.5 points'; the ESPN code when it does not parse."""
    head, sep, _ = str(title or "").partition(" over ")
    return head.strip() if sep and head.strip() else str(unit or "")


def _quote(lane, r):
    start, logged, price = D.instant(r.get("start")), D.instant(r.get("logged")), D.number(r.get("price"))
    line = r.get("line")
    if (not start or not logged or price is None or not 0 < price < 1 or line is None
            or not str(r.get("ticker") or "").startswith("KXNBATEAMTOTAL-") or r.get("side") not in ("yes", "no")):
        return None
    status = {"open": "open", "won": "won", "lost": "lost", "no_result": "settled"}.get(r.get("status"))
    if status is None:
        return None
    pick = "a" if r["side"] == "yes" else "b"
    p = D.number(r.get("p"))               # the model's probability of the side bought
    prob_a = None if p is None else (p if pick == "a" else 1.0 - p)
    return dict(
        id=r.get("id") or f"{lane}:{r['ticker']}", source=lane, sport=SPORT, venue="kalshi_binary",
        market_id=r["ticker"], event=r.get("event"), label=str(r.get("match") or r["ticker"]),
        side_a=r.get("title") or r["ticker"], side_b="No", kalshi_title=r.get("title"),
        team=r.get("unit"), team_name=_team(r.get("title"), r.get("unit")), line=float(line),
        date=start.date().isoformat(), start=start.isoformat(), logged=logged.isoformat(),
        price=price, price_a=price if pick == "a" else None, price_b=price if pick == "b" else None,
        price_draw=None, pick=pick, bet=True, stake=100.0, status=status,
        pnl=round(float(r.get("profit") or 0), 2) if status != "open" else 0.0,
        result=("price" if status == "settled" else "a" if (status == "won") == (pick == "a") else "b")
               if status != "open" else None,
        settle_px=r.get("payout"), settled=r.get("settled"), prob_a=prob_a, edge=r.get("edge"),
        untraded=False, start_source="espn", url="")


def quotes(state):
    """The two lanes' entries as Sandbox-style quotes. Read-only: nothing is copied into any ledger."""
    out = []
    for lane in PAIRS:
        for r in ((state.get("rules") or {}).get(lane) or {}).get("picks") or []:
            q = _quote(lane, r)
            if q:
                out.append(q)
    return out


def _healthy(state, now):
    stamp = D.instant(state.get("last_run"))
    return stamp is not None and not state.get("error") and dt.timedelta(0) <= now - stamp <= dt.timedelta(hours=HEALTHY_HOURS)


def feed(state, now=None, previous=None, heartbeat=False):
    """The feed; `heartbeat` stamps it with the clock (see soccer_rules_production.feed for why that is safe)."""
    import production as P
    now = now or dt.datetime.now(dt.timezone.utc)
    rows = quotes(state)
    healthy = _healthy(state, now)
    # A stale or failed read keeps the settled history but publishes no actionable entry.
    if not healthy:
        rows = [r for r in rows if r["status"] != "open"]
    built = now if heartbeat else (D.instant(state.get("last_run")) or now)
    blob = P.build_feed({"quotes": rows}, {"pairs": pairs()}, now=built, previous=previous)
    blob["collector_healthy"] = healthy
    blob["collector_error"] = state.get("error")
    return blob


def page_inputs(d, st, blob, state, now=None):
    """Augment page inputs in memory; the original ledger, stage and feed objects are untouched."""
    current = feed(state, now=now)
    return (dict(d, quotes=list(d.get("quotes") or []) + quotes(state)),
            dict(st, pairs={**(st.get("pairs") or {}), **pairs()}),
            dict(blob, leads={**(blob.get("leads") or {}), **current["leads"]},
                 pairs={**(blob.get("pairs") or {}), **current["pairs"]}))


def main(argv=None):
    import sys
    import production as P
    beat = "--heartbeat" in (sys.argv[1:] if argv is None else argv)
    if beat and (P.feed_age_min(PATH) or 1e9) < P.HEARTBEAT_SKIP_MIN:
        return 0
    previous = P.load_feed(PATH)
    P.save_feed(feed(NV.load(), previous=previous, heartbeat=beat), PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
