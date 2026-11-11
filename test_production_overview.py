#!/usr/bin/env python3
"""test_production_overview.py — the top of the Production page (2026-11-11): live records from each lane's first live bet, percentages only.

The old table restarted a lane's record at every version change and every stake raise, and a retired lane took its losses off the page.
Here: a lane's live record is every settled live bet it ever placed; a raise or a version change is a note in its fold; a lane with no
settled bet waits in its own group; retired lanes keep their final record; and no dollar amount, balance or stake size is printed.
"""
import re
import sys

import production_overview as PO

FAILS = []


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


def order(st, r, w=1.0, ko="2026-11-03T20:00"):
    return dict(id="x", ko=ko, r=r, w=w, st=st, side="yes")


blob = dict(
    generated="2026-11-11T22:00Z",
    pairs={
        "sr_a1|soccer_u35": dict(orders=[order("won", 0.5), order("lost", -1.0), order("won", 0.5, ko="2026-11-09T20:00"), order("open", None)]),
        "mls_x|soccer_p05": dict(orders=[order("won", 0.3, w=2.0)]),
        "waiting_pair|soccer_o25": dict(orders=[order("open", None)]),
        "crypto_a|crypto_fav": dict(orders=[order("won", 0.1)]),
    },
    pulled={"old_rule|soccer_btts": [order("lost", -1.0), order("lost", -1.0), order("won", 1.0)]},
    lanes={"nba_wm_yes": [dict(order("won", 0.4, ko="2026-11-03T01:00"), id="KXNBAWINMARGIN-26NOV02AAABBB-AAA1TO5", g=0.4, src="fills"),
                          dict(order("lost", -1.0, ko="2026-11-09T01:00"), id="KXNBAWINMARGIN-26NOV08AAABBB-AAA1TO5", g=-1.0, src="fills"),
                          dict(order("flat", 0.0, ko="2026-11-09T02:00"), id="KXNBAWINMARGIN-26NOV08CCCDDD-CCC1TO5", g=0.0, src="fills")],
           "nba_wm_nofade": [], "arg_dip": [], "o35_cheap_no": [dict(order("lost", -1.0), src="fills", g=-1.0)], "top5_dip": []},
)
pairs = {
    "sr_a1|soccer_u35": dict(name="Rule A1", market="Under 3.5", paper=dict(n=10, won=6, roi_fee=0.2), note="Stake raised Nov 6.", clv=None, rule="Backs X when Y. More text."),
    "mls_x|soccer_p05": dict(name="MLS fade", market="Team +0.5", paper=dict(n=3, won=2, roi_fee=0.1), note="", clv=None, rule=""),
    "waiting_pair|soccer_o25": dict(name="Waiting rule", market="Over 2.5", paper=dict(n=2, won=1, roi_fee=0.0), note="", clv=None, rule=""),
    "crypto_a|crypto_fav": dict(name="Crypto lane", market="Favourite band", paper=dict(n=1, won=1, roi_fee=0.1), note="", clv=None, rule=""),
    "nba_winmargin_v4|nba_wm": dict(name="NBA win margin YES v4", market="NBA", paper=dict(n=4, won=3, roi_fee=0.3), note="Version 4 from Nov 8.", clv=None, rule=""),
    "nba_winmargin_live|nba_wm": dict(name="NBA win margin YES v2", market="NBA", paper=dict(n=5, won=2, roi_fee=0.0), note="First version, until Nov 4.", clv=None, rule=""),
}
m = PO.build(blob, pairs)
by = {l["key"]: l for l in m["running"] + m["waiting"]}

print("records count from the first live bet")
a = by["sr_a1|soccer_u35"]["live"]
check("a pair's live record is every settled order (2 won, 1 lost; the open one waits)", (a["won"], a["lost"], a["open"]), (2, 1, 1))
check("its return is stake-weighted over the settled orders", round(a["roi"], 4), round((0.5 - 1.0 + 0.5) / 3, 4))
check("a weight of 2 counts twice", round(by["mls_x|soccer_p05"]["live"]["roi"], 4), 0.3)
n = by["nba_wm_yes"]
check("the NBA lane is ONE lane across versions, and its live record is all its trades (flat counted apart)",
      (n["live"]["won"], n["live"]["lost"], n["live"]["flat"]), (1, 1, 1))
check("a version change and a raise are notes in the fold, not a reset", ("Version 4 from Nov 8." in n["notes"], "First version, until Nov 4." in n["notes"],
      "Stake raised Nov 6." in by["sr_a1|soccer_u35"]["notes"]), (True, True, True))
check("its paper record adds the versions' Sandbox records", (n["paper"]["n"], n["paper"]["won"]), (9, 5))
check("live since the first trade, last bet the latest", (n["since"][:10], n["last"][:10]), ("2026-11-03", "2026-11-09"))

print("\ngroups and tiles")
check("a lane with no settled bet waits (open only, and no rows at all)", sorted(l["key"] for l in m["waiting"]), ["arg_dip", "nba_wm_nofade", "waiting_pair|soccer_o25"])
check("running lanes are the ones with a settled live bet", sorted(l["key"] for l in m["running"]),
      ["crypto_a|crypto_fav", "mls_x|soccer_p05", "nba_wm_yes", "sr_a1|soccer_u35"])
check("retired = the pulled lane + the retired own-state lane, with their final records",
      sorted((r["name"], r["live"]["won"], r["live"]["lost"]) for r in m["retired"]),
      sorted([(PO.PL.LANE_NAMES["o35_cheap_no"], 0, 1), (PO.plain(PO._pulled_name("old_rule|soccer_btts")), 1, 2)]))
t = m["tiles"]
check("the three tiles add up: running + retired = everything", (t["running"]["won"] + t["retired"]["won"], t["running"]["lost"] + t["retired"]["lost"]),
      (t["everything"]["won"], t["everything"]["lost"]))
check("everything's return is stake-weighted over both", round(t["everything"]["roi"], 4),
      round((t["running"]["num"] + t["retired"]["num"]) / (t["running"]["den"] + t["retired"]["den"]), 4))
check("groups: NBA, Soccer, Crypto · Econ · S&P", [PO.group_of(k) for k in ("nba_winmargin_v4|nba_wm", "sr_a1|soccer_u35", "crypto_a|crypto_fav", "econ_nc_yes|econ_daily", "finance_spx_nc_no|finance_daily")],
      ["NBA", "Soccer", "Crypto · Econ · S&P", "Crypto · Econ · S&P", "Crypto · Econ · S&P"])

print("\nthe html")
h = PO.tiles_html(m) + PO.section_html(m)
text = re.sub(r"<[^>]+>", " ", h)
check("three tiles", h.count('<div class="tile">'), 3)
check("every group folds and so does every lane", (h.count('<details class="fold lanes"'), h.count('<details class="lane">') >= 8), (5, True))
check("waiting and retired groups are closed by default", ("Retired lanes" in h and '<details class="fold lanes"><summary><h3>Retired lanes' in h,
      '<details class="fold lanes"><summary><h3>Waiting for the first live bet' in h), (True, True))
check("no dollar amount, balance or stake size", ("$" in text, re.search(r"\bstake of\b|\bbalance\b", text, re.I) is not None), (False, False))
BAD = ("real" + " money", "the" + " bot", " pa" + "irs", "leads to" + " come", "reach" + "able")      # built in pieces: the copy audit scans this file too
check("none of the retired jargon or guarded phrases in the lanes copy", [w for w in BAD if w in text.lower()], [])
check("a raise reads as a date, never an amount", "Stake raised Nov 6." in text, True)

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
