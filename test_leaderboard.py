#!/usr/bin/env python3
"""The Leaderboard (leaderboard.py, leaderboard_build.py): entity mapping, verified-only counting, shrinkage, the
minimum sample, the persistence calculation, and the page's rules (nav, no inline style or SVG, guarded copy)."""
import re
import sys

import leaderboard as L
import leaderboard_build as LB
import sandbox_audit
import site_chrome

FAILS = []


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


def trade(ticker, key, ask="verified", roi=0.5, f2=False, f3=False, night="2026-10-26", event=None, hours=1):
    return dict(ticker=ticker, side="yes", hours=hours, exit_key=key, event=event or ticker.rsplit("-", 1)[0], night=night,
                roi=roi, ask=dict(status=ask), filled_2x=f2, filled_3x=f3)


def chaos_with(*pairs):
    trades = []
    for hold, split in pairs:
        trades += [hold, split]
    return dict(lanes={"nba_ml_dog_tp50": dict(trades=trades)})


print("entity mapping")
sk = {}
cs = L.collect_chaos(chaos_with((trade("KXNBAGAME-26OCT26PHXOKC-PHX", "hold", roi=-1.0),
                                  trade("KXNBAGAME-26OCT26PHXOKC-PHX", "split", roi=0.4, f2=True, f3=False))), sk)
check("a moneyline ticker belongs to its team", [(c["sport"], c["entities"], c["market"]) for c in cs],
      [("NBA", ["Phoenix Suns"], "Moneyline underdog")])
check("reached 2x / 3x and both ROIs come from the split and hold rows",
      (cs[0]["reach2"], cs[0]["reach3"], cs[0]["split"], cs[0]["hold"]), (True, False, 0.4, -1.0))
check("team code from a team-total or spread suffix", (L.team_code("DET120"), L.team_code("WAS11"), L.team_code("UTA")),
      ("DET", "WAS", "UTA"))
check("an unknown code keeps its code", L.nba_name("XYZ"), "XYZ")
check("a ledger series maps to its asset or speaker",
      [L.ledger_entity(dict(event=e), "series") for e in ("KXWTI-26OCT2714", "KXAAAGASD-26OCT27", "KXTRUMPSAY-26NOV02", "KXOTHER-1")],
      ["WTI", "AAA gas", "Trump", None])
check("a fight lane's fighter is the market's word", L.ledger_entity(dict(event="KXUFCFIGHT-26OCT31BEKPET", word="Pat Pet"), "word"), "Pat Pet")

names = {"26OCT28VENINT": ("Venezia", "Internazionale")}
o35 = dict(entries=[dict(id="KXSERIEATOTAL-26OCT28VENINT-4", event="KXSERIEATOTAL-26OCT28VENINT", night="2026-10-28", result="no",
                         bids={"10": dict(fill_at=5, dead=False, limit=0.1, payout=1.0,
                                          sells={"2": dict(filled=True, thin=False, target=0.2, volume=300.0),
                                                 "3": dict(filled=False, thin=False, target=0.3, volume=0)})}),
                  dict(id="KXSERIEATOTAL-26OCT28XXXYYY-4", event="KXSERIEATOTAL-26OCT28XXXYYY", night="2026-10-28", result="no",
                       bids={"10": dict(fill_at=5, dead=False, limit=0.1, payout=1.0, sells={})}),
                  dict(id="KXSERIEATOTAL-26OCT28DEADAA-4", event="KXSERIEATOTAL-26OCT28DEADAA", night="2026-10-28", result="yes",
                       bids={"10": dict(fill_at=5, dead=True, limit=0.1, payout=0.0, sells={})}),
                  dict(id="KXSERIEATOTAL-26OCT28NOFILL-4", event="KXSERIEATOTAL-26OCT28NOFILL", night="2026-10-28", result="yes",
                       bids={"10": dict(fill_at=None)})])
sk, un = {}, {}
cs = L.collect_o35(o35, names, sk, un)
check("over 3.5 credits both teams and is a match contract", [(c["entities"], c["kind"], c["reach2"], c["reach3"]) for c in cs],
      [(["Venezia", "Internazionale"], "match", True, False)])
check("a fixture with no team names is reported, not guessed", un, {"o35_cheap_no (fixture has no team names)": 1})
check("a dead fill is counted out; a bid that never filled is not a contract", sk, {"dead fill": 1})

print("verified-only counting")
sk = {}
cs = L.collect_chaos(chaos_with(
    (trade("KXNBAGAME-26OCT26AAABBB-AAA", "hold", ask="unverified"), trade("KXNBAGAME-26OCT26AAABBB-AAA", "split", ask="unverified")),
    (trade("KXNBAGAME-26OCT26CCCDDD-CCC", "hold"), trade("KXNBAGAME-26OCT26CCCDDD-CCC", "split"))), sk)
check("a chaos entry with an unverified ask is left out", [c["entities"] for c in cs], [["CCC"]])
check("and counted as skipped", sk, {"unverified ask": 1})
check("a hold row with no split row yet is not guessed at", L.collect_chaos(chaos_with((trade("KXNBAGAME-26OCT26AAABBB-AAA", "hold"),
      trade("KXNBAGAME-26OCT26AAABBB-AAA", "hold", night="2026-10-26"))), {}), [])
check("the same contract seen by two lanes counts once",
      len(L.collect_chaos(dict(lanes={
          "nba_ml_dog_tp50": dict(trades=[trade("KXNBAGAME-26OCT26PHXOKC-PHX", "hold"), trade("KXNBAGAME-26OCT26PHXOKC-PHX", "split")]),
          "challenger_dog_tp30": dict(trades=[trade("KXNBAGAME-26OCT26PHXOKC-PHX", "hold"), trade("KXNBAGAME-26OCT26PHXOKC-PHX", "split")])}), {})), 1)

row_ok = dict(id="KXNBAWINMARGIN-26OCT28WASCLE-WAS11TO20", event="KXNBAWINMARGIN-26OCT28WASCLE", eligible=True, ask=0.10, team="WAS",
              night="2026-10-28", won=False, m=dict(reach2=True, reach3=False, vol2=40.0), path=[[-1800, 10, 12], [60, 20, 5]])
check("tracker print test: 10+ contracts at or under the ask in the hour before the tip", L.tracker_ask_ok(row_ok), True)
check("a thin hour fails the test", L.tracker_ask_ok(dict(row_ok, path=[[-1800, 10, 4]])), False)
check("prints above the ask or after the tip do not count", L.tracker_ask_ok(dict(row_ok, path=[[-1800, 20, 50], [60, 10, 50]])), False)
check("a cleared path is not checkable, a stamped row keeps its answer",
      (L.tracker_ask_ok(dict(row_ok, path=[])), L.tracker_ask_ok(dict(row_ok, path=[], ask_ok=True))), (None, True))
tracker = dict(rows=[row_ok, dict(row_ok, id="X-1", path=[]), dict(row_ok, id="X-2", path=[[-1800, 10, 4]])], spread_rows=[])
sk = {}
cs = L.collect_tracker(tracker, {}, sk)
check("tracker rows: verified in, thin and unchecked out", [c["uid"][0] for c in cs], [row_ok["id"]])
check("the unchecked and unverified are counted", sk, {"tracker: ask not checkable (path cleared)": 1, "unverified ask": 1})
check("a tracker row takes the chaos lane's check when its own path is gone",
      len(L.collect_tracker(dict(rows=[dict(row_ok, path=[])], spread_rows=[]),
                            dict(lanes={"nba_winmargin_split_insample": dict(trades=[trade(row_ok["id"], "hold")])}), {})), 1)
check("a tracker row's split ROI uses the fee formulas (reached 2x, not 3x, lost)", cs[0]["split"] is not None and cs[0]["hold"] < -0.9, True)
spread = dict(row_ok, id="KXNBASPREAD-26OCT28WASCLE-WAS11", comeback=True)
cs = L.collect_tracker(dict(rows=[], spread_rows=[spread]), {}, {})
check("a Comeback spread belongs to its team and its own market", [(c["entities"], c["market"]) for c in cs],
      [(["Washington Wizards"], "Comeback spread")])

ledger = dict(ask_rule_since="x", entries=[
    dict(id="KXWTI-A", event="KXWTI-26OCT2714", side="yes", entry_at="2026-10-26T01:00:00+00:00", payout=1.0, roi=1.2, roi_held=2.0,
         ask_check=dict(status="verified"), legs=[dict(multiple=2.0, filled_at="t"), dict(multiple=3.0)]),
    dict(id="KXWTI-B", event="KXWTI-26OCT2714", side="yes", entry_at="2026-10-26T01:00:00+00:00", payout=0.0, roi=-1, roi_held=-1,
         ask_check=dict(status="unverified"), legs=[]),
    dict(id="KXWTI-C", event="KXWTI-26OCT2714", side="yes", entry_at="2026-10-26T01:00:00+00:00", payout=None, status="open",
         ask_check=dict(status="verified"), legs=[])])
sk, un = {}, {}
cs = L.collect_ledgers(sk, un, lambda name: ledger if name == "wti_cheap_yes_ledger.json" else {})
check("a cheap-side ledger counts verified settled entries only", [(c["entities"], c["reach2"], c["reach3"], c["split"]) for c in cs],
      [(["WTI"], True, False, 1.2)])
check("its unverified entry is skipped and open entry waits", sk, {"unverified ask": 1})

print("shrinkage")
a = L.shrunk_score(3, 3, 0.5)
b = L.shrunk_score(30, 50, 0.5)
check("3-for-3 scores below 30-for-50 at a 50% market", a < b, True)
check("zero contracts shrink to the market average", L.shrunk_score(0, 0, 0.6), 0.6 - 0.5)
check("a large sample moves toward its own rate", round(L.shrunk_score(900, 1000, 0.5), 3), round((900 + 10) / 1020 - 0.5, 3))


def contracts_for(name, wins, n, events, sport="NBA", market="Spreads", day0="2026-10-20", step=1):
    out = []
    for i in range(n):
        d = f"2026-10-{20 + (i % events) * step:02d}"
        out.append(L.contract((f"{name}-{i}", "yes"), sport, market, f"{name}-E{i % events}", d, [name], reach2=i < wins, reach3=False,
                              split=0.1, hold=-0.1))
    return out


print("minimum sample and ranking")
cs = (contracts_for("Three", 3, 3, 3) + contracts_for("Big", 40, 50, 12) + contracts_for("Few events", 14, 20, 4)
      + contracts_for("Exactly", 9, 15, 5))
b = L.board(cs)
check("3 for 3 cannot rank (under the minimum)", "Three" in [s["name"] for s in b["watching"]], True)
check("20 contracts in 4 events is still watching (needs 5 events)", "Few events" in [s["name"] for s in b["watching"]], True)
check("15 contracts across 5 events ranks", "Exactly" in [s["name"] for s in b["ranked"]], True)
check("the best shrunk score tops the board", [s["name"] for s in b["ranked"]][0], "Big")
check("with 10 or fewer ranked there is no separate bottom list", b["bottom"], [])
many = [c for i in range(16) for c in contracts_for(f"M{i:02d}", i % 16, 20, 6)]
bm = L.board(many)
check("with more than ten ranked the bottom 5 are the worst, worst first",
      [s["name"] for s in bm["bottom"]], [s["name"] for s in reversed(bm["ranked"])][:5])
check("and none of them is in the top 10", set(s["name"] for s in bm["bottom"]) & set(s["name"] for s in bm["top"]), set())
check("the market average comes from the pooled contracts", round(b["means"][("NBA", "Spreads")], 4), round((3 + 40 + 14 + 9) / (3 + 50 + 20 + 15), 4))

print("holds up")
rows = contracts_for("H", 8, 12, 6)                     # alternate days: older events and newer events
old, new, ok = L.holds_up([dict(c, reach2=True) for c in rows])
check("both halves beating fair is marked", (old, new, ok), (1.0, 1.0, True))
old, new, ok = L.holds_up([dict(c, reach2=(c["day"] < "2026-10-23")) for c in rows])
check("an older half that beat fair and a newer half that did not is not", (old, new, ok), (1.0, 0.0, False))
check("a half with too few contracts is not judged", L.holds_up(contracts_for("T", 2, 4, 2))[2], None)

print("persistence")


def week_contracts(day, hits):
    """One contract each for entities named by `hits` {name: reached 2x} on `day`, three times each."""
    out = []
    for name, hit in hits.items():
        for i in range(L.WEEK_MIN):
            out.append(L.contract((f"{name}-{day}-{i}", "yes"), "NBA", "Spreads", f"{name}-{day}-{i}", day, [name], reach2=hit))
    return out


names8 = [f"N{i}" for i in range(8)]
w1 = week_contracts("2026-10-20", {n: i >= 4 for i, n in enumerate(names8)})        # N4..N7 reached 2x in week 1
w2_persist = week_contracts("2026-10-27", {n: i >= 4 for i, n in enumerate(names8)})
p = L.persistence(w1 + w2_persist)
check("a hot group that stays hot beats the bottom quarter", (p["tested"], p["beats"]), (1, 1))
w2_flip = week_contracts("2026-10-27", {n: i < 4 for i, n in enumerate(names8)})
p = L.persistence(w1 + w2_flip)
check("a hot group that goes cold loses to the bottom quarter", (p["tested"], p["beats"]), (1, 0))
check("one week alone has nothing to test", L.persistence(w1)["tested"], 0)
check("too few entities in a week is not tested", L.persistence(week_contracts("2026-10-20", {"A": True, "B": False})
                                                                + week_contracts("2026-10-27", {"A": True, "B": False}))["tested"], 0)
check("a skipped calendar week is not compared", L.persistence(w1 + week_contracts("2026-11-10", {n: i >= 4 for i, n in enumerate(names8)}))["tested"], 0)
check("the record is never called proven on one week", L.persistence(w1 + w2_persist)["proven"], False)
check("Spearman: perfect, inverse and ties", (round(L.spearman([1, 2, 3, 4], [1, 2, 3, 4]), 6), round(L.spearman([1, 2, 3, 4], [4, 3, 2, 1]), 6),
                                              L.spearman([1, 1, 1], [1, 2, 3])), (1.0, -1.0, None))

print("page")
b = L.board(cs)
html = LB.build(cs, {"unverified ask": 3}, {"x": 1})
check("Leaderboard is in the main nav, once", len(re.findall(r'<a href="\./leaderboard\.html"', html)), 1)
check("the page marks itself current", 'aria-current="page">Leaderboard' in html, True)
check("registered with its file name", site_chrome.PAGE_FILES["leaderboard"], "leaderboard.html")
check("no inline style, SVG or inline script", (len(re.findall(r"\sstyle=", html)), len(re.findall("<svg", html)),
                                                 len(re.findall(r"<script(?![^>]*\ssrc=)", html))), (0, 0, 0))
text = re.sub(r"<[^>]+>", " ", html)
check("no guarded public phrase", sandbox_audit.COPY_RE.findall(text), [])
check("the persistence verdict comes before the board", html.index('id="persistence"') < html.index('id="top"'), True)
check("it says plainly it is not proven while the test is not positive", "Not proven" in html, True)
check("every sport has its own table", all(f'id="sport-{s.lower()}"' in html for s in L.SPORTS), True)
check("table cells are labelled for the phone cards", 'data-l="Reached 2x"' in html, True)
check("an empty board still builds", "Nothing ranks yet" in LB.build([], {}, {}), True)

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
