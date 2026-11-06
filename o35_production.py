"""o35_cheap_no_wave v2 in Production: the feed the follower's resting-bid executor reads (2026-11-01, Olu).

The Sandbox paper lane (o35_cheap_no.py) keeps running unchanged. This file only LISTS the matches the live
rule applies to, from Kalshi's open total-goals markets in the eleven v2 leagues: the over 3.5 rung (event
ticker + "-4", floor_strike 3.5), kickoff = occurrence_datetime minus 4 hours (the paper rule's own clock).
The rule itself is carried in the feed header so the follower and the page quote one source:

  a post-only GTC NO bid at BID, STAKE dollars a match, placed an hour AFTER kickoff (second half only); when it fills
  (in play, after goals push the over up) a post-only resting sell of the filled NO at SELL (4x); the unfilled
  bid is cancelled at the final whistle; an unsold position is held to settlement. Never chases, never takes.

Written hourly by the o35 workflow and restamped by the feeds heartbeat. It writes only
data/production_o35_leads.json; the follower owns every order.
"""
import datetime as dt
import os
import sys

import daily_track as D
import o35_cheap_no as O
import production as P

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "data", "production_o35_leads.json")
NAME = "Over 3.5 cheap NO (live)"
LANE = "o35_cheap_no_wave"
MOVED_ON = "2026-11-01"
ENDED_ON = "2026-11-06"          # Olu: "return to sandbox till it's working properly" - execution off, the lane is Sandbox paper again
BID = O.HEADLINE
SELL = round(O.HEADLINE * O.HEAD_MULT, 2)
STAKE_USD = 1.0
LOOKAHEAD_H = 30
GRACE_MIN = 230                # second-half bids: a started match stays listed until about kickoff + 4h, when the follower cancels
SKIP_FRESH_MIN = 20            # a heartbeat leaves a feed this young alone


def _contract(markets):
    return O.over35(markets or [])


def leads(now, fetch=D.get):
    """[lead] for every open over 3.5 market whose kickoff is inside the window, soonest first."""
    out, errors = [], []
    lo, hi = now - dt.timedelta(minutes=GRACE_MIN), now + dt.timedelta(hours=LOOKAHEAD_H)
    for league, series in O.LEAGUES.items():
        try:
            events = D.pages(f"events?series_ticker={series}&status=open&limit=200&with_nested_markets=true", "events", fetch)
        except Exception as e:                                  # noqa: BLE001
            errors.append(f"{series}: {str(e)[:80]}")
            continue
        for ev in events:
            m = _contract(ev.get("markets"))
            if m is None or m.get("status") not in ("active", "open") or m.get("result"):
                continue
            occ = O._ts(m.get("occurrence_datetime"))
            if occ is None:
                continue
            kickoff = dt.datetime.fromtimestamp(occ - O.KICKOFF_BACK_H * 3600, O.UTC)
            if not lo <= kickoff <= hi:
                continue
            out.append(dict(id=f"{LANE}:{m['ticker']}", lane=LANE, version=O.VERSION, league=league, event=ev["event_ticker"],
                            ticker=m["ticker"], kickoff=kickoff.isoformat(), title=ev.get("title") or ev["event_ticker"],
                            side="no", bid=BID, sell=SELL, stake_usd=STAKE_USD))
    return sorted(out, key=lambda x: x["kickoff"]), errors


def feed(now=None, fetch=D.get):
    now = now or dt.datetime.now(O.UTC)
    rows, errors = leads(now, fetch)
    return dict(lane=LANE, name=NAME, version=O.VERSION, moved_on=MOVED_ON, updated_at=now.replace(microsecond=0).isoformat(),
                rule=dict(side="no", bid=BID, sell=SELL, stake_usd=STAKE_USD, bid_after_min=O.BID_AFTER_MIN,
                          kickoff_back_h=O.KICKOFF_BACK_H, leagues=sorted(O.LEAGUES)),
                errors=errors, leads=rows)


# --- the Production page (2026-11-01) -------------------------------------------------------------
# The lane is a pair on the public Production page like the other own-ledger lanes: its record is the Sandbox v3
# paper ledger (second-half 10c NO bid, 4x sell, else hold), counted from MOVED_ON; its upcoming list is the
# feed's own leads. Read-only: the ledger and the feed are never written here, and nothing here is read by the
# follower (it reads data/production_o35_leads.json, whose shape this does not change).
SPORT = "soccer_u35"       # the No of the league over 3.5 contract: the feed already names this claim (FEED_BETS)
PROMOTED = "2026-11-01T00:00:00+00:00"
HEALTHY_HOURS = 3


def pairs():
    return {f"{LANE}|{SPORT}": dict(stage="production", ready_at=PROMOTED, promoted_at=PROMOTED, by_hand=MOVED_ON)}


def _event_label(event):
    return str(event or "").split("-", 1)[-1]


def _codes(event):
    """('KAS', 'BES') from KXSUPERLIGTOTAL-26NOV01KASBES: the two team codes after the date, as the ledger has no names."""
    tail = str(event or "").rsplit("-", 1)[-1][7:]
    return (tail[:3], tail[3:]) if len(tail) >= 6 else (None, None)


def _result_quote(e):
    """One filled second-half bid of the v3 paper ledger as a Sandbox-style quote, or None. A match whose bid never
    filled is not a bet."""
    b = (e.get("bids") or {}).get(str(round(O.HEADLINE * 100)))
    if not b or e.get("version") != O.VERSION or str(e.get("night") or "") < MOVED_ON:
        return None
    s = (b.get("sells") or {}).get(str(O.HEAD_MULT)) or {}
    cost = b["limit"] + O.fee(b["limit"])
    proceeds = s["target"] - O.fee(s["target"]) if s.get("filled") else b["payout"]
    roi = (proceeds - cost) / cost
    kick = dt.datetime.fromtimestamp(e["kickoff"], O.UTC)
    logged = dt.datetime.fromtimestamp(b["fill_at"], O.UTC)
    over = e.get("result") == "yes"                       # a = the over, b = the NO this lane buys
    return dict(
        id=f"{LANE}:{e['id']}", source=LANE, sport=SPORT, venue="kalshi_binary", market_id=e["id"], event=e.get("event"),
        label=f"{_event_label(e.get('event'))} · {e.get('league')}: under 3.5 goals (second-half bid)",
        side_a="Yes", side_b="No", kalshi_title="Over 3.5 goals", league=e.get("league"), date=kick.date().isoformat(),
        start=kick.isoformat(), logged=logged.isoformat(), price=b["limit"], price_a=None, price_b=b["limit"], price_draw=None,
        pick="b", bet=True, stake=100.0, status="won" if roi > 0 else "lost", pnl=round(roi * 100, 2),
        pnl_fee_override=round(roi * 100, 2),            # the 4x exit, not a re-grade of a 10c win paid at settlement
        result="a" if over else "b", settle_px=None, settled=None, prob_a=None, edge=None, untraded=False,
        start_source="espn", url="", espn_home=_codes(e.get("event"))[0], espn_away=_codes(e.get("event"))[1],
        rule=("sold at 4x" if s.get("filled") else "held to settlement"))


def _open_quote(lead):
    k = D.instant(lead.get("kickoff"))
    if k is None:
        return None
    return dict(
        id=f"{LANE}:{lead['ticker']}", source=LANE, sport=SPORT, venue="kalshi_binary", market_id=lead["ticker"],
        event=lead.get("event"), label=f"{lead.get('title') or _event_label(lead.get('event'))}: under 3.5 goals (second-half bid)",
        side_a="Yes", side_b="No", kalshi_title="Over 3.5 goals", league=lead.get("league"), date=k.date().isoformat(),
        start=k.isoformat(), logged=(D.instant(lead.get("first_seen")) or k).isoformat(), price=BID, price_a=None, price_b=BID,
        price_draw=None, pick="b", bet=True, stake=100.0, status="open", pnl=0.0, result=None, settle_px=None, settled=None,
        prob_a=None, edge=None, untraded=False, start_source="espn", url="",
        espn_home=(str(lead.get("title") or "").partition(" v ")[0] or _codes(lead.get("event"))[0]),
        espn_away=(str(lead.get("title") or "").partition(" v ")[2] or _codes(lead.get("event"))[1]))


def quotes(ledger, leads_feed):
    """The v3 record's filled bids (settled) and the feed's upcoming matches (open), as quotes. Read-only."""
    out = [q for q in (_result_quote(e) for e in (ledger or {}).get("entries") or []) if q]
    done = {q["market_id"] for q in out}
    for lead in (leads_feed or {}).get("leads") or []:
        if lead.get("ticker") in done:
            continue
        q = _open_quote(lead)
        if q:
            out.append(q)
    return out


def page_inputs(d, st, blob, o35_ledger, now=None, leads_feed=None):
    """Augment page inputs in memory; the original ledger, stage and feed objects are untouched. `o35_ledger` is
    data/o35_cheap_no_ledger.json; `leads_feed` defaults to data/production_o35_leads.json."""
    import production as P
    if ENDED_ON:                          # back in the Sandbox: no Production pair, quotes or upcoming list (the live run is its own Sandbox row)
        return d, st, blob
    now = now or dt.datetime.now(O.UTC)
    if leads_feed is None:
        leads_feed = P.load_feed(PATH) or {}
    stamp = D.instant((leads_feed or {}).get("updated_at"))
    healthy = stamp is not None and dt.timedelta(0) <= now - stamp <= dt.timedelta(hours=HEALTHY_HOURS)
    rows = [q for q in quotes(o35_ledger, leads_feed) if q["status"] != "open" or healthy]
    current = P.build_feed({"quotes": rows}, {"pairs": pairs()}, now=now)
    return (dict(d, quotes=list(d.get("quotes") or []) + rows),
            dict(st, pairs={**(st.get("pairs") or {}), **pairs()}),
            dict(blob, leads={**(blob.get("leads") or {}), **current["leads"]},
                 pairs={**(blob.get("pairs") or {}), **current["pairs"]}))


def main(argv=None):
    heartbeat = "--heartbeat" in (sys.argv[1:] if argv is None else argv)
    age = P.feed_age_min(PATH)
    if heartbeat and age is not None and age < SKIP_FRESH_MIN:
        print("o35 feed is", round(age), "min old; left alone")
        return 0
    blob = feed()
    # a read that listed nothing because EVERY league failed must not replace a good feed with an empty one
    if blob["errors"] and len(blob["errors"]) >= len(O.LEAGUES):
        print("o35 feed not written: every league failed:", blob["errors"][:2])
        return 1
    P.save_feed(blob, PATH)
    print("o35 production feed:", len(blob["leads"]), "matches,", len(blob["errors"]), "league errors")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
