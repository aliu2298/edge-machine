#!/usr/bin/env python3
"""Offline checks for the Trump mentions Production feed (culture_production.py, 2026-10-20)."""
import datetime as dt
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
lane["picks"] += [pick("KXTRUMPSAY-26OCT26-ANTI", "Antifa", "no", 0.79),
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
      ({"kind": "mention_no", "subject": "Antifa"}, "no", 0.79, 'Trump does not say "Antifa"', "Trump mentions"))
yes = leads["KXTRUMPSAY-26OCT26-TARI"]
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

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
