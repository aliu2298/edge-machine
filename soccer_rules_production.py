"""Publish four soccer label/league rules as Production pairs, from their own ledgers (2026-10-21).

Moved to Production by hand by Olu on 2026-10-21, on small samples, with live $1 bets:
  A7   Champions League, either team O+D-      over 3.5 YES <=55c    4/7,   +$0.74 per $1
  A6   Premier League, O-D- team v O+ opponent  under 2.5 NO <=55c    2/2,   +$0.95
  D3   O-D- v O+D-, 14 BTTS leagues             BTTS YES 40-70c       11/15, +$2.01
  ARG  Argentina over 1.5, every league match   over 1.5 YES at ask   3/3,   +$0.97
(Brasileirao, sa_o15's other row, stays in the Sandbox.)

These rules run on their own ledgers (data/soccer_rules_ledger.json, data/sa_o15_ledger.json), so
this is the Econ Daily / Trump mentions shape: a read-only adapter that turns their frozen entries
into Sandbox-style quotes ON THE EXISTING SOCCER CLAIMS -- over 3.5 is the Yes of the
KX<league>TOTAL over-3.5 contract (soccer_u35, total_gte 4), under 2.5 the No of the over-2.5
contract (soccer_o25, total_lte 2), BTTS the Yes of KX<league>BTTS (soccer_btts), over 1.5 the
Yes of the over-1.5 contract (soccer_o15, total_gte 2) -- so the follower buys them exactly as it
buys every other soccer lead. It writes data/soccer_rules_production_leads.json and never writes
either ledger. It runs inside soccer-rules.yml right after the rules' own read (90 to 20 minutes
before kickoff), so a lead is published while there is time to act on it.
"""
import datetime as dt
import os

import daily_track as D
import sa_o15 as SA
import soccer_rules as SR

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "data", "soccer_rules_production_leads.json")
PROMOTED = "2026-10-21T23:00:00+00:00"
MOVED_ON = "2026-10-21"
HEALTHY_HOURS = 3
# rule key -> (Production source id, the soccer claim domain it publishes on, display name)
PAIRS = {
    "A7": ("sr_a7", "soccer_u35", "UCL either team O+D− · over 3.5"),
    "A6": ("sr_a6", "soccer_o25", "EPL O−D− v an O+ opponent · under 2.5"),
    "D3": ("sr_d3", "soccer_btts", "O−D− v O+D− · both teams to score"),
    "ARG": ("sa_o15_arg", "soccer_o15", "Argentina over 1.5"),
}
LABELS = {src: name for src, _sport, name in PAIRS.values()}
# Leagues a rule logs in but does NOT publish to Production. 2026-10-22, as asked (Olu), before
# Europa League matchday 3: D3 replayed on 2026-27 UEL games (labels from each team's last 10
# competitive matches, against the UEL mean of 1.37 goals per team) went 3/10, -47% (league phase
# 2/5) -- in the UEL the O-D- side often fails to score -- and its research edge was La Liga, Serie
# A, Primeira and the UCL. soccer_rules.py still logs D3 there, so the UEL keeps being measured
# as Sandbox paper on the same ledger; it is simply never a Production lead.
NOT_PUBLISHED = {"D3": {"Europa League"}}


def pairs():
    return {f"{src}|{sport}": dict(stage="production", ready_at=PROMOTED, promoted_at=PROMOTED, by_hand=MOVED_ON)
            for src, sport, _n in PAIRS.values()}


def _title(rule, line):
    """The contract's own Yes wording, which the follower matches exactly."""
    return "Both Teams To Score" if rule == "D3" else f"Over {line:g} goals scored"


def _quote(rule, r, league):
    src, sport, _n = PAIRS[rule]
    start, logged, price = D.instant(r.get("start")), D.instant(r.get("logged")), D.number(r.get("price"))
    home, _, away = str(r.get("match") or "").partition(" v ")
    if not start or not logged or price is None or not 0 < price < 1 or not (home and away):
        return None
    status = {"open": "open", "won": "won", "lost": "lost", "no_result": "settled"}.get(r.get("status"))
    if status is None:
        return None
    pick = "a" if r.get("side") == "yes" else "b"
    line = r.get("line")
    return dict(
        id=f"{src}:{r['ticker']}", source=src, sport=sport, venue="kalshi_binary", market_id=r["ticker"],
        event=r.get("event"), label=f"{home} v {away}", side_a="Yes", side_b="No",
        kalshi_title=_title(rule, line if line is not None else 0), league=league,
        espn_home=home, espn_away=away, date=start.date().isoformat(), start=start.isoformat(),
        logged=logged.isoformat(), price=price, price_a=price if pick == "a" else None,
        price_b=price if pick == "b" else None, price_draw=None, pick=pick, bet=True, stake=100.0,
        status=status, pnl=round(float(r.get("profit") or 0), 2) if status != "open" else 0.0,
        result=("price" if status == "settled" else "a" if (status == "won") == (pick == "a") else "b")
               if status != "open" else None,
        settle_px=r.get("payout"), settled=r.get("settled"), prob_a=None, edge=None, untraded=False,
        start_source="espn", url="", rule=rule)


def quotes(rules_state, sa_state):
    """The four rules' entries as Sandbox-style quotes. Read-only."""
    out = []
    for rule in ("A7", "A6", "D3"):
        for r in ((rules_state.get("rules") or {}).get(rule) or {}).get("picks") or []:
            if r.get("league") in NOT_PUBLISHED.get(rule, ()) or (
                    rule == "D3" and str(r.get("ticker") or "").startswith("KXUELBTTS")):
                continue
            q = _quote(rule, r, r.get("league"))
            if q:
                out.append(q)
    for r in ((sa_state.get("rules") or {}).get("ARG") or {}).get("picks") or []:
        # sa_o15 logs ESPN's league name ("Liga Profesional"); the feed's soccer leagues name it so.
        q = _quote("ARG", r, r.get("league") or "Liga Profesional")
        if q:
            out.append(q)
    return out


def _healthy(state, now):
    stamp = D.instant(state.get("last_run"))
    return stamp is not None and not state.get("error") and dt.timedelta(0) <= now - stamp <= dt.timedelta(hours=HEALTHY_HOURS)


def feed(rules_state, sa_state, now=None, previous=None):
    import production as P
    now = now or dt.datetime.now(dt.timezone.utc)
    rows = quotes(rules_state, sa_state)
    ok = {"sa_o15_arg": _healthy(sa_state, now)}
    ok.update({PAIRS[k][0]: _healthy(rules_state, now) for k in ("A7", "A6", "D3")})
    # A stale or failed read keeps the settled history but publishes no actionable entry.
    rows = [r for r in rows if r["status"] != "open" or ok.get(r["source"])]
    stamps = [D.instant(s.get("last_run")) for s in (rules_state, sa_state)]
    built = max([s for s in stamps if s] or [now])
    blob = P.build_feed({"quotes": rows}, {"pairs": pairs()}, now=built, previous=previous)
    blob["collector_healthy"] = ok
    blob["collector_error"] = rules_state.get("error") or sa_state.get("error")
    return blob


def page_inputs(d, st, blob, rules_state, sa_state, now=None):
    """Augment page inputs in memory; the original ledger, stage and feed objects are untouched."""
    current = feed(rules_state, sa_state, now=now)
    return (dict(d, quotes=list(d.get("quotes") or []) + quotes(rules_state, sa_state)),
            dict(st, pairs={**(st.get("pairs") or {}), **pairs()}),
            dict(blob, leads={**(blob.get("leads") or {}), **current["leads"]},
                 pairs={**(blob.get("pairs") or {}), **current["pairs"]}))


def load_states():
    return SR.load(), SA.load()


def main():
    import production as P
    rules_state, sa_state = load_states()
    previous = P.load_feed(PATH)
    P.save_feed(feed(rules_state, sa_state, previous=previous), PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
