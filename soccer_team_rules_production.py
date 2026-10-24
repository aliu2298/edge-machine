"""Publish soccer team-scoring rule T1 as a Production pair, from its own ledger (2026-10-24).

Moved to Production by hand by Olu on 2026-10-24, with live $1 bets on Kalshi:
  T1   O+D− v O+D−, team 2+ goals, YES      Serie A, UCL, EPL, Bundesliga, Ligue 1
       Sandbox 11/18 settled, +22.3% after fees · research 38/56, +36%, z 3.17
The other seven team rules (T2-T8) stay Sandbox paper.

A sibling of soccer_rules_production (A7, A6, D3, Argentina), not an extension of it: T1 runs in
soccer-team-rules.yml on its own VPS-stamped window and its own ledger
(data/soccer_team_rules_ledger.json), so its feed is written in THAT workflow, straight after the
rules' own read, and two workflows never write one file. The shape is the same read-only adapter:
T1's frozen entries become Sandbox-style quotes ON THE EXISTING TEAM 2+ CLAIM -- the Yes of the
team's KX<league>TEAMTOTAL "over 1.5 goals" contract (soccer_team2, team_gte 2) -- so each lead
names the exact Kalshi contract, team and side, and the follower buys it as it buys every team 2+
lead. It writes data/soccer_team_rules_production_leads.json and never writes the ledger.

T1's price band is the rule's own: soccer_team_rules.PRICE_LO-PRICE_HI (3-97c) at the YES ask.
The follower re-checks that band on the live ask, and that the contract is open, before ordering.
"""
import datetime as dt
import os
import re

import daily_track as D
import soccer_rules_production as SRP
import soccer_team_rules as TR

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "data", "soccer_team_rules_production_leads.json")
PROMOTED = "2026-10-24T22:00:00+00:00"
MOVED_ON = "2026-10-24"
HEALTHY_HOURS = SRP.HEALTHY_HOURS
# rule key -> (Production source id, the soccer claim domain it publishes on, display name)
PAIRS = {
    "T1": ("st_t1", "soccer_team2", "O+D− v O+D− · team 2+ goals"),
}
LABELS = {src: name for src, _sport, name in PAIRS.values()}
BAND = (TR.PRICE_LO, TR.PRICE_HI)
TITLE_RE = re.compile(r"^Will (.+?) score over (\d+(?:\.\d+)?) goals\??$", re.I)


def pairs():
    return {f"{src}|{sport}": dict(stage="production", ready_at=PROMOTED, promoted_at=PROMOTED, by_hand=MOVED_ON)
            for src, sport, _n in PAIRS.values()}


def kalshi_title(r):
    """The contract's own Yes wording ("Roma over 1.5 goals"), which the follower matches exactly.

    The ledger keeps Kalshi's yes_sub_title as `sub` (from 2026-10-24); older entries kept only the
    market title ("Will Roma score over 1.5 goals?"), whose words are the same."""
    if r.get("sub"):
        return str(r["sub"])
    hit = TITLE_RE.match(str(r.get("title") or "").strip())
    if hit:
        return f"{hit.group(1)} over {float(hit.group(2)):g} goals"
    return None


def _quote(rule, r):
    src, sport, _n = PAIRS[rule]
    start, logged, price = D.instant(r.get("start")), D.instant(r.get("logged")), D.number(r.get("price"))
    home, _, away = str(r.get("match") or "").partition(" v ")
    team, opp = r.get("team"), r.get("opponent")
    if (not start or not logged or price is None or not 0 < price < 1 or not (home and away and team and opp)
            or r.get("side") != "yes" or r.get("line") != 1.5):
        return None
    status = {"open": "open", "won": "won", "lost": "lost", "no_result": "settled"}.get(r.get("status"))
    if status is None:
        return None
    return dict(
        id=f"{src}:{r['ticker']}", source=src, sport=sport, venue="kalshi_binary", market_id=r["ticker"],
        event=r.get("event"), label=f"{home} v {away}: {team} to score 2+", side_a="Yes", side_b="No",
        kalshi_title=kalshi_title(r), league=r.get("league"), team=team, opponent=opp,
        espn_home=home, espn_away=away, date=start.date().isoformat(), start=start.isoformat(),
        logged=logged.isoformat(), price=price, price_a=price, price_b=None, price_draw=None, pick="a", bet=True,
        stake=100.0, status=status, pnl=round(float(r.get("profit") or 0), 2) if status != "open" else 0.0,
        result=("price" if status == "settled" else "a" if status == "won" else "b") if status != "open" else None,
        settle_px=r.get("payout"), settled=r.get("settled"), prob_a=None, edge=None, untraded=False,
        start_source="espn", url="", rule=rule)


def quotes(state):
    """T1's entries as Sandbox-style quotes. Read-only."""
    out = []
    for rule in PAIRS:
        if rule not in TR.RULES:
            continue
        for r in ((state.get("rules") or {}).get(rule) or {}).get("picks") or []:
            if r.get("league") not in TR.RULES[rule]["leagues"]:
                continue
            q = _quote(rule, r)
            if q:
                out.append(q)
    return out


def feed(state, now=None, previous=None):
    import production as P
    now = now or dt.datetime.now(dt.timezone.utc)
    rows = quotes(state)
    healthy = SRP._healthy(state, now)
    ok = {src: healthy for src, _s, _n in PAIRS.values()}
    # A stale or failed read keeps the settled history but publishes no actionable entry.
    rows = [r for r in rows if r["status"] != "open" or ok.get(r["source"])]
    built = D.instant(state.get("last_run")) or now
    blob = P.build_feed({"quotes": rows}, {"pairs": pairs()}, now=built, previous=previous)
    blob["collector_healthy"] = ok
    blob["collector_error"] = state.get("error")
    blob["bands"] = {f"{src}|{sport}": list(BAND) for src, sport, _n in PAIRS.values()}
    return blob


def page_inputs(d, st, blob, state, now=None):
    """Augment page inputs in memory; the original ledger, stage and feed objects are untouched."""
    current = feed(state, now=now)
    return (dict(d, quotes=list(d.get("quotes") or []) + quotes(state)),
            dict(st, pairs={**(st.get("pairs") or {}), **pairs()}),
            dict(blob, leads={**(blob.get("leads") or {}), **current["leads"]},
                 pairs={**(blob.get("pairs") or {}), **current["pairs"]}))


def main():
    import production as P
    state = TR.load()
    previous = P.load_feed(PATH)
    P.save_feed(feed(state, previous=previous), PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
