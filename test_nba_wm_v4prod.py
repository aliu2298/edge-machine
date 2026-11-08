#!/usr/bin/env python3
"""NBA win margin Production version 4 (nba_wm_v4prod.py, 2026-11-08): the replay takes decisions by the executor's bot_version, 2x / 2.5x
sells and the 65% bid; the pairs, the older-versions fold, the live-row windows; the version 3 paper comparison lanes."""
import datetime as dt
import sys

import chaos_replay as C
import nba_layout as NL
import nba_page as NP
import nba_wm_nofade as N
import nba_wm_production as X
import nba_wm_v3 as V3
import nba_wm_v4 as V4
import nba_wm_v4prod as V
import production as P
import production_live as PL
import sandbox_audit

FAILS = []
UTC = dt.timezone.utc
NOW = dt.datetime(2026, 11, 10, 12, tzinfo=UTC)


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


iso = lambda s: dt.datetime.fromtimestamp(s, UTC).isoformat()
TIP3 = int(dt.datetime(2026, 11, 8, 0, 0, tzinfo=UTC).timestamp())        # 7:00 PM ET on 2026-11-07 (a version 3 night)
TIP4 = int(dt.datetime(2026, 11, 9, 0, 0, tzinfo=UTC).timestamp())        # 7:00 PM ET on 2026-11-08 (the first version 4 night)
EV3, EV4 = "KXNBAWINMARGIN-26NOV07OKCCLE", "KXNBAWINMARGIN-26NOV08BOSMIA"

print("the 2x / 2.5x split and the sells it fills")
t = V3.yes_trade([(TIP4 + 60, 0.31, 5)], TIP4, 0.15, 0.0, V.SELLS)
check("a print through 2x (0.30) but under 2.5x (0.375) fills the first leg only; the second flag is filled_25x", (t["filled_2x"], t["filled_25x"], "filled_3x" in t), (True, False, False))
t3 = V3.yes_trade([(TIP4 + 60, 0.31, 5)], TIP4, 0.15, 0.0)
check("version 3's call is unchanged (2x / 3x, filled_3x)", (t3["filled_2x"], t3["filled_3x"], "filled_25x" in t3), (True, False, False))

print("\nthe run takes decisions by bot_version")


def dec(lane, ticker, outcome, ev, tip, version, **kw):
    d = dict(lane=lane, bot_version=version, ticker=ticker, event=ev, bucket=ticker.rsplit("-", 1)[-1], tip=iso(tip), decided_at=iso(tip - 3500),
             outcome=outcome, why=None, rule_ok=True, yes_bid=0.12, yes_ask=0.14, spread=0.02)
    d.update(kw)
    return d


Y3, N3 = EV3 + "-OKC1TO5", EV3 + "-CLE6TO10"
Y4, Y4b, N4 = EV4 + "-BOS11TO20", EV4 + "-MIA1TO5", EV4 + "-BOS6TO10"
DEC = {"yes:" + Y3: dec("nba_winmargin_live", Y3, "enter", EV3, TIP3, "wm-yes-v3"),
       "no:" + N3: dec("nba_wm_nofade", N3, "plan", EV3, TIP3, "wm-nofade-v3", P=0.40, limit=0.30),
       "yes:" + Y4: dec("nba_winmargin_live", Y4, "enter", EV4, TIP4, "wm-yes-v4", fav_share=0.58),
       "yes:" + Y4b: dec("nba_winmargin_live", Y4b, "enter", EV4, TIP4, "wm-yes-v4", fav_share=0.58),
       "no:" + N4: dec("nba_wm_nofade", N4, "plan", EV4, TIP4, "wm-nofade-v4", P=0.40, limit=0.26)}
legacy = dec("nba_winmargin_live", EV3 + "-OKC6TO10", "enter", EV3, TIP3, "wm-yes-v2")
legacy.pop("bot_version")
DEC["yes:legacy"] = legacy


def markets(ev):
    return [dict(ticker=k.split(":", 1)[1], result="no", status="finalized") for k, d in DEC.items() if d["event"] == ev and k != "yes:legacy"] + \
           [dict(ticker=legacy["ticker"], result="no", status="finalized")]


def trade_rows(path):
    if "BOS11TO20" in path:                                        # YES: through 2x (0.30), under 2.5x
        return dict(trades=[dict(created_time=iso(TIP4 + 60), yes_price_dollars="0.31", no_price_dollars="0.69", count_fp="20", trade_id="a")])
    if "BOS6TO10" in path:                                         # NO: 0.20 is strictly under the 0.26 limit (not under 0.75 x 0.40 = 0.30 alone), then 0.45 > P
        return dict(trades=[dict(created_time=iso(TIP4 + 100), yes_price_dollars="0.80", no_price_dollars="0.20", count_fp="40", trade_id="b"),
                            dict(created_time=iso(TIP4 + 400), yes_price_dollars="0.55", no_price_dollars="0.45", count_fp="5", trade_id="c")])
    return dict(trades=[dict(created_time=iso(TIP3 + 100), yes_price_dollars="0.75", no_price_dollars="0.25", count_fp="40", trade_id="d"),
                        dict(created_time=iso(TIP3 + 400), yes_price_dollars="0.55", no_price_dollars="0.45", count_fp="5", trade_id="e")])


real = V3.C.event_markets
V3.C.event_markets = lambda ev, f: (markets(ev), False)
try:
    s3 = V3.load("/nonexistent")
    V3.run(s3, DEC, NOW, lambda p: trade_rows(p))
    s4 = V.load("/nonexistent")
    V.run(s4, DEC, NOW, lambda p: trade_rows(p))
finally:
    V3.C.event_markets = real
check("version 3's ledger takes the v3 and the older/absent versions, never a v4 decision", sorted(s3["rows"]), sorted(["yes:" + Y3, "no:" + N3, "yes:legacy"]))
check("version 4's ledger takes only the v4 decisions", sorted(s4["rows"]), sorted(["yes:" + Y4, "yes:" + Y4b, "no:" + N4]))
check("each ledger's first night is its own (ET date of the tip)", (s3["since"], s4["since"], s4["version"]), ("2026-11-07", "2026-11-08", "v4"))
y = s4["rows"]["yes:" + Y4]
check("the v4 YES row: version, the 11-20 bucket counted, the 2x leg filled and not 2.5x, the favourite's share kept",
      (y["version"], y["filled_2x"], y["filled_25x"], y["fav_share"]), ("wm-yes-v4", True, False, 0.58))
n = s4["rows"]["no:" + N4]
check("the v4 NO row uses the decision's own limit (0.26 = 65% of 0.40): a 0.20 print fills it, 0.45 sells it back",
      (n["limit"], n["reason"], n["version"]), (0.26, "sold", "wm-nofade-v4"))
check("version 3's NO row still bids 75% (0.30)", s3["rows"]["no:" + N3]["limit"], 0.3)
check("the Production quotes carry the v4 source ids", sorted((q["source"], q["pick"]) for q in X.v4_quotes(s4)), sorted([(X.YES4_LANE, "a")] * 2 + [(X.NO4_LANE, "b")]))
check("version 3's quotes stop at the night before version 4", [q["source"] for q in X.v3_quotes(s3, "2026-11-08")].count(X.YES3_LANE) >= 1, True)

print("\nthe Production pairs and the Older versions fold")
check("before the first v4 decision the pairs are v2 + v3 only and v3 is the live version", (sorted(X.pairs(s3, {"since": None})), X.current_version(s3, {"since": None})),
      (sorted(f"{l}|nba_wm" for l in (X.YES_LANE, X.NO_LANE, X.YES3_LANE, X.NO3_LANE)), "v3"))
check("once v4 has a first night its two pairs join, with their own start", (sorted(X.pairs(s3, s4)) == sorted(f"{l}|nba_wm" for l in (
    X.YES_LANE, X.NO_LANE, X.YES3_LANE, X.NO3_LANE, X.YES4_LANE, X.NO4_LANE)), X.pairs(s3, s4)[f"{X.YES4_LANE}|nba_wm"]["by_hand"], X.current_version(s3, s4)), (True, "2026-11-08", "v4"))
check("older pairs: v2's, and v3's too once v4 has started", (sorted(X.older_pairs(s3, {"since": None})), sorted(X.older_pairs(s3, s4))),
      (sorted(f"{l}|nba_wm" for l in (X.YES_LANE, X.NO_LANE)), sorted(f"{l}|nba_wm" for l in (X.YES_LANE, X.NO_LANE, X.YES3_LANE, X.NO3_LANE))))
check("the feeds' rule: buckets 1-5, 6-10, 11-20; sells 2 / 2.5; favourite share 0.70; dip 0.65", (X.YES_RULE["buckets"], [s["multiple"] for s in X.YES_RULE["sells"]],
      X.YES_RULE["max_favourite_share"], X.NO_RULE["dip"]), (["1-5", "6-10", "11-20"], [2.0, 2.5], 0.70, 0.65))
CHAOS = dict(lanes={})
d, st_, b_ = {"quotes": []}, {"pairs": {}}, {"leads": {}, "pairs": {}}
html = P.page(d, st_, b_, "", now=NOW, nba_wm=dict(chaos=CHAOS, nofade={"entries": []}, v3=s3, v4=s4))
older = html[html.find("Older versions"):]
check("the Production page names v4 live and v3 inside the Older versions fold", (X.YES4_NAME in html[:html.find("Older versions")], X.YES3_NAME in older, X.YES_NAME in older), (True, True, True))
html0 = P.page(d, st_, b_, "", now=NOW, nba_wm=dict(chaos=CHAOS, nofade={"entries": []}, v3=s3, v4=V.load("/nonexistent")))
check("before the first v4 decision the page shows no v4 pair", (X.YES4_NAME in html0, X.YES3_NAME in html0), (False, True))
check("no guarded public phrase", sandbox_audit.COPY_RE.search(html.split(X.YES4_NAME, 1)[-1][:6000]), None)

print("\nthe live rows are windowed by slate")
row = lambda tk, ko: dict(id=tk, ko=ko, side="yes", st="won", w=1.0, r=0.5, g=0.5, src="fills", legs="2x", hold_r=0.2)
LIVE = dict(lanes={"nba_wm_yes": [row("KXNBAWINMARGIN-26NOV03AAABBB-AAA1TO5", "2026-11-04T00:30"), row("KXNBAWINMARGIN-26NOV07OKCCLE-OKC1TO5", "2026-11-08T00:30"),
                                  row("KXNBAWINMARGIN-26NOV08BOSMIA-BOS1TO5", "2026-11-09T00:30")], "nba_wm_nofade": []})
win = lambda key: [r["id"][-7:] for r in PL.own_rows(LIVE, key, "2026-11-04", "2026-11-08")]
check("v2 is before the v3 start, v3 from it to the v4 start, v4 from its start", (win(f"{X.YES_LANE}|nba_wm"), win(f"{X.YES3_LANE}|nba_wm"), win(f"{X.YES4_LANE}|nba_wm")),
      (["AAA1TO5"], ["OKC1TO5"], ["BOS1TO5"]))
check("without a v4 start no row is v4 and v3 keeps every row from its start", (PL.own_rows(LIVE, f"{X.YES4_LANE}|nba_wm", "2026-11-04", None), len(PL.own_rows(LIVE, f"{X.YES3_LANE}|nba_wm", "2026-11-04", None))), ([], 2))
sm = PL.own_summary(PL.own_rows(LIVE, f"{X.YES4_LANE}|nba_wm", "2026-11-04", "2026-11-08"), third="2.5x")
check("the v4 legs line names the 2.5x leg", "2.5x" in PL.own_detail(sm), True)
import live_record_publish as LRP
check("the publisher orders the legs 2x then 2.5x", LRP._legs(["2.5x", "2x"]), "2x+2.5x")

print("\nthe NBA page: v4 live, v3 older, the comparison on paper in the Sandbox")
nofade = N.load("/nonexistent")
rows_ = NP.rows(CHAOS, nofade, s3, LIVE, None, s4, V4.load("/nonexistent", V4.RULE_V3))
check("the Production rows read the v4 pairs; the Sandbox rows are the v3 YES and 75% NO paper", [(r["name"], r["prod"], r.get("pair")) for r in rows_],
      [("nba_winmargin_live", True, f"{X.YES4_LANE}|nba_wm"), ("nba_wm_nofade", True, f"{X.NO4_LANE}|nba_wm"), ("nba_wm_yes_v3", False, None), ("nba_wm_nofade_75", False, None)])
head, rules, _r = NP.rules_section(CHAOS, nofade, s3, LIVE, NOW, v4p=s4, v3p=V4.load("/nonexistent", V4.RULE_V3))
check("the page has version 4's block, version 3 in Older versions, the switch note and the two comparison panels",
      ('id="wm-yes-v4"' in rules, 'id="wm-yes-v3"' in rules, 'id="wm-no-v4"' in rules, 'id="wm-no-v3"' in rules, "What changed." in rules, 'id="wm-yes-v3-paper"' in rules,
       'id="wm-no-75"' in rules, "Win margin · YES split (v4)" in rules), (True,) * 8)
check("no guarded phrase, no inline style", (sandbox_audit.COPY_RE.search(rules), "style=" in rules), (None, False))

print("\nthe version 3 paper comparison (the tracker's rows, version 3 terms)")
tr = lambda i, ev, b, ask, share, **k: dict(id=i, event=ev, night="2026-11-08", tip=1, team="BOS", bucket=b, ask=ask, spread=0.02, eligible=True, team_share=share,
                                           ask_ok=True, path=[[60, 31, 5]], won=False, **k)
rows = [tr("a", "E1", "1-5", 0.15, 0.55), tr("b", "E1", "11-20", 0.15, 0.45), tr("c", "E2", "6-10", 0.15, 0.80)]
ok, skips = V4.candidates(rows, "2026-11-08", V4.RULE_V3)
check("1-5 and 6-10 enter, 11-20 does not, and a lopsided game (0.80) is NOT skipped", sorted(r["id"] for r in ok), ["a", "c"])
ok4, sk4 = V4.candidates(rows, "2026-11-08", V4.RULE_V4)
check("the v4 rule on the same rows: 11-20 enters, the 0.80 game is skipped", (sorted(r["id"] for r in ok4), list(sk4)), (["a", "b"], ["c"]))
s = V4.run(V4.load("/nonexistent", V4.RULE_V3), dict(rows=rows), NOW, V4.RULE_V3)
r = s["rows"]["a"]
check("the paper row: its own lane and version, 2x filled (0.31 > 0.30), the 3x leg flag", (r["lane"], r["version"], r["filled_2x"], r["filled_3x"]), ("nba_wm_yes_v3", "wm-yes-v3-paper", True, False))
check("its fresh record starts on the switch night and has its own ledger", (s["since"], V4.RULE_V3["path"].endswith("nba_wm_v3paper.json")), ("2026-11-08", True))

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
