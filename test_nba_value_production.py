#!/usr/bin/env python3
"""Offline checks for the NBA team-total value lanes' Production feed (nba_value_production.py, 2026-10-24)."""
import copy
import datetime as dt
import json
import sys

import nba_value as NV
import nba_value_production as NP
import production as PR
import sandbox_audit
import sandbox_sources as S
import sandbox_track as T

FAILS = []
UTC = dt.timezone.utc
NOW = dt.datetime(2026, 10, 24, 22, 30, tzinfo=UTC)


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


def pick(lane, game, team, side, price, line, status="open", tip="2026-10-25T00:30:00+00:00", p=0.60, **kw):
    code = "PHI" if team == "PHI" else "CLE"
    return dict(id=f"{lane}:{game}:{team}", rule=lane, game=game, unit=team, match="CLE @ PHI", start=tip,
                logged="2026-10-24T22:05:00+00:00", ticker=f"KXNBATEAMTOTAL-26OCT24CLEPHI-{code}{int(line + 0.5)}",
                event="KXNBATEAMTOTAL-26OCT24CLEPHI", line=line, side=side, price=price, status=status, p=p, edge=0.12,
                title=f"{'Philadelphia' if team == 'PHI' else 'Cleveland'} over {line:g} points", **kw)


def state(picks24=(), picks1=(), last="2026-10-24T22:20:00+00:00", error=None):
    return dict(rules={NV.TT_24H: dict(picks=list(picks24)), NV.TT_1H: dict(picks=list(picks1)),
                       "nba_1q_value_24h": dict(picks=[dict(id="q", rule="nba_1q_value_24h", ticker="KXNBA1QTOTAL-X-1")]),
                       "base_nba_tt_value_24h": dict(picks=[pick("base_nba_tt_value_24h", "g9", "PHI", "yes", 0.5, 110.5)])},
                last_run=last, error=error)


no = pick(NV.TT_24H, "g1", "PHI", "no", 0.35, 114.5, p=0.4864)
yes = pick(NV.TT_1H, "g1", "CLE", "yes", 0.62, 109.5, p=0.71)
won = pick(NV.TT_24H, "g0", "PHI", "no", 0.40, 112.5, status="won", payout=1.0, profit=139.92, settled="2026-10-24T03:00:00+00:00",
           tip="2026-10-23T23:00:00+00:00")

print("the pairs: two, on their own ledger, nothing else")
check("two Production pairs, 24h and 1h, on the nba_tt domain", sorted(NP.pairs()), ["nba_tt_value_1h|nba_tt", "nba_tt_value_24h|nba_tt"])
check("each is staged as moved by hand 2026-10-24", {v["by_hand"] for v in NP.pairs().values()}, {"2026-10-24"})
check("neither is in stages.json or PAIR_OVERRIDES, so no demotion or same-day flip (#176) can touch them",
      [k for k in NP.pairs() if k in T.PAIR_OVERRIDES or k in T.load_stages()["pairs"]], [])
check("the 1Q lanes, the baselines and the fade controls are not published",
      sorted({q["source"] for q in NP.quotes(state([no], [yes]))}), [NV.TT_1H, NV.TT_24H])

print("\nquotes: the exact contract, the side, the tip")
qs = {q["id"]: q for q in NP.quotes(state([no, won], [yes]))}
q = qs[no["id"]]
check("the NO is pick b at its own price, on the exact contract", (q["pick"], q["price"], q["market_id"], q["price_b"], q["price_a"]),
      ("b", 0.35, "KXNBATEAMTOTAL-26OCT24CLEPHI-PHI115", 0.35, None))
check("  the model's probability is turned into the YES one (1 - 0.4864)", round(q["prob_a"], 4), round(1 - 0.4864, 4))
check("the YES is pick a, prob_a as is", (qs[yes["id"]]["pick"], qs[yes["id"]]["prob_a"]), ("a", 0.71))
check("the team name comes from Kalshi's own wording", (q["team_name"], q["kalshi_title"]), ("Philadelphia", "Philadelphia over 114.5 points"))
check("settled rows keep their result and profit", (qs[won["id"]]["status"], qs[won["id"]]["result"], qs[won["id"]]["pnl"]), ("won", "b", 139.92))
check("a row with no readable tip or a foreign ticker is never published",
      NP.quotes(state([dict(no, start=None), dict(yes, ticker="KXNBA1QTOTAL-X-1")])), [])

print("\nthe feed")
blob = NP.feed(state([no, won], [yes]), now=NOW)
leads = {l["bet"]["kind"] + ":" + l["bet"]["team"]: l for l in blob["leads"].values()}
check("a lead per open row; the settled one is history", sorted(l["bet"]["kind"] for l in blob["leads"].values() if l["status"] == "pending"),
      ["nba_tt", "nba_tt_no"])
ln = leads["nba_tt_no:Philadelphia"]
check("the NO lead: headline, bet, kickoff = the tip, league NBA",
      (ln["headline"], ln["bet"], ln["kickoff"], ln["league"], ln["match"]),
      ("Philadelphia under 114.5 points", {"kind": "nba_tt_no", "n": 114.5, "team": "Philadelphia"}, "2026-10-25T00:30Z", "NBA", "CLE @ PHI"))
check("  routed to the exact contract, side no, price at log, Kalshi's wording",
      {k: ln["route"].get(k) for k in ("venue", "market", "event", "outcome_side", "price_at_log", "outcome")},
      dict(venue="kalshi", market="KXNBATEAMTOTAL-26OCT24CLEPHI-PHI115", event="KXNBATEAMTOTAL-26OCT24CLEPHI",
           outcome_side="no", price_at_log=0.35, outcome="Philadelphia over 114.5 points"))
check("  and the side's own probability is the lead's model_prob", ln["model_prob"], 0.4864)
ly = leads["nba_tt:Cleveland"]
check("the YES lead: over, outcome_side yes, model_prob as is",
      (ly["headline"], ly["route"]["outcome_side"], ly["model_prob"], ly["bet"]["kind"]),
      ("Cleveland over 109.5 points", "yes", 0.71, "nba_tt"))
check("the pairs block lists both Production pairs", sorted(blob["pairs"]), sorted(NP.pairs()))
check("a lane that never entered still shows as a pair", all(k in blob["pairs"] for k in NP.pairs()), True)

print("\nhealth and read-only")
stale = NP.feed(state([no], [yes], last="2026-10-24T15:00:00+00:00"), now=NOW)
check("a stale read keeps history and publishes no open lead", [l["status"] for l in stale["leads"].values()], [])
failed = NP.feed(state([no, won], [yes], error="boom"), now=NOW)
check("a failed read the same", [l["status"] for l in failed["leads"].values() if l["status"] == "pending"], [])
st = state([no, won], [yes])
before = copy.deepcopy(st)
NP.feed(st, now=NOW)
NP.quotes(st)
check("the adapter never writes the ledger it reads", st, before)
check("the feed's publish gate accepts the NO", T.placeable(qs[no["id"]]), True)
check("start_verified: an ESPN tip is verified; a missing source is not",
      (PR.start_verified(qs[no["id"]]), PR.start_verified(dict(qs[no["id"]], start_source=None))), (True, False))

print("\nthe pages")
d = {"quotes": [], "coverage": {}}
sf = {"pairs": {}}
html = PR.page(d, sf, {"leads": {}, "pairs": {}}, "", now=NOW, nba_value=st)
import re
text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))
check("the Production page lists both pairs by name, moved 2026-10-24",
      ("NBA team total value · 24h before tip" in text, "NBA team total value · 1h before tip" in text, "moved 2026-10-24" in text),
      (True, True, True))
check("  and counts two pairs", "2 pairs in Production" in text, True)
import control_center as CC
m = CC.model(d, sf, {"leads": {}, "pairs": {}}, NOW, nba_value=st)
check("the Control Center counts them and names them", (m["tiles"]["pairs"], m["prod_outside"]),
      (2, list(NP.PAIRS.values())))
check("the copy passes the audit's guarded phrases", sandbox_audit.COPY_RE.search(html + open("nba_value_production.py").read()), None)
check("the OWN_LEDGER_LABELS name both sources", all(l in S.OWN_LEDGER_LABELS for l in NP.PAIRS), True)

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
