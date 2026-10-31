#!/usr/bin/env python3
"""The cheap-side split in the chaos engine (2026-10-27): challenger_cheap_split, the split exit on every
lane (additive), and the Chaos section with split v hold first."""
import copy
import re
import sys

import chaos_build as CB
import chaos_lanes
import chaos_replay as C
import sandbox_audit

FAILS = []


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


T0 = 1_800_000_000 - 1_800_000_000 % 60


def minute(k, bid, ask, px_hi=None, px_lo=None):
    return dict(ts=T0 + 60 * k, bid=bid, ask=ask, bid_lo=bid, bid_hi=bid, ask_lo=ask, ask_hi=ask, px_hi=px_hi, px_lo=px_lo)


print("the split exit")
check("its terms: half at 2x, half at 3x, cap 0.98; every lane carries it after the old exits",
      (C.SPLIT_LEGS, C.SPLIT_CAP, C.LANE_EXITS[-1], set(C.EXITS) < set(C.LANE_EXITS)), (((2.0, 0.5), (3.0, 0.5)), 0.98, "split", True))
check("targets from the ask paid, capped", (C.split_targets(0.20), C.split_targets(0.40)),
      ([(2.0, 0.5, 0.4), (3.0, 0.5, 0.6)], [(2.0, 0.5, 0.8), (3.0, 0.5, 0.98)]))
# Entry at minute 0 (YES 0.18/0.20). A bid of 0.45 never fills a leg; a traded 0.40 fills the 2x; nothing at 0.60.
mins = [minute(0, 0.18, 0.20), minute(1, 0.45, 0.47), minute(2, 0.30, 0.33, px_hi=0.40), minute(3, 0.10, 0.12, px_hi=0.15)]
vs = [C.view(m, "yes") for m in mins]
t = C._split_trade(vs, 0, False)
fin = 0.20 + 0.07 * 0.20 * 0.80
check("only a traded print fills a leg (a bid of 0.45 does not); 2x filled, 3x held to a loss",
      (t["filled_2x"], t["filled_3x"], t["legs"][0]["filled_ts"] == T0 + 120, round(t["profit"], 5)),
      (True, False, True, round(0.5 * (0.40 - 0.0175 * 0.40 * 0.60) - fin, 5)))
t_won = C._split_trade(vs, 0, True)
check("the 3x leg held to a YES win is paid 1", round(t_won["profit"], 5),
      round(0.5 * (0.40 - 0.0175 * 0.40 * 0.60) + 0.5 - fin, 5))
no = [C.view(m, "no") for m in [minute(0, 0.80, 0.82), minute(1, 0.60, 0.62, px_lo=0.60)]]
check("the NO side reads the YES traded low: NO entry 0.20, the 2x (0.40) fills when YES trades at 0.60 or under",
      (no[0]["ask"], C._split_trade(no, 0, False)["filled_2x"]), (0.2, True))
check("a minute with no trade carries none forward", C.dense([dict(end_period_ts=T0, yes_bid=dict(close_dollars="0.1"),
      yes_ask=dict(close_dollars="0.12"), price=dict(high_dollars="0.5"))], T0, T0 + 120)[1]["px_hi"], None)

print("\nchallenger_cheap_split")
L0 = next(l for l in chaos_lanes.LANES if l["id"] == "challenger_cheap_split")
check("its terms: Challenger only, 1h, 5c spread, exits hold and split, first on the page, fresh from 2026-10-26",
      (L0["series"], L0["entry_hours"], L0["max_spread"], L0["exits"], L0["headline"], L0["first"], L0["since"], L0["duration_min"]),
      (["KXATPCHALLENGERMATCH"], (1,), 0.05, ("hold", "split"), "split", True, "2026-10-26", 120))
check("the start as challenger_dog_tp30 (no own source: the price path, else close minus 120 minutes)",
      ("start" in L0, next(l for l in chaos_lanes.LANES if l["id"] == "challenger_dog_tp30").get("start")), (False, None))
views = {"A": dict(ask=0.22, bid=0.18), "B": dict(ask=0.80, bid=0.77), "C": dict(ask=0.12, bid=0.10), "D": dict(ask=0.25, bid=0.19)}
ctx = dict(tickers=list(views), entry_view=lambda t, s: views[t])
check("the picker: YES 0.15-0.30 with a 5c spread or less (A at 4c in, D at 6c out, C under 0.15 out)",
      L0["picker"](ctx), [("A", "yes")])
check("the variants are the two exits only", C.variants_of(dict(entry_hours=[1], exits=["hold", "split"])), ["t1h_hold", "t1h_split"])
check("a split's control is the same entry held", C.control_of("t1h_split"), "t1h_hold")

print("\nthe split joins the older lanes additively")
old = dict(id="old", series=["KXX"], entry_hours=(1,), exits=None)
L = dict(trades=[dict(event="KXX-26OCT25A", ticker="T1", side="yes", hours=1, exit_key=k, variant=f"t1h_{k}", roi=0.1)
                 for k in C.EXITS], replayed={"KXX-26OCT25A": 1})
before = copy.deepcopy(L["trades"])
_saved = C.replay_event
C.replay_event = lambda lane, series, event, fetch, now=None: (
    [dict(event=event, ticker="T1", side="yes", hours=1, exit_key=k, variant=f"t1h_{k}", roi=9.9) for k in C.LANE_EXITS]
    + [dict(event=event, ticker="T9", side="yes", hours=1, exit_key="split", variant="t1h_split", roi=9.9)], None)
try:
    C._backfill(L, old, None, None, [])
finally:
    C.replay_event = _saved
check("only the missing split of a recorded entry is appended; every old row is unchanged; no new entry",
      (L["trades"][:len(before)] == before, [(t["ticker"], t["exit_key"]) for t in L["trades"][len(before):]]),
      (True, [("T1", "split")]))

print("\nthe Chaos section")


def tr(lane, k, roi, won, night="2026-10-26", f2=False, f3=False, hours=1, ticker="T1"):
    return dict(event="E-" + ticker, ticker=ticker, side="yes", hours=hours, exit_key=k, variant=f"t{hours}h_{k}", roi=roi,
                profit=roi * 0.2, cost=0.2, won=won, night=night, reason="split" if k == "split" else "settled",
                entry=0.2, entry_ts=T0, filled_2x=f2, filled_3x=f3)


state = {"lanes": {
    "atp_coinflip_tp30": dict(id="atp_coinflip_tp30", label="ATP coin-flip · sell +30%", since="2026-10-25",
                                entry_hours=[1], exits=list(C.LANE_EXITS), series=["KXATPCHALLENGERMATCH"], replayed={"a": 1},
                                trades=[tr(0, "hold", -1.0, False), tr(0, "tp30", 0.3, True)]),
    "challenger_cheap_split": dict(id="challenger_cheap_split", label="Challenger cheap side · split 2x / 3x", first=True,
                                   since="2026-10-26", entry_hours=[1], exits=["hold", "split"], series=["KXATPCHALLENGERMATCH"],
                                   replayed={"b": 1}, trades=[tr(0, "hold", 1.5, True), tr(0, "split", 1.0, True, f2=True, f3=True)])},
    "last_run": "2026-10-27T09:00:00+00:00"}
# The Sandbox's Chaos section is an index (2026-10-27); the summary and cards render on the sport page.
# atp_coinflip_tp30 was retired 2026-10-29; its retirement is lifted here so it still stands in as the
# older lane without split rows (the retirement itself is checked at the end of this file).
import chaos_lanes
_lanes = chaos_lanes.LANES
chaos_lanes.LANES = [dict(c, retired=None) if c["id"] in ("atp_coinflip_tp30", "challenger_cheap_split") else c for c in _lanes]
h = CB.sport_section("tennis", state)
chaos_lanes.LANES = _lanes
text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h))
check("the standard header", all(x in text for x in ("Cheap side + resting take-profit", "Rest a split sell: half at 2x, half at 3x.",
                                                  "A fill counts only on a traded print.", "Every lane is shown next to the same entries held.")), True)
summ = h[h.find('class="chaos-summary"'):h.find("</table>", h.find('class="chaos-summary"'))]
check("the summary: challenger_cheap_split first, then the other tennis lane",
      re.findall(r'data-lane="([^"]+)"', summ), ["challenger_cheap_split", "atp_coinflip_tp30"])
check("its columns", [re.sub(r"<[^>]+>", "", x) for x in re.findall(r"<th[^>]*>(.*?)</th>", summ)],
      ["Lane", "Entries", "Unverified asks", "Settled entries", "Settled events", "Won", "Split ROI", "Hold ROI", "Legs filled 2x / 3x", "Avg spread paid", "Status"])
check("the new lane's row: 1 entry, 1 settled, 1 won, +100% split, +150% hold, legs 1 / 1, review at 10",
      "Challenger cheap side · split 2x / 3x 1 0 1 1 1 +100.0% +150.0% 1 / 1 — 1 settled event · review at 10, decide at 30" in text, True)
check("an older lane without split rows yet shows — for split, and says the split is being added",
      ("ATP coin-flip · sell +30% 1 0 1 1 0 — −100.0%" in text.replace("-100.0%", "−100.0%"),
       "the split joined this lane on 2026-10-27 and is being added to its earlier entries" in text), (True, True))
idx = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", CB.section(state)))
check("the Sandbox's Chaos section is an index: rows and links to the sport pages, no cards",
      ("Challenger cheap side · split 2x / 3x Tennis 1 1 1 +100.0% +150.0%" in idx, 'href="./tennis.html#cheap-side"' in CB.section(state),
       "Split v hold" in CB.section(state)), (True, True, False))
cards = re.findall(r'<details class="section-disclosure" data-lane="([^"]+)" open>', h)
check("the cards in the same order", cards, ["challenger_cheap_split", "atp_coinflip_tp30"])
old_card = h[h.find('data-lane="atp_coinflip_tp30" open'):]
check("each card shows split v hold first; the old targets sit in a collapsed Other exits block",
      (old_card.find("Split v hold") < old_card.find("<summary><b>Other exits</b>"),
       '<details class="section-disclosure"><summary><b>Other exits</b>' in old_card, "sell at +30%" in old_card), (True, True, True))
new_card = h[h.find('data-lane="challenger_cheap_split" open'):h.find('data-lane="atp_coinflip_tp30" open')]
check("the split lane has no Other exits block (it carries only hold and split)", "Other exits" in new_card, False)
check("tables stay header-row tables for the phone labels", ("<thead>" not in h, h.count("<table") == h.count('<div class="tbl"><table')),
      (True, True))
check("public copy passes the guard", sandbox_audit.COPY_RE.search(text), None)
print("\nretired: atp_coinflip_tp30 (2026-10-29) and challenger_cheap_split (2026-10-31) leave the live cards for the Retired block")
rh = CB.sport_section("tennis", state)
rtext = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", rh))
check("no live summary or card remains; the section says every lane is retired",
      ('class="chaos-summary"' in rh, re.findall(r'<details class="section-disclosure" data-lane="([^"]+)" open>', rh),
       "Every cheap-side lane on this page is retired" in rtext), (False, [], True))
check("both sit in the collapsed Retired block with their dates, records and reasons",
      ('id="cheap-side-retired"' in rh, "Retired 2026-10-29 at 13 settled, 6 won; split -2.0%, hold -1.5%" in rtext,
       "every take-profit exit loses to holding" in rtext,
       "Retired 2026-10-31 at 34 settled, 10 won; split +0.8%, hold +19.6%: decided at 34 settled: the split sell (+0.8%) lost to holding (+19.6%)" in rtext,
       "not a proven edge" in rtext), (True,) * 5)
check("the NBA underdog card notes its decide-point review (kept as paper)",
      "Reviewed at 31: kept as paper (beats hold, not strong enough to promote)" in CB.sport_section("nba", {"lanes": {}, "last_run": None}) or
      "Reviewed at 31: kept as paper" in str(next(l for l in chaos_lanes.LANES if l["id"] == "nba_ml_dog_tp50")["caution"]), True)

print("\nnba_ml_dog_tp50: the split headline and the ask 10-30c sub-band (2026-10-28)")
N = next(l for l in chaos_lanes.LANES if l["id"] == "nba_ml_dog_tp50")
check("same lane id and entries; headline the split; every exit still tracked; no reset (since 2026-10-25)",
      (N["picker"] is chaos_lanes.DOG, N["entry_hours"], N["headline"], C.lane_exits(N), N["since"], N["label"]),
      (True, (1,), "split", C.LANE_EXITS, "2026-10-25", "NBA moneyline underdog · split 2x / 3x"))
check("one sub-band, ask 10-30c, inside the lane's 10-40c population",
      [(b["id"], b["lo"], b["hi"]) for b in N["sub_bands"]], [("ask_10_30", 0.10, 0.30)])
# A ledger written under the old config: +50% headline, old label and caution. Nothing in its trades changes.
old_L = dict(id="nba_ml_dog_tp50", label="NBA moneyline underdog · sell +50%", headline="tp50", since="2026-10-25",
             caution="In the research HOLD beat the sell", note="old", entry_hours=[1], exits=list(C.LANE_EXITS),
             series=["KXNBAGAME"], replayed={}, trades=[])
for i, (ask, won, split_roi) in enumerate(((0.10, False, 1.3), (0.29, True, 2.2), (0.30, False, -1.0), (0.31, True, 1.9),
                                           (0.39, True, 1.4), (0.40, False, -1.0))):
    base = dict(event=f"KXNBAGAME-26OCT2{5 + i % 3}G{i}", ticker=f"T{i}", side="yes", hours=1, night=f"2026-10-2{5 + i % 3}",
                entry=ask, spread=0.01, cost=ask, entry_ts=1_793_000_000 + 3600 * i)
    hold_roi = (1 - ask) / ask if won else -1.0
    old_L["trades"].append(dict(base, exit_key="hold", variant="t1h_hold", roi=hold_roi, profit=hold_roi * ask,
                                won=won, reason="settled"))
    old_L["trades"].append(dict(base, exit_key="split", variant="t1h_split", roi=split_roi, profit=split_roi * ask,
                                won=split_roi > 0, reason="split", filled_2x=split_roi > 0, filled_3x=split_roi > 1.5))
before = copy.deepcopy(old_L["trades"])
st_n = dict(lanes={"nba_ml_dog_tp50": copy.deepcopy(old_L)})
L_new = C.lane_state(st_n, N, C.dt.datetime(2026, 10, 28, 10, tzinfo=C.UTC))
check("the next replay rewrites label, headline, caution and sub-bands on the SAME record, trades untouched",
      (L_new["label"], L_new["headline"], "HOLD beat" in L_new["caution"], L_new["sub_bands"][0]["id"], L_new["trades"] == before,
       L_new["registered"] if "registered" in L_new else None),
      ("NBA moneyline underdog · split 2x / 3x", "split", False, "ask_10_30", True, None))
shown = CB.with_config(dict(lanes={"nba_ml_dog_tp50": copy.deepcopy(old_L)}))["lanes"]["nba_ml_dog_tp50"]
check("a page built before that replay already shows the new label and the sub-band (a copy, never saved)",
      (shown["label"], shown["sub_bands"][0]["label"], old_L["label"]),
      ("NBA moneyline underdog · split 2x / 3x", "ask 10-30c", "NBA moneyline underdog · sell +50%"))
band = N["sub_bands"][0]
full, narrow = CB.split_hold(shown), CB.split_hold(shown, band=band)
check("the sub-band keeps entries asked 10-30c, edges included (0.10, 0.29, 0.30), and drops 0.31-0.40",
      (full["entries"], narrow["entries"], narrow["won"]), (6, 3, 1))
check("its split v hold is computed on those entries alone",
      (round(narrow["split"], 4), round(narrow["hold"], 4)),
      (round((0.13 + 0.638 - 0.30) / 0.69, 4), round((-0.10 + 0.71 - 0.30) / 0.69, 4)))
nba = CB.sport_section("nba", dict(lanes={"nba_ml_dog_tp50": copy.deepcopy(old_L)}))
summ_n = nba[nba.find('class="chaos-summary"'):nba.find("</table>", nba.find('class="chaos-summary"'))]
rows_n = re.findall(r'<tr data-lane="([^"]+)"(?: data-band="([^"]+)")?>', summ_n)
check("on the NBA page the lane leads the summary, its 10-30c row directly under it",
      rows_n, [("nba_ml_dog_tp50", ""), ("nba_ml_dog_tp50", "ask_10_30")])
text_n = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", nba))
check("the lane row reads split before hold; the sub-band row says it is the same entries",
      ("NBA moneyline underdog · split 2x / 3x 6 0 6 6 3" in text_n, "· ask 10-30c, same entries 3 · 3 3 1" in text_n), (True, True))
card_n = nba[nba.find('data-lane="nba_ml_dog_tp50" open'):]
split_tbl = card_n[card_n.find('class="chaos-split"'):card_n.find("</table>", card_n.find('class="chaos-split"'))]
check("its card: split v hold first, the 10-30c row under the 1h row, then the other exits",
      (re.findall(r'<tr(?: data-band="([^"]+)")?><td>', split_tbl), card_n.find("Split v hold") < card_n.find("Other exits")),
      (["", "ask_10_30"], True))
check("the Sandbox index keeps one row for the lane, under its new label",
      re.findall(r'<tr data-lane="nba_ml_dog_tp50"[^>]*><td><b>([^<]+)</b>',
                 CB.section(dict(lanes={"nba_ml_dog_tp50": copy.deepcopy(old_L)}))),
      ["NBA moneyline underdog · split 2x / 3x"])
check("public copy passes the guard", sandbox_audit.COPY_RE.search(text_n), None)

print("\nthe outcome unit is the event, not the rung (2026-10-29)")
# A rung-heavy lane (as nba_tt_cheap_tp30 was): 6 rungs on each of 2 games, every exit on the same entries.
rungs = dict(id="t_rungs", label="Rungs", entry_hours=[1], exits=["hold", "tp30", C.SPLIT], trades=[])
for g in range(2):
    for k in range(6):
        for ex, roi in (("hold", -1.0), ("tp30", 0.3), (C.SPLIT, 0.5)):
            rungs["trades"].append(dict(event=f"KXNBATEAMTOTAL-26OCT2{5 + g}G", ticker=f"R{g}{k}", side="yes", hours=1,
                                        exit_key=ex, variant=C.vkey(1, ex), entry=0.2, entry_ts=T0 + 60 * (6 * g + k),
                                        roi=roi, profit=roi * 0.2, cost=0.2, won=roi > 0, night=f"2026-10-2{5 + g}",
                                        reason="split" if ex == C.SPLIT else "settled", spread=0.02))
rh = CB.split_hold(rungs)
check("12 entries on 2 games: 12 settled entries, 2 settled events", (rh["entries"], rh["settled"], rh["events"]), (12, 12, 2))
tbl = C.lane_table(rungs)
check("12 trades on 2 events is still too early for review: the flag counts events",
      (tbl[C.vkey(1, "tp30")]["lane"]["n"], tbl[C.vkey(1, "tp30")]["lane"]["events"], tbl[C.vkey(1, "tp30")]["flag"]), (12, 2, "too early"))
rtxt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", CB.summary([rungs])))
check("the summary row shows entries, settled entries and settled events; its status counts events",
      "Rungs 12 0 12 2 0 +50.0% −100.0% 0 / 0 2 settled events · review at 10, decide at 30" in rtxt.replace("-100.0%", "−100.0%"), True)
card = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", CB.lane_html(dict(rungs, replayed={"a": 1, "b": 1, "c": 1}, since="2026-10-25"))))
check("the card header: events replayed, entries, settled events entered; review counted in settled events",
      ("3 events replayed · 12 entries · 2 settled events entered" in card, "Review at 10 settled events, decide at 30" in card), (True, True))
check("the index row: entries, then settled events", "Rungs — 12 2 0 +50.0%" in re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", CB.index([rungs]))), True)

print("\nentry validity on replayed entries (2026-10-30)")


def row(k, bid, ask, vol=0.0, lo=None, hi=None, close=None):
    return dict(ts=T0 + 60 * k, bid=bid, ask=ask, bid_lo=bid, bid_hi=bid, ask_lo=ask, ask_hi=ask, px_lo=lo, px_hi=hi,
                px_close=close, vol=vol)


rows = [row(0, 0.18, 0.20, 3, close=0.21), row(1, 0.18, 0.20, 6, lo=0.20), row(30, 0.19, 0.21, 5, lo=0.19),
        row(61, 0.15, 0.17, 50, lo=0.15), row(20, 0.20, 0.22, 9, lo=0.21)]
rows = sorted(rows, key=lambda r: r["ts"])
ok_ = C.entry_check(rows, "yes", 0, T0 - 60)
check("verified by 11 contracts traded at or through the 0.20 ask within 60 minutes (a 0.21 low and minute 61 do not count)",
      (ok_["status"], ok_["how"], ok_["printed"], ok_["source"], ok_["first_quotes"]), ("verified", "print", 11.0, "replayed", True))
thin = [row(0, 0.03, 0.04, 0), row(10, 0.03, 0.04, 0, lo=0.08)]
check("a 4c ask nothing traded through is unverified", C.entry_check(thin, "yes", 0)["reason"],
      "0 contracts traded at or through the ask within 60 minutes (under 10)")
check("an ask under half the last trade is unverified", C.entry_check([row(0, 0.03, 0.04, 2, close=0.30), row(5, 0.03, 0.04, 40, lo=0.04)], "yes", 1)["reason"],
      "ask 0.04 under half the last trade 0.30")
check("the NO side: NO ask 1 - YES bid, printed through when the YES traded high reaches 1 - the ask",
      C.entry_check([row(0, 0.80, 0.82, 0), row(5, 0.80, 0.82, 12, hi=0.81)], "no", 0)["status"], "verified")
check("normalise keeps the minute's volume and traded close", (C.normalise(dict(end_period_ts=T0, yes_bid=dict(close_dollars="0.1"),
      yes_ask=dict(close_dollars="0.12"), price=dict(close_dollars="0.11"), volume_fp="7"))["vol"],
      C.dense([dict(end_period_ts=T0, yes_bid=dict(close_dollars="0.1"), yes_ask=dict(close_dollars="0.12"), volume_fp="7")], T0, T0 + 60)[1]["vol"]),
      (7.0, 0.0))
# A lane recorded before the rule: 2 entries on 2 events, the second never traded through its ask.
old_L = dict(id="t_old", entry_hours=[1], exits=["hold", C.SPLIT], trades=[], replayed={"E1": 1, "E2": 1}, since="2026-10-25")
for ev, roi in (("KXNBAGAME-26OCT25AAABBB", 1.5), ("KXNBAGAME-26OCT26CCCDDD", 2.0)):
    for ex in ("hold", C.SPLIT):
        old_L["trades"].append(dict(event=ev, ticker=ev + "-AAA", side="yes", hours=1, exit_key=ex, variant=C.vkey(1, ex),
                                    entry=0.2, entry_ts=T0, roi=roi, profit=roi * 0.2, cost=0.2, won=True,
                                    night=ev[10:12], reason="split" if ex == C.SPLIT else "settled", spread=0.02))
verdict = {"KXNBAGAME-26OCT25AAABBB": dict(status="verified", how="print", printed=40, source="replayed"),
           "KXNBAGAME-26OCT26CCCDDD": dict(status="unverified", printed=0, source="replayed", reason="0 contracts traded at or "
                                           "through the ask within 60 minutes (under 10)")}
_re = C.replay_event
C.replay_event = lambda ln, series, event, fetch, now=None: ([dict(ticker=event + "-AAA", side="yes", hours=1, ask=verdict[event])], None)
try:
    errs = []
    C._ask_backfill(old_L, dict(id="t_old", series=["KXNBAGAME"]), C.dt.datetime(2026, 10, 30, tzinfo=C.UTC), None, errs)
finally:
    C.replay_event = _re
check("the backfill adds each entry's ask check to its trades; nothing else on a trade changes",
      ([t["ask"]["status"] for t in old_L["trades"]], errs, sorted(old_L["trades"][0])),
      (["verified", "verified", "unverified", "unverified"], [],
       sorted(["ask", "cost", "entry", "entry_ts", "event", "exit_key", "hours", "night", "profit", "reason", "roi",
               "side", "spread", "ticker", "variant", "won"])))
check("the figure before the rule is kept as voided; the record restarts on the verified entry",
      ((old_L["voided"]["entries"], old_L["voided"]["events"], round(old_L["voided"]["split"], 2)),
       (CB.split_hold(old_L)["entries"], CB.split_hold(old_L)["events"]), CB.unverified(old_L)),
      ((2, 2, 1.75), (1, 1), (1, 0)))
otxt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", CB.lane_html(dict(old_L, label="Old"))))
check("the card: the voided line, the unverified count and the ask check on each trade",
      ("Voided 2026-10-30: the earlier figure (2 entries on 2 events, split +175.0%, hold +175.0%)" in otxt,
       "Skipped: unverified ask: 1." in otxt, "unverified, not counted: 0 contracts traded" in otxt, "verified · print, 40" in otxt),
      (True, True, True, True))
srow = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", CB.summary([dict(old_L, label="Old")])))
check("the summary row: entries 1, unverified asks 1, settled entries 1, settled events 1", "Old 1 1 1 1 1 +150.0% +150.0%" in srow, True)
check("the Other-exits flags read the verified entries only", C.lane_table(old_L)[C.vkey(1, "hold")]["lane"]["n"], 1)
check("a lane with every trade checked asks for nothing more",
      sorted({t["event"] for t in old_L["trades"] if "ask" not in t}), [])
check("public copy passes the guard", sandbox_audit.COPY_RE.search(otxt + srow), None)

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
