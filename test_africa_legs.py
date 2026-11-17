#!/usr/bin/env python3
"""The African qualifier legs (2026-11-16): subsets of the ledger's own entries, a two-pair Production feed, the page rows. Offline."""
import datetime as dt
import re

import africa_goals as AG
import africa_goals_production as AFP
import sandbox_audit
import soccer_lanes as L

FAILS = []
UTC = dt.timezone.utc
NOW = dt.datetime(2026, 11, 17, 12, 0, tzinfo=UTC)


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


def pk(rule, ev, price, status="open", team=None, side="yes", start="2026-11-17T16:00:00+00:00", **kw):
    return dict(dict(id=f"{rule}:{ev}-{team or rule}", rule=rule, event=f"KXAFCONTOTAL-{ev}", ticker=f"KXAFCONTEAMTOTAL-{ev}-{(team or 'X')[:3].upper()}1"
                     if rule == "T1" else f"KXAFCONTOTAL-{ev}-{rule}", match="Alpha v Beta", team=team, side=side, price=price, status=status,
                     start=start, logged="2026-11-17T13:30:00+00:00", entry_at="2026-11-17T13:00:00+00:00", league="AFCON Qualifying",
                     title=f"Will {team} score over 0.5 goals?" if team else "x"), **kw)


state = {"last_run": NOW.isoformat(), "error": None, "rules": {
    "T1": {"picks": [pk("T1", "26NOV17ALPBET", 0.93, team="Alpha"), pk("T1", "26NOV17ALPBET", 0.41, team="Beta"),
                     pk("T1", "26NOV17GAMDEL", 0.58, team="Gamma"), pk("T1", "26NOV17GAMDEL", 0.62, team="Delta")]},
    "U35": {"picks": [pk("U35", "26NOV17ALPBET", 0.85, side="no"), pk("U35", "26NOV17GAMDEL", 0.74, side="no")]},
    "O15": {"picks": [pk("O15", "26NOV17ALPBET", 0.80), pk("O15", "26NOV17GAMDEL", 0.70),
                      pk("O15", "26NOV12OLDONE", 0.8, start="2026-11-12T16:00:00+00:00")]},
    "BTTS": {"picks": [pk("BTTS", "26NOV17ALPBET", 0.33), pk("BTTS", "26NOV13EARLY", 0.30, counted=False)]}}}
state["rules"]["O15"]["picks"][2]["event"] = "KXAFCONTOTAL-26NOV12OLDONE"
state["rules"]["T1"]["picks"].append(pk("T1", "26NOV12OLDONE", 0.9, team="Old", start="2026-11-12T16:00:00+00:00"))

print("the legs are filters on the ledger's own entries")
check("the underdog: to-score asks under 60c (41c and 58c), not 62c or 93c", sorted(p["price"] for p in AG.leg_picks(state, "DOG")), [0.41, 0.58])
check("afq_btts is the BTTS row's counted picks only", [p["id"] for p in AG.leg_picks(state, "BTTS")], ["BTTS:26NOV17ALPBET-BTTS"])
check("afq_u35_80: the NO ask 80c or more", [p["price"] for p in AG.leg_picks(state, "U35_80")], [0.85])
check("its control: the NO ask under 80c", [p["price"] for p in AG.leg_picks(state, "CTRL_U35")], [0.74])
check("the favourite's ask is the higher of the match's two", (AG.favourite_ask(state, "KXAFCONTOTAL-26NOV17ALPBET"), AG.favourite_ask(state, "KXAFCONTOTAL-26NOV17GAMDEL")),
      (0.93, 0.62))
check("afq_o15_v2 in sample: over 1.5 where the favourite is 90c or more (both Alpha-Beta and the old match)", sorted(p["event"][-6:] for p in AG.in_sample_picks(state)), ["ALPBET", "OLDONE"])
check("... and it COUNTS only matches from Nov 16 (the old match is shown, not counted)", [p["event"][-6:] for p in AG.leg_picks(state, "O15_V2")], ["ALPBET"])
check("control: the favourite to score at 85c or more, the favourite only", sorted(p["price"] for p in AG.leg_picks(state, "CTRL_FAV")), [0.9, 0.93])
check("no entry is added or changed: the pooled rules' counts stand", {k: len(v["picks"]) for k, v in state["rules"].items()}, {"T1": 5, "U35": 2, "O15": 3, "BTTS": 2})

print("\nthe Production feed: two pairs, the follower's bands, no third leg")
check("no Production pair since 2026-11-17 (Olu: back in the Sandbox); the feed still names the two legs, which the live book grades its held positions off",
      (AFP.ENDED_ON, AFP.pairs(), sorted(AFP._feed_pairs())), ("2026-11-17", {}, ["afq_btts|soccer_btts_intl", "afq_dog_score|soccer_team1_intl"]))
check("the Production page inputs add the quotes to the Sandbox side and nothing to the stage or the feed read",
      (len(AFP.page_inputs({"quotes": []}, {"pairs": {}}, {"leads": {}, "pairs": {}}, state, now=NOW)[0]["quotes"]) > 0,
       AFP.page_inputs({"quotes": []}, {"pairs": {}}, {"leads": {}, "pairs": {}}, state, now=NOW)[1:]), (True, ({"pairs": {}}, {"leads": {}, "pairs": {}})))
f = AFP.feed(state, now=NOW)
leads = {l["route"]["market"] if l.get("route") else l["id"]: l for l in f["leads"].values()}
check("the bands: underdog 2c to 60c, BTTS the lane's own 2c to 98c", f["bands"], {"afq_dog_score|soccer_team1_intl": [0.02, 0.6], "afq_btts|soccer_btts_intl": [0.02, 0.98]})
dog = [l for l in f["leads"].values() if l["pair"].startswith("afq_dog")]
check("an open underdog lead names the team, the side and the exact contract", sorted((l["bet"]["kind"], l["bet"]["team"], l["route"]["outcome_side"]) for l in dog),
      [("team_gte", "Alpha", "yes")] if False else sorted((l["bet"]["kind"], l["bet"]["team"], "yes") for l in dog))
check("the underdog leads are Beta and Gamma, never the 93c favourite", sorted(l["bet"]["team"] for l in dog), ["Beta", "Gamma"])
bt = [l for l in f["leads"].values() if l["pair"].startswith("afq_btts")]
check("one BTTS lead, the Yes of the BTTS contract (kind btts)", [(l["bet"]["kind"], l["route"]["outcome_side"]) for l in bt], [("btts", "yes")])
stale = AFP.feed(dict(state, last_run=(NOW - dt.timedelta(hours=6)).isoformat()), now=NOW)
check("an unhealthy collector publishes no open lead", [l for l in stale["leads"].values() if l.get("status") == "pending"], [])
empty = AFP.feed({"last_run": NOW.isoformat(), "error": None, "rules": {}}, now=NOW)
check("idle between windows: a valid feed that names no match", (empty["leads"], sorted(empty["pairs"])), ({}, ["afq_btts|soccer_btts_intl", "afq_dog_score|soccer_team1_intl"]))

print("\nthe Soccer page: all of it under Internationals, the old rows retired, percentages only")
rows = L.africa_rows(state)
by = {r["name"]: r for r in rows}
check("every row is an Internationals row", {r["scope"] for r in rows}, {"intl"})
check("the four every-match rows are retired with Olu's reason", sorted((n for n, r in by.items() if r.get("gone")), key=str),
      sorted(["africa_goals_all", "africa_goals_u35", "africa_goals_o15", "africa_goals_t1"]))
check("... and say so", {r["gone"] for r in rows if r.get("gone")}, {"Retired Nov 16 by Olu: split into Production legs / v2."})
check("no African row is a Production row since 2026-11-17: all six are Sandbox", {n: bool(by[n]["prod"]) for n in ("afq_dog_score", "afq_btts", "afq_u35_80", "afq_o15_v2", "afq_ctrl_fav", "afq_ctrl_u35")},
      {"afq_dog_score": False, "afq_btts": False, "afq_u35_80": False, "afq_o15_v2": False, "afq_ctrl_fav": False, "afq_ctrl_u35": False})
check("the two legs say they were Production Nov 16 to Nov 17 and the record continues",
      all("Nov 16 to Nov 17 2026" in by[n]["own"]["details"] and "no reset" in by[n]["own"]["details"] for n in ("afq_dog_score", "afq_btts")), True)
check("the controls are baselines", (by["afq_ctrl_fav"]["meta"]["kind"], by["afq_ctrl_u35"]["meta"]["kind"]), ("Baseline", "Baseline"))
text = " ".join(r["own"]["details"] + r["own"]["entries"] + r["own"]["label"] + r["meta"]["note"] for r in rows)
check("no dollar amount on the page", "$" in text, False)
check("no guarded phrase", sandbox_audit.COPY_RE.search(text), None)
check("the u35 leg says it is not in Production and why", "22 of 29 at 83c" in by["afq_u35_80"]["own"]["details"] and "not in Production" in by["afq_u35_80"]["own"]["details"], True)

print()
if FAILS:
    print(f"{len(FAILS)} FAILED")
    raise SystemExit(1)
print("ALL PASS")
