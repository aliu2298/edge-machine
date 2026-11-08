#!/usr/bin/env python3
"""The Argentina dip Production feed, page inputs and snapshot publisher (arg_dip_production.py, arg_dip_publish.py): offline checks."""
import datetime as dt
import sys

import arg_dip_production as X
import arg_dip_publish as PUB

FAILS = []
UTC = dt.timezone.utc


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


NOW = dt.datetime(2026, 11, 9, 12, 0, tzinfo=UTC)


def occ(h):
    return (NOW + dt.timedelta(hours=h + 4)).strftime("%Y-%m-%dT%H:%M:%SZ")


def mkt(ev, h, strike=0.5, suffix="-1", status="active", result=""):
    return dict(ticker=ev + suffix, floor_strike=strike, status=status, result=result, occurrence_datetime=occ(h))


EVENTS = {"KXARGPREMDIVTOTAL": [dict(event_ticker="KXARGPREMDIVTOTAL-A", title="A v B", markets=[mkt("KXARGPREMDIVTOTAL-A", 3, strike=1.5, suffix="-2"), mkt("KXARGPREMDIVTOTAL-A", 3)]),
                         dict(event_ticker="KXARGPREMDIVTOTAL-OLD", title="old", markets=[mkt("KXARGPREMDIVTOTAL-OLD", -5)]),
                         dict(event_ticker="KXARGPREMDIVTOTAL-FAR", title="far", markets=[mkt("KXARGPREMDIVTOTAL-FAR", 48)]),
                         dict(event_ticker="KXARGPREMDIVTOTAL-CLOSED", title="c", markets=[mkt("KXARGPREMDIVTOTAL-CLOSED", 2, status="closed")]),
                         dict(event_ticker="KXARGPREMDIVTOTAL-JUST", title="j", markets=[mkt("KXARGPREMDIVTOTAL-JUST", -0.1)])],
          "KXMLSTOTAL": [dict(event_ticker="KXMLSTOTAL-M", title="m", markets=[mkt("KXMLSTOTAL-M", 2)])]}


def fetch(path):
    ser = path.split("series_ticker=")[1].split("&")[0]
    return {"events": EVENTS.get(ser, []), "cursor": None}


print("the feed")
rows, errs = X.leads(NOW, fetch)
check("only the open over 0.5 rung inside the window; a match just kicked off stays for the bid; far, closed, old out; MLS is not scanned",
      [r["event"] for r in rows], ["KXARGPREMDIVTOTAL-JUST", "KXARGPREMDIVTOTAL-A"])
a = rows[1]
check("the lead carries the rule: YES, 65%, $1, the -1 ticker", (a["side"], a["fraction"], a["stake_usd"], a["ticker"], a["version"]),
      ("yes", 0.65, 1.0, "KXARGPREMDIVTOTAL-A-1", "argdip-live-v1"))
check("kickoff is the occurrence time less 4 hours", a["kickoff"], (NOW + dt.timedelta(hours=3)).isoformat())
b = X.feed(NOW, fetch)
check("the header names the rule", (b["lane"], b["rule"]["fraction"], len(b["rule"]["leagues"])), ("arg_goalless_dip_live", 0.65, 1))
b2 = X.feed(NOW, lambda p: (_ for _ in ()).throw(ValueError("boom")))
check("every league failing is reported, not hidden", (len(b2["errors"]), b2["leads"]), (1, []))
import arg_dip_live as L
import arg_dip as T

print("the feed matches the executor's pinned terms")
check("the lead's terms are the pinned ones (version, lane, fraction, stake)", (a["version"], a["lane"], a["fraction"], a["stake_usd"]),
      ("argdip-live-v1", "arg_goalless_dip_live", 0.65, 1.0))

print("the page")
entry = dict(id="KXARGPREMDIVTOTAL-26NOV09ARSCHE-1", event="KXARGPREMDIVTOTAL-26NOV09ARSCHE", kickoff=int(NOW.timestamp()), matchday="2026-11-09", league="Argentina", result="yes",
             p=0.80, buys={"65": dict(limit=0.52, fill_at=int(NOW.timestamp()) + 300, counted=True, sold=True, payout=1.0)})
unfilled = dict(entry, id="KXARGPREMDIVTOTAL-26NOV09LIVEVE-1", buys={"65": None})
old = dict(entry, id="KXARGPREMDIVTOTAL-26NOV04OLDOLD-1", matchday="2026-11-04")
led = dict(entries=[entry, unfilled, old])
qs = X.quotes(led, dict(leads=[a]))
settled = [q for q in qs if q["status"] != "open"]
check("one settled quote (the filled, counted, post-move bid); an unfilled bid and an old matchday are not bets", len(settled), 1)
q = settled[0]
check("quote: YES over 0.5, bought at the limit, sold at P after maker fees", (q["sport"], q["pick"], q["price"], q["rule"]), ("soccer_o05", "a", 0.52, "sold at P"))
cost = 0.52 + 0.0175 * 0.52 * 0.48
proceeds = 0.80 - 0.0175 * 0.80 * 0.20
check("pnl is the after-fee exit, in percent of a 100 stake", q["pnl"], round((proceeds - cost) / cost * 100, 2))
check("an upcoming match is an open quote", [x["status"] for x in qs if x["status"] == "open"], ["open"])
check("the pair is a Production pair from the move date", X.pairs()["arg_goalless_dip_live|soccer_o05"]["stage"], "production")
d, st, blob = X.page_inputs(dict(quotes=[]), dict(pairs={}), dict(leads={}, pairs={}), led, now=NOW, leads_feed=dict(updated_at=NOW.isoformat(), leads=[a]))
check("page inputs add the quotes and the pair without touching the originals", (len(d["quotes"]), "arg_goalless_dip_live|soccer_o05" in st["pairs"]), (2, True))
d2, _s, _b = X.page_inputs(dict(quotes=[]), dict(pairs={}), dict(leads={}, pairs={}), led, now=NOW + dt.timedelta(hours=9),
                           leads_feed=dict(updated_at=NOW.isoformat(), leads=[a]))
check("a stale feed hides the upcoming matches", [x["status"] for x in d2["quotes"]], ["won"])

print("provisional entries on the page (the market has not settled)")
prov_sold = dict(entry, id="KXARGPREMDIVTOTAL-26NOV09EVECOV-1", result=None, provisional=True,
                 buys={"65": dict(limit=0.52, fill_at=int(NOW.timestamp()) + 300, counted=True, sold=True, payout=None)})
prov_held = dict(entry, id="KXARGPREMDIVTOTAL-26NOV09HSVBMG-1", result=None, provisional=True,
                 buys={"65": dict(limit=0.52, fill_at=int(NOW.timestamp()) + 300, counted=True, sold=False, payout=None)})
lead_same = dict(a, ticker="KXARGPREMDIVTOTAL-26NOV09EVECOV-1", id="arg_goalless_dip_live:KXARGPREMDIVTOTAL-26NOV09EVECOV-1")
pq = X.quotes(dict(entries=[prov_sold, prov_held]), dict(leads=[lead_same]))
by = {q["market_id"]: q for q in pq}
check("sold at P before settlement: a won trade, not the feed's open lead (one quote for the market)",
      (len(pq), by["KXARGPREMDIVTOTAL-26NOV09EVECOV-1"]["status"], by["KXARGPREMDIVTOTAL-26NOV09EVECOV-1"]["rule"], by["KXARGPREMDIVTOTAL-26NOV09EVECOV-1"]["result"]), (2, "won", "sold at P", None))
check("filled and held: open, worded as filled, open, with no P/L yet", (by["KXARGPREMDIVTOTAL-26NOV09HSVBMG-1"]["status"], by["KXARGPREMDIVTOTAL-26NOV09HSVBMG-1"]["rule"], by["KXARGPREMDIVTOTAL-26NOV09HSVBMG-1"]["pnl"]),
      ("open", "filled, open", 0.0))

print("the snapshot publisher")
good = {"decisions": {"KXARGPREMDIVTOTAL-26NOV09ARSCHE-1": dict(lane=L.LANE, bot_version=L.VERSION, ticker="KXARGPREMDIVTOTAL-26NOV09ARSCHE-1", event="KXARGPREMDIVTOTAL-26NOV09ARSCHE",
                                                          league="Argentina", matchday="2026-11-09", kickoff=NOW.isoformat(), outcome="planned", why=None, rule_ok=True,
                                                          P=0.8, limit=0.52, qty=2, yes_bid=0.78, yes_ask=0.8, spread=0.02, decided_at=NOW.isoformat())},
        "updated_at": NOW.isoformat()}
check("a clean snapshot file is published", sorted(PUB.sanitise(good)["decisions"]), ["KXARGPREMDIVTOTAL-26NOV09ARSCHE-1"])
def refused(mut):
    import copy
    blob = copy.deepcopy(good)
    mut(blob["decisions"]["KXARGPREMDIVTOTAL-26NOV09ARSCHE-1"])
    try:
        PUB.sanitise(blob)
        return False
    except PUB.Refused:
        return True
check("a balance field is refused", refused(lambda r: r.update(balance=12.5)), True)
check("an order id field is refused", refused(lambda r: r.update(order_id="x")), True)
check("a dollar sign in a reason is refused", refused(lambda r: r.update(why="free balance $0.50")), True)
check("a uuid in a reason is refused", refused(lambda r: r.update(why="order 9c64f55c-9239-5775-ac1a-f8c7c498cb53")), True)
check("an unknown outcome is refused", refused(lambda r: r.update(outcome="filled")), True)
check("a price outside 0-1 is refused", refused(lambda r: r.update(P=44.0)), True)
check("another lane is refused", refused(lambda r: r.update(lane="nba_winmargin_live")), True)



print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
