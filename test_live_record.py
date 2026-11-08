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

print("\nthe own-state lanes are TRADES after fees: the logged sells plus the unsold remainder at settlement")
fee = X.fee_per_contract
check("the taker fee: 0.07 p (1-p) rounded up to $0.0001", (fee(0.16), fee(0.5)), (0.0095, 0.0175))
# fees are the EXCHANGE's: a resting sell piece pays nothing (its recorded `fee` field is the follower's modelled maker fee and is ignored); a taker piece pays the taker fee
piece = lambda size, price, taker=False: dict(size=size, price=price, taker=taker, fee_per_contract=fee(price))
sf = lambda leg, size, price, taker=False: {"c": dict(leg=leg, size=size, price=price, fee=0.123, fills=[piece(size, price, taker)])}
check("sell_fee: a resting piece is free, a taker piece pays the taker fee, the modelled `fee` is ignored",
      (X.sell_fee(sf("2x", 3.0, 0.32)["c"]), round(X.sell_fee(sf("2x", 3.0, 0.32, True)["c"]), 6)), (0, round(3 * fee(0.32), 6)))
# a YES split: 6 bought at 0.16 (taker), 3 sold at 0.32 (2x leg) and 3 at 0.48 (3x leg)
t, stake = X.own_trade("yes", 0.16, 6.0, True, {"a": sf("2x", 3.0, 0.32)["c"], "b": sf("3x", 3.0, 0.48)["c"]}, "no", split=True)
want = (3 * 0.32 + 3 * 0.48 - (6 * 0.16 + 6 * fee(0.16))) / (6 * 0.16 + 6 * fee(0.16))
check("both legs filled: the trade is won on the sells whatever the market settled, legs 2x+3x", (t["st"], t["legs"], t["r"]), ("won", "2x+3x", round(want, 4)))
check("the same entry held to a lost settlement is the hold control", t["hold_r"], round((0 - stake) / stake, 4))
t, _ = X.own_trade("yes", 0.16, 6.0, True, {"a": sf("2x", 3.0, 0.32)["c"]}, "no", split=True)
check("only the 2x leg filled: half sold at 2x (cost back), the other half expires: gross 0%, -5.6% after the entry fee: FLAT (a scratch), legs 2x",
      (t["legs"], t["st"], t["g"], -0.1 < t["r"] < -0.02), ("2x", "flat", 0.0, True))
t, _ = X.own_trade("yes", 0.16, 6.0, True, {"a": sf("2x", 1.0, 0.32)["c"]}, "no", split=True)
check("one contract of six sold at 2x: gross -83%, a real loss", (t["st"], t["g"] < -0.5), ("lost", True))
t, _ = X.own_trade("yes", 0.16, 6.0, True, {}, None, split=True)
check("an open trade carries no return, gross or state bucket", (t["st"], t["r"], t["g"]), ("open", None, None))
check("result_state: scratch before fees is flat, +3% after fees is won, -3% with a -3% gross is lost",
      (X.result_state(-0.056, 0.0), X.result_state(0.03, 0.04), X.result_state(-0.03, -0.03)), ("flat", "won", "lost"))
for bad, why in ((dict(id="x", ko="2026-11-01T00:00", side="yes", st="won", r=1.0, g=900.0, w=1.0, legs="", hold_r=None, src="fills"), "a gross return out of range"),):
    try:
        X.check_lanes(dict(lanes={"top5_dip": [bad]}))
        check(f"refuses {why}", "accepted", "refused")
    except X.Refused:
        check(f"refuses {why}", "refused", "refused")
t, _ = X.own_trade("no", 0.5, 2.0, False, {"a": sf("sold", 2.0, 0.51)["c"]}, "yes")
check("a sale 2% over the bid with no fee is exactly +2%: flat, not won", (t["st"], t["r"]), ("flat", 0.02))
t, _ = X.own_trade("yes", 0.16, 6.0, True, {}, "no", split=True)
check("no leg filled and the bucket missed: lost, -100% of the stake", (t["st"], t["r"], t["legs"]), ("lost", -1.0, ""))
t, _ = X.own_trade("yes", 0.16, 6.0, True, {}, None, split=True)
check("an unsettled remainder keeps the trade open", (t["st"], t["r"]), ("open", None))
t, _ = X.own_trade("yes", 0.16, 6.0, True, {"a": sf("2x", 3.0, 0.32)["c"], "b": sf("3x", 3.0, 0.48)["c"]}, None, split=True)
check("everything sold: settled before the market is", t["st"], "won")
t, _ = X.own_trade("no", 0.65, 1.0, False, sf("sold", 1.0, 0.87), "yes")
check("a NO fade sold at P and the NO later lost is a WIN on the trade", (t["st"], t["legs"], round(t["r"], 3) > 0.25), ("won", "sold", True))
t, _ = X.own_trade("no", 0.65, 1.0, False, {}, "yes")
check("a NO fade never sold and lost at settlement is a loss", (t["st"], t["r"]), ("lost", -1.0))

with tempfile.TemporaryDirectory() as d:
    sell = {"c1": dict(leg="sell", size=10.0, price=0.4, fee=0.5, fills=[piece(10.0, 0.4)])}
    json.dump({"matches": {"KXUCLTOTAL-26NOV03FEYINT-4": dict(filled=10.0, bid=dict(price=0.1), kickoff=1793650800, sells=[]),
                           "KXUCLTOTAL-26NOV07FCPNAP-4": dict(filled=10.0, bid=dict(price=0.1), kickoff=1794200000, sells=[dict(qty=10)], sell_fills=sell)}},
              open(os.path.join(d, "o35_state.json"), "w"))
    json.dump({"matches": {"no:KXNBAWINMARGIN-26NOV02ATLIND-ATL1TO5": dict(filled=1.0, bid=dict(price=0.65), tip=1793665800),
                           "yes:KXNBAWINMARGIN-26NOV02ATLIND-ATL1TO5": dict(filled=6.0, buy=dict(ask=0.16), tip=1793665800)}},
              open(os.path.join(d, "nba_wm_state.json"), "w"))
    json.dump({"matches": {"KXEPLTOTAL-26NOV06EVECOV-2": dict(filled=2.0, bid=dict(price=0.44), kickoff=1793993400,
                                                              sell_fills={"s": dict(leg="sell", size=2.0, price=0.8, fee=0.0056, fills=[piece(2.0, 0.8)])})}},
              open(os.path.join(d, "top5_dip_state.json"), "w"))
    recon = {("o35_cheap_no", "KXUCLTOTAL-26NOV03FEYINT-4"): dict(lane="o35_cheap_no", id="KXUCLTOTAL-26NOV03FEYINT-4", st="lost", r=-1.0, w=1.0, legs="", hold_r=None)}
    lanes = X.lane_rows(d, lambda t: "no" if t.startswith("KXUCL") else "yes", "", recon)
    check("o35: a pre-logging entry reads the reconstruction (labelled), a logged sell reads its own fill",
          [(r["st"], r["src"], r["legs"]) for r in lanes["o35_cheap_no"]], [("lost", "reconstructed", ""), ("won", "fills", "sold")])
    check("o35: the sold-at-4x trade is a win of exactly 3x with no fee on either resting fill", lanes["o35_cheap_no"][1]["r"], 3.0)
    check("nba_wm: the NO fade loses on a yes result, the YES split (no sell logged) is held to settlement and wins",
          ([r["st"] for r in lanes["nba_wm_nofade"]], [r["st"] for r in lanes["nba_wm_yes"]]), (["lost"], ["won"]))
    check("the YES split row carries its hold control", lanes["nba_wm_yes"][0]["hold_r"] is not None, True)
    dip = lanes["top5_dip"][0]
    check("the top-5 dip is a lane: sold at P is a win, 80c in on a 44c bid", (dip["st"], dip["legs"], dip["src"], round(dip["r"], 2)), ("won", "sold", "fills", round((0.8 - 0.44) / 0.44, 2)))
    X.check_lanes(dict(lanes=lanes))
    check("and the whole lanes blob passes the whitelist", True, True)
    for bad, why in ((dict(lanes[ "top5_dip"][0], balance=1.0), "an extra field"), (dict(lanes["top5_dip"][0], legs="3x+9x"), "legs outside the whitelist"),
                     (dict(lanes["top5_dip"][0], src="vps"), "a source outside the whitelist"), (dict(lanes["top5_dip"][0], r=500.0), "a return out of range"),
                     (dict(lanes["top5_dip"][0], id="$5"), "a dollar sign")):
        try:
            X.check_lanes(dict(lanes={"top5_dip": [bad]}))
            check(f"refuses {why}", "accepted", "refused")
        except X.Refused:
            check(f"refuses {why}", "refused", "refused")

print("\nthe committed reconstruction")
rec_blob = json.load(open(X.RECON))
X.check_reconstructed(rec_blob)
check("it passes the whitelist and says where it comes from", ("reconstructed from the exchange order list" in rec_blob["header"], "$" in json.dumps(rec_blob)), (True, False))
check("every reconstructed row carries a gross return; a flat row is a scratch (|r| or |g| within 2%)", (all("g" in r for r in rec_blob["rows"]), all((r["st"] == "flat") == (abs(r["r"]) <= 0.02 or abs(r["g"]) <= 0.02) for r in rec_blob["rows"])), (True, True))
check("only the three pre-logging lanes, every tip before the cutoff", ({r["lane"] for r in rec_blob["rows"]} <= {"o35_cheap_no", "nba_wm_yes", "nba_wm_nofade"}, all(r["ko"] < X.RECON_BEFORE for r in rec_blob["rows"])), (True, True))
check("only the YES split carries a hold control", {r["lane"] for r in rec_blob["rows"] if r.get("hold_r") is not None}, {"nba_wm_yes"})
bad_blob = dict(rec_blob, rows=rec_blob["rows"] + [dict(lane="nba_wm_yes", id="x", ko="2026-11-01T00:00", side="yes", st="won", r=1.0, w=1.0, legs="", hold_r=None, order_id="abc")])
try:
    X.check_reconstructed(bad_blob)
    check("a reconstruction row with an extra field is refused", "accepted", "refused")
except X.Refused:
    check("a reconstruction row with an extra field is refused", "refused", "refused")

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
check("the own-state lanes are a separate live-only table", "Over 3.5 cheap NO" in PL.lanes_table(dict(lanes={"o35_cheap_no": [dict(o, src="fills") for o in orders]}, lane_note="n")), True)
check("an export from before the trades schema (no source on a row) is not shown as a live record",
      (PL.lanes_table(dict(lanes={"o35_cheap_no": orders}, lane_note="n")), PL.own_rows(dict(lanes={"o35_cheap_no": orders}), "o35_cheap_no_wave|soccer_u35")), ("", None))

print("\nthe committed export")
real = json.load(open(X.OUT))
X.check(real)
X.check_lanes(real)
check("the committed export passes the whitelist and carries no dollar sign", "$" in json.dumps(real), False)

import production as P
import raised_stakes as RS
check("a raised stake shows its date under the pair, with no amount", ("stake raised Nov 6" in P.stake_note("sr_a7|soccer_u35"), "$" in P.stake_note("sr_a7|soccer_u35"), P.stake_note("sr_c1|soccer_u35")), (True, False, ""))
check("the raised pairs are the follower's own seven in Production (the commodities band went back to the Sandbox 2026-11-08; sr_a6, Team 1+ and Under 3.5 Internationals raised the same day)", sorted(RS.pairs()),
      sorted(["mls_fade_home|soccer_p05", "crypto_fav_band_below|crypto_fav", "team2_ranked|soccer_team2", "sr_a7|soccer_u35", "sr_a6|soccer_o25",
              "team1_form_l5|soccer_team1_intl", "u35_low_scoring|soccer_u35_intl"]))

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)

