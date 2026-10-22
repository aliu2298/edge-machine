#!/usr/bin/env python3
"""Offline checks for the soccer rules' Production feed (soccer_rules_production.py, 2026-10-21)."""
import datetime as dt
import sys

import production as P
import sandbox_audit
import sandbox_sources as S
import sandbox_track as T
import soccer_rules_production as RP

FAILS = []
UTC = dt.timezone.utc
NOW = dt.datetime(2026, 10, 22, 17, 0, tzinfo=UTC)


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


def pick(rule, ticker, match, league, side, price, line, status="open", start="2026-10-22T19:00Z",
         logged="2026-10-22T17:31:00+00:00", **kw):
    return dict(dict(id=f"{rule}:{ticker.rsplit('-', 1)[0]}", rule=rule, ticker=ticker, event=ticker.rsplit("-", 1)[0],
                     match=match, league=league, side=side, price=price, line=line, start=start, logged=logged,
                     status=status), **kw)


rules = {"last_run": (NOW - dt.timedelta(minutes=20)).isoformat(), "error": None, "rules": {
    "A7": {"picks": [pick("A7", "KXUCLTOTAL-26OCT22ARSBAY-4", "Arsenal v Bayern Munich", "Champions League", "yes", 0.48, 3.5)]},
    "A6": {"picks": [pick("A6", "KXEPLTOTAL-26OCT25EVEBUR-3", "Everton v Burnley", "Premier League", "no", 0.52, 2.5,
                          start="2026-10-25T14:00Z")]},
    "D3": {"picks": [pick("D3", "KXLALIGABTTS-26OCT25GETOSA-BTTS", "Getafe v Osasuna", "La Liga", "yes", 0.55, None,
                          start="2026-10-25T14:00Z"),
                     pick("D3", "KXSERIEABTTS-26OCT19UDILEC-BTTS", "Udinese v Lecce", "Serie A", "yes", 0.50, None,
                          status="won", start="2026-10-19T14:00Z", logged="2026-10-19T12:30:00+00:00", profit=88.0, payout=1)]},
    "D1": {"picks": [pick("D1", "KXSERIEABTTS-26OCT22INTJUV-BTTS", "Inter v Juventus", "Serie A", "yes", 0.60, None)]}}}
sa = {"last_run": (NOW - dt.timedelta(minutes=20)).isoformat(), "error": None, "rules": {
    "ARG": {"picks": [pick("ARG", "KXARGPREMDIVTOTAL-26OCT22RIVBOC-2", "River Plate v Boca Juniors", "Liga Profesional",
                           "yes", 0.66, 1.5)]},
    "BRA": {"picks": [pick("BRA", "KXBRASILEIROTOTAL-26OCT22FLAPAL-2", "Flamengo v Palmeiras", "Brasileirão",
                           "yes", 0.74, 1.5)]}}}

print("only the four rules, on the existing soccer claims")
qs = RP.quotes(rules, sa)
check("A7, A6, D3 and Argentina; never D1 or the Brasileirão",
      sorted({q["source"] for q in qs}), ["sa_o15_arg", "sr_a6", "sr_a7", "sr_d3"])
by = {q["market_id"]: q for q in qs}
check("each on its claim domain and side",
      [(by[t]["sport"], by[t]["pick"]) for t in ("KXUCLTOTAL-26OCT22ARSBAY-4", "KXEPLTOTAL-26OCT25EVEBUR-3",
                                                  "KXLALIGABTTS-26OCT25GETOSA-BTTS", "KXARGPREMDIVTOTAL-26OCT22RIVBOC-2")],
      [("soccer_u35", "a"), ("soccer_o25", "b"), ("soccer_btts", "a"), ("soccer_o15", "a")])
check("all four may be published, on an ESPN-verified start", [(T.placeable(q), P.start_verified(q)) for q in qs],
      [(True, True)] * len(qs))
check("Argentina's league is a feed league now, and only it was added", (
    "Liga Profesional" in S.feed_binary_leagues(), S.FEED_EXTRA_LEAGUES), (True, {"Liga Profesional"}))

print("\nthe leads: the exact contract and side")
f = RP.feed(rules, sa, now=NOW)
leads = {l["route"]["market"]: l for l in f["leads"].values()}
check("four pairs listed, moved by hand 2026-10-21",
      (sorted(f["pairs"]), {v["by_hand"] for v in f["pairs"].values()}),
      (["sa_o15_arg|soccer_o15", "sr_a6|soccer_o25", "sr_a7|soccer_u35", "sr_d3|soccer_btts"], {"2026-10-21"}))
check("A7: over 3.5 is the Yes of the -4 contract, named as Kalshi names it",
      (leads["KXUCLTOTAL-26OCT22ARSBAY-4"]["bet"], leads["KXUCLTOTAL-26OCT22ARSBAY-4"]["route"]["outcome_side"],
       leads["KXUCLTOTAL-26OCT22ARSBAY-4"]["route"]["outcome"]), ({"kind": "total_gte", "n": 4}, "yes", "Over 3.5 goals scored"))
check("A6: under 2.5 is the No of the over-2.5 contract",
      (leads["KXEPLTOTAL-26OCT25EVEBUR-3"]["bet"], leads["KXEPLTOTAL-26OCT25EVEBUR-3"]["route"]["outcome_side"]),
      ({"kind": "total_lte", "n": 2}, "no"))
check("D3: the Yes of the BTTS contract", (leads["KXLALIGABTTS-26OCT25GETOSA-BTTS"]["bet"]["kind"],
                                            leads["KXLALIGABTTS-26OCT25GETOSA-BTTS"]["route"]["outcome"]), ("btts", "Both Teams To Score"))
check("ARG: over 1.5 is the Yes of the over-1.5 contract",
      (leads["KXARGPREMDIVTOTAL-26OCT22RIVBOC-2"]["bet"], leads["KXARGPREMDIVTOTAL-26OCT22RIVBOC-2"]["league"]),
      ({"kind": "total_gte", "n": 2}, "Liga Profesional"))
check("the settled D3 entry closed before Production, so it is not a lead", "KXSERIEABTTS-26OCT19UDILEC-BTTS" in leads, False)
check("each lead names its rule", sorted({l["id"].split(" · ", 1)[1] for l in f["leads"].values()}),
      sorted(RP.LABELS.values()))
stale = dict(rules, last_run=(NOW - dt.timedelta(hours=5)).isoformat())
check("a stale rules read publishes no A7/A6/D3 lead, Argentina still does",
      sorted(l["pair"] for l in RP.feed(stale, sa, now=NOW)["leads"].values()), ["sa_o15_arg|soccer_o15"])

print("\nD3 is not published in the Europa League (2026-10-22); it is still logged there as paper")
uel = dict(rules, rules=dict(rules["rules"], D3={"picks": rules["rules"]["D3"]["picks"] + [
    pick("D3", "KXUELBTTS-26OCT22CELCEL-BTTS", "Celtic v Celta Vigo", "Europa League", "yes", 0.55, None,
         start="2026-10-22T19:00Z")]}))
check("a D3 Europa League entry is never a quote", any(q["market_id"].startswith("KXUELBTTS") for q in RP.quotes(uel, sa)), False)
check("nor a lead", any(l["route"]["market"].startswith("KXUELBTTS") for l in RP.feed(uel, sa, now=NOW)["leads"].values()), False)
check("D3 in every other league still publishes", "KXLALIGABTTS-26OCT25GETOSA-BTTS" in
      {l["route"]["market"] for l in RP.feed(uel, sa, now=NOW)["leads"].values()}, True)
import soccer_rules as SRM
check("soccer_rules still runs D3 in the Europa League (Sandbox paper)", SRM.in_league(SRM.RULES["D3"], "Europa League"), True)
check("the Soccer page says so", "not the Europa League" in __import__("soccer_rules_build").section(uel), True)

print("\nthe pages")
html = P.page({"quotes": []}, {"pairs": {}}, {"leads": {}, "pairs": {}}, "", now=NOW, soccer_rules=(rules, sa))
check("the Production page lists the four rules by name", all(n in html for n in RP.LABELS.values()), True)
check("the display names are the registered ones", all(S.OWN_LEDGER_LABELS[k] == v for k, v in RP.LABELS.items()), True)
import soccer_rules_build as SB
import sa_o15_build as SAB
check("the Soccer page marks A7, A6, D3 and Argentina as in Production",
      (SB.section(rules).count("Production since 2026-10-21") >= 3, "Production since 2026-10-21" in SAB.section(sa)), (True, True))
check("no guarded public phrase in the leads",
      sandbox_audit.COPY_RE.findall(" ".join(l["headline"] + " " + l["id"] for l in f["leads"].values())), [])

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
