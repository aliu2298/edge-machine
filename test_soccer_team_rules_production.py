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

# T1 went back to the Sandbox on 2026-10-28. The checks below replay its Production era
# (2026-10-24 to 2026-10-28) by listing it again for this run; the real state is checked first.
_NOW_PAIRS = sorted(TP.PAIRS)
_NOW_MOVED = (TP.MOVED_ON, TP.PROMOTED)
# The 2026-10-25 fixtures below sit before T5 and T7's real entry instant, so the replay lists every pair
# from the day T1 entered.
TP.PROMOTED = "2026-10-24T22:00:00+00:00"
TP.PAIRS["T1"] = ("st_t1", "soccer_team2", "O+D− v O+D− · team 2+ goals")
TP.LABELS = {src: name for src, _sport, name in TP.PAIRS.values()}

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
    "T5": {"picks": [pick("T5", "KXMLSTEAMTOTAL-26OCT25LAFSEA-LAF2", "LAFC v Seattle Sounders", "LAFC", "Seattle Sounders", "MLS", 0.47)]},
    "T7": {"picks": [pick("T7", "KXBUNDESLIGATEAMTOTAL-26OCT25BAYDOR-BAY3", "Bayern Munich v Dortmund", "Bayern Munich", "Dortmund",
                          "Bundesliga", 0.70, side="no", line=2.5),
                     pick("T7", "KXEPLTEAMTOTAL-26OCT24CRYNEW-CRY3", "Crystal Palace v Newcastle", "Crystal Palace", "Newcastle",
                          "Premier League", 0.72, side="no", line=2.5, status="lost", start="2026-10-24T16:00Z",
                          logged="2026-10-24T14:31:00+00:00", profit=-100.0, payout=0.0)]},
    "T4": {"picks": [pick("T4", "KXEPLTEAMTOTAL-26OCT25CRYNEW-CRY2", "Crystal Palace v Newcastle", "Crystal Palace",
                          "Newcastle", "Premier League", 0.45)]}}}

print("T5 and T7 since 2026-10-28; T1 (out 2026-10-28) replayed for the checks below")
check("T5 and T7 are the two pairs, listed 2026-10-28", (_NOW_PAIRS, _NOW_MOVED[0]), (["T5", "T7"], "2026-10-28"))
print("only T1, on the existing team 2+ claim")
qs = TP.quotes(state)
check("T1, T5 and T7, their own leagues only", sorted(q["market_id"] for q in qs),
      sorted(["KXEPLTEAMTOTAL-26OCT25LFCBRI-LFC2", "KXEPLTEAMTOTAL-26OCT25LFCBRI-BRI2", "KXSERIEATEAMTOTAL-26OCT24NAPROM-ROM2",
              "KXMLSTEAMTOTAL-26OCT25LAFSEA-LAF2", "KXBUNDESLIGATEAMTOTAL-26OCT25BAYDOR-BAY3", "KXEPLTEAMTOTAL-26OCT24CRYNEW-CRY3"]))
check("team 2+ is the Yes on soccer_team2; team 3+ is the No on soccer_team3",
      {(q["sport"], q["pick"], q["source"]) for q in qs},
      {("soccer_team2", "a", "st_t1"), ("soccer_team2", "a", "st_t5"), ("soccer_team3", "b", "st_t7")})
check("Kalshi's own Yes words: the ledger's sub when kept, else from the market title",
      sorted(q["kalshi_title"] for q in qs),
      sorted(["Brighton over 1.5 goals", "LAFC over 1.5 goals", "Liverpool over 1.5 goals", "Munich over 2.5 goals",
              "Palace over 2.5 goals", "Roma over 1.5 goals"]))
check("all may be published, on an ESPN-verified start", [(T.placeable(q), P.start_verified(q)) for q in qs], [(True, True)] * 6)
t7 = {q["market_id"]: q for q in qs}["KXBUNDESLIGATEAMTOTAL-26OCT25BAYDOR-BAY3"]
check("T7's quote is the No at the No's own price, and a loss on the settled one flips to the Yes",
      (t7["pick"], t7["price_a"], t7["price_b"], {q["market_id"]: q["result"] for q in qs}["KXEPLTEAMTOTAL-26OCT24CRYNEW-CRY3"]),
      ("b", None, 0.70, "a"))
check("T1's band is the rule's own 3-97c", TP.BAND, (TR.PRICE_LO, TR.PRICE_HI))

print("\nthe leads: the exact contract, team and side")
f = TP.feed(state, now=NOW)
leads = {l["route"]["market"]: l for l in f["leads"].values()}
check("three pairs listed in this replay (T1 replayed, T5 and T7 real)", sorted(f["pairs"]),
      ["st_t1|soccer_team2", "st_t5|soccer_team2", "st_t7|soccer_team3"])
lfc = leads["KXEPLTEAMTOTAL-26OCT25LFCBRI-LFC2"]
check("Liverpool 2+ is the Yes of the LFC over-1.5 contract, named as Kalshi names it",
      (lfc["bet"], lfc["route"]["outcome_side"], lfc["route"]["outcome"], lfc["league"]),
      ({"kind": "team_gte", "n": 2, "team": "Liverpool"}, "yes", "Liverpool over 1.5 goals", "Premier League"))
check("both sides of one match are two leads (two contracts); T5 and T7 add one each", sorted(leads),
      ["KXBUNDESLIGATEAMTOTAL-26OCT25BAYDOR-BAY3", "KXEPLTEAMTOTAL-26OCT25LFCBRI-BRI2", "KXEPLTEAMTOTAL-26OCT25LFCBRI-LFC2",
       "KXMLSTEAMTOTAL-26OCT25LAFSEA-LAF2"])
bay = leads["KXBUNDESLIGATEAMTOTAL-26OCT25BAYDOR-BAY3"]
check("Bayern 3+ is NOT backed: the lead is the No of the over-2.5 contract, bet team_lte 2",
      (bay["bet"], bay["route"]["outcome_side"], bay["route"]["outcome"], bay["route"]["price_at_log"], bay["headline"]),
      ({"kind": "team_lte", "n": 2, "team": "Bayern Munich"}, "no", "Munich over 2.5 goals", 0.7, "Bayern Munich to score under 2.5"))
check("the settled Roma entry kicked off before Production, so it is not a lead",
      "KXSERIEATEAMTOTAL-26OCT24NAPROM-ROM2" in leads, False)
check("each lead names its rule", {l["id"].split(" · ", 1)[1] for l in f["leads"].values()}, set(TP.LABELS.values()))
check("the feed carries the band it publishes on", f["bands"],
      {k: [0.03, 0.97] for k in ("st_t1|soccer_team2", "st_t5|soccer_team2", "st_t7|soccer_team3")})
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
      (3, list(TP.LABELS.values())))
sec = TB.section(state)
check("the Soccer page says T1 was in Production 2026-10-24 to 2026-10-28 and is back in the Sandbox",
      (sec.count("Production 2026-10-24 to 2026-10-28, back in the Sandbox") >= 1,
       "T5 and T7 in Production since 2026-10-28" in sec), (True, True))
check("no guarded public phrase in the leads or the section",
      sandbox_audit.COPY_RE.findall(" ".join(l["headline"] + " " + l["id"] for l in f["leads"].values()) + sec), [])

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
