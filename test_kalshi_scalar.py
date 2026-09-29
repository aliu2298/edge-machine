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

print("\nA bad settlement number never pays")


def raw_market(**body):
    body.setdefault("status", "finalized")
    body.setdefault("result", "scalar")
    return {"market": body}


def stays_unpaid(payload, msg, **kw):
    q = grade_one(payload, **kw)
    eq((q["status"], q["result"], q["pnl"], q.get("settle_px")),
       ("void", "void", 0.0, None), msg)


stays_unpaid(raw_market(settlement_value_dollars="nan"),
             "NaN settlement_value_dollars is a void and pays nothing")
stays_unpaid(raw_market(settlement_value_dollars="inf"),
             "an infinite settlement is a void and pays nothing")
stays_unpaid(raw_market(settlement_value_dollars="-inf"),
             "a negative infinity is a void and pays nothing")
stays_unpaid(raw_market(settlement_value_dollars="-0.25"),
             "a negative settlement is a void and pays nothing")
stays_unpaid(raw_market(settlement_value_dollars="1.50"),
             "a settlement above 1 is a void and pays nothing")
stays_unpaid(raw_market(),
             "a scalar with no settlement number is a void and pays nothing")
stays_unpaid(raw_market(settlement_value_dollars="nan", settlement_value=26),
             "a NaN dollar field does not fall through to the cents field")

not_final = grade_one(raw_market(settlement_value_dollars="nan", status="active"))
eq((not_final["status"], not_final["result"], not_final["pnl"]),
   ("open", None, 0.0),
   "a non-final market with a bad number stays unsettled")

print("\nCents are cents, and a clean yes or no beats an expiration word")

one_cent = grade_one(raw_market(settlement_value=1), id="cents:1", pick="a",
                     price=0.40, price_a=0.40)
eq((one_cent["status"], one_cent["result"], one_cent["pnl"], one_cent.get("settle_px")),
   ("lost", "b", -100.0, None),
   "settlement_value 1 is one cent, the clean NO side, not a $1 win")

hundred = grade_one(raw_market(settlement_value=100), id="cents:100", pick="a",
                    price=0.40, price_a=0.40)
eq((hundred["status"], hundred["result"], hundred.get("settle_px")),
   ("won", "a", None),
   "settlement_value 100 is $1.00, the clean YES side")

twenty_six = grade_one(raw_market(settlement_value=26), id="cents:26", pick="a",
                       price=0.40, price_a=0.40)
eq((twenty_six["status"], twenty_six["result"], twenty_six.get("settle_px")),
   ("settled", "price", 0.26),
   "settlement_value 26 is $0.26, a price")
eq(twenty_six["pnl"], round(100.0 * (0.26 / 0.40 - 1.0), 2),
   "the cents fallback pays that price, not 26 dollars")

dollars_win = grade_one(raw_market(settlement_value_dollars="0.2600", settlement_value=1),
                        id="dollars-over-cents", pick="a", price=0.40, price_a=0.40)
eq(dollars_win.get("settle_px"), 0.26,
   "settlement_value_dollars wins when both fields are present")

yes_void_word = grade_one(market("yes", 1.0, expiration="void"), id="yes:exp-void",
                          pick="a", price=0.40, price_a=0.40)
eq((yes_void_word["status"], yes_void_word["result"], yes_void_word["pnl"]),
   ("won", "a", round(100.0 * (1.0 / 0.40 - 1.0), 2)),
   "a finalized yes stays a win when expiration_value is the word void")

no_void_word = grade_one(market("no", 0.0, expiration="cancelled"), id="no:exp-cancel",
                         pick="a", price=0.40, price_a=0.40)
eq((no_void_word["status"], no_void_word["result"], no_void_word["pnl"]),
   ("lost", "b", -100.0),
   "a finalized no stays a loss when expiration_value is the word cancelled")

cancel_status = grade_one(raw_market(result="", status="cancelled",
                                     expiration_value=""),
                          id="status:cancelled", pick="a", price=0.40)
eq((cancel_status["status"], cancel_status["result"], cancel_status["pnl"],
    cancel_status.get("settle_px")),
   ("void", "void", 0.0, None),
   "a cancelled status is a void, not left unsettled")

print("\nA combo basket with a scalar leg is re-graded inside the window")


def combo_quote(hours_ago):
    when = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()
    return quote(id="combo:dimrin", venue="combo",
                 market_id="combo2:2026-09-28:e4eec263a4", pick="a",
                 price=0.6134, price_a=0.6134, stake=100.0,
                 status="void", result="void", pnl=0.0, settled=when,
                 legs=[{"market_id": "KXATPCHALLENGERMATCH-26SEP28DIMRIN",
                        "pick": "a", "venue": "kalshi"},
                       {"market_id": "KXATPCHALLENGERMATCH-26SEP28KYMTOR",
                        "pick": "a", "venue": "kalshi"}])


def fake_event(event_ticker):
    ticker = str(event_ticker)
    if ticker.endswith("DIMRIN"):
        return ("price", 0.75)
    if ticker.endswith("KYMTOR"):
        return "a"
    return "void"


def grade_combo(q, mismatches):
    real_event = S.resolve_kalshi
    S.resolve_kalshi = fake_event
    try:
        T.grade({"quotes": [q], "meta": {}, "coverage": {}},
                verbose=False, mismatches=mismatches)
    finally:
        S.resolve_kalshi = real_event
    return q


recent_combo = grade_combo(combo_quote(12), set())
eq((recent_combo["status"], recent_combo["result"], recent_combo.get("settle_px")),
   ("settled", "price", 0.75),
   "a void basket inside 48h is re-graded when one leg paid 0.75 and the other won")
eq(recent_combo["pnl"], round(100.0 * (0.75 / 0.6134 - 1.0), 2),
   "the basket P/L is stake * (0.75 / entry - 1), about +22.27")

old_combo = grade_combo(combo_quote(100), set())
eq((old_combo["status"], old_combo["result"], old_combo["pnl"]),
   ("void", "void", 0.0),
   "the same basket older than 48h is left void by a plain grade()")

watched = combo_quote(100)
_prior = watched["settled"]
grade_combo(watched, {("combo", watched["market_id"])})
eq((watched["status"], watched["result"], watched.get("settle_px"), watched["pnl"]),
   ("settled", "price", 0.75, round(100.0 * (0.75 / 0.6134 - 1.0), 2)),
   "passing the basket in mismatches re-settles it however old it is")
eq(watched["settled"], _prior, "the watched re-settle keeps the original settled time")

print("\nA Polymarket US basket is not re-priced")


def pmus_basket(hours_ago, **kw):
    when = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()
    q = quote(id="pmcombo:81a09442cc", venue="combo",
              market_id="pmcombo2:2026-09-26:81a09442cc", pick="a",
              price=0.6168, price_a=0.6168, stake=100.0,
              status="settled", result="price", settle_px=0.77, pnl=24.84,
              settled=when,
              legs=[{"market_id": "aec-itfme-clapie-jirciz-2026-09-26",
                     "pick": "b", "venue": "polymarket_us"},
                    {"market_id": "aec-wta-annsis-ginfei-2026-09-26",
                     "pick": "a", "venue": "polymarket_us"}])
    q.update(kw)
    if q.get("settle_px") is None:
        q.pop("settle_px", None)
    return q


def fake_pmus_legs(slug):
    # The short leg pays 0.40. The other leg won, so the basket pays 0.40.
    if "jirciz" in str(slug):
        return ("price", 0.60)
    return "a"


def grade_pmus_basket(q, mismatches):
    real = S.resolve_polymarket_us
    S.resolve_polymarket_us = fake_pmus_legs
    try:
        T.grade({"quotes": [q], "meta": {}, "coverage": {}},
                verbose=False, mismatches=mismatches)
    finally:
        S.resolve_polymarket_us = real
    return q


in_window = grade_pmus_basket(pmus_basket(12), set())
eq((in_window["result"], in_window.get("settle_px"), in_window["pnl"]),
   ("price", 0.77, 24.84),
   "an in-window Polymarket US basket keeps 0.77 and is not re-priced to 0.40")

watched_px = pmus_basket(100)
grade_pmus_basket(watched_px, {("combo", watched_px["market_id"])})
eq((watched_px["result"], watched_px.get("settle_px"), watched_px["pnl"]),
   ("price", 0.77, 24.84),
   "a watched Polymarket US basket keeps its settle_px")

pmus_void_basket = grade_pmus_basket(
    pmus_basket(12, status="void", result="void", pnl=0.0, settle_px=None), set())
eq((pmus_void_basket["status"], pmus_void_basket["result"], pmus_void_basket["pnl"],
    pmus_void_basket.get("settle_px")),
   ("void", "void", 0.0, None),
   "a note-free Polymarket US basket void stays void")

watched_void = pmus_basket(100, status="void", result="void", pnl=0.0, settle_px=None)
grade_pmus_basket(watched_void, {("combo", watched_void["market_id"])})
eq((watched_void["status"], watched_void["result"], watched_void["pnl"],
    watched_void.get("settle_px")),
   ("void", "void", 0.0, None),
   "a watched note-free Polymarket US basket void stays void")

print("\nPolymarket US re-grade does not adopt the Kalshi price branch")


def pmus(slug):
    return ("price", 0.42)


_pmus_when = (datetime.now(timezone.utc) - timedelta(hours=12)).isoformat()
pmus_void = quote(id="pmus:void", venue="polymarket_us", market_id="some-market",
                  pick="a", price=0.50, price_a=0.50, status="void", result="void",
                  pnl=0.0, settled=_pmus_when)
pmus_price = quote(id="pmus:price", venue="polymarket_us", market_id="some-market",
                   pick="a", price=0.50, price_a=0.50, status="settled", result="price",
                   settle_px=0.30, pnl=round(100.0 * (0.30 / 0.50 - 1.0), 2),
                   settled=_pmus_when)
pmus_open = quote(id="pmus:open", venue="polymarket_us", market_id="some-market",
                  pick="a", price=0.50, price_a=0.50, status="open", result=None,
                  pnl=0.0, settled=None)
real_pmus = S.resolve_polymarket_us
S.resolve_polymarket_us = pmus
try:
    T.grade({"quotes": [pmus_void, pmus_price, pmus_open], "meta": {}, "coverage": {}},
            verbose=False, mismatches=set())
finally:
    S.resolve_polymarket_us = real_pmus
eq((pmus_void["status"], pmus_void["result"], pmus_void["pnl"], pmus_void.get("settle_px")),
   ("void", "void", 0.0, None),
   "a no-note Polymarket US void stays void when the venue now returns a price")
eq((pmus_price["result"], pmus_price.get("settle_px"), pmus_price["pnl"]),
   ("price", 0.30, round(100.0 * (0.30 / 0.50 - 1.0), 2)),
   "an existing Polymarket US price row is not re-priced")
eq((pmus_open["status"], pmus_open["result"], pmus_open.get("settle_px")),
   ("settled", "price", 0.42),
   "an open Polymarket US quote still settles at the price on the first pass")
eq(pmus_open["pnl"], round(100.0 * (0.42 / 0.50 - 1.0), 2),
   "that first pass pays stake * (settlement / entry - 1)")

print(f"\n{'FAILED: ' + str(len(FAILS)) if FAILS else 'all kalshi scalar tests passed'}")
for f in FAILS:
    print("   -", f)
sys.exit(1 if FAILS else 0)
