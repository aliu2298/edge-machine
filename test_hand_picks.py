#!/usr/bin/env python3
"""test_hand_picks.py — Hand picks · learning log (hand_picks.py, the Combo page section), 2026-11-21."""
import sys

import combo_build as B
import combo_lane as CL
import hand_picks as HP
import sandbox_audit

FAILS = []


def check(why, got, want):
    good = got == want
    print(f"  {'ok  ' if good else 'FAIL'} {why}" + ("" if good else f" — got {got!r}, want {want!r}"))
    if not good:
        FAILS.append(why)


def leg(t, side="yes", ask=0.8, market="1Q"):
    return dict(ticker=t, label=t, side=side, ask=ask, bid=ask - 0.02, market=market)


picks = [
    dict(id="a", placed_at="2026-11-21T20:00:00Z", kind="combo", legs=[leg("T1"), leg("T2", "no", 0.7)], combo_price=0.55, payout_multiple=1.82, counted=True, result="open"),
    dict(id="b", placed_at="2026-11-21T20:00:00Z", kind="combo", legs=[leg("T1"), leg("T3")], combo_price=0.62, payout_multiple=1.61, counted=True, result="open"),
    dict(id="c", placed_at="2026-11-20T20:00:00Z", kind="single", legs=[leg("T4", "yes", 0.5)], combo_price=0.5, payout_multiple=2.0, counted=False, result="open"),
    dict(id="d", placed_at="2026-11-21T21:00:00Z", kind="combo", legs=[leg("T1"), leg("T5")], combo_price=0.6, payout_multiple=1.67, counted=True, result="open"),
]
res = {"T1": "yes", "T2": "no", "T3": "no", "T4": "yes", "T5": None}
fetch = lambda path: {"market": dict(ticker=path.split("/")[-1], result=res[path.split("/")[-1]])}
CL.D.payout, _orig = (lambda m: {"yes": 1.0, "no": 0.0}.get(m["result"])), CL.D.payout
HP.D.payout = CL.D.payout
try:
    st = dict(picks=picks)
    errs = HP.settle(st, fetch)
finally:
    HP.D.payout = _orig
    CL.D.payout = _orig
by = {p["id"]: p for p in st["picks"]}
check("a combo lands only if every leg wins (a yes and a no both right)", by["a"]["result"], "won")
check("one losing leg loses the combo", by["b"]["result"], "lost")
check("a pick with a leg not yet final stays open", by["d"]["result"], "open")
check("the leg results are kept", (by["a"]["legs"][0]["value"], by["a"]["legs"][1]["value"], by["b"]["legs"][1]["value"]), (1.0, 1.0, 0.0))
check("a no side reads one minus the yes payout", HP.leg_value(leg("T2", "no"), fetch) if False else by["a"]["legs"][1]["value"], 1.0)
check("no errors", errs, [])
rec = HP.record(st)
check("counted picks only: 3 of 10, one landed, one lost, one open", (rec["n"], rec["landed"], rec["lost"], rec["open"], rec["context"]), (3, 1, 1, 1, 1))
check("land rate and return per pick on the settled two", (rec["land_rate"], round(rec["return"], 4)), (0.5, round(((1 / 0.55 - 1) + (-1.0)) / 2, 4)))
check("average payout multiple over counted picks", round(rec["avg_multiple"], 3), round((1.82 + 1.61 + 1.67) / 3, 3))
part = dict(picks=[dict(id="p", counted=True, legs=[leg("T1")], combo_price=0.5, kind="single", result="open")])
HP.D.payout = lambda m: 0.4
try:
    HP.settle(part, fetch)
finally:
    HP.D.payout = _orig
check("a part-value leg counts at its settled value", (part["picks"][0]["result"], part["picks"][0]["value"]), ("no_result", 0.4))
check("an empty file is an empty record", HP.record(dict(picks=[]))["n"], 0)

three = dict(id="x", kind="combo", legs=[leg("T1"), leg("T2"), leg("T3")], combo_price=0.4, payout_multiple=2.5, counted=True, result="open")
check("a 3-leg combo is never counted, even if marked counted", HP.is_counted(three), False)
check("a 3-leg test is left out of every stat", HP.record(dict(picks=picks + [three]))["n"], 3)
check("market is read from the field or the ticker", (HP.market_of(dict(market="pra")), HP.market_of(dict(ticker="KXNBA1HTOTAL-X")), HP.market_of(dict(ticker="KXNBA1QTOTAL-X")), HP.market_of(dict(ticker="Z"))), ("PRA", "1H", "1Q", None))
mk = dict(picks=[dict(id="m1", kind="combo", counted=True, result="won", combo_price=0.5, legs=[dict(ticker="A", market="1Q", value=1.0), dict(ticker="B", market="PRA", value=1.0)]),
                 dict(id="m2", kind="combo", counted=True, result="lost", combo_price=0.5, legs=[dict(ticker="C", market="1H", value=1.0), dict(ticker="D", market="PRA", value=0.0)]),
                 dict(id="m3", kind="combo", counted=True, result="open", combo_price=0.5, legs=[dict(ticker="E", market="1Q"), dict(ticker="F", market="1H")])])
bm = HP.record(mk)["by_market"]
check("split by leg: 1Q 2 legs 1 won 1 open", (bm["1Q"]["legs"], bm["1Q"]["won"], bm["1Q"]["open"]), (2, 1, 1))
check("split by leg: 1H 2 legs 1 won 1 open", (bm["1H"]["legs"], bm["1H"]["won"], bm["1H"]["open"]), (2, 1, 1))
check("split by leg: PRA 2 legs 1 won 1 lost, hit rate 50%", (bm["PRA"]["legs"], bm["PRA"]["won"], bm["PRA"]["lost"], bm["PRA"]["rate"]), (2, 1, 1, 0.5))

print("\nthe page")
html = B.hand_section(st)
check("the section names the log, the counts, and that context picks are not counted", all(x in html for x in ("Hand picks · learning log", "3 of 10", "context picks are shown but not counted")), True)
check("each leg's result and price at placement", ("T2 · No at 70c · won" in html, "T3 · Yes at 80c · lost" in html), (True, True))
check("percentages and multiples only: no dollar sign", "$" in html, False)
check("no guarded phrase, no name", (sandbox_audit.COPY_RE.findall(html), "Olu" in html, "real money" in html), ([], False, False))
check("the market split is on the page", ("By market, leg by leg" in html, "Player PRA" in html), (True, True))
check("the section is on the Combo page", 'id="hand"' in B.build(CL.empty()), True)
check("the empty list reads as nothing logged yet", "No hand picks logged yet" in B.hand_section(dict(picks=[])), True)
check("the workflow settles it and adds its file", all(x in open(".github/workflows/sandbox-tracker.yml").read() for x in ("python3 hand_picks.py", "data/hand_picks.json")), True)

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
