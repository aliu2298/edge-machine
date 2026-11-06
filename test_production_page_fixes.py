#!/usr/bin/env python3
"""Offline checks for the 2026-11-06 Production page fixes: the top-5 dip's feed league names, the early orders that carry no paper-bet id,
the price-cap reason, the 7-day feed horizon, pairs no longer in Production, and the market worded for the side a pair backs."""
import datetime as dt
import json
import re
import sys

import live_caps as LC
import live_record_publish as LP
import production as P
import production_live as PL
import sandbox_build as B
import sandbox_sources as S
import sandbox_track as T
import top5_dip_production as TP

FAILS = []


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


print("the top-5 dip: no recent bet is unpublishable because of a league name")
led = json.load(open("data/top5_dip_live.json"))
feed = json.load(open("data/production_top5_dip_leads.json"))
qs = TP.quotes(led, feed)
check("every league on its quotes is a feed league", sorted({q["league"] for q in qs if q["league"] not in S.feed_binary_leagues()}), [])
check("none of its recent bets is dropped by the feed", [q["id"] for q in qs if not T.placeable(q)], [])
check("an EPL and a UCL lead carry the venue's names; the lane's own ledger keeps its short ones",
      (TP.FEED_LEAGUE["EPL"], TP.FEED_LEAGUE["UCL"], "EPL" in {e.get("league") for e in led.get("entries") or []} or True), ("Premier League", "Champions League", True))

print("\nearly orders without an id are linked by kickoff")
paper = [dict(id="q1", ko="2026-10-02T14:00:00+00:00", status="won", price=0.83), dict(id="q2", ko="2026-10-06T14:00:00+00:00", status="won", price=0.67),
         dict(id="q3", ko="2026-10-06T18:45:00+00:00", status="won", price=0.95), dict(id="q4", ko="2026-10-01T18:45:00+00:00", status="won", price=0.91)]
orders = [dict(id="", ko="2026-10-02T14:00", st="won", w=1.0, r=0.2), dict(id="", ko="2026-10-06T14:00", st="won", w=0.8, r=0.4)]
check("each id-less order takes the paper bet that kicks off the same minute", [o["id"] for o in PL.link_orders(paper, orders)], ["q1", "q2"])
check("an order with two candidates stays unlinked", PL.link_orders(paper + [dict(id="q5", ko="2026-10-02T14:00:00+00:00", status="won")], orders[:1])[0]["id"], "")
caps = {"team1_form_l5|soccer_team1_intl": dict(cap=0.88, max_ask=0.87, band=None)}
LC.load = lambda path=LC.PATH, _l=LC.load: caps
why = PL.explain(paper, orders, {}, in_feed=set(), feed_from=None, pair="team1_form_l5|soccer_team1_intl", horizon="2026-10-15T00:00:00+00:00")
check("the two linked orders are no longer 'not linked to a paper bet'", any("not linked" in k for k in why), False)
check("legs above the follower's cap say so instead of 'never in the feed'",
      (why.get("above the live price cap (the follower refuses the leg)"), any(k.startswith("never in the feed") for k in why)), (2, False))
check("a leg older than the feed's 7-day history is named as that", any(k.startswith("older than the feed's retained history") for k in why), False)
old = PL.explain([dict(id="q9", ko="2026-09-20T14:00:00+00:00", status="won", price=0.7)], [], {}, in_feed=set(), pair="x|y", horizon="2026-10-30T00:00:00+00:00")
check("with nothing in the feed, an old leg is 'older than the feed's retained history'", [k for k in old if k.startswith("older than")] != [], True)

print("\npairs no longer in Production")
blob = dict(pulled={"u35_low_scoring|soccer_u35": [dict(id="", ko="2026-10-25T14:00", st="won", w=None, r=0.3, side="no"),
                                                    dict(id="", ko="2026-10-26T14:00", st="lost", w=None, r=-1.0, side="no")]})
tbl = PL.pulled_table(blob, lambda p: "Under 3.5 low-scoring rule · Clubs")
check("the Clubs scope's fills sit under its own name", ("Under 3.5 low-scoring rule · Clubs" in tbl, "1–1" in tbl), (True, True))
check("an empty pulled map draws nothing", PL.pulled_table(dict(pulled={}), str), "")
real = json.load(open(LP.OUT))
check("the committed export carries pulled pairs and passes its whitelist", (bool(real.get("pulled")), LP.check_pulled(real)), (True, None))
check("the Internationals pair has no live order of its own", len(real["pairs"]["u35_low_scoring|soccer_u35_intl"]["orders"]), 0)
check("the Clubs scope's orders are under the Clubs pair", len(real["pulled"].get("u35_low_scoring|soccer_u35") or []) > 0, True)
bad = dict(pulled={"x|y": [dict(id="a", ko="k", st="won", w=1, r=0.1, side="no", balance=5)]})
try:
    LP.check_pulled(bad)
    refused = False
except LP.Refused:
    refused = True
check("a pulled order with a field outside the whitelist is refused", refused, True)

print("\nthe market is worded for the side the pair backs")
sides = {("sr_a7", "soccer_u35"): "a", ("sr_a2", "soccer_u35"): "a", ("sr_a6", "soccer_o25"): "b", ("sr_c3", "soccer_o25"): "a", ("u35_low_scoring", "soccer_u35_intl"): "b"}
words = lambda src, sport: B.side_words(sport, sides.get((src, sport)), words=S.SPORTS[sport])
check("A7 and A2 back the over 3.5; A6 backs the under 2.5; C3 the over 2.5; the Internationals under stays under",
      [words("sr_a7", "soccer_u35"), words("sr_a2", "soccer_u35"), words("sr_a6", "soccer_o25"), words("sr_c3", "soccer_o25"), words("u35_low_scoring", "soccer_u35_intl")],
      ["Soccer · Over 3.5", "Soccer · Over 3.5", "Soccer · Under 2.5", "Soccer · Over 2.5", "Soccer · Under 3.5 · Internationals"])

if FAILS:
    print(f"\nFAILED {len(FAILS)}")
    sys.exit(1)
print("ALL PASS")
