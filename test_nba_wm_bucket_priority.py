#!/usr/bin/env python3
"""NBA win margin Bucket Priority bp-v2 (nba_wm_bucket_priority.py, frozen 2026-11-09): ceded rows come from the executor's decision records
(outcome "ceded"), are counted and never graded, for both lanes; non-ceded rows grade as before; the pages carry the note and the counts;
old data with no ceded decision renders without it."""
import datetime as dt
import sys

import nba_page as NP
import nba_wm_bucket_priority as CP
import nba_wm_nofade as N
import nba_wm_production as X
import nba_wm_v3 as V3
import nba_wm_v4 as V4
import nba_wm_v4prod as V
import production as P
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
TIP = int(dt.datetime(2026, 11, 10, 0, 0, tzinfo=UTC).timestamp())
EV = "KXNBAWINMARGIN-26NOV09BOSMIA"

print("the frozen table and the bucket labels")
check("the id and version", (CP.BP_ID, CP.BP_VERSION), ("wm_bucket_priority", "bp-v2"))
check("the table", CP.PRIORITY, {"1-5": "yes", "6-10": "no", "11-20": "yes"})
check("tickers map to the ledger labels", [CP.bucket_label(EV + s) for s in ("-BOS1TO5", "-MIA6TO10", "-BOS11TO20", "-MIA21PLUS")], ["1-5", "6-10", "11-20", "21+"])
check("21+ has no priority entry", CP.winner("21+"), None)

print("\nceded decisions leave the replay and are counted")


def dec(lane, ticker, outcome, version, **kw):
    d = dict(lane=lane, bot_version=version, ticker=ticker, event=EV, bucket=ticker.rsplit("-", 1)[-1], tip=iso(TIP), decided_at=iso(TIP - 3500),
             outcome=outcome, why=None, rule_ok=True, yes_bid=0.12, yes_ask=0.14, spread=0.02)
    d.update(kw)
    return d


Y_OK, Y_CEDED, N_OK, N_CEDED = EV + "-BOS6TO10", EV + "-BOS1TO5", EV + "-MIA1TO5", EV + "-MIA6TO10"
DEC = {"yes:" + Y_OK: dec("nba_winmargin_live", Y_OK, "enter", "wm-yes-v4", fav_share=0.5, kept=True, kept_why="NO could not fill (ask check: 0 contracts offered at or under 0.88 (under 10))", bucket_priority="bp-v2"),
       "yes:" + Y_CEDED: dec("nba_winmargin_live", Y_CEDED, "ceded", "wm-yes-v4", fav_share=0.5, ceded_to="wm-nofade-v4",
                             why="ceded to wm-nofade-v4 (Bucket Priority bp-v2, 6-10)"),
       "no:" + N_OK: dec("nba_wm_nofade", N_OK, "plan", "wm-nofade-v4", P=0.40, limit=0.26),
       "no:" + N_CEDED: dec("nba_wm_nofade", N_CEDED, "ceded", "wm-nofade-v4", P=0.40, limit=0.26, ceded_to="wm-yes-v4",
                            why="ceded to wm-yes-v4 (Bucket Priority bp-v2, 1-5)")}
check("the ceded set comes from the decision records, as (lane, ticker)", CP.ceded_set(DEC), {("nba_winmargin_live", Y_CEDED), ("nba_wm_nofade", N_CEDED)})


def prints(path):
    return dict(trades=[dict(created_time=iso(TIP + 100), yes_price_dollars="0.80", no_price_dollars="0.20", count_fp="40", trade_id="b"),
                        dict(created_time=iso(TIP + 400), yes_price_dollars="0.55", no_price_dollars="0.45", count_fp="5", trade_id="c")])


real = V3.C.event_markets
V3.C.event_markets = lambda ev, f: ([dict(ticker=k.split(":", 1)[1], result="no", status="finalized") for k in DEC], False)
try:
    s4 = V.load("/nonexistent")
    V.run(s4, DEC, NOW, lambda p: prints(p))
finally:
    V3.C.event_markets = real
check("only the two non-ceded decisions are rows (graded as before)", sorted(s4["rows"]), sorted(["yes:" + Y_OK, "no:" + N_OK]))
check("the NO row still bids the decision's own limit", s4["rows"]["no:" + N_OK]["limit"], 0.26)
check("both ceded decisions are filed, with lane, bucket and the winner", sorted((r["lane"], r["bucket"], r["ceded_to"]) for r in s4["ceded"].values()),
      sorted([("nba_winmargin_live", "1-5", "wm-nofade-v4"), ("nba_wm_nofade", "6-10", "wm-yes-v4")]))
check("filed ceded rows carry the Bucket Priority version", sorted({r["bucket_priority"] for r in s4["ceded"].values()}), ["bp-v2"])
check("bp-v2: a kept decision stays a graded row and is counted under state kept", (("yes:" + Y_OK) in s4["rows"], sorted(s4["kept"]), CP.kept_count(s4)), (True, ["yes:" + Y_OK], 1))
check("bp-v2: a kept record carries the reason and the version", (s4["kept"]["yes:" + Y_OK]["kept_why"].startswith("NO could not fill"), s4["kept"]["yes:" + Y_OK]["bucket_priority"]), (True, "bp-v2"))
check("bp-v2: the transient outcome 'kept' also counts as kept", CP.is_kept({"outcome": "kept"}), True)
check("a ceded row is in no lane's record", ([r["ticker"] for r in V.yes_rows(s4)], [g["event"] for g in V.no_games(s4)]), ([Y_OK], [EV]))
quotes = X.v4_quotes(s4)
check("the Production quotes carry only the graded rows", sorted(q["market_id"] for q in quotes), sorted([Y_OK, N_OK]))
check("the per-lane ceded counts", CP.counts(s4), {CP.YES_LANE: 1, CP.NO_LANE: 1})
check("a ceded decision arriving alone changes no graded row and is not re-filed twice", (len(s4["rows"]), len(V.run(s4, DEC, NOW, lambda p: prints(p))["ceded"])), (2, 2))

print("\nthe first night is not set by a ceded decision, and old data has no ceded field")
only = {k: v for k, v in DEC.items() if v["outcome"] == "ceded"}
s_only = V.run(V.load("/nonexistent"), only, NOW, lambda p: prints(p))
check("ceded-only decisions leave no rows and no first night", (s_only["rows"], s_only["since"]), ({}, None))
check("a state without the field counts zero", CP.counts({}, {"rows": {}}), {CP.YES_LANE: 0, CP.NO_LANE: 0})

print("\nthe pages")
CHAOS = dict(lanes={})
nofade = N.load("/nonexistent")
d, st_, b_ = {"quotes": []}, {"pairs": {}}, {"leads": {}, "pairs": {}}
s3 = V3.load("/nonexistent")
_, rules, _r = NP.rules_section(CHAOS, nofade, s3, {}, NOW, v4p=s4, v3p=V4.load("/nonexistent", V4.RULE_V3))
check("the NBA page carries the table, the status, the review rule and both counts",
      ("Bucket Priority bp-v2." in rules, "1-5 YES, 6-10 NO, 11-20 YES" in rules, "Tentative, in-sample, set 2026-11-09" in rules, "20+ NO fills and 30+ YES entries" in rules,
       "YES split: 1 ceded to the other lane, not graded." in rules, "NO fade: 1 ceded to the other lane, not graded." in rules and "kept by YES because NO could not fill (bp-v2): 1" in rules), (True,) * 6)
check("on the NBA page the note is on both lane panels", rules.count("Bucket Priority bp-v2."), 2)
html = P.page(d, st_, b_, "", now=NOW, nba_wm=dict(chaos=CHAOS, nofade={"entries": []}, v3=s3, v4=s4))
check("the Production page carries it once, under the NBA win margin block", (html.count("Bucket Priority bp-v2."), "YES split: 1 ceded" in html), (1, True))
check("no guarded public phrase, no inline style in the note", (sandbox_audit.COPY_RE.search(CP.note_html(s4)), "style=" in CP.note_html(s4)), (None, False))
old = V.load("/nonexistent")
_, rules0, _r = NP.rules_section(CHAOS, nofade, s3, {}, NOW, v4p=old, v3p=V4.load("/nonexistent", V4.RULE_V3))
html0 = P.page(d, st_, b_, "", now=NOW, nba_wm=dict(chaos=CHAOS, nofade={"entries": []}, v3=s3, v4=old))
check("old data (no v4 night, nothing ceded) renders without the note", ("Bucket Priority bp-v2." in rules0, "Bucket Priority bp-v2." in html0), (False, False))

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
