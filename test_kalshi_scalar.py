#!/usr/bin/env python3
"""Kalshi scalar settlements pay the fair value. Fixture data, no network.

A finalized market whose settlement is strictly between the clean 0 and 1
bands, including exactly 0.5, is result 'price' at that value. YES is paid
the settlement. NO is paid one minus it. A cancel stays void. A clean yes
or no is unchanged.
"""
import sys
from datetime import datetime, timedelta, timezone

import sandbox_sources as S
import sandbox_track as T

FAILS = []


def ok(cond, msg):
    print(("  ok   " if cond else "  FAIL ") + msg)
    if not cond:
        FAILS.append(msg)


def eq(got, want, msg):
    ok(got == want, msg if got == want else f"{msg} (got {got!r}, want {want!r})")


def close(got, want, msg, tol=1e-9):
    ok(got is not None and abs(got - want) < tol,
       msg if got is not None and abs(float(got) - want) < tol else f"{msg} (got {got!r}, want ~{want!r})")


def quote(**kw):
    q = dict(id="s:1", source="p05_unbeaten", sport="soccer_p05", market_id="KX-M",
             label="Yes vs No", side_a="Yes", side_b="No", url="", date="2026-09-26",
             start=(datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
             logged=(datetime.now(timezone.utc) - timedelta(days=3)).isoformat(),
             prob_a=None, price_a=0.32, price_b=0.69, pick="a", edge=None,
             price=0.40, bet=True, stake=100.0, untraded=False, venue="kalshi_binary",
             status="open", pnl=0.0, result=None, settled=None)
    q.update(kw)
    return q


def market(result, settlement=None, status="finalized", expiration=""):
    body = {"status": status, "result": result, "expiration_value": expiration}
    if settlement is not None:
        body["settlement_value_dollars"] = f"{float(settlement):.4f}"
    return {"market": body}


def grade_one(payload, **kw):
    q = quote(**kw)
    real = S._get
    S._get = lambda url, **k: payload
    try:
        T.grade({"quotes": [q], "meta": {}, "coverage": {}}, verbose=False, mismatches=set())
    finally:
        S._get = real
    return q


print("\nKalshi scalar settlement pays the settled value")

yes = grade_one(market("scalar", 0.26), id="yes:0.26", pick="a", price=0.40, price_a=0.40)
eq((yes["status"], yes["result"], yes.get("settle_px")), ("settled", "price", 0.26),
   "a 0.26 YES settlement is result price, paid 0.26")
eq(yes["pnl"], round(100.0 * (0.26 / 0.40 - 1.0), 2),
   "YES P/L is stake * (settlement / entry - 1)")

no = grade_one(market("scalar", 0.26), id="no:0.26", pick="b", price=0.69, price_b=0.69)
eq((no["status"], no["result"], no.get("settle_px")), ("settled", "price", round(1.0 - 0.26, 6)),
   "a NO buyer on the same market is paid one minus 0.26")
eq(no["pnl"], round(100.0 * ((1.0 - 0.26) / 0.69 - 1.0), 2),
   "NO P/L is stake * ((1 - settlement) / entry - 1)")

half = grade_one(market("scalar", 0.5, expiration="No Result (50/50)"),
                 id="yes:0.5", pick="a", price=0.40, price_a=0.40)
eq((half["status"], half["result"], half.get("settle_px")), ("settled", "price", 0.5),
   "exactly 0.5, including a no-result fair value, is a price and not a void")
eq(half["pnl"], round(100.0 * (0.5 / 0.40 - 1.0), 2),
   "a 0.5 YES buyer is paid 0.5")

print("\nKalshi cancel stays void, and a clean 0 or 1 is unchanged")

blank = grade_one(market(""), id="cancel:blank", pick="a", price=0.40)
eq((blank["status"], blank["result"], blank["pnl"], blank.get("settle_px")),
   ("void", "void", 0.0, None),
   "a finalized market with a blank result is a void and pays nothing")

word = grade_one(market("void"), id="cancel:void", pick="b", price=0.69)
eq((word["status"], word["result"], word["pnl"]), ("void", "void", 0.0),
   "an explicit void result stays a void")

clean_yes = grade_one(market("yes", 1.0), id="clean:yes", pick="a", price=0.40, price_a=0.40)
eq((clean_yes["status"], clean_yes["result"], clean_yes.get("settle_px")), ("won", "a", None),
   "a yes result is still a win for the YES side")
eq(clean_yes["pnl"], round(100.0 * (1.0 / 0.40 - 1.0), 2),
   "and it still pays stake * (1 / entry - 1)")

clean_no = grade_one(market("no", 0.0), id="clean:no", pick="a", price=0.40, price_a=0.40)
eq((clean_no["status"], clean_no["result"], clean_no["pnl"]), ("lost", "b", -100.0),
   "a no result is still a loss for the YES side, stake gone")

scalar_one = grade_one(market("scalar", 1.0), id="scalar:1", pick="a", price=0.40, price_a=0.40)
eq((scalar_one["status"], scalar_one["result"]), ("won", "a"),
   "a scalar settlement of 1 is the clean YES side, not a price")

scalar_zero = grade_one(market("scalar", 0.0), id="scalar:0", pick="b", price=0.69, price_b=0.69)
eq((scalar_zero["status"], scalar_zero["result"]), ("won", "b"),
   "a scalar settlement of 0 is the clean NO side")

open_m = grade_one(market("scalar", 0.26, status="active"), id="open:scalar")
eq(open_m["status"], "open", "a scalar that is not final is not settled")

print("\nA void with no note is re-settled when the venue's scalar is final")

_when = (datetime.now(timezone.utc) - timedelta(hours=12)).isoformat()
voided = quote(id="void:no-note", pick="b", price=0.69, price_b=0.69,
               status="void", result="void", pnl=0.0, settled=_when)
noted = quote(id="void:noted", pick="b", price=0.69, price_b=0.69,
              status="void", result="void", pnl=0.0, note=T.DUPLICATE_NOTE,
              settled=_when)
real = S._get
S._get = lambda url, **k: market("scalar", 0.26)
try:
    T.grade({"quotes": [voided, noted], "meta": {}, "coverage": {}},
            verbose=False, mismatches=set())
finally:
    S._get = real
eq((voided["status"], voided["result"], voided.get("settle_px")),
   ("settled", "price", round(1.0 - 0.26, 6)),
   "a resolver void is re-settled at the price when the venue says scalar")
eq(voided["pnl"], round(100.0 * ((1.0 - 0.26) / 0.69 - 1.0), 2),
   "the re-settled NO P/L uses the same payout")
eq(voided["settled"], _when, "re-settling keeps the original settled time")
eq((noted["status"], noted["result"], noted["pnl"], noted.get("settle_px")),
   ("void", "void", 0.0, None),
   "a noted duplicate void stays void")

print("\nA two-way event uses the complement; a three-way event pays each contract")


def leg(event_ticker, code, title, settlement):
    return dict(ticker=f"{event_ticker}-{code}", event_ticker=event_ticker,
                yes_sub_title=title, status="finalized", result="scalar",
                settlement_value_dollars=f"{float(settlement):.4f}")


def resolve_event(event_ticker, legs):
    real_get = S._get
    S._get = lambda url, **k: {"markets": legs}
    try:
        return S.resolve_kalshi(event_ticker)
    finally:
        S._get = real_get


two = resolve_event("KXATPMATCH-26SEP21BORUGO", [
    leg("KXATPMATCH-26SEP21BORUGO", "BOR", "Bor", 0.79),
    leg("KXATPMATCH-26SEP21BORUGO", "UGO", "Ugo", 0.21),
])
eq(two, ("price", 0.79), "a two-way scalar event is the home side's settlement")
if not hasattr(S, "price_paid"):
    ok(False, "price_paid pays each side from the venue settlement")
else:
    eq(S.price_paid("a", two), 0.79, "the home side is paid 0.79")
    eq(round(S.price_paid("b", two), 6), 0.21,
       "the away side is paid one minus 0.79, at the cent the row stores")

three = resolve_event("KXMLSGAME-26SEP26NYRBSTL", [
    leg("KXMLSGAME-26SEP26NYRBSTL", "NYRB", "New York", 0.26),
    leg("KXMLSGAME-26SEP26NYRBSTL", "STL", "St. Louis", 0.52),
    leg("KXMLSGAME-26SEP26NYRBSTL", "TIE", "Tie", 0.22),
])
if hasattr(S, "_price_result"):
    eq(S._price_result(three), 0.26, "a three-way scalar event's long number is the home settlement")
else:
    ok(False, "a three-way scalar event exposes its home settlement")
if hasattr(S, "price_paid"):
    eq(S.price_paid("a", three), 0.26, "home is paid its own contract")
    eq(S.price_paid("b", three), 0.52, "away is paid its own contract, not one minus home")
    eq(S.price_paid("draw", three), 0.22, "the draw is paid its own contract")

cancelled = resolve_event("KXEPLGAME-26SEP06ARSCFC", [
    dict(ticker="KXEPLGAME-26SEP06ARSCFC-ARS", yes_sub_title="Arsenal",
         status="finalized", result="no"),
    dict(ticker="KXEPLGAME-26SEP06ARSCFC-CFC", yes_sub_title="Chelsea",
         status="finalized", result="no"),
    dict(ticker="KXEPLGAME-26SEP06ARSCFC-TIE", yes_sub_title="Tie",
         status="finalized", result="no"),
])
eq(cancelled, "void", "every side no, with no scalar value, stays a void")

print(f"\n{'FAILED: ' + str(len(FAILS)) if FAILS else 'all kalshi scalar tests passed'}")
for f in FAILS:
    print("   -", f)
sys.exit(1 if FAILS else 0)
