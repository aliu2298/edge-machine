#!/usr/bin/env python3
"""The NBA win margin lanes in Production (nba_wm_production, 2026-11-03): the feeds the follower reads, the pairs on the Production page
and the Control Center, the record (paper version 2), and that a page build never changes a feed."""
import datetime as dt
import json
import os
import sys
import tempfile

import chaos_replay as C
import nba_wm_nofade as N
import nba_wm_production as X
import production as P
import sandbox_audit

FAILS = []
UTC = dt.timezone.utc
NOW = dt.datetime(2026, 11, 4, 12, 0, tzinfo=UTC)


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


def ts(h):
    return int((NOW + dt.timedelta(hours=h)).timestamp())


EV1, EV2 = "KXNBAWINMARGIN-26NOV03OKCCLE", "KXNBAWINMARGIN-26NOV03DENLAL"


def trade(ev, tick, roi, side_won, night="2026-11-03", exit_key="split", h=-20):
    return dict(event=ev, ticker=f"{ev}-{tick}", side="yes", hours=1, exit_key=exit_key, variant=f"t1h_{exit_key}", night=night, entry=0.15, spread=0.03,
                entry_ts=ts(h - 1), start_ts=ts(h), cost=0.16, profit=round(roi * 0.16, 4), roi=roi, won=roi > 0, reason="split", side_won=side_won)


CHAOS = dict(lanes={X.YES_LANE: dict(id=X.YES_LANE, since="2026-11-03", exits=["hold", "split"], trades=[
    trade(EV1, "OKC1TO5", 1.33, True), trade(EV1, "OKC1TO5", -1.0, True, exit_key="hold"),
    trade(EV1, "CLE6TO10", -1.0, False), trade(EV2, "DEN1TO5", 0.4, True, night="2026-11-03"),
    trade("KXNBAWINMARGIN-26NOV01AAABBB", "AAA1TO5", 1.0, True, night="2026-11-01")])})        # before Production: not in the record


def bucket(tick, fill, ok=True, no_wins=True):
    return dict(id=f"{EV1}-{tick}", bucket="1-5", team=tick[:3], P=0.40, spread=0.02, ask=dict(status="verified" if ok else "unverified"), no_wins=no_wins,
                fills={"d75": fill, "d85": None, "d65": None})


FILL = dict(limit=0.30, fill_at=ts(-19), fill_print=0.28, printed=14.0, sold_at=ts(-18), cost=0.3037, profit=0.0963, won=True, reason="sold")
NOFADE = dict(entries=[
    dict(event=EV1, night="2026-11-03", tip=ts(-20), insample=False, buckets=[bucket("OKC1TO5", FILL), bucket("CLE6TO10", dict(FILL, sold_at=None, profit=-0.3037, won=False)),
                                                                           bucket("OKC11TO20", FILL, ok=False)]),
    dict(event=EV2, night="2026-11-01", tip=ts(-40), insample=False, buckets=[bucket("DEN1TO5", FILL)]),        # version 1: not the record
])
FEED_YES = dict(lane=X.YES_LANE, updated_at=(NOW - dt.timedelta(minutes=30)).isoformat(), leads=[
    dict(id="x", lane=X.YES_LANE, event="KXNBAWINMARGIN-26NOV04BOSMIA", ticker="KXNBAWINMARGIN-26NOV04BOSMIA-BOS1TO5", tip=(NOW + dt.timedelta(hours=6)).isoformat(), side="yes")])
FEED_NO = dict(FEED_YES, lane=X.NO_LANE, leads=[dict(FEED_YES["leads"][0], lane=X.NO_LANE, side="no")])

_tmp = tempfile.mkdtemp(prefix="nbawm-page-")
X.YES_PATH, X.NO_PATH = os.path.join(_tmp, "yes.json"), os.path.join(_tmp, "no.json")
assert _tmp in X.YES_PATH

print("the feeds")
games = lambda path: None
EVENTS = dict(events=[dict(event_ticker="KXNBAWINMARGIN-26NOV04BOSMIA", markets=[
    dict(ticker="KXNBAWINMARGIN-26NOV04BOSMIA-BOS1TO5", yes_sub_title="Boston wins by 1-5 points", status="active", result=""),
    dict(ticker="KXNBAWINMARGIN-26NOV04BOSMIA-BOS11TO20", yes_sub_title="Boston wins by 11-20 points", status="active", result=""),
    dict(ticker="KXNBAWINMARGIN-26NOV04BOSMIA-MIA6TO10", yes_sub_title="Miami wins by 6-10 points", status="active", result="no")]),
    dict(event_ticker="KXNBAWINMARGIN-26NOV09FARAWAY", markets=[dict(ticker="x", yes_sub_title="A wins by 1-5 points", status="active", result="")])])


def fake(path):
    if path.startswith("events?"):
        return EVENTS
    if "event_ticker=KXNBAGAME-26NOV04BOSMIA" in path:
        return dict(markets=[dict(ticker="KXNBAGAME-26NOV04BOSMIA-BOS", expected_expiration_time=(NOW + dt.timedelta(hours=9)).isoformat().replace("+00:00", "Z"))])
    if "event_ticker=KXNBAGAME-26NOV09FARAWAY" in path:
        return dict(markets=[dict(ticker="y", expected_expiration_time=(NOW + dt.timedelta(days=5)).isoformat().replace("+00:00", "Z"))])
    raise AssertionError(path)


yes, no = X.feeds(NOW, fake)
check("a game inside the window lists its OPEN buckets; the YES feed the 1-5, 6-10 and 11-20 ones (version 4; the settled are out), the NO feed every open one",
      ([l["ticker"].rsplit("-", 1)[1] for l in yes["leads"]], [l["ticker"].rsplit("-", 1)[1] for l in no["leads"]]), (["BOS1TO5", "BOS11TO20"], ["BOS1TO5", "BOS11TO20"]))
check("a game days away is not listed", all("FARAWAY" not in l["event"] for l in yes["leads"] + no["leads"]), True)
check("tip = the KXNBAGAME expiry minus 3 hours", yes["leads"][0]["tip"], (NOW + dt.timedelta(hours=6)).isoformat())
check("the rule is in the header: YES 10-20c, spread 5c, sells 2x/2.5x from the tip, favourite share under 0.70; NO 65% dip, pregame sell, post-only",
      (yes["rule"]["band"], yes["rule"]["max_spread"], [s["multiple"] for s in yes["rule"]["sells"]], yes["rule"]["sells_from"],
       no["rule"]["dip"], no["rule"]["sell"], no["rule"]["post_only"], yes["rule"]["max_favourite_share"]), ([0.1, 0.2], 0.05, [2.0, 2.5], "tip", 0.65, "pregame", True, 0.70))
check("the lead carries lane, version, side and the stake", (yes["leads"][0]["lane"], yes["leads"][0]["version"], yes["leads"][0]["side"], yes["leads"][0]["stake_usd"]),
      (X.YES_LANE, X.YES_VERSION, "yes", 1.0))

print("\nthe record: paper version 2, from the first night")
yq, nq = X.yes_quotes(CHAOS), X.no_quotes(NOFADE)
check("YES: the split entries from 2026-11-02 on (the hold control and the earlier night are out)", sorted(q["market_id"].rsplit("-", 1)[1] for q in yq), ["CLE6TO10", "DEN1TO5", "OKC1TO5"])
check("NO: the verified fills of version 2 (the unverified bucket and version 1 are out)", sorted(q["market_id"].rsplit("-", 1)[1] for q in nq), ["CLE6TO10", "OKC1TO5"])
check("a quote books the lane's own after-fee P/L", {q["market_id"].rsplit("-", 1)[1]: q["pnl"] for q in yq}, {"OKC1TO5": 133.0, "CLE6TO10": -100.0, "DEN1TO5": 40.0})
check("quotes are Kalshi binary contracts on the NBA win margin domain", {(q["venue"], q["sport"], q["pick"]) for q in yq + nq}, {("kalshi_binary", "nba_wm", "a"), ("kalshi_binary", "nba_wm", "b")})

print("\nthe Production page")
d, st, blob = {"quotes": []}, {"pairs": {}}, {"leads": {}, "pairs": {}}
json.dump(FEED_YES, open(X.YES_PATH, "w"))
json.dump(FEED_NO, open(X.NO_PATH, "w"))
html = P.page(d, st, blob, "", now=NOW, nba_wm=dict(chaos=CHAOS, nofade=NOFADE))
check("the page lists both lanes by name", (X.YES_NAME in html, X.NO_NAME in html), (True, True))
check("without the ledgers they are not listed", (X.YES_NAME in P.page(d, st, blob, "", now=NOW)), False)
check("no guarded public phrase, no dollar amount in the lane rows", sandbox_audit.COPY_RE.search(html.split(X.YES_NAME, 1)[-1][:4000]), None)
d2, st2, blob2 = X.page_inputs(d, st, blob, CHAOS, NOFADE, now=NOW)
check("the originals are untouched", (d, st, blob), ({"quotes": []}, {"pairs": {}}, {"leads": {}, "pairs": {}}))
check("both pairs are in Production since the first night", ({k: v["stage"] for k, v in st2["pairs"].items()}, X.MOVED_ON),
      ({f"{X.YES_LANE}|nba_wm": "production", f"{X.NO_LANE}|nba_wm": "production"}, "2026-11-02"))
pend = [l for l in blob2["leads"].values() if l.get("status") == "pending"]
check("one upcoming lead per lane while the feeds are fresh", sorted(l["route"]["outcome_side"] for l in pend), ["no", "yes"])
_, _, b3 = X.page_inputs(d, st, blob, CHAOS, NOFADE, now=NOW + dt.timedelta(hours=6))
check("a stale feed lists no upcoming lead", [l for l in b3["leads"].values() if l.get("status") == "pending"], [])

print("\nthe Control Center agrees")
import control_center as CC
m0 = CC.model(d, st, blob, NOW)
m1 = CC.model(d, st, blob, NOW, nba_wm=dict(chaos=CHAOS, nofade=NOFADE))
check("the pairs tile counts both lanes and the Production list names them",
      (m1["tiles"]["pairs"] - m0["tiles"]["pairs"], X.YES_NAME in m1["prod_outside"], X.NO_NAME in m1["prod_outside"]), (2, True, True))

print("\nthe follower's feeds are not changed by a page build (byte for byte)")
before = (open(X.YES_PATH, "rb").read(), open(X.NO_PATH, "rb").read())
P.page(d, st, blob, "", now=NOW, nba_wm=dict(chaos=CHAOS, nofade=NOFADE))
CC.page(NOW, d=d, st=st, blob=blob, nba_wm=dict(chaos=CHAOS, nofade=NOFADE))
after = (open(X.YES_PATH, "rb").read(), open(X.NO_PATH, "rb").read())
check("the YES and NO feed files are identical before and after", before == after, True)
f1, f2 = X.feeds(NOW, fake), X.feeds(NOW, fake)
X.page_inputs(d, st, blob, CHAOS, NOFADE, now=NOW)
check("rebuilding the feeds after a page build gives the same feeds", json.dumps(f1, sort_keys=True) == json.dumps(X.feeds(NOW, fake), sort_keys=True), True)

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
