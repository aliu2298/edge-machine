#!/usr/bin/env python3
"""NBA win margin paper version 3 (nba_wm_v3.py): entries from the executor's decision snapshots, fills from prints; the publisher's
whitelist; the Production pairs with v2 kept apart."""
import datetime as dt
import json
import os
import subprocess
import sys
import tempfile

import chaos_replay as C
import nba_wm_nofade as N
import nba_wm_production as X
import nba_wm_publish as PUB
import nba_wm_v3 as V
import production as P
import sandbox_audit

FAILS = []
UTC = dt.timezone.utc
NOW = dt.datetime(2026, 11, 5, 12, tzinfo=UTC)


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


TIP = int(dt.datetime(2026, 11, 4, 0, 0, tzinfo=UTC).timestamp())        # 7:00 PM ET on 2026-11-03
iso = lambda s: dt.datetime.fromtimestamp(s, UTC).isoformat()

print("the YES split from a snapshot")
ask = 0.14                                       # targets 0.28 and 0.42
prints = [(TIP - 600, 0.60, 5), (TIP + 60, 0.28, 30), (TIP + 120, 0.29, 3)]
r = V.yes_trade(prints, TIP, ask, 0.0)
check("a print AT the target does not fill it; a print before the tip never does; 0.29 fills the 2x leg only",
      (r["filled_2x"], r["filled_3x"]), (True, False))
cost = C.cost(ask)
want = 0.5 * (0.28 - C.maker_fee(0.28)) + 0.5 * 0.0 - cost
check("profit: half sold at 0.28 less the maker fee, the other half settles at 0 (the bucket missed), less the ask and its taker fee",
      round(r["profit"], 5), round(want, 5))
r2 = V.yes_trade([(TIP + 60, 0.29, 3), (TIP + 90, 0.43, 3)], TIP, ask, 1.0)
check("both legs fill on strictly higher prints; the hold control is the same entry held", (r2["filled_2x"], r2["filled_3x"], r2["hold_roi"]), (True, True, round((1 - cost) / cost, 4)))
r3 = V.yes_trade([(TIP + 60, 0.28, 30)], TIP, ask, 1.0)
check("a print at the target leaves both legs to settle (a win pays 1)", (r3["filled_2x"], round(r3["profit"], 5)), (False, round(1 - cost, 5)))

print("\nthe run: only rule_ok decisions, once, after settlement")
EV = "KXNBAWINMARGIN-26NOV03OKCCLE"
YT, NT, YT2, NT2 = EV + "-OKC1TO5", EV + "-CLE6TO10", EV + "-CLE1TO5", EV + "-OKC6TO10"


def dec(lane, ticker, outcome, rule_ok=True, **kw):
    d = dict(lane=lane, bot_version="v", ticker=ticker, event=EV, bucket=ticker.rsplit("-", 1)[-1], slate="26NOV03", tip=iso(TIP), decided_at=iso(TIP - 3500),
             outcome=outcome, why=None, rule_ok=rule_ok, yes_bid=0.12, yes_ask=0.14, spread=0.02)
    d.update(kw)
    return d


DEC = {"yes:" + YT: dec("nba_winmargin_live", YT, "enter"),
       "yes:" + YT2: dec("nba_winmargin_live", YT2, "skip", rule_ok=False),
       "yes:" + NT2: dec("nba_winmargin_live", NT2, "would_enter"),
       "no:" + NT: dec("nba_wm_nofade", NT, "plan", P=0.40, limit=0.30, qty=3.0, depth=20.0),
       "no:" + YT: dec("nba_wm_nofade", YT, "bid_crossed", P=0.40, limit=0.30)}
MK = [dict(ticker=YT, result="no", status="finalized"), dict(ticker=NT, result="no", status="finalized"), dict(ticker=YT2, result="no", status="finalized")]


def trade_rows(path):
    if "KXNBAWINMARGIN-26NOV03OKCCLE-OKC1TO5" in path:
        return dict(trades=[dict(created_time=iso(TIP + 60), yes_price_dollars="0.30", no_price_dollars="0.70", count_fp="20", trade_id="a")])
    return dict(trades=[dict(created_time=iso(TIP + 100), yes_price_dollars="0.75", no_price_dollars="0.25", count_fp="40", trade_id="b"),
                        dict(created_time=iso(TIP + 400), yes_price_dollars="0.55", no_price_dollars="0.45", count_fp="5", trade_id="c")])


real_markets = V.C.event_markets
V.C.event_markets = lambda ev, f: (MK, False)
try:
    st = V.load("/nonexistent")
    V.run(st, DEC, NOW, lambda p: trade_rows(p))
finally:
    V.C.event_markets = real_markets
check("rule_ok False and would_enter are ignored; the bid_crossed NO is no entry", sorted(st["rows"]), ["no:" + NT, "no:" + YT, "yes:" + YT])
check("the first night is the first night a snapshot exists (ET date of the tip)", st["since"], "2026-11-03")
yr = st["rows"]["yes:" + YT]
check("the YES row: version, night, the snapshot's ask, and a settled-no entry whose 0.30 print filled the 2x leg", (yr["version"], yr["night"], yr["ask"], yr["filled_2x"]), ("wm-yes-v3", "2026-11-03", 0.14, True))
nr = st["rows"]["no:" + NT]
check("the NO row fills on a print strictly under 0.30 (0.25, 40 contracts) and sells back on a print strictly over 0.40 (0.45)",
      (nr.get("limit"), nr.get("reason"), nr.get("version")), (0.30, "sold", "wm-nofade-v3"))
check("a bid_crossed decision is recorded as no entry", (st["rows"]["no:" + YT]["no_entry"], st["rows"]["no:" + YT]["reason"]), (True, "bid_crossed"))
n_rows = len(st["rows"])
V.C.event_markets = lambda ev, f: (MK, False)
try:
    V.run(st, DEC, NOW, lambda p: trade_rows(p))
finally:
    V.C.event_markets = real_markets
check("a second run adds nothing", len(st["rows"]), n_rows)
V.C.event_markets = lambda ev, f: ([dict(ticker=YT, result="", status="active")], False)
try:
    st2 = V.load("/nonexistent"); V.run(st2, {"yes:" + YT: DEC["yes:" + YT]}, NOW, lambda p: trade_rows(p))
finally:
    V.C.event_markets = real_markets
check("an unsettled market waits", (len(st2["rows"]), st2["observations"]["waiting"]), (0, 1))
check("the NO games sum a game's filled buckets", [(g["fills"], g["sold"]) for g in V.no_games(st)], [(1, 1)])

print("\nthe publisher's whitelist")
good = {"updated_at": "x", "decisions": {k: v for k, v in DEC.items()}}
check("the executor's own decision fields are accepted", len(PUB.sanitise(good)["decisions"]), 5)
for label, bad in (("an order id field", {"order_id": "o1"}), ("a balance field", {"balance": 12.0}), ("a dollar sign in a reason", {"why": "short $4"}),
                   ("an id-like string", {"why": "123e4567-e89b-12d3-a456-426614174000"}), ("an unknown lane", {"lane": "other"})):
    b = json.loads(json.dumps(good)); b["decisions"]["yes:" + YT].update(bad)
    try:
        PUB.sanitise(b); got = "accepted"
    except PUB.Refused:
        got = "refused"
    check(f"{label}: refused", got, "refused")
tmp = tempfile.mkdtemp(prefix="nbawm-pub-")
src = os.path.join(tmp, "src.json"); out = os.path.join(tmp, "out.json")
json.dump(good, open(src, "w"))
PUB.SRC, PUB.OUT = src, out
check("publishing writes the file; refusing writes nothing", (PUB.main(), os.path.exists(out)), (0, True))
os.remove(out); b = json.loads(json.dumps(good)); b["decisions"]["yes:" + YT]["balance"] = 1; json.dump(b, open(src, "w"))
check("a refused snapshot exits 1 and writes nothing", (PUB.main(), os.path.exists(out)), (1, False))

print("\nthe Production pairs: v2 kept apart from v3")
CHAOS = dict(lanes={X.YES_LANE: dict(id=X.YES_LANE, since="2026-11-02", exits=["hold", "split"], trades=[
    dict(event=EV, ticker=YT, side="yes", hours=1, exit_key="split", variant="t1h_split", night="2026-11-02", entry=0.15, spread=0.03, entry_ts=TIP - 90000, start_ts=TIP - 86400,
         cost=0.16, profit=0.2, roi=1.2, won=True, reason="split", side_won=True),
    dict(event=EV, ticker=YT2, side="yes", hours=1, exit_key="split", variant="t1h_split", night="2026-11-03", entry=0.15, spread=0.03, entry_ts=TIP - 3600, start_ts=TIP,
         cost=0.16, profit=0.2, roi=1.2, won=True, reason="split", side_won=True)])})
check("before version 3 starts the pairs are v2 only", sorted(X.pairs()), sorted([f"{X.NO_LANE}|nba_wm", f"{X.YES_LANE}|nba_wm"]))
check("once it has a first night the v3 pairs join them, each under its own source id", sorted(X.pairs(st)), sorted([f"{l}|nba_wm" for l in (X.YES_LANE, X.NO_LANE, X.YES3_LANE, X.NO3_LANE)]))
check("v2's record stops at the night before v3 starts (the Nov 3 trade is not v2's)", [q["market_id"] for q in X.yes_quotes(CHAOS, st["since"])], [YT])
check("v3's quotes are the settled v3 entries under the v3 source ids", sorted((q["source"], q["pick"]) for q in X.v3_quotes(st)), sorted([(X.NO3_LANE, "b"), (X.YES3_LANE, "a")]))
d, s_, b_ = {"quotes": []}, {"pairs": {}}, {"leads": {}, "pairs": {}}
html = P.page(d, s_, b_, "", now=NOW, nba_wm=dict(chaos=CHAOS, nofade={"entries": []}, v3=st))
check("the Production page names v2 and v3 apart", (X.YES_NAME in html, X.YES3_NAME in html, X.NO3_NAME in html), (True, True, True))
check("the feeds carry the v4 versions the executor pins (from 2026-11-08)", (X.YES_VERSION, X.NO_VERSION), ("wm-yes-v4", "wm-nofade-v4"))
check("no guarded public phrase", sandbox_audit.COPY_RE.search(html.split(X.YES3_NAME, 1)[-1][:4000]), None)

print("\nthe NBA page")
import nba_layout as NL
h = NL.build(chaos=C.empty(), nofade=N.load("/nonexistent"), tracker=None, v3=st)
check("with v3 started: its block is the headline and v2 is its own labelled fold, on both cards",
      ('id="wm-yes-v3"' in h, 'id="wm-yes-v2"' in h, 'id="wm-no-v3"' in h, 'id="wm-no-v2"' in h, "Production, v3" in h), (True, True, True, True, True))
h0 = NL.build(chaos=C.empty(), nofade=N.load("/nonexistent"), tracker=None, v3={"since": None, "rows": {}})
check("before it starts the page is as it was (no v3 block)", ('id="wm-yes-v3"' in h0, 'id="wm-no-v3"' in h0), (False, False))
check("no guarded phrase in the v3 blocks", sandbox_audit.COPY_RE.search(h[h.find('id="wm-yes-v3"'):h.find('id="wm-yes-v3"') + 3000]), None)

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
