#!/usr/bin/env python3
"""Offline checks that Over 3.5 cheap NO (live) shows on the Production page with its record and upcoming leads
(o35_production.page_inputs, 2026-11-01), and that adding it cannot change what the follower reads."""
import datetime as dt
import json
import os
import sys
import tempfile

import o35_cheap_no as O
import o35_production as X
import production as P
import sandbox_audit

FAILS = []
UTC = dt.timezone.utc
NOW = dt.datetime(2026, 11, 2, 12, 0, tzinfo=UTC)


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


def kick(h):
    return int((NOW + dt.timedelta(hours=h)).timestamp())


def bid(sold, result, fill_h):
    sells = {str(m): dict(target=round(0.1 * m, 2), volume=80.0, filled=sold and m <= 4, thin=False, at=None) for m in O.MULTS}
    return dict(limit=0.10, fill_at=kick(fill_h), fill_print=0.08, dead=False, sells=sells, payout=1.0 if result == "no" else 0.0)


def entry(ev, h, version, bids, result, night="2026-11-01"):
    return dict(id=ev + "-4", event=ev, league="Turkish Super Lig", series="KXSUPERLIGTOTAL", kickoff=kick(h), night=night, result=result,
                form_rule=False, prints=9, bids=bids, version=version)


LEDGER = dict(lane=O.LANE, version=O.VERSION, since=O.SINCE, entries=[
    entry("KXSUPERLIGTOTAL-26NOV01KASBES", -30, O.VERSION, {"10": bid(True, "yes", -29), "10e": None}, "yes"),     # sold at 4x
    entry("KXSUPERLIGTOTAL-26NOV01AAABBB", -28, O.VERSION, {"10": bid(False, "no", -27), "10e": None}, "no"),      # held, NO wins
    entry("KXSUPERLIGTOTAL-26NOV01CCCDDD", -26, O.VERSION, {"10": bid(False, "yes", -25), "10e": None}, "yes"),    # held, loses
    entry("KXSUPERLIGTOTAL-26NOV01EEEFFF", -24, O.VERSION, {"10": None, "10e": None}, "no"),                       # never filled
    entry("KXSUPERLIGTOTAL-26NOV01GGGHHH", -22, O.V2, {"10": bid(True, "yes", -21)}, "yes"),                       # v2 rule: not this record
    entry("KXSUPERLIGTOTAL-26OCT31III", -48, O.VERSION, {"10": bid(True, "yes", -47)}, "yes", night="2026-10-31"),  # before Production
])
FEED = dict(lane=O.LANE, updated_at=(NOW - dt.timedelta(minutes=30)).isoformat(), leads=[
    dict(id="x", lane=O.LANE, league="Premier League", event="KXEPLTOTAL-26NOV03ARSCHE", ticker="KXEPLTOTAL-26NOV03ARSCHE-4",
         title="Arsenal v Chelsea", kickoff=(NOW + dt.timedelta(hours=5)).isoformat(), side="no", bid=0.1, sell=0.4, stake_usd=1.0)])

# page() reads the lead feed from X.PATH: point it at a temp copy of the fixture, never the real file
_tmp = tempfile.mkdtemp(prefix="o35-page-")
X.PATH = os.path.join(_tmp, "production_o35_leads.json")
assert _tmp in X.PATH
X.ENDED_ON = None      # the Production adapter is tested as it ran while the lane traded (it is a no-op once ENDED_ON is set, below)
print("quotes")
qs = X.quotes(LEDGER, FEED)
check("filled v3 bids from Production day on, plus the upcoming lead; unfilled, v2 and pre-Production entries are out",
      sorted(q["market_id"] for q in qs),
      ["KXEPLTOTAL-26NOV03ARSCHE-4", "KXSUPERLIGTOTAL-26NOV01AAABBB-4", "KXSUPERLIGTOTAL-26NOV01CCCDDD-4", "KXSUPERLIGTOTAL-26NOV01KASBES-4"])
by = {q["market_id"].split("-")[1] + q["market_id"].split("-")[2][5:]: q for q in qs}
sold = next(q for q in qs if q["market_id"].endswith("KASBES-4"))
check("a 4x sell is a win on paper even though the over hit", (sold["status"], sold["result"], sold["rule"]), ("won", "a", "sold at 4x"))
check("a held bid wins on a NO result and loses on a YES", ([q["status"] for q in qs if q["market_id"].endswith(s)] for s in ("AAABBB-4", "CCCDDD-4")) is not None
      and [next(q["status"] for q in qs if q["market_id"].endswith(s)) for s in ("AAABBB-4", "CCCDDD-4")], ["won", "lost"])
check("every quote is the lane's NO at 10c", {(q["source"], q["sport"], q["pick"], q["price"]) for q in qs}, {(O.LANE, X.SPORT, "b", 0.1)})

print("\nthe Production page")
d, st, blob = {"quotes": []}, {"pairs": {}}, {"leads": {}, "pairs": {}}
json.dump(FEED, open(X.PATH, "w"))
html = P.page(d, st, blob, "", now=NOW, o35=LEDGER)
check("the page lists the lane by name", X.NAME in html, True)
check("without the ledger it is not listed", X.NAME in P.page(d, st, blob, "", now=NOW), False)
check("the page shows the lane's record (3 settled) and an upcoming match",
      ("3 settled" in html, "Arsenal" in html, "Nothing is scheduled" in html), (True, True, False))
check("no guarded public phrase, no dollar amount or order id in the page's lane rows",
      (sandbox_audit.COPY_RE.search(html.split(X.NAME, 1)[-1][:3000]) is None), True)
d2, st2, blob2 = X.page_inputs(d, st, blob, LEDGER, now=NOW, leads_feed=FEED)
check("the originals are untouched", (d, st, blob), ({"quotes": []}, {"pairs": {}}, {"leads": {}, "pairs": {}}))
check("the pair is in Production since its move date", (st2["pairs"][f"{O.LANE}|{X.SPORT}"]["stage"], X.MOVED_ON), ("production", "2026-11-01"))
check("one upcoming lead on the page's blob", [l["route"]["market"] for l in blob2["leads"].values() if l.get("status") == "pending"],
      ["KXEPLTOTAL-26NOV03ARSCHE-4"])
stale = dict(FEED, updated_at=(NOW - dt.timedelta(hours=6)).isoformat())
check("a stale lead feed lists no upcoming lead", [q["status"] for q in X.quotes(LEDGER, stale) if q["status"] == "open"], ["open"])
_, _, b3 = X.page_inputs(d, st, blob, LEDGER, now=NOW, leads_feed=stale)
check("... on the page's blob", [l for l in b3["leads"].values() if l.get("status") == "pending"], [])

X.ENDED_ON = "2026-11-06"
d9, st9, b9 = X.page_inputs(d, st, blob, LEDGER, now=NOW, leads_feed=FEED)
check("after ENDED_ON the lane adds no Production pair, quote or upcoming lead", (d9, st9, b9), (d, st, blob))
check("... and the Production page no longer lists it", X.NAME in P.page(d, st, blob, "", now=NOW, o35=LEDGER), False)
X.ENDED_ON = None

print("\nthe record equals the lane's own 10c_4x figure")
import sandbox_track as T
fx = [e for e in LEDGER["entries"] if e["version"] == O.VERSION and e["night"] >= X.MOVED_ON and (e["bids"].get("10"))]
want = O.trade_rows(fx)
want = sum(r["roi"] for r in want if r["variant"] == "10c_4x") / sum(1 for r in want if r["variant"] == "10c_4x")
got = P.build_feed({"quotes": [q for q in X.quotes(LEDGER, {}) if q["status"] != "open"]}, {"pairs": X.pairs()}, now=NOW)["pairs"][f"{O.LANE}|{X.SPORT}"]
check("three fills (one 4x sale, one held No win, one held loss): the pair's after-fee ROI is trade_rows' 10c_4x mean",
      (got["sandbox_n"], round(got["sandbox_roi_fee"], 2)), (3, round(want, 2)))
sold_q = next(q for q in X.quotes(LEDGER, {}) if q["market_id"].endswith("KASBES-4"))
check("... the 4x sale books its sale (+~290%), not a 10c win paid at settlement (+~884%)", 250 < sold_q["pnl"] < 330, True)
rec = T.assess({"quotes": X.quotes(LEDGER, {})}, O.LANE, X.SPORT, since=None, venues=T.TRADEABLE_VENUES)
check("the page's whole-record ROI after fees agrees", round(rec["roi_fee"], 2), round(want, 2))

print("\nthe Control Center agrees with the Production page")
import control_center as CC
m0 = CC.model(d, st, blob, NOW)
m1 = CC.model(d, st, blob, NOW, o35=LEDGER)
check("the pairs tile counts the lane once it is on the page, and the Production list names it",
      (m1["tiles"]["pairs"] - m0["tiles"]["pairs"], X.NAME in m1["prod_outside"], X.NAME in m0["prod_outside"]), (1, True, False))
check("the root shows the lane's name", X.NAME in CC.page(NOW, d=d, st=st, blob=blob, o35=LEDGER), True)

print("\nthe follower's feed is not changed by this")
before = json.dumps(X.feed(NOW, lambda p: {"events": [], "cursor": None}), sort_keys=True)
X.page_inputs(d, st, blob, LEDGER, now=NOW, leads_feed=FEED)
after = json.dumps(X.feed(NOW, lambda p: {"events": [], "cursor": None}), sort_keys=True)
check("o35 feed identical before and after a page build", before == after, True)

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
