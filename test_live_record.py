#!/usr/bin/env python3
"""Offline checks for the live v paper column: the exporter (live_record_publish.py) and the Production page cells (production_live.py)."""
import json
import os
import sys
import tempfile

import live_record_publish as X
import production_live as PL

FAILS = []


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


def order(market, side, px, qty, pair="sr_a7|soccer_u35", quote=None, ko="2026-11-03T20:00:00+00:00", state="ORDER_STATE_FILLED", **kw):
    return dict(state="placed", market=market, side=side, price=px, filled=qty, avg_px=px, order_state=state, commission=0.0,
                lead=dict(pair=pair, sandbox_quote=quote or f"sr_a7:{market}", kickoff=ko), **kw)


print("the order rows come from the follower's own fills, settled by Kalshi's result")
mk = "KXUCLTOTAL-26NOV03FEYINT-4"
# results.json prices this contract with a position-wide P&L of -7 (another lane holds the NO): the order itself won.
res = {"k1": dict(resolved=True, market_settled=True, realised=-6.995, cost=6.995)}
row, stake = X.order_row("k1", order(mk, "Yes", 0.48, 2), res, {mk: "yes"})
check("a YES order on a market that settled yes is a win, whatever the merged position says", (row["st"], round(row["r"], 3)), ("won", round((2 * 0.52) / (2 * 0.48), 3)))
check("its stake is quantity x price paid", round(stake, 2), 0.96)
row, _ = X.order_row("k1", order(mk, "No", 0.10, 10), res, {mk: "yes"})
check("a NO order on the same market is the loss", (row["st"], row["r"]), ("lost", -1.0))
row, _ = X.order_row("k1", order(mk, "Yes", 0.48, 2), res, {})
check("an unsettled market is open", row["st"], "open")
row, _ = X.order_row("k1", order(mk, "Yes", 0.48, 0, state="ORDER_STATE_EXPIRED"), res, {})
check("an expired order with no fill is unfilled", row["st"], "unfilled")
row, _ = X.order_row("k1", dict(order(mk, None, 0.5, 1), side=None), dict(k1=dict(resolved=True, market_settled=True, realised=0.4)), {mk: "no"})
check("an older order with no side recorded falls back to the results row", row["st"], "won")
row, _ = X.order_row("k1", order(mk, "Yes", 0.48, 2), dict(k1=dict(closed_by_sale=True)), {mk: "yes"})
check("a bet sold early is left out of the record", row["st"], "sold")

print("\nthe refusals read as public categories")
check("categories", [X.category(t) for t in ("effective 0.9 above max_price 0.85", "price moved: ask 0.5 is +4c over", "too close to kickoff when first read",
                                              "thin book: $3", "something new")],
      ["price above the cap", "price moved from the logged price", "published inside 30 min of kickoff", "thin book", "other"])

print("\nthe whitelist refuses anything that is not public")
good = dict(generated="x", pairs={"p|s": dict(entered="2026-11-01", orders=[dict(id="p:KX-1", ko="2026-11-03T20:00", side="yes", st="won", w=1.0, r=0.5)], refused={})}, lanes={})
X.check(good)
for label, bad in (("a dollar sign", dict(id="Above $94", ko="x", side="yes", st="won", w=1.0, r=0.5)),
                   ("an extra field", dict(id="a", ko="x", side="yes", st="won", w=1.0, r=0.5, order_id="01a1")),
                   ("an unknown state", dict(id="a", ko="x", side="yes", st="mystery", w=1.0, r=0.5)),
                   ("a stake multiple out of range", dict(id="a", ko="x", side="yes", st="won", w=5000, r=0.5))):
    blob = dict(good, pairs={"p|s": dict(entered="2026-11-01", orders=[bad], refused={})})
    try:
        X.check(blob)
        check(f"refuses {label}", "accepted", "refused")
    except X.Refused:
        check(f"refuses {label}", "refused", "refused")

print("\nthe own-state lanes use their own fill and the market result")
with tempfile.TemporaryDirectory() as d:
    json.dump({"matches": {"KXUCLTOTAL-26NOV03FEYINT-4": dict(filled=10.0, bid=dict(price=0.1), kickoff=1793650800, sells=[]),
                           "KXUCLTOTAL-26NOV04FCPNAP-4": dict(filled=10.0, bid=dict(price=0.1), kickoff=1793650800, sells=[dict(qty=10)])}},
              open(os.path.join(d, "o35_state.json"), "w"))
    json.dump({"matches": {"no:KXNBAWINMARGIN-26NOV02ATLIND-ATL1TO5": dict(filled=1.0, bid=dict(price=0.65), tip=1793665800),
                           "yes:KXNBAWINMARGIN-26NOV02ATLIND-ATL1TO5": dict(filled=6.0, buy=dict(ask=0.16), tip=1793665800)}},
              open(os.path.join(d, "nba_wm_state.json"), "w"))
    lanes = X.lane_rows(d, lambda t: "no" if t.startswith("KXUCL") else "yes", "")
    check("o35: a NO bought at 10c on a market that settled no wins 9:1; the exited one is left out",
          [(r["st"], r["r"]) for r in lanes["o35_cheap_no"]], [("won", 9.0), ("sold", None)])
    check("nba_wm: the NO fade loses on a yes result, the YES split wins", ([r["st"] for r in lanes["nba_wm_nofade"]], [r["st"] for r in lanes["nba_wm_yes"]]),
          (["lost"], ["won"]))

print("\nthe page cells")
orders = [dict(id="q1", ko="2026-11-03T20:00", side="yes", st="won", w=1.0, r=1.0), dict(id="q2", ko="2026-11-03T20:00", side="yes", st="lost", w=1.0, r=-1.0),
          dict(id="q3", ko="2026-11-04T20:00", side="yes", st="open", w=1.0, r=None), dict(id="q0", ko="2026-10-01T20:00", side="yes", st="won", w=1.0, r=1.0)]
rec = PL.record(PL.window(orders, "2026-11-01T00:00:00+00:00"))
check("the window starts at the pair's Production date", (rec["won"], rec["lost"], rec["open"], rec["roi"]), (1, 1, 1, 0.0))
blob = dict(generated="2026-11-05T03:00Z", pairs={"a|b": dict(entered="2026-11-01", orders=orders, refused={"q9": "thin book"})}, lanes={})
frag_rec, frag_roi, data = PL.cells("a|b", "2026-11-01T00:00:00+00:00", dict(roi=0.25), blob)
check("the fragments carry the live record and the gap to paper, under the paper cells", ("1–1" in frag_rec, "-25.0pp v paper" in frag_roi), (True, True))
check("no live file adds nothing", PL.cells("a|b", None, dict(roi=None), None), ("", "", None))
paper = [dict(id="q1", status="won"), dict(id="q9", status="won"), dict(id="q5", status="won", ko="2026-11-01T20:00:00+00:00"), dict(id="q2", status="won")]
why = PL.explain(paper, PL.window(orders, "2026-11-01T00:00:00+00:00"), {"q9": "thin book"}, in_feed={"q1", "q2", "q9"}, feed_from="2026-11-02T00:00Z")
check("the gap is explained: refused, older than the feed, settled the other way", sorted(why),
      sorted(["refused: thin book", "older than the feed's retained history (settled leads are kept 7 days; cannot tell whether it was published)",
              "settled the other way (paper and live graded the match differently)",
              "live order outside the paper window (paper has no such bet since Production)"]))
sec = PL.gap_section([("Pair A", "a|b", 4, 0.25, data)], {"a|b": paper}, {"q1"}, {})
check("the section lists a pair whose counts differ by more than one bet", ("Pair A" in sec, "Where live and paper differ" in sec), (True, True))
check("and stays out when they agree", PL.gap_section([("Pair A", "a|b", 2, 0.0, data)], {"a|b": []}), "")
check("the own-state lanes are a separate live-only table", "Over 3.5 cheap NO" in PL.lanes_table(dict(lanes={"o35_cheap_no": orders}, lane_note="n")), True)

print("\nthe committed export")
real = json.load(open(X.OUT))
X.check(real)
X.check_lanes(real)
check("the committed export passes the whitelist and carries no dollar sign", "$" in json.dumps(real), False)

import production as P
import raised_stakes as RS
check("a raised stake shows its date under the pair, with no amount", ("stake raised Nov 6" in P.stake_note("sr_a7|soccer_u35"), "$" in P.stake_note("sr_a7|soccer_u35"), P.stake_note("sr_c1|soccer_u35")), (True, False, ""))
check("the raised pairs are the follower's own five", sorted(RS.pairs()), sorted(["mls_fade_home|soccer_p05", "commod_fav_band|commodities_fav", "crypto_fav_band_below|crypto_fav", "team2_ranked|soccer_team2", "sr_a7|soccer_u35"]))

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)

