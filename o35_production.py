"""o35_cheap_no_wave v2 in Production: the feed the bot's resting-bid executor reads (2026-11-01, Olu).

The Sandbox paper lane (o35_cheap_no.py) keeps running unchanged. This file only LISTS the matches the live
rule applies to, from Kalshi's open total-goals markets in the eleven v2 leagues: the over 3.5 rung (event
ticker + "-4", floor_strike 3.5), kickoff = occurrence_datetime minus 4 hours (the paper rule's own clock).
The rule itself is carried in the feed header so the follower and the page quote one source:

  a post-only GTC NO bid at BID, STAKE dollars a match, placed about an hour before kickoff; when it fills
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
BID = O.HEADLINE
SELL = round(O.HEADLINE * O.HEAD_MULT, 2)
STAKE_USD = 1.0
LOOKAHEAD_H = 30
GRACE_MIN = 20                 # a started match stays listed this long so a slow cycle can still see it
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
                rule=dict(side="no", bid=BID, sell=SELL, stake_usd=STAKE_USD, bid_lead_min=O.BID_LEAD_MIN,
                          kickoff_back_h=O.KICKOFF_BACK_H, leagues=sorted(O.LEAGUES)),
                errors=errors, leads=rows)


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
