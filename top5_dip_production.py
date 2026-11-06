"""top5_goalless_dip in Production: the feed the follower's resting-bid executor reads (2026-11-05, Olu).

The Sandbox paper lane (top5_dip.py) keeps running unchanged. This file only LISTS the matches the live rule applies to, from Kalshi's open
total-goals markets in the five big leagues and the Champions League: the over 1.5 rung (event ticker + "-2", floor_strike 1.5), kickoff =
occurrence_datetime minus 4 hours (the paper rule's own clock). The rule itself is pinned in the follower and carried in the feed header so the
follower and the page quote one source:

  an hour before kickoff the follower reads the YES ask P; from kickoff it rests ONE post-only YES bid at round(0.55 P, 2), $1 a match;
  when it fills, a resting sell at P; an unsold position is held to settlement. A bid that would cross the book is no entry. Never chases.

Written hourly by the top5-dip workflow and restamped by the feeds heartbeat. It writes only data/production_top5_dip_leads.json; the follower
owns every order. The Production RECORD is top5_dip_live.py's paper record, which follows the follower's own decisions.
"""
import datetime as dt
import os
import sys

import arg_dip as A
import daily_track as D
import production as P
import top5_dip as T
import top5_dip_live as L

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "data", "production_top5_dip_leads.json")
NAME = "Top-5 goalless dip (live)"
LANE = L.LANE
VERSION = L.VERSION
MOVED_ON = "2026-11-05"
FRACTION = L.HEADLINE
STAKE_USD = 1.0
LOOKAHEAD_H = 30
GRACE_MIN = 20                 # a match stays listed until a few minutes after kickoff: the follower posts its bid then, never later
SKIP_FRESH_MIN = 20            # a heartbeat leaves a feed this young alone
UTC = dt.timezone.utc


def leads(now, fetch=D.get):
    """[lead] for every open over 1.5 market whose kickoff is inside the window, soonest first."""
    out, errors = [], []
    lo, hi = now - dt.timedelta(minutes=GRACE_MIN), now + dt.timedelta(hours=LOOKAHEAD_H)
    for series, league in T.LEAGUES.items():
        try:
            events = D.pages(f"events?series_ticker={series}&status=open&limit=200&with_nested_markets=true", "events", fetch)
        except Exception as e:                                  # noqa: BLE001
            errors.append(f"{series}: {str(e)[:80]}")
            continue
        for ev in events:
            m = A.rung(ev.get("markets") or [], T.TOP5["strike"])
            if m is None or m.get("status") not in ("active", "open") or m.get("result"):
                continue
            occ = A._ts(m.get("occurrence_datetime"))
            if occ is None:
                continue
            kickoff = dt.datetime.fromtimestamp(occ - A.KICKOFF_BACK_H * 3600, UTC)
            if not lo <= kickoff <= hi:
                continue
            out.append(dict(id=f"{LANE}:{m['ticker']}", lane=LANE, version=VERSION, league=league, event=ev["event_ticker"],
                            ticker=m["ticker"], kickoff=kickoff.isoformat(), title=ev.get("title") or ev["event_ticker"],
                            side="yes", fraction=FRACTION, stake_usd=STAKE_USD))
    return sorted(out, key=lambda x: x["kickoff"]), errors


def feed(now=None, fetch=D.get):
    now = now or dt.datetime.now(UTC)
    rows, errors = leads(now, fetch)
    return dict(lane=LANE, name=NAME, version=VERSION, moved_on=MOVED_ON, updated_at=now.replace(microsecond=0).isoformat(),
                rule=dict(side="yes", fraction=FRACTION, stake_usd=STAKE_USD, kickoff_back_h=A.KICKOFF_BACK_H,
                          leagues=sorted(T.LEAGUES.values()), strike=T.TOP5["strike"]),
                errors=errors, leads=rows)


# --- the Production page ----------------------------------------------------------------------------
# A pair on the public Production page like the other own-ledger lanes: its record is the paper lane that follows the executor
# (top5_dip_live), counted from the first matchday a decision snapshot exists; its upcoming list is the feed's own leads. Read-only.
SPORT = "soccer_o15"       # the Yes of the league over 1.5 contract: the feed already names this claim (FEED_BETS)
PROMOTED = "2026-11-05T00:00:00+00:00"
HEALTHY_HOURS = 3


def pairs():
    return {f"{LANE}|{SPORT}": dict(stage="production", ready_at=PROMOTED, promoted_at=PROMOTED, by_hand=MOVED_ON)}


# The paper lane names the leagues as its own ledger does ("EPL", "UCL"); the feed's league names are the venue's ("Premier League", "Champions
# League"). The page's copy of a quote carries the feed's name, or placeable() finds no feed league and calls the bet unpublishable (2026-11-06:
# 5 of 22 recent bets, all EPL). The lane's own ledger and its feed file are untouched.
FEED_LEAGUE = {"EPL": "Premier League", "UCL": "Champions League"}


def _event_label(event):
    return str(event or "").split("-", 1)[-1]


def _codes(event):
    tail = str(event or "").rsplit("-", 1)[-1][7:]
    return (tail[:3], tail[3:]) if len(tail) >= 6 else (None, None)


def _result_quote(e):
    """One counted fill of the live paper record as a Sandbox-style quote, or None. A bid that never filled is not a bet."""
    b = (e.get("buys") or {}).get(A.vkey(FRACTION))
    if not b or not b.get("counted") or str(e.get("matchday") or "") < MOVED_ON:
        return None
    cost = b["limit"] + A.fee(b["limit"])
    proceeds = (e["p"] - A.fee(e["p"])) if b["sold"] else b["payout"]
    roi = (proceeds - cost) / cost
    kick = dt.datetime.fromtimestamp(e["kickoff"], UTC)
    logged = dt.datetime.fromtimestamp(b["fill_at"], UTC)
    over = e.get("result") == "yes"
    return dict(
        id=f"{LANE}:{e['id']}", source=LANE, sport=SPORT, venue="kalshi_binary", market_id=e["id"], event=e.get("event"),
        label=f"{_event_label(e.get('event'))} · {e.get('league')}: over 1.5 goals (dip bid)",
        side_a="Yes", side_b="No", kalshi_title="Over 1.5 goals", league=FEED_LEAGUE.get(e.get("league"), e.get("league")), date=kick.date().isoformat(),
        start=kick.isoformat(), logged=logged.isoformat(), price=b["limit"], price_a=b["limit"], price_b=None, price_draw=None,
        pick="a", bet=True, stake=100.0, status="won" if roi > 0 else "lost", pnl=round(roi * 100, 2),
        pnl_fee_override=round(roi * 100, 2),            # the sell at P, not a re-grade of a dip fill paid at settlement
        result="a" if over else "b", settle_px=None, settled=None, prob_a=None, edge=None, untraded=False,
        start_source="espn", url="", espn_home=_codes(e.get("event"))[0], espn_away=_codes(e.get("event"))[1],
        rule=("sold at P" if b["sold"] else "held to settlement"))


def _open_quote(lead):
    k = D.instant(lead.get("kickoff"))
    if k is None:
        return None
    return dict(
        id=f"{LANE}:{lead['ticker']}", source=LANE, sport=SPORT, venue="kalshi_binary", market_id=lead["ticker"],
        event=lead.get("event"), label=f"{lead.get('title') or _event_label(lead.get('event'))}: over 1.5 goals (dip bid)",
        side_a="Yes", side_b="No", kalshi_title="Over 1.5 goals", league=FEED_LEAGUE.get(lead.get("league"), lead.get("league")), date=k.date().isoformat(),
        start=k.isoformat(), logged=(D.instant(lead.get("first_seen")) or k).isoformat(), price=None, price_a=None, price_b=None,
        price_draw=None, pick="a", bet=True, stake=100.0, status="open", pnl=0.0, result=None, settle_px=None, settled=None,
        prob_a=None, edge=None, untraded=False, start_source="espn", url="",
        espn_home=(str(lead.get("title") or "").partition(" v ")[0] or _codes(lead.get("event"))[0]),
        espn_away=(str(lead.get("title") or "").partition(" v ")[2] or _codes(lead.get("event"))[1]))


def quotes(ledger, leads_feed):
    """The live paper record's filled bids (settled) and the feed's upcoming matches (open), as quotes. Read-only."""
    out = [q for q in (_result_quote(e) for e in (ledger or {}).get("entries") or []) if q]
    done = {q["market_id"] for q in out}
    for lead in (leads_feed or {}).get("leads") or []:
        if lead.get("ticker") in done:
            continue
        q = _open_quote(lead)
        if q:
            out.append(q)
    return out


def page_inputs(d, st, blob, live_ledger, now=None, leads_feed=None):
    """Augment page inputs in memory; the original ledger, stage and feed objects are untouched. `live_ledger` is data/top5_dip_live.json;
    `leads_feed` defaults to data/production_top5_dip_leads.json."""
    now = now or dt.datetime.now(UTC)
    if leads_feed is None:
        leads_feed = P.load_feed(PATH) or {}
    stamp = D.instant((leads_feed or {}).get("updated_at"))
    healthy = stamp is not None and dt.timedelta(0) <= now - stamp <= dt.timedelta(hours=HEALTHY_HOURS)
    rows = [q for q in quotes(live_ledger, leads_feed) if q["status"] != "open" or healthy]
    current = P.build_feed({"quotes": rows}, {"pairs": pairs()}, now=now)
    return (dict(d, quotes=list(d.get("quotes") or []) + rows),
            dict(st, pairs={**(st.get("pairs") or {}), **pairs()}),
            dict(blob, leads={**(blob.get("leads") or {}), **current["leads"]},
                 pairs={**(blob.get("pairs") or {}), **current["pairs"]}))


def main(argv=None):
    heartbeat = "--heartbeat" in (sys.argv[1:] if argv is None else argv)
    age = P.feed_age_min(PATH)
    if heartbeat and age is not None and age < SKIP_FRESH_MIN:
        print("top5 dip feed is", round(age), "min old; left alone")
        return 0
    blob = feed()
    # a read that listed nothing because EVERY league failed must not replace a good feed with an empty one
    if blob["errors"] and len(blob["errors"]) >= len(T.LEAGUES):
        print("top5 dip feed not written: every league failed:", blob["errors"][:2])
        return 1
    P.save_feed(blob, PATH)
    print("top5 dip production feed:", len(blob["leads"]), "matches,", len(blob["errors"]), "league errors")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
