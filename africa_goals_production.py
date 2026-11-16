"""Publish two African-qualifier legs as Production pairs, from africa_goals' own ledger (2026-11-16).

Olu, Nov 16 ("three legs to Production as trials"; the evidence test waived: these are POST-HOC splits of the Nov 12-14 window), the same
entry as the observation lane: the ask on the hourly quote three hours before the ESPN kickoff, held to settlement, every AFCON qualifier
Kalshi lists.

  afq_dog_score   YES on the UNDERDOG to score: the side whose to-score YES ask is under 60c (the Yes of "<team> over 0.5 goals")
  afq_btts        YES on both teams to score, every match (the Yes of KXAFCONBTTS)

A THIRD leg, afq_u35_80 (NO on over 3.5 when the NO ask is 80c or more), is NOT here. It went 7 of 7 in November and 22 of 29 at 83c in
September (-10%): it stays Sandbox paper until Olu confirms.

A sibling of soccer_team_rules_production, not an extension: africa_goals runs in soccer-p4.yml on its own ledger, so its feed is
written in THAT workflow right after the read, and two workflows never write one file. Read-only adapter: it writes
data/africa_goals_production_leads.json and never the ledger. Pairs are fresh live records from PROMOTED.

Idle by design: the window closes Nov 17 and Kalshi may list no more qualifiers until the next window (about March 2027); the feed is
then valid and empty, and the legs fire on their own when matches are listed.
"""
import datetime as dt
import os

import africa_goals as AG
import daily_track as D
import soccer_rules_production as SRP
import soccer_team_rules_production as TRP

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "data", "africa_goals_production_leads.json")
MOVED_ON = "2026-11-16"
PROMOTED = "2026-11-16T18:00:00+00:00"
HEALTHY_HOURS = SRP.HEALTHY_HOURS
DOG_BELOW = 0.60                        # the underdog: the to-score YES ask is under this
U35_NO_FROM = 0.80                      # afq_u35_80 (Sandbox paper): the NO ask is this or more
BAND = {"DOG": (0.02, DOG_BELOW), "BTTS": (AG.PRICE_MIN, AG.PRICE_MAX)}
# leg key -> (Production source id, the claim domain it publishes on, display name)
PAIRS = {
    "DOG": ("afq_dog_score", "soccer_team1_intl", "African qualifiers · underdog to score"),
    "BTTS": ("afq_btts", "soccer_btts_intl", "African qualifiers · both teams to score"),
}
LABELS = {src: name for src, _s, name in PAIRS.values()}


def pairs():
    return {f"{src}|{sport}": dict(stage="production", ready_at=PROMOTED, promoted_at=PROMOTED, by_hand=MOVED_ON)
            for src, sport, _n in PAIRS.values()}


def dog_picks(state):
    """T1 picks whose YES ask is under 60c: the underdog of each match. A match whose two sides are both under 60c has two."""
    return AG.leg_picks(state, "DOG")


def btts_picks(state):
    return AG.leg_picks(state, "BTTS")


def _quote(leg, r):
    src, sport, _n = PAIRS[leg]
    start, logged, price = D.instant(r.get("start")), D.instant(r.get("logged")), D.number(r.get("price"))
    home, _, away = str(r.get("match") or "").partition(" v ")
    status = {"open": "open", "won": "won", "lost": "lost", "no_result": "settled"}.get(r.get("status"))
    if not start or not logged or price is None or not 0 < price < 1 or not (home and away) or status is None:
        return None
    if leg == "DOG":
        team = r.get("team")
        if not team or r.get("side") != "yes":
            return None
        opp = away if AG.same_team(team, home) else home
        title = TRP.kalshi_title(r)
        label = f"{home} v {away}: {team} to score"
    else:
        team = opp = None
        title = "Both teams to score"
        label = f"{home} v {away}"
    return dict(
        id=f"{src}:{r['ticker']}", source=src, sport=sport, venue="kalshi_binary", market_id=r["ticker"], event=r.get("event"),
        label=label, side_a="Yes", side_b="No", kalshi_title=title, league=r.get("league"), team=team, opponent=opp,
        espn_home=home, espn_away=away, date=start.date().isoformat(), start=start.isoformat(), logged=logged.isoformat(), price=price,
        price_a=price, price_b=None, price_draw=None, pick="a", bet=True, stake=100.0, status=status,
        pnl=round(float(r.get("profit") or 0), 2) if status != "open" else 0.0,
        result=("price" if status == "settled" else ("a" if status == "won" else "b")) if status != "open" else None,
        settle_px=r.get("payout"), settled=r.get("settled"), prob_a=None, edge=None, untraded=False, start_source="espn", url="", rule=leg)


def quotes(state):
    """The two legs' entries as Sandbox-style quotes. Read-only. A no-fill (refuted ask) is not a bet."""
    out = []
    for leg, picks in (("DOG", dog_picks(state)), ("BTTS", btts_picks(state))):
        for r in picks:
            q = _quote(leg, r)
            if q:
                out.append(q)
    return out


def feed(state, now=None, previous=None, heartbeat=False):
    import production as P
    now = now or dt.datetime.now(dt.timezone.utc)
    rows = quotes(state)
    healthy = SRP._healthy(state, now)
    ok = {src: healthy for src, _s, _n in PAIRS.values()}
    rows = [r for r in rows if r["status"] != "open" or ok.get(r["source"])]
    built = now if heartbeat else (D.instant(state.get("last_run")) or now)
    blob = P.build_feed({"quotes": rows}, {"pairs": pairs()}, now=built, previous=previous)
    blob["collector_healthy"] = ok
    blob["collector_error"] = state.get("error")
    blob["bands"] = {f"{src}|{sport}": list(BAND[leg]) for leg, (src, sport, _n) in PAIRS.items()}
    return blob


def page_inputs(d, st, blob, state, now=None):
    """Augment page inputs in memory; the ledger, stage and feed objects are untouched."""
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
    state = AG.load()
    previous = P.load_feed(PATH)
    P.save_feed(feed(state, previous=previous, heartbeat=beat), PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
