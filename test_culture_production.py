#!/usr/bin/env python3
"""Offline checks for the Trump mentions Production feed (culture_production.py, 2026-10-20)."""
import datetime as dt
import json
import sys

import culture_build as KB
import culture_production as CP
import production as P
import sandbox_audit
import sandbox_track as T

FAILS = []
UTC = dt.timezone.utc
NOW = dt.datetime(2026, 10, 21, 12, 0, tzinfo=UTC)


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


def pick(t, word, side, price, status="open", close="2026-10-26T14:00:00Z", logged="2026-10-21T10:00:00+00:00", **kw):
    ev = t.rsplit("-", 1)[0]
    return dict(dict(id=t, event=ev, series=t.split("-")[0], name="What will Trump say this week?", title=word,
                     side=side, price=price, close=close, logged=logged, status=status, detail="", category="Mentions"), **kw)


state = {"lanes": {k: {"picks": [], "observations": {}, "error": None} for k in ("culture_fav_band", "culture_endgame",
                                                                              "mentions_rate", "rt_model")}}
lane = state["lanes"]["mentions_rate"]
lane["last_success"] = (NOW - dt.timedelta(minutes=20)).isoformat()
lane["picks"] += [pick("KXTRUMPSAY-26OCT26-ANTI", "Antifa", "no", 0.79, model=0.08),
                  pick("KXTRUMPSAY-26OCT26-TARI", "Tariff", "yes", 0.62),
                  pick("KXTRUMPSAY-26OCT19-BIBI", "Bibi", "no", 0.80, status="lost", close="2026-10-19T14:00:00Z",
                       logged="2026-10-17T10:00:00+00:00", profit=-100.0, payout=1),
                  pick("KXOTHER-26OCT26-X", "X", "no", 0.70)]                 # not a mentions series

print("quotes: the lane's entries, read-only")
qs = CP.quotes(state)
check("only KXTRUMPSAY contracts", sorted(q["market_id"] for q in qs),
      ["KXTRUMPSAY-26OCT19-BIBI", "KXTRUMPSAY-26OCT26-ANTI", "KXTRUMPSAY-26OCT26-TARI"])
q_no, q_yes = (next(q for q in qs if q["market_id"].endswith(s)) for s in ("ANTI", "TARI"))
check("NO is pick b at its own price, YES pick a", ((q_no["pick"], q_no["price"]), (q_yes["pick"], q_yes["price"])),
      (("b", 0.79), ("a", 0.62)))
check("the deadline is the contract's close", (q_no["start"], q_no["start_source"]), ("2026-10-26T14:00:00+00:00", "contract_close"))
lost = next(q for q in qs if q["market_id"].endswith("BIBI"))
check("a lost NO settles as side a (he said it)", (lost["status"], lost["result"]), ("lost", "a"))
check("the feed may publish them", [T.placeable(q) for q in (q_no, q_yes)], [True, True])
check("a non-mentions ticker never is", T.placeable(dict(q_no, market_id="KXRT-WHA-70")), False)
check("its deadline counts as verified", P.start_verified(q_no), True)

print("\nthe leads: the exact contract and side")
f = CP.feed(state, now=NOW)
leads = {l["route"]["market"]: l for l in f["leads"].values()}
check("the pair is listed, moved by hand", (list(f["pairs"]), f["pairs"][CP.PAIR].get("by_hand")), ([CP.PAIR], "2026-10-20"))
check("two open leads; the Oct 19 one closed before Production and is not a lead", sorted(leads),
      ["KXTRUMPSAY-26OCT26-ANTI", "KXTRUMPSAY-26OCT26-TARI"])
no = leads["KXTRUMPSAY-26OCT26-ANTI"]
check("the NO lead: kind mention_no, the No of the exact contract, headline in words",
      (no["bet"], no["route"]["outcome_side"], no["route"]["price_at_log"], no["headline"], no["league"]),
      ({"kind": "mention_no", "subject": "Antifa", "p_said": 0.08}, "no", 0.79, 'Trump does not say "Antifa"', "Trump mentions"))
check("the feed carries the model's P(said) on the bet (2026-10-24), not as model_prob",
      (no["bet"].get("p_said"), "model_prob" in no), (0.08, False))
yes = leads["KXTRUMPSAY-26OCT26-TARI"]
check("an entry with no model P carries no p_said", "p_said" in yes["bet"], False)
check("the YES lead: kind mention, outcome_side yes", (yes["bet"]["kind"], yes["route"]["outcome_side"], yes["route"]["outcome"]),
      ("mention", "yes", "Tariff"))
stale = dict(state, lanes=dict(state["lanes"], mentions_rate=dict(lane, last_success=(NOW - dt.timedelta(hours=5)).isoformat())))
check("a stale scan (5h) publishes no open lead", len(CP.feed(stale, now=NOW)["leads"]), 0)
errd = dict(state, lanes=dict(state["lanes"], mentions_rate=dict(lane, error="scan: boom")))
check("a failed scan publishes no open lead", len(CP.feed(errd, now=NOW)["leads"]), 0)

print("\nthe pages")
d, st, blob = CP.page_inputs({"quotes": []}, {"pairs": {}}, {"leads": {}, "pairs": {}}, state, now=NOW)
check("page inputs add the pair and its quotes without touching the originals",
      (CP.PAIR in st["pairs"], len(d["quotes"]), len(blob["leads"])), (True, 3, 2))
html = P.page({"quotes": []}, {"pairs": {}}, {"leads": {}, "pairs": {}}, "", now=NOW, culture=state)
check("the Production page lists the pair and its NO lead in words",
      ("Trump mentions" in html, 'Trump does not say "Antifa"' in html or "Trump does not say &quot;Antifa&quot;" in html), (True, True))
check("the Culture page says the lane is in Production", "Production · since 2026-10-20" in KB.build(state, NOW), True)
check("no guarded public phrase in the leads", sandbox_audit.COPY_RE.findall(" ".join(l["headline"] for l in f["leads"].values())), [])

print("\n2026-10-26: back to the Sandbox, the Production record kept")
OUT = dt.datetime(2026, 10, 26, 18, 0, tzinfo=UTC)
check("listed until 16:40Z on 2026-10-26 (the follower's switch went off then), not after",
      (CP.listed(dt.datetime(2026, 10, 26, 16, 39, tzinfo=UTC)), CP.listed(dt.datetime(2026, 10, 26, 16, 40, tzinfo=UTC)),
       CP.listed(OUT), CP.DEMOTED_ON), (True, False, False, "2026-10-26"))
check("no Production listing is left, so nothing re-promotes it", (CP.pairs(OUT), CP.pairs(NOW) == {CP.PAIR: CP.pairs(NOW)[CP.PAIR]}),
      ({}, True))
check("sandbox_track names the removal, record kept", T.PAIR_REMOVALS[CP.PAIR], dict(removed_on="2026-10-26", keep_record=True))
out_state = json.loads(json.dumps(state))
ol = out_state["lanes"]["mentions_rate"]
ol["last_success"] = (OUT - dt.timedelta(minutes=20)).isoformat()
ol["picks"] += [pick("KXTRUMPSAY-26OCT26-WALL", "Wall", "no", 0.85, status="won", logged="2026-10-22T10:00:00+00:00",
                     close="2026-10-26T14:00:00Z", profit=13.2, payout=0),
                pick("KXTRUMPSAY-26NOV02-NEWA", "New", "no", 0.88, close="2026-11-02T14:00:00Z",
                     logged="2026-10-26T17:41:00+00:00", amended="2026-10-26")]
fo = CP.feed(out_state, now=OUT)
check("the feed lists no pair and names no open lead", (fo["pairs"], [l for l in fo["leads"].values() if l.get("status") == "pending"]),
      ({}, []))
check("its Production-era settled lead stays, for grading only (lane retired); the pre-Production one does not",
      sorted((l["route"]["market"], l.get("lane"), l.get("retired_on")) for l in fo["leads"].values()),
      [("KXTRUMPSAY-26OCT26-WALL", "retired", "2026-10-26")])
check("the record it left Production on: entries logged while listed",
      {k: v for k, v in CP.removed_record(out_state).items() if k != "roi"}, dict(won=1, lost=0, settled=1, open=2))
d0, st0, b0 = {"quotes": []}, {"pairs": {}}, {"leads": {}, "pairs": {}}
check("page inputs add nothing once it is out", CP.page_inputs(d0, st0, b0, out_state, now=OUT), (d0, st0, b0))
ph = P.page({"quotes": []}, {"pairs": {}}, {"leads": {}, "pairs": {}}, "", now=OUT, culture=out_state)
check("the Production page says when it left and on what record, and lists no Trump mentions pair",
      ("Trump mentions left Production on 2026-10-26 (moved 2026-10-20)" in ph, "<b>0</b><span>pairs in Production" in ph,
       "Trump does not say" in ph), (True, True, False))
import control_center as CC
m = CC.model({"quotes": [], "coverage": {}}, {"pairs": {}}, {"leads": {}, "pairs": {}}, OUT, culture=out_state)
check("the Control Center: not counted, not named as in Production, named as removed on 2026-10-26",
      (m["tiles"]["pairs"], "Trump mentions" in m["prod_outside"], [x[:52] for x in m["prod_left"]]),
      (0, False, ["Trump mentions left Production on 2026-10-26 (moved "]))
m_in = CC.model({"quotes": [], "coverage": {}}, {"pairs": {}}, {"leads": {}, "pairs": {}}, NOW, culture=state)
check("  and on 2026-10-21 it was counted and named", (m_in["tiles"]["pairs"], m_in["prod_outside"], m_in["prod_left"]),
      (1, ["Trump mentions"], []))
kh = KB.build(out_state, OUT)
check("the Culture page chips it Removed from Production, a Sandbox row",
      ("Removed from Production · 2026-10-26" in kh, "Production · since 2026-10-20" in kh), (True, False))
check("no guarded public phrase in the removal note", sandbox_audit.COPY_RE.findall(CP.removed_note(out_state)), [])

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
