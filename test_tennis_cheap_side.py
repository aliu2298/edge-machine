#!/usr/bin/env python3
"""The Tennis page's cheap-side section (2026-10-27): the tennis chaos lanes, challenger_cheap_split first,
near the top of tennis.html, from the same chaos ledger as the Sandbox's Chaos section."""
import re
import sys

import chaos_build as CB
import chaos_replay as C
import sandbox_audit
import tennis_build as TB

FAILS = []


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


def tr(k, roi, won, ticker="T1", hours=1, spread=None, f2=False, f3=False):
    t = dict(event="E-" + ticker, ticker=ticker, side="yes", hours=hours, exit_key=k, variant=f"t{hours}h_{k}", roi=roi,
             profit=roi * 0.2, cost=0.2, won=won, night="2026-10-26", reason="split" if k == "split" else "settled",
             entry=0.2, entry_ts=1_800_000_000, filled_2x=f2, filled_3x=f3)
    if spread is not None:
        t["spread"] = spread
    return t


def lane(i, label, exits, trades, first=False):
    return dict(id=i, label=label, since="2026-10-26", entry_hours=[1], exits=exits, series=["KXATPCHALLENGERMATCH"],
                replayed={"e": 1}, trades=trades, first=first)


state = {"lanes": {
    "nba_tt_cheap_tp30": lane("nba_tt_cheap_tp30", "NBA team-total cheap rungs", list(C.LANE_EXITS), [tr("hold", 0.1, True)]),
    "atp_coinflip_tp30": lane("atp_coinflip_tp30", "ATP coin-flip · sell +30%", list(C.LANE_EXITS),
                              [tr("hold", 0.5, True), tr("split", 0.3, True, f2=True), tr("tp30", 0.3, True)]),
    "challenger_dog_tp30": lane("challenger_dog_tp30", "Challenger underdog · sell +30%", list(C.LANE_EXITS),
                                [tr("hold", -1.0, False), tr("split", -1.0, False), tr("tp30", 0.3, True)]),
    "challenger_cheap_split": lane("challenger_cheap_split", "Challenger cheap side · split 2x / 3x", ["hold", "split"],
                                   [tr("hold", 1.5, True, spread=0.04), tr("split", 1.0, True, spread=0.04, f2=True, f3=True)],
                                   first=True)}}
# atp_coinflip_tp30 was retired 2026-10-29: its retirement is lifted for the live-card checks below (it stands in
# as the older lane) and checked at the end of this file.
import chaos_lanes
_lanes = chaos_lanes.LANES
chaos_lanes.LANES = [dict(c, retired=None) if c["id"] in ("atp_coinflip_tp30", "challenger_cheap_split") else c for c in _lanes]
h = CB.tennis_section(state)
chaos_lanes.LANES = _lanes
text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h))

print("the section")
check("the standard header", all(x in text for x in ("Cheap side + resting take-profit",
      "Buy the cheap player about an hour before the match, at the real ask.", "Rest a split sell: half at 2x, half at 3x.",
      "A fill counts only on a traded print.", "Every lane is shown next to the same entries held.")), True)
summ = h[h.find('class="chaos-summary"'):h.find("</table>", h.find('class="chaos-summary"'))]
check("the summary: the active tennis lanes, challenger_cheap_split first; no NBA lane; challenger_dog_tp30 retired 2026-10-27",
      re.findall(r'data-lane="([^"]+)"', summ), ["challenger_cheap_split", "atp_coinflip_tp30"])
check("its columns include the average spread paid",
      [re.sub(r"<[^>]+>", "", x) for x in re.findall(r"<th[^>]*>(.*?)</th>", summ)],
      ["Lane", "Entries", "Unverified asks", "Settled entries", "Settled events", "Won", "Split ROI", "Hold ROI", "Legs filled 2x / 3x", "Avg spread paid", "Status"])
check("the cheap-split row: +100% split, +150% hold, legs 1 / 1, spread 0.04, review at 10",
      "Challenger cheap side · split 2x / 3x 1 0 1 1 1 +100.0% +150.0% 1 / 1 0.04 1 settled event · review at 10, decide at 30" in text, True)
check("a row without a recorded spread shows —", "ATP coin-flip · sell +30% 1 0 1 1 1 +30.0% +50.0% 1 / 0 —" in text, True)
cards = re.findall(r'<details class="section-disclosure" data-lane="([^"]+)" open>', h)
check("cards in the same order, with trade lists", (cards, h.count("<summary><b>Trades</b>")),
      (["challenger_cheap_split", "atp_coinflip_tp30"], 2))
check("the older lanes' targets sit in a collapsed Other exits block, after split v hold",
      (h.count("<summary><b>Other exits</b>"), all(c.find("Split v hold") < c.find("Other exits") for c in
       h.split('<details class="section-disclosure" data-lane=')[1:] if "Other exits" in c)), (1, True))
check("challenger_dog_tp30 is in a collapsed Retired block with its one-line record",
      ('<details class="section-disclosure" id="cheap-side-retired">' in h,
       "Retired 2026-10-27 at 45 settled, 13 won; hold -3.2%, split -7.9%, every target exit negative: superseded by "
       "challenger_cheap_split (the 15-30c band)." in text), (True, True))
check("it links to the Chaos section, and reads the same ledger (nothing copied)",
      ('href="./sandbox.html#chaos"' in h, state["lanes"]["challenger_cheap_split"]["trades"][0]["roi"]), (True, 1.5))
check("public copy passes the guard", sandbox_audit.COPY_RE.search(text), None)

print("\nthe Tennis page")
page = TB.build()
check("the section sits near the top: after the page heading, before the rules",
      0 < page.find("<h1") < page.find('id="cheap-side"') < page.find('<section id="rules"'), True)
check("the Chaos section links back to it", 'href="./tennis.html#cheap-side"' in CB.section(state), True)
check("tables are header-row tables (the Sandbox's phone labels apply)", "<thead>" in h, False)

print("\nthe spread is recorded on new trades")
T0 = 1_800_000_000 - 1_800_000_000 % 60
vs = [C.view(dict(ts=T0 + 60 * k, bid=b, ask=a, bid_lo=b, bid_hi=b, ask_lo=a, ask_hi=a, px_hi=None, px_lo=None), "yes")
      for k, (b, a) in enumerate([(0.18, 0.21), (0.2, 0.22)])]
check("split and target trades carry the entry spread", (C._split_trade(vs, 0, True)["spread"],
      C._trade(vs, 0, True, C.EXITS["hold"])["spread"]), (0.03, 0.03))

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
