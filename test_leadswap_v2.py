#!/usr/bin/env python3
"""test_leadswap_v2.py — Lead Swap favourite v2 (lsb-v2) and the 2026-11-12 retirements (sw15cuts round 3).

lsb-v2 is lsb-v1's favourite on Bitcoin, WTI and NEAR only, as a FRESH record from the cut; lsb-v1 and the Loss Reader stop entering at the
same instant; the three markets are frozen and fingerprinted; v1's headline is its FULL record (cut markets counted back in).
"""
import datetime as dt
import re
import sys

import leadswap as L
import leadswap_v2 as V2
import lossreader as LR
import sandbox_audit
import sw15cuts as C
import swing15 as W
import swing15_build as WB

FAILS = []


def check(why, got, want):
    good = got == want
    print(f"  {'ok  ' if good else 'FAIL'} {why}" + ("" if good else f" — got {got!r}, want {want!r}"))
    if not good:
        FAILS.append(why)


print("frozen and registered")
check("the market list is the three, fingerprinted", (V2.MARKETS, V2.fingerprint() == V2.MARKETS_SHA256), (("KXBTC15M", "KXNEAR15M", "KXWTI15M"), True))
check("round 3 is frozen too", (C.fingerprint3() == C.ROUND3_SHA256, C.RETIRED3), (True, ("lossreader",)))
check("one instant, on a window boundary: v2's FROM, the cut, v1's favourite retirement",
      (V2.FROM == C.CUT3_AT, W._ts(C.CUT3_AT) % 900, L.TRADES_RETIRED["leadswap_fav"] == C.CUT3_AT, L.TRADES_RETIRED["leadswap_fav_ctrl"] == C.CUT3_AT),
      (True, 0, True, True))
check("the swing trade's earlier retirement is unchanged", L.TRADES_RETIRED["leadswap_swing"], C.CUT2_AT)
check("review at 30, decide at 100", (V2.REVIEW_AT, V2.DECIDE_AT), (30, 100))
check("the loss reader retires at the cut; a kept rule has none", (C.retire_at("lossreader"), C.retire_at("sp500_fav5")), (C.CUT3_AT, None))

print("\nrouting: three markets only, no backfill, a fresh record, a control")
F0 = W._ts(V2.FROM)
xw = lambda s, o, won=1.0: dict(series=s, open=dt.datetime.fromtimestamp(o, dt.timezone.utc).isoformat(), group="Crypto", fee_multiplier=1.0,
                                s1={"0.35": dict(won=1.0, trigger=dict(ts=o + 60))}, s3=dict(status="filled", won=won, price=0.8, roi=0.2 if won else -1.0))
mk = lambda s, o, won=1.0: (s, "Crypto", o, o + 900, {}, xw(s, o, won))
key = lambda h: dt.datetime.fromtimestamp(h - h % 3600, dt.timezone.utc).isoformat()
hours = [F0 - 3600, F0, F0 + 3600]
rows = [mk(s, h) for h in hours for s in ("KXBTC15M", "KXWTI15M", "KXNEAR15M", "KXETH15M", "KXSOL15M")]
picks = {key(h): dict(top=["KXSOL15M", "KXBTC15M"], bottom=["KXETH15M", "KXBTC15M", "KXNEAR15M"], at=key(h)) for h in hours}
r = V2.routing(rows, picks)
check("a pick on Ethereum is skipped, and its slot is not given to another market (no backfill)",
      sorted(r["leadswap_v2"]["series"]), ["KXBTC15M", "KXNEAR15M"])
check("a window before FROM counts for nothing: two hours, two markets, two bets each", {m: v[0] for m, v in r["leadswap_v2"]["series"].items()},
      {"KXBTC15M": 2, "KXNEAR15M": 2})
check("the control is the same markets when they are in the top 3 (Bitcoin only here)", {m: v[0] for m, v in r["leadswap_v2_ctrl"]["series"].items()},
      {"KXBTC15M": 2})
check("a cell carries n, wins, return and clusters, as v1's", sorted(r["leadswap_v2"]) == sorted(
      ["n", "hits", "hit_rate", "fair", "mean_roi", "z", "clusters", "before_freeze", "series"]), True)
check("before FROM nothing is recorded", V2.routing([mk("KXBTC15M", F0 - 3600)], {key(F0 - 3600): dict(top=[], bottom=["KXBTC15M"], at=key(F0))})["leadswap_v2"], None)
v1 = L.routing(rows, picks)
check("v1 enters no favourite from the cut: Bitcoin's only entry is the window BEFORE it, and the control none from it either",
      ({m: v[0] for m, v in v1["leadswap_fav"]["series"].items()}.get("KXBTC15M"), "KXBTC15M" in (v1["leadswap_fav_ctrl"] or {"series": {}})["series"]),
      (1, True))

print("\nv1 closes with its FULL record")
rt = dict(leadswap_fav=dict(n=250, hits=222, mean_roi=0.058658, fair=0.836256))
rem = dict(leadswap_fav=dict(n=164, hits=126, mean_roi=-0.1073256, fair=0.8427134))
f = L.full_record(rt, rem)
check("kept + cut: 414 bets, 348 won, −0.7% after fees", (f["n"], f["hits"], round(f["mean_roi"] * 100, 1)), (414, 348, -0.7))
check("the two parts are kept apart for the note", (f["kept"]["n"], f["cut"]["n"]), (250, 164))
check("no record, no line", L.full_record({}, {}), None)

print("\nthe Loss Reader stops at the cut")
CUT = int(W._ts(C.CUT3_AT))
sw = lambda o: dict(series="KXSOL15M", open=dt.datetime.fromtimestamp(o, dt.timezone.utc).isoformat(), s2=dict(status="filled", won=1.0, price=0.6, roi=0.6))
opens = [CUT - 900 * k for k in range(12, 0, -1)] + [CUT + 900 * k for k in range(0, 12)]
led = LR.ledger(dict(windows={str(o): sw(o) for o in opens}), dt.datetime.fromtimestamp(CUT + 7200, dt.timezone.utc))
ts = [b["t"] for b in led["bets"]]
check("bets are made before the cut, none from it", (len(ts) > 0, max(ts) < CUT), (True, True))
check("the record and the comparison books are frozen at the cut too", (led["record"]["n"], led["every"]["n"], led["retired_at"]), (len(ts), 12, C.CUT3_AT))

print("\nthe page")
html = WB.section(W.load())
live = html.split('id="sw15-archive"')[0]
check("B is the version-2 row, Too early until 30, with the honest why", ("sw15-leadswap_v2" in live, "B · Lead Swap favourite v2 (Bitcoin, WTI, NEAR)" in live,
      "Why these three, honestly" in live, "not evidence for version 2" in live, "Too early (" in live), (True, True, True, True, True))
check("the in-sample table is there with the three markets' numbers", all(x in live for x in ("+7.1%", "+10.1%", "+14.5%", "−10.5%", "−14.6%", "−9.4%")), True)
check("the Loss Reader and lsb-v1's favourite are out of the live area", ("Loss Reader" in live, 'id="sw15-leadswap_fav"' in live), (False, False))
arc = html.split('id="sw15-archive"')[1]
check("the Retired Nov 12 block holds both, each on one line with a final record", ("<h4>Retired Nov 12</h4>" in arc, "Loss Reader" in arc.split("<h4>Retired Nov 12</h4>")[1][:1800],
      "full record" in arc.split("<h4>Retired Nov 12</h4>")[1][:2200]), (True, True, True))
r3 = arc.split("<h4>Retired Nov 12</h4>")[1].split("</details>")[0]
check("and says the kept markets alone were flattered by cutting losers", "flattered by cutting losers" in r3, True)
check("plain copy: no dollar amount, no guarded phrase, no inline style", (re.search(r"\$\d", html), sandbox_audit.COPY_RE.findall(html), "style=" in html), (None, [], False))
doc = open("docs/prereg_leadswap_v2_2026-11-12.md").read()
check("the pre-registration exists and says why in-sample, the full v1 record and the fingerprint rule",
      ("in-sample" in doc, "414 bets, 348 won, −0.7%" in doc, "MARKETS_SHA256" in doc, "no further cuts" in doc.lower()), (True, True, True, True))
check("the workflow runs the new test and the new ledger step, and saves its ledger",
      all(x in open(".github/workflows/swing15.yml").read() for x in ("test_leadswap_v2.py", "python3 leadswap_v2.py", "data/leadswap_v2_ledger.json")), True)

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
