#!/usr/bin/env python3
"""Offline checks for team-scoring rule T1's Production feed (soccer_team_rules_production.py, 2026-10-24)."""
import datetime as dt
import sys

import control_center as CC
import production as P
import sandbox_audit
import sandbox_sources as S
import sandbox_track as T
import soccer_team_rules as TR
import soccer_team_rules_build as TB
import soccer_team_rules_production as TP

FAILS = []
UTC = dt.timezone.utc
NOW = dt.datetime(2026, 10, 25, 13, 5, tzinfo=UTC)


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


def pick(rule, ticker, match, team, opp, league, price, status="open", start="2026-10-25T14:00Z",
         logged="2026-10-25T13:00:00+00:00", side="yes", line=1.5, **kw):
    ev = ticker.rsplit("-", 1)[0]
    short = team.split()[-1]
    return dict(dict(id=f"{rule}:{ev}:{'home' if match.startswith(team) else 'away'}", rule=rule, ticker=ticker, event=ev,
                     match=match, team=team, opponent=opp, league=league, side=side, price=price, line=line,
                     start=start, logged=logged, status=status, title=f"Will {short} score over {line:g} goals?"), **kw)


state = {"last_run": (NOW - dt.timedelta(minutes=10)).isoformat(), "error": None, "rules": {
    "T1": {"picks": [
        pick("T1", "KXEPLTEAMTOTAL-26OCT25LFCBRI-LFC2", "Liverpool v Brighton", "Liverpool", "Brighton", "Premier League", 0.56),
        pick("T1", "KXEPLTEAMTOTAL-26OCT25LFCBRI-BRI2", "Liverpool v Brighton", "Brighton", "Liverpool", "Premier League", 0.43,
             sub="Brighton over 1.5 goals"),
        pick("T1", "KXSERIEATEAMTOTAL-26OCT24NAPROM-ROM2", "Napoli v AS Roma", "AS Roma", "Napoli", "Serie A", 0.41,
             status="won", start="2026-10-24T16:00Z", logged="2026-10-24T14:31:00+00:00", profit=134.23, payout=1.0),
        # A T1 entry outside its five leagues is never published (it cannot be logged there today).
        pick("T1", "KXLALIGATEAMTOTAL-26OCT25RMABAR-RMA2", "Real Madrid v Barcelona", "Real Madrid", "Barcelona", "La Liga", 0.60)]},
    "T4": {"picks": [pick("T4", "KXEPLTEAMTOTAL-26OCT25CRYNEW-CRY2", "Crystal Palace v Newcastle", "Crystal Palace",
                          "Newcastle", "Premier League", 0.45)]}}}

print("only T1, on the existing team 2+ claim")
qs = TP.quotes(state)
check("T1 alone, its five leagues only", sorted(q["market_id"] for q in qs),
      sorted(["KXEPLTEAMTOTAL-26OCT25LFCBRI-LFC2", "KXEPLTEAMTOTAL-26OCT25LFCBRI-BRI2", "KXSERIEATEAMTOTAL-26OCT24NAPROM-ROM2"]))
check("on soccer_team2, the Yes, with the team and opponent", {(q["sport"], q["pick"], q["source"]) for q in qs},
      {("soccer_team2", "a", "st_t1")})
check("Kalshi's own Yes words: the ledger's sub when kept, else from the market title",
      sorted(q["kalshi_title"] for q in qs), ["Brighton over 1.5 goals", "Liverpool over 1.5 goals", "Roma over 1.5 goals"])
check("all may be published, on an ESPN-verified start", [(T.placeable(q), P.start_verified(q)) for q in qs], [(True, True)] * 3)
check("T1's band is the rule's own 3-97c", TP.BAND, (TR.PRICE_LO, TR.PRICE_HI))

print("\nthe leads: the exact contract, team and side")
f = TP.feed(state, now=NOW)
leads = {l["route"]["market"]: l for l in f["leads"].values()}
check("one pair, moved by hand 2026-10-24", (sorted(f["pairs"]), f["pairs"]["st_t1|soccer_team2"]["by_hand"]),
      (["st_t1|soccer_team2"], "2026-10-24"))
lfc = leads["KXEPLTEAMTOTAL-26OCT25LFCBRI-LFC2"]
check("Liverpool 2+ is the Yes of the LFC over-1.5 contract, named as Kalshi names it",
      (lfc["bet"], lfc["route"]["outcome_side"], lfc["route"]["outcome"], lfc["league"]),
      ({"kind": "team_gte", "n": 2, "team": "Liverpool"}, "yes", "Liverpool over 1.5 goals", "Premier League"))
check("both sides of one match are two leads (two contracts)", sorted(leads),
      ["KXEPLTEAMTOTAL-26OCT25LFCBRI-BRI2", "KXEPLTEAMTOTAL-26OCT25LFCBRI-LFC2"])
check("the settled Roma entry kicked off before Production, so it is not a lead",
      "KXSERIEATEAMTOTAL-26OCT24NAPROM-ROM2" in leads, False)
check("each lead names its rule", {l["id"].split(" · ", 1)[1] for l in f["leads"].values()}, set(TP.LABELS.values()))
check("the feed carries the band it publishes on", f["bands"], {"st_t1|soccer_team2": [0.03, 0.97]})
stale = dict(state, last_run=(NOW - dt.timedelta(hours=5)).isoformat())
check("a stale read publishes no lead", TP.feed(stale, now=NOW)["leads"], {})
check("a failed read neither", TP.feed(dict(state, error="boom"), now=NOW)["leads"], {})

print("\nthe pages")
html = P.page({"quotes": []}, {"pairs": {}}, {"leads": {}, "pairs": {}}, "", now=NOW, soccer_team_rules=state)
check("the Production page lists T1 by name", all(n in html for n in TP.LABELS.values()), True)
check("the display name is the registered one", all(S.OWN_LEDGER_LABELS[k] == v for k, v in TP.LABELS.items()), True)
m0 = CC.model({"quotes": []}, {"pairs": {}}, {"leads": {}, "pairs": {}}, NOW)
m1 = CC.model({"quotes": []}, {"pairs": {}}, {"leads": {}, "pairs": {}}, NOW, soccer_team_rules=state)
check("the Control Center counts it once and names it", (m1["tiles"]["pairs"] - m0["tiles"]["pairs"],
                                                          [n for n in m1["prod_outside"] if n in TP.LABELS.values()]),
      (1, list(TP.LABELS.values())))
sec = TB.section(state)
check("the Soccer page marks T1, and only T1, as in Production",
      (sec.count("Production since 2026-10-24") >= 1, "T1 in Production since 2026-10-24" in sec), (True, True))
check("no guarded public phrase in the leads or the section",
      sandbox_audit.COPY_RE.findall(" ".join(l["headline"] + " " + l["id"] for l in f["leads"].values()) + sec), [])

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
