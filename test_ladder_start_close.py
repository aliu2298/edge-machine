#!/usr/bin/env python3
"""A daily-close ladder rung starts at its market's own close (2026-11-04).

KXWTI-26NOV03 (the WTI event format with no hour suffix) closed on 2026-11-03T19:30Z but carries an
expected_expiration_time of 2026-11-04T15:00Z, the next morning. The row's start came from the expiration, so a Nov 3
contract became a Nov 4 Production lead and shared its contest name with that day's real lead. Offline."""
import datetime as dt
import sys

import sandbox_sources as S
import sandbox_track as T

FAILS = []


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


def market(ticker, close, exp, price=0.75):
    return dict(ticker=ticker, event_ticker=ticker.rsplit("-", 1)[0], title="WTI settle", yes_sub_title="Above",
                close_time=close, expected_expiration_time=exp, yes_ask_dollars=str(price), yes_bid_dollars=str(price - 0.01),
                no_ask_dollars=str(1 - price + 0.01), no_bid_dollars=str(1 - price))


OLD = market("KXWTI-26NOV03-T94.99", "2026-11-03T19:30:00Z", "2026-11-04T15:00:00Z")      # no hour suffix: expires next morning
NEW = market("KXWTI-26NOV0314-T94.99", "2026-11-03T19:30:00Z", "2026-11-03T19:30:00Z")     # hourly format: expiry = close
COIN = market("KXBTCD-26NOV0317-T80000", "2026-11-03T21:00:00Z", "2026-11-03T21:05:00Z")    # five minutes, left as it was
exp = lambda m: dt.datetime.fromisoformat(m["expected_expiration_time"].replace("Z", "+00:00"))

print("ladder_start")
check("the no-hour WTI event starts at its close, the day before its expiration",
      S.ladder_start(OLD, exp(OLD)).isoformat(), "2026-11-03T19:30:00+00:00")
check("the hourly format is unchanged", S.ladder_start(NEW, exp(NEW)).isoformat(), "2026-11-03T19:30:00+00:00")
check("a five-minute gap (the coin ladders) is left as it was", S.ladder_start(COIN, exp(COIN)).isoformat(), "2026-11-03T21:05:00+00:00")
check("no close_time: the expiration stands", S.ladder_start(dict(OLD, close_time=None), exp(OLD)).isoformat(), "2026-11-04T15:00:00+00:00")

print("\nthe rows the Sandbox logs")
now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0, second=0)
close = now + dt.timedelta(hours=3)
iso = lambda t: t.isoformat().replace("+00:00", "Z")
old_m = market("KXWTI-26NOV03-T94.99", iso(close), iso(close + dt.timedelta(hours=19, minutes=30)))
new_m = market("KXWTI-26NOV0314-T94.99", iso(close), iso(close))
_open = S._kalshi_open
S._kalshi_open = lambda series: [old_m, new_m] if series == "KXWTI" else []
try:
    rows = S.fetch_kalshi_binary("commodities_fav", horizon_days=30)
finally:
    S._kalshi_open = _open
by = {r["market_id"]: r for r in rows}
check("both WTI formats log the market's close as start and its date",
      sorted((r["market_id"], r["start"], r["date"]) for r in rows),
      [("KXWTI-26NOV03-T94.99", close.isoformat(), close.strftime("%Y-%m-%d")), ("KXWTI-26NOV0314-T94.99", close.isoformat(), close.strftime("%Y-%m-%d"))])
check("the market payload is untouched", by["KXWTI-26NOV03-T94.99"]["market"]["expected_expiration_time"], old_m["expected_expiration_time"])
check("only the ladder domains take the close", {"crypto", "crypto_fav", "commodities", "commodities_fav", "economics", "finance"} == S.LADDER_START_AT_CLOSE, True)

print("\nthe committed record")
d = T.load()
fixed = {q["id"]: q for q in d["quotes"] if q.get("id") in ("commod_fav_band:KXWTI-26NOV03-T94.99", "commod_nc_no:KXWTI-26NOV03-T96.99")}
check("the two mislabelled quotes are on Nov 3 at 19:30Z, results kept",
      sorted((i, q["start"], q["date"], q["status"]) for i, q in fixed.items()),
      [("commod_fav_band:KXWTI-26NOV03-T94.99", "2026-11-03T19:30:00+00:00", "2026-11-03", "won"),
       ("commod_nc_no:KXWTI-26NOV03-T96.99", "2026-11-03T19:30:00+00:00", "2026-11-03", "won")])
import production as P
# Either WTI ticker format (KXWTI-26NOV03-... or KXWTI-26NOV0314-...): the feed re-keyed the lead on the
# 26NOV0314 market after the fix, and it is the same Nov 3 lead with the same result.
leads = [l for l in P.load_feed()["leads"].values() if "|KXWTI-26NOV03" in l["id"]]
check("the Production lead is a Nov 3 lead with its graded result",
      [(l["date"], l["kickoff"], l["match"], l["status"], l["id"].startswith("2026-11-03|")) for l in leads],
      [("2026-11-03", "2026-11-03T19:30Z", "WTI crude close on Nov 3, 2026", "hit", True)])

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
