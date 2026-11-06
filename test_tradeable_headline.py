#!/usr/bin/env python3
"""Offline checks for the tradeable headline (2026-11-06, Olu): a Production pair's headline record on the Soccer page counts only the paper legs
the follower can take (ask + fee inside its price cap, ask inside its band); every leg stays in the ledger and in the row's fold."""
import json
import math
import os
import sys
import tempfile

import live_caps as LC
import live_caps_publish as LP
import sandbox_audit
import soccer_lanes as L

FAILS = []


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


def kalshi_fee(p):                      # the follower's rule: 0.07 p (1 - p) rounded UP to $0.0001
    return math.ceil(round(0.07 * p * (1 - p), 8) * 10000) / 10000


print("the exporter reads the follower's own functions")
caps = LP.compute(["a|x", "b|y", "c|z"], {"cap": {"a|x": 0.85, "b|y": 0.92}},
                  lambda cfg, pair: cfg["cap"].get(pair, 0.85), lambda cfg, pick: (0.7, 0.85) if pick["pair"] == "c|z" else None, kalshi_fee)
check("a 0.85 cap allows asks to 0.84 (an ask of 0.85 plus its fee is 0.8589)", caps["a|x"]["max_ask"], 0.84)
check("a 0.92 cap allows asks to 0.91", caps["b|y"]["max_ask"], 0.91)
check("a band pair carries its band", caps["c|z"]["band"], [0.7, 0.85])
check("an unbanded pair carries none", caps["a|x"]["band"], None)

print("\nthe tradeable test")
G = {"t|team3": dict(cap=0.85, max_ask=0.84, band=[0.03, 0.97]), "u|u35": dict(cap=0.92, max_ask=0.91, band=None),
     "a|band": dict(cap=0.86, max_ask=0.85, band=[0.70, 0.85])}
check("at the highest ask under the cap", LC.tradeable("t|team3", 0.84, G), True)
check("a cent above it: the live veto (0.93 ask + fee is 0.9346 against 0.85)", (LC.tradeable("t|team3", 0.93, G), LC.reason("t|team3", 0.93, G)), (False, "above the live price cap"))
check("a pair with a higher cap takes it", LC.tradeable("u|u35", 0.91, G), True)
check("a band pair refuses an ask under its band", (LC.tradeable("a|band", 0.65, G), LC.reason("a|band", 0.65, G)), (False, "outside the live band"))
check("an unknown pair or price counts, as before", (LC.tradeable("none|x", 0.99, G), LC.tradeable("t|team3", None, G)), (True, True))
t, al = LC.split("t|team3", [{"price": 0.7}, {"price": 0.93}, {"price": 0.9}], caps=G)
check("split keeps every row and returns the tradeable ones", (len(t), len(al)), (1, 3))

print("\nthe committed caps file")
blob = json.load(open(LC.PATH))
caps = blob["caps"]
check("every pair has a cap in (0, 1) and a max_ask under it", all(0 < c["cap"] < 1 and c["max_ask"] is not None and c["max_ask"] < c["cap"] for c in caps.values()), True)
check("the soccer team 3+ NO pair is guarded", "st_t7|soccer_team3" in caps, True)
check("no dollar figure or key in the file", "$" in json.dumps(blob), False)

print("\nthe record table and a T7-shaped row")
picks = [dict(status="won", price=0.71, profit=40.0), dict(status="won", price=0.78, profit=28.0), dict(status="lost", price=0.8, profit=-100.0),
         dict(status="won", price=0.92, profit=7.0), dict(status="won", price=0.93, profit=6.0)]
tp, ev = LC.split("t|team3", picks, caps=G)
tbl = L.legs_table(L.pick_record(tp), L.pick_record(ev))
check("the table has the headline and the all-legs row", ("Legs the follower can take (headline)" in tbl, "All paper legs, incl. above the live price cap" in tbl), (True, True))
check("the headline counts 3 settled, the all-legs row 5", (L.pick_record(tp)["n"], L.pick_record(ev)["n"]), (3, 5))
check("the table's words pass the public copy guard", bool(sandbox_audit.COPY_RE.search(tbl)), False)

print("\nthe rows on the page")
import soccer_team_rules as TR
import soccer_team_rules_production as TRP
state = TR.load()
live, gone, quotes = L.team_rows(state)
r7 = next(r for r in live if r["name"] == "st_t7")
all7 = L.pick_record((state["rules"].get("T7") or {}).get("picks") or [])
check("T7's headline drops the legs above the cap and its fold shows both records",
      (r7["a"]["n"] < all7["n"], "All paper legs" in r7["legs_html"], f'{all7["n"]}' in r7["legs_html"]), (True, True, True))

print("\nthe since-Production record and the header tile count the legs the follower can take")
import datetime as dt
import production as P
import sport_page as SP
KO = "2026-11-10T18:00:00+00:00"
mk = lambda i, price, status: dict(id=f"q{i}", source="t", sport="soccer_team3", venue="kalshi_binary", status=status, bet=True, price=price, price_a=None,
                                   price_b=price, start=KO, logged="2026-11-09T12:00:00+00:00", pnl=(100 / price - 100) if status == "won" else -100.0,
                                   market_id=f"m{i}", label=f"x{i}", pick="b", date="2026-11-10", result="b" if status == "won" else "a", settle_px=None,
                                   espn_home="A", espn_away="B", start_source="espn")
ledger = {"quotes": [mk(1, 0.70, "won"), mk(2, 0.80, "lost"), mk(3, 0.92, "won"), mk(4, 0.93, "won")]}
stage = {"stage": "production", "ready_at": "2026-11-01T00:00:00+00:00", "promoted_at": "2026-11-01T00:00:00+00:00"}
G["t|soccer_team3"] = dict(cap=0.85, max_ask=0.84, band=None)
LC.load = lambda path=LC.PATH, _g=G: _g
allv = P._assess_since_kickoff(ledger, "t|soccer_team3", stage)
trade = P._assess_since_kickoff(ledger, "t|soccer_team3", stage, tradeable=True)
check("the plain record counts all four legs; the tradeable one drops the two above the cap", (allv["n"], trade["n"], trade["won"]), (4, 2, 1))
check("the tile pools the tradeable basis", (SP.since_production(ledger, {"pairs": {"t|soccer_team3": stage}}, [dict(name="t", sport="soccer_team3", prod=True)], late={})[0]["n"],), (2,))

if FAILS:
    print(f"\nFAILED {len(FAILS)}")
    sys.exit(1)
print("ALL PASS")
